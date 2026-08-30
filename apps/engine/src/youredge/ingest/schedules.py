"""Season schedule ingestion — future games, so odds events can resolve to canonical ids.

NFL: nflverse load_schedules (free, includes kickoff times).
NCAAF: CFBD /games?year=N (1 API call per season-type).

This is the results feed as well as the schedule feed, because both leagues
return the score on the same row once a game is played. That is why it runs on a
loop rather than being a one-off backfill: without a refresh, every game sits at
'scheduled' from the moment it is first inserted, and a finished Saturday still
reads as unplayed on Sunday.

Usage:
    docker compose run --rm ingest python -m youredge.ingest.schedules
    docker compose run --rm ingest python -m youredge.ingest.schedules --season 2026
    docker compose run --rm ingest python -m youredge.ingest.schedules --loop
"""

import argparse
import asyncio
import logging
from datetime import datetime, timezone

import httpx
import nflreadpy as nfl
import pandas as pd
from sqlalchemy import text

from youredge.config import get_settings
from youredge.db import get_engine
from youredge.ingest import cfbd_map
from youredge.ingest.resolve import normalize_name

log = logging.getLogger(__name__)

# Schedule refreshes must never downgrade a game the PBP ingest already
# finalized, which is what the WHERE guard is for: a row that already says
# 'final' is left entirely alone.
#
# The guard used to be the whole story, and that was the bug. The SET list
# carried kickoff, week, season_type and notes but not status or the scores, so
# a game fetched back from the feed as completed had its result read, passed in,
# and then dropped on conflict. Every game that was ever inserted ahead of
# kickoff stayed 'scheduled' forever, however many times the schedule was
# re-ingested. The scores COALESCE against what is already there so a refresh
# that arrives before the feed has posted a result cannot blank one another
# ingest already wrote.
_GAME_UPSERT = text("""
    INSERT INTO games (game_id, league, season, week, kickoff, season_type,
                       home_team_id, away_team_id, status, home_score, away_score, notes)
    VALUES (:gid, :league, :season, :week, :kickoff, :season_type,
            :home, :away, :status, :home_score, :away_score, :notes)
    ON CONFLICT (game_id) DO UPDATE
      SET kickoff = EXCLUDED.kickoff,
          week = EXCLUDED.week,
          season_type = EXCLUDED.season_type,
          notes = COALESCE(EXCLUDED.notes, games.notes),
          status = EXCLUDED.status,
          home_score = COALESCE(EXCLUDED.home_score, games.home_score),
          away_score = COALESCE(EXCLUDED.away_score, games.away_score)
      WHERE games.status = 'scheduled'
""")


def _score(v) -> int | None:
    """nflverse leaves an unplayed game's score as NaN, which is not None."""
    return None if v is None or pd.isna(v) else int(v)


async def ingest_nfl_schedule(season: int) -> int:
    sched = nfl.load_schedules(seasons=[season]).to_pandas()
    log.info("nflverse schedule %s: %d games", season, len(sched))
    engine = get_engine()
    async with engine.begin() as conn:
        for _, g in sched.iterrows():
            gametime = g.gametime if isinstance(g.gametime, str) and g.gametime else "00:00"
            kickoff = pd.Timestamp(f"{g.gameday} {gametime}", tz="America/New_York")
            # A schedule row carries the result once the game is played, so this
            # is also the results feed — it was previously hardcoded to
            # 'scheduled' with null scores, which meant NFL finals only ever
            # arrived through the play-by-play backfill.
            home_score, away_score = _score(g.home_score), _score(g.away_score)
            await conn.execute(_GAME_UPSERT, {
                "gid": f"nfl:{g.game_id}",
                "league": "nfl",
                "season": int(g.season),
                "week": int(g.week),
                "kickoff": kickoff.to_pydatetime(),
                "season_type": "regular" if g.game_type == "REG" else "postseason",
                "home": f"nfl:{g.home_team}",
                "away": f"nfl:{g.away_team}",
                "status": ("final" if home_score is not None and away_score is not None
                           else "scheduled"),
                "home_score": home_score, "away_score": away_score, "notes": None,
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


# A football season is named for the calendar year it starts in, so anything
# from June onward belongs to this year and January's playoffs belong to last.
def current_season(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    return now.year if now.month >= 6 else now.year - 1


async def refresh(season: int, *, aliases: bool = True) -> None:
    n_nfl = await ingest_nfl_schedule(season)
    # Both season types, because a bowl game left out of the refresh is a game
    # that never gets a score.
    n_ncaaf = sum([
        await ingest_ncaaf_schedule(season, "regular"),
        await ingest_ncaaf_schedule(season, "postseason"),
    ])
    if aliases:
        await ingest_ncaaf_aliases(season)
    log.info("Schedules refreshed: %d NFL, %d NCAAF", n_nfl, n_ncaaf)


async def main(season: int | None, loop: bool, interval: int):
    season = season or current_season()
    first = True
    while True:
        try:
            # Aliases are team metadata and change once a year, not once an
            # hour; re-fetching them every cycle would be a CFBD call bought to
            # learn nothing.
            await refresh(season, aliases=first)
        except Exception:
            log.exception("schedule refresh failed")
            if not loop:
                raise
        first = False
        if not loop:
            break
        await asyncio.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int,
                        help="default: the season in progress")
    parser.add_argument("--loop", action="store_true",
                        help="keep refreshing, so finished games pick up their scores")
    parser.add_argument("--interval", type=int, default=1800,
                        help="seconds between refreshes in --loop mode")
    args = parser.parse_args()
    asyncio.run(main(args.season, args.loop, args.interval))
