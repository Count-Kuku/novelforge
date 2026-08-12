"""SQLite facade for conversational messages, actions, and config revisions."""

from __future__ import annotations

from novelforge.services import memory as _memory_api


def _open(project_name: str):
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    return _memory_api.open_project_db(_memory_api.project_path(project_name).resolve())


def _assert_session(conn, story_id: str, session_id: str) -> None:
    session = _memory_api.load_creative_session_row(conn, session_id)
    if session is None or str(session.get("story_id") or "") != str(story_id or ""):
        raise ValueError("创作会话不存在或不属于当前故事。")


def save_creative_message(project_name: str, message: dict) -> dict:
    payload = dict(message or {})
    payload["message_id"] = str(
        payload.get("message_id") or f"creative_message_{_memory_api.uuid4().hex}"
    )
    with _open(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _assert_session(conn, payload.get("story_id", ""), payload.get("session_id", ""))
        saved = _memory_api.insert_creative_message_row(conn, payload)
        conn.commit()
    return saved


def list_creative_messages(project_name: str, story_id: str, session_id: str) -> list[dict]:
    with _open(project_name) as conn:
        _assert_session(conn, story_id, session_id)
        return _memory_api.list_creative_message_rows(conn, session_id)


def save_creative_action(project_name: str, action: dict) -> dict:
    payload = dict(action or {})
    payload["action_id"] = str(
        payload.get("action_id") or f"creative_action_{_memory_api.uuid4().hex}"
    )
    with _open(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _assert_session(conn, payload.get("story_id", ""), payload.get("session_id", ""))
        saved = _memory_api.insert_creative_action_row(conn, payload)
        conn.commit()
    return saved


def load_creative_action(project_name: str, action_id: str) -> dict:
    with _open(project_name) as conn:
        return _memory_api.load_creative_action_row(conn, action_id)


def list_creative_actions(project_name: str, story_id: str, session_id: str) -> list[dict]:
    with _open(project_name) as conn:
        _assert_session(conn, story_id, session_id)
        return _memory_api.list_creative_action_rows(conn, session_id)


def update_creative_action(project_name: str, action_id: str, updates: dict) -> dict:
    with _open(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        saved = _memory_api.update_creative_action_row(conn, action_id, updates)
        conn.commit()
    return saved


def save_creative_config_revision(project_name: str, revision: dict) -> dict:
    payload = dict(revision or {})
    payload["revision_id"] = str(
        payload.get("revision_id") or f"creative_config_revision_{_memory_api.uuid4().hex}"
    )
    with _open(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        saved = _memory_api.insert_creative_config_revision_row(conn, payload)
        conn.commit()
    return saved


def load_creative_config_revision(project_name: str, action_id: str) -> dict:
    with _open(project_name) as conn:
        return _memory_api.load_creative_config_revision_row(conn, action_id)


def mark_creative_config_revision_reversed(
    project_name: str, revision_id: str, reversed_by_action_id: str
) -> None:
    with _open(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _memory_api.mark_creative_config_revision_reversed_row(
            conn, revision_id, reversed_by_action_id
        )
        conn.commit()
