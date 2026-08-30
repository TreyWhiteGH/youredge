-- Tags for the things a box score cannot say.
--
-- The existing vocabulary describes a finished game as a set of totals. What it
-- could not describe: a team held scoreless through eight straight possessions,
-- twenty unanswered points in a fourth quarter, a defence that took an offence
-- away entirely, or a winner that broke its own drought to retake the lead with
-- ninety seconds left. All four happened in the first week of the season and
-- none of them produced a tag.
INSERT INTO tags (slug, dimension, description, status, source) VALUES
    -- Game shape
    ('TRADED_HAYMAKERS', 'script',
     'Both teams put together a scoring run of 14+ unanswered', 'active', 'seed'),
    ('WIRE_TO_WIRE', 'script',
     'Whoever led first was never headed; the lead never changed hands', 'active', 'seed'),
    ('LATE_LEAD_CHANGE', 'script',
     'The lead changed hands for the last time inside the final five minutes', 'active', 'seed'),
    ('COMEBACK_BID_FAILED', 'script',
     'Losing side mounted a 14+ run in the fourth and still lost', 'active', 'seed'),
    ('SLOW_BURN', 'script',
     'Neither side scored in the first quarter', 'active', 'seed'),
    -- One team's story
    ('COLD_START', 'diagnostic',
     'Scoreless first quarter and three or more opening possessions without points', 'active', 'seed'),
    ('SCORING_RUN', 'diagnostic',
     'Scored 14+ consecutive points without being answered', 'active', 'seed'),
    ('LATE_SURGE', 'diagnostic',
     'Scored 14+ in the fourth quarter', 'active', 'seed'),
    ('SCORING_DROUGHT', 'diagnostic',
     'Five or more consecutive possessions without points', 'active', 'seed'),
    ('SMOTHERING_DEFENSE', 'diagnostic',
     'Held the opponent to negative EPA both through the air and on the ground, at bottom-quartile points', 'active', 'seed'),
    ('OFFENSE_SHUT_DOWN', 'diagnostic',
     'Negative EPA in both phases and bottom-quartile points; the opponent took the offence away', 'active', 'seed'),
    ('THREE_AND_OUT_PLAGUED', 'diagnostic',
     'Top-quartile count of three-and-out possessions', 'active', 'seed'),
    ('GO_AHEAD_ANSWER', 'diagnostic',
     'Retook the lead in the fourth quarter and held it to the whistle', 'active', 'seed')
ON CONFLICT (slug) DO UPDATE
    SET description = EXCLUDED.description, dimension = EXCLUDED.dimension;
