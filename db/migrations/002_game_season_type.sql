-- CFBD files the entire postseason under week=1; without this column a January
-- CFP game is indistinguishable from opening weekend. NFL playoffs are weeks
-- 19-22 but get the explicit marker too.

ALTER TABLE games ADD COLUMN season_type TEXT NOT NULL DEFAULT 'regular'
    CHECK (season_type IN ('regular', 'postseason'));

-- Backfill NFL playoffs already ingested (weeks 19+ in nflverse numbering).
UPDATE games SET season_type = 'postseason' WHERE league = 'nfl' AND week > 18;
