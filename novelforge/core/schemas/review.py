"""Chapter review and analysis result schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from novelforge.core.schemas._base import (
    NovelForgeSchema,
    _infer_knowledge_item_name,
    _normalize_string_list,
    _stringify_item,
)

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

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, value: Any) -> str:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"pass", "revise", "blocked"}:
                return lowered
        return str(value).strip()


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
