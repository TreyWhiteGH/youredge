"""Test a stated theory against history, and then against the price.

Two questions, in order, because answering only the first is how people lose
money confidently:

  1. Is it true? Take the claim, restrict to the games where its condition held,
     and compare the leg's hit rate there against its hit rate everywhere.
  2. Is it already in the price? A true theory the market has also noticed is not
     an edge. "Real but fully priced" is the most common honest answer and is
     returned as a first-class verdict rather than buried.

    conditional rate  vs  base rate      -> is it real
    conditional rate  vs  today's price  -> is it worth anything

One distinction is enforced rather than left to the reader. Conditions divide
into what was knowable before kickoff — who is favoured, by how much, home or
away — and what only became true during the game, which is every script label.
A claim conditioned on a script describes games that turned out that way; it
cannot tell anyone what to bet beforehand, because you do not know at kickoff
whether this one will. Those results come back flagged `retrospective` and carry
no price comparison, because comparing them to a price would imply a bet that
cannot be placed.
"""

import logging
import math
import re
from typing import Any

from sqlalchemy import text

from youredge.pricing.fair_value import price_leg

log = logging.getLogger(__name__)

MIN_SAMPLE = 80
# Two standard errors on the difference of proportions. Not a p-value ritual —
# just a floor beneath which a gap is indistinguishable from noise.
Z_REAL = 2.0
# How close the market has to be before a true theory counts as already priced.
PRICED_WITHIN = 0.03

# Claim keywords -> the leg template they assert.
CLAIMS: list[tuple[str, tuple[str, str]]] = [
    (r"\b(over|overs|high[- ]scoring|shootout|points)\b", ("TOTAL", "over")),
    (r"\b(under|unders|low[- ]scoring|grind|defensive)\b", ("TOTAL", "under")),
    (r"\b(cover|covers|ats|against the spread)\b", ("SPREAD", "")),
    (r"\b(win|wins|outright|moneyline|upset)\b", ("MONEYLINE", "")),
    (r"\b(blowout|blow out|double.?digit)\b", ("MARGIN", "double_digit")),
    (r"\b(close|one score|nail.?biter)\b", ("MARGIN", "one_score")),
]

# Pre-kickoff conditions: knowable in advance, so a claim built on them is
# actionable.
PREGAME = {
    "favorite": (r"\b(favorite|favoured|favored|favourite|chalk|laying)\b",
                 "gf.closing_spread * (CASE WHEN :tside = 'home' THEN 1 ELSE -1 END) < 0"),
    "underdog": (r"\b(underdog|dog|getting points|plus money)\b",
                 "gf.closing_spread * (CASE WHEN :tside = 'home' THEN 1 ELSE -1 END) > 0"),
    "home":     (r"\b(at home|home)\b", ":tside = 'home'"),
    "away":     (r"\b(on the road|road|away)\b", ":tside = 'away'"),
    "big_total":(r"\b(big total|high total)\b", "gf.closing_total >= 48"),
    "low_total":(r"\b(low total|small total)\b", "gf.closing_total <= 42"),
}


def _z(p1: float, n1: int, p0: float, n0: int) -> float | None:
    """Z on the difference of two proportions."""
    if n1 < 2 or n0 < 2:
        return None
    se = math.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
    return (p1 - p0) / se if se > 0 else None


async def parse(conn, league: str, game_id: str, raw: str) -> dict[str, Any] | None:
    """Turn a stated theory into a template, a side and a set of conditions."""
    t = re.sub(r"\s+", " ", raw.strip().lower())
    if not t:
        return None

    claim = next(((tpl, side) for pat, (tpl, side) in CLAIMS if re.search(pat, t)), None)
    if not claim:
        return None
    template, side = claim

    # A team named anywhere in the theory scopes it to that team's games.
    rows = (await conn.execute(text(
        "SELECT team_id, name, abbr FROM teams WHERE league = :lg"), {"lg": league}
    )).mappings().all()
    tokens = set(re.findall(r"[a-z0-9']+", t))
    team = None
    best = 0
    for r in rows:
        name = r["name"].lower()
        words = [w for w in re.findall(r"[a-z0-9']+", name) if len(w) > 2]
        # Score by how much of the team's name the theory actually named, so
        # "New York Giants" beats "New York Jets" on the full phrase and neither
        # wins on the city alone.
        hit = sum(len(w) for w in words if w in tokens)
        if name in t:
            hit += 100
        if r["abbr"].lower() in tokens:
            hit += 50
        if hit > best:
            best, team = hit, r
    # A single shared city token is not an identification.
    if best and best < 4:
        team = None

    conditions = [k for k, (pat, _) in PREGAME.items() if re.search(pat, t)]

    scripts = [r[0] for r in (await conn.execute(text(
        "SELECT slug FROM tags WHERE dimension = 'script'"))).all()
        if re.search(r"\b" + r[0].lower().replace("_", "[ _]") + r"\b", t)]

    return {"template": template, "side": side, "team": dict(team) if team else None,
            "conditions": conditions, "scripts": scripts, "raw": raw}


async def evaluate(conn, league: str, game_id: str, sportsbook: str,
                   raw: str) -> dict[str, Any]:
    spec = await parse(conn, league, game_id, raw)
    if not spec:
        return {
            "hypothesis": raw, "verdict": "unreadable",
            "detail": ("No testable claim found. This engine reads theories about "
                       "covering, winning, totals and margins, optionally scoped to a "
                       "team and to pre-game conditions like favourite, underdog, "
                       "home or road. Free-form phrasing is the narrator's job in "
                       "Phase 3; nothing is guessed at here."),
        }

    team, side = spec["team"], spec["side"]
    needs_team = {"favorite", "underdog", "home", "away"}
    if not team and needs_team & set(spec["conditions"]):
        return {
            "hypothesis": raw, "verdict": "unreadable",
            "reading": {"claim": f"{spec['template']} {spec['side']}".strip(),
                        "team": None, "pregame_conditions": spec["conditions"],
                        "script_conditions": spec["scripts"]},
            "detail": ("This theory conditions on being a favourite, an underdog, "
                       "home or away, but names no team — so there is no side to "
                       "apply it to. Name the team you mean."),
        }
    # Which side of each game the claim is about. A team-scoped claim follows the
    # team; an unscoped one is read from the home side.
    tside_sql = ("CASE WHEN g.home_team_id = :team THEN 'home' ELSE 'away' END"
                 if team else "'home'")

    where, params = [], {"lg": league}
    if team:
        params["team"] = team["team_id"]
        where.append("(g.home_team_id = :team OR g.away_team_id = :team)")
    for cond in spec["conditions"]:
        where.append(PREGAME[cond][1].replace(":tside", f"({tside_sql})"))
    for i, slug in enumerate(spec["scripts"]):
        params[f"script{i}"] = slug
        where.append(f"""EXISTS (SELECT 1 FROM taggings tg JOIN tags tt
                          ON tt.tag_id = tg.tag_id AND tt.slug = :script{i}
                          WHERE tg.entity_type = 'game' AND tg.entity_id = g.game_id)""")

    # SPREAD and MONEYLINE are sided; TOTAL and MARGIN are not.
    side_sql = (f"lo.side = ({tside_sql})" if side == "" else "lo.side = :side")
    if side:
        params["side"] = side

    base = (await conn.execute(text(f"""
        SELECT count(*) AS n, avg(lo.hit::int)::float8 AS p
        FROM leg_outcomes lo JOIN games g USING (game_id)
        WHERE g.league = :lg AND lo.template = :tpl AND lo.hit IS NOT NULL
          AND {side_sql.replace(':side', "'" + (side or '') + "'") if side else side_sql}
    """), {**params, "tpl": spec["template"]})).mappings().first()

    cond_sql = (" AND " + " AND ".join(where)) if where else ""
    conditional = (await conn.execute(text(f"""
        SELECT count(*) AS n, avg(lo.hit::int)::float8 AS p
        FROM leg_outcomes lo
        JOIN games g USING (game_id)
        LEFT JOIN game_features gf ON gf.game_id = g.game_id
        WHERE g.league = :lg AND lo.template = :tpl AND lo.hit IS NOT NULL
          AND {side_sql.replace(':side', "'" + (side or '') + "'") if side else side_sql}
          {cond_sql}
    """), {**params, "tpl": spec["template"]})).mappings().first()

    # Postgres avg() is numeric, which asyncpg hands back as Decimal, and Decimal
    # will not divide against the floats every calculation below uses. Coerce at
    # the boundary rather than casting in five places downstream.
    def _f(v):
        return float(v) if v is not None else None

    n_c, p_c = conditional["n"], _f(conditional["p"])
    n_b, p_b = base["n"], _f(base["p"])
    z = _z(p_c, n_c, p_b, n_b) if (p_c is not None and p_b is not None) else None

    retrospective = bool(spec["scripts"])
    # Direction matters. A theory can be significantly *wrong*, and telling
    # someone their read is real but backwards is worth more than calling it
    # supported because the gap was large. Magnitude alone conflates the two.
    strong = bool(n_c >= MIN_SAMPLE and z is not None and abs(z) >= Z_REAL)
    supported = strong and z > 0
    contradicted = strong and z < 0

    # --- is it priced? only meaningful for a claim you could actually bet
    market = None
    if supported and not retrospective:
        market_key = {"TOTAL": "totals", "SPREAD": "spreads",
                      "MONEYLINE": "h2h"}.get(spec["template"])
        if market_key:
            outcome = (spec["side"].capitalize() if spec["template"] == "TOTAL"
                       else (team["name"] if team else None))
            if outcome:
                p = await price_leg(conn, game_id, market_key, outcome, None, sportsbook)
                if p.fair_prob is not None:
                    market = {
                        "fair_prob": round(p.fair_prob, 4), "anchor_book": p.anchor_book,
                        "book_price": p.book_price,
                        "gap_vs_history": round(p_c - p.fair_prob, 4),
                    }

    if contradicted:
        verdict = "contradicted"
    elif not supported:
        verdict = "unsupported" if n_c >= MIN_SAMPLE else "insufficient_sample"
    elif retrospective:
        verdict = "supported_retrospective"
    elif market and abs(market["gap_vs_history"]) <= PRICED_WITHIN:
        verdict = "supported_but_priced"
    elif market and market["gap_vs_history"] > PRICED_WITHIN:
        verdict = "supported_and_unpriced"
    else:
        verdict = "supported_no_price"

    return {
        "hypothesis": raw,
        "reading": {
            "claim": f"{spec['template']} {spec['side']}".strip(),
            "team": team["name"] if team else None,
            "pregame_conditions": spec["conditions"],
            "script_conditions": spec["scripts"],
        },
        "history": {
            "conditional_rate": round(p_c, 4) if p_c is not None else None,
            "conditional_n": n_c,
            "base_rate": round(p_b, 4) if p_b is not None else None,
            "base_n": n_b,
            "lift": round(p_c / p_b, 3) if (p_c and p_b) else None,
            "z": round(z, 2) if z is not None else None,
        },
        "market": market,
        "verdict": verdict,
        "retrospective": retrospective,
        "retrospective_note": (
            "This condition is a script label, which is only known after the game. "
            "It describes what happened in games that turned out that way and cannot "
            "tell you what to bet beforehand, so no price comparison is offered."
        ) if retrospective else None,
    }
