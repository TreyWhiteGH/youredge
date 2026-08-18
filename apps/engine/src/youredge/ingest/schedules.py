"""Season schedule ingestion — future games, so odds events can resolve to canonical ids.

NFL: nflverse load_schedules (free, includes kickoff times).
NCAAF: CFBD /games?year=N (1 API call per season-type).

Usage:
    docker compose run --rm ingest python -m youredge.ingest.schedules --season 2026
"""

import argparse
import asyncio
import logging

import httpx
import nflreadpy as nfl
import pandas as pd
from sqlalchemy import text

from youredge.config import get_settings
from youredge.db import get_engine
from youredge.ingest import cfbd_map
from youredge.ingest.resolve import normalize_name

log = logging.getLogger(__name__)

# Schedule refreshes must never downgrade a game the PBP ingest already finalized.
_GAME_UPSERT = text("""
    INSERT INTO games (game_id, league, season, week, kickoff, season_type,
                       home_team_id, away_team_id, status, home_score, away_score, notes)
    VALUES (:gid, :league, :season, :week, :kickoff, :season_type,
            :home, :away, :status, :home_score, :away_score, :notes)
    ON CONFLICT (game_id) DO UPDATE
      SET kickoff = EXCLUDED.kickoff,
          week = EXCLUDED.week,
          season_type = EXCLUDED.season_type,
          notes = COALESCE(EXCLUDED.notes, games.notes)
      WHERE games.status = 'scheduled'
""")


async def ingest_nfl_schedule(season: int) -> int:
    sched = nfl.load_schedules(seasons=[season]).to_pandas()
    log.info("nflverse schedule %s: %d games", season, len(sched))
    engine = get_engine()
    async with engine.begin() as conn:
        for _, g in sched.iterrows():
            gametime = g.gametime if isinstance(g.gametime, str) and g.gametime else "00:00"
            kickoff = pd.Timestamp(f"{g.gameday} {gametime}", tz="America/New_York")
            await conn.execute(_GAME_UPSERT, {
                "gid": f"nfl:{g.game_id}",
                "league": "nfl",
                "season": int(g.season),
                "week": int(g.week),
                "kickoff": kickoff.to_pydatetime(),
                "season_type": "regular" if g.game_type == "REG" else "postseason",
                "home": f"nfl:{g.home_team}",
                "away": f"nfl:{g.away_team}",
                "status": "scheduled",
                "home_score": None, "away_score": None, "notes": None,
            })
    return len(sched)


async def ingest_ncaaf_schedule(season: int, season_type: str = "regular") -> int:
    settings = get_settings()
    if not settings.cfbd_api_key:
        raise SystemExit("CFBD_API_KEY not set in .env")
    headers = {"Authorization": f"Bearer {settings.cfbd_api_key}"}
    async with httpx.AsyncClient(headers=headers, timeout=60) as client:
        r = await client.get(
            "https://api.collegefootballdata.com/games",
            params={"year": season, "seasonType": season_type, "classification": "fbs"},
        )
        r.raise_for_status()
        games = r.json()
    log.info("CFBD schedule %s %s: %d games", season, season_type, len(games))

    t = cfbd_map.transform_games(games)
    engine = get_engine()
    async with engine.begin() as conn:
        for tm in t["teams"]:
            await conn.execute(
                text("""
                    INSERT INTO teams (team_id, league, abbr, name)
                    VALUES (:tid, 'ncaaf', :abbr, :name)
                    ON CONFLICT (team_id) DO NOTHING
                """),
                tm,
            )
        for g in t["games"]:
            await conn.execute(_GAME_UPSERT, {
                **{k: g[k] for k in ("gid", "season", "week", "kickoff", "season_type",
                                     "home", "away", "status", "home_score", "away_score", "notes")},
                "league": "ncaaf",
            })
        for x in t["xwalk"]:
            await conn.execute(
                text("""
                    INSERT INTO entity_xwalk (entity_type, canonical_id, source, source_id)
                    VALUES (:etype, :cid, :source, :sid)
                    ON CONFLICT (entity_type, source, source_id) DO NOTHING
                """),
                x,
            )
    return len(games)


async def ingest_ncaaf_aliases(season: int) -> int:
    """CFBD team metadata → normalized alias rows in entity_xwalk.

    Aliases are every (school | alternateName) with and without the mascot,
    normalized; the odds resolver matches book names ('San Jose State Spartans')
    against these. Ambiguous aliases (two teams, same normalized form) are dropped.
    """
    settings = get_settings()
    headers = {"Authorization": f"Bearer {settings.cfbd_api_key}"}
    async with httpx.AsyncClient(headers=headers, timeout=60) as client:
        r = await client.get("https://api.collegefootballdata.com/teams",
                             params={"year": season})
        r.raise_for_status()
        teams = r.json()

    # Book names CFBD's alternateNames don't cover, keyed by CFBD school name.
    extra = {"UAlbany": ["Albany"], "SE Louisiana": ["Southeastern Louisiana"]}

    aliases: dict[str, str] = {}
    ambiguous: set[str] = set()
    for t in teams:
        tid = f"ncaaf:{t['id']}"
        mascot = t.get("mascot") or ""
        bases = {t["school"], *(t.get("alternateNames") or []), *extra.get(t["school"], [])}
        for base in bases:
            for form in (base, f"{base} {mascot}".strip()):
                key = normalize_name(form)
                if not key:
                    continue
                if aliases.get(key, tid) != tid:
                    ambiguous.add(key)
                aliases[key] = tid
    for key in ambiguous:
        del aliases[key]

    engine = get_engine()
    async with engine.begin() as conn:
        for key, tid in aliases.items():
            await conn.execute(
                text("""
                    INSERT INTO entity_xwalk (entity_type, canonical_id, source, source_id)
                    VALUES ('team', :cid, 'cfbd_alias', :sid)
                    ON CONFLICT (entity_type, source, source_id)
                      DO UPDATE SET canonical_id = EXCLUDED.canonical_id
                """),
                {"cid": tid, "sid": key},
            )
    log.info("CFBD aliases: %d rows (%d ambiguous dropped)", len(aliases), len(ambiguous))
    return len(aliases)


async def main(season: int):
    n_nfl = await ingest_nfl_schedule(season)
    n_ncaaf = await ingest_ncaaf_schedule(season)
    await ingest_ncaaf_aliases(season)
    log.info("Schedules ingested: %d NFL, %d NCAAF", n_nfl, n_ncaaf)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.season))
