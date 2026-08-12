CREATE TABLE IF NOT EXISTS creative_attachments (
    attachment_id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_revision_id TEXT,
    relative_path TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL DEFAULT '',
    media_type TEXT NOT NULL DEFAULT '',
    attachment_kind TEXT NOT NULL DEFAULT 'file'
        CHECK (attachment_kind IN ('file', 'pasted_text', 'url', 'existing_source')),
    scope TEXT NOT NULL DEFAULT 'session'
        CHECK (scope IN ('turn', 'session', 'story', 'project')),
    story_id TEXT,
    session_id TEXT,
    turn_id TEXT,
    remaining_uses INTEGER CHECK (remaining_uses IS NULL OR remaining_uses >= 0),
    status TEXT NOT NULL DEFAULT 'indexed'
        CHECK (status IN ('parsed', 'indexed', 'processing', 'ready', 'failed')),
    ingestion_task_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (source_id) REFERENCES source_documents(source_id) ON DELETE RESTRICT,
    FOREIGN KEY (source_revision_id) REFERENCES source_revisions(revision_id) ON DELETE SET NULL,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES creative_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (turn_id) REFERENCES creative_turns(turn_id) ON DELETE CASCADE,
    FOREIGN KEY (ingestion_task_id) REFERENCES workflow_runs(run_id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_creative_attachments_scope_content
ON creative_attachments (
    content_hash,
    scope,
    COALESCE(story_id, ''),
    COALESCE(session_id, ''),
    COALESCE(turn_id, '')
);

CREATE INDEX IF NOT EXISTS idx_creative_attachments_session
ON creative_attachments (session_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_creative_attachments_story
ON creative_attachments (story_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_creative_attachments_source
ON creative_attachments (source_id, source_revision_id);
