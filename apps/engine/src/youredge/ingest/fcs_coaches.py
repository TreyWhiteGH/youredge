"""Seeded sub-FBS coaching stints, with records computed from CFBD game data.

Why this is manual: no free source carries historical FCS coach-season mappings.
CFBD's /coaches is FBS-only (its classification param is silently ignored), ESPN's
coach endpoint is not season-aware and returns the current coach for every historical
year, and Wikidata's college coverage is sparse and undated.

What is NOT manual: the performance. CFBD serves FCS games (~820/season) and SRS
ratings, so once a stint says "Cignetti, James Madison, 2019-2021", the W-L record and
rating come from data. Only the mapping is asserted.

Every row loads with source='manual_fcs' and verified=false so provenance stays visible.

Usage:
    docker compose run --rm ingest python -m youredge.ingest.fcs_coaches
"""

import asyncio
import csv
import logging
from pathlib import Path

import httpx
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from youredge.config import get_settings
from youredge.db import get_engine
from youredge.ingest.resolve import normalize_name

log = logging.getLogger(__name__)
BASE = "https://api.collegefootballdata.com"
SEED = Path("/app/data/seeds/fcs_coach_stints.csv")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def _get(client, path, params):
    r = await client.get(f"{BASE}{path}", params=params)
    r.raise_for_status()
    return r.json()


def _read_seed() -> list[dict]:
    rows = []
    with SEED.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, school, start, end = (p.strip() for p in line.split(","))
            rows.append({"coach": name, "school": school,
                         "start": int(start), "end": int(end)})
    return rows


async def main():
    settings = get_settings()
    headers = {"Authorization": f"Bearer {settings.cfbd_api_key}"}
    stints = _read_seed()
    seasons = sorted({y for s in stints for y in range(s["start"], s["end"] + 1)})
    log.info("%d seeded stints across seasons %s-%s", len(stints), seasons[0], seasons[-1])

    engine = get_engine()
    async with httpx.AsyncClient(headers=headers, timeout=90) as client:
        # One games fetch per season covers every stint in it.
        games_by_season = {}
        srs_by_season = {}
        for y in seasons:
            games_by_season[y] = await _get(client, "/games", {"year": y, "classification": "fcs"})
            srs_by_season[y] = {r["team"]: r.get("rating")
                                for r in await _get(client, "/ratings/srs", {"year": y})}

    inserted = skipped = 0
    async with engine.begin() as conn:
        coaches = {normalize_name(r[1]): r[0] for r in await conn.execute(
            text("SELECT coach_id, name FROM coaches"))}
        teams = {r[0]: r[1] for r in await conn.execute(text(
            "SELECT x.source_id, x.canonical_id FROM entity_xwalk x "
            "JOIN teams t ON t.team_id = x.canonical_id "
            "WHERE x.entity_type='team' AND x.source='cfbd_alias'"))}

        for s in stints:
            coach_id = coaches.get(normalize_name(s["coach"]))
            team_id = teams.get(normalize_name(s["school"]))
            if not coach_id or not team_id:
                log.warning("skip %s @ %s (coach=%s team=%s) - seed a coach who exists "
                            "in FBS data, and a school we carry",
                            s["coach"], s["school"], bool(coach_id), bool(team_id))
                skipped += 1
                continue

            for year in range(s["start"], s["end"] + 1):
                # A seed must never shadow CFBD. If that school was FBS that season,
                # CFBD already has the real record and this row would be computed from
                # crossover games only - e.g. Sumrall at Troy 2022 came out 1-0.
                covered = (await conn.execute(
                    text("""
                        SELECT 1 FROM coach_seasons
                        WHERE team_id = :tid AND season = :y AND source = 'cfbd'
                    """),
                    {"tid": team_id, "y": year},
                )).first()
                if covered:
                    log.warning("  skip %s @ %s %s: CFBD already covers it (was FBS)",
                                s["coach"], s["school"], year)
                    continue

                wins = losses = 0
                for g in games_by_season.get(year, []):
                    home, away = g.get("homeTeam"), g.get("awayTeam")
                    hp, ap = g.get("homePoints"), g.get("awayPoints")
                    if hp is None or ap is None:
                        continue
                    if home == s["school"]:
                        wins, losses = (wins + 1, losses) if hp > ap else (wins, losses + 1)
                    elif away == s["school"]:
                        wins, losses = (wins + 1, losses) if ap > hp else (wins, losses + 1)
                games = wins + losses
                await conn.execute(
                    text("""
                        INSERT INTO coach_seasons (coach_id, team_id, season, games, wins,
                            losses, win_pct, srs, classification, source, verified)
                        VALUES (:cid, :tid, :y, :g, :w, :l, :wp, :srs, 'fcs',
                                'manual_fcs', FALSE)
                        ON CONFLICT (coach_id, team_id, season) DO UPDATE SET
                            games=EXCLUDED.games, wins=EXCLUDED.wins, losses=EXCLUDED.losses,
                            win_pct=EXCLUDED.win_pct, srs=EXCLUDED.srs,
                            classification='fcs', source='manual_fcs', verified=FALSE
                    """),
                    {"cid": coach_id, "tid": team_id, "y": year, "g": games or None,
                     "w": wins, "l": losses,
                     "wp": (wins / games) if games else None,
                     "srs": srs_by_season.get(year, {}).get(s["school"])},
                )
                inserted += 1
                log.info("  %s @ %s %s: %d-%d (srs %s)", s["coach"], s["school"], year,
                         wins, losses, srs_by_season.get(year, {}).get(s["school"]))

    log.info("seeded %d coach-seasons (%d stints skipped)", inserted, skipped)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(main())
