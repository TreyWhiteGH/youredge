"""NCAAF drives from CollegeFootballData's /drives endpoint.

The NFL builds `drives` by deriving possession outcomes from plays. College
cannot: CFBD's play rows lose the outcome on the way in, because
`cfbd_map.map_play_type` folds "Rushing Touchdown" into "run" and "Field Goal
Good" into "field_goal" to match nflverse's vocabulary. Deriving from that
produced a league where nobody scored.

CFBD answers the question directly instead. /drives returns `driveResult` per
possession, already resolved, and one call covers a whole season — six calls for
2023-25 across both season types. That is cheaper and more authoritative than
re-deriving from play text, and it needs neither ESPN (unofficial, and reserved
for live state) nor PFF college (deliberately refused over level conflation).

    docker compose run --rm ingest python -m youredge.ingest.cfbd_drives --seasons 2023 2024 2025

What this endpoint gets right that a naive derivation does not: it names return
touchdowns as their own results. 'INT TD' is an interception the defence took
back — the possessing team scored nothing — and folding it in with 'TD' would
teach a simulator that throwing a pick sometimes pays.
"""

import argparse
import asyncio
import logging

import httpx
from sqlalchemy import text

from youredge.config import get_settings
from youredge.db import get_engine
from youredge.ingest.cfbd_http import CFBDError, get_json
from youredge.ingest.resolve import normalize_name

log = logging.getLogger(__name__)
BASE = "https://api.collegefootballdata.com"

# CFBD driveResult -> (our result, defence scored on the return).
# The offence's own points are implied by the result: only TD and FG_MADE pay.
RESULT_MAP: dict[str, tuple[str, bool]] = {
    "TD": ("TD", False),
    "FG": ("FG_MADE", False),
    "MISSED FG": ("FG_MISS", False),
    "BLOCKED FG": ("FG_MISS", False),
    "BLOCKED FG TD": ("FG_MISS", True),
    "MISSED FG TD": ("FG_MISS", True),
    "PUNT": ("PUNT", False),
    "BLOCKED PUNT": ("PUNT", False),
    "PUNT TD": ("PUNT", True),
    "PUNT RETURN TD": ("PUNT", True),
    "BLOCKED PUNT TD": ("PUNT", True),
    "INT": ("INT", False),
    "INT TD": ("INT", True),
    "INTERCEPTION": ("INT", False),
    "FUMBLE": ("FUMBLE_LOST", False),
    "FUMBLE RETURN TD": ("FUMBLE_LOST", True),
    # Ambiguous in principle — an offence can recover its own fumble in the end
    # zone — but CFBD spells that case 'TD', and this variant is vanishingly rare
    # (one drive in a full week), so it is read as a return.
    "FUMBLE TD": ("FUMBLE_LOST", True),
    "DOWNS": ("DOWNS", False),
    "TURNOVER ON DOWNS": ("DOWNS", False),
    "SF": ("SAFETY", False),
    "SAFETY": ("SAFETY", False),
    # A score on the last snap of a half is an offensive touchdown that happens
    # to end the period — the half ending is incidental to it.
    "END OF HALF TD": ("TD", False),
    "END OF GAME TD": ("TD", False),
    "END OF HALF": ("END_HALF", False),
    "END OF GAME": ("END_HALF", False),
    "END OF REGULATION": ("END_HALF", False),
    "END OF 4TH QUARTER": ("END_HALF", False),
    "Uncategorized": ("UNKNOWN", False),
    # Deliberately absent: 'DOWNS TD', 'FG TD', 'KICKOFF'. Fifteen drives in three
    # seasons, and each reading is a guess about who scored — the one mistake this
    # table exists to avoid. They land in UNKNOWN with result_raw intact, so they
    # can be settled against play-by-play later rather than assumed now.
}

POINTS = {"TD": 7, "FG_MADE": 3}


def _clock(period: int | None, t: dict | None) -> int | None:
    """Game seconds remaining from a CFBD {minutes, seconds} period clock.

    OT (period > 4) returns None, matching the convention cfbd_map already sets
    for plays — overtime has no place on a regulation clock.
    """
    if not period or period > 4 or not t:
        return None
    return (4 - period) * 900 + (t.get("minutes") or 0) * 60 + (t.get("seconds") or 0)


async def _get(client: httpx.AsyncClient, params: dict):
    return await get_json(client, f"{BASE}/drives", params)


async def _team_lookup(conn) -> dict[str, str]:
    """{normalized school name -> canonical team_id} for every known alias."""
    rows = (await conn.execute(text("""
        SELECT source_id, canonical_id FROM entity_xwalk
        WHERE entity_type = 'team' AND source = 'cfbd_alias'
    """))).all()
    lookup = {sid: cid for sid, cid in rows}
    named = (await conn.execute(text(
        "SELECT name, team_id FROM teams WHERE league = 'ncaaf'"
    ))).all()
    for name, tid in named:
        lookup.setdefault(normalize_name(name), tid)
    return lookup


_UPSERT = text("""
    INSERT INTO drives (
        game_id, drive_num, posteam_id, defteam_id,
        start_quarter, start_seconds, start_yardline, start_score_diff,
        result, result_raw, points, defensive_td, plays, pass_plays, rush_plays,
        yards, seconds, end_yardline
    )
    VALUES (
        :gid, :dnum, :pos, :def,
        :q, :start_sec, :start_yl, :score_diff,
        :result, :raw, :points, :def_td, :plays, NULL, NULL,
        :yards, :seconds, :end_yl
    )
    ON CONFLICT (game_id, drive_num) DO UPDATE SET
        posteam_id = EXCLUDED.posteam_id, defteam_id = EXCLUDED.defteam_id,
        start_quarter = EXCLUDED.start_quarter, start_seconds = EXCLUDED.start_seconds,
        start_yardline = EXCLUDED.start_yardline,
        start_score_diff = EXCLUDED.start_score_diff,
        result = EXCLUDED.result, result_raw = EXCLUDED.result_raw,
        points = EXCLUDED.points,
        defensive_td = EXCLUDED.defensive_td, plays = EXCLUDED.plays,
        yards = EXCLUDED.yards, seconds = EXCLUDED.seconds,
        end_yardline = EXCLUDED.end_yardline
""")


async def ingest_season(season: int, season_type: str) -> tuple[int, int]:
    settings = get_settings()
    if not settings.cfbd_api_key:
        raise SystemExit("CFBD_API_KEY not set in .env")

    headers = {"Authorization": f"Bearer {settings.cfbd_api_key}"}
    async with httpx.AsyncClient(headers=headers, timeout=120) as client:
        drives = await _get(client, {
            "year": season, "seasonType": season_type, "classification": "fbs",
        })
    log.info("CFBD %s %s: %d drives", season, season_type, len(drives))

    engine = get_engine()
    written = skipped = 0
    unknown_results: set[str] = set()
    async with engine.begin() as conn:
        teams = await _team_lookup(conn)
        # Only games already ingested — drives hang off games by foreign key, and
        # a drive for a game we do not have is not something to invent a game for.
        known = {r[0] for r in (await conn.execute(text(
            "SELECT game_id FROM games WHERE league = 'ncaaf' AND season = :s"
        ), {"s": season})).all()}

        for d in drives:
            gid = f"ncaaf:{d.get('gameId')}"
            if gid not in known:
                skipped += 1
                continue

            raw = (d.get("driveResult") or "").strip()
            mapped = RESULT_MAP.get(raw) or RESULT_MAP.get(raw.upper())
            if mapped is None:
                # A result we have never seen is recorded as UNKNOWN and reported,
                # not silently bucketed into something plausible.
                unknown_results.add(raw)
                mapped = ("UNKNOWN", False)
            result, def_td = mapped

            pos = teams.get(normalize_name(d.get("offense") or ""))
            dfn = teams.get(normalize_name(d.get("defense") or ""))
            period = d.get("startPeriod")
            start_sec = _clock(period, d.get("startTime"))
            end_sec = _clock(d.get("endPeriod"), d.get("endTime"))
            elapsed = d.get("elapsed") or {}
            seconds = (elapsed.get("minutes") or 0) * 60 + (elapsed.get("seconds") or 0)
            if not seconds and start_sec is not None and end_sec is not None and start_sec >= end_sec:
                seconds = start_sec - end_sec

            await conn.execute(_UPSERT, {
                "gid": gid,
                "dnum": d.get("driveNumber"),
                "pos": pos, "def": dfn,
                "q": period,
                "start_sec": start_sec,
                "start_yl": d.get("startYardsToGoal"),
                "score_diff": (
                    (d.get("startOffenseScore") or 0) - (d.get("startDefenseScore") or 0)
                    if d.get("startOffenseScore") is not None else None
                ),
                "result": result,
                "raw": raw,
                "points": 0 if def_td else POINTS.get(result, 0),
                "def_td": def_td,
                "plays": d.get("plays") or 0,
                "yards": d.get("yards"),
                "seconds": seconds or None,
                "end_yl": d.get("endYardsToGoal"),
            })
            written += 1

    if unknown_results:
        log.warning("unmapped driveResult values (stored as UNKNOWN): %s",
                    sorted(unknown_results))
    return written, skipped


# /drives gives total plays but not the pass/run split. The plays we already
# ingested do carry it, so fill it in where the drive numbering lines up rather
# than leaving the mix unknown for games whose play-by-play is loaded.
_FILL_SPLIT = text("""
    WITH split AS (
        SELECT p.game_id, p.drive_num,
               count(*) FILTER (WHERE p.play_type = 'pass') AS pass_plays,
               count(*) FILTER (WHERE p.play_type = 'run')  AS rush_plays
        FROM plays p JOIN games g ON g.game_id = p.game_id
        WHERE g.league = 'ncaaf' AND p.drive_num IS NOT NULL
          AND p.play_type IN ('pass', 'run')
        GROUP BY p.game_id, p.drive_num
    )
    UPDATE drives d
       SET pass_plays = s.pass_plays,
           rush_plays = s.rush_plays
      FROM split s
     WHERE d.game_id = s.game_id AND d.drive_num = s.drive_num
""")


# Fill UNKNOWN drives from their own plays.
#
# CFBD leaves some possessions 'Uncategorized', and a few carry results whose
# reading is genuinely ambiguous from the label alone — 'FG TD' turns out to be a
# fake field goal run in for a score, 'DOWNS TD' varies drive by drive. Once
# college plays carry scoring flags, each of these can be settled against its own
# evidence instead of guessed at from a string.
#
# Deliberately scoped to result = 'UNKNOWN'. Where CFBD stated an outcome it is
# the authority and stays untouched; the derivation's job is to fill silence, not
# to argue. result_raw is preserved either way, so what was filled stays visible.
_RESOLVE_UNKNOWN = text("""
    WITH derived AS (
        SELECT p.game_id, p.drive_num,
               CASE
                   WHEN bool_or(p.interception) THEN 'INT'
                   WHEN bool_or(p.fumble_lost)  THEN 'FUMBLE_LOST'
                   WHEN bool_or(p.touchdown AND p.play_type_raw IN
                                ('Rushing Touchdown', 'Passing Touchdown')) THEN 'TD'
                   WHEN bool_or(p.field_goal_result = 'made')     THEN 'FG_MADE'
                   WHEN bool_or(p.safety)                         THEN 'SAFETY'
                   WHEN bool_or(p.field_goal_result IS NOT NULL)  THEN 'FG_MISS'
                   WHEN bool_or(p.play_type = 'punt')             THEN 'PUNT'
                   ELSE NULL
               END AS result,
               -- A return score on a drive the offence did not finish itself.
               COALESCE(bool_or(p.touchdown AND p.play_type_raw NOT IN
                                ('Rushing Touchdown', 'Passing Touchdown')), FALSE)
                   AS defensive_td
        FROM plays p
        JOIN games g ON g.game_id = p.game_id
        WHERE g.league = 'ncaaf' AND p.drive_num IS NOT NULL
          AND p.play_type_raw IS NOT NULL
        GROUP BY p.game_id, p.drive_num
    )
    UPDATE drives d
       SET result = x.result,
           defensive_td = x.defensive_td,
           points = CASE WHEN x.result = 'TD' THEN 7
                         WHEN x.result = 'FG_MADE' THEN 3 ELSE 0 END
      FROM derived x
     WHERE d.game_id = x.game_id AND d.drive_num = x.drive_num
       AND d.result = 'UNKNOWN' AND x.result IS NOT NULL
""")


async def resolve_unknown() -> int:
    engine = get_engine()
    async with engine.begin() as conn:
        return (await conn.execute(_RESOLVE_UNKNOWN)).rowcount


async def main(seasons: list[int], season_types: list[str]):
    total = 0
    for season in seasons:
        for st in season_types:
            written, skipped = await ingest_season(season, st)
            log.info("%s %s: %d drives written, %d skipped (game not ingested)",
                     season, st, written, skipped)
            total += written

    engine = get_engine()
    async with engine.begin() as conn:
        filled = (await conn.execute(_FILL_SPLIT)).rowcount
        log.info("pass/run split filled from plays for %d drives", filled)
        resolved = (await conn.execute(_RESOLVE_UNKNOWN)).rowcount
        log.info("UNKNOWN drives resolved from play flags: %d", resolved)
        mix = (await conn.execute(text("""
            SELECT d.result, count(*) AS n,
                   count(*) FILTER (WHERE d.defensive_td) AS def_td
            FROM drives d JOIN games g USING (game_id)
            WHERE g.league = 'ncaaf' GROUP BY 1 ORDER BY 2 DESC
        """))).mappings().all()
    grand = sum(r["n"] for r in mix) or 1
    for r in mix:
        log.info("  %-12s %7d  %5.1f%%%s", r["result"], r["n"], 100 * r["n"] / grand,
                 f"   ({r['def_td']} returned for a defensive TD)" if r["def_td"] else "")
    log.info("ncaaf: %d drives", grand)
    return total


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, required=True)
    parser.add_argument("--season-type", nargs="+", default=["regular", "postseason"])
    args = parser.parse_args()
    asyncio.run(main(args.seasons, args.season_type))
