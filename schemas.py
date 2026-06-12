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


class OrganizedReferenceEntry(NovelForgeSchema):
    source_type: Literal[
        "external_source",
        "external_character_sheet",
        "external_location_sheet",
        "external_organization_sheet",
        "external_timeline_note",
        "external_canon_event",
        "external_world_rule",
        "external_artifact_note",
    ] = "external_source"
    title: str
    summary: str = ""
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    extra_fields: dict[str, str] = Field(default_factory=dict)

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("extra_fields", mode="before")
    @classmethod
    def _normalize_extra_fields(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        normalized = {}
        for key, item in value.items():
            cleaned_key = str(key).strip()
            cleaned_value = _stringify_item(item)
            if cleaned_key and cleaned_value:
                normalized[cleaned_key] = cleaned_value
        return normalized


class OrganizedReferenceResult(NovelForgeSchema):
    source_title: str = ""
    source_summary: str = ""
    entries: list[OrganizedReferenceEntry] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("notes", mode="before")
    @classmethod
    def _normalize_notes(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class PlanningOption(NovelForgeSchema):
    title: str
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    @field_validator("strengths", "risks", mode="before")
    @classmethod
    def _normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class OutlineDiscussionResult(NovelForgeSchema):
    title: str = "全书大纲讨论"
    current_understanding: str = ""
    core_goals: list[str] = Field(default_factory=list)
    key_constraints: list[str] = Field(default_factory=list)
    options: list[PlanningOption] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_direction: str = ""
    approval_ready: bool = False

    @field_validator("core_goals", "key_constraints", "open_questions", "risks", mode="before")
    @classmethod
    def _normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class ChapterDiscussionResult(NovelForgeSchema):
    title: str = "章节讨论"
    chapter_goal: str = ""
    current_understanding: str = ""
    key_constraints: list[str] = Field(default_factory=list)
    options: list[PlanningOption] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_direction: str = ""
    approval_ready: bool = False

    @field_validator("key_constraints", "open_questions", "risks", mode="before")
    @classmethod
    def _normalize_lists(cls, value: Any) -> list[str]:
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


class RetrievalConflict(NovelForgeSchema):
    shared_terms: list[str] = Field(default_factory=list)
    project_hit: RetrievalHit
    external_hit: RetrievalHit
    project_authority: str = "project"
    external_authority: str = "unknown"
    severity: Literal["low", "medium", "high"] = "low"
    rationale: str = ""


class ValidationStatus(NovelForgeSchema):
    status: Literal["not_applicable", "passed", "failed"] = "not_applicable"
    schema_name: str = ""
    message: str = ""
    errors: list[str] = Field(default_factory=list)


class WorkflowStepResult(NovelForgeSchema):
    step_name: str
    success: bool
    status: Literal["completed", "failed", "rejected", "skipped"]
    data: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    warnings: list[str] = Field(default_factory=list)
    retrieval_hits: list[RetrievalHit] = Field(default_factory=list)
    validation: ValidationStatus = Field(default_factory=ValidationStatus)
    artifacts: dict[str, Any] = Field(default_factory=dict)


class WorkflowPipelineResult(NovelForgeSchema):
    success: bool
    steps: dict[str, WorkflowStepResult] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class WorkflowError(NovelForgeSchema):
    step_name: str
    error_type: Literal["llm", "validation", "persistence", "retrieval", "input", "unknown"] = "unknown"
    message: str
    recoverable: bool = True


class WorkflowTransition(NovelForgeSchema):
    from_step: str
    to_step: str
    reason: str = ""
    timestamp: str = ""


class ChapterPipelineState(NovelForgeSchema):
    run_id: str = ""
    project_name: str
    chapter_no: int
    user_requirement: str = ""
    word_count: str = "2000-2500"
    current_step: str = "pending"
    next_step: str = ""
    last_successful_step: str = ""
    chapter_outline: str = ""
    chapter: str = ""
    review: dict[str, Any] = Field(default_factory=dict)
    review_markdown: str = ""
    memory_update: dict[str, Any] = Field(default_factory=dict)
    steps: dict[str, WorkflowStepResult] = Field(default_factory=dict)
    completed_steps: list[str] = Field(default_factory=list)
    failed_steps: list[str] = Field(default_factory=list)
    retry_counts: dict[str, int] = Field(default_factory=dict)
    transition_log: list[WorkflowTransition] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[WorkflowError] = Field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    halted: bool = False
    halt_reason: str = ""
    resumable: bool = False
    success: bool = False


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


def render_organized_reference_markdown(result: OrganizedReferenceResult) -> str:
    lines = [f"# {result.source_title or '资料整理结果'}"]
    if result.source_summary:
        lines.extend(["", "## Source Summary", "", result.source_summary])
    if result.notes:
        lines.extend(["", "## Notes", ""])
        lines.extend([f"- {item}" for item in result.notes])

    for index, entry in enumerate(result.entries, start=1):
        lines.extend(["", f"## [{index}] {entry.title}", ""])
        lines.append(f"- type: `{entry.source_type}`")
        if entry.tags:
            lines.append(f"- tags: {', '.join(entry.tags)}")
        if entry.summary:
            lines.extend(["", "### Summary", "", entry.summary])
        if entry.content:
            lines.extend(["", "### Details", "", entry.content])
        if entry.extra_fields:
            lines.extend(["", "### Extra Fields", ""])
            for key, value in entry.extra_fields.items():
                lines.append(f"- {key}: {value}")

    return "\n".join(lines)


def render_discussion_markdown(result: OutlineDiscussionResult | ChapterDiscussionResult) -> str:
    lines = [f"# {result.title}"]

    chapter_goal = getattr(result, "chapter_goal", "")
    if chapter_goal:
        lines.extend(["", "## Chapter Goal", "", chapter_goal])

    if result.current_understanding:
        lines.extend(["", "## Current Understanding", "", result.current_understanding])

    if getattr(result, "core_goals", []):
        lines.extend(["", "## Core Goals", ""])
        lines.extend([f"- {item}" for item in result.core_goals])

    if result.key_constraints:
        lines.extend(["", "## Key Constraints", ""])
        lines.extend([f"- {item}" for item in result.key_constraints])

    if result.options:
        lines.extend(["", "## Options", ""])
        for index, option in enumerate(result.options, start=1):
            lines.append(f"### [{index}] {option.title}")
            if option.summary:
                lines.extend(["", option.summary, ""])
            if option.strengths:
                lines.append("Strengths:")
                lines.extend([f"- {item}" for item in option.strengths])
            if option.risks:
                lines.append("Risks:")
                lines.extend([f"- {item}" for item in option.risks])
            lines.append("")

    if result.open_questions:
        lines.extend(["", "## Open Questions", ""])
        lines.extend([f"- {item}" for item in result.open_questions])

    if result.risks:
        lines.extend(["", "## Risks", ""])
        lines.extend([f"- {item}" for item in result.risks])

    if result.recommended_direction:
        lines.extend(["", "## Recommended Direction", "", result.recommended_direction])

    lines.extend(["", f"Approval Ready: `{result.approval_ready}`"])
    return "\n".join(lines)
