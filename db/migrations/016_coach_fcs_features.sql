-- FCS success kept as its own feature rather than folded into career_sp_residual.
-- FCS has no SP+, and an FCS SRS of -13.5 does not mean what an FBS SP+ of -13.5 means,
-- so blending them would invent a comparison. Exposing them separately lets the Phase 3
-- model learn what sub-FBS success is actually worth instead of us asserting it.
ALTER TABLE coach_features
    ADD COLUMN fcs_seasons INT NOT NULL DEFAULT 0,
    ADD COLUMN fcs_wins INT, ADD COLUMN fcs_losses INT,
    ADD COLUMN fcs_win_pct REAL;
