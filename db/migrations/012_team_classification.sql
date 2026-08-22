-- FBS vs FCS. The context layer is FBS-only: coaching/returning-production signal is
-- modelled against FBS competition, and FCS programs enter our data only as crossover
-- opponents. Keeping the column (rather than deleting FCS teams) preserves the games
-- already ingested against them.
ALTER TABLE teams ADD COLUMN classification TEXT;
CREATE INDEX idx_teams_classification ON teams (league, classification);
