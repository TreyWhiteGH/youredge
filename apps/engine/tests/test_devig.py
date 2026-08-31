"""De-vig invariants.

Every one of these corresponds to a defect that reached the database.
"""

import pytest
from sqlalchemy import text

from tests.conftest import count, require

# Float rounding across a few hundred thousand rows, not a tolerance for being
# wrong: a group that misses by more than this is mis-grouped, not imprecise.
EPS = 0.002


async def test_two_way_groups_sum_to_one(conn):
    """A de-vigged pair is a probability distribution over two outcomes.

    This is the property that the whole rung-grouping change exists to restore.
    Before it, an alternate ladder was divided by the sum of the entire board —
    an overround near 50 — and 15,932 rows sat at roughly a thirtieth of their
    true value while still summing, as a board, to one.
    """
    await require(conn, "odds_snapshots")
    bad = await count(conn, """
        WITH keyed AS (
            SELECT s.market_id, s.captured_at, s.fair_prob,
                   CASE WHEN m.market_key LIKE '%spread%'
                             AND s.outcome <> min(s.outcome) OVER (
                                   PARTITION BY s.market_id, s.captured_at)
                        THEN -s.line ELSE s.line END AS rung
            FROM odds_snapshots s JOIN markets m USING (market_id)
            WHERE s.fair_prob IS NOT NULL
              AND m.market_key NOT LIKE 'player%'
        )
        SELECT count(*) FROM (
            SELECT sum(fair_prob) AS total, count(*) AS n
            FROM keyed GROUP BY market_id, captured_at, rung
        ) g WHERE g.n = 2 AND abs(g.total - 1.0) > :eps
    """, eps=EPS)
    assert bad == 0, f"{bad} two-way groups do not sum to 1.0"


async def test_no_group_holds_more_than_two_priced_sides(conn):
    """Three rows in one rung means the pairing rule matched the wrong things."""
    await require(conn, "odds_snapshots")
    # The rung key has to be computed in its own pass: a window function cannot
    # appear in GROUP BY, which is why the production query is two CTEs deep.
    bad = await count(conn, """
        WITH keyed AS (
            SELECT s.market_id, s.captured_at,
                   CASE WHEN m.market_key LIKE '%spread%'
                             AND s.outcome <> min(s.outcome) OVER (
                                   PARTITION BY s.market_id, s.captured_at)
                        THEN -s.line ELSE s.line END AS rung
            FROM odds_snapshots s JOIN markets m USING (market_id)
            WHERE s.fair_prob IS NOT NULL AND m.market_key NOT LIKE 'player%'
        )
        SELECT count(*) FROM (
            SELECT count(*) AS n FROM keyed
            GROUP BY market_id, captured_at, rung
        ) g WHERE g.n > 2
    """)
    assert bad == 0, f"{bad} rung groups hold more than two priced sides"


async def test_alternate_ladders_are_monotone(conn):
    """P(over X) must fall as X rises. A ladder that rises is mis-priced.

    This is the check that caught nothing when it was run by hand — 418
    comparisons, zero violations — which is exactly why it is worth keeping: it
    is the property a future change to rung grouping would break first.
    """
    await require(conn, "odds_snapshots")
    bad = await count(conn, """
        SELECT count(*) FROM (
            SELECT s.fair_prob,
                   lag(s.fair_prob) OVER (PARTITION BY s.market_id, s.captured_at
                                          ORDER BY s.line) AS prev
            FROM odds_snapshots s JOIN markets m USING (market_id)
            WHERE m.market_key LIKE 'player%_alternate'
              AND s.fair_prob IS NOT NULL AND s.line IS NOT NULL
        ) z WHERE prev IS NOT NULL AND fair_prob > prev + :eps
    """, eps=EPS)
    assert bad == 0, f"{bad} ladder rungs price higher than a lower rung"


async def test_fair_prob_is_a_probability(conn):
    await require(conn, "odds_snapshots")
    bad = await count(conn, """
        SELECT count(*) FROM odds_snapshots
        WHERE fair_prob IS NOT NULL AND (fair_prob <= 0 OR fair_prob >= 1)
    """)
    assert bad == 0, f"{bad} fair_prob values outside (0, 1)"


async def test_touchdown_boards_land_near_their_target(conn):
    """A de-vigged anytime-TD board should sum to about the expected scorers.

    Not pinned to it — each book keeps its own measured margin rather than being
    stretched to one game's number — but a board landing at 1.0, or at 8, means
    the target lookup broke.
    """
    await require(conn, "odds_snapshots")
    rows = (await conn.execute(text("""
        SELECT sum(s.fair_prob) AS total, count(*) AS names
        FROM odds_snapshots s JOIN markets m USING (market_id)
        WHERE m.market_key = 'player_anytime_td' AND s.fair_prob IS NOT NULL
        GROUP BY m.game_id, m.bookmaker, s.captured_at
        HAVING count(*) >= 15
    """))).all()
    if not rows:
        pytest.skip("no complete touchdown boards priced yet")
    off = [t for t, _ in rows if not (2.0 <= float(t) <= 8.0)]
    assert not off, f"{len(off)} boards sum outside 2–8 scorers, e.g. {off[:3]}"


def test_power_leaves_a_coin_flip_alone():
    """The two methods must agree where a book's cut really is symmetric.

    A -110/-110 market is the case multiplicative de-vig gets right, so power
    has to reproduce it exactly or the correction is doing something other than
    removing favourite-longshot bias.
    """
    from youredge.pricing.devig import solve_power

    pair = (0.5238, 0.5238)
    k = solve_power(pair)
    power = [p ** k for p in pair]
    mult = [p / sum(pair) for p in pair]
    assert abs(power[0] - mult[0]) < 1e-4
    assert abs(sum(power) - 1.0) < 1e-9


def test_power_pulls_the_longshot_down():
    """On a lopsided market the longshot must come in, not stay put.

    Dividing by the overround assumes a book takes the same proportional cut on
    both sides; it does not, and the extra sits on the longshot. A 9.1% leg by
    the old method is 5.8% by this one — a 37% relative move on exactly the kind
    of leg a parlay is built from.
    """
    from youredge.pricing.devig import solve_power

    pair = (0.9524, 0.0952)
    k = solve_power(pair)
    power = [p ** k for p in pair]
    mult = [p / sum(pair) for p in pair]
    assert abs(sum(power) - 1.0) < 1e-9
    assert power[1] < mult[1] - 0.02, "longshot should come in materially"
    assert power[0] > mult[0], "favourite should firm up correspondingly"


def test_power_refuses_a_market_that_is_not_one():
    """Both sides near-certain is bad data, and must not be answered anyway.

    Bisection returns an endpoint rather than an error when the root is outside
    its bracket. Five h2h pairs in the archive have both sides implied near 0.99
    — an overround of 1.96 — and without a bracket check the solver returned the
    ceiling and wrote a pair summing to 1.72.
    """
    from youredge.pricing.devig import solve_power

    assert solve_power((0.9990, 0.9615)) is None
    assert solve_power((0.5, 1.0)) is None
    assert solve_power((0.0, 0.5)) is None


def test_freshness_tightens_toward_kickoff():
    """A price's shelf life depends on how close the game is.

    One flat threshold has to be wrong at one end: generous enough for a game
    three days out is far too generous inside the last hour, when the line has
    moved twice since.
    """
    from youredge.pricing.fair_value import stale_after

    last_hour = stale_after(0.5)
    inside_three = stale_after(2)
    same_day = stale_after(12)
    days_out = stale_after(72)

    assert last_hour < inside_three < same_day < days_out
    assert last_hour <= 20 * 60
    # A game already under way, or one with no kickoff, falls back to the
    # loosest setting rather than to zero — a missing kickoff must not silently
    # mark every quote stale.
    assert stale_after(None) == days_out
    assert stale_after(-3) == days_out
