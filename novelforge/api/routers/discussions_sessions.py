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
    extract_fragment_knowledge,
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


@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/discussions/{{asset_type}}")
async def discussion_artifact(project_id: str, story_id: str, asset_type: str, request: Request, asset_no: int | None = None) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    if asset_type == "profile":
        artifact = memory.load_creative_profile_discussion_artifact(name, story_id)
    elif asset_type == "outline":
        artifact = memory.load_outline_discussion_artifact(name, story_id)
    elif asset_type == "volume" and asset_no:
        artifact = memory.load_volume_discussion_artifact(name, asset_no, story_id)
    elif asset_type == "arc" and asset_no:
        artifact = memory.load_arc_discussion_artifact(name, asset_no, story_id)
    elif asset_type == "chapter" and asset_no:
        artifact = memory.load_chapter_discussion_artifact(name, asset_no, story_id)
    else:
        raise ValueError("不支持的讨论资产类型。")
    return _envelope({"asset_type": asset_type, "artifact": artifact}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/discussions/{{asset_type}}/stream")
async def discussion_stream(project_id: str, story_id: str, asset_type: str, payload: DiscussionRequest, request: Request, asset_no: int | None = None):
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    if asset_type not in {"profile", "outline", "volume", "arc", "chapter"}:
        raise ValueError("不支持的讨论资产类型。")
    if asset_type in {"volume", "arc", "chapter"} and not asset_no:
        raise ValueError("分卷或剧情段讨论需要 asset_no。")

    def worker(emit: Callable[[str, Any], None], cancel_check: Callable[[], bool]) -> dict[str, Any]:
        from novelforge.workflows.skills import discussions

        stream_callback = lambda text: emit("delta", {"text": str(text or "")})
        if asset_type == "profile":
            return discussions.discuss_creative_profile(name, payload.idea, story_id, stream_callback=stream_callback)
        if asset_type == "outline":
            return discussions.discuss_outline(name, payload.idea, story_id, stream_callback=stream_callback)
        if asset_type == "volume":
            metadata = memory.load_volume_metadata(name, asset_no, story_id)
            return discussions.discuss_volume(name, asset_no, str(metadata.get("title") or ""), str(metadata.get("summary") or ""), payload.idea, story_id, stream_callback=stream_callback)
        if asset_type == "chapter":
            return discussions.discuss_chapter(name, asset_no, payload.idea, story_id, stream_callback=stream_callback)
        metadata = memory.load_arc_metadata(name, asset_no, story_id)
        if asset_type == "arc":
            return discussions.discuss_arc(name, asset_no, metadata.get("volume_no"), str(metadata.get("title") or ""), str(metadata.get("summary") or ""), metadata.get("estimated_chapter_count"), str(metadata.get("target_word_count_range") or ""), payload.idea, story_id, stream_callback=stream_callback)
        raise ValueError("不支持的讨论资产类型。")

    return StreamingResponse(_threaded_stream(worker), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/discussions/{{asset_type}}/approve")
async def approve_discussion(project_id: str, story_id: str, asset_type: str, payload: DiscussionApprovalRequest, request: Request, asset_no: int | None = None) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    from novelforge.workflows.skills import discussions

    if asset_type == "profile":
        result = await run_in_threadpool(discussions.approve_creative_profile_discussion, name, payload.step, story_id)
    elif asset_type == "outline":
        result = await run_in_threadpool(discussions.approve_outline_discussion, name, payload.step, story_id)
    elif asset_type == "volume" and asset_no:
        result = await run_in_threadpool(discussions.approve_volume_discussion, name, asset_no, payload.step, story_id)
    elif asset_type == "arc" and asset_no:
        result = await run_in_threadpool(discussions.approve_arc_discussion, name, asset_no, payload.step, story_id)
    elif asset_type == "chapter" and asset_no:
        result = await run_in_threadpool(discussions.approve_chapter_discussion, name, asset_no, payload.step, story_id)
    else:
        raise ValueError("不支持的讨论资产类型。")
    return _envelope({"asset_type": asset_type, "result": result}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(project_id: str, story_id: str, payload: CreateSessionRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    story = _story(name, story_id)
    auto_extract = payload.auto_extract_mode or ("on_accept" if story.get("creation_mode") == "conversational" else "manual")
    session = await run_in_threadpool(
        create_writing_session,
        name,
        story_id,
        session_goal=payload.session_goal,
        title=payload.title,
        auto_extract_mode=auto_extract,
    )
    return _envelope({"session": session}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions")
async def list_sessions(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    sessions = await run_in_threadpool(memory.list_creative_sessions, name, story_id, include_archived=True)
    return _envelope({"sessions": sessions}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}")
async def session_detail(project_id: str, story_id: str, session_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    bundle = await run_in_threadpool(memory.load_creative_session_bundle, name, session_id, story_id=story_id)
    if not bundle:
        raise FileNotFoundError(f"创作会话不存在：{session_id}")
    return _envelope(bundle, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/attachments")
async def list_session_attachments(project_id: str, story_id: str, session_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    return _envelope({"attachments": await run_in_threadpool(memory.list_creative_attachments, name, story_id=story_id, session_id=session_id)}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/attachments", status_code=status.HTTP_201_CREATED)
async def create_session_attachment(project_id: str, story_id: str, session_id: str, payload: CreateAttachmentRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    from novelforge.workflows.creative_attachments import import_creative_pasted_text

    attachment = await run_in_threadpool(import_creative_pasted_text, name, story_id, session_id, payload.text, title=payload.title, scope=payload.scope)
    return _envelope({"attachment": attachment}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/attachments/url", status_code=status.HTTP_201_CREATED)
async def create_session_url_attachment(project_id: str, story_id: str, session_id: str, payload: CreateUrlAttachmentRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    from novelforge.workflows.creative_attachments import import_creative_url

    attachment = await run_in_threadpool(import_creative_url, name, story_id, session_id, payload.url, scope=payload.scope)
    return _envelope({"attachment": attachment}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/attachments/file", status_code=status.HTTP_201_CREATED)
async def create_session_file_attachment(project_id: str, story_id: str, session_id: str, request: Request, file: UploadFile = File(...), scope: str = Form("session")) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    if scope not in {"turn", "session", "story", "project"}:
        raise ValueError("附件作用域无效。")
    content = await file.read()
    if len(content) > 8 * 1024 * 1024:
        raise ValueError("附件超过 8MB 限制。")
    from novelforge.services.document_parsing import parse_document_bytes
    from novelforge.workflows.creative_attachments import import_creative_documents

    document = await run_in_threadpool(parse_document_bytes, file.filename or "attachment.txt", content)
    attachments = await run_in_threadpool(import_creative_documents, name, story_id, session_id, [document], scope=scope)
    return _envelope({"attachment": attachments[0] if attachments else None, "warnings": document.warnings}, request)

@router.patch(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}")
async def update_session(project_id: str, story_id: str, session_id: str, payload: UpdateSessionRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    updates = {key: value for key, value in payload.model_dump().items() if value is not None}
    session = await run_in_threadpool(memory.update_creative_session, name, session_id, updates, story_id=story_id)
    return _envelope({"session": session}, request)

@router.delete(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}")
async def archive_session(project_id: str, story_id: str, session_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    session = await run_in_threadpool(memory.update_creative_session, name, session_id, {"status": "archived"}, story_id=story_id)
    return _envelope({"session": session, "archived": True}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/actions")
async def list_session_actions(project_id: str, story_id: str, session_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    return _envelope({"actions": await run_in_threadpool(memory.list_creative_actions, name, story_id, session_id)}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/actions/plan", status_code=status.HTTP_201_CREATED)
async def plan_session_action(project_id: str, story_id: str, session_id: str, payload: PlanActionRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    from novelforge.workflows.creative_actions import plan_creative_action

    action = await run_in_threadpool(plan_creative_action, name, story_id, session_id, payload.request, idempotency_key=payload.idempotency_key or request.headers.get("idempotency-key", ""))
    return _envelope({"action": action}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/actions/{{action_id}}/execute")
async def execute_session_action(project_id: str, story_id: str, session_id: str, action_id: str, payload: ExecuteActionRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    from novelforge.workflows.creative_actions import execute_creative_action

    action = await run_in_threadpool(
        execute_creative_action, name, action_id,
        story_id=story_id, session_id=session_id, confirmed=payload.confirmed,
    )
    return _envelope({"action": action}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/actions/{{action_id}}/cancel")
async def cancel_session_action(project_id: str, story_id: str, session_id: str, action_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    from novelforge.workflows.creative_actions import cancel_creative_action

    action = await run_in_threadpool(cancel_creative_action, name, action_id, story_id, session_id)
    return _envelope({"action": action}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/actions/{{action_id}}/undo")
async def undo_session_action(project_id: str, story_id: str, session_id: str, action_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    from novelforge.workflows.creative_actions import undo_creative_action

    action = await run_in_threadpool(
        undo_creative_action, name, action_id,
        story_id=story_id, session_id=session_id,
        idempotency_key=request.headers.get("idempotency-key", ""),
    )
    return _envelope({"action": action}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/fragments/accept")
async def accept_fragment(project_id: str, story_id: str, session_id: str, payload: FragmentActionRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    saved = await run_in_threadpool(memory.accept_creative_fragment, name, session_id, payload.fragment_id, story_id=story_id)
    return _envelope({"fragment": saved}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/fragments/{{fragment_id}}/extract/stream")
async def extract_fragment_stream(project_id: str, story_id: str, session_id: str, fragment_id: str, request: Request):
    """显式提炼已采用片段：无风险候选自动确认进正式知识，有风险留待审核。"""
    name = _resolve_project_name(project_id)
    _story(name, story_id)

    def worker(emit: Callable[[str, Any], None], cancel_check: Callable[[], bool]) -> dict[str, Any]:
        result = extract_fragment_knowledge(
            name,
            story_id,
            session_id,
            fragment_id,
            stream_callback=lambda text: emit("delta", {"text": str(text or "")}),
        )
        return result

    return StreamingResponse(
        _threaded_stream(worker),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/fragments/select")
async def select_fragment(project_id: str, story_id: str, session_id: str, payload: FragmentActionRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    saved = await run_in_threadpool(memory.select_creative_fragment_variant, name, session_id, payload.fragment_id, story_id=story_id)
    return _envelope({"fragment": saved}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/frontier")
async def select_frontier(project_id: str, story_id: str, session_id: str, payload: FragmentActionRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    saved = await run_in_threadpool(memory.select_creative_frontier, name, session_id, payload.fragment_id, story_id=story_id)
    return _envelope({"session": saved}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/turns/stream")
async def generate_turn_stream(project_id: str, story_id: str, session_id: str, payload: GenerateTurnRequest, request: Request):
    name = _resolve_project_name(project_id)
    _story(name, story_id)

    def worker(emit: Callable[[str, Any], None], cancel_check: Callable[[], bool]) -> dict[str, Any]:
        result = generate_writing_fragment(
            name,
            story_id,
            session_id,
            payload.user_message,
            action_type=payload.action_type,
            word_count=payload.word_count,
            branch_from_fragment_id=payload.branch_from_fragment_id,
            stream_callback=lambda text: emit("delta", {"text": str(text or "")}),
            cancel_check=cancel_check,
        )
        return result

    return StreamingResponse(
        _threaded_stream(worker),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/events")
async def story_events(project_id: str, story_id: str, request: Request):
    name = _resolve_project_name(project_id)
    story = _story(name, story_id)

    async def events() -> AsyncIterator[str]:
        yield _sse("ready", {"story": story, "server_time": datetime.now(timezone.utc).isoformat()})
        yield _sse("done", {"reason": "snapshot"})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
