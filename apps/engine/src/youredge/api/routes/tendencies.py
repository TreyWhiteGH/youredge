"""Tendency surfaces — first real (non-stub) data endpoints.

pass-rate describes play calling. The three drive surfaces below are the
simulator's parameters: how a possession ends from a given field position, how
long possessions take, and how much a defence gives up late versus early.
"""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from youredge.db import get_engine
from youredge.tendencies.drive_profile import drive_outcomes, fatigue, pace
from youredge.tendencies.pass_rate import pass_rate_by_score_state

router = APIRouter(tags=["tendencies"])

DEFAULT_SEASONS = [2023, 2024, 2025]


async def _require_team(conn, team_id: str) -> None:
    exists = await conn.execute(
        text("SELECT 1 FROM teams WHERE team_id = :tid"), {"tid": team_id}
    )
    if exists.first() is None:
        raise HTTPException(status_code=404, detail=f"unknown team_id {team_id}")


async def _require_drive_data(conn, team_id: str) -> None:
    """Drive surfaces read `drives`, which is populated per league by a job.

    A 501 rather than an empty result: "this team has no drives" and "this league
    has no drive data" are exactly the two things the product refuses to blur.
    """
    loaded = await conn.execute(
        text("""
            SELECT 1 FROM drives d JOIN games g USING (game_id)
            WHERE g.league = :lg LIMIT 1
        """),
        {"lg": team_id.split(":", 1)[0]},
    )
    if loaded.first() is None:
        raise HTTPException(
            status_code=501,
            detail={
                "error": "drive data not loaded for this league",
                "phase": "1-simulator",
                "detail": "NFL: modeling.drives. NCAAF: ingest.cfbd_drives.",
            },
        )


@router.get("/tendencies/pass-rate")
async def pass_rate(
    team_id: str = Query(description="Canonical team id, e.g. nfl:BAL"),
    seasons: list[int] = Query(default=DEFAULT_SEASONS),
):
    async with get_engine().connect() as conn:
        await _require_team(conn, team_id)
        cells = await pass_rate_by_score_state(conn, team_id, seasons)
    return {"team_id": team_id, "seasons": seasons, "cells": cells}


@router.get("/tendencies/drive-outcomes")
async def drive_outcomes_route(
    team_id: str = Query(description="Canonical team id, e.g. nfl:BAL"),
    seasons: list[int] = Query(default=DEFAULT_SEASONS),
):
    """How drives end, by starting field position. The simulator's kernel."""
    async with get_engine().connect() as conn:
        await _require_team(conn, team_id)
        await _require_drive_data(conn, team_id)
        buckets = await drive_outcomes(conn, team_id, seasons)
    return {"team_id": team_id, "seasons": seasons, "buckets": buckets}


@router.get("/tendencies/pace")
async def pace_route(
    team_id: str = Query(description="Canonical team id, e.g. nfl:BAL"),
    seasons: list[int] = Query(default=DEFAULT_SEASONS),
):
    """Seconds per play and plays per drive, by score state."""
    async with get_engine().connect() as conn:
        await _require_team(conn, team_id)
        await _require_drive_data(conn, team_id)
        cells = await pace(conn, team_id, seasons)
    return {"team_id": team_id, "seasons": seasons, "cells": cells}


@router.get("/tendencies/fatigue")
async def fatigue_route(
    team_id: str = Query(description="Canonical team id, e.g. nfl:BAL"),
    seasons: list[int] = Query(default=DEFAULT_SEASONS),
):
    """Defensive yards per play, first half vs second, against the league split."""
    async with get_engine().connect() as conn:
        await _require_team(conn, team_id)
        await _require_drive_data(conn, team_id)
        split = await fatigue(conn, team_id, seasons)
    return {"team_id": team_id, "seasons": seasons, **split}
