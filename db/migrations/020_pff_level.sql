-- PFF assigns ONE player_id per human across college and the pros: Tai Felton is
-- 144886 at Maryland in 2024 and 144886 in the NFL now. That is a gift for identity
-- (it bridges a player's two career phases for free) and a hazard for storage, because
-- (player_id, season, week, facet) cannot tell "his NFL week 3" from "his college
-- week 3" — the same key, two different games.
--
-- level makes the distinction explicit. It is part of the primary key so both can
-- coexist for the same person rather than one silently overwriting the other.
ALTER TABLE pff_player_stats
    ADD COLUMN level TEXT NOT NULL DEFAULT 'nfl' CHECK (level IN ('nfl', 'ncaa'));

ALTER TABLE pff_player_stats DROP CONSTRAINT pff_player_stats_pkey;
ALTER TABLE pff_player_stats
    ADD PRIMARY KEY (player_id, season, facet, week, level);
