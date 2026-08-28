-- Play-grain scoring and turnover flags for NCAAF, plus the source's own words.
--
-- These columns already exist and are populated for the NFL. They were NULL for
-- college not because CFBD withholds them but because `cfbd_map.map_play_type`
-- folds CFBD's precise vocabulary — 'Rushing Touchdown', 'Field Goal Good',
-- 'Fumble Recovery (Opponent)' — into eight nflverse-shaped buckets on the way
-- in, and nothing kept the detail it discarded.
--
-- The flattening itself is correct and stays: the coarse vocabulary is what lets
-- both leagues share query paths. The bug was throwing the detail away rather
-- than producing the summary, so now both coexist.
--
-- play_type_raw is stored for every league unconditionally. Mapping a vendor's
-- taxonomy onto ours is a judgement call, and keeping the original makes those
-- calls auditable and revisable without re-fetching a season — the same reason
-- drives.result_raw exists.

ALTER TABLE plays ADD COLUMN IF NOT EXISTS play_type_raw TEXT;
ALTER TABLE plays ADD COLUMN IF NOT EXISTS scoring       BOOLEAN;

COMMENT ON COLUMN plays.play_type_raw IS
    'The source''s own play-type string, before map_play_type folded it into the '
    'shared vocabulary. NCAAF: CFBD playType. NULL for rows loaded before 030.';

CREATE INDEX IF NOT EXISTS idx_plays_type_raw ON plays (play_type_raw)
    WHERE play_type_raw IS NOT NULL;
