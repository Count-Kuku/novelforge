from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class NovelForgeSchema(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _stringify_item(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    if isinstance(value, dict):
        preferred_keys = [
            "summary",
            "content",
            "description",
            "detail",
            "finding",
            "issue",
            "recommendation",
            "title",
            "name",
            "text",
        ]
        for key in preferred_keys:
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()

        parts = []
        for key, item in value.items():
            text = _stringify_item(item)
            if text:
                parts.append(f"{key}: {text}")
        return "; ".join(parts)

    if isinstance(value, list):
        parts = [_stringify_item(item) for item in value]
        return "; ".join(part for part in parts if part)

    return str(value).strip()


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]

    normalized = []
    for item in value:
        text = _stringify_item(item)
        if text:
            normalized.append(text)
    return normalized


class ConsistencyChecks(NovelForgeSchema):
    characters: str = ""
    world: str = ""
    timeline: str = ""
    foreshadowing: str = ""


class ReviewResult(NovelForgeSchema):
    status: Literal["pass", "revise", "blocked"]
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    consistency_checks: ConsistencyChecks = Field(default_factory=ConsistencyChecks)
    pacing: str = ""
    next_action: str = ""


class ChapterSummary(NovelForgeSchema):
    chapter_no: int
    summary: str = ""


class MemoryUpdatePayload(NovelForgeSchema):
    new_characters: list[str | dict[str, Any]] = Field(default_factory=list)
    world_updates: list[Any] = Field(default_factory=list)
    timeline_updates: list[Any] = Field(default_factory=list)
    foreshadowing_updates: list[Any] = Field(default_factory=list)
    chapter_summary: str = ""


class MemoryUpdateResult(MemoryUpdatePayload):
    chapter_no: int


class OperationResult(NovelForgeSchema):
    status: Literal["accepted", "rejected"]
    reason: str = ""
    raw_response: str = ""
    applied_updates: MemoryUpdateResult | None = None


class CharacterAnalysisResult(NovelForgeSchema):
    title: str = "角色分析"
    character_overview: list[str] = Field(default_factory=list)
    consistency_findings: list[str] = Field(default_factory=list)
    relationship_progression: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    @field_validator("character_overview", "consistency_findings", "relationship_progression", "issues", "recommendations", mode="before")
    @classmethod
    def _normalize_fields(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class TimelineAnalysisResult(NovelForgeSchema):
    title: str = "时间线分析"
    key_events: list[str] = Field(default_factory=list)
    timeline_alignment: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    pacing_assessment: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    @field_validator("key_events", "timeline_alignment", "contradictions", "pacing_assessment", "recommendations", mode="before")
    @classmethod
    def _normalize_fields(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class ForeshadowingAnalysisResult(NovelForgeSchema):
    title: str = "伏笔分析"
    new_foreshadowing: list[str] = Field(default_factory=list)
    callbacks_and_payoffs: list[str] = Field(default_factory=list)
    strength_assessment: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    @field_validator("new_foreshadowing", "callbacks_and_payoffs", "strength_assessment", "issues", "recommendations", mode="before")
    @classmethod
    def _normalize_fields(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class ConsistencyAnalysisResult(NovelForgeSchema):
    title: str = "一致性总检查"
    overall_conclusion: str = ""
    character_consistency: list[str] = Field(default_factory=list)
    world_consistency: list[str] = Field(default_factory=list)
    timeline_consistency: list[str] = Field(default_factory=list)
    foreshadowing_and_setup: list[str] = Field(default_factory=list)
    priority_fixes: list[str] = Field(default_factory=list)

    @field_validator("overall_conclusion", mode="before")
    @classmethod
    def _normalize_overall_conclusion(cls, value: Any) -> str:
        return _stringify_item(value)

    @field_validator("character_consistency", "world_consistency", "timeline_consistency", "foreshadowing_and_setup", "priority_fixes", mode="before")
    @classmethod
    def _normalize_fields(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class RetrievalDocument(NovelForgeSchema):
    doc_id: str
    project_name: str
    source_type: str
    scope: Literal["project", "canon", "reference"] = "project"
    title: str = ""
    content: str
    chapter_no: int | None = None
    path: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class RetrievalChunk(NovelForgeSchema):
    chunk_id: str
    document_id: str
    project_name: str
    source_type: str
    scope: Literal["project", "canon", "reference"] = "project"
    title: str = ""
    content: str
    chapter_no: int | None = None
    path: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class RetrievalHit(NovelForgeSchema):
    chunk: RetrievalChunk
    score: float
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    retrieval_mode: str = "lexical"
    matched_terms: list[str] = Field(default_factory=list)

    @field_validator("matched_terms", mode="before")
    @classmethod
    def _normalize_matched_terms(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class RetrievalIndexManifest(NovelForgeSchema):
    project_name: str
    version: int = 1
    built_at: str
    document_count: int = 0
    chunk_count: int = 0
    embedding_model: str = ""
    embedding_enabled: bool = False
    documents: list[RetrievalDocument] = Field(default_factory=list)
    chunks: list[RetrievalChunk] = Field(default_factory=list)


class RetrievalVectorStore(NovelForgeSchema):
    project_name: str
    built_at: str
    embedding_model: str
    vectors: dict[str, list[float]] = Field(default_factory=dict)


def validate_review_result(data: dict[str, Any]) -> ReviewResult:
    return ReviewResult.model_validate(data)


def validate_memory_update_result(data: dict[str, Any], chapter_no: int) -> MemoryUpdateResult:
    payload = MemoryUpdatePayload.model_validate(data)
    return MemoryUpdateResult(chapter_no=chapter_no, **payload.model_dump())


def parse_operation_result(data: str | dict[str, Any]) -> OperationResult:
    if isinstance(data, str):
        return OperationResult.model_validate_json(data)
    return OperationResult.model_validate(data)


def format_schema_validation_error(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error.get("loc", [])) or "root"
        parts.append(f"{location}: {error.get('msg', 'invalid value')}")
    return "; ".join(parts)


def _markdown_section(title: str, items: list[str]) -> str:
    body = "\n".join(f"- {item}" for item in items) if items else "- 无"
    return f"## {title}\n\n{body}"


def render_character_analysis_markdown(result: CharacterAnalysisResult) -> str:
    return "\n\n".join([
        f"# {result.title}",
        _markdown_section("角色出场概览", result.character_overview),
        _markdown_section("角色行为与设定一致性", result.consistency_findings),
        _markdown_section("角色关系推进", result.relationship_progression),
        _markdown_section("发现的问题", result.issues),
        _markdown_section("修改建议", result.recommendations),
    ])


def render_timeline_analysis_markdown(result: TimelineAnalysisResult) -> str:
    return "\n\n".join([
        f"# {result.title}",
        _markdown_section("本章关键事件顺序", result.key_events),
        _markdown_section("与已有时间线的衔接", result.timeline_alignment),
        _markdown_section("可能的时间矛盾", result.contradictions),
        _markdown_section("节奏与推进评估", result.pacing_assessment),
        _markdown_section("修改建议", result.recommendations),
    ])


def render_foreshadowing_analysis_markdown(result: ForeshadowingAnalysisResult) -> str:
    return "\n\n".join([
        f"# {result.title}",
        _markdown_section("本章新增伏笔", result.new_foreshadowing),
        _markdown_section("已有伏笔的呼应或回收", result.callbacks_and_payoffs),
        _markdown_section("伏笔强度评估", result.strength_assessment),
        _markdown_section("发现的问题", result.issues),
        _markdown_section("修改建议", result.recommendations),
    ])


def render_consistency_analysis_markdown(result: ConsistencyAnalysisResult) -> str:
    overall = result.overall_conclusion or "无"
    return "\n\n".join([
        f"# {result.title}",
        f"## 总体结论\n\n{overall}",
        _markdown_section("角色一致性", result.character_consistency),
        _markdown_section("世界设定一致性", result.world_consistency),
        _markdown_section("时间线一致性", result.timeline_consistency),
        _markdown_section("伏笔与铺垫", result.foreshadowing_and_setup),
        _markdown_section("优先修改项", result.priority_fixes),
    ])
