CREATE TABLE IF NOT EXISTS creative_sessions (
    session_id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'archived')),
    session_goal TEXT NOT NULL DEFAULT '',
    writing_guidance_json TEXT NOT NULL DEFAULT '{}',
    target_chapter_no INTEGER,
    rolling_summary TEXT NOT NULL DEFAULT '',
    summary_fragment_id TEXT,
    active_fragment_id TEXT,
    worldline_id TEXT NOT NULL DEFAULT 'main',
    auto_extract_mode TEXT NOT NULL DEFAULT 'manual'
        CHECK (auto_extract_mode IN ('manual', 'on_accept')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS creative_turns (
    turn_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    user_message TEXT NOT NULL,
    action_type TEXT NOT NULL DEFAULT 'generate'
        CHECK (action_type IN ('generate', 'continue', 'rewrite', 'branch', 'revise')),
    parent_fragment_id TEXT,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed')),
    error_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (session_id) REFERENCES creative_sessions(session_id) ON DELETE CASCADE,
    UNIQUE (session_id, turn_index)
);

CREATE TABLE IF NOT EXISTS creative_fragments (
    fragment_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL UNIQUE,
    parent_fragment_id TEXT,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('proposed', 'accepted', 'superseded', 'discarded', 'finalized')),
    content_hash TEXT NOT NULL,
    word_count INTEGER NOT NULL DEFAULT 0,
    context_snapshot_id TEXT,
    extraction_status TEXT NOT NULL DEFAULT 'not_started'
        CHECK (extraction_status IN ('not_started', 'running', 'completed', 'failed')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    accepted_at TEXT,
    FOREIGN KEY (session_id) REFERENCES creative_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (turn_id) REFERENCES creative_turns(turn_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_creative_sessions_story_status
ON creative_sessions(story_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_creative_turns_session_order
ON creative_turns(session_id, turn_index);

CREATE INDEX IF NOT EXISTS idx_creative_fragments_session_created
ON creative_fragments(session_id, created_at, fragment_id);

CREATE INDEX IF NOT EXISTS idx_creative_fragments_parent
ON creative_fragments(parent_fragment_id);
