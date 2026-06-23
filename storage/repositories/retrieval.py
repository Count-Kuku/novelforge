from __future__ import annotations

import json
import sqlite3
from hashlib import sha256
from typing import Any


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _authority_from_metadata(metadata: dict) -> float:
    value = metadata.get("authority_weight")
    try:
        return float(value)
    except (TypeError, ValueError):
        authority = str(metadata.get("authority") or "").strip()
        return {
            "project": 2.0,
            "official": 1.5,
            "curated": 1.0,
            "community": 0.5,
            "unknown": 0.0,
        }.get(authority, 0.0)


def _story_id_or_none(conn: sqlite3.Connection, story_id: Any) -> str | None:
    clean_story_id = str(story_id or "").strip()
    if not clean_story_id:
        return None
    row = conn.execute(
        "SELECT story_id FROM stories WHERE story_id = ? AND deleted_at IS NULL",
        (clean_story_id,),
    ).fetchone()
    return clean_story_id if row else None


def sync_retrieval_manifest_payload(conn: sqlite3.Connection, manifest: dict) -> dict:
    documents = manifest.get("documents", []) if isinstance(manifest, dict) else []
    chunks = manifest.get("chunks", []) if isinstance(manifest, dict) else []
    normalized_documents = [dict(item) for item in documents if isinstance(item, dict)]
    normalized_chunks = [dict(item) for item in chunks if isinstance(item, dict)]

    active_doc_ids: list[str] = []
    for doc in normalized_documents:
        doc_id = str(doc.get("doc_id") or doc.get("document_id") or "").strip()
        if not doc_id:
            continue
        active_doc_ids.append(doc_id)
        metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
        conn.execute(
            """
            INSERT INTO retrieval_documents (
                document_id, story_id, source_id, asset_id, knowledge_id, document_type,
                scope, title, summary, authority, canon_status, worldline_id,
                metadata_json, created_at, updated_at, deleted_at
            )
            VALUES (
                ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                NULL
            )
            ON CONFLICT(document_id) DO UPDATE SET
                story_id = excluded.story_id,
                knowledge_id = excluded.knowledge_id,
                document_type = excluded.document_type,
                scope = excluded.scope,
                title = excluded.title,
                summary = excluded.summary,
                authority = excluded.authority,
                canon_status = excluded.canon_status,
                worldline_id = excluded.worldline_id,
                metadata_json = excluded.metadata_json,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                deleted_at = NULL
            """,
            (
                doc_id,
                _story_id_or_none(conn, metadata.get("story_id")),
                str(metadata.get("knowledge_id") or doc.get("knowledge_id") or "").strip() or None,
                str(doc.get("source_type") or "unknown"),
                str(doc.get("scope") or "project"),
                str(doc.get("title") or ""),
                str(doc.get("content") or "")[:1000],
                _authority_from_metadata(metadata),
                str(metadata.get("canon_status") or "").strip() or None,
                str(metadata.get("worldline_id") or "").strip() or None,
                _json_dumps(doc),
            ),
        )

    active_chunk_ids: list[str] = []
    for chunk in normalized_chunks:
        chunk_id = str(chunk.get("chunk_id") or "").strip()
        document_id = str(chunk.get("document_id") or "").strip()
        if not chunk_id or not document_id:
            continue
        if document_id not in active_doc_ids:
            continue
        active_chunk_ids.append(chunk_id)
        metadata = chunk.get("metadata", {}) if isinstance(chunk.get("metadata"), dict) else {}
        conn.execute(
            """
            INSERT INTO retrieval_chunks (
                chunk_id, document_id, chunk_index, text, token_count, content_hash,
                metadata_json, created_at, updated_at, deleted_at
            )
            VALUES (
                ?, ?, ?, ?, NULL, NULL, ?,
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                NULL
            )
            ON CONFLICT(chunk_id) DO UPDATE SET
                document_id = excluded.document_id,
                chunk_index = excluded.chunk_index,
                text = excluded.text,
                metadata_json = excluded.metadata_json,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                deleted_at = NULL
            """,
            (
                chunk_id,
                document_id,
                int(metadata.get("chunk_index") or _infer_chunk_index(chunk_id)),
                str(chunk.get("content") or ""),
                _json_dumps(chunk),
            ),
        )

    if active_chunk_ids:
        placeholders = ",".join("?" for _ in active_chunk_ids)
        conn.execute(
            f"""
            UPDATE retrieval_chunks
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE chunk_id NOT IN ({placeholders}) AND deleted_at IS NULL
            """,
            tuple(active_chunk_ids),
        )
    else:
        conn.execute(
            """
            UPDATE retrieval_chunks
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE deleted_at IS NULL
            """
        )
    if active_chunk_ids:
        placeholders = ",".join("?" for _ in active_chunk_ids)
        conn.execute(
            f"DELETE FROM retrieval_vectors WHERE chunk_id NOT IN ({placeholders})",
            tuple(active_chunk_ids),
        )
    else:
        conn.execute("DELETE FROM retrieval_vectors")

    if active_doc_ids:
        placeholders = ",".join("?" for _ in active_doc_ids)
        conn.execute(
            f"""
            UPDATE retrieval_documents
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE document_id NOT IN ({placeholders}) AND deleted_at IS NULL
            """,
            tuple(active_doc_ids),
        )
    else:
        conn.execute(
            """
            UPDATE retrieval_documents
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE deleted_at IS NULL
            """
        )
    conn.execute(
        """
        DELETE FROM retrieval_vectors
        WHERE chunk_id NOT IN (
            SELECT chunk.chunk_id
            FROM retrieval_chunks AS chunk
            JOIN retrieval_documents AS doc ON doc.document_id = chunk.document_id
            WHERE chunk.deleted_at IS NULL AND doc.deleted_at IS NULL
        )
        """
    )
    return manifest


def load_retrieval_manifest_payload(conn: sqlite3.Connection, project_name: str) -> dict:
    doc_rows = conn.execute(
        """
        SELECT document_id, document_type, scope, title, summary, metadata_json, updated_at
        FROM retrieval_documents
        WHERE deleted_at IS NULL
        ORDER BY document_id
        """
    ).fetchall()
    chunk_rows = conn.execute(
        """
        SELECT chunk.chunk_id, chunk.document_id, chunk.text, chunk.metadata_json, chunk.updated_at
        FROM retrieval_chunks AS chunk
        JOIN retrieval_documents AS doc ON doc.document_id = chunk.document_id
        WHERE chunk.deleted_at IS NULL
          AND doc.deleted_at IS NULL
        ORDER BY chunk.document_id, chunk.chunk_index, chunk.chunk_id
        """
    ).fetchall()
    if not doc_rows and not chunk_rows:
        return {}

    documents: list[dict] = []
    documents_by_id: dict[str, dict] = {}
    for row in doc_rows:
        payload = _json_loads_dict(row["metadata_json"] if isinstance(row, sqlite3.Row) else row[5])
        document_id = row["document_id"] if isinstance(row, sqlite3.Row) else row[0]
        payload.setdefault("doc_id", document_id)
        payload.setdefault("project_name", project_name)
        payload.setdefault("source_type", row["document_type"] if isinstance(row, sqlite3.Row) else row[1])
        payload.setdefault("scope", row["scope"] if isinstance(row, sqlite3.Row) else row[2])
        payload.setdefault("title", row["title"] if isinstance(row, sqlite3.Row) else row[3])
        payload.setdefault("content", row["summary"] if isinstance(row, sqlite3.Row) else row[4])
        payload.setdefault("metadata", {})
        documents.append(payload)
        documents_by_id[str(document_id)] = payload

    chunks: list[dict] = []
    for row in chunk_rows:
        payload = _json_loads_dict(row["metadata_json"] if isinstance(row, sqlite3.Row) else row[3])
        payload.setdefault("chunk_id", row["chunk_id"] if isinstance(row, sqlite3.Row) else row[0])
        document_id = row["document_id"] if isinstance(row, sqlite3.Row) else row[1]
        document = documents_by_id.get(str(document_id), {})
        payload.setdefault("document_id", document_id)
        payload.setdefault("project_name", project_name)
        payload.setdefault("source_type", document.get("source_type", "unknown"))
        payload.setdefault("scope", document.get("scope", "project"))
        payload.setdefault("title", document.get("title", ""))
        payload.setdefault("content", row["text"] if isinstance(row, sqlite3.Row) else row[2])
        if document.get("path") is not None:
            payload.setdefault("path", document.get("path"))
        if document.get("tags") is not None:
            payload.setdefault("tags", document.get("tags"))
        payload.setdefault("metadata", {})
        chunks.append(payload)

    model_row = conn.execute(
        """
        SELECT vector.embedding_model
        FROM retrieval_vectors AS vector
        JOIN retrieval_chunks AS chunk ON chunk.chunk_id = vector.chunk_id
        JOIN retrieval_documents AS doc ON doc.document_id = chunk.document_id
        WHERE chunk.deleted_at IS NULL AND doc.deleted_at IS NULL
        GROUP BY vector.embedding_model
        ORDER BY MAX(vector.updated_at) DESC, vector.embedding_model
        LIMIT 1
        """
    ).fetchone()
    embedding_model = ""
    if model_row:
        embedding_model = model_row["embedding_model"] if isinstance(model_row, sqlite3.Row) else model_row[0]

    updated_values = []
    for row in list(doc_rows) + list(chunk_rows):
        updated_values.append(row["updated_at"] if isinstance(row, sqlite3.Row) else row[-1])
    built_at = max([str(value) for value in updated_values if value] or [""])
    return {
        "project_name": project_name,
        "version": 1,
        "built_at": built_at,
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "embedding_model": embedding_model,
        "embedding_enabled": bool(embedding_model),
        "documents": documents,
        "chunks": chunks,
    }


def sync_retrieval_vector_store_payload(conn: sqlite3.Connection, payload: dict) -> dict:
    vector_store = dict(payload or {})
    embedding_model = str(vector_store.get("embedding_model") or "").strip()
    if not embedding_model:
        raise ValueError("Embedding model cannot be empty.")
    vectors = vector_store.get("vectors", {})
    if not isinstance(vectors, dict):
        vectors = {}
    active_chunk_ids: list[str] = []
    for chunk_id, raw_vector in vectors.items():
        clean_chunk_id = str(chunk_id or "").strip()
        if not clean_chunk_id or not isinstance(raw_vector, list):
            continue
        vector = []
        for value in raw_vector:
            try:
                vector.append(float(value))
            except (TypeError, ValueError):
                vector = []
                break
        if not vector:
            continue
        row = conn.execute(
            """
            SELECT chunk.chunk_id
            FROM retrieval_chunks AS chunk
            JOIN retrieval_documents AS doc ON doc.document_id = chunk.document_id
            WHERE chunk.chunk_id = ?
              AND chunk.deleted_at IS NULL
              AND doc.deleted_at IS NULL
            """,
            (clean_chunk_id,),
        ).fetchone()
        if not row:
            continue
        encoded = json.dumps(vector, separators=(",", ":")).encode("utf-8")
        active_chunk_ids.append(clean_chunk_id)
        conn.execute(
            """
            INSERT INTO retrieval_vectors (
                chunk_id, embedding_model, vector_dim, vector_blob, content_hash,
                created_at, updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?,
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            )
            ON CONFLICT(chunk_id, embedding_model) DO UPDATE SET
                vector_dim = excluded.vector_dim,
                vector_blob = excluded.vector_blob,
                content_hash = excluded.content_hash,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            """,
            (
                clean_chunk_id,
                embedding_model,
                len(vector),
                encoded,
                sha256(encoded).hexdigest(),
            ),
        )
    if active_chunk_ids:
        placeholders = ",".join("?" for _ in active_chunk_ids)
        conn.execute(
            f"""
            DELETE FROM retrieval_vectors
            WHERE embedding_model = ? AND chunk_id NOT IN ({placeholders})
            """,
            (embedding_model, *active_chunk_ids),
        )
    else:
        conn.execute(
            "DELETE FROM retrieval_vectors WHERE embedding_model = ?",
            (embedding_model,),
        )
    return vector_store


def load_retrieval_vector_store_payload(conn: sqlite3.Connection, project_name: str, embedding_model: str | None = None) -> dict:
    clean_model = str(embedding_model or "").strip()
    if not clean_model:
        row = conn.execute(
            """
            SELECT vector.embedding_model
            FROM retrieval_vectors AS vector
            JOIN retrieval_chunks AS chunk ON chunk.chunk_id = vector.chunk_id
            JOIN retrieval_documents AS doc ON doc.document_id = chunk.document_id
            WHERE chunk.deleted_at IS NULL AND doc.deleted_at IS NULL
            GROUP BY vector.embedding_model
            ORDER BY MAX(vector.updated_at) DESC, vector.embedding_model
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return {}
        clean_model = row["embedding_model"] if isinstance(row, sqlite3.Row) else row[0]

    rows = conn.execute(
        """
        SELECT vector.chunk_id, vector.vector_blob, vector.updated_at
        FROM retrieval_vectors AS vector
        JOIN retrieval_chunks AS chunk ON chunk.chunk_id = vector.chunk_id
        JOIN retrieval_documents AS doc ON doc.document_id = chunk.document_id
        WHERE vector.embedding_model = ?
          AND chunk.deleted_at IS NULL
          AND doc.deleted_at IS NULL
        ORDER BY vector.chunk_id
        """,
        (clean_model,),
    ).fetchall()
    if not rows:
        return {}

    vectors: dict[str, list[float]] = {}
    updated_values: list[str] = []
    for row in rows:
        chunk_id = row["chunk_id"] if isinstance(row, sqlite3.Row) else row[0]
        blob = row["vector_blob"] if isinstance(row, sqlite3.Row) else row[1]
        if isinstance(blob, bytes):
            raw = blob.decode("utf-8")
        else:
            raw = str(blob or "")
        try:
            vector = json.loads(raw)
        except Exception:
            vector = []
        if isinstance(vector, list):
            vectors[str(chunk_id)] = [float(value) for value in vector]
        updated_values.append(str(row["updated_at"] if isinstance(row, sqlite3.Row) else row[2]))
    return {
        "project_name": project_name,
        "built_at": max([value for value in updated_values if value] or [""]),
        "embedding_model": clean_model,
        "vectors": vectors,
    }


def _infer_chunk_index(chunk_id: str) -> int:
    marker = "#chunk"
    if marker not in chunk_id:
        return 1
    try:
        return int(chunk_id.rsplit(marker, 1)[-1])
    except ValueError:
        return 1
