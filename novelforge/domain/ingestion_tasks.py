"""State model for persistent source-ingestion tasks."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


INGESTION_TASK_WORKFLOW_TYPE = "source_ingestion"
INGESTION_TASK_ACTIVE_STATUSES = {
    "queued",
    "running",
    "paused",
    "failed",
    "completed_with_errors",
}
INGESTION_TASK_TERMINAL_STATUSES = {"completed", "cancelled"}
INGESTION_TASK_ITEM_TERMINAL_STATUSES = {"completed", "cancelled", "skipped"}
INGESTION_TASK_STATUSES = INGESTION_TASK_ACTIVE_STATUSES | INGESTION_TASK_TERMINAL_STATUSES
INGESTION_TASK_ITEM_STATUSES = {
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "skipped",
}
INGESTION_TASK_STAGE_NAMES = (
    "import",
    "extraction",
    "consolidation",
    "auto_confirm",
)
INGESTION_TASK_STAGE_STATUSES = {
    "pending",
    "running",
    "completed",
    "failed",
    "skipped",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def summarize_ingestion_task_items(items: list[dict]) -> dict:
    counts = {
        "queued": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
        "skipped": 0,
    }
    for item in items:
        status = str(item.get("status") or "queued")
        if status not in INGESTION_TASK_ITEM_STATUSES:
            status = "queued"
        counts[status] += 1
    total = len(items)
    finished = counts["completed"] + counts["cancelled"] + counts["skipped"]
    return {
        "total": total,
        "finished": finished,
        "remaining": max(total - finished, 0),
        **counts,
    }


def _normalize_execution_state(raw: dict, configuration: dict, task_status: str) -> dict:
    raw_execution = raw.get("execution", {})
    execution = dict(raw_execution) if isinstance(raw_execution, dict) else {}
    raw_stages = execution.get("stages", {})
    if not isinstance(raw_stages, dict):
        raw_stages = {}
    required = {
        "import": bool(configuration.get("import_to_index", True)),
        "extraction": True,
        "consolidation": bool(configuration.get("consolidate_after_extract", False)),
        "auto_confirm": bool(configuration.get("auto_confirm_safe_items", True)),
    }
    stages: dict[str, dict] = {}
    for stage_name in INGESTION_TASK_STAGE_NAMES:
        raw_stage = raw_stages.get(stage_name, {})
        if not isinstance(raw_stage, dict):
            raw_stage = {}
        if not required[stage_name]:
            status = "skipped"
        else:
            status = str(raw_stage.get("status") or "")
            if status not in INGESTION_TASK_STAGE_STATUSES:
                status = "completed" if task_status == "completed" else "pending"
        raw_result = raw_stage.get("result", {})
        stages[stage_name] = {
            **raw_stage,
            "status": status,
            "error": str(raw_stage.get("error") or ""),
            "result": dict(raw_result) if isinstance(raw_result, dict) else {},
            "updated_at": str(raw_stage.get("updated_at") or ""),
        }

    candidate_ids: list[str] = []
    for value in execution.get("candidate_ids", []):
        clean_value = str(value or "").strip()
        if clean_value and clean_value not in candidate_ids:
            candidate_ids.append(clean_value)
    return {
        **execution,
        "stages": stages,
        "candidate_ids": candidate_ids,
        "quick_run_recorded": bool(execution.get("quick_run_recorded", False)),
    }


def ingestion_task_has_pending_stages(task: dict) -> bool:
    """Return whether required task-level work remains after item processing."""
    normalized = normalize_ingestion_task(task)
    return any(
        stage.get("status") not in {"completed", "skipped"}
        for stage in normalized["execution"]["stages"].values()
    )


def normalize_ingestion_task(task: dict | None) -> dict:
    """Return a complete, backwards-compatible task snapshot."""
    raw = dict(task or {})
    task_id = str(raw.get("task_id") or raw.get("run_id") or f"ingestion_{uuid4().hex}")
    now = _now_iso()
    raw_items = raw.get("items", [])
    if not isinstance(raw_items, list):
        raw_items = []

    items: list[dict] = []
    for order, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, dict):
            continue
        segment_index = _safe_int(raw_item.get("segment_index"), order - 1)
        item_id = str(
            raw_item.get("item_id")
            or raw_item.get("step_id")
            or f"segment_{segment_index:04d}"
        )
        status = str(raw_item.get("status") or "queued")
        if status not in INGESTION_TASK_ITEM_STATUSES:
            status = "queued"
        items.append(
            {
                **raw_item,
                "item_id": item_id,
                "segment_index": segment_index,
                "segment_id": str(raw_item.get("segment_id") or ""),
                "title": str(raw_item.get("title") or f"片段 {segment_index + 1}"),
                "status": status,
                "attempt_count": max(0, _safe_int(raw_item.get("attempt_count"))),
                "error": str(raw_item.get("error") or ""),
                "created_at": str(raw_item.get("created_at") or raw.get("created_at") or now),
                "updated_at": str(raw_item.get("updated_at") or now),
            }
        )

    status = str(raw.get("status") or "queued")
    if status not in INGESTION_TASK_STATUSES:
        status = "queued"
    configuration = dict(raw.get("configuration") or {})
    normalized = {
        **raw,
        "task_id": task_id,
        "run_id": task_id,
        "workflow_type": INGESTION_TASK_WORKFLOW_TYPE,
        "story_id": str(raw.get("story_id") or ""),
        "batch_id": str(raw.get("batch_id") or ""),
        "title": str(raw.get("title") or "资料处理任务"),
        "status": status,
        "configuration": configuration,
        "estimate": dict(raw.get("estimate") or {}),
        "priority": _safe_int(raw.get("priority")),
        "items": items,
        "created_at": str(raw.get("created_at") or now),
        "updated_at": str(raw.get("updated_at") or now),
        "started_at": str(raw.get("started_at") or ""),
        "finished_at": str(raw.get("finished_at") or ""),
        "paused_at": str(raw.get("paused_at") or ""),
        "cancelled_at": str(raw.get("cancelled_at") or ""),
        "current_message": str(raw.get("current_message") or ""),
        "last_error": str(raw.get("last_error") or ""),
        "result": dict(raw.get("result") or {}),
        "worker_id": str(raw.get("worker_id") or ""),
        "lease_expires_at": str(raw.get("lease_expires_at") or ""),
        "heartbeat_at": str(raw.get("heartbeat_at") or ""),
        "control_requested": str(raw.get("control_requested") or ""),
        "archived_at": str(raw.get("archived_at") or ""),
    }
    normalized["execution"] = _normalize_execution_state(raw, configuration, status)
    normalized["progress"] = summarize_ingestion_task_items(items)
    return normalized


def create_ingestion_task(
    batch: dict,
    segment_indices: list[int],
    *,
    configuration: dict,
    story_id: str = "",
) -> dict:
    """Create an immutable work selection from a source batch."""
    segments = batch.get("segments", []) if isinstance(batch.get("segments", []), list) else []
    now = _now_iso()
    unique_indices: list[int] = []
    for raw_index in segment_indices:
        index = _safe_int(raw_index, -1)
        if 0 <= index < len(segments) and index not in unique_indices:
            unique_indices.append(index)
    if not unique_indices:
        raise ValueError("资料任务至少需要一个有效片段。")

    task_id = f"ingestion_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}_{uuid4().hex[:8]}"
    items = []
    for index in unique_indices:
        segment = segments[index]
        segment_id = str(segment.get("segment_id") or "")
        items.append(
            {
                "item_id": segment_id or f"segment_{index:04d}",
                "segment_index": index,
                "segment_id": segment_id,
                "title": str(segment.get("title") or f"片段 {index + 1}"),
                "status": "queued",
                "attempt_count": 0,
                "error": "",
                "created_at": now,
                "updated_at": now,
            }
        )
    return normalize_ingestion_task(
        {
            "task_id": task_id,
            "story_id": story_id,
            "batch_id": str(batch.get("batch_id") or ""),
            "batch_updated_at": str(batch.get("updated_at") or ""),
            "title": f"处理《{batch.get('title') or '未命名资料'}》",
            "status": "queued",
            "configuration": dict(configuration or {}),
            "items": items,
            "created_at": now,
            "updated_at": now,
        }
    )


def set_ingestion_task_status(
    task: dict,
    status: str,
    *,
    message: str = "",
    error: str = "",
) -> dict:
    """Apply a task-level state transition and its item side effects."""
    if status not in INGESTION_TASK_STATUSES:
        raise ValueError(f"不支持的资料任务状态：{status}")
    normalized = normalize_ingestion_task(task)
    now = _now_iso()
    normalized["status"] = status
    normalized["updated_at"] = now
    if message:
        normalized["current_message"] = message
    if error:
        normalized["last_error"] = error
    if status == "running":
        normalized["started_at"] = normalized.get("started_at") or now
        normalized["paused_at"] = ""
        normalized["finished_at"] = ""
    elif status == "paused":
        normalized["paused_at"] = now
        for item in normalized["items"]:
            if item.get("status") == "running":
                item["status"] = "queued"
                item["updated_at"] = now
    elif status == "cancelled":
        normalized["cancelled_at"] = now
        normalized["finished_at"] = now
        for item in normalized["items"]:
            if item.get("status") not in INGESTION_TASK_ITEM_TERMINAL_STATUSES:
                item["status"] = "cancelled"
                item["updated_at"] = now
    elif status in {"completed", "completed_with_errors"}:
        normalized["finished_at"] = now
    normalized["progress"] = summarize_ingestion_task_items(normalized["items"])
    return normalized


def retry_failed_ingestion_task_items(task: dict) -> dict:
    """Move failed items and stages back to the queue without repeating completed work."""
    normalized = normalize_ingestion_task(task)
    now = _now_iso()
    reset_count = 0
    for item in normalized["items"]:
        if item.get("status") == "failed":
            item["status"] = "queued"
            item["error"] = ""
            item["failure_stages"] = []
            item["updated_at"] = now
            reset_count += 1
    stages = normalized["execution"]["stages"]
    failed_stage_names = {
        stage_name
        for stage_name, stage in stages.items()
        if stage.get("status") == "failed"
    }
    reset_stage_names = set(failed_stage_names)
    # Extraction changes the pending-knowledge input consumed by consolidation
    # and auto-confirm. Retrying it must therefore invalidate completed
    # downstream stages, otherwise newly extracted knowledge is silently left
    # unprocessed. The same dependency applies from consolidation to
    # auto-confirm.
    if "extraction" in failed_stage_names:
        reset_stage_names.update({"consolidation", "auto_confirm"})
    elif "consolidation" in failed_stage_names:
        reset_stage_names.add("auto_confirm")

    reset_stage_count = 0
    required_stages = {
        "import": bool(normalized.get("configuration", {}).get("import_to_index", True)),
        "extraction": True,
        "consolidation": bool(normalized.get("configuration", {}).get("consolidate_after_extract", False)),
        "auto_confirm": bool(normalized.get("configuration", {}).get("auto_confirm_safe_items", True)),
    }
    for stage_name in INGESTION_TASK_STAGE_NAMES:
        if stage_name not in reset_stage_names:
            continue
        stage = stages[stage_name]
        if stage.get("status") == "skipped" and not required_stages[stage_name]:
            continue
        stage["status"] = "pending"
        stage["error"] = ""
        if stage_name in failed_stage_names and stage_name in {"import", "extraction"}:
            preserved_result = dict(stage.get("result") or {})
            preserved_result["failed_titles"] = []
            stage["result"] = preserved_result
        else:
            stage["result"] = {}
        stage["updated_at"] = now
        reset_stage_count += 1
    if not reset_count and not reset_stage_count:
        raise ValueError("当前任务没有可重试的失败片段或阶段。")
    normalized["status"] = "queued"
    normalized["updated_at"] = now
    normalized["finished_at"] = ""
    normalized["last_error"] = ""
    normalized["current_message"] = (
        f"已重置 {reset_count} 个失败片段和 {reset_stage_count} 个失败阶段。"
    )
    normalized["progress"] = summarize_ingestion_task_items(normalized["items"])
    return normalized


def reconcile_ingestion_task_with_batch(task: dict, batch: dict) -> dict:
    """Recover item states from the durable batch after a restart or crash."""
    normalized = normalize_ingestion_task(task)
    segments = batch.get("segments", []) if isinstance(batch.get("segments", []), list) else []
    segments_by_id = {
        str(segment.get("segment_id") or ""): segment
        for segment in segments
        if isinstance(segment, dict) and str(segment.get("segment_id") or "")
    }
    now = _now_iso()
    import_required = bool(normalized.get("configuration", {}).get("import_to_index", True))
    resolved_segments: list[dict | None] = []
    for item in normalized["items"]:
        index = _safe_int(item.get("segment_index"), -1)
        segment = segments_by_id.get(str(item.get("segment_id") or ""))
        if segment is None and 0 <= index < len(segments) and isinstance(segments[index], dict):
            segment = segments[index]
        resolved_segments.append(segment)
        failure_stages: list[str] = []
        errors: list[str] = []
        if segment is None:
            item["status"] = "failed"
            errors.append("对应资料片段不存在。")
            failure_stages.append("extraction")
            if import_required:
                failure_stages.append("import")
        else:
            extraction_complete = segment.get("extract_status") in {"queued", "extracted"}
            import_complete = not import_required or segment.get("import_status") == "imported"
            if segment.get("extract_status") == "failed":
                failure_stages.append("extraction")
                errors.append(str(segment.get("extract_error") or "片段提取失败。"))
            if import_required and segment.get("import_status") == "failed":
                failure_stages.append("import")
                errors.append(str(segment.get("import_error") or "片段导入失败。"))
            if failure_stages:
                item["status"] = "failed"
            elif extraction_complete and import_complete:
                item["status"] = "completed"
            elif item.get("status") in {"running", "failed", "completed"}:
                # An interrupted or partially completed request is recoverable.
                item["status"] = "queued"

        if item.get("status") == "completed":
            item["status"] = "completed"
            item["error"] = ""
            item["queued_knowledge_count"] = _safe_int(segment.get("queued_knowledge_count"))
        elif errors:
            item["error"] = "；".join(dict.fromkeys(errors))
        else:
            item["error"] = ""
        item["failure_stages"] = failure_stages
        item["updated_at"] = now

    stages = normalized["execution"]["stages"]

    def settle_segment_stage(stage_name: str, *, required: bool, status_key: str, complete_values: set[str]) -> None:
        stage = stages[stage_name]
        if not required:
            stage["status"] = "skipped"
            stage["error"] = ""
            return
        existing_segments = [segment for segment in resolved_segments if segment is not None]
        values = [str(segment.get(status_key) or "pending") for segment in existing_segments]
        missing_segment = len(existing_segments) != len(resolved_segments)
        if values and len(values) == len(resolved_segments) and all(value in complete_values for value in values):
            stage["status"] = "completed"
            stage["error"] = ""
        elif missing_segment or any(value == "failed" for value in values):
            stage["status"] = "failed"
            stage["error"] = "一个或多个片段处理失败。"
        elif stage.get("status") in {"running", "failed", "completed"}:
            stage["status"] = "pending"
            stage["error"] = ""
        stage["updated_at"] = now

    settle_segment_stage(
        "import",
        required=import_required,
        status_key="import_status",
        complete_values={"imported"},
    )
    settle_segment_stage(
        "extraction",
        required=True,
        status_key="extract_status",
        complete_values={"queued", "extracted"},
    )
    for stage_name in ("consolidation", "auto_confirm"):
        stage = stages[stage_name]
        if stage.get("status") == "running":
            stage["status"] = "pending"
            stage["updated_at"] = now
    normalized["updated_at"] = now
    normalized["progress"] = summarize_ingestion_task_items(normalized["items"])
    return normalized
