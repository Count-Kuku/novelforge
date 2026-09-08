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


@router.get(f"{API_PREFIX}/projects/{{project_id}}/content")
async def project_content(project_id: str, request: Request, story_id: str = "default", cursor: int = 0, page_size: int = 40) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    from novelforge.services.resource_browser import list_resource_browser_items
    return _envelope(await run_in_threadpool(list_resource_browser_items, name, story_id, cursor=cursor, page_size=page_size), request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/works")
async def story_works(project_id: str, story_id: str, request: Request, cursor: int = 0, page_size: int = 40, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    from novelforge.services.creative_works import list_story_works
    return _envelope(await run_in_threadpool(list_story_works, name, story_id, cursor=cursor, page_size=page_size, branch_id=branch_id), request)

@router.delete(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/works/chapters/{{chapter_no}}")
async def delete_chapter_work_endpoint(project_id: str, story_id: str, chapter_no: int, request: Request, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    from novelforge.services.creative_works import delete_chapter_work
    deleted = await run_in_threadpool(delete_chapter_work, name, story_id, chapter_no, branch_id)
    return _envelope({"deleted": bool(deleted), "chapter_no": chapter_no, "branch_id": branch_id}, request)

@router.delete(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/works/fragments/{{fragment_id}}")
async def remove_fragment_work_endpoint(project_id: str, story_id: str, fragment_id: str, request: Request, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    from novelforge.services.creative_works import remove_fragment_work
    removed = await run_in_threadpool(remove_fragment_work, name, story_id, fragment_id, branch_id)
    return _envelope({"removed": bool(removed), "fragment_id": fragment_id, "branch_id": branch_id}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/content/delete")
async def delete_project_content(project_id: str, payload: ContentDeleteRequest, request: Request, story_id: str = "default") -> dict[str, Any]:
    if not payload.confirm:
        raise ValueError("删除内容需要明确确认。")
    name = _resolve_project_name(project_id)
    from novelforge.services.resource_browser import delete_resource_browser_item
    deleted = await run_in_threadpool(delete_resource_browser_item, name, payload.resource, story_id)
    return _envelope({"deleted": bool(deleted)}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/tasks")
async def project_tasks(project_id: str, request: Request, status_filter: str | None = None) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    statuses = [status_filter] if status_filter else None
    return _envelope({
        "ingestion": memory.list_source_ingestion_tasks(name, statuses=statuses),
        "web_research": memory.list_web_research_tasks(name, statuses=statuses),
    }, request)
