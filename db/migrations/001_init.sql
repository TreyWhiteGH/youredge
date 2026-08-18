-- YourEdge core schema (Phase 0)
-- Runs automatically on first `docker compose up` via /docker-entrypoint-initdb.d

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============ Reference ============

CREATE TABLE teams (
    team_id      TEXT PRIMARY KEY,              -- canonical: 'nfl:BAL', 'ncaaf:333'
    league       TEXT NOT NULL CHECK (league IN ('nfl', 'ncaaf')),
    abbr         TEXT NOT NULL,
    name         TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE players (
    player_id    TEXT PRIMARY KEY,              -- canonical: 'nfl:00-0034796'
    league       TEXT NOT NULL CHECK (league IN ('nfl', 'ncaaf')),
    team_id      TEXT REFERENCES teams(team_id),
    name         TEXT NOT NULL,
    position     TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Entity resolution across sources (nflverse / CFBD / odds feeds / ESPN).
-- The unglamorous table everything depends on.
CREATE TABLE entity_xwalk (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_type  TEXT NOT NULL CHECK (entity_type IN ('team', 'player', 'game')),
    canonical_id TEXT NOT NULL,
    source       TEXT NOT NULL,                 -- 'nflverse' | 'cfbd' | 'odds_api' | 'espn' | 'sgo'
    source_id    TEXT NOT NULL,
    confidence   REAL NOT NULL DEFAULT 1.0,
    UNIQUE (entity_type, source, source_id)
);
CREATE INDEX idx_xwalk_canonical ON entity_xwalk (entity_type, canonical_id);

-- ============ Games & plays ============

CREATE TABLE games (
    game_id      TEXT PRIMARY KEY,              -- canonical: 'nfl:2026_01_BAL_CIN'
    league       TEXT NOT NULL CHECK (league IN ('nfl', 'ncaaf')),
    season       INT NOT NULL,
    week         INT,
    kickoff      TIMESTAMPTZ,
    home_team_id TEXT REFERENCES teams(team_id),
    away_team_id TEXT REFERENCES teams(team_id),
    status       TEXT NOT NULL DEFAULT 'scheduled'
                 CHECK (status IN ('scheduled', 'live', 'final', 'cancelled')),
    home_score   INT,
    away_score   INT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_games_league_season_week ON games (league, season, week);
CREATE INDEX idx_games_kickoff ON games (kickoff);

-- PBP lands raw-ish; tendency features are computed FROM this, not stored on it.
CREATE TABLE plays (
    play_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    game_id      TEXT NOT NULL REFERENCES games(game_id),
    source_play_id TEXT,
    quarter      INT,
    game_seconds_remaining INT,
    drive_num    INT,
    posteam_id   TEXT,
    defteam_id   TEXT,
    down         INT,
    ydstogo      INT,
    yardline_100 INT,
    play_type    TEXT,
    yards_gained REAL,
    epa          REAL,
    wp           REAL,
    score_differential INT,                     -- posteam perspective, pre-snap
    passer_player_id TEXT,
    rusher_player_id TEXT,
    receiver_player_id TEXT,
    raw          JSONB,                         -- full source row for anything not extracted
    UNIQUE (game_id, source_play_id)
);
CREATE INDEX idx_plays_game ON plays (game_id);
CREATE INDEX idx_plays_posteam_state ON plays (posteam_id, quarter, score_differential);

-- ============ Odds ============

-- A market is a book's priced question; a leg is one selectable side of it.
CREATE TABLE markets (
    market_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    game_id      TEXT NOT NULL REFERENCES games(game_id),
    bookmaker    TEXT NOT NULL,
    market_key   TEXT NOT NULL,                 -- 'spreads', 'totals', 'player_pass_yds', 'team_totals_2h', ...
    player_id    TEXT REFERENCES players(player_id),
    UNIQUE NULLS NOT DISTINCT (game_id, bookmaker, market_key, player_id)
);

CREATE TABLE odds_snapshots (
    snapshot_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    market_id    BIGINT NOT NULL REFERENCES markets(market_id),
    captured_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    outcome      TEXT NOT NULL,                 -- 'over' | 'under' | 'BAL' | ...
    line         REAL,                          -- 44.5, -6.5, NULL for h2h
    price_american INT,                         -- -110; NULL for priceless historical lines (CFBD)
    implied_prob REAL,                          -- with vig; NULL when price is NULL
    fair_prob    REAL,                          -- de-vigged (filled by engine)
    is_live      BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX idx_snapshots_market_time ON odds_snapshots (market_id, captured_at DESC);

-- ============ Tagging (first-class, day one) ============

CREATE TABLE tags (
    tag_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug         TEXT NOT NULL UNIQUE,          -- 'SHOOTOUT', 'Q4_PASS_D_FADE'
    dimension    TEXT NOT NULL CHECK (dimension IN ('script', 'leg_role', 'angle', 'outcome')),
    description  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active'
                 CHECK (status IN ('candidate', 'active', 'deprecated')),
    source       TEXT NOT NULL DEFAULT 'seed'
                 CHECK (source IN ('seed', 'miner', 'manual')),
    motivation   JSONB,                         -- miner: the statistical split that motivated it
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    promoted_at  TIMESTAMPTZ,
    deprecated_at TIMESTAMPTZ
);

-- Polymorphic taggings: anything can carry tags.
CREATE TABLE taggings (
    tagging_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tag_id       BIGINT NOT NULL REFERENCES tags(tag_id),
    entity_type  TEXT NOT NULL CHECK (entity_type IN
                 ('game', 'script', 'leg', 'bet', 'angle', 'debrief')),
    entity_id    TEXT NOT NULL,
    weight       REAL,                          -- e.g. sim probability of script tag for a game
    tagged_by    TEXT NOT NULL DEFAULT 'engine' CHECK (tagged_by IN ('engine', 'llm', 'user', 'miner')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tag_id, entity_type, entity_id)
);
CREATE INDEX idx_taggings_entity ON taggings (entity_type, entity_id);
CREATE INDEX idx_taggings_tag ON taggings (tag_id);

-- Game Tag Surface: top script tags per game, ranked by sim probability.
CREATE VIEW game_scripts AS
SELECT t2.entity_id AS game_id,
       t.slug,
       t.dimension,
       t2.weight AS sim_probability,
       t2.created_at
FROM taggings t2
JOIN tags t ON t.tag_id = t2.tag_id
WHERE t2.entity_type = 'game'
  AND t.status IN ('active', 'candidate')
ORDER BY t2.entity_id, t2.weight DESC NULLS LAST;

-- ============ Bets & memory ============

CREATE TABLE user_bets (
    bet_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      TEXT NOT NULL,
    game_id      TEXT NOT NULL REFERENCES games(game_id),
    bookmaker    TEXT NOT NULL,
    mode         TEXT NOT NULL CHECK (mode IN ('generate', 'build_around', 'hypothesis', 'critique', 'manual')),
    legs         JSONB NOT NULL,                -- [{market_key, outcome, line, price_american}]
    quoted_price_american INT,
    fair_prob_at_rec REAL,                      -- engine's joint prob at rec time
    edge_at_rec  REAL,
    sim_snapshot_ref TEXT,                      -- pointer to stored pregame sim (debriefs need this)
    closing_price_american INT,                 -- filled at kickoff → CLV
    result       TEXT CHECK (result IN ('win', 'loss', 'push', 'void')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_user_bets_user ON user_bets (user_id, created_at DESC);

-- ============ Seed tags ============

INSERT INTO tags (slug, dimension, description, source) VALUES
-- script
('BLOWOUT_FAV',       'script', 'Favorite controls throughout; starters may rest late', 'seed'),
('SHOOTOUT',          'script', 'Both offenses efficient; high pace, high total', 'seed'),
('GRIND',             'script', 'Low pace, run-heavy, defensive; under-leaning', 'seed'),
('BACKDOOR',          'script', 'Favorite leads big, dog scores late vs soft coverage', 'seed'),
('FAST_START_FADE',   'script', 'Team scores early then goes conservative / fades', 'seed'),
('GARBAGE_TIME_PASS', 'script', 'Trailing team accumulates late passing volume', 'seed'),
('COMEBACK',          'script', 'Trailing team completes comeback; lead change in 4Q', 'seed'),
('CLOCK_KILL',        'script', 'Leading team runs clock; 4Q play volume collapses', 'seed'),
-- leg_role
('ANCHOR',            'leg_role', 'User or engine anchor leg', 'seed'),
('CORRELATE',         'leg_role', 'Positively correlated with anchor above threshold', 'seed'),
('LOTTO',             'leg_role', 'Long-tail script region leg', 'seed'),
('REDUNDANT',         'leg_role', 'Proxies same event as another leg', 'seed'),
('SCRIPT_CONFLICT',   'leg_role', 'Lives in a sim region that contradicts other legs', 'seed'),
('NEG_EV',            'leg_role', 'Negative expected value at quoted price', 'seed'),
-- angle
('RUN_D',             'angle', 'Run defense unit', 'seed'),
('PASS_D',            'angle', 'Pass defense unit', 'seed'),
('RUN_O',             'angle', 'Run offense unit', 'seed'),
('PASS_O',            'angle', 'Pass offense unit', 'seed'),
('Q1', 'angle', 'First quarter situation', 'seed'),
('Q4', 'angle', 'Fourth quarter situation', 'seed'),
('H1', 'angle', 'First half situation', 'seed'),
('H2', 'angle', 'Second half situation', 'seed'),
('RED_ZONE',          'angle', 'Red zone situation', 'seed'),
('REST_ADVANTAGE',    'angle', 'Bye/short-week rest differential', 'seed'),
('HOME_DOG',          'angle', 'Home underdog situation', 'seed'),
('DIVISIONAL',        'angle', 'Divisional matchup (NFL)', 'seed'),
('AI_MINED',          'angle', 'Discovered by the Angle Miner', 'seed'),
('USER_THEORY',       'angle', 'Originated from a user hypothesis', 'seed'),
-- outcome
('PROCESS_WIN',       'outcome', 'Read was right regardless of result', 'seed'),
('VARIANCE_LOSS',     'outcome', 'Script hit; lost to noise (fluke TD, missed kick)', 'seed'),
('BAD_READ',          'outcome', 'Script never materialized', 'seed'),
('SCRIPT_HIT',        'outcome', 'Game landed in the bet''s script region', 'seed'),
('SCRIPT_MISS',       'outcome', 'Game landed outside the bet''s script region', 'seed');
