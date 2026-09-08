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


def _session_branch(conn, story_id: str, session_id: str, branch_id: str | None = None, *, require_active: bool = True) -> tuple[dict, str]:
    """Resolve the immutable session owner; callers never select a branch from action payload."""
    _assert_session(conn, story_id, session_id)
    story = conn.execute(
        "SELECT status, deleted_at FROM stories WHERE story_id = ?",
        (str(story_id or ""),),
    ).fetchone()
    if story is None or story[1] is not None:
        raise ValueError("当前故事不存在。")
    if require_active and str(story[0] or "active") != "active":
        raise ValueError("已归档的故事不能执行动作。")
    session = _memory_api.load_creative_session_row(conn, session_id) or {}
    if require_active and str(session.get("status") or "active") == "archived":
        raise ValueError("已归档的创作会话不能执行动作。")
    expected = str(session.get("branch_id") or _memory_api.default_branch_id(story_id)).strip()
    requested = str(branch_id or expected).strip()
    if requested != expected:
        raise ValueError("会话已固定到另一条世界线，拒绝跨线动作。")
    branch = conn.execute(
        "SELECT branch_id, story_id, status FROM story_branches WHERE branch_id = ? AND story_id = ?",
        (expected, str(story_id or "")),
    ).fetchone()
    if branch is None:
        raise ValueError("当前世界线不存在或不属于当前故事。")
    if require_active and str(branch[2] or "active") != "active":
        raise ValueError("已归档的世界线只读，不能执行动作。")
    return session, expected


def _assert_branch(project_name: str, story_id: str, branch_id: str, *, require_active: bool = True) -> dict:
    branch = _memory_api.load_story_branch(project_name, story_id, branch_id)
    if require_active and str(branch.get("status") or "active") != "active":
        raise ValueError("已归档的世界线只读，不能执行动作。")
    return branch


def resolve_creative_session_branch(
    project_name: str,
    story_id: str,
    session_id: str,
    branch_id: str | None = None,
    *,
    require_active: bool = True,
) -> str:
    with _open(project_name) as conn:
        _, expected = _session_branch(conn, story_id, session_id, branch_id, require_active=require_active)
    return expected


def validate_creative_action_scope(
    project_name: str,
    action_id: str,
    *,
    story_id: str = "",
    session_id: str = "",
    branch_id: str | None = None,
    require_active: bool = True,
) -> dict:
    """Load an action and bind it to its session's story/branch owner."""
    with _open(project_name) as conn:
        return _validate_creative_action_scope_conn(
            conn, action_id, story_id=story_id, session_id=session_id,
            branch_id=branch_id, require_active=require_active,
        )


def _validate_creative_action_scope_conn(
    conn,
    action_id: str,
    *,
    story_id: str = "",
    session_id: str = "",
    branch_id: str | None = None,
    require_active: bool = True,
) -> dict:
    action = _memory_api.load_creative_action_row(conn, action_id)
    if not action:
        raise ValueError("创作动作不存在。")
    expected_story = str(story_id or action.get("story_id") or "")
    expected_session = str(session_id or action.get("session_id") or "")
    if str(action.get("story_id") or "") != expected_story or str(action.get("session_id") or "") != expected_session:
        raise ValueError("创作动作不属于当前故事或会话。")
    _, expected_branch = _session_branch(
        conn, expected_story, expected_session, branch_id, require_active=require_active,
    )
    stored_branch = str(action.get("branch_id") or "").strip()
    if stored_branch and stored_branch != expected_branch:
        raise ValueError("创作动作属于另一条世界线，拒绝跨线操作。")
    action["branch_id"] = expected_branch
    return action


def save_creative_message(project_name: str, message: dict) -> dict:
    payload = dict(message or {})
    payload["message_id"] = str(
        payload.get("message_id") or f"creative_message_{_memory_api.uuid4().hex}"
    )
    with _open(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _, branch_id = _session_branch(conn, payload.get("story_id", ""), payload.get("session_id", ""), payload.get("branch_id"))
        payload["branch_id"] = branch_id
        saved = _memory_api.insert_creative_message_row(conn, payload)
        saved_branch = str(saved.get("branch_id") or "").strip()
        if (
            str(saved.get("story_id") or "") != str(payload.get("story_id") or "")
            or str(saved.get("session_id") or "") != str(payload.get("session_id") or "")
            or (saved_branch and saved_branch != branch_id)
        ):
            conn.rollback()
            raise ValueError("消息 ID 已被另一故事或会话占用。")
        saved["branch_id"] = branch_id
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
        _, branch_id = _session_branch(conn, payload.get("story_id", ""), payload.get("session_id", ""), payload.get("branch_id"))
        payload["branch_id"] = branch_id
        existing_by_id = _memory_api.load_creative_action_row(conn, payload["action_id"])
        if existing_by_id:
            existing_branch = str(existing_by_id.get("branch_id") or "").strip()
            if (
                str(existing_by_id.get("story_id") or "") != str(payload.get("story_id") or "")
                or str(existing_by_id.get("session_id") or "") != str(payload.get("session_id") or "")
                or (existing_branch and existing_branch != branch_id)
            ):
                conn.rollback()
                raise ValueError("动作 ID 已被另一故事或会话占用。")
            if str(existing_by_id.get("idempotency_key") or "") != str(payload.get("idempotency_key") or ""):
                conn.rollback()
                raise ValueError("动作 ID 已绑定其它幂等请求。")
        saved = _memory_api.insert_creative_action_row(conn, payload)
        saved_branch = str(saved.get("branch_id") or "").strip()
        if (
            str(saved.get("story_id") or "") != str(payload.get("story_id") or "")
            or str(saved.get("session_id") or "") != str(payload.get("session_id") or "")
            or (saved_branch and saved_branch != branch_id)
        ):
            conn.rollback()
            raise ValueError("动作幂等键已被另一故事或会话占用。")
        saved["branch_id"] = branch_id
        conn.commit()
    return saved


def load_creative_action(project_name: str, action_id: str) -> dict:
    with _open(project_name) as conn:
        return _memory_api.load_creative_action_row(conn, action_id)


def list_creative_actions(project_name: str, story_id: str, session_id: str, branch_id: str | None = None) -> list[dict]:
    with _open(project_name) as conn:
        _, expected_branch = _session_branch(conn, story_id, session_id, branch_id, require_active=False)
        rows = _memory_api.list_creative_action_rows(conn, session_id)
    for row in rows:
        stored_branch = str(row.get("branch_id") or "").strip()
        if stored_branch and stored_branch != expected_branch:
            continue
        row["branch_id"] = expected_branch
    return [row for row in rows if str(row.get("branch_id") or "") == expected_branch]


def update_creative_action(project_name: str, action_id: str, updates: dict, *, story_id: str = "", session_id: str = "", branch_id: str | None = None) -> dict:
    with _open(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        stored = _memory_api.load_creative_action_row(conn, action_id)
        if not stored:
            conn.rollback()
            raise ValueError("创作动作不存在。")
        scoped = _validate_creative_action_scope_conn(
            conn, action_id,
            story_id=story_id or str(stored.get("story_id") or ""),
            session_id=session_id or str(stored.get("session_id") or ""),
            branch_id=branch_id,
        )
        updates = {**dict(updates or {}), "branch_id": scoped.get("branch_id")}
        saved = _memory_api.update_creative_action_row(conn, action_id, updates)
        conn.commit()
    return saved


def claim_creative_action(
    project_name: str,
    action_id: str,
    story_id: str,
    session_id: str,
    from_statuses: tuple[str, ...],
    updates: dict | None = None,
    branch_id: str | None = None,
) -> dict:
    with _open(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _, expected_branch = _session_branch(conn, story_id, session_id, branch_id)
        saved = _memory_api.claim_creative_action_row(
            conn, action_id, story_id, session_id, expected_branch, from_statuses, updates,
        )
        conn.commit()
    return saved


def transition_creative_action(
    project_name: str,
    action_id: str,
    story_id: str,
    session_id: str,
    from_status: str,
    to_status: str,
    branch_id: str | None = None,
) -> dict:
    with _open(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _, expected_branch = _session_branch(conn, story_id, session_id, branch_id)
        saved = _memory_api.transition_creative_action_row(
            conn, action_id, story_id, session_id, expected_branch, from_status, to_status,
        )
        conn.commit()
    return saved


def save_creative_config_revision(project_name: str, revision: dict) -> dict:
    payload = dict(revision or {})
    payload["revision_id"] = str(
        payload.get("revision_id") or f"creative_config_revision_{_memory_api.uuid4().hex}"
    )
    with _open(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        action_id = str(payload.get("action_id") or "").strip()
        if action_id:
            action = _memory_api.load_creative_action_row(conn, action_id)
            if not action:
                conn.rollback()
                raise ValueError("配置修订关联的创作动作不存在。")
            payload["story_id"] = str(payload.get("story_id") or action.get("story_id") or "")
            payload["session_id"] = str(payload.get("session_id") or action.get("session_id") or "") or None
            scoped = _validate_creative_action_scope_conn(
                conn, action_id,
                story_id=str(payload.get("story_id") or ""),
                session_id=str(payload.get("session_id") or ""),
                branch_id=payload.get("branch_id"),
            )
            payload["branch_id"] = str(scoped.get("branch_id") or "")
        elif payload.get("session_id"):
            _, expected_branch = _session_branch(
                conn, str(payload.get("story_id") or ""),
                str(payload.get("session_id") or ""), payload.get("branch_id"),
            )
            payload["branch_id"] = expected_branch
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
