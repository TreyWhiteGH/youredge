"""Snap counts (per game, per player) + current depth charts.

Snap counts key on pfr_player_id -> resolved via the 'pfr' xwalk rows written
by players.py. Depth charts carry gsis_id natively; only the latest snapshot
per team is kept (whole-table refresh, as_of = snapshot timestamp).

Usage:
    docker compose run --rm ingest python -m youredge.ingest.snaps_depth --seasons 2023 2024 2025 --depth-season 2026
"""

import argparse
import asyncio
import logging

import nflreadpy as nfl
import pandas as pd
from sqlalchemy import text

from youredge.db import get_engine

log = logging.getLogger(__name__)


async def ingest_snap_counts(seasons: list[int]) -> int:
    snaps = nfl.load_snap_counts(seasons=seasons).to_pandas()
    log.info("snap counts %s: %d rows", seasons, len(snaps))

    engine = get_engine()
    async with engine.begin() as conn:
        pfr_map = {
            r[0]: r[1] for r in await conn.execute(text(
                "SELECT source_id, canonical_id FROM entity_xwalk "
                "WHERE entity_type='player' AND source='pfr'"))
        }
        known_games = {
            r[0] for r in await conn.execute(text(
                "SELECT game_id FROM games WHERE league='nfl'"))
        }
        records, skipped = [], 0
        seen = set()
        for row in snaps.itertuples(index=False):
            pid = pfr_map.get(row.pfr_player_id)
            gid = f"nfl:{row.game_id}"
            if pid is None or gid not in known_games or (pid, gid) in seen:
                skipped += 1
                continue
            seen.add((pid, gid))
            records.append((
                pid, gid, f"nfl:{row.team}", row.position,
                _i(row.offense_snaps), _f(row.offense_pct),
                _i(row.defense_snaps), _f(row.defense_pct),
                _i(row.st_snaps), _f(row.st_pct),
            ))

        raw_conn = await conn.get_raw_connection()
        apg = raw_conn.driver_connection
        await apg.execute("""
            CREATE TEMP TABLE _snaps_stage (
                player_id TEXT, game_id TEXT, team_id TEXT, position TEXT,
                offense_snaps INT, offense_pct REAL,
                defense_snaps INT, defense_pct REAL,
                st_snaps INT, st_pct REAL
            ) ON COMMIT DROP
        """)
        cols = ["player_id", "game_id", "team_id", "position", "offense_snaps", "offense_pct",
                "defense_snaps", "defense_pct", "st_snaps", "st_pct"]
        await apg.copy_records_to_table("_snaps_stage", records=records, columns=cols)
        await apg.execute(f"""
            INSERT INTO snap_counts ({", ".join(cols)})
            SELECT {", ".join(cols)} FROM _snaps_stage
            ON CONFLICT (player_id, game_id) DO UPDATE
              SET {", ".join(f"{c} = EXCLUDED.{c}" for c in cols[2:])}
        """)
    log.info("snap counts upserted: %d (skipped %d unmatched)", len(records), skipped)
    return len(records)


async def ingest_depth_charts(season: int) -> int:
    dc = nfl.load_depth_charts(seasons=[season]).to_pandas()
    latest = dc[dc.dt == dc.dt.max()]
    log.info("depth charts %s: snapshot %s, %d rows", season, dc.dt.max(), len(latest))

    engine = get_engine()
    inserted = 0
    async with engine.begin() as conn:
        known = {r[0] for r in await conn.execute(text("SELECT player_id FROM players"))}
        await conn.execute(text("DELETE FROM depth_chart"))
        seen = set()
        for row in latest.itertuples(index=False):
            if pd.isna(row.gsis_id):
                continue
            pid = f"nfl:{row.gsis_id}"
            key = (f"nfl:{row.team}", row.pos_grp, int(row.pos_slot), int(row.pos_rank))
            if pid not in known or key in seen:
                continue
            seen.add(key)
            await conn.execute(
                text("""
                    INSERT INTO depth_chart (team_id, pos_grp, pos_name, pos_abb,
                                             pos_slot, pos_rank, player_id, as_of)
                    VALUES (:team, :grp, :name, :abb, :slot, :rank, :pid, :as_of)
                """),
                {"team": key[0], "grp": row.pos_grp, "name": row.pos_name,
                 "abb": row.pos_abb, "slot": key[2], "rank": key[3],
                 "pid": pid, "as_of": pd.Timestamp(row.dt).to_pydatetime()},
            )
            inserted += 1
    log.info("depth chart rows: %d", inserted)
    return inserted


def _i(v):
    return None if pd.isna(v) else int(v)


def _f(v):
    return None if pd.isna(v) else float(v)


async def main(seasons: list[int], depth_season: int):
    await ingest_snap_counts(seasons)
    await ingest_depth_charts(depth_season)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, required=True)
    parser.add_argument("--depth-season", type=int, default=2026)
    args = parser.parse_args()
    asyncio.run(main(args.seasons, args.depth_season))
