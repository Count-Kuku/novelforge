from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def verify_batch_guards() -> None:
    from ui.ingestion_batch_guard import render_batch_mutation_error
    from ui.long_reference_batch import _find_batch_write_conflicts

    tasks = [
        {"task_id": "queued", "batch_id": "batch-a", "status": "queued"},
        {"task_id": "running", "batch_id": "batch-a", "status": "running"},
        {"task_id": "paused", "batch_id": "batch-a", "status": "paused"},
        {"task_id": "failed", "batch_id": "batch-a", "status": "failed"},
        {"task_id": "partial", "batch_id": "batch-a", "status": "completed_with_errors"},
        {"task_id": "completed", "batch_id": "batch-a", "status": "completed"},
        {"task_id": "other", "batch_id": "batch-b", "status": "running"},
        {"task_id": "archived", "batch_id": "batch-a", "status": "paused", "archived_at": "2026-01-01"},
    ]
    conflicts = _find_batch_write_conflicts(tasks, "batch-a")
    conflict_ids = {task["task_id"] for task in conflicts}
    check(
        conflict_ids == {"queued", "running", "paused", "failed", "partial"},
        "同批次所有未完成任务锁定写操作",
    )
    check(not _find_batch_write_conflicts(tasks, "missing"), "其它批次任务不误锁当前批次")

    importer_source = (ROOT / "ui" / "long_reference_importer.py").read_text(encoding="utf-8")
    guard_position = importer_source.index("if render_batch_write_guard(")
    quick_position = importer_source.index("extraction_options = _render_long_reference_quick_processing(")
    stepwise_position = importer_source.index("_render_long_reference_stepwise_processing(", quick_position)
    check(guard_position < quick_position < stepwise_position, "导入向导在自动和分步写入入口前检查批次守卫")
    check("widget_scope=\"importer\"" in importer_source, "导入向导使用独立的任务跳转控件作用域")

    with (
        patch("ui.ingestion_batch_guard.st.error") as show_error,
        patch("ui.ingestion_batch_guard.st.info") as show_info,
    ):
        render_batch_mutation_error("保存批次", ValueError("批次已被任务占用"))
    check("批次已被任务占用" in str(show_error.call_args.args[0]), "原子批次冲突转为界面错误")
    check("刷新" in str(show_info.call_args.args[0]), "批次冲突提示刷新并进入任务处理")


def verify_project_guards() -> None:
    from novelforge.services import project_manager

    blocking = [
        {"task_id": "q", "status": "queued"},
        {"task_id": "r", "status": "running"},
    ]
    with patch.object(project_manager, "list_source_ingestion_tasks", return_value=blocking) as loader:
        try:
            project_manager._ensure_project_mutation_is_safe("demo", "重命名项目")
        except RuntimeError as exc:
            message = str(exc)
        else:
            raise AssertionError("运行任务未阻止项目操作")
    check("运行中" in message and "等待中" in message, "项目操作给出可执行的任务处理提示")
    check(set(loader.call_args.kwargs["statuses"]) == {"queued", "running"}, "项目守卫只查询阻断状态")

    with patch.object(
        project_manager,
        "list_source_ingestion_tasks",
        return_value=[{"task_id": "p", "status": "paused"}],
    ):
        project_manager._ensure_project_mutation_is_safe("demo", "删除项目")
    check(True, "已暂停任务不阻止安全的项目目录移动")

    sentinel = RuntimeError("guard-called")
    existing_dir = MagicMock()
    existing_dir.exists.return_value = True
    existing_dir.is_dir.return_value = True
    with (
        patch.object(project_manager, "_project_dir", return_value=existing_dir),
        patch.object(project_manager, "project_is_discoverable", return_value=True),
        patch.object(project_manager, "set_project_maintenance", return_value=True),
        patch.object(project_manager, "_ensure_project_mutation_is_safe", side_effect=sentinel),
    ):
        try:
            project_manager.delete_project("demo")
        except RuntimeError as exc:
            check(exc is sentinel, "删除项目在移动目录前调用服务层守卫")
        else:
            raise AssertionError("删除项目绕过服务层守卫")
    source_dir = MagicMock()
    source_dir.exists.return_value = True
    source_dir.is_dir.return_value = True
    target_dir = MagicMock()
    target_dir.exists.return_value = False
    with (
        patch.object(project_manager, "_project_dir", side_effect=[source_dir, target_dir]),
        patch.object(project_manager, "project_is_discoverable", return_value=False),
        patch.object(project_manager, "set_project_maintenance", return_value=True),
        patch.object(project_manager, "_ensure_project_mutation_is_safe", side_effect=sentinel),
    ):
        try:
            project_manager.rename_project("demo", "renamed")
        except RuntimeError as exc:
            check(exc is sentinel, "重命名项目在移动目录前调用服务层守卫")
        else:
            raise AssertionError("重命名项目绕过服务层守卫")


def verify_task_action_errors() -> None:
    from ui import ingestion_tasks

    with (
        patch.object(ingestion_tasks.st, "error") as show_error,
        patch.object(ingestion_tasks.st, "rerun") as rerun,
    ):
        result = ingestion_tasks._execute_task_action(
            lambda: (_ for _ in ()).throw(ValueError("Task status cannot be resumed: running"))
        )
    check(result is False and show_error.called, "过期状态异常转为界面错误")
    check("刷新" in str(show_error.call_args.args[0]), "过期状态错误引导用户刷新")
    check(not rerun.called, "失败操作不触发无意义 rerun")

    with (
        patch.object(ingestion_tasks.st, "error") as show_error,
        patch.object(ingestion_tasks.st, "rerun") as rerun,
    ):
        result = ingestion_tasks._execute_task_action(lambda: False, false_message="归档未生效")
    check(result is False and show_error.call_args.args[0] == "归档未生效", "布尔失败不会被静默当作成功")
    check(not rerun.called, "布尔失败保留当前任务视图")

    with (
        patch.object(ingestion_tasks.st, "error") as show_error,
        patch.object(ingestion_tasks.st, "rerun") as rerun,
        patch.object(ingestion_tasks, "wake_ingestion_task_dispatcher") as wake,
    ):
        result = ingestion_tasks._execute_task_action(lambda: {"status": "queued"}, wake_dispatcher=True)
    check(result is True and rerun.called and not show_error.called, "成功任务操作正常刷新界面")
    check(wake.called, "继续或重试成功后唤醒后台调度器")


def main() -> None:
    verify_batch_guards()
    verify_project_guards()
    verify_task_action_errors()
    print(f"Ingestion UI guard verification passed: {len(CHECKS)} checks")


if __name__ == "__main__":
    main()
