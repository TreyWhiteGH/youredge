"""Team defense endpoints — unit rating card and defender-absence impact.

GET /teams/{team_id}/defense                        rating card vs league
GET /teams/{team_id}/defense/absence?player_id=...  on/off + who plugs in
"""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from youredge.db import get_engine
from youredge.tendencies.defense import defender_onoff, team_defense

router = APIRouter(tags=["teams"])

DEFAULT_SEASONS = [2023, 2024, 2025]


@router.get("/teams/{team_id}/defense")
async def defense_card(team_id: str, seasons: list[int] = Query(default=DEFAULT_SEASONS)):
    async with get_engine().connect() as conn:
        card = await team_defense(conn, team_id, seasons)
    if not card:
        raise HTTPException(status_code=404, detail=f"no defensive plays for {team_id}")
    return card


@router.get("/teams/{team_id}/defense/absence")
async def defense_absence(
    team_id: str,
    player_id: str = Query(description="canonical id, e.g. nfl:00-0036130"),
    seasons: list[int] = Query(default=DEFAULT_SEASONS),
):
    async with get_engine().connect() as conn:
        player = (await conn.execute(
            text("SELECT player_id, name, position FROM players WHERE player_id = :pid"),
            {"pid": player_id},
        )).mappings().first()
        if player is None:
            raise HTTPException(status_code=404, detail=f"unknown player_id {player_id}")

        onoff = await defender_onoff(conn, player_id, seasons)

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
            prof = (await conn.execute(
                text("""
                    SELECT count(*) AS games,
                           round(avg(sc.defense_pct)::numeric, 3) AS avg_snap_pct,
                           sum((s.stats->>'def_tackles_solo')::real) AS tackles_solo,
                           sum((s.stats->>'def_sacks')::real) AS sacks,
                           sum((s.stats->>'def_interceptions')::real) AS interceptions,
                           sum((s.stats->>'def_pass_defended')::real) AS passes_defended
                    FROM player_game_stats s
                    LEFT JOIN snap_counts sc ON sc.player_id = s.player_id
                         AND sc.game_id = s.game_id
                    WHERE s.player_id = :pid AND s.season = ANY(:seasons)
                """),
                {"pid": backup["player_id"], "seasons": seasons},
            )).mappings().first()
            backup_profile = {**dict(backup), **{k: (float(v) if v is not None else None)
                                                 for k, v in dict(prof).items()}}

    return {
        "team_id": team_id,
        "player": dict(player),
        "depth_slot": dict(slot) if slot else None,
        "onoff": onoff,
        "backup": backup_profile,
    }
