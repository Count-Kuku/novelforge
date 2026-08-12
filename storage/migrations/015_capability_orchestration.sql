CREATE TABLE IF NOT EXISTS credential_references (
    credential_ref TEXT PRIMARY KEY,
    purpose TEXT NOT NULL,
    owner_id TEXT NOT NULL DEFAULT '',
    backend TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    last_four TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_credential_references_owner
ON credential_references(owner_id, purpose, deleted_at);

CREATE TABLE IF NOT EXISTS automatic_configuration_state (
    config_key TEXT PRIMARY KEY,
    project_name TEXT NOT NULL DEFAULT '',
    story_id TEXT NOT NULL DEFAULT '',
    operation TEXT NOT NULL,
    settings_json TEXT NOT NULL DEFAULT '{}',
    locked_fields_json TEXT NOT NULL DEFAULT '[]',
    source_revision_id TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_automatic_configuration_scope
ON automatic_configuration_state(project_name, story_id, operation);

CREATE TABLE IF NOT EXISTS automatic_configuration_revisions (
    revision_id TEXT PRIMARY KEY,
    config_key TEXT NOT NULL,
    project_name TEXT NOT NULL DEFAULT '',
    story_id TEXT NOT NULL DEFAULT '',
    operation TEXT NOT NULL,
    before_json TEXT NOT NULL DEFAULT '{}',
    after_json TEXT NOT NULL DEFAULT '{}',
    diff_json TEXT NOT NULL DEFAULT '{}',
    reasons_json TEXT NOT NULL DEFAULT '[]',
    signals_json TEXT NOT NULL DEFAULT '{}',
    locked_fields_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (config_key) REFERENCES automatic_configuration_state(config_key) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_automatic_configuration_revisions_scope
ON automatic_configuration_revisions(config_key, created_at DESC);
