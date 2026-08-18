-- CFBD postseason games are all week=1; the notes field ('Boca Raton Bowl',
-- 'College Football Playoff Semifinal...') is the only round/bowl identifier.

ALTER TABLE games ADD COLUMN notes TEXT;
