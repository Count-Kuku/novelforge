"""Persistence facade for creative-session source attachments."""

from __future__ import annotations

from novelforge.services import memory as _memory_api


def save_creative_attachment(project_name: str, attachment: dict) -> dict:
    raw = dict(attachment or {})
    raw["attachment_id"] = str(
        raw.get("attachment_id") or f"attachment_{_memory_api.uuid4().hex}"
    )
    normalized = _memory_api.CreativeAttachment.model_validate(raw).model_dump()
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(
        _memory_api.project_path(project_name).resolve()
    ) as conn:
        conn.execute("BEGIN IMMEDIATE")
        story_id = str(normalized.get("story_id") or "")
        session_id = str(normalized.get("session_id") or "")
        turn_id = str(normalized.get("turn_id") or "")
        if story_id and conn.execute(
            "SELECT 1 FROM stories WHERE story_id = ? AND deleted_at IS NULL",
            (story_id,),
        ).fetchone() is None:
            conn.rollback()
            raise ValueError("附件对应的故事不存在。")
        if session_id:
            session = _memory_api.load_creative_session_row(conn, session_id)
            if session is None or (story_id and str(session.get("story_id") or "") != story_id):
                conn.rollback()
                raise ValueError("附件对应的创作会话不存在或不属于当前故事。")
        if turn_id:
            turn = conn.execute(
                "SELECT session_id FROM creative_turns WHERE turn_id = ?",
                (turn_id,),
            ).fetchone()
            if turn is None or str(turn["session_id"]) != session_id:
                conn.rollback()
                raise ValueError("附件对应的创作轮次不存在或不属于当前会话。")
        saved = _memory_api.upsert_creative_attachment_row(conn, normalized)
        conn.commit()
    return _memory_api.CreativeAttachment.model_validate(saved).model_dump()


def load_creative_attachment(project_name: str, attachment_id: str) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(
        _memory_api.project_path(project_name).resolve()
    ) as conn:
        row = _memory_api.load_creative_attachment_row(conn, attachment_id)
    return (
        _memory_api.CreativeAttachment.model_validate(row).model_dump()
        if row
        else {}
    )


def list_creative_attachments(
    project_name: str,
    *,
    story_id: str = "",
    session_id: str = "",
) -> list[dict]:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(
        _memory_api.project_path(project_name).resolve()
    ) as conn:
        rows = _memory_api.list_creative_attachment_rows(
            conn,
            story_id=story_id,
            session_id=session_id,
        )
    return [
        _memory_api.CreativeAttachment.model_validate(row).model_dump()
        for row in rows
    ]


def list_all_creative_attachments(project_name: str) -> list[dict]:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(
        _memory_api.project_path(project_name).resolve()
    ) as conn:
        rows = _memory_api.list_all_creative_attachment_rows(conn)
    return [
        _memory_api.CreativeAttachment.model_validate(row).model_dump()
        for row in rows
    ]


def update_creative_attachment(
    project_name: str,
    attachment_id: str,
    updates: dict,
) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(
        _memory_api.project_path(project_name).resolve()
    ) as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = _memory_api.load_creative_attachment_row(conn, attachment_id)
        if current is None:
            conn.rollback()
            raise ValueError("创作附件不存在。")
        candidate = {**current, **dict(updates or {})}
        normalized = _memory_api.CreativeAttachment.model_validate(candidate).model_dump()
        saved = _memory_api.update_creative_attachment_row(
            conn,
            attachment_id,
            {
            key: normalized[key]
                for key in {
                    "status", "ingestion_task_id", "source_revision_id", "metadata",
                    "turn_id", "remaining_uses",
                }
                if key in updates
            },
        )
        conn.commit()
    return _memory_api.CreativeAttachment.model_validate(saved).model_dump()


def claim_turn_creative_attachments(
    project_name: str,
    *,
    story_id: str,
    session_id: str,
    turn_id: str,
) -> list[dict]:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(
        _memory_api.project_path(project_name).resolve()
    ) as conn:
        conn.execute("BEGIN IMMEDIATE")
        session = _memory_api.load_creative_session_row(conn, session_id)
        if session is None or str(session.get("story_id") or "") != str(story_id):
            conn.rollback()
            raise ValueError("创作会话不存在或不属于当前故事。")
        turn = conn.execute(
            "SELECT session_id FROM creative_turns WHERE turn_id = ?",
            (str(turn_id or "").strip(),),
        ).fetchone()
        if turn is None or str(turn["session_id"]) != str(session_id):
            conn.rollback()
            raise ValueError("创作轮次不存在或不属于当前会话。")
        rows = _memory_api.claim_turn_creative_attachment_rows(
            conn,
            session_id=session_id,
            turn_id=turn_id,
        )
        conn.commit()
    return [
        _memory_api.CreativeAttachment.model_validate(row).model_dump()
        for row in rows
    ]


def release_turn_creative_attachments(
    project_name: str,
    *,
    story_id: str,
    session_id: str,
    turn_id: str,
) -> int:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(
        _memory_api.project_path(project_name).resolve()
    ) as conn:
        conn.execute("BEGIN IMMEDIATE")
        session = _memory_api.load_creative_session_row(conn, session_id)
        if session is None or str(session.get("story_id") or "") != str(story_id):
            conn.rollback()
            raise ValueError("创作会话不存在或不属于当前故事。")
        released = _memory_api.release_turn_creative_attachment_rows(
            conn,
            session_id=session_id,
            turn_id=turn_id,
        )
        conn.commit()
    return released
