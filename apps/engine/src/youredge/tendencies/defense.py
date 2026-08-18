"""Defense surfaces: unit rating card + defender on/off splits.

Rating card: what the defense allows, split pass/run, with league rank (1 = best,
i.e. lowest EPA allowed). Raw allowed numbers, not opponent-adjusted — good enough
to rank units and feed script priors; opponent adjustment is a Phase 2 refinement.

On/off: the honest "what do they miss" measure without tracking data — defense
performance in games the defender played (>= 20% of defensive snaps) vs games
their team played without them. Correlational: injuries cluster and opponents
vary, so deltas ship with sample sizes and are meant to be read with them.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

ON_SNAP_PCT = 0.20

_CARD = text("""
    WITH d AS (
        SELECT p.defteam_id,
               p.play_type, p.epa, p.success, p.yards_gained, p.touchdown,
               p.interception, p.complete_pass, p.qb_dropback,
               p.yardline_100, p.quarter, p.score_differential
        FROM plays p JOIN games g ON g.game_id = p.game_id
        WHERE g.league = 'nfl' AND g.season = ANY(:seasons)
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

_ONOFF = text("""
    WITH played AS (
        SELECT game_id, team_id FROM snap_counts
        WHERE player_id = :pid AND defense_pct >= :thresh
    ),
    team_games AS (
        -- games the defender's team(s) played in these seasons
        SELECT g.game_id, tg.team_id
        FROM games g
        JOIN (SELECT DISTINCT team_id FROM played) tg
          ON g.home_team_id = tg.team_id OR g.away_team_id = tg.team_id
        WHERE g.league = 'nfl' AND g.season = ANY(:seasons) AND g.status = 'final'
    ),
    labeled AS (
        SELECT t.game_id, t.team_id, (p.game_id IS NOT NULL) AS is_on
        FROM team_games t LEFT JOIN played p ON p.game_id = t.game_id
    )
    SELECT l.is_on,
        count(DISTINCT l.game_id)                              AS games,
        avg(p.epa) FILTER (WHERE p.qb_dropback)                AS pass_epa_allowed,
        avg(p.success::int) FILTER (WHERE p.qb_dropback)       AS pass_success_allowed,
        avg(p.epa) FILTER (WHERE p.play_type = 'run')          AS rush_epa_allowed,
        avg(p.success::int) FILTER (WHERE p.play_type = 'run') AS rush_success_allowed,
        avg((p.yards_gained >= 15)::int)
            FILTER (WHERE p.play_type = 'pass' AND p.complete_pass) AS explosive_pass_allowed
    FROM labeled l
    JOIN plays p ON p.game_id = l.game_id AND p.defteam_id = l.team_id
    WHERE p.play_type IN ('pass', 'run') AND p.down IS NOT NULL
    GROUP BY l.is_on
""")


def _r(v, nd=4):
    return round(float(v), nd) if v is not None else None


async def team_defense(conn: AsyncConnection, team_id: str, seasons: list[int]) -> dict[str, Any]:
    rows = (await conn.execute(_CARD, {"seasons": seasons})).mappings().all()
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


async def defender_onoff(conn: AsyncConnection, player_id: str, seasons: list[int]) -> dict[str, Any]:
    rows = {r["is_on"]: r for r in
            (await conn.execute(_ONOFF, {"pid": player_id, "seasons": seasons,
                                         "thresh": ON_SNAP_PCT})).mappings().all()}
    on, off = rows.get(True), rows.get(False)

    def block(r):
        if r is None:
            return None
        return {
            "games": r["games"],
            "pass_epa_allowed": _r(r["pass_epa_allowed"]),
            "pass_success_allowed": _r(r["pass_success_allowed"]),
            "rush_epa_allowed": _r(r["rush_epa_allowed"]),
            "rush_success_allowed": _r(r["rush_success_allowed"]),
            "explosive_pass_allowed": _r(r["explosive_pass_allowed"]),
        }

    out = {"player_id": player_id, "seasons": seasons,
           "on": block(on), "off": block(off), "delta_when_out": None}
    if on and off:
        out["delta_when_out"] = {
            "pass_epa_allowed": _r(off["pass_epa_allowed"] - on["pass_epa_allowed"]),
            "rush_epa_allowed": _r(off["rush_epa_allowed"] - on["rush_epa_allowed"]),
            "note": "positive = defense worse without them; correlational, mind the sample sizes",
        }
    return out
