-- Keep the source's play description.
--
-- Needed because CFBD's play-level player attribution (/plays/stats) covers SEC
-- and ACC only, and playText is the sole remaining route to naming players on
-- the other ~71% of college games. It is also the audit trail for every flag
-- derived from playType: when a classification looks wrong, this is the sentence
-- that settles it.

ALTER TABLE plays ADD COLUMN IF NOT EXISTS play_text TEXT;
