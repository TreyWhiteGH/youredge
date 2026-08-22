"""NFL closing lines + final scores from nflverse schedules.

Two gaps this closes, both blocking any trained model:
  - `games.home_score`/`away_score` were never populated for NFL (the PBP ingest
    only wrote status='final'), so margins couldn't be computed at all.
  - We had zero historical NFL odds — every NFL row in odds_snapshots was a 2026
    opener from live polling. Without a market baseline there is nothing honest to
    train against, since "beat the closing line" is the only target that matters.

nflverse ships both inside load_schedules(), free, so this costs no API budget.

Line convention matches the CFBD historical rows already in the table: the home
side carries a negative line when favored. nflverse's `spread_line` uses the
opposite sign (positive = home favored), so it is negated on the way in.

Stored as bookmaker 'nflverse:closing' with captured_at = kickoff, mirroring how
CFBD closing lines are stored, so de-vig and CLV queries treat them uniformly.

Usage:
    docker compose run --rm ingest python -m youredge.ingest.nfl_lines --seasons 2023 2024 2025
"""

import argparse
import asyncio
import logging

import nflreadpy as nfl
import pandas as pd
from sqlalchemy import text

from youredge.db import get_engine
from youredge.ingest.odds_poller import american_to_implied

log = logging.getLogger(__name__)

BOOKMAKER = "nflverse:closing"


def _f(v):
    return None if pd.isna(v) else float(v)


def _i(v):
    return None if pd.isna(v) else int(v)


async def ingest_lines(seasons: list[int]) -> dict:
    sched = nfl.load_schedules(seasons=seasons).to_pandas()
    sched = sched[sched.result.notna()]  # played games only
    log.info("nflverse schedules %s: %d completed games", seasons, len(sched))

    engine = get_engine()
    stats = {"scores": 0, "markets": 0, "snapshots": 0, "missing_game": 0}

    async with engine.begin() as conn:
        known = {r[0] for r in await conn.execute(
            text("SELECT game_id FROM games WHERE league='nfl'"))}

        for g in sched.itertuples(index=False):
            gid = f"nfl:{g.game_id}"
            if gid not in known:
                stats["missing_game"] += 1
                continue

            # Historical NFL games also have no kickoff (the PBP ingest never set
            # one), and closing lines are stamped at kickoff, so derive it here.
            gametime = g.gametime if isinstance(g.gametime, str) and g.gametime else "00:00"
            kickoff = pd.Timestamp(f"{g.gameday} {gametime}",
                                   tz="America/New_York").to_pydatetime()

            # ---- final scores + kickoff (previously absent for every NFL game) ----
            await conn.execute(
                text("""
                    UPDATE games SET home_score = :hs, away_score = :as_,
                                     status = 'final',
                                     kickoff = COALESCE(games.kickoff, :kick)
                    WHERE game_id = :gid
                """),
                {"gid": gid, "hs": _i(g.home_score), "as_": _i(g.away_score),
                 "kick": kickoff},
            )
            stats["scores"] += 1

            home, away = f"nfl:{g.home_team}", f"nfl:{g.away_team}"
            spread, total = _f(g.spread_line), _f(g.total_line)

            # (market_key, outcome, line, american price)
            legs: list[tuple[str, str, float | None, int | None]] = []
            if spread is not None:
                # nflverse: positive = home favored. Ours: favored side is negative.
                legs.append(("spreads", home, -spread, _i(g.home_spread_odds)))
                legs.append(("spreads", away, spread, _i(g.away_spread_odds)))
            if total is not None:
                legs.append(("totals", "over", total, _i(g.over_odds)))
                legs.append(("totals", "under", total, _i(g.under_odds)))
            if _i(g.home_moneyline) is not None:
                legs.append(("h2h", home, None, _i(g.home_moneyline)))
            if _i(g.away_moneyline) is not None:
                legs.append(("h2h", away, None, _i(g.away_moneyline)))

            for market_key, outcome, line, price in legs:
                market_id = (await conn.execute(
                    text("""
                        INSERT INTO markets (game_id, bookmaker, market_key)
                        VALUES (:gid, :bm, :mk)
                        ON CONFLICT (game_id, bookmaker, market_key, player_id) DO UPDATE
                          SET market_key = EXCLUDED.market_key
                        RETURNING market_id
                    """),
                    {"gid": gid, "bm": BOOKMAKER, "mk": market_key},
                )).scalar_one()
                stats["markets"] += 1

                res = await conn.execute(
                    text("""
                        INSERT INTO odds_snapshots
                            (market_id, captured_at, outcome, line, price_american, implied_prob)
                        VALUES (:mid, :at, :outcome, :line, :price, :implied)
                        ON CONFLICT (market_id, captured_at, outcome) DO NOTHING
                    """),
                    {"mid": market_id, "at": kickoff, "outcome": outcome, "line": line,
                     "price": price,
                     "implied": american_to_implied(price) if price is not None else None},
                )
                stats["snapshots"] += res.rowcount

    return stats


async def main(seasons: list[int]):
    stats = await ingest_lines(seasons)
    log.info("scores set: %d | markets: %d | snapshots: %d | games not in db: %d",
             stats["scores"], stats["markets"], stats["snapshots"], stats["missing_game"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, default=[2023, 2024, 2025])
    args = parser.parse_args()
    asyncio.run(main(args.seasons))
