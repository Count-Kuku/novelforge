"""Import and activate sources directly from the free-writing workspace."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from novelforge.services.document_parsing import ParsedDocument
from novelforge.services.memory import (
    create_long_reference_batch,
    list_creative_attachments,
    list_long_reference_batches,
    load_creative_attachment,
    load_creative_session_bundle,
    save_creative_attachment,
    update_creative_attachment,
)
from novelforge.domain.extraction_presets import KNOWLEDGE_EXTRACTION_EXPERT_PRESETS
from novelforge.services.model_readiness import get_model_readiness
from novelforge.services.retrieval import (
    build_structured_external_source_payload,
    ingest_external_source_file,
    rebuild_retrieval_assets,
)
from novelforge.services.web_research import fetch_web_page
from novelforge.workflows.ingestion_task_dispatcher import wake_ingestion_task_dispatcher
from novelforge.workflows.ingestion_tasks import (
    build_long_reference_ingestion_estimate,
    create_long_reference_ingestion_task,
)
from novelforge.workflows.source_workflows import (
    build_ingestion_source_ledger,
    read_retrieval_source_payload,
    split_long_reference_text,
)


ATTACHMENT_SCOPE_LABELS = {
    "turn": "仅下一轮",
    "session": "当前创作",
    "story": "当前故事",
    "project": "整个项目",
}


def _source_name(content_hash: str, title: str) -> str:
    safe_title = re.sub(
        r"[^A-Za-z0-9_\-\u4e00-\u9fff]+",
        "_",
        str(title or "资料"),
    ).strip("_")[:40]
    return f"creative_{content_hash[:20]}_{safe_title or 'source'}"


def _attachment_source_name(
    content_hash: str,
    title: str,
    *,
    scope: str,
    story_id: str,
    session_id: str,
) -> str:
    owner = (
        session_id
        if scope == "session"
        else story_id
        if scope == "story"
        else "project"
    )
    owner_hash = hashlib.sha256(
        f"{scope}:{owner}".encode("utf-8")
    ).hexdigest()[:12]
    return f"{_source_name(content_hash, title)}_{owner_hash}"


def _scope_ownership(
    scope: str,
    *,
    story_id: str,
    session_id: str,
    turn_id: str = "",
) -> dict:
    if scope not in ATTACHMENT_SCOPE_LABELS:
        raise ValueError(f"不支持的附件作用域：{scope}")
    if scope in {"turn", "session"} and not session_id:
        raise ValueError("请先创建创作记录，再添加仅本轮或当前创作使用的资料。")
    return {
        "story_id": story_id if scope != "project" else None,
        "session_id": session_id if scope in {"turn", "session"} else None,
        "turn_id": turn_id if scope == "turn" else None,
    }


def _attachment_payload(
    *,
    content_hash: str,
    source_record: dict,
    title: str,
    filename: str,
    media_type: str,
    attachment_kind: str,
    scope: str,
    story_id: str,
    session_id: str,
    metadata: dict,
) -> dict:
    ownership = _scope_ownership(
        scope,
        story_id=story_id,
        session_id=session_id,
    )
    return {
        "attachment_id": f"attachment_{uuid4().hex}",
        "content_hash": content_hash,
        "source_id": str(source_record.get("source_id") or ""),
        "source_revision_id": str(source_record.get("source_revision_id") or "") or None,
        "relative_path": str(source_record.get("relative_path") or ""),
        "title": title,
        "filename": filename,
        "media_type": media_type,
        "attachment_kind": attachment_kind,
        "scope": scope,
        "status": "indexed",
        "remaining_uses": 1 if scope == "turn" else None,
        "metadata": {
            **metadata,
            "session_id": ownership.get("session_id") or "",
            "turn_id": ownership.get("turn_id") or "",
        },
        **ownership,
    }


def _source_metadata(
    metadata: dict,
    *,
    scope: str,
    story_id: str,
    session_id: str,
) -> dict:
    ownership = _scope_ownership(
        scope,
        story_id=story_id,
        session_id=session_id,
    )
    return {
        **metadata,
        "story_id": ownership.get("story_id") or "",
        "session_id": ownership.get("session_id") or "",
        "turn_id": ownership.get("turn_id") or "",
    }


def _source_scope(scope: str) -> str:
    return "project" if scope == "project" else "reference"


def _attachment_content(project_name: str, attachment: dict) -> str:
    payload = read_retrieval_source_payload(
        project_name,
        str(attachment.get("relative_path") or ""),
    )
    return str(payload.get("content") or "").strip()


def _existing_background_batch(project_name: str, attachment_id: str) -> dict:
    for batch in list_long_reference_batches(project_name):
        if str(batch.get("creative_attachment_id") or "") == attachment_id:
            return batch
    return {}


def schedule_creative_attachment_knowledge(
    project_name: str,
    attachment_id: str,
    *,
    confirm_over_budget: bool = False,
) -> dict:
    """Queue full-source extraction while keeping the lexical source usable."""

    attachment = load_creative_attachment(project_name, attachment_id)
    if not attachment:
        raise ValueError("创作附件不存在。")
    if attachment.get("ingestion_task_id"):
        return attachment

    readiness = get_model_readiness()
    metadata = dict(attachment.get("metadata") or {})
    if not readiness.get("chat_available") or readiness.get("chat_status") == "failed":
        return update_creative_attachment(
            project_name,
            attachment_id,
            {
                "metadata": {
                    **metadata,
                    "background_status": "capability_unavailable",
                    "background_message": readiness.get("chat_message") or "聊天模型暂不可用。",
                }
            },
        )

    content = _attachment_content(project_name, attachment)
    if not content:
        return update_creative_attachment(
            project_name,
            attachment_id,
            {
                "status": "failed",
                "metadata": {
                    **metadata,
                    "background_status": "failed",
                    "background_message": "资料正文为空，无法建立知识提取计划。",
                },
            },
        )

    batch = _existing_background_batch(project_name, attachment_id)
    if not batch:
        segments = split_long_reference_text(
            str(attachment.get("title") or "创作资料"),
            content,
            max_chars=6000,
            source_type="creative_attachment",
        )
        batch = create_long_reference_batch(
            project_name,
            title=str(attachment.get("title") or "创作资料"),
            scope="reference",
            authority="curated",
            source_type="creative_attachment",
            source_origin=str(metadata.get("source_origin") or ""),
            source_file_name=str(attachment.get("filename") or ""),
            content_fingerprint=str(attachment.get("content_hash") or ""),
            source_content_hash=str(attachment.get("content_hash") or ""),
            content_char_count=len(content),
            segments=segments,
            story_id=str(attachment.get("story_id") or "default"),
            parser_metadata=dict(metadata.get("parser_metadata") or {}),
            source_files=[{
                "name": str(attachment.get("filename") or attachment.get("title") or "资料"),
                "sha256": str(attachment.get("content_hash") or ""),
            }],
        )
        batch["creative_attachment_id"] = attachment_id
        from novelforge.services.memory import save_long_reference_batch

        batch = save_long_reference_batch(project_name, batch)

    segment_indices = list(range(len(batch.get("segments") or [])))
    preset = KNOWLEDGE_EXTRACTION_EXPERT_PRESETS["balanced"]
    estimate = build_long_reference_ingestion_estimate(
        batch,
        segment_indices,
        enabled_categories=list(preset["categories"]),
        extraction_mode=str(preset["mode"]),
        import_to_index=False,
        consolidate_after_extract=True,
    )
    if estimate.get("budget", {}).get("confirmation_required") and not confirm_over_budget:
        return update_creative_attachment(
            project_name,
            attachment_id,
            {
                "metadata": {
                    **metadata,
                    "background_status": "awaiting_confirmation",
                    "background_message": "后台知识整理超过当前费用或调用量确认阈值。",
                    "background_batch_id": batch.get("batch_id"),
                    "background_estimate": estimate,
                }
            },
        )

    task = create_long_reference_ingestion_task(
        project_name,
        batch,
        segment_indices,
        enabled_categories=list(preset["categories"]),
        extraction_mode=str(preset["mode"]),
        extract_limit=len(segment_indices),
        import_to_index=False,
        consolidate_after_extract=True,
        auto_confirm_safe_items=True,
        story_id=str(attachment.get("story_id") or "default"),
        priority=10,
    )
    updated = update_creative_attachment(
        project_name,
        attachment_id,
        {
            "status": "processing",
            "ingestion_task_id": task.get("task_id"),
            "metadata": {
                **metadata,
                "background_status": "queued",
                "background_message": "原文可检索，知识提取已进入后台队列。",
                "background_batch_id": batch.get("batch_id"),
                "background_estimate": estimate,
            },
        },
    )
    wake_ingestion_task_dispatcher()
    return updated


def _schedule_imported_attachments(project_name: str, attachments: list[dict]) -> list[dict]:
    result: list[dict] = []
    for attachment in attachments:
        try:
            result.append(
                schedule_creative_attachment_knowledge(
                    project_name,
                    str(attachment.get("attachment_id") or ""),
                )
            )
        except Exception as exc:
            metadata = dict(attachment.get("metadata") or {})
            result.append(
                update_creative_attachment(
                    project_name,
                    str(attachment.get("attachment_id") or ""),
                    {
                        "metadata": {
                            **metadata,
                            "background_status": "failed",
                            "background_message": str(exc),
                        }
                    },
                )
            )
    return result


def import_creative_documents(
    project_name: str,
    story_id: str,
    session_id: str,
    documents: list[ParsedDocument],
    *,
    scope: str = "session",
    schedule_knowledge: bool = True,
) -> list[dict]:
    imported: list[dict] = []
    for document in documents:
        content = str(document.text or "").strip()
        if not content:
            continue
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        metadata = {
            "creative_attachment": True,
            "attachment_scope": scope,
            "parser_metadata": {"documents": [document.to_dict()]},
            "original_filename": document.filename,
            "warnings": list(document.warnings),
        }
        metadata = _source_metadata(
            metadata,
            scope=scope,
            story_id=story_id,
            session_id=session_id,
        )
        payload = build_structured_external_source_payload(
            source_type="creative_attachment",
            scope=_source_scope(scope),
            title=document.title,
            summary=f"自由创作附件 · {ATTACHMENT_SCOPE_LABELS[scope]}",
            content=content,
            tags=["自由创作附件", ATTACHMENT_SCOPE_LABELS[scope]],
            metadata=metadata,
        )
        source_record = ingest_external_source_file(
            project_name,
            _attachment_source_name(
                content_hash,
                document.title,
                scope=scope,
                story_id=story_id,
                session_id=session_id,
            ),
            json.dumps(payload, ensure_ascii=False, indent=2),
            overwrite=True,
            return_record=True,
        )
        attachment = save_creative_attachment(
            project_name,
            _attachment_payload(
                content_hash=content_hash,
                source_record=source_record,
                title=document.title,
                filename=document.filename,
                media_type=document.media_type,
                attachment_kind="file",
                scope=scope,
                story_id=story_id,
                session_id=session_id,
                metadata=metadata,
            ),
        )
        imported.append(attachment)
    if imported:
        rebuild_retrieval_assets(project_name, build_vectors=False)
    return _schedule_imported_attachments(project_name, imported) if schedule_knowledge else imported


def import_creative_pasted_text(
    project_name: str,
    story_id: str,
    session_id: str,
    text: str,
    *,
    title: str = "粘贴资料",
    scope: str = "session",
    schedule_knowledge: bool = True,
) -> dict:
    content = str(text or "").strip()
    if not content:
        raise ValueError("粘贴资料不能为空。")
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    clean_title = str(title or "").strip() or "粘贴资料"
    metadata = {
        "creative_attachment": True,
        "attachment_scope": scope,
        "pasted_text": True,
    }
    metadata = _source_metadata(
        metadata,
        scope=scope,
        story_id=story_id,
        session_id=session_id,
    )
    payload = build_structured_external_source_payload(
        source_type="creative_attachment",
        scope=_source_scope(scope),
        title=clean_title,
        summary=f"自由创作附件 · {ATTACHMENT_SCOPE_LABELS[scope]}",
        content=content,
        tags=["自由创作附件", ATTACHMENT_SCOPE_LABELS[scope]],
        metadata=metadata,
    )
    source_record = ingest_external_source_file(
        project_name,
        _attachment_source_name(
            content_hash,
            clean_title,
            scope=scope,
            story_id=story_id,
            session_id=session_id,
        ),
        json.dumps(payload, ensure_ascii=False, indent=2),
        overwrite=True,
        return_record=True,
    )
    attachment = save_creative_attachment(
        project_name,
        _attachment_payload(
            content_hash=content_hash,
            source_record=source_record,
            title=clean_title,
            filename="",
            media_type="text/plain",
            attachment_kind="pasted_text",
            scope=scope,
            story_id=story_id,
            session_id=session_id,
            metadata=metadata,
        ),
    )
    rebuild_retrieval_assets(project_name, build_vectors=False)
    if schedule_knowledge:
        return _schedule_imported_attachments(project_name, [attachment])[0]
    return attachment


def import_creative_url(
    project_name: str,
    story_id: str,
    session_id: str,
    url: str,
    *,
    scope: str = "session",
    schedule_knowledge: bool = True,
) -> dict:
    page = fetch_web_page(url)
    content_hash = hashlib.sha256(page.text.encode("utf-8")).hexdigest()
    metadata = {
        "creative_attachment": True,
        "attachment_scope": scope,
        "source_origin": page.final_url,
        "requested_url": page.requested_url,
        "canonical_url": page.final_url,
        "fetched_at": page.fetched_at,
        "untrusted_web_content": True,
    }
    metadata = _source_metadata(
        metadata,
        scope=scope,
        story_id=story_id,
        session_id=session_id,
    )
    payload = build_structured_external_source_payload(
        source_type="creative_attachment",
        scope=_source_scope(scope),
        title=page.title,
        summary=f"网页附件 · {ATTACHMENT_SCOPE_LABELS[scope]}",
        content=page.text,
        tags=["自由创作附件", "网页", ATTACHMENT_SCOPE_LABELS[scope]],
        metadata=metadata,
    )
    source_record = ingest_external_source_file(
        project_name,
        _attachment_source_name(
            content_hash,
            str(urlsplit(page.final_url).hostname or page.title),
            scope=scope,
            story_id=story_id,
            session_id=session_id,
        ),
        json.dumps(payload, ensure_ascii=False, indent=2),
        overwrite=True,
        return_record=True,
    )
    attachment = save_creative_attachment(
        project_name,
        _attachment_payload(
            content_hash=content_hash,
            source_record=source_record,
            title=page.title,
            filename=Path(urlsplit(page.final_url).path).name,
            media_type=page.content_type,
            attachment_kind="url",
            scope=scope,
            story_id=story_id,
            session_id=session_id,
            metadata=metadata,
        ),
    )
    rebuild_retrieval_assets(project_name, build_vectors=False)
    if schedule_knowledge:
        return _schedule_imported_attachments(project_name, [attachment])[0]
    return attachment


def list_existing_creative_sources(project_name: str) -> list[dict]:
    """Return already imported retrieval sources that can be focused as attachments."""

    return [
        record
        for record in build_ingestion_source_ledger(project_name)
        if record.get("kind") == "retrieval_source"
        and record.get("relative_path")
        and record.get("source_id")
    ]


def attach_existing_creative_source(
    project_name: str,
    story_id: str,
    session_id: str,
    relative_path: str,
    *,
    scope: str = "session",
    schedule_knowledge: bool = False,
) -> dict:
    record = next(
        (
            item
            for item in list_existing_creative_sources(project_name)
            if str(item.get("relative_path") or "") == str(relative_path or "")
        ),
        None,
    )
    if record is None:
        raise ValueError("选择的已有资料不存在。")
    payload = read_retrieval_source_payload(project_name, relative_path)
    content = str(payload.get("content") or "").strip()
    if not content:
        raise ValueError("选择的已有资料没有可用正文。")
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    source_record = {
        "source_id": record.get("source_id"),
        "source_revision_id": record.get("source_revision_id"),
        "relative_path": relative_path,
    }
    metadata = _source_metadata(
        {
            "creative_attachment": True,
            "attachment_scope": scope,
            "existing_source": True,
            "original_source_type": record.get("source_type"),
            "source_origin": record.get("source_origin"),
        },
        scope=scope,
        story_id=story_id,
        session_id=session_id,
    )
    attachment = save_creative_attachment(
        project_name,
        _attachment_payload(
            content_hash=content_hash,
            source_record=source_record,
            title=str(record.get("title") or relative_path),
            filename=Path(relative_path).name,
            media_type="text/plain",
            attachment_kind="existing_source",
            scope=scope,
            story_id=story_id,
            session_id=session_id,
            metadata=metadata,
        ),
    )
    rebuild_retrieval_assets(project_name, build_vectors=False)
    if schedule_knowledge:
        return _schedule_imported_attachments(project_name, [attachment])[0]
    return attachment


def effective_creative_attachments(
    project_name: str,
    story_id: str,
    session_id: str,
) -> list[dict]:
    attachments = list_creative_attachments(
        project_name,
        story_id=story_id,
        session_id=session_id,
    )
    if session_id and load_creative_session_bundle(
        project_name,
        session_id,
        story_id=story_id,
    ) is None:
        raise ValueError("创作会话不存在或不属于当前故事。")
    return attachments
