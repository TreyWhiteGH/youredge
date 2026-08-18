-- Historical line ingests use captured_at = kickoff, so re-runs inserted exact
-- duplicate snapshots. Live poller rows are safe: captured_at is transaction
-- now(), and each poll writes one row per (market, outcome).

DELETE FROM odds_snapshots a
USING odds_snapshots b
WHERE a.snapshot_id > b.snapshot_id
  AND a.market_id = b.market_id
  AND a.captured_at = b.captured_at
  AND a.outcome = b.outcome;

CREATE UNIQUE INDEX uq_snapshots_market_time_outcome
    ON odds_snapshots (market_id, captured_at, outcome);
