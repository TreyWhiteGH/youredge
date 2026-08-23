-- Venue and game conditions, both leagues.
--
-- Split deliberately: venues holds what never changes (location, elevation, capacity),
-- games holds what varies per game. Roof is game-level because retractable stadiums
-- open and close, and nflverse reports it that way; surface is game-level too because
-- fields get replaced mid-season and neutral-site games aren't played on the home
-- team's turf at all.
--
-- CFBD gives NCAAF venue statics but no per-game weather on the free tier. nflverse
-- gives NFL temp/wind per game. So NFL rows will have conditions and NCAAF rows will
-- not - NULL means "not available", never "indoors" or "calm".

CREATE TABLE venues (
    venue_id     TEXT PRIMARY KEY,          -- 'ncaaf:<cfbd id>' | 'nfl:<nflverse stadium_id>'
    league       TEXT NOT NULL CHECK (league IN ('nfl', 'ncaaf')),
    name         TEXT NOT NULL,
    city         TEXT,
    state        TEXT,
    timezone     TEXT,
    latitude     REAL,
    longitude    REAL,
    elevation    REAL,                      -- metres; altitude matters for totals
    capacity     INT,
    dome         BOOLEAN,
    grass        BOOLEAN
);

ALTER TABLE games
    ADD COLUMN venue_id TEXT REFERENCES venues(venue_id),
    ADD COLUMN roof     TEXT,               -- 'outdoors'|'dome'|'closed'|'open'
    ADD COLUMN surface  TEXT,
    ADD COLUMN temp     REAL,               -- F, NFL only
    ADD COLUMN wind     REAL,               -- mph, NFL only
    ADD COLUMN neutral_site BOOLEAN;

CREATE INDEX idx_games_venue ON games (venue_id);
