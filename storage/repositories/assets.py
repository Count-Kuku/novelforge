from __future__ import annotations

import json
import sqlite3
from typing import Any


def _json_loads(value: Any):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def register_asset_file(
    conn: sqlite3.Connection,
    *,
    asset_id: str,
    asset_type: str,
    logical_key: str,
    relative_path: str,
    story_id: str | None = None,
    title: str = "",
    content_hash: str | None = None,
    mime_type: str | None = None,
    source_kind: str | None = None,
    source_ref: str | None = None,
    metadata: dict | None = None,
) -> dict:
    clean_asset_id = str(asset_id or "").strip()
    if not clean_asset_id:
        raise ValueError("Asset ID cannot be empty.")
    clean_asset_type = str(asset_type or "").strip()
    clean_logical_key = str(logical_key or "").strip()
    clean_relative_path = str(relative_path or "").strip()
    if not clean_asset_type or not clean_logical_key or not clean_relative_path:
        raise ValueError("Asset type, logical key, and relative path are required.")
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
    clean_story_id = str(story_id or "").strip() or None
    existing = conn.execute(
        """
        SELECT asset_id FROM asset_files
        WHERE ((story_id = ?) OR (story_id IS NULL AND ? IS NULL))
          AND asset_type = ?
          AND logical_key = ?
        ORDER BY
          CASE WHEN deleted_at IS NULL THEN 0 ELSE 1 END,
          updated_at DESC,
          created_at DESC
        LIMIT 1
        """,
        (clean_story_id, clean_story_id, clean_asset_type, clean_logical_key),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE asset_files
            SET title = ?,
                relative_path = ?,
                content_hash = ?,
                mime_type = ?,
                source_kind = ?,
                source_ref = ?,
                metadata_json = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                deleted_at = NULL
            WHERE asset_id = ?
            """,
            (
                str(title or ""),
                clean_relative_path,
                content_hash,
                mime_type,
                source_kind,
                source_ref,
                metadata_json,
                existing["asset_id"],
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO asset_files (
                asset_id, story_id, asset_type, logical_key, title, relative_path, content_hash,
                mime_type, source_kind, source_ref, metadata_json, created_at, updated_at, deleted_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                NULL
            )
            """,
            (
                clean_asset_id,
                clean_story_id,
                clean_asset_type,
                clean_logical_key,
                str(title or ""),
                clean_relative_path,
                content_hash,
                mime_type,
                source_kind,
                source_ref,
                metadata_json,
            ),
        )
    row = conn.execute(
        """
        SELECT asset_id, story_id, asset_type, logical_key, title, relative_path, content_hash,
               mime_type, source_kind, source_ref, metadata_json, created_at, updated_at, deleted_at
        FROM asset_files
        WHERE ((story_id = ?) OR (story_id IS NULL AND ? IS NULL))
          AND asset_type = ?
          AND logical_key = ?
        ORDER BY
          CASE WHEN deleted_at IS NULL THEN 0 ELSE 1 END,
          updated_at DESC,
          created_at DESC
        LIMIT 1
        """,
        (clean_story_id, clean_story_id, clean_asset_type, clean_logical_key),
    ).fetchone()
    return dict(row)


def mark_asset_deleted(
    conn: sqlite3.Connection,
    *,
    asset_type: str,
    logical_key: str,
    story_id: str | None = None,
) -> int:
    clean_story_id = str(story_id or "").strip() or None
    clean_asset_type = str(asset_type or "").strip()
    clean_logical_key = str(logical_key or "").strip()
    if not clean_asset_type or not clean_logical_key:
        raise ValueError("Asset type and logical key are required.")
    cursor = conn.execute(
        """
        UPDATE asset_files
        SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE ((story_id = ?) OR (story_id IS NULL AND ? IS NULL))
          AND asset_type = ?
          AND logical_key = ?
          AND deleted_at IS NULL
        """,
        (clean_story_id, clean_story_id, clean_asset_type, clean_logical_key),
    )
    return int(cursor.rowcount or 0)


def upsert_asset_payload(
    conn: sqlite3.Connection,
    *,
    asset_type: str,
    logical_key: str,
    payload,
    story_id: str | None = None,
) -> bool:
    clean_story_id = str(story_id or "").strip() or None
    clean_asset_type = str(asset_type or "").strip()
    clean_logical_key = str(logical_key or "").strip()
    row = conn.execute(
        """
        SELECT asset_id
        FROM asset_files
        WHERE ((story_id = ?) OR (story_id IS NULL AND ? IS NULL))
          AND asset_type = ?
          AND logical_key = ?
          AND deleted_at IS NULL
        """,
        (clean_story_id, clean_story_id, clean_asset_type, clean_logical_key),
    ).fetchone()
    if not row:
        return False
    asset_id = row["asset_id"] if isinstance(row, sqlite3.Row) else row[0]
    conn.execute(
        """
        INSERT INTO asset_payloads (asset_id, payload_json, created_at, updated_at)
        VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ON CONFLICT(asset_id) DO UPDATE SET
            payload_json = excluded.payload_json,
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        """,
        (asset_id, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
    )
    return True


def load_asset_payload(
    conn: sqlite3.Connection,
    *,
    asset_type: str,
    logical_key: str,
    story_id: str | None = None,
):
    clean_story_id = str(story_id or "").strip() or None
    clean_asset_type = str(asset_type or "").strip()
    clean_logical_key = str(logical_key or "").strip()
    row = conn.execute(
        """
        SELECT payload.payload_json
        FROM asset_files AS asset
        JOIN asset_payloads AS payload ON payload.asset_id = asset.asset_id
        WHERE ((asset.story_id = ?) OR (asset.story_id IS NULL AND ? IS NULL))
          AND asset.asset_type = ?
          AND asset.logical_key = ?
          AND asset.deleted_at IS NULL
        """,
        (clean_story_id, clean_story_id, clean_asset_type, clean_logical_key),
    ).fetchone()
    if not row:
        return None
    payload_json = row["payload_json"] if isinstance(row, sqlite3.Row) else row[0]
    return _json_loads(payload_json)


def list_asset_file_rows(
    conn: sqlite3.Connection,
    *,
    asset_type: str | None = None,
    story_id: str | None = None,
    include_deleted: bool = False,
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    clean_story_id = str(story_id or "").strip()
    if clean_story_id:
        clauses.append("story_id = ?")
        params.append(clean_story_id)
    clean_asset_type = str(asset_type or "").strip()
    if clean_asset_type:
        clauses.append("asset_type = ?")
        params.append(clean_asset_type)
    if not include_deleted:
        clauses.append("deleted_at IS NULL")
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT asset_id, story_id, asset_type, logical_key, title, relative_path, content_hash,
               mime_type, source_kind, source_ref, metadata_json, created_at, updated_at, deleted_at
        FROM asset_files
        {where_sql}
        ORDER BY updated_at DESC, created_at DESC, asset_type, logical_key
        """,
        tuple(params),
    ).fetchall()
    result: list[dict] = []
    for row in rows:
        item = dict(row)
        metadata = _json_loads(item.get("metadata_json"))
        item["metadata"] = metadata if isinstance(metadata, dict) else {}
        result.append(item)
    return result


def list_asset_payload_rows(
    conn: sqlite3.Connection,
    *,
    asset_type: str | None = None,
    story_id: str | None = None,
    include_deleted: bool = False,
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    clean_story_id = str(story_id or "").strip()
    if clean_story_id:
        clauses.append("asset.story_id = ?")
        params.append(clean_story_id)
    clean_asset_type = str(asset_type or "").strip()
    if clean_asset_type:
        clauses.append("asset.asset_type = ?")
        params.append(clean_asset_type)
    if not include_deleted:
        clauses.append("asset.deleted_at IS NULL")
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT asset.asset_id, asset.story_id, asset.asset_type, asset.logical_key,
               asset.title, asset.relative_path, asset.content_hash, asset.mime_type,
               asset.source_kind, asset.source_ref, asset.metadata_json,
               asset.created_at, asset.updated_at, asset.deleted_at,
               payload.payload_json
        FROM asset_files AS asset
        JOIN asset_payloads AS payload ON payload.asset_id = asset.asset_id
        {where_sql}
        ORDER BY asset.updated_at DESC, asset.created_at DESC, asset.asset_type, asset.logical_key
        """,
        tuple(params),
    ).fetchall()
    result: list[dict] = []
    for row in rows:
        item = dict(row)
        metadata = _json_loads(item.get("metadata_json"))
        payload = _json_loads(item.get("payload_json"))
        item["metadata"] = metadata if isinstance(metadata, dict) else {}
        item["payload"] = payload
        result.append(item)
    return result
