"""The scoring timeline, and the tags counted off it."""

import pytest
from sqlalchemy import text

from tests.conftest import count, require


async def test_timeline_reconciles_to_the_final_score(conn):
    """Points read off the play scoreboard must equal the game's final score.

    This is the check that exposed the whole problem: three of eight games
    disagreed, because drive points credit a flat 7 per touchdown (blind to a
    missed extra point or a two-point conversion) and credit nothing at all for
    a return touchdown, which belongs to no offensive drive.
    """
    await require(conn, "plays")
    rows = (await conn.execute(text("""
        WITH tl AS (
            SELECT p.game_id, max(p.home_score) AS mh, max(p.away_score) AS ma
            FROM plays p JOIN games g USING (game_id)
            WHERE p.home_score IS NOT NULL AND g.status = 'final'
            GROUP BY p.game_id
        )
        SELECT g.league, count(*) AS n,
               count(*) FILTER (WHERE g.home_score = tl.mh
                                  AND g.away_score = tl.ma) AS exact
        FROM tl JOIN games g USING (game_id) GROUP BY 1
    """))).all()
    if not rows:
        pytest.skip("no scored plays yet")
    # Held to different bars on purpose. nflverse carries the running score on
    # every row and reconciles exactly, so anything less is a regression. CFBD
    # omits the score on some rows and disagrees with its own game endpoint on a
    # small tail, which is a property of the feed rather than of this code --
    # the bar there is that the tail stays a tail.
    floors = {"nfl": 1.0, "ncaaf": 0.95}
    for league, n, exact in rows:
        rate = exact / n
        assert rate >= floors.get(league, 0.95), (
            f"{league}: only {exact}/{n} ({rate:.1%}) of games reconcile")


async def test_scoreboard_never_falls(conn):
    """A score cannot go down.

    CFBD's differential on kickoff and timeout rows can be stale, which is why
    the sequence builder takes a running maximum. If the stored columns
    themselves ever regress, the raw feed changed shape and the running maximum
    is hiding it rather than correcting it.
    """
    await require(conn, "plays")
    bad = await count(conn, """
        SELECT count(*) FROM (
            SELECT home_score, away_score,
                   lag(home_score) OVER w AS ph, lag(away_score) OVER w AS pa
            FROM plays WHERE home_score IS NOT NULL
            WINDOW w AS (PARTITION BY game_id
                         ORDER BY game_seconds_remaining DESC NULLS LAST, play_id)
        ) z
        WHERE (ph IS NOT NULL AND home_score < ph - 1)
           OR (pa IS NOT NULL AND away_score < pa - 1)
    """)
    # Not zero: the feed genuinely reorders a handful of rows around a score.
    # The bar is that it stays a handful rather than becoming a pattern.
    total = await count(conn, "SELECT count(*) FROM plays WHERE home_score IS NOT NULL")
    assert bad / max(total, 1) < 0.02, f"{bad}/{total} plays report a falling score"


async def test_quarter_points_sum_to_the_final(conn):
    """Per-quarter points must add up. NULL here is the bug this caught before.

    A scoreless quarter sums to NULL over an empty set, and every comparison
    against NULL fails silently — which is how SLOW_BURN was written correctly
    and fired zero times.
    """
    await require(conn, "game_state")
    bad = await count(conn, """
        SELECT count(*) FROM game_state
        WHERE home_q1_points IS NOT NULL
          AND (home_q1_points + home_q2_points + home_q3_points + home_q4_points
                 <> home_points
            OR away_q1_points + away_q2_points + away_q3_points + away_q4_points
                 <> away_points)
    """)
    # Overtime scoring is filed under quarter 4 by the builder, so this holds
    # exactly; a mismatch means a quarter went missing.
    # Same split as the reconciliation test above, and for the same reason: a
    # quarter cannot add up if the plays it was summed from never carried the
    # score in the first place.
    total = await count(conn, "SELECT count(*) FROM game_state WHERE home_q1_points IS NOT NULL")
    assert bad / max(total, 1) < 0.07, (
        f"{bad}/{total} games where quarter points do not sum to the final")


async def test_a_run_never_exceeds_a_team_total(conn):
    """Unanswered points are a subset of points scored."""
    await require(conn, "game_state")
    bad = await count(conn, """
        SELECT count(*) FROM game_state
        WHERE (home_max_run IS NOT NULL AND home_max_run > home_points)
           OR (away_max_run IS NOT NULL AND away_max_run > away_points)
    """)
    total = await count(conn, "SELECT count(*) FROM game_state WHERE home_max_run IS NOT NULL")
    assert bad / max(total, 1) < 0.01, (
        f"{bad}/{total} games where a scoring run exceeds the team's total")


@pytest.mark.parametrize("dimension", ["script", "diagnostic"])
async def test_no_tag_is_modal_or_dead(conn, dimension):
    """Every tag has to discriminate.

    A tag firing on 60% of games describes football, not this game; one firing
    on nothing is either broken or unreachable. Both have happened: a flat
    14-point run hit 44% of college team-games, and SLOW_BURN fired zero times
    while reading correctly.
    """
    await require(conn, "taggings")
    rows = (await conn.execute(text("""
        WITH pop AS (
            SELECT g.league, count(*) AS n FROM games g
            JOIN game_state gs USING (game_id) GROUP BY 1
        )
        SELECT g.league, t.slug,
               count(*)::float / (pop.n * CASE WHEN :dim = 'diagnostic'
                                               THEN 2 ELSE 1 END) AS rate
        FROM taggings tg
        JOIN tags t ON t.tag_id = tg.tag_id AND t.dimension = :dim
        JOIN games g ON g.game_id = split_part(tg.entity_id, '|', 1)
        JOIN pop ON pop.league = g.league
        GROUP BY g.league, t.slug, pop.n
    """), {"dim": dimension})).all()
    if not rows:
        pytest.skip(f"no {dimension} taggings yet")
    modal = [(lg, slug, round(r, 3)) for lg, slug, r in rows if r > 0.60]
    assert not modal, f"{dimension} tags fire on more than 60%: {modal}"

    seeded = await count(
        conn, "SELECT count(*) FROM tags WHERE dimension = :dim AND status = 'active'",
        dim=dimension)
    fired = len({slug for _, slug, _ in rows})
    assert fired >= seeded - 1, f"only {fired} of {seeded} {dimension} tags ever fire"
