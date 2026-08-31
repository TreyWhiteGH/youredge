"""Generate a sheet of slips to check against a real sportsbook.

The estimator has two halves that can each be wrong — the counted correlation
and the book's margin — and no amount of internal consistency tells you which.
Only a real quote does. This produces the slips worth checking, with what the
model expects, so an hour spent pasting into DraftKings and FanDuel answers a
question rather than collecting anecdotes.

The slips are chosen, not enumerated. A game has tens of thousands of possible
three-leg combinations and they carry almost no independent information: what
moves the haircut is the number of legs, how related they are, and how long the
price is. So the sheet walks that grid — a strongly correlated pair, a weakly
related one, a deliberately conflicting one, then three and four legs — and each
row is a different question rather than another sample of the same one.

Legs are phrased with the team's full name or abbreviation, because the leg
parser matches on those and not on nicknames. That is a limitation of the
scaffolding parser rather than of the model, and it is worked around here rather
than papered over.

    docker compose run --rm ingest python -m youredge.scripts.sgp_sheet
    docker compose run --rm ingest python -m youredge.scripts.sgp_sheet --games 8 --csv
"""

import argparse
import asyncio
import csv
import logging
import sys

from sqlalchemy import text

from youredge.db import get_engine
from youredge.legs.critique import parse_leg
from youredge.pricing import sgp as sgp_model
from youredge.pricing.fair_value import price_leg
from youredge.pricing.implications import analyse

log = logging.getLogger(__name__)

BOOKS = ("draftkings", "fanduel")

# Each entry is (label, what it is testing, leg builder). The label is what makes
# a disagreement interpretable: "conflict" missing by 30% means something quite
# different from "correlated pair" missing by 30%.
# Offsets from the main total, used to reach for a line the entailment does not
# already settle. Every combination available off the main numbers collapses to
# two legs of risk -- which is why the first fifteen quotes produced no
# observation at three, and why the margin there is still a prior.
_ALT_TOTAL_STEPS = (0, 6, 10, -6)

DESIGNS = [
    ("pair/correlated", "spread + over: the classic reinforcing pair",
     lambda h, a, sp, tot, ht, at: [f"{h} {sp:+g}", f"over {tot}"]),
    ("pair/conflicting", "favourite covering while the game stays under",
     lambda h, a, sp, tot, ht, at: [f"{h} {sp:+g}", f"under {tot}"]),
    ("pair/team-total", "side with its own team total, near-duplicate legs",
     lambda h, a, sp, tot, ht, at: [f"{h} {sp:+g}", f"{h} team total over {ht}"]),
    ("pair/moneyline", "moneyline with the game total",
     lambda h, a, sp, tot, ht, at: [f"{h} moneyline", f"over {tot}"]),
    ("triple/reinforcing", "three legs that all want the same script",
     lambda h, a, sp, tot, ht, at: [f"{h} {sp:+g}", f"over {tot}",
                                    f"{h} team total over {ht}"]),
    ("triple/mixed", "two that agree and one that does not",
     lambda h, a, sp, tot, ht, at: [f"{h} {sp:+g}", f"under {tot}",
                                    f"{h} team total over {ht}"]),
    ("quad/reinforcing", "four legs, where compounding margin should show",
     lambda h, a, sp, tot, ht, at: [f"{h} {sp:+g}", f"over {tot}",
                                    f"{h} team total over {ht}",
                                    f"{a} team total over {at}"]),
]

_GAMES = text("""
    SELECT g.game_id, g.league, g.kickoff,
           ht.name AS home, ht.abbr AS home_abbr,
           at.name AS away, at.abbr AS away_abbr,
           (SELECT s.line FROM markets m JOIN odds_snapshots s USING (market_id)
             WHERE m.game_id = g.game_id AND m.market_key = 'spreads'
               AND (s.outcome ILIKE ht.name || '%')
             ORDER BY s.captured_at DESC LIMIT 1) AS spread,
           (SELECT s.line FROM markets m JOIN odds_snapshots s USING (market_id)
             WHERE m.game_id = g.game_id AND m.market_key = 'totals'
               AND s.outcome ILIKE 'over'
             ORDER BY s.captured_at DESC LIMIT 1) AS total,
           -- The team totals a book has actually posted. Half the game total is
           -- a reasonable guess and a useless one: a leg has to name a line the
           -- book quotes or there is nothing to price it against.
           (SELECT s.line FROM markets m JOIN odds_snapshots s USING (market_id)
             WHERE m.game_id = g.game_id AND m.market_key = 'team_totals'
               AND m.side_team_id = g.home_team_id AND s.outcome ILIKE 'over'
             ORDER BY s.captured_at DESC LIMIT 1) AS home_tt,
           (SELECT s.line FROM markets m JOIN odds_snapshots s USING (market_id)
             WHERE m.game_id = g.game_id AND m.market_key = 'team_totals'
               AND m.side_team_id = g.away_team_id AND s.outcome ILIKE 'over'
             ORDER BY s.captured_at DESC LIMIT 1) AS away_tt
    FROM games g
    JOIN teams ht ON ht.team_id = g.home_team_id
    JOIN teams at ON at.team_id = g.away_team_id
    WHERE g.status = 'scheduled' AND g.kickoff > now()
      AND g.league = :league
      -- Games already quoted are dropped by default. Ordering by kickoff and
      -- taking the first few handed back the same games every run, so a second
      -- sheet asked for work already done and answered no new question.
      AND (:repeat OR g.game_id NOT IN (SELECT game_id FROM user_bets))
    ORDER BY g.kickoff
    LIMIT :pool
""")


def spread_of(g) -> float:
    return abs(float(g["spread"])) if g["spread"] is not None else 0.0


def diversify(games: list, want: int) -> list:
    """Pick games across spread buckets rather than the next few on the calendar.

    The open question is whether leg correlation changes with the matchup, and
    the line is the market's summary of that. A sheet drawn from one week's
    nearest kickoffs is nearly all pick'ems, which is precisely where the
    league-average lift is already accurate — so it cannot answer the question
    however many rows it has.
    """
    buckets: dict[str, list] = {}
    for g in games:
        sp = spread_of(g)
        key = ("pickem" if sp <= 3 else "short" if sp <= 7
               else "mid" if sp <= 14 else "big")
        buckets.setdefault(key, []).append(g)
    order = ["big", "mid", "short", "pickem"]      # rarest first
    out, i = [], 0
    while len(out) < want and any(buckets.values()):
        key = order[i % len(order)]
        if buckets.get(key):
            out.append(buckets[key].pop(0))
        i += 1
        if i > len(order) * (want + len(games)):
            break
    return out


async def build(league: str, limit: int, as_csv: bool, repeat: bool) -> None:
    engine = get_engine()
    rows = []
    async with engine.connect() as conn:
        pool = (await conn.execute(_GAMES, {
            "league": league, "pool": max(limit * 8, 40), "repeat": repeat,
        })).mappings().all()
        priced_pool = [g for g in pool
                       if g["spread"] is not None and g["total"] is not None]
        games = diversify(priced_pool, limit)
        if not games:
            log.warning("no unquoted games with a spread and total left; "
                        "pass --repeat to sample games already recorded")
            return
        log.info("spreads on this sheet: %s",
                 ", ".join(f"{spread_of(g):g}" for g in games))
        for g in games:
            if g["spread"] is None or g["total"] is None:
                continue
            seen: set[tuple[str, ...]] = set()
            for label, purpose, build_legs in DESIGNS:
                if "team total" in label and (g["home_tt"] is None
                                              or g["away_tt"] is None):
                    continue
                raw = build_legs(g["home_abbr"], g["away_abbr"],
                                 g["spread"], g["total"],
                                 g["home_tt"], g["away_tt"])
                priced, missing = [], []
                for r in raw:
                    leg = await parse_leg(conn, g["game_id"], r)
                    if not leg:
                        missing.append(r)
                        continue
                    p = await price_leg(conn, g["game_id"], leg["market_key"],
                                        leg["outcome"], leg["line"], "draftkings",
                                        subject=leg.get("subject"))
                    if p.fair_prob is None:
                        missing.append(r)
                        continue
                    priced.append({**leg, "raw": r, "fair_prob": p.fair_prob})
                # A design that lost a leg is no longer that design. TB @ CIN
                # has no game total quoted, so three separate rows collapsed to
                # the same two legs and printed under three different labels --
                # which invites three checks of one slip and reads as agreement
                # between designs that were never run.
                if missing or len(priced) < 2:
                    continue
                slip = tuple(l["raw"] for l in priced)
                if slip in seen:
                    continue
                seen.add(slip)
                est = {}
                for book in BOOKS:
                    est[book] = await sgp_model.estimate(
                        conn, league, book, priced)
                first = est[BOOKS[0]]
                rows.append({
                    "game": f"{g['away_abbr']} @ {g['home_abbr']}",
                    "kickoff": g["kickoff"].strftime("%a %d %b %H:%M"),
                    "design": label,
                    "legs": " | ".join(l["raw"] for l in priced),
                    "n": len(priced),
                    "independence": first["independence_price"],
                    "fair": first["fair_price"],
                    "corr": first["correlation_multiplier"],
                    **{f"est_{b}": est[b]["estimated_book_price"] for b in BOOKS},
                    "margin_basis": first["margin"]["basis"],
                    # Filled in by hand from the book, then read back by
                    # scripts.sgp_record. Empty is the normal state of a fresh
                    # sheet; a row with neither price set is simply skipped on
                    # load rather than treated as a zero.
                    "actual_draftkings": "",
                    "actual_fanduel": "",
                    "game_id": g["game_id"],
                    "league": g["league"],
                })

    # Reach for slips that carry three and four legs of genuine risk, by walking
    # the total away from its main number until entailment stops collapsing the
    # slip. Which offset works is not worked out in algebra -- that has been
    # wrong once already -- but by asking the same checker the estimate uses.
    async with engine.connect() as conn:
        for g in games:
            if g["home_tt"] is None:
                continue
            have = {r["design"] for r in rows if r["game"].endswith(g["home_abbr"])}
            for step in _ALT_TOTAL_STEPS:
                if any(d.startswith("genuine") for d in have):
                    break
                alt = float(g["total"]) + step
                candidate = [f"{g['home_abbr']} {g['spread']:+g}",
                             f"over {alt}",
                             f"{g['home_abbr']} team total over {g['home_tt']}"]
                priced, missing = [], []
                for r in candidate:
                    leg = await parse_leg(conn, g["game_id"], r)
                    if not leg:
                        missing.append(r); continue
                    p = await price_leg(conn, g["game_id"], leg["market_key"],
                                        leg["outcome"], leg["line"], "draftkings",
                                        subject=leg.get("subject"))
                    if p.fair_prob is None:
                        missing.append(r); continue
                    priced.append({**leg, "raw": r, "fair_prob": p.fair_prob})
                if missing or len(priced) < 3:
                    continue
                if analyse(priced)["entailed"]:
                    continue                      # still collapses; try further out
                est = {b: await sgp_model.estimate(conn, league, b, priced)
                       for b in BOOKS}
                first = est[BOOKS[0]]
                rows.append({
                    "game": f"{g['away_abbr']} @ {g['home_abbr']}",
                    "kickoff": g["kickoff"].strftime("%a %d %b %H:%M"),
                    "design": "genuine/three-risk",
                    "legs": " | ".join(l["raw"] for l in priced),
                    "n": 3,
                    "independence": first["independence_price"],
                    "fair": first["fair_price"], "corr": first["correlation_multiplier"],
                    **{f"est_{b}": est[b]["estimated_book_price"] for b in BOOKS},
                    "margin_basis": first["margin"]["basis"],
                    "actual_draftkings": "", "actual_fanduel": "",
                    "game_id": g["game_id"], "league": g["league"],
                })
                break

    if not rows:
        log.warning("no games with both a spread and a total quoted yet")
        return

    if as_csv:
        w = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
        return

    print(f"\n{len(rows)} slips to check. Paste each into the book, read the "
          f"price it quotes, and compare with est_*.\n")
    hdr = (f"{'game':<12} {'design':<18} {'n':>2} {'indep':>7} {'fair':>7} "
           f"{'corr':>6} {'DK':>7} {'FD':>7}  legs")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['game']:<12} {r['design']:<18} {r['n']:>2} "
              f"{r['independence']:>+7d} {r['fair']:>+7d} {r['corr']:>6.2f} "
              f"{r['est_draftkings']:>+7d} {r['est_fanduel']:>+7d}  {r['legs']}")
    print(f"\nMargin basis: {rows[0]['margin_basis']}. Once twelve real quotes "
          f"exist for a book at a leg count, that cell stops using the prior.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default="nfl", choices=("nfl", "ncaaf"))
    ap.add_argument("--games", type=int, default=4)
    ap.add_argument("--csv", action="store_true")
    ap.add_argument("--repeat", action="store_true",
                    help="include games already recorded in user_bets")
    args = ap.parse_args()
    asyncio.run(build(args.league, args.games, args.csv, args.repeat))
