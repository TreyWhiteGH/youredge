-- Distinguish attribution we were told from attribution we inferred.
--
-- play_players holds two kinds of row now. CFBD's /plays/stats gives real athlete
-- ids, but only for SEC and ACC. Everywhere else the player is recovered by
-- parsing the play description, which is measurably good — 99.3% precision on
-- rushers, 99.4% on receivers, 97.6% on passers, scored against 60,000 plays
-- where both exist — but it is inference, and a model that cannot tell the two
-- apart cannot decide how much to trust a thin split.
--
-- Feed rows are never overwritten by parsed ones.

ALTER TABLE play_players ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'cfbd_stats'
    CHECK (source IN ('cfbd_stats', 'playtext'));

COMMENT ON COLUMN play_players.source IS
    'cfbd_stats = play-level feed with real athlete ids (SEC/ACC only). '
    'playtext = parsed from the play description and resolved to a roster.';

CREATE INDEX IF NOT EXISTS idx_play_players_source ON play_players (source);
