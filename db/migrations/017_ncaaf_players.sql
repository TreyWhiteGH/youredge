-- College player identity. CFBD is canonical for NCAAF exactly as nflverse is for the
-- NFL: player_id = 'ncaaf:<espn_athlete_id>', which is the same id space /roster,
-- /stats/player/season and /games/players all key on.
--
-- jersey + class_year are stored because they are the disambiguators that make later
-- matching reliable: college rosters are full of shared surnames, and a future PFF
-- college crosswalk has to validate a name match against jersey + position rather than
-- trusting the name alone.

ALTER TABLE players
    ADD COLUMN jersey TEXT,
    ADD COLUMN class_year TEXT;      -- 'FR' | 'SO' | 'JR' | 'SR' as CFBD reports it

CREATE INDEX IF NOT EXISTS idx_players_league_team ON players (league, team_id);
