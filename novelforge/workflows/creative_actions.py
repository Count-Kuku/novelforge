"""Plan, confirm, execute, and undo conversational creative actions."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

from novelforge.domain.creative_actions import action_requires_confirmation, route_creative_action
from novelforge.services.memory import (
    load_creative_action,
    load_creative_config_revision,
    load_creative_profile,
    load_creative_session_bundle,
    load_effective_story_branch_configuration,
    save_story_branch_configuration,
    default_branch_id,
    story_reference_mode,
    load_knowledge_category,
    load_knowledge_center_record,
    assert_story_knowledge_writable,
    create_story_knowledge_override,
    validate_creative_action_scope,
    resolve_creative_session_branch,
    mark_creative_config_revision_reversed,
    save_creative_action,
    save_creative_config_revision,
    save_creative_message,
    save_creative_profile,
    update_confirmed_knowledge_item_record,
    update_creative_action,
    update_creative_session,
)
from novelforge.services.retrieval import retrieve_context
from novelforge.core.schemas import RetrievalChunk, RetrievalHit
from novelforge.workflows.interactive_writing import (
    active_fragment_chain,
    extract_fragment_knowledge,
    save_writing_session_as_chapter,
)
from novelforge.services.memory.creative_actions import claim_creative_action, transition_creative_action


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_key(session_id: str, request: str) -> str:
    digest = hashlib.sha256(f"{session_id}|{request}|{uuid4().hex}".encode()).hexdigest()
    return f"creative_action_{digest}"


def plan_creative_action(
    project_name: str,
    story_id: str,
    session_id: str,
    request: str,
    *,
    idempotency_key: str = "",
    branch_id: str | None = None,
) -> dict:
    branch_id = resolve_creative_session_branch(
        project_name, story_id, session_id, branch_id,
    )
    bundle = load_creative_session_bundle(project_name, session_id, story_id=story_id)
    if not bundle:
        raise ValueError("创作会话不存在或不属于当前故事。")
    route = route_creative_action(
        request,
        has_fragment=bool(bundle.get("session", {}).get("active_fragment_id")),
    )
    key = str(idempotency_key or "").strip() or _default_key(session_id, request)
    target = dict(route.get("target") or {})
    if route.get("action_type") == "extract_knowledge" and target.pop("active_fragment", False):
        target["fragment_id"] = next(
            (
                str(item.get("fragment_id") or "")
                for item in reversed(active_fragment_chain(bundle))
                if str(item.get("status") or "") in {"accepted", "finalized"}
            ),
            "",
        )
    if route.get("action_type") == "save_chapter" and target.get("chapter_no") is None:
        target["chapter_no"] = int(bundle.get("session", {}).get("target_chapter_no") or 1)
    stable_token = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    message = save_creative_message(project_name, {
        "message_id": f"creative_message_{stable_token}",
        "story_id": story_id, "session_id": session_id, "role": "user",
        "branch_id": branch_id,
        "content": str(request or "").strip(),
        "metadata": {"idempotency_key": key},
    })
    action_type = str(route.get("action_type") or "clarify")
    requires_confirmation = action_requires_confirmation(action_type)
    action = save_creative_action(project_name, {
        "action_id": f"creative_action_{stable_token}",
        "story_id": story_id, "session_id": session_id,
        "branch_id": branch_id,
        "request_message_id": message.get("message_id"),
        "action_type": action_type,
        "status": "awaiting_confirmation" if requires_confirmation else "planned",
        "scope": route.get("scope") or "session",
        "target": target, "patch": route.get("patch") or {},
        "plan": route.get("plan") or {}, "requires_confirmation": requires_confirmation,
        "idempotency_key": key,
    })
    # A duplicate idempotency key returns the authoritative first action; its
    # request message is harmless but should not appear twice in the UI.
    return action


def _assistant_receipt(project_name: str, action: dict, content: str, *, error: bool = False) -> None:
    save_creative_message(project_name, {
        "message_id": f"creative_message_{uuid4().hex}",
        "story_id": action.get("story_id"), "session_id": action.get("session_id"),
        "role": "assistant", "message_kind": "error" if error else "action_receipt",
        "content": content, "metadata": {"action_id": action.get("action_id")},
    })


def _apply_config(project_name: str, action: dict) -> tuple[dict, dict]:
    story_id = str(action.get("story_id") or "")
    session_id = str(action.get("session_id") or "")
    branch_id = str(action.get("branch_id") or "")
    patch = dict(action.get("patch") or {})
    if action.get("scope") == "story":
        effective = load_effective_story_branch_configuration(project_name, story_id, branch_id)
        before = dict(effective.get("profile") or {})
        after_profile = {**before, **patch}
        if branch_id == default_branch_id(story_id):
            after_profile = save_creative_profile(
                project_name, after_profile, story_id, mark_configured=True,
            )
        else:
            save_story_branch_configuration(
                project_name, story_id, branch_id, {"profile": after_profile},
            )
        after = {**effective, "profile": after_profile}
        config_scope = "story"
    else:
        bundle = load_creative_session_bundle(project_name, session_id, story_id=story_id) or {}
        session = dict(bundle.get("session") or {})
        before = {
            "writing_guidance": dict(session.get("writing_guidance") or {}),
            "target_chapter_no": session.get("target_chapter_no"),
        }
        guidance = dict(before["writing_guidance"])
        target_chapter = before["target_chapter_no"]
        for key, value in patch.items():
            if key == "target_chapter_no":
                target_chapter = int(value)
            else:
                guidance[key] = value
        after = {"writing_guidance": guidance, "target_chapter_no": target_chapter}
        update_creative_session(project_name, session_id, after, story_id=story_id)
        config_scope = "session"
    revision = save_creative_config_revision(project_name, {
        "action_id": action.get("action_id"), "story_id": story_id,
        "session_id": session_id if config_scope == "session" else None,
        "config_scope": config_scope, "before": before, "after": after,
        "patch": patch, "reason": "对话动作更新配置",
        "branch_id": branch_id,
    })
    return after, {"revision_id": revision.get("revision_id"), "before": before}


def _apply_knowledge_update(project_name: str, action: dict) -> tuple[dict, dict]:
    story_id = str(action.get("story_id") or "")
    branch_id = str(action.get("branch_id") or "")
    target = dict(action.get("target") or {})
    category = str(target.get("category") or "")
    item_id = str(target.get("item_id") or "")
    original = load_knowledge_center_record(
        project_name, "knowledge", item_id, story_id=story_id, branch_id=branch_id,
    )
    if not original:
        raise ValueError("要修改的知识不存在。")
    category = str(original.get("category") or (original.get("payload") or {}).get("category") or category)
    patch = dict(action.get("patch") or {})
    inherited = bool(
        original.get("visible_from_checkpoint")
        or (
            original.get("origin_branch_id")
            and str(original.get("origin_branch_id")) != branch_id
        )
    )
    if inherited:
        # First materialize the frozen parent snapshot in this branch, then
        # apply the user's patch.  This gives undo a branch-owned ID and never
        # writes through to the parent's knowledge item.
        base_copy = create_story_knowledge_override(
            project_name, original, {}, story_id=story_id, branch_id=branch_id,
            reason="对话动作创建世界线知识副本",
        )
        local_id = str(base_copy.get("knowledge_id") or base_copy.get("id") or "")
        local_before = dict(base_copy.get("payload") or base_copy)
        if not update_confirmed_knowledge_item_record(
            project_name, category, local_id,
            {**local_before, **patch, "story_id": story_id, "branch_id": branch_id, "setting_scope": "story"},
            target_category=category,
        ):
            raise RuntimeError("知识修改未能提交。")
        return {"category": category, "item_id": local_id, "origin_knowledge_id": item_id, "changes": patch}, {
            "category": category, "item_id": local_id, "before": local_before,
        }

    effective_branch, writable = assert_story_knowledge_writable(
        project_name, story_id, branch_id, item_id,
    )
    payload = dict(writable.get("payload") or writable)
    if not update_confirmed_knowledge_item_record(
        project_name, category, item_id,
        {**payload, **patch, "story_id": story_id, "branch_id": effective_branch, "setting_scope": "story"},
        target_category=category,
    ):
        raise RuntimeError("知识修改未能提交。")
    return {"category": category, "item_id": item_id, "changes": patch}, {
        "category": category, "item_id": item_id, "before": payload,
    }


def _frozen_query_hits(
    project_name: str,
    story_id: str,
    session_id: str,
    branch_id: str,
    query: str,
) -> list[RetrievalHit] | None:
    """Search the same immutable branch payloads used by generation context.

    The retrieval index stores live text.  A checkpoint can keep the same
    knowledge ID after its parent is edited or deleted, so filtering live
    chunks by ID is insufficient.  ``list_visible_story_knowledge`` resolves
    the effective frozen payload, including always and manual-only records,
    before this action searches it. ``None`` preserves legacy story behavior,
    where dynamic retrieval remains intentional until strict mode is confirmed.
    """
    if story_reference_mode(project_name, story_id) != "strict":
        return None
    from novelforge.services.memory import list_visible_story_knowledge
    from novelforge.services.retrieval.common import _tokenize

    query_terms = set(_tokenize(str(query or "").lower()))
    visible_items = list_visible_story_knowledge(
        project_name, story_id, branch_id,
    )
    candidates: list[tuple[tuple[int, int, int, int], RetrievalHit]] = []
    for index, item in enumerate(visible_items):
        if str(item.get("status") or "confirmed").strip().lower() not in {"confirmed", "user_override"}:
            continue
        payload = dict(item.get("payload") or {})
        knowledge_id = str(item.get("knowledge_id") or item.get("id") or payload.get("knowledge_id") or "").strip()
        if not knowledge_id:
            continue
        category = str(item.get("category") or payload.get("category") or "other")
        name = str(payload.get("name") or item.get("name") or payload.get("title") or knowledge_id)
        summary = str(payload.get("summary") or item.get("summary") or payload.get("content") or "")
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        content = "\n".join(
            value for value in [
                f"name: {name}",
                f"summary: {summary}",
                *(f"{key}: {value}" for key, value in details.items()),
            ] if str(value).strip()
        )
        content_terms = set(_tokenize(content.lower()))
        if query_terms and not query_terms.intersection(content_terms):
            continue
        name_text = name.strip().lower()
        query_text = " ".join(str(query or "").lower().split())
        name_terms = set(_tokenize(name_text))
        matched_terms = sorted(query_terms.intersection(content_terms))
        name_overlap = len(query_terms.intersection(name_terms))
        exact_name = int(bool(query_text and query_text in name_text))
        chunk = RetrievalChunk(
            chunk_id=f"branch_snapshot:{branch_id}:{knowledge_id}",
            document_id=f"branch_snapshot_document:{branch_id}:{knowledge_id}",
            project_name=project_name,
            source_type=f"knowledge_{category}",
            scope="project",
            title=name,
            content=content,
            metadata={
                "knowledge_id": knowledge_id,
                "branch_id": branch_id,
                "story_id": story_id,
                "snapshot": True,
            },
        )
        hit = RetrievalHit(
            chunk=chunk,
            score=float(exact_name * 100 + name_overlap * 10 + len(matched_terms)),
            lexical_score=(len(matched_terms) / len(query_terms)) if query_terms else 0.0,
            retrieval_mode="lexical",
            matched_terms=matched_terms,
            match_reasons=["来自当前世界线不可变检查点"],
        )
        # Prefer an exact name match, then terms in the name, then total
        # content overlap.  The final index keeps the snapshot's stable order.
        candidates.append(((exact_name, name_overlap, len(matched_terms), -index), hit))
    candidates.sort(key=lambda entry: entry[0], reverse=True)
    return [hit for _, hit in candidates[:6]]


def execute_creative_action(
    project_name: str,
    action_id: str,
    *,
    story_id: str = "",
    session_id: str = "",
    branch_id: str | None = None,
    confirmed: bool = False,
    stream_callback=None,
) -> dict:
    action = validate_creative_action_scope(
        project_name, action_id, story_id=story_id, session_id=session_id,
        branch_id=branch_id,
    )
    expected_story_id = str(action.get("story_id") or "")
    expected_session_id = str(action.get("session_id") or "")
    branch_id = str(action.get("branch_id") or "")
    if action.get("status") in {"completed", "undone", "cancelled"}:
        return action
    if action.get("requires_confirmation") and not confirmed:
        return action
    claimed = claim_creative_action(
        project_name,
        action_id,
        expected_story_id,
        expected_session_id,
        ("awaiting_confirmation", "planned"),
        {"confirmed_at": _now()} if action.get("requires_confirmation") else None,
        branch_id=branch_id,
    )
    if not claimed:
        current = validate_creative_action_scope(
            project_name, action_id, story_id=expected_story_id,
            session_id=expected_session_id, branch_id=branch_id,
        )
        if current and current.get("status") in {"completed", "undone", "cancelled"}:
            return current
        raise ValueError("创作动作正在执行或状态已改变，请刷新后重试。")
    action = claimed

    try:
        action_type = str(action.get("action_type") or "clarify")
        result: dict
        undo: dict = {}
        if action_type == "query_knowledge":
            query = str(action.get("target", {}).get("query") or "")
            query_story_id = str(action.get("story_id") or "default")
            hits = _frozen_query_hits(
                project_name, query_story_id, str(action.get("session_id") or ""),
                branch_id, query,
            )
            if hits is None:
                hits = retrieve_context(
                    project_name, query, retrieval_profile="drafting",
                    story_id=query_story_id,
                    session_id=str(action.get("session_id") or ""), top_k=6,
                )
            result = {"query": query, "hits": [hit.model_dump() for hit in hits]}
            receipt = "\n\n".join(
                f"**{hit.chunk.title}**\n\n{hit.chunk.content[:700]}" for hit in hits[:5]
            ) or "没有找到匹配资料。"
        elif action_type == "import_sources":
            result = {"open_attachment_tray": True}
            receipt = str(action.get("plan", {}).get("message") or "请使用资料与附件托盘。")
        elif action_type == "extract_knowledge":
            fragment_id = str(action.get("target", {}).get("fragment_id") or "")
            if not fragment_id:
                raise ValueError("当前没有已保留的片段可提炼。")
            result = extract_fragment_knowledge(
                project_name, str(action.get("story_id") or ""),
                str(action.get("session_id") or ""), fragment_id,
                stream_callback=stream_callback, branch_id=branch_id,
            )
            receipt = f"已提炼 {len(result.get('candidate_ids') or [])} 条待审核知识。"
        elif action_type == "update_config":
            result, undo = _apply_config(project_name, action)
            receipt = "配置差异已确认并保存，可从动作记录撤销。"
        elif action_type == "update_knowledge":
            result, undo = _apply_knowledge_update(project_name, action)
            receipt = "知识修订已保存并立即更新检索索引。"
        elif action_type == "save_chapter":
            target = dict(action.get("target") or {})
            chapter_no = target.get("chapter_no")
            if chapter_no is None:
                bundle = load_creative_session_bundle(
                    project_name, str(action.get("session_id") or ""),
                    story_id=str(action.get("story_id") or ""),
                ) or {}
                chapter_no = bundle.get("session", {}).get("target_chapter_no") or 1
            result = save_writing_session_as_chapter(
                project_name, str(action.get("story_id") or ""),
                str(action.get("session_id") or ""), int(chapter_no),
                stream_callback=stream_callback, branch_id=branch_id,
            )
            receipt = f"已保存为第 {int(chapter_no)} 章。"
        elif action_type == "clarify":
            result = {"message": action.get("plan", {}).get("message") or "请补充说明。"}
            receipt = str(result["message"])
        else:
            raise ValueError("正文写作动作必须由正文生成工作流执行。")
        action = update_creative_action(project_name, action_id, {
            "status": "completed", "result": result, "undo": undo,
            "finished_at": _now(),
        }, story_id=expected_story_id, session_id=expected_session_id, branch_id=branch_id)
        _assistant_receipt(project_name, action, receipt)
        return action
    except Exception as exc:
        failed = update_creative_action(project_name, action_id, {
            "status": "failed", "error_text": str(exc), "finished_at": _now(),
        }, story_id=expected_story_id, session_id=expected_session_id, branch_id=branch_id)
        _assistant_receipt(project_name, failed, f"动作执行失败：{exc}", error=True)
        raise


def cancel_creative_action(project_name: str, action_id: str, story_id: str = "", session_id: str = "", branch_id: str | None = None) -> dict:
    action = validate_creative_action_scope(
        project_name, action_id, story_id=story_id, session_id=session_id,
        branch_id=branch_id,
    )
    expected_story_id = str(action.get("story_id") or "")
    expected_session_id = str(action.get("session_id") or "")
    expected_branch_id = str(action.get("branch_id") or "")
    claimed = transition_creative_action(
        project_name, action_id, expected_story_id, expected_session_id,
        "awaiting_confirmation", "cancelled", branch_id=expected_branch_id,
    )
    if not claimed:
        raise ValueError("只有等待确认的动作可以取消。")
    return update_creative_action(
        project_name, action_id, {"finished_at": _now()},
        story_id=expected_story_id, session_id=expected_session_id, branch_id=expected_branch_id,
    )


def undo_creative_action(
    project_name: str,
    action_id: str,
    *,
    story_id: str = "",
    session_id: str = "",
    branch_id: str | None = None,
    idempotency_key: str = "",
) -> dict:
    original = validate_creative_action_scope(
        project_name, action_id, story_id=story_id, session_id=session_id,
        branch_id=branch_id,
    )
    if not original or original.get("status") != "completed" or not original.get("undo"):
        raise ValueError("该动作不可撤销或已经撤销。")
    expected_story_id = str(original.get("story_id") or "")
    expected_session_id = str(original.get("session_id") or "")
    expected_branch_id = str(original.get("branch_id") or "")
    claimed_original = transition_creative_action(
        project_name, action_id, expected_story_id, expected_session_id,
        "completed", "running", branch_id=expected_branch_id,
    )
    if not claimed_original:
        raise ValueError("该动作正在撤销或状态已改变，请刷新后重试。")
    try:
        reverse = save_creative_action(project_name, {
            "action_id": f"creative_action_{uuid4().hex}",
            "story_id": original.get("story_id"), "session_id": original.get("session_id"),
            "branch_id": expected_branch_id,
            "action_type": original.get("action_type"), "status": "running",
            "scope": original.get("scope"), "target": original.get("target"),
            "patch": {}, "plan": {"undoes": action_id},
            "idempotency_key": idempotency_key or f"undo:{action_id}",
        })
        undo = dict(original.get("undo") or {})
        if original.get("action_type") == "update_config":
            revision = load_creative_config_revision(project_name, action_id)
            before = dict(undo.get("before") or {})
            if original.get("scope") == "story":
                if expected_branch_id == default_branch_id(expected_story_id):
                    save_creative_profile(
                        project_name, before, expected_story_id,
                        mark_configured=bool(before.get("is_configured")),
                    )
                else:
                    save_story_branch_configuration(
                        project_name, expected_story_id, expected_branch_id,
                        {"profile": before},
                    )
            else:
                update_creative_session(
                    project_name, str(original.get("session_id") or ""), before,
                    story_id=str(original.get("story_id") or ""),
                )
            if revision:
                mark_creative_config_revision_reversed(
                    project_name, str(revision.get("revision_id") or ""),
                    str(reverse.get("action_id") or ""),
                )
        elif original.get("action_type") == "update_knowledge":
            assert_story_knowledge_writable(
                project_name, expected_story_id, expected_branch_id,
                str(undo.get("item_id") or ""),
            )
            if not update_confirmed_knowledge_item_record(
                project_name, str(undo.get("category") or ""),
                str(undo.get("item_id") or ""),
                {**dict(undo.get("before") or {}), "story_id": expected_story_id,
                 "branch_id": expected_branch_id, "setting_scope": "story"},
            ):
                raise RuntimeError("知识撤销未能提交。")
        else:
            raise ValueError("该动作不支持撤销。")
        update_creative_action(project_name, action_id, {
            "status": "undone", "finished_at": original.get("finished_at") or _now(),
        }, story_id=expected_story_id, session_id=expected_session_id, branch_id=expected_branch_id)
        return update_creative_action(project_name, str(reverse.get("action_id") or ""), {
            "status": "completed", "result": {"undone_action_id": action_id},
            "finished_at": _now(),
        }, story_id=expected_story_id, session_id=expected_session_id, branch_id=expected_branch_id)
    except Exception:
        update_creative_action(
            project_name, action_id, {"status": "completed"},
            story_id=expected_story_id, session_id=expected_session_id, branch_id=expected_branch_id,
        )
        raise


def record_creative_generation_action(
    project_name: str, story_id: str, session_id: str, request: str,
    result: dict, *, action_type: str, branch_id: str | None = None,
) -> dict:
    branch_id = resolve_creative_session_branch(project_name, story_id, session_id, branch_id)
    mapped = "revise" if action_type in {"rewrite", "revise"} else "write"
    fragment = dict(result.get("fragment") or {})
    fragment_id = str(fragment.get("fragment_id") or "")
    stable_token = hashlib.sha256(f"fragment:{fragment_id}".encode()).hexdigest()[:24]
    message = save_creative_message(project_name, {
        "message_id": f"creative_message_{stable_token}", "story_id": story_id,
        "session_id": session_id, "branch_id": branch_id, "role": "user", "content": request,
    })
    action = save_creative_action(project_name, {
        "action_id": f"creative_action_{stable_token}", "story_id": story_id,
        "session_id": session_id, "branch_id": branch_id, "request_message_id": message.get("message_id"),
        "action_type": mapped, "status": "completed", "scope": "turn",
        "target": {"generation_action": action_type},
        "result": {"fragment_id": fragment_id, "turn_id": result.get("turn", {}).get("turn_id")},
        "idempotency_key": f"fragment:{fragment_id}",
        "finished_at": _now(),
    })
    return action
