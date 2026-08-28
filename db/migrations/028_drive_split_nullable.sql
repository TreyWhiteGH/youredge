-- plays / pass_plays / rush_plays may legitimately be unknown.
--
-- 026 declared them NOT NULL DEFAULT 0, which was fine while drives came only
-- from NFL play-by-play where every split is derivable. CFBD's /drives endpoint
-- gives a possession's outcome and total plays but not its pass/run mix, and
-- writing 0 there would state that a college offence threw no passes on the
-- drive — the null-is-not-zero rule the rest of this codebase already follows.

ALTER TABLE drives ALTER COLUMN plays      DROP NOT NULL;
ALTER TABLE drives ALTER COLUMN pass_plays DROP NOT NULL;
ALTER TABLE drives ALTER COLUMN rush_plays DROP NOT NULL;
ALTER TABLE drives ALTER COLUMN plays      DROP DEFAULT;
ALTER TABLE drives ALTER COLUMN pass_plays DROP DEFAULT;
ALTER TABLE drives ALTER COLUMN rush_plays DROP DEFAULT;
