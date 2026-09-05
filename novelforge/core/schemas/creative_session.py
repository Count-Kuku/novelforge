"""Creative session, context and prompt option schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from novelforge.core.schemas._base import (
    NovelForgeSchema,
    _infer_knowledge_item_name,
    _normalize_string_list,
    _stringify_item,
)

class CreativeSession(NovelForgeSchema):
    session_id: str
    story_id: str
    title: str = ""
    status: Literal["active", "completed", "archived"] = "active"
    session_goal: str = ""
    writing_guidance: dict[str, Any] = Field(default_factory=dict)
    target_chapter_no: int | None = Field(default=None, ge=1)
    rolling_summary: str = ""
    summary_fragment_id: str | None = None
    active_fragment_id: str | None = None
    worldline_id: str = "main"
    auto_extract_mode: Literal["manual", "on_accept"] = "manual"
    created_at: str = ""
    updated_at: str = ""


class CreativeTurn(NovelForgeSchema):
    turn_id: str
    session_id: str
    turn_index: int = Field(ge=1)
    user_message: str
    action_type: Literal["generate", "continue", "rewrite", "branch", "revise"] = "generate"
    parent_fragment_id: str | None = None
    status: Literal["running", "completed", "failed"] = "running"
    error_text: str = ""
    created_at: str = ""
    updated_at: str = ""


class CreativeFragment(NovelForgeSchema):
    fragment_id: str
    session_id: str
    turn_id: str
    parent_fragment_id: str | None = None
    content: str
    status: Literal["proposed", "accepted", "superseded", "discarded", "finalized"] = "proposed"
    content_hash: str = ""
    word_count: int = Field(default=0, ge=0)
    context_snapshot_id: str | None = None
    extraction_status: Literal["not_started", "running", "completed", "failed"] = "not_started"
    created_at: str = ""
    accepted_at: str | None = None


class CreativeAttachment(NovelForgeSchema):
    attachment_id: str
    content_hash: str
    source_id: str
    source_revision_id: str | None = None
    relative_path: str
    title: str = ""
    filename: str = ""
    media_type: str = ""
    attachment_kind: Literal["file", "pasted_text", "url", "existing_source"] = "file"
    scope: Literal["turn", "session", "story", "project"] = "session"
    story_id: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    remaining_uses: int | None = Field(default=None, ge=0)
    status: Literal["parsed", "indexed", "processing", "ready", "failed"] = "indexed"
    ingestion_task_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    task_status: str = ""
    task_message: str = ""
    task_progress: dict[str, Any] = Field(default_factory=dict)
    task_stages: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class CreativeSessionBundle(NovelForgeSchema):
    session: CreativeSession
    turns: list[CreativeTurn] = Field(default_factory=list)
    fragments: list[CreativeFragment] = Field(default_factory=list)
    attachments: list[CreativeAttachment] = Field(default_factory=list)


class ContextDirective(NovelForgeSchema):
    directive_id: str = ""
    name: str = ""
    content: str = ""
    scope: Literal["project", "story", "chapter", "run"] = "story"
    story_id: str | None = None
    chapter_start: int | None = Field(default=None, ge=1)
    chapter_end: int | None = Field(default=None, ge=1)
    capabilities: list[str] = Field(default_factory=list)
    placement: Literal[
        "hard_constraints",
        "story_state",
        "chapter_direction",
        "character_voice",
        "style",
        "reference",
    ] = "chapter_direction"
    priority: int = 50
    enabled: bool = True
    remaining_uses: int | None = Field(default=None, ge=0)
    expires_at: str | None = None
    created_at: str = ""
    updated_at: str = ""

    @field_validator("capabilities", mode="before")
    @classmethod
    def _normalize_capabilities(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @model_validator(mode="after")
    def _validate_directive(self):
        if self.scope == "chapter" and self.chapter_start is None and self.chapter_end is None:
            raise ValueError("chapter-scoped directives require a chapter range")
        if self.chapter_start is not None and self.chapter_end is not None and self.chapter_end < self.chapter_start:
            raise ValueError("chapter_end cannot be earlier than chapter_start")
        if self.scope == "run" and self.remaining_uses is None:
            self.remaining_uses = 1
        return self


class ContextBlock(NovelForgeSchema):
    block_id: str
    category: str
    content: str
    source_type: str
    source_ref: str | None = None
    scope: str = "project"
    story_id: str | None = None
    worldline: str | None = None
    placement: str = "reference"
    priority: int = 0
    hard_constraint: bool = False
    activation_reason: str = ""
    estimated_tokens: int = 0
    included: bool = True
    omission_reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextAssembly(NovelForgeSchema):
    assembly_id: str
    capability: str
    query: str
    chapter_no: int | None = None
    blocks: list[ContextBlock] = Field(default_factory=list)
    retrieval_hits: list[dict[str, Any]] = Field(default_factory=list)
    total_estimated_tokens: int = 0
    context_budget: int = 0
    omitted_blocks: list[ContextBlock] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    hard_budget_exceeded: bool = False
    fingerprint: str = ""
    created_at: str = ""


class PromptOption(NovelForgeSchema):
    id: str = ""
    name: str = ""
    scope: str = "story"
    capability: str = "write"
    category: str = "custom"
    slot: str = "custom"
    content: str = ""
    enabled: bool = True
    built_in: bool = False
    priority: int = 50
    source: str = "manual"
    source_kind: str = ""
    source_ref: str = ""
    tags: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)
