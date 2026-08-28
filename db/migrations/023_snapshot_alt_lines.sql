-- Alternate lines make (market_id, captured_at, outcome) too narrow.
--
-- 004 assumed one row per (market, outcome) per poll, which holds for a single
-- spread or total. An alternate-spread market quotes the *same* side at a ladder
-- of numbers in one snapshot — "New England Patriots" at -18.5, -17.5, -16.5 and
-- so on — so the line is part of what makes a quote distinct, not an attribute
-- hanging off it.
--
-- NULLS NOT DISTINCT keeps the original guarantee intact for h2h, where line is
-- NULL: two moneyline rows for the same outcome in one poll still collide.

DROP INDEX IF EXISTS uq_snapshots_market_time_outcome;

CREATE UNIQUE INDEX IF NOT EXISTS uq_snapshots_market_time_outcome_line
    ON odds_snapshots (market_id, captured_at, outcome, line) NULLS NOT DISTINCT;
