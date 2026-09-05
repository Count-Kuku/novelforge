"""Retrieval and evaluation schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from novelforge.core.schemas._base import (
    NovelForgeSchema,
    _infer_knowledge_item_name,
    _normalize_string_list,
    _stringify_item,
)

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
    expanded_terms: list[str] = Field(default_factory=list)
    match_reasons: list[str] = Field(default_factory=list)
    score_breakdown: dict[str, float] = Field(default_factory=dict)

    @field_validator("matched_terms", mode="before")
    @classmethod
    def _normalize_matched_terms(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("expanded_terms", "match_reasons", mode="before")
    @classmethod
    def _normalize_retrieval_lists(cls, value: Any) -> list[str]:
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
    # Hash of the exact title/content text used to produce each vector.  A
    # stable chunk id alone is not sufficient because users can edit a chunk
    # without changing its position in the document.
    content_hashes: dict[str, str] = Field(default_factory=dict)
    build_mode: Literal["full", "incremental"] = "full"
    reused_vector_count: int = Field(default=0, ge=0)
    generated_vector_count: int = Field(default=0, ge=0)
    removed_vector_count: int = Field(default=0, ge=0)


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
    story_id: str = ""
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
