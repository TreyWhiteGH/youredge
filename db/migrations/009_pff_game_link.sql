-- Weekly PFF rows link to the canonical game (season, week, team), which is
-- what lets PFF context join play-by-play: "his 34.2 pass-block grade game"
-- becomes queryable next to the sacks in plays for that same game_id.

ALTER TABLE pff_player_stats ADD COLUMN game_id TEXT REFERENCES games(game_id);
CREATE INDEX idx_pff_game ON pff_player_stats (game_id);
