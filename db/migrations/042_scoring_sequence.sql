-- Sequence, not just totals.
--
-- Every script tag so far is a predicate over aggregates: final margin, peak
-- lead, whole-game pass rate. None of them know what order anything happened
-- in, which is why a team scoring twenty unanswered points in the fourth
-- quarter produced no tag, and why a team held scoreless through eight straight
-- possessions produced no tag either. Both are among the most describable things
-- that happen in a football game.
--
-- These columns are all read off the scoreboard timeline in `plays` (see
-- migration 041), which is exact: it sees missed extra points, two-point
-- conversions and return touchdowns, none of which the drive table gets right.
ALTER TABLE game_state
    -- Points by quarter, per side. Underpins cold starts, late surges and any
    -- question about when a team's offence actually showed up.
    ADD COLUMN IF NOT EXISTS home_q1_points INT,
    ADD COLUMN IF NOT EXISTS home_q2_points INT,
    ADD COLUMN IF NOT EXISTS home_q3_points INT,
    ADD COLUMN IF NOT EXISTS home_q4_points INT,
    ADD COLUMN IF NOT EXISTS away_q1_points INT,
    ADD COLUMN IF NOT EXISTS away_q2_points INT,
    ADD COLUMN IF NOT EXISTS away_q3_points INT,
    ADD COLUMN IF NOT EXISTS away_q4_points INT,
    -- The largest run of points scored without the opponent answering, and the
    -- quarter it ended in. A 20-0 run is the same number whether it decided the
    -- game in the first half or nearly stole it in the fourth; the quarter is
    -- what separates those two stories.
    ADD COLUMN IF NOT EXISTS home_max_run INT,
    ADD COLUMN IF NOT EXISTS away_max_run INT,
    ADD COLUMN IF NOT EXISTS home_max_run_end_q INT,
    ADD COLUMN IF NOT EXISTS away_max_run_end_q INT,
    -- Quarter of a side's first points. NULL means they never scored.
    ADD COLUMN IF NOT EXISTS home_first_score_q INT,
    ADD COLUMN IF NOT EXISTS away_first_score_q INT,
    -- Possessions, from `drives`: how many a side opened with before scoring,
    -- and its longest scoreless stretch at any point. Drives are the right grain
    -- here because a drought is measured in chances, not in minutes.
    ADD COLUMN IF NOT EXISTS home_open_scoreless_drives INT,
    ADD COLUMN IF NOT EXISTS away_open_scoreless_drives INT,
    ADD COLUMN IF NOT EXISTS home_max_scoreless_drives INT,
    ADD COLUMN IF NOT EXISTS away_max_scoreless_drives INT,
    ADD COLUMN IF NOT EXISTS home_three_and_outs INT,
    ADD COLUMN IF NOT EXISTS away_three_and_outs INT,
    -- Game seconds remaining at the final change of leader. Small values mean
    -- the game turned over late, which is a different game from one decided in
    -- the second quarter and never threatened again.
    ADD COLUMN IF NOT EXISTS last_lead_change_sec INT;

COMMENT ON COLUMN game_state.home_max_run IS
    'Most consecutive points scored by home without away answering. Read from the plays scoreboard, so conversions and return TDs are included.';
