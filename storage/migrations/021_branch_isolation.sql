-- 多世界线首版基础：branch 身份与不可变检查点。
-- worldline_id 仍然表示来源世界；branch_id 只表示故事创作连续性。

CREATE TABLE IF NOT EXISTS story_branches (
    branch_id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    parent_branch_id TEXT,
    fork_fragment_id TEXT,
    fork_checkpoint_id TEXT,
    head_checkpoint_id TEXT,
    revision INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    source_worldline_id TEXT NOT NULL DEFAULT 'main',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    archived_at TEXT,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE CASCADE,
    FOREIGN KEY (parent_branch_id) REFERENCES story_branches(branch_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_story_branches_story
    ON story_branches(story_id, status, updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS ux_story_branches_name
    ON story_branches(story_id, lower(name))
    WHERE status = 'active';

CREATE TABLE IF NOT EXISTS branch_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    branch_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    revision INTEGER NOT NULL,
    frontier_fragment_id TEXT,
    frontier_content_hash TEXT NOT NULL DEFAULT '',
    baseline_revision INTEGER NOT NULL DEFAULT 0,
    snapshot_manifest_json TEXT NOT NULL DEFAULT '{}',
    snapshot_hash TEXT NOT NULL DEFAULT '',
    extraction_status TEXT NOT NULL DEFAULT 'ready'
        CHECK (extraction_status IN ('pending', 'completed', 'skipped', 'ready')),
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (branch_id) REFERENCES story_branches(branch_id) ON DELETE RESTRICT,
    FOREIGN KEY (parent_checkpoint_id) REFERENCES branch_checkpoints(checkpoint_id) ON DELETE RESTRICT,
    UNIQUE (branch_id, revision)
);

CREATE INDEX IF NOT EXISTS idx_branch_checkpoints_branch
    ON branch_checkpoints(branch_id, revision DESC);

CREATE TABLE IF NOT EXISTS branch_checkpoint_items (
    checkpoint_id TEXT NOT NULL,
    item_kind TEXT NOT NULL,
    item_id TEXT NOT NULL,
    item_revision_id TEXT,
    origin_id TEXT,
    state TEXT NOT NULL DEFAULT 'inherited'
        CHECK (state IN ('inherited', 'local', 'overridden', 'tombstone')),
    ordinal INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (checkpoint_id, item_kind, item_id),
    FOREIGN KEY (checkpoint_id) REFERENCES branch_checkpoints(checkpoint_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_branch_checkpoint_items_lookup
    ON branch_checkpoint_items(checkpoint_id, item_kind, ordinal, item_id);

CREATE TABLE IF NOT EXISTS branch_fragment_states (
    branch_id TEXT NOT NULL,
    fragment_id TEXT NOT NULL,
    checkpoint_id TEXT,
    state TEXT NOT NULL DEFAULT 'inherited'
        CHECK (state IN ('inherited', 'local', 'accepted', 'finalized', 'discarded', 'tombstone')),
    ordinal INTEGER NOT NULL DEFAULT 0,
    source_branch_id TEXT,
    content_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (branch_id, fragment_id),
    FOREIGN KEY (branch_id) REFERENCES story_branches(branch_id) ON DELETE RESTRICT,
    FOREIGN KEY (checkpoint_id) REFERENCES branch_checkpoints(checkpoint_id) ON DELETE RESTRICT
);

-- 迁移现有故事和创作数据到各自默认主线。ID 可重复计算，便于离线迁移校验。
INSERT OR IGNORE INTO story_branches (
    branch_id, story_id, name, description, source_worldline_id, created_at, updated_at
)
SELECT
    -- 保留 story_id 原文，避免 a-b/ab 或大小写故事碰撞。
    'branch_main_' || story_id,
    story_id,
    '主线',
    '从历史数据迁移的默认主线',
    'main',
    COALESCE(created_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    COALESCE(updated_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
FROM stories
WHERE deleted_at IS NULL;

ALTER TABLE creative_sessions ADD COLUMN branch_id TEXT;
ALTER TABLE creative_turns ADD COLUMN branch_id TEXT;
ALTER TABLE creative_fragments ADD COLUMN branch_id TEXT;
ALTER TABLE creative_messages ADD COLUMN branch_id TEXT;
ALTER TABLE creative_action_runs ADD COLUMN branch_id TEXT;
ALTER TABLE creative_config_revisions ADD COLUMN branch_id TEXT;
ALTER TABLE creative_attachments ADD COLUMN branch_id TEXT;
ALTER TABLE knowledge_items ADD COLUMN branch_id TEXT;
ALTER TABLE pending_knowledge_items ADD COLUMN branch_id TEXT;
ALTER TABLE retrieval_documents ADD COLUMN branch_id TEXT;
ALTER TABLE retrieval_chunks ADD COLUMN branch_id TEXT;
ALTER TABLE retrieval_feedback ADD COLUMN branch_id TEXT;

UPDATE creative_sessions
SET branch_id = (
    SELECT branch_id FROM story_branches
    WHERE story_branches.story_id = creative_sessions.story_id
      AND story_branches.parent_branch_id IS NULL
      AND story_branches.name = '主线'
    ORDER BY created_at, branch_id LIMIT 1
)
WHERE branch_id IS NULL;
UPDATE creative_turns
SET branch_id = (SELECT branch_id FROM creative_sessions WHERE creative_sessions.session_id = creative_turns.session_id)
WHERE branch_id IS NULL;
UPDATE creative_fragments
SET branch_id = (SELECT branch_id FROM creative_sessions WHERE creative_sessions.session_id = creative_fragments.session_id)
WHERE branch_id IS NULL;
UPDATE creative_messages
SET branch_id = (SELECT branch_id FROM creative_sessions WHERE creative_sessions.session_id = creative_messages.session_id)
WHERE branch_id IS NULL;
UPDATE creative_action_runs
SET branch_id = (SELECT branch_id FROM creative_sessions WHERE creative_sessions.session_id = creative_action_runs.session_id)
WHERE branch_id IS NULL;
UPDATE creative_config_revisions
SET branch_id = (SELECT branch_id FROM creative_sessions WHERE creative_sessions.session_id = creative_config_revisions.session_id)
WHERE branch_id IS NULL;
UPDATE creative_attachments
SET branch_id = (SELECT branch_id FROM creative_sessions WHERE creative_sessions.session_id = creative_attachments.session_id)
WHERE branch_id IS NULL;

UPDATE knowledge_items
SET branch_id = (
    SELECT branch_id FROM story_branches
    WHERE story_branches.story_id = knowledge_items.story_id
      AND story_branches.parent_branch_id IS NULL AND story_branches.name = '主线'
    ORDER BY created_at, branch_id LIMIT 1
)
WHERE branch_id IS NULL AND story_id IS NOT NULL AND setting_scope = 'story';
UPDATE pending_knowledge_items
SET branch_id = (
    SELECT branch_id FROM story_branches
    WHERE story_branches.story_id = pending_knowledge_items.story_id
      AND story_branches.parent_branch_id IS NULL AND story_branches.name = '主线'
    ORDER BY created_at, branch_id LIMIT 1
)
WHERE branch_id IS NULL AND story_id IS NOT NULL;
UPDATE retrieval_documents
SET branch_id = (
    SELECT branch_id FROM story_branches
    WHERE story_branches.story_id = retrieval_documents.story_id
      AND story_branches.parent_branch_id IS NULL AND story_branches.name = '主线'
    ORDER BY created_at, branch_id LIMIT 1
)
WHERE branch_id IS NULL AND story_id IS NOT NULL;
UPDATE retrieval_chunks
SET branch_id = (SELECT branch_id FROM retrieval_documents WHERE retrieval_documents.document_id = retrieval_chunks.document_id)
WHERE branch_id IS NULL;
UPDATE retrieval_feedback
SET branch_id = (
    SELECT branch_id FROM story_branches
    WHERE story_branches.story_id = retrieval_feedback.story_id
      AND story_branches.parent_branch_id IS NULL AND story_branches.name = '主线'
    ORDER BY created_at, branch_id LIMIT 1
)
WHERE branch_id IS NULL AND story_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sessions_branch ON creative_sessions(story_id, branch_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_turns_branch ON creative_turns(branch_id, session_id, turn_index);
CREATE INDEX IF NOT EXISTS idx_fragments_branch ON creative_fragments(branch_id, session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_knowledge_branch ON knowledge_items(story_id, branch_id, setting_scope, deleted_at);
CREATE INDEX IF NOT EXISTS idx_pending_knowledge_branch ON pending_knowledge_items(story_id, branch_id, status);
CREATE INDEX IF NOT EXISTS idx_retrieval_documents_branch ON retrieval_documents(story_id, branch_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_retrieval_chunks_branch ON retrieval_chunks(branch_id, source_revision_id);
