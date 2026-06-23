CREATE TABLE IF NOT EXISTS project_meta (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL DEFAULT '',
    genre TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS stories (
    story_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS story_profiles (
    story_id TEXT PRIMARY KEY,
    profile_json TEXT NOT NULL DEFAULT '{}',
    worldline_id TEXT,
    worldline_name TEXT,
    retrieval_mode TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS asset_files (
    asset_id TEXT PRIMARY KEY,
    story_id TEXT,
    asset_type TEXT NOT NULL,
    logical_key TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    relative_path TEXT NOT NULL,
    content_hash TEXT,
    mime_type TEXT,
    source_kind TEXT,
    source_ref TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE SET NULL,
    UNIQUE (story_id, asset_type, logical_key)
);

CREATE TABLE IF NOT EXISTS rules (
    rule_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL CHECK (scope IN ('global', 'project', 'story')),
    story_id TEXT,
    capability TEXT NOT NULL,
    content TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 50,
    source TEXT NOT NULL DEFAULT 'manual',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS prompt_options (
    option_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL CHECK (scope IN ('global', 'project', 'story')),
    story_id TEXT,
    capability TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'custom',
    slot TEXT NOT NULL DEFAULT 'custom',
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    built_in INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 50,
    source TEXT NOT NULL DEFAULT 'manual',
    source_kind TEXT,
    source_ref TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS source_documents (
    source_id TEXT PRIMARY KEY,
    story_id TEXT,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL,
    authority REAL NOT NULL DEFAULT 0,
    canon_status TEXT,
    original_asset_id TEXT,
    content_hash TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE SET NULL,
    FOREIGN KEY (original_asset_id) REFERENCES asset_files(asset_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS source_segments (
    segment_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    segment_index INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    asset_id TEXT,
    text_hash TEXT,
    summary TEXT NOT NULL DEFAULT '',
    import_status TEXT NOT NULL DEFAULT 'pending',
    extraction_status TEXT NOT NULL DEFAULT 'pending',
    last_extraction_mode TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT,
    FOREIGN KEY (source_id) REFERENCES source_documents(source_id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES asset_files(asset_id) ON DELETE SET NULL,
    UNIQUE (source_id, segment_index)
);

CREATE TABLE IF NOT EXISTS knowledge_items (
    knowledge_id TEXT PRIMARY KEY,
    story_id TEXT,
    category TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    content_json TEXT NOT NULL DEFAULT '{}',
    canon_status TEXT,
    worldline_id TEXT,
    worldline_name TEXT,
    confidence REAL,
    importance REAL,
    evidence_strength REAL,
    source_id TEXT,
    segment_id TEXT,
    extraction_mode TEXT,
    setting_scope TEXT,
    setting_role TEXT,
    injection_policy TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE SET NULL,
    FOREIGN KEY (source_id) REFERENCES source_documents(source_id) ON DELETE SET NULL,
    FOREIGN KEY (segment_id) REFERENCES source_segments(segment_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS pending_knowledge_items (
    pending_id TEXT PRIMARY KEY,
    story_id TEXT,
    category TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    content_json TEXT NOT NULL DEFAULT '{}',
    canon_status TEXT,
    worldline_id TEXT,
    confidence REAL,
    importance REAL,
    evidence_strength REAL,
    source_id TEXT,
    segment_id TEXT,
    extraction_mode TEXT,
    quality_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE SET NULL,
    FOREIGN KEY (source_id) REFERENCES source_documents(source_id) ON DELETE SET NULL,
    FOREIGN KEY (segment_id) REFERENCES source_segments(segment_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS knowledge_evidence (
    evidence_id TEXT PRIMARY KEY,
    knowledge_id TEXT,
    pending_id TEXT,
    source_id TEXT,
    segment_id TEXT,
    chunk_id TEXT,
    quote TEXT NOT NULL DEFAULT '',
    location_json TEXT NOT NULL DEFAULT '{}',
    confidence REAL,
    evidence_strength REAL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (knowledge_id) REFERENCES knowledge_items(knowledge_id) ON DELETE CASCADE,
    FOREIGN KEY (pending_id) REFERENCES pending_knowledge_items(pending_id) ON DELETE CASCADE,
    FOREIGN KEY (source_id) REFERENCES source_documents(source_id) ON DELETE SET NULL,
    FOREIGN KEY (segment_id) REFERENCES source_segments(segment_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS entity_alias_groups (
    alias_group_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    entity_type TEXT,
    story_id TEXT,
    worldline_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS retrieval_documents (
    document_id TEXT PRIMARY KEY,
    story_id TEXT,
    source_id TEXT,
    asset_id TEXT,
    knowledge_id TEXT,
    document_type TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'project',
    title TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    authority REAL NOT NULL DEFAULT 0,
    canon_status TEXT,
    worldline_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE SET NULL,
    FOREIGN KEY (source_id) REFERENCES source_documents(source_id) ON DELETE SET NULL,
    FOREIGN KEY (asset_id) REFERENCES asset_files(asset_id) ON DELETE SET NULL,
    FOREIGN KEY (knowledge_id) REFERENCES knowledge_items(knowledge_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS retrieval_chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    token_count INTEGER,
    content_hash TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT,
    FOREIGN KEY (document_id) REFERENCES retrieval_documents(document_id) ON DELETE CASCADE,
    UNIQUE (document_id, chunk_index)
);

CREATE VIRTUAL TABLE IF NOT EXISTS retrieval_chunks_fts USING fts5(
    title,
    text,
    entity_names,
    source_terms,
    content='retrieval_chunks',
    content_rowid='rowid'
);

CREATE TABLE IF NOT EXISTS retrieval_vectors (
    chunk_id TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    vector_dim INTEGER NOT NULL,
    vector_blob BLOB NOT NULL,
    content_hash TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (chunk_id, embedding_model),
    FOREIGN KEY (chunk_id) REFERENCES retrieval_chunks(chunk_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS retrieval_feedback (
    feedback_id TEXT PRIMARY KEY,
    chunk_id TEXT,
    story_id TEXT,
    task_type TEXT,
    feedback_type TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    weight REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (chunk_id) REFERENCES retrieval_chunks(chunk_id) ON DELETE SET NULL,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS retrieval_eval_cases (
    case_id TEXT PRIMARY KEY,
    story_id TEXT,
    name TEXT NOT NULL,
    query TEXT NOT NULL,
    task_type TEXT,
    expected_json TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS retrieval_eval_runs (
    run_id TEXT PRIMARY KEY,
    case_id TEXT,
    story_id TEXT,
    status TEXT NOT NULL,
    result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (case_id) REFERENCES retrieval_eval_cases(case_id) ON DELETE SET NULL,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS retrieval_conflict_resolutions (
    resolution_id TEXT PRIMARY KEY,
    story_id TEXT,
    conflict_key TEXT NOT NULL,
    preferred_scope TEXT,
    preferred_source_id TEXT,
    decision TEXT NOT NULL,
    rationale TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE SET NULL,
    FOREIGN KEY (preferred_source_id) REFERENCES source_documents(source_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS graph_nodes (
    node_id TEXT PRIMARY KEY,
    story_id TEXT,
    node_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    knowledge_id TEXT,
    alias_group_id TEXT,
    canon_status TEXT,
    worldline_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE SET NULL,
    FOREIGN KEY (knowledge_id) REFERENCES knowledge_items(knowledge_id) ON DELETE SET NULL,
    FOREIGN KEY (alias_group_id) REFERENCES entity_alias_groups(alias_group_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS graph_edges (
    edge_id TEXT PRIMARY KEY,
    story_id TEXT,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'directed',
    confidence REAL,
    evidence_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deleted_at TEXT,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE SET NULL,
    FOREIGN KEY (source_node_id) REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
    FOREIGN KEY (target_node_id) REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
    FOREIGN KEY (evidence_id) REFERENCES knowledge_evidence(evidence_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS auto_review_policy (
    policy_id TEXT PRIMARY KEY,
    policy_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS auto_review_runs (
    run_id TEXT PRIMARY KEY,
    run_type TEXT NOT NULL DEFAULT 'auto_review',
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id TEXT PRIMARY KEY,
    story_id TEXT,
    workflow_type TEXT NOT NULL,
    status TEXT NOT NULL,
    parent_run_id TEXT,
    input_json TEXT NOT NULL DEFAULT '{}',
    output_json TEXT NOT NULL DEFAULT '{}',
    error_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE SET NULL,
    FOREIGN KEY (parent_run_id) REFERENCES workflow_runs(run_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS workflow_steps (
    step_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    step_order INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    input_json TEXT NOT NULL DEFAULT '{}',
    output_json TEXT NOT NULL DEFAULT '{}',
    error_json TEXT NOT NULL DEFAULT '{}',
    artifact_asset_id TEXT,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (artifact_asset_id) REFERENCES asset_files(asset_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_asset_files_story_type ON asset_files(story_id, asset_type, deleted_at);
CREATE INDEX IF NOT EXISTS idx_rules_scope_capability ON rules(scope, story_id, capability, deleted_at);
CREATE INDEX IF NOT EXISTS idx_prompt_options_scope_capability ON prompt_options(scope, story_id, capability, deleted_at);
CREATE INDEX IF NOT EXISTS idx_source_segments_source ON source_segments(source_id, segment_index);
CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge_items(category, story_id, worldline_id, canon_status, deleted_at);
CREATE INDEX IF NOT EXISTS idx_pending_knowledge_status ON pending_knowledge_items(status, category, story_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_evidence_knowledge ON knowledge_evidence(knowledge_id, pending_id, source_id, segment_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_documents_scope ON retrieval_documents(story_id, scope, document_type, deleted_at);
CREATE INDEX IF NOT EXISTS idx_retrieval_chunks_document ON retrieval_chunks(document_id, chunk_index, deleted_at);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_lookup ON graph_nodes(story_id, node_type, canonical_name, worldline_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source_node_id, relation_type, deleted_at);
CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target_node_id, relation_type, deleted_at);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_story ON workflow_runs(story_id, workflow_type, status, created_at);
