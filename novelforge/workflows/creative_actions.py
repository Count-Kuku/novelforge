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
    load_knowledge_category,
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
from novelforge.workflows.interactive_writing import (
    active_fragment_chain,
    extract_fragment_knowledge,
    save_writing_session_as_chapter,
)


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
) -> dict:
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
        "content": str(request or "").strip(),
        "metadata": {"idempotency_key": key},
    })
    action_type = str(route.get("action_type") or "clarify")
    requires_confirmation = action_requires_confirmation(action_type)
    action = save_creative_action(project_name, {
        "action_id": f"creative_action_{stable_token}",
        "story_id": story_id, "session_id": session_id,
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
    patch = dict(action.get("patch") or {})
    if action.get("scope") == "story":
        before = load_creative_profile(project_name, story_id) or {}
        after = {**before, **patch}
        after = save_creative_profile(project_name, after, story_id, mark_configured=True)
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
    })
    return after, {"revision_id": revision.get("revision_id"), "before": before}


def _apply_knowledge_update(project_name: str, action: dict) -> tuple[dict, dict]:
    target = dict(action.get("target") or {})
    category = str(target.get("category") or "")
    item_id = str(target.get("item_id") or "")
    original = next(
        (
            item for item in load_knowledge_category(project_name, category)
            if str(item.get("id") or item.get("knowledge_id") or "") == item_id
        ), None,
    )
    if original is None:
        raise ValueError("要修改的知识不存在。")
    patch = dict(action.get("patch") or {})
    if not update_confirmed_knowledge_item_record(
        project_name, category, item_id, patch, target_category=category
    ):
        raise RuntimeError("知识修改未能提交。")
    return {"category": category, "item_id": item_id, "changes": patch}, {
        "category": category, "item_id": item_id, "before": original,
    }


def execute_creative_action(
    project_name: str,
    action_id: str,
    *,
    confirmed: bool = False,
    stream_callback=None,
) -> dict:
    action = load_creative_action(project_name, action_id)
    if not action:
        raise ValueError("创作动作不存在。")
    if action.get("status") in {"completed", "undone", "cancelled"}:
        return action
    if action.get("requires_confirmation") and not confirmed:
        return action
    if action.get("requires_confirmation"):
        action = update_creative_action(project_name, action_id, {
            "status": "running", "confirmed_at": _now(),
        })
    else:
        action = update_creative_action(project_name, action_id, {"status": "running"})

    try:
        action_type = str(action.get("action_type") or "clarify")
        result: dict
        undo: dict = {}
        if action_type == "query_knowledge":
            query = str(action.get("target", {}).get("query") or "")
            hits = retrieve_context(
                project_name, query, retrieval_profile="drafting",
                story_id=str(action.get("story_id") or "default"),
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
                stream_callback=stream_callback,
            )
            receipt = f"已提炼 {len(result.get('candidate_ids') or [])} 条待审核设定。"
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
                stream_callback=stream_callback,
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
        })
        _assistant_receipt(project_name, action, receipt)
        return action
    except Exception as exc:
        failed = update_creative_action(project_name, action_id, {
            "status": "failed", "error_text": str(exc), "finished_at": _now(),
        })
        _assistant_receipt(project_name, failed, f"动作执行失败：{exc}", error=True)
        raise


def cancel_creative_action(project_name: str, action_id: str) -> dict:
    action = load_creative_action(project_name, action_id)
    if not action or action.get("status") != "awaiting_confirmation":
        raise ValueError("只有等待确认的动作可以取消。")
    return update_creative_action(project_name, action_id, {
        "status": "cancelled", "finished_at": _now(),
    })


def undo_creative_action(
    project_name: str,
    action_id: str,
    *,
    idempotency_key: str = "",
) -> dict:
    original = load_creative_action(project_name, action_id)
    if not original or original.get("status") != "completed" or not original.get("undo"):
        raise ValueError("该动作不可撤销或已经撤销。")
    reverse = save_creative_action(project_name, {
        "action_id": f"creative_action_{uuid4().hex}",
        "story_id": original.get("story_id"), "session_id": original.get("session_id"),
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
            save_creative_profile(
                project_name, before, str(original.get("story_id") or ""),
                mark_configured=bool(before.get("is_configured")),
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
        if not update_confirmed_knowledge_item_record(
            project_name, str(undo.get("category") or ""),
            str(undo.get("item_id") or ""), dict(undo.get("before") or {}),
        ):
            raise RuntimeError("知识撤销未能提交。")
    else:
        raise ValueError("该动作不支持撤销。")
    update_creative_action(project_name, action_id, {
        "status": "undone", "finished_at": original.get("finished_at") or _now(),
    })
    return update_creative_action(project_name, str(reverse.get("action_id") or ""), {
        "status": "completed", "result": {"undone_action_id": action_id},
        "finished_at": _now(),
    })


def record_creative_generation_action(
    project_name: str, story_id: str, session_id: str, request: str,
    result: dict, *, action_type: str,
) -> dict:
    mapped = "revise" if action_type in {"rewrite", "revise"} else "write"
    fragment = dict(result.get("fragment") or {})
    fragment_id = str(fragment.get("fragment_id") or "")
    stable_token = hashlib.sha256(f"fragment:{fragment_id}".encode()).hexdigest()[:24]
    message = save_creative_message(project_name, {
        "message_id": f"creative_message_{stable_token}", "story_id": story_id,
        "session_id": session_id, "role": "user", "content": request,
    })
    action = save_creative_action(project_name, {
        "action_id": f"creative_action_{stable_token}", "story_id": story_id,
        "session_id": session_id, "request_message_id": message.get("message_id"),
        "action_type": mapped, "status": "completed", "scope": "turn",
        "target": {"generation_action": action_type},
        "result": {"fragment_id": fragment_id, "turn_id": result.get("turn", {}).get("turn_id")},
        "idempotency_key": f"fragment:{fragment_id}",
        "finished_at": _now(),
    })
    return action
