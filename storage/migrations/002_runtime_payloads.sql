ALTER TABLE retrieval_feedback
ADD COLUMN payload_json TEXT NOT NULL DEFAULT '{}';

ALTER TABLE retrieval_conflict_resolutions
ADD COLUMN payload_json TEXT NOT NULL DEFAULT '{}';
