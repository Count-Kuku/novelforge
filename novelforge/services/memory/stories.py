"""Implementation slice for the memory facade: stories."""

from __future__ import annotations

from novelforge.services import memory as _memory_api

from novelforge.domain.creation_modes import (
    DEFAULT_CREATION_MODE,
    normalize_creation_mode,
)

# ---------------------------------------------------------------------------
# Story spaces
# ---------------------------------------------------------------------------

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


def _default_story_meta() -> dict:
    return _memory_api.StoryMeta(
        story_id="default",
        name="默认故事",
        description="",
        status="active",
        creation_mode=DEFAULT_CREATION_MODE,
        created_at=_memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds"),
        updated_at=_memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds"),
    ).model_dump()


def _normalize_stories_index_payload(index: dict | None) -> dict:
    normalized = _memory_api.StoriesIndex.model_validate(index or {}).model_dump()
    stories: list[dict] = []
    seen_story_ids: set[str] = set()
    for story in normalized.get("stories", []):
        try:
            clean_story_id = normalize_story_id(story.get("story_id", ""))
        except ValueError as exc:
            _memory_api.logging.getLogger("novelforge.storage").warning(
                "Skipping invalid story ID in stories index: %s", exc
            )
            continue
        if clean_story_id in seen_story_ids:
            _memory_api.logging.getLogger("novelforge.storage").warning(
                "Skipping duplicate story ID in stories index: %s", clean_story_id
            )
            continue
        clean_story = dict(story)
        clean_story["story_id"] = clean_story_id
        clean_story["creation_mode"] = normalize_creation_mode(clean_story.get("creation_mode"))
        stories.append(clean_story)
        seen_story_ids.add(clean_story_id)

    if not stories:
        stories.append(_default_story_meta())
        seen_story_ids.add("default")

    try:
        active_story_id = normalize_story_id(normalized.get("active_story_id", "default"))
    except ValueError:
        active_story_id = "default"
    if active_story_id not in seen_story_ids:
        active_story_id = stories[0]["story_id"]

    return _memory_api.StoriesIndex(stories=stories, active_story_id=active_story_id).model_dump()


def stories_index_path(project_name: str) -> _memory_api.Path:
    return _memory_api.project_path(project_name) / "stories" / "index.json"


def story_path(project_name: str, story_id: str) -> _memory_api.Path:
    stories_root = _memory_api.project_path(project_name) / "stories"
    target = stories_root / normalize_story_id(story_id)
    resolved_root = stories_root.resolve()
    resolved_target = target.resolve()
    if resolved_root != resolved_target and resolved_root not in resolved_target.parents:
        raise ValueError("Invalid story path.")
    return target


def _stories_index_payload_from_rows(
    rows: list[dict],
    *,
    active_story_id: str = "",
) -> dict:
    stories = [
        {
            "story_id": row.get("story_id", ""),
            "name": row.get("name", ""),
            "description": row.get("description", ""),
            "status": row.get("status", "active"),
            "creation_mode": normalize_creation_mode(row.get("creation_mode")),
            "created_at": row.get("created_at", ""),
            "updated_at": row.get("updated_at", ""),
        }
        for row in rows
        if str(row.get("story_id") or "")
    ]
    if not stories:
        stories = [_default_story_meta()]
    story_ids = {str(item.get("story_id") or "") for item in stories}
    resolved_active_id = str(active_story_id or "")
    if resolved_active_id not in story_ids:
        resolved_active_id = next(
            (
                str(row.get("story_id") or "")
                for row in rows
                if row.get("is_active")
                and str(row.get("story_id") or "") in story_ids
            ),
            str(stories[0].get("story_id") or "default"),
        )
    return _normalize_stories_index_payload({
        "stories": stories,
        "active_story_id": resolved_active_id,
    })


def _story_chapter_summaries_path(project_name: str, story_id: str) -> _memory_api.Path:
    return story_path(project_name, story_id) / "chapter_summaries.json"


def _story_memory_overrides_path(project_name: str, story_id: str) -> _memory_api.Path:
    return story_path(project_name, story_id) / "memory_overrides.json"


def _story_rules_overrides_path(project_name: str, story_id: str) -> _memory_api.Path:
    return story_path(project_name, story_id) / "rules_overrides.json"


def _project_prompt_options_path(project_name: str) -> _memory_api.Path:
    return _memory_api.project_path(project_name) / "prompt_options.json"


def _story_prompt_options_path(project_name: str, story_id: str) -> _memory_api.Path:
    return story_path(project_name, story_id) / "prompt_options.json"


def _project_rule_conflict_resolutions_path(project_name: str) -> _memory_api.Path:
    return _memory_api.project_path(project_name) / "rule_conflict_resolutions.json"


def _story_rule_conflict_resolutions_path(project_name: str, story_id: str) -> _memory_api.Path:
    return story_path(project_name, story_id) / "rule_conflict_resolutions.json"


def _load_stories_index_file(project_name: str) -> dict:
    path = stories_index_path(project_name)
    if not path.exists():
        return _normalize_stories_index_payload(None)
    try:
        raw = _memory_api.json.loads(path.read_text(encoding="utf-8"))
        return _normalize_stories_index_payload(raw)
    except Exception:
        return _normalize_stories_index_payload(None)


def load_stories_index(project_name: str) -> dict:
    db_index = _memory_api._load_stories_index_from_db_best_effort(project_name)
    if db_index and db_index.get("stories"):
        return _normalize_stories_index_payload(db_index)

    path = stories_index_path(project_name)
    if path.exists():
        normalized = _load_stories_index_file(project_name)
        if db_index is not None and normalized.get("stories"):
            _memory_api._sync_stories_index_to_db_best_effort(project_name, normalized)
        return normalized

    if not db_index or not db_index.get("stories"):
        idx = _normalize_stories_index_payload({"stories": [_default_story_meta()], "active_story_id": "default"})
        save_stories_index(project_name, idx)
        return idx

    return _normalize_stories_index_payload(db_index)


def save_stories_index(project_name: str, index: dict):
    normalized = _normalize_stories_index_payload(index)
    path = stories_index_path(project_name)
    _memory_api._write_json_mirror(path, normalized)
    _memory_api._sync_stories_index_to_db_best_effort(project_name, normalized)


def get_active_story_id(project_name: str) -> str:
    index = load_stories_index(project_name)
    return str(index.get("active_story_id", "default") or "default")


def set_active_story(project_name: str, story_id: str):
    clean_story_id = normalize_story_id(story_id)
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = [dict(row) for row in _memory_api.list_story_rows(conn)]
        if clean_story_id not in {str(row.get("story_id") or "") for row in rows}:
            conn.rollback()
            raise ValueError(f"故事不存在：{clean_story_id}")
        normalized_index = _stories_index_payload_from_rows(
            rows,
            active_story_id=clean_story_id,
        )
        _memory_api.sync_stories_index(conn, normalized_index)
        conn.commit()
    _memory_api._refresh_project_json_mirror(project_name, stories_index_path(project_name), normalized_index)


def create_story(
    project_name: str,
    name: str,
    description: str = "",
    creation_mode: str = DEFAULT_CREATION_MODE,
) -> dict:
    clean_name = str(name or "").strip()
    clean_creation_mode = normalize_creation_mode(creation_mode)
    if not clean_name:
        raise ValueError("故事名称不能为空。")
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    normalized_index: dict | None = None
    sp: _memory_api.Path | None = None
    meta: _memory_api.StoryMeta | None = None
    try:
        with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            current_rows = [dict(row) for row in _memory_api.list_story_rows(conn)]
            existing_ids = {
                str(row.get("story_id") or "")
                for row in current_rows
            }
            base_story_id = normalize_story_id(_story_id_slug(clean_name))
            story_id = base_story_id
            if story_id in existing_ids:
                counter = 2
                while f"{base_story_id}_{counter}" in existing_ids:
                    counter += 1
                    if counter > 1000:
                        raise RuntimeError(f"无法为故事名 '{clean_name}' 生成唯一 ID：计数器已超上限。")
                story_id = normalize_story_id(f"{base_story_id}_{counter}")

            sp = story_path(project_name, story_id)
            if sp.exists():
                raise FileExistsError(f"故事目录已存在但未登记：{story_id}")
            sp.mkdir(parents=True, exist_ok=False)

            now = _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds")
            meta = _memory_api.StoryMeta(
                story_id=story_id,
                name=clean_name,
                description=description,
                status="active",
                creation_mode=clean_creation_mode,
                created_at=now,
                updated_at=now,
            )
            stories = [
                {
                    "story_id": row.get("story_id", ""),
                    "name": row.get("name", ""),
                    "description": row.get("description", ""),
                    "status": row.get("status", "active"),
                    "creation_mode": normalize_creation_mode(row.get("creation_mode")),
                    "created_at": row.get("created_at", ""),
                    "updated_at": row.get("updated_at", ""),
                }
                for row in current_rows
            ]
            stories.append(meta.model_dump())
            active_story_id = next(
                (
                    str(row.get("story_id") or "")
                    for row in current_rows
                    if row.get("is_active")
                ),
                "",
            )
            if not active_story_id or active_story_id == "default":
                active_story_id = story_id
            normalized_index = _normalize_stories_index_payload({
                "stories": stories,
                "active_story_id": active_story_id,
            })
            _memory_api.sync_stories_index(conn, normalized_index)
            conn.commit()
    except Exception:
        if sp is not None:
            try:
                sp.rmdir()
            except OSError as rollback_exc:
                _memory_api.logging.getLogger("novelforge.storage").warning(
                    "Failed to remove story directory after create rollback %s: %s",
                    sp,
                    rollback_exc,
                )
        raise
    if normalized_index is not None:
        _memory_api._refresh_project_json_mirror(project_name, stories_index_path(project_name), normalized_index)
    if meta is None:
        raise RuntimeError("Story creation did not produce metadata.")
    return meta.model_dump()


def rename_story(project_name: str, story_id: str, name: str, description: str | None = None) -> dict:
    clean_story_id = normalize_story_id(story_id)
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("故事名称不能为空。")

    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = [dict(row) for row in _memory_api.list_story_rows(conn)]
        target = next(
            (row for row in rows if str(row.get("story_id") or "") == clean_story_id),
            None,
        )
        if target is None:
            conn.rollback()
            raise ValueError(f"故事不存在：{clean_story_id}")
        target["name"] = clean_name
        if description is not None:
            target["description"] = str(description or "").strip()
        target["updated_at"] = _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds")
        normalized_index = _stories_index_payload_from_rows(rows)
        _memory_api.sync_stories_index(conn, normalized_index)
        conn.commit()
    _memory_api._refresh_project_json_mirror(project_name, stories_index_path(project_name), normalized_index)
    return next(
        dict(story)
        for story in normalized_index.get("stories", [])
        if story.get("story_id") == clean_story_id
    )



def copy_story_settings(
    project_name: str,
    source_story_id: str,
    target_story_id: str,
    *,
    include_discussions: bool = True,
):
    """复制故事级创作配置、讨论工件、Prompt 选项、规则、旧 memory 覆盖层和正式优先设定。"""
    profile = _memory_api.load_creative_profile(project_name, source_story_id)
    _memory_api.save_creative_profile(
        project_name,
        profile,
        target_story_id,
        mark_configured=bool(profile.get("is_configured")),
    )

    discussion_artifact = (
        _memory_api.load_creative_profile_discussion_artifact(project_name, source_story_id)
        if include_discussions
        else {}
    )
    if discussion_artifact:
        _memory_api.save_creative_profile_discussion_artifact(
            project_name,
            discussion_artifact.get("discussion", {}),
            discussion_artifact.get("report_markdown", ""),
            target_story_id,
        )

    save_story_memory(project_name, target_story_id, load_story_memory(project_name, source_story_id))
    _memory_api.save_story_rules(project_name, target_story_id, _memory_api.load_story_rules(project_name, source_story_id))
    copied_prompt_options: list[dict] = []
    for source_option in _memory_api.load_story_prompt_options(project_name, source_story_id):
        clone = dict(source_option)
        clone["source"] = "story_copy"
        copied_prompt_options.append(clone)
    _memory_api.save_story_prompt_options(project_name, target_story_id, copied_prompt_options)
    save_rule_conflict_resolutions(
        project_name,
        "story",
        load_rule_conflict_resolutions(project_name, "story", source_story_id),
        target_story_id,
    )

    from novelforge.domain.setting_knowledge import copy_story_core_settings_to_story

    core_result = copy_story_core_settings_to_story(project_name, source_story_id, target_story_id)

    _memory_api.sync_project_retrieval_assets(project_name)
    return core_result


def _merge_list_values(source: list | None, target: list | None) -> list:
    seen: set[str] = set()
    merged: list = []
    for item in (source or []) + (target or []):
        if item is None:
            continue
        if isinstance(item, dict):
            key = str(item.get("name") or item.get("title") or "").strip()
            if not key:
                merged.append(item)
                continue
        else:
            key = str(item).strip()
            if not key:
                merged.append(item)
                continue
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def merge_story_to_project_memory(project_name: str, story_id: str, field_resolutions: dict[str, _memory_api.Any] | None = None) -> dict:
    from novelforge.core.merge import build_merge_plan

    base = _memory_api.load_memory(project_name)
    story = load_story_memory(project_name, story_id)
    plan = build_merge_plan(story, base, source_label="故事", target_label="项目", base_path="memory")
    resolved = {}
    for opt in plan:
        if not opt.conflict:
            if opt.field_type == "list":
                resolved[opt.path.replace("memory.", "")] = _merge_list_values(opt.source_value, opt.target_value)
            else:
                resolved[opt.path.replace("memory.", "")] = opt.source_value if opt.source_value is not None else opt.target_value
        elif field_resolutions and opt.path in field_resolutions:
            resolved[opt.path.replace("memory.", "")] = field_resolutions[opt.path]
        else:
            resolved[opt.path.replace("memory.", "")] = opt.source_value

    merged = dict(base)
    for key, value in resolved.items():
        merged[key] = value
    _memory_api.save_memory(project_name, merged)

    overrides_path = _story_memory_overrides_path(project_name, story_id)
    if overrides_path.exists():
        overrides_path.unlink()
    _memory_api.sync_project_retrieval_assets(project_name)
    return merged


def merge_project_to_story_memory(project_name: str, story_id: str, field_resolutions: dict[str, _memory_api.Any] | None = None) -> dict:
    from novelforge.core.merge import build_merge_plan

    base = _memory_api.load_memory(project_name)
    story = load_story_memory(project_name, story_id)
    plan = build_merge_plan(base, story, source_label="项目", target_label="故事", base_path="memory")
    resolved = {}
    for opt in plan:
        key = opt.path.replace("memory.", "")
        if key == "chapter_summaries":
            continue
        if not opt.conflict:
            if opt.field_type == "list":
                resolved[key] = _merge_list_values(opt.source_value, opt.target_value)
            else:
                resolved[key] = opt.source_value if opt.source_value is not None else opt.target_value
        elif field_resolutions and opt.path in field_resolutions:
            resolved[key] = field_resolutions[opt.path]
        else:
            resolved[key] = opt.source_value

    overrides: dict = {}
    for key, value in resolved.items():
        if base.get(key) != value:
            overrides[key] = value
    path = _story_memory_overrides_path(project_name, story_id)
    _memory_api._write_json_mirror(path, overrides)
    _memory_api.sync_project_retrieval_assets(project_name)
    return {**base, **overrides}


def merge_story_rules_to_project(project_name: str, story_id: str) -> dict:
    project_rules = _memory_api.load_project_rules(project_name)
    story_rules = _memory_api.load_story_rules(project_name, story_id)
    merged = _merge_rules_dedup(project_rules, story_rules)
    _memory_api.save_project_rules(project_name, merged)
    path = _story_rules_overrides_path(project_name, story_id)
    if path.exists():
        path.unlink()
    return merged


def merge_project_rules_to_story(project_name: str, story_id: str) -> dict:
    project_rules = _memory_api.load_project_rules(project_name)
    _memory_api.save_story_rules(project_name, story_id, project_rules)
    return project_rules


def _merge_rules_dedup(target_rules: dict, source_rules: dict) -> dict:
    from novelforge.core.merge import _merge_dedup

    merged = dict(target_rules)
    for scope in _memory_api.RULE_SCOPES:
        source_items = source_rules.get(scope, [])
        if source_items:
            existing = merged.get(scope, [])
            merged[scope] = _merge_dedup(existing, source_items)
    return _memory_api.normalize_rules(merged)


def merge_project_rules_to_global(project_name: str) -> dict:
    global_rules = _memory_api.load_global_rules()
    project_rules = _memory_api.load_project_rules(project_name)
    merged = _merge_rules_dedup(global_rules, project_rules)
    _memory_api.save_global_rules(merged)
    return merged


def merge_story_rules_to_global(project_name: str, story_id: str) -> dict:
    global_rules = _memory_api.load_global_rules()
    story_rules = _memory_api.load_story_rules(project_name, story_id)
    merged = _merge_rules_dedup(global_rules, story_rules)
    _memory_api.save_global_rules(merged)
    return merged


def merge_global_rules_to_project(project_name: str) -> dict:
    global_rules = _memory_api.load_global_rules()
    project_rules = _memory_api.load_project_rules(project_name)
    merged = _merge_rules_dedup(project_rules, global_rules)
    _memory_api.save_project_rules(project_name, merged)
    return merged


def merge_global_rules_to_story(project_name: str, story_id: str) -> dict:
    global_rules = _memory_api.load_global_rules()
    story_rules = _memory_api.load_story_rules(project_name, story_id)
    merged = _merge_rules_dedup(story_rules, global_rules)
    _memory_api.save_story_rules(project_name, story_id, merged)
    return merged


def normalize_rule_conflict_resolutions(items: list | None, source: str = "") -> list[dict]:
    normalized: list[dict] = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict):
            continue
        decision = str(item.get("decision", "") or "").strip()
        if not decision:
            continue
        scope = str(item.get("scope", "all") or "all").strip()
        if scope not in _memory_api.RULE_SCOPES:
            scope = "all"
        title = str(item.get("title", "") or "").strip() or decision[:40]
        payload = {
            "id": str(item.get("id", "") or _memory_api.uuid4()).strip(),
            "scope": scope,
            "title": title,
            "decision": decision,
            "updated_at": str(item.get("updated_at", "") or _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds")),
        }
        if source:
            payload["source"] = source
        normalized.append(payload)
    return normalized


def _rule_conflict_resolution_path(project_name: str, layer: str, story_id: str = "default") -> _memory_api.Path:
    if layer == "global":
        return _memory_api.GLOBAL_RULE_CONFLICT_RESOLUTIONS_PATH
    if layer == "story":
        return _story_rule_conflict_resolutions_path(project_name, story_id)
    return _project_rule_conflict_resolutions_path(project_name)


def load_rule_conflict_resolutions(project_name: str, layer: str = "story", story_id: str = "default") -> list[dict]:
    if layer == "global":
        db_items = _memory_api._load_global_from_db_best_effort(
            lambda conn: _memory_api.load_global_setting(conn, "rule_conflict_resolutions"),
            "global rule conflict resolutions",
        )
        if isinstance(db_items, list):
            return normalize_rule_conflict_resolutions(db_items)
    if layer != "global":
        logical_key = f"{layer}:{story_id if layer == 'story' else 'project'}"
        db_items = _memory_api._load_asset_payload_from_db_best_effort(
            project_name,
            asset_type="rule_conflict_resolutions",
            logical_key=logical_key,
            story_id=story_id if layer == "story" else None,
        )
        if isinstance(db_items, list):
            return normalize_rule_conflict_resolutions(db_items)
    path = _rule_conflict_resolution_path(project_name, layer, story_id)
    if not path.exists():
        return []
    try:
        raw = _memory_api.json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    normalized = normalize_rule_conflict_resolutions(raw if isinstance(raw, list) else None)
    if layer == "global":
        _memory_api._sync_global_to_db_best_effort(
            lambda conn: _memory_api.sync_global_setting(conn, "rule_conflict_resolutions", normalized)
        )
    return normalized


def save_rule_conflict_resolutions(project_name: str, layer: str, resolutions: list[dict], story_id: str = "default") -> list[dict]:
    path = _rule_conflict_resolution_path(project_name, layer, story_id)
    normalized = normalize_rule_conflict_resolutions(resolutions)
    logical_key = f"{layer}:{story_id if layer == 'story' else 'project'}"
    if not normalized:
        if path.exists():
            path.unlink()
        if layer == "global":
            _memory_api._sync_global_to_db_best_effort(
                lambda conn: _memory_api.sync_global_setting(conn, "rule_conflict_resolutions", [])
            )
        if layer != "global":
            _memory_api.mark_asset_deleted_record(
                project_name,
                asset_type="rule_conflict_resolutions",
                logical_key=logical_key,
                story_id=story_id if layer == "story" else None,
            )
        return []
    _memory_api._write_json_mirror(path, normalized)
    if layer == "global":
        _memory_api._sync_global_to_db_best_effort(
            lambda conn: _memory_api.sync_global_setting(conn, "rule_conflict_resolutions", normalized)
        )
    if layer != "global":
        _memory_api._sync_asset_payload_to_db_best_effort(
            project_name,
            path,
            asset_type="rule_conflict_resolutions",
            logical_key=logical_key,
            story_id=story_id if layer == "story" else None,
            title=f"{layer.title()} Rule Conflict Resolutions",
            payload=normalized,
        )
    return normalized


def add_rule_conflict_resolution(
    project_name: str,
    layer: str,
    scope: str,
    title: str,
    decision: str,
    story_id: str = "default",
) -> dict:
    existing = load_rule_conflict_resolutions(project_name, layer, story_id)
    normalized_items = normalize_rule_conflict_resolutions([{
        "id": str(_memory_api.uuid4()),
        "scope": scope,
        "title": title,
        "decision": decision,
        "updated_at": _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds"),
    }])
    if not normalized_items:
        raise ValueError("Conflict resolution decision cannot be empty.")
    item = normalized_items[0]
    existing.append(item)
    save_rule_conflict_resolutions(project_name, layer, existing, story_id)
    return item


def delete_rule_conflict_resolution(project_name: str, layer: str, resolution_id: str, story_id: str = "default") -> bool:
    existing = load_rule_conflict_resolutions(project_name, layer, story_id)
    kept = [item for item in existing if item.get("id") != resolution_id]
    if len(kept) == len(existing):
        return False
    save_rule_conflict_resolutions(project_name, layer, kept, story_id)
    return True


def load_effective_rule_conflict_resolutions(project_name: str, story_id: str, scope: str) -> list[dict]:
    effective: list[dict] = []
    for layer, source_label in [("global", "全局"), ("project", "项目"), ("story", "故事")]:
        for item in load_rule_conflict_resolutions(project_name, layer, story_id):
            item_scope = item.get("scope", "all")
            if item_scope in {"all", scope}:
                normalized = dict(item)
                normalized["source"] = source_label
                effective.append(normalized)
    return effective


_STORY_COPY_CHAPTER_DIRS = {
    "chapters",
    "chapter_outlines",
    "reviews",
    "analysis",
    "evaluation",
    "runs",
}

_STORY_COPY_TOP_LEVEL_JSON_MIRRORS = {
    "chapter_summaries.json",
    "creative_profile.discussion.json",
    "creative_profile.json",
    "memory_overrides.json",
    "outline.discussion.json",
    "prompt_options.json",
    "rule_conflict_resolutions.json",
    "rules_overrides.json",
}


def _story_copy_path_is_known_json_mirror(relative_path: _memory_api.Path) -> bool:
    parts = tuple(part.casefold() for part in relative_path.parts)
    if len(parts) == 1:
        return parts[0] in _STORY_COPY_TOP_LEVEL_JSON_MIRRORS
    if len(parts) != 2:
        return False
    directory, file_name = parts
    if directory == "runs":
        return file_name.endswith(".json")
    patterns = {
        "reviews": r"chapter_\d+\.json",
        "evaluation": r"chapter_\d+\.json",
        "chapter_outlines": r"chapter_\d+\.(?:meta|discussion)\.json",
        "volumes": r"volume_\d+\.(?:meta|discussion)\.json",
        "arcs": r"arc_\d+\.(?:meta|discussion|chapter_plan)\.json",
    }
    pattern = patterns.get(directory)
    return bool(pattern and _memory_api.re.fullmatch(pattern, file_name))


def _story_db_json_mirror_paths(conn, story_id: str) -> set[str]:
    prefix = f"stories/{story_id}/"
    rows = conn.execute(
        """
        SELECT asset.relative_path
        FROM asset_files AS asset
        INNER JOIN asset_payloads AS payload ON payload.asset_id = asset.asset_id
        WHERE asset.story_id = ? AND asset.deleted_at IS NULL
        """,
        (story_id,),
    ).fetchall()
    paths: set[str] = set()
    for row in rows:
        project_relative = str(row["relative_path"] or "").replace("\\", "/")
        if project_relative.startswith(prefix) and project_relative.casefold().endswith(".json"):
            paths.add(project_relative[len(prefix):])
    return paths


def _story_copy_file_is_included(
    relative_path: _memory_api.Path,
    *,
    include_discussions: bool,
    include_summaries: bool,
    include_chapters: bool,
    db_json_mirror_paths: set[str] | None = None,
) -> bool:
    parts = relative_path.parts
    top_level = parts[0] if parts else ""
    if not include_chapters and top_level in _STORY_COPY_CHAPTER_DIRS:
        return False
    if not include_summaries and relative_path.name == "chapter_summaries.json":
        return False
    if not include_discussions:
        if top_level in {"volumes", "arcs"}:
            return False
        if "discussion" in relative_path.name.casefold():
            return False
    normalized_relative_path = "/".join(relative_path.parts)
    if (
        relative_path.suffix.casefold() == ".json"
        and (
            _story_copy_path_is_known_json_mirror(relative_path)
            or normalized_relative_path in (db_json_mirror_paths or set())
        )
    ):
        return False
    return True


def _copy_story_files(
    source_dir: _memory_api.Path,
    target_dir: _memory_api.Path,
    *,
    include_discussions: bool,
    include_summaries: bool,
    include_chapters: bool,
    db_json_mirror_paths: set[str] | None = None,
) -> None:
    import shutil

    if not source_dir.exists():
        return
    source_root = source_dir.resolve()
    target_root = target_dir.resolve()
    for item in source_dir.rglob("*"):
        if item.is_symlink():
            raise ValueError(f"Story copies do not follow symbolic links: {item}")
        if not item.is_file():
            continue
        resolved_item = item.resolve()
        if source_root not in resolved_item.parents:
            raise ValueError(f"Story file escaped its source directory: {item}")
        relative_path = item.relative_to(source_dir)
        if not _story_copy_file_is_included(
            relative_path,
            include_discussions=include_discussions,
            include_summaries=include_summaries,
            include_chapters=include_chapters,
            db_json_mirror_paths=db_json_mirror_paths,
        ):
            continue
        target_file = (target_dir / relative_path).resolve()
        if target_root not in target_file.parents:
            raise ValueError(f"Story copy target escaped its directory: {relative_path}")
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(resolved_item), str(target_file))


def _copied_story_json_mirror_path(
    project_name: str,
    target_story_id: str,
    project_relative_path: str,
) -> _memory_api.Path:
    normalized = str(project_relative_path or "").replace("\\", "/")
    parts = tuple(normalized.split("/"))
    if (
        len(parts) < 3
        or parts[:2] != ("stories", target_story_id)
        or any(part in {"", ".", ".."} or ":" in part for part in parts)
        or not parts[-1].casefold().endswith(".json")
    ):
        raise ValueError(f"Invalid copied story JSON mirror path: {project_relative_path}")
    target_root = story_path(project_name, target_story_id).resolve()
    target_file = _memory_api.project_path(project_name).joinpath(*parts).resolve()
    if target_root not in target_file.parents:
        raise ValueError(f"Copied story JSON mirror escaped its story directory: {project_relative_path}")
    return target_file


def _materialize_copied_story_json_mirrors(project_name: str, target_story_id: str) -> None:
    if not _memory_api._write_json_mirrors_enabled():
        return
    project_root = _memory_api.project_path(project_name).resolve()
    with _memory_api.open_project_db(project_root) as conn:
        asset_rows = conn.execute(
            """
            SELECT asset.asset_id, asset.relative_path, payload.payload_json
            FROM asset_files AS asset
            INNER JOIN asset_payloads AS payload ON payload.asset_id = asset.asset_id
            WHERE asset.story_id = ? AND asset.deleted_at IS NULL
            ORDER BY asset.asset_id
            """,
            (target_story_id,),
        ).fetchall()
        for row in asset_rows:
            relative_path = str(row["relative_path"] or "")
            if not relative_path.replace("\\", "/").casefold().endswith(".json"):
                continue
            target_file = _copied_story_json_mirror_path(
                project_name,
                target_story_id,
                relative_path,
            )
            payload = _memory_api.json.loads(str(row["payload_json"] or "null"))
            _memory_api._write_json_mirror(target_file, payload)
            content_hash = _memory_api.hashlib.sha256(target_file.read_bytes()).hexdigest()
            conn.execute(
                "UPDATE asset_files SET content_hash = ? WHERE asset_id = ?",
                (content_hash, str(row["asset_id"])),
            )

        workflow_rows = conn.execute(
            """
            SELECT run_id, output_json
            FROM workflow_runs
            WHERE story_id = ?
            ORDER BY run_id
            """,
            (target_story_id,),
        ).fetchall()
        for row in workflow_rows:
            run_id = _memory_api.normalize_storage_component(str(row["run_id"]), "Workflow run ID")
            relative_path = f"stories/{target_story_id}/runs/{run_id}.json"
            target_file = _copied_story_json_mirror_path(
                project_name,
                target_story_id,
                relative_path,
            )
            payload = _memory_api.json.loads(str(row["output_json"] or "{}"))
            _memory_api._write_json_mirror(target_file, payload)
            content_hash = _memory_api.hashlib.sha256(target_file.read_bytes()).hexdigest()
            conn.execute(
                """
                UPDATE asset_files
                SET content_hash = ?
                WHERE story_id = ?
                  AND asset_type = 'workflow_run_snapshot'
                  AND logical_key = ?
                  AND deleted_at IS NULL
                """,
                (content_hash, target_story_id, run_id),
            )
        conn.commit()


def _rollback_story_copy(project_name: str, target_story_id: str, original_index: dict) -> list[str]:
    import shutil

    errors: list[str] = []
    normalized_index: dict | None = None
    database_cleaned = False
    try:
        if _memory_api._project_db_marked_unavailable(project_name):
            raise RuntimeError(f"Project database is unavailable for {project_name}.")
        with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            current_rows = [
                dict(row)
                for row in _memory_api.list_story_rows(conn)
                if str(row.get("story_id") or "") != target_story_id
            ]
            current_stories = [
                {
                    "story_id": row.get("story_id", ""),
                    "name": row.get("name", ""),
                    "description": row.get("description", ""),
                    "status": row.get("status", "active"),
                    "creation_mode": normalize_creation_mode(row.get("creation_mode")),
                    "created_at": row.get("created_at", ""),
                    "updated_at": row.get("updated_at", ""),
                }
                for row in current_rows
            ]
            if not current_stories:
                current_stories = [_default_story_meta()]
            active_story_id = next(
                (
                    str(row.get("story_id") or "")
                    for row in current_rows
                    if row.get("is_active")
                ),
                "",
            )
            current_ids = {str(item.get("story_id") or "") for item in current_stories}
            original_active_id = str(original_index.get("active_story_id") or "")
            if active_story_id not in current_ids:
                active_story_id = (
                    original_active_id
                    if original_active_id in current_ids
                    else str(current_stories[0].get("story_id") or "default")
                )
            normalized_index = _normalize_stories_index_payload({
                "stories": current_stories,
                "active_story_id": active_story_id,
            })
            _memory_api.sync_stories_index(conn, normalized_index)
            _memory_api.purge_story_scoped_rows(conn, target_story_id)
            conn.commit()
        database_cleaned = True
    except Exception as exc:
        errors.append(f"database cleanup failed: {exc}")

    if database_cleaned and normalized_index is not None:
        try:
            _memory_api._write_json_mirror(stories_index_path(project_name), normalized_index)
            if not _memory_api._write_json_mirrors_enabled():
                _memory_api._delete_pending_mirrors(_memory_api._take_project_pending_mirror_deletions(project_name))
        except Exception as exc:
            errors.append(f"index mirror cleanup failed: {exc}")

    target_dir = story_path(project_name, target_story_id)
    if database_cleaned:
        try:
            if target_dir.exists():
                shutil.rmtree(str(target_dir))
        except Exception as exc:
            errors.append(f"file cleanup failed: {exc}")
    elif target_dir.exists():
        errors.append("file cleanup skipped because database cleanup failed")

    if database_cleaned:
        try:
            from novelforge.services.automatic_configuration import delete_automatic_configurations

            delete_automatic_configurations(project_name, story_id=target_story_id)
        except Exception as exc:
            errors.append(f"automatic configuration cleanup failed: {exc}")

    if database_cleaned:
        try:
            _memory_api.sync_project_retrieval_assets(project_name)
        except Exception as exc:
            _memory_api.logging.getLogger("novelforge").warning(
                "Failed to refresh retrieval assets after rolling back story copy: "
                "project=%s target=%s error=%s",
                project_name,
                target_story_id,
                exc,
            )
    return errors


def copy_story(project_name: str, source_story_id: str, new_name: str,
               *, include_discussions: bool = True, include_summaries: bool = True,
               include_chapters: bool = True) -> dict:
    source_story_id = normalize_story_id(source_story_id)
    original_index = _normalize_stories_index_payload(load_stories_index(project_name))
    source_story = next(
        (
            story
            for story in original_index.get("stories", [])
            if str(story.get("story_id") or "") == source_story_id
        ),
        None,
    )
    if source_story is None:
        raise ValueError(f"故事不存在：{source_story_id}")

    target_id = _story_id_slug(new_name)
    existing_ids = {
        str(story.get("story_id") or "")
        for story in original_index.get("stories", [])
    }
    if target_id in existing_ids:
        counter = 2
        while f"{target_id}_{counter}" in existing_ids:
            counter += 1
            if counter > 1000:
                raise RuntimeError(f"无法为故事名 '{new_name}' 生成唯一 ID：计数器已超上限。")
        target_id = f"{target_id}_{counter}"

    # create_story validates and creates the directory before committing the
    # index, so compensation is only needed after it returns an owned target.
    meta: dict | None = None
    try:
        created_meta = create_story(
            project_name,
            new_name,
            str(source_story.get("description") or ""),
            normalize_creation_mode(source_story.get("creation_mode")),
        )
        meta = created_meta
        target_id = str(created_meta["story_id"])
        src_dir = story_path(project_name, source_story_id)
        dst_dir = story_path(project_name, target_id)
        dst_dir.mkdir(parents=True, exist_ok=True)

        with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            source_json_mirror_paths = _story_db_json_mirror_paths(conn, source_story_id)
            _memory_api.clone_story_storage_rows(
                conn,
                source_story_id,
                target_id,
                include_discussions=include_discussions,
                include_summaries=include_summaries,
                include_chapters=include_chapters,
            )
            conn.commit()

        _copy_story_files(
            src_dir,
            dst_dir,
            include_discussions=include_discussions,
            include_summaries=include_summaries,
            include_chapters=include_chapters,
            db_json_mirror_paths=source_json_mirror_paths,
        )

        copy_story_settings(
            project_name,
            source_story_id,
            target_id,
            include_discussions=include_discussions,
        )
        from novelforge.services.automatic_configuration import copy_story_automatic_configurations

        copy_story_automatic_configurations(project_name, source_story_id, target_id)
        _materialize_copied_story_json_mirrors(project_name, target_id)
        _memory_api.sync_project_retrieval_assets(project_name)
        return meta
    except Exception as exc:
        if meta is not None:
            cleanup_errors = _rollback_story_copy(
                project_name,
                str(meta.get("story_id") or ""),
                original_index,
            )
            if cleanup_errors:
                raise RuntimeError(
                    "Story copy failed and rollback was incomplete: " + "; ".join(cleanup_errors)
                ) from exc
        raise


def archive_story(project_name: str, story_id: str) -> bool:
    clean_story_id = normalize_story_id(story_id)
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = [dict(row) for row in _memory_api.list_story_rows(conn)]
        target = next(
            (row for row in rows if str(row.get("story_id") or "") == clean_story_id),
            None,
        )
        if target is None:
            conn.rollback()
            return False
        target["status"] = "archived"
        target["updated_at"] = _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds")
        normalized_index = _stories_index_payload_from_rows(rows)
        _memory_api.sync_stories_index(conn, normalized_index)
        conn.commit()
    _memory_api._refresh_project_json_mirror(project_name, stories_index_path(project_name), normalized_index)
    return True


def delete_story(project_name: str, story_id: str) -> bool:
    story_id = normalize_story_id(story_id)

    from novelforge.services.automatic_configuration import delete_automatic_configurations

    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        current_rows = [dict(row) for row in _memory_api.list_story_rows(conn)]
        if not any(str(row.get("story_id") or "") == story_id for row in current_rows):
            conn.rollback()
            return False
        remaining_rows = [
            row
            for row in current_rows
            if str(row.get("story_id") or "") != story_id
        ]
        remaining_stories = [
            {
                "story_id": row.get("story_id", ""),
                "name": row.get("name", ""),
                "description": row.get("description", ""),
                "status": row.get("status", "active"),
                "creation_mode": normalize_creation_mode(row.get("creation_mode")),
                "created_at": row.get("created_at", ""),
                "updated_at": row.get("updated_at", ""),
            }
            for row in remaining_rows
        ]
        if not remaining_stories:
            remaining_stories = [_default_story_meta()]
        remaining_ids = {
            str(item.get("story_id") or "")
            for item in remaining_stories
        }
        active_story_id = next(
            (
                str(row.get("story_id") or "")
                for row in remaining_rows
                if row.get("is_active")
                and str(row.get("story_id") or "") in remaining_ids
            ),
            str(remaining_stories[0].get("story_id") or "default"),
        )
        normalized_index = _normalize_stories_index_payload({
            "stories": remaining_stories,
            "active_story_id": active_story_id,
        })
        _memory_api.sync_stories_index(conn, normalized_index)
        _memory_api.purge_story_scoped_rows(conn, story_id)
        conn.commit()

    try:
        _memory_api._write_json_mirror(stories_index_path(project_name), normalized_index)
        if not _memory_api._write_json_mirrors_enabled():
            _memory_api._delete_pending_mirrors(_memory_api._take_project_pending_mirror_deletions(project_name))
    except OSError as exc:
        _memory_api.logging.getLogger("novelforge.storage").warning(
            "Story %s was deleted from SQLite, but its index mirror could not be refreshed: %s",
            story_id,
            exc,
        )

    # Compatibility mirrors are non-authoritative. Keep shared knowledge files
    # consistent when mirror mode is explicitly enabled, without performing a
    # second series of whole-category database writes.
    if _memory_api._write_json_mirrors_enabled():
        for category in _memory_api.KNOWLEDGE_CATEGORIES:
            path = _memory_api.knowledge_category_path(project_name, category)
            if not path.exists():
                continue
            items = _memory_api._load_json_list(path)
            remaining = [
                item for item in items
                if str(item.get("story_id") or "").strip() != story_id
            ]
            if remaining != items:
                try:
                    _memory_api._write_json_mirror(path, remaining)
                except OSError as exc:
                    _memory_api.logging.getLogger("novelforge.storage").warning(
                        "Failed to refresh knowledge mirror %s after story deletion: %s",
                        path,
                        exc,
                    )
        pending_path = _memory_api.pending_knowledge_path(project_name)
        if pending_path.exists():
            pending_items = _memory_api._load_json_list(pending_path)
            remaining_pending = [
                item for item in pending_items
                if str(item.get("story_id") or "").strip() != story_id
            ]
            if remaining_pending != pending_items:
                try:
                    _memory_api._write_json_mirror(pending_path, remaining_pending)
                except OSError as exc:
                    _memory_api.logging.getLogger("novelforge.storage").warning(
                        "Failed to refresh pending mirror %s after story deletion: %s",
                        pending_path,
                        exc,
                    )

    try:
        delete_automatic_configurations(project_name, story_id=story_id)
    except Exception as exc:
        _memory_api.logging.getLogger("novelforge.configuration").warning(
            "Story %s was deleted, but automatic settings cleanup failed for %s: %s",
            story_id,
            project_name,
            exc,
        )
    sp = story_path(project_name, story_id)
    if sp.exists():
        import shutil

        shutil.rmtree(str(sp))
    try:
        _memory_api.sync_project_retrieval_assets(project_name)
    except Exception as exc:
        _memory_api.logging.getLogger("novelforge.retrieval").warning(
            "Story %s was deleted, but retrieval rebuild failed for %s: %s",
            story_id,
            project_name,
            exc,
        )
    return True


def list_stories(project_name: str) -> list[dict]:
    index = load_stories_index(project_name)
    return list(index.get("stories", []))


def get_story_creation_mode(project_name: str, story_id: str = "default") -> str:
    """Read the story mode from SQLite first, with the normal compatibility path."""

    clean_story_id = normalize_story_id(story_id)
    rows = list_stories(project_name)
    target = next(
        (row for row in rows if str(row.get("story_id") or "") == clean_story_id),
        None,
    )
    if target is None:
        raise ValueError(f"故事不存在：{clean_story_id}")
    return normalize_creation_mode(target.get("creation_mode"))


def set_story_creation_mode(
    project_name: str,
    story_id: str,
    creation_mode: str,
) -> dict:
    """Change the story's UI/workflow mode without deleting any story asset."""

    clean_story_id = normalize_story_id(story_id)
    clean_creation_mode = normalize_creation_mode(creation_mode)
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")

    normalized_index: dict | None = None
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = [dict(row) for row in _memory_api.list_story_rows(conn)]
        target = next(
            (row for row in rows if str(row.get("story_id") or "") == clean_story_id),
            None,
        )
        if target is None:
            conn.rollback()
            raise ValueError(f"故事不存在：{clean_story_id}")
        target["creation_mode"] = clean_creation_mode
        target["updated_at"] = _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds")
        normalized_index = _stories_index_payload_from_rows(rows)
        _memory_api.sync_stories_index(conn, normalized_index)
        conn.commit()

    if normalized_index is None:
        raise RuntimeError("Story mode update did not produce an index.")
    _memory_api._refresh_project_json_mirror(project_name, stories_index_path(project_name), normalized_index)
    return next(
        dict(story)
        for story in normalized_index.get("stories", [])
        if story.get("story_id") == clean_story_id
    )


def load_story_memory_overrides(project_name: str, story_id: str) -> dict:
    """Load only a story's persisted override layer, using SQLite first."""

    story_id = normalize_story_id(story_id)
    if story_id == "default":
        return {}
    db_overrides = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="story_memory_overrides",
        logical_key="memory_overrides",
        story_id=story_id,
    )
    if isinstance(db_overrides, dict):
        overrides = db_overrides
    else:
        overrides = None
    overrides_path = _story_memory_overrides_path(project_name, story_id)
    if overrides is None and not overrides_path.exists():
        return {}
    if overrides is None:
        try:
            overrides = _memory_api.json.loads(overrides_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if isinstance(overrides, dict):
            _memory_api._sync_asset_payload_to_db_best_effort(
                project_name,
                overrides_path,
                asset_type="story_memory_overrides",
                logical_key="memory_overrides",
                story_id=story_id,
                title="Story Memory Overrides",
                payload=overrides,
            )
    if not isinstance(overrides, dict):
        return {}
    return dict(overrides)


def load_story_memory(project_name: str, story_id: str) -> dict:
    base = _memory_api.load_memory(project_name)
    overrides = load_story_memory_overrides(project_name, story_id)
    if not overrides:
        return base
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, list) and isinstance(base.get(key), list):
            # 基于 key 去重合并，防止前缀匹配优化未命中时产生重复条目
            seen: set[str] = set()
            deduped: list = []
            for item in base[key] + value:
                item_key = str(item.get("name") or item.get("title") or item) if isinstance(item, dict) else str(item)
                if item_key not in seen:
                    seen.add(item_key)
                    deduped.append(item)
            merged[key] = deduped
        elif value is not None:
            merged[key] = value
    return merged


def save_story_memory(project_name: str, story_id: str, memory: dict):
    if story_id == "default":
        _memory_api.save_memory(project_name, memory)
        return

    base = _memory_api.load_memory(project_name)
    overrides: dict = {}
    for key, value in (memory or {}).items():
        base_value = base.get(key)
        if value == base_value:
            continue
        # 使用前缀匹配检测仅追加的新条目；若条目被插入到列表开头或中间，则整体值会存入覆盖层，
        # 下次加载时会基于 key 去重合并，因此数据一致性不会受损。
        if isinstance(value, list) and isinstance(base_value, list) and value[:len(base_value)] == base_value:
            extra_items = value[len(base_value):]
            if extra_items:
                overrides[key] = extra_items
        else:
            overrides[key] = value

    path = _story_memory_overrides_path(project_name, story_id)
    _memory_api._write_json_mirror(path, overrides)
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        path,
        asset_type="story_memory_overrides",
        logical_key="memory_overrides",
        story_id=story_id,
        title="Story Memory Overrides",
        payload=overrides,
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_story_chapter_summaries(project_name: str, story_id: str) -> list[dict]:
    db_items = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="chapter_summaries",
        logical_key="chapter_summaries",
        story_id=story_id,
    )
    if isinstance(db_items, list):
        return [item for item in db_items if isinstance(item, dict)]
    path = _story_chapter_summaries_path(project_name, story_id)
    if not path.exists():
        return []
    try:
        raw = _memory_api.json.loads(path.read_text(encoding="utf-8"))
        items = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
        if items:
            _memory_api._sync_asset_payload_to_db_best_effort(
                project_name,
                path,
                asset_type="chapter_summaries",
                logical_key="chapter_summaries",
                story_id=story_id,
                title="Chapter Summaries",
                payload=items,
            )
        return items
    except Exception:
        return []


def save_story_chapter_summaries(project_name: str, story_id: str, summaries: list[dict]):
    path = _story_chapter_summaries_path(project_name, story_id)
    normalized = [item for item in list(summaries or []) if isinstance(item, dict)]
    _memory_api._write_json_mirror(path, normalized)
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        path,
        asset_type="chapter_summaries",
        logical_key="chapter_summaries",
        story_id=story_id,
        title="Chapter Summaries",
        payload=normalized,
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def migrate_project_to_stories(project_name: str) -> bool:
    marker = _memory_api.project_path(project_name) / ".migrated"
    if marker.exists():
        return False
    legacy_memory: dict = {}
    legacy_memory_path = _memory_api.project_path(project_name) / "memory.json"
    if legacy_memory_path.exists():
        try:
            loaded_legacy_memory = _memory_api.json.loads(legacy_memory_path.read_text(encoding="utf-8"))
            if isinstance(loaded_legacy_memory, dict):
                legacy_memory = loaded_legacy_memory
        except (_memory_api.json.JSONDecodeError, OSError) as exc:
            _memory_api.logging.getLogger("novelforge.storage").warning(
                "Failed to read legacy memory during story migration for %s: %s",
                project_name,
                exc,
            )
    sp = story_path(project_name, "default")
    sp.mkdir(parents=True, exist_ok=True)

    migratable = [
        ("outline.md", "outline.md"),
        ("outline.discussion.json", "outline.discussion.json"),
        ("creative_profile.json", "creative_profile.json"),
        ("creative_profile.discussion.json", "creative_profile.discussion.json"),
        ("volumes", "volumes"),
        ("arcs", "arcs"),
        ("chapter_outlines", "chapter_outlines"),
        ("chapters", "chapters"),
        ("reviews", "reviews"),
        ("analysis", "analysis"),
        ("evaluation", "evaluation"),
        ("runs", "runs"),
    ]
    moved_any = False
    for src_name, dst_name in migratable:
        src = _memory_api.project_path(project_name) / src_name
        dst = sp / dst_name
        if src.exists():
            if dst.exists():
                continue
            src.rename(dst)
            moved_any = True

    conflict_src = _memory_api.project_path(project_name) / "retrieval" / "conflict_resolutions.json"
    conflict_dst = sp / "retrieval" / "conflict_resolutions.json"
    if conflict_src.exists():
        conflict_dst.parent.mkdir(parents=True, exist_ok=True)
        conflict_src.rename(conflict_dst)

    summaries = legacy_memory.get("chapter_summaries", [])
    if summaries:
        save_story_chapter_summaries(project_name, "default", list(summaries))

    memory = _memory_api.load_memory(project_name)
    if "chapter_summaries" in memory:
        memory["chapter_summaries"] = []
        _memory_api.save_memory(project_name, memory)

    idx_path = _memory_api.project_path(project_name) / "stories" / "index.json"
    if not idx_path.exists():
        now = _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds")
        default_meta = _memory_api.StoryMeta(
            story_id="default",
            name="默认故事",
            description="",
            status="active",
            created_at=now,
            updated_at=now,
        )
        idx = _memory_api.StoriesIndex(stories=[default_meta], active_story_id="default")
        save_stories_index(project_name, idx.model_dump())

    marker.write_text("")
    _memory_api.sync_project_retrieval_assets(project_name)
    return moved_any


def _story_path_from_project_path(project_name: str, story_id: str, *parts: str) -> _memory_api.Path:
    return story_path(project_name, story_id).joinpath(*parts)
