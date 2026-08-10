"""Resumable orchestration for long-reference import and knowledge processing."""
from __future__ import annotations

from datetime import datetime, timezone

from novelforge.services.memory import load_pending_knowledge_items, save_long_reference_batch
from novelforge.workflows.source_workflows import (
    auto_confirm_pending_items_without_risk,
    consolidate_batch_pending_items,
    extract_long_reference_segments_to_queue,
    import_long_reference_segments,
)


def append_long_reference_quick_run(batch: dict, summary: dict, *, run_key: str = "") -> dict:
    history = batch.get("quick_process_runs", [])
    if not isinstance(history, list):
        history = []
    history = [item for item in history if isinstance(item, dict)]
    run = {**summary, "run_at": datetime.now(timezone.utc).isoformat()}
    clean_run_key = str(run_key or "").strip()
    if clean_run_key:
        run["run_key"] = clean_run_key
        history = [item for item in history if str(item.get("run_key") or "") != clean_run_key]
    history.append(run)
    batch["quick_process_runs"] = history[-20:]
    batch["last_quick_process_run"] = run
    return batch


def _selected_pending_knowledge_ids(
    project_name: str,
    batch: dict,
    segment_indices: list[int],
) -> list[str]:
    segments = batch.get("segments", []) if isinstance(batch.get("segments", []), list) else []
    selected_ids = {
        str(segments[index].get("segment_id") or "")
        for index in segment_indices
        if 0 <= index < len(segments) and isinstance(segments[index], dict)
    }
    selected_ids.discard("")
    candidate_ids: list[str] = []
    for item in load_pending_knowledge_items(project_name):
        direct_id = str(item.get("source_segment_id") or "")
        related_ids = {
            str(value or "")
            for value in item.get("source_segment_ids", [])
            if str(value or "")
        }
        if direct_id not in selected_ids and not related_ids.intersection(selected_ids):
            continue
        pending_id = str(item.get("pending_id") or "")
        if pending_id and pending_id not in candidate_ids:
            candidate_ids.append(pending_id)
    return candidate_ids


def _safe_count(value: object) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def run_long_reference_quick_process(
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
    progress_callback=None,
    stream_callback=None,
    execution_state: dict | None = None,
    run_key: str = "",
    task_id: str = "",
    worker_id: str = "",
) -> tuple[dict, dict]:
    selected_indices = list(segment_indices)
    planned_extract_indices = selected_indices[: max(0, int(extract_limit))]
    segments = batch.get("segments", []) if isinstance(batch.get("segments", []), list) else []
    execution = dict(execution_state) if isinstance(execution_state, dict) else {}
    stages = execution.get("stages", {}) if isinstance(execution.get("stages", {}), dict) else {}

    def stage_is_done(stage_name: str) -> bool:
        stage = stages.get(stage_name, {})
        return isinstance(stage, dict) and stage.get("status") in {"completed", "skipped"}

    def previous_stage_result(stage_name: str) -> dict:
        stage = stages.get(stage_name, {})
        result = stage.get("result", {}) if isinstance(stage, dict) else {}
        return dict(result) if isinstance(result, dict) else {}

    progress_total = max(1, len(planned_extract_indices), len(selected_indices))

    def emit_stage(
        stage_name: str,
        stage_status: str,
        message: str,
        *,
        result: dict | None = None,
        candidate_ids: list[str] | None = None,
    ) -> None:
        result_payload = dict(result or {})
        stage_error = str(result_payload.get("error") or "")
        if stage_status == "failed" and not stage_error:
            failed_values = result_payload.get("failed_titles", [])
            if isinstance(failed_values, list) and failed_values:
                stage_error = "；".join(str(value) for value in failed_values if str(value))
            else:
                stage_error = str(result_payload.get("message") or message)
        stages[stage_name] = {
            **(stages.get(stage_name, {}) if isinstance(stages.get(stage_name, {}), dict) else {}),
            "status": stage_status,
            "error": stage_error if stage_status == "failed" else "",
            "result": result_payload,
        }
        if progress_callback:
            event = {
                "current": progress_total,
                "total": progress_total,
                "message": message,
                "stage": stage_name,
                "stage_status": stage_status,
                "stage_error": stage_error if stage_status == "failed" else "",
                "stage_result": result_payload,
            }
            if candidate_ids is not None:
                event["candidate_ids"] = list(candidate_ids)
            progress_callback(event)

    extract_indices = [
        index
        for index in planned_extract_indices
        if 0 <= index < len(segments)
        and isinstance(segments[index], dict)
        and segments[index].get("extract_status") not in {"queued", "extracted"}
    ]
    before_pending_ids = {str(item.get("pending_id") or "") for item in load_pending_knowledge_items(project_name)}
    raw_candidate_ids = execution.get("candidate_ids", [])
    if not isinstance(raw_candidate_ids, list):
        raw_candidate_ids = []
    candidate_ids = [str(value) for value in raw_candidate_ids if str(value)]
    previous_import_result = previous_stage_result("import")
    previous_extraction_result = previous_stage_result("extraction")
    imported = max(
        _safe_count(previous_import_result.get("imported_count")),
        sum(
            1
            for index in selected_indices
            if 0 <= index < len(segments)
            and isinstance(segments[index], dict)
            and segments[index].get("import_status") == "imported"
        ),
    )
    processed = max(
        _safe_count(previous_extraction_result.get("processed_count")),
        sum(
            1
            for index in planned_extract_indices
            if 0 <= index < len(segments)
            and isinstance(segments[index], dict)
            and segments[index].get("extract_status") in {"queued", "extracted"}
        ),
    )
    queued_total = max(
        _safe_count(previous_extraction_result.get("queued_count")),
        sum(
            _safe_count(segments[index].get("queued_knowledge_count"))
            for index in planned_extract_indices
            if 0 <= index < len(segments) and isinstance(segments[index], dict)
        ),
    )
    previous_failed_titles = previous_extraction_result.get("failed_titles", [])
    failed_titles = (
        [str(value) for value in previous_failed_titles if str(value)]
        if isinstance(previous_failed_titles, list)
        else []
    )
    consolidation_summary: dict = previous_stage_result("consolidation")
    auto_confirm_summary: dict = previous_stage_result("auto_confirm")

    if progress_callback:
        progress_callback({"current": 0, "total": progress_total, "message": "准备自动处理"})
    if import_to_index and not stage_is_done("import"):
        if progress_callback:
            progress_callback({"current": 0, "total": progress_total, "message": "正在导入资料索引"})
        batch, newly_imported = import_long_reference_segments(
            project_name,
            batch,
            selected_indices,
            progress_callback=progress_callback,
            task_id=task_id,
            worker_id=worker_id,
        )
        imported += newly_imported
        import_failures = [
            str(segments[index].get("title") or f"片段 {index + 1}")
            for index in selected_indices
            if 0 <= index < len(segments) and segments[index].get("import_status") == "failed"
        ]
        emit_stage(
            "import",
            "failed" if import_failures else "completed",
            "资料导入阶段完成" if not import_failures else f"资料导入失败 {len(import_failures)} 段",
            result={"imported_count": imported, "failed_titles": import_failures},
        )
    if not import_to_index and not stage_is_done("import"):
        emit_stage("import", "skipped", "已跳过资料索引导入")

    if not stage_is_done("extraction"):
        if extract_indices:
            batch, newly_processed, newly_queued, failed_titles = extract_long_reference_segments_to_queue(
                project_name,
                batch,
                extract_indices,
                enabled_categories,
                extraction_mode=extraction_mode,
                custom_instructions=custom_instructions,
                progress_callback=progress_callback,
                stream_callback=stream_callback,
                task_id=task_id,
                worker_id=worker_id,
            )
            processed += newly_processed
            queued_total += newly_queued
        selected_pending_ids = _selected_pending_knowledge_ids(
            project_name,
            batch,
            planned_extract_indices,
        )
        candidate_ids = list(dict.fromkeys([*candidate_ids, *selected_pending_ids]))
        emit_stage(
            "extraction",
            "failed" if failed_titles else "completed",
            "知识提取阶段完成" if not failed_titles else f"知识提取失败 {len(failed_titles)} 段",
            result={
                "processed_count": processed,
                "queued_count": queued_total,
                "failed_titles": failed_titles,
            },
            candidate_ids=candidate_ids,
        )
    else:
        # Rebuild the scoped candidate set when resuming older checkpoints
        # that did not persist candidate_ids yet.
        selected_pending_ids = _selected_pending_knowledge_ids(
            project_name,
            batch,
            planned_extract_indices,
        )
        candidate_ids = list(dict.fromkeys([*candidate_ids, *selected_pending_ids]))

    # The pending queue is project-wide. Restrict the before/after delta to
    # this task's selected segments so concurrent batches cannot leak their
    # candidates into this task's automatic review.
    new_pending_ids = [
        pending_id
        for pending_id in selected_pending_ids
        if pending_id not in before_pending_ids
    ]

    extraction_failed = (
        isinstance(stages.get("extraction"), dict)
        and stages["extraction"].get("status") == "failed"
    )
    if consolidate_after_extract and not extraction_failed and not stage_is_done("consolidation"):
        emit_stage("consolidation", "running", "正在整理散知识")
        consolidation_summary = consolidate_batch_pending_items(
            project_name,
            batch,
            categories=enabled_categories,
            consolidation_mode="balanced",
            limit=max(20, min(120, queued_total)),
            stream_callback=stream_callback,
            task_id=task_id,
        )
        candidate_ids = list(dict.fromkeys([
            *candidate_ids,
            *_selected_pending_knowledge_ids(project_name, batch, planned_extract_indices),
        ]))
        consolidation_status = "completed"
        if not consolidation_summary.get("success"):
            consolidation_status = (
                "skipped"
                if int(consolidation_summary.get("source_count") or 0) < 2
                else "failed"
            )
        emit_stage(
            "consolidation",
            consolidation_status,
            str(consolidation_summary.get("message") or "知识整理阶段完成"),
            result=consolidation_summary,
            candidate_ids=candidate_ids,
        )
    if not consolidate_after_extract and not stage_is_done("consolidation"):
        emit_stage("consolidation", "skipped", "已跳过知识整理")

    consolidation_failed = (
        isinstance(stages.get("consolidation"), dict)
        and stages["consolidation"].get("status") == "failed"
    )
    if auto_confirm_safe_items and not extraction_failed and not consolidation_failed and not stage_is_done("auto_confirm"):
        emit_stage("auto_confirm", "running", "正在自动审核低风险知识")
        auto_confirm_summary = auto_confirm_pending_items_without_risk(
            project_name,
            candidate_ids,
            source_type="long_reference_quick_process",
            source_title=batch.get("title", ""),
            batch_id=batch.get("batch_id", ""),
            note="长篇资料自动处理审核",
        )
        emit_stage(
            "auto_confirm",
            "completed",
            "自动审核阶段完成",
            result=auto_confirm_summary,
            candidate_ids=candidate_ids,
        )
    if not auto_confirm_safe_items and not stage_is_done("auto_confirm"):
        emit_stage("auto_confirm", "skipped", "已跳过自动审核")

    summary = {
        "selected_segment_count": len(selected_indices),
        "extract_segment_count": len(planned_extract_indices),
        "executed_extract_segment_count": len(extract_indices),
        "imported_count": imported,
        "processed_count": processed,
        "queued_count": queued_total,
        "new_pending_count": len(new_pending_ids),
        "candidate_count": len(candidate_ids),
        "auto_confirmed_count": len(auto_confirm_summary.get("confirmed_ids", [])) if auto_confirm_summary else 0,
        "blocked_count": len(auto_confirm_summary.get("blocked_ids", [])) if auto_confirm_summary else len(new_pending_ids),
        "failed_titles": failed_titles,
        "extraction_mode": extraction_mode,
        "categories": enabled_categories,
        "import_to_index": import_to_index,
        "consolidate_after_extract": consolidate_after_extract,
        "auto_confirm_safe_items": auto_confirm_safe_items,
        "custom_instructions": custom_instructions,
        "auto_confirm": auto_confirm_summary,
        "consolidation": consolidation_summary,
        "stage_statuses": {
            stage_name: str(stage.get("status") or "")
            for stage_name, stage in stages.items()
            if isinstance(stage, dict)
        },
    }
    batch = append_long_reference_quick_run(batch, summary, run_key=run_key)
    batch = save_long_reference_batch(
        project_name,
        batch,
        task_id=task_id,
        worker_id=worker_id,
    )
    if progress_callback:
        progress_callback({
            "current": progress_total,
            "total": progress_total,
            "message": f"自动处理完成：提取 {processed} 段，新增候选 {len(new_pending_ids)} 条",
            "quick_run_recorded": True,
            "quick_summary": summary,
        })
    return batch, summary
