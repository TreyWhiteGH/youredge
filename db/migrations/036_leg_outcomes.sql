-- What every leg template would have done, in every finished game.
--
-- The ledger Layer B counts over. A "leg" here is a bet you could have placed --
-- home covers, over the total, the lead back goes over his rushing line -- and
-- this records whether it won, what number it was judged against, and where that
-- number came from.
--
-- line_source is load-bearing. Spreads and totals are judged against the real
-- closing line, so those rows are what actually happened at a price the market
-- set. We hold no historical team-total, half or prop lines, so those are judged
-- against a synthetic number derived from the closing line or the player's own
-- history. A synthetic line supports a correlation -- does this leg win when that
-- one does -- but it is NOT a fair price, and nothing downstream may quote edge
-- from a leg whose line we invented.

CREATE TABLE IF NOT EXISTS leg_outcomes (
    game_id     TEXT NOT NULL REFERENCES games(game_id),
    template    TEXT NOT NULL,          -- HOME_COVER, RB1_RUSH_YDS_OVER, ...
    side        TEXT NOT NULL DEFAULT '',   -- home / away / '' where not sided
    line        REAL,                   -- the number the leg was judged against
    line_source TEXT NOT NULL CHECK (line_source IN ('closing', 'synthetic')),
    realized    REAL,                   -- what actually happened
    hit         BOOLEAN,                -- NULL for a push
    player_id   TEXT REFERENCES players(player_id),

    PRIMARY KEY (game_id, template, side)
);

CREATE INDEX IF NOT EXISTS idx_leg_outcomes_template ON leg_outcomes (template, side);
CREATE INDEX IF NOT EXISTS idx_leg_outcomes_game ON leg_outcomes (game_id);
CREATE INDEX IF NOT EXISTS idx_leg_outcomes_hit ON leg_outcomes (template, side, hit);
