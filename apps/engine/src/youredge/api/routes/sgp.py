"""SGP endpoints — the routes apps/web/src/sgp/lib/api.js already calls.

Lit one at a time as the layer beneath each one becomes real. Critique is live:
it runs on counted history — the empirical leg surface plus de-vigged market
prices — and needs no simulator. The other three still return 501 with the phase
they are waiting on, because generating or pricing a parlay needs a joint
distribution that does not exist yet.

Critique deliberately does not return a combined price. It reports per-leg edge
against the sharpest book, which is a real number today, and pairwise redundancy
and script conflict from history, which are real findings today. Multiplying
historical base rates into an expected value would look like a price and would
not be one.
"""

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from youredge.db import get_engine
from youredge.legs import ledger_bets
from youredge.legs.critique import critique as run_critique
from youredge.legs.hypothesis import evaluate as run_hypothesis

log = logging.getLogger(__name__)
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
    """Test a stated theory against history, then against the price.

    Live, on the same counted surface Critique uses. Answers whether the claim
    holds and, separately, whether the market has already noticed — the second
    being the question that decides if a true theory is worth anything.
    """
    if not req.hypothesis or not req.hypothesis.strip():
        raise HTTPException(status_code=400, detail="no hypothesis supplied")

    async with get_engine().connect() as conn:
        known = await conn.execute(
            text("SELECT 1 FROM games WHERE game_id = :gid"), {"gid": req.game_id})
        if known.first() is None:
            raise HTTPException(status_code=404, detail=f"unknown game {req.game_id}")

        ledger = await conn.execute(
            text("""SELECT 1 FROM leg_outcomes lo JOIN games g USING (game_id)
                    WHERE g.league = :lg LIMIT 1"""), {"lg": req.league})
        if ledger.first() is None:
            return JSONResponse(status_code=501, content={
                "error": "no outcome ledger for this league",
                "phase": "layer-b",
                "detail": "Run make layer-b to build leg_outcomes.",
            })

        return await run_hypothesis(
            conn, req.league, req.game_id, req.sportsbook, req.hypothesis)


@router.post("/sgp/critique")
async def critique(req: CritiqueRequest):
    """Diagnose a slip: per-leg fair value, redundancy, script conflict.

    Live. Runs on counted outcomes and de-vigged prices; no model involved, and
    no combined price returned.
    """
    if not req.legs:
        raise HTTPException(status_code=400, detail="no legs supplied")

    async with get_engine().connect() as conn:
        known = await conn.execute(
            text("SELECT 1 FROM games WHERE game_id = :gid"), {"gid": req.game_id})
        if known.first() is None:
            raise HTTPException(status_code=404, detail=f"unknown game {req.game_id}")

        # The surface is per-league and built from finished games. Without it
        # there is nothing to critique against, and saying so beats returning an
        # empty analysis that reads like "no problems found".
        surface = await conn.execute(
            text("SELECT 1 FROM leg_pair_stats WHERE league = :lg LIMIT 1"),
            {"lg": req.league})
        if surface.first() is None:
            return JSONResponse(status_code=501, content={
                "error": "no empirical surface for this league",
                "phase": "layer-b",
                "detail": "Run make layer-b to build leg_pair_stats.",
            })

        result = await run_critique(
            conn, req.game_id, req.league, req.sportsbook, req.legs, req.quoted_odds)

    # A separate transaction, and deliberately after the answer is complete: the
    # critique is what the caller asked for, and a bookkeeping failure must not
    # turn a good one into an error. The pasted price is the only real SGP quote
    # anyone will ever hand us, so it is written down the moment it arrives.
    async with get_engine().begin() as conn:
        clv = await ledger_bets.record(
            conn, result, league=req.league, sportsbook=req.sportsbook)
    if clv:
        result["recorded"] = clv
    return result


@router.post("/sgp/save")
async def save_sgp():
    return _not_implemented("save")


@router.get("/sgp/history")
async def history():
    return _not_implemented("history")
