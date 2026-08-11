"""Session selection and infrequent session-management controls."""

from __future__ import annotations

import streamlit as st

from novelforge.services.memory import list_creative_sessions, update_creative_session
from ui.common import scoped_widget_key

from .shared import (
    SESSION_STATUS_LABELS,
    active_session_key,
    pending_active_session_key,
)


def render_session_toolbar(project_name: str, story_id: str) -> str:
    """Render a compact session picker and an optional management popover."""
    sessions = list_creative_sessions(
        project_name,
        story_id,
        include_archived=True,
    )
    session_map = {
        str(item.get("session_id") or ""): item
        for item in sessions
        if str(item.get("session_id") or "")
    }
    state_key = active_session_key(project_name, story_id)
    pending_session_id = str(
        st.session_state.pop(
            pending_active_session_key(project_name, story_id),
            "",
        )
        or ""
    )
    if pending_session_id in session_map:
        st.session_state[state_key] = pending_session_id
    current = str(st.session_state.get(state_key) or "")
    if current and current not in session_map:
        current = ""
        st.session_state[state_key] = ""
    elif state_key not in st.session_state:
        st.session_state[state_key] = current

    picker_col, management_col = st.columns(
        [5, 1],
        vertical_alignment="bottom",
    )
    options = [""] + list(session_map)
    selected = picker_col.selectbox(
        "创作记录",
        options=options,
        format_func=lambda value: (
            "新建创作"
            if not value
            else (
                f"{session_map[value].get('title') or '未命名创作'} · "
                f"{SESSION_STATUS_LABELS.get(str(session_map[value].get('status') or ''), '未知状态')}"
            )
        ),
        key=state_key,
    )

    if selected:
        _render_session_management(
            management_col,
            project_name,
            story_id,
            session_map[selected],
        )
    return selected


def _render_session_management(
    host,
    project_name: str,
    story_id: str,
    session: dict,
) -> None:
    session_id = str(session.get("session_id") or "")
    with host.popover("管理", width="stretch"):
        st.markdown("**会话管理**")
        title = st.text_input(
            "标题",
            value=str(session.get("title") or ""),
            key=scoped_widget_key(
                "creative_session_title",
                project_name,
                story_id,
                session_id,
            ),
        )
        goal = st.text_area(
            "创作目标",
            value=str(session.get("session_goal") or ""),
            height=90,
            key=scoped_widget_key(
                "creative_session_goal",
                project_name,
                story_id,
                session_id,
            ),
        )
        auto_extract = st.checkbox(
            "保留片段后自动整理可保存的新设定",
            value=str(session.get("auto_extract_mode") or "on_accept") == "on_accept",
            key=scoped_widget_key(
                "creative_auto_extract",
                project_name,
                story_id,
                session_id,
            ),
        )
        if st.button(
            "保存设置",
            key=scoped_widget_key(
                "creative_save_session",
                project_name,
                story_id,
                session_id,
            ),
            width="stretch",
            type="primary",
        ):
            update_creative_session(
                project_name,
                session_id,
                {
                    "title": title.strip(),
                    "session_goal": goal.strip(),
                    "auto_extract_mode": "on_accept" if auto_extract else "manual",
                },
                story_id=story_id,
            )
            st.success("会话设置已保存。")
            st.rerun()

        archived = str(session.get("status") or "") == "archived"
        if st.button(
            "恢复创作" if archived else "归档创作",
            key=scoped_widget_key(
                "creative_archive_session",
                project_name,
                story_id,
                session_id,
            ),
            width="stretch",
        ):
            update_creative_session(
                project_name,
                session_id,
                {"status": "active" if archived else "archived"},
                story_id=story_id,
            )
            st.rerun()


def session_generation_options(session: dict) -> dict:
    """Return persistence options without asking new users to configure them."""
    return {
        "target_chapter_no": int(session.get("target_chapter_no") or 0) or None,
        "auto_extract_mode": str(session.get("auto_extract_mode") or "on_accept"),
    }
