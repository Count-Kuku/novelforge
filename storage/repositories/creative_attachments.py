from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_object(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _attachment_row(row: sqlite3.Row | dict | None) -> dict | None:
    if row is None:
        return None
    payload = dict(row)
    payload["metadata"] = _json_object(payload.pop("metadata_json", "{}"))
    task_payload = _json_object(payload.pop("task_output_json", "{}"))
    task_status = str(payload.pop("task_runtime_status", "") or "")
    if task_status:
        payload["task_status"] = task_status
        payload["task_message"] = str(task_payload.get("current_message") or "")
        payload["task_progress"] = dict(task_payload.get("progress") or {})
        execution = task_payload.get("execution")
        payload["task_stages"] = dict(execution.get("stages") or {}) if isinstance(execution, dict) else {}
        task_result = task_payload.get("result") if isinstance(task_payload.get("result"), dict) else {}
        payload["task_result"] = task_result
        payload["auto_confirmed_count"] = int(task_result.get("auto_confirmed_count") or 0)
        payload["blocked_count"] = int(task_result.get("blocked_count") or 0)
        payload["retryable"] = task_status in {"failed", "completed_with_errors"}
        payload["status"] = {
            "queued": "processing",
            "running": "processing",
            "paused": "processing",
            "completed": "ready",
            "completed_with_errors": "failed",
            "failed": "failed",
            "cancelled": "indexed",
        }.get(task_status, str(payload.get("status") or "indexed"))
    return payload


def _attachment_promotion_state(conn: sqlite3.Connection, attachment: dict) -> dict:
    """Return confirmed story knowledge eligible for explicit promotion."""

    story_id = str(attachment.get("story_id") or "").strip()
    attachment_id = str(attachment.get("attachment_id") or "").strip()
    source_id = str(attachment.get("source_id") or "").strip()
    if not story_id or not attachment_id:
        return {"can_promote": False, "promotable_knowledge_count": 0}
    rows = conn.execute(
        """
        SELECT ki.*, source.source_type, source.metadata_json AS source_metadata_json,
               segment.segment_id AS live_segment_id,
               segment.source_id AS segment_source_id,
               segment.import_status AS segment_import_status
        FROM knowledge_items AS ki
        LEFT JOIN source_documents AS source ON source.source_id = ki.source_id
        LEFT JOIN source_segments AS segment
          ON segment.segment_id = ki.segment_id
         AND segment.source_id = ki.source_id
         AND segment.deleted_at IS NULL
        WHERE ki.deleted_at IS NULL AND ki.setting_scope = 'story'
          AND ki.story_id = ? AND ki.status IN ('confirmed', 'active')
          AND segment.segment_id IS NOT NULL
          AND COALESCE(segment.import_status, '') NOT IN ('failed', 'error', 'deleted', 'archived')
          AND (
              ki.source_id = ?
              OR json_extract(ki.content_json, '$.creative_attachment_id') = ?
              OR json_extract(source.metadata_json, '$.creative_attachment_id') = ?
          )
        ORDER BY ki.knowledge_id
        """,
        (story_id, source_id, attachment_id, attachment_id),
    ).fetchall()
    try:
        from novelforge.domain.knowledge_promotion import check_knowledge_promotion_eligibility
    except Exception:
        return {"can_promote": False, "promotable_knowledge_count": 0}
    eligible_count = 0
    for row in rows:
        item = _json_object(row["content_json"])
        item.update({
            "id": str(row["knowledge_id"] or ""),
            "knowledge_id": str(row["knowledge_id"] or ""),
            "category": str(row["category"] or ""),
            "setting_scope": str(row["setting_scope"] or ""),
            "story_id": str(row["story_id"] or ""),
            "status": str(row["status"] or ""),
            "source_id": str(row["source_id"] or ""),
            "source_segment_id": str(row["segment_id"] or ""),
            "source_type": str(row["source_type"] or ""),
        })
        source = {
            "source_type": row["source_type"],
            "metadata_json": row["source_metadata_json"],
            "source_id": row["source_id"],
            "segment_id": row["live_segment_id"],
            "segment_source_id": row["segment_source_id"],
            "import_status": row["segment_import_status"],
        }
        if check_knowledge_promotion_eligibility(item, source=source).get("eligible"):
            eligible_count += 1
    return {
        "can_promote": eligible_count > 0,
        "promotable_knowledge_count": eligible_count,
    }


def upsert_creative_attachment_row(conn: sqlite3.Connection, attachment: dict) -> dict:
    payload = dict(attachment or {})
    attachment_id = str(payload.get("attachment_id") or "").strip()
    content_hash = str(payload.get("content_hash") or "").strip()
    source_id = str(payload.get("source_id") or "").strip()
    relative_path = str(payload.get("relative_path") or "").replace("\\", "/").strip()
    scope = str(payload.get("scope") or "story").strip()
    story_id = str(payload.get("story_id") or "").strip() or None
    branch_id = str(payload.get("branch_id") or "").strip() or None
    session_id = str(payload.get("session_id") or "").strip() or None
    turn_id = str(payload.get("turn_id") or "").strip() or None
    if not attachment_id or not content_hash or not source_id or not relative_path:
        raise ValueError("Attachment ID, content hash, source ID, and relative path are required.")
    if scope == "turn" and not session_id:
        raise ValueError("Turn-scoped attachments require a session.")
    if scope == "session" and not session_id:
        raise ValueError("Session-scoped attachments require a session.")
    if scope == "story" and not story_id:
        raise ValueError("Story-scoped attachments require a story.")
    from storage.repositories.branches import default_branch_id, load_branch_for_story
    if scope == "project":
        story_id = None
        branch_id = None
        session_id = None
        turn_id = None
    elif story_id:
        branch_id = branch_id or default_branch_id(story_id)
        branch = load_branch_for_story(conn, story_id, branch_id)
        if branch.get("status") != "active":
            raise ValueError("已归档世界线不能修改资料。")
    identity = conn.execute(
        "SELECT scope, story_id, branch_id, session_id FROM creative_attachments WHERE attachment_id = ?",
        (attachment_id,),
    ).fetchone()
    if identity:
        old_branch = identity["branch_id"] or (
            default_branch_id(identity["story_id"]) if identity["story_id"] else None
        )
        if (identity["scope"], identity["story_id"], old_branch, identity["session_id"]) != (scope, story_id, branch_id, session_id):
            raise ValueError("已有资料不能改变故事或世界线归属。")
    now = _now()
    existing = conn.execute(
        """
        SELECT *
        FROM creative_attachments
        WHERE content_hash = ? AND scope = ?
          AND COALESCE(story_id, '') = COALESCE(?, '')
          AND COALESCE(branch_id, '') = COALESCE(?, '')
          AND COALESCE(session_id, '') = COALESCE(?, '')
          AND COALESCE(turn_id, '') = COALESCE(?, '')
        """,
        (content_hash, scope, story_id, branch_id, session_id, turn_id),
    ).fetchone()
    stable_attachment_id = str(existing["attachment_id"]) if existing else attachment_id
    existing_payload = _attachment_row(existing) if existing else {}
    merged_metadata = {
        **dict((existing_payload or {}).get("metadata") or {}),
        **dict(payload.get("metadata") or {}),
    }
    existing_task_id = str((existing_payload or {}).get("ingestion_task_id") or "").strip()
    ingestion_task_id = str(payload.get("ingestion_task_id") or "").strip() or existing_task_id or None
    incoming_status = str(payload.get("status") or "indexed")
    existing_status = str((existing_payload or {}).get("status") or "")
    status = existing_status if existing_status in {"processing", "ready", "failed"} and incoming_status == "indexed" else incoming_status
    remaining_uses = payload.get("remaining_uses")
    if existing_payload and scope == "turn":
        remaining_uses = existing_payload.get("remaining_uses")
        turn_id = str(existing_payload.get("turn_id") or "").strip() or turn_id
    conn.execute(
        """
        INSERT INTO creative_attachments (
            attachment_id, content_hash, source_id, source_revision_id,
            relative_path, title, filename, media_type, attachment_kind,
            scope, story_id, session_id, turn_id, status, ingestion_task_id,
            branch_id, remaining_uses, metadata_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(attachment_id) DO UPDATE SET
            source_id = excluded.source_id,
            source_revision_id = excluded.source_revision_id,
            relative_path = excluded.relative_path,
            title = excluded.title,
            filename = excluded.filename,
            media_type = excluded.media_type,
            attachment_kind = excluded.attachment_kind,
            status = excluded.status,
            ingestion_task_id = excluded.ingestion_task_id,
            remaining_uses = excluded.remaining_uses,
            metadata_json = excluded.metadata_json,
            updated_at = excluded.updated_at
        """,
        (
            stable_attachment_id,
            content_hash,
            source_id,
            str(payload.get("source_revision_id") or "").strip() or None,
            relative_path,
            str(payload.get("title") or ""),
            str(payload.get("filename") or ""),
            str(payload.get("media_type") or ""),
            str(payload.get("attachment_kind") or "file"),
            scope,
            story_id,
            session_id,
            turn_id,
            status,
            ingestion_task_id,
            branch_id,
            remaining_uses,
            json.dumps(merged_metadata, ensure_ascii=False, sort_keys=True),
            str(payload.get("created_at") or now),
            now,
        ),
    )
    return load_creative_attachment_row(conn, stable_attachment_id) or {}


def load_creative_attachment_row(conn: sqlite3.Connection, attachment_id: str) -> dict | None:
    row = conn.execute(
        """
        SELECT attachment.*, task.status AS task_runtime_status,
               task.output_json AS task_output_json
        FROM creative_attachments AS attachment
        LEFT JOIN workflow_runs AS task ON task.run_id = attachment.ingestion_task_id
        WHERE attachment.attachment_id = ?
        """,
        (str(attachment_id or "").strip(),),
    ).fetchone()
    payload = _attachment_row(row)
    if payload is not None:
        payload.update(_attachment_promotion_state(conn, payload))
    return payload


def list_creative_attachment_rows(
    conn: sqlite3.Connection,
    *,
    story_id: str = "",
    session_id: str = "",
    branch_id: str = "",
    include_project: bool = True,
    include_story: bool = True,
    include_session: bool = True,
) -> list[dict]:
    clean_story_id = str(story_id or "").strip()
    clean_session_id = str(session_id or "").strip()
    clean_branch_id = str(branch_id or "").strip()
    clauses: list[str] = []
    params: list[str] = []
    if include_project:
        clauses.append("attachment.scope = 'project'")
    if include_story and clean_story_id:
        clauses.append("(attachment.scope = 'story' AND attachment.story_id = ?" + (" AND attachment.branch_id = ?)" if clean_branch_id else ")"))
        params.append(clean_story_id)
        if clean_branch_id:
            params.append(clean_branch_id)
    if include_session and clean_session_id:
        clauses.append("(attachment.scope IN ('session', 'turn') AND attachment.session_id = ?" + (" AND attachment.branch_id = ?)" if clean_branch_id else ")"))
        params.append(clean_session_id)
        if clean_branch_id:
            params.append(clean_branch_id)
    if not clauses:
        return []
    rows = conn.execute(
        f"""
        SELECT attachment.*, task.status AS task_runtime_status,
               task.output_json AS task_output_json
        FROM creative_attachments AS attachment
        LEFT JOIN workflow_runs AS task ON task.run_id = attachment.ingestion_task_id
        WHERE {' OR '.join(clauses)}
        ORDER BY attachment.updated_at DESC, attachment.attachment_id
        """,
        tuple(params),
    ).fetchall()
    result = []
    for row in rows:
        item = _attachment_row(row)
        if item is not None:
            item.update(_attachment_promotion_state(conn, item))
            result.append(item)
    return result


def list_all_creative_attachment_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT attachment.*, task.status AS task_runtime_status,
               task.output_json AS task_output_json
        FROM creative_attachments AS attachment
        LEFT JOIN workflow_runs AS task ON task.run_id = attachment.ingestion_task_id
        ORDER BY attachment.updated_at DESC, attachment.attachment_id
        """
    ).fetchall()
    result = []
    for row in rows:
        item = _attachment_row(row)
        if item is not None:
            item.update(_attachment_promotion_state(conn, item))
            result.append(item)
    return result


def update_creative_attachment_row(
    conn: sqlite3.Connection,
    attachment_id: str,
    updates: dict,
) -> dict:
    allowed = {
        "status", "ingestion_task_id", "source_revision_id", "metadata",
        "turn_id", "remaining_uses",
    }
    assignments: list[str] = []
    values: list[Any] = []
    for key in allowed:
        if key not in updates:
            continue
        if key == "metadata":
            assignments.append("metadata_json = ?")
            values.append(json.dumps(updates.get(key) or {}, ensure_ascii=False, sort_keys=True))
        else:
            assignments.append(f"{key} = ?")
            values.append(updates.get(key) or None)
    if not assignments:
        existing = load_creative_attachment_row(conn, attachment_id)
        if existing is None:
            raise ValueError("Creative attachment does not exist.")
        return existing
    assignments.append("updated_at = ?")
    values.extend([_now(), str(attachment_id or "").strip()])
    updated = conn.execute(
        f"UPDATE creative_attachments SET {', '.join(assignments)} WHERE attachment_id = ?",
        tuple(values),
    ).rowcount
    if updated != 1:
        raise ValueError("Creative attachment does not exist.")
    return load_creative_attachment_row(conn, attachment_id) or {}


def claim_turn_creative_attachment_rows(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    turn_id: str,
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM creative_attachments
        WHERE scope = 'turn' AND session_id = ?
          AND remaining_uses > 0 AND turn_id IS NULL
        ORDER BY created_at, attachment_id
        """,
        (str(session_id or "").strip(),),
    ).fetchall()
    if not rows:
        return []
    attachment_ids = [str(row["attachment_id"]) for row in rows]
    placeholders = ",".join("?" for _ in attachment_ids)
    conn.execute(
        f"""
        UPDATE creative_attachments
        SET turn_id = ?, remaining_uses = remaining_uses - 1, updated_at = ?
        WHERE attachment_id IN ({placeholders})
        """,
        (str(turn_id or "").strip(), _now(), *attachment_ids),
    )
    claimed = conn.execute(
        f"""
        SELECT attachment.*, task.status AS task_runtime_status,
               task.output_json AS task_output_json
        FROM creative_attachments AS attachment
        LEFT JOIN workflow_runs AS task ON task.run_id = attachment.ingestion_task_id
        WHERE attachment.attachment_id IN ({placeholders})
        ORDER BY attachment.created_at, attachment.attachment_id
        """,
        tuple(attachment_ids),
    ).fetchall()
    result = []
    for row in claimed:
        item = _attachment_row(row)
        if item is not None:
            item.update(_attachment_promotion_state(conn, item))
            result.append(item)
    return result


def release_turn_creative_attachment_rows(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    turn_id: str,
) -> int:
    updated = conn.execute(
        """
        UPDATE creative_attachments
        SET turn_id = NULL, remaining_uses = 1, updated_at = ?
        WHERE scope = 'turn' AND session_id = ? AND turn_id = ?
          AND remaining_uses = 0
        """,
        (_now(), str(session_id or "").strip(), str(turn_id or "").strip()),
    ).rowcount
    return int(updated or 0)
