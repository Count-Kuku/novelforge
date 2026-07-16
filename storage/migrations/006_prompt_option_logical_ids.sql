ALTER TABLE prompt_options ADD COLUMN logical_id TEXT;

UPDATE prompt_options
SET logical_id = option_id
WHERE logical_id IS NULL OR logical_id = '';

CREATE INDEX IF NOT EXISTS idx_prompt_options_logical_scope
ON prompt_options(scope, story_id, logical_id, deleted_at);
