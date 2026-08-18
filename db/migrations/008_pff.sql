-- PFF Premium Stats exports (manual CSV drops in data/pff/ — no consumer API).
-- Sparse typed columns for the alignment/coverage numbers we consume directly;
-- every export column lands in stats JSONB, so unknown-in-advance CSV shapes
-- are preserved and columns get promoted once real files arrive.

CREATE TABLE pff_player_stats (
    player_id    TEXT NOT NULL REFERENCES players(player_id),
    season       INT NOT NULL,
    week         INT NOT NULL DEFAULT 0,         -- 0 = season-level export (NGS convention)
    facet        TEXT NOT NULL,                  -- 'receiving' | 'coverage' | ...
    team_id      TEXT,
    snaps        INT,
    slot_rate    REAL,                           -- % of pass snaps aligned slot
    wide_rate    REAL,
    grade        REAL,                           -- facet's PFF grade 0-100
    stats        JSONB NOT NULL,
    PRIMARY KEY (player_id, season, facet, week)
);
CREATE INDEX idx_pff_facet ON pff_player_stats (facet, season);
