"""Context summary shown after a free-writing generation."""

from __future__ import annotations

import json

import streamlit as st

from ui.common import developer_mode_enabled
from ui.prompt_option_tools import render_context_assembly_summary

from .shared import last_result_key


def render_last_context(project_name: str, story_id: str, session_id: str) -> None:
    if not session_id:
        return
    result = st.session_state.get(
        last_result_key(project_name, story_id, session_id),
        {},
    )
    if not result:
        return
    for warning in result.get("warnings", []):
        st.warning(warning)
    render_context_assembly_summary(
        result.get("context_assembly", {}),
        "上一轮使用了哪些资料",
    )
    if developer_mode_enabled():
        with st.expander("技术信息（排查问题时使用）", expanded=False):
            st.code(json.dumps(result, ensure_ascii=False, indent=2), language="json")
