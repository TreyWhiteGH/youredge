"""Team colours and logo references, from ESPN's public teams endpoint.

Stores a URL for the mark, never the mark itself. Whether a logo is rendered is a
product decision that belongs to the client, and keeping the bytes out of our database
keeps that decision reversible.

Colours are the part worth having regardless: they carry the recognition a logo does
without carrying its trademark question, so a surface can be unmistakably Ohio State
without reproducing anyone's artwork.

Do NOT set a browser User-Agent here — see youredge.api.routes.live for why a spoofed
Chrome string gets a 403 from this host while httpx's own default passes.
"""

import argparse
import asyncio
import logging

import httpx
from sqlalchemy import text

from youredge.db import get_engine

log = logging.getLogger(__name__)

TEAMS_URL = {
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams",
    "ncaaf": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams",
}

# The same two franchises ESPN spells differently everywhere else.
ESPN_TEAM_ALIAS = {"WSH": "WAS", "LAR": "LA"}

_UPDATE = text("""
    UPDATE teams SET color = :color, alt_color = :alt, logo_url = :logo
    WHERE team_id = :tid
""")


def _canonical(league: str, team: dict) -> str:
    """NCAAF ids are ESPN's numeric ids; NFL keys on abbreviation."""
    if league == "ncaaf":
        return f"ncaaf:{team['id']}"
    abbr = team.get("abbreviation", "")
    return f"nfl:{ESPN_TEAM_ALIAS.get(abbr, abbr)}"


async def ingest(leagues: list[str]) -> dict:
    out = {}
    async with httpx.AsyncClient(timeout=45.0) as client:
        for league in leagues:
            r = await client.get(TEAMS_URL[league], params={"limit": 1000})
            r.raise_for_status()
            teams = [g["team"] for g in r.json()["sports"][0]["leagues"][0]["teams"]]

            matched = skipped = 0
            async with get_engine().begin() as conn:
                known = set((await conn.execute(
                    text("SELECT team_id FROM teams WHERE league = :lg"),
                    {"lg": league})).scalars())
                for t in teams:
                    tid = _canonical(league, t)
                    if tid not in known:
                        # ESPN lists 760 college programmes; we carry the 138 FBS teams
                        # plus FCS crossover opponents. The rest are simply not ours.
                        skipped += 1
                        continue
                    logos = t.get("logos") or []
                    await conn.execute(_UPDATE, {
                        "tid": tid,
                        "color": t.get("color"),
                        "alt": t.get("alternateColor"),
                        "logo": logos[0].get("href") if logos else None,
                    })
                    matched += 1
            out[league] = {"updated": matched, "not_ours": skipped}
            log.info("%s: %s", league, out[league])
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--leagues", nargs="+", default=["nfl", "ncaaf"])
    args = parser.parse_args()
    asyncio.run(ingest(args.leagues))
