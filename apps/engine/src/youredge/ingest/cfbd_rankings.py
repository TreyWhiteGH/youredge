"""Poll rankings — AP, Coaches, and the CFP committee — week by week.

`team_season_context.sp_ranking` already gave us an ordering, but SP+ is a rating
system and a poll is a vote. They disagree often and loudly, and a "Top 25" built from
SP+ would contain teams no voter ranked. This loads the polls themselves.

CFBD keys ranked teams by the same numeric id our `ncaaf:` ids are built from, so the
join is exact. FCS polls are skipped: those schools are outside our team table, and a
row that cannot resolve is dropped with a count rather than guessed at.
"""

import argparse
import asyncio
import logging

import httpx
from sqlalchemy import text

from youredge.config import get_settings
from youredge.db import get_engine
from youredge.ingest.cfbd_http import get_json

log = logging.getLogger(__name__)

BASE = "https://api.collegefootballdata.com"

# The FCS coaches poll ranks schools we do not carry, and mixing it in would put an FCS
# team in an FBS Top 25. Named rather than filtered by a substring so a new poll shows
# up as "unknown" in the logs instead of being silently swallowed.
POLLS = {"AP Top 25", "Coaches Poll", "Playoff Committee Rankings"}

_UPSERT = text("""
    INSERT INTO team_rankings
        (season, season_type, week, poll, team_id, rank, points, first_place_votes)
    VALUES (:season, :stype, :week, :poll, :tid, :rank, :points, :fpv)
    ON CONFLICT (season, season_type, week, poll, team_id) DO UPDATE
       SET rank = EXCLUDED.rank,
           points = EXCLUDED.points,
           first_place_votes = EXCLUDED.first_place_votes
""")


async def ingest(seasons: list[int], season_type: str = "regular") -> dict:
    settings = get_settings()
    if not settings.cfbd_api_key:
        raise RuntimeError("CFBD_API_KEY is not set")

    written = skipped = 0
    unknown_polls: set[str] = set()

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {settings.cfbd_api_key}"}, timeout=30.0
    ) as client:
        async with get_engine().begin() as conn:
            known = set((await conn.execute(
                text("SELECT team_id FROM teams WHERE league = 'ncaaf'"))).scalars())

            for season in seasons:
                weeks = await get_json(client, f"{BASE}/rankings",
                                       {"year": season, "seasonType": season_type})
                for wk in weeks:
                    for poll in wk.get("polls") or []:
                        name = poll.get("poll")
                        if name not in POLLS:
                            unknown_polls.add(name)
                            continue
                        for r in poll.get("ranks") or []:
                            tid = f"ncaaf:{r.get('teamId')}"
                            if tid not in known:
                                skipped += 1
                                continue
                            await conn.execute(_UPSERT, {
                                "season": season, "stype": season_type,
                                "week": wk.get("week"), "poll": name, "tid": tid,
                                "rank": r.get("rank"), "points": r.get("points"),
                                "fpv": r.get("firstPlaceVotes"),
                            })
                            written += 1
                log.info("season %s: %d weeks", season, len(weeks))

    return {"written": written, "unresolved_teams": skipped,
            "polls_ignored": sorted(unknown_polls)}


async def main(seasons: list[int], season_type: str):
    log.info("rankings: %s", await ingest(seasons, season_type))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, required=True)
    parser.add_argument("--season-type", default="regular",
                        choices=["regular", "postseason"])
    args = parser.parse_args()
    asyncio.run(main(args.seasons, args.season_type))
