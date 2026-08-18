"""NFL player ingestion from nflverse (via nflreadpy load_players).

Fills the players table (prop layer depends on it) and writes xwalk rows:
  - espn_id     -> future live-feed joins
  - name alias  -> odds-feed prop outcomes name players ("Lamar Jackson"),
                   normalized like team aliases; ambiguous names dropped

Scope: players whose last_season >= 2023 — covers everyone referenced by the
ingested PBP plus current rosters, keeps the table lean.

Usage:
    docker compose run --rm ingest python -m youredge.ingest.players
"""

import asyncio
import logging

import nflreadpy as nfl
import pandas as pd
from sqlalchemy import text

from youredge.db import get_engine
from youredge.ingest.resolve import normalize_name

log = logging.getLogger(__name__)

MIN_LAST_SEASON = 2023


async def ingest_players() -> int:
    players = nfl.load_players().to_pandas()
    players = players[
        (players.last_season >= MIN_LAST_SEASON) & players.gsis_id.notna()
    ]
    log.info("nflverse players (last_season >= %s): %d", MIN_LAST_SEASON, len(players))

    engine = get_engine()
    async with engine.begin() as conn:
        known_teams = {
            r[0] for r in await conn.execute(text("SELECT team_id FROM teams WHERE league='nfl'"))
        }

        for _, p in players.iterrows():
            team_id = f"nfl:{p.latest_team}" if pd.notna(p.latest_team) else None
            await conn.execute(
                text("""
                    INSERT INTO players (player_id, league, team_id, name, position)
                    VALUES (:pid, 'nfl', :team, :name, :pos)
                    ON CONFLICT (player_id) DO UPDATE
                      SET team_id = EXCLUDED.team_id,
                          name = EXCLUDED.name,
                          position = EXCLUDED.position
                """),
                {
                    "pid": f"nfl:{p.gsis_id}",
                    "team": team_id if team_id in known_teams else None,
                    "name": p.display_name,
                    "pos": p.position if pd.notna(p.position) else None,
                },
            )
            if pd.notna(p.espn_id):
                await conn.execute(
                    text("""
                        INSERT INTO entity_xwalk (entity_type, canonical_id, source, source_id)
                        VALUES ('player', :cid, 'espn', :sid)
                        ON CONFLICT (entity_type, source, source_id) DO NOTHING
                    """),
                    {"cid": f"nfl:{p.gsis_id}", "sid": str(int(p.espn_id))},
                )

        # Name aliases for prop-outcome resolution; ambiguous names are dropped
        # (an odds feed saying just "Josh Allen" must never guess between two).
        aliases: dict[str, str] = {}
        ambiguous: set[str] = set()
        for _, p in players.iterrows():
            pid = f"nfl:{p.gsis_id}"
            forms = {p.display_name}
            if pd.notna(p.first_name) and pd.notna(p.last_name):
                forms.add(f"{p.first_name} {p.last_name}")
            for form in forms:
                key = normalize_name(form)
                if not key:
                    continue
                if aliases.get(key, pid) != pid:
                    ambiguous.add(key)
                aliases[key] = pid
        for key in ambiguous:
            del aliases[key]
        for key, pid in aliases.items():
            await conn.execute(
                text("""
                    INSERT INTO entity_xwalk (entity_type, canonical_id, source, source_id)
                    VALUES ('player', :cid, 'nflverse_alias', :sid)
                    ON CONFLICT (entity_type, source, source_id)
                      DO UPDATE SET canonical_id = EXCLUDED.canonical_id
                """),
                {"cid": pid, "sid": key},
            )
        log.info("player aliases: %d rows (%d ambiguous dropped)", len(aliases), len(ambiguous))
    return len(players)


async def main():
    n = await ingest_players()
    log.info("Players ingested: %d", n)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
