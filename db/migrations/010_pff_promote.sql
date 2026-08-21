-- Promote the PFF metrics our own surfaces filter and rank on. Everything else
-- stays in stats JSONB; the GIN index makes those arbitrary lookups fast, so
-- new questions never require a migration.

ALTER TABLE pff_player_stats
    ADD COLUMN routes INT,          -- receiving volume denominator (yprr's base)
    ADD COLUMN yprr REAL,           -- yards per route run: the WR efficiency stat
    ADD COLUMN inline_rate REAL;    -- TE/WR alignment, completes slot/wide

CREATE INDEX idx_pff_stats_gin ON pff_player_stats USING gin (stats jsonb_path_ops);

-- Alignment lookups drive backup selection and matchup queries.
CREATE INDEX idx_pff_slot ON pff_player_stats (facet, season, slot_rate)
    WHERE slot_rate IS NOT NULL;
