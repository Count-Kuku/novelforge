"""Persistent background source-ingestion task manager."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import streamlit as st

from novelforge.services.memory import list_source_ingestion_tasks, load_llm_settings, load_source_ingestion_task
from novelforge.services.llm_usage import summarize_llm_usage
from novelforge.workflows.ingestion_task_dispatcher import (
    get_ingestion_task_dispatcher_status,
    wake_ingestion_task_dispatcher,
)
from novelforge.workflows.ingestion_tasks import (
    archive_long_reference_ingestion_task,
    cancel_long_reference_ingestion_task,
    cleanup_long_reference_ingestion_tasks,
    delete_long_reference_ingestion_task,
    pause_long_reference_ingestion_task,
    restore_long_reference_ingestion_task,
    resume_long_reference_ingestion_task,
    retry_failed_long_reference_ingestion_task,
)
from ui.common import confirmed_button, developer_mode_enabled, scoped_widget_key
from ui.ingestion_task_estimate import render_ingestion_task_estimate
from ui.llm_usage import format_usage_cost


TASK_STATUS_LABELS = {
    "queued": "等待后台执行",
    "running": "后台处理中",
    "paused": "已暂停",
    "failed": "执行中断",
    "completed_with_errors": "部分失败",
    "completed": "已完成",
    "cancelled": "已取消",
}

ITEM_STATUS_LABELS = {
    "queued": "等待处理",
    "running": "处理中",
    "completed": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
    "skipped": "已跳过",
}

STAGE_LABELS = {
    "import": "资料导入",
    "extraction": "知识提取",
    "consolidation": "知识整理",
    "auto_confirm": "自动审核",
}

STAGE_STATUS_LABELS = {
    "pending": "等待处理",
    "running": "处理中",
    "completed": "已完成",
    "failed": "失败",
    "skipped": "已跳过",
}


if hasattr(st, "fragment"):
    @st.fragment(run_every="3s")
    def _poll_task_update(project_name: str, task_id: str, known_updated_at: str) -> None:
        """Refresh the full task view only after its durable row changes."""
        latest = load_source_ingestion_task(project_name, task_id)
        if latest and str(latest.get("updated_at") or "") != str(known_updated_at or ""):
            st.rerun()
else:
    def _poll_task_update(project_name: str, task_id: str, known_updated_at: str) -> None:
        return None


def _task_action_error_message(exc: Exception) -> str:
    detail = str(exc).strip() or exc.__class__.__name__
    lowered = detail.lower()
    if any(token in lowered for token in ["worker", "lease", "租约", "status", "状态", "cannot", "不存在"]):
        return f"任务状态已发生变化，操作未执行：{detail}。请刷新任务列表后重试。"
    return f"任务操作失败：{detail}。任务记录仍会保留，可刷新后重试。"


def _execute_task_action(
    action,
    *,
    false_message: str = "操作未生效，任务状态可能已经变化。请刷新后重试。",
    wake_dispatcher: bool = False,
) -> bool:
    """Run one UI mutation without leaking stale-state exceptions to Streamlit."""
    try:
        result = action()
        if result is not False and wake_dispatcher:
            wake_ingestion_task_dispatcher()
    except Exception as exc:
        st.error(_task_action_error_message(exc))
        return False
    if result is False:
        st.error(false_message)
        return False
    st.rerun()
    return True


def _task_select_key(project_name: str, story_id: str) -> str:
    return scoped_widget_key("source_ingestion_task_select", project_name, story_id)


def _status_label(task: dict) -> str:
    control = str(task.get("control_requested") or "")
    if control == "pause":
        return "正在等待暂停"
    if control == "cancel":
        return "正在等待取消"
    return TASK_STATUS_LABELS.get(task.get("status"), str(task.get("status") or "-"))


def _render_task_filters(project_name: str, story_id: str) -> tuple[list[dict], str]:
    filter_cols = st.columns([2, 4, 1])
    archive_mode = filter_cols[0].selectbox(
        "任务范围",
        options=["活跃任务", "已归档", "全部任务"],
        key=scoped_widget_key("source_task_archive_filter", project_name, story_id),
    )
    status_options = list(TASK_STATUS_LABELS.keys())
    statuses = filter_cols[1].multiselect(
        "状态筛选",
        options=status_options,
        format_func=lambda value: TASK_STATUS_LABELS[value],
        key=scoped_widget_key("source_task_status_filter", project_name, story_id),
        placeholder="全部状态",
    )
    if filter_cols[2].button(
        "刷新",
        key=scoped_widget_key("refresh_source_tasks", project_name, story_id),
        width="stretch",
    ):
        st.rerun()
    include_archived = archive_mode != "活跃任务"
    tasks = list_source_ingestion_tasks(
        project_name,
        statuses=statuses or None,
        include_archived=include_archived,
    )
    if archive_mode == "已归档":
        tasks = [task for task in tasks if task.get("archived_at")]
    elif archive_mode == "全部任务":
        pass
    else:
        tasks = [task for task in tasks if not task.get("archived_at")]
    return tasks, archive_mode


def _render_runtime_status(task: dict) -> None:
    dispatcher = get_ingestion_task_dispatcher_status()
    if dispatcher.get("running"):
        st.caption("后台调度器正在运行；关闭浏览器页面不会停止资料任务。")
    else:
        st.warning("后台调度器当前未运行。任务会保留在数据库中，并在调度器恢复后继续。")
    if task.get("worker_id") and developer_mode_enabled():
        with st.expander("Worker、租约与心跳", expanded=False):
            st.json({
                "worker_id": task.get("worker_id", ""),
                "heartbeat_at": task.get("heartbeat_at", ""),
                "lease_expires_at": task.get("lease_expires_at", ""),
                "control_requested": task.get("control_requested", ""),
            })


def _render_task_actions(project_name: str, task: dict) -> None:
    task_id = str(task.get("task_id") or "")
    status = str(task.get("status") or "queued")
    progress = dict(task.get("progress") or {})
    archived = bool(task.get("archived_at"))
    control_pending = bool(task.get("control_requested"))

    if archived:
        action_cols = st.columns(2)
        if action_cols[0].button(
            "恢复到任务列表",
            key=scoped_widget_key("restore_source_task", project_name, task_id),
            width="stretch",
        ):
            _execute_task_action(
                lambda: restore_long_reference_ingestion_task(project_name, task_id),
                false_message="恢复失败：任务可能已恢复或已被删除。请刷新后确认。",
            )
        if confirmed_button(
            action_cols[1],
            "永久删除",
            "我确认永久删除这个任务记录",
            scoped_widget_key("delete_source_task", project_name, task_id),
            width="stretch",
        ):
            _execute_task_action(
                lambda: delete_long_reference_ingestion_task(project_name, task_id),
                false_message="永久删除未生效：任务可能不再处于归档状态。请刷新后确认。",
            )
        return

    action_cols = st.columns(4)
    if status in {"queued", "running"} and action_cols[0].button(
        "暂停",
        key=scoped_widget_key("pause_source_task", project_name, task_id),
        width="stretch",
        disabled=control_pending,
    ):
        _execute_task_action(lambda: pause_long_reference_ingestion_task(project_name, task_id))
    elif status in {"paused", "failed"} and action_cols[0].button(
        "继续后台执行",
        key=scoped_widget_key("resume_source_task", project_name, task_id),
        width="stretch",
        type="primary",
    ):
        _execute_task_action(
            lambda: resume_long_reference_ingestion_task(project_name, task_id),
            wake_dispatcher=True,
        )

    failed_count = int(progress.get("failed") or 0)
    failed_stage_count = sum(
        1
        for stage in task.get("execution", {}).get("stages", {}).values()
        if isinstance(stage, dict) and stage.get("status") == "failed"
    )
    if (failed_count or failed_stage_count) and status in {"paused", "failed", "completed_with_errors"} and action_cols[1].button(
        "重试失败项/阶段",
        key=scoped_widget_key("retry_source_task", project_name, task_id),
        width="stretch",
        type="primary" if status == "completed_with_errors" else "secondary",
    ):
        _execute_task_action(
            lambda: retry_failed_long_reference_ingestion_task(project_name, task_id),
            wake_dispatcher=True,
        )

    if status in {"queued", "running", "paused", "failed"} and action_cols[2].button(
        "取消未完成项",
        key=scoped_widget_key("cancel_source_task", project_name, task_id),
        width="stretch",
        disabled=control_pending,
    ):
        _execute_task_action(lambda: cancel_long_reference_ingestion_task(project_name, task_id))

    if status in {"failed", "completed_with_errors", "completed", "cancelled"} and action_cols[3].button(
        "归档",
        key=scoped_widget_key("archive_source_task", project_name, task_id),
        width="stretch",
    ):
        _execute_task_action(
            lambda: archive_long_reference_ingestion_task(project_name, task_id),
            false_message="归档未生效：任务可能仍由后台 worker 持有，或状态已经变化。请刷新后重试。",
        )


def _render_task_details(task: dict) -> None:
    stages = task.get("execution", {}).get("stages", {})
    if stages:
        with st.expander("处理阶段", expanded=task.get("status") in {"failed", "completed_with_errors"}):
            st.dataframe(
                [
                    {
                        "阶段": STAGE_LABELS.get(stage_name, stage_name),
                        "状态": STAGE_STATUS_LABELS.get(stage.get("status"), stage.get("status", "")),
                        "错误": stage.get("error", ""),
                    }
                    for stage_name, stage in stages.items()
                    if isinstance(stage, dict)
                ],
                width="stretch",
                hide_index=True,
            )
    with st.expander("片段执行明细", expanded=task.get("status") in {"failed", "completed_with_errors"}):
        st.dataframe(
            [
                {
                    "片段": item.get("title", ""),
                    "状态": ITEM_STATUS_LABELS.get(item.get("status"), item.get("status", "")),
                    "尝试次数": item.get("attempt_count", 0),
                    "候选知识": item.get("queued_knowledge_count", 0),
                    "错误": item.get("error", ""),
                }
                for item in task.get("items", [])
            ],
            width="stretch",
            hide_index=True,
        )
    if developer_mode_enabled():
        with st.expander("任务设置与最近结果", expanded=False):
            st.json({
            "任务 ID": task.get("task_id", ""),
            "批次 ID": task.get("batch_id", ""),
            "创建时间": task.get("created_at", ""),
            "更新时间": task.get("updated_at", ""),
            "归档时间": task.get("archived_at", ""),
            "设置": task.get("configuration", {}),
            "最近结果": task.get("result", {}),
            })


def _render_actual_usage(project_name: str, task: dict) -> None:
    task_id = str(task.get("task_id") or "")
    if not task_id:
        return
    try:
        usage = summarize_llm_usage(project_name=project_name, task_id=task_id)
    except Exception as exc:
        st.caption(f"暂时无法读取实际用量：{exc}")
        return
    with st.expander("实际 Token 与费用", expanded=bool(usage.get("has_usage"))):
        if not usage.get("has_usage"):
            st.caption("任务尚未产生可记录的模型调用。")
            return
        cols = st.columns(4)
        cols[0].metric("模型请求", int(usage.get("request_count") or 0))
        cols[1].metric("输入 Token", f"{int(usage.get('input_tokens') or 0):,}")
        cols[2].metric("输出 Token", f"{int(usage.get('output_tokens') or 0):,}")
        cols[3].metric("实际费用", format_usage_cost(usage, load_llm_settings()))
        if int(usage.get("embedding_tokens") or 0):
            st.caption(f"向量 Token：{int(usage.get('embedding_tokens') or 0):,}")


def render_ingestion_task_manager(project_name: str, story_id: str = "default") -> None:
    st.markdown("#### 后台资料任务")
    st.caption(
        "任务由后台 worker 执行。关闭当前浏览器页面后仍会继续；应用进程异常退出时，"
        "下次启动会在旧租约过期后自动接管。暂停和取消在片段处理边界生效。"
    )
    tasks, archive_mode = _render_task_filters(project_name, story_id)
    if not tasks:
        st.info("当前筛选条件下没有资料任务。可从“导入向导”或“长篇批次”创建。")
        return

    task_map = {str(task.get("task_id") or ""): task for task in tasks}
    task_ids = list(task_map.keys())
    select_key = _task_select_key(project_name, story_id)
    if st.session_state.get(select_key) not in task_ids:
        st.session_state[select_key] = task_ids[0]
    selected_task_id = st.selectbox(
        "选择资料任务",
        options=task_ids,
        format_func=lambda task_id: f"{_status_label(task_map[task_id])} · {task_map[task_id].get('title') or task_id}",
        key=select_key,
    )
    task = load_source_ingestion_task(project_name, selected_task_id) or task_map[selected_task_id]
    progress = dict(task.get("progress") or {})
    total = max(int(progress.get("total") or 0), 1)
    processed = sum(int(progress.get(key) or 0) for key in ["completed", "failed", "cancelled", "skipped"])

    metric_cols = st.columns(6)
    metric_cols[0].metric("状态", _status_label(task))
    metric_cols[1].metric("总片段", progress.get("total", 0))
    metric_cols[2].metric("已完成", progress.get("completed", 0))
    metric_cols[3].metric("等待", progress.get("queued", 0))
    metric_cols[4].metric("处理中", progress.get("running", 0))
    metric_cols[5].metric("失败", progress.get("failed", 0))
    st.progress(min(max(processed / total, 0.0), 1.0))
    if task.get("current_message"):
        st.caption(str(task.get("current_message")))
    if task.get("last_error"):
        st.error(f"最近错误：{task.get('last_error')}")
    if task.get("control_requested"):
        st.warning("控制请求已写入数据库，将在当前片段处理结束后生效。")
    if task.get("status") in {"queued", "running"}:
        auto_refresh = st.toggle(
            "自动刷新任务状态（每 3 秒）",
            value=True,
            key=scoped_widget_key("auto_refresh_source_task", project_name, selected_task_id),
        )
        if auto_refresh:
            _poll_task_update(project_name, selected_task_id, str(task.get("updated_at") or ""))

    _render_runtime_status(task)
    _render_task_actions(project_name, task)
    if task.get("estimate"):
        render_ingestion_task_estimate(
            task["estimate"],
            expanded=False,
            interactive_confirmation=False,
        )
    _render_actual_usage(project_name, task)
    _render_task_details(task)

    if archive_mode in {"已归档", "全部任务"}:
        st.divider()
        if confirmed_button(
            st,
            "清理 30 天前的归档任务",
            "我确认永久删除 30 天前的全部归档任务记录",
            scoped_widget_key("cleanup_source_tasks", project_name, story_id),
            width="content",
        ):
            try:
                deleted = cleanup_long_reference_ingestion_tasks(
                    project_name,
                    before=datetime.now(timezone.utc) - timedelta(days=30),
                )
            except Exception as exc:
                st.error(_task_action_error_message(exc))
            else:
                st.success(f"已永久清理 {deleted} 个归档任务。")
                st.rerun()
