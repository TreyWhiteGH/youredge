"""Offense rating card — what the unit generates, with league ranks (1 = best).

Mirror of defense.py's card from the posteam side: raw, not opponent-adjusted.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

_CARD = text("""
    WITH o AS (
        SELECT p.posteam_id,
               p.play_type, p.epa, p.success, p.yards_gained, p.touchdown,
               p.interception, p.complete_pass, p.qb_dropback,
               p.yardline_100, p.quarter, p.score_differential
        FROM plays p JOIN games g ON g.game_id = p.game_id
        WHERE g.league = :league AND g.season = ANY(:seasons)
          AND p.play_type IN ('pass', 'run') AND p.down IS NOT NULL
    ),
    per_team AS (
        SELECT posteam_id,
          count(*) FILTER (WHERE qb_dropback)                    AS dropbacks,
          avg(epa)          FILTER (WHERE qb_dropback)           AS pass_epa,
          avg(success::int) FILTER (WHERE qb_dropback)           AS pass_success,
          avg(complete_pass::int) FILTER (WHERE play_type='pass') AS comp_rate,
          avg(interception::int)  FILTER (WHERE play_type='pass') AS int_rate,
          avg((yards_gained >= 15)::int)
              FILTER (WHERE play_type='pass' AND complete_pass)  AS explosive_pass,
          count(*) FILTER (WHERE play_type='run')                AS rushes,
          avg(epa)          FILTER (WHERE play_type='run')       AS rush_epa,
          avg(success::int) FILTER (WHERE play_type='run')       AS rush_success,
          avg((yards_gained >= 10)::int)
              FILTER (WHERE play_type='run')                     AS explosive_rush,
          avg(touchdown::int) FILTER (WHERE yardline_100 <= 20)  AS rz_td_rate,
          avg(epa) FILTER (WHERE quarter >= 4
                           AND abs(score_differential) <= 8)     AS late_close_epa
        FROM o GROUP BY posteam_id
    )
    SELECT *,
        rank() OVER (ORDER BY pass_epa DESC)       AS pass_rank,
        rank() OVER (ORDER BY rush_epa DESC)       AS rush_rank,
        rank() OVER (ORDER BY late_close_epa DESC) AS late_close_rank
    FROM per_team
""")


def _r(v, nd=4):
    return round(float(v), nd) if v is not None else None


async def team_offense(conn: AsyncConnection, team_id: str, seasons: list[int]) -> dict[str, Any]:
    league = team_id.split(":", 1)[0]
    rows = (await conn.execute(
        _CARD, {"seasons": seasons, "league": league})).mappings().all()
    mine = next((r for r in rows if r["posteam_id"] == team_id), None)
    if mine is None:
        return {}
    lg = {k: sum(r[k] for r in rows if r[k] is not None) / len(rows)
          for k in ("pass_epa", "rush_epa", "comp_rate", "explosive_pass", "explosive_rush")}
    return {
        "team_id": team_id, "seasons": seasons, "teams_ranked": len(rows),
        "pass_offense": {
            "dropbacks": mine["dropbacks"],
            "epa": _r(mine["pass_epa"]),
            "league_avg": _r(lg["pass_epa"]),
            "rank": mine["pass_rank"],
            "success_rate": _r(mine["pass_success"]),
            "comp_rate": _r(mine["comp_rate"]),
            "int_rate": _r(mine["int_rate"]),
            "explosive_rate": _r(mine["explosive_pass"]),
        },
        "run_offense": {
            "rushes": mine["rushes"],
            "epa": _r(mine["rush_epa"]),
            "league_avg": _r(lg["rush_epa"]),
            "rank": mine["rush_rank"],
            "success_rate": _r(mine["rush_success"]),
            "explosive_rate": _r(mine["explosive_rush"]),
        },
        "situational": {
            "rz_td_rate": _r(mine["rz_td_rate"]),
            "late_close_epa": _r(mine["late_close_epa"]),
            "late_close_rank": mine["late_close_rank"],
        },
    }
