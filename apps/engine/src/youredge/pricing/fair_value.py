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

# Past this the number describes a market that has moved on.
STALE_AFTER_SECONDS = 6 * 3600


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

    @property
    def is_stale(self) -> bool:
        return self.stale_seconds is None or self.stale_seconds > STALE_AFTER_SECONDS


def american_to_implied(price: int) -> float:
    return -price / (-price + 100) if price < 0 else 100 / (price + 100)


_LATEST = text("""
    SELECT DISTINCT ON (m.bookmaker, s.outcome, s.line)
           m.bookmaker, s.outcome, s.line, s.price_american, s.implied_prob,
           s.captured_at
    FROM markets m
    JOIN odds_snapshots s ON s.market_id = m.market_id
    WHERE m.game_id = :gid AND m.market_key = :mkey
      AND s.price_american IS NOT NULL
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
    user_book: str,
) -> Priced:
    """Fair value for one leg, anchored on the sharpest book quoting it."""
    rows = (await conn.execute(_LATEST, {"gid": game_id, "mkey": market_key})).mappings().all()

    def matches(r, want_outcome: str) -> bool:
        if r["outcome"].lower() != want_outcome.lower():
            return False
        if line is None:
            return True
        # Spreads are quoted from each side, so the opposite side carries the
        # negated number.
        return r["line"] is not None and abs(abs(r["line"]) - abs(line)) < 0.01

    by_book: dict[str, dict[str, dict]] = {}
    for r in rows:
        by_book.setdefault(r["bookmaker"], {})[r["outcome"].lower()] = r

    # The other side of this leg, needed to strip the vig.
    sides = {r["outcome"].lower() for r in rows}
    other = next((s for s in sides if s != outcome.lower()), None)

    fair = anchor = None
    if other:
        for book in ANCHOR_BOOKS:
            quotes = by_book.get(book, {})
            a, b = quotes.get(outcome.lower()), quotes.get(other)
            if a and b and matches(a, outcome) and a["implied_prob"] and b["implied_prob"]:
                fair = _devig_pair(a["implied_prob"], b["implied_prob"])
                anchor = book
                break

    mine = by_book.get(user_book, {}).get(outcome.lower())
    if mine and not matches(mine, outcome):
        mine = None
    book_implied = mine["implied_prob"] if mine else None
    captured = mine["captured_at"] if mine else None
    stale = ((datetime.now(timezone.utc) - captured).total_seconds()
             if captured else None)

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
    )
