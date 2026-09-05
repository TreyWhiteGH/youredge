"""Raw SportsGameOdds slate capture — write now, parse later.

In-game line movement is the one thing in this system that cannot be bought back.
SGO's event payload carries three price points per outcome (`openFairOdds`,
`fairOdds`, `closeFairOdds`) and nothing between them: `includeOddsHistory=true` is
silently ignored, returning a byte-identical body. So the *path* a line took during
a game exists only if we were watching when it moved.

This module does exactly one thing: fetch the slate and write it to disk, gzipped.
It does not touch Postgres, does not resolve teams, does not de-vig, and imports
nothing outside the standard library. That is deliberate -- capture has to survive a
schema it does not know about yet, and the way to guarantee that is to give it no
opinions. Mapping these files into `markets`/`odds_snapshots` is a separate job that
can be rewritten as many times as it takes, because the bytes are already safe.

Cost, measured against a live Saturday rather than assumed: one call returns the
whole slate -- 85 NCAAF events, 8,059 odds objects, 10.5 MB -- and bills **85
entities, one per event**, not one per odd. At a 40-second cadence that is ~7,650
entities/hour against a 250,000/hour Pro cap, so quota is not the constraint here.
Bandwidth is: ~11 GB/day raw, which gzip takes to roughly a tenth of that.

Usage:
    python -m youredge.ingest.sgo_capture                 # loop, both leagues
    python -m youredge.ingest.sgo_capture --once
    python -m youredge.ingest.sgo_capture --interval 40 --league NCAAF
"""

import argparse
import gzip
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("sgo_capture")

BASE = "https://api.sportsgameodds.com/v2"
OUT_ROOT = Path(os.environ.get("SGO_CAPTURE_DIR", "/var/lib/youredge/sgo_raw"))

# SGO's own league ids, which are not ours. The translation to `nfl:`/`ncaaf:`
# happens in the ingest job, not here -- see the module docstring.
LEAGUES = ("NCAAF", "NFL")

# Slate window. Games are keyed by kickoff, and a Saturday slate spills past
# midnight UTC constantly, so a day either side is the honest bound.
WINDOW_BEFORE = timedelta(days=1)
WINDOW_AFTER = timedelta(days=2)

# The whole point is the in-game path, so this wants to be short. 40s at 85 events
# is 3% of the hourly entity budget; the reason not to go lower is the 10 MB body,
# not the quota.
DEFAULT_INTERVAL = 40.0

# SGO caps a page at 100 events no matter what `limit` asks for, and says so only by
# returning a `nextCursor`. Asking for 250 does not fail -- it silently hands back
# 100, which on a college Saturday is most of the slate and looks entirely plausible
# in a log line. The cap is the reason this paginates rather than trusting one call.
PAGE_LIMIT = 100

# A cursor loop with no bound is one malformed response away from spinning until the
# disk fills. Nothing in football needs 20 pages; hitting this means something is
# wrong upstream and the right move is to log it, not to keep asking.
MAX_PAGES = 20


def _api_key() -> str:
    """Key from the environment, falling back to .env.prod for a bare shell run.

    Deliberately never logged, and never placed in a query string: SGO takes it as a
    header, and a URL carrying a secret ends up in access logs and exception traces
    that nobody thinks of as sensitive until they are.
    """
    key = os.environ.get("SGO_API_KEY", "").strip()
    if key:
        return key
    for candidate in (Path("/root/youredge/.env.prod"), Path(".env.prod")):
        if not candidate.exists():
            continue
        for line in candidate.read_text().splitlines():
            if line.startswith("SGO_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("SGO_API_KEY not set and not found in .env.prod")


# SGO sits behind Cloudflare, which 403s urllib's default `Python-urllib/3.12`
# agent before the request reaches the API -- the key is never consulted, so the
# failure looks like an auth problem and is not one. Any other agent passes;
# curl's default and this one both return 200. Note this is the opposite of the
# ESPN rule in api/routes/live.py, where a *browser* string is what gets refused.
# Neither WAF wants to be lied to; they just disagree about what a lie looks like.
USER_AGENT = "youredge/1.0"


def _get(path: str, params: dict, key: str, timeout: float = 60.0) -> dict:
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url, headers={"X-Api-Key": key, "User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_slate(league: str, key: str, now: datetime) -> dict:
    """Every event in the window, following `nextCursor` until the slate is exhausted.

    Returns a payload shaped like a single response -- `data` holding every event
    across all pages -- plus `pages`, so the capture file records how many calls it
    took. A slate that suddenly needs an extra page is worth being able to see after
    the fact.
    """
    params = {
        "leagueID": league,
        "startsAfter": (now - WINDOW_BEFORE).date().isoformat(),
        "startsBefore": (now + WINDOW_AFTER).date().isoformat(),
        "limit": PAGE_LIMIT,
    }
    events: list[dict] = []
    cursor: str | None = None
    pages = 0

    while pages < MAX_PAGES:
        page = _get("events/", {**params, **({"cursor": cursor} if cursor else {})}, key)
        pages += 1
        if not page.get("success"):
            # Hand the failure back whole rather than returning a short slate that
            # looks complete. The caller logs it and skips the write.
            return page
        events.extend(page.get("data") or [])
        cursor = page.get("nextCursor")
        if not cursor:
            break
    else:
        log.warning("%s: stopped at the %d-page cap with a cursor still open",
                    league, MAX_PAGES)

    return {"success": True, "data": events, "pages": pages}


def summarize(payload: dict) -> dict:
    """Cheap counts for the log line, so a bad capture is visible without opening it.

    `live` is counted from each event's own status rather than inferred from the
    clock: a delayed kickoff is common on a college Saturday and would make any
    time-based guess wrong in exactly the window that matters most.
    """
    events = payload.get("data") or []
    live = sum(1 for e in events if (e.get("status") or {}).get("live"))
    started = sum(1 for e in events if (e.get("status") or {}).get("started"))
    odds = sum(len(e.get("odds") or {}) for e in events)
    return {"events": len(events), "live": live, "started": started, "odds": odds}


def write_capture(league: str, payload: dict, captured_at: datetime) -> Path:
    """One file per league per poll, gzipped, named by UTC epoch seconds.

    Partitioned by date so a day can be moved off the box or replayed on its own.
    Written to a .part file and renamed, because the ingest job will eventually walk
    this directory while the poller is still writing to it, and a half-written 10 MB
    body that looks complete is worse than one that is obviously missing.
    """
    day_dir = OUT_ROOT / captured_at.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{league.lower()}_{int(captured_at.timestamp())}"
    final = day_dir / f"{stem}.json.gz"
    partial = day_dir / f"{stem}.json.gz.part"

    # captured_at is recorded inside the file as well as in its name. The name is a
    # convenience; the envelope is what the ingest job trusts, since files get
    # copied, renamed and re-sorted and a timestamp in a filename is a guess.
    envelope = {
        "captured_at": captured_at.isoformat(),
        "league": league,
        "source": "sportsgameodds/v2/events",
        "payload": payload,
    }
    with gzip.open(partial, "wt", encoding="utf-8", compresslevel=6) as fh:
        json.dump(envelope, fh, separators=(",", ":"))
    partial.rename(final)
    return final


def capture_once(key: str, leagues: tuple[str, ...]) -> None:
    for league in leagues:
        now = datetime.now(timezone.utc)
        try:
            payload = fetch_slate(league, key, now)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            # A missed poll is a gap in a series; a dead poller is the loss of the
            # whole rest of the slate. Never let one league's failure end the run.
            log.warning("%s: fetch failed: %s", league, e)
            continue
        except json.JSONDecodeError as e:
            log.warning("%s: unparseable body: %s", league, e)
            continue

        if not payload.get("success"):
            log.warning("%s: api reported failure: %s", league, str(payload)[:200])
            continue

        s = summarize(payload)
        path = write_capture(league, payload, now)
        log.info("%s: %d events (%d live, %d started), %d odds, %d page(s) -> %s (%.1f MB)",
                 league, s["events"], s["live"], s["started"], s["odds"],
                 payload.get("pages", 1), path.name, path.stat().st_size / 1e6)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                        help=f"seconds between polls (default {DEFAULT_INTERVAL:g})")
    parser.add_argument("--league", action="append", choices=LEAGUES,
                        help="capture one league only (repeatable); default all")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    key = _api_key()
    leagues = tuple(args.league or LEAGUES)
    log.info("capturing %s every %.0fs into %s", ",".join(leagues), args.interval, OUT_ROOT)

    while True:
        started = time.monotonic()
        capture_once(key, leagues)
        if args.once:
            return
        # Sleep the remainder of the interval rather than the whole of it, so a slow
        # 10 MB fetch does not quietly stretch a 40s cadence into a 70s one.
        time.sleep(max(1.0, args.interval - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
