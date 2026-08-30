"""Keep the season in progress current, without being told to.

Every other ingest in this package is a backfill: someone names a season, it
runs, it finishes. That is the right shape for history and the wrong shape for a
season being played, and the gap showed up the obvious way — Stanford beat
Hawai'i on a Saturday and the app still called the game scheduled on Sunday,
because nothing had asked the feed since.

Three stages, in dependency order, each of which only does work when the stage
above it produced something:

  1. **Schedules and results**, plus the polls. The same feed carries schedule
     and result, so this is what moves a game to 'final' and gives it a score.
     Rankings ride along here rather than behind the play trigger, because a
     poll moves every Sunday whether or not this season's play-by-play did.
  2. **Play-by-play** for weeks that now hold finished games with no plays. This
     is the stage the season's statistics actually rest on: a game can be final
     and still leave every unit surface empty, which reads on screen as the team
     having played nobody.
  2b. **Drives**, which are not derivable from the same rows in both leagues.
     NFL drives are computed from play flags; CFBD's play rows carry neither a
     touchdown flag nor a field-goal result, so college drives come from CFBD's
     own /drives endpoint. Both are refreshed, because the script labels are
     counted off drives rather than plays.
  3. **The derived layers** — game features first, because the script labels are
     defined against the closing line and a game with no feature row can only
     ever receive the handful of labels that need nothing but the score; then
     game state, labels, the leg ledger, the pair surface and diagnoses. Rebuilt
     only when new rows landed: they are full rebuilds over all history, so
     running them on a timer rather than on a trigger would burn most of an hour
     recomputing what has not changed.

Usage:
    docker compose run --rm ingest python -m youredge.ingest.catchup
    docker compose run --rm ingest python -m youredge.ingest.catchup --loop
"""

import argparse
import asyncio
import logging

from sqlalchemy import text

from youredge.db import get_engine
from youredge.ingest import cfbd_drives, cfbd_pbp, cfbd_rankings, nfl_pbp, schedules
from youredge.legs import ledger, pairs
from youredge.modeling import drives as nfl_drives
from youredge.modeling import features
from youredge.scripts import diagnose, game_state, label

log = logging.getLogger(__name__)

# Matches the default in modeling.features. A closing line can arrive long after
# the game — a book's history backfill, a re-resolved event — so the rebuild
# covers every season rather than only the live one.
FEATURE_SEASONS = list(range(2016, 2027))

# A finished game with no plays is the definition of behind. Asking per week
# rather than per game is deliberate: both play-by-play feeds are fetched a week
# at a time, so the week is the smallest unit that can actually be repaired.
_STALE_WEEKS = text("""
    SELECT DISTINCT g.week, g.season_type
    FROM games g
    WHERE g.league = :league AND g.season = :season AND g.status = 'final'
      AND g.week IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM plays p WHERE p.game_id = g.game_id)
    ORDER BY g.season_type, g.week
""")


# Drives get their own test rather than riding on the play one. They are a
# separate fetch for college and a separate derivation for the NFL, so either can
# fail or be skipped while plays are perfectly current — and a trigger that only
# watched plays would then report everything up to date forever, which is the
# same class of silence this whole module exists to remove.
_STALE_DRIVES = text("""
    SELECT DISTINCT g.season_type
    FROM games g
    WHERE g.league = :league AND g.season = :season AND g.status = 'final'
      AND EXISTS (SELECT 1 FROM plays p WHERE p.game_id = g.game_id)
      AND NOT EXISTS (SELECT 1 FROM drives d WHERE d.game_id = g.game_id)
""")


async def stale_weeks(conn, league: str, season: int) -> list[tuple[int, str]]:
    rows = (await conn.execute(_STALE_WEEKS, {"league": league, "season": season})).all()
    return [(int(w), st) for w, st in rows]


async def stale_drives(conn, league: str, season: int) -> set[str]:
    rows = (await conn.execute(_STALE_DRIVES, {"league": league, "season": season})).all()
    return {st for (st,) in rows}


async def catch_up_plays(season: int) -> int:
    """Ingest play-by-play for every week holding an unbacked finished game."""
    engine = get_engine()
    async with engine.connect() as conn:
        ncaaf = await stale_weeks(conn, "ncaaf", season)
        nfl = await stale_weeks(conn, "nfl", season)

    if not ncaaf and not nfl:
        log.info("play-by-play is current for %s", season)
        return 0

    touched = 0
    for week, season_type in ncaaf:
        log.info("ncaaf %s week %s (%s): fetching plays", season, week, season_type)
        await cfbd_pbp.ingest_week(season, week, season_type=season_type)
        touched += 1

    if nfl:
        # nflverse ships a season of play-by-play as one file, so there is no
        # per-week fetch to make; the weeks are only how we noticed.
        log.info("nfl %s: %d week(s) behind, refreshing the season", season, len(nfl))
        await nfl_pbp.main([season])
        touched += len(nfl)
    return touched


async def catch_up_drives(season: int) -> bool:
    """Refresh drives for whichever league is behind, by the route that works for it."""
    engine = get_engine()
    async with engine.connect() as conn:
        ncaaf = await stale_drives(conn, "ncaaf", season)
        nfl = await stale_drives(conn, "nfl", season)
    if ncaaf:
        log.info("ncaaf %s: drives behind for %s", season, ", ".join(sorted(ncaaf)))
        await cfbd_drives.main([season], sorted(ncaaf))
    if nfl:
        log.info("nfl %s: drives behind, re-deriving from play flags", season)
        await nfl_drives.main(["nfl"])
    return bool(ncaaf or nfl)


async def rebuild_derived() -> None:
    """Recompute everything counted off plays and drives. Order matters.

    Features lead, because they are where a game's closing spread and total come
    from, and three of the script labels are defined relative to those numbers.
    Labelling before them is not an error that shows up as an error: the game
    simply comes back with fewer tags than it should have, and nothing says so.
    """
    for lg in ("nfl", "ncaaf"):
        await features.build(lg, FEATURE_SEASONS)
    await game_state.build(["nfl", "ncaaf"])
    await label.label(["nfl", "ncaaf"], True)
    await ledger.build(["nfl", "ncaaf"])
    await pairs.build()
    await diagnose.build(["nfl", "ncaaf"])


async def cycle(season: int, *, aliases: bool, force: bool = False) -> None:
    await schedules.refresh(season, aliases=aliases)
    # A failed poll fetch must not stop the results chain behind it. Rankings are
    # a garnish on the slate; scores are not.
    try:
        log.info("rankings: %s", await cfbd_rankings.ingest([season]))
    except Exception:
        log.exception("rankings refresh failed (continuing)")
    # Drives are checked after plays because new plays create the very gap the
    # drive test looks for, and checked unconditionally because an old gap has
    # to be repairable on a later pass than the one that opened it.
    fresh = await catch_up_plays(season)
    fresh = await catch_up_drives(season) or fresh
    if fresh or force:
        log.info("new rows landed — rebuilding the derived layers")
        await rebuild_derived()


async def main(season: int | None, loop: bool, interval: int, force: bool = False):
    season = season or schedules.current_season()
    first = True
    while True:
        try:
            # Force applies to the first cycle only. A loop that rebuilt every
            # half hour whether or not anything changed would be the timer this
            # module was written to avoid.
            await cycle(season, aliases=first, force=force and first)
        except Exception:
            # A loop that dies on one bad response stops updating anything, and
            # the failure mode of that is silence rather than an error page.
            log.exception("catch-up cycle failed")
            if not loop:
                raise
        first = False
        if not loop:
            break
        await asyncio.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, help="default: the season in progress")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=1800,
                    help="seconds between cycles in --loop mode")
    ap.add_argument("--rebuild", action="store_true",
                    help="rebuild the derived layers even if nothing new landed")
    args = ap.parse_args()
    asyncio.run(main(args.season, args.loop, args.interval, args.rebuild))
