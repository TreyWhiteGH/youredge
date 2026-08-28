"""Build leg_pair_stats: how often two legs won together.

The end of Layer B. Every pair of leg templates is counted over the games where
both were evaluable, giving P(A), P(B), P(A and B), the phi coefficient and the
lift over independence — unconditionally and again within each script.

    docker compose run --rm ingest python -m youredge.legs.pairs

What this can and cannot support is worth being blunt about, because the
temptation runs the other way.

It CAN say: these two legs move together, this pair is redundant, this third leg
wants a different game than the other two, and here is the sample behind each
claim. That is enough to critique a slip.

It CANNOT price a parlay. The marginals here are historical base rates, not this
game's fair probabilities, and most of the lines are synthetic. Turning P(A and B)
into an expected value would be quoting a number the data does not contain. That
waits for the simulator, and the disagreement between the two is the point.
"""

import argparse
import asyncio
import logging

from sqlalchemy import text

from youredge.db import get_engine

log = logging.getLogger(__name__)

# Below this a correlation is noise dressed as a finding.
MIN_PAIR_GAMES = 60

_BUILD = text(f"""
    WITH ctx AS (
        -- Unconditional, plus one context per script the game landed in.
        SELECT lo.game_id, g.league, '' AS script_tag,
               lo.template, lo.side, lo.hit
        FROM leg_outcomes lo JOIN games g USING (game_id)
        WHERE lo.hit IS NOT NULL
        UNION ALL
        SELECT lo.game_id, g.league, t.slug,
               lo.template, lo.side, lo.hit
        FROM leg_outcomes lo
        JOIN games g USING (game_id)
        JOIN taggings tg ON tg.entity_type = 'game' AND tg.entity_id = lo.game_id
        JOIN tags t ON t.tag_id = tg.tag_id AND t.dimension = 'script'
        WHERE lo.hit IS NOT NULL
    ),
    pairs AS (
        SELECT a.league, a.script_tag,
               a.template AS template_a, a.side AS side_a,
               b.template AS template_b, b.side AS side_b,
               count(*) AS n,
               avg(a.hit::int) AS p_a,
               avg(b.hit::int) AS p_b,
               avg((a.hit AND b.hit)::int) AS p_ab
        FROM ctx a
        JOIN ctx b
          ON b.game_id = a.game_id AND b.script_tag = a.script_tag
         -- Ordered so each unordered pair is stored once, and a leg is never
         -- paired with itself.
         AND (a.template, a.side) < (b.template, b.side)
        GROUP BY 1, 2, 3, 4, 5, 6
        HAVING count(*) >= {MIN_PAIR_GAMES}
    )
    INSERT INTO leg_pair_stats
        (league, script_tag, template_a, side_a, template_b, side_b,
         n, p_a, p_b, p_ab, phi, lift)
    SELECT league, script_tag, template_a, side_a, template_b, side_b,
           n, p_a, p_b, p_ab,
           -- phi for two binary outcomes. NULL where either leg never varies,
           -- because a constant has no correlation with anything.
           CASE WHEN p_a > 0 AND p_a < 1 AND p_b > 0 AND p_b < 1
                THEN (p_ab - p_a * p_b)
                     / sqrt(p_a * (1 - p_a) * p_b * (1 - p_b))
           END,
           CASE WHEN p_a > 0 AND p_b > 0 THEN p_ab / (p_a * p_b) END
    FROM pairs
    ON CONFLICT (league, script_tag, template_a, side_a, template_b, side_b)
    DO UPDATE SET n = EXCLUDED.n, p_a = EXCLUDED.p_a, p_b = EXCLUDED.p_b,
                  p_ab = EXCLUDED.p_ab, phi = EXCLUDED.phi, lift = EXCLUDED.lift,
                  built_at = now()
""")


async def build() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM leg_pair_stats"))
        n = (await conn.execute(_BUILD)).rowcount
        log.info("%d pair rows\n", n)

        for league in ("nfl", "ncaaf"):
            rows = (await conn.execute(text("""
                SELECT template_a, side_a, template_b, side_b, n, phi, p_ab
                FROM leg_pair_stats
                WHERE league = :lg AND script_tag = '' AND phi IS NOT NULL
                ORDER BY abs(phi) DESC LIMIT 10
            """), {"lg": league})).mappings().all()
            log.info("%s — strongest unconditional relationships", league)
            for r in rows:
                log.info("  %-14s %-12s  %-14s %-12s  n=%4d  phi=%+.2f  P(both)=%.2f",
                         r["template_a"], r["side_a"], r["template_b"], r["side_b"],
                         r["n"], r["phi"], r["p_ab"])
            log.info("")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    argparse.ArgumentParser().parse_args()
    asyncio.run(build())
