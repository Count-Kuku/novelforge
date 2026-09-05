"""Implementation slice for the memory facade: long reference batches."""

from __future__ import annotations

import logging

from novelforge.services import memory as _memory_api
from storage.repositories.ingestion_batch_mutations import (
    delete_long_reference_batch_row,
    persist_long_reference_batch_row,
)
from storage.repositories.retrieval import search_retrieval_chunks_fts
from storage.repositories.sources import list_source_revision_rows

def long_reference_batches_path(project_name: str) -> _memory_api.Path:
    path = _memory_api.project_path(project_name) / "long_reference_batches"
    path.mkdir(exist_ok=True)
    return path


def long_reference_batch_path(project_name: str, batch_id: str) -> _memory_api.Path:
    safe_id = _memory_api.re.sub(r"[^A-Za-z0-9_\-]+", "_", str(batch_id or "")).strip("_")
    if not safe_id:
        raise ValueError("Batch id cannot be empty.")
    return long_reference_batches_path(project_name) / f"{safe_id}.json"


def _now_iso() -> str:
    return _memory_api.datetime.now(_memory_api.timezone.utc).isoformat()


def summarize_long_reference_batch(batch: dict) -> dict:
    segments = batch.get("segments", []) if isinstance(batch.get("segments", []), list) else []
    imported_count = len([item for item in segments if item.get("import_status") == "imported"])
    extracted_count = len([item for item in segments if item.get("extract_status") in {"queued", "extracted"}])
    failed_count = len([item for item in segments if item.get("extract_status") == "failed"])
    skipped_count = len([item for item in segments if item.get("extract_status") == "skipped"])
    total_count = len(segments)
    return {
        "segment_count": total_count,
        "imported_count": imported_count,
        "extract_queued_count": extracted_count,
        "extract_failed_count": failed_count,
        "extract_skipped_count": skipped_count,
        "import_pending_count": max(total_count - imported_count, 0),
        "extract_pending_count": len([
            item for item in segments
            if item.get("extract_status", "pending") in {"pending", ""}
        ]),
    }


def normalize_long_reference_batch(batch: dict | None) -> dict:
    raw = batch if isinstance(batch, dict) else {}
    batch_id = str(raw.get("batch_id") or f"batch_{_memory_api.uuid4().hex}")
    now = _now_iso()
    segments = []
    for index, item in enumerate(raw.get("segments", []) if isinstance(raw.get("segments", []), list) else [], start=1):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", ""))
        title = str(item.get("title") or f"片段 {index:03d}")
        segments.append({
            **item,
            "segment_id": str(item.get("segment_id") or f"seg_{index:04d}_{_memory_api.uuid4().hex[:8]}"),
            "index": int(item.get("index") or index),
            "title": title,
            "content": content,
            "char_count": int(item.get("char_count") or len(content)),
            "split_method": str(item.get("split_method") or "未知"),
            "import_status": str(item.get("import_status") or "pending"),
            "extract_status": str(item.get("extract_status") or "pending"),
            "queued_knowledge_count": int(item.get("queued_knowledge_count") or 0),
            "imported_source_name": str(item.get("imported_source_name") or ""),
            "extract_error": str(item.get("extract_error") or ""),
        })
    normalized = {
        **raw,
        "batch_id": batch_id,
        "title": str(raw.get("title") or "长篇资料批次"),
        "scope": str(raw.get("scope") or "reference"),
        "authority": str(raw.get("authority") or "curated"),
        "source_type": str(raw.get("source_type") or "external_source"),
        "source_origin": str(raw.get("source_origin") or ""),
        "source_file_name": str(raw.get("source_file_name") or ""),
        "content_fingerprint": str(raw.get("content_fingerprint") or ""),
        "source_content_hash": str(raw.get("source_content_hash") or ""),
        # 显式 None 判断：上游可能传 0 表示「未统计/空批次」，`or` 会把它当假值
        # 转而重算 sum()，覆盖掉调用方明确给出的 0。
        "content_char_count": int(
            raw["content_char_count"]
            if raw.get("content_char_count") is not None
            else sum(len(item.get("content", "")) for item in segments)
        ),
        "created_at": str(raw.get("created_at") or now),
        "updated_at": str(raw.get("updated_at") or now),
        "segments": segments,
    }
    normalized["summary"] = summarize_long_reference_batch(normalized)
    return normalized


def create_long_reference_batch(
    project_name: str,
    *,
    title: str,
    scope: str,
    authority: str,
    source_type: str,
    source_origin: str = "",
    source_file_name: str = "",
    content_fingerprint: str = "",
    source_content_hash: str = "",
    content_char_count: int = 0,
    segments: list[dict],
    story_id: str = "default",
    parser_metadata: dict | None = None,
    source_files: list[dict] | None = None,
) -> dict:
    batch = normalize_long_reference_batch({
        "batch_id": f"batch_{_memory_api.uuid4().hex}",
        "title": title,
        "scope": scope,
        "authority": authority,
        "source_type": source_type,
        "source_origin": source_origin,
        "source_file_name": source_file_name,
        "content_fingerprint": content_fingerprint,
        "source_content_hash": source_content_hash,
        "content_char_count": content_char_count,
        "story_id": str(story_id or "default"),
        "parser_metadata": dict(parser_metadata or {}),
        "source_files": [dict(item) for item in (source_files or []) if isinstance(item, dict)],
        "segments": segments,
    })
    return save_long_reference_batch(project_name, batch)


def save_long_reference_batch(
    project_name: str,
    batch: dict,
    *,
    task_id: str = "",
    worker_id: str = "",
) -> dict:
    normalized = normalize_long_reference_batch({
        **(batch or {}),
        "updated_at": _now_iso(),
    })
    persisted = _memory_api._mutate_workflow_in_db(
        project_name,
        lambda conn: persist_long_reference_batch_row(
            conn,
            batch=normalized,
            task_id=str(task_id or ""),
            worker_id=str(worker_id or ""),
        ),
        "long reference batch",
    )
    if not isinstance(persisted, dict):
        if not _memory_api.project_is_discoverable(project_name):
            raise FileNotFoundError(f"项目不存在或已被移动：{project_name}")
        raise RuntimeError("资料批次未能写入项目数据库。")
    normalized = normalize_long_reference_batch(persisted)
    return normalized


def load_long_reference_batch(project_name: str, batch_id: str) -> dict:
    db_item = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.load_long_reference_batch_row(conn, batch_id),
        "long reference batch",
    )
    if db_item is not None:
        if not db_item:
            return {}
        return normalize_long_reference_batch(db_item)
    path = long_reference_batch_path(project_name, batch_id)
    if not path.exists():
        return {}
    try:
        raw = _memory_api.json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return normalize_long_reference_batch(raw)


def _list_long_reference_batches_from_files(project_name: str) -> list[dict]:
    path = long_reference_batches_path(project_name)
    batches = []
    for file in sorted(path.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            raw = _memory_api.json.loads(file.read_text(encoding="utf-8"))
        except Exception:
            continue
        batch = normalize_long_reference_batch(raw)
        batch["file_name"] = file.name
        batches.append(batch)
    return batches


def list_long_reference_batches(project_name: str) -> list[dict]:
    db_items = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        _memory_api.load_long_reference_batch_rows,
        "long reference batches",
    )
    if db_items is not None:
        batches = []
        for item in db_items:
            batch = normalize_long_reference_batch(item)
            safe_id = _memory_api.re.sub(r"[^A-Za-z0-9_\-]+", "_", str(batch.get("batch_id") or "")).strip("_")
            batch["file_name"] = f"{safe_id}.json"
            batches.append(batch)
        return batches
    batches = _list_long_reference_batches_from_files(project_name)
    if db_items == [] and batches:
        for batch in batches:
            _memory_api._sync_source_to_db_best_effort(
                project_name,
                lambda conn, payload=batch: _memory_api.sync_long_reference_batch(conn, payload),
            )
    return batches


def delete_long_reference_batch(project_name: str, batch_id: str) -> bool:
    clean_batch_id = str(batch_id or "").strip()
    deleted = _memory_api._mutate_workflow_in_db(
        project_name,
        lambda conn: delete_long_reference_batch_row(conn, batch_id=clean_batch_id),
        "long reference batch deletion",
    )
    if deleted is None:
        if not _memory_api.project_is_discoverable(project_name):
            return False
        raise RuntimeError("资料批次未能从项目数据库删除。")
    return bool(deleted)
