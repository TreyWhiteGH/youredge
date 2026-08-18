-- Alignment layer: NGS tracking-derived primary alignment label (SLOT_WR,
-- SLOT_CB, HIGH_SAFETY, ...) on players, and NGS receiving traits whose
-- cushion/separation numbers are alignment-diagnostic. True per-snap alignment
-- percentages are PFF-licensed; this is the best free signal.

ALTER TABLE players ADD COLUMN ngs_position TEXT;

CREATE TABLE ngs_receiving_weekly (
    player_id    TEXT NOT NULL REFERENCES players(player_id),
    season       INT NOT NULL,
    week         INT NOT NULL,                 -- week 0 = NGS season aggregate
    avg_cushion  REAL,
    avg_separation REAL,
    avg_intended_air_yards REAL,
    percent_share_of_intended_air_yards REAL,
    catch_percentage REAL,
    avg_yac REAL,
    avg_expected_yac REAL,
    avg_yac_above_expectation REAL,
    stats        JSONB NOT NULL,
    PRIMARY KEY (player_id, season, week)
);
