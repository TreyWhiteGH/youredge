"""NFL play-by-play ingestion from nflverse (via nflreadpy).

Usage:
    docker compose run --rm ingest python -m youredge.ingest.nfl_pbp --seasons 2023 2024 2025
"""

import argparse
import asyncio
import logging

import nflreadpy as nfl
import pandas as pd
from sqlalchemy import text

from youredge.db import get_engine

log = logging.getLogger(__name__)

# nflverse pbp columns we extract into typed columns; everything else goes to raw JSONB.
EXTRACTED = [
    "play_id", "game_id", "qtr", "game_seconds_remaining", "drive",
    "posteam", "defteam", "down", "ydstogo", "yardline_100", "play_type",
    "yards_gained", "epa", "wp", "score_differential",
    "passer_player_id", "rusher_player_id", "receiver_player_id",
    "home_team", "away_team", "season", "week", "season_type",
]

PLAY_COLS = [
    "game_id", "source_play_id", "quarter", "game_seconds_remaining", "drive_num",
    "posteam_id", "defteam_id", "down", "ydstogo", "yardline_100", "play_type",
    "yards_gained", "epa", "wp", "score_differential",
    "passer_player_id", "rusher_player_id", "receiver_player_id",
]


def _i(v):
    return None if pd.isna(v) else int(v)


def _f(v):
    return None if pd.isna(v) else float(v)


def _s(v):
    return None if (v is None or (isinstance(v, float) and pd.isna(v)) or str(v) == "nan") else str(v)


async def upsert_teams(engine) -> None:
    teams = nfl.load_teams().to_pandas()
    async with engine.begin() as conn:
        for _, t in teams.iterrows():
            await conn.execute(
                text("""
                    INSERT INTO teams (team_id, league, abbr, name)
                    VALUES (:tid, 'nfl', :abbr, :name)
                    ON CONFLICT (team_id) DO UPDATE SET abbr = EXCLUDED.abbr, name = EXCLUDED.name
                """),
                {"tid": f"nfl:{t.team_abbr}", "abbr": t.team_abbr, "name": t.team_name},
            )
    log.info("Upserted %d teams", len(teams))


async def ingest_season(season: int) -> int:
    log.info("Loading nflverse PBP for %s...", season)
    pbp = nfl.load_pbp(seasons=[season]).to_pandas()
    log.info("Loaded %d plays", len(pbp))

    engine = get_engine()
    async with engine.begin() as conn:
        # Historical abbrs (e.g. OAK, SD) may not be in load_teams(); games FK needs a row anyway
        games = pbp[["game_id", "season", "week", "home_team", "away_team", "season_type"]].drop_duplicates("game_id")
        for abbr in sorted(set(games.home_team) | set(games.away_team)):
            await conn.execute(
                text("""
                    INSERT INTO teams (team_id, league, abbr, name)
                    VALUES (:tid, 'nfl', :abbr, :abbr)
                    ON CONFLICT (team_id) DO NOTHING
                """),
                {"tid": f"nfl:{abbr}", "abbr": abbr},
            )

        for _, g in games.iterrows():
            await conn.execute(
                text("""
                    INSERT INTO games (game_id, league, season, week, season_type, home_team_id, away_team_id, status)
                    VALUES (:gid, 'nfl', :season, :week, :stype, :home, :away, 'final')
                    ON CONFLICT (game_id) DO NOTHING
                """),
                {
                    "gid": f"nfl:{g.game_id}",
                    "season": int(g.season),
                    "week": int(g.week),
                    "stype": "postseason" if g.season_type == "POST" else "regular",
                    "home": f"nfl:{g.home_team}",
                    "away": f"nfl:{g.away_team}",
                },
            )

        # COPY into a temp stage, then insert-select so ON CONFLICT keeps re-runs idempotent
        records = []
        for p in pbp[EXTRACTED].itertuples(index=False):
            records.append((
                f"nfl:{p.game_id}", str(p.play_id),
                _i(p.qtr), _i(p.game_seconds_remaining), _i(p.drive),
                f"nfl:{p.posteam}" if _s(p.posteam) else None,
                f"nfl:{p.defteam}" if _s(p.defteam) else None,
                _i(p.down), _i(p.ydstogo), _i(p.yardline_100),
                _s(p.play_type), _f(p.yards_gained),
                _f(p.epa), _f(p.wp), _i(p.score_differential),
                _s(p.passer_player_id), _s(p.rusher_player_id), _s(p.receiver_player_id),
            ))

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
        await apg.copy_records_to_table("_plays_stage", records=records, columns=PLAY_COLS)
        tag = await apg.execute(f"""
            INSERT INTO plays ({", ".join(PLAY_COLS)})
            SELECT {", ".join(PLAY_COLS)} FROM _plays_stage
            ON CONFLICT (game_id, source_play_id) DO NOTHING
        """)
        inserted = int(tag.split()[-1])
    return inserted


async def main(seasons: list[int]):
    engine = get_engine()
    await upsert_teams(engine)
    for season in seasons:
        n = await ingest_season(season)
        log.info("Season %s: %d plays ingested", season, n)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.seasons))
