"""NFL player ingestion from nflverse (via nflreadpy load_players).

Fills the players table (prop layer depends on it) and writes xwalk rows:
  - espn_id     -> future live-feed joins
  - name alias  -> odds-feed prop outcomes name players ("Lamar Jackson"),
                   normalized like team aliases; ambiguous names dropped

Scope: players whose last_season >= 2023 (everyone referenced by ingested PBP)
plus the current season's rosters — the master players file lags on rookies,
who won't appear there until they've played, but get props before Week 1.

Usage:
    docker compose run --rm ingest python -m youredge.ingest.players
"""

import argparse
import asyncio
import logging

import nflreadpy as nfl
import pandas as pd
from sqlalchemy import text

from youredge.db import get_engine
from youredge.ingest.resolve import normalize_name

log = logging.getLogger(__name__)

MIN_LAST_SEASON = 2023


def _load_player_pool(current_season: int) -> pd.DataFrame:
    players = nfl.load_players().to_pandas()
    players = players[
        (players.last_season >= MIN_LAST_SEASON) & players.gsis_id.notna()
    ][["gsis_id", "display_name", "first_name", "last_name", "position", "latest_team", "espn_id", "pfr_id"]]
    log.info("nflverse players (last_season >= %s): %d", MIN_LAST_SEASON, len(players))

    rosters = nfl.load_rosters(seasons=[current_season]).to_pandas()
    rosters = rosters[rosters.gsis_id.notna()]
    # Roster team is fresher than latest_team; roster-only rows are rookies.
    players = players.set_index("gsis_id")
    roster_team = rosters.set_index("gsis_id").team
    players.loc[players.index.intersection(roster_team.index), "latest_team"] = roster_team
    new = rosters[~rosters.gsis_id.isin(players.index)]
    log.info("%s rosters: %d players, %d not in master file (rookies)",
             current_season, len(rosters), len(new))
    additions = pd.DataFrame({
        "gsis_id": new.gsis_id,
        "display_name": new.full_name,
        "first_name": new.first_name if "first_name" in new.columns else None,
        "last_name": new.last_name if "last_name" in new.columns else None,
        "position": new.position,
        "latest_team": new.team,
        "espn_id": new.espn_id if "espn_id" in new.columns else None,
        "pfr_id": new.pfr_id if "pfr_id" in new.columns else None,
    })
    return pd.concat([players.reset_index(), additions], ignore_index=True)


async def ingest_players(current_season: int = 2026) -> int:
    players = _load_player_pool(current_season)

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
            for source, val in (("espn", p.espn_id), ("pfr", p.pfr_id)):
                if pd.notna(val):
                    sid = str(int(val)) if source == "espn" else str(val)
                    await conn.execute(
                        text("""
                            INSERT INTO entity_xwalk (entity_type, canonical_id, source, source_id)
                            VALUES ('player', :cid, :source, :sid)
                            ON CONFLICT (entity_type, source, source_id) DO NOTHING
                        """),
                        {"cid": f"nfl:{p.gsis_id}", "source": source, "sid": sid},
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


async def main(current_season: int):
    n = await ingest_players(current_season)
    log.info("Players ingested: %d", n)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    args = parser.parse_args()
    asyncio.run(main(args.season))
