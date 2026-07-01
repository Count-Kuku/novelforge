"""Shared discussion rendering helpers for planning pages."""
from __future__ import annotations

import html
from collections.abc import Callable

import streamlit as st

from ui.step_views import render_step_validation
from ui.streaming import render_stream_preview

DISCUSSION_WORKSPACE_WIDTH = "stretch"

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


def _discussion_initial_user_message(messages: list[dict], fallback: str = "") -> str:
    for message in messages:
        if message.get("role") == "user":
            content = str(message.get("content") or "").strip()
            if content:
                return content
    return str(fallback or "").strip()


def _run_discussion_chat_stream(preview_container, user_message: str, label: str, func, *args, preview_language: str = "json", **kwargs):
    with preview_container.container():
        with st.chat_message("user"):
            st.markdown(user_message)
        with st.chat_message("assistant"):
            preview_slot = st.empty()
            render_stream_preview(preview_slot, "", preview_language)

    state = {"text": "", "last_render_len": 0}

    def stream_callback(delta: str):
        if not delta:
            return
        delta_text = str(delta)
        state["text"] += delta_text
        if preview_language == "json":
            text_len = len(state["text"])
            should_render = text_len - state["last_render_len"] >= 120 or any(char in delta_text for char in "\n,}]")
            if not should_render:
                return
            state["last_render_len"] = text_len
        render_stream_preview(preview_slot, state["text"], preview_language, cursor=True)

    try:
        result = func(*args, stream_callback=stream_callback, **kwargs)
        render_stream_preview(preview_slot, state["text"], preview_language)
        return result
    except Exception as exc:
        preview_slot.error(f"{label}失败：{exc}")
        raise

def _discussion_context_text(base_text: str, user_message: str, label: str = "讨论补充") -> str:
    base = str(base_text or "").strip()
    message = str(user_message or "").strip()
    if base and message and message not in base:
        return f"{base}\n\n{label}：{message}"
    return base or message

def _discussion_workspace_key(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in str(value or "discussion")).strip("-") or "discussion"


def _render_discussion_decision_hint(decisions: list[str], impact: str, *, note: str = "") -> None:
    cleaned_decisions = [str(item).strip() for item in decisions if str(item or "").strip()]
    cleaned_impact = str(impact or "").strip()
    cleaned_note = str(note or "").strip()
    if not cleaned_decisions and not cleaned_impact and not cleaned_note:
        return

    chips = "".join(
        f'<span class="nf-discussion-chip">{html.escape(item)}</span>'
        for item in cleaned_decisions
    )
    impact_html = (
        f'<div class="nf-discussion-impact"><span>保存后用于</span><b>{html.escape(cleaned_impact)}</b></div>'
        if cleaned_impact
        else ""
    )
    note_html = f'<div class="nf-discussion-note">{html.escape(cleaned_note)}</div>' if cleaned_note else ""
    st.markdown(
        f"""
        <div class="nf-discussion-brief">
            <div class="nf-discussion-brief-title">这次讨论会确定</div>
            {f'<div class="nf-discussion-chip-row">{chips}</div>' if chips else ''}
            {impact_html}
            {note_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_discussion_empty_hint(message: str) -> None:
    text = str(message or "").strip()
    if not text:
        return
    st.markdown(
        f'<div class="nf-discussion-empty-hint">{html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


def _render_discussion_workspace(workspace_key: str, render_input_panel: Callable[[object], None], render_output_panel: Callable[[], None]) -> None:
    safe_key = _discussion_workspace_key(workspace_key)
    with st.container(key=f"nf-discussion-shell-{safe_key}", width=DISCUSSION_WORKSPACE_WIDTH):
        with st.container(key=f"nf-discussion-input-{safe_key}", width="stretch"):
            stream_container = st.empty()
            render_input_panel(stream_container)
        with st.container(key=f"nf-discussion-output-{safe_key}", width="stretch"):
            render_output_panel()

def _render_discussion_chat(messages: list[dict], *, height: int | None = None):
    def render_messages() -> None:
        if not messages:
            st.caption("当前还没有讨论消息。")
            return
        for item in messages:
            role = "user" if item.get("role") == "user" else "assistant"
            with st.chat_message(role):
                st.markdown(str(item.get("content", "") or ""))

    if height and messages:
        with st.container(height=height, border=False):
            render_messages()
        return
    render_messages()

def _render_discussion_summary(discussion_result: dict, empty_message: str):
    discussion = discussion_result.get("data", {}).get("discussion", {}) if discussion_result else {}
    report_markdown = discussion_result.get("data", {}).get("report_markdown", "") if discussion_result else ""
    if not discussion:
        st.caption(empty_message)
        return
    st.markdown(report_markdown)
    render_step_validation(discussion_result)

def _render_approved_discussion_artifact(artifact: dict, empty_message: str):
    discussion = artifact.get("discussion", {}) if isinstance(artifact, dict) else {}
    report_markdown = artifact.get("report_markdown", "") if isinstance(artifact, dict) else ""
    if not discussion:
        st.caption(empty_message)
        return
    st.markdown(report_markdown or "已保存讨论结论，但缺少可读预览。")

def _format_discussion_artifact_as_guidance(artifact: dict) -> str:
    discussion = artifact.get("discussion", {}) if isinstance(artifact, dict) else {}
    if not discussion:
        return ""

    lines = ["来自已保存章节结论："]
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
