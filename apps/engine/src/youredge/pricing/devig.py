"""De-vig: strip bookmaker margin from snapshot implied probabilities.

Multiplicative method: within one priced snapshot group (market_id, captured_at),
fair_i = implied_i / sum(implied). Correct for 2-way markets and a sane baseline
for h2h with extreme favorites; power-method and Pinnacle anchoring are Phase 2
refinements (see ROADMAP "De-vig module").

Groups are skipped when any side is missing (n < 2) or unpriced (CFBD historical
spreads/totals carry lines without juice — their implied_prob is NULL).

Usage (backfill):
    docker compose run --rm ingest python -m youredge.pricing.devig
"""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from youredge.db import get_engine

log = logging.getLogger(__name__)

_DEVIG = text("""
    WITH grp AS (
        SELECT market_id, captured_at,
               SUM(implied_prob) AS overround,
               COUNT(*) AS n
        FROM odds_snapshots
        WHERE implied_prob IS NOT NULL AND fair_prob IS NULL
        GROUP BY market_id, captured_at
    )
    UPDATE odds_snapshots s
    SET fair_prob = s.implied_prob / g.overround
    FROM grp g
    WHERE s.market_id = g.market_id
      AND s.captured_at = g.captured_at
      AND s.implied_prob IS NOT NULL
      AND s.fair_prob IS NULL
      AND g.n >= 2
      AND g.overround > 0
""")


async def devig_snapshots(conn: AsyncConnection) -> int:
    """Fill fair_prob for every complete, priced, not-yet-devigged snapshot group."""
    result = await conn.execute(_DEVIG)
    return result.rowcount


async def main():
    engine = get_engine()
    async with engine.begin() as conn:
        n = await devig_snapshots(conn)
    log.info("fair_prob filled on %d snapshots", n)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
