-- Defender availability (snap counts) + current depth charts: the inputs for
-- defense on/off splits and "who plugs in when X is out".

CREATE TABLE snap_counts (
    player_id    TEXT NOT NULL REFERENCES players(player_id),
    game_id      TEXT NOT NULL REFERENCES games(game_id),
    team_id      TEXT,                        -- the team the snaps were for (players move)
    position     TEXT,
    offense_snaps INT, offense_pct REAL,
    defense_snaps INT, defense_pct REAL,
    st_snaps      INT, st_pct      REAL,
    PRIMARY KEY (player_id, game_id)
);
CREATE INDEX idx_snaps_game ON snap_counts (game_id);

-- Latest snapshot per team; refreshed whole-table per ingest (as_of tracks it).
CREATE TABLE depth_chart (
    team_id   TEXT NOT NULL REFERENCES teams(team_id),
    pos_grp   TEXT NOT NULL,                  -- 'Base 3-4 D', 'Offense', ...
    pos_name  TEXT NOT NULL,                  -- 'Left Cornerback'
    pos_abb   TEXT NOT NULL,                  -- 'LCB'
    pos_slot  INT NOT NULL,
    pos_rank  INT NOT NULL,                   -- 1 = starter, 2 = primary backup
    player_id TEXT NOT NULL REFERENCES players(player_id),
    as_of     TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (team_id, pos_grp, pos_slot, pos_rank)
);
