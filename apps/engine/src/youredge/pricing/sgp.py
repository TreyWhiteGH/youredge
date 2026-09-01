"""Estimate what a book will quote for a same-game parlay.

Three quantities, and keeping them separate is the whole design:

  1. **Independence** — the legs' fair probabilities multiplied. Wrong on
     purpose: legs in one game are correlated, which is the reason to bet them
     together. It is the reference everything else is measured against.
  2. **The joint** — independence corrected by how often these legs actually
     landed together, from the counted pair surface. This is the model's claim.
  3. **The book's margin** — what it charges on top of the joint. Fitted from
     real quotes where there are enough, and a stated prior where there are not.

A quote is `joint x (1 + margin)` expressed as a price. Splitting it this way
means a bad estimate can be attributed: if the joint is right and the quote is
off, the margin model is wrong; if both legs are priced right and the joint is
off, the correlation is.

**Composition beyond two legs is an approximation, and bounded rather than
trusted.** Multiplying every pairwise lift triple-counts shared dependence and
explodes: three legs each lifting 1.3 would come out at 2.2x independence, which
is not a probability anyone should act on. The pairwise log-lifts are scaled by
2/n so each leg contributes its average relationship once, and the result is then
clamped to the Frechet-Hoeffding bounds -- the joint cannot exceed its least
likely leg, and cannot fall below the sum of the marginals minus (n-1). Those are
exact for any dependence structure, so the estimate is wrong inside a range that
is provably right.
"""

import logging
from typing import Any, Sequence

from sqlalchemy import text

from youredge.pricing.implications import entailed

log = logging.getLogger(__name__)

# Per-leg hold used until a book has enough observed quotes to fit. Books charge
# noticeably more on a same-game parlay than on the straights inside it; 4.5% a
# leg compounds to ~9% on two and ~19% on four, which is the band the public
# numbers sit in. It is a placeholder with a number attached, not a measurement.
PRIOR_LEG_MARGIN = 0.045
# Below this many observed quotes for a (book, leg-count) cell, the prior stands.
MIN_QUOTES_TO_FIT = 12

_PAIR = text("""
    SELECT lift, n FROM leg_pair_stats
    WHERE league = :lg AND script_tag = ''
      AND template_a = :ta AND side_a = :sa
      AND template_b = :tb AND side_b = :sb
""")

# A lift measured on a handful of games is a rumour, and using it moves the
# estimate on noise. Below this the pair is treated as independent and said to be.
MIN_PAIR_N = 200


def frechet_bounds(probs: Sequence[float]) -> tuple[float, float]:
    """The range a joint probability can occupy given only its marginals."""
    lo = max(0.0, sum(probs) - (len(probs) - 1))
    return lo, min(probs)


async def estimate_joint(conn, league: str,
                         legs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Independence, the correlation correction, and the bounded joint."""
    import math

    # A leg that cannot fail given the others contributes a probability of one,
    # and must not contribute a correlation term either -- pairing a certainty
    # with anything produces a lift that is really just the certainty. Removing
    # it before any of the arithmetic is what makes a three-leg slip price as
    # its two-leg core, which is what the books do.
    implied = entailed(legs)
    core = [l for i, l in enumerate(legs) if i not in implied]
    if len(core) < 2:
        core = list(legs)
        implied = {}

    probs = [float(l["fair_prob"]) for l in core]
    independence = math.prod(probs)
    n = len(probs)
    legs = core

    pairs, log_lift = [], 0.0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = legs[i], legs[j]
            # A leg with no template has no counted surface -- an anytime
            # touchdown, or a prop on someone who is not his team's primary at
            # the position. It is priced perfectly well and simply cannot be
            # correlated, so it is reported as independent rather than sorted
            # against a string it is not.
            if a.get("template") is None or b.get("template") is None:
                pairs.append({
                    "legs": [a.get("raw"), b.get("raw")], "lift": None, "n": 0,
                    "used": False,
                    "note": ("no counted surface for one of these legs, so they "
                             "are treated as independent — which understates a "
                             "real relationship rather than inventing one"),
                })
                continue
            key = sorted([(a["template"], a["side"]), (b["template"], b["side"])])
            row = (await conn.execute(_PAIR, {
                "lg": league, "ta": key[0][0], "sa": key[0][1],
                "tb": key[1][0], "sb": key[1][1]})).mappings().first()
            lift = row["lift"] if row and row["n"] >= MIN_PAIR_N else None
            pairs.append({
                "legs": [a.get("raw"), b.get("raw")],
                "lift": round(lift, 3) if lift else None,
                "n": row["n"] if row else 0,
                "used": bool(lift and lift > 0),
            })
            if lift and lift > 0:
                log_lift += math.log(lift)

    # 2/n so each leg contributes its average pairwise relationship once rather
    # than once per partner. Exact for two legs; damped, deliberately, above.
    scaled = math.exp((2.0 / n) * log_lift) if n > 1 else 1.0
    raw = independence * scaled
    lo, hi = frechet_bounds(probs)
    joint = min(max(raw, lo), hi)

    return {
        "independence": independence,
        "correlation_multiplier": round(scaled, 4),
        "joint": joint,
        "joint_before_bounds": round(raw, 6),
        "bounded": not (lo <= raw <= hi),
        "frechet_low": round(lo, 6), "frechet_high": round(hi, 6),
        "pairs": pairs,
        "pairs_used": sum(1 for p in pairs if p["used"]),
        "entailed_legs": list(implied.values()),
    }


_FIT = text("""
    SELECT game_id, quoted_price_american AS quoted, legs
    FROM user_bets
    WHERE bookmaker = :book AND quoted_price_american IS NOT NULL
""")


async def book_margin(conn, league: str, book: str, n_legs: int) -> dict[str, Any]:
    """What this book charges over the joint, measured if possible.

    Measured against the *joint*, and that distinction is not pedantic. Fitting
    against independence produced a "margin" of 120% for DraftKings at three
    legs — no book holds 120%. What it had actually absorbed was the
    correlation, and on slips whose third leg is free it absorbed the entailment
    too: independence over three legs is tiny while the book is pricing a
    two-leg bet, so the ratio exploded and every estimate that used it came out
    far too short.

    So each stored slip is re-run through the same joint estimate a live request
    gets, entailment included, and cells are keyed on the number of legs that
    actually carry risk rather than the number typed in.
    """
    prior = (1 + PRIOR_LEG_MARGIN) ** n_legs - 1
    rows = (await conn.execute(_FIT, {"book": book})).mappings().all()

    ratios = []
    for r in rows:
        legs = [l for l in r["legs"] if l.get("fair_prob")]
        if len(legs) < 2:
            continue
        j = await estimate_joint(conn, league, legs)
        risk = len(legs) - len(j["entailed_legs"])
        if risk != n_legs or not j["joint"]:
            continue
        q = r["quoted"]
        implied = (-q / (-q + 100)) if q < 0 else (100 / (q + 100))
        ratios.append(implied / j["joint"] - 1)

    if len(ratios) < MIN_QUOTES_TO_FIT:
        return {"margin": prior, "basis": "prior", "n_quotes": len(ratios),
                "detail": (f"{len(ratios)} observed quotes carrying {n_legs} "
                           f"legs of risk at {book}; {MIN_QUOTES_TO_FIT} needed "
                           "before the prior is replaced by a measurement")}
    ratios.sort()
    fitted = ratios[len(ratios) // 2]
    # A book cannot hold half the pool. A fit that says so is measuring
    # something other than margin, and the prior is the safer wrong answer.
    if not 0 <= fitted <= 0.5:
        log.warning("%s at %d legs fitted an implausible margin of %.2f; "
                    "keeping the prior", book, n_legs, fitted)
        return {"margin": prior, "basis": "prior_implausible_fit",
                "n_quotes": len(ratios), "rejected_fit": round(fitted, 4)}
    return {"margin": fitted, "basis": "fitted", "n_quotes": len(ratios)}


def prob_to_american(p: float) -> int | None:
    if not 0 < p < 1:
        return None
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


async def estimate(conn, league: str, book: str,
                   legs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """A full estimate: what the slip is worth, and what the book will offer."""
    if len(legs) < 2:
        return {"error": "a parlay needs at least two priced legs"}

    j = await estimate_joint(conn, league, legs)
    # The margin is charged on the legs that carry risk. A free leg does not
    # make a book hold more, so counting it here would reintroduce through the
    # margin exactly what the implication check just removed.
    n_priced = len(legs) - len(j["entailed_legs"])
    m = await book_margin(conn, league, book, max(n_priced, 2))
    quoted_prob = min(j["joint"] * (1 + m["margin"]), 0.999)

    return {
        "legs": len(legs),
        "legs_carrying_risk": n_priced,
        "entailed_legs": j["entailed_legs"],
        "independence_price": prob_to_american(j["independence"]),
        "fair_price": prob_to_american(j["joint"]),
        "estimated_book_price": prob_to_american(quoted_prob),
        "joint": round(j["joint"], 5),
        "independence": round(j["independence"], 5),
        "correlation_multiplier": j["correlation_multiplier"],
        "bounded_by_frechet": j["bounded"],
        "pairs": j["pairs"],
        "pairs_used": j["pairs_used"],
        "margin": {"value": round(m["margin"], 4), **{k: v for k, v in m.items()
                                                      if k != "margin"}},
        "how_to_read": (
            "fair_price is what the slip is worth if the counted correlation is "
            "right. estimated_book_price is that plus what this book is expected "
            "to charge. Check the second against the book and the gap tells you "
            "which half to distrust."
        ),
    }
