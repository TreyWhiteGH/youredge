"""Tendency surfaces — first real (non-stub) data endpoints."""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from youredge.db import get_engine
from youredge.tendencies.pass_rate import pass_rate_by_score_state

router = APIRouter(tags=["tendencies"])


@router.get("/tendencies/pass-rate")
async def pass_rate(
    team_id: str = Query(description="Canonical team id, e.g. nfl:BAL"),
    seasons: list[int] = Query(default=[2023, 2024, 2025]),
):
    async with get_engine().connect() as conn:
        exists = await conn.execute(
            text("SELECT 1 FROM teams WHERE team_id = :tid"), {"tid": team_id}
        )
        if exists.first() is None:
            raise HTTPException(status_code=404, detail=f"unknown team_id {team_id}")
        cells = await pass_rate_by_score_state(conn, team_id, seasons)
    return {"team_id": team_id, "seasons": seasons, "cells": cells}
