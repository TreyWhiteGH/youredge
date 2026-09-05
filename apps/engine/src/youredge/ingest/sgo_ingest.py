"""Raw SGO captures -> markets / odds_snapshots.

The half of live capture that is allowed to be opinionated. sgo_capture.py writes
everything and decides nothing, because bytes not written are gone; this reads those
files and decides what belongs in Postgres, because a row written wrongly is worse
than one not written at all. Rerunning it against the same files is the intended way
to change your mind.

**Why this rations, and capture does not.** A college slate is 11,440 odds across 58
bookmakers -- 61,846 quotes -- and at a 20-second cadence that is roughly 11 million
observations an hour. Stored as samples it buries a managed Postgres inside a day, and
almost all of it is the same number written again: books repost every four to twelve
minutes, so at 20s the great majority of polls see no change at all. So:

  * **Changes, not samples.** A quote is written only when its price or its line
    differs from the last one stored for that market, outcome and rung. The series
    that comes back out is identical, because a price that did not change is fully
    described by the row that said so first.
  * **Live games only, by default.** Pregame is odds_poller.py's job and it already
    does it against a metered API. Re-recording it here would double-count the
    pregame surface and spend the row budget where nothing is moving.
  * **A configured book list.** All 58 are captured; the ones with a de-vig anchor or
    a bet behind them are what get stored. The rest stay in the files.

Usage:
    python -m youredge.ingest.sgo_ingest --dry-run          # parse, decide, write nothing
    python -m youredge.ingest.sgo_ingest --since 30m
    python -m youredge.ingest.sgo_ingest --loop
"""

import argparse
import asyncio
import glob
import gzip
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

from youredge.db import get_engine
from youredge.ingest import sgo_map as M
from youredge.ingest.resolve import normalize_name

log = logging.getLogger(__name__)

CAPTURE_ROOT = Path(os.environ.get("SGO_CAPTURE_DIR", "/var/lib/youredge/sgo_raw"))
LEAGUE_OF = {"ncaaf": "ncaaf", "nfl": "nfl"}

# Books worth a row. Pinnacle is the de-vig anchor (pricing/fair_value.ANCHOR_BOOKS)
# and the rest are where a bet actually gets placed. SGO carries 58, including one
# literally named "unknown"; capture keeps them all and this list is what reaches
# Postgres. Widening it is a config change and a re-run, not a lost opportunity.
DEFAULT_BOOKS = (
    "pinnacle", "draftkings", "fanduel", "betmgm", "caesars",
    "espnbet", "bet365", "hardrockbet", "betrivers", "fanatics",
)

# A capture every 20s means consecutive files are nearly identical. Walking all of
# them costs time and buys nothing, so the default reach-back is short and the loop
# keeps up rather than catching up.
DEFAULT_SINCE = timedelta(minutes=30)

_DURATION = re.compile(r"^(\d+)([smhd])$")
_UNIT = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def parse_since(s: str) -> timedelta:
    m = _DURATION.match(s.strip())
    if not m:
        raise argparse.ArgumentTypeError(f"expected e.g. 30m, 2h, 1d -- got {s!r}")
    return timedelta(**{_UNIT[m.group(2)]: int(m.group(1))})


def capture_files(since: datetime) -> list[Path]:
    """Capture files newer than `since`, oldest first, across both leagues.

    Ordered by the epoch in the filename rather than mtime: these get copied to and
    from backups, and mtime does not survive that while the name does.
    """
    out: list[tuple[int, Path]] = []
    for path in CAPTURE_ROOT.glob("*/*.json.gz"):
        stem = path.name.removesuffix(".json.gz")
        league, _, ts = stem.rpartition("_")
        if league not in LEAGUE_OF or not ts.isdigit():
            continue
        if datetime.fromtimestamp(int(ts), timezone.utc) >= since:
            out.append((int(ts), path))
    return [p for _, p in sorted(out)]


_XWALK_GET = text("""
    SELECT canonical_id FROM entity_xwalk
    WHERE entity_type = :etype AND source = 'sgo' AND source_id = :sid
""")
_XWALK_PUT = text("""
    INSERT INTO entity_xwalk (entity_type, canonical_id, source, source_id)
    VALUES (:etype, :cid, 'sgo', :sid)
    ON CONFLICT (entity_type, source, source_id) DO NOTHING
""")


async def resolve_team(conn, league: str, team: dict) -> str | None:
    """SGO team -> canonical team_id, cached in entity_xwalk under source='sgo'.

    `teamID` is the key rather than the display name: SGO writes `ILLINOIS_NCAAF`,
    which is stable, while `names.long` is "Illinois" on one event and absent on
    another -- `names.short` is empty on precisely the games that carry odds. The
    name is still used for the first resolution, because the alias crosswalk is
    built from names; once that succeeds the id is what gets remembered.
    """
    sgo_id = team.get("teamID")
    if not sgo_id:
        return None
    hit = (await conn.execute(_XWALK_GET, {"etype": "team", "sid": sgo_id})).first()
    if hit:
        return hit[0]

    name = (team.get("names") or {}).get("long")
    if not name:
        return None
    row = (await conn.execute(
        text("SELECT team_id FROM teams WHERE league = :lg AND name = :n"),
        {"lg": league, "n": name},
    )).first()
    if not row:
        # Same alias table the Odds API path uses. SGO writes bare school names
        # ("Illinois", "UAB") where The Odds API writes school+mascot, so the
        # normalised alias is the only thing the two spellings share.
        row = (await conn.execute(
            text("""
                SELECT canonical_id FROM entity_xwalk
                WHERE entity_type = 'team' AND source = 'cfbd_alias' AND source_id = :n
            """),
            {"n": normalize_name(name)},
        )).first()
    if not row:
        return None

    await conn.execute(_XWALK_PUT, {"etype": "team", "cid": row[0], "sid": sgo_id})
    return row[0]


async def resolve_event(conn, league: str, ev: dict) -> tuple[str | None, str | None, str | None]:
    """SGO event -> (game_id, home_team_id, away_team_id).

    A miss returns Nones and the caller counts it. Unlike odds_poller, no stub game
    is created: that path exists there so a metered poll is never wasted, and here
    the capture file is on disk and can simply be re-ingested once schedules land.
    """
    eid = ev.get("eventID")
    teams = ev.get("teams") or {}
    home = await resolve_team(conn, league, teams.get("home") or {})
    away = await resolve_team(conn, league, teams.get("away") or {})
    if not eid or not home or not away:
        return None, home, away

    hit = (await conn.execute(_XWALK_GET, {"etype": "game", "sid": eid})).first()
    if hit:
        return hit[0], home, away

    starts = (ev.get("status") or {}).get("startsAt")
    if not starts:
        return None, home, away
    kickoff = datetime.fromisoformat(starts.replace("Z", "+00:00"))
    row = (await conn.execute(
        text("""
            SELECT game_id FROM games
            WHERE league = :lg AND home_team_id = :h AND away_team_id = :a
              AND game_id NOT LIKE '%:oddsapi:%'
              AND kickoff BETWEEN CAST(:t AS timestamptz) - interval '36 hours'
                              AND CAST(:t AS timestamptz) + interval '36 hours'
            ORDER BY abs(extract(epoch FROM kickoff - CAST(:t AS timestamptz))) LIMIT 1
        """),
        {"lg": league, "h": home, "a": away, "t": kickoff},
    )).first()
    if not row:
        return None, home, away
    await conn.execute(_XWALK_PUT, {"etype": "game", "cid": row[0], "sid": eid})
    return row[0], home, away


_UPSERT_MARKET = text("""
    INSERT INTO markets (game_id, bookmaker, market_key, player_id, player_name, side_team_id)
    VALUES (:gid, :bm, :mk, NULL, :pname, :side)
    ON CONFLICT (game_id, bookmaker, market_key, player_id, player_name) DO UPDATE
      SET side_team_id = COALESCE(EXCLUDED.side_team_id, markets.side_team_id)
    RETURNING market_id
""")

_INSERT_SNAPSHOT = text("""
    INSERT INTO odds_snapshots
        (market_id, captured_at, outcome, line, price_american, implied_prob,
         is_live, source)
    VALUES (:mid, :at, :outcome, :line, :price, :prob, :live, 'sgo')
    ON CONFLICT DO NOTHING
""")


def in_play(ev: dict, now: datetime) -> bool:
    """Is this game being played right now?

    Kickoff-passed-and-not-finalized, deliberately not SGO's own `live` flag, which
    still read false on games four minutes underway. Being wrong in the generous
    direction is the safe error here: it stores a few pregame rows, where trusting
    the flag would miss the opening minutes of every game.
    """
    s = ev.get("status") or {}
    starts = s.get("startsAt")
    if not starts or s.get("finalized") or s.get("cancelled"):
        return False
    return datetime.fromisoformat(starts.replace("Z", "+00:00")) <= now


class Ingestor:
    """Holds the last price seen per rung, so change detection is not a query.

    The cache is what makes this affordable. Asking Postgres "what did this outcome
    last cost" once per quote would be 61,846 round trips per file; asking once per
    market when it is first seen, and remembering, is a few thousand for a whole
    slate. It is a cache of our own writes, so it cannot go stale against anything
    but another writer, and there is only ever one of these running.
    """

    def __init__(self, books: tuple[str, ...], live_only: bool, dry_run: bool):
        self.books = set(books)
        self.live_only = live_only
        self.dry_run = dry_run
        self._market_ids: dict[tuple, int] = {}
        self._last: dict[tuple, tuple[int | None, float | None]] = {}
        self.stats = {
            "files": 0, "events": 0, "events_live": 0, "unresolved": 0,
            "skipped_not_fbs": 0, "skipped_not_live": 0, "unmapped_odds": 0,
            "quotes_seen": 0, "quotes_offbook": 0, "rows": 0, "unchanged": 0,
        }

    async def _fbs(self, conn, home: str, away: str) -> bool:
        """At least one FBS side, which is the rule the user asked for.

        A crossover against an FCS opponent is a real FBS game and its market is
        worth keeping; two FCS teams is a board we have no context layer for.
        """
        row = (await conn.execute(
            text("""SELECT count(*) FROM teams
                    WHERE team_id IN (:h, :a) AND classification = 'fbs'"""),
            {"h": home, "a": away},
        )).scalar()
        return bool(row)

    async def _market_id(self, conn, gid, book, key, pname, side) -> int:
        ck = (gid, book, key, pname)
        if ck not in self._market_ids:
            self._market_ids[ck] = (await conn.execute(_UPSERT_MARKET, {
                "gid": gid, "bm": book, "mk": key, "pname": pname, "side": side,
            })).scalar_one()
        return self._market_ids[ck]

    async def _prime(self, conn, market_id: int) -> None:
        """Load the newest stored price per (outcome, line) for one market.

        DISTINCT ON is the whole point: a market has many rungs and each needs its
        own baseline, and without the per-rung split the first row for a ladder
        would be compared against a neighbouring rung's price and look like a move.
        """
        rows = (await conn.execute(
            text("""
                SELECT DISTINCT ON (outcome, line) outcome, line, price_american
                FROM odds_snapshots WHERE market_id = :mid
                ORDER BY outcome, line, captured_at DESC
            """),
            {"mid": market_id},
        )).all()
        for outcome, line, price in rows:
            self._last[(market_id, outcome, line)] = (price, line)

    async def ingest_file(self, conn, path: Path) -> None:
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                env = json.load(fh)
        except (OSError, EOFError, json.JSONDecodeError) as e:
            log.warning("unreadable capture %s: %s", path.name, e)
            return

        league = LEAGUE_OF.get((env.get("league") or "").lower())
        captured_at = datetime.fromisoformat(env["captured_at"])
        if not league:
            return
        self.stats["files"] += 1

        for ev in ((env.get("payload") or {}).get("data") or []):
            self.stats["events"] += 1
            live = in_play(ev, captured_at)
            if self.live_only and not live:
                self.stats["skipped_not_live"] += 1
                continue
            self.stats["events_live"] += 1

            gid, home, away = await resolve_event(conn, league, ev)
            if not gid:
                self.stats["unresolved"] += 1
                continue
            if league == "ncaaf" and not await self._fbs(conn, home, away):
                self.stats["skipped_not_fbs"] += 1
                continue
            await self._ingest_event(conn, ev, gid, home, away, captured_at, live)

    async def _ingest_event(self, conn, ev, gid, home, away, captured_at, live) -> None:
        habbr = (await conn.execute(
            text("SELECT abbr FROM teams WHERE team_id = :t"), {"t": home})).scalar()
        aabbr = (await conn.execute(
            text("SELECT abbr FROM teams WHERE team_id = :t"), {"t": away})).scalar()

        for odd in (ev.get("odds") or {}).values():
            key = M.market_key(odd)
            if not key:
                self.stats["unmapped_odds"] += 1
                continue
            outcome = M.outcome_of(odd, habbr, aabbr)
            if not outcome:
                continue

            entity = odd.get("statEntityID")
            player_name = entity if M.is_player(entity) else None
            side = {"home": home, "away": away}.get(entity)

            for book, quote in (odd.get("byBookmaker") or {}).items():
                self.stats["quotes_seen"] += 1
                if book not in self.books:
                    self.stats["quotes_offbook"] += 1
                    continue
                price = M.american(quote.get("odds"))
                if price is None:
                    continue
                line = M.book_line(odd, quote)

                if self.dry_run:
                    # No market_id exists to key the cache on, so a dry run counts
                    # every eligible quote as a row. It is an upper bound on what a
                    # real run would write, not a prediction of it.
                    self.stats["rows"] += 1
                    continue

                mid = await self._market_id(conn, gid, book, key, player_name, side)
                ck = (mid, outcome, line)
                if ck not in self._last:
                    await self._prime(conn, mid)
                if self._last.get(ck, (None, None))[0] == price:
                    self.stats["unchanged"] += 1
                    continue
                await conn.execute(_INSERT_SNAPSHOT, {
                    "mid": mid, "at": captured_at, "outcome": outcome, "line": line,
                    "price": price, "prob": M.implied(price), "live": live,
                })
                self._last[ck] = (price, line)
                self.stats["rows"] += 1


async def run(since: timedelta, books: tuple[str, ...], live_only: bool,
              dry_run: bool) -> dict:
    files = capture_files(datetime.now(timezone.utc) - since)
    ing = Ingestor(books, live_only, dry_run)
    if not files:
        log.info("no capture files in the last %s", since)
        return ing.stats

    engine = get_engine()
    async with engine.begin() as conn:
        for path in files:
            await ing.ingest_file(conn, path)
    return ing.stats


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--since", type=parse_since, default=DEFAULT_SINCE)
    p.add_argument("--books", default=",".join(DEFAULT_BOOKS))
    p.add_argument("--all-games", action="store_true",
                   help="ingest pregame too (default: in-progress only)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--loop", action="store_true")
    p.add_argument("--interval", type=float, default=60.0)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    books = tuple(b.strip() for b in args.books.split(",") if b.strip())

    async def once():
        stats = await run(args.since, books, not args.all_games, args.dry_run)
        log.info("%s%s", "DRY RUN " if args.dry_run else "",
                 "  ".join(f"{k}={v}" for k, v in stats.items()))

    async def loop():
        while True:
            await once()
            await asyncio.sleep(args.interval)

    asyncio.run(loop() if args.loop else once())


if __name__ == "__main__":
    main()
