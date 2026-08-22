"""As-of feature builder — the correctness foundation for any trained model.

Every feature for a game comes only from games that kicked off before it. The team
cards in tendencies/ deliberately average over a whole window (right for describing a
team, fatal for training), so training gets its own path rather than reusing them.

Two stages:
  1. team_game_form — what each team did in each game (plain aggregation over plays)
  2. game_features  — expanding means over PRIOR games only, joined home vs away,
                      plus the closing line and the realised outcome

Usage:
    docker compose run --rm ingest python -m youredge.modeling.features --league nfl
"""

import argparse
import asyncio
import logging

from sqlalchemy import text

from youredge.db import get_engine

log = logging.getLogger(__name__)

# NCAAF has no qb_dropback (nflverse-only); play_type='pass' already folds in sacks
# and interceptions via cfbd_map, so this reads correctly in both leagues.
_IS_PASS = "COALESCE(p.qb_dropback, p.play_type = 'pass')"

_BUILD_FORM = text(f"""
    INSERT INTO team_game_form (game_id, team_id, opponent_id, league, season, week,
        kickoff, is_home, points_for, points_against, off_epa, off_pass_epa, off_rush_epa,
        off_success, def_epa, def_pass_epa, def_rush_epa, def_success, off_plays, off_pass_rate)
    WITH sides AS (
        SELECT g.game_id, g.league, g.season, g.week, g.kickoff,
               g.home_team_id AS team_id, g.away_team_id AS opponent_id, TRUE AS is_home,
               g.home_score AS pf, g.away_score AS pa
        FROM games g
        WHERE g.league = :league AND g.season = ANY(:seasons) AND g.home_score IS NOT NULL
        UNION ALL
        SELECT g.game_id, g.league, g.season, g.week, g.kickoff,
               g.away_team_id, g.home_team_id, FALSE, g.away_score, g.home_score
        FROM games g
        WHERE g.league = :league AND g.season = ANY(:seasons) AND g.home_score IS NOT NULL
    ),
    off AS (
        SELECT p.game_id, p.posteam_id AS team_id,
               avg(p.epa) AS epa,
               avg(p.epa) FILTER (WHERE {_IS_PASS}) AS pass_epa,
               avg(p.epa) FILTER (WHERE p.play_type = 'run') AS rush_epa,
               avg(p.success::int) AS success,
               count(*) AS plays,
               avg(({_IS_PASS})::int) AS pass_rate
        FROM plays p
        WHERE p.play_type IN ('pass','run') AND p.down IS NOT NULL AND p.posteam_id IS NOT NULL
        GROUP BY 1,2
    ),
    def AS (
        SELECT p.game_id, p.defteam_id AS team_id,
               avg(p.epa) AS epa,
               avg(p.epa) FILTER (WHERE {_IS_PASS}) AS pass_epa,
               avg(p.epa) FILTER (WHERE p.play_type = 'run') AS rush_epa,
               avg(p.success::int) AS success
        FROM plays p
        WHERE p.play_type IN ('pass','run') AND p.down IS NOT NULL AND p.defteam_id IS NOT NULL
        GROUP BY 1,2
    )
    SELECT s.game_id, s.team_id, s.opponent_id, s.league, s.season, s.week, s.kickoff,
           s.is_home, s.pf, s.pa,
           o.epa, o.pass_epa, o.rush_epa, o.success,
           d.epa, d.pass_epa, d.rush_epa, d.success,
           o.plays, o.pass_rate
    FROM sides s
    LEFT JOIN off o ON o.game_id = s.game_id AND o.team_id = s.team_id
    LEFT JOIN def d ON d.game_id = s.game_id AND d.team_id = s.team_id
    ON CONFLICT (game_id, team_id) DO UPDATE SET
        points_for = EXCLUDED.points_for, points_against = EXCLUDED.points_against,
        off_epa = EXCLUDED.off_epa, def_epa = EXCLUDED.def_epa,
        off_pass_epa = EXCLUDED.off_pass_epa, off_rush_epa = EXCLUDED.off_rush_epa,
        def_pass_epa = EXCLUDED.def_pass_epa, def_rush_epa = EXCLUDED.def_rush_epa,
        off_success = EXCLUDED.off_success, def_success = EXCLUDED.def_success,
        off_plays = EXCLUDED.off_plays, off_pass_rate = EXCLUDED.off_pass_rate,
        kickoff = EXCLUDED.kickoff
""")

# ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING is the as-of guarantee: the current
# game is excluded from its own features. Partitioning by season keeps the in-season
# form separate from the prior-season prior.
_BUILD_FEATURES = text("""
    INSERT INTO game_features (game_id, league, season, week, kickoff, home_team_id,
        away_team_id, home_prior_games, away_prior_games,
        home_off_epa, home_def_epa, home_off_pass_epa, home_off_rush_epa,
        home_def_pass_epa, home_def_rush_epa, home_off_success, home_pass_rate,
        away_off_epa, away_def_epa, away_off_pass_epa, away_off_rush_epa,
        away_def_pass_epa, away_def_rush_epa, away_off_success, away_pass_rate,
        home_prev_season_off_epa, home_prev_season_def_epa,
        away_prev_season_off_epa, away_prev_season_def_epa,
        home_rest_days, away_rest_days,
        closing_spread, closing_total, home_margin, total_points,
        spread_residual, total_residual)
    WITH form AS (
        SELECT f.*,
            count(*)      OVER w AS prior_games,
            avg(off_epa)  OVER w AS pri_off_epa,
            avg(def_epa)  OVER w AS pri_def_epa,
            avg(off_pass_epa) OVER w AS pri_off_pass_epa,
            avg(off_rush_epa) OVER w AS pri_off_rush_epa,
            avg(def_pass_epa) OVER w AS pri_def_pass_epa,
            avg(def_rush_epa) OVER w AS pri_def_rush_epa,
            avg(off_success)  OVER w AS pri_off_success,
            avg(off_pass_rate) OVER w AS pri_pass_rate,
            lag(kickoff) OVER (PARTITION BY team_id ORDER BY kickoff) AS prev_kickoff
        FROM team_game_form f
        WHERE f.league = :league
        WINDOW w AS (PARTITION BY team_id, season ORDER BY kickoff
                     ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
    ),
    season_means AS (
        SELECT team_id, season, avg(off_epa) AS off_epa, avg(def_epa) AS def_epa
        FROM team_game_form WHERE league = :league GROUP BY 1,2
    ),
    closing AS (
        SELECT m.game_id,
               max(CASE WHEN mk.market_key='spreads' AND s.outcome = g.home_team_id
                        THEN s.line END) AS spread,
               max(CASE WHEN mk.market_key='totals' THEN s.line END) AS total
        FROM markets mk
        JOIN odds_snapshots s USING (market_id)
        JOIN markets m ON m.market_id = mk.market_id
        JOIN games g ON g.game_id = mk.game_id
        WHERE mk.bookmaker = :closing_book
        GROUP BY 1
    )
    SELECT g.game_id, g.league, g.season, g.week, g.kickoff, g.home_team_id, g.away_team_id,
        h.prior_games, a.prior_games,
        h.pri_off_epa, h.pri_def_epa, h.pri_off_pass_epa, h.pri_off_rush_epa,
        h.pri_def_pass_epa, h.pri_def_rush_epa, h.pri_off_success, h.pri_pass_rate,
        a.pri_off_epa, a.pri_def_epa, a.pri_off_pass_epa, a.pri_off_rush_epa,
        a.pri_def_pass_epa, a.pri_def_rush_epa, a.pri_off_success, a.pri_pass_rate,
        hp.off_epa, hp.def_epa, ap.off_epa, ap.def_epa,
        EXTRACT(DAY FROM g.kickoff - h.prev_kickoff)::int,
        EXTRACT(DAY FROM g.kickoff - a.prev_kickoff)::int,
        c.spread, c.total,
        g.home_score - g.away_score,
        g.home_score + g.away_score,
        (g.home_score - g.away_score) + c.spread,
        (g.home_score + g.away_score) - c.total
    FROM games g
    JOIN form h ON h.game_id = g.game_id AND h.team_id = g.home_team_id
    JOIN form a ON a.game_id = g.game_id AND a.team_id = g.away_team_id
    LEFT JOIN season_means hp ON hp.team_id = g.home_team_id AND hp.season = g.season - 1
    LEFT JOIN season_means ap ON ap.team_id = g.away_team_id AND ap.season = g.season - 1
    LEFT JOIN closing c ON c.game_id = g.game_id
    WHERE g.league = :league AND g.season = ANY(:seasons) AND g.home_score IS NOT NULL
    ON CONFLICT (game_id) DO UPDATE SET
        home_prior_games = EXCLUDED.home_prior_games,
        away_prior_games = EXCLUDED.away_prior_games,
        home_off_epa = EXCLUDED.home_off_epa, home_def_epa = EXCLUDED.home_def_epa,
        away_off_epa = EXCLUDED.away_off_epa, away_def_epa = EXCLUDED.away_def_epa,
        closing_spread = EXCLUDED.closing_spread, closing_total = EXCLUDED.closing_total,
        spread_residual = EXCLUDED.spread_residual, total_residual = EXCLUDED.total_residual
""")

CLOSING_BOOK = {"nfl": "nflverse:closing", "ncaaf": "cfbd:draftkings"}


async def build(league: str, seasons: list[int]) -> dict:
    engine = get_engine()
    async with engine.begin() as conn:
        r1 = await conn.execute(_BUILD_FORM, {"league": league, "seasons": seasons})
        r2 = await conn.execute(_BUILD_FEATURES, {
            "league": league, "seasons": seasons,
            "closing_book": CLOSING_BOOK[league],
        })
    return {"team_game_form": r1.rowcount, "game_features": r2.rowcount}


async def main(league: str, seasons: list[int]):
    stats = await build(league, seasons)
    log.info("%s: %d team-game rows, %d game feature rows",
             league, stats["team_game_form"], stats["game_features"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", default="nfl", choices=["nfl", "ncaaf"])
    parser.add_argument("--seasons", nargs="+", type=int, default=[2023, 2024, 2025])
    args = parser.parse_args()
    asyncio.run(main(args.league, args.seasons))
