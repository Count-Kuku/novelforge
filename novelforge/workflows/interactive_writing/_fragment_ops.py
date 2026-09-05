"""Interactive writing: fragment acceptance, extraction and compilation."""

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

def accept_writing_fragment(
    project_name: str,
    story_id: str,
    session_id: str,
    fragment_id: str,
    *,
    extract_if_enabled: bool = True,
) -> dict:
    bundle = _iw._bundle_or_raise(project_name, story_id, session_id)
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
    bundle = _iw._bundle_or_raise(project_name, story_id, session_id)
    session = bundle.get("session", {}) or {}
    accepted, pending, pending_text, total_text = _iw._summary_refresh_material(bundle)
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
    bundle = _iw._bundle_or_raise(project_name, story_id, session_id)
    session = bundle.get("session", {}) or {}
    if str(session.get("status") or "") == "archived":
        raise ValueError("已归档的创作会话不能提炼知识。")
    fragments = _iw._fragment_map(bundle)
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
        # refactor 2 P4（D10）：接受片段提炼的候选自动确认，不再堆积待人工审核。
        # 入队函数返回 int 不返回 ids —— pending_ids 从 candidates 的 pending_id 键提取。
        auto_confirm: dict = {}
        pending_ids_for_confirm = [
            str(item.get("pending_id") or "") for item in candidates if str(item.get("pending_id") or "")
        ]
        if pending_ids_for_confirm:
            try:
                from novelforge.workflows.source_workflows import auto_confirm_pending_items_without_risk

                auto_confirm = auto_confirm_pending_items_without_risk(
                    project_name,
                    pending_ids_for_confirm,
                    source_type="interactive_fragment",
                    source_title=source_title,
                    note="接受创作片段后自动提炼并确认",
                )
            except Exception as exc:
                LOGGER.warning("自动确认创作片段提炼候选失败：fragment=%s error=%s", fragment_id, exc)
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
            "auto_confirm": auto_confirm,
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
        for fragment in _iw.active_fragment_chain(bundle)
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
    bundle = _iw._bundle_or_raise(project_name, story_id, session_id)
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
        for fragment in _iw.active_fragment_chain(bundle)
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
