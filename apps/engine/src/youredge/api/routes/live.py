"""Live scoreboard — the only surface in this engine that is not database-backed.

GET /{league}/live?date=YYYY-MM-DD    scores, clock, down & distance, game leaders

Everything else here computes from Postgres. This reads ESPN's public scoreboard on
each request, because in-game state has no home in our schema: `games` carries a final
score and a status, not a play clock. Storing it would mean a poller, a staleness window,
and a second source of truth for a number that is worthless thirty seconds later.

So it is a pass-through with a short TTL, and every response states when it was fetched.
A stale cache is never served silently — if the upstream call fails the endpoint says so
rather than returning the last good payload dressed up as current.
"""

import time
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import text

from youredge.db import get_engine

router = APIRouter(tags=["live"])

SCOREBOARD = {
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "ncaaf": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard",
}

# NCAAF is the whole FBS+FCS field, and the default response is only the top handful of
# games. groups=80 is "all FBS"; limit lifts the default page size.
EXTRA_PARAMS = {"ncaaf": {"groups": "80", "limit": "200"}}

# ESPN abbreviations that differ from ours. Only two franchises disagree; everything else
# matches, so this stays a two-line map rather than a crosswalk table.
ESPN_TEAM_ALIAS = {"WSH": "WAS", "LAR": "LA"}

# Cached briefly so a page with several components mounting at once, or a user mashing
# refresh, does not fan out into a burst of upstream calls. Short enough that a score is
# never more than a few seconds behind.
_TTL_LIVE = 12.0
_TTL_SETTLED = 120.0   # a date with nothing in progress cannot change quickly
_cache: dict[tuple[str, str], tuple[float, dict]] = {}


def _espn_get(league: str, day: str) -> dict:
    """Fetch one day's scoreboard.

    Do NOT set a browser User-Agent here. ESPN sits behind a WAF that allows recognised
    programmatic clients (httpx's and curl's defaults both pass) and rejects anything
    claiming to be a browser, because the TLS fingerprint does not match the claim. A
    spoofed `Mozilla/5.0 ... Chrome/...` header returns 403 on every request — verified
    across Chrome 58, Chrome 124 and Safari 17 strings — and an unrecognised custom agent
    is refused too. Sending no User-Agent override is what makes this work.
    """
    params = {"dates": day.replace("-", ""), **EXTRA_PARAMS.get(league, {})}
    try:
        r = httpx.get(SCOREBOARD[league], params=params, timeout=12.0)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"scoreboard upstream returned {e.response.status_code}",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"scoreboard unreachable: {e}") from e


def _canonical_team(league: str, team: dict | None) -> str | None:
    """ESPN team object -> our canonical team id.

    The two leagues key differently and neither is a guess: `nfl:BAL` is an
    abbreviation, while `ncaaf:24` is ESPN's own numeric athlete/team id, which is the
    id space our college rows were built from. Using the abbreviation for NCAAF would
    produce `ncaaf:STAN`, which matches nothing.
    """
    if not team:
        return None
    if league == "ncaaf":
        tid = team.get("id")
        return f"ncaaf:{tid}" if tid else None
    abbr = team.get("abbreviation")
    return f"nfl:{ESPN_TEAM_ALIAS.get(abbr, abbr)}" if abbr else None


# ESPN writes 99 into curatedRank for everyone outside the poll. Rendering that as "#99"
# would invent a ranking for three-quarters of the field.
UNRANKED = 99


def _rank(c: dict) -> int | None:
    rank = (c.get("curatedRank") or {}).get("current")
    return rank if rank and rank < UNRANKED else None


def _side(competitors: list[dict], which: str) -> dict:
    for c in competitors:
        if c.get("homeAway") == which:
            return c
    return {}


def _shape_side(league: str, c: dict) -> dict:
    team = c.get("team") or {}
    records = {r.get("type"): r.get("summary") for r in c.get("records") or []}
    score = c.get("score")
    return {
        "team_id": _canonical_team(league, team),
        "abbr": team.get("abbreviation"),
        "name": team.get("shortDisplayName") or team.get("displayName"),
        "full_name": team.get("displayName"),
        "logo": team.get("logo"),
        "score": int(score) if score not in (None, "") else None,
        "record": records.get("total"),
        "rank": _rank(c),
        "winner": c.get("winner"),
        # Per-quarter scoring, for the box line under a live game.
        "linescores": [ls.get("value") for ls in c.get("linescores") or []],
    }


def _shape_situation(league: str, comp: dict) -> dict | None:
    """Down, distance, field position, possession.

    ESPN only includes `situation` while a game is actually in progress, so a null here
    means "not being played right now", not "unavailable".
    """
    s = comp.get("situation")
    if not s:
        return None
    poss_id = s.get("possession")
    poss_team = None
    for c in comp.get("competitors") or []:
        if str(c.get("id")) == str(poss_id):
            poss_team = c.get("team")
    poss_abbr = (poss_team or {}).get("abbreviation")
    last = s.get("lastPlay") or {}

    # ESPN parks sentinels in these fields between snaps — down 0 during a timeout,
    # down -1 and distance -1 on a kickoff or extra point. Rendering them literally
    # produces "0th & 7" and "-1st & -1", so an inactive down is reported as absent.
    down, distance = s.get("down"), s.get("distance")
    active_down = isinstance(down, int) and down >= 1
    if not active_down:
        down = distance = None
    return {
        "down": down,
        "distance": distance,
        "yard_line": s.get("yardLine"),
        "down_distance_text": s.get("downDistanceText"),
        "short_down_distance_text": s.get("shortDownDistanceText"),
        "possession_text": s.get("possessionText"),
        "possession_team_id": _canonical_team(league, poss_team),
        "possession_abbr": poss_abbr,
        "is_red_zone": s.get("isRedZone"),
        "last_play": last.get("text"),
    }


_LEADER_LABEL = {
    "passingYards": "Passing", "rushingYards": "Rushing", "receivingYards": "Receiving",
    "passingLeader": "Passing", "rushingLeader": "Rushing", "receivingLeader": "Receiving",
}


def _shape_leaders(league: str, comp: dict) -> list[dict]:
    """Top statistical performer per category — ESPN's own game leaders."""
    out = []
    for group in comp.get("leaders") or []:
        entries = group.get("leaders") or []
        if not entries:
            continue
        top = entries[0]
        athlete = top.get("athlete") or {}
        team = top.get("team") or {}
        # Leader entries often carry only a team id, so fill the rest off the competitors.
        if not team.get("abbreviation"):
            for c in comp.get("competitors") or []:
                if str(c.get("id")) == str(team.get("id")):
                    team = c.get("team") or team
        abbr = team.get("abbreviation")
        out.append({
            "category": group.get("name"),
            "label": _LEADER_LABEL.get(group.get("name"), group.get("displayName")),
            "player": athlete.get("shortName") or athlete.get("displayName"),
            "headshot": athlete.get("headshot"),
            "position": (athlete.get("position") or {}).get("abbreviation"),
            "stat": top.get("displayValue"),
            "team_id": _canonical_team(league, team),
            "team_abbr": abbr,
        })
    return out


async def _match_canonical(conn, league: str, events: list[dict]) -> dict[str, str]:
    """ESPN event id -> our game_id.

    NCAAF is free: our ids are literally `ncaaf:<espn_event_id>`, which is the same id
    space CFBD's roster and stats endpoints use. NFL ids come from nflverse
    (`nfl:2026_01_NE_SEA`), so those are matched on kickoff date plus both team
    abbreviations — enough to be unique, since a pair cannot meet twice in a day.
    """
    if league == "ncaaf":
        ids = [f"ncaaf:{e['id']}" for e in events]
        rows = (await conn.execute(
            text("SELECT game_id FROM games WHERE game_id = ANY(:ids)"), {"ids": ids},
        )).scalars().all()
        found = set(rows)
        return {e["id"]: f"ncaaf:{e['id']}" for e in events if f"ncaaf:{e['id']}" in found}

    pairs = []
    for e in events:
        comp = (e.get("competitions") or [{}])[0]
        home = _side(comp.get("competitors") or [], "home").get("team", {}).get("abbreviation")
        away = _side(comp.get("competitors") or [], "away").get("team", {}).get("abbreviation")
        if home and away and e.get("date"):
            pairs.append((e["id"], ESPN_TEAM_ALIAS.get(home, home),
                          ESPN_TEAM_ALIAS.get(away, away), e["date"][:10]))
    if not pairs:
        return {}

    rows = (await conn.execute(
        text("""
            SELECT g.game_id, h.abbr AS home_abbr, a.abbr AS away_abbr,
                   to_char(g.kickoff, 'YYYY-MM-DD') AS day
            FROM games g
            JOIN teams h ON h.team_id = g.home_team_id
            JOIN teams a ON a.team_id = g.away_team_id
            WHERE g.league = 'nfl' AND g.kickoff >= :d0 AND g.kickoff < :d1
        """),
        # Window widened in Python, not SQL: asyncpg sends parameters untyped, so
        # `:param - 1` leaves Postgres unable to tell date arithmetic from integer
        # subtraction. Passing two real dates sidesteps the inference entirely.
        {"d0": date_cls.fromisoformat(min(p[3] for p in pairs)) - timedelta(days=1),
         "d1": date_cls.fromisoformat(max(p[3] for p in pairs)) + timedelta(days=2)},
    )).mappings().all()

    # Kickoffs cross midnight UTC constantly, so match on the team pair and accept any
    # kickoff within the surrounding day rather than requiring the dates to be equal.
    by_pair: dict[tuple[str, str], str] = {(r["home_abbr"], r["away_abbr"]): r["game_id"]
                                           for r in rows}
    return {eid: by_pair[(h, a)] for eid, h, a, _ in pairs if (h, a) in by_pair}


@router.get("/live")
async def live_scoreboard(
    request: Request,
    date: str | None = Query(default=None, description="YYYY-MM-DD; defaults to today"),
    refresh: bool = Query(default=False, description="bypass the short cache"),
):
    league = request.url.path.split("/")[2]
    day = date or date_cls.today().isoformat()

    key = (league, day)
    hit = _cache.get(key)
    now = time.monotonic()
    if hit and not refresh and now - hit[0] < hit[1].get("_ttl", _TTL_LIVE):
        payload = dict(hit[1])
        payload["age_seconds"] = round(now - hit[0], 1)
        payload.pop("_ttl", None)
        return payload

    raw = _espn_get(league, day)
    events = raw.get("events") or []

    async with get_engine().connect() as conn:
        canonical = await _match_canonical(conn, league, events)

    games = []
    any_live = False
    for e in events:
        comp = (e.get("competitions") or [{}])[0]
        status = e.get("status") or comp.get("status") or {}
        stype = status.get("type") or {}
        state = stype.get("state")
        any_live = any_live or state == "in"
        competitors = comp.get("competitors") or []
        broadcasts = comp.get("broadcasts") or []
        games.append({
            "espn_id": e.get("id"),
            "game_id": canonical.get(e.get("id")),
            "name": e.get("shortName"),
            "kickoff": e.get("date"),
            "state": state,                       # pre | in | post
            "status": {
                "detail": stype.get("detail"),
                "short_detail": stype.get("shortDetail"),
                "description": stype.get("description"),
                "completed": stype.get("completed"),
                "clock": status.get("displayClock"),
                "period": status.get("period"),
            },
            "home": _shape_side(league, _side(competitors, "home")),
            "away": _shape_side(league, _side(competitors, "away")),
            "situation": _shape_situation(league, comp),
            "leaders": _shape_leaders(league, comp),
            "venue": (comp.get("venue") or {}).get("fullName"),
            "neutral_site": comp.get("neutralSite"),
            "broadcast": (broadcasts[0].get("names") or [None])[0] if broadcasts else None,
            "notes": (comp.get("notes") or [{}])[0].get("headline") if comp.get("notes") else None,
        })

    # In-progress order first — that is what a live tab is for — then by kickoff.
    order = {"in": 0, "pre": 1, "post": 2}
    games.sort(key=lambda g: (order.get(g["state"], 3), g["kickoff"] or ""))

    payload = {
        "league": league,
        "date": day,
        "source": "espn",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "age_seconds": 0.0,
        "live_count": sum(1 for g in games if g["state"] == "in"),
        "count": len(games),
        "games": games,
    }
    _cache[key] = (now, {**payload, "_ttl": _TTL_LIVE if any_live else _TTL_SETTLED})
    return payload
