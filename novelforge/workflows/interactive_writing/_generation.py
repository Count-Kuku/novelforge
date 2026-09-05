"""Interactive writing: query, preflight, preview and fragment generation."""

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
from novelforge.workflows.cancellation import raise_if_cancelled


LOGGER = logging.getLogger("novelforge.interactive_writing")
RECENT_FRAGMENT_CONTEXT_CHARS = 9_000
SUMMARY_REFRESH_THRESHOLD_CHARS = 12_000
SUMMARY_BATCH_MIN_FRAGMENTS = 3



from novelforge.workflows import interactive_writing as _iw

def build_writing_session_query(
    bundle: dict,
    user_message: str,
    *,
    context_head_id: str | None,
) -> str:
    session = bundle.get("session", {}) or {}
    chain = _iw.active_fragment_chain(bundle, head_fragment_id=context_head_id)
    recent = _iw._recent_fragment_text(chain)
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
        branch = _iw._resolve_generation_branch(
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
        accepted, pending, pending_text, total_text = _iw._summary_refresh_material(
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
            fragment = _iw._fragment_map(active_bundle).get(accept_fragment_id, {})
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
    bundle = _iw._bundle_or_raise(project_name, story_id, session_id)
    branch = _iw._resolve_generation_branch(
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
            *_iw._session_context_blocks(
                bundle,
                context_head_id=branch["context_head_id"],
            ),
            *list(turn_attachment_blocks or []),
        ],
        allowed_scopes=["project", "canon", "reference"],
        retrieval_profile="drafting",
        context_budget=context_budget,
        retrieval_session_id=session_id,
        # 自由创作正文默认开启实体聚焦（refactor 2 P1 接线，遗留 #5 收口）。
        enable_entity_planning=True,
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
    cancel_check=None,
) -> dict:
    raise_if_cancelled(cancel_check)
    require_operation_capabilities("creative_writing", action="对话式创作")
    bundle = _iw._bundle_or_raise(project_name, story_id, session_id)
    session = bundle.get("session", {}) or {}
    branch = _iw._resolve_generation_branch(
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
        raise_if_cancelled(cancel_check)
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
            turn_attachment_blocks=_iw._claimed_attachment_blocks(
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
        raise_if_cancelled(cancel_check)
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
        raise_if_cancelled(cancel_check)
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
        raise_if_cancelled(cancel_check)
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
                "created_at": _iw._now(),
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
    summary_warning = _iw.maybe_refresh_session_summary(
        project_name,
        story_id,
        session_id,
    )
    if summary_warning:
        warnings.append(summary_warning)

    auto_extraction: dict = {}
    if branch["accept_fragment_id"] and session.get("auto_extract_mode") == "on_accept":
        try:
            auto_extraction = _iw.extract_fragment_knowledge(
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
