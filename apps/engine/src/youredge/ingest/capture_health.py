"""Is the live capture actually capturing? Read the files and decide.

Every way this breaks breaks quietly. The trial key expires and SGO answers with an
empty slate; Cloudflare starts refusing the agent and every fetch 403s; the loop
wedges on a slow 10 MB body and writes nothing while the process still looks alive.
None of those raise, none of them stop the container, and all of them cost the rest
of a slate before anyone opens the log.

So this checks the output rather than the process. A poller that is running is not
the claim worth making -- the claim worth making is that prices moved and the clock
advanced since the last time we looked.

The distinction that keeps this usable: **quiet is not the same as broken.** At 3am
with nothing being played, zero movement is the correct answer, and a check that
pages for it gets muted before Saturday. Every liveness assertion here is therefore
conditioned on ESPN reporting a game actually in progress, and ESPN is used for that
because SGO's own status block is late -- it reported `started: false` on games four
minutes past kickoff.

Usage:
    python -m youredge.ingest.capture_health              # human-readable, exits 0/1
    python -m youredge.ingest.capture_health --json
"""

import argparse
import glob
import gzip
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT_ROOT = Path(os.environ.get("SGO_CAPTURE_DIR", "/var/lib/youredge/sgo_raw"))
LEAGUES = ("ncaaf", "nfl")

# Capture runs at 40s. Two missed ticks is noise -- a slow upstream, a rebuild -- and
# five minutes is not: that is a dead loop, and on a Saturday it is a real hole.
STALE_WARN = timedelta(seconds=150)
STALE_FAIL = timedelta(minutes=5)

# Movement is bursty. One 40s tick can legitimately show nothing on a quiet drive, so
# liveness is judged across a window wide enough that silence means something.
MOVEMENT_WINDOW = timedelta(minutes=5)

# Below this the disk is not yet a problem but is on its way to one. A slate costs
# about 1.4 GB, so a season of them is real.
DISK_WARN_GB = 20.0

OK, WARN, FAIL = "ok", "warn", "fail"
_RANK = {OK: 0, WARN: 1, FAIL: 2}


def _captures(league: str, since: datetime) -> list[Path]:
    """Capture files for a league newer than `since`, oldest first.

    Files are named by epoch seconds, so the name is enough to filter on and there is
    no need to open and parse a hundred 1.4 MB bodies to find the recent ones.
    """
    out = []
    for day in sorted(OUT_ROOT.glob("*")):
        if not day.is_dir():
            continue
        for p in day.glob(f"{league}_*.json.gz"):
            try:
                ts = int(p.stem.split("_")[-1].removesuffix(".json"))
            except ValueError:
                continue
            if datetime.fromtimestamp(ts, timezone.utc) >= since:
                out.append((ts, p))
    return [p for _, p in sorted(out)]


def _load(path: Path) -> dict | None:
    """Read one capture, tolerating a file the writer is still working on.

    Captures land via a .part rename so a torn read should be impossible, but a
    truncated file from a killed process is not, and a health check that crashes on
    bad input is worse than no health check.
    """
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, EOFError, json.JSONDecodeError):
        return None


def _in_progress(envelope: dict) -> set[str]:
    """ESPN event ids currently being played, per the scoreboard in this capture."""
    state = envelope.get("state") or {}
    return {
        e["id"] for e in (state.get("events") or [])
        if ((e.get("status") or {}).get("type") or {}).get("state") == "in" and e.get("id")
    }


def _sgo_in_play(envelope: dict) -> set[str]:
    """SGO event ids past kickoff and not yet finalized.

    The movement check cannot reuse the ESPN set: those are ESPN event ids and the
    prices are keyed by SGO's, two id spaces that share no values, so intersecting
    them silently matches nothing and reports "no outcomes to compare" while the
    board is moving underneath. api/routes/live.py carries a crosswalk for exactly
    this, and a health check has no business depending on one -- each feed is judged
    against its own ids instead.

    Kickoff-and-not-final rather than SGO's `live` flag, which lags several minutes.
    """
    out = set()
    for ev in ((envelope.get("payload") or {}).get("data") or []):
        s = ev.get("status") or {}
        starts, eid = s.get("startsAt"), ev.get("eventID")
        if not starts or not eid or s.get("finalized") or s.get("cancelled"):
            continue
        if datetime.fromisoformat(starts.replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            out.add(eid)
    return out


def _clocks(envelope: dict) -> dict[str, str]:
    state = envelope.get("state") or {}
    return {
        e["id"]: (e.get("status") or {}).get("displayClock") or ""
        for e in (state.get("events") or []) if e.get("id")
    }


def _prices(envelope: dict) -> dict[tuple[str, str], str]:
    """(eventID, oddID) -> book price, for every outcome in the capture."""
    out = {}
    for ev in ((envelope.get("payload") or {}).get("data") or []):
        eid = ev.get("eventID")
        for oid, odd in (ev.get("odds") or {}).items():
            out[(eid, oid)] = odd.get("bookOdds")
    return out


def check_league(league: str, now: datetime) -> dict:
    """One league's verdict, with the numbers behind it."""
    checks: list[dict] = []

    def add(name, status, detail):
        checks.append({"check": name, "status": status, "detail": detail})

    recent = _captures(league, now - MOVEMENT_WINDOW * 2)
    if not recent:
        add("freshness", FAIL, f"no {league} captures in the last "
                               f"{int(MOVEMENT_WINDOW.total_seconds() * 2 // 60)} minutes")
        return {"league": league, "status": FAIL, "checks": checks}

    newest = _load(recent[-1])
    if newest is None:
        add("readable", FAIL, f"newest capture {recent[-1].name} is unreadable")
        return {"league": league, "status": FAIL, "checks": checks}

    # --- freshness -----------------------------------------------------------
    age = now - datetime.fromisoformat(newest["captured_at"])
    status = FAIL if age > STALE_FAIL else WARN if age > STALE_WARN else OK
    add("freshness", status, f"newest capture is {age.total_seconds():.0f}s old")

    # --- both halves present -------------------------------------------------
    n_events = len((newest.get("payload") or {}).get("data") or [])
    n_odds = sum(len(e.get("odds") or {})
                 for e in ((newest.get("payload") or {}).get("data") or []))
    has_state = newest.get("state") is not None
    add("scoreboard", OK if has_state else FAIL,
        "present" if has_state else "ESPN state missing from newest capture")

    live_ids = _in_progress(newest) if has_state else set()
    add("slate", OK if n_events or not live_ids else FAIL,
        f"{n_events} events, {n_odds} odds, {len(live_ids)} in progress")

    # The signature of an expired key or a refused agent: ESPN can see games being
    # played and SGO has nothing to say about any of them.
    if live_ids and n_odds == 0:
        add("odds_feed", FAIL,
            f"{len(live_ids)} games in progress but SGO returned no odds -- "
            "check the key and the agent")

    # --- movement, but only where movement is owed ---------------------------
    older = None
    for p in recent:
        cand = _load(p)
        if cand is None:
            continue
        if now - datetime.fromisoformat(cand["captured_at"]) <= MOVEMENT_WINDOW:
            break
        older = cand
    baseline = older or (_load(recent[0]) if len(recent) > 1 else None)

    playing = _sgo_in_play(newest)
    if not playing:
        # The important non-alarm. Nothing is being played, so nothing is expected
        # to move, and saying "ok" here is the difference between a check people
        # read and one they mute.
        add("movement", OK, "no games in progress -- nothing owed")
    elif baseline is None:
        add("movement", WARN, "not enough history yet to judge movement")
    else:
        before, after = _prices(baseline), _prices(newest)
        shared = [k for k in after if k in before and k[0] in playing]
        moved = sum(1 for k in shared if before[k] != after[k])
        span = (datetime.fromisoformat(newest["captured_at"])
                - datetime.fromisoformat(baseline["captured_at"])).total_seconds()
        if not shared:
            add("movement", WARN, "no shared outcomes on in-progress games to compare")
        else:
            add("movement", OK if moved else FAIL,
                f"{moved}/{len(shared)} outcomes moved on {len(playing)} live "
                f"games over {span:.0f}s")

    # Judged on ESPN's own ids and ESPN's own notion of in-progress, independently of
    # whatever the odds side concluded -- the two feeds are allowed to disagree about
    # which games are live, and each check should fail only for its own reasons.
    if live_ids and baseline is not None:
        cb, ca = _clocks(baseline), _clocks(newest)
        advanced = sum(1 for i in live_ids if i in cb and cb[i] != ca.get(i))
        span = (datetime.fromisoformat(newest["captured_at"])
                - datetime.fromisoformat(baseline["captured_at"])).total_seconds()
        add("scoreboard_advancing", OK if advanced else WARN,
            f"{advanced}/{len(live_ids)} live game clocks advanced over {span:.0f}s")

    worst = max((c["status"] for c in checks), key=lambda s: _RANK[s])
    return {"league": league, "status": worst, "checks": checks}


def run() -> dict:
    now = datetime.now(timezone.utc)
    leagues = [check_league(lg, now) for lg in LEAGUES]

    free_gb = shutil.disk_usage(OUT_ROOT).free / 1e9 if OUT_ROOT.exists() else 0.0
    used_gb = sum(f.stat().st_size for f in OUT_ROOT.rglob("*.json.gz")) / 1e9 \
        if OUT_ROOT.exists() else 0.0
    disk = {
        "check": "disk",
        "status": WARN if free_gb < DISK_WARN_GB else OK,
        "detail": f"{used_gb:.2f} GB captured, {free_gb:.0f} GB free",
    }

    # NFL is empty until Wednesday and that is not a fault, so a league with no games
    # scheduled cannot drag the overall verdict down. Only a league that should have
    # something to say and does not is a failure.
    overall = max([l["status"] for l in leagues] + [disk["status"]],
                  key=lambda s: _RANK[s])
    return {
        "checked_at": now.isoformat(),
        "status": overall,
        "capture_dir": str(OUT_ROOT),
        "disk": disk,
        "leagues": leagues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    report = run()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        mark = {OK: "ok  ", WARN: "WARN", FAIL: "FAIL"}
        print(f"[{mark[report['status']]}] capture  {report['capture_dir']}")
        print(f"        {report['disk']['detail']}")
        for lg in report["leagues"]:
            print(f"  [{mark[lg['status']]}] {lg['league']}")
            for c in lg["checks"]:
                print(f"          {mark[c['status']]}  {c['check']:<22} {c['detail']}")

    # Non-zero on failure so cron mails it and any monitor can gate on it. A warning
    # is deliberately still a zero -- a slow tick is not something to wake up for.
    sys.exit(1 if report["status"] == FAIL else 0)


if __name__ == "__main__":
    main()
