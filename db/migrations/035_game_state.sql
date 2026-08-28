-- Realized game state, one row per finished game.
--
-- Layer B is built on what actually happened, not on what a model thinks would
-- happen. Script labels and the leg ledger both need the same handful of derived
-- quantities — how big the lead got, where the margin sat at each break, how the
-- play mix shifted once the game was decided — so they are computed once here
-- rather than twice in two different queries that would drift apart.
--
-- Derived from plays; rebuildable at any time.
--
-- Deliberately no win probability. nflverse supplies `wp` and CFBD does not, and
-- a script vocabulary that means one thing in the NFL and something else in
-- college is worse than no vocabulary. Score and clock exist for both.

CREATE TABLE IF NOT EXISTS game_state (
    game_id            TEXT PRIMARY KEY REFERENCES games(game_id),

    -- Scoring. Margins are from the home team's perspective throughout.
    home_points        INT,
    away_points        INT,
    total_points       INT,
    home_margin        INT,

    -- The shape of the game: where the margin sat at each break, and the
    -- furthest either side ever got ahead.
    margin_end_q1      INT,
    margin_end_h1      INT,
    margin_end_q3      INT,
    max_home_lead      INT,
    max_away_lead      INT,
    lead_changes       INT,

    -- Pace and mix.
    plays_total        INT,
    home_pass_rate     REAL,
    away_pass_rate     REAL,

    -- What the teams did once the game was lopsided. The mechanism behind
    -- garbage-time passing and clock-killing, expressed without win probability.
    q4_trail_pass_rate REAL,
    q4_trail_plays     INT,
    q4_lead_run_rate   REAL,
    q4_lead_plays      INT,

    -- Late scoring, which is what a backdoor cover is made of.
    late_trail_points  INT,   -- scored by the trailing side inside the last 4:00

    built_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_game_state_margin ON game_state (home_margin);
CREATE INDEX IF NOT EXISTS idx_game_state_total ON game_state (total_points);
