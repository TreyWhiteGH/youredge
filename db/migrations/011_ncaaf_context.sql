-- NCAAF context layer: coaching and roster experience.
--
-- College is not a player-stats sport the way the NFL is: the portal churns rosters,
-- so last year's player grades travel poorly. Coaching and returning production carry
-- the signal, and the spread is huge (2025: Navy returned 97.3% of production, New
-- Mexico 2.8%).
--
-- Everything here is COACH-keyed, not team-keyed, because the signal moves with the
-- coach. Cignetti at JMU (2022-23) and Indiana (2024-25) is one career, not two.

CREATE TABLE coaches (
    coach_id        TEXT PRIMARY KEY,          -- 'cfbd_coach:<id>'
    name            TEXT NOT NULL,
    first_season    INT,
    history_seasons INT NOT NULL DEFAULT 0     -- FBS seasons we can see; FCS years are
                                               -- absent from CFBD, so short history
                                               -- means uncertain, not average
);

CREATE TABLE coach_seasons (
    coach_id     TEXT NOT NULL REFERENCES coaches(coach_id),
    team_id      TEXT NOT NULL REFERENCES teams(team_id),
    season       INT NOT NULL,
    games        INT, wins INT, losses INT, ties INT,
    win_pct      REAL,
    srs          REAL,
    sp_overall   REAL, sp_offense REAL, sp_defense REAL,
    preseason_rank INT, postseason_rank INT,
    hire_date    DATE,
    tenure_year  INT,                          -- 1 = first year at THIS school
    is_first_year_at_school BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (coach_id, team_id, season)
);
CREATE INDEX idx_coach_seasons_team ON coach_seasons (team_id, season);

-- Derived from ALL prior seasons at ANY school — this is the portable signal.
CREATE TABLE coach_features (
    coach_id            TEXT NOT NULL REFERENCES coaches(coach_id),
    season              INT NOT NULL,
    team_id             TEXT REFERENCES teams(team_id),
    career_sp_residual  REAL,     -- mean SP+ minus what their talent predicted
    career_sp_mean      REAL,
    prior_school_trajectory REAL, -- SP+ slope over prior seasons
    seasons_of_history  INT NOT NULL DEFAULT 0,
    arrived_this_season BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (coach_id, season)
);

CREATE TABLE team_season_context (
    team_id      TEXT NOT NULL REFERENCES teams(team_id),
    season       INT NOT NULL,
    -- returning production (CFBD /player/returning)
    pct_ppa            REAL, pct_passing_ppa REAL,
    pct_rushing_ppa    REAL, pct_receiving_ppa REAL,
    usage              REAL, passing_usage REAL,
    rushing_usage      REAL, receiving_usage REAL,
    total_ppa          REAL,
    -- talent & recruiting
    talent             REAL,
    recruiting_rank    INT, recruiting_points REAL,
    -- SP+ (team level)
    sp_overall REAL, sp_offense REAL, sp_defense REAL, sp_ranking INT,
    -- portal: NULL before 2021 (CFBD has no data), which is NOT the same as zero
    portal_in          INT, portal_out INT,
    portal_in_stars    REAL, portal_out_stars REAL,
    PRIMARY KEY (team_id, season)
);

CREATE TABLE transfers (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    season         INT NOT NULL,
    player_name    TEXT NOT NULL,
    position       TEXT,
    origin_team_id      TEXT REFERENCES teams(team_id),
    destination_team_id TEXT REFERENCES teams(team_id),
    stars          INT,
    rating         REAL,
    eligibility    TEXT,
    transfer_date  DATE,
    UNIQUE (season, player_name, origin_team_id, destination_team_id)
);
CREATE INDEX idx_transfers_dest ON transfers (destination_team_id, season);
CREATE INDEX idx_transfers_origin ON transfers (origin_team_id, season);
