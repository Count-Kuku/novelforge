"""Shared retrieval models, constants, and low-level helpers."""

from __future__ import annotations

from novelforge.services import retrieval as _retrieval_api

import json
import logging
import math
import os
import re
from collections import Counter
from datetime import datetime
from hashlib import sha256

from novelforge.core.llm import get_embedding
from novelforge.services.memory import (
    load_creative_profile_discussion_artifact,
    load_chapter_discussion_artifact,
    load_arc_discussion_artifact,
    load_arc_chapter_plan,
    load_arc_metadata,
    load_arc_outline,
    load_analysis_report,
    load_chapter,
    load_chapter_outline,
    load_chapter_outline_metadata,
    load_character_entities,
    load_entity_aliases,
    load_setting_entities,
    load_memory,
    load_outline,
    load_outline_discussion_artifact,
    load_story_chapter_summaries,
    load_volume_outline,
    load_volume_metadata,
    load_review,
    load_review_json,
    load_volume_discussion_artifact,
    load_conflict_resolutions,
    load_retrieval_feedback,
    load_evaluation_report,
    load_evaluation_json,
    load_knowledge_base,
    load_llm_settings,
    list_asset_payload_records,
    list_arcs,
    list_volumes,
    load_retrieval_manifest,
    load_retrieval_vectors,
    list_retrieval_source_files,
    list_stories,
    project_path,
    retrieval_sources_path,
    save_retrieval_manifest,
    save_retrieval_vectors,
    sync_retrieval_source_file_record,
    search_project_retrieval_fts,
    story_path,
)
from novelforge.core.schemas import RetrievalChunk, RetrievalDocument, RetrievalHit, RetrievalIndexManifest, RetrievalVectorStore


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\-]{2,}|[\u4e00-\u9fff]+")
MAX_CJK_NGRAM = 4
CJK_STOP_TOKENS = {
    "一个",
    "一些",
    "这个",
    "那个",
    "这些",
    "那些",
    "什么",
    "怎么",
    "如何",
    "是否",
    "不是",
    "没有",
    "存在",
    "检索",
    "查询",
}
MAX_ALIAS_EXPANSION_GROUPS = 12
MAX_ALIAS_EXPANDED_TERMS = 80
DEFAULT_WORLDLINE_ID = "main"
DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 150
DEFAULT_TOP_K = 6
DEFAULT_EMBEDDING_MODEL = os.getenv("LLM_EMBEDDING_MODEL") or os.getenv("EMBEDDING_MODEL") or "text-embedding-3-small"
GLOBAL_WORLDLINE_IDS = {"", "all", "global", "shared", "common", "canon", "unknown"}
AUTHORITY_WEIGHTS = {
    "project": 2.0,
    "official": 1.5,
    "curated": 1.0,
    "community": 0.5,
    "unknown": 0.0,
}
REFERENCE_FOCUS_SOURCE_MAP = {
    "角色": ["entity_character_card", "entity_alias_group", "knowledge_characters", "memory_character"],
    "世界观": ["entity_setting_card", "knowledge_world_rules", "knowledge_locations", "knowledge_organizations", "memory_world"],
    "剧情事件": ["knowledge_timeline_events", "memory_timeline"],
    "道具能力": ["entity_setting_card", "knowledge_items", "knowledge_abilities"],
    "时间线": ["knowledge_timeline_events", "memory_timeline"],
    "写作风格": ["knowledge_writing_style", "knowledge_dialogue_style", "knowledge_narrative_techniques"],
    "硬性约束": ["entity_setting_card", "knowledge_constraints"],
}

KNOWLEDGE_SOURCE_TYPES = [
    "knowledge_characters",
    "knowledge_items",
    "knowledge_abilities",
    "knowledge_world_rules",
    "knowledge_locations",
    "knowledge_organizations",
    "knowledge_timeline_events",
    "knowledge_relationships",
    "knowledge_writing_style",
    "knowledge_dialogue_style",
    "knowledge_narrative_techniques",
    "knowledge_constraints",
]


def _active_embedding_model_name() -> str:
    try:
        model_name = str(load_llm_settings().get("embedding_model_name") or DEFAULT_EMBEDDING_MODEL).strip()
    except Exception:
        model_name = DEFAULT_EMBEDDING_MODEL
    return model_name or DEFAULT_EMBEDDING_MODEL

STORY_SCOPED_SOURCE_TYPES = {
    "outline",
    "chapter_summary",
    "creative_profile_discussion",
    "outline_discussion",
    "volume_outline",
    "volume_discussion",
    "arc_outline",
    "arc_discussion",
    "arc_chapter_plan",
    "chapter_outline",
    "chapter_discussion",
    "chapter_content",
    "review_summary",
    "review_issue",
    "review_characters_check",
    "review_world_check",
    "review_timeline_check",
    "review_foreshadowing_check",
    "review_markdown",
    "evaluation_chapter",
}

RETRIEVAL_TASK_PROFILES = {
    "creative_profile_discussion": {
        "top_k": 8,
        "source_types": [
            "creative_profile_discussion",
            "memory_world",
            "memory_au_rule",
            "memory_character",
            "entity_setting_card",
            "entity_character_card",
            "entity_alias_group",
            "external_source",
            "conflict_resolution",
            "knowledge_world_rules",
            "knowledge_constraints",
            "knowledge_writing_style",
            "knowledge_dialogue_style",
            "knowledge_narrative_techniques",
        ],
    },
    "outline_discussion": {
        "top_k": 9,
        "source_types": [
            "outline",
            "outline_discussion",
            "memory_character",
            "memory_world",
            "memory_au_rule",
            "memory_relationship",
            "memory_timeline",
            "memory_foreshadowing",
            "memory_active_constraint",
            "entity_character_card",
            "entity_setting_card",
            "entity_alias_group",
            "external_source",
            "conflict_resolution",
            "knowledge_characters",
            "knowledge_world_rules",
            "knowledge_timeline_events",
            "knowledge_relationships",
            "knowledge_constraints",
        ],
    },
    "volume_discussion": {
        "top_k": 8,
        "source_types": [
            "outline",
            "outline_discussion",
            "volume_outline",
            "volume_discussion",
            "chapter_summary",
            "memory_character",
            "memory_world",
            "memory_relationship",
            "memory_timeline",
            "memory_foreshadowing",
            "memory_active_constraint",
            "entity_character_card",
            "entity_setting_card",
            "external_source",
            "knowledge_characters",
            "knowledge_world_rules",
            "knowledge_timeline_events",
            "knowledge_relationships",
            "knowledge_constraints",
        ],
    },
    "arc_discussion": {
        "top_k": 8,
        "source_types": [
            "outline",
            "volume_outline",
            "volume_discussion",
            "arc_outline",
            "arc_discussion",
            "arc_chapter_plan",
            "chapter_summary",
            "chapter_outline",
            "memory_character",
            "memory_relationship",
            "memory_timeline",
            "memory_foreshadowing",
            "memory_active_constraint",
            "entity_character_card",
            "entity_setting_card",
            "external_source",
            "knowledge_characters",
            "knowledge_timeline_events",
            "knowledge_relationships",
            "knowledge_constraints",
        ],
    },
    "chapter_discussion": {
        "top_k": 8,
        "source_types": [
            "outline",
            "volume_outline",
            "volume_discussion",
            "arc_outline",
            "arc_discussion",
            "chapter_discussion",
            "chapter_summary",
            "chapter_outline",
            "memory_character",
            "memory_relationship",
            "memory_timeline",
            "memory_foreshadowing",
            "memory_active_constraint",
            "entity_character_card",
            "entity_setting_card",
            "external_source",
            "knowledge_characters",
            "knowledge_timeline_events",
            "knowledge_relationships",
            "knowledge_constraints",
        ],
    },
    "outline_generation": {
        "top_k": 10,
        "source_types": [
            "outline",
            "creative_profile_discussion",
            "outline_discussion",
            "memory_character",
            "memory_world",
            "memory_au_rule",
            "memory_relationship",
            "memory_timeline",
            "memory_foreshadowing",
            "memory_active_constraint",
            "entity_character_card",
            "entity_setting_card",
            "entity_alias_group",
            "external_source",
            "conflict_resolution",
        ] + KNOWLEDGE_SOURCE_TYPES,
    },
    "chapter_planning": {
        "top_k": 8,
        "source_types": [
            "outline",
            "creative_profile_discussion",
            "outline_discussion",
            "volume_outline",
            "volume_discussion",
            "arc_outline",
            "arc_discussion",
            "arc_chapter_plan",
            "chapter_discussion",
            "chapter_summary",
            "chapter_outline",
            "memory_character",
            "memory_relationship",
            "memory_timeline",
            "memory_foreshadowing",
            "memory_active_constraint",
            "entity_character_card",
            "entity_setting_card",
            "external_source",
            "conflict_resolution",
        ] + KNOWLEDGE_SOURCE_TYPES,
    },
    "drafting": {
        "top_k": 8,
        "source_types": [
            "chapter_outline",
            "chapter_discussion",
            "chapter_summary",
            "memory_character",
            "memory_relationship",
            "memory_active_constraint",
            "entity_character_card",
            "entity_alias_group",
            "external_source",
            "knowledge_characters",
            "knowledge_relationships",
            "knowledge_writing_style",
            "knowledge_dialogue_style",
            "knowledge_narrative_techniques",
            "knowledge_constraints",
        ],
    },
    "review": {
        "top_k": 9,
        "source_types": [
            "chapter_outline",
            "chapter_discussion",
            "chapter_summary",
            "chapter_content",
            "memory_character",
            "memory_world",
            "memory_relationship",
            "memory_timeline",
            "memory_foreshadowing",
            "memory_active_constraint",
            "entity_character_card",
            "entity_setting_card",
            "external_source",
            "conflict_resolution",
            "review_issue",
        ] + KNOWLEDGE_SOURCE_TYPES,
    },
}

REFERENCE_STRENGTH_PARAMS = {
    "轻参考": {"top_k": 3, "mode": "lexical", "scopes": None, "source_types": None},
    "中参考": {"top_k": 6, "mode": "hybrid", "scopes": None, "source_types": None},
    "强参考": {"top_k": 10, "mode": "hybrid", "scopes": None, "source_types": None},
    "严格原作": {"top_k": 15, "mode": "hybrid", "scopes": ["canon", "reference"], "source_types": None},
    "主要参考文风": {"top_k": 8, "mode": "hybrid", "scopes": None,
                     "source_types": ["knowledge_writing_style", "knowledge_dialogue_style", "knowledge_narrative_techniques"]},
}

STRUCTURED_SOURCE_TYPES = {
    "memory_character",
    "memory_world",
    "memory_au_rule",
    "memory_relationship",
    "memory_timeline",
    "memory_foreshadowing",
    "memory_active_constraint",
    "chapter_summary",
    "review_summary",
    "review_issue",
    "review_characters_check",
    "review_world_check",
    "review_timeline_check",
    "review_foreshadowing_check",
    "creative_profile_discussion",
    "outline_discussion",
    "volume_discussion",
    "arc_discussion",
    "chapter_discussion",
    "conflict_resolution",
}


def _normalize_whitespace(text: str) -> str:
    """Normalize inline whitespace without destroying document structure.

    Markdown headings and paragraph boundaries are semantic input to the
    chunker.  Collapsing every whitespace character into a space previously
    turned ``# Summary``/``# Details`` into one heading and produced an empty
    external-source index.
    """

    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).rstrip() for line in normalized.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw_token in TOKEN_PATTERN.findall(text):
        token = raw_token.lower()
        if not token:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            if len(token) >= 2 and token not in CJK_STOP_TOKENS:
                tokens.append(token)
            max_ngram = min(MAX_CJK_NGRAM, len(token))
            for ngram_size in range(2, max_ngram + 1):
                for start in range(0, len(token) - ngram_size + 1):
                    ngram = token[start:start + ngram_size]
                    if ngram not in CJK_STOP_TOKENS:
                        tokens.append(ngram)
        elif len(token) >= 2:
            tokens.append(token)
    return tokens


def _split_long_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks = []
    start = 0
    step = max(chunk_size - overlap, 1)
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(cleaned):
            break
        start += step
    return chunks


def _split_markdown_sections(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_title = ""
    current_lines: list[str] = []
    fence = ""

    for line in lines:
        stripped = line.strip()
        fence_match = re.match(r"^(`{3,}|~{3,})", stripped)
        if fence_match:
            marker = fence_match.group(1)[0]
            if not fence:
                fence = marker
            elif fence == marker:
                fence = ""
            current_lines.append(line)
            continue
        if not fence and re.match(r"^ {0,3}#{1,6}\s+", line):
            if current_title or current_lines:
                sections.append((current_title, current_lines))
            current_title = stripped.lstrip("#").strip()
            current_lines = []
            continue
        current_lines.append(line)

    if current_title or current_lines:
        sections.append((current_title, current_lines))

    result = []
    for title, section_lines in sections:
        body = "\n".join(section_lines).strip()
        if title or body:
            result.append((title, body))
    return result


def _split_paragraph_blocks(text: str) -> list[str]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n+", text) if block.strip()]
    return blocks


def _chunk_by_paragraphs(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    blocks = _split_paragraph_blocks(text)
    if not blocks:
        return _split_long_text(text, chunk_size=chunk_size, overlap=overlap)

    chunks = []
    current = []
    current_length = 0

    for block in blocks:
        block_length = len(block)
        if block_length > chunk_size:
            if current:
                combined = "\n\n".join(current).strip()
                if combined:
                    chunks.append(combined)
                current = []
                current_length = 0
            chunks.extend(_split_long_text(block, chunk_size=chunk_size, overlap=overlap))
            continue
        if current and current_length + block_length + 2 > chunk_size:
            combined = "\n\n".join(current).strip()
            if combined:
                chunks.append(combined)

            overlap_text = combined[-min(max(int(overlap or 0), 0), chunk_size):].strip() if overlap > 0 else ""
            current = [overlap_text] if overlap_text and len(overlap_text) + 2 + block_length <= chunk_size else []
            current_length = len(overlap_text) if current else 0

        current.append(block)
        current_length += block_length + 2

    if current:
        combined = "\n\n".join(current).strip()
        if combined:
            chunks.append(combined)

    deduplicated_adjacent: list[str] = []
    for chunk in chunks:
        if not deduplicated_adjacent or chunk != deduplicated_adjacent[-1]:
            deduplicated_adjacent.append(chunk)
    return deduplicated_adjacent or _split_long_text(text, chunk_size=chunk_size, overlap=overlap)


def _chunk_markdown_sections(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[tuple[str, str]]:
    sections = _split_markdown_sections(text)
    if not sections:
        return [("", chunk) for chunk in _chunk_by_paragraphs(text, chunk_size=chunk_size, overlap=overlap)]

    result: list[tuple[str, str]] = []
    for title, body in sections:
        if not body.strip():
            continue
        paragraph_chunks = _chunk_by_paragraphs(body, chunk_size=chunk_size, overlap=overlap)
        if paragraph_chunks:
            result.extend([(title, chunk) for chunk in paragraph_chunks])
        else:
            result.append((title, body.strip()))
    return result


def _document_id(source_type: str, project_name: str, identifier: str) -> str:
    return f"{project_name}:{source_type}:{identifier}"


def _make_document(
    project_name: str,
    source_type: str,
    identifier: str,
    title: str,
    content: str,
    *,
    scope: str = "project",
    chapter_no: int | None = None,
    path: str = "",
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> RetrievalDocument | None:
    normalized_content = _normalize_whitespace(content)
    if not normalized_content:
        return None
    return RetrievalDocument(
        doc_id=_document_id(source_type, project_name, identifier),
        project_name=project_name,
        source_type=source_type,
        scope=scope,
        title=title,
        content=normalized_content,
        chapter_no=chapter_no,
        path=path,
        tags=tags or [],
        metadata=metadata or {},
    )


def _infer_authority(scope: str, metadata: dict | None) -> str:
    if isinstance(metadata, dict):
        authority = str(metadata.get("authority", "")).strip().lower()
        if authority:
            return authority
    if scope == "project":
        return "project"
    return "unknown"


def _chapter_no_from_asset_record(record: dict) -> int | None:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    try:
        value = metadata.get("chapter_no")
        if value is not None:
            return int(value)
    except (TypeError, ValueError):
        pass
    match = re.search(r"chapter_(\d+)", str(record.get("logical_key") or record.get("relative_path") or ""))
    return int(match.group(1)) if match else None
