"""Entity resolution: odds-feed events → canonical game ids via entity_xwalk.

The Odds API gives (event_id, home_team name, away_team name, commence_time).
Resolution order:
  1. entity_xwalk hit on the event id (fast path after first sight)
  2. team-name resolution + kickoff-window match against canonical games
     - NFL names match teams.name exactly ("Baltimore Ravens")
     - NCAAF odds names are school+mascot ("Georgia Tech Yellow Jackets");
       longest teams.name prefix wins, which also disambiguates
       "Miami Hurricanes" vs "Miami (OH) RedHawks"
Successful resolutions are written back to entity_xwalk (game and team rows),
so steady-state polling is one indexed lookup per event.
"""

import logging
import re
import unicodedata
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

log = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    """Accent-, punctuation-, and case-insensitive form for alias matching.

    'San José State' -> 'san jose st', 'Arkansas-Pine Bluff' -> 'arkansas pine bluff',
    'The Citadel' -> 'citadel'. 'State'->'st' folds the two sources' conventions.
    """
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[''ʻ`]", "", s.lower())  # Hawai'i -> hawaii, not 'hawai i'
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    tokens = [("st" if t == "state" else t) for t in s.split() if t != "the"]
    return " ".join(tokens)

_XWALK_GET = text("""
    SELECT canonical_id FROM entity_xwalk
    WHERE entity_type = :etype AND source = 'odds_api' AND source_id = :sid
""")
_XWALK_PUT = text("""
    INSERT INTO entity_xwalk (entity_type, canonical_id, source, source_id)
    VALUES (:etype, :cid, 'odds_api', :sid)
    ON CONFLICT (entity_type, source, source_id) DO NOTHING
""")


async def _resolve_team(conn: AsyncConnection, league: str, odds_name: str) -> str | None:
    row = (await conn.execute(_XWALK_GET, {"etype": "team", "sid": f"{league}:{odds_name}"})).first()
    if row:
        return row[0]

    exact = (await conn.execute(
        text("SELECT team_id FROM teams WHERE league = :lg AND name = :name"),
        {"lg": league, "name": odds_name},
    )).first()
    if exact:
        tid = exact[0]
    elif league == "ncaaf":
        alias = (await conn.execute(
            text("""
                SELECT canonical_id FROM entity_xwalk
                WHERE entity_type = 'team' AND source = 'cfbd_alias' AND source_id = :norm
            """),
            {"norm": normalize_name(odds_name)},
        )).first()
        tid = alias[0] if alias else None
    else:
        tid = None

    if tid:
        await conn.execute(_XWALK_PUT, {"etype": "team", "cid": tid, "sid": f"{league}:{odds_name}"})
    return tid


async def resolve_event(
    conn: AsyncConnection,
    league: str,
    event_id: str,
    home_name: str,
    away_name: str,
    commence: datetime,
) -> str | None:
    """Canonical game_id for an odds event, or None if unresolvable."""
    row = (await conn.execute(_XWALK_GET, {"etype": "game", "sid": event_id})).first()
    if row:
        return row[0]

    home = await _resolve_team(conn, league, home_name)
    away = await _resolve_team(conn, league, away_name)
    if not home or not away:
        log.warning("unresolved %s teams: home=%r->%s away=%r->%s",
                    league, home_name, home, away_name, away)
        return None

    game = (await conn.execute(
        text("""
            SELECT game_id FROM games
            WHERE league = :lg AND home_team_id = :home AND away_team_id = :away
              AND game_id NOT LIKE '%:oddsapi:%'
              AND kickoff BETWEEN CAST(:t AS timestamptz) - interval '36 hours'
                              AND CAST(:t AS timestamptz) + interval '36 hours'
            ORDER BY abs(extract(epoch FROM kickoff - CAST(:t AS timestamptz))) LIMIT 1
        """),
        {"lg": league, "home": home, "away": away, "t": commence},
    )).first()
    if not game:
        log.warning("no canonical %s game for %s @ %s near %s", league, away_name, home_name, commence)
        return None

    await conn.execute(_XWALK_PUT, {"etype": "game", "cid": game[0], "sid": event_id})
    return game[0]
