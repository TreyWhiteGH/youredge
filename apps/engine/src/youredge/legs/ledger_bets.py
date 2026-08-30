"""Record every critiqued slip, and settle it once the game is over.

Two things this exists for, and only one of them is obvious.

The obvious one is closing-line value. A recommendation is only honestly
assessed against the number the market closed at, and that number cannot be
reconstructed after kickoff — so the price at recommendation time has to be
written down when it is offered, not worked out later.

The second is the reason it matters more. No API sells book *SGP* quotes, so the
central product claim — that a book charges you less for correlation than it is
worth — has no data behind it that can be bought. What it can have is data that
is collected: when someone pastes the price off their slip, that one field is a
real SGP quote from a real book, paired with our own per-leg fair values. The
ratio between the two is the book's haircut, and a few hundred of them is enough
to fit one per book. That is what eventually lets Generate estimate a quote
without anyone pasting anything.

So the row stores the independence price alongside the quote. Independence is
not what a parlay is worth — legs in one game are correlated, which is the whole
premise — but it is a fixed, computable reference, and a haircut measured
against a moving reference teaches nothing.
"""

import json
import logging
from typing import Any

from sqlalchemy import text

log = logging.getLogger(__name__)

# There is no auth yet. Writing a constant is better than not writing the row:
# the analysis this feeds is per-book, not per-person, and a user column can be
# backfilled from a session when there is one to backfill from.
LOCAL_USER = "local"

_INSERT = text("""
    INSERT INTO user_bets (user_id, game_id, bookmaker, mode, legs,
                           quoted_price_american, fair_prob_at_rec, edge_at_rec)
    VALUES (:user, :gid, :book, :mode, CAST(:legs AS jsonb),
            :quoted, :fair, :edge)
    RETURNING bet_id
""")


def american_to_prob(price: int) -> float:
    return (-price / (-price + 100)) if price < 0 else (100 / (price + 100))


def prob_to_american(p: float) -> int | None:
    """Inverse, for reporting the independence price in the units books use."""
    if not 0 < p < 1:
        return None
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def parse_american(raw: str | None) -> int | None:
    """A pasted price. Accepts '+650', '650', '-110'; anything else is not a price."""
    if raw is None:
        return None
    t = str(raw).strip().replace(" ", "")
    if t.startswith("+"):
        t = t[1:]
    try:
        v = int(t)
    except ValueError:
        return None
    # Books do not quote inside +/-100; a 0 or a 50 is a typo, not a price.
    return v if abs(v) >= 100 else None


async def record(conn, result: dict[str, Any], *, league: str, sportsbook: str,
                 mode: str = "critique") -> dict[str, Any] | None:
    """Write one critiqued slip. Returns the CLV stub, or None if unpriceable.

    Silent about failure by design: this is bookkeeping running alongside an
    answer the user asked for, and a logging problem must never turn a good
    critique into an error page.
    """
    legs = result.get("legs") or []
    priced = [l for l in legs
              if (l.get("pricing") or {}).get("fair_prob") is not None]
    if not priced:
        return None

    independence = 1.0
    for leg in priced:
        independence *= leg["pricing"]["fair_prob"]

    quoted = parse_american(result.get("quoted_odds"))
    # Positive haircut means the book paid less than independence alone would
    # justify — before any correlation is accounted for, which is the point.
    haircut = None
    if quoted is not None and independence > 0:
        haircut = round(american_to_prob(quoted) / independence - 1, 4)

    payload = [{"raw": l.get("raw"), "template": l.get("template"),
                "side": l.get("side"), "line": l.get("line"),
                "fair_prob": l["pricing"]["fair_prob"],
                "book_price": l["pricing"].get("book_price"),
                "edge": l["pricing"].get("edge"),
                "quotable": l["pricing"].get("quotable")}
               for l in priced]

    try:
        bet_id = (await conn.execute(_INSERT, {
            "user": LOCAL_USER, "gid": result["game_id"], "book": sportsbook,
            "mode": mode, "legs": json.dumps(payload),
            "quoted": quoted,
            "fair": independence,
            # Edge of the slip as quoted against independence. Not the real edge
            # — correlation is missing — but it is the honest arithmetic on the
            # two numbers actually in hand.
            "edge": (american_to_prob(quoted) - independence)
                    if quoted is not None else None,
        })).scalar_one()
    except Exception:
        log.exception("could not record slip for %s", result.get("game_id"))
        return None

    return {
        "bet_id": str(bet_id),
        "legs_priced": len(priced),
        "legs_total": len(legs),
        "independence_prob": round(independence, 4),
        "independence_price_american": prob_to_american(independence),
        "quoted_price_american": quoted,
        "book_haircut_vs_independence": haircut,
        "note": (
            "Independence is a reference, not a fair price — these legs are "
            "correlated, which is the reason to bet them together. The haircut "
            "is recorded so a per-book model can be fitted from real quotes."
        ),
    }


# Closing price and outcome, both of which only exist after the fact. Run from
# the catch-up cycle, where every other after-the-fact repair lives.
_SETTLE = text("""
    UPDATE user_bets b
    SET closing_price_american = c.price,
        result = CASE WHEN c.hits = c.total THEN 'win' ELSE 'loss' END
    FROM (
        SELECT b2.bet_id,
               (SELECT s.price_american
                  FROM markets m JOIN odds_snapshots s USING (market_id)
                 WHERE m.game_id = b2.game_id AND m.bookmaker = b2.bookmaker
                   AND s.is_closing
                 ORDER BY s.captured_at DESC LIMIT 1) AS price,
               count(*) FILTER (WHERE lo.hit) AS hits,
               count(*) AS total
        FROM user_bets b2
        JOIN games g ON g.game_id = b2.game_id AND g.status = 'final'
        CROSS JOIN LATERAL jsonb_array_elements(b2.legs) AS leg
        LEFT JOIN leg_outcomes lo
               ON lo.game_id = b2.game_id
              AND lo.template = leg->>'template'
              AND lo.side = COALESCE(leg->>'side', '')
        WHERE b2.result IS NULL
        GROUP BY b2.bet_id, b2.game_id, b2.bookmaker
        -- Every leg has to resolve. A slip settled on a partial read is worse
        -- than one left open, because it enters the record as a fact.
        HAVING count(*) = count(lo.hit)
    ) c
    WHERE b.bet_id = c.bet_id
""")


async def settle(conn) -> int:
    n = (await conn.execute(_SETTLE)).rowcount
    if n:
        log.info("settled %d recorded slips", n)
    return n
