"""Implementation slice for the memory facade: creative sessions."""

from __future__ import annotations

from novelforge.services import memory as _memory_api

from novelforge.domain.creation_modes import (
    DEFAULT_CREATION_MODE,
    normalize_creation_mode,
)

def _story_id_slug(name: str) -> str:
    text = str(name or "").strip()
    if not text:
        return "untitled"
    slug = _memory_api.re.sub(r"[^a-zA-Z0-9_-]+", "_", text).strip("_").lower()
    slug = _memory_api.re.sub(r"_+", "_", slug)
    if slug and (_memory_api.re.search(r"[a-zA-Z]", slug) or len(slug) >= 3):
        slug = slug[:48]
        if slug.split(".", 1)[0].upper() in _memory_api.WINDOWS_RESERVED_PATH_NAMES:
            slug = f"story_{slug}"[:48]
        return normalize_story_id(slug)
    digest = _memory_api.hashlib.md5(text.encode("utf-8")).hexdigest()[:10]
    return normalize_story_id(f"story_{digest}")


def normalize_story_id(story_id: str) -> str:
    normalized = str(story_id or "").strip()
    if not normalized:
        raise ValueError("Story ID cannot be empty.")
    if (
        normalized in {".", ".."}
        or ".." in normalized
        or any(char in _memory_api.WINDOWS_INVALID_PATH_CHARS for char in normalized)
        or any(ord(char) < 32 for char in normalized)
        or normalized.endswith(".")
        or normalized.split(".", 1)[0].upper() in _memory_api.WINDOWS_RESERVED_PATH_NAMES
    ):
        raise ValueError("Invalid story ID: path traversal characters not allowed.")
    return normalized


def _creative_session_owner(
    conn,
    session_id: str,
    story_id: str | None = None,
) -> dict:
    session = _memory_api.load_creative_session_row(conn, str(session_id or "").strip())
    if session is None:
        raise ValueError("创作会话不存在。")
    if story_id is not None and str(session.get("story_id") or "") != normalize_story_id(story_id):
        raise ValueError("创作会话不属于当前故事。")
    return session


def _creative_session_has_running_turn(conn, session_id: str) -> bool:
    conn.execute(
        """
        UPDATE creative_turns
        SET status = 'failed',
            error_text = '上一次生成异常中断，已自动释放会话。',
            updated_at = ?
        WHERE session_id = ? AND status = 'running'
          AND julianday(updated_at) < julianday('now', '-1 hour')
        """,
        (
            _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds"),
            str(session_id or "").strip(),
        ),
    )
    return conn.execute(
        """
        SELECT 1
        FROM creative_turns
        WHERE session_id = ? AND status = 'running'
        LIMIT 1
        """,
        (str(session_id or "").strip(),),
    ).fetchone() is not None


def create_creative_session(project_name: str, payload: dict) -> dict:
    raw = dict(payload or {})
    raw["session_id"] = str(raw.get("session_id") or f"session_{_memory_api.uuid4().hex}")
    raw["story_id"] = normalize_story_id(str(raw.get("story_id") or "default"))
    now = _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds")
    raw["created_at"] = str(raw.get("created_at") or now)
    raw["updated_at"] = now
    normalized = _memory_api.CreativeSession.model_validate(raw).model_dump()
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        story_exists = conn.execute(
            "SELECT 1 FROM stories WHERE story_id = ? AND deleted_at IS NULL",
            (normalized["story_id"],),
        ).fetchone()
        if story_exists is None:
            conn.rollback()
            raise ValueError("当前故事不存在。")
        saved = _memory_api.create_creative_session_row(conn, normalized)
        conn.commit()
    return _memory_api.CreativeSession.model_validate(saved).model_dump()


def list_creative_sessions(
    project_name: str,
    story_id: str = "default",
    *,
    include_archived: bool = False,
) -> list[dict]:
    clean_story_id = normalize_story_id(story_id)
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        rows = _memory_api.list_creative_session_rows(
            conn,
            clean_story_id,
            include_archived=include_archived,
        )
    return [_memory_api.CreativeSession.model_validate(row).model_dump() for row in rows]


def list_creative_works(project_name: str, story_id: str = "default") -> list[dict]:
    clean_story_id = normalize_story_id(story_id)
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        return _memory_api.list_creative_work_rows(conn, clean_story_id)


def remove_creative_work(project_name: str, fragment_id: str, *, story_id: str) -> bool:
    """Hide an accepted fragment from Works without erasing its source conversation."""
    clean_fragment_id = str(fragment_id or "").strip()
    if not clean_fragment_id:
        raise ValueError("创作片段 ID 不能为空。")
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        fragment = _memory_api.load_creative_fragment_row(conn, clean_fragment_id)
        if fragment is None:
            conn.rollback()
            return False
        _creative_session_owner(conn, str(fragment["session_id"]), story_id)
        if str(fragment.get("status") or "") not in {"accepted", "finalized"}:
            conn.rollback()
            return False
        _memory_api.update_creative_fragment_row(
            conn,
            clean_fragment_id,
            {"status": "discarded"},
        )
        conn.commit()
    return True


def load_creative_session_bundle(
    project_name: str,
    session_id: str,
    *,
    story_id: str | None = None,
) -> dict | None:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        session = _memory_api.load_creative_session_row(conn, str(session_id or "").strip())
        if session is None:
            return None
        if story_id is not None and str(session.get("story_id") or "") != normalize_story_id(story_id):
            return None
        turns = _memory_api.list_creative_turn_rows(conn, str(session["session_id"]))
        fragments = _memory_api.list_creative_fragment_rows(conn, str(session["session_id"]))
        attachments = _memory_api.list_creative_attachment_rows(
            conn,
            story_id=str(session["story_id"]),
            session_id=str(session["session_id"]),
        )
    return _memory_api.CreativeSessionBundle.model_validate({
        "session": session,
        "turns": turns,
        "fragments": fragments,
        "attachments": attachments,
    }).model_dump()


def update_creative_session(
    project_name: str,
    session_id: str,
    updates: dict,
    *,
    story_id: str | None = None,
) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = _creative_session_owner(conn, session_id, story_id)
        if "active_fragment_id" in updates:
            conn.rollback()
            raise ValueError("当前片段只能通过生成、接受或候选切换流程更新。")
        candidate = {**current, **dict(updates or {})}
        normalized = _memory_api.CreativeSession.model_validate(candidate).model_dump()
        if (
            "status" in updates
            and normalized.get("status") == "archived"
            and _creative_session_has_running_turn(
                conn,
                str(current.get("session_id") or ""),
            )
        ):
            conn.rollback()
            raise ValueError("当前会话仍有生成任务运行，暂时不能归档。")
        for reference_field in {"summary_fragment_id"}:
            if reference_field not in updates:
                continue
            reference_id = str(normalized.get(reference_field) or "")
            if not reference_id:
                continue
            reference = _memory_api.load_creative_fragment_row(conn, reference_id)
            if (
                reference is None
                or str(reference.get("session_id") or "")
                != str(current.get("session_id") or "")
            ):
                conn.rollback()
                raise ValueError("创作会话引用的片段不属于当前会话。")
            if str(reference.get("status") or "") not in {"accepted", "finalized"}:
                conn.rollback()
                raise ValueError("滚动摘要只能标记已接受的片段进度。")
        allowed_updates = {
            key: normalized[key]
            for key in {
                "title",
                "status",
                "session_goal",
                "writing_guidance",
                "target_chapter_no",
                "rolling_summary",
                "summary_fragment_id",
                "worldline_id",
                "auto_extract_mode",
            }
            if key in updates
        }
        saved = _memory_api.update_creative_session_row(conn, session_id, allowed_updates)
        conn.commit()
    return _memory_api.CreativeSession.model_validate(saved).model_dump()


def begin_creative_turn(
    project_name: str,
    session_id: str,
    user_message: str,
    *,
    action_type: str,
    parent_fragment_id: str | None,
    story_id: str,
) -> dict:
    clean_message = str(user_message or "").strip()
    if not clean_message:
        raise ValueError("创作要求不能为空。")
    raw = {
        "turn_id": f"turn_{_memory_api.uuid4().hex}",
        "session_id": str(session_id or "").strip(),
        "turn_index": 1,
        "user_message": clean_message,
        "action_type": action_type,
        "parent_fragment_id": parent_fragment_id,
        "status": "running",
    }
    normalized = _memory_api.CreativeTurn.model_validate(raw).model_dump()
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        session = _creative_session_owner(conn, session_id, story_id)
        if session.get("status") == "archived":
            conn.rollback()
            raise ValueError("已归档的创作会话不能继续生成。")
        if _creative_session_has_running_turn(conn, session_id):
            conn.rollback()
            raise ValueError("当前创作会话已有生成任务正在运行，请等待完成后再试。")
        if parent_fragment_id:
            fragment = _memory_api.load_creative_fragment_row(conn, parent_fragment_id)
            if fragment is None or str(fragment.get("session_id") or "") != session_id:
                conn.rollback()
                raise ValueError("父片段不属于当前创作会话。")
        saved = _memory_api.begin_creative_turn_row(conn, normalized)
        conn.commit()
    return _memory_api.CreativeTurn.model_validate(saved).model_dump()


def complete_creative_turn(
    project_name: str,
    turn_id: str,
    fragment: dict,
    *,
    story_id: str,
    accept_fragment_id: str | None = None,
    supersede_fragment_id: str | None = None,
) -> dict:
    raw = dict(fragment or {})
    raw["fragment_id"] = str(raw.get("fragment_id") or f"fragment_{_memory_api.uuid4().hex}")
    raw["turn_id"] = str(turn_id or "").strip()
    raw["created_at"] = str(
        raw.get("created_at")
        or _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds")
    )
    normalized = _memory_api.CreativeFragment.model_validate(raw).model_dump()
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        turn = conn.execute(
            """
            SELECT session_id, parent_fragment_id
            FROM creative_turns
            WHERE turn_id = ?
            """,
            (str(turn_id or "").strip(),),
        ).fetchone()
        if turn is None:
            conn.rollback()
            raise ValueError("创作轮次不存在。")
        session = _creative_session_owner(conn, str(turn["session_id"]), story_id)
        if str(normalized.get("session_id") or "") != str(session["session_id"]):
            conn.rollback()
            raise ValueError("生成片段不属于当前创作会话。")
        normalized_parent_id = str(normalized.get("parent_fragment_id") or "")
        turn_parent_id = str(turn["parent_fragment_id"] or "")
        if normalized_parent_id != turn_parent_id:
            conn.rollback()
            raise ValueError("生成片段的父节点与创作轮次不一致。")
        current_active_id = str(session.get("active_fragment_id") or "")
        if (
            accept_fragment_id
            and current_active_id != str(accept_fragment_id)
        ) or (
            supersede_fragment_id
            and current_active_id != str(supersede_fragment_id)
        ):
            conn.rollback()
            raise ValueError("生成期间当前候选已变化，本轮结果不会覆盖新的选择。")
        for related_id in [accept_fragment_id, supersede_fragment_id]:
            if not related_id:
                continue
            related = _memory_api.load_creative_fragment_row(conn, related_id)
            if related is None or str(related.get("session_id") or "") != str(session["session_id"]):
                conn.rollback()
                raise ValueError("要更新的片段不属于当前创作会话。")
        saved = _memory_api.complete_creative_turn_row(
            conn,
            turn_id,
            normalized,
            accept_fragment_id=accept_fragment_id,
            supersede_fragment_id=supersede_fragment_id,
        )
        conn.commit()
    return _memory_api.CreativeFragment.model_validate(saved).model_dump()


def fail_creative_turn(
    project_name: str,
    turn_id: str,
    error_text: str,
    *,
    story_id: str,
) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        turn = conn.execute(
            "SELECT session_id FROM creative_turns WHERE turn_id = ?",
            (str(turn_id or "").strip(),),
        ).fetchone()
        if turn is None:
            conn.rollback()
            raise ValueError("创作轮次不存在。")
        _creative_session_owner(conn, str(turn["session_id"]), story_id)
        saved = _memory_api.fail_creative_turn_row(conn, turn_id, error_text)
        conn.commit()
    return _memory_api.CreativeTurn.model_validate(saved).model_dump()


def update_creative_fragment(
    project_name: str,
    fragment_id: str,
    updates: dict,
    *,
    story_id: str,
) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        fragment = _memory_api.load_creative_fragment_row(conn, fragment_id)
        if fragment is None:
            conn.rollback()
            raise ValueError("创作片段不存在。")
        _creative_session_owner(conn, str(fragment["session_id"]), story_id)
        if (
            "status" in updates
            and str(updates.get("status") or "")
            != str(fragment.get("status") or "")
        ):
            conn.rollback()
            raise ValueError("片段状态只能通过接受、重写或章节汇编流程更新。")
        if "accepted_at" in updates:
            conn.rollback()
            raise ValueError("片段接受时间只能由接受流程更新。")
        if (
            "content" in updates
            and str(fragment.get("status") or "") != "proposed"
        ):
            conn.rollback()
            raise ValueError("只有尚未接受的候选片段可以修改正文。")
        candidate = {**fragment, **dict(updates or {})}
        normalized = _memory_api.CreativeFragment.model_validate(candidate).model_dump()
        allowed_updates = {
            key: normalized[key]
            for key in {
                "status",
                "content",
                "context_snapshot_id",
                "extraction_status",
                "accepted_at",
            }
            if key in updates
        }
        saved = _memory_api.update_creative_fragment_row(conn, fragment_id, allowed_updates)
        conn.commit()
    return _memory_api.CreativeFragment.model_validate(saved).model_dump()


def accept_creative_fragment(
    project_name: str,
    session_id: str,
    fragment_id: str,
    *,
    story_id: str,
) -> dict:
    now = _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds")
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        session = _creative_session_owner(conn, session_id, story_id)
        if session.get("status") == "archived":
            conn.rollback()
            raise ValueError("已归档的创作会话不能接受片段。")
        if _creative_session_has_running_turn(conn, session_id):
            conn.rollback()
            raise ValueError("当前会话仍有生成任务运行，暂时不能接受片段。")
        if str(session.get("active_fragment_id") or "") != str(fragment_id or ""):
            conn.rollback()
            raise ValueError("只能接受当前分支的候选片段。")
        fragment = _memory_api.load_creative_fragment_row(conn, fragment_id)
        if fragment is None or str(fragment.get("session_id") or "") != session_id:
            conn.rollback()
            raise ValueError("创作片段不属于当前会话。")
        if str(fragment.get("status") or "") not in {"proposed", "accepted"}:
            conn.rollback()
            raise ValueError("只有当前候选片段可以接受。")
        saved = _memory_api.update_creative_fragment_row(
            conn,
            fragment_id,
            {"status": "accepted", "accepted_at": fragment.get("accepted_at") or now},
        )
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
                fragment_id,
                fragment.get("parent_fragment_id"),
            ),
        )
        _memory_api.update_creative_session_row(
            conn,
            session_id,
            {"active_fragment_id": fragment_id},
        )
        conn.commit()
    return _memory_api.CreativeFragment.model_validate(saved).model_dump()


def select_creative_fragment_variant(
    project_name: str,
    session_id: str,
    fragment_id: str,
    *,
    story_id: str,
) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        session = _creative_session_owner(conn, session_id, story_id)
        if session.get("status") == "archived":
            conn.rollback()
            raise ValueError("已归档的创作会话不能切换候选。")
        if _creative_session_has_running_turn(conn, session_id):
            conn.rollback()
            raise ValueError("当前会话仍有生成任务运行，暂时不能切换候选。")
        current = _memory_api.load_creative_fragment_row(
            conn,
            str(session.get("active_fragment_id") or ""),
        )
        target = _memory_api.load_creative_fragment_row(conn, fragment_id)
        if (
            current is None
            or target is None
            or str(current.get("session_id") or "") != session_id
            or str(target.get("session_id") or "") != session_id
        ):
            conn.rollback()
            raise ValueError("候选片段不属于当前创作会话。")
        if (
            str(current.get("status") or "") != "proposed"
            or str(target.get("status") or "") != "proposed"
        ):
            conn.rollback()
            raise ValueError("只能在尚未接受的同级候选之间切换。")
        if str(current.get("parent_fragment_id") or "") != str(
            target.get("parent_fragment_id") or ""
        ):
            conn.rollback()
            raise ValueError("只能切换当前创作前沿的同级候选。")
        saved = _memory_api.update_creative_session_row(
            conn,
            session_id,
            {"active_fragment_id": fragment_id},
        )
        conn.commit()
    return _memory_api.CreativeSession.model_validate(saved).model_dump()



def select_creative_frontier(
    project_name: str,
    session_id: str,
    fragment_id: str,
    *,
    story_id: str,
) -> dict:
    """把创作前沿切到本会话任意已确认/已定稿片段（真正“分支”起点）。

    与 select_creative_fragment_variant 不同：后者仅允许在同级 proposed 之间切换；
    这里允许从已转正（accepted/finalized）的节点重设前沿，
    之后 continue 即从该节点往后生成，旧分支内容原样保留。
    """
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        session = _creative_session_owner(conn, session_id, story_id)
        if session.get("status") == "archived":
            conn.rollback()
            raise ValueError("已归档的创作会话不能切换创作前沿。")
        if _creative_session_has_running_turn(conn, session_id):
            conn.rollback()
            raise ValueError("当前会话仍有生成任务运行，暂时不能切换创作前沿。")
        target = _memory_api.load_creative_fragment_row(conn, fragment_id)
        if target is None or str(target.get("session_id") or "") != session_id:
            conn.rollback()
            raise ValueError("创作片段不属于当前会话。")
        if str(target.get("status") or "") not in {"accepted", "finalized"}:
            conn.rollback()
            raise ValueError("只能把创作前沿切到已确认（accepted/finalized）的片段。")
        saved = _memory_api.update_creative_session_row(
            conn,
            session_id,
            {"active_fragment_id": fragment_id},
        )
        conn.commit()
    return _memory_api.CreativeSession.model_validate(saved).model_dump()


def finalize_creative_session(
    project_name: str,
    session_id: str,
    fragment_ids: list[str],
    chapter_no: int,
    *,
    story_id: str,
) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        session = _creative_session_owner(conn, session_id, story_id)
        if session.get("status") == "archived":
            conn.rollback()
            raise ValueError("已归档的创作会话不能汇编为章节。")
        if _creative_session_has_running_turn(conn, session_id):
            conn.rollback()
            raise ValueError("当前会话仍有生成任务运行，暂时不能汇编章节。")
        active_chain_ids: set[str] = set()
        current_fragment_id = str(session.get("active_fragment_id") or "")
        while current_fragment_id:
            if current_fragment_id in active_chain_ids:
                conn.rollback()
                raise ValueError("创作片段链包含循环引用。")
            active_chain_ids.add(current_fragment_id)
            current_fragment = _memory_api.load_creative_fragment_row(
                conn,
                current_fragment_id,
            )
            if (
                current_fragment is None
                or str(current_fragment.get("session_id") or "") != session_id
            ):
                conn.rollback()
                raise ValueError("创作会话引用了不存在的片段。")
            current_fragment_id = str(
                current_fragment.get("parent_fragment_id") or ""
            )
        requested_ids = {
            str(fragment_id or "").strip()
            for fragment_id in fragment_ids
            if str(fragment_id or "").strip()
        }
        if not requested_ids.issubset(active_chain_ids):
            conn.rollback()
            raise ValueError("只能汇编当前分支中的已接受片段。")
        saved = _memory_api.finalize_creative_session_rows(
            conn,
            session_id,
            fragment_ids,
            int(chapter_no),
        )
        conn.commit()
    return _memory_api.CreativeSession.model_validate(saved).model_dump()


def delete_creative_session(
    project_name: str,
    session_id: str,
    *,
    story_id: str,
) -> bool:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _creative_session_owner(conn, session_id, story_id)
        if _creative_session_has_running_turn(conn, session_id):
            conn.rollback()
            raise ValueError("当前会话仍有生成任务运行，暂时不能删除。")
        deleted = _memory_api.delete_creative_session_row(conn, session_id)
        conn.commit()
    return deleted
