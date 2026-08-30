"""De-vig: strip bookmaker margin from snapshot implied probabilities.

Multiplicative method: within one priced two-way group, fair_i = implied_i /
sum(implied). Power-method and Pinnacle anchoring are still to come.

**What a group is.** A group is (market_id, captured_at, |line|) — not
(market_id, captured_at). The line is part of the key because a ladder market
keeps every rung in one market row: `alternate_totals` posts Over/Under at 30.5,
31.5, ... 55.5 side by side, and `player_reception_yds_alternate` posts a rung
for every receiver at every yardage. Summing implied probability across a whole
ladder produces an overround of fifty rather than 1.05, and dividing by it turns
a -110 price into 0.018. Each rung is its own two-way market and is de-vigged as
one.

Pairing differs by family, and the difference is not cosmetic. A totals-style
market puts both sides on the *same* number — Over 44.5 against Under 44.5 — so
the line alone is the key. A spread puts them on *opposite* numbers, home -3.5
against away +3.5, and a spread ladder quotes both teams at every rung, so |3.5|
alone gathers four rows: two complete, independent pairs. Summing them gives an
overround near 2.1 and halves every fair value. Spread rungs are therefore keyed
by the line as seen from one canonical side, which puts home -3.5 with away +3.5
and home +3.5 with away -3.5 in separate groups where they belong. Moneylines
carry no line at all and fall through to a single group.

**Ladders a book quotes one-sided.** `player_pass_yds_alternate` and its
siblings post only the Over at each rung — there is no Under to normalise
against. The margin is borrowed instead from the two-way parent market: Drake
Maye's `player_pass_yds` is quoted -111/-113, an overround of 1.048, and every
rung of his alternate ladder is divided by it. This assumes the book applies one
margin across a player's whole ladder, which is an approximation — real books
charge more on the deep favourites at the short end — but it is a far smaller
error than the alternative of leaving the rows unpriced, and it is honest about
which market the margin came from.

Groups are skipped when a side is missing (n < 2) or unpriced (CFBD historical
spreads/totals carry lines without juice — their implied_prob is NULL). One-sided
many-way boards are skipped for a deeper reason: `player_anytime_td` quotes only
Yes, and those Yes prices legitimately sum well above 1, because a game has
roughly two dozen candidate scorers and about five of them score. Normalising
them to 1.0 would not remove vig, it would invent a different wrong answer. Those
need an expected-scorer target derived from the de-vigged game total, which is
its own piece of work. `player_tds_over` is the same board at 2+ and 3+ and is
left alone for the same reason — its parent is `player_anytime_td`, which is
itself one-sided, so there is no margin to borrow.

Usage:
    docker compose run --rm ingest python -m youredge.pricing.devig
    docker compose run --rm ingest python -m youredge.pricing.devig --rebuild
"""

import argparse
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from youredge.db import get_engine

log = logging.getLogger(__name__)

_DEVIG = text("""
    WITH keyed AS (
        SELECT s.snapshot_id, s.market_id, s.captured_at, s.implied_prob,
               CASE
                 -- Flip the sign for whichever side is not the canonical one, so
                 -- the two halves of a spread rung land on the same key. Which
                 -- side is canonical does not matter, only that it is stable
                 -- within the group; the alphabetically first outcome is.
                 WHEN m.market_key LIKE '%spread%'
                      AND s.outcome <> min(s.outcome) OVER (
                            PARTITION BY s.market_id, s.captured_at)
                 THEN -s.line
                 ELSE s.line
               END AS rung
        FROM odds_snapshots s JOIN markets m USING (market_id)
        WHERE s.implied_prob IS NOT NULL AND s.fair_prob IS NULL
    ),
    grp AS (
        SELECT market_id, captured_at, rung,
               SUM(implied_prob) AS overround, COUNT(*) AS n
        FROM keyed
        GROUP BY market_id, captured_at, rung
    )
    UPDATE odds_snapshots s
    SET fair_prob = k.implied_prob / g.overround
    FROM keyed k
    JOIN grp g ON g.market_id = k.market_id
              AND g.captured_at = k.captured_at
              AND g.rung IS NOT DISTINCT FROM k.rung
    WHERE s.snapshot_id = k.snapshot_id
      -- Exactly two, not at least two. A two-way group has two sides; a group
      -- that somehow holds three is a pairing this rule got wrong, and leaving
      -- it unpriced is better than dividing by an overround built from it.
      AND g.n = 2
      AND g.overround > 0
""")

# One margin per player per book, taken from the two-way parent and applied to
# every rung of the one-sided ladder beside it. DISTINCT ON picks the parent
# quote closest in time to the rung, because the two are polled in the same sweep
# but land at slightly different instants.
_BORROW = text("""
    WITH parent AS (
        SELECT m.game_id, m.bookmaker, m.player_name, m.market_key, s.captured_at,
               SUM(s.implied_prob) AS overround
        FROM markets m JOIN odds_snapshots s USING (market_id)
        WHERE m.market_key IN ('player_pass_yds', 'player_rush_yds',
                               'player_reception_yds', 'player_receptions',
                               'player_pass_tds')
          AND s.implied_prob IS NOT NULL
        GROUP BY 1, 2, 3, 4, 5
        HAVING COUNT(*) = 2 AND SUM(s.implied_prob) > 0
    ),
    rung AS (
        SELECT s.snapshot_id, s.implied_prob, s.captured_at,
               m.game_id, m.bookmaker, m.player_name,
               replace(m.market_key, '_alternate', '') AS base_key
        FROM markets m JOIN odds_snapshots s USING (market_id)
        WHERE m.market_key LIKE 'player\\_%\\_alternate'
          AND s.implied_prob IS NOT NULL AND s.fair_prob IS NULL
    ),
    pick AS (
        SELECT DISTINCT ON (r.snapshot_id)
               r.snapshot_id, r.implied_prob / p.overround AS fair
        FROM rung r
        JOIN parent p ON p.game_id = r.game_id AND p.bookmaker = r.bookmaker
                     AND p.player_name = r.player_name AND p.market_key = r.base_key
        ORDER BY r.snapshot_id,
                 abs(EXTRACT(epoch FROM (p.captured_at - r.captured_at)))
    )
    UPDATE odds_snapshots s
    SET fair_prob = pick.fair
    FROM pick
    WHERE s.snapshot_id = pick.snapshot_id AND pick.fair > 0 AND pick.fair < 1
""")

# Every row this reaches was de-vigged against a whole ladder rather than against
# its own rung. Clearing them is what lets the pass above recompute — it only
# touches rows where fair_prob IS NULL, which is deliberate everywhere else.
_CLEAR = text("UPDATE odds_snapshots SET fair_prob = NULL WHERE fair_prob IS NOT NULL")


async def devig_snapshots(conn: AsyncConnection) -> int:
    """Fill fair_prob for every complete, priced, not-yet-devigged group.

    Two-way groups first, because the borrowed pass reads the parent quotes the
    first pass has already validated as a genuine pair.
    """
    paired = (await conn.execute(_DEVIG)).rowcount
    borrowed = (await conn.execute(_BORROW)).rowcount
    if borrowed:
        log.info("%d ladder rungs priced off a borrowed parent margin", borrowed)
    return paired + borrowed


async def main(rebuild: bool):
    engine = get_engine()
    async with engine.begin() as conn:
        if rebuild:
            cleared = (await conn.execute(_CLEAR)).rowcount
            log.info("cleared fair_prob on %d snapshots", cleared)
        n = await devig_snapshots(conn)
    log.info("fair_prob filled on %d snapshots", n)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true",
                        help="clear every fair_prob and recompute from scratch")
    args = parser.parse_args()
    asyncio.run(main(args.rebuild))
