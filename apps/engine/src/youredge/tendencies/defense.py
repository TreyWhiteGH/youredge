"""Defense rating card — what the unit allows, with league ranks (1 = best,
i.e. lowest EPA allowed). Raw allowed numbers, not opponent-adjusted — good enough
to rank units and feed script priors; opponent adjustment is a Phase 2 refinement.

On/off splits live in tendencies/onoff.py (side-aware, shared with offense).
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

_CARD = text("""
    WITH d AS (
        SELECT p.defteam_id,
               p.play_type, p.epa, p.success, p.yards_gained, p.touchdown,
               p.interception, p.complete_pass,
               -- NCAAF has no qb_dropback (nflverse-only); play_type='pass'
               -- already includes sacks/INTs via cfbd_map
               COALESCE(p.qb_dropback, p.play_type = 'pass') AS qb_dropback,
               p.yardline_100, p.quarter, p.score_differential
        FROM plays p JOIN games g ON g.game_id = p.game_id
        JOIN teams tm ON tm.team_id = p.defteam_id
        WHERE g.league = :league AND g.season = ANY(:seasons)
          -- rank within division: FCS crossover opponents would otherwise
          -- pad the field to 237 and make FBS ranks look better than they are
          AND (tm.classification = 'fbs' OR g.league = 'nfl')
          AND p.play_type IN ('pass', 'run') AND p.down IS NOT NULL
    ),
    per_team AS (
        SELECT defteam_id,
          count(*) FILTER (WHERE qb_dropback)                    AS dropbacks_faced,
          avg(epa)         FILTER (WHERE qb_dropback)            AS pass_epa_allowed,
          avg(success::int) FILTER (WHERE qb_dropback)           AS pass_success_allowed,
          avg(complete_pass::int) FILTER (WHERE play_type='pass') AS comp_rate_allowed,
          avg(interception::int) FILTER (WHERE play_type='pass') AS int_rate,
          avg((yards_gained >= 15)::int)
              FILTER (WHERE play_type='pass' AND complete_pass)  AS explosive_pass_allowed,
          count(*) FILTER (WHERE play_type='run')                AS rushes_faced,
          avg(epa)          FILTER (WHERE play_type='run')       AS rush_epa_allowed,
          avg(success::int) FILTER (WHERE play_type='run')       AS rush_success_allowed,
          avg((yards_gained >= 10)::int)
              FILTER (WHERE play_type='run')                     AS explosive_rush_allowed,
          avg(touchdown::int) FILTER (WHERE yardline_100 <= 20)  AS rz_td_rate_allowed,
          avg(epa) FILTER (WHERE quarter >= 4
                           AND abs(score_differential) <= 8)     AS late_close_epa_allowed
        FROM d GROUP BY defteam_id
    )
    SELECT *,
        rank() OVER (ORDER BY pass_epa_allowed)      AS pass_rank,
        rank() OVER (ORDER BY rush_epa_allowed)      AS rush_rank,
        rank() OVER (ORDER BY late_close_epa_allowed) AS late_close_rank
    FROM per_team
""")


def _r(v, nd=4):
    return round(float(v), nd) if v is not None else None


async def team_defense(conn: AsyncConnection, team_id: str, seasons: list[int]) -> dict[str, Any]:
    league = team_id.split(":", 1)[0]
    rows = (await conn.execute(
        _CARD, {"seasons": seasons, "league": league})).mappings().all()
    mine = next((r for r in rows if r["defteam_id"] == team_id), None)
    if mine is None:
        return {}
    lg = {k: sum(r[k] for r in rows if r[k] is not None) / len(rows)
          for k in ("pass_epa_allowed", "rush_epa_allowed", "comp_rate_allowed",
                    "explosive_pass_allowed", "explosive_rush_allowed")}
    return {
        "team_id": team_id, "seasons": seasons, "teams_ranked": len(rows),
        "pass_defense": {
            "dropbacks_faced": mine["dropbacks_faced"],
            "epa_allowed": _r(mine["pass_epa_allowed"]),
            "league_avg": _r(lg["pass_epa_allowed"]),
            "rank": mine["pass_rank"],
            "success_rate_allowed": _r(mine["pass_success_allowed"]),
            "comp_rate_allowed": _r(mine["comp_rate_allowed"]),
            "int_rate": _r(mine["int_rate"]),
            "explosive_rate_allowed": _r(mine["explosive_pass_allowed"]),
        },
        "run_defense": {
            "rushes_faced": mine["rushes_faced"],
            "epa_allowed": _r(mine["rush_epa_allowed"]),
            "league_avg": _r(lg["rush_epa_allowed"]),
            "rank": mine["rush_rank"],
            "success_rate_allowed": _r(mine["rush_success_allowed"]),
            "explosive_rate_allowed": _r(mine["explosive_rush_allowed"]),
        },
        "situational": {
            "rz_td_rate_allowed": _r(mine["rz_td_rate_allowed"]),
            "late_close_epa_allowed": _r(mine["late_close_epa_allowed"]),
            "late_close_rank": mine["late_close_rank"],
        },
    }

