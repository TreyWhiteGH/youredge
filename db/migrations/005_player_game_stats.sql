-- Player game logs + QB trait layer (nflverse weekly stats / Next Gen Stats).
-- Typed columns = what queries filter/aggregate on; full source row in stats JSONB
-- so nothing is lost. QBs get the extra NGS table; other positions don't need it.

CREATE TABLE player_game_stats (
    player_id    TEXT NOT NULL REFERENCES players(player_id),
    season       INT NOT NULL,
    week         INT NOT NULL,
    season_type  TEXT NOT NULL DEFAULT 'regular',
    game_id      TEXT REFERENCES games(game_id),   -- backfilled from (season, week, teams)
    team_id      TEXT,
    opponent_team_id TEXT,
    position     TEXT,
    -- passing
    attempts INT, completions INT, passing_yards REAL, passing_tds INT,
    passing_interceptions INT, sacks_suffered INT, passing_air_yards REAL,
    passing_epa REAL, passing_cpoe REAL,
    -- rushing
    carries INT, rushing_yards REAL, rushing_tds INT, rushing_epa REAL,
    -- receiving
    targets INT, receptions INT, receiving_yards REAL, receiving_tds INT,
    receiving_air_yards REAL, receiving_epa REAL,
    target_share REAL, air_yards_share REAL, wopr REAL,
    stats        JSONB NOT NULL,
    PRIMARY KEY (player_id, season, week)
);
CREATE INDEX idx_pgs_game ON player_game_stats (game_id);
CREATE INDEX idx_pgs_season_week ON player_game_stats (season, week);

CREATE TABLE qb_ngs_weekly (
    player_id    TEXT NOT NULL REFERENCES players(player_id),
    season       INT NOT NULL,
    week         INT NOT NULL,                     -- week 0 = NGS season aggregate
    avg_time_to_throw REAL,
    avg_intended_air_yards REAL,
    avg_completed_air_yards REAL,
    avg_air_yards_to_sticks REAL,
    aggressiveness REAL,
    completion_percentage_above_expectation REAL,
    passer_rating REAL,
    stats        JSONB NOT NULL,
    PRIMARY KEY (player_id, season, week)
);

-- Pass/rush detail the original extraction skipped; filled by re-running nfl_pbp.
ALTER TABLE plays
    ADD COLUMN complete_pass BOOLEAN,
    ADD COLUMN interception BOOLEAN,
    ADD COLUMN touchdown BOOLEAN,
    ADD COLUMN air_yards REAL,
    ADD COLUMN yards_after_catch REAL,
    ADD COLUMN qb_dropback BOOLEAN,
    ADD COLUMN qb_scramble BOOLEAN,
    ADD COLUMN pass_location TEXT,
    ADD COLUMN run_location TEXT,
    ADD COLUMN wpa REAL,
    ADD COLUMN success BOOLEAN,
    ADD COLUMN field_goal_result TEXT;
