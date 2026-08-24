-- The same human has two canonical ids in this system: ncaaf:<espn_athlete_id> for his
-- college career and nfl:<gsis_id> for his pro one. That split is correct — they are
-- different id spaces with different source data — but it means nothing joins a rookie
-- to the college production he was drafted on.
--
-- ESPN athlete ids persist from college to the pros, and we already store them for NFL
-- players, so the bridge is exact and free: no fuzzy matching, no thresholds.
--
-- It is worth noting WHY id-linking beats name-linking here. Of 1,663 links, 72 pairs
-- disagree on name — Cam/Cameron Camper, Nate/Nathan Carter, suffixes, M.J./MJ. Those
-- are the same people, and they are exactly the cases a name matcher would drop.
CREATE TABLE player_career_links (
    ncaaf_player_id TEXT NOT NULL REFERENCES players(player_id),
    nfl_player_id   TEXT NOT NULL REFERENCES players(player_id),
    method          TEXT NOT NULL,     -- 'espn_id'
    name_agrees     BOOLEAN,           -- FALSE is usually formatting, not a wrong link
    PRIMARY KEY (ncaaf_player_id, nfl_player_id)
);
CREATE INDEX idx_career_nfl ON player_career_links (nfl_player_id);

INSERT INTO player_career_links (ncaaf_player_id, nfl_player_id, method, name_agrees)
SELECT col_p.player_id, nfl_p.player_id, 'espn_id', nfl_p.name = col_p.name
FROM entity_xwalk x
JOIN players nfl_p ON nfl_p.player_id = x.canonical_id AND nfl_p.league = 'nfl'
JOIN players col_p ON col_p.player_id = 'ncaaf:' || x.source_id
WHERE x.entity_type = 'player' AND x.source = 'espn'
ON CONFLICT DO NOTHING;
