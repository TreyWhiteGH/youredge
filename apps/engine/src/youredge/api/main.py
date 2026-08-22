from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from youredge import __version__
from fastapi import Depends, HTTPException, Request

from youredge.api.routes import ncaaf, pff_drop, players, sgp, teams, tendencies
from youredge.db import get_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await get_engine().dispose()


app = FastAPI(title="YourEdge Engine", version=__version__, lifespan=lifespan)
# Dev: lets the PFF harvest page POST facet JSON to /pff-drop
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://premium.pff.com"],
    allow_methods=["GET", "POST"],
    allow_headers=["content-type"],
)
app.include_router(sgp.router, prefix="/api/football")
app.include_router(pff_drop.router, prefix="/api/football")


@app.middleware("http")
async def allow_private_network(request, call_next):
    # Chrome PNA: public https origin -> localhost needs this on the preflight
    response = await call_next(request)
    if request.method == "OPTIONS":
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


async def league_guard(request: Request):
    """Canonical ids carry their league, so /api/nfl/teams/ncaaf:59 is a mistake.

    Fail it loudly with a 400 instead of running the query and returning an empty
    result that reads like "no data" — the two mean very different things.
    """
    parts = request.url.path.split("/")
    path_league = parts[2] if len(parts) > 2 else None
    if path_league not in ("nfl", "ncaaf"):
        return
    for key in ("team_id", "player_id"):
        value = request.path_params.get(key) or request.query_params.get(key)
        if value and ":" in value and value.split(":", 1)[0] != path_league:
            raise HTTPException(
                status_code=400,
                detail=f"{key}={value} is not a {path_league} id; use /api/"
                       f"{value.split(':', 1)[0]}/...",
            )


_guard = [Depends(league_guard)]

# NFL-only surfaces: props, NGS, PFF alignment/protection, clutch.
app.include_router(players.router, prefix="/api/nfl", dependencies=_guard)
app.include_router(teams.router, prefix="/api/nfl", dependencies=_guard)
app.include_router(tendencies.router, prefix="/api/nfl", dependencies=_guard)

# NCAAF: the shared team cards plus coaching/experience surfaces the NFL has no
# analog for.
app.include_router(teams.router, prefix="/api/ncaaf", dependencies=_guard)
app.include_router(tendencies.router, prefix="/api/ncaaf", dependencies=_guard)
app.include_router(ncaaf.router, prefix="/api/ncaaf", dependencies=_guard)


@app.get("/api/football/health")
async def health():
    db_ok = False
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    return {"status": "ok" if db_ok else "degraded", "version": __version__, "db": db_ok}
