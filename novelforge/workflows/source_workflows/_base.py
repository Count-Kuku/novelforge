import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from uuid import uuid4

from novelforge.domain.extraction_presets import (
    KNOWLEDGE_CONSOLIDATION_MODE_LABELS,
    KNOWLEDGE_EXTRACTION_EXPERT_PRESETS,
)
from novelforge.domain.knowledge_quality import (
    build_pending_issue_map,
    build_pending_knowledge_quality_issues,
    details_conflicts,
    fact_conflicts,
    merge_list_values,
    normalize_knowledge_match_name,
)
from novelforge.domain.knowledge_workflows import (
    evaluate_pending_auto_review_decision,
    safe_confidence,
    summarize_item_evidence,
)
from novelforge.domain.reference_chunking import split_reference_text
from novelforge.domain.ingestion_workbench import (
    build_ingestion_workbench_summary,
    summarize_long_reference_resume_state,
)
from novelforge.services.memory import (
    confirm_pending_knowledge_items_with_records,
    list_long_reference_batches,
    list_source_ingestion_tasks,
    list_retrieval_source_files,
    load_auto_review_policy,
    load_entity_aliases,
    load_extraction_plan_templates,
    load_knowledge_base,
    load_pending_knowledge_items,
    load_source_revisions,
    load_knowledge_storage_health,
    queue_pending_knowledge_items,
    retrieval_sources_path,
    save_extraction_plan_templates,
    save_long_reference_batch,
)
from novelforge.services.retrieval import (
    build_structured_external_source_payload,
    ingest_external_source_file,
    rebuild_retrieval_assets,
)
from novelforge.core.schemas import KNOWLEDGE_CATEGORY_LABELS, label_knowledge_category
from novelforge.workflows.skills import consolidate_extracted_knowledge, extract_reference_knowledge, build_pending_knowledge_from_reference_extraction, recall_missed_knowledge

LOGGER = logging.getLogger("novelforge.source_workflows")

import novelforge.workflows.source_workflows as _sw

"""Shared helpers, labels, and text fingerprinting for source workflows."""

def _safe_stream_emit(stream_callback, text: str) -> None:
    if not stream_callback:
        return
    try:
        stream_callback(text)
    except Exception as exc:
        if getattr(exc, "cancel_generation", False):
            raise
        LOGGER.warning("Stream callback failed while emitting workflow marker: %s", exc, exc_info=True)


SCOPE_LABELS = {
    "project": "项目资料",
    "canon": "原作资料",
    "reference": "参考资料",
}

AUTHORITY_LABELS = {
    "project": "项目设定",
    "official": "官方资料",
    "curated": "人工整理",
    "community": "社区资料",
    "unknown": "未标明",
}

DEFAULT_WORLDLINE_ID = "main"
DEFAULT_WORLDLINE_LABEL = "本项目主线"


def derive_worldline_id(source_id: str | None) -> str:
    """从 source_id 确定性派生独立世界线 id（D10/D16）。

    每个独立原著 = 独立 worldline_id，避免多源同名实体撞同一 entity_id（F10）。
    用 source_id（不可变）而非标题/slug（可变）派生，保证改名不导致 entity_id 全量重算（D16）。
    """
    clean = str(source_id or "").strip()
    if not clean:
        return DEFAULT_WORLDLINE_ID
    digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()[:12]
    return f"world_{digest}"

CHAPTER_TITLE_PATTERN = re.compile(
    r"^\s*(?:第\s*[0-9零一二三四五六七八九十百千万两〇]+\s*[章节卷回部篇]|Chapter\s+\d+|CHAPTER\s+\d+|番外|楔子|序章|终章).*$"
)


def label_scope(value: str) -> str:
    return SCOPE_LABELS.get(str(value or ""), str(value or "未知范围"))


def label_authority(value: str) -> str:
    return AUTHORITY_LABELS.get(str(value or ""), str(value or "未标明"))
