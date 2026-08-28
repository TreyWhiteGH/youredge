-- Widen the market surface: props, period lines, alternates, team totals.
--
-- Until now the poller asked for h2h/spreads/totals only, so every SGP claim the
-- product wants to make had nothing to price against. These columns are what the
-- wider poll needs to land somewhere honest.

-- The closing snapshot is the one price you cannot reconstruct after kickoff, and
-- every CLV number and every backtest is measured against it. Flag it explicitly
-- rather than inferring "last row before kickoff", which silently lies whenever a
-- poll was missed.
ALTER TABLE odds_snapshots ADD COLUMN IF NOT EXISTS is_closing BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE odds_snapshots ADD COLUMN IF NOT EXISTS is_opening BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_snapshots_closing
    ON odds_snapshots (market_id) WHERE is_closing;

-- Prop markets name a player the books spell their own way. Resolution against
-- players/entity_xwalk will not be perfect on day one, and a row we cannot resolve
-- is still a price worth keeping — so store the raw name and let player_id stay
-- NULL until a later pass fills it in. Dropping unresolved props would quietly
-- discard exactly the market surface we are here to collect.
ALTER TABLE markets ADD COLUMN IF NOT EXISTS player_name TEXT;

-- Team-total and team-side period markets belong to one side of the game.
ALTER TABLE markets ADD COLUMN IF NOT EXISTS side_team_id TEXT REFERENCES teams(team_id);

-- Reading "every prop on this game" is the Bet Lab's hot path.
CREATE INDEX IF NOT EXISTS idx_markets_game_key ON markets (game_id, market_key);
CREATE INDEX IF NOT EXISTS idx_markets_player ON markets (player_id) WHERE player_id IS NOT NULL;

-- markets is UNIQUE NULLS NOT DISTINCT (game_id, bookmaker, market_key, player_id).
-- Props keyed by an unresolved player would all collapse onto the single NULL
-- player_id row for that market_key, so the raw name has to participate in identity.
-- It arrives as a UNIQUE CONSTRAINT, so the backing index goes with it.
ALTER TABLE markets DROP CONSTRAINT IF EXISTS markets_game_id_bookmaker_market_key_player_id_key;
CREATE UNIQUE INDEX IF NOT EXISTS markets_identity_key
    ON markets (game_id, bookmaker, market_key, player_id, player_name)
    NULLS NOT DISTINCT;
