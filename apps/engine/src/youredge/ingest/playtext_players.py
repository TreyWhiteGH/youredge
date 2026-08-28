"""Write player attribution parsed from play text, for games the feed misses.

CFBD's /plays/stats covers SEC and ACC — 790 of 2,761 games. This fills the rest
from `plays.play_text`, resolved against the roster crosswalk.

Only three roles are written, and the cut is not arbitrary. Scored against 60,000
plays where the feed and the text both exist:

    rusher      99.3% precision   96.2% recall
    receiver    99.4%             96.4%
    passer      97.6%             97.9%
    sacker      79.9%             95.6%   <- not written
    interceptor 80.2%             75.6%   <- not written

Sacks and interceptions stay out. A shared sack names two defenders and the text
does not say who is credited, so four rows in five being right is not good enough
for something a model would read as a defensive rate. Rerun
`validate_playtext.py` after any change to the patterns — the thresholds above
are the reason this is allowed to write at all.

Feed rows are authoritative and never overwritten; parsed rows carry
source='playtext' so anything downstream can weigh them differently.

    docker compose run --rm ingest python -m youredge.ingest.playtext_players
"""

import argparse
import asyncio
import logging

from sqlalchemy import text

from youredge.db import get_engine
from youredge.ingest.playtext import PASSER, RECEIVER, RUSHER, load_roster, parse

log = logging.getLogger(__name__)

WRITTEN_ROLES = {RUSHER, RECEIVER, PASSER}

# The feed's own stat vocabulary, so a parsed row reads the same as a fed one.
# What the passer and receiver are credited with depends on how the pass ended,
# which play_type_raw already records.
PASSER_STAT = {
    "Pass Reception": "Completion",
    "Passing Touchdown": "Completion",
    "Pass Incompletion": "Incompletion",
    "Interception": "Interception Thrown",
    "Pass Interception Return": "Interception Thrown",
    "Interception Return Touchdown": "Interception Thrown",
    "Sack": "Sack Taken",
}
RECEIVER_STAT = {
    "Pass Reception": "Reception",
    "Passing Touchdown": "Reception",
    "Pass Incompletion": "Target",
}

_SOURCE = text("""
    SELECT p.game_id, p.source_play_id, p.play_text, p.play_type_raw,
           p.posteam_id, p.yards_gained
    FROM plays p
    JOIN games g ON g.game_id = p.game_id
    WHERE g.league = 'ncaaf'
      AND p.play_text IS NOT NULL
      AND p.posteam_id IS NOT NULL
      -- Only games the feed does not already cover. Where real athlete ids
      -- exist they are the answer, and inference has nothing to add.
      AND NOT EXISTS (
          SELECT 1 FROM play_players pp
          WHERE pp.game_id = p.game_id AND pp.source = 'cfbd_stats'
      )
""")

_INSERT = text("""
    INSERT INTO play_players
        (game_id, source_play_id, athlete_id, player_id, athlete_name,
         team_id, stat_type, stat, source)
    SELECT s.game_id, s.source_play_id,
           replace(s.player_id, 'ncaaf:', ''), s.player_id, s.name,
           s.team_id, s.stat_type, s.stat, 'playtext'
    FROM (
        SELECT unnest(CAST(:gids  AS text[])) AS game_id,
               unnest(CAST(:pids  AS text[])) AS source_play_id,
               unnest(CAST(:plids AS text[])) AS player_id,
               unnest(CAST(:names AS text[])) AS name,
               unnest(CAST(:teams AS text[])) AS team_id,
               unnest(CAST(:stats AS text[])) AS stat_type,
               unnest(CAST(:vals  AS real[])) AS stat
    ) s
    -- Never clobber the feed.
    ON CONFLICT (game_id, source_play_id, athlete_id, stat_type) DO NOTHING
""")


def _stat_type(role: str, play_type_raw: str | None) -> str | None:
    pt = play_type_raw or ""
    if role == RUSHER:
        return "Rush"
    if role == PASSER:
        return PASSER_STAT.get(pt)
    if role == RECEIVER:
        return RECEIVER_STAT.get(pt)
    return None


async def run(batch: int) -> None:
    engine = get_engine()
    async with engine.connect() as conn:
        roster = await load_roster(conn)
        rows = (await conn.execute(_SOURCE)).mappings().all()
    log.info("%d plays on games the feed does not cover", len(rows))

    cols: dict[str, list] = {k: [] for k in
                             ("gids", "pids", "plids", "names", "teams", "stats", "vals")}
    written = unresolved = skipped = 0

    async def flush() -> int:
        if not cols["gids"]:
            return 0
        engine_ = get_engine()
        async with engine_.begin() as conn_:
            n = (await conn_.execute(_INSERT, cols)).rowcount
        for v in cols.values():
            v.clear()
        return n

    for r in rows:
        for role, name in parse(r["play_text"]):
            if role not in WRITTEN_ROLES:
                continue
            stat_type = _stat_type(role, r["play_type_raw"])
            if not stat_type:
                skipped += 1
                continue
            pid = roster.resolve(r["posteam_id"], name)
            if pid is None:
                unresolved += 1
                continue
            cols["gids"].append(r["game_id"])
            cols["pids"].append(r["source_play_id"])
            cols["plids"].append(pid)
            cols["names"].append(name)
            cols["teams"].append(r["posteam_id"])
            cols["stats"].append(stat_type)
            cols["vals"].append(
                float(r["yards_gained"]) if r["yards_gained"] is not None else None
            )
            if len(cols["gids"]) >= batch:
                written += await flush()
    written += await flush()

    async with engine.connect() as conn:
        summary = (await conn.execute(text("""
            SELECT source, count(*) AS rows, count(DISTINCT game_id) AS games
            FROM play_players GROUP BY source ORDER BY 2 DESC
        """))).mappings().all()
    log.info("wrote %d parsed rows (%d names unresolved, %d roles with no stat type)",
             written, unresolved, skipped)
    for s in summary:
        log.info("  %-12s %8d rows  %5d games", s["source"], s["rows"], s["games"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=20000)
    args = ap.parse_args()
    asyncio.run(run(args.batch))
