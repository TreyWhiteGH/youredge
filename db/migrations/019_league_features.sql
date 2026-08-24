-- League-specific model features.
--
-- The typed columns on game_features are the shared base: play-derived form, rest,
-- the closing line, the realised residual. Both leagues have them and both models
-- use them.
--
-- What each league adds on top is completely different. NFL's edge is PFF pressure,
-- protection and usage; NCAAF's is coaching residual, returning production, portal
-- churn, talent and elevation. Neither belongs in the other's row. Rather than 40
-- columns half-NULL for whichever league you're looking at, extensions live in JSONB
-- - the same typed-plus-JSONB split pff_player_stats and player_game_stats already
-- use. Adding a college feature never requires a migration or a NULL NFL column.
ALTER TABLE game_features ADD COLUMN features JSONB;

CREATE INDEX idx_gf_features ON game_features USING gin (features jsonb_path_ops);
