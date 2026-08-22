-- A coach can hold two schools in one season (mid-season change, interim role), so
-- (coach_id, season) is not unique. The portable-signal row is per school-stint.
ALTER TABLE coach_features DROP CONSTRAINT coach_features_pkey;
ALTER TABLE coach_features ALTER COLUMN team_id SET NOT NULL;
ALTER TABLE coach_features ADD PRIMARY KEY (coach_id, season, team_id);
