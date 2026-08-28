"""Play-level player attribution for NCAAF, from CFBD /plays/stats.

Closes the gap both CAPABILITIES.md and NCAAF.md describe as structural. It is
real for /plays, which omits player ids, but /plays/stats carries them:

    playId · athleteId · athleteName · statType · stat

across 26 stat types (Reception, Target, Completion, Rush, Touchdown, Sack,
Interception Thrown, Fumble Forced...). The athlete ids are ESPN ids, the same
identity space `players.player_id` already uses for college, so resolution is
`ncaaf:{athleteId}` — a prefix, not a fuzzy name match.

    docker compose run --rm ingest python -m youredge.ingest.cfbd_play_players --seasons 2023 2024 2025

Scoped by conference rather than by game. The endpoint caps a response at 2,000
rows, and a conference-week comes in under that (SEC week 1: 1,622 across 16
games) — roughly 530 calls for three seasons instead of the 2,700 per-game ones.
Any conference-week that comes back at exactly the cap is re-fetched game by
game, because a truncated response is indistinguishable from a complete one and
silently losing a third of a week is worse than spending the extra calls.

Unblocks NCAAF props, the NCAAF player pages the UI still stubs, and player-grain
college script analysis.
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

# The endpoint's hard response cap. Hitting it exactly means "probably truncated".
PAGE_CAP = 2000

FBS_CONFERENCES = [
    "SEC", "Big Ten", "ACC", "Big 12", "Pac-12", "American Athletic",
    "Mountain West", "Sun Belt", "Mid-American", "Conference USA",
    "FBS Independents",
]


async def _get(client: httpx.AsyncClient, params: dict):
    return await get_json(client, f"{BASE}/plays/stats", params)


_UPSERT = text("""
    INSERT INTO play_players
        (game_id, source_play_id, athlete_id, player_id, athlete_name, team_id, stat_type, stat)
    SELECT s.game_id, s.source_play_id, s.athlete_id,
           p.player_id,          -- NULL when the athlete is not on our roster
           s.athlete_name, t.team_id, s.stat_type, s.stat
    FROM (
        SELECT unnest(CAST(:gids  AS text[])) AS game_id,
               unnest(CAST(:pids  AS text[])) AS source_play_id,
               unnest(CAST(:aids  AS text[])) AS athlete_id,
               unnest(CAST(:names AS text[])) AS athlete_name,
               unnest(CAST(:teams AS text[])) AS team_name,
               unnest(CAST(:stats AS text[])) AS stat_type,
               unnest(CAST(:vals  AS real[])) AS stat
    ) s
    LEFT JOIN players p ON p.player_id = 'ncaaf:' || s.athlete_id
    LEFT JOIN teams   t ON t.league = 'ncaaf' AND t.name = s.team_name
    WHERE EXISTS (SELECT 1 FROM games g WHERE g.game_id = s.game_id)
    ON CONFLICT (game_id, source_play_id, athlete_id, stat_type) DO UPDATE
      SET stat = EXCLUDED.stat,
          player_id = COALESCE(EXCLUDED.player_id, play_players.player_id),
          team_id   = COALESCE(EXCLUDED.team_id, play_players.team_id)
""")


async def _store(rows: list[dict]) -> int:
    if not rows:
        return 0
    cols: dict[str, list] = {k: [] for k in
                             ("gids", "pids", "aids", "names", "teams", "stats", "vals")}
    for r in rows:
        cols["gids"].append(f"ncaaf:{r.get('gameId')}")
        cols["pids"].append(str(r.get("playId")))
        cols["aids"].append(str(r.get("athleteId")))
        cols["names"].append(r.get("athleteName"))
        cols["teams"].append(r.get("team"))
        cols["stats"].append(r.get("statType"))
        try:
            cols["vals"].append(float(r.get("stat")) if r.get("stat") is not None else None)
        except (TypeError, ValueError):
            cols["vals"].append(None)

    engine = get_engine()
    async with engine.begin() as conn:
        return (await conn.execute(_UPSERT, cols)).rowcount


async def fetch_week(client, season: int, week: int, season_type: str) -> list[dict]:
    """Every player-event for a week, conference by conference.

    Falls back to per-game whenever a conference response comes back at the cap,
    since a truncated page looks exactly like a complete one.
    """
    out: list[dict] = []
    for conf in FBS_CONFERENCES:
        rows = await _get(client, {
            "year": season, "week": week, "seasonType": season_type,
            "conference": conf,
        })
        if len(rows) < PAGE_CAP:
            out.extend(rows)
            continue

        log.warning("%s %s wk%s: hit the %d-row cap — refetching per game",
                    season, conf, week, PAGE_CAP)
        for gid in {r.get("gameId") for r in rows}:
            out.extend(await _get(client, {"gameId": gid}))
    return out


async def main(seasons: list[int], weeks: range, season_types: list[str]):
    settings = get_settings()
    if not settings.cfbd_api_key:
        raise SystemExit("CFBD_API_KEY not set in .env")

    headers = {"Authorization": f"Bearer {settings.cfbd_api_key}"}
    total = 0
    failures: list[tuple] = []
    async with httpx.AsyncClient(headers=headers, timeout=120) as client:
        for season in seasons:
            for st in season_types:
                for week in (weeks if st == "regular" else [1]):
                    try:
                        rows = await fetch_week(client, season, week, st)
                    except CFBDError as e:
                        # Recorded, not swallowed. A backfill that skips weeks and
                        # still exits 0 is how 81 games got mistaken for 900.
                        failures.append((season, st, week, str(e)))
                        log.error("%s %s wk%s FAILED: %s", season, st, week, e)
                        continue
                    n = await _store(rows)
                    total += n
                    if n:
                        log.info("%s %s wk%-2s  %6d player-events", season, st, week, n)

    engine = get_engine()
    async with engine.begin() as conn:
        summary = (await conn.execute(text("""
            SELECT count(*) AS rows,
                   count(*) FILTER (WHERE player_id IS NOT NULL) AS resolved,
                   count(DISTINCT athlete_id) AS athletes,
                   count(DISTINCT game_id) AS games,
                   count(DISTINCT stat_type) AS stat_types
            FROM play_players
        """))).mappings().first()
    log.info("play_players: %d rows, %d athletes, %d games, %d stat types",
             summary["rows"], summary["athletes"], summary["games"],
             summary["stat_types"])
    log.info("  resolved to canonical player_id: %d (%.1f%%)",
             summary["resolved"],
             100 * summary["resolved"] / (summary["rows"] or 1))

    if failures:
        log.error("%d week(s) failed and are MISSING from the table:", len(failures))
        for season, st, week, err in failures:
            log.error("    %s %s wk%s — %s", season, st, week, err)
        raise SystemExit(1)
    return total


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, required=True)
    parser.add_argument("--max-week", type=int, default=17)
    parser.add_argument("--season-type", nargs="+", default=["regular", "postseason"])
    args = parser.parse_args()
    asyncio.run(main(args.seasons, range(1, args.max_week + 1), args.season_type))
