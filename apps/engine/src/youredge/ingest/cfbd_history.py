"""Historical NCAAF labels: whole-season games + closing lines, no plays.

Why separate from cfbd_pbp: that module walks week by week and pulls plays, which is
~45 calls and ~25k plays per season. Labels don't need plays. CFBD serves a full season
of games and a full season of lines in **one call each**, so a decade of labeled games
costs ~20 calls instead of ~300.

This exists because the NCAAF context features (coaching, returning production, talent,
SP+) already reach back to 2016 while games and lines only reached 2023 — the features
had nothing to be paired against. Purely a data backfill; no modeling here.

Usage:
    docker compose run --rm ingest python -m youredge.ingest.cfbd_history --seasons 2016 2017
"""

import argparse
import asyncio
import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from youredge.config import get_settings
from youredge.ingest.cfbd_pbp import insert_week

log = logging.getLogger(__name__)
BASE = "https://api.collegefootballdata.com"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
async def _get(client: httpx.AsyncClient, path: str, params: dict) -> list[dict]:
    r = await client.get(f"{BASE}{path}", params=params)
    r.raise_for_status()
    return r.json()


async def ingest_season(season: int, season_type: str = "regular") -> dict:
    settings = get_settings()
    if not settings.cfbd_api_key:
        raise SystemExit("CFBD_API_KEY not set in .env")
    headers = {"Authorization": f"Bearer {settings.cfbd_api_key}"}

    async with httpx.AsyncClient(headers=headers, timeout=120) as client:
        common = {"year": season, "seasonType": season_type}
        games = await _get(client, "/games", {**common, "classification": "fbs"})
        lines = await _get(client, "/lines", common)
    log.info("CFBD %s %s: %d games, %d line records", season, season_type,
             len(games), len(lines))

    # Empty plays list: insert_week already handles teams/games/xwalk/lines, and its
    # COPY stage is a no-op on zero records, so labels reuse the proven path.
    stats = await insert_week(games, [], lines)
    log.info("  inserted: %s", stats)
    return stats


async def main(seasons: list[int], season_types: list[str]):
    for season in seasons:
        for st in season_types:
            try:
                await ingest_season(season, st)
            except httpx.HTTPStatusError as e:
                # One season failing must not discard the ones already committed.
                log.error("season %s %s failed: %s", season, st, e)
            await asyncio.sleep(2)  # be polite to CFBD's limiter


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, required=True)
    parser.add_argument("--season-types", nargs="+", default=["regular", "postseason"])
    args = parser.parse_args()
    asyncio.run(main(args.seasons, args.season_types))
