"""Slate, matchup, and odds-board endpoints — what the web app navigates by.

GET /teams                       every team in the league (the picker's source)
GET /games                       the slate: filter by season/week/team, or just "upcoming"
GET /games/{game_id}             one matchup: teams, venue, conditions, best-book prices
GET /games/{game_id}/odds        full board — every book, every outcome, plus line movement

Everything here reads `games`/`teams`/`venues`/`markets`/`odds_snapshots` directly. No
model output appears in these responses: `fair_prob` is the de-vigged *market* price, not
a projection, and it is labelled as such all the way to the UI.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import text

from youredge.db import get_engine
from youredge.scripts.forecast import game_surface
from youredge.ingest.resolve import normalize_name

router = APIRouter(tags=["games"])

# Books that quote a live price. The `cfbd:*` and `nflverse:closing` rows are historical
# archives — useful for backtests, wrong to show as "the current line", so they are only
# consulted when a live book has nothing and are flagged when they are.
LIVE_BOOKS = ["draftkings", "fanduel", "betmgm", "caesars", "pinnacle"]
ARCHIVE_BOOKS = ["cfbd:consensus", "nflverse:closing", "cfbd:draftkings", "cfbd:bovada"]
BOOK_PREFERENCE = LIVE_BOOKS + ARCHIVE_BOOKS


def _instant(value: str | None, field: str) -> datetime | None:
    """Parse an ISO instant for binding.

    asyncpg types parameters from how they are used, so a string compared against a
    timestamptz column is rejected outright rather than coerced — the cast in the SQL
    does not save it. Parsing here also means a malformed value is a 400 naming the
    field, instead of a 500 out of the driver.
    """
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"{field} must be an ISO 8601 instant, got {value!r}",
        ) from e


def _league(request: Request) -> str:
    """`/api/nfl/games` -> "nfl". The routers mount twice, once per league."""
    return request.url.path.split("/")[2]


@router.get("/teams")
async def list_teams(request: Request, classification: str | None = Query(default=None)):
    """Every team in the league. NCAAF defaults to FBS only — the 105 FCS teams have no
    odds and no context rows, so listing them makes the picker worse, not more complete."""
    league = _league(request)
    if league == "ncaaf" and classification is None:
        classification = "fbs"
    async with get_engine().connect() as conn:
        rows = (await conn.execute(
            text("""
                SELECT team_id, abbr, name, classification
                FROM teams
                WHERE league = :league
                  AND (CAST(:cls AS text) IS NULL OR classification = :cls)
                ORDER BY name
            """),
            {"league": league, "cls": classification},
        )).mappings().all()
    return {"league": league, "count": len(rows), "teams": [dict(r) for r in rows]}


_GAMES_SQL = """
    SELECT g.game_id, g.season, g.week, g.season_type, g.kickoff, g.status,
           g.home_score, g.away_score, g.neutral_site, g.roof, g.surface,
           g.temp, g.wind, g.notes,
           h.team_id AS home_id, h.abbr AS home_abbr, h.name AS home_name,
           a.team_id AS away_id, a.abbr AS away_abbr, a.name AS away_name,
           v.name AS venue_name, v.city AS venue_city, v.state AS venue_state,
           v.elevation AS venue_elevation, v.dome AS venue_dome
    FROM games g
    JOIN teams h ON h.team_id = g.home_team_id
    JOIN teams a ON a.team_id = g.away_team_id
    LEFT JOIN venues v ON v.venue_id = g.venue_id
    WHERE g.league = :league
      AND (CAST(:season AS int) IS NULL OR g.season = :season)
      AND (CAST(:week AS int) IS NULL OR g.week = :week)
      AND (CAST(:status AS text) IS NULL OR g.status = :status)
      AND (CAST(:team AS text) IS NULL OR :team IN (g.home_team_id, g.away_team_id))
      AND (NOT :upcoming OR g.kickoff >= :now)
      AND (CAST(:ko_from AS timestamptz) IS NULL OR g.kickoff >= :ko_from)
      AND (CAST(:ko_to   AS timestamptz) IS NULL OR g.kickoff <  :ko_to)
    ORDER BY g.kickoff {order}
    LIMIT :lim
"""

# One row per (market, outcome) — the most recent price each book is showing.
# The board is a featured-markets board. Since the poller widened, markets also
# carries alternates, period lines, team totals and props — all of which have a
# NULL player_id when the subject is a team or unresolved, so "player_id IS NULL"
# is no longer enough to mean "the three main lines". Name them.
FEATURED_MARKETS = ("h2h", "spreads", "totals")


_LATEST_ODDS = text("""
    WITH latest AS (
        SELECT DISTINCT ON (s.market_id, s.outcome)
               s.market_id, s.outcome, s.line, s.price_american,
               s.implied_prob, s.fair_prob, s.captured_at
        FROM odds_snapshots s
        JOIN markets m ON m.market_id = s.market_id
        WHERE m.game_id = ANY(:gids) AND m.market_key = ANY(:featured)
        ORDER BY s.market_id, s.outcome, s.captured_at DESC
    )
    SELECT m.game_id, m.bookmaker, m.market_key, l.outcome, l.line,
           l.price_american, l.implied_prob, l.fair_prob, l.captured_at
    FROM latest l JOIN markets m ON m.market_id = l.market_id
""")


# The Odds API writes outcomes as the book's own team string — "North Carolina Tar
# Heels" where our `teams.name` is "North Carolina". Comparing those directly is what
# silently dropped every college spread and moneyline while leaving Over/Under intact.
# The ingest already built a normalized alias table for exactly this; reuse it rather
# than inventing a second, weaker matcher here.
_ALIAS = text("""
    SELECT source_id, canonical_id FROM entity_xwalk
    WHERE entity_type = 'team' AND source IN ('cfbd_alias', 'odds_api')
      AND source_id = ANY(:keys)
""")


async def _resolve_outcomes(conn, rows: list[dict]) -> dict[str, str]:
    """{raw outcome string -> canonical team id} for the team-named outcomes present."""
    names = {r["outcome"] for r in rows if r["outcome"] not in ("Over", "Under")}
    if not names:
        return {}
    by_norm = {normalize_name(n): n for n in names}
    found = (await conn.execute(_ALIAS, {"keys": list(by_norm)})).mappings().all()
    return {by_norm[f["source_id"]]: f["canonical_id"]
            for f in found if f["source_id"] in by_norm}


def _shape_board(rows: list[dict], home: dict, away: dict,
                 resolved: dict[str, str] | None = None) -> dict[str, dict]:
    """Collapse flat snapshot rows into {bookmaker: {spread, total, moneyline}}.

    A side is assigned by exact name, by abbreviation, or by the alias crosswalk — in
    that order. An outcome that matches none of the three is dropped rather than
    guessed at, because attributing a price to the wrong team is worse than omitting it.
    """
    resolved = resolved or {}
    board: dict[str, dict] = {}
    for r in rows:
        book = board.setdefault(r["bookmaker"], {
            "bookmaker": r["bookmaker"],
            "is_live_book": r["bookmaker"] in LIVE_BOOKS,
            "captured_at": r["captured_at"],
        })
        if r["captured_at"] and (not book["captured_at"] or r["captured_at"] > book["captured_at"]):
            book["captured_at"] = r["captured_at"]

        outcome = r["outcome"]
        canonical = resolved.get(outcome)
        side = None
        if outcome in (home["name"], home["abbr"]) or (
                canonical and canonical == home.get("team_id")):
            side = "home"
        elif outcome in (away["name"], away["abbr"]) or (
                canonical and canonical == away.get("team_id")):
            side = "away"

        price = {
            "price_american": r["price_american"],
            "line": r["line"],
            "implied_prob": r["implied_prob"],
            "fair_prob": r["fair_prob"],
        }
        if r["market_key"] == "spreads" and side:
            book.setdefault("spread", {})[side] = price
        elif r["market_key"] == "h2h" and side:
            book.setdefault("moneyline", {})[side] = price
        elif r["market_key"] == "totals" and r["outcome"] in ("Over", "Under"):
            book.setdefault("total", {})[r["outcome"].lower()] = price
    return board


def _best_book(board: dict[str, dict]) -> dict | None:
    """The one price line the slate shows. Preference order, live books first."""
    for name in BOOK_PREFERENCE:
        if name in board:
            return board[name]
    return next(iter(board.values()), None)


@router.get("/games")
async def list_games(
    request: Request,
    season: int | None = Query(default=None),
    week: int | None = Query(default=None),
    status: str | None = Query(default=None, description="scheduled | live | final"),
    team_id: str | None = Query(default=None, description="canonical id, e.g. nfl:BAL"),
    upcoming: bool = Query(default=False, description="kickoff in the future only"),
    # Absolute instants rather than a date string, deliberately. "Games from today" is a
    # question about the caller's day, and a college Saturday night kickoff lands on
    # Sunday in UTC — so the client sends its own local midnight boundaries and the
    # server does not have to guess at a timezone.
    kickoff_from: str | None = Query(default=None, description="ISO instant, inclusive"),
    kickoff_to: str | None = Query(default=None, description="ISO instant, exclusive"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=100, le=400),
    odds: bool = Query(default=True, description="attach the best-book price line"),
):
    league = _league(request)
    sql = text(_GAMES_SQL.format(order="ASC" if order == "asc" else "DESC"))
    async with get_engine().connect() as conn:
        rows = (await conn.execute(sql, {
            "league": league, "season": season, "week": week, "status": status,
            "team": team_id, "upcoming": upcoming, "lim": limit,
            "ko_from": _instant(kickoff_from, "kickoff_from"),
            "ko_to": _instant(kickoff_to, "kickoff_to"),
            "now": datetime.now(timezone.utc),
        })).mappings().all()

        boards: dict[str, list[dict]] = {}
        resolved: dict[str, str] = {}
        if odds and rows:
            snaps = [dict(x) for x in (await conn.execute(
                _LATEST_ODDS,
                {"gids": [r["game_id"] for r in rows], "featured": list(FEATURED_MARKETS)},
            )).mappings()]
            resolved = await _resolve_outcomes(conn, snaps)
            for snap in snaps:
                boards.setdefault(snap["game_id"], []).append(snap)

    games = []
    for r in rows:
        g = _game_shape(r)
        if odds:
            board = _shape_board(boards.get(r["game_id"], []), g["home"], g["away"], resolved)
            g["odds"] = _best_book(board)
            g["books_quoting"] = len(board)
        games.append(g)
    return {"league": league, "count": len(games), "games": games}


def _game_shape(r: dict) -> dict:
    return {
        "game_id": r["game_id"],
        "season": r["season"],
        "week": r["week"],
        "season_type": r["season_type"],
        "kickoff": r["kickoff"],
        "status": r["status"],
        "notes": r["notes"],
        "neutral_site": r["neutral_site"],
        "home": {"team_id": r["home_id"], "abbr": r["home_abbr"],
                 "name": r["home_name"], "score": r["home_score"]},
        "away": {"team_id": r["away_id"], "abbr": r["away_abbr"],
                 "name": r["away_name"], "score": r["away_score"]},
        # roof/surface/temp/wind are per game, not per venue: retractable roofs open and
        # a neutral-site game isn't played on the home surface. NULL temp means "not
        # reported" (CFBD's weather is paywalled) — never "indoors" or "calm".
        "conditions": {
            "roof": r["roof"], "surface": r["surface"],
            "temp": r["temp"], "wind": r["wind"],
            "venue": r["venue_name"], "city": r["venue_city"], "state": r["venue_state"],
            "elevation": r["venue_elevation"], "dome": r["venue_dome"],
        },
    }


@router.get("/games/{game_id}")
async def game_detail(request: Request, game_id: str):
    league = _league(request)
    async with get_engine().connect() as conn:
        row = (await conn.execute(
            text(_GAMES_SQL.format(order="ASC").replace(
                "AND (NOT :upcoming OR g.kickoff >= :now)", "AND g.game_id = :gid")),
            {"league": league, "season": None, "week": None, "status": None,
             "team": None, "lim": 1, "gid": game_id, "ko_from": None, "ko_to": None},
        )).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail=f"unknown game_id {game_id}")
        snaps = [dict(x) for x in (await conn.execute(
            _LATEST_ODDS, {"gids": [game_id], "featured": list(FEATURED_MARKETS)})).mappings()]
        resolved = await _resolve_outcomes(conn, snaps)

    game = _game_shape(row)
    board = _shape_board(snaps, game["home"], game["away"], resolved)
    game["odds"] = _best_book(board)
    game["books"] = sorted(board.values(),
                           key=lambda b: (not b["is_live_book"], b["bookmaker"]))
    return game


# Everything the poller stores that is not one of the three featured lines. Grouped so a
# board can render them in sections rather than as one undifferentiated list.
ALT_MARKETS = ("alternate_spreads", "alternate_totals")
TEAM_MARKETS = ("team_totals",)
# Period markets are named by suffix (spreads_h1, totals_q1...), so they are matched
# rather than enumerated — the poller can widen without this list going stale.
PERIOD_SUFFIXES = ("_h1", "_h2", "_q1", "_q2", "_q3", "_q4")

_ALL_SNAPSHOTS = text("""
    WITH latest AS (
        SELECT DISTINCT ON (s.market_id, s.outcome, s.line)
               s.market_id, s.outcome, s.line, s.price_american,
               s.implied_prob, s.fair_prob, s.captured_at
        FROM odds_snapshots s
        JOIN markets m ON m.market_id = s.market_id
        WHERE m.game_id = :gid AND m.market_key = ANY(:keys)
        ORDER BY s.market_id, s.outcome, s.line, s.captured_at DESC
    )
    SELECT m.bookmaker, m.market_key, m.player_id, m.player_name, m.side_team_id,
           l.outcome, l.line, l.price_american, l.implied_prob, l.fair_prob, l.captured_at
    FROM latest l JOIN markets m ON m.market_id = l.market_id
""")


async def _market_keys(conn, game_id: str) -> list[str]:
    return list((await conn.execute(
        text("SELECT DISTINCT market_key FROM markets WHERE game_id = :gid"),
        {"gid": game_id},
    )).scalars())


@router.get("/games/{game_id}/props")
async def game_props(
    game_id: str,
    market: str | None = Query(default=None, description="one market_key, e.g. player_pass_yds"),
):
    """Player props, grouped by the person they are about.

    A prop board keyed by market makes you hunt for a player across six tables; keyed by
    player it reads the way it is actually used. Over/under markets carry a line and two
    sides; anytime-touchdown carries neither, only a price on "Yes", so the shape is
    per-market rather than forced into one mould.

    `player_id` is null for defence/special-teams entries — "Buffalo Bills D/ST" is not a
    person and does not resolve to one. Those keep `side_team_id` instead, and are
    labelled rather than dropped.
    """
    async with get_engine().connect() as conn:
        exists = (await conn.execute(
            text("SELECT 1 FROM games WHERE game_id = :gid"), {"gid": game_id})).first()
        if exists is None:
            raise HTTPException(status_code=404, detail=f"unknown game_id {game_id}")

        keys = [k for k in await _market_keys(conn, game_id) if k.startswith("player_")]
        if market:
            keys = [k for k in keys if k == market]
        rows = [dict(r) for r in (await conn.execute(
            _ALL_SNAPSHOTS, {"gid": game_id, "keys": keys or [""]})).mappings()] if keys else []

    # subject -> markets -> books. A subject is a player, or a team for D/ST entries.
    subjects: dict[str, dict] = {}
    for r in rows:
        sid = r["player_id"] or r["side_team_id"] or r["player_name"]
        subj = subjects.setdefault(sid, {
            "subject_id": sid,
            "player_id": r["player_id"],
            "team_id": r["side_team_id"],
            "name": r["player_name"],
            "is_team_unit": r["player_id"] is None,
            "markets": {},
        })
        mkt = subj["markets"].setdefault(r["market_key"], {"market_key": r["market_key"],
                                                          "lines": {}})
        # Books disagree on the line, so the line is part of the key, not a property of
        # the market — an over 249.5 and an over 264.5 are different bets.
        line_key = "-" if r["line"] is None else str(r["line"])
        line = mkt["lines"].setdefault(line_key, {"line": r["line"], "books": {}})
        book = line["books"].setdefault(r["bookmaker"], {"bookmaker": r["bookmaker"],
                                                         "captured_at": r["captured_at"]})
        book[(r["outcome"] or "").lower() or "price"] = {
            "price_american": r["price_american"],
            "implied_prob": r["implied_prob"],
            "fair_prob": r["fair_prob"],
        }

    out = []
    for subj in subjects.values():
        subj["markets"] = [
            {**m, "lines": sorted(m["lines"].values(),
                                  key=lambda x: (x["line"] is None, x["line"]))}
            for m in subj["markets"].values()
        ]
        for m in subj["markets"]:
            for ln in m["lines"]:
                ln["books"] = sorted(ln["books"].values(), key=lambda b: b["bookmaker"])
        out.append(subj)
    # Most-quoted first: a player six books priced is the one being talked about.
    out.sort(key=lambda x: (-sum(len(m["lines"]) for m in x["markets"]), x["name"] or ""))

    return {
        "game_id": game_id,
        "market_keys": sorted(keys),
        "subjects": out,
        "count": len(out),
    }


@router.get("/games/{game_id}/odds")
async def game_odds(
    request: Request,
    game_id: str,
    history: bool = Query(default=True, description="include the snapshot time series"),
):
    """Every book's current price, plus how each line has moved since it opened.

    Edge is model probability minus `fair_prob` — the de-vigged number — never minus
    `implied_prob`, which overstates it by exactly the hold.
    """
    async with get_engine().connect() as conn:
        exists = (await conn.execute(
            text("SELECT 1 FROM games WHERE game_id = :gid"), {"gid": game_id})).first()
        if exists is None:
            raise HTTPException(status_code=404, detail=f"unknown game_id {game_id}")
        teams = (await conn.execute(
            text("""
                SELECT h.team_id AS home_id, h.abbr AS home_abbr, h.name AS home_name,
                       a.team_id AS away_id, a.abbr AS away_abbr, a.name AS away_name
                FROM games g JOIN teams h ON h.team_id = g.home_team_id
                             JOIN teams a ON a.team_id = g.away_team_id
                WHERE g.game_id = :gid
            """), {"gid": game_id})).mappings().first()
        snaps = [dict(x) for x in (await conn.execute(
            _LATEST_ODDS, {"gids": [game_id], "featured": list(FEATURED_MARKETS)})).mappings()]
        resolved = await _resolve_outcomes(conn, snaps)

        # Everything the poller stores beyond the three featured lines, split into the
        # sections a board renders. Props are counted but not expanded here — they are a
        # different shape and a much larger payload, so they have their own endpoint.
        all_keys = await _market_keys(conn, game_id)
        prop_keys = sorted(k for k in all_keys if k.startswith("player_"))
        extra_keys = [k for k in all_keys
                      if k not in FEATURED_MARKETS and not k.startswith("player_")]
        sections: dict[str, list] = {"alternates": [], "periods": [], "team_totals": []}
        if extra_keys:
            extra = [dict(x) for x in (await conn.execute(
                _ALL_SNAPSHOTS, {"gid": game_id, "keys": extra_keys})).mappings()]
            extra_resolved = await _resolve_outcomes(conn, extra)
            for r in extra:
                if r["market_key"] in ALT_MARKETS:
                    bucket = "alternates"
                elif r["market_key"] in TEAM_MARKETS:
                    bucket = "team_totals"
                elif any(r["market_key"].endswith(sfx) for sfx in PERIOD_SUFFIXES):
                    bucket = "periods"
                else:
                    bucket = "alternates"
                canonical = extra_resolved.get(r["outcome"])
                sections[bucket].append({
                    "market_key": r["market_key"],
                    "bookmaker": r["bookmaker"],
                    "outcome": r["outcome"],
                    "team_id": canonical or r["side_team_id"],
                    "line": r["line"],
                    "price_american": r["price_american"],
                    "fair_prob": r["fair_prob"],
                    "captured_at": r["captured_at"],
                })
            for rows_ in sections.values():
                rows_.sort(key=lambda x: (x["market_key"], x["line"] is None,
                                          x["line"] or 0, x["bookmaker"]))

        movement = []
        if history:
            movement = [dict(r) for r in (await conn.execute(
                text("""
                    SELECT m.bookmaker, m.market_key, s.outcome, s.line,
                           s.price_american, s.fair_prob, s.captured_at
                    FROM odds_snapshots s JOIN markets m ON m.market_id = s.market_id
                    WHERE m.game_id = :gid AND m.market_key = ANY(:featured)
                    ORDER BY s.captured_at
                """), {"gid": game_id, "featured": list(FEATURED_MARKETS)})).mappings()]

    home = {"team_id": teams["home_id"], "name": teams["home_name"], "abbr": teams["home_abbr"]}
    away = {"team_id": teams["away_id"], "name": teams["away_name"], "abbr": teams["away_abbr"]}
    board = _shape_board(snaps, home, away, resolved)

    return {
        "game_id": game_id,
        "books": sorted(board.values(), key=lambda b: (not b["is_live_book"], b["bookmaker"])),
        "sections": sections,
        "prop_market_keys": prop_keys,
        "movement": movement,
    }


@router.get("/games/{game_id}/scripts")
async def game_scripts(game_id: str):
    """The Game Tag Surface: likely script shapes, and each side's tendencies.

    Empirical, not simulated — base rates conditioned on this game's closing
    line, with the sample and the conditioning level returned alongside every
    number so a league average is never mistaken for a read on this game.
    """
    async with get_engine().connect() as conn:
        surface = await game_surface(conn, game_id)
    if not surface:
        raise HTTPException(status_code=404, detail=f"unknown game {game_id}")
    return surface
