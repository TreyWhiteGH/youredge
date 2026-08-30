"""Retro-label finished games with script tags.

Fills `taggings`, which the schema has anticipated since day one and which the
`game_scripts` view reads. Every label here is a predicate over what actually
happened — `game_state` plus the closing line — not a simulator's opinion. That
matters for Layer B: the correlation surface it feeds has to be countable, so a
game either was a shootout or it wasn't.

    docker compose run --rm ingest python -m youredge.scripts.label

Labels are written with weight 1.0 and tagged_by 'engine'. When the simulator
lands it will write *probabilities* for upcoming games against the same
vocabulary; these rows stay the realized record, which is what makes the two
comparable at all.

Thresholds are stated in one place below rather than buried in SQL, because they
are judgement calls and will want revisiting once the base rates are visible.
"""

import argparse
import asyncio
import logging

from sqlalchemy import text

from youredge.db import get_engine

log = logging.getLogger(__name__)

# Two scores is where play calling changes; 17 is three scores, where a lead
# stops being a lead and starts being control.
BLOWOUT_LEAD = 17
COMEBACK_DEFICIT = 10
TOTAL_MARGIN = 7          # points away from the closing total
SHOOTOUT_TEAM_POINTS = 24
BACKDOOR_SHRINK = 10      # final margin this much better than the peak
MIN_LATE_PLAYS = 8        # a rate over fewer snaps than this is noise

# The two mix-based tags use a percentile *within the league*, not a fixed rate.
# A fixed 0.70 fired on 28.1% of NFL games and 9.3% of college ones, and that gap
# is measurement rather than football: nflverse counts a scramble as a dropback
# and CFBD files it as a rush, so college pass rate is understated by roughly the
# scramble rate. A tag that means "unusually pass-heavy when trailing" has to be
# read against the league's own distribution or it means two different things.
MIX_PERCENTILE = 0.75
FADE_LEAD = 10

# Each entry is (tag slug, SQL predicate over gs / gf / g). Predicates that need
# a closing line simply evaluate NULL without one, and NULL is not true, so those
# games go unlabelled for that tag rather than mislabelled.
SCRIPTS: list[tuple[str, str]] = [
    ("BLOWOUT_FAV", f"""
        gf.closing_spread IS NOT NULL
        AND abs(gs.home_margin) >= 14
        AND (CASE WHEN gf.closing_spread < 0 THEN gs.max_home_lead
                  ELSE gs.max_away_lead END) >= {BLOWOUT_LEAD}
        -- The favourite has to be the one who did it. A dog blowing out a
        -- favourite is a different script entirely.
        AND sign(gs.home_margin) = sign(-gf.closing_spread)
    """),
    ("SHOOTOUT", f"""
        gf.closing_total IS NOT NULL
        AND gs.total_points >= gf.closing_total + {TOTAL_MARGIN}
        AND LEAST(gs.home_points, gs.away_points) >= {SHOOTOUT_TEAM_POINTS}
    """),
    ("GRIND", f"""
        gf.closing_total IS NOT NULL
        AND gs.total_points <= gf.closing_total - {TOTAL_MARGIN}
    """),
    ("COMEBACK", f"""
        (gs.home_margin > 0 AND gs.max_away_lead >= {COMEBACK_DEFICIT})
        OR (gs.home_margin < 0 AND gs.max_home_lead >= {COMEBACK_DEFICIT})
    """),
    # The winner was up big and let it close. Whether that covered a spread is a
    # separate question the leg ledger answers; this is the shape, not the result.
    ("BACKDOOR", f"""
        GREATEST(gs.max_home_lead, gs.max_away_lead) >= {BLOWOUT_LEAD}
        AND abs(gs.home_margin)
            <= GREATEST(gs.max_home_lead, gs.max_away_lead) - {BACKDOOR_SHRINK}
        AND gs.late_trail_points > 0
    """),
    ("GARBAGE_TIME_PASS", f"""
        gs.q4_trail_plays >= {MIN_LATE_PLAYS}
        AND gs.q4_trail_pass_rate >= thr.garbage
    """),
    ("CLOCK_KILL", f"""
        gs.q4_lead_plays >= {MIN_LATE_PLAYS}
        AND gs.q4_lead_run_rate >= thr.clock
    """),
    # Led by double digits after one quarter and finished at least that much
    # worse off. The early lead was not the game.
    # --- sequence -----------------------------------------------------------
    # Everything above reads totals and peaks. These read order.
    ("TRADED_HAYMAKERS", """
        gs.home_max_run >= 14 AND gs.away_max_run >= 14
    """),
    # Nobody ever took the lead back. NULL here means the leader never changed
    # hands at all, which is exactly the condition — a game tied and untied is
    # not a change of hands, and the sequence builder already excludes ties.
    # home_q1_points is the witness that the sequence was built at all: it is
    # 0 for a scoreless quarter and NULL only when the timeline is missing.
    # Without that guard this fires on every game awaiting a backfill, because
    # "no lead change recorded" and "nothing recorded" look identical.
    # Also ahead at the first break. Without that this is just "the lead never
    # changed hands", which is 65% of college games because the favourites are
    # so large -- true, and too common to be worth saying. Wire to wire should
    # mean ahead from early on and never headed, which is both the literal sense
    # and the rarer, more informative one.
    ("WIRE_TO_WIRE", """
        gs.home_q1_points IS NOT NULL
        AND gs.last_lead_change_sec IS NULL AND gs.home_margin <> 0
        AND gs.margin_end_q1 <> 0
        AND sign(gs.margin_end_q1) = sign(gs.home_margin)
    """),
    ("LATE_LEAD_CHANGE", """
        gs.last_lead_change_sec IS NOT NULL AND gs.last_lead_change_sec <= 300
    """),
    # The losing side put together two unanswered scores in the fourth and still
    # lost. This is the shape of a game that reads close at the end and was not.
    ("COMEBACK_BID_FAILED", """
        (gs.home_margin < 0 AND gs.home_max_run >= 14 AND gs.home_max_run_end_q >= 4)
        OR (gs.home_margin > 0 AND gs.away_max_run >= 14 AND gs.away_max_run_end_q >= 4)
    """),
    ("SLOW_BURN", """
        gs.home_q1_points = 0 AND gs.away_q1_points = 0
    """),
    ("FAST_START_FADE", f"""
        gs.margin_end_q1 IS NOT NULL
        AND abs(gs.margin_end_q1) >= {FADE_LEAD}
        AND (gs.home_margin - gs.margin_end_q1) * sign(gs.margin_end_q1) <= -{FADE_LEAD}
    """),
]

_LABEL = f"""
    WITH thresholds AS (
        SELECT g2.league,
               percentile_cont({MIX_PERCENTILE}) WITHIN GROUP (ORDER BY gs2.q4_trail_pass_rate)
                   AS garbage,
               percentile_cont({MIX_PERCENTILE}) WITHIN GROUP (ORDER BY gs2.q4_lead_run_rate)
                   AS clock
        FROM game_state gs2 JOIN games g2 USING (game_id)
        WHERE gs2.q4_trail_plays >= {MIN_LATE_PLAYS} AND gs2.q4_lead_plays >= {MIN_LATE_PLAYS}
        GROUP BY g2.league
    )
    INSERT INTO taggings (tag_id, entity_type, entity_id, weight, tagged_by)
    SELECT t.tag_id, 'game', gs.game_id, 1.0, 'engine'
    FROM game_state gs
    JOIN games g ON g.game_id = gs.game_id
    JOIN thresholds thr ON thr.league = g.league
    LEFT JOIN game_features gf ON gf.game_id = gs.game_id
    CROSS JOIN (SELECT tag_id FROM tags WHERE slug = :slug) t
    WHERE g.league = ANY(:leagues) AND ({{predicate}})
    ON CONFLICT (tag_id, entity_type, entity_id) DO NOTHING
"""


async def label(leagues: list[str], reset: bool) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        if reset:
            n = (await conn.execute(text("""
                DELETE FROM taggings USING tags
                WHERE taggings.tag_id = tags.tag_id
                  AND tags.dimension = 'script' AND taggings.entity_type = 'game'
            """))).rowcount
            log.info("cleared %d existing script labels", n)

        for slug, predicate in SCRIPTS:
            await conn.execute(
                text(_LABEL.format(predicate=predicate)),
                {"slug": slug, "leagues": leagues},
            )

        rows = (await conn.execute(text("""
            SELECT t.slug, g.league, count(*) AS n,
                   round(100.0 * count(*) / NULLIF(
                       (SELECT count(*) FROM game_state gs2
                        JOIN games g2 USING (game_id) WHERE g2.league = g.league), 0), 1) AS pct
            FROM taggings tg
            JOIN tags t ON t.tag_id = tg.tag_id
            JOIN games g ON g.game_id = tg.entity_id
            WHERE t.dimension = 'script' AND tg.entity_type = 'game'
            GROUP BY 1, 2 ORDER BY 2, 3 DESC
        """))).mappings().all()

    league = None
    for r in rows:
        if r["league"] != league:
            league = r["league"]
            log.info("\n%s", league)
        log.info("  %-18s %6d  %5s%% of games", r["slug"], r["n"], r["pct"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", nargs="+", default=["nfl", "ncaaf"])
    ap.add_argument("--reset", action="store_true", default=True)
    args = ap.parse_args()
    asyncio.run(label(args.league, args.reset))
