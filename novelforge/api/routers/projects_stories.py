from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from novelforge.services import memory
from novelforge.services import project_manager
from novelforge.workflows.interactive_writing import (
    create_writing_session,
    generate_writing_fragment,
)
from storage.repositories.projects import upsert_project_meta
from storage.schema import CURRENT_SCHEMA_VERSION

from .._helpers import (
    API_PREFIX,
    LOGGER,
    _envelope,
    _error_payload,
    _project_meta,
    _request_id,
    _resolve_project_name,
    _sse,
    _story,
    _threaded_stream,
)
from ..schemas import (
    ApiError,
    CreateProjectRequest,
    CreateAttachmentRequest,
    CreateUrlAttachmentRequest,
    CreateSessionRequest,
    CreateStoryRequest,
    CopyStoryRequest,
    DiscussionApprovalRequest,
    DiscussionRequest,
    ExecuteActionRequest,
    FragmentActionRequest,
    GenerateTurnRequest,
    RenameProjectRequest,
    RenameStoryRequest,
    SetStoryModeRequest,
    UpdateProfileRequest,
    UpdateChapterRequest,
    UpdateStructureAssetRequest,
    UpdateChapterPlanRequest,
    PlanActionRequest,
    PendingKnowledgeRequest,
    KnowledgeUpdateRequest,
    RestoreRevisionRequest,
    ModelProfileRequest,
    ActiveModelProfileRequest,
    RulesUpdateRequest,
    PromptOptionsUpdateRequest,
    AutoConfigurationRequest,
    ResearchClaimsReviewRequest,
    ChapterPlanValidationRequest,
    ContentDeleteRequest,
    ResearchTaskRequest,
    TaskControlRequest,
    UpdateOutlineRequest,
    UpdateSessionRequest,
)

router = APIRouter()


def _validate_workspace_branch(project_name: str, story_id: str, branch_id: str | None) -> str | None:
    """Validate explicit branch ownership before serving workspace assets.

    Workspace structure assets still use the legacy story-level storage. A
    non-main branch must therefore fail clearly instead of silently returning
    or mutating the main story assets.
    """
    if not branch_id:
        return None
    clean_branch_id = str(branch_id).strip()
    branch = memory.load_story_branch(project_name, story_id, clean_branch_id)
    if str(branch.get("story_id") or "") != str(story_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="世界线不属于当前故事。")
    if clean_branch_id != memory.default_branch_id(story_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="工作区结构资料暂不支持非主线世界线。")
    return clean_branch_id


@router.patch(f"{API_PREFIX}/projects/{{project_id}}")
async def rename_project_endpoint(project_id: str, payload: RenameProjectRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    renamed = await run_in_threadpool(project_manager.rename_project, name, payload.name)
    return _envelope({"project": _project_meta(renamed)}, request)

@router.delete(f"{API_PREFIX}/projects/{{project_id}}")
async def delete_project_endpoint(project_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    deleted = await run_in_threadpool(project_manager.delete_project, name)
    return _envelope({"deleted": bool(deleted), "project_id": project_id}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories")
async def stories(project_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    return _envelope({"stories": memory.list_stories(name)}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories", status_code=status.HTTP_201_CREATED)
async def create_story_endpoint(project_id: str, payload: CreateStoryRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    story = await run_in_threadpool(memory.create_story, name, payload.name, payload.description, payload.creation_mode)
    return _envelope({"story": story}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}")
async def story_detail(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    story = _story(name, story_id)
    return _envelope({"story": story, "profile": memory.load_creative_profile(name, story_id)}, request)

@router.patch(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}")
async def rename_story_endpoint(project_id: str, story_id: str, payload: RenameStoryRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    story = await run_in_threadpool(memory.rename_story, name, story_id, payload.name, payload.description)
    return _envelope({"story": story}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/copy", status_code=status.HTTP_201_CREATED)
async def copy_story_endpoint(project_id: str, story_id: str, payload: CopyStoryRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    story = await run_in_threadpool(
        memory.copy_story,
        name,
        story_id,
        payload.name,
        include_discussions=payload.include_discussions,
        include_summaries=payload.include_summaries,
        include_chapters=payload.include_chapters,
    )
    return _envelope({"story": story}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/archive")
async def archive_story_endpoint(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    archived = await run_in_threadpool(memory.archive_story, name, story_id)
    return _envelope({"archived": bool(archived), "story_id": story_id}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/restore")
async def restore_story_endpoint(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    restored = await run_in_threadpool(memory.restore_story, name, story_id)
    return _envelope({"restored": bool(restored), "story_id": story_id}, request)

@router.delete(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}")
async def delete_story_endpoint(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    deleted = await run_in_threadpool(memory.delete_story, name, story_id)
    return _envelope({"deleted": bool(deleted), "story_id": story_id}, request)

@router.patch(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/mode")
async def set_story_mode(project_id: str, story_id: str, payload: SetStoryModeRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    updated = await run_in_threadpool(memory.set_story_creation_mode, name, story_id, payload.creation_mode)
    return _envelope({"story": updated}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/workspace")
async def story_workspace(project_id: str, story_id: str, request: Request, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    story = _story(name, story_id)
    _validate_workspace_branch(name, story_id, branch_id)
    return _envelope({
        "story": story,
        "profile": memory.load_creative_profile(name, story_id),
        "outline": memory.load_outline(name, story_id=story_id),
        "volumes": memory.list_volumes(name, story_id=story_id),
        "arcs": memory.list_arcs(name, story_id=story_id),
        "chapters": project_manager.list_chapter_inventory(name, story_id=story_id),
        "branch_id": branch_id,
    }, request)
