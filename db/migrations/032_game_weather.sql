-- Richer game conditions, now that CFBD's weather endpoint is reachable.
--
-- games already had temp and wind. CFBD returns more than those, and the extras
-- are the ones that actually move a total: precipitation and snowfall change how
-- a game is called, humidity and dew point affect the ball. Storing them as
-- columns rather than folding them into a "bad weather" flag keeps the judgement
-- with the model instead of baking it into ingest.
--
-- NULL continues to mean "not available", never "calm" or "clear".

ALTER TABLE games ADD COLUMN IF NOT EXISTS humidity          REAL;
ALTER TABLE games ADD COLUMN IF NOT EXISTS precipitation     REAL;
ALTER TABLE games ADD COLUMN IF NOT EXISTS snowfall          REAL;
ALTER TABLE games ADD COLUMN IF NOT EXISTS dew_point         REAL;
ALTER TABLE games ADD COLUMN IF NOT EXISTS pressure          REAL;
ALTER TABLE games ADD COLUMN IF NOT EXISTS wind_direction    REAL;
ALTER TABLE games ADD COLUMN IF NOT EXISTS weather_condition TEXT;

COMMENT ON COLUMN games.weather_condition IS
    'CFBD weather condition text (e.g. Fair, Light Rain). NULL means unavailable.';
