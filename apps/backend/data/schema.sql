-- Historical sports games and analytics database schema

-- Main games table
CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    sport TEXT NOT NULL,
    season INTEGER,
    week_number INTEGER,
    game_date TEXT NOT NULL,
    start_time TEXT,
    home_team_id TEXT,
    away_team_id TEXT,
    home_team_name TEXT,
    away_team_name TEXT,
    home_score INTEGER,
    away_score INTEGER,
    status TEXT,
    espn_event_id TEXT UNIQUE,
    venue TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_games_sport_date ON games(sport, game_date);
CREATE INDEX IF NOT EXISTS idx_games_espn_id ON games(espn_event_id);
CREATE INDEX IF NOT EXISTS idx_games_season ON games(sport, season);

-- Play-by-play events for games
CREATE TABLE IF NOT EXISTS game_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL,
    period INTEGER,
    clock_seconds INTEGER,
    event_type TEXT,
    team_id TEXT,
    description TEXT,
    home_score INTEGER,
    away_score INTEGER,
    timestamp TEXT,
    raw_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(game_id)
);

CREATE INDEX IF NOT EXISTS idx_game_events_game_id ON game_events(game_id);
CREATE INDEX IF NOT EXISTS idx_game_events_game_time ON game_events(game_id, clock_seconds);

-- Team context snapshots from sports_ai framework
CREATE TABLE IF NOT EXISTS team_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    timestamp TEXT,
    period INTEGER,
    clock_seconds INTEGER,
    score_diff INTEGER,
    game_state TEXT,
    time_bucket TEXT,
    -- Serialized ContextSnapshot JSON from sports_ai
    snapshot_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(game_id)
);

CREATE INDEX IF NOT EXISTS idx_team_snapshots_game_team ON team_snapshots(game_id, team_id);
CREATE INDEX IF NOT EXISTS idx_team_snapshots_game_id ON team_snapshots(game_id);

-- Historical betting odds
CREATE TABLE IF NOT EXISTS historical_odds (
    odds_id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL,
    bookmaker TEXT,
    market TEXT,
    home_odds REAL,
    away_odds REAL,
    home_point REAL,
    away_point REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(game_id)
);

CREATE INDEX IF NOT EXISTS idx_historical_odds_game_market ON historical_odds(game_id, market);
CREATE INDEX IF NOT EXISTS idx_historical_odds_bookmaker ON historical_odds(bookmaker);

-- Training labels (ground truth for ML models)
CREATE TABLE IF NOT EXISTS training_labels (
    label_id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL,
    market TEXT,
    selection TEXT,
    line REAL,
    outcome BOOLEAN,
    actual_margin REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(game_id)
);

CREATE INDEX IF NOT EXISTS idx_training_labels_game_market ON training_labels(game_id, market);

-- Team stats (pre-calculated for feature engineering)
CREATE TABLE IF NOT EXISTS team_stats (
    stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport TEXT NOT NULL,
    team_id TEXT NOT NULL,
    game_date TEXT,
    -- Recent averages (last 5, 10, 20 games)
    off_rating_5 REAL,
    def_rating_5 REAL,
    pace_5 REAL,
    off_rating_10 REAL,
    def_rating_10 REAL,
    pace_10 REAL,
    off_rating_season REAL,
    def_rating_season REAL,
    pace_season REAL,
    -- Record
    wins INTEGER,
    losses INTEGER,
    win_streak INTEGER,
    loss_streak INTEGER,
    home_wins INTEGER,
    home_losses INTEGER,
    away_wins INTEGER,
    away_losses INTEGER,
    -- Other stats
    ast_per_game REAL,
    tov_per_game REAL,
    reb_per_game REAL,
    fg_pct REAL,
    three_pct REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_team_stats_team_date ON team_stats(sport, team_id, game_date);
CREATE INDEX IF NOT EXISTS idx_team_stats_sport ON team_stats(sport);

-- Predictions made by models (for monitoring and evaluation)
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL,
    sport TEXT NOT NULL,
    market TEXT,
    model_version TEXT,
    selection TEXT,
    predicted_line REAL,
    confidence REAL,
    edge REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved BOOLEAN DEFAULT 0,
    correct BOOLEAN,
    resolved_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_predictions_game_model ON predictions(game_id, model_version);
CREATE INDEX IF NOT EXISTS idx_predictions_resolved ON predictions(resolved);
CREATE INDEX IF NOT EXISTS idx_predictions_created ON predictions(created_at);

-- Model metadata and versions
CREATE TABLE IF NOT EXISTS model_metadata (
    model_id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL UNIQUE,
    sport TEXT NOT NULL,
    market TEXT NOT NULL,
    version TEXT,
    path TEXT,
    features_json TEXT,
    accuracy REAL,
    roi_pct REAL,
    win_rate REAL,
    sharpe_ratio REAL,
    max_drawdown REAL,
    num_backtests INTEGER,
    training_start_date TEXT,
    training_end_date TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_model_metadata_active ON model_metadata(is_active);
