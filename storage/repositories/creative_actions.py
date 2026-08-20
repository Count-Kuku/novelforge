from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value or "{}"))
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _message(row) -> dict:
    payload = dict(row)
    payload["metadata"] = _json_dict(payload.pop("metadata_json", "{}"))
    return payload


def _action(row) -> dict:
    payload = dict(row)
    for field in ("target", "patch", "plan", "result", "undo"):
        payload[field] = _json_dict(payload.pop(f"{field}_json", "{}"))
    payload["requires_confirmation"] = bool(payload.get("requires_confirmation"))
    return payload


def insert_creative_message_row(conn: sqlite3.Connection, message: dict) -> dict:
    payload = dict(message or {})
    message_id = str(payload.get("message_id") or "").strip()
    if not message_id or not str(payload.get("session_id") or "").strip():
        raise ValueError("Creative message ID and session ID are required.")
    conn.execute(
        """
        INSERT INTO creative_messages (
            message_id, story_id, session_id, role, message_kind,
            content, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(message_id) DO NOTHING
        """,
        (
            message_id,
            str(payload.get("story_id") or ""),
            str(payload.get("session_id") or ""),
            str(payload.get("role") or "user"),
            str(payload.get("message_kind") or "plain"),
            str(payload.get("content") or ""),
            json.dumps(payload.get("metadata") or {}, ensure_ascii=False, sort_keys=True),
            str(payload.get("created_at") or _now()),
        ),
    )
    row = conn.execute(
        "SELECT * FROM creative_messages WHERE message_id = ?", (message_id,)
    ).fetchone()
    return _message(row)


def list_creative_message_rows(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM creative_messages
        WHERE session_id = ? ORDER BY created_at, message_id
        """,
        (str(session_id or ""),),
    ).fetchall()
    return [_message(row) for row in rows]


def insert_creative_action_row(conn: sqlite3.Connection, action: dict) -> dict:
    payload = dict(action or {})
    action_id = str(payload.get("action_id") or "").strip()
    key = str(payload.get("idempotency_key") or "").strip()
    if not action_id or not key:
        raise ValueError("Creative action ID and idempotency key are required.")
    conn.execute(
        """
        INSERT INTO creative_action_runs (
            action_id, story_id, session_id, request_message_id, action_type,
            status, scope, target_json, patch_json, plan_json, result_json,
            undo_json, requires_confirmation, confirmed_at, idempotency_key,
            error_text, created_at, updated_at, finished_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(idempotency_key) DO NOTHING
        """,
        (
            action_id, str(payload.get("story_id") or ""),
            str(payload.get("session_id") or ""),
            str(payload.get("request_message_id") or "") or None,
            str(payload.get("action_type") or "clarify"),
            str(payload.get("status") or "planned"),
            str(payload.get("scope") or "session"),
            json.dumps(payload.get("target") or {}, ensure_ascii=False, sort_keys=True),
            json.dumps(payload.get("patch") or {}, ensure_ascii=False, sort_keys=True),
            json.dumps(payload.get("plan") or {}, ensure_ascii=False, sort_keys=True),
            json.dumps(payload.get("result") or {}, ensure_ascii=False, sort_keys=True),
            json.dumps(payload.get("undo") or {}, ensure_ascii=False, sort_keys=True),
            1 if payload.get("requires_confirmation") else 0,
            payload.get("confirmed_at"), key, str(payload.get("error_text") or ""),
            str(payload.get("created_at") or _now()),
            str(payload.get("updated_at") or _now()), payload.get("finished_at"),
        ),
    )
    row = conn.execute(
        "SELECT * FROM creative_action_runs WHERE idempotency_key = ?", (key,)
    ).fetchone()
    return _action(row)


def load_creative_action_row(conn: sqlite3.Connection, action_id: str) -> dict:
    row = conn.execute(
        "SELECT * FROM creative_action_runs WHERE action_id = ?",
        (str(action_id or ""),),
    ).fetchone()
    return _action(row) if row else {}


def list_creative_action_rows(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM creative_action_runs WHERE session_id = ?
        ORDER BY created_at, action_id
        """,
        (str(session_id or ""),),
    ).fetchall()
    return [_action(row) for row in rows]


def update_creative_action_row(conn: sqlite3.Connection, action_id: str, updates: dict) -> dict:
    allowed = {
        "status", "result", "undo", "confirmed_at", "error_text", "finished_at"
    }
    assignments: list[str] = []
    values: list[Any] = []
    for key, value in dict(updates or {}).items():
        if key not in allowed:
            continue
        if key in {"result", "undo"}:
            assignments.append(f"{key}_json = ?")
            values.append(json.dumps(value or {}, ensure_ascii=False, sort_keys=True))
        else:
            assignments.append(f"{key} = ?")
            values.append(value)
    if not assignments:
        return load_creative_action_row(conn, action_id)
    assignments.append("updated_at = ?")
    values.extend([_now(), str(action_id or "")])
    if conn.execute(
        f"UPDATE creative_action_runs SET {', '.join(assignments)} WHERE action_id = ?",
        tuple(values),
    ).rowcount != 1:
        raise ValueError("Creative action does not exist.")
    return load_creative_action_row(conn, action_id)


def claim_creative_action_row(
    conn: sqlite3.Connection,
    action_id: str,
    story_id: str,
    session_id: str,
    from_statuses: tuple[str, ...],
    updates: dict | None = None,
) -> dict:
    """Atomically claim an action for execution within its story/session."""
    allowed = tuple(str(status) for status in from_statuses if str(status))
    if not allowed:
        raise ValueError("At least one source status is required.")
    assignments = ["status = ?", "updated_at = ?"]
    values: list[Any] = ["running", _now()]
    for key, value in dict(updates or {}).items():
        if key == "confirmed_at":
            assignments.append("confirmed_at = ?")
            values.append(value)
        elif key == "error_text":
            assignments.append("error_text = ?")
            values.append(str(value or ""))
    placeholders = ",".join("?" for _ in allowed)
    values.extend([
        str(action_id or ""), str(story_id or ""), str(session_id or ""),
        *allowed,
    ])
    result = conn.execute(
        f"""
        UPDATE creative_action_runs
        SET {', '.join(assignments)}
        WHERE action_id = ? AND story_id = ? AND session_id = ?
          AND status IN ({placeholders})
        """,
        tuple(values),
    )
    if result.rowcount != 1:
        return {}
    return load_creative_action_row(conn, action_id)


def transition_creative_action_row(
    conn: sqlite3.Connection,
    action_id: str,
    story_id: str,
    session_id: str,
    from_status: str,
    to_status: str,
) -> dict:
    """Atomically transition one scoped action and return its new row."""
    result = conn.execute(
        """
        UPDATE creative_action_runs
        SET status = ?, updated_at = ?
        WHERE action_id = ? AND story_id = ? AND session_id = ? AND status = ?
        """,
        (
            str(to_status or ""), _now(), str(action_id or ""),
            str(story_id or ""), str(session_id or ""), str(from_status or ""),
        ),
    )
    if result.rowcount != 1:
        return {}
    return load_creative_action_row(conn, action_id)


def insert_creative_config_revision_row(conn: sqlite3.Connection, revision: dict) -> dict:
    payload = dict(revision or {})
    conn.execute(
        """
        INSERT INTO creative_config_revisions (
            revision_id, action_id, story_id, session_id, config_scope,
            before_json, after_json, patch_json, reason,
            reversed_by_action_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(payload.get("revision_id") or ""), str(payload.get("action_id") or ""),
            str(payload.get("story_id") or ""),
            str(payload.get("session_id") or "") or None,
            str(payload.get("config_scope") or "session"),
            json.dumps(payload.get("before") or {}, ensure_ascii=False, sort_keys=True),
            json.dumps(payload.get("after") or {}, ensure_ascii=False, sort_keys=True),
            json.dumps(payload.get("patch") or {}, ensure_ascii=False, sort_keys=True),
            str(payload.get("reason") or ""), payload.get("reversed_by_action_id"),
            str(payload.get("created_at") or _now()),
        ),
    )
    return dict(payload)


def load_creative_config_revision_row(conn: sqlite3.Connection, action_id: str) -> dict:
    row = conn.execute(
        """
        SELECT * FROM creative_config_revisions WHERE action_id = ?
        ORDER BY created_at DESC, revision_id DESC LIMIT 1
        """,
        (str(action_id or ""),),
    ).fetchone()
    if not row:
        return {}
    payload = dict(row)
    for field in ("before", "after", "patch"):
        payload[field] = _json_dict(payload.pop(f"{field}_json", "{}"))
    return payload


def mark_creative_config_revision_reversed_row(
    conn: sqlite3.Connection, revision_id: str, reversed_by_action_id: str
) -> None:
    conn.execute(
        """
        UPDATE creative_config_revisions SET reversed_by_action_id = ?
        WHERE revision_id = ? AND reversed_by_action_id IS NULL
        """,
        (str(reversed_by_action_id or ""), str(revision_id or "")),
    )
