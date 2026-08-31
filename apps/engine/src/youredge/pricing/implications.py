"""Legs that are already decided by other legs — free ones, and impossible ones.

Correlation is not the only relationship between two legs in one game. Some
combinations are arithmetic: given the others, a leg cannot fail, or cannot
possibly land. No amount of counting finds that, because it is a fact about
scoring rather than about football — the empirical surface only ever sees how
often two things happened together, and it called a certainty a 1.52 lift.

Two cases, both from the same algebra.

**Free.** Seattle -3.5 with over 44.5 means winning by at least 4 in a game
reaching at least 45, so Seattle scores at least 25. "Seattle team total over
24.5" is then certain, and DraftKings quotes the three-leg parlay at exactly the
two-leg price because the third leg costs it nothing.

**Impossible.** Swap that total to *under* 44.5 and the same addition runs the
other way: at most 44 points in a game won by at least 4 means Seattle scores at
most 24. Now "Seattle team total over 24.5" cannot happen. The slip is not
expensive, it is dead, and the only honest answer is to refuse it rather than
quote a long price on a bet that cannot win.

Rather than derive each case in algebra — where a sign error is silent and
plausible — every leg is turned into a predicate over a final score and the
whole grid of realistic scores is checked. A slip is impossible when no score
satisfies it, and a leg is free when no score satisfies the others while
violating it. That is exact, needs no case analysis, and extends to any leg that
can be written as a condition on the final score.
"""

from typing import Any, Callable, Sequence

# Every plausible final score. Football scores are integers, which is doing real
# work: 2h > 48 alone gives h > 24, which does not settle a 24.5 line, but whole
# numbers make it h >= 25, which does.
_MAX_SCORE = 100
_SCORES = [(h, a) for h in range(_MAX_SCORE + 1) for a in range(_MAX_SCORE + 1)]


def predicate(leg: dict[str, Any]) -> Callable[[int, int], bool] | None:
    """Turn a leg into a test on (home score, away score), or None if it is not
    a condition on the final score at all — a player prop, for instance, which
    this says nothing about and must not pretend to."""
    t, side, line = leg["template"], leg.get("side"), leg.get("line")

    if t == "SPREAD" and line is not None:
        need = -float(line)          # a leg's line is written from its own side
        if side == "home":
            return lambda h, a: (h - a) > need
        if side == "away":
            return lambda h, a: (a - h) > need
    if t == "MONEYLINE":
        if side == "home":
            return lambda h, a: h > a
        if side == "away":
            return lambda h, a: a > h
    if t == "TOTAL" and line is not None:
        v = float(line)
        if side == "over":
            return lambda h, a: (h + a) > v
        if side == "under":
            return lambda h, a: (h + a) < v
    if t == "TEAM_TOTAL" and line is not None and side:
        v = float(line)
        team, _, direction = side.rpartition("_")
        if team == "home":
            return (lambda h, a: h > v) if direction == "over" else (lambda h, a: h < v)
        if team == "away":
            return (lambda h, a: a > v) if direction == "over" else (lambda h, a: a < v)
    return None


def analyse(legs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Which legs are free, and whether the slip can happen at all."""
    preds = [(i, predicate(l)) for i, l in enumerate(legs)]
    scoreable = [(i, p) for i, p in preds if p is not None]
    if len(scoreable) < 2:
        return {"impossible": False, "entailed": {}}

    def satisfies(hb, ab, skip: int | None = None) -> bool:
        return all(p(hb, ab) for i, p in scoreable if i != skip)

    feasible = [(h, a) for h, a in _SCORES if satisfies(h, a)]
    if not feasible:
        return {
            "impossible": True, "entailed": {},
            "reason": ("no final score satisfies every leg at once — these "
                       "conditions contradict each other, so the slip cannot "
                       "win at any price"),
        }

    # Removed one at a time, re-checking against what is left, because
    # entailment is not simultaneous. On a four-leg slip both the total and one
    # team total can each be implied by the other three, yet dropping both at
    # once is only safe if the two that remain still imply them. Greedy removal
    # guarantees that by construction: every leg taken out was implied by the
    # legs still standing at the moment it went.
    remaining = [i for i, _ in scoreable]
    entailed: dict[int, str] = {}
    changed = True
    while changed and len(remaining) > 2:
        changed = False
        for i in list(remaining):
            others = [j for j in remaining if j != i]
            pred_i = dict(scoreable)[i]

            def ok(h, a, keep=others):
                return all(dict(scoreable)[j](h, a) for j in keep)

            if all(pred_i(h, a) for h, a in _SCORES if ok(h, a)):
                entailed[i] = (
                    f"{legs[i].get('raw', 'this leg')} cannot fail once the "
                    f"other legs land — it is already implied by them, and a "
                    f"book charges nothing for it"
                )
                remaining = others
                changed = True
                break
    return {"impossible": False, "entailed": entailed}


def entailed(legs: Sequence[dict[str, Any]]) -> dict[int, str]:
    """Backwards-compatible view: just the free legs."""
    return analyse(legs)["entailed"]
