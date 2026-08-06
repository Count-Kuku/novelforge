"""Shared UI guard for batches owned by durable ingestion tasks."""
from __future__ import annotations

import streamlit as st

from novelforge.domain.ingestion_tasks import INGESTION_TASK_ACTIVE_STATUSES
from novelforge.services.memory import list_source_ingestion_tasks
from ui.common import scoped_widget_key


BATCH_WRITE_BLOCKING_TASK_STATUSES = set(INGESTION_TASK_ACTIVE_STATUSES)


def find_batch_write_conflicts(tasks: list[dict], batch_id: str) -> list[dict]:
    clean_batch_id = str(batch_id or "")
    return [
        task
        for task in tasks
        if str(task.get("batch_id") or "") == clean_batch_id
        and str(task.get("status") or "") in BATCH_WRITE_BLOCKING_TASK_STATUSES
        and not task.get("archived_at")
    ]


def load_batch_write_conflicts(project_name: str, batch_id: str) -> list[dict]:
    tasks = list_source_ingestion_tasks(
        project_name,
        statuses=sorted(BATCH_WRITE_BLOCKING_TASK_STATUSES),
    )
    return find_batch_write_conflicts(tasks, batch_id)


def render_batch_mutation_error(action: str, exc: Exception) -> None:
    """Present an atomic storage rejection without exposing a Streamlit traceback."""
    st.error(f"{action}失败：{exc}")
    if isinstance(exc, ValueError):
        st.info("批次状态可能已被其他页面或后台任务更新，请刷新页面后前往资料任务处理。")


def render_batch_write_guard(
    project_name: str,
    batch_id: str,
    *,
    widget_scope: str,
) -> bool:
    """Keep inspection available while disabling every competing write path."""
    try:
        conflicts = load_batch_write_conflicts(project_name, batch_id)
    except Exception as exc:
        st.error(f"无法确认当前批次的后台任务状态：{exc}。为避免覆盖数据，写入操作已暂时停用。")
        return True
    if not conflicts:
        return False

    labels = {
        "queued": "等待执行",
        "running": "正在处理",
        "paused": "已暂停",
        "failed": "执行失败",
        "completed_with_errors": "部分失败",
    }
    status_text = "、".join(
        f"{labels.get(str(task.get('status') or ''), task.get('status') or '-')}：{task.get('title') or task.get('task_id')}"
        for task in conflicts[:3]
    )
    st.warning(
        "当前批次已有持久资料任务，现仅提供只读查看。为避免后台快照与手工操作互相覆盖，"
        f"导入、提取、整理、原始数据保存和删除均已停用。{status_text}"
    )
    story_id = str(st.session_state.get("active_story_id") or "default")
    if st.button(
        "前往资料任务处理",
        key=scoped_widget_key("open_batch_ingestion_task", project_name, batch_id, widget_scope),
        type="primary",
    ):
        st.session_state[scoped_widget_key("source_ingestion_task_select", project_name, story_id)] = str(
            conflicts[0].get("task_id") or ""
        )
        st.session_state[scoped_widget_key("ingestion_workspace_section", project_name, story_id)] = "资料任务"
        st.rerun()
    return True
