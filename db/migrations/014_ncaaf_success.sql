-- nflverse defines success as EPA > 0; CFBD ships no success column but does ship PPA
-- (its EPA analog, stored in plays.epa). Applying the same definition makes success
-- rate mean the same thing in both leagues instead of silently missing for NCAAF.
UPDATE plays p SET success = (p.epa > 0)
FROM games g
WHERE g.game_id = p.game_id AND g.league = 'ncaaf'
  AND p.success IS NULL AND p.epa IS NOT NULL;
