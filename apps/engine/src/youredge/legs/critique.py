"""Critique a same-game parlay against the empirical joint.

What this answers, and what it refuses to, are both deliberate.

It answers: is any single leg priced badly against the sharpest book; are two of
these legs the same bet wearing different names; do any of them want the game to
go in opposite directions; and which script does the slip as a whole need. Every
claim carries the number of games behind it.

It refuses to answer what the parlay is worth. The marginals in `leg_pair_stats`
are historical base rates rather than this game's fair probabilities, and most of
the lines behind them are synthetic. Multiplying them into an expected value
would produce a number that looks like a price and is not one. That waits for the
simulator — and when it arrives, the disagreement between it and this surface is
the check, which is only possible because this was built without it.
"""

import logging
import re
from typing import Any

from sqlalchemy import text

from youredge.pricing.fair_value import price_leg

log = logging.getLogger(__name__)

# Two legs this correlated are one leg. Whatever the second one costs, it is
# buying almost nothing the first did not already buy.
REDUNDANT_PHI = 0.80
# Opposite enough that the slip needs the game to do two different things.
CONFLICT_PHI = -0.20
MIN_N = 100


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


async def parse_leg(conn, game_id: str, raw: str) -> dict[str, Any] | None:
    """Map a free-text leg onto a template, a market and a side.

    Deliberately narrow. Anything it cannot read confidently comes back as
    unparsed and is reported to the user rather than guessed at — a leg quietly
    matched to the wrong template would poison every diagnostic built on it.
    Richer phrasing is the narrator's job in Phase 3; this is the deterministic
    core underneath it.
    """
    teams = (await conn.execute(text("""
        SELECT g.home_team_id, g.away_team_id,
               ht.name AS home_name, ht.abbr AS home_abbr,
               at.name AS away_name, at.abbr AS away_abbr
        FROM games g
        JOIN teams ht ON ht.team_id = g.home_team_id
        JOIN teams at ON at.team_id = g.away_team_id
        WHERE g.game_id = :gid
    """), {"gid": game_id})).mappings().first()
    if not teams:
        return None

    t = _norm(raw)
    home_tokens = {_norm(teams["home_name"]), _norm(teams["home_abbr"])}
    away_tokens = {_norm(teams["away_name"]), _norm(teams["away_abbr"])}

    def side_of(text_: str) -> str | None:
        for tok in home_tokens:
            if tok and tok in text_:
                return "home"
        for tok in away_tokens:
            if tok and tok in text_:
                return "away"
        return None

    num = re.search(r"([+-]?\d+(?:\.\d+)?)", t)
    value = float(num.group(1)) if num else None

    # over/under on the game total
    if re.search(r"\b(over|under)\b", t) and "team total" not in t:
        ou = "over" if "over" in t else "under"
        return {"template": "TOTAL", "side": ou, "market_key": "totals",
                "outcome": ou.capitalize(), "line": value}

    team = side_of(t)
    if team and "team total" in t:
        ou = "over" if "over" in t else "under"
        return {"template": "TEAM_TOTAL", "side": f"{team}_{ou}",
                "market_key": "team_totals", "outcome": ou.capitalize(),
                "line": value}

    if team and re.search(r"\b(ml|moneyline|money line|to win)\b", t):
        name = teams[f"{team}_name"]
        return {"template": "MONEYLINE", "side": team, "market_key": "h2h",
                "outcome": name, "line": None}

    if team and value is not None:
        name = teams[f"{team}_name"]
        return {"template": "SPREAD", "side": team, "market_key": "spreads",
                "outcome": name, "line": value}

    return None


async def critique(conn, game_id: str, league: str, sportsbook: str,
                   raw_legs: list[str], quoted_odds: str | None) -> dict[str, Any]:
    parsed, unparsed = [], []
    for raw in raw_legs:
        leg = await parse_leg(conn, game_id, raw)
        (parsed.append({**leg, "raw": raw}) if leg else unparsed.append(raw))

    # --- per-leg fair value, which needs no model
    for leg in parsed:
        p = await price_leg(conn, game_id, leg["market_key"], leg["outcome"],
                            leg["line"], sportsbook)
        leg["pricing"] = {
            "book": p.book, "book_price": p.book_price,
            "anchor_book": p.anchor_book,
            "fair_prob": round(p.fair_prob, 4) if p.fair_prob else None,
            "book_implied": round(p.book_implied, 4) if p.book_implied else None,
            "edge": round(p.edge, 4) if p.edge is not None else None,
            "stale_seconds": p.stale_seconds,
            "stale_after_seconds": p.stale_after_seconds,
            # An edge computed off a stale line is not an edge; say so rather
            # than let the number stand on its own.
            "quotable": bool(p.edge is not None and not p.is_stale),
        }

    # --- pairwise relationships, straight from the counted surface
    pairs = []
    for i, a in enumerate(parsed):
        for b in parsed[i + 1:]:
            key = sorted([(a["template"], a["side"]), (b["template"], b["side"])])
            row = (await conn.execute(text("""
                SELECT n, p_a, p_b, p_ab, phi, lift FROM leg_pair_stats
                WHERE league = :lg AND script_tag = ''
                  AND template_a = :ta AND side_a = :sa
                  AND template_b = :tb AND side_b = :sb
            """), {"lg": league, "ta": key[0][0], "sa": key[0][1],
                   "tb": key[1][0], "sb": key[1][1]})).mappings().first()
            if not row:
                pairs.append({"legs": [a["raw"], b["raw"]], "verdict": "no_sample",
                              "detail": "these two legs have not co-occurred often "
                                        "enough to say anything"})
                continue

            phi, n = row["phi"], row["n"]
            verdict = "independent"
            if phi is not None and n >= MIN_N:
                if phi >= REDUNDANT_PHI:
                    verdict = "redundant"
                elif phi <= CONFLICT_PHI:
                    verdict = "script_conflict"
                elif phi > 0.2:
                    verdict = "correlated"
            pairs.append({
                "legs": [a["raw"], b["raw"]], "verdict": verdict,
                "phi": round(phi, 3) if phi is not None else None,
                "p_both": round(row["p_ab"], 3),
                "lift": round(row["lift"], 2) if row["lift"] else None,
                "n": n,
            })

    # --- which scripts this slip needs, by how the pairs behave inside each
    scripts = []
    if len(parsed) >= 2:
        a, b = parsed[0], parsed[1]
        key = sorted([(a["template"], a["side"]), (b["template"], b["side"])])
        # The tag's own description travels with it. The vocabulary is expected
        # to keep growing, so any label map living in the frontend would be
        # stale the day after the next tag is seeded.
        rows = (await conn.execute(text("""
            SELECT s.script_tag, s.n, s.phi, t.description
            FROM leg_pair_stats s
            LEFT JOIN tags t ON t.slug = s.script_tag AND t.dimension = 'script'
            WHERE s.league = :lg AND s.script_tag <> ''
              AND s.template_a = :ta AND s.side_a = :sa
              AND s.template_b = :tb AND s.side_b = :sb
              AND s.n >= 100 AND s.phi IS NOT NULL
            ORDER BY s.phi DESC
        """), {"lg": league, "ta": key[0][0], "sa": key[0][1],
               "tb": key[1][0], "sb": key[1][1]})).mappings().all()
        scripts = [{"script": r["script_tag"], "phi": round(r["phi"], 3),
                    "n": r["n"], "description": r["description"]}
                   for r in rows]

    return {
        "game_id": game_id,
        "legs": [{k: v for k, v in leg.items() if k != "market_key"} for leg in parsed],
        "unparsed_legs": unparsed,
        "pairs": pairs,
        "script_sensitivity": scripts,
        "quoted_odds": quoted_odds,
        # Stated in the payload, not just the docs, so no caller can render a
        # combined number by accident.
        "combined_price": None,
        "combined_price_unavailable": (
            "Pricing a parlay needs this game's joint distribution. What is here is "
            "how often these legs won together historically — enough to spot "
            "redundancy and script conflict, not enough to quote a fair price. "
            "The simulator is what closes that gap."
        ),
    }
