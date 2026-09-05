"""Workflow pipeline schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from novelforge.core.schemas._base import (
    NovelForgeSchema,
    _infer_knowledge_item_name,
    _normalize_string_list,
    _stringify_item,
)
from novelforge.core.schemas.retrieval import RetrievalHit

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
    setting_extraction: dict[str, Any] = Field(default_factory=dict)
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
