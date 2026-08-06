ALTER TABLE project_meta ADD COLUMN maintenance_mode INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS retrieval_vector_store_meta (
    embedding_model TEXT PRIMARY KEY,
    build_mode TEXT NOT NULL DEFAULT 'full',
    reused_vector_count INTEGER NOT NULL DEFAULT 0,
    generated_vector_count INTEGER NOT NULL DEFAULT 0,
    removed_vector_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

UPDATE workflow_runs
SET worker_id = NULL,
    heartbeat_at = NULL,
    lease_expires_at = NULL,
    control_requested = ''
WHERE workflow_type = 'source_ingestion'
  AND status <> 'running';

CREATE INDEX IF NOT EXISTS idx_project_meta_maintenance
ON project_meta(maintenance_mode);
