-- Where a snapshot came from.
--
-- Two pollers now write odds_snapshots. odds_poller.py takes pregame prices from The
-- Odds API; sgo_capture.py records in-game movement from SportsGameOdds, which is the
-- only feed here that keeps pricing after kickoff. They share the markets table on
-- purpose -- a spread at DraftKings is the same market whoever quoted it, and forcing
-- two rows for it would split every ladder in half -- but a price with no provenance
-- cannot be audited, and these two disagree in ways that matter: different book
-- coverage, different de-vig, different update cadence.
--
-- `is_live` was already here from day one and is not the same claim. It says a price
-- was quoted after kickoff; this says which feed reported it. A pregame SGO capture is
-- source='sgo' and is_live=false, and both facts are worth keeping.
ALTER TABLE odds_snapshots
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'odds_api';

-- Existing rows all predate SGO, so the default is already correct for them and no
-- backfill is needed. The default stays on the column rather than being dropped: it
-- keeps odds_poller.py's INSERT working unchanged, which is one less thing to get
-- wrong in a file that is polling a metered API.

-- The live surface is read as "this game, this market, most recent first" -- the query
-- behind any in-game price -- and without this it is a scan of 358k rows and climbing.
CREATE INDEX IF NOT EXISTS idx_snapshots_live
    ON odds_snapshots (market_id, captured_at DESC) WHERE is_live;
