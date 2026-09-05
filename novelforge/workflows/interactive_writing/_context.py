"""Interactive writing: context block assembly and branch resolution."""

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

def _session_context_blocks(
    bundle: dict,
    *,
    context_head_id: str | None,
) -> list[dict]:
    session = bundle.get("session", {}) or {}
    chain = _iw.active_fragment_chain(bundle, head_fragment_id=context_head_id)
    recent_text = _iw._recent_fragment_text(chain)
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
    fragments = _iw._fragment_map(bundle)
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
