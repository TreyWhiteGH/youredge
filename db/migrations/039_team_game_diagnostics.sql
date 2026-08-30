-- Why a team is winning or losing, per team per game.
--
-- The script tags already in `tags` describe the *shape* of a game — blowout,
-- shootout, grind. These describe the *mechanism*: this team lost despite moving
-- the ball because it gave the ball away three times; this quarterback never
-- threw past the sticks; this offence was run off the field.
--
-- That is a different grain. A script belongs to a game; a diagnosis belongs to
-- one team within one game, because both sides of the same game get different
-- ones. `taggings` is already polymorphic, so it gains an entity type rather
-- than a parallel table: entity_id is 'game_id|team_id'.

ALTER TABLE taggings DROP CONSTRAINT IF EXISTS taggings_entity_type_check;
ALTER TABLE taggings ADD CONSTRAINT taggings_entity_type_check
    CHECK (entity_type = ANY (ARRAY['game', 'team_game', 'script', 'leg', 'bet',
                                    'angle', 'debrief']));

ALTER TABLE tags DROP CONSTRAINT IF EXISTS tags_dimension_check;
ALTER TABLE tags ADD CONSTRAINT tags_dimension_check
    CHECK (dimension = ANY (ARRAY['script', 'leg_role', 'angle', 'outcome',
                                  'diagnostic']));

-- The measurements the diagnoses are read off. Stored rather than recomputed
-- because the thresholds are league-relative percentiles, so the whole
-- distribution has to exist before any single game can be judged.
CREATE TABLE IF NOT EXISTS team_game_diagnostics (
    game_id       TEXT NOT NULL REFERENCES games(game_id),
    team_id       TEXT NOT NULL REFERENCES teams(team_id),
    opponent_id   TEXT REFERENCES teams(team_id),

    points_for    INT,
    points_against INT,

    -- Ball security
    giveaways     INT,          -- interceptions thrown + fumbles lost
    takeaways     INT,
    turnover_margin INT,

    -- Ground game
    rush_att      INT,
    rush_yards    REAL,
    rush_epa      REAL,
    rush_success  REAL,
    rush_epa_allowed REAL,

    -- Passing and the quarterback
    dropbacks     INT,
    pass_epa      REAL,
    pass_success  REAL,
    sacks_taken   INT,
    sack_rate     REAL,
    -- NULL where air yards are unavailable, which is most of the sample. NULL
    -- means unmeasured; it must never read as "threw everything short".
    adot          REAL,
    deep_rate     REAL,
    air_yards_n   INT,

    -- Situational
    rz_trips      INT,
    rz_tds        INT,
    third_att     INT,
    third_conv    INT,
    explosive_rate REAL,
    penalties     INT,
    avg_start_yardline REAL,

    -- Leverage: share of offensive yards gained while already down two scores.
    -- High values are how a box score flatters a team that was never in it.
    garbage_yard_share REAL,

    built_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (game_id, team_id)
);

CREATE INDEX IF NOT EXISTS idx_tgd_team ON team_game_diagnostics (team_id);

INSERT INTO tags (slug, dimension, description, status, source) VALUES
 ('TURNOVER_LOSS',      'diagnostic', 'Lost while moving the ball; giveaways decided it', 'active', 'seed'),
 ('TURNOVER_FUELED_WIN','diagnostic', 'Won on takeaways rather than on offence', 'active', 'seed'),
 ('BALL_SECURITY_ISSUE','diagnostic', 'Three or more giveaways', 'active', 'seed'),
 ('TAKEAWAY_BURST',     'diagnostic', 'Defence forced three or more turnovers', 'active', 'seed'),
 ('GROUND_CONTROL',     'diagnostic', 'Ran the ball at will: heavy volume, top-quartile efficiency', 'active', 'seed'),
 ('RUN_STUFFED',        'diagnostic', 'Ran often and got nothing for it', 'active', 'seed'),
 ('RUN_D_GASHED',       'diagnostic', 'Run defence gave up top-quartile efficiency', 'active', 'seed'),
 ('SHAKY_QB',           'diagnostic', 'Bottom-quartile dropback EPA with multiple sacks or picks', 'active', 'seed'),
 ('SURGICAL_QB',        'diagnostic', 'Top-quartile dropback EPA with at most one giveaway', 'active', 'seed'),
 ('QB_UNDER_SIEGE',     'diagnostic', 'Top-quartile sack rate', 'active', 'seed'),
 ('NO_DEEP_SHOT',       'diagnostic', 'Almost nothing thrown past 15 air yards (needs air-yard data)', 'active', 'seed'),
 ('CHECKDOWN_HEAVY',    'diagnostic', 'Bottom-quartile average depth of target (needs air-yard data)', 'active', 'seed'),
 ('RED_ZONE_STALL',     'diagnostic', 'Reached the red zone repeatedly and came away without touchdowns', 'active', 'seed'),
 ('THIRD_DOWN_FAILURE', 'diagnostic', 'Bottom-quartile third-down conversion', 'active', 'seed'),
 ('THIRD_DOWN_SHARP',   'diagnostic', 'Top-quartile third-down conversion', 'active', 'seed'),
 ('EXPLOSIVE_OFFENSE',  'diagnostic', 'Top-quartile rate of chunk plays', 'active', 'seed'),
 ('FIELD_POSITION_EDGE','diagnostic', 'Started drives materially closer to the end zone than the opponent', 'active', 'seed'),
 ('PENALTY_PLAGUED',    'diagnostic', 'Top-quartile penalty count', 'active', 'seed'),
 ('EMPTY_CALORIES',     'diagnostic', 'Most of the offence arrived after the game was already gone', 'active', 'seed')
ON CONFLICT (slug) DO NOTHING;
