-- Training tables.
--
-- The whole point of these is the as-of guarantee: every feature for a game is
-- computed from games that kicked off BEFORE it. Our team cards (defense.py etc.)
-- average over a whole multi-season window, which is fine for describing a team and
-- catastrophic for training — a 2023 game scored with 2025 information will look
-- brilliant on holdout and be worthless live.

-- One row per (team, game): what that team actually did in that game.
CREATE TABLE team_game_form (
    game_id      TEXT NOT NULL REFERENCES games(game_id),
    team_id      TEXT NOT NULL REFERENCES teams(team_id),
    opponent_id  TEXT NOT NULL REFERENCES teams(team_id),
    league       TEXT NOT NULL,
    season       INT NOT NULL,
    week         INT,
    kickoff      TIMESTAMPTZ,
    is_home      BOOLEAN NOT NULL,
    points_for   INT, points_against INT,
    off_epa      REAL, off_pass_epa REAL, off_rush_epa REAL, off_success REAL,
    def_epa      REAL, def_pass_epa REAL, def_rush_epa REAL, def_success REAL,
    off_plays    INT, off_pass_rate REAL,
    PRIMARY KEY (game_id, team_id)
);
CREATE INDEX idx_tgf_team_kick ON team_game_form (team_id, kickoff);

-- One row per game: as-of features for both sides plus the label.
CREATE TABLE game_features (
    game_id       TEXT PRIMARY KEY REFERENCES games(game_id),
    league        TEXT NOT NULL,
    season        INT NOT NULL,
    week          INT,
    kickoff       TIMESTAMPTZ,
    home_team_id  TEXT NOT NULL,
    away_team_id  TEXT NOT NULL,
    -- prior-games counts: the model needs to know how much evidence backs a feature
    home_prior_games INT, away_prior_games INT,
    -- in-season expanding means, current game excluded
    home_off_epa REAL, home_def_epa REAL, home_off_pass_epa REAL, home_off_rush_epa REAL,
    home_def_pass_epa REAL, home_def_rush_epa REAL, home_off_success REAL, home_pass_rate REAL,
    away_off_epa REAL, away_def_epa REAL, away_off_pass_epa REAL, away_off_rush_epa REAL,
    away_def_pass_epa REAL, away_def_rush_epa REAL, away_off_success REAL, away_pass_rate REAL,
    -- prior full season (complete before this season began; a stable early-week prior)
    home_prev_season_off_epa REAL, home_prev_season_def_epa REAL,
    away_prev_season_off_epa REAL, away_prev_season_def_epa REAL,
    -- schedule context
    home_rest_days INT, away_rest_days INT,
    -- label side: market and outcome
    closing_spread REAL,      -- home line, negative = home favored
    closing_total  REAL,
    home_margin    INT,       -- home_score - away_score
    total_points   INT,
    spread_residual REAL,     -- home_margin + closing_spread; >0 = home beat the number
    total_residual  REAL      -- total_points - closing_total
);
CREATE INDEX idx_gf_season ON game_features (league, season);
