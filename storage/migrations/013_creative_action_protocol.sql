CREATE TABLE IF NOT EXISTS creative_messages (
    message_id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    message_kind TEXT NOT NULL DEFAULT 'plain'
        CHECK (message_kind IN ('plain', 'clarification', 'action_receipt', 'error')),
    content TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES creative_sessions(session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS creative_action_runs (
    action_id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    request_message_id TEXT,
    action_type TEXT NOT NULL CHECK (action_type IN (
        'write', 'revise', 'import_sources', 'extract_knowledge',
        'query_knowledge', 'update_knowledge', 'update_config',
        'save_chapter', 'clarify'
    )),
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN (
        'planned', 'awaiting_confirmation', 'running', 'completed',
        'failed', 'undone', 'cancelled'
    )),
    scope TEXT NOT NULL DEFAULT 'session'
        CHECK (scope IN ('turn', 'session', 'story', 'project')),
    target_json TEXT NOT NULL DEFAULT '{}',
    patch_json TEXT NOT NULL DEFAULT '{}',
    plan_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    undo_json TEXT NOT NULL DEFAULT '{}',
    requires_confirmation INTEGER NOT NULL DEFAULT 0 CHECK (requires_confirmation IN (0, 1)),
    confirmed_at TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    error_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    finished_at TEXT,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES creative_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (request_message_id) REFERENCES creative_messages(message_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS creative_config_revisions (
    revision_id TEXT PRIMARY KEY,
    action_id TEXT NOT NULL,
    story_id TEXT NOT NULL,
    session_id TEXT,
    config_scope TEXT NOT NULL CHECK (config_scope IN ('session', 'story')),
    before_json TEXT NOT NULL DEFAULT '{}',
    after_json TEXT NOT NULL DEFAULT '{}',
    patch_json TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL DEFAULT '',
    reversed_by_action_id TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (action_id) REFERENCES creative_action_runs(action_id) ON DELETE CASCADE,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES creative_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (reversed_by_action_id) REFERENCES creative_action_runs(action_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_creative_messages_session
ON creative_messages (session_id, created_at, message_id);

CREATE INDEX IF NOT EXISTS idx_creative_action_runs_session
ON creative_action_runs (session_id, updated_at DESC, action_id);

CREATE INDEX IF NOT EXISTS idx_creative_config_revisions_action
ON creative_config_revisions (action_id, created_at DESC);
