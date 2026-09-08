"""Interactive writing: session creation and fragment chain."""

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
    branch_id: str | None = None,
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
        "branch_id": str(branch_id or ""),
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
