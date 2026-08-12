"""Creation, control, and leased execution of persistent ingestion tasks."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

from novelforge.core.llm_usage import llm_usage_scope
from novelforge.domain.ingestion_task_estimates import estimate_ingestion_task
from novelforge.domain.ingestion_tasks import (
    create_ingestion_task,
    ingestion_task_has_pending_stages,
    normalize_ingestion_task,
    reconcile_ingestion_task_with_batch,
    retry_failed_ingestion_task_items,
    set_ingestion_task_status,
)
from novelforge.services.memory import (
    claim_source_ingestion_task,
    cleanup_archived_source_ingestion_tasks,
    delete_archived_source_ingestion_task,
    get_active_llm_profile,
    finalize_source_ingestion_task,
    load_long_reference_batch,
    load_source_ingestion_task,
    load_source_ingestion_task_control,
    is_project_in_maintenance,
    request_source_ingestion_task_control,
    save_long_reference_batch,
    save_source_ingestion_task,
    set_source_ingestion_task_archived,
)
from novelforge.services.llm_estimation import load_stage_calibration
from novelforge.services.model_readiness import require_chat_ready
from novelforge.workflows.long_reference_quick_process import run_long_reference_quick_process
from novelforge.workflows.ingestion_task_results import build_ingestion_task_result


DEFAULT_TASK_LEASE_SECONDS = 30


class IngestionTaskLeaseUnavailable(RuntimeError):
    pass


class IngestionTaskLeaseLost(RuntimeError):
    pass


class _IngestionTaskControlSignal(RuntimeError):
    def __init__(self, control: str):
        super().__init__(control)
        self.control = control


def build_long_reference_ingestion_estimate(
    batch: dict,
    segment_indices: list[int],
    *,
    enabled_categories: list[str],
    extraction_mode: str,
    import_to_index: bool,
    consolidate_after_extract: bool,
    custom_instructions: str = "",
) -> dict:
    profile = get_active_llm_profile()
    return estimate_ingestion_task(
        batch,
        segment_indices,
        enabled_categories=enabled_categories,
        extraction_mode=extraction_mode,
        import_to_index=import_to_index,
        consolidate_after_extract=consolidate_after_extract,
        custom_instructions=custom_instructions,
        model_profile=profile,
        calibrations={
            "extract": load_stage_calibration(
                "reference.extract",
                agent_role="extractor",
                endpoint_type="chat",
                profile=profile,
            ),
            "consolidate": load_stage_calibration(
                "reference.consolidate",
                agent_role="consolidator",
                endpoint_type="chat",
                profile=profile,
            ),
            "embedding": load_stage_calibration(
                "source_ingestion.run",
                agent_role="ingestion",
                endpoint_type="embedding",
                profile=profile,
            ),
        },
    )


def create_long_reference_ingestion_task(
    project_name: str,
    batch: dict,
    segment_indices: list[int],
    *,
    enabled_categories: list[str],
    extraction_mode: str,
    extract_limit: int,
    import_to_index: bool,
    consolidate_after_extract: bool,
    auto_confirm_safe_items: bool,
    custom_instructions: str = "",
    story_id: str = "",
    priority: int = 0,
) -> dict:
    planned_indices = list(segment_indices)[: max(0, int(extract_limit))]
    if planned_indices and enabled_categories:
        require_chat_ready(action="资料提取任务")
    configuration = {
        "enabled_categories": list(enabled_categories),
        "extraction_mode": str(extraction_mode),
        "extract_limit": len(planned_indices),
        "import_to_index": bool(import_to_index),
        "consolidate_after_extract": bool(consolidate_after_extract),
        "auto_confirm_safe_items": bool(auto_confirm_safe_items),
        "custom_instructions": str(custom_instructions or ""),
    }
    task = create_ingestion_task(
        batch,
        planned_indices,
        configuration=configuration,
        story_id=story_id,
    )
    task["priority"] = int(priority)
    task["estimate"] = build_long_reference_ingestion_estimate(
        batch,
        planned_indices,
        enabled_categories=enabled_categories,
        extraction_mode=extraction_mode,
        import_to_index=import_to_index,
        consolidate_after_extract=consolidate_after_extract,
        custom_instructions=custom_instructions,
    )
    return save_source_ingestion_task(project_name, task)


def _require_task(project_name: str, task_id: str) -> dict:
    task = load_source_ingestion_task(project_name, task_id)
    if not task:
        raise FileNotFoundError(f"资料任务不存在：{task_id}")
    return task


def pause_long_reference_ingestion_task(project_name: str, task_id: str) -> dict:
    result = request_source_ingestion_task_control(project_name, task_id, "pause")
    task = _require_task(project_name, task_id)
    if result.get("immediate"):
        task = set_ingestion_task_status(task, "paused", message="任务已暂停，可稍后继续。")
        return save_source_ingestion_task(project_name, task)
    return task


def resume_long_reference_ingestion_task(project_name: str, task_id: str) -> dict:
    request_source_ingestion_task_control(project_name, task_id, "resume")
    task = _require_task(project_name, task_id)
    # Another dispatcher may claim immediately after the atomic resume. Never
    # write an old queued snapshot over that new worker.
    if task.get("status") == "running" or task.get("worker_id"):
        return task
    task = set_ingestion_task_status(task, "queued", message="任务已放回后台队列。")
    task["finished_at"] = ""
    task["last_error"] = ""
    return save_source_ingestion_task(project_name, task)


def cancel_long_reference_ingestion_task(project_name: str, task_id: str) -> dict:
    result = request_source_ingestion_task_control(project_name, task_id, "cancel")
    task = _require_task(project_name, task_id)
    if result.get("immediate"):
        task = set_ingestion_task_status(task, "cancelled", message="未完成片段已取消。")
        return save_source_ingestion_task(project_name, task)
    return task


def retry_failed_long_reference_ingestion_task(project_name: str, task_id: str) -> dict:
    if is_project_in_maintenance(project_name):
        raise ValueError("项目正在重命名或删除，暂时不能重试资料任务。")
    task = _require_task(project_name, task_id)
    if task.get("worker_id"):
        raise ValueError("任务仍由后台 worker 持有，不能重试。")
    failed_items = [item for item in task.get("items", []) if item.get("status") == "failed"]
    failed_stages = [
        name
        for name, stage in task.get("execution", {}).get("stages", {}).items()
        if isinstance(stage, dict) and stage.get("status") == "failed"
    ]
    if not failed_items and not failed_stages:
        raise ValueError("当前任务没有可重试的失败片段或阶段。")
    batch = load_long_reference_batch(project_name, task.get("batch_id", ""))
    if not batch:
        raise FileNotFoundError("任务对应的长篇资料批次不存在。")
    segments = batch.get("segments", [])
    segments_by_id = {
        str(segment.get("segment_id") or ""): segment
        for segment in segments
        if isinstance(segment, dict) and str(segment.get("segment_id") or "")
    }
    for item in failed_items:
        index = int(item.get("segment_index", -1))
        segment = segments_by_id.get(str(item.get("segment_id") or ""))
        if segment is None and 0 <= index < len(segments):
            segment = segments[index]
        if segment is not None:
            failure_stages = set(item.get("failure_stages") or [])
            if not failure_stages or "extraction" in failure_stages:
                segment["extract_status"] = "pending"
                segment["extract_error"] = ""
            if "import" in failure_stages:
                segment["import_status"] = "pending"
                segment["import_error"] = ""
    save_long_reference_batch(project_name, batch, task_id=task_id)
    task = retry_failed_ingestion_task_items(task)
    return save_source_ingestion_task(project_name, task)


def archive_long_reference_ingestion_task(project_name: str, task_id: str) -> bool:
    return set_source_ingestion_task_archived(project_name, task_id, True)


def restore_long_reference_ingestion_task(project_name: str, task_id: str) -> bool:
    return set_source_ingestion_task_archived(project_name, task_id, False)


def delete_long_reference_ingestion_task(project_name: str, task_id: str) -> bool:
    return delete_archived_source_ingestion_task(project_name, task_id)


def cleanup_long_reference_ingestion_tasks(project_name: str, *, before) -> int:
    return cleanup_archived_source_ingestion_tasks(project_name, before=before)


def _claim_for_execution(
    project_name: str,
    task_id: str,
    worker_id: str,
    lease_seconds: int,
    lease_already_claimed: bool,
) -> dict:
    if lease_already_claimed:
        control = load_source_ingestion_task_control(project_name, task_id, worker_id)
        if not control.get("owned") or control.get("status") != "running":
            raise IngestionTaskLeaseLost(f"资料任务租约已失效：{task_id}")
        return _require_task(project_name, task_id)
    existing = _require_task(project_name, task_id)
    if existing.get("status") in {"paused", "failed"} and not existing.get("worker_id"):
        resume_long_reference_ingestion_task(project_name, task_id)
    claimed = claim_source_ingestion_task(
        project_name,
        task_id,
        worker_id,
        lease_seconds=lease_seconds,
    )
    if not claimed:
        existing = _require_task(project_name, task_id)
        if existing.get("status") == "completed":
            return existing
        raise IngestionTaskLeaseUnavailable(f"资料任务正由其他 worker 执行或当前不可运行：{task_id}")
    return claimed


def _save_owned_task(project_name: str, task: dict, worker_id: str) -> dict:
    saved = save_source_ingestion_task(project_name, task)
    if (
        str(saved.get("worker_id") or "") != str(worker_id)
        or str(saved.get("status") or "") != "running"
    ):
        raise IngestionTaskLeaseLost(
            f"资料任务租约已失效，旧 worker 的进度未写入：{task.get('task_id', '')}"
        )
    return saved


def _finalize_owned_task(project_name: str, task: dict, worker_id: str) -> dict:
    expected_status = str(task.get("status") or "")
    saved = finalize_source_ingestion_task(project_name, task, worker_id)
    requested = str(saved.get("control_requested") or "")
    if (
        str(saved.get("worker_id") or "") == str(worker_id)
        and str(saved.get("status") or "") == "running"
        and requested in {"pause", "cancel"}
    ):
        if expected_status in {"completed", "completed_with_errors"}:
            saved = finalize_source_ingestion_task(
                project_name,
                task,
                worker_id,
                acknowledged_control=requested,
            )
        else:
            expected_status = "paused" if requested == "pause" else "cancelled"
            controlled_task = set_ingestion_task_status(
                task,
                expected_status,
                message="任务已暂停，可稍后继续。" if requested == "pause" else "未完成片段已取消。",
            )
            saved = finalize_source_ingestion_task(project_name, controlled_task, worker_id)
    if saved.get("worker_id") or str(saved.get("status") or "") != expected_status:
        raise IngestionTaskLeaseLost(
            f"资料任务租约已失效，旧 worker 无权结束任务：{task.get('task_id', '')}"
        )
    return saved


def run_long_reference_ingestion_task(
    project_name: str,
    task_id: str,
    *,
    worker_id: str = "",
    lease_seconds: int = DEFAULT_TASK_LEASE_SECONDS,
    lease_already_claimed: bool = False,
    progress_callback=None,
    stream_callback=None,
) -> tuple[dict, dict]:
    owner = worker_id or f"manual:{os.getpid()}:{uuid4().hex[:10]}"
    task = _claim_for_execution(project_name, task_id, owner, lease_seconds, lease_already_claimed)
    if task.get("status") == "completed" and not task.get("worker_id"):
        return task, dict(task.get("result") or {})
    batch = load_long_reference_batch(project_name, task.get("batch_id", ""))
    if not batch:
        task = set_ingestion_task_status(task, "failed", message="任务对应的资料批次不存在。", error="任务对应的长篇资料批次不存在。")
        return _finalize_owned_task(project_name, task, owner), {}

    task = reconcile_ingestion_task_with_batch(task, batch)
    queued_items = [item for item in task.get("items", []) if item.get("status") == "queued"]
    if not queued_items and not ingestion_task_has_pending_stages(task):
        final_status = "completed_with_errors" if task["progress"].get("failed") else "completed"
        summary = build_ingestion_task_result(task, batch, task.get("result"))
        task["result"] = summary
        task = set_ingestion_task_status(task, final_status, message="任务没有剩余待处理片段。")
        return _finalize_owned_task(project_name, task, owner), summary

    task = set_ingestion_task_status(task, "running", message="正在后台处理剩余片段。")
    task = _save_owned_task(project_name, task, owner)
    task_holder = {"task": task}
    attempted_item_ids: set[str] = set()

    def checkpoint_progress(event: dict) -> None:
        event = dict(event or {})
        current = normalize_ingestion_task(task_holder["task"])
        current["current_message"] = str(event.get("message") or "正在处理资料片段。")
        now = datetime.now(timezone.utc).isoformat()
        stage_name = str(event.get("stage") or "")
        stage_status = str(event.get("stage_status") or "")
        stages = current.get("execution", {}).get("stages", {})
        if stage_name in stages and stage_status:
            stage = stages[stage_name]
            stage["status"] = stage_status
            stage["error"] = str(event.get("stage_error") or "")
            stage["result"] = dict(event.get("stage_result") or {})
            stage["updated_at"] = now
        if "candidate_ids" in event:
            current["execution"]["candidate_ids"] = list(dict.fromkeys(
                str(value) for value in event.get("candidate_ids", []) if str(value)
            ))
        if event.get("quick_run_recorded"):
            current["execution"]["quick_run_recorded"] = True
        if isinstance(event.get("quick_summary"), dict):
            current["execution"]["quick_summary"] = dict(event["quick_summary"])

        segment_index = event.get("segment_index")
        segment_id = str(event.get("segment_id") or "")
        if segment_index is None and not segment_id:
            try:
                event_position = int(event.get("current") or 0) - 1
            except (TypeError, ValueError):
                event_position = -1
            if 0 <= event_position < len(remaining_indices):
                segment_index = remaining_indices[event_position]
        for item in current.get("items", []):
            matches = segment_id and str(item.get("segment_id") or "") == segment_id
            if not matches and segment_index is not None:
                try:
                    matches = int(item.get("segment_index", -1)) == int(segment_index)
                except (TypeError, ValueError):
                    matches = False
            item_id = str(item.get("item_id") or "")
            if matches and item_id not in attempted_item_ids:
                item["status"] = "running"
                item["attempt_count"] = int(item.get("attempt_count") or 0) + 1
                item["updated_at"] = now
                attempted_item_ids.add(item_id)
                break

        task_holder["task"] = _save_owned_task(project_name, current, owner)
        control = load_source_ingestion_task_control(project_name, task_id, owner)
        if not control.get("owned"):
            raise IngestionTaskLeaseLost(f"资料任务租约已被其他 worker 接管：{task_id}")
        requested = str(control.get("control_requested") or "")
        if requested in {"pause", "cancel"}:
            raise _IngestionTaskControlSignal(requested)
        if progress_callback:
            progress_callback(event)

    selected_items = queued_items or list(task.get("items", []))
    remaining_indices = [int(item.get("segment_index", -1)) for item in selected_items]
    configuration = dict(task.get("configuration") or {})
    try:
        with llm_usage_scope(
            project_name=project_name,
            story_id=str(task.get("story_id") or "default"),
            task_id=task_id,
            workflow_run_id=task_id,
            operation="source_ingestion.run",
            agent_role="ingestion",
        ):
            updated_batch, summary = run_long_reference_quick_process(
                project_name,
                batch,
                remaining_indices,
                enabled_categories=list(configuration.get("enabled_categories") or []),
                extraction_mode=str(configuration.get("extraction_mode") or "general"),
                extract_limit=len(remaining_indices),
                import_to_index=bool(configuration.get("import_to_index", True)),
                consolidate_after_extract=bool(configuration.get("consolidate_after_extract", False)),
                auto_confirm_safe_items=bool(configuration.get("auto_confirm_safe_items", True)),
                custom_instructions=str(configuration.get("custom_instructions") or ""),
                progress_callback=checkpoint_progress,
                stream_callback=stream_callback,
                execution_state=dict(task.get("execution") or {}),
                run_key=task_id,
                task_id=task_id,
                worker_id=owner,
                story_id=str(task.get("story_id") or "default"),
            )
    except _IngestionTaskControlSignal as signal:
        latest_batch = load_long_reference_batch(project_name, task.get("batch_id", "")) or batch
        task = reconcile_ingestion_task_with_batch(task_holder["task"], latest_batch)
        summary = build_ingestion_task_result(
            task,
            latest_batch,
            task.get("execution", {}).get("quick_summary") or task.get("result"),
        )
        task["result"] = summary
        no_remaining_work = (
            not task["progress"].get("queued")
            and not task["progress"].get("running")
            and not ingestion_task_has_pending_stages(task)
        )
        if no_remaining_work:
            final_status = "completed_with_errors" if task["progress"].get("failed") else "completed"
            task = set_ingestion_task_status(task, final_status, message="资料任务已完成。")
            return _finalize_owned_task(project_name, task, owner), summary
        final_status = "paused" if signal.control == "pause" else "cancelled"
        task = set_ingestion_task_status(task, final_status)
        return _finalize_owned_task(project_name, task, owner), summary
    except IngestionTaskLeaseLost:
        # A replacement worker is now authoritative. The stale worker must not
        # overwrite its status or release somebody else's lease.
        raise
    except Exception as exc:
        before_reconcile = normalize_ingestion_task(task_holder["task"])
        running_stages = [
            name
            for name, stage in before_reconcile.get("execution", {}).get("stages", {}).items()
            if isinstance(stage, dict) and stage.get("status") == "running"
        ]
        latest_batch = load_long_reference_batch(project_name, task.get("batch_id", "")) or batch
        task = reconcile_ingestion_task_with_batch(before_reconcile, latest_batch)
        for stage_name in running_stages:
            stage = task.get("execution", {}).get("stages", {}).get(stage_name, {})
            stage["status"] = "failed"
            stage["error"] = str(exc)
            stage["updated_at"] = datetime.now(timezone.utc).isoformat()
        task = set_ingestion_task_status(task, "failed", message="任务执行中断，可稍后继续。", error=str(exc))
        _finalize_owned_task(project_name, task, owner)
        raise

    task = reconcile_ingestion_task_with_batch(task_holder["task"], updated_batch)
    summary = build_ingestion_task_result(task, updated_batch, summary)
    task["result"] = summary
    failed_stage = any(
        stage.get("status") == "failed"
        for stage in task.get("execution", {}).get("stages", {}).values()
        if isinstance(stage, dict)
    )
    unsettled_stage = any(
        stage.get("status") in {"pending", "running"}
        for stage in task.get("execution", {}).get("stages", {}).values()
        if isinstance(stage, dict)
    )
    unfinished_items = int(task["progress"].get("queued") or 0) + int(task["progress"].get("running") or 0)
    if unfinished_items or unsettled_stage:
        error = "处理流程已返回，但仍有片段或阶段未完成。"
        task = set_ingestion_task_status(
            task,
            "failed",
            message="任务未完整结束，可继续后台执行。",
            error=error,
        )
        return _finalize_owned_task(project_name, task, owner), summary

    final_status = "completed_with_errors" if task["progress"].get("failed") or failed_stage else "completed"
    message = "任务完成，但有失败片段或阶段可重试。" if final_status == "completed_with_errors" else "资料任务已完成。"
    task = set_ingestion_task_status(task, final_status, message=message)
    return _finalize_owned_task(project_name, task, owner), summary
