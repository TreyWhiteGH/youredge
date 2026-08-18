"""SGP endpoints — the routes apps/web/src/sgp/lib/api.js already calls.

Phase 0: honest stubs returning 501 with a machine-readable phase marker,
so the UI can fall back to mocks and we can light these up one at a time.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter(tags=["sgp"])


class GenerateRequest(BaseModel):
    league: str = Field(pattern="^(nfl|ncaaf)$")
    game_id: str
    sportsbook: str
    risk_mode: str = Field(default="balanced", pattern="^(sharp|balanced|lotto)$")


class AnchorRequest(BaseModel):
    league: str
    game_id: str
    sportsbook: str
    anchor: str  # e.g. "BAL -6.5"


class HypothesisRequest(BaseModel):
    league: str
    game_id: str
    sportsbook: str
    hypothesis: str


class CritiqueRequest(BaseModel):
    league: str
    game_id: str
    sportsbook: str
    legs: list[str]
    quoted_odds: str | None = None


def _not_implemented(mode: str) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={
            "error": f"{mode} not implemented yet",
            "phase": "0-foundation",
            "detail": "Engine is ingesting data; sim + pricing land in Phases 1-2.",
        },
    )


@router.get("/odds")
async def get_odds(league: str, game_id: str, sportsbook: str):
    return _not_implemented("odds")


@router.post("/sgp/generate")
async def generate(req: GenerateRequest):
    return _not_implemented("generate")


@router.post("/sgp/build-around-pick")
async def build_around_pick(req: AnchorRequest):
    return _not_implemented("build-around-pick")


@router.post("/sgp/test-hypothesis")
async def test_hypothesis(req: HypothesisRequest):
    return _not_implemented("test-hypothesis")


@router.post("/sgp/critique")
async def critique(req: CritiqueRequest):
    return _not_implemented("critique")


@router.post("/sgp/save")
async def save_sgp():
    return _not_implemented("save")


@router.get("/sgp/history")
async def history():
    return _not_implemented("history")
