-- Visual identity: the colours a team is known by, and where its mark lives.
--
-- Only the logo URL is stored, never the image. A reference costs nothing and infringes
-- nothing; the artwork stays on its origin and the client decides whether to render it.
-- That decision is deliberately not baked into the data.
--
-- Colours carry most of the recognition anyway and carry none of the trademark question,
-- which is why they are first-class here rather than an afterthought beside the logo.
ALTER TABLE teams
    ADD COLUMN color     TEXT,   -- primary, hex without '#'
    ADD COLUMN alt_color TEXT,
    ADD COLUMN logo_url  TEXT;
