"""CFBD /passing/plays — intended target, and air-yards detail where it exists.

Wired for what the endpoint actually contains rather than what it advertises.

Measured against 2025 week 8 (3,718 attempts): airYards 2.7% populated,
yardsAfterCatch 1.8%, pass locations 3.5%. 2023 and 2024 return nothing. Those
fields are mapped so they fill in automatically if coverage improves — CFBD says
2026 onward should be more complete — but nothing is built on them yet, and no
downstream metric should assume they are there.

The field worth having is the one the announcement does not lead with. `targetId`
is present on 96% of completions and **89% of incompletions**, against roughly 9%
recoverable from play text. Target share has been undercounting from every source
we had; for 2025 it no longer has to.

    docker compose run --rm ingest python -m youredge.ingest.cfbd_passing --seasons 2025

Interceptions carry no targetId at all (0 of 82 in the sample), which is a real
hole rather than a rounding error: the intended receiver on a pick is exactly the
player a coverage read would want.
"""

import argparse
import asyncio
import logging

import httpx
from sqlalchemy import text

from youredge.config import get_settings
from youredge.db import get_engine
from youredge.ingest.cfbd_http import CFBDError, get_json

log = logging.getLogger(__name__)
BASE = "https://api.collegefootballdata.com"


async def _get(client: httpx.AsyncClient, params: dict):
    return await get_json(client, f"{BASE}/passing/plays", params)


# air_yards / yards_after_catch / pass_location already exist as nflverse columns
# that were NULL for college. Filled, not duplicated — COALESCE so a later run
# with thinner coverage cannot erase a value an earlier one found.
_UPDATE_PLAYS = text("""
    UPDATE plays p SET
        air_yards        = COALESCE(s.air_yards, p.air_yards),
        yards_after_catch = COALESCE(s.yac, p.yards_after_catch),
        pass_location    = COALESCE(s.direction, p.pass_location),
        pass_depth       = COALESCE(s.depth, p.pass_depth),
        is_throwaway     = COALESCE(s.throwaway, p.is_throwaway),
        target_player_id = COALESCE(tp.player_id, p.target_player_id)
    FROM (
        SELECT unnest(CAST(:gids AS text[]))    AS game_id,
               unnest(CAST(:pids AS text[]))    AS source_play_id,
               unnest(CAST(:air  AS real[]))    AS air_yards,
               unnest(CAST(:yac  AS real[]))    AS yac,
               unnest(CAST(:dir  AS text[]))    AS direction,
               unnest(CAST(:dep  AS text[]))    AS depth,
               unnest(CAST(:thr  AS boolean[])) AS throwaway,
               unnest(CAST(:tid  AS text[]))    AS target_athlete
    ) s
    LEFT JOIN players tp ON tp.player_id = 'ncaaf:' || s.target_athlete
    WHERE p.game_id = s.game_id AND p.source_play_id = s.source_play_id
""")

# Targets as attribution rows, so target share can be counted the same way every
# other stat is.
_INSERT_TARGETS = text("""
    INSERT INTO play_players
        (game_id, source_play_id, athlete_id, player_id, athlete_name,
         team_id, stat_type, stat, source)
    SELECT s.game_id, s.source_play_id, s.target_athlete,
           tp.player_id, s.target_name, t.team_id, 'Target', 1.0, 'cfbd_passing'
    FROM (
        SELECT unnest(CAST(:gids AS text[]))  AS game_id,
               unnest(CAST(:pids AS text[]))  AS source_play_id,
               unnest(CAST(:tid  AS text[]))  AS target_athlete,
               unnest(CAST(:tnm  AS text[]))  AS target_name,
               unnest(CAST(:off  AS text[]))  AS offense
    ) s
    LEFT JOIN players tp ON tp.player_id = 'ncaaf:' || s.target_athlete
    LEFT JOIN teams   t  ON t.league = 'ncaaf' AND t.name = s.offense
    WHERE s.target_athlete IS NOT NULL
      AND EXISTS (SELECT 1 FROM games g WHERE g.game_id = s.game_id)
    ON CONFLICT (game_id, source_play_id, athlete_id, stat_type) DO UPDATE
      SET player_id = COALESCE(EXCLUDED.player_id, play_players.player_id)
""")


def _f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


async def ingest_week(client, season: int, week: int, season_type: str) -> tuple[int, int]:
    rows = await _get(client, {"year": season, "week": week, "seasonType": season_type})
    if not rows:
        return 0, 0

    cols = {k: [] for k in ("gids", "pids", "air", "yac", "dir", "dep", "thr", "tid",
                            "tnm", "off")}
    for r in rows:
        cols["gids"].append(f"ncaaf:{r.get('gameId')}")
        cols["pids"].append(str(r.get("playId")))
        cols["air"].append(_f(r.get("airYards")))
        cols["yac"].append(_f(r.get("yardsAfterCatch")))
        cols["dir"].append(r.get("passDirection"))
        cols["dep"].append(r.get("passDepth"))
        cols["thr"].append(bool(r.get("isThrowaway")) if r.get("isThrowaway") is not None else None)
        tid = r.get("targetId")
        cols["tid"].append(str(tid) if tid else None)
        cols["tnm"].append(r.get("target"))
        cols["off"].append(r.get("offense"))

    engine = get_engine()
    async with engine.begin() as conn:
        updated = (await conn.execute(_UPDATE_PLAYS, cols)).rowcount
        targets = (await conn.execute(_INSERT_TARGETS, {
            k: cols[k] for k in ("gids", "pids", "tid", "tnm", "off")})).rowcount
    return updated, targets


async def main(seasons: list[int], weeks: range, season_types: list[str]):
    settings = get_settings()
    if not settings.cfbd_api_key:
        raise SystemExit("CFBD_API_KEY not set in .env")

    headers = {"Authorization": f"Bearer {settings.cfbd_api_key}"}
    plays = targets = 0
    failures = []
    async with httpx.AsyncClient(headers=headers, timeout=120) as client:
        for season in seasons:
            for st in season_types:
                for week in (weeks if st == "regular" else [1]):
                    try:
                        u, t = await ingest_week(client, season, week, st)
                    except CFBDError as e:
                        failures.append((season, st, week, str(e)))
                        log.error("%s %s wk%s FAILED: %s", season, st, week, e)
                        continue
                    plays += u
                    targets += t
                    if u:
                        log.info("%s %s wk%-2s  %5d plays enriched, %5d targets",
                                 season, st, week, u, t)

    engine = get_engine()
    async with engine.connect() as conn:
        cov = (await conn.execute(text("""
            SELECT count(*) FILTER (WHERE p.air_yards IS NOT NULL)        AS air,
                   count(*) FILTER (WHERE p.yards_after_catch IS NOT NULL) AS yac,
                   count(*) FILTER (WHERE p.target_player_id IS NOT NULL)  AS target,
                   count(*) AS passes
            FROM plays p JOIN games g USING (game_id)
            WHERE g.league = 'ncaaf' AND p.play_type_raw IN
                  ('Pass Reception', 'Pass Incompletion', 'Passing Touchdown')
        """))).mappings().first()
    n = cov["passes"] or 1
    log.info("\n%d plays enriched, %d target rows written", plays, targets)
    log.info("NCAAF pass plays: %d", cov["passes"])
    log.info("  with a resolved target : %6d (%.1f%%)", cov["target"], 100 * cov["target"] / n)
    log.info("  with air yards         : %6d (%.1f%%)", cov["air"], 100 * cov["air"] / n)
    log.info("  with yards after catch : %6d (%.1f%%)", cov["yac"], 100 * cov["yac"] / n)
    if failures:
        log.error("%d week(s) failed and are MISSING", len(failures))
        raise SystemExit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", type=int, required=True)
    ap.add_argument("--max-week", type=int, default=17)
    ap.add_argument("--season-type", nargs="+", default=["regular", "postseason"])
    a = ap.parse_args()
    asyncio.run(main(a.seasons, range(1, a.max_week + 1), a.season_type))
