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
    workspace = make_workspace("novelforge_ingestion_recovery_")
    previous_cwd = Path.cwd()
    os.chdir(workspace)
    try:
        from novelforge.domain.ingestion_tasks import (
            create_ingestion_task,
            reconcile_ingestion_task_with_batch,
            retry_failed_ingestion_task_items,
        )
        from novelforge.services.memory import (
            create_long_reference_batch,
            create_project,
            load_long_reference_batch,
        )
        from novelforge.workflows import source_workflows

        project_name = create_project("recovery_verify")
        batch = create_long_reference_batch(
            project_name,
            title="恢复验证",
            scope="reference",
            authority="curated",
            source_type="external_source",
            segments=[{"title": "片段", "content": "验证" * 40}],
        )

        task = create_ingestion_task(
            batch,
            [0],
            configuration={
                "import_to_index": True,
                "consolidate_after_extract": False,
                "auto_confirm_safe_items": False,
            },
        )
        batch["segments"][0]["extract_status"] = "queued"
        batch["segments"][0]["import_status"] = "pending"
        reconciled = reconcile_ingestion_task_with_batch(task, batch)
        check(reconciled["items"][0]["status"] == "queued", "已提取但未导入的片段仍待处理")
        check(reconciled["execution"]["stages"]["extraction"]["status"] == "completed", "提取阶段独立完成")
        check(reconciled["execution"]["stages"]["import"]["status"] == "pending", "导入阶段保持待处理")

        batch["segments"][0]["import_status"] = "failed"
        batch["segments"][0]["import_error"] = "模拟导入失败"
        failed = reconcile_ingestion_task_with_batch(reconciled, batch)
        check(failed["items"][0]["status"] == "failed", "导入失败会标记任务项失败")
        check(failed["items"][0]["failure_stages"] == ["import"], "失败项记录准确阶段")
        retried = retry_failed_ingestion_task_items(failed)
        check(retried["execution"]["stages"]["import"]["status"] == "pending", "重试只重置失败导入阶段")
        check(retried["execution"]["stages"]["extraction"]["status"] == "completed", "导入重试保留成功提取阶段")

        dependent_task = create_ingestion_task(
            batch,
            [0],
            configuration={
                "import_to_index": False,
                "consolidate_after_extract": True,
                "auto_confirm_safe_items": True,
            },
        )
        dependent_task["items"][0]["status"] = "failed"
        dependent_task["items"][0]["failure_stages"] = ["extraction"]
        dependent_task["execution"]["stages"]["extraction"]["status"] = "failed"
        dependent_task["execution"]["stages"]["consolidation"]["status"] = "skipped"
        dependent_task["execution"]["stages"]["auto_confirm"]["status"] = "completed"
        dependent_retry = retry_failed_ingestion_task_items(dependent_task)
        check(dependent_retry["execution"]["stages"]["extraction"]["status"] == "pending", "提取重试重置失败阶段")
        check(dependent_retry["execution"]["stages"]["consolidation"]["status"] == "pending", "提取重试使下游整理失效")
        check(dependent_retry["execution"]["stages"]["auto_confirm"]["status"] == "pending", "提取重试使下游自动审核失效")

        # A task-control exception raised after the durable extraction save
        # must propagate without rewriting the segment as failed.
        durable_batch = load_long_reference_batch(project_name, batch["batch_id"])

        def stop_after_success(event: dict) -> None:
            if str(event.get("message") or "").startswith("已完成："):
                raise RuntimeError("pause-boundary")

        with (
            patch.object(source_workflows, "extract_reference_knowledge", return_value={
                "data": {"knowledge_extraction": {"items": [], "source_title": ""}}
            }),
            patch.object(source_workflows, "get_segment_related_knowledge_items", return_value={"pending": []}),
            patch.object(source_workflows, "queue_pending_knowledge_items", return_value=0),
        ):
            try:
                source_workflows.extract_long_reference_segments_to_queue(
                    project_name,
                    durable_batch,
                    [0],
                    ["events"],
                    progress_callback=stop_after_success,
                )
            except RuntimeError as exc:
                check(str(exc) == "pause-boundary", "完成边界控制信号向上透传")
            else:
                raise AssertionError("完成边界控制信号被吞掉")
        durable_batch = load_long_reference_batch(project_name, batch["batch_id"])
        check(durable_batch["segments"][0]["extract_status"] == "queued", "完成边界暂停不污染成功片段")
        check(not durable_batch["segments"][0].get("extract_error"), "完成边界暂停不写入伪失败原因")

        # Retrying after source files were committed must still repair a failed
        # derived-index rebuild.
        durable_batch["segments"][0]["import_status"] = "imported"
        rebuild_calls: list[bool] = []
        with (
            patch.object(source_workflows, "ingest_external_source_file", side_effect=AssertionError("不应重复写源文件")),
            patch.object(
                source_workflows,
                "rebuild_retrieval_assets",
                side_effect=lambda _project, build_vectors: rebuild_calls.append(bool(build_vectors)),
            ),
        ):
            _, imported = source_workflows.import_long_reference_segments(project_name, durable_batch, [0])
        check(imported == 0, "已导入片段重试不重复写源文件")
        check(rebuild_calls == [True], "已导入片段重试仍修复派生索引")

        # With extraction already complete, a resumed durable task must execute
        # pending post-processing rather than finish early.
        stage_events: list[tuple[str, str]] = []
        consolidation_limits: list[int] = []
        execution_state = {
            "stages": {
                "import": {"status": "skipped"},
                "extraction": {
                    "status": "completed",
                    "result": {"processed_count": 1, "queued_count": 75, "failed_titles": []},
                },
                "consolidation": {"status": "pending"},
                "auto_confirm": {"status": "skipped"},
            },
            "candidate_ids": [],
        }

        def capture_stage(event: dict) -> None:
            if event.get("stage_status"):
                stage_events.append((str(event.get("stage")), str(event.get("stage_status"))))

        def skip_consolidation(*args, **kwargs):
            consolidation_limits.append(int(kwargs.get("limit") or 0))
            return {
                "success": False,
                "message": "无需整理",
                "source_count": 0,
                "queued_count": 0,
            }

        with (
            patch.object(source_workflows, "extract_long_reference_segments_to_queue", side_effect=AssertionError("不应重复提取")),
            patch.object(source_workflows, "consolidate_batch_pending_items", side_effect=skip_consolidation),
        ):
            _, summary = source_workflows.run_long_reference_quick_process(
                project_name,
                durable_batch,
                [0],
                enabled_categories=["events"],
                extraction_mode="general",
                extract_limit=1,
                import_to_index=False,
                consolidate_after_extract=True,
                auto_confirm_safe_items=False,
                execution_state=execution_state,
                progress_callback=capture_stage,
                run_key="resume-post-stage",
            )
        check(("consolidation", "running") in stage_events, "恢复任务进入待处理整理阶段")
        check(("consolidation", "skipped") in stage_events, "输入不足的整理阶段明确记为跳过")
        check(summary["executed_extract_segment_count"] == 0, "后处理恢复不重复调用模型提取")
        check(summary["queued_count"] == 75, "后处理恢复保留已提取候选计数")
        check(consolidation_limits == [75], "后处理恢复按持久化候选数设置整理上限")

        from novelforge.workflows import long_reference_quick_process as quick_process

        failed_stage_events: list[tuple[str, str]] = []

        def capture_failed_stage(event: dict) -> None:
            if event.get("stage_status"):
                failed_stage_events.append((str(event.get("stage")), str(event.get("stage_status"))))

        failed_execution_state = {
            "stages": {
                "import": {"status": "skipped"},
                "extraction": {"status": "completed"},
                "consolidation": {"status": "pending"},
                "auto_confirm": {"status": "pending"},
            },
            "candidate_ids": [],
        }
        with (
            patch.object(quick_process, "consolidate_batch_pending_items", return_value={
                "success": False,
                "message": "整理结果未写入",
                "source_count": 2,
                "queued_count": 0,
            }),
            patch.object(
                quick_process,
                "auto_confirm_pending_items_without_risk",
                side_effect=AssertionError("整理失败后不应执行自动审核"),
            ),
        ):
            source_workflows.run_long_reference_quick_process(
                project_name,
                durable_batch,
                [0],
                enabled_categories=["events"],
                extraction_mode="general",
                extract_limit=1,
                import_to_index=False,
                consolidate_after_extract=True,
                auto_confirm_safe_items=True,
                execution_state=failed_execution_state,
                progress_callback=capture_failed_stage,
                run_key="failed-post-stage",
            )
        check(("consolidation", "failed") in failed_stage_events, "整理写入失败会持久化失败阶段")
        check(not any(name == "auto_confirm" for name, _ in failed_stage_events), "整理失败会阻止下游自动审核")

        # Pending knowledge is project-wide. A concurrent task may add an
        # unrelated item between this task's before/after reads; automatic
        # review must remain scoped to the selected source segment.
        scoped_batch = load_long_reference_batch(project_name, batch["batch_id"])
        scoped_batch["segments"][0]["extract_status"] = "pending"
        selected_segment_id = str(scoped_batch["segments"][0]["segment_id"])
        reviewed_candidate_ids: list[str] = []

        def finish_scoped_extraction(_project, current_batch, *_args, **_kwargs):
            current_batch["segments"][0]["extract_status"] = "queued"
            current_batch["segments"][0]["queued_knowledge_count"] = 1
            return current_batch, 1, 1, []

        def capture_auto_confirm(_project, candidate_ids, **_kwargs):
            reviewed_candidate_ids.extend(candidate_ids)
            return {"confirmed_ids": [], "blocked_ids": list(candidate_ids)}

        with (
            patch.object(quick_process, "extract_long_reference_segments_to_queue", side_effect=finish_scoped_extraction),
            patch.object(quick_process, "load_pending_knowledge_items", side_effect=[
                [],
                [
                    {"pending_id": "selected-new", "source_segment_id": selected_segment_id},
                    {"pending_id": "other-batch-new", "source_segment_id": "other-segment"},
                ],
            ]),
            patch.object(quick_process, "auto_confirm_pending_items_without_risk", side_effect=capture_auto_confirm),
        ):
            _, scoped_summary = source_workflows.run_long_reference_quick_process(
                project_name,
                scoped_batch,
                [0],
                enabled_categories=["events"],
                extraction_mode="general",
                extract_limit=1,
                import_to_index=False,
                consolidate_after_extract=False,
                auto_confirm_safe_items=True,
                run_key="candidate-scope",
            )
        check(reviewed_candidate_ids == ["selected-new"], "自动审核候选不会串入并发批次")
        check(scoped_summary["new_pending_count"] == 1, "新增候选计数仅覆盖当前任务片段")

        print(f"Ingestion task recovery verification passed: {len(CHECKS)} checks")
    finally:
        os.chdir(previous_cwd)
        retry_rmtree(workspace)


if __name__ == "__main__":
    main()
