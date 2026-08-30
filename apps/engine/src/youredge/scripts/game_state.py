"""Build game_state: what actually happened in each finished game.

The substrate for Layer B. Script labels and the leg ledger both read from here,
so the awkward parts — reconstructing a margin timeline from pre-snap score
differentials, deciding what "trailing" means without win probability — are
solved once.

    docker compose run --rm ingest python -m youredge.scripts.game_state

Two conventions worth stating, because everything downstream inherits them:

  * Margins are from the home team's perspective, always. `plays.score_differential`
    is from the *possessing* team's, which flips every drive.
  * `score_differential` is pre-snap, so the margin at the end of a quarter is
    read from the first play of the next one. Taking the last play of the quarter
    would miss any score on that play, which is exactly the play most likely to
    have one.
"""

import argparse
import asyncio
import logging

from sqlalchemy import text

from youredge.db import get_engine

log = logging.getLogger(__name__)

# "Trailing" without win probability. Two scores is the point where play calling
# actually changes: below it teams still run their offence, above it the trailing
# side throws and the leading side kills clock.
TWO_SCORES = 9
LATE_SECONDS = 240  # last 4:00, where a backdoor cover happens

_BUILD = text(f"""
    WITH margins AS (
        SELECT p.game_id, p.quarter, p.game_seconds_remaining, p.play_type,
               p.qb_dropback, p.posteam_id, g.home_team_id,
               CASE WHEN p.posteam_id = g.home_team_id THEN p.score_differential
                    ELSE -p.score_differential END AS home_margin,
               p.score_differential AS pos_margin,
               row_number() OVER (PARTITION BY p.game_id, p.quarter
                                  ORDER BY p.game_seconds_remaining DESC NULLS LAST,
                                           p.play_id) AS rn_in_q
        FROM plays p
        JOIN games g ON g.game_id = p.game_id
        WHERE g.status = 'final'
          AND p.score_differential IS NOT NULL
          AND p.posteam_id IS NOT NULL
          AND p.quarter BETWEEN 1 AND 4
    ),
    -- Margin *after* quarter N is the pre-snap margin on the first play of N+1.
    breaks AS (
        SELECT game_id,
               max(home_margin) FILTER (WHERE quarter = 2 AND rn_in_q = 1) AS margin_end_q1,
               max(home_margin) FILTER (WHERE quarter = 3 AND rn_in_q = 1) AS margin_end_h1,
               max(home_margin) FILTER (WHERE quarter = 4 AND rn_in_q = 1) AS margin_end_q3
        FROM margins GROUP BY game_id
    ),
    swings AS (
        SELECT game_id,
               max(home_margin) AS max_home_lead,
               -min(home_margin) AS max_away_lead,
               count(*) FILTER (WHERE sign_changed) AS lead_changes
        FROM (
            SELECT game_id, home_margin,
                   -- A lead change needs a lead to change: both sides of the
                   -- comparison must be non-zero and opposite. Counting 0 -> ahead
                   -- makes the opening score a lead change, which put this at
                   -- 99.8% of games.
                   home_margin <> 0
                   AND lag(home_margin) OVER (PARTITION BY game_id
                                              ORDER BY quarter, game_seconds_remaining DESC) <> 0
                   AND sign(home_margin) <> sign(
                       lag(home_margin) OVER (PARTITION BY game_id
                                              ORDER BY quarter, game_seconds_remaining DESC)
                   ) AS sign_changed
            FROM margins
        ) s GROUP BY game_id
    ),
    mix AS (
        SELECT m.game_id,
               count(*) AS plays_total,
               avg((m.qb_dropback)::int) FILTER (WHERE m.posteam_id = m.home_team_id)
                   AS home_pass_rate,
               avg((m.qb_dropback)::int) FILTER (WHERE m.posteam_id <> m.home_team_id)
                   AS away_pass_rate,
               -- Down two scores in the fourth: the garbage-time mechanism.
               avg((m.qb_dropback)::int)
                   FILTER (WHERE m.quarter = 4 AND m.pos_margin <= -{TWO_SCORES})
                   AS q4_trail_pass_rate,
               count(*) FILTER (WHERE m.quarter = 4 AND m.pos_margin <= -{TWO_SCORES})
                   AS q4_trail_plays,
               -- Up two scores in the fourth: the clock-kill mechanism.
               avg((m.play_type = 'run')::int)
                   FILTER (WHERE m.quarter = 4 AND m.pos_margin >= {TWO_SCORES})
                   AS q4_lead_run_rate,
               count(*) FILTER (WHERE m.quarter = 4 AND m.pos_margin >= {TWO_SCORES})
                   AS q4_lead_plays
        FROM margins m
        WHERE m.play_type IN ('pass', 'run') OR m.qb_dropback IS NOT NULL
        GROUP BY m.game_id
    ),
    -- Points scored inside the last four minutes by whoever was behind at the
    -- time. Read off drives, which already know what a possession was worth.
    late AS (
        SELECT d.game_id,
               sum(d.points) FILTER (
                   WHERE d.start_seconds IS NOT NULL AND d.start_seconds <= {LATE_SECONDS}
                     AND d.start_score_diff < 0
               ) AS late_trail_points
        FROM drives d GROUP BY d.game_id
    )
    INSERT INTO game_state (
        game_id, home_points, away_points, total_points, home_margin,
        margin_end_q1, margin_end_h1, margin_end_q3,
        max_home_lead, max_away_lead, lead_changes,
        plays_total, home_pass_rate, away_pass_rate,
        q4_trail_pass_rate, q4_trail_plays, q4_lead_run_rate, q4_lead_plays,
        late_trail_points
    )
    SELECT g.game_id, g.home_score, g.away_score,
           g.home_score + g.away_score, g.home_score - g.away_score,
           b.margin_end_q1, b.margin_end_h1, b.margin_end_q3,
           GREATEST(s.max_home_lead, 0), GREATEST(s.max_away_lead, 0), s.lead_changes,
           x.plays_total, x.home_pass_rate, x.away_pass_rate,
           x.q4_trail_pass_rate, x.q4_trail_plays, x.q4_lead_run_rate, x.q4_lead_plays,
           COALESCE(l.late_trail_points, 0)
    FROM games g
    LEFT JOIN breaks b ON b.game_id = g.game_id
    LEFT JOIN swings s ON s.game_id = g.game_id
    LEFT JOIN mix    x ON x.game_id = g.game_id
    LEFT JOIN late   l ON l.game_id = g.game_id
    WHERE g.status = 'final' AND g.home_score IS NOT NULL
      AND g.league = ANY(:leagues)
      AND EXISTS (SELECT 1 FROM plays p WHERE p.game_id = g.game_id)
    ON CONFLICT (game_id) DO UPDATE SET
        home_points = EXCLUDED.home_points, away_points = EXCLUDED.away_points,
        total_points = EXCLUDED.total_points, home_margin = EXCLUDED.home_margin,
        margin_end_q1 = EXCLUDED.margin_end_q1, margin_end_h1 = EXCLUDED.margin_end_h1,
        margin_end_q3 = EXCLUDED.margin_end_q3,
        max_home_lead = EXCLUDED.max_home_lead, max_away_lead = EXCLUDED.max_away_lead,
        lead_changes = EXCLUDED.lead_changes, plays_total = EXCLUDED.plays_total,
        home_pass_rate = EXCLUDED.home_pass_rate, away_pass_rate = EXCLUDED.away_pass_rate,
        q4_trail_pass_rate = EXCLUDED.q4_trail_pass_rate,
        q4_trail_plays = EXCLUDED.q4_trail_plays,
        q4_lead_run_rate = EXCLUDED.q4_lead_run_rate,
        q4_lead_plays = EXCLUDED.q4_lead_plays,
        late_trail_points = EXCLUDED.late_trail_points,
        built_at = now()
""")


# The scoreboard timeline. Two things make this harder than reading a column.
#
# CFBD's score on kickoff and timeout rows is unreliable — it can report a stale
# value, so a naive read has the score going backwards mid-quarter. A running
# maximum fixes that without a play-type blacklist, because a score cannot fall.
#
# And a run has to be defined by what interrupts it. The gaps-and-islands trick
# below counts the opponent's scores so far and groups a side's own scores by
# that count: every time the other team scores, the group advances and the run
# starts over. The largest group sum is the run.
_SEQUENCE = text("""
    WITH tl AS (
        SELECT p.game_id, p.quarter, p.game_seconds_remaining AS sec, p.play_id,
               max(p.home_score) OVER w AS hs,
               max(p.away_score) OVER w AS a_s
        FROM plays p
        JOIN games g USING (game_id)
        WHERE p.home_score IS NOT NULL AND g.status = 'final'
          AND g.league = ANY(:leagues)
        WINDOW w AS (PARTITION BY p.game_id
                     ORDER BY p.game_seconds_remaining DESC NULLS LAST, p.play_id
                     ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
    ),
    ev AS (
        SELECT game_id, quarter, sec, hs, a_s,
               hs  - lag(hs,  1, 0) OVER w AS h_delta,
               a_s - lag(a_s, 1, 0) OVER w AS a_delta,
               sign(hs - a_s) AS leader,
               sign(lag(hs, 1, 0) OVER w - lag(a_s, 1, 0) OVER w) AS prev_leader,
               row_number() OVER w AS seq
        FROM tl
        WINDOW w AS (PARTITION BY game_id ORDER BY sec DESC NULLS LAST, play_id)
    ),
    scores AS (SELECT * FROM ev WHERE h_delta > 0 OR a_delta > 0),
    runs AS (
        SELECT game_id, quarter, h_delta, a_delta,
               count(*) FILTER (WHERE a_delta > 0) OVER (
                   PARTITION BY game_id ORDER BY seq) AS h_grp,
               count(*) FILTER (WHERE h_delta > 0) OVER (
                   PARTITION BY game_id ORDER BY seq) AS a_grp
        FROM scores
    ),
    h_runs AS (
        SELECT game_id, sum(h_delta) AS run, max(quarter) AS end_q
        FROM runs GROUP BY game_id, h_grp
    ),
    a_runs AS (
        SELECT game_id, sum(a_delta) AS run, max(quarter) AS end_q
        FROM runs GROUP BY game_id, a_grp
    ),
    h_best AS (
        SELECT DISTINCT ON (game_id) game_id, run, end_q
        FROM h_runs ORDER BY game_id, run DESC, end_q
    ),
    a_best AS (
        SELECT DISTINCT ON (game_id) game_id, run, end_q
        FROM a_runs ORDER BY game_id, run DESC, end_q
    ),
    quarters AS (
        SELECT game_id,
               sum(h_delta) FILTER (WHERE quarter = 1) AS hq1,
               sum(h_delta) FILTER (WHERE quarter = 2) AS hq2,
               sum(h_delta) FILTER (WHERE quarter = 3) AS hq3,
               sum(h_delta) FILTER (WHERE quarter >= 4) AS hq4,
               sum(a_delta) FILTER (WHERE quarter = 1) AS aq1,
               sum(a_delta) FILTER (WHERE quarter = 2) AS aq2,
               sum(a_delta) FILTER (WHERE quarter = 3) AS aq3,
               sum(a_delta) FILTER (WHERE quarter >= 4) AS aq4,
               min(quarter) FILTER (WHERE h_delta > 0) AS h_first_q,
               min(quarter) FILTER (WHERE a_delta > 0) AS a_first_q
        FROM scores GROUP BY game_id
    ),
    -- A lead change needs a real leader on both sides of it: 0 is a tie, and a
    -- tie is not a change of hands.
    leadchg AS (
        SELECT game_id, min(sec) AS last_sec
        FROM ev
        WHERE leader <> 0 AND prev_leader <> 0 AND leader <> prev_leader
        GROUP BY game_id
    ),
    dr AS (
        SELECT d.game_id, d.posteam_id, d.drive_num, d.points,
               d.plays, d.result,
               row_number() OVER (PARTITION BY d.game_id, d.posteam_id
                                  ORDER BY d.drive_num) AS own_num,
               sum(CASE WHEN d.points > 0 THEN 1 ELSE 0 END) OVER (
                   PARTITION BY d.game_id, d.posteam_id
                   ORDER BY d.drive_num) AS scored_so_far
        FROM drives d
        WHERE d.posteam_id IS NOT NULL AND d.result <> 'END_HALF'
    ),
    streaks AS (
        SELECT game_id, posteam_id,
               count(*) FILTER (WHERE scored_so_far = 0) AS open_scoreless,
               max(len) AS max_scoreless,
               count(*) FILTER (WHERE plays <= 3 AND result = 'PUNT') AS three_outs
        FROM (
            SELECT dr.*, count(*) OVER (PARTITION BY game_id, posteam_id,
                                                     scored_so_far) AS len
            FROM dr
        ) z GROUP BY game_id, posteam_id
    )
    -- Zero, not NULL, for anything countable. A quarter with no scoring sums to
    -- NULL over an empty set, and NULL fails every comparison silently -- which
    -- is how a "neither side scored in the first quarter" tag can be written
    -- correctly and never fire once. NULL is reserved for "the sequence was
    -- never built for this game", which the WHERE below makes the only cause.
    UPDATE game_state gs SET
        home_q1_points = COALESCE(q.hq1, 0), home_q2_points = COALESCE(q.hq2, 0),
        home_q3_points = COALESCE(q.hq3, 0), home_q4_points = COALESCE(q.hq4, 0),
        away_q1_points = COALESCE(q.aq1, 0), away_q2_points = COALESCE(q.aq2, 0),
        away_q3_points = COALESCE(q.aq3, 0), away_q4_points = COALESCE(q.aq4, 0),
        home_first_score_q = q.h_first_q, away_first_score_q = q.a_first_q,
        home_max_run = COALESCE(hb.run, 0), home_max_run_end_q = hb.end_q,
        away_max_run = COALESCE(ab.run, 0), away_max_run_end_q = ab.end_q,
        last_lead_change_sec = lc.last_sec,
        home_open_scoreless_drives = COALESCE(hst.open_scoreless, 0),
        away_open_scoreless_drives = COALESCE(ast.open_scoreless, 0),
        home_max_scoreless_drives = COALESCE(hst.max_scoreless, 0),
        away_max_scoreless_drives = COALESCE(ast.max_scoreless, 0),
        home_three_and_outs = COALESCE(hst.three_outs, 0),
        away_three_and_outs = COALESCE(ast.three_outs, 0)
    FROM games g
    LEFT JOIN quarters q ON q.game_id = g.game_id
    LEFT JOIN h_best hb  ON hb.game_id = g.game_id
    LEFT JOIN a_best ab  ON ab.game_id = g.game_id
    LEFT JOIN leadchg lc ON lc.game_id = g.game_id
    LEFT JOIN streaks hst ON hst.game_id = g.game_id AND hst.posteam_id = g.home_team_id
    LEFT JOIN streaks ast ON ast.game_id = g.game_id AND ast.posteam_id = g.away_team_id
    WHERE gs.game_id = g.game_id AND g.league = ANY(:leagues)
      -- Only games whose scoreboard timeline actually exists. Without this the
      -- LEFT JOINs write NULLs over every game still awaiting a score backfill,
      -- and a downstream tag reading "no lead change" cannot tell that apart
      -- from "we never looked".
      AND EXISTS (SELECT 1 FROM tl WHERE tl.game_id = g.game_id)
""")


async def build(leagues: list[str]) -> int:
    engine = get_engine()
    async with engine.begin() as conn:
        n = (await conn.execute(_BUILD, {"leagues": leagues})).rowcount
        seq = (await conn.execute(_SEQUENCE, {"leagues": leagues})).rowcount
        log.info("scoring sequence filled on %d games", seq)
        stats = (await conn.execute(text("""
            SELECT g.league, count(*) AS games,
                   round(avg(gs.total_points)::numeric, 1) AS avg_total,
                   round(avg(abs(gs.home_margin))::numeric, 1) AS avg_margin,
                   round(avg(gs.plays_total)::numeric, 1) AS avg_plays,
                   round(avg(gs.q4_trail_pass_rate)::numeric, 3) AS q4_trail_pass,
                   round(avg(gs.q4_lead_run_rate)::numeric, 3) AS q4_lead_run
            FROM game_state gs JOIN games g USING (game_id)
            GROUP BY 1 ORDER BY 1
        """))).mappings().all()
    for s in stats:
        log.info("%-6s %5d games | total %5s | margin %5s | plays %5s | "
                 "Q4 trailing pass %s, leading run %s",
                 s["league"], s["games"], s["avg_total"], s["avg_margin"],
                 s["avg_plays"], s["q4_trail_pass"], s["q4_lead_run"])
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", nargs="+", default=["nfl", "ncaaf"])
    args = ap.parse_args()
    asyncio.run(build(args.league))
