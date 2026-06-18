from __future__ import annotations

import json
import logging
import math
import os
import re
from collections import Counter
from datetime import datetime

from llm import get_embedding
from memory import (
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
    list_arcs,
    list_volumes,
    load_retrieval_manifest,
    load_retrieval_vectors,
    list_stories,
    project_path,
    retrieval_sources_path,
    save_retrieval_manifest,
    save_retrieval_vectors,
    story_path,
)
from schemas import RetrievalChunk, RetrievalDocument, RetrievalHit, RetrievalIndexManifest, RetrievalVectorStore


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
    return re.sub(r"\s+", " ", text).strip()


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

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
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
        if current and current_length + block_length + 2 > chunk_size:
            combined = "\n\n".join(current).strip()
            if combined:
                chunks.append(combined)

            if overlap > 0 and current:
                overlap_blocks = []
                overlap_length = 0
                for item in reversed(current):
                    item_length = len(item)
                    if overlap_blocks and overlap_length + item_length > overlap:
                        break
                    overlap_blocks.insert(0, item)
                    overlap_length += item_length
                current = overlap_blocks[:]
                current_length = sum(len(item) for item in current)
            else:
                current = []
                current_length = 0

        current.append(block)
        current_length += block_length + 2

    if current:
        combined = "\n\n".join(current).strip()
        if combined:
            chunks.append(combined)

    return chunks or _split_long_text(text, chunk_size=chunk_size, overlap=overlap)


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


def _documents_from_memory(project_name: str) -> list[RetrievalDocument]:
    memory = load_memory(project_name)
    documents: list[RetrievalDocument] = []

    for index, item in enumerate(memory.get("characters", []), start=1):
        doc = _make_document(
            project_name,
            "memory_character",
            str(index),
            f"Character {index}",
            str(item),
            tags=["character"],
            metadata={"memory_field": "characters", "authority": "project"},
        )
        if doc:
            documents.append(doc)

    canon_mode = str(memory.get("canon_mode", "")).strip()
    if canon_mode:
        doc = _make_document(
            project_name,
            "memory_world",
            "canon_mode",
            "Canon Mode",
            canon_mode,
            tags=["canon_mode", "world"],
            metadata={"memory_field": "canon_mode", "authority": "project"},
        )
        if doc:
            documents.append(doc)

    for index, item in enumerate(memory.get("au_rules", []), start=1):
        doc = _make_document(
            project_name,
            "memory_au_rule",
            str(index),
            f"架空规则 {index}",
            str(item),
            tags=["au_rule"],
            metadata={"memory_field": "au_rules", "authority": "project"},
        )
        if doc:
            documents.append(doc)

    for index, item in enumerate(memory.get("relationships", []), start=1):
        doc = _make_document(
            project_name,
            "memory_relationship",
            str(index),
            f"Relationship {index}",
            str(item),
            tags=["relationship"],
            metadata={"memory_field": "relationships", "authority": "project"},
        )
        if doc:
            documents.append(doc)

    for field_name, source_type, tag in [
        ("world", "memory_world", "world"),
        ("timeline", "memory_timeline", "timeline"),
        ("foreshadowing", "memory_foreshadowing", "foreshadowing"),
    ]:
        for index, item in enumerate(memory.get(field_name, []), start=1):
            doc = _make_document(
                project_name,
                source_type,
                str(index),
                f"{field_name.title()} {index}",
                str(item),
                tags=[tag],
                metadata={"memory_field": field_name, "authority": "project"},
            )
            if doc:
                documents.append(doc)

    for item in memory.get("chapter_summaries", []):
        if not isinstance(item, dict):
            continue
        chapter_no = item.get("chapter_no")
        summary = item.get("summary", "")
        if not summary:
            continue
        doc = _make_document(
            project_name,
            "chapter_summary",
            str(chapter_no),
            f"Chapter {chapter_no:03d} Summary" if isinstance(chapter_no, int) else "Chapter Summary",
            summary,
            chapter_no=chapter_no if isinstance(chapter_no, int) else None,
            tags=["summary"],
            metadata={"memory_field": "chapter_summaries", "authority": "project"},
        )
        if doc:
            documents.append(doc)

    for index, item in enumerate(memory.get("active_constraints", []), start=1):
        doc = _make_document(
            project_name,
            "memory_active_constraint",
            str(index),
            f"Active Constraint {index}",
            str(item),
            tags=["constraint"],
            metadata={"memory_field": "active_constraints", "authority": "project"},
        )
        if doc:
            documents.append(doc)

    for field_name, source_type, tag in [
        ("locations", "memory_location", "location"),
        ("organizations", "memory_organization", "organization"),
        ("power_systems", "memory_power_system", "power_system"),
    ]:
        for index, item in enumerate(memory.get(field_name, []), start=1):
            doc = _make_document(
                project_name,
                source_type,
                str(index),
                f"{field_name.title()} {index}",
                str(item),
                tags=[tag],
                metadata={"memory_field": field_name, "authority": "project"},
            )
            if doc:
                documents.append(doc)

    for index, item in enumerate(memory.get("relationship_graph", []), start=1):
        if isinstance(item, dict):
            content = f"{item.get('source', '')} -> {item.get('target', '')}: {item.get('relation', '')}"
        else:
            content = str(item)
        doc = _make_document(
            project_name,
            "memory_relationship_graph",
            str(index),
            f"Relationship Graph {index}",
            content,
            tags=["relationship_graph"],
            metadata={"memory_field": "relationship_graph", "authority": "project"},
        )
        if doc:
            documents.append(doc)

    return documents


def _knowledge_item_retrieval_metadata(category: str, item: dict) -> dict:
    return {
        "knowledge_category": category,
        "authority": str(item.get("authority") or "project"),
        "source_title": str(item.get("source_title") or ""),
        "source_origin": str(item.get("source_origin") or ""),
        "confidence": item.get("confidence", 0.7),
        "status": str(item.get("status") or "confirmed"),
        "canon_status": str(item.get("canon_status") or "unknown"),
        "setting_scope": str(item.get("setting_scope") or ""),
        "setting_role": str(item.get("setting_role") or ""),
        "setting_field": str(item.get("setting_field") or ""),
        "story_id": str(item.get("story_id") or ""),
        "injection_policy": str(item.get("injection_policy") or ""),
        "version_scope": str(item.get("version_scope") or ""),
        "worldline_id": str(item.get("worldline_id") or ""),
        "worldline_label": str(item.get("worldline_label") or ""),
    }


def _knowledge_metadata_by_doc_id(project_name: str) -> dict[str, dict]:
    knowledge_base = load_knowledge_base(project_name)
    metadata_by_doc_id: dict[str, dict] = {}
    for category, items in knowledge_base.items():
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            doc_id = _document_id(f"knowledge_{category}", project_name, str(item.get("id") or index))
            metadata_by_doc_id[doc_id] = _knowledge_item_retrieval_metadata(category, item)
    return metadata_by_doc_id


def _documents_from_knowledge(project_name: str) -> list[RetrievalDocument]:
    knowledge_base = load_knowledge_base(project_name)
    documents: list[RetrievalDocument] = []

    for category, items in knowledge_base.items():
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip() or f"{category}_{index:04d}"
            summary = str(item.get("summary", "")).strip()
            details = item.get("details", {}) if isinstance(item.get("details"), dict) else {}
            evidence = item.get("evidence", []) if isinstance(item.get("evidence"), list) else []
            detail_lines = [f"{key}: {value}" for key, value in details.items() if str(value).strip()]
            evidence_lines = []
            for evidence_item in evidence[:5]:
                if not isinstance(evidence_item, dict):
                    continue
                quote = str(evidence_item.get("quote", "") or evidence_item.get("note", "")).strip()
                if quote:
                    evidence_lines.append(f"evidence: {quote}")
            content = "\n".join([
                f"name: {name}",
                f"summary: {summary}",
                *detail_lines,
                *evidence_lines,
            ])
            doc = _make_document(
                project_name,
                f"knowledge_{category}",
                str(item.get("id") or index),
                name,
                content,
                scope=str(item.get("scope") or "project"),
                path=str(project_path(project_name) / "knowledge" / f"{category}.json"),
                tags=[str(tag) for tag in item.get("tags", []) if str(tag).strip()] if isinstance(item.get("tags"), list) else [],
                metadata=_knowledge_item_retrieval_metadata(category, item),
            )
            if doc:
                documents.append(doc)

    return documents


def _documents_from_character_entities(project_name: str) -> list[RetrievalDocument]:
    documents: list[RetrievalDocument] = []
    for index, card in enumerate(load_character_entities(project_name), start=1):
        if not isinstance(card, dict):
            continue
        name = str(card.get("name", "")).strip() or f"角色实体卡 {index}"
        profile = card.get("profile", {}) if isinstance(card.get("profile"), dict) else {}
        profile_lines = [f"{key}: {value}" for key, value in profile.items() if str(value).strip()]
        list_fields = [
            ("relationships", "relationship"),
            ("abilities_and_items", "ability_or_item"),
            ("dialogue_style", "dialogue_style"),
            ("constraints", "constraint"),
            ("timeline", "timeline"),
        ]
        content_lines = [
            f"name: {name}",
            "aliases: " + " / ".join(str(value) for value in card.get("aliases", []) if str(value).strip()) if isinstance(card.get("aliases", []), list) else "",
            f"summary: {str(card.get('summary', '')).strip()}",
            *profile_lines,
        ]
        for field_name, label in list_fields:
            values = card.get(field_name, [])
            if not isinstance(values, list):
                continue
            for value in values:
                text = str(value or "").strip()
                if text:
                    content_lines.append(f"{label}: {text}")
        evidence = card.get("evidence", []) if isinstance(card.get("evidence"), list) else []
        for evidence_item in evidence[:5]:
            if not isinstance(evidence_item, dict):
                continue
            quote = str(evidence_item.get("quote", "") or evidence_item.get("note", "")).strip()
            if quote:
                content_lines.append(f"evidence: {quote}")
        doc = _make_document(
            project_name,
            "entity_character_card",
            str(card.get("id") or index),
            name,
            "\n".join(content_lines),
            scope=str(card.get("scope") or "project"),
            path=str(project_path(project_name) / "knowledge" / "entities" / "characters.json"),
            tags=[str(tag) for tag in card.get("tags", []) if str(tag).strip()] if isinstance(card.get("tags"), list) else ["character_entity"],
            metadata={
                "entity_type": "character",
                "authority": str(card.get("authority") or "project"),
                "confidence": card.get("confidence", 0.7),
                "importance": card.get("importance", 0.5),
                "canon_status": str(card.get("canon_status") or "unknown"),
                "version_scope": str(card.get("version_scope") or ""),
                "worldline_id": str(card.get("worldline_id") or ""),
                "worldline_label": str(card.get("worldline_label") or ""),
                "source_knowledge_ids": card.get("source_knowledge_ids", []),
            },
        )
        if doc:
            documents.append(doc)
    return documents


def _documents_from_entity_aliases(project_name: str) -> list[RetrievalDocument]:
    documents: list[RetrievalDocument] = []
    for index, group in enumerate(load_entity_aliases(project_name), start=1):
        if not isinstance(group, dict):
            continue
        canonical_name = str(group.get("canonical_name") or "").strip()
        aliases = [str(value).strip() for value in group.get("aliases", []) if str(value).strip()] if isinstance(group.get("aliases", []), list) else []
        if not canonical_name and not aliases:
            continue
        title = canonical_name or aliases[0]
        content_lines = [
            f"canonical_name: {title}",
            f"category: {group.get('category', '')}",
            "aliases: " + " / ".join(aliases),
        ]
        if group.get("notes"):
            content_lines.append(f"notes: {group.get('notes')}")
        doc = _make_document(
            project_name,
            "entity_alias_group",
            str(group.get("id") or index),
            title,
            "\n".join(content_lines),
            scope="project",
            path=str(project_path(project_name) / "knowledge" / "entities" / "aliases.json"),
            tags=["entity_alias", str(group.get("category") or "")],
            metadata={
                "entity_type": "alias_group",
                "knowledge_category": str(group.get("category") or ""),
                "aliases": aliases,
                "source_pending_ids": group.get("source_pending_ids", []),
                "authority": "project",
            },
        )
        if doc:
            documents.append(doc)
    return documents


def _documents_from_setting_entities(project_name: str) -> list[RetrievalDocument]:
    documents: list[RetrievalDocument] = []
    for index, card in enumerate(load_setting_entities(project_name), start=1):
        if not isinstance(card, dict):
            continue
        name = str(card.get("name") or "").strip()
        if not name:
            continue
        content_lines = [
            f"name: {name}",
            f"setting_type: {card.get('setting_type', '')}",
            f"summary: {card.get('summary', '')}",
        ]
        for field in ["rules", "locations", "organizations", "abilities", "constraints", "timeline", "related_entities"]:
            values = card.get(field, [])
            if isinstance(values, list) and values:
                content_lines.append(f"{field}: " + "；".join(str(item) for item in values[:12]))
            elif isinstance(values, dict) and values:
                content_lines.append(f"{field}: " + json.dumps(values, ensure_ascii=False))
        doc = _make_document(
            project_name,
            "entity_setting_card",
            str(card.get("id") or index),
            name,
            "\n".join(content_lines),
            scope=str(card.get("scope") or "project"),
            path=str(project_path(project_name) / "knowledge" / "entities" / "settings.json"),
            tags=[str(tag) for tag in card.get("tags", []) if str(tag).strip()] if isinstance(card.get("tags"), list) else ["setting_entity"],
            metadata={
                "entity_type": "setting",
                "setting_type": str(card.get("setting_type") or ""),
                "authority": str(card.get("authority") or "project"),
                "confidence": card.get("confidence", 0.7),
                "importance": card.get("importance", 0.5),
                "canon_status": str(card.get("canon_status") or "unknown"),
                "worldline_id": str(card.get("worldline_id") or ""),
                "worldline_label": str(card.get("worldline_label") or ""),
                "version_scope": str(card.get("version_scope") or ""),
                "source_knowledge_ids": card.get("source_knowledge_ids", []),
            },
        )
        if doc:
            documents.append(doc)
    return documents


def _documents_from_project_files(project_name: str, story_id: str = "default") -> list[RetrievalDocument]:
    documents: list[RetrievalDocument] = []
    base_path = story_path(project_name, story_id)

    outline = load_outline(project_name, story_id=story_id)
    creative_profile_discussion_artifact = load_creative_profile_discussion_artifact(project_name, story_id=story_id)
    outline_discussion_artifact = load_outline_discussion_artifact(project_name, story_id=story_id)
    doc = _make_document(
        project_name,
        "outline",
        f"{story_id}/outline",
        f"[{story_id}] Project Outline",
        outline,
        path=str(base_path / "outline.md"),
        tags=["outline", f"story:{story_id}"],
        metadata={"authority": "project", "story_id": story_id},
    )
    if doc:
        documents.append(doc)

    for item in load_story_chapter_summaries(project_name, story_id):
        if not isinstance(item, dict):
            continue
        chapter_no = item.get("chapter_no")
        summary = str(item.get("summary", "") or "").strip()
        if not summary:
            continue
        doc = _make_document(
            project_name,
            "chapter_summary",
            f"{story_id}/chapter_summary_{chapter_no}",
            f"[{story_id}] Chapter {chapter_no:03d} Summary" if isinstance(chapter_no, int) else f"[{story_id}] Chapter Summary",
            summary,
            chapter_no=chapter_no if isinstance(chapter_no, int) else None,
            path=str(base_path / "chapter_summaries.json"),
            tags=["summary", f"story:{story_id}"],
            metadata={"memory_field": "chapter_summaries", "authority": "project", "story_id": story_id},
        )
        if doc:
            documents.append(doc)

    creative_profile_discussion = creative_profile_discussion_artifact.get("report_markdown", "")
    doc = _make_document(
        project_name,
        "creative_profile_discussion",
        f"{story_id}/creative_profile_discussion",
        f"[{story_id}] Approved Creative Profile Discussion",
        creative_profile_discussion,
        path=str(base_path / "creative_profile.discussion.json"),
        tags=["creative_profile_discussion", "approved_discussion", "creative_profile", f"story:{story_id}"],
        metadata={
            "authority": "project",
            "story_id": story_id,
            "approval_ready": bool((creative_profile_discussion_artifact.get("discussion") or {}).get("approval_ready")),
            "recommended_profile": (creative_profile_discussion_artifact.get("discussion") or {}).get("recommended_profile", {}),
        },
    )
    if doc:
        documents.append(doc)

    outline_discussion = outline_discussion_artifact.get("report_markdown", "")
    doc = _make_document(
        project_name,
        "outline_discussion",
        f"{story_id}/outline_discussion",
        f"[{story_id}] Approved Outline Discussion",
        outline_discussion,
        path=str(base_path / "outline.discussion.json"),
        tags=["outline_discussion", "approved_discussion"],
        metadata={
            "authority": "project",
            "story_id": story_id,
            "approval_ready": bool((outline_discussion_artifact.get("discussion") or {}).get("approval_ready")),
        },
    )
    if doc:
        documents.append(doc)

    for volume in list_volumes(project_name, story_id=story_id):
        volume_no = int(volume.get("volume_no", 0))
        volume_outline = load_volume_outline(project_name, volume_no, story_id=story_id)
        volume_meta = load_volume_metadata(project_name, volume_no, story_id=story_id)
        volume_discussion_artifact = load_volume_discussion_artifact(project_name, volume_no, story_id=story_id)
        doc = _make_document(
            project_name,
            "volume_outline",
            f"{story_id}/volume_{volume_no:03d}",
            volume_meta.get("title") or f"Volume {volume_no:03d}",
            volume_outline,
            path=str(base_path / "volumes" / f"volume_{volume_no:03d}.md"),
            tags=["volume_outline", f"volume_{volume_no:03d}"],
            metadata={
                "authority": "project",
                "story_id": story_id,
                "volume_no": volume_no,
                "status": volume_meta.get("status", "draft"),
                "summary": volume_meta.get("summary", ""),
            },
        )
        if doc:
            documents.append(doc)

        volume_discussion = volume_discussion_artifact.get("report_markdown", "")
        doc = _make_document(
            project_name,
            "volume_discussion",
            f"{story_id}/volume_{volume_no:03d}",
            f"{volume_meta.get('title') or f'Volume {volume_no:03d}'} Approved Discussion",
            volume_discussion,
            path=str(base_path / "volumes" / f"volume_{volume_no:03d}.discussion.json"),
            tags=["volume_discussion", f"volume_{volume_no:03d}", "approved_discussion"],
            metadata={
                "authority": "project",
                "story_id": story_id,
                "volume_no": volume_no,
                "approval_ready": bool((volume_discussion_artifact.get("discussion") or {}).get("approval_ready")),
            },
        )
        if doc:
            documents.append(doc)

    for arc in list_arcs(project_name, story_id=story_id):
        arc_no = int(arc.get("arc_no", 0))
        arc_outline = load_arc_outline(project_name, arc_no, story_id=story_id)
        arc_meta = load_arc_metadata(project_name, arc_no, story_id=story_id)
        arc_discussion_artifact = load_arc_discussion_artifact(project_name, arc_no, story_id=story_id)
        doc = _make_document(
            project_name,
            "arc_outline",
            f"{story_id}/arc_{arc_no:03d}",
            arc_meta.get("title") or f"Arc {arc_no:03d}",
            arc_outline,
            path=str(base_path / "arcs" / f"arc_{arc_no:03d}.md"),
            tags=["arc_outline", f"arc_{arc_no:03d}"],
            metadata={
                "authority": "project",
                "story_id": story_id,
                "arc_no": arc_no,
                "volume_no": arc_meta.get("volume_no"),
                "status": arc_meta.get("status", "draft"),
                "summary": arc_meta.get("summary", ""),
                "estimated_chapter_count": arc_meta.get("estimated_chapter_count"),
                "target_word_count_range": arc_meta.get("target_word_count_range", ""),
            },
        )
        if doc:
            documents.append(doc)

        arc_discussion = arc_discussion_artifact.get("report_markdown", "")
        doc = _make_document(
            project_name,
            "arc_discussion",
            f"{story_id}/arc_{arc_no:03d}",
            f"{arc_meta.get('title') or f'Arc {arc_no:03d}'} Approved Discussion",
            arc_discussion,
            path=str(base_path / "arcs" / f"arc_{arc_no:03d}.discussion.json"),
            tags=["arc_discussion", f"arc_{arc_no:03d}", "approved_discussion"],
            metadata={
                "authority": "project",
                "story_id": story_id,
                "arc_no": arc_no,
                "volume_no": arc_meta.get("volume_no"),
                "approval_ready": bool((arc_discussion_artifact.get("discussion") or {}).get("approval_ready")),
            },
        )
        if doc:
            documents.append(doc)

        arc_chapter_plan = load_arc_chapter_plan(project_name, arc_no, story_id=story_id)
        plan_markdown = arc_chapter_plan.get("report_markdown", "")
        doc = _make_document(
            project_name,
            "arc_chapter_plan",
            f"{story_id}/arc_{arc_no:03d}",
            f"{arc_meta.get('title') or f'Arc {arc_no:03d}'} Chapter Plan",
            plan_markdown,
            path=str(base_path / "arcs" / f"arc_{arc_no:03d}.chapter_plan.json"),
            tags=["arc_chapter_plan", f"arc_{arc_no:03d}"],
            metadata={
                "authority": "project",
                "story_id": story_id,
                "arc_no": arc_no,
                "volume_no": arc_meta.get("volume_no"),
            },
        )
        if doc:
            documents.append(doc)

    chapter_outline_dir = base_path / "chapter_outlines"
    chapter_discussion_numbers: set[int] = set()
    if chapter_outline_dir.exists():
        for file in chapter_outline_dir.glob("chapter_*.discussion.json"):
            match = re.search(r"chapter_(\d+)\.discussion\.json$", file.name)
            if match:
                chapter_discussion_numbers.add(int(match.group(1)))
    if chapter_outline_dir.exists():
        for file in sorted(chapter_outline_dir.glob("chapter_*.md")):
            match = re.search(r"chapter_(\d+)\.md$", file.name)
            chapter_no = int(match.group(1)) if match else None
            chapter_meta = load_chapter_outline_metadata(project_name, chapter_no, story_id=story_id) if chapter_no is not None else {}
            doc = _make_document(
                project_name,
                "chapter_outline",
                f"{story_id}/{file.stem}",
                f"Chapter {chapter_no:03d} Outline" if chapter_no is not None else file.stem,
                load_chapter_outline(project_name, chapter_no, story_id=story_id) if chapter_no is not None else file.read_text(encoding="utf-8"),
                chapter_no=chapter_no,
                path=str(file),
                tags=["chapter_outline"],
                metadata={
                    "authority": "project",
                    "story_id": story_id,
                    "volume_no": chapter_meta.get("volume_no"),
                    "arc_no": chapter_meta.get("arc_no"),
                },
            )
            if doc:
                documents.append(doc)

        for chapter_no in sorted(chapter_discussion_numbers):
            chapter_meta = load_chapter_outline_metadata(project_name, chapter_no, story_id=story_id)
            chapter_discussion_artifact = load_chapter_discussion_artifact(project_name, chapter_no, story_id=story_id)
            chapter_discussion = chapter_discussion_artifact.get("report_markdown", "")
            doc = _make_document(
                project_name,
                "chapter_discussion",
                f"{story_id}/chapter_{chapter_no:03d}",
                f"Chapter {chapter_no:03d} Approved Discussion",
                chapter_discussion,
                chapter_no=chapter_no,
                path=str(base_path / "chapter_outlines" / f"chapter_{chapter_no:03d}.discussion.json"),
                tags=["chapter_discussion", f"chapter_{chapter_no:03d}", "approved_discussion"],
                metadata={
                    "authority": "project",
                    "story_id": story_id,
                    "chapter_no": chapter_no,
                    "volume_no": chapter_meta.get("volume_no"),
                    "arc_no": chapter_meta.get("arc_no"),
                    "approval_ready": bool((chapter_discussion_artifact.get("discussion") or {}).get("approval_ready")),
                },
            )
            if doc:
                documents.append(doc)

    chapters_dir = base_path / "chapters"
    if chapters_dir.exists():
        for file in sorted(chapters_dir.glob("chapter_*.md")):
            match = re.search(r"chapter_(\d+)\.md$", file.name)
            chapter_no = int(match.group(1)) if match else None
            content = load_chapter(project_name, chapter_no, story_id=story_id) if chapter_no is not None else file.read_text(encoding="utf-8")
            doc = _make_document(
                project_name,
                "chapter_content",
                f"{story_id}/{file.stem}",
                f"Chapter {chapter_no:03d} Content" if chapter_no is not None else file.stem,
                content,
                chapter_no=chapter_no,
                path=str(file),
                tags=["chapter"],
                metadata={"authority": "project", "story_id": story_id},
            )
            if doc:
                documents.append(doc)

    reviews_dir = base_path / "reviews"
    if reviews_dir.exists():
        for file in sorted(reviews_dir.glob("chapter_*.json")):
            match = re.search(r"chapter_(\d+)\.json$", file.name)
            if not match:
                continue
            chapter_no = int(match.group(1))
            review_json = load_review_json(project_name, chapter_no, story_id=story_id)
            if not review_json:
                continue
            summary_doc = _make_document(
                project_name,
                "review_summary",
                f"{story_id}/summary_{chapter_no:03d}",
                f"Chapter {chapter_no:03d} Review Summary",
                review_json.get("summary", ""),
                chapter_no=chapter_no,
                path=str(file),
                tags=["review", "summary", review_json.get("status", "")],
                metadata={"status": review_json.get("status", ""), "authority": "project", "story_id": story_id},
            )
            if summary_doc:
                documents.append(summary_doc)

            for index, issue in enumerate(review_json.get("issues", []), start=1):
                doc = _make_document(
                    project_name,
                    "review_issue",
                    f"{story_id}/{chapter_no:03d}_{index:02d}",
                    f"Chapter {chapter_no:03d} Review Issue {index}",
                    issue,
                    chapter_no=chapter_no,
                    path=str(file),
                    tags=["review", "issue"],
                    metadata={"status": review_json.get("status", ""), "authority": "project", "story_id": story_id},
                )
                if doc:
                    documents.append(doc)

            for field_name, label in [
                ("characters", "review_characters_check"),
                ("world", "review_world_check"),
                ("timeline", "review_timeline_check"),
                ("foreshadowing", "review_foreshadowing_check"),
            ]:
                content = review_json.get("consistency_checks", {}).get(field_name, "")
                doc = _make_document(
                    project_name,
                    label,
                    f"{story_id}/{chapter_no:03d}_{field_name}",
                    f"Chapter {chapter_no:03d} {field_name.title()} Check",
                    content,
                    chapter_no=chapter_no,
                    path=str(file),
                    tags=["review", field_name],
                    metadata={"status": review_json.get("status", ""), "authority": "project", "story_id": story_id},
                )
                if doc:
                    documents.append(doc)

        for file in sorted(reviews_dir.glob("chapter_*.md")):
            match = re.search(r"chapter_(\d+)\.md$", file.name)
            chapter_no = int(match.group(1)) if match else None
            content = load_review(project_name, chapter_no, story_id=story_id) if chapter_no is not None else file.read_text(encoding="utf-8")
            doc = _make_document(
                project_name,
                "review_markdown",
                f"{story_id}/{file.stem}",
                f"Chapter {chapter_no:03d} Review Markdown" if chapter_no is not None else file.stem,
                content,
                chapter_no=chapter_no,
                path=str(file),
                tags=["review", "markdown"],
                metadata={"authority": "project", "story_id": story_id},
            )
            if doc:
                documents.append(doc)

    analysis_dir = base_path / "analysis"
    if analysis_dir.exists():
        for file in sorted(analysis_dir.glob("*.md")):
            match = re.search(r"(.+)_chapter_(\d+)\.md$", file.name)
            analysis_type = match.group(1) if match else file.stem
            chapter_no = int(match.group(2)) if match else None
            content = load_analysis_report(project_name, analysis_type, chapter_no, story_id=story_id) if chapter_no is not None else file.read_text(encoding="utf-8")
            for section_title, section_body in _split_markdown_sections(content):
                identifier = f"{analysis_type}_{chapter_no or 'na'}_{section_title or 'body'}"
                doc = _make_document(
                    project_name,
                    f"analysis_{analysis_type}",
                    f"{story_id}/{identifier}",
                    section_title or f"{analysis_type} analysis",
                    section_body,
                    chapter_no=chapter_no,
                    path=str(file),
                    tags=["analysis", analysis_type],
                    metadata={"authority": "project", "story_id": story_id},
                )
                if doc:
                    documents.append(doc)

    evaluation_dir = base_path / "evaluation"
    if evaluation_dir.exists():
        for file in sorted(evaluation_dir.glob("chapter_*.md")):
            match = re.search(r"chapter_(\d+)\.md$", file.name)
            chapter_no = int(match.group(1)) if match else None
            content = load_evaluation_report(project_name, chapter_no, story_id=story_id) if chapter_no is not None else file.read_text(encoding="utf-8")
            doc = _make_document(
                project_name,
                "evaluation_chapter",
                f"{story_id}/{file.stem}",
                f"Chapter {chapter_no:03d} Evaluation" if chapter_no is not None else file.stem,
                content,
                chapter_no=chapter_no,
                path=str(file),
                tags=["evaluation"],
                metadata={
                    "authority": "project",
                    "story_id": story_id,
                    "evaluation": load_evaluation_json(project_name, chapter_no, story_id=story_id) if chapter_no is not None else {},
                },
            )
            if doc:
                documents.append(doc)

    return documents


def _documents_from_external_sources(project_name: str) -> list[RetrievalDocument]:
    source_dir = retrieval_sources_path(project_name)
    documents: list[RetrievalDocument] = []

    for file in sorted(source_dir.rglob("*")):
        if not file.is_file() or file.suffix.lower() not in {".md", ".txt", ".json"}:
            continue

        raw_text = file.read_text(encoding="utf-8")
        scope = "reference"
        title = file.stem
        content = raw_text
        metadata = {"external_file": True}
        tags = ["external"]
        source_type = "external_source"

        if file.suffix.lower() == ".json":
            try:
                parsed = json.loads(raw_text)
                scope = str(parsed.get("scope", scope)) if isinstance(parsed, dict) else scope
                title = str(parsed.get("title", title)) if isinstance(parsed, dict) else title
                body = parsed.get("content", "") if isinstance(parsed, dict) else ""
                content = body if isinstance(body, str) and body.strip() else raw_text
                metadata.update(parsed.get("metadata", {}) if isinstance(parsed, dict) and isinstance(parsed.get("metadata"), dict) else {})
                tags.extend(parsed.get("tags", []) if isinstance(parsed, dict) and isinstance(parsed.get("tags"), list) else [])
                source_type = str(parsed.get("source_type", source_type)) if isinstance(parsed, dict) else source_type
            except Exception as exc:
                logging.getLogger("novelforge").warning(
                    "Failed to parse external retrieval source as JSON: project=%s file=%s error=%s",
                    project_name, file, exc,
                )
                content = raw_text

        doc = _make_document(
            project_name,
            source_type,
            file.stem,
            title,
            content,
            scope=scope if scope in {"project", "canon", "reference"} else "reference",
            path=str(file),
            tags=tags,
            metadata={**metadata, "authority": _infer_authority(scope, metadata)},
        )
        if doc:
            documents.append(doc)

    return documents


def gather_retrieval_documents(project_name: str) -> list[RetrievalDocument]:
    documents = []
    documents.extend(_documents_from_memory(project_name))
    documents.extend(_documents_from_knowledge(project_name))
    documents.extend(_documents_from_character_entities(project_name))
    documents.extend(_documents_from_entity_aliases(project_name))
    documents.extend(_documents_from_setting_entities(project_name))
    documents.extend(_documents_from_external_sources(project_name))

    # Project-level conflict resolutions are added once, not per story
    conflict_resolutions = load_conflict_resolutions(project_name)
    for item in conflict_resolutions:
        content = "\n".join([
            f"decision: {item.get('decision', '')}",
            f"note: {item.get('note', '')}",
            f"shared_terms: {', '.join(item.get('shared_terms', []))}",
            f"project_source: {item.get('project_source', '')}",
            f"external_source: {item.get('external_source', '')}",
        ])
        doc = _make_document(
            project_name,
            "conflict_resolution",
            str(item.get("conflict_id", "")),
            f"Conflict Resolution {item.get('conflict_id', '')}",
            content,
            path=str(project_path(project_name) / "retrieval" / "conflict_resolutions.json"),
            tags=["conflict_resolution"],
            metadata={"authority": "project", "decision": item.get("decision", "")},
        )
        if doc:
            documents.append(doc)

    for story in list_stories(project_name):
        story_id = story.get("story_id", "default")
        try:
            documents.extend(_documents_from_project_files(project_name, story_id))
        except Exception as exc:
            logging.getLogger("novelforge").warning(
                "Failed to gather story retrieval documents: project=%s story=%s error=%s",
                project_name, story_id, exc,
            )
    return documents


def chunk_document(document: RetrievalDocument) -> list[RetrievalChunk]:
    if document.source_type in STRUCTURED_SOURCE_TYPES or document.source_type.startswith("knowledge_") or document.source_type.startswith("entity_"):
        parts = [(document.title, document.content.strip())] if document.content.strip() else []
    elif document.source_type.startswith("analysis_"):
        parts = _chunk_markdown_sections(document.content)
    elif document.source_type in {"outline", "chapter_outline", "arc_chapter_plan", "evaluation_chapter", "review_markdown", "external_source", "external_character_sheet", "external_location_sheet", "external_organization_sheet", "external_timeline_note", "external_canon_event", "external_world_rule", "external_artifact_note"}:
        parts = _chunk_markdown_sections(document.content)
    elif document.source_type == "chapter_content":
        parts = [(document.title, chunk) for chunk in _chunk_by_paragraphs(document.content)]
    else:
        parts = [(document.title, chunk) for chunk in _split_long_text(document.content)]

    if not parts:
        return []

    result = []
    for index, (section_title, chunk_text) in enumerate(parts, start=1):
        chunk_title = section_title or document.title
        result.append(RetrievalChunk(
            chunk_id=f"{document.doc_id}#chunk{index:03d}",
            document_id=document.doc_id,
            project_name=document.project_name,
            source_type=document.source_type,
            scope=document.scope,
            title=chunk_title,
            content=chunk_text,
            chapter_no=document.chapter_no,
            path=document.path,
            tags=document.tags,
            metadata={
                **document.metadata,
                "chunk_index": index,
                "chunk_total": len(parts),
                "section_title": section_title,
            },
        ))
    return result


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_vector_store(project_name: str, manifest: RetrievalIndexManifest | None = None) -> RetrievalVectorStore:
    manifest = manifest or load_retrieval_index(project_name)
    vectors = {}
    for chunk in manifest.chunks:
        vectors[chunk.chunk_id] = get_embedding(f"{chunk.title}\n{chunk.content}")

    store = RetrievalVectorStore(
        project_name=project_name,
        built_at=datetime.now().isoformat(timespec="seconds"),
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        vectors=vectors,
    )
    save_retrieval_vectors(project_name, store.model_dump_json(indent=2))
    return store


def load_vector_store(project_name: str) -> RetrievalVectorStore | None:
    content = load_retrieval_vectors(project_name)
    if not content.strip():
        return None
    try:
        return RetrievalVectorStore.model_validate_json(content)
    except Exception:
        return None


def inspect_retrieval_health(project_name: str) -> dict:
    issues: list[dict] = []
    try:
        manifest = load_retrieval_index(project_name)
        manifest_error = ""
    except Exception as exc:
        manifest = build_retrieval_index(project_name)
        manifest_error = str(exc)
        issues.append({
            "severity": "high",
            "message": f"索引读取失败，已尝试重建关键词索引：{exc}",
        })

    try:
        current_documents = gather_retrieval_documents(project_name)
        current_chunks: list[RetrievalChunk] = []
        for document in current_documents:
            current_chunks.extend(chunk_document(document))
        gather_error = ""
    except Exception as exc:
        current_documents = []
        current_chunks = []
        gather_error = str(exc)
        issues.append({
            "severity": "high",
            "message": f"当前资料收集失败：{exc}",
        })

    manifest_chunk_ids = {chunk.chunk_id for chunk in manifest.chunks}
    current_chunk_ids = {chunk.chunk_id for chunk in current_chunks}
    stale_chunk_count = len(manifest_chunk_ids - current_chunk_ids)
    missing_index_chunk_count = len(current_chunk_ids - manifest_chunk_ids)
    if stale_chunk_count or missing_index_chunk_count:
        issues.append({
            "severity": "medium",
            "message": f"索引与当前资料不一致：陈旧片段 {stale_chunk_count} 个，未入索引片段 {missing_index_chunk_count} 个。建议重建索引。",
        })

    store = load_vector_store(project_name)
    try:
        active_embedding_model = str(load_llm_settings().get("embedding_model_name") or DEFAULT_EMBEDDING_MODEL)
    except Exception:
        active_embedding_model = DEFAULT_EMBEDDING_MODEL
    vector_ids = set(store.vectors.keys()) if store else set()
    missing_vector_count = len(manifest_chunk_ids - vector_ids)
    stale_vector_count = len(vector_ids - manifest_chunk_ids)
    vector_dimension = 0
    if store and store.vectors:
        first_vector = next(iter(store.vectors.values()), [])
        vector_dimension = len(first_vector) if isinstance(first_vector, list) else 0

    if manifest.chunk_count and not manifest.embedding_enabled:
        issues.append({
            "severity": "medium",
            "message": f"当前索引没有启用语义向量，混合检索会退回关键词检索。当前配置的向量模型：{active_embedding_model or '-'}。",
        })
    elif manifest.embedding_enabled and missing_vector_count:
        issues.append({
            "severity": "medium",
            "message": f"语义向量不完整：缺少 {missing_vector_count} 个片段向量。建议重建向量索引。",
        })
    if stale_vector_count:
        issues.append({
            "severity": "low",
            "message": f"向量文件包含 {stale_vector_count} 个不再存在于索引中的旧向量。建议重建向量索引。",
        })
    if manifest.embedding_model and active_embedding_model and manifest.embedding_model != active_embedding_model:
        issues.append({
            "severity": "low",
            "message": f"当前配置的向量模型 `{active_embedding_model}` 与索引记录 `{manifest.embedding_model}` 不一致。切换模型后建议重建完整索引。",
        })
    if store and store.embedding_model and active_embedding_model and store.embedding_model != active_embedding_model:
        issues.append({
            "severity": "low",
            "message": f"当前配置的向量模型 `{active_embedding_model}` 与向量文件记录 `{store.embedding_model}` 不一致。建议重建完整索引。",
        })

    source_type_counts = Counter(chunk.source_type for chunk in manifest.chunks)
    scope_counts = Counter(chunk.scope for chunk in manifest.chunks)
    if manifest.chunk_count == 0:
        issues.append({
            "severity": "medium",
            "message": "当前检索索引没有任何片段。请先导入资料、确认知识或保存大纲/章节后重建索引。",
        })

    status = "healthy"
    if any(issue["severity"] == "high" for issue in issues):
        status = "error"
    elif any(issue["severity"] == "medium" for issue in issues):
        status = "warning"

    return {
        "status": status,
        "manifest_error": manifest_error,
        "gather_error": gather_error,
        "document_count": manifest.document_count,
        "chunk_count": manifest.chunk_count,
        "current_document_count": len(current_documents),
        "current_chunk_count": len(current_chunks),
        "embedding_enabled": manifest.embedding_enabled,
        "embedding_model": manifest.embedding_model,
        "active_embedding_model": active_embedding_model,
        "vector_store_present": bool(store),
        "vector_count": len(vector_ids),
        "vector_dimension": vector_dimension,
        "missing_vector_count": missing_vector_count,
        "stale_vector_count": stale_vector_count,
        "stale_chunk_count": stale_chunk_count,
        "missing_index_chunk_count": missing_index_chunk_count,
        "built_at": manifest.built_at,
        "vector_built_at": store.built_at if store else "",
        "vector_model": store.embedding_model if store else "",
        "source_type_counts": dict(source_type_counts.most_common()),
        "scope_counts": dict(scope_counts.most_common()),
        "issues": issues,
    }


def build_retrieval_index(project_name: str) -> RetrievalIndexManifest:
    documents = gather_retrieval_documents(project_name)
    chunks: list[RetrievalChunk] = []
    for document in documents:
        chunks.extend(chunk_document(document))

    manifest = RetrievalIndexManifest(
        project_name=project_name,
        built_at=datetime.now().isoformat(timespec="seconds"),
        document_count=len(documents),
        chunk_count=len(chunks),
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        embedding_enabled=False,
        documents=documents,
        chunks=chunks,
    )
    save_retrieval_manifest(project_name, manifest.model_dump_json(indent=2))
    return manifest


def rebuild_retrieval_assets(project_name: str, *, build_vectors: bool = True) -> RetrievalIndexManifest:
    manifest = build_retrieval_index(project_name)
    if not build_vectors:
        return manifest
    try:
        build_vector_store(project_name, manifest)
        manifest.embedding_enabled = True
        save_retrieval_manifest(project_name, manifest.model_dump_json(indent=2))
    except Exception:
        manifest.embedding_enabled = False
        save_retrieval_manifest(project_name, manifest.model_dump_json(indent=2))
    return manifest


def _refresh_manifest_knowledge_metadata(project_name: str, manifest: RetrievalIndexManifest) -> RetrievalIndexManifest:
    metadata_by_doc_id = _knowledge_metadata_by_doc_id(project_name)
    if not metadata_by_doc_id:
        return manifest
    changed = False
    for document in manifest.documents:
        if not document.source_type.startswith("knowledge_"):
            continue
        metadata = metadata_by_doc_id.get(document.doc_id)
        if not metadata:
            continue
        merged = {**document.metadata, **metadata}
        if merged != document.metadata:
            document.metadata = merged
            changed = True
    for chunk in manifest.chunks:
        if not chunk.source_type.startswith("knowledge_"):
            continue
        metadata = metadata_by_doc_id.get(chunk.document_id)
        if not metadata:
            continue
        merged = {**chunk.metadata, **metadata}
        if merged != chunk.metadata:
            chunk.metadata = merged
            changed = True
    if changed:
        save_retrieval_manifest(project_name, manifest.model_dump_json(indent=2))
    return manifest


def _is_story_scoped_source_type(source_type: str) -> bool:
    normalized = str(source_type or "")
    return normalized in STORY_SCOPED_SOURCE_TYPES or normalized.startswith("analysis_")


def _manifest_needs_story_scope_rebuild(manifest: RetrievalIndexManifest) -> bool:
    seen_doc_ids: set[str] = set()
    for document in manifest.documents:
        if document.doc_id in seen_doc_ids:
            return True
        seen_doc_ids.add(document.doc_id)
        if _is_story_scoped_source_type(document.source_type) and not str(document.metadata.get("story_id") or "").strip():
            return True
    for chunk in manifest.chunks:
        if _is_story_scoped_source_type(chunk.source_type) and not str(chunk.metadata.get("story_id") or "").strip():
            return True
    return False


def load_retrieval_index(project_name: str) -> RetrievalIndexManifest:
    content = load_retrieval_manifest(project_name)
    if not content.strip():
        return build_retrieval_index(project_name)
    try:
        manifest = RetrievalIndexManifest.model_validate_json(content)
        if _manifest_needs_story_scope_rebuild(manifest):
            return build_retrieval_index(project_name)
        return _refresh_manifest_knowledge_metadata(project_name, manifest)
    except Exception:
        return build_retrieval_index(project_name)


def _append_unique(target: list[str], values: list[str]) -> None:
    seen = set(target)
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        target.append(cleaned)
        seen.add(cleaned)


def _build_alias_query_expansion(project_name: str, query: str, base_terms: list[str]) -> dict:
    query_lower = query.lower()
    base_term_set = set(base_terms)
    expanded_terms: list[str] = []
    matched_alias_groups: list[dict] = []

    try:
        alias_groups = load_entity_aliases(project_name)
    except Exception:
        alias_groups = []

    for group in alias_groups:
        if len(matched_alias_groups) >= MAX_ALIAS_EXPANSION_GROUPS:
            break
        if not isinstance(group, dict):
            continue
        canonical_name = str(group.get("canonical_name") or "").strip()
        aliases = [
            str(value).strip()
            for value in group.get("aliases", [])
            if str(value).strip()
        ] if isinstance(group.get("aliases", []), list) else []
        names = []
        _append_unique(names, [canonical_name] + aliases)
        if not names:
            continue

        matched_names = []
        for name in names:
            name_lower = name.lower()
            name_terms = set(_tokenize(name))
            if name_lower and name_lower in query_lower:
                matched_names.append(name)
            elif name_terms and (name_terms & base_term_set):
                matched_names.append(name)

        if not matched_names:
            continue

        _append_unique(expanded_terms, names)
        matched_alias_groups.append({
            "canonical_name": canonical_name or names[0],
            "aliases": aliases,
            "matched_names": matched_names,
            "category": str(group.get("category") or ""),
        })
        if len(expanded_terms) >= MAX_ALIAS_EXPANDED_TERMS:
            expanded_terms = expanded_terms[:MAX_ALIAS_EXPANDED_TERMS]
            break

    return {
        "expanded_terms": expanded_terms,
        "matched_alias_groups": matched_alias_groups,
    }


def _build_query_plan(project_name: str, query: str) -> dict:
    base_terms = _tokenize(query)
    alias_expansion = _build_alias_query_expansion(project_name, query, base_terms)
    expanded_terms = alias_expansion.get("expanded_terms", [])
    expanded_text = " ".join(expanded_terms)
    query_terms = _dedupe_terms(base_terms + _tokenize(expanded_text))
    return {
        "query": query,
        "base_terms": _dedupe_terms(base_terms),
        "query_terms": query_terms,
        "expanded_terms": expanded_terms,
        "matched_alias_groups": alias_expansion.get("matched_alias_groups", []),
        "semantic_query": f"{query}\n{expanded_text}".strip() if expanded_text else query,
    }


def _dedupe_terms(terms: list[str]) -> list[str]:
    unique_terms = []
    seen = set()
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        unique_terms.append(term)
    return unique_terms


def _term_hits(candidate: str, matched_terms: list[str]) -> bool:
    candidate_terms = set(_tokenize(candidate))
    if not candidate_terms:
        return False
    return bool(candidate_terms & set(matched_terms))


def _normalize_worldline_id(value: str | None) -> str:
    return str(value or "").strip().lower()


def _chunk_worldline_id(chunk: RetrievalChunk) -> str:
    return _normalize_worldline_id(chunk.metadata.get("worldline_id") if isinstance(chunk.metadata, dict) else "")


def _chunk_worldline_label(chunk: RetrievalChunk) -> str:
    if not isinstance(chunk.metadata, dict):
        return ""
    return str(chunk.metadata.get("worldline_label") or chunk.metadata.get("worldline_id") or "").strip()


def _worldline_match_state(chunk: RetrievalChunk, worldline_id: str | None) -> str:
    target = _normalize_worldline_id(worldline_id)
    if not target:
        return "off"
    chunk_worldline = _chunk_worldline_id(chunk)
    if not chunk_worldline or chunk_worldline in GLOBAL_WORLDLINE_IDS:
        return "global"
    if chunk_worldline == target:
        return "match"
    return "mismatch"


def _worldline_allowed(chunk: RetrievalChunk, worldline_id: str | None, worldline_mode: str = "prefer") -> bool:
    mode = str(worldline_mode or "prefer").strip().lower()
    if mode != "strict":
        return True
    return _worldline_match_state(chunk, worldline_id) in {"off", "global", "match"}


def _story_scope_allowed(chunk: RetrievalChunk, story_id: str | None = "default") -> bool:
    if not isinstance(chunk.metadata, dict):
        return True
    target_story_id = str(story_id or "default").strip() or "default"
    chunk_story_id = str(chunk.metadata.get("story_id") or "").strip()
    if chunk_story_id:
        return chunk_story_id == target_story_id
    setting_scope = str(chunk.metadata.get("setting_scope") or "").strip().lower()
    if setting_scope == "story":
        return False
    return True


def _expand_query_terms(query: str) -> list[str]:
    return _dedupe_terms(_tokenize(query))


def _score_chunk(
    chunk: RetrievalChunk,
    query_terms: list[str],
    expanded_terms: list[str] | None = None,
    *,
    worldline_id: str | None = None,
    worldline_mode: str = "prefer",
) -> tuple[float, list[str], dict[str, float], list[str]]:
    content_terms = _tokenize(f"{chunk.title} {chunk.content} {' '.join(chunk.tags)}")
    if not content_terms:
        return 0.0, [], {}, []

    counter = Counter(content_terms)
    matched_terms = []
    lexical_score = 0.0
    for term in query_terms:
        count = counter.get(term, 0)
        if count <= 0:
            continue
        matched_terms.append(term)
        lexical_score += 2.0 + min(count, 4) * 0.5

    if not matched_terms:
        return 0.0, [], {}, []

    score = lexical_score
    score_breakdown = {"lexical": lexical_score}
    match_reasons = [f"关键词命中：{', '.join(matched_terms[:8])}"]

    expanded_matches = []
    for term in expanded_terms or []:
        if term and _term_hits(term, matched_terms):
            expanded_matches.append(term)
    if expanded_matches:
        alias_bonus = min(len(expanded_matches), 4) * 0.35
        score += alias_bonus
        score_breakdown["alias_expansion"] = alias_bonus
        match_reasons.append(f"别名/主名称扩展命中：{', '.join(expanded_matches[:6])}")

    if chunk.scope == "project":
        score += 1.5
        score_breakdown["scope"] = 1.5
        match_reasons.append("项目范围优先")
    elif chunk.scope == "canon":
        score += 1.0
        score_breakdown["scope"] = 1.0
        match_reasons.append("原作范围优先")

    if chunk.source_type.startswith("memory_"):
        score += 0.5
        score_breakdown["source_type"] = score_breakdown.get("source_type", 0.0) + 0.5
        match_reasons.append("核心设定来源")
    if chunk.source_type in {"review_issue", "chapter_summary"}:
        score += 0.25
        score_breakdown["source_type"] = score_breakdown.get("source_type", 0.0) + 0.25
        match_reasons.append("章节摘要/审阅来源")

    authority = str(chunk.metadata.get("authority", "")).strip().lower()
    authority_bonus = AUTHORITY_WEIGHTS.get(authority, 0.0)
    if authority_bonus:
        score += authority_bonus
        score_breakdown["authority"] = authority_bonus
        match_reasons.append(f"可信度加权：{authority}")

    worldline_state = _worldline_match_state(chunk, worldline_id)
    if worldline_state == "match":
        score += 0.9
        score_breakdown["worldline"] = 0.9
        label = _chunk_worldline_label(chunk) or str(worldline_id or "")
        match_reasons.append(f"世界线匹配：{label}")
    elif worldline_state == "global":
        score += 0.2
        score_breakdown["worldline"] = 0.2
        match_reasons.append("通用世界线资料")
    elif worldline_state == "mismatch" and str(worldline_mode or "prefer").strip().lower() != "strict":
        score -= 0.6
        score_breakdown["worldline"] = -0.6
        label = _chunk_worldline_label(chunk) or _chunk_worldline_id(chunk)
        match_reasons.append(f"世界线不同：{label}")

    return score, matched_terms, score_breakdown, match_reasons


def _semantic_scores(project_name: str, query: str, chunks: list[RetrievalChunk]) -> dict[str, float]:
    store = load_vector_store(project_name)
    if not store or not store.vectors:
        return {}

    query_vector = get_embedding(query)
    scores = {}
    for chunk in chunks:
        vector = store.vectors.get(chunk.chunk_id)
        if not vector:
            continue
        scores[chunk.chunk_id] = _cosine_similarity(query_vector, vector)
    return scores


def _build_feedback_stats(project_name: str) -> dict[str, dict[str, float]]:
    weights = {
        "helpful": 0.25,
        "priority": 0.6,
        "irrelevant": -0.35,
        "wrong": -0.8,
    }
    stats: dict[str, dict[str, float]] = {}
    for item in load_retrieval_feedback(project_name):
        if not isinstance(item, dict):
            continue
        chunk_id = str(item.get("chunk_id") or "").strip()
        rating = str(item.get("rating") or "").strip()
        if not chunk_id or rating not in weights:
            continue
        entry = stats.setdefault(chunk_id, {"score": 0.0, "count": 0.0})
        entry["score"] += weights[rating]
        entry["count"] += 1
    return stats


def _feedback_bonus_for_chunk(chunk: RetrievalChunk, feedback_stats: dict[str, dict[str, float]]) -> float:
    stat = feedback_stats.get(chunk.chunk_id, {})
    score = float(stat.get("score", 0.0) or 0.0)
    if not score:
        return 0.0
    return max(-1.5, min(1.2, score))


def _rerank_hits(hits: list[RetrievalHit], feedback_stats: dict[str, dict[str, float]] | None = None) -> list[RetrievalHit]:
    reranked = []
    feedback_stats = feedback_stats or {}
    for hit in hits:
        chunk = hit.chunk
        authority = str(chunk.metadata.get("authority", "unknown") or "unknown").strip().lower()
        rerank_bonus = 0.0

        if hit.semantic_score >= 0.55:
            rerank_bonus += 0.6
        elif hit.semantic_score >= 0.35:
            rerank_bonus += 0.3

        if chunk.scope == "project":
            rerank_bonus += 0.4
        if authority == "official":
            rerank_bonus += 0.3
        elif authority == "curated":
            rerank_bonus += 0.15

        feedback_bonus = _feedback_bonus_for_chunk(chunk, feedback_stats)
        adjusted_score = hit.score + rerank_bonus + feedback_bonus
        score_breakdown = dict(hit.score_breakdown or {})
        match_reasons = list(hit.match_reasons or [])
        if rerank_bonus:
            score_breakdown["rerank"] = rerank_bonus
            match_reasons.append(f"重排加权：{rerank_bonus:.2f}")
        if feedback_bonus:
            score_breakdown["feedback"] = feedback_bonus
            if feedback_bonus > 0:
                match_reasons.append(f"用户反馈加权：{feedback_bonus:.2f}")
            else:
                match_reasons.append(f"用户反馈降权：{feedback_bonus:.2f}")
        reranked.append(hit.model_copy(update={
            "score": adjusted_score,
            "score_breakdown": score_breakdown,
            "match_reasons": match_reasons,
        }))

    reranked.sort(key=lambda item: (-item.score, -item.semantic_score, -item.lexical_score, item.chunk.source_type, item.chunk.chapter_no or 0, item.chunk.chunk_id))
    return reranked


def _diversify_hits(
    hits: list[RetrievalHit],
    top_k: int,
    *,
    max_per_document: int = 2,
    max_per_source_type: int = 4,
) -> list[RetrievalHit]:
    if top_k <= 0 or len(hits) <= top_k:
        return hits[:top_k]

    selected: list[RetrievalHit] = []
    document_counts: Counter[str] = Counter()
    source_type_counts: Counter[str] = Counter()

    for hit in hits:
        chunk = hit.chunk
        if document_counts[chunk.document_id] >= max_per_document:
            continue
        if source_type_counts[chunk.source_type] >= max_per_source_type:
            continue
        selected.append(hit)
        document_counts[chunk.document_id] += 1
        source_type_counts[chunk.source_type] += 1
        if len(selected) >= top_k:
            return selected

    selected_ids = {hit.chunk.chunk_id for hit in selected}
    for hit in hits:
        if hit.chunk.chunk_id in selected_ids:
            continue
        selected.append(hit)
        if len(selected) >= top_k:
            break
    return selected


def resolve_retrieval_params(
    reference_focus: list[str] | None = None,
    reference_strength: str | None = None,
    allowed_source_types: list[str] | None = None,
    allowed_scopes: list[str] | None = None,
    top_k: int | None = None,
    retrieval_mode: str | None = None,
    retrieval_profile: str | None = None,
) -> dict:
    profile = RETRIEVAL_TASK_PROFILES.get(str(retrieval_profile or "").strip(), {})
    params: dict = {
        "allowed_source_types": list(allowed_source_types) if allowed_source_types else list(profile.get("source_types", []) or []) or None,
        "allowed_scopes": list(allowed_scopes) if allowed_scopes else None,
        "top_k": top_k or int(profile.get("top_k") or DEFAULT_TOP_K),
        "retrieval_mode": retrieval_mode or str(profile.get("mode") or "hybrid"),
    }

    if reference_strength and reference_strength in REFERENCE_STRENGTH_PARAMS:
        sp = REFERENCE_STRENGTH_PARAMS[reference_strength]
        if sp["top_k"]:
            params["top_k"] = sp["top_k"]
        if sp["mode"]:
            params["retrieval_mode"] = sp["mode"]
        if sp["scopes"]:
            params["allowed_scopes"] = list(sp["scopes"])
        if sp["source_types"]:
            params["allowed_source_types"] = list(sp["source_types"])

    if reference_focus:
        focus_types: list[str] = []
        for focus in reference_focus:
            focus_types.extend(REFERENCE_FOCUS_SOURCE_MAP.get(focus, []))
        if focus_types:
            existing = params.get("allowed_source_types")
            if existing:
                params["allowed_source_types"] = [t for t in existing if t in focus_types] or focus_types
            else:
                params["allowed_source_types"] = focus_types

    return params


def _run_retrieval(
    project_name: str,
    query: str,
    *,
    top_k: int | None = None,
    allowed_scopes: list[str] | None = None,
    allowed_source_types: list[str] | None = None,
    retrieval_mode: str = "hybrid",
    reference_focus: list[str] | None = None,
    reference_strength: str | None = None,
    retrieval_profile: str | None = None,
    worldline_id: str | None = None,
    worldline_mode: str = "prefer",
    story_id: str = "default",
) -> dict:
    resolved = resolve_retrieval_params(
        reference_focus,
        reference_strength,
        allowed_source_types,
        allowed_scopes,
        top_k,
        retrieval_mode,
        retrieval_profile,
    )
    top_k = resolved["top_k"]
    retrieval_mode = resolved["retrieval_mode"]
    allowed_scopes = resolved.get("allowed_scopes")
    allowed_source_types = resolved.get("allowed_source_types")
    normalized_worldline = _normalize_worldline_id(worldline_id)
    normalized_worldline_mode = str(worldline_mode or "prefer").strip().lower()
    if normalized_worldline_mode not in {"prefer", "strict"}:
        normalized_worldline_mode = "prefer"

    index = load_retrieval_index(project_name)
    query_plan = _build_query_plan(project_name, query)
    query_terms = query_plan["query_terms"]
    scope_filter = set(allowed_scopes or ["project", "canon", "reference"])
    source_filter = set(allowed_source_types or [])

    filtered_chunks = []
    for chunk in index.chunks:
        if chunk.scope not in scope_filter:
            continue
        if source_filter and chunk.source_type not in source_filter:
            continue
        if not _story_scope_allowed(chunk, story_id):
            continue
        if not _worldline_allowed(chunk, normalized_worldline, normalized_worldline_mode):
            continue
        filtered_chunks.append(chunk)

    semantic_scores = {}
    if retrieval_mode in {"semantic", "hybrid"}:
        try:
            semantic_scores = _semantic_scores(project_name, query_plan["semantic_query"], filtered_chunks)
        except Exception:
            semantic_scores = {}

    initial_hits: list[RetrievalHit] = []
    if query_terms or retrieval_mode != "lexical":
        for chunk in filtered_chunks:
            if query_terms:
                lexical_score, matched_terms, score_breakdown, match_reasons = _score_chunk(
                    chunk,
                    query_terms,
                    query_plan["expanded_terms"],
                    worldline_id=normalized_worldline,
                    worldline_mode=normalized_worldline_mode,
                )
            else:
                lexical_score, matched_terms, score_breakdown, match_reasons = (0.0, [], {}, [])
            semantic_score = semantic_scores.get(chunk.chunk_id, 0.0)

            if retrieval_mode == "lexical":
                final_score = lexical_score
            elif retrieval_mode == "semantic":
                final_score = semantic_score
            else:
                final_score = lexical_score + semantic_score * 4.0

            if final_score <= 0:
                continue
            if semantic_score > 0:
                score_breakdown["semantic"] = semantic_score * (1.0 if retrieval_mode == "semantic" else 4.0)
                match_reasons.append(f"语义相似度：{semantic_score:.2f}")
            initial_hits.append(RetrievalHit(
                chunk=chunk,
                score=final_score,
                lexical_score=lexical_score,
                semantic_score=semantic_score,
                retrieval_mode=retrieval_mode if semantic_scores else "lexical",
                matched_terms=matched_terms,
                expanded_terms=query_plan["expanded_terms"],
                match_reasons=match_reasons,
                score_breakdown=score_breakdown,
            ))

    initial_hits.sort(key=lambda item: (-item.score, -item.semantic_score, -item.lexical_score, item.chunk.chunk_id))
    feedback_stats = _build_feedback_stats(project_name)
    reranked_hits = _rerank_hits(initial_hits, feedback_stats)
    diversified_hits = _diversify_hits(reranked_hits, top_k)
    return {
        "query": query,
        "base_query_terms": query_plan["base_terms"],
        "query_terms": query_terms,
        "expanded_terms": query_plan["expanded_terms"],
        "matched_alias_groups": query_plan["matched_alias_groups"],
        "semantic_query": query_plan["semantic_query"],
        "retrieval_mode": retrieval_mode,
        "retrieval_profile": retrieval_profile or "",
        "top_k": top_k,
        "scope_filter": sorted(scope_filter),
        "source_type_filter": sorted(source_filter),
        "candidate_chunk_count": len(filtered_chunks),
        "semantic_enabled": bool(semantic_scores),
        "story_id": str(story_id or "default"),
        "worldline_id": normalized_worldline,
        "worldline_mode": normalized_worldline_mode,
        "initial_hits": initial_hits,
        "reranked_hits": diversified_hits,
    }


def retrieve_context(
    project_name: str,
    query: str,
    *,
    top_k: int | None = None,
    allowed_scopes: list[str] | None = None,
    allowed_source_types: list[str] | None = None,
    retrieval_mode: str = "hybrid",
    reference_focus: list[str] | None = None,
    reference_strength: str | None = None,
    retrieval_profile: str | None = None,
    worldline_id: str | None = None,
    worldline_mode: str = "prefer",
    story_id: str = "default",
) -> list[RetrievalHit]:
    result = _run_retrieval(
        project_name,
        query,
        top_k=top_k,
        allowed_scopes=allowed_scopes,
        allowed_source_types=allowed_source_types,
        retrieval_mode=retrieval_mode,
        reference_focus=reference_focus,
        reference_strength=reference_strength,
        retrieval_profile=retrieval_profile,
        worldline_id=worldline_id,
        worldline_mode=worldline_mode,
        story_id=story_id,
    )
    return result["reranked_hits"]


def debug_retrieve_context(
    project_name: str,
    query: str,
    *,
    top_k: int | None = None,
    allowed_scopes: list[str] | None = None,
    allowed_source_types: list[str] | None = None,
    retrieval_mode: str = "hybrid",
    retrieval_profile: str | None = None,
    reference_focus: list[str] | None = None,
    reference_strength: str | None = None,
    worldline_id: str | None = None,
    worldline_mode: str = "prefer",
    story_id: str = "default",
) -> dict:
    result = _run_retrieval(
        project_name,
        query,
        top_k=top_k,
        allowed_scopes=allowed_scopes,
        allowed_source_types=allowed_source_types,
        retrieval_mode=retrieval_mode,
        reference_focus=reference_focus,
        reference_strength=reference_strength,
        retrieval_profile=retrieval_profile,
        worldline_id=worldline_id,
        worldline_mode=worldline_mode,
        story_id=story_id,
    )
    return {
        **{key: value for key, value in result.items() if key not in {"initial_hits", "reranked_hits"}},
        "initial_hits": [hit.model_dump() for hit in result["initial_hits"][:result.get("top_k", top_k or DEFAULT_TOP_K)]],
        "reranked_hits": [hit.model_dump() for hit in result["reranked_hits"]],
    }


def build_retrieval_briefing(hits: list[RetrievalHit]) -> dict:
    groups: dict[str, list[RetrievalHit]] = {}
    for hit in hits:
        groups.setdefault(hit.chunk.source_type, []).append(hit)

    priority_sources = []
    constraints = []
    conflicts = []
    for hit in hits:
        chunk = hit.chunk
        meta = chunk.metadata if isinstance(chunk.metadata, dict) else {}
        source_label = f"{chunk.source_type} / {chunk.title or chunk.document_id}"
        if chunk.source_type in {"knowledge_constraints", "memory_active_constraint", "entity_setting_card"}:
            constraints.append({
                "source": source_label,
                "content": chunk.content[:260],
            })
        if chunk.source_type == "conflict_resolution":
            conflicts.append({
                "source": source_label,
                "content": chunk.content[:260],
            })
        priority_sources.append({
            "source_type": chunk.source_type,
            "scope": chunk.scope,
            "title": chunk.title,
            "score": hit.score,
            "authority": str(meta.get("authority") or ""),
            "matched_terms": hit.matched_terms[:8],
        })

    return {
        "hit_count": len(hits),
        "source_type_counts": {key: len(value) for key, value in sorted(groups.items(), key=lambda pair: pair[0])},
        "priority_sources": priority_sources[:8],
        "constraints": constraints[:5],
        "conflicts": conflicts[:5],
    }


def format_retrieval_briefing(hits: list[RetrievalHit]) -> str:
    briefing = build_retrieval_briefing(hits)
    if not hits:
        return "资料简报：未检索到额外上下文。"
    lines = ["资料简报："]
    counts = briefing.get("source_type_counts", {})
    if counts:
        lines.append("- 来源分布：" + " / ".join(f"{key}={value}" for key, value in counts.items()))
    priority_sources = briefing.get("priority_sources", [])
    if priority_sources:
        lines.append("- 优先参考：")
        for item in priority_sources[:5]:
            matched = ", ".join(item.get("matched_terms", [])[:5]) or "-"
            lines.append(
                f"  - {item.get('source_type')} / {item.get('scope')} / {item.get('title') or '未命名'} / "
                f"score={float(item.get('score') or 0):.2f} / matched={matched}"
            )
    constraints = briefing.get("constraints", [])
    if constraints:
        lines.append("- 需要优先遵守的约束/设定：")
        for item in constraints[:3]:
            lines.append(f"  - {item.get('source')}: {item.get('content')}")
    conflicts = briefing.get("conflicts", [])
    if conflicts:
        lines.append("- 已保存的冲突裁决：")
        for item in conflicts[:3]:
            lines.append(f"  - {item.get('source')}: {item.get('content')}")
    return "\n".join(lines)


def format_retrieval_context(hits: list[RetrievalHit]) -> str:
    if not hits:
        return "未检索到额外上下文。"

    lines = [
        format_retrieval_briefing(hits),
        "",
        "以下为检索到的相关上下文，请优先参考与当前任务直接相关的内容：",
    ]
    for index, hit in enumerate(hits, start=1):
        chunk = hit.chunk
        header = f"[{index}] {chunk.source_type} / mode={hit.retrieval_mode} / score={hit.score:.2f}"
        if chunk.chapter_no is not None:
            header += f" / chapter {chunk.chapter_no:03d}"
        if chunk.scope != "project":
            header += f" / scope={chunk.scope}"
        if chunk.title:
            header += f" / {chunk.title}"
        lines.append(header)
        authority = str(chunk.metadata.get("authority") or "").strip()
        evidence_notes = []
        if authority:
            evidence_notes.append(f"authority={authority}")
        if hit.matched_terms:
            evidence_notes.append("matched_terms=" + ", ".join(hit.matched_terms[:8]))
        if hit.match_reasons:
            evidence_notes.append("reasons=" + "；".join(hit.match_reasons[:3]))
        if evidence_notes:
            lines.append("evidence_meta: " + " / ".join(evidence_notes))
        lines.append(chunk.content)
    return "\n".join(lines)


def ingest_external_source_file(project_name: str, source_name: str, content: str, *, overwrite: bool = True) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "_", source_name).strip("_") or "external_source"
    try:
        parsed = json.loads(content)
        suffix = ".json" if isinstance(parsed, dict) else ".md"
    except Exception:
        suffix = ".md"
    source_root = retrieval_sources_path(project_name)
    target = source_root / f"{safe_name}{suffix}"
    if not overwrite:
        counter = 2
        while target.exists():
            target = source_root / f"{safe_name}_{counter:02d}{suffix}"
            counter += 1
    target.write_text(content, encoding="utf-8")
    return target.relative_to(source_root).as_posix()


def build_structured_external_source_payload(
    *,
    source_type: str,
    scope: str,
    title: str,
    summary: str,
    content: str,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    extra_fields: dict | None = None,
) -> dict:
    tags = [str(item).strip() for item in (tags or []) if str(item).strip()]
    metadata = metadata.copy() if isinstance(metadata, dict) else {}
    extra_fields = extra_fields.copy() if isinstance(extra_fields, dict) else {}

    sections = []
    if summary.strip():
        sections.append("# Summary\n\n" + summary.strip())
    if content.strip():
        sections.append("# Details\n\n" + content.strip())
    for key, value in extra_fields.items():
        cleaned = str(value).strip()
        if cleaned:
            section_title = key.replace("_", " ").title()
            sections.append(f"# {section_title}\n\n{cleaned}")

    return {
        "source_type": source_type,
        "scope": scope,
        "title": title.strip(),
        "content": "\n\n".join(section for section in sections if section.strip()),
        "tags": tags,
        "metadata": metadata,
    }
