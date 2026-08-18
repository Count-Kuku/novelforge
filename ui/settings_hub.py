"""设置 Hub：模型、费用、高级创作设置和开发工具。"""
from __future__ import annotations

import streamlit as st

from ui.common import developer_mode_enabled, render_hub_navigation, scoped_widget_key


SETTINGS_VIEWS = ["模型与费用", "高级创作"]
ADVANCED_VIEWS = ["生成规则", "写作偏好"]
DEVELOPER_VIEWS = ["资料检索", "质量评测", "索引维护"]


def render_settings_hub(project_name: str | None, ui_modules: dict[str, object]) -> None:
    story_id = str(st.session_state.get("active_story_id") or "default")
    view_options = list(SETTINGS_VIEWS)
    if project_name and developer_mode_enabled():
        view_options.append("开发工具")
    view_key = "settings_hub_view"
    current_view = st.session_state.get(view_key)
    if current_view not in view_options:
        current_view = "模型与费用"
        st.session_state[view_key] = current_view
    view = render_hub_navigation("设置工作区", view_options, key=view_key, default=current_view)
    if view == "模型与费用":
        ui_modules["llm_settings"].render_llm_settings_page()
        return
    if view == "高级创作":
        advanced_key = scoped_widget_key("settings_advanced_view", project_name or "global", story_id)
        advanced_view = render_hub_navigation(
            "高级创作设置",
            ADVANCED_VIEWS,
            key=advanced_key,
            default="生成规则",
        )
        if not project_name:
            st.info("创建项目后才能管理项目级生成规则和写作偏好。")
        elif advanced_view == "生成规则":
            ui_modules["rules"].render_rules_page(project_name)
        else:
            ui_modules["prompt_options_page"].render_prompt_options_page(project_name)
        return

    developer_key = scoped_widget_key("settings_developer_view", project_name or "global", story_id)
    developer_view = render_hub_navigation(
        "开发工具",
        DEVELOPER_VIEWS,
        key=developer_key,
        default="资料检索",
    )
    if not project_name:
        st.info("开发工具需要先选择项目。")
        return
    retrieval_key = scoped_widget_key("retrieval_center_view", project_name, story_id)
    if developer_view == "资料检索":
        st.session_state[retrieval_key] = "查找资料"
        ui_modules["retrieval_center"].render_retrieval_center_page(project_name, story_id)
    elif developer_view == "质量评测":
        st.session_state[retrieval_key] = "质量评测"
        ui_modules["retrieval_center"].render_retrieval_center_page(project_name, story_id)
    else:
        st.session_state[retrieval_key] = "索引维护"
        ui_modules["retrieval_center"].render_retrieval_center_page(project_name, story_id)
