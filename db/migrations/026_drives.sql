-- Drives: one row per possession, derived from plays.
--
-- This is the substrate the drive-level simulator is fit from. A drive-level
-- Monte Carlo is, concretely, a kernel over "given a possession starting here in
-- this game state, how does it end and how long does it take" — which is exactly
-- one row of this table.
--
-- It is derived, not ingested: plays is the source of truth and this can always
-- be rebuilt. Materialised anyway because the sim, script labelling and the leg
-- ledger all read it, and re-deriving 500k plays per query is not sensible.

CREATE TABLE IF NOT EXISTS drives (
    game_id        TEXT NOT NULL REFERENCES games(game_id),
    drive_num      INT  NOT NULL,
    posteam_id     TEXT,
    defteam_id     TEXT,

    -- Starting state: what the sim conditions on.
    start_quarter  INT,
    start_seconds  INT,      -- game_seconds_remaining at first play
    start_yardline INT,      -- yards to opponent end zone (100 = own goal line)
    start_score_diff INT,    -- posteam perspective, pre-snap

    -- What happened.
    result         TEXT NOT NULL,   -- see the CHECK below
    points         INT NOT NULL DEFAULT 0,   -- points the possessing team scored
    plays          INT NOT NULL DEFAULT 0,
    pass_plays     INT NOT NULL DEFAULT 0,
    rush_plays     INT NOT NULL DEFAULT 0,
    yards          REAL,
    seconds        INT,      -- elapsed; NULL when the half boundary truncates it
    end_yardline   INT,

    PRIMARY KEY (game_id, drive_num),

    -- END_HALF is a clock event, not a possession outcome, and FUMBLE_LOST is a
    -- turnover with a live field position. Keeping them distinct is the whole
    -- reason 025 extracted fumble_lost.
    CONSTRAINT drives_result_known CHECK (result IN (
        'TD', 'FG_MADE', 'FG_MISS', 'PUNT', 'INT', 'FUMBLE_LOST',
        'DOWNS', 'SAFETY', 'END_HALF', 'UNKNOWN'
    ))
);

CREATE INDEX IF NOT EXISTS idx_drives_posteam ON drives (posteam_id, result);
CREATE INDEX IF NOT EXISTS idx_drives_start ON drives (start_yardline, result);
CREATE INDEX IF NOT EXISTS idx_drives_game ON drives (game_id);
