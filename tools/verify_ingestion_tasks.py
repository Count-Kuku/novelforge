from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.verify_utils import make_workspace, retry_rmtree


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def main() -> None:
    workspace = make_workspace("novelforge_ingestion_tasks_")
    previous_cwd = Path.cwd()
    os.chdir(workspace)
    try:
        from novelforge.services.memory import (
            create_long_reference_batch,
            create_project,
            list_source_ingestion_tasks,
            load_long_reference_batch,
            load_source_ingestion_task,
            project_path,
            save_long_reference_batch,
        )
        from novelforge.workflows import ingestion_tasks as source_workflows
        from storage import open_project_db

        project_name = create_project("ingestion_task_verify")
        batch = create_long_reference_batch(
            project_name,
            title="任务验证资料",
            scope="canon",
            authority="official",
            source_type="external_source",
            segments=[
                {
                    "title": "片段一",
                    "content": "甲" * 100,
                    "import_status": "imported",
                    "extract_status": "queued",
                },
                {"title": "片段二", "content": "乙" * 100},
                {"title": "片段三", "content": "丙" * 100},
            ],
        )

        task = source_workflows.create_long_reference_ingestion_task(
            project_name,
            batch,
            [0, 1, 2],
            enabled_categories=["characters", "events"],
            extraction_mode="balanced",
            extract_limit=3,
            import_to_index=True,
            consolidate_after_extract=False,
            auto_confirm_safe_items=False,
            story_id="default",
        )
        check(task["status"] == "queued", "new task is queued")
        check(task["progress"]["total"] == 3, "task stores selected segment count")
        check(task["configuration"]["enabled_categories"] == ["characters", "events"], "task stores execution configuration")

        loaded = load_source_ingestion_task(project_name, task["task_id"])
        check(loaded["task_id"] == task["task_id"], "task round-trips through SQLite")
        check(len(loaded["items"]) == 3, "task item snapshots round-trip")
        listed_ids = [item["task_id"] for item in list_source_ingestion_tasks(project_name)]
        check(task["task_id"] in listed_ids, "task appears in durable task list")
        with open_project_db(project_path(project_name)) as conn:
            run_row = conn.execute(
                "SELECT workflow_type, status FROM workflow_runs WHERE run_id = ?",
                (task["task_id"],),
            ).fetchone()
            step_count = conn.execute(
                "SELECT COUNT(*) FROM workflow_steps WHERE run_id = ?",
                (task["task_id"],),
            ).fetchone()[0]
        check(run_row["workflow_type"] == "source_ingestion", "task uses source_ingestion workflow type")
        check(step_count == 3, "each task segment has a workflow step")

        calls: list[list[int]] = []

        def successful_quick_process(project_name, batch, segment_indices, **kwargs):
            calls.append(list(segment_indices))
            progress_callback = kwargs.get("progress_callback")
            for current, index in enumerate(segment_indices, start=1):
                if kwargs.get("import_to_index"):
                    batch["segments"][index]["import_status"] = "imported"
                batch["segments"][index]["extract_status"] = "queued"
                batch["segments"][index]["queued_knowledge_count"] = current
                batch = save_long_reference_batch(
                    project_name,
                    batch,
                    task_id=str(kwargs.get("task_id") or ""),
                    worker_id=str(kwargs.get("worker_id") or ""),
                )
                if progress_callback:
                    progress_callback({"current": current, "total": len(segment_indices), "message": f"完成 {index}"})
            return batch, {
                "processed_count": len(segment_indices),
                "new_pending_count": len(segment_indices),
                "failed_titles": [],
            }

        # The first segment was durably completed before this task's worker
        # starts. Recovery must reconcile it without repeating the work.
        batch = load_long_reference_batch(project_name, batch["batch_id"])
        with patch.object(source_workflows, "run_long_reference_quick_process", side_effect=successful_quick_process):
            completed_task, summary = source_workflows.run_long_reference_ingestion_task(project_name, task["task_id"])
        check(calls == [[1, 2]], "resume skips already completed segments")
        check(completed_task["status"] == "completed", "recovered task completes")
        check(completed_task["progress"]["completed"] == 3, "all recovered task items complete")
        check(summary["processed_count"] == 3, "summary reports durable total across resumed work")
        check(load_source_ingestion_task(project_name, task["task_id"])["status"] == "completed", "completed status persists")

        stalled_batch = create_long_reference_batch(
            project_name,
            title="无进展保护资料",
            scope="reference",
            authority="curated",
            source_type="external_source",
            segments=[{"title": "仍待处理", "content": "保护" * 50}],
        )
        stalled_task = source_workflows.create_long_reference_ingestion_task(
            project_name,
            stalled_batch,
            [0],
            enabled_categories=["events"],
            extraction_mode="balanced",
            extract_limit=1,
            import_to_index=False,
            consolidate_after_extract=False,
            auto_confirm_safe_items=False,
        )

        def no_progress_process(project_name, batch, segment_indices, **kwargs):
            return batch, {"processed_count": 0, "failed_titles": []}

        with patch.object(source_workflows, "run_long_reference_quick_process", side_effect=no_progress_process):
            stalled_result, _ = source_workflows.run_long_reference_ingestion_task(
                project_name,
                stalled_task["task_id"],
            )
        check(stalled_result["status"] == "failed", "无进展流程不会误报完成")
        check(stalled_result["progress"]["queued"] == 1, "无进展流程保留可恢复片段")

        controlled_batch = create_long_reference_batch(
            project_name,
            title="终态控制竞争资料",
            scope="reference",
            authority="curated",
            source_type="external_source",
            segments=[{"title": "控制片段", "content": "控制" * 50}],
        )
        controlled_task = source_workflows.create_long_reference_ingestion_task(
            project_name,
            controlled_batch,
            [0],
            enabled_categories=["events"],
            extraction_mode="balanced",
            extract_limit=1,
            import_to_index=False,
            consolidate_after_extract=False,
            auto_confirm_safe_items=False,
        )

        def cancel_before_finalize(project_name, batch, segment_indices, **kwargs):
            index = segment_indices[0]
            batch["segments"][index]["extract_status"] = "queued"
            batch = save_long_reference_batch(
                project_name,
                batch,
                task_id=str(kwargs.get("task_id") or ""),
                worker_id=str(kwargs.get("worker_id") or ""),
            )
            source_workflows.cancel_long_reference_ingestion_task(project_name, controlled_task["task_id"])
            summary = {"processed_count": 1, "failed_titles": []}
            progress_callback = kwargs.get("progress_callback")
            if progress_callback:
                progress_callback({
                    "current": 1,
                    "total": 1,
                    "message": "最终结果已落盘",
                    "quick_run_recorded": True,
                    "quick_summary": summary,
                })
            return batch, summary

        with patch.object(source_workflows, "run_long_reference_quick_process", side_effect=cancel_before_finalize):
            controlled_result, _ = source_workflows.run_long_reference_ingestion_task(
                project_name,
                controlled_task["task_id"],
            )
        check(controlled_result["status"] == "completed", "全部工作落盘后的取消不会伪造取消终态")
        check(controlled_result["result"].get("processed_count") == 1, "终态控制竞争仍保留任务结果")
        check(not controlled_result.get("control_requested"), "过晚控制请求在终态事务中确认")

        # Simulate a partial result with one failed segment.
        retry_batch = create_long_reference_batch(
            project_name,
            title="失败重试资料",
            scope="reference",
            authority="curated",
            source_type="external_source",
            segments=[
                {"title": "成功片段", "content": "成功" * 50},
                {"title": "失败片段", "content": "失败" * 50},
            ],
        )
        retry_task = source_workflows.create_long_reference_ingestion_task(
            project_name,
            retry_batch,
            [0, 1],
            enabled_categories=["events"],
            extraction_mode="balanced",
            extract_limit=2,
            import_to_index=False,
            consolidate_after_extract=False,
            auto_confirm_safe_items=False,
        )
        retry_calls: list[list[int]] = []

        def partially_failed_process(project_name, batch, segment_indices, **kwargs):
            retry_calls.append(list(segment_indices))
            progress_callback = kwargs.get("progress_callback")
            if progress_callback:
                for current, index in enumerate(segment_indices, start=1):
                    progress_callback({
                        "current": current,
                        "total": len(segment_indices),
                        "message": f"处理 {index}",
                        "segment_index": index,
                    })
            batch["segments"][0]["extract_status"] = "queued"
            batch["segments"][1]["extract_status"] = "failed"
            batch["segments"][1]["extract_error"] = "模拟失败"
            batch = save_long_reference_batch(
                project_name,
                batch,
                task_id=str(kwargs.get("task_id") or ""),
                worker_id=str(kwargs.get("worker_id") or ""),
            )
            return batch, {"processed_count": 1, "new_pending_count": 1, "failed_titles": ["失败片段"]}

        with patch.object(source_workflows, "run_long_reference_quick_process", side_effect=partially_failed_process):
            partial_task, _ = source_workflows.run_long_reference_ingestion_task(project_name, retry_task["task_id"])
        check(partial_task["status"] == "completed_with_errors", "partial failure gets recoverable terminal status")
        check(partial_task["progress"]["completed"] == 1, "successful item remains completed")
        check(partial_task["progress"]["failed"] == 1, "failed item is recorded")

        reset_task = source_workflows.retry_failed_long_reference_ingestion_task(project_name, retry_task["task_id"])
        check(reset_task["status"] == "queued", "retry returns task to queue")
        check(reset_task["progress"]["queued"] == 1, "retry queues only failed item")
        check(reset_task["progress"]["completed"] == 1, "retry preserves completed item")
        retry_calls.clear()
        with patch.object(source_workflows, "run_long_reference_quick_process", side_effect=successful_quick_process):
            retried_task, _ = source_workflows.run_long_reference_ingestion_task(project_name, retry_task["task_id"])
        check(calls[-1] == [1], "failed retry executes only failed segment")
        check(retried_task["status"] == "completed", "retry can finish task")
        attempts = [item["attempt_count"] for item in retried_task["items"]]
        check(attempts == [1, 2], "attempt counts distinguish completed and retried items")

        # An exception after the first checkpoint must remain resumable.
        crash_batch = create_long_reference_batch(
            project_name,
            title="中断恢复资料",
            scope="reference",
            authority="curated",
            source_type="external_source",
            segments=[
                {"title": "已落盘片段", "content": "一" * 50},
                {"title": "未执行片段", "content": "二" * 50},
            ],
        )
        crash_task = source_workflows.create_long_reference_ingestion_task(
            project_name,
            crash_batch,
            [0, 1],
            enabled_categories=["events"],
            extraction_mode="balanced",
            extract_limit=2,
            import_to_index=False,
            consolidate_after_extract=False,
            auto_confirm_safe_items=False,
        )

        def crashing_process(project_name, batch, segment_indices, **kwargs):
            batch["segments"][segment_indices[0]]["extract_status"] = "queued"
            save_long_reference_batch(
                project_name,
                batch,
                task_id=str(kwargs.get("task_id") or ""),
                worker_id=str(kwargs.get("worker_id") or ""),
            )
            raise RuntimeError("模拟进程中断")

        with patch.object(source_workflows, "run_long_reference_quick_process", side_effect=crashing_process):
            try:
                source_workflows.run_long_reference_ingestion_task(project_name, crash_task["task_id"])
            except RuntimeError:
                pass
        crashed = load_source_ingestion_task(project_name, crash_task["task_id"])
        check(crashed["status"] == "failed", "execution exception persists failed task state")
        check(crashed["progress"]["completed"] == 1, "checkpointed segment survives exception")
        check(crashed["progress"]["queued"] == 1, "uncommitted segment returns to queue")
        calls.clear()
        with patch.object(source_workflows, "run_long_reference_quick_process", side_effect=successful_quick_process):
            recovered, _ = source_workflows.run_long_reference_ingestion_task(project_name, crash_task["task_id"])
        check(calls == [[1]], "exception recovery runs only uncommitted work")
        check(recovered["status"] == "completed", "exception recovery completes")

        control_batch = create_long_reference_batch(
            project_name,
            title="控制状态资料",
            scope="reference",
            authority="curated",
            source_type="external_source",
            segments=[{"title": "待处理", "content": "控制" * 50}],
        )
        paused_task = source_workflows.create_long_reference_ingestion_task(
            project_name,
            control_batch,
            [0],
            enabled_categories=["events"],
            extraction_mode="balanced",
            extract_limit=1,
            import_to_index=False,
            consolidate_after_extract=False,
            auto_confirm_safe_items=False,
        )
        paused_task = source_workflows.pause_long_reference_ingestion_task(project_name, paused_task["task_id"])
        check(paused_task["status"] == "paused", "queued task can be paused")
        cancelled_task = source_workflows.cancel_long_reference_ingestion_task(project_name, paused_task["task_id"])
        check(cancelled_task["status"] == "cancelled", "paused task can be cancelled")
        check(cancelled_task["progress"]["cancelled"] == 1, "cancel marks remaining items")

        print(f"Ingestion task verification passed: {len(CHECKS)} checks")
    finally:
        os.chdir(previous_cwd)
        retry_rmtree(workspace)


if __name__ == "__main__":
    main()
