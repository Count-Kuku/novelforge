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


class ReferenceLibraryCreateRequest(ApiModel):
    title: str = Field(min_length=1, max_length=300)
    source_kind: str = Field(default="reference", max_length=80)
    source_id: str | None = Field(default=None, max_length=160)


class ReferenceLibraryReleaseRequest(ApiModel):
    knowledge_ids: list[str] = Field(default_factory=list, max_length=5000)
    release_id: str | None = Field(default=None, max_length=160)
    content_hash: str | None = Field(default=None, max_length=160)
    manifest: dict[str, Any] = Field(default_factory=dict)


class StoryLibraryBindingRequest(ApiModel):
    release_id: str = Field(min_length=1, max_length=160)
    branch_id: str | None = Field(default=None, max_length=160)
    idempotency_key: str = Field(default="", max_length=200)


class LegacyStoryLibraryMigrationRequest(ApiModel):
    class Selection(ApiModel):
        library_id: str = Field(min_length=1, max_length=160)
        release_id: str = Field(min_length=1, max_length=160)
        branch_id: str | None = Field(default=None, max_length=160)

    selections: list[Selection] = Field(default_factory=list, max_length=100)
    # Backward-compatible single selection; the service normalizes it into the
    # same atomic multi-library transaction.
    library_id: str | None = Field(default=None, max_length=160)
    release_id: str | None = Field(default=None, max_length=160)
    branch_id: str | None = Field(default=None, max_length=160)
    confirmed: bool = False


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
    branch_id: str | None = Field(default=None, max_length=200)


class BranchContextRequest(ApiModel):
    branch_id: str | None = Field(default=None, max_length=200)


class RenameStoryRequest(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)


class CopyStoryRequest(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    include_discussions: bool = True
    include_summaries: bool = True
    include_chapters: bool = True


class CreateBranchRequest(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    parent_branch_id: str | None = Field(default=None, max_length=200)
    fork_fragment_id: str | None = Field(default=None, max_length=200)
    fork_checkpoint_id: str | None = Field(default=None, max_length=200)
    allow_current_state: bool = False


class UpdateBranchRequest(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    status: Literal["active", "archived"] | None = None


class BranchCheckpointRequest(ApiModel):
    frontier_fragment_id: str | None = Field(default=None, max_length=200)
    extraction_status: Literal["ready", "completed", "skipped", "pending"] = "ready"
    reason: str = Field(default="", max_length=500)
    allow_current_state: bool = False


class CreateSessionRequest(ApiModel):
    session_goal: str = Field(default="", max_length=4000)
    title: str = Field(default="", max_length=200)
    auto_extract_mode: Literal["manual", "on_accept"] | None = None
    branch_id: str | None = Field(default=None, max_length=200)


class CreateAttachmentRequest(ApiModel):
    text: str = Field(min_length=1, max_length=500_000)
    title: str = Field(default="粘贴资料", max_length=200)
    # 会话资料默认跟随当前故事；需要跨故事共享时由调用方明确选择 project。
    scope: Literal["story", "project"] = "story"
    branch_id: str | None = Field(default=None, max_length=200)


class CreateUrlAttachmentRequest(ApiModel):
    url: str = Field(min_length=8, max_length=2000)
    scope: Literal["story", "project"] = "story"
    branch_id: str | None = Field(default=None, max_length=200)


class IngestionTextRequest(ApiModel):
    """资料库文本导入。

    资料库条目恒为项目作用域，保留 ``scope`` 仅用于兼容旧客户端的请求
    形状，服务端会拒绝任何非 project 值，避免调用方把资料库内容误落到故事。
    """

    text: str = Field(min_length=1, max_length=2_000_000)
    title: str = Field(default="粘贴资料", max_length=200)
    scope: Literal["project"] = "project"


class PlanActionRequest(ApiModel):
    request: str = Field(min_length=1, max_length=20_000)
    idempotency_key: str = Field(default="", max_length=200)
    branch_id: str | None = Field(default=None, max_length=200)


class ExecuteActionRequest(ApiModel):
    confirmed: bool = False
    branch_id: str | None = Field(default=None, max_length=200)


class PendingKnowledgeRequest(ApiModel):
    pending_ids: list[str] = Field(default_factory=list, max_length=500)


class ResolvePendingEntityRequest(ApiModel):
    target_entity_id: str = Field(min_length=1, max_length=200)


class KnowledgePromotionRequest(ApiModel):
    knowledge_ids: list[str] = Field(default_factory=list, max_length=500)
    attachment_id: str | None = Field(default=None, max_length=160)


class RetryAttachmentRequest(ApiModel):
    # awaiting_confirmation 任务只有用户明确确认预算后才会继续。
    confirm_over_budget: bool = False


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


class DiscoverModelsRequest(ApiModel):
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=1000)
    provider_type: str = Field(default="auto", max_length=80)


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
    branch_id: str | None = Field(default=None, max_length=200)


class GenerateTurnRequest(ApiModel):
    user_message: str = Field(min_length=1, max_length=20000)
    action_type: Literal["generate", "continue", "rewrite", "branch"] = "generate"
    word_count: str = Field(default="800-1200", max_length=40)
    branch_from_fragment_id: str | None = Field(default=None, max_length=120)
    enable_web_search: bool = Field(default=False)
    branch_id: str | None = Field(default=None, max_length=200)


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
