from __future__ import annotations

import json
import sqlite3
from hashlib import sha256
from pathlib import Path
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


def _source_id_from_path(relative_path: str) -> str:
    digest = sha256(str(relative_path or "").encode("utf-8")).hexdigest()[:24]
    return f"source_file_{digest}"


def _segment_id_from_path(relative_path: str) -> str:
    digest = sha256(str(relative_path or "").encode("utf-8")).hexdigest()[:24]
    return f"segment_file_{digest}"


def _story_id_or_none(conn: sqlite3.Connection, story_id: Any) -> str | None:
    clean_story_id = str(story_id or "").strip()
    if not clean_story_id:
        return None
    row = conn.execute(
        "SELECT story_id FROM stories WHERE story_id = ? AND deleted_at IS NULL",
        (clean_story_id,),
    ).fetchone()
    return clean_story_id if row else None


def _sync_source_revision(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    content_hash: str | None,
    metadata: dict | None = None,
    filename: str = "",
    char_count: int = 0,
) -> str:
    payload = dict(metadata or {})
    clean_hash = str(content_hash or "").strip()
    if not clean_hash:
        clean_hash = sha256(_json_dumps(payload).encode("utf-8")).hexdigest()
    revision_seed = f"{source_id}|{clean_hash}"
    revision_id = f"source_revision_{sha256(revision_seed.encode('utf-8')).hexdigest()[:24]}"
    current = conn.execute(
        "SELECT active_revision_id FROM source_documents WHERE source_id = ?",
        (source_id,),
    ).fetchone()
    previous_revision_id = (
        str(current["active_revision_id"] or "")
        if isinstance(current, sqlite3.Row) and current
        else str(current[0] or "") if current else ""
    )
    parser = payload.get("parser_metadata") if isinstance(payload.get("parser_metadata"), dict) else {}
    documents = parser.get("documents", []) if isinstance(parser, dict) else []
    first_document = documents[0] if isinstance(documents, list) and documents and isinstance(documents[0], dict) else {}
    conn.execute(
        """
        INSERT INTO source_revisions (
            revision_id, source_id, previous_revision_id, content_hash,
            parser_name, parser_version, media_type, filename, char_count,
            metadata_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ON CONFLICT(source_id, content_hash) DO NOTHING
        """,
        (
            revision_id,
            source_id,
            previous_revision_id or None,
            clean_hash,
            str(first_document.get("parser_name") or payload.get("parser_name") or ""),
            str(first_document.get("parser_version") or payload.get("parser_version") or ""),
            str(first_document.get("media_type") or payload.get("media_type") or ""),
            str(filename or first_document.get("filename") or ""),
            max(int(char_count or 0), 0),
            _json_dumps(payload),
        ),
    )
    conn.execute(
        "UPDATE source_documents SET active_revision_id = ? WHERE source_id = ?",
        (revision_id, source_id),
    )
    return revision_id


def sync_retrieval_source_file(
    conn: sqlite3.Connection,
    *,
    relative_path: str,
    title: str,
    content_hash: str | None = None,
    source_type: str = "reference",
    authority: float = 0.0,
    metadata: dict | None = None,
) -> dict:
    clean_relative_path = str(relative_path or "").replace("\\", "/").strip()
    if not clean_relative_path:
        raise ValueError("Retrieval source relative path cannot be empty.")
    source_id = _source_id_from_path(clean_relative_path)
    segment_id = _segment_id_from_path(clean_relative_path)
    payload = {
        "relative_path": clean_relative_path,
        **(metadata or {}),
    }
    conn.execute(
        """
        INSERT INTO source_documents (
            source_id, story_id, title, source_type, authority, canon_status,
            original_asset_id, content_hash, metadata_json, created_at, updated_at, deleted_at
        )
        VALUES (?, NULL, ?, ?, ?, NULL, NULL, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL)
        ON CONFLICT(source_id) DO UPDATE SET
            title = excluded.title,
            source_type = excluded.source_type,
            authority = excluded.authority,
            content_hash = excluded.content_hash,
            metadata_json = excluded.metadata_json,
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            deleted_at = NULL
        """,
        (
            source_id,
            str(title or clean_relative_path),
            str(source_type or "reference"),
            float(authority or 0.0),
            content_hash,
            _json_dumps(payload),
        ),
    )
    revision_id = _sync_source_revision(
        conn,
        source_id=source_id,
        content_hash=content_hash,
        metadata=payload,
        filename=Path(clean_relative_path).name,
        char_count=int(payload.get("char_count") or 0),
    )
    payload["source_revision_id"] = revision_id
    conn.execute(
        """
        INSERT INTO source_segments (
            segment_id, source_id, segment_index, title, asset_id, text_hash,
            summary, import_status, extraction_status, last_extraction_mode,
            metadata_json, source_revision_id, parent_segment_id, start_offset,
            end_offset, heading_path_json, content_kind, created_at, updated_at, deleted_at
        )
        VALUES (?, ?, 1, ?, NULL, ?, '', 'imported', 'pending', NULL, ?, ?, NULL, 0, NULL, '[]', 'document', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL)
        ON CONFLICT(source_id, segment_index) DO UPDATE SET
            segment_id = excluded.segment_id,
            title = excluded.title,
            text_hash = excluded.text_hash,
            metadata_json = excluded.metadata_json,
            source_revision_id = excluded.source_revision_id,
            start_offset = excluded.start_offset,
            end_offset = excluded.end_offset,
            content_kind = excluded.content_kind,
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            deleted_at = NULL
        """,
        (
            segment_id,
            source_id,
            str(title or Path(clean_relative_path).name),
            content_hash,
            _json_dumps(payload),
            revision_id,
        ),
    )
    conn.execute(
        "UPDATE source_documents SET metadata_json = ? WHERE source_id = ?",
        (_json_dumps(payload), source_id),
    )
    return {"source_id": source_id, "segment_id": segment_id, "source_revision_id": revision_id}


def mark_retrieval_source_file_deleted(conn: sqlite3.Connection, *, relative_path: str) -> int:
    source_id = _source_id_from_path(str(relative_path or "").replace("\\", "/").strip())
    conn.execute(
        """
        UPDATE source_segments
        SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE source_id = ? AND deleted_at IS NULL
        """,
        (source_id,),
    )
    cursor = conn.execute(
        """
        UPDATE source_documents
        SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE source_id = ? AND deleted_at IS NULL
        """,
        (source_id,),
    )
    return int(cursor.rowcount or 0)


def list_retrieval_source_file_rows(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT metadata_json
        FROM source_documents
        WHERE source_id LIKE 'source_file_%' AND deleted_at IS NULL
        ORDER BY lower(title), source_id
        """
    ).fetchall()
    paths: list[str] = []
    for row in rows:
        payload = _json_loads_dict(row["metadata_json"] if isinstance(row, sqlite3.Row) else row[0])
        relative_path = str(payload.get("relative_path") or "").replace("\\", "/").strip()
        if relative_path:
            paths.append(relative_path)
    return sorted(set(paths), key=str.lower)


def sync_long_reference_batch(conn: sqlite3.Connection, batch: dict) -> dict:
    payload = dict(batch or {})
    batch_id = str(payload.get("batch_id") or "").strip()
    if not batch_id:
        raise ValueError("Long reference batch ID cannot be empty.")
    source_id = f"long_batch_{batch_id}"
    segments = payload.get("segments", [])
    if not isinstance(segments, list):
        segments = []
    story_id = _story_id_or_none(conn, payload.get("story_id"))
    exact_content_hash = str(payload.get("source_content_hash") or "").strip()
    if not exact_content_hash and segments:
        source_snapshot = [
            {
                "index": int(item.get("index") or index),
                "content": str(item.get("content") or ""),
            }
            for index, item in enumerate(segments, start=1)
            if isinstance(item, dict)
        ]
        exact_content_hash = sha256(_json_dumps(source_snapshot).encode("utf-8")).hexdigest()
    content_hash = exact_content_hash or str(payload.get("content_fingerprint") or "").strip() or None
    if content_hash:
        payload["source_content_hash"] = content_hash
    conn.execute(
        """
        INSERT INTO source_documents (
            source_id, story_id, title, source_type, authority, canon_status,
            original_asset_id, content_hash, metadata_json, created_at, updated_at, deleted_at
        )
        VALUES (?, ?, ?, ?, 0, ?, NULL, ?, ?, ?, ?, NULL)
        ON CONFLICT(source_id) DO UPDATE SET
            story_id = excluded.story_id,
            title = excluded.title,
            source_type = excluded.source_type,
            canon_status = excluded.canon_status,
            content_hash = excluded.content_hash,
            metadata_json = excluded.metadata_json,
            updated_at = excluded.updated_at,
            deleted_at = NULL
        """,
        (
            source_id,
            story_id,
            str(payload.get("title") or "长篇资料批次"),
            str(payload.get("source_type") or "long_form_source"),
            str(payload.get("canon_status") or payload.get("scope") or "").strip() or None,
            content_hash,
            _json_dumps(payload),
            str(payload.get("created_at") or ""),
            str(payload.get("updated_at") or payload.get("created_at") or ""),
        ),
    )
    revision_metadata = {
        key: payload.get(key)
        for key in (
            "title", "scope", "source_type", "source_origin", "source_file_name",
            "source_files", "parser_metadata", "content_char_count",
        )
        if payload.get(key) not in (None, "", [], {})
    }
    revision_id = _sync_source_revision(
        conn,
        source_id=source_id,
        content_hash=content_hash,
        metadata=revision_metadata,
        filename=str(payload.get("source_file_name") or ""),
        char_count=int(payload.get("content_char_count") or 0),
    )
    payload["source_id"] = source_id
    payload["source_revision_id"] = revision_id
    conn.execute(
        "UPDATE source_documents SET metadata_json = ? WHERE source_id = ?",
        (_json_dumps(payload), source_id),
    )
    active_segment_ids: list[str] = []
    for index, raw_segment in enumerate(segments, start=1):
        if not isinstance(raw_segment, dict):
            continue
        segment_id = str(raw_segment.get("segment_id") or f"{batch_id}_seg_{index:04d}").strip()
        active_segment_ids.append(segment_id)
        content = str(raw_segment.get("content") or "")
        text_hash = sha256(content.encode("utf-8")).hexdigest() if content else None
        conn.execute(
            """
            INSERT INTO source_segments (
                segment_id, source_id, segment_index, title, asset_id, text_hash,
                summary, import_status, extraction_status, last_extraction_mode,
                metadata_json, source_revision_id, parent_segment_id, start_offset,
                end_offset, heading_path_json, content_kind, created_at, updated_at, deleted_at
            )
            VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL)
            ON CONFLICT(source_id, segment_index) DO UPDATE SET
                segment_id = excluded.segment_id,
                title = excluded.title,
                text_hash = excluded.text_hash,
                summary = excluded.summary,
                import_status = excluded.import_status,
                extraction_status = excluded.extraction_status,
                last_extraction_mode = excluded.last_extraction_mode,
                metadata_json = excluded.metadata_json,
                source_revision_id = excluded.source_revision_id,
                parent_segment_id = excluded.parent_segment_id,
                start_offset = excluded.start_offset,
                end_offset = excluded.end_offset,
                heading_path_json = excluded.heading_path_json,
                content_kind = excluded.content_kind,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                deleted_at = NULL
            """,
            (
                segment_id,
                source_id,
                int(raw_segment.get("index") or index),
                str(raw_segment.get("title") or f"片段 {index:03d}"),
                text_hash,
                str(raw_segment.get("summary") or "")[:1000],
                str(raw_segment.get("import_status") or "pending"),
                str(raw_segment.get("extract_status") or raw_segment.get("extraction_status") or "pending"),
                str(raw_segment.get("last_extraction_mode") or payload.get("last_extraction_mode") or "").strip() or None,
                _json_dumps(raw_segment),
                revision_id,
                str(raw_segment.get("parent_segment_id") or "").strip() or None,
                raw_segment.get("start_offset"),
                raw_segment.get("end_offset"),
                _json_dumps(raw_segment.get("heading_path", [])),
                str(raw_segment.get("content_kind") or "section"),
            ),
        )
    if active_segment_ids:
        placeholders = ",".join("?" for _ in active_segment_ids)
        conn.execute(
            f"""
            UPDATE source_segments
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE source_id = ? AND segment_id NOT IN ({placeholders}) AND deleted_at IS NULL
            """,
            (source_id, *active_segment_ids),
        )
    else:
        conn.execute(
            """
            UPDATE source_segments
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE source_id = ? AND deleted_at IS NULL
            """,
            (source_id,),
        )
    return payload


def list_source_revision_rows(conn: sqlite3.Connection, source_id: str = "") -> list[dict]:
    clean_source_id = str(source_id or "").strip()
    if clean_source_id:
        rows = conn.execute(
            """
            SELECT * FROM source_revisions
            WHERE source_id = ?
            ORDER BY created_at DESC, revision_id DESC
            """,
            (clean_source_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM source_revisions ORDER BY created_at DESC, revision_id DESC"
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row) if isinstance(row, sqlite3.Row) else {}
        item["metadata"] = _json_loads_dict(item.pop("metadata_json", "{}"))
        result.append(item)
    return result


def load_long_reference_batch_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT source_id, title, metadata_json, updated_at
        FROM source_documents
        WHERE source_id LIKE 'long_batch_%' AND deleted_at IS NULL
        ORDER BY updated_at DESC, source_id
        """
    ).fetchall()
    batches: list[dict] = []
    for row in rows:
        payload = _json_loads_dict(row["metadata_json"] if isinstance(row, sqlite3.Row) else row[2])
        source_id = row["source_id"] if isinstance(row, sqlite3.Row) else row[0]
        batch_id = str(source_id).removeprefix("long_batch_")
        payload.setdefault("batch_id", batch_id)
        payload.setdefault("title", row["title"] if isinstance(row, sqlite3.Row) else row[1])
        payload.setdefault("updated_at", row["updated_at"] if isinstance(row, sqlite3.Row) else row[3])
        batches.append(payload)
    return batches


def load_long_reference_batch_row(conn: sqlite3.Connection, batch_id: str) -> dict:
    source_id = f"long_batch_{str(batch_id or '').strip()}"
    row = conn.execute(
        """
        SELECT source_id, title, metadata_json, updated_at
        FROM source_documents
        WHERE source_id = ? AND deleted_at IS NULL
        """,
        (source_id,),
    ).fetchone()
    if not row:
        return {}
    payload = _json_loads_dict(row["metadata_json"] if isinstance(row, sqlite3.Row) else row[2])
    payload.setdefault("batch_id", str(batch_id or "").strip())
    payload.setdefault("title", row["title"] if isinstance(row, sqlite3.Row) else row[1])
    payload.setdefault("updated_at", row["updated_at"] if isinstance(row, sqlite3.Row) else row[3])
    return payload


def mark_long_reference_batch_deleted(conn: sqlite3.Connection, *, batch_id: str) -> int:
    source_id = f"long_batch_{str(batch_id or '').strip()}"
    conn.execute(
        """
        UPDATE source_segments
        SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE source_id = ? AND deleted_at IS NULL
        """,
        (source_id,),
    )
    cursor = conn.execute(
        """
        UPDATE source_documents
        SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE source_id = ? AND deleted_at IS NULL
        """,
        (source_id,),
    )
    return int(cursor.rowcount or 0)
