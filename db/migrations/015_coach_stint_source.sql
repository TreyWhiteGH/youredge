-- FCS coaching history has no free API source: CFBD's /coaches is FBS-only (its
-- classification param is ignored), ESPN's coach endpoint returns the CURRENT coach for
-- every historical season (using it would misattribute Chesney's Holy Cross record to
-- his successor), and Wikidata's college-coaching coverage is sparse and undated.
--
-- So sub-FBS stints are seeded by hand. `source` keeps that visible forever: a model or
-- a narrator can weight manual rows differently, and nobody can mistake a hand-entered
-- date for an API fact.
ALTER TABLE coach_seasons
    ADD COLUMN source TEXT NOT NULL DEFAULT 'cfbd'
        CHECK (source IN ('cfbd', 'manual_fcs')),
    ADD COLUMN classification TEXT,          -- 'fbs' | 'fcs' at the time of the stint
    ADD COLUMN verified BOOLEAN NOT NULL DEFAULT TRUE;

UPDATE coach_seasons SET classification = 'fbs';

-- Existing rows are CFBD-sourced and therefore verified; seeded ones will not be.
COMMENT ON COLUMN coach_seasons.verified IS
    'FALSE for hand-seeded stints awaiting confirmation against a primary source';
