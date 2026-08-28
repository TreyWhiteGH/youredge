"""Evaluate every leg template against every finished game.

This is the counting layer. For each game it asks, of each template, "would this
leg have won?" — and the answers are what the correlation surface is built from.
No model is involved anywhere: a leg either won or it did not.

    docker compose run --rm ingest python -m youredge.legs.ledger

Where the numbers come from matters more than the templates do.

Spreads, totals and moneylines are judged against the **real closing line**, so
those rows describe outcomes at a price the market actually set. We hold no
historical team-total, half or player-prop lines, so those are judged against a
**synthetic** number — the closing line split for team totals and halves, the
player's own trailing median for props. That is enough to measure whether two
legs move together, which is the point. It is not enough to price anything, and
`line_source` is recorded on every row so nothing downstream can forget which
kind it is holding.
"""

import argparse
import asyncio
import logging

from sqlalchemy import text

from youredge.db import get_engine

log = logging.getLogger(__name__)

# Halves do not split evenly. Second halves outscore first ones — more possessions
# after adjustments, and clock-stopping late — so a synthetic first-half total is
# a shade under half. Measured from game_state rather than assumed.
H1_SHARE = 0.47
Q1_SHARE = 0.22

# Game-market templates. Each is (template, side, line expr, realized expr, hit expr).
# `gs` is game_state, `gf` is game_features (closing lines).
GAME_TEMPLATES: list[tuple[str, str, str, str, str, str]] = [
    # --- real closing lines
    ("SPREAD", "home", "gf.closing_spread", "gs.home_margin",
     "gs.home_margin + gf.closing_spread > 0", "closing"),
    ("SPREAD", "away", "gf.closing_spread", "-gs.home_margin",
     "gs.home_margin + gf.closing_spread < 0", "closing"),
    ("TOTAL", "over", "gf.closing_total", "gs.total_points",
     "gs.total_points > gf.closing_total", "closing"),
    ("TOTAL", "under", "gf.closing_total", "gs.total_points",
     "gs.total_points < gf.closing_total", "closing"),
    ("MONEYLINE", "home", "NULL", "gs.home_margin", "gs.home_margin > 0", "closing"),
    ("MONEYLINE", "away", "NULL", "-gs.home_margin", "gs.home_margin < 0", "closing"),
    # The favourite is defined by the market, so this is a real line too.
    ("FAVORITE", "cover", "gf.closing_spread", "gs.home_margin",
     "(gf.closing_spread < 0 AND gs.home_margin + gf.closing_spread > 0) OR "
     "(gf.closing_spread > 0 AND -gs.home_margin - gf.closing_spread > 0)", "closing"),

    # --- synthetic: team totals, split from the closing line
    ("TEAM_TOTAL", "home_over",
     "round((gf.closing_total - gf.closing_spread)::numeric / 2) + 0.5",
     "gs.home_points",
     "gs.home_points > round((gf.closing_total - gf.closing_spread)::numeric / 2) + 0.5",
     "synthetic"),
    ("TEAM_TOTAL", "away_over",
     "round((gf.closing_total + gf.closing_spread)::numeric / 2) + 0.5",
     "gs.away_points",
     "gs.away_points > round((gf.closing_total + gf.closing_spread)::numeric / 2) + 0.5",
     "synthetic"),

    # --- synthetic: halves and quarters
    ("H1_TOTAL", "over", f"round((gf.closing_total * {H1_SHARE})::numeric) + 0.5",
     "gs.home_points + gs.away_points",
     f"NULL", "synthetic"),   # filled below from margin data; placeholder replaced
    ("Q1_TOTAL", "over", f"round((gf.closing_total * {Q1_SHARE})::numeric) + 0.5",
     "NULL", "NULL", "synthetic"),

    # --- shape of the game, no line needed
    ("MARGIN", "double_digit", "9.5", "abs(gs.home_margin)",
     "abs(gs.home_margin) > 9.5", "synthetic"),
    ("MARGIN", "one_score", "8.5", "abs(gs.home_margin)",
     "abs(gs.home_margin) <= 8.5", "synthetic"),
    ("BOTH_TEAMS", "twenty_plus", "19.5", "LEAST(gs.home_points, gs.away_points)",
     "LEAST(gs.home_points, gs.away_points) > 19.5", "synthetic"),
    ("LEAD_CHANGE", "any", "0.5", "gs.lead_changes", "gs.lead_changes > 0", "synthetic"),
]

_INSERT_GAME = """
    INSERT INTO leg_outcomes (game_id, template, side, line, line_source, realized, hit)
    SELECT gs.game_id, :template, :side,
           ({line})::real, :src, ({realized})::real, ({hit})
    FROM game_state gs
    JOIN games g ON g.game_id = gs.game_id
    LEFT JOIN game_features gf ON gf.game_id = gs.game_id
    WHERE g.league = ANY(:leagues)
      AND ({line}) IS NOT NULL
      AND ({hit}) IS NOT NULL
    ON CONFLICT (game_id, template, side) DO UPDATE SET
        line = EXCLUDED.line, line_source = EXCLUDED.line_source,
        realized = EXCLUDED.realized, hit = EXCLUDED.hit
"""

# Player templates. The lead back, lead receiver and starting quarterback of each
# team, judged against their own trailing median so the line means "a normal game
# for this player". Roles are assigned per game by volume, which is what a book
# does implicitly when it posts a number.
_INSERT_PLAYER = text("""
    WITH per_game AS (
        SELECT pp.game_id, pp.team_id, pp.player_id,
               sum(pp.stat) FILTER (WHERE pp.stat_type = 'Rush')      AS rush_yds,
               count(*)     FILTER (WHERE pp.stat_type = 'Rush')      AS carries,
               sum(pp.stat) FILTER (WHERE pp.stat_type = 'Reception') AS rec_yds,
               count(*)     FILTER (WHERE pp.stat_type = 'Reception') AS catches,
               sum(pp.stat) FILTER (WHERE pp.stat_type = 'Completion') AS pass_yds,
               count(*)     FILTER (WHERE pp.stat_type = 'Completion') AS completions
        FROM play_players pp
        GROUP BY 1, 2, 3
    ),
    -- Role by *season* usage, not by what happened in this game. Ranking within
    -- the game makes "RB1" mean "had a big day", so the leg is judged against a
    -- line the selection already beat — it ran at 74% over, which is not a prop,
    -- it is a tautology.
    season_usage AS (
        SELECT pg.team_id, g.season, pg.player_id,
               sum(pg.carries)     AS carries,
               sum(pg.catches)     AS catches,
               sum(pg.completions) AS completions
        FROM per_game pg JOIN games g ON g.game_id = pg.game_id
        WHERE g.league = ANY(:leagues) AND g.status = 'final'
        GROUP BY 1, 2, 3
    ),
    roles AS (
        SELECT team_id, season, player_id,
               row_number() OVER (PARTITION BY team_id, season ORDER BY carries DESC)     AS rb_rank,
               row_number() OVER (PARTITION BY team_id, season ORDER BY catches DESC)     AS wr_rank,
               row_number() OVER (PARTITION BY team_id, season ORDER BY completions DESC) AS qb_rank
        FROM season_usage
    ),
    ranked AS (
        SELECT pg.*, g.league, g.season,
               ro.rb_rank, ro.wr_rank, ro.qb_rank,
               CASE WHEN pg.team_id = g.home_team_id THEN 'home' ELSE 'away' END AS team_side
        FROM per_game pg
        JOIN games g ON g.game_id = pg.game_id
        JOIN roles ro ON ro.team_id = pg.team_id AND ro.season = g.season
                     AND ro.player_id = pg.player_id
        WHERE g.league = ANY(:leagues) AND g.status = 'final'
    ),
    -- The player's median in his other games. Computed over the whole sample
    -- rather than as-of, which is fine for measuring co-occurrence and would not
    -- be fine for training anything.
    medians AS (
        SELECT pg.player_id, g.season,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY pg.rush_yds) AS med_rush,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY pg.rec_yds)  AS med_rec,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY pg.pass_yds) AS med_pass,
               count(*) AS games
        FROM per_game pg JOIN games g ON g.game_id = pg.game_id
        GROUP BY 1, 2
    )
    INSERT INTO leg_outcomes
        (game_id, template, side, line, line_source, realized, hit, player_id)
    SELECT r.game_id, x.template, r.team_side || '_' || x.side,
           x.line, 'synthetic', x.realized,
           x.realized > x.line, r.player_id
    FROM ranked r
    JOIN medians m ON m.player_id = r.player_id AND m.season = r.season
                  AND m.games >= 4
    CROSS JOIN LATERAL (VALUES
        ('RB1_RUSH_YDS', CASE WHEN r.rb_rank = 1 THEN 'over' END,
         round(m.med_rush::numeric) + 0.5, r.rush_yds),
        ('WR1_REC_YDS',  CASE WHEN r.wr_rank = 1 THEN 'over' END,
         round(m.med_rec::numeric) + 0.5,  r.rec_yds),
        ('QB1_PASS_YDS', CASE WHEN r.qb_rank = 1 THEN 'over' END,
         round(m.med_pass::numeric) + 0.5, r.pass_yds)
    ) AS x(template, side, line, realized)
    WHERE x.side IS NOT NULL AND x.line IS NOT NULL AND x.realized IS NOT NULL
      AND x.line > 0
    ON CONFLICT (game_id, template, side) DO UPDATE SET
        line = EXCLUDED.line, realized = EXCLUDED.realized,
        hit = EXCLUDED.hit, player_id = EXCLUDED.player_id
""")


async def build(leagues: list[str]) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        for template, side, line, realized, hit, src in GAME_TEMPLATES:
            if hit == "NULL":
                continue   # period templates need period scoring; see build_periods
            await conn.execute(
                text(_INSERT_GAME.format(line=line, realized=realized, hit=hit)),
                {"template": template, "side": side, "src": src, "leagues": leagues},
            )
        await conn.execute(_INSERT_PLAYER, {"leagues": leagues})

        rows = (await conn.execute(text("""
            SELECT lo.template, lo.side, lo.line_source, count(*) AS n,
                   round(avg(lo.hit::int)::numeric, 3) AS hit_rate
            FROM leg_outcomes lo GROUP BY 1, 2, 3 ORDER BY 4 DESC
        """))).mappings().all()

    log.info("%-14s %-12s %-10s %8s %9s", "template", "side", "source", "n", "hit rate")
    for r in rows:
        log.info("%-14s %-12s %-10s %8d %9s",
                 r["template"], r["side"], r["line_source"], r["n"], r["hit_rate"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", nargs="+", default=["nfl", "ncaaf"])
    args = ap.parse_args()
    asyncio.run(build(args.league))
