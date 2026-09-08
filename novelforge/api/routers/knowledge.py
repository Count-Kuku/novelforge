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
    ResolvePendingEntityRequest,
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
    KnowledgePromotionRequest,
)

router = APIRouter()


@router.post(f"{API_PREFIX}/projects/{{project_id}}/knowledge/pending/{{pending_id}}/resolve-entity")
async def resolve_pending_entity(project_id: str, pending_id: str, payload: ResolvePendingEntityRequest, request: Request, story_id: str, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    from novelforge.workflows.interactive_writing._fragment_ops import resolve_fragment_entity_candidate

    candidate = await run_in_threadpool(resolve_fragment_entity_candidate, _resolve_project_name(project_id), story_id, branch_id, pending_id, payload.target_entity_id)
    return _envelope({
        "candidate": candidate,
        "resolved": candidate.get("entity_resolution_status") != "pending_confirmation",
    }, request)


@router.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/search")
async def search_knowledge(project_id: str, request: Request, query: str = "", story_id: str | None = None, branch_id: str | None = Query(default=None), cursor: str = "", page_size: int = 40, record_type: str = "") -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    result = await run_in_threadpool(
        memory.search_knowledge_center,
        name,
        query=query,
        record_types=[record_type] if record_type.strip() else None,
        story_id=story_id,
        branch_id=branch_id,
        cursor=cursor,
        page_size=max(1, min(page_size, 100)),
    )
    return _envelope(result, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/pending")
async def pending_knowledge(project_id: str, request: Request, story_id: str | None = None, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    return _envelope({"items": await run_in_threadpool(memory.list_pending_knowledge_for_scope, name, story_id=story_id, branch_id=branch_id)}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/knowledge/pending/confirm")
async def confirm_pending_knowledge(project_id: str, payload: PendingKnowledgeRequest, request: Request, story_id: str | None = None, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    await run_in_threadpool(memory.assert_pending_scope, name, payload.pending_ids, story_id=story_id, branch_id=branch_id, writing=True)
    result = await run_in_threadpool(memory.confirm_pending_knowledge_items_with_records, name, payload.pending_ids)
    return _envelope(result, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/knowledge/pending/discard")
async def discard_pending_knowledge(project_id: str, payload: PendingKnowledgeRequest, request: Request, story_id: str | None = None, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    await run_in_threadpool(memory.assert_pending_scope, name, payload.pending_ids, story_id=story_id, branch_id=branch_id, writing=True)
    removed = await run_in_threadpool(memory.discard_pending_knowledge_items, name, payload.pending_ids)
    return _envelope({"removed_count": removed}, request)


@router.post(f"{API_PREFIX}/projects/{{project_id}}/knowledge/promote")
async def promote_knowledge(project_id: str, payload: KnowledgePromotionRequest, request: Request, story_id: str | None = None, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    if story_id is not None:
        if payload.knowledge_ids:
            for knowledge_id in payload.knowledge_ids:
                await run_in_threadpool(memory.assert_story_knowledge_writable, name, story_id, branch_id, knowledge_id)
        else:
            # Attachment-based promotion still needs a branch owner check when
            # the caller has selected a story view; the workflow validates the
            # attachment's story before selecting its items.
            await run_in_threadpool(memory._branch_scope, name, story_id, branch_id, writing=True)
    from novelforge.workflows.knowledge_promotion import promote_knowledge_to_project
    result = await run_in_threadpool(
        promote_knowledge_to_project,
        name,
        payload.knowledge_ids,
        attachment_id=payload.attachment_id or None,
    )
    # A failed promotion must never look like a successful zero-item response
    # to the UI.  Current workflow results use ``blocked``; retain the
    # defensive success check for older/alternate workflow implementations.
    failed_without_items = (
        result.get("success") is False
        and not result.get("items")
        and not result.get("promoted_items")
        and not result.get("already_promoted")
    )
    if result.get("blocked") or failed_without_items:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                str(result.get("reason") or "知识条目未通过项目提升门禁。")
                + (
                    "（条目：" + "、".join(str(item) for item in (result.get("blocked_ids") or [])) + "）"
                    if result.get("blocked_ids") else ""
                )
            ),
        )
    return _envelope(result, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/entities")
async def knowledge_entities(project_id: str, request: Request, entity_type: str = "character", story_id: str | None = None, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    from novelforge.domain.knowledge_entities import build_character_entity_cards, build_setting_entity_cards, timeline_item_sort_key
    if entity_type == "character":
        items = await run_in_threadpool(memory.load_character_entity_cards, name, story_id=story_id, branch_id=branch_id)
    elif entity_type == "setting":
        items = await run_in_threadpool(memory.load_setting_entity_cards, name, story_id=story_id, branch_id=branch_id)
    elif entity_type == "timeline":
        base = await run_in_threadpool(memory.list_visible_story_knowledge, name, story_id, branch_id, category="timeline_events") if story_id is not None else await run_in_threadpool(memory.load_knowledge_category, name, "timeline_events")
        items = sorted([item for item in base if isinstance(item, dict)], key=timeline_item_sort_key)
    else:
        raise ValueError("entity_type 只支持 character、setting 或 timeline。")
    return _envelope({"entity_type": entity_type, "items": items}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/{{record_type}}/{{record_id}}/evidence")
async def knowledge_evidence(project_id: str, record_type: str, record_id: str, request: Request, story_id: str | None = None, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    if record_type != "knowledge":
        raise ValueError("只有正式知识条目支持证据查看。")
    name = _resolve_project_name(project_id)
    record = await run_in_threadpool(memory.load_knowledge_center_record, name, record_type, record_id, story_id=story_id, branch_id=branch_id)
    if not record:
        raise FileNotFoundError(f"知识条目不属于当前作用域：{record_id}")
    if story_id is not None:
        evidence = await run_in_threadpool(memory.load_visible_story_knowledge_evidence, name, record_id, story_id=story_id, branch_id=branch_id)
    else:
        resolved_id = str(record.get("knowledge_id") or record.get("record_id") or record_id)
        evidence = await run_in_threadpool(memory.load_knowledge_evidence, name, resolved_id)
    return _envelope({"evidence": evidence}, request)

@router.get(f"{API_PREFIX}/knowledge/schema/{{category}}")
async def knowledge_schema(category: str, request: Request) -> dict[str, Any]:
    from novelforge.domain.knowledge_types import KNOWLEDGE_TYPE_FIELDS
    fields = [{"key": field.key, "label": field.label, "kind": field.kind, "aliases": list(field.aliases), "required": field.required} for field in KNOWLEDGE_TYPE_FIELDS.get(category, ())]
    if not fields and category not in KNOWLEDGE_TYPE_FIELDS:
        raise ValueError("未知知识分类。")
    return _envelope({"category": category, "fields": fields, "schema_version": 2}, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/{{record_type}}/{{record_id}}")
async def knowledge_detail(project_id: str, record_type: str, record_id: str, request: Request, story_id: str | None = None, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    record = await run_in_threadpool(memory.load_knowledge_center_record, name, record_type, record_id, story_id=story_id, branch_id=branch_id)
    if not record:
        raise FileNotFoundError(f"知识条目不存在：{record_type}/{record_id}")
    return _envelope(record, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/{{record_type}}/{{record_id}}/revisions")
async def knowledge_revisions(project_id: str, record_type: str, record_id: str, request: Request, story_id: str | None = None, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    if record_type != "knowledge":
        raise ValueError("只有正式知识条目支持修订历史。")
    record = await run_in_threadpool(memory.load_knowledge_center_record, name, record_type, record_id, story_id=story_id, branch_id=branch_id)
    if not record:
        raise FileNotFoundError(f"知识条目不属于当前作用域：{record_id}")
    if story_id is not None:
        revisions = await run_in_threadpool(memory.load_visible_story_knowledge_revisions, name, record_id, story_id=story_id, branch_id=branch_id)
    else:
        resolved_id = str(record.get("knowledge_id") or record.get("record_id") or record_id)
        revisions = await run_in_threadpool(memory.load_knowledge_revisions, name, resolved_id)
    return _envelope({"revisions": revisions}, request)

@router.put(f"{API_PREFIX}/projects/{{project_id}}/knowledge/{{record_type}}/{{record_id}}")
async def update_knowledge_record(project_id: str, record_type: str, record_id: str, payload: KnowledgeUpdateRequest, request: Request, story_id: str | None = None, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    if record_type != "knowledge":
        raise ValueError("只有正式知识条目支持编辑。")
    current = await run_in_threadpool(memory.load_knowledge_center_record, name, record_type, record_id, story_id=story_id, branch_id=branch_id)
    if not current:
        raise FileNotFoundError(f"知识条目不存在：{record_id}")
    target_record_id = str(current.get("knowledge_id") or current.get("record_id") or record_id)
    effective_branch_id = str(branch_id or memory.default_branch_id(story_id)) if story_id is not None else ""
    inherited = bool(
        story_id is not None
        and current.get("visible_from_checkpoint")
        and str(current.get("origin_branch_id") or "")
        and str(current.get("origin_branch_id") or "") != effective_branch_id
    )
    source_category = str(current.get("category") or "").strip()
    if inherited and payload.target_category and str(payload.target_category).strip() != source_category:
        raise ValueError("继承资料的独立副本暂不支持跨分类移动，请在当前分类保存修订。")
    if payload.expected_revision_id:
        revision_loader = memory.load_visible_story_knowledge_revisions if inherited and story_id is not None else memory.load_knowledge_revisions
        revision_kwargs = {
            "story_id": story_id,
            "branch_id": effective_branch_id,
        } if inherited and story_id is not None else {}
        revisions = await run_in_threadpool(revision_loader, name, target_record_id, **revision_kwargs)
        latest_revision_id = str(revisions[0].get("revision_id") or "") if revisions else ""
        if latest_revision_id and latest_revision_id != payload.expected_revision_id:
            raise RuntimeError("知识条目已被其它操作修改，请重新加载或选择手动合并。")
    if story_id is not None and not inherited:
        await run_in_threadpool(memory.assert_story_knowledge_writable, name, story_id, branch_id, target_record_id)
    for owner_key in ("story_id", "branch_id", "setting_scope"):
        if owner_key in payload.patch and str(payload.patch.get(owner_key) or "") != str(current.get(owner_key) or ""):
            raise ValueError(f"不允许通过 patch 修改知识归属字段：{owner_key}")
    current_payload = current.get("payload") if isinstance(current.get("payload"), dict) else current
    patch = {**dict(current_payload), **payload.patch, "revision_reason": payload.reason}
    if inherited:
        saved = await run_in_threadpool(
            memory.create_story_knowledge_override,
            name,
            current,
            payload.patch,
            story_id=story_id,
            branch_id=effective_branch_id,
            reason=payload.reason or "编辑当前世界线继承资料",
        )
        override_id = str(saved.get("knowledge_id") or saved.get("id") or "")
        if not override_id:
            raise RuntimeError("当前世界线知识副本创建失败。")
        return _envelope({
            "record": await run_in_threadpool(memory.load_knowledge_center_record, name, record_type, override_id, story_id=story_id, branch_id=effective_branch_id),
            "saved": True,
            "created_override": True,
            "origin_knowledge_id": target_record_id,
        }, request)
    updated = await run_in_threadpool(memory.update_confirmed_knowledge_item_record, name, source_category, target_record_id, patch, target_category=payload.target_category or source_category)
    if not updated:
        raise RuntimeError("知识编辑未能提交，可能已被其它操作修改。")
    return _envelope({"record": await run_in_threadpool(memory.load_knowledge_center_record, name, record_type, target_record_id, story_id=story_id, branch_id=effective_branch_id or None), "saved": True}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/knowledge/{{record_type}}/{{record_id}}/restore")
async def restore_knowledge_record(project_id: str, record_type: str, record_id: str, payload: RestoreRevisionRequest, request: Request, story_id: str | None = None, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    if record_type != "knowledge":
        raise ValueError("只有正式知识条目支持修订恢复。")
    result = await run_in_threadpool(memory.restore_knowledge_revision, name, record_id, payload.revision_id, reason=payload.reason, story_id=story_id, branch_id=branch_id)
    return _envelope(result, request)

@router.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/graph")
async def knowledge_graph(project_id: str, request: Request, story_id: str | None = None, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    return _envelope(await run_in_threadpool(memory.load_knowledge_graph, name, story_id=story_id, branch_id=branch_id), request)
