from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
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


@router.get(f"{API_PREFIX}/projects/{{project_id}}/sources")
async def project_sources(project_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    from novelforge.workflows.source_workflows import build_ingestion_source_ledger

    return _envelope({"sources": await run_in_threadpool(build_ingestion_source_ledger, name)}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/research", status_code=status.HTTP_201_CREATED)
async def create_research(project_id: str, payload: ResearchTaskRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    if payload.story_id:
        _story(name, payload.story_id)
    from novelforge.workflows.web_research_tasks import create_web_research_task

    task = await run_in_threadpool(
        create_web_research_task,
        name,
        payload.topic,
        objective=payload.objective,
        source_kinds=payload.source_kinds,
        official_domains=payload.official_domains,
        max_results_per_branch=payload.max_results_per_branch,
        max_pages=payload.max_pages,
        language=payload.language,
        freshness=payload.freshness,
        scope=payload.scope,
        story_id=payload.story_id,
    )
    return _envelope({"task": task}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/research/{{task_id}}")
async def research_detail(project_id: str, task_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    task = await run_in_threadpool(memory.load_web_research_task, name, task_id)
    if not task:
        raise FileNotFoundError(f"网络研究任务不存在：{task_id}")
    return _envelope({"task": task}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/research/{{task_id}}/control")
async def research_control(project_id: str, task_id: str, payload: TaskControlRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    from novelforge.workflows import web_research_tasks

    handlers = {
        "pause": web_research_tasks.pause_web_research_task,
        "resume": web_research_tasks.resume_web_research_task,
        "cancel": web_research_tasks.cancel_web_research_task,
        "retry": web_research_tasks.retry_web_research_task,
    }
    task = await run_in_threadpool(handlers[payload.action], name, task_id)
    return _envelope({"task": task, "action": payload.action}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/research/{{task_id}}/sources/activate")
async def activate_research_sources(project_id: str, task_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    from novelforge.workflows.web_research_tasks import activate_web_research_sources

    result = await run_in_threadpool(activate_web_research_sources, name, task_id)
    task = await run_in_threadpool(memory.load_web_research_task, name, task_id)
    return _envelope({"result": result, "task": task}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/research/{{task_id}}/sources/quarantine")
async def quarantine_research_sources(project_id: str, task_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    from novelforge.workflows.web_research_tasks import quarantine_web_research_sources

    result = await run_in_threadpool(quarantine_web_research_sources, name, task_id)
    task = await run_in_threadpool(memory.load_web_research_task, name, task_id)
    return _envelope({"result": result, "task": task}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/research/{{task_id}}/claims/review")
async def review_research_claims(project_id: str, task_id: str, payload: ResearchClaimsReviewRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    from novelforge.workflows.web_research_tasks import queue_web_research_claims_for_review
    result = await run_in_threadpool(queue_web_research_claims_for_review, name, task_id, payload.claim_ids)
    task = await run_in_threadpool(memory.load_web_research_task, name, task_id)
    return _envelope({"result": result, "task": task}, request)
