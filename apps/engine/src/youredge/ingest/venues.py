"""Venue statics and per-game conditions, both leagues.

NCAAF: CFBD /venues (one call, 852 venues incl. elevation) plus a /games pass per
season to attach venue_id and neutral-site.

NFL: nflverse schedules already carry stadium_id, roof, surface, temp and wind per
game, so venues are derived from the schedule itself.

Weather asymmetry is real and left visible: nflverse reports temp/wind, CFBD's weather
endpoint is paywalled, so NCAAF games keep NULL conditions. NULL means "not available",
never "indoors" or "calm".

Usage:
    docker compose run --rm ingest python -m youredge.ingest.venues --seasons 2023 2024 2025 2026
"""

import argparse
import asyncio
import logging

import httpx
import nflreadpy as nfl
import pandas as pd
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from youredge.config import get_settings
from youredge.db import get_engine

log = logging.getLogger(__name__)
BASE = "https://api.collegefootballdata.com"

_VENUE_UPSERT = text("""
    INSERT INTO venues (venue_id, league, name, city, state, timezone,
                        latitude, longitude, elevation, capacity, dome, grass)
    VALUES (:vid, :league, :name, :city, :state, :tz, :lat, :lon, :elev,
            :cap, :dome, :grass)
    ON CONFLICT (venue_id) DO UPDATE SET
        name=EXCLUDED.name, city=EXCLUDED.city, state=EXCLUDED.state,
        timezone=EXCLUDED.timezone, latitude=EXCLUDED.latitude,
        longitude=EXCLUDED.longitude, elevation=EXCLUDED.elevation,
        capacity=EXCLUDED.capacity, dome=EXCLUDED.dome, grass=EXCLUDED.grass
""")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
async def _get(client, path, params=None):
    r = await client.get(f"{BASE}{path}", params=params or {})
    r.raise_for_status()
    return r.json()


def _f(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


async def ingest_ncaaf(seasons: list[int]) -> dict:
    settings = get_settings()
    headers = {"Authorization": f"Bearer {settings.cfbd_api_key}"}
    async with httpx.AsyncClient(headers=headers, timeout=120) as client:
        venues = await _get(client, "/venues")
        games_by_season = {}
        for s in seasons:
            games_by_season[s] = await _get(client, "/games",
                                            {"year": s, "classification": "fbs"})
            await asyncio.sleep(1)
    log.info("CFBD venues: %d", len(venues))

    engine = get_engine()
    n_v = n_g = 0
    async with engine.begin() as conn:
        for v in venues:
            if v.get("id") is None:
                continue
            await conn.execute(_VENUE_UPSERT, {
                "vid": f"ncaaf:{v['id']}", "league": "ncaaf",
                "name": v.get("name") or "unknown", "city": v.get("city"),
                "state": v.get("state"), "tz": v.get("timezone"),
                "lat": _f(v.get("latitude")), "lon": _f(v.get("longitude")),
                "elev": _f(v.get("elevation")), "cap": v.get("capacity"),
                "dome": v.get("dome"), "grass": v.get("grass"),
            })
            n_v += 1

        for season, games in games_by_season.items():
            for g in games:
                if g.get("venueId") is None:
                    continue
                res = await conn.execute(
                    text("""
                        UPDATE games SET venue_id = :vid, neutral_site = :neutral
                        WHERE game_id = :gid
                          AND EXISTS (SELECT 1 FROM venues WHERE venue_id = :vid)
                    """),
                    {"vid": f"ncaaf:{g['venueId']}", "gid": f"ncaaf:{g['id']}",
                     "neutral": g.get("neutralSite")},
                )
                n_g += res.rowcount
    return {"venues": n_v, "games_linked": n_g}


async def ingest_nfl(seasons: list[int]) -> dict:
    sched = nfl.load_schedules(seasons=seasons).to_pandas()
    log.info("nflverse schedules %s: %d games", seasons, len(sched))

    engine = get_engine()
    n_v = n_g = 0
    async with engine.begin() as conn:
        # Venue statics come from the schedule; nflverse has no lat/lon/elevation.
        seen = sched[sched.stadium_id.notna()].drop_duplicates("stadium_id")
        for _, r in seen.iterrows():
            await conn.execute(_VENUE_UPSERT, {
                "vid": f"nfl:{r.stadium_id}", "league": "nfl",
                "name": r.stadium if pd.notna(r.stadium) else "unknown",
                "city": None, "state": None, "tz": None, "lat": None, "lon": None,
                "elev": None, "cap": None,
                "dome": (str(r.roof) in ("dome", "closed")) if pd.notna(r.roof) else None,
                "grass": (str(r.surface) == "grass") if pd.notna(r.surface) and r.surface else None,
            })
            n_v += 1

        for _, r in sched.iterrows():
            res = await conn.execute(
                text("""
                    UPDATE games SET
                        venue_id = COALESCE(:vid, venue_id),
                        roof = :roof, surface = :surface, temp = :temp, wind = :wind,
                        neutral_site = :neutral
                    WHERE game_id = :gid
                """),
                {
                    "gid": f"nfl:{r.game_id}",
                    "vid": f"nfl:{r.stadium_id}" if pd.notna(r.stadium_id) else None,
                    "roof": str(r.roof) if pd.notna(r.roof) else None,
                    "surface": str(r.surface) if pd.notna(r.surface) and r.surface else None,
                    "temp": _f(r.temp), "wind": _f(r.wind),
                    "neutral": (str(r.location) == "Neutral") if pd.notna(r.location) else None,
                },
            )
            n_g += res.rowcount
    return {"venues": n_v, "games_updated": n_g}


async def main(seasons: list[int]):
    log.info("NCAAF: %s", await ingest_ncaaf(seasons))
    log.info("NFL: %s", await ingest_nfl(seasons))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.seasons))
