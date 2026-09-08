-- 分支实体隔离：实体主档的唯一身份必须包含 branch_id。
ALTER TABLE entities ADD COLUMN branch_id TEXT;

UPDATE entities
SET branch_id = (
    SELECT 'branch_main_' || entities.story_id
    FROM stories
    WHERE stories.story_id = entities.story_id
      AND entities.setting_scope = 'story'
      AND stories.deleted_at IS NULL
)
WHERE branch_id IS NULL AND setting_scope = 'story' AND story_id IS NOT NULL;

DROP INDEX IF EXISTS idx_entities_identity;
CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_identity
    ON entities(entity_type, canonical_name, story_id, branch_id, worldline_id, setting_scope, version_scope);
