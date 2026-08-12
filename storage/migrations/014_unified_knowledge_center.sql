-- Unified, paged knowledge/source search with durable incremental indexing.

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_center_fts USING fts5(
    record_type UNINDEXED,
    record_id UNINDEXED,
    category,
    title,
    body,
    source_terms,
    worldline_terms,
    story_id UNINDEXED,
    worldline_id UNINDEXED,
    record_status UNINDEXED,
    updated_at UNINDEXED,
    tokenize = 'trigram'
);

CREATE TABLE IF NOT EXISTS knowledge_index_jobs (
    job_id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL CHECK (record_type IN ('knowledge', 'pending', 'source')),
    record_id TEXT NOT NULL,
    operation TEXT NOT NULL DEFAULT 'upsert' CHECK (operation IN ('upsert', 'delete')),
    revision_token TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    error_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS knowledge_index_state (
    state_id INTEGER PRIMARY KEY CHECK (state_id = 1),
    retrieval_status TEXT NOT NULL DEFAULT 'completed' CHECK (retrieval_status IN ('queued', 'running', 'completed', 'failed')),
    indexed_revision INTEGER NOT NULL DEFAULT 0,
    requested_revision INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    last_fts_at TEXT,
    last_retrieval_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT OR IGNORE INTO knowledge_index_state (state_id) VALUES (1);

CREATE INDEX IF NOT EXISTS idx_knowledge_index_jobs_status
ON knowledge_index_jobs (status, updated_at, job_id);

INSERT INTO knowledge_center_fts (
    record_type, record_id, category, title, body, source_terms,
    worldline_terms, story_id, worldline_id, record_status, updated_at
)
SELECT
    'knowledge', knowledge_id, category,
    COALESCE(NULLIF(name, ''), NULLIF(title, ''), knowledge_id),
    content_json,
    COALESCE((SELECT title FROM source_documents WHERE source_id = knowledge_items.source_id), ''),
    COALESCE(worldline_name, '') || ' ' || COALESCE(worldline_id, ''),
    COALESCE(story_id, ''), COALESCE(worldline_id, ''),
    CASE WHEN deleted_at IS NULL THEN COALESCE(status, 'confirmed') ELSE 'archived' END,
    COALESCE(updated_at, created_at)
FROM knowledge_items;

INSERT INTO knowledge_center_fts (
    record_type, record_id, category, title, body, source_terms,
    worldline_terms, story_id, worldline_id, record_status, updated_at
)
SELECT
    'pending', pending_id, category,
    COALESCE(NULLIF(name, ''), NULLIF(title, ''), pending_id),
    content_json,
    COALESCE((SELECT title FROM source_documents WHERE source_id = pending_knowledge_items.source_id), ''),
    COALESCE(worldline_id, ''), COALESCE(story_id, ''), COALESCE(worldline_id, ''),
    CASE WHEN deleted_at IS NULL THEN COALESCE(status, 'pending') ELSE 'archived' END,
    COALESCE(updated_at, created_at)
FROM pending_knowledge_items;

INSERT INTO knowledge_center_fts (
    record_type, record_id, category, title, body, source_terms,
    worldline_terms, story_id, worldline_id, record_status, updated_at
)
SELECT
    'source', segment.segment_id, 'source',
    COALESCE(NULLIF(segment.title, ''), NULLIF(source.title, ''), segment.segment_id),
    COALESCE(
        (
            SELECT GROUP_CONCAT(chunk.text, char(10))
            FROM retrieval_documents AS document
            JOIN retrieval_chunks AS chunk ON chunk.document_id = document.document_id
            WHERE chunk.deleted_at IS NULL AND document.deleted_at IS NULL
              AND (
                  document.source_id = source.source_id
                  OR (
                      COALESCE(json_extract(source.metadata_json, '$.relative_path'), '') <> ''
                      AND instr(
                          replace(COALESCE(json_extract(document.metadata_json, '$.path'), ''), '\', '/'),
                          json_extract(source.metadata_json, '$.relative_path')
                      ) > 0
                  )
              )
        ),
        segment.metadata_json
    ),
    COALESCE(source.title, '') || ' ' || COALESCE(source.source_type, ''),
    '', COALESCE(source.story_id, ''), '',
    CASE WHEN segment.deleted_at IS NULL AND source.deleted_at IS NULL THEN 'source' ELSE 'archived' END,
    COALESCE(segment.updated_at, segment.created_at)
FROM source_segments AS segment
JOIN source_documents AS source ON source.source_id = segment.source_id;

CREATE TRIGGER IF NOT EXISTS trg_knowledge_center_knowledge_insert
AFTER INSERT ON knowledge_items
BEGIN
    INSERT INTO knowledge_index_jobs (
        job_id, record_type, record_id, operation, revision_token, status, updated_at, finished_at
    ) VALUES (
        'knowledge:' || NEW.knowledge_id, 'knowledge', NEW.knowledge_id, 'upsert',
        COALESCE(NEW.updated_at, '') || ':' || COALESCE(NEW.deleted_at, ''), 'queued',
        strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL
    )
    ON CONFLICT(job_id) DO UPDATE SET
        operation = excluded.operation, revision_token = excluded.revision_token,
        status = 'queued', error_text = '', updated_at = excluded.updated_at, finished_at = NULL;
    UPDATE knowledge_index_state
    SET retrieval_status = 'queued', requested_revision = requested_revision + 1,
        last_error = '', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    WHERE state_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS trg_knowledge_center_knowledge_update
AFTER UPDATE ON knowledge_items
WHEN OLD.content_json IS NOT NEW.content_json
  OR OLD.deleted_at IS NOT NEW.deleted_at
  OR OLD.category IS NOT NEW.category
  OR OLD.story_id IS NOT NEW.story_id
  OR OLD.worldline_id IS NOT NEW.worldline_id
  OR OLD.status IS NOT NEW.status
BEGIN
    INSERT INTO knowledge_index_jobs (
        job_id, record_type, record_id, operation, revision_token, status, updated_at, finished_at
    ) VALUES (
        'knowledge:' || NEW.knowledge_id, 'knowledge', NEW.knowledge_id, 'upsert',
        COALESCE(NEW.updated_at, '') || ':' || COALESCE(NEW.deleted_at, ''), 'queued',
        strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL
    )
    ON CONFLICT(job_id) DO UPDATE SET
        operation = excluded.operation, revision_token = excluded.revision_token,
        status = 'queued', error_text = '', updated_at = excluded.updated_at, finished_at = NULL;
    UPDATE knowledge_index_state
    SET retrieval_status = 'queued', requested_revision = requested_revision + 1,
        last_error = '', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    WHERE state_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS trg_knowledge_center_knowledge_delete
AFTER DELETE ON knowledge_items
BEGIN
    INSERT INTO knowledge_index_jobs (
        job_id, record_type, record_id, operation, revision_token, status, updated_at, finished_at
    ) VALUES (
        'knowledge:' || OLD.knowledge_id, 'knowledge', OLD.knowledge_id, 'delete',
        COALESCE(OLD.updated_at, ''), 'queued', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL
    )
    ON CONFLICT(job_id) DO UPDATE SET
        operation = 'delete', revision_token = excluded.revision_token,
        status = 'queued', error_text = '', updated_at = excluded.updated_at, finished_at = NULL;
    UPDATE knowledge_index_state
    SET retrieval_status = 'queued', requested_revision = requested_revision + 1,
        last_error = '', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    WHERE state_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS trg_knowledge_center_pending_insert
AFTER INSERT ON pending_knowledge_items
BEGIN
    INSERT INTO knowledge_index_jobs (
        job_id, record_type, record_id, operation, revision_token, status, updated_at, finished_at
    ) VALUES (
        'pending:' || NEW.pending_id, 'pending', NEW.pending_id, 'upsert',
        COALESCE(NEW.updated_at, '') || ':' || COALESCE(NEW.deleted_at, ''), 'queued',
        strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL
    )
    ON CONFLICT(job_id) DO UPDATE SET
        operation = excluded.operation, revision_token = excluded.revision_token,
        status = 'queued', error_text = '', updated_at = excluded.updated_at, finished_at = NULL;
    UPDATE knowledge_index_state
    SET retrieval_status = 'queued', requested_revision = requested_revision + 1,
        last_error = '', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    WHERE state_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS trg_knowledge_center_pending_update
AFTER UPDATE ON pending_knowledge_items
WHEN OLD.content_json IS NOT NEW.content_json
  OR OLD.deleted_at IS NOT NEW.deleted_at
  OR OLD.category IS NOT NEW.category
  OR OLD.story_id IS NOT NEW.story_id
  OR OLD.worldline_id IS NOT NEW.worldline_id
  OR OLD.status IS NOT NEW.status
BEGIN
    INSERT INTO knowledge_index_jobs (
        job_id, record_type, record_id, operation, revision_token, status, updated_at, finished_at
    ) VALUES (
        'pending:' || NEW.pending_id, 'pending', NEW.pending_id, 'upsert',
        COALESCE(NEW.updated_at, '') || ':' || COALESCE(NEW.deleted_at, ''), 'queued',
        strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL
    )
    ON CONFLICT(job_id) DO UPDATE SET
        operation = excluded.operation, revision_token = excluded.revision_token,
        status = 'queued', error_text = '', updated_at = excluded.updated_at, finished_at = NULL;
    UPDATE knowledge_index_state
    SET retrieval_status = 'queued', requested_revision = requested_revision + 1,
        last_error = '', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    WHERE state_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS trg_knowledge_center_pending_delete
AFTER DELETE ON pending_knowledge_items
BEGIN
    INSERT INTO knowledge_index_jobs (
        job_id, record_type, record_id, operation, revision_token, status, updated_at, finished_at
    ) VALUES (
        'pending:' || OLD.pending_id, 'pending', OLD.pending_id, 'delete',
        COALESCE(OLD.updated_at, ''), 'queued', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL
    )
    ON CONFLICT(job_id) DO UPDATE SET
        operation = 'delete', revision_token = excluded.revision_token,
        status = 'queued', error_text = '', updated_at = excluded.updated_at, finished_at = NULL;
    UPDATE knowledge_index_state
    SET retrieval_status = 'queued', requested_revision = requested_revision + 1,
        last_error = '', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    WHERE state_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS trg_knowledge_center_source_insert
AFTER INSERT ON source_segments
BEGIN
    INSERT INTO knowledge_index_jobs (
        job_id, record_type, record_id, operation, revision_token, status, updated_at, finished_at
    ) VALUES (
        'source:' || NEW.segment_id, 'source', NEW.segment_id, 'upsert',
        COALESCE(NEW.updated_at, '') || ':' || COALESCE(NEW.deleted_at, ''), 'queued',
        strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL
    )
    ON CONFLICT(job_id) DO UPDATE SET
        operation = excluded.operation, revision_token = excluded.revision_token,
        status = 'queued', error_text = '', updated_at = excluded.updated_at, finished_at = NULL;
    UPDATE knowledge_index_state
    SET retrieval_status = 'queued', requested_revision = requested_revision + 1,
        last_error = '', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    WHERE state_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS trg_knowledge_center_source_update
AFTER UPDATE ON source_segments
WHEN OLD.metadata_json IS NOT NEW.metadata_json
  OR OLD.deleted_at IS NOT NEW.deleted_at
  OR OLD.title IS NOT NEW.title
  OR OLD.source_revision_id IS NOT NEW.source_revision_id
BEGIN
    INSERT INTO knowledge_index_jobs (
        job_id, record_type, record_id, operation, revision_token, status, updated_at, finished_at
    ) VALUES (
        'source:' || NEW.segment_id, 'source', NEW.segment_id, 'upsert',
        COALESCE(NEW.updated_at, '') || ':' || COALESCE(NEW.deleted_at, ''), 'queued',
        strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL
    )
    ON CONFLICT(job_id) DO UPDATE SET
        operation = excluded.operation, revision_token = excluded.revision_token,
        status = 'queued', error_text = '', updated_at = excluded.updated_at, finished_at = NULL;
    UPDATE knowledge_index_state
    SET retrieval_status = 'queued', requested_revision = requested_revision + 1,
        last_error = '', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    WHERE state_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS trg_knowledge_center_source_document_update
AFTER UPDATE ON source_documents
WHEN OLD.title IS NOT NEW.title
  OR OLD.source_type IS NOT NEW.source_type
  OR OLD.story_id IS NOT NEW.story_id
  OR OLD.deleted_at IS NOT NEW.deleted_at
BEGIN
    INSERT INTO knowledge_index_jobs (
        job_id, record_type, record_id, operation, revision_token, status, updated_at, finished_at
    )
    SELECT
        'source:' || segment_id, 'source', segment_id, 'upsert',
        COALESCE(updated_at, '') || ':' || COALESCE(deleted_at, ''), 'queued',
        strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL
    FROM source_segments WHERE source_id = NEW.source_id
    ON CONFLICT(job_id) DO UPDATE SET
        operation = excluded.operation, revision_token = excluded.revision_token,
        status = 'queued', error_text = '', updated_at = excluded.updated_at, finished_at = NULL;
    UPDATE knowledge_index_state
    SET retrieval_status = 'queued', requested_revision = requested_revision + 1,
        last_error = '', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    WHERE state_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS trg_knowledge_center_source_delete
AFTER DELETE ON source_segments
BEGIN
    INSERT INTO knowledge_index_jobs (
        job_id, record_type, record_id, operation, revision_token, status, updated_at, finished_at
    ) VALUES (
        'source:' || OLD.segment_id, 'source', OLD.segment_id, 'delete',
        COALESCE(OLD.updated_at, ''), 'queued', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL
    )
    ON CONFLICT(job_id) DO UPDATE SET
        operation = 'delete', revision_token = excluded.revision_token,
        status = 'queued', error_text = '', updated_at = excluded.updated_at, finished_at = NULL;
    UPDATE knowledge_index_state
    SET retrieval_status = 'queued', requested_revision = requested_revision + 1,
        last_error = '', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    WHERE state_id = 1;
END;
