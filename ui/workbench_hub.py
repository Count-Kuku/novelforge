"""工作台 Hub：项目概览、内容浏览和项目/故事管理。"""
from __future__ import annotations

import streamlit as st

from ui.common import render_hub_navigation, scoped_widget_key
from ui.layout import render_section_heading


WORKBENCH_VIEWS = ["概览", "内容", "项目与故事"]


def render_workbench_hub(project_name: str, ui_modules: dict[str, object]) -> None:
    story_id = str(st.session_state.get("active_story_id") or "default")
    view_key = scoped_widget_key("workbench_hub_view", project_name, story_id)
    view = render_hub_navigation("工作台视图", WORKBENCH_VIEWS, key=view_key, default="概览")
    if view == "概览":
        ui_modules["project_overview"].render_project_overview_page(project_name)
        return
    if view == "内容":
        ui_modules["resource_management"].render_resource_management_page(project_name)
        return

    render_section_heading("项目与故事", "管理当前项目、故事信息和复制/切换操作。")
    settings_module = ui_modules["settings"]
    renderer = getattr(settings_module, "render_story_management_page", None)
    if renderer is None:
        st.error("故事管理组件尚未加载，请刷新页面重试。")
        return
    renderer(project_name)
