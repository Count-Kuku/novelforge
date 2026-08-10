CREATE TABLE IF NOT EXISTS llm_usage_events (
    event_id TEXT PRIMARY KEY,
    provider_request_id TEXT,
    occurred_at TEXT NOT NULL,
    project_name TEXT NOT NULL DEFAULT '',
    story_id TEXT NOT NULL DEFAULT '',
    workflow_run_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    operation_id TEXT NOT NULL DEFAULT '',
    operation TEXT NOT NULL DEFAULT 'unattributed',
    agent_role TEXT NOT NULL DEFAULT '',
    profile_id TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT 'openai_compatible',
    endpoint_type TEXT NOT NULL DEFAULT 'chat',
    requested_model TEXT NOT NULL DEFAULT '',
    reported_model TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    cached_input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (cached_input_tokens >= 0),
    cache_write_tokens INTEGER NOT NULL DEFAULT 0 CHECK (cache_write_tokens >= 0),
    output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    reasoning_tokens INTEGER NOT NULL DEFAULT 0 CHECK (reasoning_tokens >= 0),
    embedding_tokens INTEGER NOT NULL DEFAULT 0 CHECK (embedding_tokens >= 0),
    total_tokens INTEGER NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
    cost_microusd INTEGER,
    provider_cost_microusd INTEGER,
    calculated_cost_microusd INTEGER,
    cost_source TEXT NOT NULL DEFAULT 'unpriced',
    usage_status TEXT NOT NULL DEFAULT 'exact',
    price_snapshot_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_llm_usage_provider_request
ON llm_usage_events(provider, provider_request_id)
WHERE provider_request_id IS NOT NULL AND provider_request_id <> '';

CREATE INDEX IF NOT EXISTS idx_llm_usage_time
ON llm_usage_events(occurred_at);

CREATE INDEX IF NOT EXISTS idx_llm_usage_project_time
ON llm_usage_events(project_name, occurred_at);

CREATE INDEX IF NOT EXISTS idx_llm_usage_story_time
ON llm_usage_events(project_name, story_id, occurred_at);

CREATE INDEX IF NOT EXISTS idx_llm_usage_task
ON llm_usage_events(task_id, occurred_at);

CREATE INDEX IF NOT EXISTS idx_llm_usage_operation
ON llm_usage_events(operation_id, occurred_at);
