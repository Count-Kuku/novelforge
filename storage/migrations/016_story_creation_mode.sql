ALTER TABLE stories
ADD COLUMN creation_mode TEXT NOT NULL DEFAULT 'planned'
CHECK (creation_mode IN ('planned', 'conversational'));
