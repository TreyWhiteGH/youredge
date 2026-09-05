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


_INSERT_SNAPSHOT = text("""
    INSERT INTO odds_snapshots
        (market_id, captured_at, outcome, line, price_american, implied_prob,
         is_live, source)
    VALUES (:mid, :at, :outcome, :line, :price, :prob, :live, 'sgo')
    ON CONFLICT DO NOTHING
""")

# Markets are created in bulk and read back in bulk, rather than upserted one at a
# time with RETURNING. Neon is a network hop away: the per-row version issued one
# round trip per market and one per snapshot, and measured against a real slate it
# ingested 2m18s of captures in 7 minutes -- three times slower than the 20-second
# cadence it is supposed to keep up with. The work was never the database's; it was
# 20ms of latency, tens of thousands of times.
#
# Two statements per game instead: insert what is missing, then select the ids back.
_INSERT_MARKETS_BULK = text("""
    INSERT INTO markets (game_id, bookmaker, market_key, player_id, player_name, side_team_id)
    SELECT :gid, :bm, :mk, NULL, :pname, :side
    ON CONFLICT (game_id, bookmaker, market_key, player_name) DO NOTHING
""")

_SELECT_MARKETS = text("""
    SELECT market_id, bookmaker, market_key, player_name
    FROM markets WHERE game_id = :gid
""")

# One prime per game rather than per market. DISTINCT ON still splits by rung, which
# is the part that matters: without the per-(outcome, line) split the first row of a
# ladder is compared against a neighbouring rung and every rung looks like a move.
_PRIME_GAME = text("""
    SELECT DISTINCT ON (s.market_id, s.outcome, s.line)
           s.market_id, s.outcome, s.line, s.price_american
    FROM odds_snapshots s JOIN markets m USING (market_id)
    WHERE m.game_id = :gid
    ORDER BY s.market_id, s.outcome, s.line, s.captured_at DESC
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
        # Resolution and FBS status are per-event facts that do not change between
        # captures, but there are 180 captures an hour of the same slate. Without
        # these, a three-hour catch-up re-resolves the same 117 games 500 times.
        # It matters most in a dry run, where the rollback discards the entity_xwalk
        # rows that would otherwise make the second lookup cheap.
        self._events: dict[tuple[str, str], tuple] = {}
        self._fbs_cache: dict[tuple[str, str], bool] = {}
        # Abbreviations become the stored `outcome` for home/away sides.
        self._abbr: dict[str, str | None] = {}
        # `unresolved` used to be one number covering two very different things, and
        # on a college Saturday the harmless one drowns the other: 28% of live games
        # failed to resolve, all of them D-III and FCS sides that are not in `teams`
        # and never will be. An FBS game failing on a name mismatch would have landed
        # in the same counter and been invisible. Split, so that one of these is
        # expected noise and the other is always worth reading.
        self.stats = {
            "files": 0, "events": 0, "events_live": 0,
            # At least one side is not in `teams` at all. Expected: migration 012
            # records that FCS programs enter our data only as crossover opponents,
            # so a D-III fixture has no rows to match and cannot be classified.
            "skipped_unknown_team": 0,
            # Both sides known, no game row within 36 hours of kickoff. This one is
            # a real fault -- a schedule gap or a bad kickoff -- and should be zero.
            "unresolved_game": 0,
            "skipped_not_fbs": 0, "skipped_not_live": 0, "unmapped_odds": 0,
            "quotes_seen": 0, "quotes_offbook": 0, "rows": 0, "unchanged": 0,
            "market_missing": 0,
        }
        # Games whose markets have been created and whose last prices are loaded.
        # Primed once per process, not once per capture file -- there are 180 files
        # an hour describing the same slate.
        self._primed: set[str] = set()

    async def _fbs(self, conn, home: str, away: str) -> bool:
        """At least one FBS side.

        A crossover against an FCS opponent is a real FBS game and its market is
        worth keeping; two FCS teams is a board we have no context layer for.
        """
        ck = (home, away)
        if ck not in self._fbs_cache:
            row = (await conn.execute(
                text("""SELECT count(*) FROM teams
                        WHERE team_id IN (:h, :a) AND classification = 'fbs'"""),
                {"h": home, "a": away},
            )).scalar()
            self._fbs_cache[ck] = bool(row)
        return self._fbs_cache[ck]

    async def _abbr_of(self, conn, team_id: str) -> str | None:
        if team_id not in self._abbr:
            self._abbr[team_id] = (await conn.execute(
                text("SELECT abbr FROM teams WHERE team_id = :t"), {"t": team_id},
            )).scalar()
        return self._abbr[team_id]

    async def _load_game(self, conn, gid: str, wanted: list[dict]) -> None:
        """Ensure every market this game needs exists, and prime its last prices.

        Three statements for a whole game, whatever its market count: create the
        missing markets, read their ids back, then load the newest stored price per
        rung. The version this replaces did two round trips per market and one per
        snapshot, which is the difference between keeping up with a 20-second
        cadence and falling three times behind it.
        """
        missing = [w for w in wanted
                   if (gid, w["bm"], w["mk"], w["pname"]) not in self._market_ids]
        if not missing and gid in self._primed:
            # Steady state: every market this capture needs is already known and the
            # last prices are in memory. Nothing to ask the database.
            return

        if missing:
            # executemany: one statement, one round trip, N parameter sets.
            await conn.execute(_INSERT_MARKETS_BULK,
                               [{"gid": gid, **w} for w in missing])
            for mid, bm, mk, pname in (
                await conn.execute(_SELECT_MARKETS, {"gid": gid})
            ).all():
                self._market_ids[(gid, bm, mk, pname)] = mid

        if gid not in self._primed:
            # Only on first sight. Afterwards `_last` is authoritative because this
            # process is the only writer of source='sgo' rows, and re-reading it per
            # capture would put the round trips straight back.
            for mid, outcome, line, price in (
                await conn.execute(_PRIME_GAME, {"gid": gid})
            ).all():
                self._last[(mid, outcome, line)] = (price, line)
            self._primed.add(gid)

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

            ck = (league, ev.get("eventID") or "")
            if ck not in self._events:
                self._events[ck] = await resolve_event(conn, league, ev)
            gid, home, away = self._events[ck]
            if not home or not away:
                self.stats["skipped_unknown_team"] += 1
                continue
            # Division is checked before the game lookup, not after. FCS-versus-FCS
            # fixtures resolve both teams -- migration 012 keeps FCS programs as
            # crossover opponents -- and then find no game row, because our schedule
            # does not carry games between two of them. Checking afterwards filed
            # 105 of those under unresolved_game, which is meant to mean "our gap"
            # and is worth nothing if a whole division's fixtures land in it.
            if league == "ncaaf" and not await self._fbs(conn, home, away):
                self.stats["skipped_not_fbs"] += 1
                continue
            if not gid:
                # Both teams are ones we know, so a missing game is our gap rather
                # than SGO covering a division we do not. Logged with names because
                # this is the case someone has to act on.
                teams = ev.get("teams") or {}
                self.stats["unresolved_game"] += 1
                log.warning(
                    "no canonical %s game: %s @ %s (%s)", league,
                    ((teams.get("away") or {}).get("names") or {}).get("long"),
                    ((teams.get("home") or {}).get("names") or {}).get("long"),
                    (ev.get("status") or {}).get("startsAt"),
                )
                continue
            await self._ingest_event(conn, ev, gid, home, away, captured_at, live)

    async def _ingest_event(self, conn, ev, gid, home, away, captured_at, live) -> None:
        habbr = await self._abbr_of(conn, home)
        aabbr = await self._abbr_of(conn, away)
        players = ev.get("players") or {}

        # Walked twice on purpose. The first pass decides which markets this game
        # needs so they can all be created in one statement; the second, below,
        # builds the snapshot rows now that every market id is known. Interleaving
        # them is what forced a round trip per market.
        if not self.dry_run:
            wanted, seen = [], set()
            for odd in (ev.get("odds") or {}).values():
                key = M.market_key(odd)
                if not key:
                    continue
                entity = odd.get("statEntityID")
                pname = (((players.get(entity) or {}).get("name")) or entity) \
                    if M.is_player(entity) else None
                side = {"home": home, "away": away}.get(entity)
                for book in (odd.get("byBookmaker") or {}):
                    if book not in self.books:
                        continue
                    ck = (book, key, pname)
                    if ck in seen:
                        continue
                    seen.add(ck)
                    wanted.append({"bm": book, "mk": key, "pname": pname, "side": side})
            # Recomputed every capture, not once per game. A slate is not a fixed
            # set of markets: books post props and alternate rungs while the game
            # runs, so a game primed at kickoff is missing whatever appeared since.
            # Priming once dropped 4,598 quotes in twelve minutes -- counted as
            # market_missing, and never recovered, because the guard that skipped
            # the reprime is also what kept them missing.
            await self._load_game(conn, gid, wanted)

        pending: list[dict] = []
        for odd in (ev.get("odds") or {}).values():
            key = M.market_key(odd)
            if not key:
                self.stats["unmapped_odds"] += 1
                continue
            outcome = M.outcome_of(odd, habbr, aabbr)
            if not outcome:
                continue

            entity = odd.get("statEntityID")
            # The display name, not SGO's player id. markets is keyed on player_name
            # (024), and odds_poller writes what the book called him -- "Sam Darnold".
            # Writing `SAM_DARNOLD_1_NFL` here would give the same player two market
            # rows, one per feed, and split his line movement down the middle. The
            # event's `players` block carries the name; the id is the fallback for
            # the rare odd whose subject is missing from it.
            player_name = None
            if M.is_player(entity):
                player_name = ((players.get(entity) or {}).get("name")) or entity
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

                mid = self._market_ids.get((gid, book, key, player_name))
                if mid is None:
                    # The market could not be created or read back -- almost always
                    # a book/market pair that appeared inside this same file, after
                    # the first pass built the list. It will exist next capture.
                    self.stats["market_missing"] += 1
                    continue
                ck = (mid, outcome, line)
                if self._last.get(ck, (None, None))[0] == price:
                    self.stats["unchanged"] += 1
                    continue
                pending.append({
                    "mid": mid, "at": captured_at, "outcome": outcome, "line": line,
                    "price": price, "prob": M.implied(price), "live": live,
                })
                self._last[ck] = (price, line)
                self.stats["rows"] += 1

        # One statement for the whole event's changes. This is where the latency
        # went: a slate with 200 moved prices was 200 sequential round trips.
        if pending:
            await conn.execute(_INSERT_SNAPSHOT, pending)


async def run(since: timedelta, books: tuple[str, ...], live_only: bool,
              dry_run: bool) -> dict:
    files = capture_files(datetime.now(timezone.utc) - since)
    ing = Ingestor(books, live_only, dry_run)
    if not files:
        log.info("no capture files in the last %s", since)
        return ing.stats

    engine = get_engine()
    async with engine.connect() as conn:
        for path in files:
            # One transaction per capture file, not one for the whole run. A three-hour
            # catch-up is 500-odd files and tens of thousands of rows; holding that open
            # keeps a single long transaction against a managed Postgres for minutes,
            # and a failure at the end would discard every file that had already parsed
            # cleanly. Per-file means progress is durable and a re-run resumes rather
            # than restarts -- the inserts are ON CONFLICT DO NOTHING, so overlapping a
            # file that already landed costs nothing.
            trans = await conn.begin()
            try:
                await ing.ingest_file(conn, path)
            except Exception:
                await trans.rollback()
                raise
            if dry_run:
                # A dry run still resolves teams and events, and resolution writes
                # entity_xwalk rows as it learns them. Those are harmless and
                # idempotent, but "dry run" has to mean the database is untouched or
                # it is not a rehearsal, so the work is done and then thrown away.
                await trans.rollback()
            else:
                await trans.commit()
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
