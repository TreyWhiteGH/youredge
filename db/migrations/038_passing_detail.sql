-- CFBD's passing endpoints: intended target, and the air-yards fields when they
-- arrive.
--
-- The announcement leads with air yards, ADOT, yards after catch and pass
-- locations. Measured against 2025 week 8, those are 2-3% populated, and 2023
-- and 2024 return nothing at all — so they are wired up but not depended on.
--
-- What is actually usable is the field the announcement does not lead with:
-- targetId, present on 96% of completions and **89% of incompletions**. CFBD's
-- play text names the intended receiver on roughly 9% of incompletions, which is
-- why target share has been undercounting from every source we had. This closes
-- that, for 2025.
--
-- plays already carries air_yards, yards_after_catch and pass_location as
-- nflverse columns that were NULL for college; those get filled rather than
-- duplicated. pass_depth is new because nflverse folds short/deep into
-- pass_location and CFBD splits them.

ALTER TABLE plays ADD COLUMN IF NOT EXISTS pass_depth TEXT;      -- short | deep
ALTER TABLE plays ADD COLUMN IF NOT EXISTS is_throwaway BOOLEAN;
ALTER TABLE plays ADD COLUMN IF NOT EXISTS target_player_id TEXT REFERENCES players(player_id);

CREATE INDEX IF NOT EXISTS idx_plays_target ON plays (target_player_id)
    WHERE target_player_id IS NOT NULL;

-- A third provenance for attribution rows. Kept distinct from cfbd_stats because
-- it comes from a different endpoint with different coverage, and from playtext
-- because it is fed rather than inferred.
ALTER TABLE play_players DROP CONSTRAINT IF EXISTS play_players_source_check;
ALTER TABLE play_players ADD CONSTRAINT play_players_source_check
    CHECK (source IN ('cfbd_stats', 'playtext', 'cfbd_passing'));
