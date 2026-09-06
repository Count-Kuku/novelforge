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


@router.get(f"{API_PREFIX}/projects/{{project_id}}/ingestion/workbench")
async def ingestion_workbench_before_detail(project_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    from novelforge.workflows.source_workflows import build_ingestion_workbench
    return _envelope(await run_in_threadpool(build_ingestion_workbench, name), request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/ingestion/batch", status_code=status.HTTP_202_ACCEPTED)
async def create_batch_ingestion(project_id: str, story_id: str, request: Request, files: list[UploadFile] = File(...), scope: str = Form("project"), use_ocr: bool = Form(False)) -> dict[str, Any]:
    """Import several reference files in one confirmed batch and queue knowledge work."""
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    if scope not in {"story", "project"}:
        raise ValueError("批量导入只支持故事或项目作用域。")
    if not files or len(files) > 20:
        raise ValueError("批量导入一次最多选择 20 个文件。")
    from novelforge.services.document_parsing import SUPPORTED_DOCUMENT_EXTENSIONS, ocr_pdf_bytes, parse_document_bytes
    from novelforge.workflows.creative_attachments import import_creative_documents

    # 前置校验：为不支持的格式尽早失败，避免读完整个（可能很大的）文件才报错。
    unsupported = [
        (file.filename or "attachment.txt")
        for file in files
        if Path(file.filename or "attachment.txt").suffix.lower() not in SUPPORTED_DOCUMENT_EXTENSIONS
    ]
    if unsupported:
        raise ValueError(
            "不支持的资料格式：{}；仅支持 {}。".format(
                "、".join(unsupported), "、".join(sorted(SUPPORTED_DOCUMENT_EXTENSIONS))
            )
        )

    documents = []
    warnings: list[str] = []
    total_bytes = 0
    for file in files:
        content = await file.read()
        total_bytes += len(content)
        if total_bytes > 32 * 1024 * 1024:
            raise ValueError("批量资料总大小不能超过 32MB。")
        filename = file.filename or "attachment.txt"
        parser = ocr_pdf_bytes if use_ocr and filename.lower().endswith(".pdf") else parse_document_bytes
        document = await run_in_threadpool(parser, filename, content)
        documents.append(document)
        warnings.extend([f"{file.filename or '资料'}：{warning}" for warning in document.warnings])
    attachments = await run_in_threadpool(import_creative_documents, name, story_id, "", documents, scope=scope)
    return _envelope({"accepted_count": len(attachments), "attachments": attachments, "warnings": warnings, "scope": scope, "ocr_requested": bool(use_ocr)}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/ingestion/ocr-preview")
async def preview_ocr(project_id: str, story_id: str, request: Request, file: UploadFile = File(...), languages: str = Form("chi_sim+eng"), dpi: int = Form(200)) -> dict[str, Any]:
    """Preview local OCR without persisting the source or scheduling extraction."""
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    filename = file.filename or "preview.pdf"
    if not filename.lower().endswith(".pdf"):
        raise ValueError("OCR 预览只支持 PDF 文件。")
    content = await file.read()
    progress: list[dict[str, Any]] = []
    from novelforge.services.document_parsing import ocr_pdf_bytes

    document = await run_in_threadpool(
        ocr_pdf_bytes,
        filename,
        content,
        languages=languages,
        dpi=max(72, min(int(dpi or 200), 600)),
        progress_callback=progress.append,
    )
    sections = [
        {
            "title": section.title,
            "page": section.location.get("page"),
            "confidence": section.location.get("ocr_confidence"),
            "char_count": len(section.text),
            "text_preview": section.text[:2_000],
        }
        for section in document.sections
    ]
    return _envelope(
        {
            "filename": document.filename,
            "parser_name": document.parser_name,
            "warnings": document.warnings,
            "metadata": document.metadata,
            "sections": sections,
            "progress": progress,
        },
        request,
    )

@router.get(f"{API_PREFIX}/projects/{{project_id}}/ingestion/{{task_id}}")
async def ingestion_detail(project_id: str, task_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    task = await run_in_threadpool(memory.load_source_ingestion_task, name, task_id)
    if not task:
        raise FileNotFoundError(f"资料导入任务不存在：{task_id}")
    return _envelope({"task": task}, request)

@router.post(f"{API_PREFIX}/projects/{{project_id}}/ingestion/{{task_id}}/control")
async def ingestion_control(project_id: str, task_id: str, payload: TaskControlRequest, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    from novelforge.workflows import ingestion_tasks

    handlers = {
        "pause": ingestion_tasks.pause_long_reference_ingestion_task,
        "resume": ingestion_tasks.resume_long_reference_ingestion_task,
        "cancel": ingestion_tasks.cancel_long_reference_ingestion_task,
        "retry": ingestion_tasks.retry_failed_long_reference_ingestion_task,
    }
    task = await run_in_threadpool(handlers[payload.action], name, task_id)
    return _envelope({"task": task, "action": payload.action}, request)
