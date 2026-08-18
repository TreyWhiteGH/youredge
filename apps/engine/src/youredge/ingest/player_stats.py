"""Player game logs (nflverse weekly stats) + QB traits (Next Gen Stats passing).

Typed columns land for filtering/aggregation; the complete source row goes to
stats JSONB so any column not promoted is still queryable. game_id is backfilled
by joining (season, week, team, opponent) against games in either orientation.

Usage:
    docker compose run --rm ingest python -m youredge.ingest.player_stats --seasons 2023 2024 2025
"""

import argparse
import asyncio
import json
import logging

import nflreadpy as nfl
import pandas as pd
from sqlalchemy import text

from youredge.db import get_engine

log = logging.getLogger(__name__)

TYPED = [
    "attempts", "completions", "passing_yards", "passing_tds",
    "passing_interceptions", "sacks_suffered", "passing_air_yards",
    "passing_epa", "passing_cpoe",
    "carries", "rushing_yards", "rushing_tds", "rushing_epa",
    "targets", "receptions", "receiving_yards", "receiving_tds",
    "receiving_air_yards", "receiving_epa",
    "target_share", "air_yards_share", "wopr",
]
INT_COLS = {"attempts", "completions", "passing_tds", "passing_interceptions",
            "sacks_suffered", "carries", "rushing_tds", "targets", "receptions",
            "receiving_tds"}
STAGE_COLS = ["player_id", "season", "week", "season_type", "team_id",
              "opponent_team_id", "position", *TYPED, "stats"]

NGS_TYPED = ["avg_time_to_throw", "avg_intended_air_yards", "avg_completed_air_yards",
             "avg_air_yards_to_sticks", "aggressiveness",
             "completion_percentage_above_expectation", "passer_rating"]


def _clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
        return None
    return v.item() if hasattr(v, "item") else v


def _row_json(row: dict) -> str:
    return json.dumps({k: _clean(v) for k, v in row.items()}, default=str)


async def ingest_game_stats(seasons: list[int]) -> int:
    stats = nfl.load_player_stats(seasons=seasons).to_pandas()
    log.info("weekly player stats %s: %d rows", seasons, len(stats))

    engine = get_engine()
    async with engine.begin() as conn:
        known = {r[0] for r in await conn.execute(text("SELECT player_id FROM players"))}
        records, skipped = [], 0
        for row in stats.to_dict("records"):
            pid = f"nfl:{row['player_id']}"
            if pid not in known:
                skipped += 1
                continue
            records.append((
                pid, int(row["season"]), int(row["week"]),
                "postseason" if row.get("season_type") == "POST" else "regular",
                f"nfl:{row['team']}" if _clean(row.get("team")) else None,
                f"nfl:{row['opponent_team']}" if _clean(row.get("opponent_team")) else None,
                _clean(row.get("position")),
                *[
                    (int(v) if c in INT_COLS and (v := _clean(row.get(c))) is not None
                     else (float(v) if (v := _clean(row.get(c))) is not None else None))
                    for c in TYPED
                ],
                _row_json(row),
            ))

        raw_conn = await conn.get_raw_connection()
        apg = raw_conn.driver_connection
        typed_ddl = ", ".join(
            f"{c} {'INT' if c in INT_COLS else 'REAL'}" for c in TYPED
        )
        await apg.execute(f"""
            CREATE TEMP TABLE _pgs_stage (
                player_id TEXT, season INT, week INT, season_type TEXT,
                team_id TEXT, opponent_team_id TEXT, position TEXT,
                {typed_ddl}, stats JSONB
            ) ON COMMIT DROP
        """)
        await apg.copy_records_to_table("_pgs_stage", records=records, columns=STAGE_COLS)
        cols = ", ".join(STAGE_COLS)
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in STAGE_COLS[3:])
        await apg.execute(f"""
            INSERT INTO player_game_stats ({cols})
            SELECT {cols} FROM _pgs_stage
            ON CONFLICT (player_id, season, week) DO UPDATE SET {updates}
        """)

        await conn.execute(text("""
            UPDATE player_game_stats s SET game_id = g.game_id
            FROM games g
            WHERE s.game_id IS NULL AND g.league = 'nfl'
              AND g.season = s.season AND g.week = s.week
              AND ((g.home_team_id = s.team_id AND g.away_team_id = s.opponent_team_id)
                OR (g.away_team_id = s.team_id AND g.home_team_id = s.opponent_team_id))
        """))
    log.info("game stats upserted: %d (skipped %d unknown players)", len(records), skipped)
    return len(records)


async def ingest_qb_ngs(seasons: list[int]) -> int:
    ngs = nfl.load_nextgen_stats(seasons=seasons, stat_type="passing").to_pandas()
    ngs = ngs[ngs.season.isin(seasons)]
    log.info("NGS passing %s: %d rows", seasons, len(ngs))

    engine = get_engine()
    upserted = 0
    async with engine.begin() as conn:
        known = {r[0] for r in await conn.execute(text("SELECT player_id FROM players"))}
        for row in ngs.to_dict("records"):
            pid = f"nfl:{row['player_gsis_id']}"
            if pid not in known:
                continue
            await conn.execute(
                text(f"""
                    INSERT INTO qb_ngs_weekly
                        (player_id, season, week, {", ".join(NGS_TYPED)}, stats)
                    VALUES (:pid, :season, :week, {", ".join(f":{c}" for c in NGS_TYPED)},
                            CAST(:stats AS jsonb))
                    ON CONFLICT (player_id, season, week) DO UPDATE
                      SET {", ".join(f"{c} = EXCLUDED.{c}" for c in NGS_TYPED)},
                          stats = EXCLUDED.stats
                """),
                {
                    "pid": pid, "season": int(row["season"]), "week": int(row["week"]),
                    **{c: (float(v) if (v := _clean(row.get(c))) is not None else None)
                       for c in NGS_TYPED},
                    "stats": _row_json(row),
                },
            )
            upserted += 1
    log.info("QB NGS upserted: %d", upserted)
    return upserted


async def main(seasons: list[int]):
    await ingest_game_stats(seasons)
    await ingest_qb_ngs(seasons)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.seasons))
