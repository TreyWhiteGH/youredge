-- Market identity keys on the feed's player *name*, not on our resolved id.
--
-- 022 put player_id in the unique key. That is backwards: player_id is something
-- we derive, and the crosswalk gets better over time. Keying on it means the day
-- "Deebo Samuel" starts resolving, his prop history forks — the old NULL-id row
-- and a new resolved row, same book, same market, same player, neither holding
-- the full line movement.
--
-- player_name is what the book actually said, and it is stable. Keying on it lets
-- player_id be corrected in place by a re-resolution pass without disturbing the
-- snapshots already hanging off the market.

-- Fold any rows that already forked, keeping the resolved one.
WITH ranked AS (
    SELECT market_id,
           first_value(market_id) OVER (
               PARTITION BY game_id, bookmaker, market_key, player_name
               ORDER BY (player_id IS NULL), market_id
           ) AS keep_id
    FROM markets
)
UPDATE odds_snapshots s
   SET market_id = r.keep_id
  FROM ranked r
 WHERE s.market_id = r.market_id AND r.market_id <> r.keep_id;

DELETE FROM markets m
 WHERE EXISTS (
     SELECT 1 FROM markets k
      WHERE k.game_id = m.game_id AND k.bookmaker = m.bookmaker
        AND k.market_key = m.market_key
        AND k.player_name IS NOT DISTINCT FROM m.player_name
        AND (k.player_id IS NOT NULL AND m.player_id IS NULL
             OR (k.player_id IS NULL) = (m.player_id IS NULL) AND k.market_id < m.market_id)
 );

DROP INDEX IF EXISTS markets_identity_key;

CREATE UNIQUE INDEX IF NOT EXISTS markets_identity_key
    ON markets (game_id, bookmaker, market_key, player_name) NULLS NOT DISTINCT;
