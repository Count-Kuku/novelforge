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
    conn.execute(
        """
        INSERT INTO source_segments (
            segment_id, source_id, segment_index, title, asset_id, text_hash,
            summary, import_status, extraction_status, last_extraction_mode,
            metadata_json, created_at, updated_at, deleted_at
        )
        VALUES (?, ?, 1, ?, NULL, ?, '', 'imported', 'pending', NULL, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL)
        ON CONFLICT(source_id, segment_index) DO UPDATE SET
            segment_id = excluded.segment_id,
            title = excluded.title,
            text_hash = excluded.text_hash,
            metadata_json = excluded.metadata_json,
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            deleted_at = NULL
        """,
        (
            segment_id,
            source_id,
            str(title or Path(clean_relative_path).name),
            content_hash,
            _json_dumps(payload),
        ),
    )
    return {"source_id": source_id, "segment_id": segment_id}


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
    content_hash = str(payload.get("content_fingerprint") or "").strip() or None
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
                metadata_json, created_at, updated_at, deleted_at
            )
            VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL)
            ON CONFLICT(source_id, segment_index) DO UPDATE SET
                segment_id = excluded.segment_id,
                title = excluded.title,
                text_hash = excluded.text_hash,
                summary = excluded.summary,
                import_status = excluded.import_status,
                extraction_status = excluded.extraction_status,
                last_extraction_mode = excluded.last_extraction_mode,
                metadata_json = excluded.metadata_json,
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
