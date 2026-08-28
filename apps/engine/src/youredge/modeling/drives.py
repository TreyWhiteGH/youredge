"""Derive the drives table from plays.

One row per possession: where it started, how it ended, how long it took. This is
what the drive-level simulator is fit from — its kernel is "given this starting
state, sample a result and a duration", and each row here is one observation of
exactly that.

Rebuildable at will: plays is the source of truth, this is a projection of it.

    docker compose run --rm ingest python -m youredge.modeling.drives --league nfl

Result precedence matters and is not arbitrary. A drive that ends in a fumble on a
completed pass is a FUMBLE_LOST, not a completion; a drive with a touchdown is a
TD whatever else happened on the way. Scoring plays are checked first, then
turnovers, then the ways a drive ends without either.

NFL only. NCAAF is refused rather than approximated — see build() for why.
UNKNOWN is named that way deliberately: it is a gap still to be closed, not a
residual bucket to be modelled around.
"""

import argparse
import asyncio
import logging

from sqlalchemy import text

from youredge.db import get_engine

log = logging.getLogger(__name__)

_BUILD = text("""
    WITH ordered AS (
        SELECT p.*,
               row_number() OVER w_asc  AS rn_asc,
               row_number() OVER w_desc AS rn_desc,
               count(*)     OVER (PARTITION BY p.game_id, p.drive_num) AS n_plays
        FROM plays p
        JOIN games g ON g.game_id = p.game_id
        WHERE g.league = :league
          AND p.drive_num IS NOT NULL
          AND p.posteam_id IS NOT NULL
        WINDOW
            -- Rank only scrimmage plays. nflverse files the kickoff under the
            -- receiving team's drive, and a kickoff's yardline_100 is the kicking
            -- spot — so taking the drive's literal first row put every touchback
            -- drive's start at the opponent's 35 instead of the own 25.
            -- `down IS NOT NULL` is what separates a snap from a kick.
            w_asc  AS (PARTITION BY p.game_id, p.drive_num
                       ORDER BY (p.down IS NULL),
                                p.game_seconds_remaining DESC NULLS LAST, p.play_id),
            w_desc AS (PARTITION BY p.game_id, p.drive_num
                       ORDER BY (p.down IS NULL),
                                p.game_seconds_remaining ASC  NULLS LAST, p.play_id DESC)
    ),
    agg AS (
        SELECT
            game_id,
            drive_num,
            max(posteam_id) FILTER (WHERE rn_asc = 1) AS posteam_id,
            max(defteam_id) FILTER (WHERE rn_asc = 1) AS defteam_id,
            max(quarter)                FILTER (WHERE rn_asc = 1) AS start_quarter,
            max(game_seconds_remaining) FILTER (WHERE rn_asc = 1) AS start_seconds,
            max(yardline_100)           FILTER (WHERE rn_asc = 1) AS start_yardline,
            max(score_differential)     FILTER (WHERE rn_asc = 1) AS start_score_diff,
            min(game_seconds_remaining) FILTER (WHERE rn_desc = 1) AS end_seconds,
            max(yardline_100)           FILTER (WHERE rn_desc = 1) AS end_yardline,
            max(down)                   FILTER (WHERE rn_desc = 1) AS last_down,

            count(*) FILTER (WHERE play_type IN ('pass', 'run'))   AS plays,
            count(*) FILTER (WHERE play_type = 'pass')             AS pass_plays,
            count(*) FILTER (WHERE play_type = 'run')              AS rush_plays,
            sum(yards_gained) FILTER (WHERE play_type IN ('pass', 'run')) AS yards,

            bool_or(touchdown AND play_type IN ('pass', 'run'))    AS had_td,
            bool_or(interception)                                  AS had_int,
            bool_or(fumble_lost)                                   AS had_fumble,
            bool_or(safety)                                        AS had_safety,
            bool_or(play_type = 'punt')                            AS had_punt,
            max(field_goal_result)                                 AS fg_result
        FROM ordered
        GROUP BY game_id, drive_num
    ),
    -- A drive with no outcome play ran out of clock. Detect that structurally —
    -- is this the last possession of its half? — rather than by thresholding the
    -- clock, because the game clock expires *during* the final play and so never
    -- reliably reads zero on the row we have.
    halved AS (
        SELECT a.*,
               a.drive_num = max(a.drive_num) OVER (
                   PARTITION BY a.game_id, (a.start_quarter <= 2)
               ) AS is_last_of_half
        FROM agg a
        WHERE a.start_quarter IS NOT NULL
    )
    INSERT INTO drives (
        game_id, drive_num, posteam_id, defteam_id,
        start_quarter, start_seconds, start_yardline, start_score_diff,
        result, points, defensive_td, plays, pass_plays, rush_plays, yards,
        seconds, end_yardline
    )
    SELECT
        game_id, drive_num, posteam_id, defteam_id,
        start_quarter, start_seconds, start_yardline, start_score_diff,
        CASE
            -- Turnovers outrank the touchdown flag. A drive ends at whichever
            -- comes first, so a TD *co-occurring* with an interception on the
            -- same drive is the return score, not an offensive one — nflverse
            -- files a pick-six as play_type='pass' with touchdown=1, which read
            -- naively credits it to the team that threw the pick.
            WHEN had_int              THEN 'INT'
            WHEN had_fumble           THEN 'FUMBLE_LOST'
            WHEN had_td               THEN 'TD'
            WHEN fg_result = 'made'   THEN 'FG_MADE'
            WHEN had_safety           THEN 'SAFETY'
            WHEN fg_result IS NOT NULL THEN 'FG_MISS'
            WHEN had_punt             THEN 'PUNT'
            -- A drive that simply stops on 4th down without punting or kicking
            -- turned the ball over on downs. Checked after the explicit outcomes
            -- so a blocked punt on 4th does not get miscounted here.
            WHEN last_down = 4        THEN 'DOWNS'
            WHEN is_last_of_half      THEN 'END_HALF'
            ELSE 'UNKNOWN'
        END AS result,
        -- Only the offence's own points. 7 approximates TD+PAT; two-point
        -- conversions and missed extra points are not modelled at this grain.
        CASE
            WHEN had_int OR had_fumble THEN 0
            WHEN had_td              THEN 7
            WHEN fg_result = 'made'  THEN 3
            ELSE 0
        END AS points,
        COALESCE(had_td AND (had_int OR had_fumble), FALSE) AS defensive_td,
        plays, pass_plays, rush_plays, yards,
        CASE WHEN start_seconds IS NOT NULL AND end_seconds IS NOT NULL
                  AND start_seconds >= end_seconds
             THEN start_seconds - end_seconds END AS seconds,
        end_yardline
    FROM halved
    ON CONFLICT (game_id, drive_num) DO UPDATE SET
        posteam_id = EXCLUDED.posteam_id, defteam_id = EXCLUDED.defteam_id,
        start_quarter = EXCLUDED.start_quarter, start_seconds = EXCLUDED.start_seconds,
        start_yardline = EXCLUDED.start_yardline, start_score_diff = EXCLUDED.start_score_diff,
        result = EXCLUDED.result, points = EXCLUDED.points,
        defensive_td = EXCLUDED.defensive_td,
        plays = EXCLUDED.plays, pass_plays = EXCLUDED.pass_plays,
        rush_plays = EXCLUDED.rush_plays, yards = EXCLUDED.yards,
        seconds = EXCLUDED.seconds, end_yardline = EXCLUDED.end_yardline
""")


class LeagueNotDerivable(RuntimeError):
    """The league's plays cannot express a drive result yet."""


async def build(league: str) -> int:
    # NCAAF is refused *here*, and handled elsewhere. This module derives drive
    # outcomes from play flags, and CFBD's play rows carry no `touchdown` and no
    # `field_goal_result` — both nflverse-only — so a college derivation produced
    # 36.9% UNKNOWN and not one scoring drive.
    #
    # The answer was not another data vendor but CFBD's own /drives endpoint,
    # which returns the outcome already resolved and names return touchdowns
    # separately. See ingest/cfbd_drives.py.
    if league == "ncaaf":
        raise LeagueNotDerivable(
            "NCAAF drives are ingested from CFBD /drives, not derived from plays "
            "— run: python -m youredge.ingest.cfbd_drives --seasons 2023 2024 2025"
        )

    engine = get_engine()
    async with engine.begin() as conn:
        res = await conn.execute(_BUILD, {"league": league})
        n = res.rowcount
        mix = (await conn.execute(
            text("""
                SELECT d.result, count(*) AS n
                FROM drives d JOIN games g USING (game_id)
                WHERE g.league = :lg GROUP BY 1 ORDER BY 2 DESC
            """),
            {"lg": league},
        )).mappings().all()
    total = sum(r["n"] for r in mix) or 1
    for r in mix:
        log.info("  %-12s %7d  %5.1f%%", r["result"], r["n"], 100 * r["n"] / total)
    return n


async def main(leagues: list[str]):
    for lg in leagues:
        try:
            n = await build(lg)
        except LeagueNotDerivable as e:
            log.warning("%s: skipped — %s", lg, e)
            continue
        log.info("%s: %d drives", lg, n)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", nargs="+", default=["nfl", "ncaaf"])
    args = parser.parse_args()
    asyncio.run(main(args.league))
