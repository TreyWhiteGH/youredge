-- Play-level player attribution for NCAAF.
--
-- Both CAPABILITIES.md and NCAAF.md record college play-level player identity as
-- structurally unobtainable, on the grounds that CFBD's /plays endpoint omits
-- player ids. That is true of /plays and false of the API: /plays/stats returns
-- playId + athleteId + statType across 26 stat types, and the athlete ids are
-- ESPN ids — the same identity space players.player_id already uses for college
-- ('ncaaf:4692048'). Resolution is a prefix, not a fuzzy match.
--
-- One row per player-event, so a single play yields several: the passer's
-- Completion, the receiver's Reception and Target, a defender's Tackle.

CREATE TABLE IF NOT EXISTS play_players (
    game_id        TEXT NOT NULL REFERENCES games(game_id),
    source_play_id TEXT NOT NULL,
    athlete_id     TEXT NOT NULL,          -- ESPN athlete id, as CFBD returns it
    player_id      TEXT REFERENCES players(player_id),
    athlete_name   TEXT,                   -- kept even when resolved, per the
                                           -- same rule the prop poller follows
    team_id        TEXT REFERENCES teams(team_id),
    stat_type      TEXT NOT NULL,          -- Reception, Target, Rush, Sack, ...
    stat           REAL,

    PRIMARY KEY (game_id, source_play_id, athlete_id, stat_type)
);

CREATE INDEX IF NOT EXISTS idx_play_players_player ON play_players (player_id)
    WHERE player_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_play_players_game ON play_players (game_id);
CREATE INDEX IF NOT EXISTS idx_play_players_stat ON play_players (stat_type);
