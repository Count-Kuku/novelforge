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


@router.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/search")
async def search_knowledge(project_id: str, request: Request, query: str = "", story_id: str | None = None, cursor: str = "", page_size: int = 40, record_type: str = "") -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    result = await run_in_threadpool(
        memory.search_knowledge_center,
        name,
        query=query,
        record_types=[record_type] if record_type.strip() else None,
        story_id=story_id,
        cursor=cursor,
        page_size=max(1, min(page_size, 100)),
    )
    return _envelope(result, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/pending")
async def pending_knowledge(project_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    return _envelope({"items": await run_in_threadpool(memory.load_pending_knowledge_items, name)}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/knowledge/pending/confirm")
async def confirm_pending_knowledge(project_id: str, payload: PendingKnowledgeRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    result = await run_in_threadpool(memory.confirm_pending_knowledge_items_with_records, name, payload.pending_ids)
    return _envelope(result, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/knowledge/pending/discard")
async def discard_pending_knowledge(project_id: str, payload: PendingKnowledgeRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    removed = await run_in_threadpool(memory.discard_pending_knowledge_items, name, payload.pending_ids)
    return _envelope({"removed_count": removed}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/entities")
async def knowledge_entities(project_id: str, request: Request, entity_type: str = "character") -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    from novelforge.domain.knowledge_entities import build_character_entity_cards, build_setting_entity_cards, timeline_item_sort_key
    if entity_type == "character":
        items = await run_in_threadpool(build_character_entity_cards, name)
    elif entity_type == "setting":
        items = await run_in_threadpool(build_setting_entity_cards, name)
    elif entity_type == "timeline":
        base = await run_in_threadpool(memory.load_knowledge_category, name, "timeline_events")
        items = sorted([item for item in base if isinstance(item, dict)], key=timeline_item_sort_key)
    else:
        raise ValueError("entity_type 只支持 character、setting 或 timeline。")
    return _envelope({"entity_type": entity_type, "items": items}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/{{record_type}}/{{record_id}}/evidence")
async def knowledge_evidence(project_id: str, record_type: str, record_id: str, request: Request) -> dict[str, Any]:
    if record_type != "knowledge":
        raise ValueError("只有正式知识条目支持证据查看。")
    name = _resolve_project_name(project_id)
    return _envelope({"evidence": await run_in_threadpool(memory.load_knowledge_evidence, name, record_id)}, request)

@router.get(f"{API_PREFIX}/knowledge/schema/{{category}}")
async def knowledge_schema(category: str, request: Request) -> dict[str, Any]:
    from novelforge.domain.knowledge_types import KNOWLEDGE_TYPE_FIELDS
    fields = [{"key": field.key, "label": field.label, "kind": field.kind, "aliases": list(field.aliases), "required": field.required} for field in KNOWLEDGE_TYPE_FIELDS.get(category, ())]
    if not fields and category not in KNOWLEDGE_TYPE_FIELDS:
        raise ValueError("未知知识分类。")
    return _envelope({"category": category, "fields": fields, "schema_version": 2}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/{{record_type}}/{{record_id}}")
async def knowledge_detail(project_id: str, record_type: str, record_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    record = await run_in_threadpool(memory.load_knowledge_center_record, name, record_type, record_id)
    if not record:
        raise FileNotFoundError(f"知识条目不存在：{record_type}/{record_id}")
    return _envelope(record, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/{{record_type}}/{{record_id}}/revisions")
async def knowledge_revisions(project_id: str, record_type: str, record_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    if record_type != "knowledge":
        raise ValueError("只有正式知识条目支持修订历史。")
    return _envelope({"revisions": await run_in_threadpool(memory.load_knowledge_revisions, name, record_id)}, request)

@router.put(f"{API_PREFIX}/projects/{{project_id}}/knowledge/{{record_type}}/{{record_id}}")
async def update_knowledge_record(project_id: str, record_type: str, record_id: str, payload: KnowledgeUpdateRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    if record_type != "knowledge":
        raise ValueError("只有正式知识条目支持编辑。")
    current = await run_in_threadpool(memory.load_knowledge_center_record, name, record_type, record_id)
    if not current:
        raise FileNotFoundError(f"知识条目不存在：{record_id}")
    if payload.expected_revision_id:
        revisions = await run_in_threadpool(memory.load_knowledge_revisions, name, record_id)
        latest_revision_id = str(revisions[0].get("revision_id") or "") if revisions else ""
        if latest_revision_id and latest_revision_id != payload.expected_revision_id:
            raise RuntimeError("知识条目已被其它操作修改，请重新加载或选择手动合并。")
    source_category = str(current.get("category") or "").strip()
    current_payload = current.get("payload") if isinstance(current.get("payload"), dict) else current
    patch = {**dict(current_payload), **payload.patch, "revision_reason": payload.reason}
    updated = await run_in_threadpool(memory.update_confirmed_knowledge_item_record, name, source_category, record_id, patch, target_category=payload.target_category or source_category)
    if not updated:
        raise RuntimeError("知识编辑未能提交，可能已被其它操作修改。")
    return _envelope({"record": await run_in_threadpool(memory.load_knowledge_center_record, name, record_type, record_id), "saved": True}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/knowledge/{{record_type}}/{{record_id}}/restore")
async def restore_knowledge_record(project_id: str, record_type: str, record_id: str, payload: RestoreRevisionRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    if record_type != "knowledge":
        raise ValueError("只有正式知识条目支持修订恢复。")
    result = await run_in_threadpool(memory.restore_knowledge_revision, name, record_id, payload.revision_id, reason=payload.reason)
    return _envelope(result, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/graph")
async def knowledge_graph(project_id: str, request: Request, story_id: str | None = None) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    return _envelope(await run_in_threadpool(memory.load_knowledge_graph, name, story_id=story_id), request)
