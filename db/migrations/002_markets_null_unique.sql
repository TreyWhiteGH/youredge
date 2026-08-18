-- Fix: UNIQUE treats NULL player_id as distinct, so game-level markets
-- (player_id IS NULL) duplicate on every odds poll and ON CONFLICT never fires.
-- PG16 supports NULLS NOT DISTINCT.
--
-- Apply to an existing DB with:  make migrate
-- (Runs automatically only on a fresh volume via docker-entrypoint-initdb.d.)

BEGIN;

-- 1) Remap snapshots from duplicate markets to the surviving (lowest) market_id
WITH canon AS (
    SELECT market_id,
           MIN(market_id) OVER (
               PARTITION BY game_id, bookmaker, market_key,
                            COALESCE(player_id, '')
           ) AS keep_id
    FROM markets
)
UPDATE odds_snapshots s
SET market_id = c.keep_id
FROM canon c
WHERE s.market_id = c.market_id
  AND c.market_id <> c.keep_id;

-- 2) Delete the orphaned duplicates
WITH canon AS (
    SELECT market_id,
           MIN(market_id) OVER (
               PARTITION BY game_id, bookmaker, market_key,
                            COALESCE(player_id, '')
           ) AS keep_id
    FROM markets
)
DELETE FROM markets m
USING canon c
WHERE m.market_id = c.market_id
  AND c.market_id <> c.keep_id;

-- 3) Swap the constraint
ALTER TABLE markets
    DROP CONSTRAINT markets_game_id_bookmaker_market_key_player_id_key;
ALTER TABLE markets
    ADD CONSTRAINT markets_game_id_bookmaker_market_key_player_id_key
    UNIQUE NULLS NOT DISTINCT (game_id, bookmaker, market_key, player_id);

COMMIT;
