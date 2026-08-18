"""Odds snapshot poller — The Odds API (the-odds-api.com).

Snapshots current odds for tracked games into markets/odds_snapshots.
Pregame cadence: every 30 min (config: ODDS_POLL_INTERVAL_SECONDS).

Usage:
    docker compose run --rm ingest python -m youredge.ingest.odds_poller --once
    docker compose run --rm ingest python -m youredge.ingest.odds_poller   # loop
"""

import argparse
import asyncio
import logging
from datetime import datetime

import httpx
from sqlalchemy import text

from youredge.config import get_settings
from youredge.db import get_engine

log = logging.getLogger(__name__)
BASE = "https://api.the-odds-api.com/v4"

SPORT_KEYS = {"nfl": "americanfootball_nfl", "ncaaf": "americanfootball_ncaaf"}
CORE_MARKETS = "h2h,spreads,totals"


def american_to_implied(price: int) -> float:
    if price < 0:
        return -price / (-price + 100)
    return 100 / (price + 100)


async def poll_once(league: str) -> int:
    settings = get_settings()
    if not settings.odds_api_key:
        raise SystemExit("ODDS_API_KEY not set in .env")

    params = {
        "apiKey": settings.odds_api_key,
        "regions": "us",
        "markets": CORE_MARKETS,
        "bookmakers": settings.odds_bookmakers,
        "oddsFormat": "american",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{BASE}/sports/{SPORT_KEYS[league]}/odds", params=params)
        r.raise_for_status()
        remaining = r.headers.get("x-requests-remaining")
        events = r.json()
    log.info("%s: %d events (API credits remaining: %s)", league, len(events), remaining)

    engine = get_engine()
    rows = 0
    async with engine.begin() as conn:
        for ev in events:
            # TODO(phase-0): resolve ev['id'] -> canonical game_id via entity_xwalk.
            # Until then, stub a games row under the oddsapi: id so snapshots can land;
            # the resolver will remap these to canonical ids later.
            gid = f"{league}:oddsapi:{ev['id']}"
            kickoff = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
            season = kickoff.year if kickoff.month >= 6 else kickoff.year - 1
            await conn.execute(
                text("""
                    INSERT INTO games (game_id, league, season, kickoff, status)
                    VALUES (:gid, :league, :season, :kickoff, 'scheduled')
                    ON CONFLICT (game_id) DO NOTHING
                """),
                {"gid": gid, "league": league, "season": season, "kickoff": kickoff},
            )
            for bm in ev.get("bookmakers", []):
                for mkt in bm.get("markets", []):
                    res = await conn.execute(
                        text("""
                            INSERT INTO markets (game_id, bookmaker, market_key)
                            VALUES (:gid, :bm, :mk)
                            ON CONFLICT (game_id, bookmaker, market_key, player_id) DO UPDATE
                              SET market_key = EXCLUDED.market_key
                            RETURNING market_id
                        """),
                        {"gid": gid, "bm": bm["key"], "mk": mkt["key"]},
                    )
                    market_id = res.scalar_one()
                    for oc in mkt.get("outcomes", []):
                        await conn.execute(
                            text("""
                                INSERT INTO odds_snapshots
                                    (market_id, outcome, line, price_american, implied_prob)
                                VALUES (:mid, :outcome, :line, :price, :prob)
                            """),
                            {
                                "mid": market_id,
                                "outcome": oc["name"],
                                "line": oc.get("point"),
                                "price": int(oc["price"]),
                                "prob": american_to_implied(int(oc["price"])),
                            },
                        )
                        rows += 1
    return rows


async def main(once: bool):
    settings = get_settings()
    while True:
        for league in ("nfl", "ncaaf"):
            try:
                n = await poll_once(league)
                log.info("%s: %d snapshot rows", league, n)
            except httpx.HTTPStatusError as e:
                log.error("%s poll failed: %s", league, e)
        if once:
            break
        await asyncio.sleep(settings.odds_poll_interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # httpx INFO logs the full request URL, which includes the apiKey param
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.once))
