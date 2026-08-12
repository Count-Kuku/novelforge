from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_object(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _session_row(row: sqlite3.Row | dict | None) -> dict | None:
    if row is None:
        return None
    payload = dict(row)
    payload["writing_guidance"] = _json_object(payload.pop("writing_guidance_json", "{}"))
    return payload


def _fragment_row(row: sqlite3.Row | dict | None) -> dict | None:
    return dict(row) if row is not None else None


def create_creative_session_row(conn: sqlite3.Connection, session: dict) -> dict:
    payload = dict(session or {})
    session_id = str(payload.get("session_id") or "").strip()
    story_id = str(payload.get("story_id") or "").strip()
    if not session_id or not story_id:
        raise ValueError("Creative session ID and story ID are required.")
    now = _now()
    conn.execute(
        """
        INSERT INTO creative_sessions (
            session_id, story_id, title, status, session_goal,
            writing_guidance_json, target_chapter_no, rolling_summary,
            summary_fragment_id, active_fragment_id, worldline_id,
            auto_extract_mode, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            story_id,
            str(payload.get("title") or ""),
            str(payload.get("status") or "active"),
            str(payload.get("session_goal") or ""),
            json.dumps(payload.get("writing_guidance") or {}, ensure_ascii=False, sort_keys=True),
            payload.get("target_chapter_no"),
            str(payload.get("rolling_summary") or ""),
            payload.get("summary_fragment_id"),
            payload.get("active_fragment_id"),
            str(payload.get("worldline_id") or "main"),
            str(payload.get("auto_extract_mode") or "manual"),
            str(payload.get("created_at") or now),
            str(payload.get("updated_at") or now),
        ),
    )
    return load_creative_session_row(conn, session_id) or {}


def load_creative_session_row(conn: sqlite3.Connection, session_id: str) -> dict | None:
    row = conn.execute(
        """
        SELECT session_id, story_id, title, status, session_goal,
               writing_guidance_json, target_chapter_no, rolling_summary,
               summary_fragment_id, active_fragment_id, worldline_id,
               auto_extract_mode, created_at, updated_at
        FROM creative_sessions
        WHERE session_id = ?
        """,
        (str(session_id or "").strip(),),
    ).fetchone()
    return _session_row(row)


def list_creative_session_rows(
    conn: sqlite3.Connection,
    story_id: str,
    *,
    include_archived: bool = False,
) -> list[dict]:
    if include_archived:
        rows = conn.execute(
            """
            SELECT session_id, story_id, title, status, session_goal,
                   writing_guidance_json, target_chapter_no, rolling_summary,
                   summary_fragment_id, active_fragment_id, worldline_id,
                   auto_extract_mode, created_at, updated_at
            FROM creative_sessions
            WHERE story_id = ?
            ORDER BY updated_at DESC, created_at DESC, session_id
            """,
            (str(story_id or "").strip(),),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT session_id, story_id, title, status, session_goal,
                   writing_guidance_json, target_chapter_no, rolling_summary,
                   summary_fragment_id, active_fragment_id, worldline_id,
                   auto_extract_mode, created_at, updated_at
            FROM creative_sessions
            WHERE story_id = ? AND status <> 'archived'
            ORDER BY updated_at DESC, created_at DESC, session_id
            """,
            (str(story_id or "").strip(),),
        ).fetchall()
    return [value for row in rows if (value := _session_row(row)) is not None]


_SESSION_UPDATE_COLUMNS = {
    "title",
    "status",
    "session_goal",
    "target_chapter_no",
    "rolling_summary",
    "summary_fragment_id",
    "active_fragment_id",
    "worldline_id",
    "auto_extract_mode",
}


def update_creative_session_row(
    conn: sqlite3.Connection,
    session_id: str,
    updates: dict,
) -> dict:
    clean_session_id = str(session_id or "").strip()
    if not clean_session_id:
        raise ValueError("Creative session ID is required.")
    assignments: list[str] = []
    values: list[Any] = []
    for key in _SESSION_UPDATE_COLUMNS:
        if key not in updates:
            continue
        assignments.append(f"{key} = ?")
        values.append(updates[key])
    if "writing_guidance" in updates:
        assignments.append("writing_guidance_json = ?")
        values.append(json.dumps(updates.get("writing_guidance") or {}, ensure_ascii=False, sort_keys=True))
    if not assignments:
        existing = load_creative_session_row(conn, clean_session_id)
        if existing is None:
            raise ValueError("Creative session does not exist.")
        return existing
    assignments.append("updated_at = ?")
    values.append(_now())
    values.append(clean_session_id)
    updated = conn.execute(
        f"UPDATE creative_sessions SET {', '.join(assignments)} WHERE session_id = ?",
        tuple(values),
    ).rowcount
    if updated != 1:
        raise ValueError("Creative session does not exist.")
    return load_creative_session_row(conn, clean_session_id) or {}


def begin_creative_turn_row(conn: sqlite3.Connection, turn: dict) -> dict:
    payload = dict(turn or {})
    turn_id = str(payload.get("turn_id") or "").strip()
    session_id = str(payload.get("session_id") or "").strip()
    user_message = str(payload.get("user_message") or "").strip()
    if not turn_id or not session_id or not user_message:
        raise ValueError("Turn ID, session ID, and user message are required.")
    if load_creative_session_row(conn, session_id) is None:
        raise ValueError("Creative session does not exist.")
    next_index = int(
        conn.execute(
            "SELECT COALESCE(MAX(turn_index), 0) + 1 FROM creative_turns WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
    )
    now = _now()
    conn.execute(
        """
        INSERT INTO creative_turns (
            turn_id, session_id, turn_index, user_message, action_type,
            parent_fragment_id, status, error_text, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'running', '', ?, ?)
        """,
        (
            turn_id,
            session_id,
            next_index,
            user_message,
            str(payload.get("action_type") or "generate"),
            payload.get("parent_fragment_id"),
            now,
            now,
        ),
    )
    conn.execute(
        "UPDATE creative_sessions SET updated_at = ? WHERE session_id = ?",
        (now, session_id),
    )
    return dict(
        conn.execute(
            "SELECT * FROM creative_turns WHERE turn_id = ?",
            (turn_id,),
        ).fetchone()
    )


def fail_creative_turn_row(conn: sqlite3.Connection, turn_id: str, error_text: str) -> dict:
    turn = conn.execute(
        "SELECT session_id FROM creative_turns WHERE turn_id = ?",
        (str(turn_id or "").strip(),),
    ).fetchone()
    if turn is None:
        raise ValueError("Running creative turn does not exist.")
    now = _now()
    updated = conn.execute(
        """
        UPDATE creative_turns
        SET status = 'failed', error_text = ?, updated_at = ?
        WHERE turn_id = ? AND status = 'running'
        """,
        (str(error_text or "")[:4000], now, str(turn_id or "").strip()),
    ).rowcount
    if updated != 1:
        raise ValueError("Running creative turn does not exist.")
    conn.execute(
        "UPDATE creative_sessions SET updated_at = ? WHERE session_id = ?",
        (now, str(turn["session_id"])),
    )
    return dict(conn.execute("SELECT * FROM creative_turns WHERE turn_id = ?", (turn_id,)).fetchone())


def complete_creative_turn_row(
    conn: sqlite3.Connection,
    turn_id: str,
    fragment: dict,
    *,
    accept_fragment_id: str | None = None,
    supersede_fragment_id: str | None = None,
) -> dict:
    turn = conn.execute(
        "SELECT * FROM creative_turns WHERE turn_id = ?",
        (str(turn_id or "").strip(),),
    ).fetchone()
    if turn is None or str(turn["status"]) != "running":
        raise ValueError("Running creative turn does not exist.")
    payload = dict(fragment or {})
    fragment_id = str(payload.get("fragment_id") or "").strip()
    content = str(payload.get("content") or "").strip()
    if not fragment_id or not content:
        raise ValueError("Fragment ID and content are required.")
    session_id = str(turn["session_id"])
    if str(payload.get("session_id") or session_id) != session_id:
        raise ValueError("Creative fragment belongs to a different session.")
    now = _now()
    if accept_fragment_id:
        accepted = conn.execute(
            """
            UPDATE creative_fragments
            SET status = 'accepted', accepted_at = COALESCE(accepted_at, ?)
            WHERE fragment_id = ? AND session_id = ?
              AND status IN ('proposed', 'accepted')
            """,
            (now, accept_fragment_id, session_id),
        ).rowcount
        if accepted != 1:
            raise ValueError("Creative fragment cannot be accepted.")
        accepted_parent = conn.execute(
            """
            SELECT parent_fragment_id
            FROM creative_fragments
            WHERE fragment_id = ? AND session_id = ?
            """,
            (accept_fragment_id, session_id),
        ).fetchone()
        conn.execute(
            """
            UPDATE creative_fragments
            SET status = 'superseded'
            WHERE session_id = ? AND fragment_id <> ?
              AND parent_fragment_id IS ?
              AND status = 'proposed'
            """,
            (
                session_id,
                accept_fragment_id,
                accepted_parent["parent_fragment_id"],
            ),
        )
    if supersede_fragment_id:
        superseded = conn.execute(
            """
            UPDATE creative_fragments
            SET status = 'superseded'
            WHERE fragment_id = ? AND session_id = ? AND status = 'proposed'
            """,
            (supersede_fragment_id, session_id),
        ).rowcount
        if superseded != 1:
            raise ValueError("Creative fragment cannot be superseded.")
    conn.execute(
        """
        INSERT INTO creative_fragments (
            fragment_id, session_id, turn_id, parent_fragment_id, content,
            status, content_hash, word_count, context_snapshot_id,
            extraction_status, created_at, accepted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fragment_id,
            session_id,
            str(turn["turn_id"]),
            payload.get("parent_fragment_id"),
            content,
            str(payload.get("status") or "proposed"),
            str(payload.get("content_hash") or hashlib.sha256(content.encode("utf-8")).hexdigest()),
            int(payload.get("word_count") or len(content)),
            payload.get("context_snapshot_id"),
            str(payload.get("extraction_status") or "not_started"),
            str(payload.get("created_at") or now),
            payload.get("accepted_at"),
        ),
    )
    conn.execute(
        """
        UPDATE creative_turns
        SET status = 'completed', error_text = '', updated_at = ?
        WHERE turn_id = ?
        """,
        (now, turn_id),
    )
    conn.execute(
        """
        UPDATE creative_sessions
        SET active_fragment_id = ?, updated_at = ?
        WHERE session_id = ?
        """,
        (fragment_id, now, session_id),
    )
    return _fragment_row(
        conn.execute(
            "SELECT * FROM creative_fragments WHERE fragment_id = ?",
            (fragment_id,),
        ).fetchone()
    ) or {}


def list_creative_turn_rows(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT turn_id, session_id, turn_index, user_message, action_type,
               parent_fragment_id, status, error_text, created_at, updated_at
        FROM creative_turns
        WHERE session_id = ?
        ORDER BY turn_index, created_at, turn_id
        """,
        (str(session_id or "").strip(),),
    ).fetchall()
    return [dict(row) for row in rows]


def list_creative_fragment_rows(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT fragment_id, session_id, turn_id, parent_fragment_id, content,
               status, content_hash, word_count, context_snapshot_id,
               extraction_status, created_at, accepted_at
        FROM creative_fragments
        WHERE session_id = ?
        ORDER BY created_at, fragment_id
        """,
        (str(session_id or "").strip(),),
    ).fetchall()
    return [dict(row) for row in rows]


def load_creative_fragment_row(conn: sqlite3.Connection, fragment_id: str) -> dict | None:
    row = conn.execute(
        """
        SELECT fragment_id, session_id, turn_id, parent_fragment_id, content,
               status, content_hash, word_count, context_snapshot_id,
               extraction_status, created_at, accepted_at
        FROM creative_fragments
        WHERE fragment_id = ?
        """,
        (str(fragment_id or "").strip(),),
    ).fetchone()
    return dict(row) if row is not None else None


def update_creative_fragment_row(
    conn: sqlite3.Connection,
    fragment_id: str,
    updates: dict,
) -> dict:
    allowed = {"status", "content", "context_snapshot_id", "extraction_status", "accepted_at"}
    assignments: list[str] = []
    values: list[Any] = []
    for key in allowed:
        if key not in updates:
            continue
        assignments.append(f"{key} = ?")
        values.append(updates[key])
    if "content" in updates:
        content = str(updates.get("content") or "")
        assignments.extend(["content_hash = ?", "word_count = ?"])
        values.extend([hashlib.sha256(content.encode("utf-8")).hexdigest(), len(content)])
    if not assignments:
        row = conn.execute(
            "SELECT * FROM creative_fragments WHERE fragment_id = ?",
            (fragment_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Creative fragment does not exist.")
        return dict(row)
    values.append(str(fragment_id or "").strip())
    updated = conn.execute(
        f"UPDATE creative_fragments SET {', '.join(assignments)} WHERE fragment_id = ?",
        tuple(values),
    ).rowcount
    if updated != 1:
        raise ValueError("Creative fragment does not exist.")
    return dict(
        conn.execute(
            "SELECT * FROM creative_fragments WHERE fragment_id = ?",
            (fragment_id,),
        ).fetchone()
    )


def finalize_creative_session_rows(
    conn: sqlite3.Connection,
    session_id: str,
    fragment_ids: list[str],
    chapter_no: int,
) -> dict:
    normalized_ids = list(dict.fromkeys(
        str(fragment_id or "").strip()
        for fragment_id in fragment_ids
        if str(fragment_id or "").strip()
    ))
    if not normalized_ids:
        raise ValueError("At least one creative fragment is required.")
    placeholders = ", ".join("?" for _ in normalized_ids)
    rows = conn.execute(
        f"""
        SELECT fragment_id, status
        FROM creative_fragments
        WHERE session_id = ? AND fragment_id IN ({placeholders})
        """,
        (str(session_id or "").strip(), *normalized_ids),
    ).fetchall()
    statuses = {
        str(row["fragment_id"]): str(row["status"])
        for row in rows
    }
    if set(statuses) != set(normalized_ids):
        raise ValueError("Creative fragment does not belong to the session.")
    if any(status not in {"accepted", "finalized"} for status in statuses.values()):
        raise ValueError("Only accepted creative fragments can be finalized.")
    conn.execute(
        f"""
        UPDATE creative_fragments
        SET status = 'finalized'
        WHERE session_id = ? AND fragment_id IN ({placeholders})
        """,
        (str(session_id or "").strip(), *normalized_ids),
    )
    saved = update_creative_session_row(
        conn,
        session_id,
        {
            "status": "completed",
            "target_chapter_no": int(chapter_no),
        },
    )
    return saved


def delete_creative_session_row(conn: sqlite3.Connection, session_id: str) -> bool:
    source_ids = [
        str(row["source_id"])
        for row in conn.execute(
            """
            SELECT DISTINCT source_id
            FROM creative_attachments
            WHERE session_id = ? AND scope IN ('session', 'turn')
            """,
            (str(session_id or "").strip(),),
        ).fetchall()
    ]
    for source_id in source_ids:
        other_owner = conn.execute(
            """
            SELECT 1 FROM creative_attachments
            WHERE source_id = ? AND session_id <> ?
            LIMIT 1
            """,
            (source_id, str(session_id or "").strip()),
        ).fetchone()
        if other_owner is not None:
            continue
        conn.execute(
            """
            UPDATE source_segments
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE source_id = ? AND deleted_at IS NULL
            """,
            (source_id,),
        )
        conn.execute(
            """
            UPDATE source_documents
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE source_id = ? AND deleted_at IS NULL
            """,
            (source_id,),
        )
    return conn.execute(
        "DELETE FROM creative_sessions WHERE session_id = ?",
        (str(session_id or "").strip(),),
    ).rowcount == 1


def _copy_id(prefix: str, target_story_id: str, source_id: str) -> str:
    digest = hashlib.sha256(f"{target_story_id}:{source_id}".encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def clone_creative_session_rows(
    conn: sqlite3.Connection,
    source_story_id: str,
    target_story_id: str,
) -> dict:
    sessions = conn.execute(
        "SELECT * FROM creative_sessions WHERE story_id = ? ORDER BY created_at, session_id",
        (source_story_id,),
    ).fetchall()
    session_map = {
        str(row["session_id"]): _copy_id("session", target_story_id, str(row["session_id"]))
        for row in sessions
    }
    turn_rows = conn.execute(
        """
        SELECT turn.*
        FROM creative_turns AS turn
        JOIN creative_sessions AS session ON session.session_id = turn.session_id
        WHERE session.story_id = ?
        ORDER BY turn.created_at, turn.turn_id
        """,
        (source_story_id,),
    ).fetchall()
    fragment_rows = conn.execute(
        """
        SELECT fragment.*
        FROM creative_fragments AS fragment
        JOIN creative_sessions AS session ON session.session_id = fragment.session_id
        WHERE session.story_id = ?
        ORDER BY fragment.created_at, fragment.fragment_id
        """,
        (source_story_id,),
    ).fetchall()
    turn_map = {
        str(row["turn_id"]): _copy_id("turn", target_story_id, str(row["turn_id"]))
        for row in turn_rows
    }
    fragment_map = {
        str(row["fragment_id"]): _copy_id("fragment", target_story_id, str(row["fragment_id"]))
        for row in fragment_rows
    }
    attachment_rows = conn.execute(
        """
        SELECT attachment.*
        FROM creative_attachments AS attachment
        LEFT JOIN creative_sessions AS session ON session.session_id = attachment.session_id
        WHERE attachment.scope IN ('story', 'session', 'turn')
          AND (attachment.story_id = ? OR session.story_id = ?)
        ORDER BY attachment.created_at, attachment.attachment_id
        """,
        (source_story_id, source_story_id),
    ).fetchall()
    now = _now()
    for row in sessions:
        conn.execute(
            """
            INSERT INTO creative_sessions (
                session_id, story_id, title, status, session_goal,
                writing_guidance_json, target_chapter_no, rolling_summary,
                summary_fragment_id, active_fragment_id, worldline_id,
                auto_extract_mode, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_map[str(row["session_id"])],
                target_story_id,
                str(row["title"] or ""),
                str(row["status"] or "active"),
                str(row["session_goal"] or ""),
                str(row["writing_guidance_json"] or "{}"),
                row["target_chapter_no"],
                str(row["rolling_summary"] or ""),
                fragment_map.get(str(row["summary_fragment_id"] or "")),
                fragment_map.get(str(row["active_fragment_id"] or "")),
                str(row["worldline_id"] or "main"),
                str(row["auto_extract_mode"] or "manual"),
                now,
                now,
            ),
        )
    for row in turn_rows:
        source_turn_status = str(row["status"] or "completed")
        copied_turn_status = "failed" if source_turn_status == "running" else source_turn_status
        copied_error_text = (
            "故事复制时源轮次仍在运行，副本已将该轮次标记为失败。"
            if source_turn_status == "running"
            else str(row["error_text"] or "")
        )
        conn.execute(
            """
            INSERT INTO creative_turns (
                turn_id, session_id, turn_index, user_message, action_type,
                parent_fragment_id, status, error_text, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn_map[str(row["turn_id"])],
                session_map[str(row["session_id"])],
                int(row["turn_index"]),
                str(row["user_message"] or ""),
                str(row["action_type"] or "generate"),
                fragment_map.get(str(row["parent_fragment_id"] or "")),
                copied_turn_status,
                copied_error_text,
                now,
                now,
            ),
        )
    for row in fragment_rows:
        source_extraction_status = str(row["extraction_status"] or "not_started")
        copied_extraction_status = (
            "failed"
            if source_extraction_status == "running"
            else source_extraction_status
        )
        conn.execute(
            """
            INSERT INTO creative_fragments (
                fragment_id, session_id, turn_id, parent_fragment_id, content,
                status, content_hash, word_count, context_snapshot_id,
                extraction_status, created_at, accepted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fragment_map[str(row["fragment_id"])],
                session_map[str(row["session_id"])],
                turn_map[str(row["turn_id"])],
                fragment_map.get(str(row["parent_fragment_id"] or "")),
                str(row["content"] or ""),
                str(row["status"] or "proposed"),
                str(row["content_hash"] or ""),
                int(row["word_count"] or 0),
                row["context_snapshot_id"],
                copied_extraction_status,
                now,
                now if row["accepted_at"] else None,
            ),
        )
    for row in attachment_rows:
        source_attachment_id = str(row["attachment_id"])
        target_attachment_id = _copy_id(
            "attachment", target_story_id, source_attachment_id
        )
        source_session_id = str(row["session_id"] or "")
        source_turn_id = str(row["turn_id"] or "")
        source_id = str(row["source_id"])
        source_row = conn.execute(
            "SELECT story_id FROM source_documents WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        if source_row is not None and str(source_row["story_id"] or "") == source_story_id:
            conn.execute(
                "UPDATE source_documents SET story_id = NULL WHERE source_id = ?",
                (source_id,),
            )
        conn.execute(
            """
            INSERT INTO creative_attachments (
                attachment_id, content_hash, source_id, source_revision_id,
                relative_path, title, filename, media_type, attachment_kind,
                scope, story_id, session_id, turn_id, status,
                ingestion_task_id, remaining_uses, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_attachment_id,
                str(row["content_hash"]),
                source_id,
                row["source_revision_id"],
                str(row["relative_path"]),
                str(row["title"] or ""),
                str(row["filename"] or ""),
                str(row["media_type"] or ""),
                str(row["attachment_kind"] or "file"),
                str(row["scope"] or "story"),
                target_story_id,
                session_map.get(source_session_id),
                turn_map.get(source_turn_id),
                str(row["status"] or "indexed"),
                None,
                row["remaining_uses"],
                str(row["metadata_json"] or "{}"),
                now,
                now,
            ),
        )
    return {
        "session_count": len(sessions),
        "turn_count": len(turn_rows),
        "fragment_count": len(fragment_rows),
        "attachment_count": len(attachment_rows),
        "session_id_map": session_map,
    }
