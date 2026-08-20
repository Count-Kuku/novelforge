from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime, timezone
from uuid import uuid4

from novelforge.workflows.context_assembly import (
    assemble_generation_context,
    ensure_context_budget,
    render_context_for_prompt,
)
from novelforge.core.llm import call_llm
from novelforge.core.llm_usage import llm_usage_scope
from novelforge.core.token_estimation import estimate_chat_input_tokens, estimate_text_tokens
from novelforge.domain.llm_preflight import parse_requested_output_range
from novelforge.services.llm_estimation import build_calibrated_preflight
from novelforge.services.automatic_configuration import (
    configure_operation_automatically,
    estimate_project_source_chars,
)
from novelforge.services.capabilities import require_operation_capabilities
from novelforge.services.memory import (
    accept_creative_fragment,
    begin_creative_turn,
    claim_turn_creative_attachments,
    release_turn_creative_attachments,
    complete_creative_turn,
    consume_context_directives,
    create_creative_session,
    get_story_creation_mode,
    fail_creative_turn,
    finalize_creative_session,
    load_creative_profile,
    load_creative_session_bundle,
    load_pending_knowledge_items,
    load_chapter,
    queue_pending_knowledge_items,
    save_chapter,
    save_generation_context_snapshot,
    select_creative_fragment_variant,
    update_creative_fragment,
    update_creative_session,
)
from novelforge.core.prompts import (
    compile_creative_fragments_prompt,
    creative_fragment_prompt,
    creative_session_summary_prompt,
)
from novelforge.core.schemas import ChapterWritingGuidance
from novelforge.services.memory import retrieval_sources_path


LOGGER = logging.getLogger("novelforge.interactive_writing")
RECENT_FRAGMENT_CONTEXT_CHARS = 9_000
SUMMARY_REFRESH_THRESHOLD_CHARS = 12_000
SUMMARY_BATCH_MIN_FRAGMENTS = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _short_title(text: str, fallback: str = "自由创作") -> str:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return fallback
    for separator in ["。", "！", "？", "\n", "，", ",", "；", ";", "：", ":"]:
        if separator in normalized:
            normalized = normalized.split(separator, 1)[0].strip() or normalized
            break
    return normalized[:48].rstrip() or fallback


def _bundle_or_raise(
    project_name: str,
    story_id: str,
    session_id: str,
) -> dict:
    bundle = load_creative_session_bundle(
        project_name,
        session_id,
        story_id=story_id,
    )
    if not bundle:
        raise ValueError("创作会话不存在或不属于当前故事。")
    return bundle


def create_writing_session(
    project_name: str,
    story_id: str,
    *,
    session_goal: str,
    title: str = "",
    writing_guidance: dict | None = None,
    target_chapter_no: int | None = None,
    auto_extract_mode: str | None = None,
) -> dict:
    profile = load_creative_profile(project_name, story_id) or {}
    if auto_extract_mode is None:
        try:
            creation_mode = get_story_creation_mode(project_name, story_id)
        except Exception:
            creation_mode = "planned"
        auto_extract_mode = "on_accept" if creation_mode == "conversational" else "manual"
    return create_creative_session(project_name, {
        "session_id": f"session_{uuid4().hex}",
        "story_id": story_id,
        "title": str(title or "").strip() or _short_title(session_goal),
        "status": "active",
        "session_goal": str(session_goal or "").strip(),
        "writing_guidance": ChapterWritingGuidance.model_validate(
            writing_guidance or {}
        ).model_dump(),
        "target_chapter_no": target_chapter_no,
        "worldline_id": str(profile.get("worldline_id") or "main"),
        "auto_extract_mode": auto_extract_mode,
    })


def _fragment_map(bundle: dict) -> dict[str, dict]:
    return {
        str(fragment.get("fragment_id") or ""): fragment
        for fragment in bundle.get("fragments", [])
        if str(fragment.get("fragment_id") or "")
    }


def active_fragment_chain(
    bundle: dict,
    *,
    head_fragment_id: str | None = None,
) -> list[dict]:
    fragments = _fragment_map(bundle)
    session = bundle.get("session", {}) or {}
    current_id = str(
        head_fragment_id
        if head_fragment_id is not None
        else session.get("active_fragment_id") or ""
    )
    chain: list[dict] = []
    seen: set[str] = set()
    while current_id:
        if current_id in seen:
            raise RuntimeError("创作片段链包含循环引用。")
        seen.add(current_id)
        fragment = fragments.get(current_id)
        if fragment is None:
            raise RuntimeError("创作会话引用了不存在的片段。")
        chain.append(fragment)
        current_id = str(fragment.get("parent_fragment_id") or "")
    chain.reverse()
    return chain


def accepted_active_fragments(bundle: dict) -> list[dict]:
    return [
        fragment
        for fragment in active_fragment_chain(bundle)
        if str(fragment.get("status") or "") in {"accepted", "finalized"}
    ]


def _summary_refresh_material(
    bundle: dict,
    *,
    additionally_accepted_fragment_id: str | None = None,
) -> tuple[list[dict], list[dict], str, str]:
    """Return the accepted chain and the portion pending rolling-summary refresh."""

    extra_id = str(additionally_accepted_fragment_id or "")
    accepted = [
        fragment
        for fragment in active_fragment_chain(bundle)
        if (
            str(fragment.get("status") or "") in {"accepted", "finalized"}
            or str(fragment.get("fragment_id") or "") == extra_id
        )
    ]
    if not accepted:
        return [], [], "", ""
    session = bundle.get("session", {}) or {}
    summary_fragment_id = str(session.get("summary_fragment_id") or "")
    if not summary_fragment_id:
        pending = accepted
    else:
        pending = []
        covered = False
        for fragment in accepted:
            if covered:
                pending.append(fragment)
            elif str(fragment.get("fragment_id") or "") == summary_fragment_id:
                covered = True
        if not covered:
            pending = accepted
    pending_text = "\n\n".join(str(item.get("content") or "") for item in pending)
    total_text = "\n\n".join(str(item.get("content") or "") for item in accepted)
    return accepted, pending, pending_text, total_text


def _recent_fragment_text(chain: list[dict]) -> str:
    sections: list[str] = []
    remaining = RECENT_FRAGMENT_CONTEXT_CHARS
    for fragment in reversed(chain):
        content = str(fragment.get("content") or "").strip()
        if not content:
            continue
        excerpt = content[-remaining:]
        sections.append(
            f"[片段 {str(fragment.get('fragment_id') or '')[:16]}]\n{excerpt}"
        )
        remaining -= len(excerpt)
        if remaining <= 0:
            break
    sections.reverse()
    return "\n\n".join(sections)


def _session_context_blocks(
    bundle: dict,
    *,
    context_head_id: str | None,
) -> list[dict]:
    session = bundle.get("session", {}) or {}
    chain = active_fragment_chain(bundle, head_fragment_id=context_head_id)
    recent_text = _recent_fragment_text(chain)
    blocks: list[dict] = []
    rolling_summary = str(session.get("rolling_summary") or "").strip()
    if rolling_summary:
        blocks.append({
            "block_id": f"session_summary:{session.get('session_id')}",
            "category": "session_summary",
            "content": rolling_summary,
            "source_type": "creative_session_summary",
            "source_ref": str(session.get("session_id") or ""),
            "placement": "story_state",
            "priority": 92,
            "scope": "story",
            "story_id": session.get("story_id"),
            "activation_reason": "当前会话较早的已接受片段滚动摘要",
        })
    if recent_text:
        blocks.append({
            "block_id": f"session_fragments:{context_head_id or 'root'}",
            "category": "session_fragments",
            "content": recent_text,
            "source_type": "creative_session_fragment",
            "source_ref": context_head_id,
            "placement": "chapter_direction",
            "priority": 98,
            "scope": "story",
            "story_id": session.get("story_id"),
            "activation_reason": "当前分支最近的已接受或即将接受片段",
        })
    return blocks


def _claimed_attachment_blocks(project_name: str, attachments: list[dict]) -> list[dict]:
    blocks: list[dict] = []
    source_root = retrieval_sources_path(project_name).resolve()
    for attachment in attachments:
        relative_path = str(attachment.get("relative_path") or "")
        target = (source_root / relative_path).resolve()
        if source_root != target and source_root not in target.parents:
            raise ValueError("创作附件路径超出项目资料目录。")
        if not target.is_file():
            continue
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            continue
        content = str(payload.get("content") or "") if isinstance(payload, dict) else ""
        if not content.strip():
            continue
        blocks.append({
            "block_id": f"creative_attachment:{attachment.get('attachment_id')}",
            "category": "retrieval",
            "content": content,
            "source_type": "creative_attachment",
            "source_ref": str(attachment.get("source_revision_id") or attachment.get("source_id") or ""),
            "placement": "reference",
            "priority": 85,
            "scope": "story",
            "story_id": attachment.get("story_id"),
            "activation_reason": "用户指定仅下一轮使用的资料",
            "metadata": {
                "attachment_id": attachment.get("attachment_id"),
                "attachment_scope": "turn",
                "source_revision_id": attachment.get("source_revision_id"),
            },
        })
    return blocks


def _resolve_generation_branch(
    bundle: dict,
    action_type: str,
    branch_from_fragment_id: str | None = None,
) -> dict:
    session = bundle.get("session", {}) or {}
    if str(session.get("status") or "") == "archived":
        raise ValueError("已归档的创作会话不能继续生成。")
    fragments = _fragment_map(bundle)
    active_id = str(session.get("active_fragment_id") or "")
    active = fragments.get(active_id) if active_id else None
    action = str(action_type or "generate")

    if action == "generate":
        if active is not None:
            action = "continue"
        else:
            return {
                "action_type": "generate",
                "parent_fragment_id": None,
                "context_head_id": None,
                "accept_fragment_id": None,
                "supersede_fragment_id": None,
            }

    if action == "continue":
        if active is None:
            raise ValueError("当前会话还没有可续写片段。")
        return {
            "action_type": action,
            "parent_fragment_id": active_id,
            "context_head_id": active_id,
            "accept_fragment_id": (
                active_id if str(active.get("status") or "") == "proposed" else None
            ),
            "supersede_fragment_id": None,
        }

    if action in {"rewrite", "revise"}:
        if active is None:
            raise ValueError("当前会话还没有可重写片段。")
        if str(active.get("status") or "") != "proposed":
            raise ValueError("只有尚未接受的当前候选片段可以重写。")
        parent_id = str(active.get("parent_fragment_id") or "") or None
        return {
            "action_type": action,
            "parent_fragment_id": parent_id,
            "context_head_id": parent_id,
            "accept_fragment_id": None,
            "supersede_fragment_id": active_id,
        }

    if action == "branch":
        parent_id = str(branch_from_fragment_id or "").strip()
        parent = fragments.get(parent_id)
        if parent is None:
            raise ValueError("请选择当前会话中的分支起点。")
        if str(parent.get("status") or "") not in {"accepted", "finalized"}:
            raise ValueError("只能从已接受片段创建分支。")
        frontier_id = (
            active_id
            if str(active.get("status") or "") in {"accepted", "finalized"}
            else str(active.get("parent_fragment_id") or "")
        ) if active is not None else ""
        if parent_id != frontier_id:
            raise ValueError("只能从当前创作前沿的已接受片段创建分支。")
        return {
            "action_type": action,
            "parent_fragment_id": parent_id,
            "context_head_id": parent_id,
            "accept_fragment_id": None,
            "supersede_fragment_id": None,
        }
    raise ValueError(f"未知创作操作：{action_type}")


def build_writing_session_query(
    bundle: dict,
    user_message: str,
    *,
    context_head_id: str | None,
) -> str:
    session = bundle.get("session", {}) or {}
    chain = active_fragment_chain(bundle, head_fragment_id=context_head_id)
    recent = _recent_fragment_text(chain)
    return "\n".join([
        f"自由创作会话：{session.get('title') or ''}",
        f"会话目标：{session.get('session_goal') or ''}",
        f"本轮要求：{str(user_message or '').strip()}",
        f"滚动摘要：{str(session.get('rolling_summary') or '')[:1800]}",
        f"最近片段：{recent[-2400:]}",
    ])


def build_writing_fragment_preflight(
    bundle: dict | None,
    user_message: str,
    *,
    word_count: str = "800-1200",
    context_budget: int = 12_000,
    action_type: str = "continue",
    branch_from_fragment_id: str | None = None,
    auto_extract_mode: str | None = None,
) -> dict:
    """Estimate one free-writing turn without running retrieval or the model."""

    active_bundle = dict(bundle or {})
    branch: dict | None = None
    if active_bundle:
        branch = _resolve_generation_branch(
            active_bundle,
            action_type,
            branch_from_fragment_id,
        )
        query = build_writing_session_query(
            active_bundle,
            user_message,
            context_head_id=branch["context_head_id"],
        )
    else:
        query = f"自由创作目标：{str(user_message or '').strip()}"
    known_input = estimate_chat_input_tokens(query)
    budget = max(int(context_budget), 2000)
    input_low = max(known_input + 800, 1800)
    input_expected = min(max(known_input + 3500, 4500), budget + 1200)
    input_high = max(input_expected, budget + 1800, known_input + 1800)
    low_chars, high_chars = parse_requested_output_range(word_count)
    expected_chars = math.ceil((low_chars + high_chars) / 2)
    output_range = {
        "low": max(math.ceil(low_chars / 1.8), 1),
        "expected": max(math.ceil(expected_chars / 1.6), 1),
        "high": max(math.ceil(high_chars / 1.35), 1),
    }
    retrieval_query_tokens = max(estimate_text_tokens(query), 1)
    stages = [
        {
            "stage_name": "写作资料检索",
            "operation": "ui.generate_writing_fragment",
            "agent_role": "ui_action",
            "endpoint_type": "embedding",
            "call_count": 1,
            "embedding_tokens_per_call": {
                "low": retrieval_query_tokens,
                "expected": retrieval_query_tokens,
                "high": math.ceil(retrieval_query_tokens * 1.1),
            },
            "calibrate_output": False,
            "confidence": "high",
        },
        {
            "stage_name": "创作片段生成",
            "operation": "creative.fragment",
            "agent_role": "generator",
            "call_count": 1,
            "input_tokens_per_call": {
                "low": input_low,
                "expected": input_expected,
                "high": input_high,
            },
            "output_tokens_per_call": output_range,
            "calibrate_input": False,
            "calibrate_output": True,
            "confidence": "low",
            "assumptions": [
                "执行前不运行语义检索，输入区间包含可能注入的设定、规则和检索资料。",
                "输出区间由片段长度设置和同类历史调用共同校准。",
            ],
        },
    ]
    accept_fragment_id = str((branch or {}).get("accept_fragment_id") or "")
    if active_bundle:
        accepted, pending, pending_text, total_text = _summary_refresh_material(
            active_bundle,
            additionally_accepted_fragment_id=accept_fragment_id or None,
        )
        if (
            len(total_text) >= SUMMARY_REFRESH_THRESHOLD_CHARS
            and len(pending) >= SUMMARY_BATCH_MIN_FRAGMENTS
            and pending_text.strip()
        ):
            rolling_summary = str(
                (active_bundle.get("session", {}) or {}).get("rolling_summary") or ""
            )
            summary_input = estimate_chat_input_tokens(
                f"{rolling_summary}\n\n{pending_text}"
            )
            stages.append({
                "stage_name": "会话滚动摘要",
                "operation": "creative.summary",
                "agent_role": "summarizer",
                "call_count": 1,
                "input_tokens_per_call": {
                    "low": max(summary_input + 350, 900),
                    "expected": max(summary_input + 900, 1600),
                    "high": max(math.ceil(summary_input * 1.25) + 1500, 2800),
                },
                "output_tokens_per_call": {
                    "low": 250,
                    "expected": 650,
                    "high": 1400,
                },
                "calibrate_input": True,
                "calibrate_output": True,
                "confidence": "medium",
                "assumptions": [
                    (
                        f"接受当前候选后，{len(accepted)} 个已接受片段将达到滚动摘要刷新条件。"
                        if accept_fragment_id
                        else f"当前 {len(accepted)} 个已接受片段已达到滚动摘要刷新条件。"
                    )
                ],
            })

    if accept_fragment_id:
        session = active_bundle.get("session", {}) or {}
        effective_auto_extract_mode = str(
            auto_extract_mode
            if auto_extract_mode is not None
            else session.get("auto_extract_mode") or "manual"
        )
        if effective_auto_extract_mode == "on_accept":
            fragment = _fragment_map(active_bundle).get(accept_fragment_id, {})
            source_tokens = max(
                estimate_text_tokens(str(fragment.get("content") or "")),
                1,
            )
            stages.append({
                "stage_name": "已接受片段设定提炼",
                "operation": "reference.extract",
                "agent_role": "extractor",
                "call_count": 1,
                "input_tokens_per_call": {
                    "low": source_tokens + 1200,
                    "expected": source_tokens + 3000,
                    "high": source_tokens + 7000,
                },
                "output_tokens_per_call": {
                    "low": 500,
                    "expected": 1400,
                    "high": 3000,
                },
                "calibrate_input": True,
                "calibrate_output": True,
                "confidence": "low",
                "assumptions": [
                    "继续生成会先接受当前候选；自动提炼开启时会追加一次结构化知识提取调用。"
                ],
            })
    return build_calibrated_preflight(
        stages,
        estimate_kind="creative_fragment",
    )


def preview_writing_context(
    project_name: str,
    story_id: str,
    session_id: str,
    user_message: str,
    *,
    action_type: str = "continue",
    writing_guidance: dict | None = None,
    prompt_option_ids: list[str] | None = None,
    manual_knowledge_ids: list[str] | None = None,
    branch_from_fragment_id: str | None = None,
    context_budget: int | None = None,
    turn_attachment_blocks: list[dict] | None = None,
):
    bundle = _bundle_or_raise(project_name, story_id, session_id)
    branch = _resolve_generation_branch(
        bundle,
        action_type,
        branch_from_fragment_id,
    )
    session = bundle.get("session", {}) or {}
    guidance = ChapterWritingGuidance.model_validate(
        writing_guidance or session.get("writing_guidance") or {}
    ).model_dump()
    if prompt_option_ids is None:
        prompt_option_ids = list(guidance.get("prompt_option_ids") or [])
    else:
        guidance["prompt_option_ids"] = list(prompt_option_ids)
    if manual_knowledge_ids is None:
        manual_knowledge_ids = list(guidance.get("manual_knowledge_ids") or [])
    else:
        guidance["manual_knowledge_ids"] = list(manual_knowledge_ids)
    query = build_writing_session_query(
        bundle,
        user_message,
        context_head_id=branch["context_head_id"],
    )
    if context_budget is None:
        automatic = configure_operation_automatically(
            project_name,
            story_id,
            "creative_writing",
            goal=f"{session.get('session_goal', '')} {user_message}",
            source_chars=estimate_project_source_chars(project_name) + len(str(query or "")),
        )
        context_budget = int(automatic.get("settings", {}).get("context_budget") or 12_000)
    return assemble_generation_context(
        project_name,
        story_id=story_id,
        capability="write",
        query=query,
        chapter_no=session.get("target_chapter_no"),
        generation_guidance=guidance,
        prompt_option_ids=prompt_option_ids,
        manual_knowledge_ids=manual_knowledge_ids,
        additional_blocks=[
            *_session_context_blocks(
                bundle,
                context_head_id=branch["context_head_id"],
            ),
            *list(turn_attachment_blocks or []),
        ],
        allowed_scopes=["project", "canon", "reference"],
        retrieval_profile="drafting",
        context_budget=context_budget,
        retrieval_session_id=session_id,
    )


def generate_writing_fragment(
    project_name: str,
    story_id: str,
    session_id: str,
    user_message: str,
    *,
    action_type: str = "continue",
    word_count: str = "800-1200",
    writing_guidance: dict | None = None,
    prompt_option_ids: list[str] | None = None,
    manual_knowledge_ids: list[str] | None = None,
    branch_from_fragment_id: str | None = None,
    stream_callback=None,
) -> dict:
    require_operation_capabilities("creative_writing", action="对话式创作")
    bundle = _bundle_or_raise(project_name, story_id, session_id)
    session = bundle.get("session", {}) or {}
    branch = _resolve_generation_branch(
        bundle,
        action_type,
        branch_from_fragment_id,
    )
    guidance = ChapterWritingGuidance.model_validate(
        writing_guidance or session.get("writing_guidance") or {}
    ).model_dump()
    if prompt_option_ids is None:
        prompt_option_ids = list(guidance.get("prompt_option_ids") or [])
    else:
        guidance["prompt_option_ids"] = list(prompt_option_ids)
    if manual_knowledge_ids is None:
        manual_knowledge_ids = list(guidance.get("manual_knowledge_ids") or [])
    else:
        guidance["manual_knowledge_ids"] = list(manual_knowledge_ids)
    turn = begin_creative_turn(
        project_name,
        session_id,
        user_message,
        action_type=branch["action_type"],
        parent_fragment_id=branch["parent_fragment_id"],
        story_id=story_id,
    )
    try:
        claimed_attachments = claim_turn_creative_attachments(
            project_name,
            story_id=story_id,
            session_id=session_id,
            turn_id=str(turn["turn_id"]),
        )
        assembly = preview_writing_context(
            project_name,
            story_id,
            session_id,
            user_message,
            action_type=branch["action_type"],
            writing_guidance=guidance,
            prompt_option_ids=prompt_option_ids,
            manual_knowledge_ids=manual_knowledge_ids,
            branch_from_fragment_id=branch_from_fragment_id,
            turn_attachment_blocks=_claimed_attachment_blocks(
                project_name,
                claimed_attachments,
            ),
        )
        ensure_context_budget(assembly)
        prompt = creative_fragment_prompt(
            render_context_for_prompt(assembly),
            str(session.get("session_goal") or ""),
            str(user_message or "").strip(),
            branch["action_type"],
            word_count,
        )
        with llm_usage_scope(
            project_name=project_name,
            story_id=story_id,
            task_id=session_id,
            operation="creative.fragment",
            agent_role="generator",
            metadata={"turn_id": str(turn.get("turn_id") or "")},
        ):
            content = call_llm(prompt, stream_callback=stream_callback)
        if not str(content or "").strip():
            raise RuntimeError("模型没有返回创作片段。")
    except Exception as exc:
        try:
            release_turn_creative_attachments(
                project_name,
                story_id=story_id,
                session_id=session_id,
                turn_id=str(turn["turn_id"]),
            )
        except Exception as attachment_exc:
            LOGGER.warning(
                "Failed to release turn-scoped creative attachments: turn=%s error=%s",
                turn.get("turn_id"),
                attachment_exc,
            )
        try:
            fail_creative_turn(
                project_name,
                str(turn["turn_id"]),
                str(exc),
                story_id=story_id,
            )
        except Exception as failure_exc:
            LOGGER.warning(
                "Failed to record creative turn failure: turn=%s error=%s",
                turn.get("turn_id"),
                failure_exc,
            )
        raise

    fragment_id = f"fragment_{uuid4().hex}"
    warnings = list(assembly.warnings)
    snapshot_id: str | None = None
    try:
        snapshot_payload = assembly.model_dump()
        snapshot_payload.update({
            "session_id": session_id,
            "turn_id": turn["turn_id"],
            "fragment_id": fragment_id,
        })
        snapshot_id = save_generation_context_snapshot(
            project_name,
            story_id,
            snapshot_payload,
        )
    except Exception as exc:
        LOGGER.warning(
            "Failed to save creative fragment context snapshot: session=%s turn=%s error=%s",
            session_id,
            turn.get("turn_id"),
            exc,
        )
        warnings.append(f"片段已生成，但上下文快照保存失败：{exc}")

    try:
        fragment = complete_creative_turn(
            project_name,
            str(turn["turn_id"]),
            {
                "fragment_id": fragment_id,
                "session_id": session_id,
                "turn_id": turn["turn_id"],
                "parent_fragment_id": branch["parent_fragment_id"],
                "content": str(content).strip(),
                "status": "proposed",
                "content_hash": hashlib.sha256(str(content).strip().encode("utf-8")).hexdigest(),
                "word_count": len(str(content).strip()),
                "context_snapshot_id": snapshot_id,
                "extraction_status": "not_started",
                "created_at": _now(),
            },
            story_id=story_id,
            accept_fragment_id=branch["accept_fragment_id"],
            supersede_fragment_id=branch["supersede_fragment_id"],
        )
    except Exception as exc:
        try:
            fail_creative_turn(
                project_name,
                str(turn["turn_id"]),
                f"片段持久化失败：{exc}",
                story_id=story_id,
            )
        except Exception as failure_exc:
            LOGGER.warning(
                "Failed to record creative turn persistence failure: turn=%s error=%s",
                turn.get("turn_id"),
                failure_exc,
            )
        raise
    directive_ids = [
        str(block.metadata.get("directive_id") or "")
        for block in assembly.blocks
        if str(block.metadata.get("directive_id") or "")
    ]
    if directive_ids:
        try:
            consume_context_directives(
                project_name,
                story_id,
                directive_ids,
            )
        except Exception as exc:
            LOGGER.warning(
                "Failed to consume creative-session directives: session=%s error=%s",
                session_id,
                exc,
            )
            warnings.append(f"片段已保存，但导演注剩余次数更新失败：{exc}")

    try:
        current_profile = load_creative_profile(project_name, story_id) or {}
        update_creative_session(
            project_name,
            session_id,
            {
                "writing_guidance": guidance,
                "status": "active",
                "worldline_id": str(
                    current_profile.get("worldline_id")
                    or session.get("worldline_id")
                    or "main"
                ),
            },
            story_id=story_id,
        )
    except Exception as exc:
        LOGGER.warning(
            "Creative fragment persisted but session metadata update failed: "
            "session=%s error=%s",
            session_id,
            exc,
        )
        warnings.append(f"片段已保存，但会话设置更新失败：{exc}")
    summary_warning = maybe_refresh_session_summary(
        project_name,
        story_id,
        session_id,
    )
    if summary_warning:
        warnings.append(summary_warning)

    auto_extraction: dict = {}
    if branch["accept_fragment_id"] and session.get("auto_extract_mode") == "on_accept":
        try:
            auto_extraction = extract_fragment_knowledge(
                project_name,
                story_id,
                session_id,
                str(branch["accept_fragment_id"]),
            )
        except Exception as exc:
            warnings.append(f"上一片段已接受，但自动设定提炼失败：{exc}")

    completed_turn = {
        **turn,
        "status": "completed",
        "error_text": "",
    }
    result = {
        "success": True,
        "status": "completed",
        "session_id": session_id,
        "turn": completed_turn,
        "fragment": fragment,
        "context_assembly": assembly.model_dump(),
        "retrieval_hits": list(assembly.retrieval_hits),
        "auto_extraction": auto_extraction,
        "warnings": warnings,
    }
    try:
        # Keep正文 persistence and the conversational action ledger aligned for
        # every workflow caller, including non-UI integrations.  The import is
        # intentionally local because the action workflow reuses generation
        # helpers from this module.
        from novelforge.workflows.creative_actions import record_creative_generation_action

        record_creative_generation_action(
            project_name,
            story_id,
            session_id,
            user_message,
            result,
            action_type=branch["action_type"],
        )
    except Exception as exc:
        LOGGER.warning(
            "Creative fragment persisted but action ledger update failed: "
            "session=%s fragment=%s error=%s",
            session_id,
            fragment_id,
            exc,
        )
        warnings.append(f"片段已保存，但动作账本更新失败：{exc}")
    return result


def accept_writing_fragment(
    project_name: str,
    story_id: str,
    session_id: str,
    fragment_id: str,
    *,
    extract_if_enabled: bool = True,
) -> dict:
    bundle = _bundle_or_raise(project_name, story_id, session_id)
    fragment = accept_creative_fragment(
        project_name,
        session_id,
        fragment_id,
        story_id=story_id,
    )
    extraction: dict = {}
    warnings: list[str] = []
    if (
        extract_if_enabled
        and bundle.get("session", {}).get("auto_extract_mode") == "on_accept"
    ):
        try:
            extraction = extract_fragment_knowledge(
                project_name,
                story_id,
                session_id,
                fragment_id,
            )
        except Exception as exc:
            warnings.append(f"片段已接受，但自动设定提炼失败：{exc}")
    summary_warning = maybe_refresh_session_summary(
        project_name,
        story_id,
        session_id,
    )
    if summary_warning:
        warnings.append(summary_warning)
    return {
        "fragment": fragment,
        "extraction": extraction,
        "warnings": warnings,
    }


def select_writing_fragment_variant(
    project_name: str,
    story_id: str,
    session_id: str,
    fragment_id: str,
) -> dict:
    return select_creative_fragment_variant(
        project_name,
        session_id,
        fragment_id,
        story_id=story_id,
    )


def maybe_refresh_session_summary(
    project_name: str,
    story_id: str,
    session_id: str,
    *,
    force: bool = False,
) -> str:
    bundle = _bundle_or_raise(project_name, story_id, session_id)
    session = bundle.get("session", {}) or {}
    accepted, pending, pending_text, total_text = _summary_refresh_material(bundle)
    if not accepted:
        return ""
    if not force and (
        len(total_text) < SUMMARY_REFRESH_THRESHOLD_CHARS
        or len(pending) < SUMMARY_BATCH_MIN_FRAGMENTS
    ):
        return ""
    if not pending_text.strip():
        return ""
    try:
        with llm_usage_scope(
            project_name=project_name,
            story_id=story_id,
            task_id=session_id,
            operation="creative.summary",
            agent_role="summarizer",
        ):
            summary = call_llm(
                creative_session_summary_prompt(
                    str(session.get("rolling_summary") or ""),
                    pending_text,
                ),
                temperature=0.2,
            )
        update_creative_session(
            project_name,
            session_id,
            {
                "rolling_summary": str(summary or "").strip(),
                "summary_fragment_id": str(accepted[-1].get("fragment_id") or ""),
            },
            story_id=story_id,
        )
        return ""
    except Exception as exc:
        LOGGER.warning(
            "Failed to refresh creative-session summary: session=%s error=%s",
            session_id,
            exc,
        )
        return f"片段已保存，但会话滚动摘要更新失败：{exc}"


def extract_fragment_knowledge(
    project_name: str,
    story_id: str,
    session_id: str,
    fragment_id: str,
    *,
    stream_callback=None,
) -> dict:
    bundle = _bundle_or_raise(project_name, story_id, session_id)
    session = bundle.get("session", {}) or {}
    if str(session.get("status") or "") == "archived":
        raise ValueError("已归档的创作会话不能提炼知识。")
    fragments = _fragment_map(bundle)
    fragment = fragments.get(str(fragment_id or ""))
    if fragment is None:
        raise ValueError("创作片段不存在。")
    if str(fragment.get("status") or "") not in {"accepted", "finalized"}:
        raise ValueError("只有已接受片段可以提炼知识。")
    update_creative_fragment(
        project_name,
        fragment_id,
        {"extraction_status": "running"},
        story_id=story_id,
    )
    try:
        from novelforge.workflows.skills import extract_reference_knowledge

        extraction_step = extract_reference_knowledge(
            project_name,
            f"自由创作：{session.get('title') or session_id}",
            str(fragment.get("content") or ""),
            enabled_categories=[],
            extraction_mode="general",
            story_id=story_id,
            custom_instructions=(
                "这是用户已经接受的原创正文片段。只提取后续创作需要长期复用的稳定事实、"
                "角色状态变化、关系变化、世界规则、地点、物品、能力、时间线和明确风格；"
                "不要把临时动作、普通场景描写和未证实猜测保存为长期知识。"
                "canon_status 使用 user_override。"
            ),
            stream_callback=stream_callback,
        )
        extraction = (
            extraction_step.get("data", {}).get("knowledge_extraction", {})
            if isinstance(extraction_step, dict)
            else {}
        )
        items = extraction.get("items", []) if isinstance(extraction, dict) else []
        profile = load_creative_profile(project_name, story_id) or {}
        worldline_id = str(
            profile.get("worldline_id")
            or session.get("worldline_id")
            or "main"
        )
        worldline_label = str(
            profile.get("worldline_label")
            or worldline_id
            or "本项目主线"
        )
        source_title = f"自由创作：{session.get('title') or session_id}"
        candidates: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            category = str(normalized.get("category") or "")
            name = str(normalized.get("name") or "").strip()
            summary = str(normalized.get("summary") or "").strip()
            if not category or not name or not summary:
                continue
            digest = hashlib.sha256(
                f"{fragment_id}|{category}|{name}|{summary}".encode("utf-8")
            ).hexdigest()[:20]
            normalized.update({
                "pending_id": f"fragment_knowledge_{digest}",
                "story_id": story_id,
                "setting_scope": "story",
                "injection_policy": "retrieval",
                "scope": "project",
                "authority": "project",
                "source_title": source_title,
                "source_origin": "interactive_fragment",
                "source_segment_id": fragment_id,
                "source_segment_ids": [fragment_id],
                "source_segment_title": source_title,
                "source_segment_titles": [source_title],
                "canon_status": "user_override",
                "extraction_mode": "creative_fragment",
                "worldline_id": worldline_id,
                "worldline_label": worldline_label,
                "version_scope": "project_main",
                "status": "pending",
                "tags": list(dict.fromkeys([
                    *[
                        str(tag)
                        for tag in normalized.get("tags", [])
                        if str(tag).strip()
                    ],
                    "自由创作",
                    "片段提炼",
                ])),
            })
            evidence = normalized.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                normalized["evidence"] = [{
                    "source_title": source_title,
                    "quote": str(fragment.get("content") or "")[:160],
                    "note": "来自用户已接受的自由创作片段。",
                }]
            candidates.append(normalized)
        queued_count = queue_pending_knowledge_items(
            project_name,
            candidates,
            scope="project",
            authority="project",
            source_title=source_title,
            source_origin="interactive_fragment",
        )
        update_creative_fragment(
            project_name,
            fragment_id,
            {"extraction_status": "completed"},
            story_id=story_id,
        )
        return {
            "success": True,
            "status": "completed",
            "session_id": session_id,
            "fragment_id": fragment_id,
            "candidates": candidates,
            "candidate_ids": [
                str(item.get("pending_id") or "")
                for item in candidates
                if str(item.get("pending_id") or "")
            ],
            "queued_count": queued_count,
            "extraction_step": extraction_step,
        }
    except Exception:
        try:
            update_creative_fragment(
                project_name,
                fragment_id,
                {"extraction_status": "failed"},
                story_id=story_id,
            )
        except Exception as status_exc:
            LOGGER.warning(
                "Failed to record fragment extraction failure: fragment=%s error=%s",
                fragment_id,
                status_exc,
            )
        raise


def pending_knowledge_for_fragment(
    project_name: str,
    fragment_id: str,
) -> list[dict]:
    return [
        item
        for item in load_pending_knowledge_items(project_name)
        if str(item.get("source_segment_id") or "") == str(fragment_id or "")
        or str(fragment_id or "") in {
            str(value)
            for value in item.get("source_segment_ids", [])
            if str(value)
        }
    ]


def compile_session_text(
    bundle: dict,
) -> str:
    fragments = [
        fragment
        for fragment in active_fragment_chain(bundle)
        if str(fragment.get("status") or "") == "accepted"
    ]
    if not fragments:
        return ""
    return "\n\n".join(
        str(fragment.get("content") or "").strip()
        for fragment in fragments
        if str(fragment.get("content") or "").strip()
    )


def save_writing_session_as_chapter(
    project_name: str,
    story_id: str,
    session_id: str,
    chapter_no: int,
    *,
    append_to_existing: bool = False,
    smooth_transitions: bool = False,
    target_word_count: str = "",
    stream_callback=None,
) -> dict:
    bundle = _bundle_or_raise(project_name, story_id, session_id)
    if str(bundle.get("session", {}).get("status") or "") == "archived":
        raise ValueError("已归档的创作会话不能汇编为章节。")
    normalized_chapter_no = int(chapter_no)
    if normalized_chapter_no < 1:
        raise ValueError("章节编号必须大于等于 1。")
    compiled = compile_session_text(bundle)
    if not compiled.strip():
        raise ValueError("当前会话还没有已接受片段。")
    existing = load_chapter(project_name, normalized_chapter_no, story_id=story_id)
    if existing.strip() and not append_to_existing:
        raise FileExistsError("目标章节已有正文；请选择其它章节编号或明确使用追加模式。")
    source_text = (
        f"{existing.rstrip()}\n\n{compiled}"
        if existing.strip() and append_to_existing
        else compiled
    )
    final_text = source_text
    if smooth_transitions:
        with llm_usage_scope(
            project_name=project_name,
            story_id=story_id,
            task_id=session_id,
            operation="creative.compile",
            agent_role="editor",
        ):
            final_text = call_llm(
                compile_creative_fragments_prompt(source_text, target_word_count),
                stream_callback=stream_callback,
            )
        if not str(final_text or "").strip():
            raise RuntimeError("模型没有返回整理后的章节正文。")
    save_chapter(
        project_name,
        normalized_chapter_no,
        str(final_text).strip(),
        story_id=story_id,
    )
    accepted_ids = {
        str(fragment.get("fragment_id") or "")
        for fragment in active_fragment_chain(bundle)
        if str(fragment.get("status") or "") == "accepted"
    }
    finalize_creative_session(
        project_name,
        session_id,
        sorted(accepted_ids),
        normalized_chapter_no,
        story_id=story_id,
    )
    return {
        "success": True,
        "status": "completed",
        "session_id": session_id,
        "chapter_no": normalized_chapter_no,
        "append_to_existing": bool(append_to_existing),
        "smooth_transitions": bool(smooth_transitions),
        "fragment_count": len(accepted_ids),
        "chapter": str(final_text).strip(),
    }
