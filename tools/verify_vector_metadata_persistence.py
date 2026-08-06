from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage.repositories.retrieval import (
    load_retrieval_vector_store_payload,
    sync_retrieval_vector_store_payload,
)
from storage.schema import ensure_schema


def main() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    conn.execute(
        "INSERT INTO retrieval_documents (document_id, document_type, title) VALUES ('doc', 'source', 'Doc')"
    )
    conn.execute(
        """
        INSERT INTO retrieval_chunks (chunk_id, document_id, chunk_index, text, content_hash)
        VALUES ('chunk', 'doc', 1, 'content', 'hash')
        """
    )
    sync_retrieval_vector_store_payload(conn, {
        "project_name": "metadata_verify",
        "embedding_model": "model",
        "vectors": {"chunk": [0.1, 0.2, 0.3]},
        "content_hashes": {"chunk": "hash"},
        "build_mode": "incremental",
        "reused_vector_count": 7,
        "generated_vector_count": 2,
        "removed_vector_count": 1,
    })
    conn.commit()

    loaded = load_retrieval_vector_store_payload(conn, "metadata_verify")
    assert loaded["build_mode"] == "incremental"
    assert loaded["reused_vector_count"] == 7
    assert loaded["generated_vector_count"] == 2
    assert loaded["removed_vector_count"] == 1
    assert loaded["vectors"]["chunk"] == [0.1, 0.2, 0.3]

    sync_retrieval_vector_store_payload(conn, {
        "project_name": "metadata_verify",
        "embedding_model": "empty-model",
        "vectors": {},
        "content_hashes": {},
        "build_mode": "full",
        "reused_vector_count": 0,
        "generated_vector_count": 0,
        "removed_vector_count": 3,
    })
    conn.execute(
        "UPDATE retrieval_vector_store_meta SET updated_at = '2099-01-01T00:00:00Z' WHERE embedding_model = 'empty-model'"
    )
    conn.commit()
    loaded_empty = load_retrieval_vector_store_payload(conn, "metadata_verify", "empty-model")
    assert loaded_empty["embedding_model"] == "empty-model"
    assert loaded_empty["vectors"] == {}
    assert loaded_empty["build_mode"] == "full"
    assert loaded_empty["generated_vector_count"] == 0
    assert loaded_empty["removed_vector_count"] == 3
    assert loaded_empty["built_at"] == "2099-01-01T00:00:00Z"
    loaded_latest = load_retrieval_vector_store_payload(conn, "metadata_verify")
    assert loaded_latest["embedding_model"] == "empty-model"
    conn.close()
    print("Vector metadata persistence verification passed: 12 checks")


if __name__ == "__main__":
    main()
