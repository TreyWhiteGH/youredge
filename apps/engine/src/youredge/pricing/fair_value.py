"""Single-leg fair value: the first honest edge number in the product.

No model required. Take the sharpest book's two-sided price, strip the vig, and
compare it to what the user's book is offering. If Pinnacle says a side is 47.5%
and DraftKings pays you as though it were 45%, that difference is real and
countable, and it exists today — before any simulator.

    fair = devig(pinnacle two-sided prices)
    edge = fair - implied(user's book price)

Two rules the rest of the codebase already follows and this must not break:

  * Edge is measured against `fair_prob`, never the raw implied price. Comparing
    to the vigged number overstates every edge by exactly the hold.
  * A stale line is not a price. Quoting edge off a snapshot from last Tuesday is
    worse than quoting nothing, so freshness is returned with every number and
    the caller is expected to gate on it.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text

log = logging.getLogger(__name__)

# The sharp anchor, in order of preference. Pinnacle first because its price is
# the one the market corrects toward; the others are a fallback so a leg is not
# left unpriced simply because Pinnacle skipped the game.
ANCHOR_BOOKS = ("pinnacle", "betmgm", "fanduel", "draftkings", "caesars")

# Where to look when the main market does not quote the requested line.
_ALTERNATE_OF = {"totals": "alternate_totals", "spreads": "alternate_spreads"}

# Past this the number describes a market that has moved on — and how long that
# takes depends entirely on how close kickoff is. A line six hours old on a
# Thursday game is the same line; six hours before kickoff it is two moves
# behind, and inside the last hour a price from thirty minutes ago is already
# history. One flat threshold has to be wrong at one end or the other, so it is
# tiered against time to kickoff the way the poller's own schedule is.
STALE_AFTER_SECONDS = 6 * 3600          # kept: the default beyond a day out
_FRESHNESS_TIERS = (
    (1, 20 * 60),        # inside the last hour: 20 minutes
    (3, 45 * 60),        # inside three: 45 minutes
    (24, 3 * 3600),      # inside a day: 3 hours
)


def stale_after(hours_to_kickoff: float | None) -> int:
    """How old a quote may be, for a game this far from kickoff."""
    if hours_to_kickoff is None or hours_to_kickoff < 0:
        return STALE_AFTER_SECONDS
    for cutoff, allowed in _FRESHNESS_TIERS:
        if hours_to_kickoff <= cutoff:
            return allowed
    return STALE_AFTER_SECONDS


@dataclass
class Priced:
    market_key: str
    outcome: str
    line: float | None
    book: str
    book_price: int | None
    book_implied: float | None
    anchor_book: str | None
    fair_prob: float | None
    edge: float | None
    captured_at: datetime | None
    stale_seconds: float | None
    # How old this quote was allowed to be, given how close the game is. Carried
    # rather than recomputed so a caller rendering "4 min old" can also say what
    # it was measured against, which is the difference between a number and a
    # verdict someone can check.
    stale_after_seconds: int = STALE_AFTER_SECONDS

    @property
    def is_stale(self) -> bool:
        return (self.stale_seconds is None
                or self.stale_seconds > self.stale_after_seconds)


def american_to_implied(price: int) -> float:
    return -price / (-price + 100) if price < 0 else 100 / (price + 100)


# `subject` is what separates one team's total from the other's. Without it both
# sides of a team-total market reduce to the same (bookmaker, 'Over', line) key
# and the query returns whichever sorted first — so a leg naming a team was
# priced off a coin toss between the two, or silently not priced at all.
_LATEST = text("""
    SELECT DISTINCT ON (m.bookmaker, s.outcome, s.line)
           m.bookmaker, s.outcome, s.line, s.price_american, s.implied_prob,
           s.captured_at
    FROM markets m
    JOIN odds_snapshots s ON s.market_id = m.market_id
    WHERE m.game_id = :gid AND m.market_key = :mkey
      AND s.price_american IS NOT NULL
      -- A subject is a team for a team total and a player for a prop. The two
      -- id namespaces do not overlap, so one parameter covers both without the
      -- caller having to say which kind it is.
      AND (CAST(:subject AS text) IS NULL
           OR m.side_team_id = :subject OR m.player_id = :subject)
    ORDER BY m.bookmaker, s.outcome, s.line, s.captured_at DESC
""")


def _devig_pair(p_a: float, p_b: float) -> float:
    """Fair probability of side A from a two-sided vigged pair.

    Multiplicative (proportional) de-vig. For a roughly balanced two-way market —
    spreads and totals — it is within a few tenths of a point of the power method,
    and it does not pretend to know a longshot bias that is not there at -110.
    """
    total = p_a + p_b
    return p_a / total if total > 0 else p_a


async def price_leg(
    conn, game_id: str, market_key: str, outcome: str, line: float | None,
    user_book: str, subject: str | None = None,
) -> Priced:
    """Fair value for one leg, anchored on the sharpest book quoting it.

    `subject` is a canonical team id, required for markets a book quotes once per
    side — team totals above all. Without it the two sides are indistinguishable.
    """
    rows = (await conn.execute(
        _LATEST, {"gid": game_id, "mkey": market_key,
                  "subject": subject})).mappings().all()

    # A book posts one main number and a ladder of alternates in a separate
    # market. "over 51.5" is a perfectly ordinary thing to ask for on a game
    # whose main total is 44.5, and looking only at the main market answers "not
    # quoted" for a line the book is plainly offering. Fall through to the
    # ladder when the main market has nothing at the requested number.
    if line is not None and market_key in _ALTERNATE_OF:
        if not any(r["line"] is not None
                   and abs(abs(r["line"]) - abs(line)) < 0.01 for r in rows):
            alt = (await conn.execute(
                _LATEST, {"gid": game_id, "mkey": _ALTERNATE_OF[market_key],
                          "subject": subject})).mappings().all()
            if alt:
                rows = alt

    def matches(r, want_outcome: str) -> bool:
        if r["outcome"].lower() != want_outcome.lower():
            return False
        if line is None:
            return True
        # Spreads are quoted from each side, so the opposite side carries the
        # negated number.
        return r["line"] is not None and abs(abs(r["line"]) - abs(line)) < 0.01

    # Keyed on outcome *and* line, because a market can be a ladder. Keying on
    # outcome alone kept only the last row per side, so a request for over 46.5
    # was compared against whichever alternate happened to sort last and matched
    # nothing — which is why no slip carrying three legs of real risk could be
    # constructed: every one of them needs a total off the main number.
    def key(r) -> tuple[str, float | None]:
        return (r["outcome"].lower(),
                None if r["line"] is None else abs(round(float(r["line"]), 2)))

    by_book: dict[str, dict[tuple, dict]] = {}
    for r in rows:
        by_book.setdefault(r["bookmaker"], {})[key(r)] = r

    want_line = None if line is None else abs(round(float(line), 2))
    sides = {r["outcome"].lower() for r in rows}
    other = next((s for s in sides if s != outcome.lower()), None)

    def at(quotes: dict, side: str) -> dict | None:
        """That side of this rung. Falls back to the sole quote when the market
        carries no line at all, which is how moneylines arrive."""
        if want_line is not None:
            return quotes.get((side, want_line))
        found = [v for k, v in quotes.items() if k[0] == side]
        return found[0] if found else None

    fair = anchor = None
    if other:
        for book in ANCHOR_BOOKS:
            quotes = by_book.get(book, {})
            a, b = at(quotes, outcome.lower()), at(quotes, other)
            if a and b and matches(a, outcome) and a["implied_prob"] and b["implied_prob"]:
                fair = _devig_pair(a["implied_prob"], b["implied_prob"])
                anchor = book
                break

    mine = at(by_book.get(user_book, {}), outcome.lower())
    if mine and not matches(mine, outcome):
        mine = None
    book_implied = mine["implied_prob"] if mine else None
    captured = mine["captured_at"] if mine else None
    stale = ((datetime.now(timezone.utc) - captured).total_seconds()
             if captured else None)
    kickoff = (await conn.execute(
        text("SELECT kickoff FROM games WHERE game_id = :gid"), {"gid": game_id}
    )).scalar()
    hours = ((kickoff - datetime.now(timezone.utc)).total_seconds() / 3600
             if kickoff else None)

    return Priced(
        market_key=market_key, outcome=outcome, line=line,
        book=user_book,
        book_price=mine["price_american"] if mine else None,
        book_implied=book_implied,
        anchor_book=anchor,
        fair_prob=fair,
        # Positive means the book pays as though the leg were less likely than
        # the sharp price says it is.
        edge=(fair - book_implied) if (fair is not None and book_implied) else None,
        captured_at=captured,
        stale_seconds=stale,
        stale_after_seconds=stale_after(hours),
    )
