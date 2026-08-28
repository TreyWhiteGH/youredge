"""Backfill NCAAF play-grain scoring and turnover flags from CFBD.

College plays landed with `touchdown`, `interception`, `fumble_lost`, `safety`,
`sack` and `field_goal_result` all NULL — not because CFBD withholds them, but
because `cfbd_map.map_play_type` folds its precise vocabulary into the eight
nflverse-shaped buckets both leagues share, and nothing kept what it discarded.

This recovers them. Every flag comes from `playType` directly; no play-text
parsing is involved, because CFBD names each event exactly:

    Rushing Touchdown · Passing Touchdown · Field Goal Good · Field Goal Missed
    Interception Return Touchdown · Fumble Recovery (Own) vs (Opponent) · Sack

That Own/Opponent split is the one that matters most — it is precisely
`fumble_lost`, and without it a recovered fumble and a turnover look identical.

Writes in place by (game_id, source_play_id): CFBD's play `id` is stored verbatim
as source_play_id, so no row is re-inserted and nothing downstream of `plays` is
invalidated.

    docker compose run --rm ingest python -m youredge.ingest.cfbd_play_flags --seasons 2023 2024 2025
"""

import argparse
import asyncio
import logging

import httpx
from sqlalchemy import text

from youredge.config import get_settings
from youredge.db import get_engine
from youredge.ingest.cfbd_http import CFBDError, get_json

log = logging.getLogger(__name__)
BASE = "https://api.collegefootballdata.com"

TOUCHDOWN_TYPES = {
    "Rushing Touchdown", "Passing Touchdown", "Interception Return Touchdown",
    "Fumble Return Touchdown", "Punt Return Touchdown", "Kickoff Return Touchdown",
    "Blocked Punt Touchdown", "Blocked Field Goal Touchdown",
    "Missed Field Goal Return Touchdown", "Fumble Recovery (Opponent) Touchdown",
}
# A touchdown scored by the defence or on a return. The offence gets no points,
# which is the distinction that made 4.4% of NFL drives wrong before it was fixed.
DEFENSIVE_TD_TYPES = {
    "Interception Return Touchdown", "Fumble Return Touchdown",
    "Punt Return Touchdown", "Kickoff Return Touchdown", "Blocked Punt Touchdown",
    "Blocked Field Goal Touchdown", "Missed Field Goal Return Touchdown",
    "Fumble Recovery (Opponent) Touchdown",
}
INTERCEPTION_TYPES = {
    "Interception", "Pass Interception Return", "Interception Return Touchdown",
}
# Only fumbles the offence *lost*. 'Fumble Recovery (Own)' is a fumble the offence
# kept, and calling it a turnover would invent one out of a muffed handoff.
FUMBLE_LOST_TYPES = {
    "Fumble Recovery (Opponent)", "Fumble Return Touchdown",
    "Fumble Recovery (Opponent) Touchdown",
}
FG_RESULT = {
    "Field Goal Good": "made",
    "Field Goal Missed": "missed",
    "Blocked Field Goal": "blocked",
    "Blocked Field Goal Touchdown": "blocked",
    "Missed Field Goal Return Touchdown": "missed",
    "Missed Field Goal Return": "missed",
}
SACK_TYPES = {"Sack"}
SAFETY_TYPES = {"Safety"}
COMPLETION_TYPES = {"Pass Reception", "Passing Touchdown"}
# A dropback is any called pass: completions, incompletions, interceptions and
# sacks alike. This is what separates pass/run mix from play_type, where a sack
# is not a pass and a scramble is a run.
DROPBACK_TYPES = (
    COMPLETION_TYPES | INTERCEPTION_TYPES | SACK_TYPES | {"Pass Incompletion"}
)


def derive(play_type: str) -> dict:
    """Every flag we can state about a play from its CFBD type alone."""
    return {
        "touchdown": play_type in TOUCHDOWN_TYPES,
        "defensive_td": play_type in DEFENSIVE_TD_TYPES,
        "interception": play_type in INTERCEPTION_TYPES,
        "fumble_lost": play_type in FUMBLE_LOST_TYPES,
        "safety": play_type in SAFETY_TYPES,
        "sack": play_type in SACK_TYPES,
        "complete_pass": play_type in COMPLETION_TYPES,
        "qb_dropback": play_type in DROPBACK_TYPES,
        "field_goal_result": FG_RESULT.get(play_type),
    }


async def _get(client: httpx.AsyncClient, params: dict):
    return await get_json(client, f"{BASE}/plays", params)


_UPDATE = text("""
    UPDATE plays SET
        play_type_raw     = s.raw,
        scoring           = s.scoring,
        touchdown         = s.touchdown,
        interception      = s.interception,
        fumble_lost       = s.fumble_lost,
        safety            = s.safety,
        sack              = s.sack,
        complete_pass     = s.complete_pass,
        qb_dropback       = s.qb_dropback,
        field_goal_result = s.fg_result
    FROM (
        SELECT unnest(CAST(:gids AS text[]))    AS game_id,
               unnest(CAST(:pids AS text[]))    AS source_play_id,
               unnest(CAST(:raws AS text[]))    AS raw,
               unnest(CAST(:scor AS boolean[])) AS scoring,
               unnest(CAST(:td   AS boolean[])) AS touchdown,
               unnest(CAST(:intc AS boolean[])) AS interception,
               unnest(CAST(:fum  AS boolean[])) AS fumble_lost,
               unnest(CAST(:saf  AS boolean[])) AS safety,
               unnest(CAST(:sk   AS boolean[])) AS sack,
               unnest(CAST(:cmp  AS boolean[])) AS complete_pass,
               unnest(CAST(:drop AS boolean[])) AS qb_dropback,
               unnest(CAST(:fg   AS text[]))    AS fg_result
    ) s
    WHERE plays.game_id = s.game_id AND plays.source_play_id = s.source_play_id
""")


async def backfill_week(season: int, week: int, season_type: str) -> tuple[int, set[str]]:
    settings = get_settings()
    if not settings.cfbd_api_key:
        raise SystemExit("CFBD_API_KEY not set in .env")

    headers = {"Authorization": f"Bearer {settings.cfbd_api_key}"}
    async with httpx.AsyncClient(headers=headers, timeout=120) as client:
        plays = await _get(client, {
            "year": season, "week": week, "seasonType": season_type,
            "classification": "fbs",
        })
    if not plays:
        return 0, set()

    cols: dict[str, list] = {k: [] for k in (
        "gids", "pids", "raws", "scor", "td", "intc", "fum", "saf", "sk", "cmp",
        "drop", "fg",
    )}
    seen_types: set[str] = set()
    for p in plays:
        raw = p.get("playType") or ""
        seen_types.add(raw)
        d = derive(raw)
        cols["gids"].append(f"ncaaf:{p.get('gameId')}")
        cols["pids"].append(str(p.get("id")))
        cols["raws"].append(raw)
        cols["scor"].append(bool(p.get("scoring")))
        cols["td"].append(d["touchdown"])
        cols["intc"].append(d["interception"])
        cols["fum"].append(d["fumble_lost"])
        cols["saf"].append(d["safety"])
        cols["sk"].append(d["sack"])
        cols["cmp"].append(d["complete_pass"])
        cols["drop"].append(d["qb_dropback"])
        cols["fg"].append(d["field_goal_result"])

    engine = get_engine()
    async with engine.begin() as conn:
        res = await conn.execute(_UPDATE, cols)
    return res.rowcount, seen_types


async def main(seasons: list[int], weeks: range, season_types: list[str]):
    updated = 0
    all_types: set[str] = set()
    for season in seasons:
        for st in season_types:
            for week in (weeks if st == "regular" else [1]):
                try:
                    n, types = await backfill_week(season, week, st)
                except CFBDError as e:
                    log.warning("%s %s wk%s failed: %s", season, st, week, e)
                    continue
                all_types |= types
                updated += n
                if n:
                    log.info("%s %s wk%-2s  %6d plays updated", season, st, week, n)

    # A playType we have no rule for is silently treated as an ordinary snap, so
    # surface anything unrecognised rather than letting the vocabulary drift.
    known = (
        TOUCHDOWN_TYPES | INTERCEPTION_TYPES | FUMBLE_LOST_TYPES | set(FG_RESULT)
        | SACK_TYPES | SAFETY_TYPES | DROPBACK_TYPES
        | {"Rush", "Punt", "Kickoff", "Penalty", "Timeout", "End Period",
           "End of Half", "End of Game", "End of Regulation", "Uncategorized",
           "Kickoff Return (Offense)", "Fumble Recovery (Own)", "Blocked Punt",
           "Two Point Rush", "Two Point Pass", "Defensive 2pt Conversion",
           "Extra Point Good", "Extra Point Missed", "Kickoff Return (Defense)",
           "Pass", "Pass Completion", "Rushing Touchdown",
           # Return plays. Not scrimmage snaps, so no offensive flag applies;
           # possession outcome is already carried by the punt/FG play itself.
           "Punt Return", "Missed Field Goal Return",
           # A bare 'Fumble' is one CFBD could not resolve to Own or Opponent
           # recovery — it emits those explicitly when it knows. Deliberately NOT
           # flagged as fumble_lost: inventing a turnover from an unresolved
           # fumble is the one error that would corrupt the drive kernel, and it
           # is 76 plays in 487k.
           "Fumble",
           "placeholder"}
    )
    unmapped = sorted(all_types - known)
    if unmapped:
        log.warning("playType values with no flag rule (treated as plain snaps): %s",
                    unmapped)
    log.info("total plays updated: %d", updated)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, required=True)
    parser.add_argument("--max-week", type=int, default=17)
    parser.add_argument("--season-type", nargs="+", default=["regular", "postseason"])
    args = parser.parse_args()
    asyncio.run(main(args.seasons, range(1, args.max_week + 1), args.season_type))
