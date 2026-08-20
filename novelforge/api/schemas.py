"""Transport DTOs for the versioned HTTP API.

The DTO layer deliberately does not expose the large internal workflow models;
that keeps the frontend contract stable while the Python services evolve.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


CreationMode = Literal["planned", "conversational"]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateProjectRequest(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    title: str = Field(default="", max_length=200)
    genre: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=2000)


class RenameProjectRequest(ApiModel):
    name: str = Field(min_length=1, max_length=120)


class CreateStoryRequest(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    creation_mode: CreationMode = "planned"


class SetStoryModeRequest(ApiModel):
    creation_mode: CreationMode


class UpdateOutlineRequest(ApiModel):
    content: str = Field(max_length=500_000)


class UpdateChapterRequest(ApiModel):
    content: str = Field(max_length=2_000_000)
    kind: Literal["content", "outline"] = "content"


class UpdateStructureAssetRequest(ApiModel):
    outline: str | None = Field(default=None, max_length=500_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateChapterPlanRequest(ApiModel):
    plan: dict[str, Any] = Field(default_factory=dict)
    report_markdown: str = Field(default="", max_length=200_000)


class UpdateProfileRequest(ApiModel):
    """Validated transport wrapper for the stable creative-profile object.

    The profile itself is normalized by the domain schema. Keeping the API
    wrapper open at this one boundary lets new profile fields ship without a
    frontend/server lockstep migration while still rejecting unknown request
    envelope keys.
    """

    profile: dict[str, Any] = Field(default_factory=dict)


class DiscussionRequest(ApiModel):
    idea: str = Field(min_length=1, max_length=20_000)


class DiscussionApprovalRequest(ApiModel):
    step: dict[str, Any] = Field(default_factory=dict)


class FragmentActionRequest(ApiModel):
    fragment_id: str = Field(min_length=1, max_length=160)


class RenameStoryRequest(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)


class CopyStoryRequest(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    include_discussions: bool = True
    include_summaries: bool = True
    include_chapters: bool = True


class CreateSessionRequest(ApiModel):
    session_goal: str = Field(min_length=1, max_length=4000)
    title: str = Field(default="", max_length=200)
    auto_extract_mode: Literal["manual", "on_accept"] | None = None


class CreateAttachmentRequest(ApiModel):
    text: str = Field(min_length=1, max_length=500_000)
    title: str = Field(default="粘贴资料", max_length=200)
    scope: Literal["turn", "session", "story", "project"] = "session"


class CreateUrlAttachmentRequest(ApiModel):
    url: str = Field(min_length=8, max_length=2000)
    scope: Literal["turn", "session", "story", "project"] = "session"


class PlanActionRequest(ApiModel):
    request: str = Field(min_length=1, max_length=20_000)
    idempotency_key: str = Field(default="", max_length=200)


class ExecuteActionRequest(ApiModel):
    confirmed: bool = False


class PendingKnowledgeRequest(ApiModel):
    pending_ids: list[str] = Field(default_factory=list, max_length=500)


class KnowledgeUpdateRequest(ApiModel):
    patch: dict[str, Any] = Field(default_factory=dict)
    target_category: str | None = Field(default=None, max_length=80)
    reason: str = Field(default="Vue 工作区编辑", max_length=500)
    expected_revision_id: str | None = Field(default=None, max_length=160)


class RestoreRevisionRequest(ApiModel):
    revision_id: str = Field(min_length=1, max_length=160)
    reason: str = Field(default="从 Vue 工作区恢复历史修订", max_length=500)


class ModelProfileRequest(ApiModel):
    profile_id: str = Field(default="", max_length=120)
    name: str = Field(min_length=1, max_length=160)
    provider_type: str = Field(default="auto", max_length=80)
    base_url: str = Field(default="", max_length=500)
    model_name: str = Field(default="", max_length=160)
    embedding_mode: str = Field(default="disabled", max_length=40)
    embedding_model_name: str = Field(default="", max_length=160)
    embedding_base_url: str = Field(default="", max_length=500)
    api_key: str = Field(default="", max_length=1000)
    embedding_api_key: str = Field(default="", max_length=1000)
    cost_tracking_mode: str = Field(default="auto", max_length=40)


class ActiveModelProfileRequest(ApiModel):
    profile_id: str = Field(min_length=1, max_length=120)


class RulesUpdateRequest(ApiModel):
    rules: dict[str, Any] = Field(default_factory=dict)


class PromptOptionsUpdateRequest(ApiModel):
    options: list[dict[str, Any]] = Field(default_factory=list, max_length=500)


class AutoConfigurationRequest(ApiModel):
    operation: str = Field(min_length=1, max_length=120)
    goal: str = Field(default="", max_length=4000)
    source_chars: int = Field(default=0, ge=0, le=100_000_000)
    locked_fields: list[str] = Field(default_factory=list, max_length=20)


class ResearchClaimsReviewRequest(ApiModel):
    claim_ids: list[str] = Field(default_factory=list, min_length=1, max_length=500)


class ChapterPlanValidationRequest(ApiModel):
    plan: dict[str, Any] = Field(default_factory=dict)


class ContentDeleteRequest(ApiModel):
    resource: dict[str, Any] = Field(default_factory=dict)
    confirm: bool = False


class ResearchTaskRequest(ApiModel):
    topic: str = Field(min_length=1, max_length=500)
    objective: str = Field(default="", max_length=4000)
    source_kinds: list[str] = Field(default_factory=list, max_length=10)
    official_domains: list[str] = Field(default_factory=list, max_length=30)
    max_results_per_branch: int = Field(default=5, ge=1, le=20)
    max_pages: int = Field(default=8, ge=1, le=20)
    language: str = Field(default="zh-hans", max_length=20)
    freshness: str = Field(default="", max_length=8)
    scope: Literal["canon", "reference", "project"] = "reference"
    story_id: str = Field(default="", max_length=120)


class TaskControlRequest(ApiModel):
    action: Literal["pause", "resume", "cancel", "retry"]


class UpdateSessionRequest(ApiModel):
    title: str | None = Field(default=None, max_length=200)
    status: Literal["active", "archived"] | None = None


class GenerateTurnRequest(ApiModel):
    user_message: str = Field(min_length=1, max_length=20000)
    action_type: Literal["continue", "rewrite", "branch"] = "continue"
    word_count: str = Field(default="800-1200", max_length=40)
    branch_from_fragment_id: str | None = Field(default=None, max_length=120)


class ApiError(BaseModel):
    code: str
    message: str
    details: Any = None


class ProjectItem(BaseModel):
    project_id: str
    name: str
    title: str
    genre: str = ""
    description: str = ""
    updated_at: str = ""
    story_count: int = 0


class StoryItem(BaseModel):
    story_id: str
    name: str
    description: str = ""
    status: str = "active"
    creation_mode: CreationMode = "planned"
    created_at: str = ""
    updated_at: str = ""
