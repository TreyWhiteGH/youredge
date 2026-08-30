"""Why each team is winning or losing a given game.

Script tags say what shape a game took. These say what is *causing* it, per team,
so a single game reads as a story with two sides: one team is losing despite
moving the ball because it gave it away three times; the other never threw past
the sticks and is winning on field position.

    docker compose run --rm ingest python -m youredge.scripts.diagnose
    docker compose run --rm ingest python -m youredge.scripts.diagnose --game nfl:2024_01_...

Two design choices carried over from the script labels, both learned the hard way.

Thresholds are percentiles **within league**, never fixed numbers. A fixed cut
fired on 28% of NFL games and 9% of college ones purely because nflverse counts a
scramble as a dropback and CFBD files it as a rush. "Top-quartile rush EPA" means
the same thing in both leagues; "rush EPA above 0.1" does not.

Where a measurement is unavailable the diagnosis is withheld rather than guessed.
Air yards exist for 39% of NFL plays and 5% of college ones, so NO_DEEP_SHOT and
CHECKDOWN_HEAVY simply do not fire without them. A quarterback who was not
measured is not a quarterback who threw everything short.

The same computation runs on a game in progress — nothing here reads a final
score except points_for/against, and the diagnoses are all rate-based. What is
missing for live use is a live play feed, not this.
"""

import argparse
import asyncio
import logging

from sqlalchemy import text

from youredge.db import get_engine

log = logging.getLogger(__name__)

EXPLOSIVE_RUN = 10
EXPLOSIVE_PASS = 16
DEEP_AIR_YARDS = 15
TWO_SCORES = 9
MIN_AIR_YARDS_SAMPLE = 8   # below this, aDOT is an anecdote

_BUILD = text(f"""
    WITH pl AS (
        SELECT p.*, g.league, g.season,
               CASE WHEN p.posteam_id = g.home_team_id THEN g.away_team_id
                    ELSE g.home_team_id END AS opp_id
        FROM plays p JOIN games g ON g.game_id = p.game_id
        WHERE g.status = 'final' AND p.posteam_id IS NOT NULL
          AND g.league = ANY(:leagues)
    ),
    off AS (
        SELECT game_id, posteam_id AS team_id, max(opp_id) AS opponent_id,
               count(*) FILTER (WHERE play_type = 'run')                     AS rush_att,
               sum(yards_gained) FILTER (WHERE play_type = 'run')            AS rush_yards,
               avg(epa) FILTER (WHERE play_type = 'run')                     AS rush_epa,
               avg(success::int) FILTER (WHERE play_type = 'run')            AS rush_success,
               count(*) FILTER (WHERE qb_dropback)                           AS dropbacks,
               avg(epa) FILTER (WHERE qb_dropback)                           AS pass_epa,
               avg(success::int) FILTER (WHERE qb_dropback)                  AS pass_success,
               count(*) FILTER (WHERE sack)                                  AS sacks_taken,
               count(*) FILTER (WHERE interception)                          AS ints,
               count(*) FILTER (WHERE fumble_lost)                           AS fumbles,
               avg(air_yards) FILTER (WHERE air_yards IS NOT NULL)           AS adot,
               count(*) FILTER (WHERE air_yards IS NOT NULL)                 AS air_n,
               avg((air_yards >= {DEEP_AIR_YARDS})::int)
                   FILTER (WHERE air_yards IS NOT NULL)                      AS deep_rate,
               count(*) FILTER (WHERE yardline_100 <= 20 AND down = 1)       AS rz_trips,
               count(*) FILTER (WHERE yardline_100 <= 20 AND touchdown)      AS rz_tds,
               count(*) FILTER (WHERE down = 3)                              AS third_att,
               count(*) FILTER (WHERE down = 3 AND yards_gained >= ydstogo)  AS third_conv,
               avg((CASE WHEN play_type = 'run' THEN yards_gained >= {EXPLOSIVE_RUN}
                         WHEN qb_dropback THEN yards_gained >= {EXPLOSIVE_PASS} END)::int)
                   FILTER (WHERE play_type = 'run' OR qb_dropback)           AS explosive_rate,
               -- Penalties: nflverse sets a flag, CFBD names the play type.
               count(*) FILTER (WHERE penalty OR play_type_raw = 'Penalty')  AS penalties,
               -- Yards banked once the game was already two scores gone.
               COALESCE(sum(yards_gained) FILTER (
                   WHERE score_differential <= -{TWO_SCORES}
                     AND (play_type = 'run' OR qb_dropback)), 0)
                 / NULLIF(sum(yards_gained) FILTER (
                   WHERE play_type = 'run' OR qb_dropback), 0)               AS garbage_share
        FROM pl GROUP BY game_id, posteam_id
    ),
    defense AS (
        SELECT game_id, defteam_id AS team_id,
               avg(epa) FILTER (WHERE play_type = 'run') AS rush_epa_allowed,
               count(*) FILTER (WHERE interception) + count(*) FILTER (WHERE fumble_lost)
                   AS takeaways
        FROM pl WHERE defteam_id IS NOT NULL GROUP BY game_id, defteam_id
    ),
    starts AS (
        SELECT game_id, posteam_id AS team_id, avg(start_yardline) AS avg_start
        FROM drives WHERE posteam_id IS NOT NULL GROUP BY game_id, posteam_id
    )
    INSERT INTO team_game_diagnostics (
        game_id, team_id, opponent_id, points_for, points_against,
        giveaways, takeaways, turnover_margin,
        rush_att, rush_yards, rush_epa, rush_success, rush_epa_allowed,
        dropbacks, pass_epa, pass_success, sacks_taken, sack_rate,
        adot, deep_rate, air_yards_n,
        rz_trips, rz_tds, third_att, third_conv, explosive_rate, penalties,
        avg_start_yardline, garbage_yard_share
    )
    SELECT o.game_id, o.team_id, o.opponent_id,
           CASE WHEN o.team_id = g.home_team_id THEN g.home_score ELSE g.away_score END,
           CASE WHEN o.team_id = g.home_team_id THEN g.away_score ELSE g.home_score END,
           o.ints + o.fumbles,
           COALESCE(d.takeaways, 0),
           COALESCE(d.takeaways, 0) - (o.ints + o.fumbles),
           o.rush_att, o.rush_yards, o.rush_epa, o.rush_success, d.rush_epa_allowed,
           o.dropbacks, o.pass_epa, o.pass_success, o.sacks_taken,
           o.sacks_taken::real / NULLIF(o.dropbacks, 0),
           CASE WHEN o.air_n >= {MIN_AIR_YARDS_SAMPLE} THEN o.adot END,
           CASE WHEN o.air_n >= {MIN_AIR_YARDS_SAMPLE} THEN o.deep_rate END,
           o.air_n,
           o.rz_trips, o.rz_tds, o.third_att, o.third_conv,
           o.explosive_rate, o.penalties, s.avg_start, o.garbage_share
    FROM off o
    JOIN games g ON g.game_id = o.game_id
    LEFT JOIN defense d ON d.game_id = o.game_id AND d.team_id = o.team_id
    LEFT JOIN starts  s ON s.game_id = o.game_id AND s.team_id = o.team_id
    ON CONFLICT (game_id, team_id) DO UPDATE SET
        opponent_id = EXCLUDED.opponent_id, points_for = EXCLUDED.points_for,
        points_against = EXCLUDED.points_against, giveaways = EXCLUDED.giveaways,
        takeaways = EXCLUDED.takeaways, turnover_margin = EXCLUDED.turnover_margin,
        rush_att = EXCLUDED.rush_att, rush_yards = EXCLUDED.rush_yards,
        rush_epa = EXCLUDED.rush_epa, rush_success = EXCLUDED.rush_success,
        rush_epa_allowed = EXCLUDED.rush_epa_allowed, dropbacks = EXCLUDED.dropbacks,
        pass_epa = EXCLUDED.pass_epa, pass_success = EXCLUDED.pass_success,
        sacks_taken = EXCLUDED.sacks_taken, sack_rate = EXCLUDED.sack_rate,
        adot = EXCLUDED.adot, deep_rate = EXCLUDED.deep_rate,
        air_yards_n = EXCLUDED.air_yards_n, rz_trips = EXCLUDED.rz_trips,
        rz_tds = EXCLUDED.rz_tds, third_att = EXCLUDED.third_att,
        third_conv = EXCLUDED.third_conv, explosive_rate = EXCLUDED.explosive_rate,
        penalties = EXCLUDED.penalties, avg_start_yardline = EXCLUDED.avg_start_yardline,
        garbage_yard_share = EXCLUDED.garbage_yard_share, built_at = now()
""")

# Each diagnosis: (slug, predicate over d / q). `q` holds this league's quartiles,
# so every threshold is relative to the league rather than to a magic number.
DIAGNOSES: list[tuple[str, str]] = [
    ("BALL_SECURITY_ISSUE", "d.giveaways >= 3"),
    ("TAKEAWAY_BURST",      "d.takeaways >= 3"),
    # Lost the game, gave it away, and was not actually outplayed between the
    # twenties — the turnovers are the difference, not the football.
    ("TURNOVER_LOSS", """
        d.points_for < d.points_against AND d.turnover_margin <= -2
        AND d.rush_epa + d.pass_epa >= q.epa_sum_med
    """),
    ("TURNOVER_FUELED_WIN", """
        d.points_for > d.points_against AND d.turnover_margin >= 2
        AND d.rush_epa + d.pass_epa < q.epa_sum_med
    """),
    ("GROUND_CONTROL",  "d.rush_att >= q.rush_att_p75 AND d.rush_epa >= q.rush_epa_p75"),
    ("RUN_STUFFED",     "d.rush_att >= 20 AND d.rush_success <= q.rush_success_p25"),
    ("RUN_D_GASHED",    "d.rush_epa_allowed >= q.rush_epa_p75"),
    ("SHAKY_QB", """
        d.dropbacks >= 15 AND d.pass_epa <= q.pass_epa_p25
        AND (d.sacks_taken + d.giveaways) >= 3
    """),
    ("SURGICAL_QB",     "d.dropbacks >= 15 AND d.pass_epa >= q.pass_epa_p75 AND d.giveaways <= 1"),
    ("QB_UNDER_SIEGE",  "d.dropbacks >= 15 AND d.sack_rate >= q.sack_rate_p75"),
    # Both of these require air yards. NULL fails the comparison, so a team with
    # no air-yard data is never diagnosed as short-throwing.
    ("NO_DEEP_SHOT",    "d.deep_rate IS NOT NULL AND d.deep_rate <= q.deep_rate_p25"),
    ("CHECKDOWN_HEAVY", "d.adot IS NOT NULL AND d.adot <= q.adot_p25"),
    ("RED_ZONE_STALL",  "d.rz_trips >= 3 AND d.rz_tds::real / NULLIF(d.rz_trips,0) <= 0.34"),
    ("THIRD_DOWN_FAILURE",
     "d.third_att >= 8 AND d.third_conv::real / NULLIF(d.third_att,0) <= q.third_p25"),
    ("THIRD_DOWN_SHARP",
     "d.third_att >= 8 AND d.third_conv::real / NULLIF(d.third_att,0) >= q.third_p75"),
    ("EXPLOSIVE_OFFENSE", "d.explosive_rate >= q.explosive_p75"),
    ("PENALTY_PLAGUED",   "d.penalties >= q.penalties_p75"),
    ("FIELD_POSITION_EDGE", """
        d.avg_start_yardline IS NOT NULL AND o.avg_start_yardline IS NOT NULL
        AND o.avg_start_yardline - d.avg_start_yardline >= 5
    """),
    ("EMPTY_CALORIES",  "d.garbage_yard_share >= 0.40"),

    # --- sequence: what a box score cannot say -------------------------------
    # Nothing above knows what order anything happened in. These do.

    # Scoreless through the opening quarter and three or more possessions.
    # Distinct from simply being bad: a team can start cold and win.
    ("COLD_START", """
        seq.q1_points = 0 AND seq.open_scoreless >= 3
    """),
    # Fourteen unanswered is two scores with no reply, which is where a game
    # stops being close on the scoreboard even when it is close on the field.
    # Fourteen unanswered is two scores with no reply, which is where a game
    # stops being close on the scoreboard even when it is close on the field.
    # But a flat 14 fires on 44% of college team-games against 12% of NFL ones,
    # and a tag that describes almost half the population describes nothing. The
    # floor keeps the football meaning — this never fires on a one-score run —
    # and the league percentile keeps it rare where scoring runs are ordinary.
    ("SCORING_RUN", "seq.max_run >= GREATEST(14, q.max_run_p80)"),
    ("LATE_SURGE",  "seq.q4_points >= 14"),
    ("SCORING_DROUGHT", "seq.max_scoreless >= q.scoreless_p90"),
    # Took the offence away rather than merely outscoring it: negative EPA in
    # both phases at once, with the points to match. Written from the defence's
    # side, so it reads off the opponent's row.
    ("SMOTHERING_DEFENSE", """
        o.pass_epa < 0 AND o.rush_epa < 0
        AND d.points_against <= q.points_p25
    """),
    # The same game from the other bench.
    ("OFFENSE_SHUT_DOWN", """
        d.pass_epa < 0 AND d.rush_epa < 0
        AND d.points_for <= q.points_p25
    """),
    # Strictly greater, not at least. Three-and-out counts are small integers
    # and the 75th percentile is itself 3, so >= sweeps in the whole modal band
    # and fires on two team-games in five.
    ("THREE_AND_OUT_PLAGUED", "seq.three_outs > q.three_outs_p75"),
    # Won, and the last time the lead changed hands was in the fourth. Only the
    # winner can satisfy this, which is why no side check is needed: the loser
    # was ahead before that change, not after it.
    ("GO_AHEAD_ANSWER", """
        seq.won AND gs.last_lead_change_sec IS NOT NULL
        AND gs.last_lead_change_sec <= 900
    """),
]

_QUARTILES = """
    SELECT g.league,
      percentile_cont(0.75) WITHIN GROUP (ORDER BY d.rush_att)       AS rush_att_p75,
      percentile_cont(0.75) WITHIN GROUP (ORDER BY d.rush_epa)       AS rush_epa_p75,
      percentile_cont(0.25) WITHIN GROUP (ORDER BY d.rush_success)   AS rush_success_p25,
      percentile_cont(0.25) WITHIN GROUP (ORDER BY d.pass_epa)       AS pass_epa_p25,
      percentile_cont(0.75) WITHIN GROUP (ORDER BY d.pass_epa)       AS pass_epa_p75,
      percentile_cont(0.75) WITHIN GROUP (ORDER BY d.sack_rate)      AS sack_rate_p75,
      percentile_cont(0.25) WITHIN GROUP (ORDER BY d.deep_rate)      AS deep_rate_p25,
      percentile_cont(0.25) WITHIN GROUP (ORDER BY d.adot)           AS adot_p25,
      percentile_cont(0.25) WITHIN GROUP (ORDER BY d.third_conv::real
                                          / NULLIF(d.third_att,0))   AS third_p25,
      percentile_cont(0.75) WITHIN GROUP (ORDER BY d.third_conv::real
                                          / NULLIF(d.third_att,0))   AS third_p75,
      percentile_cont(0.75) WITHIN GROUP (ORDER BY d.explosive_rate) AS explosive_p75,
      percentile_cont(0.75) WITHIN GROUP (ORDER BY d.penalties)      AS penalties_p75,
      percentile_cont(0.50) WITHIN GROUP (ORDER BY d.rush_epa + d.pass_epa) AS epa_sum_med,
      percentile_cont(0.25) WITHIN GROUP (ORDER BY d.points_for)      AS points_p25,
      -- Three-and-outs are a possession fact and live in game_state, so the
      -- percentile has to reach across and flip by side like the predicates do.
      percentile_cont(0.75) WITHIN GROUP (ORDER BY
          CASE WHEN d.team_id = g.home_team_id THEN gs2.home_three_and_outs
               ELSE gs2.away_three_and_outs END)                     AS three_outs_p75,
      -- A drought has to be rare to be worth saying. The median team already
      -- goes four possessions without points in a normal game, so anything at
      -- or near the median describes football rather than this game. p90 is the
      -- level that picks out a genuine stall, and it differs by league.
      percentile_cont(0.90) WITHIN GROUP (ORDER BY
          CASE WHEN d.team_id = g.home_team_id THEN gs2.home_max_scoreless_drives
               ELSE gs2.away_max_scoreless_drives END)               AS scoreless_p90,
      percentile_cont(0.80) WITHIN GROUP (ORDER BY
          CASE WHEN d.team_id = g.home_team_id THEN gs2.home_max_run
               ELSE gs2.away_max_run END)                            AS max_run_p80
    FROM team_game_diagnostics d
    JOIN games g USING (game_id)
    LEFT JOIN game_state gs2 ON gs2.game_id = d.game_id
    GROUP BY g.league
"""

_TAG = """
    INSERT INTO taggings (tag_id, entity_type, entity_id, weight, tagged_by)
    SELECT t.tag_id, 'team_game', d.game_id || '|' || d.team_id, 1.0, 'engine'
    FROM team_game_diagnostics d
    JOIN games g ON g.game_id = d.game_id
    JOIN ({quartiles}) q ON q.league = g.league
    LEFT JOIN team_game_diagnostics o
           ON o.game_id = d.game_id AND o.team_id = d.opponent_id
    LEFT JOIN game_state gs ON gs.game_id = d.game_id
    -- game_state stores everything home/away; a diagnosis is about one team.
    -- Flipping once here keeps every predicate below written from that team's
    -- point of view instead of repeating a CASE in each one.
    LEFT JOIN LATERAL (
        SELECT (d.team_id = g.home_team_id) AS is_home,
               CASE WHEN d.team_id = g.home_team_id
                    THEN gs.home_q1_points ELSE gs.away_q1_points END AS q1_points,
               CASE WHEN d.team_id = g.home_team_id
                    THEN gs.home_q4_points ELSE gs.away_q4_points END AS q4_points,
               CASE WHEN d.team_id = g.home_team_id
                    THEN gs.home_max_run ELSE gs.away_max_run END AS max_run,
               CASE WHEN d.team_id = g.home_team_id
                    THEN gs.home_max_run_end_q ELSE gs.away_max_run_end_q END AS run_end_q,
               CASE WHEN d.team_id = g.home_team_id
                    THEN gs.home_first_score_q ELSE gs.away_first_score_q END AS first_score_q,
               CASE WHEN d.team_id = g.home_team_id
                    THEN gs.home_open_scoreless_drives
                    ELSE gs.away_open_scoreless_drives END AS open_scoreless,
               CASE WHEN d.team_id = g.home_team_id
                    THEN gs.home_max_scoreless_drives
                    ELSE gs.away_max_scoreless_drives END AS max_scoreless,
               CASE WHEN d.team_id = g.home_team_id
                    THEN gs.home_three_and_outs ELSE gs.away_three_and_outs END AS three_outs,
               (d.points_for > d.points_against) AS won
    ) seq ON TRUE
    CROSS JOIN (SELECT tag_id FROM tags WHERE slug = :slug) t
    WHERE ({predicate})
    ON CONFLICT (tag_id, entity_type, entity_id) DO NOTHING
"""


async def build(leagues: list[str]) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(_BUILD, {"leagues": leagues})
        await conn.execute(text("""
            DELETE FROM taggings USING tags
            WHERE taggings.tag_id = tags.tag_id
              AND tags.dimension = 'diagnostic' AND taggings.entity_type = 'team_game'
        """))
        for slug, predicate in DIAGNOSES:
            await conn.execute(
                text(_TAG.format(quartiles=_QUARTILES, predicate=predicate)),
                {"slug": slug})

        rows = (await conn.execute(text("""
            SELECT g.league, t.slug, count(*) AS n,
                   round(100.0 * count(*) / NULLIF((
                       SELECT count(*) FROM team_game_diagnostics d2
                       JOIN games g2 USING (game_id) WHERE g2.league = g.league), 0), 1) AS pct
            FROM taggings tg
            JOIN tags t ON t.tag_id = tg.tag_id AND t.dimension = 'diagnostic'
            JOIN games g ON g.game_id = split_part(tg.entity_id, '|', 1)
            WHERE tg.entity_type = 'team_game'
            GROUP BY 1, 2 ORDER BY 1, 3 DESC
        """))).mappings().all()

    league = None
    for r in rows:
        if r["league"] != league:
            league = r["league"]
            log.info("\n%s", league)
        log.info("  %-22s %6d  %5s%% of team-games", r["slug"], r["n"], r["pct"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", nargs="+", default=["nfl", "ncaaf"])
    args = ap.parse_args()
    asyncio.run(build(args.league))
