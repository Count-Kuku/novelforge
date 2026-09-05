"""Creative profile, story, knowledge and planning schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from novelforge.core.schemas._base import (
    NovelForgeSchema,
    _infer_knowledge_item_name,
    _normalize_string_list,
    _stringify_item,
)

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
    worldline_id: str = "main"
    worldline_label: str = "本项目主线"
    worldline_retrieval_mode: Literal["prefer", "strict"] = "prefer"
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
    creation_mode: Literal["planned", "conversational"] = "planned"
    created_at: str = ""
    updated_at: str = ""


class StoriesIndex(NovelForgeSchema):
    stories: list[StoryMeta] = Field(default_factory=list)
    active_story_id: str = "default"


class KnowledgeEvidence(NovelForgeSchema):
    source_title: str = ""
    quote: str = ""
    note: str = ""
    source_id: str = ""
    source_revision_id: str = ""
    segment_id: str = ""
    chunk_id: str = ""
    start_offset: int | None = None
    end_offset: int | None = None
    prefix: str = ""
    suffix: str = ""
    validation_status: str = "unverified"


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
    ]
    name: str
    summary: str = ""
    details: dict[str, str] = Field(default_factory=dict)
    typed_data: dict[str, Any] = Field(default_factory=dict)
    setting_field: str = ""
    fact_key: str = ""
    aliases: list[str] = Field(default_factory=list)
    schema_version: int = Field(default=2, ge=1)
    evidence: list[KnowledgeEvidence] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_strength: float = Field(default=0.5, ge=0.0, le=1.0)
    canon_status: str = "unknown"
    extraction_mode: str = "general"
    source_segment_id: str = ""
    source_segment_ids: list[str] = Field(default_factory=list)
    source_segment_index: int | None = None
    source_segment_title: str = ""
    source_segment_titles: list[str] = Field(default_factory=list)
    merged_from_pending_ids: list[str] = Field(default_factory=list)
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

    @field_validator("source_segment_ids", "source_segment_titles", "merged_from_pending_ids", mode="before")
    @classmethod
    def _normalize_trace_lists(cls, value: Any) -> list[str]:
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
    # refactor 2 P2（D6）：章节/arc 级世界线注入来源。None=继承 profile/story 主世界线。
    worldline_id: str | None = None
    worldline_label: str = ""


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
    prompt_option_ids: list[str] = Field(default_factory=list)
    manual_knowledge_ids: list[str] = Field(default_factory=list)

    @field_validator("focus", "prompt_option_ids", "manual_knowledge_ids", mode="before")
    @classmethod
    def _normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)
