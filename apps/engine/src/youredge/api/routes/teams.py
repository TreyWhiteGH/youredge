"""Team unit endpoints — rating cards and player-absence impact, both sides.

GET /teams/{team_id}/defense                        defense card vs league
GET /teams/{team_id}/offense                        offense card vs league
GET /teams/{team_id}/defense/absence?player_id=...  on/off + who plugs in
GET /teams/{team_id}/offense/absence?player_id=...  same for offensive players
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from youredge.db import get_engine
from youredge.tendencies.defense import team_defense
from youredge.tendencies.offense import team_offense
from youredge.tendencies.onoff import player_onoff

router = APIRouter(tags=["teams"])

DEFAULT_SEASONS = [2023, 2024, 2025]

# Backup production profile differs by side: box-score keys for defenders live
# in the stats JSONB; offensive volume lives in typed columns.
_BACKUP_DEF = text("""
    SELECT count(*) AS games,
           round(avg(sc.defense_pct)::numeric, 3) AS avg_snap_pct,
           sum((s.stats->>'def_tackles_solo')::real) AS tackles_solo,
           sum((s.stats->>'def_sacks')::real) AS sacks,
           sum((s.stats->>'def_interceptions')::real) AS interceptions,
           sum((s.stats->>'def_pass_defended')::real) AS passes_defended
    FROM player_game_stats s
    LEFT JOIN snap_counts sc ON sc.player_id = s.player_id AND sc.game_id = s.game_id
    WHERE s.player_id = :pid AND s.season = ANY(:seasons)
""")
_BACKUP_OFF = text("""
    SELECT count(*) AS games,
           round(avg(sc.offense_pct)::numeric, 3) AS avg_snap_pct,
           sum(s.attempts) AS attempts, sum(s.passing_yards) AS passing_yards,
           sum(s.passing_tds) AS passing_tds,
           sum(s.carries) AS carries, sum(s.rushing_yards) AS rushing_yards,
           sum(s.targets) AS targets, sum(s.receptions) AS receptions,
           sum(s.receiving_yards) AS receiving_yards,
           round(avg(s.target_share)::numeric, 3) AS avg_target_share
    FROM player_game_stats s
    LEFT JOIN snap_counts sc ON sc.player_id = s.player_id AND sc.game_id = s.game_id
    WHERE s.player_id = :pid AND s.season = ANY(:seasons)
""")


@router.get("/teams/{team_id}/defense")
async def defense_card(team_id: str, seasons: list[int] = Query(default=DEFAULT_SEASONS)):
    async with get_engine().connect() as conn:
        card = await team_defense(conn, team_id, seasons)
    if not card:
        raise HTTPException(status_code=404, detail=f"no defensive plays for {team_id}")
    return card


@router.get("/teams/{team_id}/offense")
async def offense_card(team_id: str, seasons: list[int] = Query(default=DEFAULT_SEASONS)):
    async with get_engine().connect() as conn:
        card = await team_offense(conn, team_id, seasons)
    if not card:
        raise HTTPException(status_code=404, detail=f"no offensive plays for {team_id}")
    return card


async def _absence(team_id: str, player_id: str, seasons: list[int],
                   side: Literal["offense", "defense"]):
    async with get_engine().connect() as conn:
        player = (await conn.execute(
            text("SELECT player_id, name, position FROM players WHERE player_id = :pid"),
            {"pid": player_id},
        )).mappings().first()
        if player is None:
            raise HTTPException(status_code=404, detail=f"unknown player_id {player_id}")

        onoff = await player_onoff(conn, player_id, seasons, side)

        slot = (await conn.execute(
            text("""
                SELECT pos_grp, pos_name, pos_abb, pos_slot, pos_rank
                FROM depth_chart WHERE team_id = :tid AND player_id = :pid
                ORDER BY pos_rank LIMIT 1
            """),
            {"tid": team_id, "pid": player_id},
        )).mappings().first()

        backup = None
        if slot:
            backup = (await conn.execute(
                text("""
                    SELECT d.player_id, p.name, p.position
                    FROM depth_chart d JOIN players p ON p.player_id = d.player_id
                    WHERE d.team_id = :tid AND d.pos_grp = :grp AND d.pos_slot = :slot
                      AND d.pos_rank = :next_rank
                """),
                {"tid": team_id, "grp": slot["pos_grp"], "slot": slot["pos_slot"],
                 "next_rank": slot["pos_rank"] + 1},
            )).mappings().first()

        backup_profile = None
        if backup:
            q = _BACKUP_DEF if side == "defense" else _BACKUP_OFF
            prof = (await conn.execute(
                q, {"pid": backup["player_id"], "seasons": seasons},
            )).mappings().first()
            backup_profile = {**dict(backup), **{k: (float(v) if v is not None else None)
                                                 for k, v in dict(prof).items()}}

    return {
        "team_id": team_id,
        "side": side,
        "player": dict(player),
        "depth_slot": dict(slot) if slot else None,
        "onoff": onoff,
        "backup": backup_profile,
    }


@router.get("/teams/{team_id}/defense/absence")
async def defense_absence(
    team_id: str,
    player_id: str = Query(description="canonical id, e.g. nfl:00-0033886"),
    seasons: list[int] = Query(default=DEFAULT_SEASONS),
):
    return await _absence(team_id, player_id, seasons, "defense")


@router.get("/teams/{team_id}/offense/absence")
async def offense_absence(
    team_id: str,
    player_id: str = Query(description="canonical id, e.g. nfl:00-0036322"),
    seasons: list[int] = Query(default=DEFAULT_SEASONS),
):
    return await _absence(team_id, player_id, seasons, "offense")
