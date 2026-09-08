-- 项目资料的不可变 release 与故事级知识副本。
CREATE TABLE IF NOT EXISTS reference_libraries (
    library_id TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    source_kind TEXT NOT NULL DEFAULT 'reference',
    source_id TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    archived_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_reference_libraries_project
    ON reference_libraries(project_name, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS reference_library_releases (
    release_id TEXT PRIMARY KEY,
    library_id TEXT NOT NULL,
    release_no INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready'
        CHECK (status IN ('preparing', 'ready', 'archived', 'failed')),
    manifest_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    ready_at TEXT,
    FOREIGN KEY (library_id) REFERENCES reference_libraries(library_id) ON DELETE RESTRICT,
    UNIQUE (library_id, release_no),
    UNIQUE (library_id, content_hash)
);

CREATE TABLE IF NOT EXISTS reference_library_release_items (
    release_id TEXT NOT NULL,
    item_kind TEXT NOT NULL,
    origin_id TEXT NOT NULL,
    origin_revision_id TEXT,
    source_id TEXT,
    source_revision_id TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    ordinal INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (release_id, item_kind, origin_id),
    FOREIGN KEY (release_id) REFERENCES reference_library_releases(release_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS story_library_bindings (
    binding_id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL,
    branch_id TEXT,
    library_id TEXT NOT NULL,
    release_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready'
        CHECK (status IN ('preparing', 'ready', 'archived', 'failed')),
    idempotency_key TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    removed_at TEXT,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE RESTRICT,
    FOREIGN KEY (branch_id) REFERENCES story_branches(branch_id) ON DELETE RESTRICT,
    FOREIGN KEY (library_id) REFERENCES reference_libraries(library_id) ON DELETE RESTRICT,
    FOREIGN KEY (release_id) REFERENCES reference_library_releases(release_id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_story_library_binding
    ON story_library_bindings(story_id, COALESCE(branch_id, ''), library_id)
    WHERE status <> 'archived';

CREATE TABLE IF NOT EXISTS story_library_item_links (
    binding_id TEXT NOT NULL,
    origin_knowledge_id TEXT NOT NULL,
    origin_revision_id TEXT,
    origin_entity_id TEXT,
    local_knowledge_id TEXT,
    local_entity_id TEXT,
    baseline_hash TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'active'
        CHECK (state IN ('active', 'modified', 'deleted', 'tombstone')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (binding_id, origin_knowledge_id),
    FOREIGN KEY (binding_id) REFERENCES story_library_bindings(binding_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_story_library_bindings_story
    ON story_library_bindings(story_id, branch_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_story_library_links_local
    ON story_library_item_links(local_knowledge_id, state);

CREATE TABLE IF NOT EXISTS story_library_entity_links (
    binding_id TEXT NOT NULL,
    origin_entity_id TEXT NOT NULL,
    local_entity_id TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT '',
    canonical_name TEXT NOT NULL DEFAULT '',
    worldline_id TEXT,
    PRIMARY KEY (binding_id, origin_entity_id),
    FOREIGN KEY (binding_id) REFERENCES story_library_bindings(binding_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_story_library_entity_links_local
    ON story_library_entity_links(local_entity_id);

-- branch_id 已由 021 加入 knowledge_items；这里仅补充资料副本查询索引。
CREATE INDEX IF NOT EXISTS idx_knowledge_items_story_branch
    ON knowledge_items(story_id, branch_id, setting_scope, deleted_at);

-- Release 需要能够在原故事/原文被归档后回读证据锚点。正文快照只用于
-- 来源查证，不进入普通创作上下文。
CREATE TABLE IF NOT EXISTS reference_library_release_sources (
    release_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    revision_id TEXT NOT NULL DEFAULT '',
    source_json TEXT NOT NULL DEFAULT '{}',
    revision_json TEXT NOT NULL DEFAULT '{}',
    segments_json TEXT NOT NULL DEFAULT '[]',
    chunks_json TEXT NOT NULL DEFAULT '[]',
    snapshot_status TEXT NOT NULL DEFAULT 'partial'
        CHECK (snapshot_status IN ('complete', 'partial', 'unavailable')),
    content_hash_verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (release_id, source_id, revision_id),
    FOREIGN KEY (release_id) REFERENCES reference_library_releases(release_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS story_reference_states (
    story_id TEXT PRIMARY KEY,
    read_mode TEXT NOT NULL DEFAULT 'legacy'
        CHECK (read_mode IN ('legacy', 'strict')),
    migration_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (migration_status IN ('pending', 'confirmed', 'not_required')),
    confirmed_at TEXT,
    migrated_binding_id TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE RESTRICT,
    FOREIGN KEY (migrated_binding_id) REFERENCES story_library_bindings(binding_id) ON DELETE SET NULL
);

-- Existing stories retain the old read behavior until the user explicitly
-- confirms a complete public-library selection. New stories are initialized
-- by the story creation service as strict.
INSERT OR IGNORE INTO story_reference_states (story_id, read_mode, migration_status)
SELECT story_id, 'legacy', 'pending'
FROM stories
WHERE deleted_at IS NULL;
