-- Distinguish a drive that ended in a return touchdown from one where the
-- offence scored.
--
-- The first NFL derivation checked "did a touchdown happen on this drive" before
-- it checked for turnovers, so every pick-six and scoop-and-score was filed as an
-- offensive TD worth 7 points to the team that had just thrown the interception:
-- 609 of 13,994 TD drives, 4.4%. A simulator fit on that would learn that
-- turnovers sometimes pay the offence.
--
-- CFBD names these explicitly for college ('INT TD', 'FUMBLE RETURN TD',
-- 'PUNT RETURN TD', 'MISSED FG TD'), so both leagues can now say the same thing:
-- the drive's `result` is the turnover, `points` stays 0 for the possessing team,
-- and defensive_td records that the other side scored on the return.

ALTER TABLE drives ADD COLUMN IF NOT EXISTS defensive_td BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN drives.defensive_td IS
    'The defence scored on this possession (return TD). result holds how the '
    'offence lost the ball; points is the offence''s points and stays 0.';
