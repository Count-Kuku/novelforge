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

from ..operations import operation_registry
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


@router.get(f"{API_PREFIX}/operations/demo-stream")
async def demo_stream():
    async def events() -> AsyncIterator[str]:
        yield _sse("operation.started", {"operation_id": "demo", "status": "running"}, event_id="1")
        yield _sse("operation.delta", {"text": "SSE contract ready"}, event_id="2")
        yield _sse("operation.completed", {"operation_id": "demo", "status": "completed"}, event_id="3")

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

@router.get(f"{API_PREFIX}/operations/{{operation_id}}")
async def operation_detail(operation_id: str, request: Request) -> dict[str, Any]:
    snapshot = operation_registry.snapshot(operation_id)
    if snapshot is None:
        raise FileNotFoundError(f"操作不存在或已过期：{operation_id}")
    return _envelope(snapshot, request)

@router.get(f"{API_PREFIX}/operations/{{operation_id}}/events")
async def operation_events(operation_id: str, request: Request, after: int = 0) -> dict[str, Any]:
    snapshot = operation_registry.snapshot(operation_id)
    if snapshot is None:
        raise FileNotFoundError(f"操作不存在或已过期：{operation_id}")
    return _envelope({"operation_id": operation_id, "events": operation_registry.events_after(operation_id, after)}, request)

@router.post(f"{API_PREFIX}/operations/{{operation_id}}/cancel")
async def cancel_operation(operation_id: str, request: Request) -> dict[str, Any]:
    if not operation_registry.cancel(operation_id):
        raise ValueError(f"操作不存在或已结束：{operation_id}")
    return _envelope({"operation_id": operation_id, "status": "cancel_requested"}, request)
