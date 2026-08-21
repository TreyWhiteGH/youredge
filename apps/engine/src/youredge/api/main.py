from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from youredge import __version__
from youredge.api.routes import pff_drop, players, sgp, teams, tendencies
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
app.include_router(tendencies.router, prefix="/api/football")
app.include_router(players.router, prefix="/api/football")
app.include_router(teams.router, prefix="/api/football")


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
