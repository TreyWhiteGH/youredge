"""Score the play-text parser against real play-level attribution.

The parser exists because CFBD's /plays/stats covers SEC and ACC only. Those two
conferences are also what makes it checkable: for 790 games we have both the text
and the ground truth, so the parser can be measured on a quarter of the data
before it is trusted on the rest.

Nothing here writes. It answers one question — if we had used the text instead of
the feed, how often would we have named the right player? — and reports precision
and recall per role, plus what the mistakes look like.

    docker compose run --rm ingest python -m youredge.ingest.validate_playtext

Roles map onto /plays/stats stat types like this:

    rusher      -> Rush
    receiver    -> Reception
    passer      -> Completion / Incompletion / Interception Thrown / Sack Taken
    sacker      -> Sack
    interceptor -> Interception
"""

import argparse
import asyncio
import collections
import logging

from sqlalchemy import text

from youredge.db import get_engine
from youredge.ingest.playtext import (
    INTERCEPTOR, PASSER, RECEIVER, RUSHER, SACKER, load_roster, parse,
)

log = logging.getLogger(__name__)

ROLE_STATS = {
    RUSHER: {"Rush"},
    # Receptions only. Targets are deliberately excluded from the score: CFBD
    # names the intended receiver on just 9% of incompletions, so target recall
    # measures the source text's silence rather than this parser's accuracy.
    RECEIVER: {"Reception"},
    PASSER: {"Completion", "Incompletion", "Interception Thrown", "Sack Taken"},
    SACKER: {"Sack"},
    INTERCEPTOR: {"Interception"},
}
# Offensive roles belong to the team with the ball; the other two to the defence.
DEFENSIVE_ROLES = {SACKER, INTERCEPTOR}


_SAMPLE = text("""
    SELECT p.game_id, p.source_play_id, p.play_text, p.posteam_id, p.defteam_id
    FROM plays p
    WHERE p.play_text IS NOT NULL
      AND EXISTS (SELECT 1 FROM play_players pp WHERE pp.game_id = p.game_id)
    -- Ordered, because an unordered LIMIT samples a different set every run and
    -- two scores taken from different plays cannot be compared. Without this the
    -- harness cannot tell a regression from a reshuffle.
    ORDER BY p.game_id, p.source_play_id
    LIMIT :lim
""")

_TRUTH = text("""
    SELECT game_id, source_play_id, player_id, stat_type
    FROM play_players
    WHERE player_id IS NOT NULL
""")


async def run(limit: int) -> None:
    engine = get_engine()
    async with engine.connect() as conn:
        roster = await load_roster(conn)
        plays = (await conn.execute(_SAMPLE, {"lim": limit})).mappings().all()
        truth_rows = (await conn.execute(_TRUTH)).all()

    if not plays:
        log.error("no plays with text on ground-truth games — is plays.play_text loaded?")
        return

    truth: dict[tuple[str, str], set[tuple[str, str]]] = collections.defaultdict(set)
    for gid, pid, player, stat in truth_rows:
        truth[(gid, pid)].add((player, stat))

    tp = collections.Counter()
    fp = collections.Counter()
    fn = collections.Counter()
    unresolved = collections.Counter()
    unscored = collections.Counter()
    examples: list[str] = []

    for p in plays:
        key = (p["game_id"], p["source_play_id"])
        actual = truth.get(key)
        if not actual:
            continue

        predicted: set[tuple[str, str]] = set()
        for role, name in parse(p["play_text"]):
            team = p["defteam_id"] if role in DEFENSIVE_ROLES else p["posteam_id"]
            pid = roster.resolve(team, name) if team else None
            if pid is None:
                unresolved[role] += 1
                if len(examples) < 8:
                    examples.append(f"[{role}] {name!r} on {team} — {p['play_text'][:70]}")
                continue
            predicted.add((pid, role))

        for role, stats in ROLE_STATS.items():
            want = {player for player, stat in actual if stat in stats}
            got = {player for player, r in predicted if r == role}
            if not want:
                # The feed says nothing about this role on this play, and silence
                # is not disagreement. It records the quarterback's 'Sack Taken'
                # on 3,033 of 3,160 sacks but names the defender on only 2,295 —
                # scoring those 738 as errors measured the feed's gaps, not the
                # parser's, and put sacker precision at 32% when the parse was
                # right. Counted separately instead.
                unscored[role] += len(got)
                continue
            tp[role] += len(want & got)
            fp[role] += len(got - want)
            fn[role] += len(want - got)

    log.info("scored %d plays against ground truth\n", len(plays))
    log.info("%-12s %8s %8s %8s   %9s %9s", "role", "tp", "fp", "fn", "precision", "recall")
    for role in ROLE_STATS:
        t, f, n = tp[role], fp[role], fn[role]
        prec = t / (t + f) if t + f else 0.0
        rec = t / (t + n) if t + n else 0.0
        log.info("%-12s %8d %8d %8d   %8.1f%% %8.1f%%", role, t, f, n, 100 * prec, 100 * rec)

    T, F, N = sum(tp.values()), sum(fp.values()), sum(fn.values())
    log.info("\n%-12s %8d %8d %8d   %8.1f%% %8.1f%%", "OVERALL", T, F, N,
             100 * T / (T + F) if T + F else 0, 100 * T / (T + N) if T + N else 0)

    if unscored:
        log.info("\npredictions on plays where the feed names nobody for that role")
        log.info("(not scored either way — the feed is silent, not contradicting): %s",
                 dict(unscored))

    if unresolved:
        log.info("\nnames parsed but not resolved to a roster: %s", dict(unresolved))
        for e in examples:
            log.info("    %s", e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20000)
    args = ap.parse_args()
    asyncio.run(run(args.limit))
