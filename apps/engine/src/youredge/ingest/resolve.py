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
    'The Citadel' -> 'citadel', 'T.J. Watt' -> 'tj watt'. 'State'->'st' folds the
    two sources' conventions; runs of single letters merge so dotted initials
    match their undotted query form.
    """
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # Every apostrophe form, ASCII and typographic alike: Hawai'i -> hawaii, not
    # 'hawai i'. U+2019 was missing, so any feed using curly quotes silently
    # failed to match — "Jo’Quavious Marks" normalised to 'jo quavious marks'
    # and resolved to nobody.
    s = re.sub(r"['‘’ʻʼ`´]", "", s.lower())
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    tokens = [("st" if t == "state" else t) for t in s.split() if t != "the"]
    merged: list[str] = []
    run: list[str] = []
    for t in tokens:
        if len(t) == 1:
            run.append(t)
        else:
            if run:
                merged.append("".join(run))
                run = []
            merged.append(t)
    if run:
        merged.append("".join(run))
    return " ".join(merged)

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


async def resolve_nfl_player(conn: AsyncConnection, name: str) -> str | None:
    """Canonical NFL player_id from a free-text name, or None.

    Prop feeds name players as strings ("Sam Darnold"); nflverse_alias is keyed by
    the same normalized form. Unlike college there is no team scoping needed —
    NFL rosters are small enough that the normalized name is near-unique — but an
    unresolved name is still returned as None rather than guessed. Callers keep
    the raw string on markets.player_name so the price survives the miss.
    """
    norm = normalize_name(name)
    if not norm:
        return None
    # Books drop generational suffixes that nflverse keeps ("Deebo Samuel" vs
    # "Deebo Samuel Sr."), so a miss on the exact form retries against aliases
    # that differ only by a trailing suffix. Anchored, and only accepted when it
    # picks out exactly one player — two Kenneth Walkers would resolve to neither.
    #
    # DISTINCT on the canonical id, not on the alias: nflverse carries both
    # "marvin harrison" and "marvin harrison jr" for the same person, and counting
    # rows would read one player as an ambiguous two and refuse to resolve him.
    # The league filter matters too — nflverse_alias holds the odd ncaaf: id, and
    # an NFL prop must never resolve to a college player.
    rows = (await conn.execute(
        text("""
            SELECT DISTINCT canonical_id FROM entity_xwalk
            WHERE entity_type = 'player' AND source = 'nflverse_alias'
              AND canonical_id LIKE 'nfl:%'
              AND (source_id = :sid
                   OR source_id ~ ('^' || :sid || ' (jr|sr|ii|iii|iv|v)$'))
            LIMIT 2
        """),
        {"sid": norm},
    )).fetchall()
    return rows[0][0] if len(rows) == 1 else None


async def resolve_ncaaf_player(
    conn: AsyncConnection, name: str, team_id: str | None = None
) -> str | None:
    """Canonical NCAAF player_id from a free-text name, or None.

    Odds feeds name players as strings ("J'Koby Williams") but always attach them
    to an event, so the team is known. Team-scoped aliases are tried first because
    college rosters share surnames constantly; the global alias is a fallback for
    names unique across all of FBS. A name ambiguous even within one roster
    resolves to neither — it is returned as None rather than guessed.
    """
    norm = normalize_name(name)
    if not norm:
        return None

    if team_id:
        row = (await conn.execute(
            text("""
                SELECT canonical_id FROM entity_xwalk
                WHERE entity_type = 'player' AND source = 'ncaaf_alias_team'
                  AND source_id = :sid
            """),
            {"sid": f"{team_id}|{norm}"},
        )).first()
        if row:
            return row[0]

    row = (await conn.execute(
        text("""
            SELECT canonical_id FROM entity_xwalk
            WHERE entity_type = 'player' AND source = 'ncaaf_alias'
              AND source_id = :sid
        """),
        {"sid": norm},
    )).first()
    return row[0] if row else None
