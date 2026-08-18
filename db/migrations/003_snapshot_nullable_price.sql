-- CFBD historical lines carry spreads/totals without prices (except moneylines).
-- Allow NULL price on snapshots; implied_prob is derived so it goes nullable too.
-- Apply with: make migrate

BEGIN;
ALTER TABLE odds_snapshots ALTER COLUMN price_american DROP NOT NULL;
ALTER TABLE odds_snapshots ALTER COLUMN implied_prob DROP NOT NULL;
COMMIT;
