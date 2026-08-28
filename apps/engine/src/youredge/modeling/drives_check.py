"""Cross-check stored drive results against an independent derivation.

Two ways of knowing the same thing, which is the point. NCAAF drives are ingested
from CFBD's /drives endpoint, where the outcome arrives pre-labelled. Once college
plays carry scoring and turnover flags, the same outcome can be derived from the
plays themselves — the way the NFL does it — and the two must agree.

This does not write. Overwriting the ingested rows with a derivation would throw
away the more authoritative source and leave nothing to check against; the value
here is precisely that the two are independent. Disagreement is a bug report:
either the playType map is wrong, or drive numbering is misaligned, or CFBD
mislabelled a possession.

    docker compose run --rm ingest python -m youredge.modeling.drives_check --league ncaaf
"""

import argparse
import asyncio
import logging

from sqlalchemy import text

from youredge.db import get_engine

log = logging.getLogger(__name__)

# Mirrors the precedence in modeling/drives.py: turnovers outrank the touchdown
# flag, because a drive ends at whichever came first and a TD alongside an
# interception is the return score.
_COMPARE = text("""
    WITH derived AS (
        SELECT p.game_id, p.drive_num,
               CASE
                   WHEN bool_or(p.interception)        THEN 'INT'
                   WHEN bool_or(p.fumble_lost)         THEN 'FUMBLE_LOST'
                   -- Offensive touchdowns only. A punt- or interception-return
                   -- score also sets p.touchdown, and counting it here would
                   -- read the possession as the offence scoring when the drive
                   -- in fact ended in a punt or a turnover.
                   WHEN bool_or(p.touchdown AND p.play_type_raw IN
                                ('Rushing Touchdown', 'Passing Touchdown'))
                                                       THEN 'TD'
                   WHEN bool_or(p.field_goal_result = 'made')  THEN 'FG_MADE'
                   WHEN bool_or(p.safety)              THEN 'SAFETY'
                   WHEN bool_or(p.field_goal_result IS NOT NULL) THEN 'FG_MISS'
                   WHEN bool_or(p.play_type = 'punt')  THEN 'PUNT'
                   ELSE NULL          -- no outcome play: DOWNS or clock, not decidable here
               END AS derived_result
        FROM plays p
        JOIN games g ON g.game_id = p.game_id
        WHERE g.league = :league AND p.drive_num IS NOT NULL
          AND p.play_type_raw IS NOT NULL
        GROUP BY p.game_id, p.drive_num
    )
    SELECT d.result AS stored, x.derived_result AS derived, count(*) AS n
    FROM drives d
    JOIN derived x ON x.game_id = d.game_id AND x.drive_num = d.drive_num
    WHERE x.derived_result IS NOT NULL
    GROUP BY 1, 2
    ORDER BY 3 DESC
""")


async def check(league: str) -> float:
    engine = get_engine()
    async with engine.connect() as conn:
        rows = (await conn.execute(_COMPARE, {"league": league})).mappings().all()

    if not rows:
        log.warning("%s: nothing to compare — are play_type_raw flags loaded?", league)
        return 0.0

    total = sum(r["n"] for r in rows)
    agreed = sum(r["n"] for r in rows if r["stored"] == r["derived"])
    log.info("%s: %d comparable drives, %.2f%% agreement", league, total,
             100 * agreed / total)

    disagreements = [r for r in rows if r["stored"] != r["derived"]]
    if disagreements:
        log.info("  disagreements, largest first:")
        for r in sorted(disagreements, key=lambda r: -r["n"])[:12]:
            log.info("    stored=%-12s derived=%-12s %6d  (%.2f%%)",
                     r["stored"], r["derived"], r["n"], 100 * r["n"] / total)
    return 100 * agreed / total


async def main(leagues: list[str]):
    for lg in leagues:
        await check(lg)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", nargs="+", default=["ncaaf"])
    args = parser.parse_args()
    asyncio.run(main(args.league))
