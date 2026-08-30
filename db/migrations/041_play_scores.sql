-- Absolute scoreboard on every play.
--
-- plays.score_differential is (offense - defense), which is enough to know who
-- is ahead and useless for knowing by how much either side actually scored.
-- Reconstructing a scoring sequence from it means flipping the sign by
-- possession, and that inverts wherever offense/defense attribution is off --
-- producing phantom runs of points that cancel out to the right final margin
-- while being wrong at every step in between.
--
-- CFBD ships offenseScore and defenseScore on every play, alongside home and
-- away, and nflverse ships total_home_score / total_away_score. Both were read
-- and discarded. Stored absolutely, they settle three things the differential
-- cannot: a missed PAT, a two-point conversion, and a defensive or return
-- touchdown that belongs to no offensive drive.
ALTER TABLE plays
    ADD COLUMN IF NOT EXISTS home_score INT,
    ADD COLUMN IF NOT EXISTS away_score INT;

COMMENT ON COLUMN plays.home_score IS
    'Home points on the scoreboard at this play. Authoritative for scoring sequence; prefer over score_differential.';
COMMENT ON COLUMN plays.away_score IS
    'Away points on the scoreboard at this play.';
