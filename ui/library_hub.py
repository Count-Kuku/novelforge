"""资料库 Hub：知识、待审核和资料导入/来源管理。"""
from __future__ import annotations

import streamlit as st

from ui.labels import KNOWLEDGE_CATEGORY_LABELS
from ui.common import render_hub_navigation, scoped_widget_key


LIBRARY_VIEWS = ["查找与编辑", "优先设定", "待审核", "导入与来源"]


def _render_knowledge_view(project_name: str, ui_modules: dict[str, object], view: str, *, render_memory_page) -> None:
    story_id = str(st.session_state.get("active_story_id") or "default")
    library_key = scoped_widget_key("knowledge_library_view", project_name, story_id)
    all_view_key = scoped_widget_key("knowledge_library_all_view", project_name, story_id)
    review_view_key = scoped_widget_key("knowledge_library_review_view", project_name, story_id)
    if view == "查找与编辑":
        st.session_state[library_key] = "全部知识"
        st.session_state[all_view_key] = "统一搜索"
    elif view == "优先设定":
        st.session_state[library_key] = "优先设定"
    else:
        st.session_state[library_key] = "待审核知识"
        st.session_state[review_view_key] = "审核队列"

    settings_module = ui_modules["settings"]
    settings_module.render_settings_page(
        project_name,
        library_view=view,
        render_memory_page=render_memory_page,
        render_knowledge_organizer=ui_modules["knowledge_management"].render_knowledge_organizer,
        render_pending_knowledge_queue=ui_modules["knowledge_management"].render_pending_knowledge_queue,
        render_auto_review_policy_panel=ui_modules["knowledge_management"].render_auto_review_policy_panel,
        render_auto_review_runs_panel=ui_modules["knowledge_management"].render_auto_review_runs_panel,
        knowledge_category_options=list(KNOWLEDGE_CATEGORY_LABELS.keys()),
    )


def render_library_hub(
    project_name: str,
    ui_modules: dict[str, object],
    *,
    render_ingestion_page,
    render_memory_page,
) -> None:
    story_id = str(st.session_state.get("active_story_id") or "default")
    view_key = scoped_widget_key("library_hub_view", project_name, story_id)
    view = render_hub_navigation("资料库工作区", LIBRARY_VIEWS, key=view_key, default="查找与编辑")
    if view == "导入与来源":
        render_ingestion_page(project_name, ui_modules, mode="ingestion")
        return
    _render_knowledge_view(project_name, ui_modules, view, render_memory_page=render_memory_page)
