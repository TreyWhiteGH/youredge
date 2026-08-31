"""Legs that are already implied by other legs.

Correlation is not the only relationship between two legs in one game. Some
combinations are arithmetic: given the others, a leg cannot fail, and no amount
of counting will discover that because it is a fact about scoring rather than
about football.

The case that exposed it. Seattle -3.5 with over 44.5 means Seattle wins by at
least 4 and the game reaches at least 45. Add those:

    (h - a) >= 4  and  (h + a) >= 45   =>   2h >= 49   =>   h >= 25

So "Seattle team total over 24.5" is certain once the first two legs are on the
slip. DraftKings quotes the three-leg parlay at exactly the two-leg price,
because the third leg is free. The empirical surface, which only ever sees how
often two things happened together, called it a 1.52 lift and priced the parlay
far too long.

Integer scoring is doing real work here. `2h > 48` alone gives h > 24, which does
not settle a 24.5 line — but football scores are whole numbers, so h > 24 means
h >= 25, and that does. Every bound below is tightened to the next attainable
score for the same reason.

What this deliberately does not do is decide anything about *near*-implications.
A leg that is 95% certain given the others is a correlation, and correlation is
already counted. Only the legs that cannot fail are collapsed here.
"""

import math
from typing import Any, Sequence


def _spread_constraint(leg: dict[str, Any]) -> tuple[str, float] | None:
    """(side, margin) — that side wins by more than `margin`."""
    if leg["template"] == "SPREAD" and leg.get("line") is not None:
        side = leg["side"]
        line = float(leg["line"])
        # A leg's line is written from its own side, so the margin it needs is
        # simply its negation: -3.5 must win by more than 3.5, +2.5 may lose by
        # up to 2.5.
        return side, -line
    if leg["template"] == "MONEYLINE":
        return leg["side"], 0.0
    return None


def entailed(legs: Sequence[dict[str, Any]]) -> dict[int, str]:
    """Indices of legs that cannot fail given the others, and why.

    Only forward implications from a spread (or moneyline) plus a game total
    onto a team total are derived. That is the combination that actually appears
    on slips and the one books charge nothing for; anything more exotic is left
    to the counted surface rather than guessed at with more algebra.
    """
    out: dict[int, str] = {}

    totals = [(i, l) for i, l in enumerate(legs)
              if l["template"] == "TOTAL" and l.get("line") is not None]
    spreads = [(i, l) for i, l in enumerate(legs) if _spread_constraint(l)]
    team_totals = [(i, l) for i, l in enumerate(legs)
                   if l["template"] == "TEAM_TOTAL" and l.get("line") is not None]
    if not (totals and spreads and team_totals):
        return out

    for ti, tleg in totals:
        if tleg["side"] != "over":
            continue
        total = float(tleg["line"])
        for si, sleg in spreads:
            side, margin = _spread_constraint(sleg)
            for tti, ttleg in team_totals:
                tt_side, tt_dir = ttleg["side"].rsplit("_", 1)
                if tt_dir != "over" or tt_side != side:
                    continue
                # That side scores more than (total + margin) / 2, and scores
                # are integers, so it scores at least the next whole number up.
                bound = (total + margin) / 2
                floor_score = math.floor(bound) + 1
                if float(ttleg["line"]) < floor_score:
                    out[tti] = (
                        f"implied by {sleg['raw']} and {tleg['raw']}: winning by "
                        f"more than {margin:g} in a game of more than {total:g} "
                        f"means scoring at least {floor_score}, which clears "
                        f"{ttleg['line']:g}"
                    )
    return out
