-- Keep the source's own words for the drive outcome.
--
-- `result` is our taxonomy, and mapping into it is a judgement call: CFBD emits
-- strings like 'INT TD' and 'DOWNS TD' whose reading determines whether points
-- go to the offence or the defence. Storing the raw value makes those decisions
-- auditable after the fact and lets the mapping be revised without re-fetching a
-- season — and it means an unrecognised result is inspectable rather than
-- vanishing into UNKNOWN.
--
-- NULL for NFL drives, which are derived from play flags rather than a label.

ALTER TABLE drives ADD COLUMN IF NOT EXISTS result_raw TEXT;
