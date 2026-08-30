"""NCAAF ingestion from CollegeFootballData.com REST API.

Free tier: 1,000 calls/month — backfill deliberately, one season at a time.
Patreon Tier 3 ($10/mo) → 75k calls when we need it.
Each week costs 3 calls (games, plays, lines) → full regular season ≈ 45 calls.

Usage:
    docker compose run --rm ingest python -m youredge.ingest.cfbd_pbp --seasons 2024 --week 1
    docker compose run --rm ingest python -m youredge.ingest.cfbd_pbp --seasons 2023 2024 2025
    docker compose run --rm ingest python -m youredge.ingest.cfbd_pbp --seasons 2024 --week 1 --season-type postseason
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path

import httpx
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from youredge.config import get_settings
from youredge.db import get_engine
from youredge.ingest import cfbd_map

log = logging.getLogger(__name__)
BASE = "https://api.collegefootballdata.com"

# Order matches cfbd_map.transform_plays record tuples
PLAY_COLS = [
    "game_id", "source_play_id", "quarter", "game_seconds_remaining", "drive_num",
    "posteam_id", "defteam_id", "down", "ydstogo", "yardline_100", "play_type",
    "yards_gained", "epa", "wp", "score_differential",
    "passer_player_id", "rusher_player_id", "receiver_player_id",
]
# transform_plays emits tuples in exactly this column order.


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def _get(client: httpx.AsyncClient, path: str, params: dict) -> list[dict]:
    r = await client.get(f"{BASE}{path}", params=params)
    r.raise_for_status()
    return r.json()


async def fetch_week(season: int, week: int, season_type: str):
    settings = get_settings()
    if not settings.cfbd_api_key:
        raise SystemExit("CFBD_API_KEY not set in .env — get a free key at collegefootballdata.com/key")

    headers = {"Authorization": f"Bearer {settings.cfbd_api_key}"}
    common = {"year": season, "week": week, "seasonType": season_type}
    async with httpx.AsyncClient(headers=headers, timeout=60) as client:
        games = await _get(client, "/games", {**common, "classification": "fbs"})
        plays = await _get(client, "/plays", {**common, "classification": "fbs"})
        lines = await _get(client, "/lines", common)  # no classification param; filtered on insert
    log.info("CFBD %s %s wk%s: %d games, %d plays, %d line records",
             season, season_type, week, len(games), len(plays), len(lines))
    return games, plays, lines


async def insert_week(games: list[dict], plays: list[dict], lines: list[dict]) -> dict:
    t = cfbd_map.transform_games(games)
    known_gids = {g["gid"] for g in t["games"]}
    play_records, plays_skipped = cfbd_map.transform_plays(plays, t["name_to_tid"], known_gids)
    line_rows, lines_skipped = cfbd_map.transform_lines(lines, known_gids)

    engine = get_engine()
    async with engine.begin() as conn:
        for tm in t["teams"]:
            await conn.execute(
                text("""
                    INSERT INTO teams (team_id, league, abbr, name)
                    VALUES (:tid, 'ncaaf', :abbr, :name)
                    ON CONFLICT (team_id) DO UPDATE SET name = EXCLUDED.name
                """),
                tm,
            )
        for g in t["games"]:
            await conn.execute(
                text("""
                    INSERT INTO games (game_id, league, season, week, kickoff, season_type,
                                       home_team_id, away_team_id, status, home_score, away_score, notes)
                    VALUES (:gid, 'ncaaf', :season, :week, :kickoff, :season_type,
                            :home, :away, :status, :home_score, :away_score, :notes)
                    ON CONFLICT (game_id) DO UPDATE
                      SET status = EXCLUDED.status,
                          season_type = EXCLUDED.season_type,
                          notes = EXCLUDED.notes,
                          home_score = EXCLUDED.home_score,
                          away_score = EXCLUDED.away_score
                """),
                g,
            )
        for x in t["xwalk"]:
            await conn.execute(
                text("""
                    INSERT INTO entity_xwalk (entity_type, canonical_id, source, source_id)
                    VALUES (:etype, :cid, :source, :sid)
                    ON CONFLICT (entity_type, source, source_id) DO NOTHING
                """),
                x,
            )

        # Plays: COPY into temp stage, insert-select for idempotent re-runs
        raw_conn = await conn.get_raw_connection()
        apg = raw_conn.driver_connection
        await apg.execute("""
            CREATE TEMP TABLE _plays_stage (
                game_id TEXT, source_play_id TEXT, quarter INT, game_seconds_remaining INT,
                drive_num INT, posteam_id TEXT, defteam_id TEXT, down INT, ydstogo INT,
                yardline_100 INT, play_type TEXT, yards_gained REAL, epa REAL, wp REAL,
                score_differential INT, passer_player_id TEXT, rusher_player_id TEXT,
                receiver_player_id TEXT
            ) ON COMMIT DROP
        """)
        await apg.copy_records_to_table("_plays_stage", records=play_records, columns=PLAY_COLS)
        tag = await apg.execute(f"""
            INSERT INTO plays ({", ".join(PLAY_COLS)})
            SELECT {", ".join(PLAY_COLS)} FROM _plays_stage
            ON CONFLICT (game_id, source_play_id) DO NOTHING
        """)
        plays_inserted = int(tag.split()[-1])

        # Historical lines → markets + snapshots (closing proxy @ kickoff)
        snaps = 0
        for row in line_rows:
            res = await conn.execute(
                text("""
                    INSERT INTO markets (game_id, bookmaker, market_key)
                    VALUES (:gid, :bookmaker, :market_key)
                    -- Identity moved to player_name in 024: player_id is derived and
                        -- improves over time, so keying on it forks a market's history.
                        ON CONFLICT (game_id, bookmaker, market_key, player_name) DO UPDATE
                      SET market_key = EXCLUDED.market_key
                    RETURNING market_id
                """),
                row,
            )
            market_id = res.scalar_one()
            price = row["price"]
            implied = None
            if price is not None:
                implied = (-price / (-price + 100)) if price < 0 else (100 / (price + 100))
            res = await conn.execute(
                text("""
                    INSERT INTO odds_snapshots
                        (market_id, captured_at, outcome, line, price_american, implied_prob)
                    VALUES (:mid, :captured_at, :outcome, :line, :price, :implied)
                    -- 023 added line to snapshot uniqueness, because an alternate-line
                        -- market quotes the same side at a ladder of numbers.
                        ON CONFLICT (market_id, captured_at, outcome, line) DO NOTHING
                """),
                {"mid": market_id, "captured_at": row["captured_at"], "outcome": row["outcome"],
                 "line": row["line"], "price": price, "implied": implied},
            )
            snaps += res.rowcount

    return {
        "plays_inserted": plays_inserted,
        "plays_skipped": plays_skipped,
        "line_snapshots": snaps,
        "line_games_skipped": lines_skipped,
    }


# CFBD ships no success column but does ship PPA, its EPA analog, and nflverse
# defines success as EPA > 0 — so applying that definition here makes success
# rate mean the same thing in both leagues. Migration 014 did this once, for the
# rows that existed the day it ran; every play ingested afterwards arrived with
# success NULL and stayed that way, which is why the 2026 season had a null
# success rate on every surface that reports one. It belongs with the ingest,
# where it runs for whatever was just written.
_FILL_SUCCESS = text("""
    UPDATE plays p SET success = (p.epa > 0)
    FROM games g
    WHERE g.game_id = p.game_id AND g.league = 'ncaaf'
      AND p.success IS NULL AND p.epa IS NOT NULL
""")


async def ingest_week(season: int, week: int, season_type: str = "regular", dump: bool = False):
    games, plays, lines = await fetch_week(season, week, season_type)

    if dump:
        out = Path("/app/data")
        out.mkdir(parents=True, exist_ok=True)
        for name, payload in (("games", games), ("plays", plays), ("lines", lines)):
            path = out / f"cfbd_{season}_wk{week}_{name}.json"
            path.write_text(json.dumps(payload, indent=2))
            log.info("Dumped %s", path)

    stats = await insert_week(games, plays, lines)
    async with get_engine().begin() as conn:
        stats["success_filled"] = (await conn.execute(_FILL_SUCCESS)).rowcount
    log.info("Inserted: %s", stats)
    return stats


async def main(seasons: list[int], week: int | None, season_type: str, dump: bool = False):
    for season in seasons:
        weeks = [week] if week else range(1, 16)
        for w in weeks:
            await ingest_week(season, w, season_type=season_type, dump=dump)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, required=True)
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument("--season-type", default="regular", choices=["regular", "postseason"])
    parser.add_argument("--dump", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.seasons, args.week, args.season_type, args.dump))
