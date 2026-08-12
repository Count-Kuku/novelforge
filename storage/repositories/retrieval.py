from __future__ import annotations

import json
import math
import re
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


def _chunk_content_hash(chunk: dict) -> str:
    title = str(chunk.get("title") or "")
    content = str(chunk.get("content") or "")
    return sha256(f"{title}\n{content}".encode("utf-8")).hexdigest()


def _existing_id(conn: sqlite3.Connection, table: str, column: str, value: Any) -> str | None:
    clean_value = str(value or "").strip()
    if not clean_value:
        return None
    if table not in {"source_documents", "source_revisions"}:
        raise ValueError("Unsupported retrieval reference table.")
    return clean_value if conn.execute(
        f"SELECT {column} FROM {table} WHERE {column} = ?",
        (clean_value,),
    ).fetchone() else None


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
        source_id = _existing_id(conn, "source_documents", "source_id", metadata.get("source_id"))
        if not source_id and str(metadata.get("relative_path") or "").strip():
            relative_path = str(metadata.get("relative_path") or "").replace("\\", "/").strip()
            candidate_source_id = "source_file_" + sha256(relative_path.encode("utf-8")).hexdigest()[:24]
            source_id = _existing_id(conn, "source_documents", "source_id", candidate_source_id)
        source_revision_id = _existing_id(
            conn, "source_revisions", "revision_id", metadata.get("source_revision_id")
        )
        document_content_hash = sha256(str(doc.get("content") or "").encode("utf-8")).hexdigest()
        conn.execute(
            """
            INSERT INTO retrieval_documents (
                document_id, story_id, source_id, asset_id, knowledge_id, document_type,
                scope, title, summary, authority, canon_status, worldline_id,
                metadata_json, source_revision_id, content_hash,
                created_at, updated_at, deleted_at
            )
            VALUES (
                ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                NULL
            )
            ON CONFLICT(document_id) DO UPDATE SET
                story_id = excluded.story_id,
                source_id = excluded.source_id,
                knowledge_id = excluded.knowledge_id,
                document_type = excluded.document_type,
                scope = excluded.scope,
                title = excluded.title,
                summary = excluded.summary,
                authority = excluded.authority,
                canon_status = excluded.canon_status,
                worldline_id = excluded.worldline_id,
                metadata_json = excluded.metadata_json,
                source_revision_id = excluded.source_revision_id,
                content_hash = excluded.content_hash,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                deleted_at = NULL
            """,
            (
                doc_id,
                _story_id_or_none(conn, metadata.get("story_id")),
                source_id,
                str(metadata.get("knowledge_id") or doc.get("knowledge_id") or "").strip() or None,
                str(doc.get("source_type") or "unknown"),
                str(doc.get("scope") or "project"),
                str(doc.get("title") or ""),
                str(doc.get("content") or "")[:1000],
                _authority_from_metadata(metadata),
                str(metadata.get("canon_status") or "").strip() or None,
                str(metadata.get("worldline_id") or "").strip() or None,
                _json_dumps(doc),
                source_revision_id,
                document_content_hash,
            ),
        )

    active_chunk_ids: list[str] = []
    conn.execute("DELETE FROM retrieval_chunks_fts")
    for chunk in normalized_chunks:
        chunk_id = str(chunk.get("chunk_id") or "").strip()
        document_id = str(chunk.get("document_id") or "").strip()
        if not chunk_id or not document_id:
            continue
        if document_id not in active_doc_ids:
            continue
        active_chunk_ids.append(chunk_id)
        metadata = chunk.get("metadata", {}) if isinstance(chunk.get("metadata"), dict) else {}
        content_hash = _chunk_content_hash(chunk)
        conn.execute(
            """
            INSERT INTO retrieval_chunks (
                chunk_id, document_id, chunk_index, text, token_count, content_hash,
                metadata_json, parent_chunk_id, previous_chunk_id, next_chunk_id,
                chunk_level, start_offset, end_offset, source_revision_id,
                created_at, updated_at, deleted_at
            )
            VALUES (
                ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                NULL
            )
            ON CONFLICT(chunk_id) DO UPDATE SET
                document_id = excluded.document_id,
                chunk_index = excluded.chunk_index,
                text = excluded.text,
                content_hash = excluded.content_hash,
                metadata_json = excluded.metadata_json,
                parent_chunk_id = excluded.parent_chunk_id,
                previous_chunk_id = excluded.previous_chunk_id,
                next_chunk_id = excluded.next_chunk_id,
                chunk_level = excluded.chunk_level,
                start_offset = excluded.start_offset,
                end_offset = excluded.end_offset,
                source_revision_id = excluded.source_revision_id,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                deleted_at = NULL
            """,
            (
                chunk_id,
                document_id,
                int(metadata.get("chunk_index") or _infer_chunk_index(chunk_id)),
                str(chunk.get("content") or ""),
                content_hash,
                _json_dumps(chunk),
                str(metadata.get("parent_chunk_id") or "").strip() or None,
                str(metadata.get("previous_chunk_id") or "").strip() or None,
                str(metadata.get("next_chunk_id") or "").strip() or None,
                str(metadata.get("chunk_level") or "child"),
                metadata.get("start_offset"),
                metadata.get("end_offset"),
                _existing_id(conn, "source_revisions", "revision_id", metadata.get("source_revision_id")),
            ),
        )
        tags = chunk.get("tags") if isinstance(chunk.get("tags"), list) else []
        entity_names = metadata.get("entity_names") if isinstance(metadata.get("entity_names"), list) else []
        conn.execute(
            """
            INSERT INTO retrieval_chunks_fts (chunk_id, title, text, entity_names, source_terms)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                chunk_id,
                str(chunk.get("title") or ""),
                str(chunk.get("content") or ""),
                " ".join(str(value) for value in entity_names),
                " ".join([str(chunk.get("source_type") or ""), *(str(value) for value in tags)]),
            ),
        )
        # A chunk id is position based and survives edits.  Vectors generated
        # from an older payload must never be reused for the new text.
        conn.execute(
            "DELETE FROM retrieval_vectors WHERE chunk_id = ? AND COALESCE(content_hash, '') <> ?",
            (chunk_id, content_hash),
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


def search_retrieval_chunks_fts(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[dict]:
    clean_query = " ".join(
        re.sub(r"[\x00-\x1f\x7f]+", " ", str(query or "")).replace('"', " ").split()
    )
    if not clean_query:
        return []
    terms = clean_query.split()[:32]
    match_query = " OR ".join(f'"{term}"' for term in terms)
    bounded_limit = max(1, min(int(limit or 20), 200))
    rows = conn.execute(
        """
        SELECT chunk_id, bm25(retrieval_chunks_fts, 0.0, 2.0, 1.0, 1.0) AS rank,
               snippet(retrieval_chunks_fts, 2, '[', ']', '…', 18) AS snippet
        FROM retrieval_chunks_fts
        WHERE retrieval_chunks_fts MATCH ?
        ORDER BY rank, chunk_id
        LIMIT ?
        """,
        (match_query, bounded_limit),
    ).fetchall()
    result = [
        {
            "chunk_id": row["chunk_id"] if isinstance(row, sqlite3.Row) else row[0],
            "rank": row["rank"] if isinstance(row, sqlite3.Row) else row[1],
            "snippet": row["snippet"] if isinstance(row, sqlite3.Row) else row[2],
        }
        for row in rows
    ]
    if result:
        return result
    short_terms = list(dict.fromkeys(term for term in terms if len(term) < 3))
    if not short_terms:
        return []
    predicates = " OR ".join("(text LIKE ? OR metadata_json LIKE ?)" for _ in short_terms)
    params: list[Any] = []
    for term in short_terms:
        pattern = f"%{term}%"
        params.extend((pattern, pattern))
    params.append(bounded_limit)
    fallback_rows = conn.execute(
        f"""
        SELECT chunk_id, 0.0 AS rank, substr(text, 1, 180) AS snippet
        FROM retrieval_chunks
        WHERE deleted_at IS NULL AND ({predicates})
        ORDER BY chunk_id
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    return [
        {
            "chunk_id": row["chunk_id"] if isinstance(row, sqlite3.Row) else row[0],
            "rank": row["rank"] if isinstance(row, sqlite3.Row) else row[1],
            "snippet": row["snippet"] if isinstance(row, sqlite3.Row) else row[2],
        }
        for row in fallback_rows
    ]


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
    content_hashes = vector_store.get("content_hashes", {})
    if not isinstance(content_hashes, dict):
        content_hashes = {}
    active_chunk_ids: list[str] = []
    for chunk_id, raw_vector in vectors.items():
        clean_chunk_id = str(chunk_id or "").strip()
        if not clean_chunk_id or not isinstance(raw_vector, list):
            continue
        vector = []
        for value in raw_vector:
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                vector = []
                break
            if not math.isfinite(numeric_value):
                vector = []
                break
            vector.append(numeric_value)
        if not vector:
            continue
        row = conn.execute(
            """
            SELECT chunk.chunk_id, chunk.content_hash
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
        chunk_content_hash = str(row["content_hash"] or "") if isinstance(row, sqlite3.Row) else str(row[1] or "")
        expected_content_hash = str(content_hashes.get(clean_chunk_id) or "")
        if not chunk_content_hash or expected_content_hash != chunk_content_hash:
            continue
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
                chunk_content_hash,
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
    build_mode = str(vector_store.get("build_mode") or "full")
    if build_mode not in {"full", "incremental"}:
        build_mode = "full"
    conn.execute(
        """
        INSERT INTO retrieval_vector_store_meta (
            embedding_model, build_mode, reused_vector_count,
            generated_vector_count, removed_vector_count, updated_at
        )
        VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ON CONFLICT(embedding_model) DO UPDATE SET
            build_mode = excluded.build_mode,
            reused_vector_count = excluded.reused_vector_count,
            generated_vector_count = excluded.generated_vector_count,
            removed_vector_count = excluded.removed_vector_count,
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        """,
        (
            embedding_model,
            build_mode,
            max(int(vector_store.get("reused_vector_count") or 0), 0),
            max(int(vector_store.get("generated_vector_count") or 0), 0),
            max(int(vector_store.get("removed_vector_count") or 0), 0),
        ),
    )
    return vector_store


def load_retrieval_vector_store_payload(conn: sqlite3.Connection, project_name: str, embedding_model: str | None = None) -> dict:
    clean_model = str(embedding_model or "").strip()
    if not clean_model:
        row = conn.execute(
            """
            SELECT embedding_model
            FROM retrieval_vector_store_meta
            ORDER BY updated_at DESC, embedding_model
            LIMIT 1
            """
        ).fetchone()
        if row:
            clean_model = row["embedding_model"] if isinstance(row, sqlite3.Row) else row[0]
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

    meta_row = conn.execute(
        """
        SELECT build_mode, reused_vector_count, generated_vector_count,
               removed_vector_count, updated_at
        FROM retrieval_vector_store_meta
        WHERE embedding_model = ?
        """,
        (clean_model,),
    ).fetchone()
    meta = dict(meta_row) if isinstance(meta_row, sqlite3.Row) else {}
    if meta_row and not meta:
        meta = {
            "build_mode": meta_row[0],
            "reused_vector_count": meta_row[1],
            "generated_vector_count": meta_row[2],
            "removed_vector_count": meta_row[3],
            "updated_at": meta_row[4],
        }

    rows = conn.execute(
        """
        SELECT vector.chunk_id, vector.vector_blob, vector.content_hash, vector.updated_at
        FROM retrieval_vectors AS vector
        JOIN retrieval_chunks AS chunk ON chunk.chunk_id = vector.chunk_id
        JOIN retrieval_documents AS doc ON doc.document_id = chunk.document_id
        WHERE vector.embedding_model = ?
          AND chunk.deleted_at IS NULL
          AND doc.deleted_at IS NULL
          AND vector.content_hash = chunk.content_hash
        ORDER BY vector.chunk_id
        """,
        (clean_model,),
    ).fetchall()
    if not rows and not meta_row:
        return {}

    vectors: dict[str, list[float]] = {}
    content_hashes: dict[str, str] = {}
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
        content_hash = row["content_hash"] if isinstance(row, sqlite3.Row) else row[2]
        if content_hash:
            content_hashes[str(chunk_id)] = str(content_hash)
        updated_values.append(str(row["updated_at"] if isinstance(row, sqlite3.Row) else row[3]))
    return {
        "project_name": project_name,
        "built_at": str(meta.get("updated_at") or max([value for value in updated_values if value] or [""])),
        "embedding_model": clean_model,
        "vectors": vectors,
        "content_hashes": content_hashes,
        "build_mode": str(meta.get("build_mode") or "full"),
        "reused_vector_count": int(meta.get("reused_vector_count") or 0),
        "generated_vector_count": int(meta.get("generated_vector_count") or 0),
        "removed_vector_count": int(meta.get("removed_vector_count") or 0),
    }


def _infer_chunk_index(chunk_id: str) -> int:
    marker = "#chunk"
    if marker not in chunk_id:
        return 1
    try:
        return int(chunk_id.rsplit(marker, 1)[-1])
    except ValueError:
        return 1
