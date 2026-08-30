"""Odds snapshot poller — The Odds API (the-odds-api.com).

Snapshots current odds for tracked games into markets/odds_snapshots.

Two endpoints, because the API splits its catalogue:

  * **Featured markets** (h2h/spreads/totals) come from the per-sport bulk
    endpoint. Cost is markets x regions per call, independent of how many games
    come back, so this is cheap and runs for every tracked game.
  * **Everything else** — period lines, alternates, team totals, player props —
    is only available per event, and is charged per event, so this tier is
    scheduled against time-to-kickoff instead of run every poll.

The derivative tier is the whole reason this file changed: without props, period
lines and alternates there is no market surface for an SGP claim to be priced
against. That data only accrues in real time — it cannot be bought back later at
this granularity — so the poll runs even when nothing downstream consumes it yet.

Usage:
    docker compose run --rm ingest python -m youredge.ingest.odds_poller --once
    docker compose run --rm ingest python -m youredge.ingest.odds_poller          # loop
    docker compose run --rm ingest python -m youredge.ingest.odds_poller --core-only
"""

import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import text

from youredge.config import get_settings
from youredge.db import get_engine
from youredge.ingest.resolve import (
    _resolve_team, resolve_event, resolve_ncaaf_player, resolve_nfl_player,
)
from youredge.pricing.devig import devig_snapshots

log = logging.getLogger(__name__)
BASE = "https://api.the-odds-api.com/v4"

SPORT_KEYS = {"nfl": "americanfootball_nfl", "ncaaf": "americanfootball_ncaaf"}

# Bulk endpoint. Charged markets x regions per call, not per event.
CORE_MARKETS = ("h2h", "spreads", "totals")

# Per-event endpoint. Every key below was probed against a live event before
# being wired in; the four that came back empty at every book
# (team_totals_q2/q3/q4, which no book quotes) are left out.
_QUARTERS = ("q1", "q2", "q3", "q4")
_HALVES = ("h1", "h2")

PERIOD_MARKETS = (
    tuple(f"h2h_{p}" for p in _HALVES + _QUARTERS)
    + tuple(f"spreads_{p}" for p in _HALVES + _QUARTERS)
    + tuple(f"totals_{p}" for p in _HALVES + _QUARTERS)
    # Team totals are quoted for the halves and the first quarter only.
    + ("team_totals", "team_totals_h1", "team_totals_h2", "team_totals_q1")
)
ALT_MARKETS = ("alternate_spreads", "alternate_totals")
PROP_MARKETS = (
    "player_pass_yds", "player_rush_yds", "player_reception_yds",
    "player_receptions", "player_pass_tds", "player_anytime_td",
)
# The "X+ yards" boards. A book posts one over-priced rung per threshold rather
# than an over/under pair at a single number, which is how a bettor actually
# shops a prop — and it is the only source of the tail of a player's
# distribution, since the main line only ever reports its middle. player_tds_over
# is the same idea for scoring: 1+, 2+, 3+.
ALT_PROP_MARKETS = (
    "player_pass_yds_alternate", "player_rush_yds_alternate",
    "player_reception_yds_alternate", "player_receptions_alternate",
    "player_pass_tds_alternate", "player_tds_over",
)
DERIVATIVE_MARKETS = PERIOD_MARKETS + ALT_MARKETS + PROP_MARKETS + ALT_PROP_MARKETS

# One list for both leagues. The per-league split this replaces was built on the
# assumption that asking for a market college books do not quote wastes credits.
# Measured against a live event, it does not: a 29-market request against an
# NCAAF game that returned nothing was charged **zero**, while the same request
# against an NFL game that returned 25 markets was charged 26. The meter counts
# what comes back, not what was asked for. So availability rations itself, and
# college gets the full list — which is strictly better than guessing, because
# what college books offer changes as kickoff approaches.
DERIVATIVE_LEAGUES = ("nfl", "ncaaf")

# A Saturday puts ~80 college games inside the near window at once, against the
# NFL's 16. Cap the sweep and take the games closest to kickoff, which is also
# where the props actually are — availability tracks time-to-kickoff, not the
# profile of the matchup.
MAX_NEAR_EVENTS = {"nfl": 32, "ncaaf": 20}


# Books post props well before the week of the game — Week 1 props were quoted a
# fortnight out — so the horizon is generous. What bounds the spend is not the
# horizon but MAX_FAR_EVENTS below: beyond 48 hours only the nearest slate is
# swept, so a distant week entering the horizon costs nothing until it is next.
DERIVATIVE_HORIZON_HOURS = 24 * 21
MAX_FAR_EVENTS = 16

# An upper bound, not a forecast. The meter charges one credit per market that
# actually returns a quote, so a sweep costs this much only for a game where
# every market on the list is up — a Week 1 NFL game inside its final day, and
# little else. A college game five days out returns none of them and costs zero.
# Books are free: credits scale with markets x regions, never with how many
# bookmakers are asked for, which is why odds_bookmakers stays wide while the
# market list is what gets rationed.
MAX_CREDITS_PER_EVENT_SWEEP = len(DERIVATIVE_MARKETS)


def derivative_interval(hours_to_kickoff: float) -> timedelta | None:
    """How stale a game's derivative markets may get before we re-poll it.

    Tightens as kickoff approaches, because that is when the lines move and the
    books post depth. None means "out of range" — don't spend on it.

    The final tier is deliberately narrow. Polling every 30 minutes for the last
    three hours would cost six sweeps a game to buy little more than one: what
    that window is really for is catching the closing line, and one sweep inside
    the last hour does that at a sixth of the price.
    """
    if hours_to_kickoff < 0:
        return None                      # kicked off; live pricing is Phase 5
    if hours_to_kickoff <= 1:
        return timedelta(minutes=30)     # closing snapshot
    if hours_to_kickoff <= 48:
        return timedelta(hours=8)
    if hours_to_kickoff <= DERIVATIVE_HORIZON_HOURS:
        return timedelta(hours=24)
    return None


def american_to_implied(price: int) -> float:
    if price < 0:
        return -price / (-price + 100)
    return 100 / (price + 100)


_UPSERT_MARKET = text("""
    INSERT INTO markets (game_id, bookmaker, market_key, player_id, player_name, side_team_id)
    VALUES (:gid, :bm, :mk, :pid, :pname, :side)
    ON CONFLICT (game_id, bookmaker, market_key, player_name) DO UPDATE
      SET side_team_id = COALESCE(EXCLUDED.side_team_id, markets.side_team_id),
          -- Let a later, better crosswalk fill an id in place; never let a miss
          -- clear one that already resolved.
          player_id    = COALESCE(EXCLUDED.player_id, markets.player_id)
    RETURNING market_id
""")

_INSERT_SNAPSHOT = text("""
    INSERT INTO odds_snapshots
        (market_id, outcome, line, price_american, implied_prob, is_closing)
    VALUES (:mid, :outcome, :line, :price, :prob, :closing)
""")


_DEFENSE_SUFFIXES = (" D/ST", " Defense", " DST")


def _defense_team(subject: str | None) -> str | None:
    """Team name behind a defense/special-teams prop subject, if that's what it is."""
    if not subject:
        return None
    for suffix in _DEFENSE_SUFFIXES:
        if subject.endswith(suffix):
            return subject[: -len(suffix)].strip()
    return None


async def _store_market(conn, gid, book, mkt, *, league, closing) -> int:
    """Write one book's quote for one market. Returns snapshot rows written.

    Props and team totals carry the subject in each outcome's `description`
    ("Sam Darnold", "Seattle Seahawks") rather than on the market, so outcomes
    are grouped by it and each subject becomes its own market row.
    """
    groups: dict[str | None, list[dict]] = {}
    for oc in mkt.get("outcomes", []):
        groups.setdefault(oc.get("description"), []).append(oc)

    is_prop = mkt["key"].startswith("player_")
    rows = 0
    for subject, outcomes in groups.items():
        player_id = None
        side_team_id = None
        # Anytime-TD boards list team defenses among the players ("Seattle
        # Seahawks D/ST"). They are a team scoring, not a person, so they resolve
        # to side_team_id — chasing them through the player crosswalk would only
        # ever miss.
        team_subject = subject if (subject and not is_prop) else _defense_team(subject)
        if team_subject:
            # Books write the full mascot name — "Eastern Michigan Eagles" against
            # a teams.name of "Eastern Michigan" — so an exact match silently
            # loses every college team total. The alias crosswalk built for event
            # resolution already handles this; reuse it rather than matching
            # weakly here.
            side_team_id = await _resolve_team(conn, league, team_subject)
        elif subject and is_prop and league == "nfl":
            player_id = await resolve_nfl_player(conn, subject)
        elif subject and is_prop and league == "ncaaf":
            # College aliases are team-scoped, because rosters share surnames
            # constantly. A prop names the game but not the side, so both are
            # tried and a name that resolves on both is treated as resolving on
            # neither — the whole point of scoping is not to guess.
            sides = (await conn.execute(
                text("SELECT home_team_id, away_team_id FROM games WHERE game_id = :gid"),
                {"gid": gid},
            )).first()
            hits = set()
            for team_id in (sides or ()):
                if not team_id:
                    continue
                hit = await resolve_ncaaf_player(conn, subject, team_id)
                if hit:
                    hits.add(hit)
            player_id = next(iter(hits)) if len(hits) == 1 else None

        market_id = (await conn.execute(_UPSERT_MARKET, {
            "gid": gid, "bm": book, "mk": mkt["key"],
            "pid": player_id,
            # Keep the raw string even when resolved, so market identity stays
            # stable if the crosswalk later changes its mind about a name.
            "pname": subject,
            "side": side_team_id,
        })).scalar_one()

        for oc in outcomes:
            if oc.get("price") is None:
                continue
            price = int(oc["price"])
            await conn.execute(_INSERT_SNAPSHOT, {
                "mid": market_id,
                "outcome": oc["name"],
                "line": oc.get("point"),
                "price": price,
                "prob": american_to_implied(price),
                "closing": closing,
            })
            rows += 1
    return rows


async def _store_event(conn, league, ev, *, closing=False) -> tuple[int, bool]:
    """Resolve an event to a canonical game and store every market on it."""
    kickoff = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
    gid = await resolve_event(
        conn, league, ev["id"], ev["home_team"], ev["away_team"], kickoff
    )
    resolved = gid is not None
    if not gid:
        # Fallback stub keeps snapshots flowing; re-resolves once schedules land.
        gid = f"{league}:oddsapi:{ev['id']}"
        season = kickoff.year if kickoff.month >= 6 else kickoff.year - 1
        await conn.execute(
            text("""
                INSERT INTO games (game_id, league, season, kickoff, status)
                VALUES (:gid, :league, :season, :kickoff, 'scheduled')
                ON CONFLICT (game_id) DO NOTHING
            """),
            {"gid": gid, "league": league, "season": season, "kickoff": kickoff},
        )

    rows = 0
    for bm in ev.get("bookmakers", []):
        for mkt in bm.get("markets", []):
            rows += await _store_market(
                conn, gid, bm["key"], mkt, league=league, closing=closing
            )
    return rows, resolved


async def poll_core(client, league: str) -> tuple[list[dict], int]:
    """Featured markets for every tracked game. One call, markets x regions credits."""
    settings = get_settings()
    r = await client.get(
        f"{BASE}/sports/{SPORT_KEYS[league]}/odds",
        params={
            "apiKey": settings.odds_api_key,
            "regions": "us",
            "markets": ",".join(CORE_MARKETS),
            "bookmakers": settings.odds_bookmakers,
            "oddsFormat": "american",
        },
    )
    r.raise_for_status()
    return r.json(), int(r.headers.get("x-requests-last", 0))


async def _due_for_derivatives(conn, gid: str, kickoff: datetime) -> bool:
    """Has this game's derivative surface gone stale for its tier?"""
    hours = (kickoff - datetime.now(timezone.utc)).total_seconds() / 3600
    interval = derivative_interval(hours)
    if interval is None:
        return False
    last = (await conn.execute(
        text("""
            SELECT max(s.captured_at)
            FROM markets m JOIN odds_snapshots s USING (market_id)
            WHERE m.game_id = :gid AND m.market_key = ANY(:keys)
        """),
        {"gid": gid, "keys": list(DERIVATIVE_MARKETS)},
    )).scalar()
    return last is None or (datetime.now(timezone.utc) - last) >= interval


async def poll_derivatives(client, conn, league: str, events: list[dict]) -> tuple[int, int]:
    """Per-event props, period lines, alternates and team totals.

    Charged per event, so each game is polled only when its tier says it has gone
    stale. Returns (snapshot rows, credits spent).
    """
    settings = get_settings()

    # Decide who is due before spending anything, so the far-slate cap applies to
    # the games that actually need a poll rather than to whatever came first in
    # the feed. Near games (inside 48h) are never capped — that window is where
    # the lines move and where the closing snapshot has to be caught.
    now = datetime.now(timezone.utc)
    near: list[tuple[str, dict]] = []
    far: list[tuple[float, str, dict]] = []
    for ev in events:
        kickoff = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
        hours = (kickoff - now).total_seconds() / 3600
        if derivative_interval(hours) is None:
            continue
        gid = await resolve_event(
            conn, league, ev["id"], ev["home_team"], ev["away_team"], kickoff
        ) or f"{league}:oddsapi:{ev['id']}"
        if not await _due_for_derivatives(conn, gid, kickoff):
            continue
        (near.append((hours, gid, ev)) if hours <= 48 else far.append((hours, gid, ev)))

    near.sort(key=lambda t: t[0])
    far.sort(key=lambda t: t[0])
    near_cap = MAX_NEAR_EVENTS.get(league, 32)
    due = ([(gid, ev) for _, gid, ev in near[:near_cap]]
           + [(gid, ev) for _, gid, ev in far[:MAX_FAR_EVENTS]])
    deferred = max(0, len(near) - near_cap) + max(0, len(far) - MAX_FAR_EVENTS)
    if deferred:
        log.info("%s: deferring %d events past the sweep caps", league, deferred)

    rows = credits = 0
    for gid, ev in due:
        kickoff = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
        try:
            r = await client.get(
                f"{BASE}/sports/{SPORT_KEYS[league]}/events/{ev['id']}/odds",
                params={
                    "apiKey": settings.odds_api_key,
                    "regions": "us",
                    "markets": ",".join(DERIVATIVE_MARKETS),
                    "bookmakers": settings.odds_bookmakers,
                    "oddsFormat": "american",
                },
            )
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            # One event's markets going missing must not abort the sweep.
            log.warning("derivative poll failed for %s: %s", gid, e)
            continue

        credits += int(r.headers.get("x-requests-last", 0))
        # Inside the final half hour this snapshot is the closing line — the one
        # price CLV and every backtest is measured against, unreconstructable
        # after kickoff.
        hours = (kickoff - datetime.now(timezone.utc)).total_seconds() / 3600
        n, _ = await _store_event(conn, league, r.json(), closing=(0 <= hours <= 0.5))
        rows += n
    return rows, credits


async def poll_once(league: str, *, core_only: bool = False) -> int:
    settings = get_settings()
    if not settings.odds_api_key:
        raise SystemExit("ODDS_API_KEY not set in .env")

    engine = get_engine()
    total = 0
    async with httpx.AsyncClient(timeout=30) as client:
        events, core_credits = await poll_core(client, league)
        log.info("%s: %d events from bulk endpoint (%d credits)",
                 league, len(events), core_credits)

        async with engine.begin() as conn:
            resolved = 0
            for ev in events:
                kickoff = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
                hours = (kickoff - datetime.now(timezone.utc)).total_seconds() / 3600
                n, ok = await _store_event(
                    conn, league, ev, closing=(0 <= hours <= 0.5)
                )
                total += n
                resolved += ok

            deriv_credits = 0
            if not core_only and league in DERIVATIVE_LEAGUES:
                n, deriv_credits = await poll_derivatives(client, conn, league, events)
                total += n
                log.info("%s: %d derivative snapshot rows (%d credits)",
                         league, n, deriv_credits)

            filled = await devig_snapshots(conn)

    log.info(
        "%s: %d/%d events resolved, %d snapshot rows, %d fair probs filled, %d credits",
        league, resolved, len(events), total, filled, core_credits + deriv_credits,
    )
    return total


async def main(once: bool, core_only: bool, leagues: tuple[str, ...]):
    settings = get_settings()
    while True:
        for league in leagues:
            try:
                n = await poll_once(league, core_only=core_only)
                log.info("%s: %d snapshot rows", league, n)
            except httpx.HTTPStatusError as e:
                log.error("%s poll failed: %s", league, e)
        if once:
            break
        await asyncio.sleep(settings.odds_poll_interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # httpx INFO logs the full request URL, which includes the apiKey param
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--core-only", action="store_true",
                        help="skip the per-event tier (props/periods/alternates)")
    parser.add_argument("--league", choices=("nfl", "ncaaf"), action="append",
                        help="poll one league only (repeatable); default both")
    args = parser.parse_args()
    asyncio.run(main(args.once, args.core_only, tuple(args.league or ("nfl", "ncaaf"))))
