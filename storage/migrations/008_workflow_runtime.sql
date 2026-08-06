ALTER TABLE workflow_runs ADD COLUMN updated_at TEXT;
ALTER TABLE workflow_runs ADD COLUMN worker_id TEXT;
ALTER TABLE workflow_runs ADD COLUMN lease_expires_at TEXT;
ALTER TABLE workflow_runs ADD COLUMN heartbeat_at TEXT;
ALTER TABLE workflow_runs ADD COLUMN control_requested TEXT NOT NULL DEFAULT '';
ALTER TABLE workflow_runs ADD COLUMN priority INTEGER NOT NULL DEFAULT 0;
ALTER TABLE workflow_runs ADD COLUMN estimated_input_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE workflow_runs ADD COLUMN estimated_output_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE workflow_runs ADD COLUMN estimated_embedding_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE workflow_runs ADD COLUMN estimated_cost_usd REAL NOT NULL DEFAULT 0;
ALTER TABLE workflow_runs ADD COLUMN archived_at TEXT;

UPDATE workflow_runs
SET updated_at = COALESCE(finished_at, started_at, created_at)
WHERE updated_at IS NULL OR updated_at = '';

CREATE INDEX IF NOT EXISTS idx_workflow_runs_runtime_queue
ON workflow_runs(workflow_type, archived_at, status, priority, created_at);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_runtime_lease
ON workflow_runs(workflow_type, status, lease_expires_at);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_runtime_archive
ON workflow_runs(workflow_type, archived_at, updated_at);
