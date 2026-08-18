from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from youredge import __version__
from youredge.api.routes import players, sgp, teams, tendencies
from youredge.db import get_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await get_engine().dispose()


app = FastAPI(title="YourEdge Engine", version=__version__, lifespan=lifespan)
app.include_router(sgp.router, prefix="/api/football")
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
