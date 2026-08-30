"""De-vig: strip bookmaker margin from snapshot implied probabilities.

**Power method.** Within one priced two-way group, find the exponent k for which
`sum(implied_i ** k) = 1`, then `fair_i = implied_i ** k`. The obvious
alternative — divide every side by the overround — assumes a book takes the same
proportional cut on both sides of a market, and books do not. They take more on
the longshot, which is the favourite-longshot bias, and dividing proportionally
leaves that bias in place while looking like it removed the vig.

The difference is small on a coin-flip and large exactly where it matters. On a
-110/-110 spread the two methods agree to three decimals. On a lopsided
moneyline, where the live data reaches an overround near 2.0, multiplicative
overstates the longshot by several points of probability — and a several-point
error on a 5% leg is a large relative error on precisely the kind of leg a
parlay is built from.

Raising both sides to a common power leaves a near-certainty almost untouched
(0.95 ** 1.06 is still 0.947) while pulling a longshot down much harder
(0.10 ** 1.06 is 0.087). That asymmetry is the correction, and it falls out of
the functional form rather than being tuned.

k is found by bisection: `sum(p ** k)` is strictly decreasing in k for
probabilities under 1, so the root is unique and forty halvings put it well
inside float precision. Where a group refuses to bracket — any side at or above
1.0, which should not occur but would silently poison the solve — it is left
unpriced rather than approximated.

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

**The touchdown boards.** `player_anytime_td` quotes only Yes, for twenty-odd
players at once, and those Yes prices legitimately sum well above 1 — a game has
four or five distinct touchdown scorers, so the board sums to roughly that plus
the book's margin. Normalising it to 1.0 would not remove vig, it would invent a
different wrong answer.

What it needs is a target, and the target is countable: regress the number of
distinct rushing/receiving touchdown scorers on the closing total, per league,
over every finished game. Scorers rise from about 2.6 at a total of 30 to 6.4 at
70, so this is a real relationship rather than a constant.

Scaling each board to its own target is still wrong, because books post
different numbers of players — a ten-name board is not a low-margin board, it is
a partial one, and stretching it to a full-game target inflates every name on
it. The margin is a property of the book, so it is measured on the boards that
look complete and then applied to all of that book's boards, exactly as the
one-sided player ladders borrow from their two-way parent.

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
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from youredge.db import get_engine

log = logging.getLogger(__name__)

# Bisection bounds. k < 1 is legitimate — a group whose prices sum to under one
# is a book quoting a market at negative hold, which happens on screen-scraped
# and stale pairs — and k above 8 would mean an overround no book charges.
_K_LO, _K_HI, _K_STEPS = 0.2, 8.0, 40


def solve_power(probs: Sequence[float]) -> float | None:
    """Exponent k with sum(p ** k) == 1, or None if the group cannot be solved."""
    if any(p <= 0 or p >= 1 for p in probs):
        return None
    # Bisection assumes the root is inside the bracket, and returns an endpoint
    # rather than an error when it is not. Some quotes are not markets: five
    # h2h pairs in the archive have *both* sides implied near 0.99, an overround
    # of 1.96, and no exponent in any sane range brings that to one. Without this
    # check the solver returned the ceiling and wrote a pair summing to 1.72.
    if sum(p ** _K_HI for p in probs) > 1.0:
        return None
    if sum(p ** _K_LO for p in probs) < 1.0:
        return None
    lo, hi = _K_LO, _K_HI
    for _ in range(_K_STEPS):
        mid = (lo + hi) / 2
        # Decreasing in k, so a sum still above one means k must go higher.
        if sum(p ** mid for p in probs) > 1.0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


_GROUPS = text("""
    WITH keyed AS (
        SELECT s.snapshot_id, s.market_id, s.captured_at, s.implied_prob,
               CASE
                 WHEN m.market_key LIKE '%spread%'
                      AND s.outcome <> min(s.outcome) OVER (
                            PARTITION BY s.market_id, s.captured_at)
                 THEN -s.line ELSE s.line
               END AS rung
        FROM odds_snapshots s JOIN markets m USING (market_id)
        WHERE s.implied_prob IS NOT NULL AND s.fair_prob IS NULL
    ),
    sized AS (
        SELECT *, count(*) OVER (PARTITION BY market_id, captured_at, rung) AS n
        FROM keyed
    )
    SELECT market_id, captured_at, rung,
           array_agg(snapshot_id) AS ids,
           array_agg(implied_prob) AS probs
    FROM sized WHERE n = 2
    GROUP BY market_id, captured_at, rung
""")

_APPLY = text("UPDATE odds_snapshots SET fair_prob = :fair WHERE snapshot_id = :sid")

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

# Distinct touchdown scorers as a function of the closing total, fitted per
# league over every finished game, then the book's own margin measured against
# it. Postgres regr_slope/regr_intercept do the fit, so it re-derives as history
# grows rather than freezing a coefficient into the source.
MIN_BOARD = 15          # names below which a board is partial, not cheap
_TD_BOARD = text("""
    WITH scorers AS (
        SELECT s.game_id,
               count(*) FILTER (WHERE COALESCE(s.rushing_tds, 0)
                                   + COALESCE(s.receiving_tds, 0) > 0) AS n
        FROM player_game_stats s GROUP BY 1
    ),
    fit AS (
        SELECT g.league,
               regr_slope(sc.n, gf.closing_total)     AS b,
               regr_intercept(sc.n, gf.closing_total) AS a
        FROM scorers sc
        JOIN games g USING (game_id)
        JOIN game_features gf USING (game_id)
        WHERE g.status = 'final' AND gf.closing_total IS NOT NULL
        GROUP BY 1
    ),
    -- The total to price against: the closing line where one exists, otherwise
    -- the latest quoted one, because an upcoming game has a market and no close.
    totals AS (
        SELECT g.game_id, g.league,
               COALESCE(gf.closing_total, (
                   SELECT s2.line FROM markets m2
                   JOIN odds_snapshots s2 USING (market_id)
                   WHERE m2.game_id = g.game_id AND m2.market_key = 'totals'
                     AND s2.outcome ILIKE 'over'
                   ORDER BY s2.captured_at DESC LIMIT 1)) AS total
        FROM games g LEFT JOIN game_features gf USING (game_id)
    ),
    board AS (
        SELECT m.game_id, m.bookmaker, s.captured_at,
               count(*) AS names, sum(s.implied_prob) AS sum_yes
        FROM odds_snapshots s JOIN markets m USING (market_id)
        WHERE m.market_key = 'player_anytime_td' AND s.implied_prob IS NOT NULL
        GROUP BY 1, 2, 3
    ),
    ratios AS (
        SELECT b.bookmaker, t.league,
               b.sum_yes / NULLIF(f.a + f.b * t.total, 0) AS ratio
        FROM board b
        JOIN totals t ON t.game_id = b.game_id
        JOIN fit f ON f.league = t.league
        WHERE b.names >= :min_board AND t.total IS NOT NULL
          AND f.a + f.b * t.total > 0
    ),
    -- Median, not mean: one board against a mispriced or missing total would
    -- drag an average and quietly reprice every game that book quotes.
    margin AS (
        SELECT bookmaker, league,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY ratio) AS k,
               count(*) AS boards
        FROM ratios WHERE ratio > 0 GROUP BY 1, 2
    )
    UPDATE odds_snapshots s
    SET fair_prob = s.implied_prob / mg.k
    FROM markets m, games g, margin mg
    WHERE s.market_id = m.market_id
      AND m.game_id = g.game_id
      AND mg.bookmaker = m.bookmaker AND mg.league = g.league
      -- player_tds_over is the same board at 2+ and 3+: one-sided, same book,
      -- same market family, so it carries the same margin. Stated rather than
      -- derived, because there is not yet enough of it to fit separately.
      AND m.market_key IN ('player_anytime_td', 'player_tds_over')
      AND s.implied_prob IS NOT NULL AND s.fair_prob IS NULL
      AND mg.k > 0 AND mg.boards >= 3
      AND s.implied_prob / mg.k < 1
""")

# Every row this reaches was de-vigged against a whole ladder rather than against
# its own rung. Clearing them is what lets the pass above recompute — it only
# touches rows where fair_prob IS NULL, which is deliberate everywhere else.
_CLEAR = text("UPDATE odds_snapshots SET fair_prob = NULL WHERE fair_prob IS NOT NULL")


async def devig_power(conn: AsyncConnection) -> int:
    """Power-method de-vig over every unpriced two-way group."""
    rows = (await conn.execute(_GROUPS)).all()
    updates = []
    unsolved = 0
    for _mid, _at, _rung, ids, probs in rows:
        k = solve_power([float(p) for p in probs])
        if k is None:
            unsolved += 1
            continue
        updates.extend({"sid": sid, "fair": float(p) ** k}
                       for sid, p in zip(ids, probs))
    if unsolved:
        log.info("%d groups had no power solution in range; "
                 "falling through to multiplicative", unsolved)
    # Chunked because a single executemany of a few hundred thousand statements
    # holds the whole list in the driver at once for no benefit.
    for i in range(0, len(updates), 5000):
        await conn.execute(_APPLY, updates[i:i + 5000])
    return len(updates)


async def devig_snapshots(conn: AsyncConnection) -> int:
    """Fill fair_prob for every complete, priced, not-yet-devigged group.

    Two-way groups first, because the borrowed pass reads the parent quotes the
    first pass has already validated as a genuine pair.
    """
    paired = await devig_power(conn)
    borrowed = (await conn.execute(_BORROW)).rowcount
    if borrowed:
        log.info("%d ladder rungs priced off a borrowed parent margin", borrowed)
    # Anything the power solve could not bracket falls through to the
    # multiplicative pass, which is worse but defined everywhere.
    fallback = (await conn.execute(_DEVIG)).rowcount
    if fallback:
        log.info("%d snapshots de-vigged multiplicatively as a fallback", fallback)
    boards = (await conn.execute(_TD_BOARD, {"min_board": MIN_BOARD})).rowcount
    if boards:
        log.info("%d touchdown-board prices scaled to an expected-scorer target",
                 boards)
    return paired + fallback + borrowed + boards


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
