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


@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/structure")
async def story_structure(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    return _envelope({
        "volumes": memory.list_volumes(name, story_id=story_id),
        "arcs": memory.list_arcs(name, story_id=story_id),
        "chapters": await run_in_threadpool(project_manager.list_chapter_inventory, name, story_id),
    }, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/context/preview")
async def context_preview(project_id: str, story_id: str, request: Request, query: str = "", chapter_no: int | None = None, budget: int = 24_000) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    from novelforge.workflows.context_assembly import assemble_generation_context

    context = await run_in_threadpool(
        assemble_generation_context,
        name,
        story_id=story_id,
        capability="creative_writing",
        query=query or "当前故事上下文",
        chapter_no=chapter_no,
        context_budget=max(1_000, min(int(budget), 200_000)),
    )
    return _envelope(context.model_dump(), request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/rules")
async def story_rules(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    return _envelope({"project": memory.load_project_rules(name), "story": memory.load_story_rules(name, story_id)}, request)

@router.put(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/rules")
async def update_story_rules(project_id: str, story_id: str, payload: RulesUpdateRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    saved = await run_in_threadpool(memory.save_story_rules, name, story_id, payload.rules)
    return _envelope({"story": saved, "saved": True}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/volumes/{{volume_no}}")
async def volume_detail(project_id: str, story_id: str, volume_no: int, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    return _envelope({"metadata": memory.load_volume_metadata(name, volume_no, story_id), "outline": memory.load_volume_outline(name, volume_no, story_id), "discussion": memory.load_volume_discussion_artifact(name, volume_no, story_id)}, request)

@router.put(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/volumes/{{volume_no}}")
async def update_volume(project_id: str, story_id: str, volume_no: int, payload: UpdateStructureAssetRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    if payload.outline is not None:
        await run_in_threadpool(memory.save_volume_outline, name, volume_no, payload.outline, story_id)
    if payload.metadata:
        await run_in_threadpool(memory.save_volume_metadata, name, volume_no, payload.metadata, story_id)
    return _envelope({"metadata": memory.load_volume_metadata(name, volume_no, story_id), "outline": memory.load_volume_outline(name, volume_no, story_id), "saved": True}, request)

@router.delete(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/volumes/{{volume_no}}")
async def delete_volume(project_id: str, story_id: str, volume_no: int, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    deleted = await run_in_threadpool(memory.delete_volume, name, volume_no, story_id)
    return _envelope({"deleted": bool(deleted), "volume_no": volume_no}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/arcs/{{arc_no}}")
async def arc_detail(project_id: str, story_id: str, arc_no: int, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    return _envelope({"metadata": memory.load_arc_metadata(name, arc_no, story_id), "outline": memory.load_arc_outline(name, arc_no, story_id), "discussion": memory.load_arc_discussion_artifact(name, arc_no, story_id)}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/arcs/{{arc_no}}/chapter-plan")
async def arc_chapter_plan(project_id: str, story_id: str, arc_no: int, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    return _envelope(await run_in_threadpool(memory.load_arc_chapter_plan, name, arc_no, story_id), request)

@router.put(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/arcs/{{arc_no}}/chapter-plan")
async def update_arc_chapter_plan(project_id: str, story_id: str, arc_no: int, payload: UpdateChapterPlanRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    await run_in_threadpool(memory.save_arc_chapter_plan, name, arc_no, payload.plan, payload.report_markdown, story_id)
    saved = await run_in_threadpool(memory.load_arc_chapter_plan, name, arc_no, story_id)
    return _envelope({"plan": saved, "saved": True}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/arcs/{{arc_no}}/chapter-plan/validate")
async def validate_arc_chapter_plan(project_id: str, story_id: str, arc_no: int, payload: ChapterPlanValidationRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    from novelforge.domain.structure_validation import validate_arc_chapter_plan
    result = await run_in_threadpool(validate_arc_chapter_plan, name, story_id, arc_no, payload.plan)
    return _envelope(result, request)

@router.put(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/arcs/{{arc_no}}")
async def update_arc(project_id: str, story_id: str, arc_no: int, payload: UpdateStructureAssetRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    if payload.outline is not None:
        await run_in_threadpool(memory.save_arc_outline, name, arc_no, payload.outline, story_id)
    if payload.metadata:
        await run_in_threadpool(memory.save_arc_metadata, name, arc_no, payload.metadata, story_id)
    return _envelope({"metadata": memory.load_arc_metadata(name, arc_no, story_id), "outline": memory.load_arc_outline(name, arc_no, story_id), "saved": True}, request)

@router.delete(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/arcs/{{arc_no}}")
async def delete_arc(project_id: str, story_id: str, arc_no: int, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    deleted = await run_in_threadpool(memory.delete_arc, name, arc_no, story_id)
    return _envelope({"deleted": bool(deleted), "arc_no": arc_no}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/outline")
async def story_outline(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    return _envelope({"content": memory.load_outline(name, story_id=story_id)}, request)

@router.put(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/outline")
async def update_story_outline(project_id: str, story_id: str, payload: UpdateOutlineRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    await run_in_threadpool(memory.save_outline, name, payload.content, story_id)
    return _envelope({"content": payload.content, "saved": True}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/chapters/{{chapter_no}}")
async def chapter_detail(project_id: str, story_id: str, chapter_no: int, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    inventory = await run_in_threadpool(project_manager.list_chapter_inventory, name, story_id)
    item = next((row for row in inventory if int(row.get("chapter_no", -1)) == chapter_no), {"chapter_no": chapter_no})
    return _envelope({"chapter": item, "outline": memory.load_chapter_outline(name, chapter_no, story_id), "content": memory.load_chapter(name, chapter_no, story_id), "review": memory.load_review(name, chapter_no, story_id)}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/chapters/{{chapter_no}}/versions")
async def chapter_versions(project_id: str, story_id: str, chapter_no: int, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    runs = await run_in_threadpool(memory.list_pipeline_run_summaries, name, chapter_no, story_id)
    current = await run_in_threadpool(memory.load_chapter, name, chapter_no, story_id)
    versions: list[dict[str, Any]] = [{"version_id": "current", "label": "当前正文", "content": current, "updated_at": "", "source": "current"}]
    for run in runs:
        payload = run.get("payload") if isinstance(run.get("payload"), dict) else {}
        artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
        snapshot = artifacts.get("chapter_content") or artifacts.get("content") or payload.get("chapter_content")
        if isinstance(snapshot, str) and snapshot.strip():
            versions.append({"version_id": str(run.get("run_id") or ""), "label": str(run.get("workflow_type") or "历史运行"), "content": snapshot, "updated_at": run.get("updated_at", ""), "source": "workflow_run"})
    return _envelope({"versions": versions}, request)

@router.put(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/chapters/{{chapter_no}}")
async def update_chapter(project_id: str, story_id: str, chapter_no: int, payload: UpdateChapterRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    if payload.kind == "outline":
        await run_in_threadpool(memory.save_chapter_outline, name, chapter_no, payload.content, story_id)
    else:
        await run_in_threadpool(memory.save_chapter, name, chapter_no, payload.content, story_id)
    return _envelope({"chapter_no": chapter_no, "kind": payload.kind, "content": payload.content, "saved": True}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/profile")
async def story_profile(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    return _envelope({"profile": memory.load_creative_profile(name, story_id)}, request)

@router.put(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/profile")
async def update_story_profile(project_id: str, story_id: str, payload: UpdateProfileRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    profile = await run_in_threadpool(memory.save_creative_profile, name, payload.profile, story_id, True)
    return _envelope({"profile": profile, "saved": True}, request)
