"""创作 Hub：创作方向、小说规划、章节写作和自由模式。"""
from __future__ import annotations

import streamlit as st

from ui.common import render_hub_navigation, render_next_step_action, scoped_widget_key
from ui.layout import render_section_heading


CREATION_VIEWS = ["创作方向", "小说规划", "章节写作", "自由模式"]
PLANNING_VIEWS = ["全书", "分卷", "剧情段", "章节细纲"]


def _render_next_step(view: str, planning_view: str | None = None) -> None:
    targets = {
        "创作方向": ("下一步：进入小说规划", "创作", "小说规划", "全书", "保存创作方向后，从全书大纲开始规划。"),
        "全书": ("下一步：进入分卷规划", "创作", "小说规划", "分卷", "全书主线稳定后继续拆分分卷。"),
        "分卷": ("下一步：进入剧情段规划", "创作", "小说规划", "剧情段", "分卷定位稳定后继续安排剧情段。"),
        "剧情段": ("下一步：进入章节细纲", "创作", "小说规划", "章节细纲", "剧情段确定后，为具体章节准备细纲。"),
        "章节细纲": ("下一步：进入章节写作", "创作", "章节写作", "章节需求", "细纲完成后即可进入正文和审阅流程。"),
    }
    target = targets.get(planning_view if view == "小说规划" else view)
    if not target:
        return
    label, page, target_view, subview, help_text = target
    render_next_step_action(label, page, view=target_view, subview=subview, help_text=help_text, key_suffix=view)


def _render_planning(project_name: str, ui_modules: dict[str, object], story_id: str) -> None:
    planning_key = scoped_widget_key("creation_planning_view", project_name, story_id)
    planning_view = render_hub_navigation("小说规划阶段", PLANNING_VIEWS, key=planning_key, default="全书")
    render_kwargs = {
        "render_discussion_asset_candidates": ui_modules["discussion_assets"].render_discussion_asset_candidates,
    }
    if planning_view == "全书":
        ui_modules["outline"].render_outline_page(project_name, **render_kwargs)
    elif planning_view == "分卷":
        ui_modules["volume_outline"].render_volume_outline_page(project_name, **render_kwargs)
    elif planning_view == "剧情段":
        ui_modules["arc_outline"].render_arc_outline_page(project_name, **render_kwargs)
    else:
        ui_modules["chapter_outline"].render_chapter_outline_page(project_name, **render_kwargs)


def render_creation_hub(project_name: str, ui_modules: dict[str, object]) -> None:
    story_id = str(st.session_state.get("active_story_id") or "default")
    view_key = scoped_widget_key("creation_hub_view", project_name, story_id)
    view = render_hub_navigation("创作工作区", CREATION_VIEWS, key=view_key, default="章节写作")
    if view == "创作方向":
        ui_modules["creative_profile"].render_creative_profile_page(
            project_name,
            render_discussion_asset_candidates=ui_modules["discussion_assets"].render_discussion_asset_candidates,
        )
        _render_next_step(view)
        return
    if view == "小说规划":
        _render_planning(project_name, ui_modules, story_id)
        planning_view = st.session_state.get(scoped_widget_key("creation_planning_view", project_name, story_id), "全书")
        _render_next_step(view, planning_view)
        return
    if view == "自由模式":
        ui_modules["free_writing"].render_dynamic_generation_page(
            project_name,
            ui_modules["prompt_option_tools"]._render_prompt_option_capability_tools,
        )
        return

    render_section_heading("章节写作", "先准备细纲，再写正文，最后保存并选择快速或综合审阅。")
    ui_modules["chapter"].render_chapter_page(project_name)
