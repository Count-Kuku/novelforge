from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.workflows import source_workflows


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def _health(**overrides) -> dict:
    payload = {
        "score": 88,
        "pending_count": 0,
        "confirmed_count": 0,
        "failed_segments": 0,
        "high_risk_issue_count": 0,
        "missing_confirmed": [],
    }
    payload.update(overrides)
    return payload


def _segment(import_status: str, extract_status: str) -> dict:
    return {
        "import_status": import_status,
        "extract_status": extract_status,
    }


def verify_attention_workbench() -> None:
    batches = [
        {
            "batch_id": "failed-batch",
            "title": "失败资料",
            "updated_at": "2026-08-05T01:00:00",
            "segments": [
                _segment("imported", "failed"),
                _segment("imported", "queued"),
            ],
        },
        {
            "batch_id": "continue-batch",
            "title": "待继续资料",
            "updated_at": "2026-08-05T02:00:00",
            "segments": [_segment("imported", "pending")],
        },
        {
            "batch_id": "ready-batch",
            "title": "已完成资料",
            "updated_at": "2026-08-05T03:00:00",
            "segments": [_segment("imported", "queued")],
        },
    ]
    with (
        patch.object(source_workflows, "list_long_reference_batches", return_value=batches),
        patch.object(source_workflows, "list_source_ingestion_tasks", return_value=[]),
        patch.object(source_workflows, "list_retrieval_source_files", return_value=["source-a.md", "source-b.md"]),
        patch.object(
            source_workflows,
            "build_ingestion_health_report",
            return_value=_health(
                pending_count=7,
                confirmed_count=12,
                failed_segments=1,
                high_risk_issue_count=2,
            ),
        ),
    ):
        workbench = source_workflows.build_ingestion_workbench("workbench_verify")

    check(workbench["overall_status"] == "attention", "risk makes overall status attention")
    check(workbench["risk_count"] == 3, "risk count combines failed segments and high-risk knowledge")
    check(workbench["unfinished_batch_count"] == 2, "unfinished batch count")
    check(workbench["completed_batch_count"] == 1, "completed batch count")
    check(workbench["needs_processing_count"] == 3, "processing count includes review queue")
    check(workbench["ready_source_count"] == 2, "ready source count")
    check(workbench["confirmed_knowledge_count"] == 12, "confirmed knowledge count")
    check(workbench["pending_review_count"] == 7, "pending review count")

    action_ids = [item["action_id"] for item in workbench["actions"]]
    check(action_ids[0] == "retry_batch:failed-batch", "failed retry is first recommendation")
    check(action_ids[1] == "review_high_risk_pending", "high-risk review is second recommendation")
    check("continue_batch:continue-batch" in action_ids, "unfinished batch recommendation exists")
    retry_action = workbench["actions"][0]
    check(retry_action["target_section"] == "长篇批次", "retry targets batch workspace")
    check(retry_action["batch_id"] == "failed-batch", "retry preserves selected batch")

    row_map = {row["batch_id"]: row for row in workbench["batch_rows"]}
    check(row_map["failed-batch"]["status"] == "attention", "failed batch status")
    check(row_map["continue-batch"]["status"] == "processing", "unfinished batch status")
    check(row_map["ready-batch"]["status"] == "ready", "completed batch status")


def verify_empty_workbench() -> None:
    with (
        patch.object(source_workflows, "list_long_reference_batches", return_value=[]),
        patch.object(source_workflows, "list_source_ingestion_tasks", return_value=[]),
        patch.object(source_workflows, "list_retrieval_source_files", return_value=[]),
        patch.object(source_workflows, "build_ingestion_health_report", return_value=_health()),
    ):
        workbench = source_workflows.build_ingestion_workbench("empty_verify")

    check(workbench["overall_status"] == "empty", "empty workspace status")
    check(workbench["actions"][0]["action_id"] == "start_ingestion", "empty workspace recommends import")
    check(workbench["actions"][0]["target_section"] == "导入向导", "empty action targets import wizard")


def verify_ready_workbench() -> None:
    batches = [{
        "batch_id": "ready-batch",
        "title": "已完成资料",
        "segments": [_segment("imported", "extracted")],
    }]
    with (
        patch.object(source_workflows, "list_long_reference_batches", return_value=batches),
        patch.object(source_workflows, "list_source_ingestion_tasks", return_value=[]),
        patch.object(source_workflows, "list_retrieval_source_files", return_value=["source.md"]),
        patch.object(
            source_workflows,
            "build_ingestion_health_report",
            return_value=_health(confirmed_count=8),
        ),
    ):
        workbench = source_workflows.build_ingestion_workbench("ready_verify")

    check(workbench["overall_status"] == "ready", "completed workspace status")
    check(workbench["needs_processing_count"] == 0, "completed workspace has no tasks")
    check(workbench["risk_count"] == 0, "completed workspace has no risk")
    check(workbench["actions"] == [], "completed workspace has no artificial recommendations")


def verify_empty_batch_attention() -> None:
    with (
        patch.object(
            source_workflows,
            "list_long_reference_batches",
            return_value=[{"batch_id": "empty-batch", "title": "空资料", "segments": []}],
        ),
        patch.object(source_workflows, "list_source_ingestion_tasks", return_value=[]),
        patch.object(source_workflows, "list_retrieval_source_files", return_value=["source.md"]),
        patch.object(
            source_workflows,
            "build_ingestion_health_report",
            return_value=_health(confirmed_count=1),
        ),
    ):
        workbench = source_workflows.build_ingestion_workbench("empty_batch_verify")

    check(workbench["overall_status"] == "attention", "empty batch needs attention")
    check(workbench["empty_batch_count"] == 1, "empty batch count")
    check(workbench["risk_count"] == 1, "empty batch contributes risk")
    check(workbench["needs_processing_count"] == 1, "empty batch contributes task")
    check(workbench["actions"][0]["action_id"] == "inspect_empty_batch:empty-batch", "empty batch action")


def verify_persistent_task_workbench() -> None:
    batches = [{
        "batch_id": "task-batch",
        "title": "任务资料",
        "segments": [_segment("imported", "queued"), _segment("imported", "failed")],
    }]
    tasks = [{
        "task_id": "ingestion-task-1",
        "batch_id": "task-batch",
        "title": "处理任务资料",
        "status": "completed_with_errors",
        "updated_at": "2026-08-05T04:00:00",
        "progress": {"total": 2, "completed": 1, "failed": 1, "remaining": 1},
    }]
    with (
        patch.object(source_workflows, "list_long_reference_batches", return_value=batches),
        patch.object(source_workflows, "list_source_ingestion_tasks", return_value=tasks),
        patch.object(source_workflows, "list_retrieval_source_files", return_value=["source.md"]),
        patch.object(
            source_workflows,
            "build_ingestion_health_report",
            return_value=_health(failed_segments=1, confirmed_count=1),
        ),
    ):
        workbench = source_workflows.build_ingestion_workbench("task_verify")

    check(workbench["active_task_count"] == 1, "recoverable task counts as active")
    check(workbench["failed_task_count"] == 1, "failed task count")
    check(workbench["needs_processing_count"] == 1, "task-covered batch is not double counted")
    check(workbench["task_rows"][0]["status_label"] == "部分失败", "task row status label")
    check(workbench["actions"][0]["action_id"] == "recover_task:ingestion-task-1", "task recovery is top recommendation")
    check(workbench["actions"][0]["target_section"] == "资料任务", "task action targets task manager")
    check(workbench["actions"][0]["task_id"] == "ingestion-task-1", "task action preserves selected task")
    check("retry_batch:task-batch" not in [item["action_id"] for item in workbench["actions"]], "task suppresses duplicate batch retry")


def main() -> None:
    verify_attention_workbench()
    verify_empty_workbench()
    verify_ready_workbench()
    verify_empty_batch_attention()
    verify_persistent_task_workbench()
    print(f"Ingestion workbench verification passed: {len(CHECKS)} checks")


if __name__ == "__main__":
    main()
