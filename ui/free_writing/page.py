"""Orchestration for the simplified free-writing page."""

from __future__ import annotations

import streamlit as st

from novelforge.services.memory import (
    load_creative_profile,
    load_creative_session_bundle,
)
from ui.layout import render_section_heading

from .chapter_panel import render_chapter_panel
from .actions import render_creative_action_history
from .composer import render_composer
from .context_panel import render_last_context
from .fragments import render_fragment_actions, render_fragment_history
from .knowledge_panel import render_knowledge_panel
from .session_controls import render_session_toolbar, session_generation_options


def render_dynamic_generation_page(
    project_name: str,
    render_prompt_option_capability_tools,
) -> None:
    story_id = str(st.session_state.get("active_story_id") or "default")
    profile = load_creative_profile(project_name, story_id=story_id) or {}
    session_id = render_session_toolbar(project_name, story_id)
    bundle = (
        load_creative_session_bundle(project_name, session_id, story_id=story_id)
        if session_id
        else None
    )
    session = dict((bundle or {}).get("session") or {})
    session_options = session_generation_options(session)

    if bundle:
        render_section_heading(
            "创作内容",
            "当前采用的内容会沿着这里继续；其他版本仍会保留在折叠区域中。",
        )
        render_fragment_history(project_name, story_id, bundle)
        render_fragment_actions(project_name, story_id, bundle)
        render_creative_action_history(project_name, story_id, session_id)
        render_section_heading(
            "继续创作",
            "只写下一段要发生什么；角色卡、世界观和正式知识会自动匹配。",
        )

    render_composer(
        project_name,
        story_id,
        profile,
        session_id,
        bundle or {},
        session_options,
        render_prompt_option_capability_tools,
    )

    if bundle:
        render_knowledge_panel(project_name, story_id, bundle)
        render_chapter_panel(project_name, story_id, bundle)
        render_last_context(project_name, story_id, session_id)
