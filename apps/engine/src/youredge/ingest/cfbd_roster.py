"""College player identity from CFBD rosters.

CFBD is canonical for NCAAF as nflverse is for the NFL: player_id is
'ncaaf:<espn_athlete_id>', the same id /roster, /stats/player/season and
/games/players all key on. One bulk call per season returns every FBS player
(22,843 for 2024), so this is cheap.

Alias strategy differs from the NFL on purpose. With ~22k players per season,
name collisions are common, and the NFL approach (drop every ambiguous name)
would discard a large share of real players. Instead two alias sources are
written:

  ncaaf_alias        <normalized name>              - only when globally unique
  ncaaf_alias_team   <team_id>|<normalized name>    - always

Prop odds name players as free text but always arrive attached to an event, so
the team is known: resolution tries the team-scoped alias first and falls back
to the global one. A name that is ambiguous even within one roster is written
to neither - it is not resolvable and must not be guessed.

Usage:
    docker compose run --rm ingest python -m youredge.ingest.cfbd_roster --seasons 2023 2024 2025 2026
"""

import argparse
import asyncio
import logging
from collections import defaultdict

import httpx
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from youredge.config import get_settings
from youredge.db import get_engine
from youredge.ingest.resolve import normalize_name

log = logging.getLogger(__name__)
BASE = "https://api.collegefootballdata.com"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
async def _get(client: httpx.AsyncClient, path: str, params: dict) -> list[dict]:
    r = await client.get(f"{BASE}{path}", params=params)
    r.raise_for_status()
    return r.json()


async def ingest_season(season: int) -> dict:
    settings = get_settings()
    if not settings.cfbd_api_key:
        raise SystemExit("CFBD_API_KEY not set in .env")
    headers = {"Authorization": f"Bearer {settings.cfbd_api_key}"}

    async with httpx.AsyncClient(headers=headers, timeout=180) as client:
        roster = await _get(client, "/roster", {"year": season})
    log.info("CFBD roster %s: %d players", season, len(roster))

    engine = get_engine()
    inserted = skipped = 0
    async with engine.begin() as conn:
        # Schools resolve through the alias rows the context ingest built, joined
        # against teams: the alias table covers every CFBD school (684), while teams
        # only holds the ones we actually carry, so an unjoined lookup FK-violates.
        teams = {r[0]: r[1] for r in await conn.execute(text(
            "SELECT x.source_id, x.canonical_id FROM entity_xwalk x "
            "JOIN teams t ON t.team_id = x.canonical_id "
            "WHERE x.entity_type='team' AND x.source='cfbd_alias'"))}

        rows = []
        for p in roster:
            if p.get("id") is None or not p.get("team"):
                skipped += 1
                continue
            team_id = teams.get(normalize_name(p["team"]))
            if team_id is None:
                skipped += 1
                continue
            name = " ".join(x for x in (p.get("firstName"), p.get("lastName")) if x).strip()
            if not name:
                skipped += 1
                continue
            rows.append({
                "pid": f"ncaaf:{p['id']}", "team": team_id, "name": name,
                "pos": p.get("position"),
                "jersey": str(p["jersey"]) if p.get("jersey") is not None else None,
                "year": str(p["year"]) if p.get("year") is not None else None,
                "norm": normalize_name(name),
            })

        for r in rows:
            await conn.execute(
                text("""
                    INSERT INTO players (player_id, league, team_id, name, position,
                                         jersey, class_year)
                    VALUES (:pid, 'ncaaf', :team, :name, :pos, :jersey, :year)
                    ON CONFLICT (player_id) DO UPDATE SET
                        team_id = EXCLUDED.team_id, name = EXCLUDED.name,
                        position = EXCLUDED.position, jersey = EXCLUDED.jersey,
                        class_year = EXCLUDED.class_year
                """),
                r,
            )
            inserted += 1

        # Team-scoped aliases: written for everyone except within-roster duplicates,
        # which are genuinely unresolvable from a name plus a team.
        by_team = defaultdict(list)
        by_name = defaultdict(set)
        for r in rows:
            by_team[(r["team"], r["norm"])].append(r["pid"])
            by_name[r["norm"]].add(r["pid"])

        team_aliases = dupes = 0
        for (team_id, norm), pids in by_team.items():
            if len(set(pids)) != 1:
                dupes += 1
                continue
            await conn.execute(
                text("""
                    INSERT INTO entity_xwalk (entity_type, canonical_id, source, source_id)
                    VALUES ('player', :cid, 'ncaaf_alias_team', :sid)
                    ON CONFLICT (entity_type, source, source_id)
                      DO UPDATE SET canonical_id = EXCLUDED.canonical_id
                """),
                {"cid": pids[0], "sid": f"{team_id}|{norm}"},
            )
            team_aliases += 1

        global_aliases = 0
        for norm, pids in by_name.items():
            if len(pids) != 1:
                continue
            await conn.execute(
                text("""
                    INSERT INTO entity_xwalk (entity_type, canonical_id, source, source_id)
                    VALUES ('player', :cid, 'ncaaf_alias', :sid)
                    ON CONFLICT (entity_type, source, source_id)
                      DO UPDATE SET canonical_id = EXCLUDED.canonical_id
                """),
                {"cid": next(iter(pids)), "sid": norm},
            )
            global_aliases += 1

    stats = {"players": inserted, "skipped": skipped, "team_aliases": team_aliases,
             "global_aliases": global_aliases, "within_roster_dupes": dupes}
    log.info("  %s", stats)
    return stats


async def main(seasons: list[int]):
    for season in seasons:
        try:
            await ingest_season(season)
        except httpx.HTTPStatusError as e:
            log.error("season %s failed: %s", season, e)
        await asyncio.sleep(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.seasons))
