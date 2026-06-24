"""Shared discussion rendering helpers for planning pages."""
from __future__ import annotations

import streamlit as st

from ui.step_views import render_step_json_expander, render_step_validation

def _discussion_messages_key(kind: str, suffix: str = "") -> str:
    return f"discussion_messages:{kind}:{suffix}" if suffix else f"discussion_messages:{kind}"

def _discussion_result_key(kind: str, suffix: str = "") -> str:
    return f"discussion_result:{kind}:{suffix}" if suffix else f"discussion_result:{kind}"

def _discussion_input_key(kind: str, suffix: str = "") -> str:
    return f"discussion_input:{kind}:{suffix}" if suffix else f"discussion_input:{kind}"

def _discussion_input_clear_flag_key(kind: str, suffix: str = "") -> str:
    return f"discussion_input_clear:{kind}:{suffix}" if suffix else f"discussion_input_clear:{kind}"

def _consume_discussion_input_clear(kind: str, suffix: str = ""):
    flag_key = _discussion_input_clear_flag_key(kind, suffix)
    if st.session_state.pop(flag_key, False):
        st.session_state[_discussion_input_key(kind, suffix)] = ""

def _append_discussion_message(key: str, role: str, content: str):
    content = str(content or "").strip()
    if not content:
        return
    messages = list(st.session_state.get(key, []))
    messages.append({"role": role, "content": content})
    st.session_state[key] = messages

def _render_discussion_chat(messages: list[dict]):
    if not messages:
        st.caption("当前还没有讨论消息。")
        return
    for item in messages:
        role = "user" if item.get("role") == "user" else "assistant"
        with st.chat_message(role):
            st.markdown(str(item.get("content", "") or ""))

def _render_discussion_summary(discussion_result: dict, empty_message: str):
    discussion = discussion_result.get("data", {}).get("discussion", {}) if discussion_result else {}
    report_markdown = discussion_result.get("data", {}).get("report_markdown", "") if discussion_result else ""
    if not discussion:
        st.caption(empty_message)
        return
    st.markdown(report_markdown)
    render_step_validation(discussion_result)
    render_step_json_expander("讨论结构化数据", discussion)

def _render_approved_discussion_artifact(artifact: dict, empty_message: str):
    discussion = artifact.get("discussion", {}) if isinstance(artifact, dict) else {}
    report_markdown = artifact.get("report_markdown", "") if isinstance(artifact, dict) else ""
    if not discussion:
        st.caption(empty_message)
        return
    st.markdown(report_markdown or "已存在批准后的讨论工件，但缺少可读预览。")
    render_step_json_expander("已批准讨论数据", discussion)

def _format_discussion_artifact_as_guidance(artifact: dict) -> str:
    discussion = artifact.get("discussion", {}) if isinstance(artifact, dict) else {}
    if not discussion:
        return ""

    lines = ["来自已批准章节讨论："]
    field_specs = [
        ("current_understanding", "当前理解"),
        ("recommended_direction", "推荐方向"),
    ]
    for field, label in field_specs:
        value = str(discussion.get(field, "") or "").strip()
        if value:
            lines.append(f"- {label}：{value}")

    list_field_specs = [
        ("key_constraints", "关键约束"),
        ("risks", "风险提醒"),
        ("open_questions", "待确认问题"),
    ]
    for field, label in list_field_specs:
        values = discussion.get(field, [])
        if isinstance(values, list):
            cleaned_values = [str(item).strip() for item in values if str(item).strip()]
        else:
            cleaned_values = [str(values).strip()] if str(values or "").strip() else []
        if cleaned_values:
            lines.append(f"- {label}：{'；'.join(cleaned_values)}")

    if len(lines) == 1:
        return ""
    return "\n".join(lines)

