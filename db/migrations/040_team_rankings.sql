-- Weekly poll rankings. SP+ rank already lived in team_season_context, but that is a
-- rating system's ordering, not a poll — "ranked" and "Top 25" mean the AP and Coaches
-- polls in college football, and conflating the two would put teams in a Top 25 that no
-- voter has ever placed there.
--
-- Keyed per week because polls move: a team ranked 3rd in the preseason and 19th in
-- November is one row per week, not an overwrite. The current poll is the newest week,
-- which is a query, not a column to keep in sync.
CREATE TABLE team_rankings (
    season       INTEGER NOT NULL,
    season_type  TEXT    NOT NULL,          -- regular | postseason
    week         INTEGER NOT NULL,          -- 0 = preseason
    poll         TEXT    NOT NULL,          -- 'AP Top 25', 'Coaches Poll', 'Playoff Committee Rankings'
    team_id      TEXT    NOT NULL REFERENCES teams(team_id),
    rank         INTEGER NOT NULL,
    points       INTEGER,
    first_place_votes INTEGER,
    PRIMARY KEY (season, season_type, week, poll, team_id)
);

CREATE INDEX idx_rankings_lookup ON team_rankings (team_id, season, poll, week DESC);
CREATE INDEX idx_rankings_week ON team_rankings (season, poll, week DESC, rank);
