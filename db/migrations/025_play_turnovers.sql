-- Columns the drive kernel needs that the first ingest did not extract.
--
-- A drive-level simulator is a distribution over how possessions end, so the
-- ways a drive can end have to be representable. Without fumble_lost, every lost
-- fumble collapses into an "other" bucket alongside end-of-half — two events with
-- nothing in common: one is a turnover that hands the opponent the ball at a live
-- field position, the other is the clock running out. Turnovers are also where
-- script variance actually lives, so folding them away would bias the sim toward
-- tidier games than football produces.
--
-- safety, penalty and sack come along because they are free at ingest time and
-- sack is what separates a called pass from a scramble in the pass/run mix.

ALTER TABLE plays ADD COLUMN IF NOT EXISTS fumble_lost BOOLEAN;
ALTER TABLE plays ADD COLUMN IF NOT EXISTS safety      BOOLEAN;
ALTER TABLE plays ADD COLUMN IF NOT EXISTS penalty     BOOLEAN;
ALTER TABLE plays ADD COLUMN IF NOT EXISTS sack        BOOLEAN;
