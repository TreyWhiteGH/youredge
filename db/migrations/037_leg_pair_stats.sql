-- The empirical joint: how often two legs won together.
--
-- This is what Layer B exists to produce, and it is counting, not modelling.
-- For every pair of leg templates it records how often each won, how often both
-- won, and whether that is more or less than independence would give. No
-- simulator is involved, so it carries no simulator's error — which is exactly
-- why it can later serve as the witness that checks one.
--
-- `n` travels with every row and is not optional. A correlation over 40 games is
-- a rumour.
--
-- script_tag = '' is the unconditional surface; a slug restricts to games that
-- landed in that script, which is how "these legs only agree in a shootout"
-- becomes answerable.

CREATE TABLE IF NOT EXISTS leg_pair_stats (
    league     TEXT NOT NULL,
    script_tag TEXT NOT NULL DEFAULT '',
    template_a TEXT NOT NULL,
    side_a     TEXT NOT NULL,
    template_b TEXT NOT NULL,
    side_b     TEXT NOT NULL,

    n          INT  NOT NULL,          -- games where both legs were evaluable
    p_a        REAL NOT NULL,
    p_b        REAL NOT NULL,
    p_ab       REAL NOT NULL,
    phi        REAL,                   -- NULL when a leg never varies
    lift       REAL,                   -- p_ab / (p_a * p_b); 1.0 is independence

    built_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (league, script_tag, template_a, side_a, template_b, side_b)
);

CREATE INDEX IF NOT EXISTS idx_pair_phi ON leg_pair_stats (league, script_tag, phi);
CREATE INDEX IF NOT EXISTS idx_pair_a ON leg_pair_stats (league, template_a, side_a);
