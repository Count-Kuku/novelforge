from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


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


def _shorten_text(value: str, max_length: int = 40) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "..."


def _infer_knowledge_item_name(item: dict, index: int) -> str:
    for key in ("name", "title", "subject", "entity", "item", "summary", "content", "description"):
        text = _stringify_item(item.get(key))
        if text:
            return _shorten_text(text)

    details = item.get("details")
    if isinstance(details, dict):
        for key in ("名称", "标题", "对象", "角色", "物品", "能力", "地点", "组织", "事件", "关系"):
            text = _stringify_item(details.get(key))
            if text:
                return _shorten_text(text)
        text = _stringify_item(details)
        if text:
            return _shorten_text(text)

    evidence = item.get("evidence")
    if isinstance(evidence, list):
        for evidence_item in evidence:
            text = _stringify_item(evidence_item)
            if text:
                return _shorten_text(text)

    return f"未命名知识 {index + 1}"


SOURCE_TYPE_LABELS = {
    "external_source": "通用外部资料",
    "external_character_sheet": "角色资料",
    "external_location_sheet": "地点资料",
    "external_organization_sheet": "组织资料",
    "external_timeline_note": "时间线资料",
    "external_canon_event": "原作事件",
    "external_world_rule": "世界规则",
    "external_artifact_note": "道具资料",
}


def _label_source_type(value: str) -> str:
    return SOURCE_TYPE_LABELS.get(str(value or ""), str(value or "未知资料"))


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


class CreativeProfile(NovelForgeSchema):
    is_configured: bool = False
    story_mode: str = "主线故事"
    target_length: str = "长篇"
    target_word_count: str = ""
    workflow_depth: str = "完整长篇流程"
    reference_strength: str = "中参考"
    reference_focus: list[str] = Field(default_factory=lambda: ["角色", "世界观", "剧情事件"])
    allow_canon_deviation: bool = True
    conflict_policy: str = "优先项目设定"
    notes: str = ""

    @field_validator("reference_focus", mode="before")
    @classmethod
    def _normalize_reference_focus(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @model_validator(mode="after")
    def _migrate_legacy_length_modes(self):
        if self.story_mode in {"短篇", "中篇", "长篇"}:
            if not self.target_length or self.target_length == "长篇":
                self.target_length = self.story_mode
            self.story_mode = "主线故事"
        elif self.story_mode == "片段":
            if not self.target_length or self.target_length == "长篇":
                self.target_length = "片段"
            self.story_mode = "单场景片段"
        return self


class StoryMeta(NovelForgeSchema):
    story_id: str
    name: str = ""
    description: str = ""
    status: Literal["active", "archived"] = "active"
    created_at: str = ""
    updated_at: str = ""


class StoriesIndex(NovelForgeSchema):
    stories: list[StoryMeta] = Field(default_factory=list)
    active_story_id: str = "default"


class KnowledgeEvidence(NovelForgeSchema):
    source_title: str = ""
    quote: str = ""
    note: str = ""


class ExtractedKnowledgeItem(NovelForgeSchema):
    category: Literal[
        "characters",
        "items",
        "abilities",
        "world_rules",
        "locations",
        "organizations",
        "timeline_events",
        "relationships",
        "writing_style",
        "dialogue_style",
        "narrative_techniques",
        "constraints",
    ]
    name: str
    summary: str = ""
    details: dict[str, str] = Field(default_factory=dict)
    evidence: list[KnowledgeEvidence] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)

    @field_validator("details", mode="before")
    @classmethod
    def _normalize_details(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        normalized = {}
        for key, item in value.items():
            cleaned_key = str(key).strip()
            cleaned_value = _stringify_item(item)
            if cleaned_key and cleaned_value:
                normalized[cleaned_key] = cleaned_value
        return normalized

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class KnowledgeExtractionResult(NovelForgeSchema):
    source_title: str = ""
    source_summary: str = ""
    items: list[ExtractedKnowledgeItem] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("items", mode="before")
    @classmethod
    def _normalize_items(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]

        normalized = []
        for index, item in enumerate(value):
            if isinstance(item, dict):
                normalized_item = dict(item)
                if not _stringify_item(normalized_item.get("name")):
                    normalized_item["name"] = _infer_knowledge_item_name(normalized_item, index)
                normalized.append(normalized_item)
            else:
                normalized.append(item)
        return normalized

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


class VolumeDiscussionResult(NovelForgeSchema):
    title: str = "分卷讨论"
    volume_goal: str = ""
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


class ArcDiscussionResult(NovelForgeSchema):
    title: str = "剧情段讨论"
    arc_goal: str = ""
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


class CreativeProfileDiscussionResult(NovelForgeSchema):
    title: str = "创作配置讨论"
    current_understanding: str = ""
    key_constraints: list[str] = Field(default_factory=list)
    options: list[PlanningOption] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_direction: str = ""
    recommended_profile: CreativeProfile = Field(default_factory=CreativeProfile)
    approval_ready: bool = False

    @field_validator("key_constraints", "open_questions", "risks", mode="before")
    @classmethod
    def _normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class VolumeOutlineMetadata(NovelForgeSchema):
    volume_no: int
    title: str = ""
    summary: str = ""
    status: Literal["draft", "approved", "archived"] = "draft"
    has_approved_discussion: bool = False


class ArcOutlineMetadata(NovelForgeSchema):
    arc_no: int
    volume_no: int | None = None
    title: str = ""
    summary: str = ""
    status: Literal["draft", "approved", "archived"] = "draft"
    estimated_chapter_count: int | None = None
    target_word_count_range: str = ""
    has_approved_discussion: bool = False


class ChapterOutlineMetadata(NovelForgeSchema):
    chapter_no: int
    volume_no: int | None = None
    arc_no: int | None = None


class ChapterWritingGuidance(NovelForgeSchema):
    tone: str = ""
    pacing: str = ""
    dialogue_density: str = ""
    focus: list[str] = Field(default_factory=list)
    ending_strength: str = ""
    extra_requirements: str = ""

    @field_validator("focus", mode="before")
    @classmethod
    def _normalize_focus(cls, value: Any) -> list[str]:
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


class ConflictResolution(NovelForgeSchema):
    conflict_id: str
    shared_terms: list[str] = Field(default_factory=list)
    decision: Literal["use_project", "use_external", "merge", "ignore"] = "merge"
    note: str = ""
    project_source: str = ""
    external_source: str = ""
    updated_at: str = ""

    @field_validator("shared_terms", mode="before")
    @classmethod
    def _normalize_terms(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class ChapterAllocationItem(NovelForgeSchema):
    chapter_no: int
    title: str = ""
    chapter_goal: str = ""
    conflict: str = ""
    expected_word_count: str = ""
    key_events: list[str] = Field(default_factory=list)
    foreshadowing_dependencies: list[str] = Field(default_factory=list)

    @field_validator("key_events", "foreshadowing_dependencies", mode="before")
    @classmethod
    def _normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class ArcChapterPlanResult(NovelForgeSchema):
    title: str = "剧情段章节分配"
    arc_goal: str = ""
    planning_assumptions: list[str] = Field(default_factory=list)
    chapters: list[ChapterAllocationItem] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    @field_validator("planning_assumptions", "risks", mode="before")
    @classmethod
    def _normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class ChapterEvaluationResult(NovelForgeSchema):
    title: str = "章节质量评估"
    overall_score: int = Field(default=0, ge=0, le=100)
    character_consistency_score: int = Field(default=0, ge=0, le=100)
    plot_progression_score: int = Field(default=0, ge=0, le=100)
    information_density_score: int = Field(default=0, ge=0, le=100)
    emotional_impact_score: int = Field(default=0, ge=0, le=100)
    foreshadowing_score: int = Field(default=0, ge=0, le=100)
    prose_quality_score: int = Field(default=0, ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    revision_priorities: list[str] = Field(default_factory=list)
    summary: str = ""

    @field_validator("strengths", "issues", "revision_priorities", mode="before")
    @classmethod
    def _normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class ChapterConsistencyDiagnosis(NovelForgeSchema):
    characters: list[str] = Field(default_factory=list)
    world: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    foreshadowing: list[str] = Field(default_factory=list)

    @field_validator("characters", "world", "timeline", "foreshadowing", mode="before")
    @classmethod
    def _normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class ComprehensiveChapterEvaluationResult(NovelForgeSchema):
    title: str = "章节综合评价"
    status: Literal["pass", "revise", "blocked"] = "revise"
    verdict_summary: str = ""
    overall_score: int = Field(default=0, ge=0, le=100)
    character_consistency_score: int = Field(default=0, ge=0, le=100)
    plot_progression_score: int = Field(default=0, ge=0, le=100)
    information_density_score: int = Field(default=0, ge=0, le=100)
    emotional_impact_score: int = Field(default=0, ge=0, le=100)
    foreshadowing_score: int = Field(default=0, ge=0, le=100)
    prose_quality_score: int = Field(default=0, ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    consistency_diagnosis: ChapterConsistencyDiagnosis = Field(default_factory=ChapterConsistencyDiagnosis)
    revision_priorities: list[str] = Field(default_factory=list)
    next_action: str = ""
    summary: str = ""

    @field_validator("verdict_summary", "next_action", "summary", mode="before")
    @classmethod
    def _normalize_text(cls, value: Any) -> str:
        return _stringify_item(value)

    @field_validator("strengths", "blocking_issues", "issues", "revision_priorities", mode="before")
    @classmethod
    def _normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


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
    parent_run_id: str = ""
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
        lines.extend(["", "## 资料摘要", "", result.source_summary])
    if result.notes:
        lines.extend(["", "## 备注", ""])
        lines.extend([f"- {item}" for item in result.notes])

    for index, entry in enumerate(result.entries, start=1):
        lines.extend(["", f"## [{index}] {entry.title}", ""])
        lines.append(f"- 资料类型：{_label_source_type(entry.source_type)}")
        if entry.tags:
            lines.append(f"- 标签：{', '.join(entry.tags)}")
        if entry.summary:
            lines.extend(["", "### 摘要", "", entry.summary])
        if entry.content:
            lines.extend(["", "### 详细内容", "", entry.content])
        if entry.extra_fields:
            lines.extend(["", "### 补充字段", ""])
            for key, value in entry.extra_fields.items():
                lines.append(f"- {key}: {value}")

    return "\n".join(lines)


KNOWLEDGE_CATEGORY_LABELS = {
    "characters": "角色知识",
    "items": "物品与道具",
    "abilities": "技能与能力",
    "world_rules": "世界观规则",
    "locations": "地点资料",
    "organizations": "组织资料",
    "timeline_events": "事件与时间线",
    "relationships": "角色关系",
    "writing_style": "写作风格",
    "dialogue_style": "对白风格",
    "narrative_techniques": "写作手法",
    "constraints": "硬性约束",
}


def label_knowledge_category(value: str) -> str:
    return KNOWLEDGE_CATEGORY_LABELS.get(str(value or ""), str(value or "未知知识"))


def render_knowledge_extraction_markdown(result: KnowledgeExtractionResult) -> str:
    lines = [f"# {result.source_title or '资料知识提取结果'}"]
    if result.source_summary:
        lines.extend(["", "## 资料摘要", "", result.source_summary])

    grouped: dict[str, list[ExtractedKnowledgeItem]] = {}
    for item in result.items:
        grouped.setdefault(item.category, []).append(item)

    if not grouped:
        lines.extend(["", "## 提取结果", "", "- 未提取到可保存知识。"])

    for category, items in grouped.items():
        lines.extend(["", f"## {label_knowledge_category(category)}", ""])
        for index, item in enumerate(items, start=1):
            lines.append(f"### [{index}] {item.name}")
            if item.summary:
                lines.extend(["", item.summary])
            lines.append(f"- 可信度：{item.confidence:.2f}")
            if item.tags:
                lines.append(f"- 标签：{', '.join(item.tags)}")
            if item.details:
                lines.append("- 细节：")
                for key, value in item.details.items():
                    lines.append(f"  - {key}：{value}")
            evidence_lines = [evidence for evidence in item.evidence if evidence.quote or evidence.note]
            if evidence_lines:
                lines.append("- 证据：")
                for evidence in evidence_lines[:3]:
                    source = evidence.source_title or result.source_title or "未标明来源"
                    quote = evidence.quote or evidence.note
                    lines.append(f"  - {source}：{quote}")
            lines.append("")

    if result.notes:
        lines.extend(["", "## 备注", ""])
        lines.extend([f"- {item}" for item in result.notes])

    return "\n".join(lines).strip()


def render_discussion_markdown(
    result: OutlineDiscussionResult | ChapterDiscussionResult | VolumeDiscussionResult | ArcDiscussionResult | CreativeProfileDiscussionResult,
) -> str:
    lines = [f"# {result.title}"]

    goal_sections = [
        ("chapter_goal", "章节目标"),
        ("volume_goal", "分卷目标"),
        ("arc_goal", "剧情段目标"),
    ]
    for attr_name, label in goal_sections:
        goal = getattr(result, attr_name, "")
        if goal:
            lines.extend(["", f"## {label}", "", goal])

    if result.current_understanding:
        lines.extend(["", "## 当前理解", "", result.current_understanding])

    if getattr(result, "core_goals", []):
        lines.extend(["", "## 核心目标", ""])
        lines.extend([f"- {item}" for item in result.core_goals])

    if result.key_constraints:
        lines.extend(["", "## 关键约束", ""])
        lines.extend([f"- {item}" for item in result.key_constraints])

    if result.options:
        lines.extend(["", "## 可选方案", ""])
        for index, option in enumerate(result.options, start=1):
            lines.append(f"### [{index}] {option.title}")
            if option.summary:
                lines.extend(["", option.summary, ""])
            if option.strengths:
                lines.append("优点：")
                lines.extend([f"- {item}" for item in option.strengths])
            if option.risks:
                lines.append("风险：")
                lines.extend([f"- {item}" for item in option.risks])
            lines.append("")

    if result.open_questions:
        lines.extend(["", "## 待确认问题", ""])
        lines.extend([f"- {item}" for item in result.open_questions])

    if result.risks:
        lines.extend(["", "## 风险", ""])
        lines.extend([f"- {item}" for item in result.risks])

    if result.recommended_direction:
        lines.extend(["", "## 推荐方向", "", result.recommended_direction])

    recommended_profile = getattr(result, "recommended_profile", None)
    if isinstance(recommended_profile, CreativeProfile):
        lines.extend(["", "## 推荐创作配置", ""])
        lines.extend([
            f"- 任务性质：{recommended_profile.story_mode or '-'}",
            f"- 目标篇幅：{recommended_profile.target_length or '-'}",
            f"- 目标字数：{recommended_profile.target_word_count or '未设置'}",
            f"- 生成层级：{recommended_profile.workflow_depth or '-'}",
            f"- 资料参考强度：{recommended_profile.reference_strength or '-'}",
            f"- 重点参考方向：{', '.join(recommended_profile.reference_focus or []) or '未设置'}",
            f"- 允许改写原设：{'是' if recommended_profile.allow_canon_deviation else '否'}",
            f"- 资料冲突处理：{recommended_profile.conflict_policy or '-'}",
            f"- 自由说明：{recommended_profile.notes or '无'}",
        ])

    lines.extend(["", f"是否可批准：`{result.approval_ready}`"])
    return "\n".join(lines)


def render_arc_chapter_plan_markdown(result: ArcChapterPlanResult) -> str:
    lines = [f"# {result.title}"]
    if result.arc_goal:
        lines.extend(["", "## 剧情段目标", "", result.arc_goal])
    if result.planning_assumptions:
        lines.extend(["", "## 规划假设", ""])
        lines.extend([f"- {item}" for item in result.planning_assumptions])
    if result.chapters:
        lines.extend(["", "## 章节分配", ""])
        for item in result.chapters:
            lines.append(f"### 第 {item.chapter_no:03d} 章：{item.title or '未命名'}")
            lines.extend(["", f"- 目标：{item.chapter_goal or '无'}"])
            lines.append(f"- 冲突：{item.conflict or '无'}")
            lines.append(f"- 预计字数：{item.expected_word_count or '未设置'}")
            if item.key_events:
                lines.append("- 关键事件：")
                lines.extend([f"  - {event}" for event in item.key_events])
            if item.foreshadowing_dependencies:
                lines.append("- 伏笔依赖：")
                lines.extend([f"  - {dependency}" for dependency in item.foreshadowing_dependencies])
            lines.append("")
    if result.risks:
        lines.extend(["", "## 风险", ""])
        lines.extend([f"- {item}" for item in result.risks])
    return "\n".join(lines).strip()


def render_chapter_evaluation_markdown(result: ChapterEvaluationResult) -> str:
    score_lines = [
        f"- 总分：{result.overall_score}",
        f"- 角色一致性：{result.character_consistency_score}",
        f"- 剧情推进：{result.plot_progression_score}",
        f"- 信息密度：{result.information_density_score}",
        f"- 情绪冲击：{result.emotional_impact_score}",
        f"- 伏笔处理：{result.foreshadowing_score}",
        f"- 文笔质量：{result.prose_quality_score}",
    ]
    return "\n\n".join([
        f"# {result.title}",
        "## 评分\n\n" + "\n".join(score_lines),
        f"## 总结\n\n{result.summary or '无'}",
        _markdown_section("优点", result.strengths),
        _markdown_section("问题", result.issues),
        _markdown_section("优先修改项", result.revision_priorities),
    ])


def render_comprehensive_chapter_evaluation_markdown(result: ComprehensiveChapterEvaluationResult) -> str:
    score_lines = [
        f"- 总分：{result.overall_score}",
        f"- 角色一致性：{result.character_consistency_score}",
        f"- 剧情推进：{result.plot_progression_score}",
        f"- 信息密度：{result.information_density_score}",
        f"- 情绪效果：{result.emotional_impact_score}",
        f"- 伏笔处理：{result.foreshadowing_score}",
        f"- 文字完成度：{result.prose_quality_score}",
    ]
    diagnosis = result.consistency_diagnosis
    return "\n\n".join([
        f"# {result.title}",
        f"## 总结论\n\n- 状态：`{result.status}`\n- 结论：{result.verdict_summary or '无'}\n- 下一步：{result.next_action or '无'}",
        "## 评分\n\n" + "\n".join(score_lines),
        f"## 总结\n\n{result.summary or '无'}",
        _markdown_section("优点", result.strengths),
        _markdown_section("阻塞问题", result.blocking_issues),
        _markdown_section("主要问题", result.issues),
        "## 一致性诊断\n\n"
        + _markdown_section("角色", diagnosis.characters)
        + "\n\n"
        + _markdown_section("世界观", diagnosis.world)
        + "\n\n"
        + _markdown_section("时间线", diagnosis.timeline)
        + "\n\n"
        + _markdown_section("伏笔", diagnosis.foreshadowing),
        _markdown_section("优先修改项", result.revision_priorities),
    ])
