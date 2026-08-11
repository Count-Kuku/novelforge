-- Traceable source/knowledge revisions, typed knowledge and hierarchical RAG.

CREATE TABLE IF NOT EXISTS source_revisions (
    revision_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    previous_revision_id TEXT,
    content_hash TEXT NOT NULL,
    parser_name TEXT NOT NULL DEFAULT '',
    parser_version TEXT NOT NULL DEFAULT '',
    media_type TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL DEFAULT '',
    char_count INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (source_id) REFERENCES source_documents(source_id) ON DELETE CASCADE,
    FOREIGN KEY (previous_revision_id) REFERENCES source_revisions(revision_id) ON DELETE SET NULL,
    UNIQUE (source_id, content_hash)
);

ALTER TABLE source_documents ADD COLUMN active_revision_id TEXT;

ALTER TABLE source_segments ADD COLUMN source_revision_id TEXT;
ALTER TABLE source_segments ADD COLUMN parent_segment_id TEXT;
ALTER TABLE source_segments ADD COLUMN start_offset INTEGER;
ALTER TABLE source_segments ADD COLUMN end_offset INTEGER;
ALTER TABLE source_segments ADD COLUMN heading_path_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE source_segments ADD COLUMN content_kind TEXT NOT NULL DEFAULT 'section';

ALTER TABLE knowledge_items ADD COLUMN status TEXT NOT NULL DEFAULT 'confirmed';
ALTER TABLE knowledge_items ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE knowledge_items ADD COLUMN structured_json TEXT NOT NULL DEFAULT '{}';

ALTER TABLE pending_knowledge_items ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE pending_knowledge_items ADD COLUMN structured_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE pending_knowledge_items ADD COLUMN source_revision_id TEXT;

ALTER TABLE knowledge_evidence ADD COLUMN source_revision_id TEXT;
ALTER TABLE knowledge_evidence ADD COLUMN quote_hash TEXT;
ALTER TABLE knowledge_evidence ADD COLUMN start_offset INTEGER;
ALTER TABLE knowledge_evidence ADD COLUMN end_offset INTEGER;
ALTER TABLE knowledge_evidence ADD COLUMN prefix TEXT NOT NULL DEFAULT '';
ALTER TABLE knowledge_evidence ADD COLUMN suffix TEXT NOT NULL DEFAULT '';
ALTER TABLE knowledge_evidence ADD COLUMN validation_status TEXT NOT NULL DEFAULT 'unverified';

CREATE TABLE IF NOT EXISTS knowledge_revisions (
    revision_id TEXT PRIMARY KEY,
    knowledge_id TEXT NOT NULL,
    revision_no INTEGER NOT NULL,
    change_type TEXT NOT NULL DEFAULT 'update',
    snapshot_json TEXT NOT NULL DEFAULT '{}',
    source_revision_id TEXT,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (knowledge_id) REFERENCES knowledge_items(knowledge_id) ON DELETE CASCADE,
    FOREIGN KEY (source_revision_id) REFERENCES source_revisions(revision_id) ON DELETE SET NULL,
    UNIQUE (knowledge_id, revision_no)
);

ALTER TABLE retrieval_documents ADD COLUMN source_revision_id TEXT;
ALTER TABLE retrieval_documents ADD COLUMN content_hash TEXT;

ALTER TABLE retrieval_chunks ADD COLUMN parent_chunk_id TEXT;
ALTER TABLE retrieval_chunks ADD COLUMN previous_chunk_id TEXT;
ALTER TABLE retrieval_chunks ADD COLUMN next_chunk_id TEXT;
ALTER TABLE retrieval_chunks ADD COLUMN chunk_level TEXT NOT NULL DEFAULT 'child';
ALTER TABLE retrieval_chunks ADD COLUMN start_offset INTEGER;
ALTER TABLE retrieval_chunks ADD COLUMN end_offset INTEGER;
ALTER TABLE retrieval_chunks ADD COLUMN source_revision_id TEXT;

ALTER TABLE retrieval_feedback ADD COLUMN content_hash TEXT;
ALTER TABLE retrieval_feedback ADD COLUMN source_revision_id TEXT;

DROP TABLE IF EXISTS retrieval_chunks_fts;
CREATE VIRTUAL TABLE retrieval_chunks_fts USING fts5(
    chunk_id UNINDEXED,
    title,
    text,
    entity_names,
    source_terms,
    tokenize='trigram'
);

-- Existing projects already have authoritative retrieval rows when this
-- migration runs.  Backfill the new FTS channel immediately so users do not
-- need a manual index rebuild before the first post-upgrade query.
INSERT INTO retrieval_chunks_fts (chunk_id, title, text, entity_names, source_terms)
SELECT chunk.chunk_id, doc.title, chunk.text, '', doc.document_type
FROM retrieval_chunks AS chunk
JOIN retrieval_documents AS doc ON doc.document_id = chunk.document_id
WHERE chunk.deleted_at IS NULL AND doc.deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_source_revisions_source_created
    ON source_revisions(source_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_segments_revision
    ON source_segments(source_revision_id, segment_index);
CREATE INDEX IF NOT EXISTS idx_knowledge_items_type_status
    ON knowledge_items(category, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_revisions_item
    ON knowledge_revisions(knowledge_id, revision_no DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_evidence_source_anchor
    ON knowledge_evidence(source_id, segment_id, start_offset);
CREATE INDEX IF NOT EXISTS idx_retrieval_chunks_parent
    ON retrieval_chunks(parent_chunk_id, chunk_index);
