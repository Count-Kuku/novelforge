"""Whole-book outline page."""
from __future__ import annotations

import streamlit as st

from memory import load_outline, load_outline_discussion_artifact, save_outline
from skills import (
    approve_outline_discussion,
    clear_outline_discussion_approval,
    discuss_outline,
    discuss_outline_turn,
    generate_outline,
    get_retrieval_trace,
)
from ui.common import scoped_session_key, scoped_widget_key
from ui.discussion import (
    _append_discussion_message,
    _consume_discussion_input_clear,
    _discussion_initial_user_message,
    _discussion_input_clear_flag_key,
    _discussion_input_key,
    _discussion_messages_key,
    _discussion_result_key,
    _render_approved_discussion_artifact,
    _render_discussion_chat,
    _render_discussion_decision_hint,
    _render_discussion_empty_hint,
    _render_discussion_summary,
    _render_discussion_workspace,
    _run_discussion_chat_stream,
)
from ui.layout import render_section_heading
from ui.prompt_option_tools import _render_prompt_option_capability_tools
from ui.step_views import render_step_retrieval, render_step_validation
from ui.streaming import run_with_stream as _run_with_stream


def _prepare_outline_discussion_context(project_name: str, story_id: str) -> dict:
    suffix = f"{project_name}:{story_id}"
    messages_key = _discussion_messages_key("outline", suffix)
    result_key = _discussion_result_key("outline", suffix)
    input_key = _discussion_input_key("outline", suffix)
    clear_input_flag_key = _discussion_input_clear_flag_key("outline", suffix)
    _consume_discussion_input_clear("outline", suffix)
    return {
        "suffix": suffix,
        "messages_key": messages_key,
        "result_key": result_key,
        "input_key": input_key,
        "clear_input_flag_key": clear_input_flag_key,
        "discussion_step": st.session_state.get(result_key, {}),
        "approved_artifact": load_outline_discussion_artifact(project_name, story_id=story_id),
    }


def _render_outline_discussion_summary_panel(project_name: str, story_id: str, discussion_context: dict, render_discussion_asset_candidates) -> None:
    discussion_step = discussion_context["discussion_step"]
    st.markdown("##### 全书方向结论")
    _render_discussion_summary(discussion_step, "开始讨论后，这里显示主线、主题和整体结构建议。")
    render_step_retrieval(discussion_step, "本次大纲讨论参考的资料")
    render_discussion_asset_candidates(
        project_name,
        story_id,
        discussion_step,
        "outline",
        f"outline:{project_name}:{story_id}",
        scoped_widget_key("outline_discussion_prompt_options", project_name, story_id),
    )
    approve_col, clear_col = st.columns(2)
    if approve_col.button("保存全书结论", key=scoped_widget_key("approve_outline_discussion", project_name, story_id), use_container_width=True):
        try:
            result = approve_outline_discussion(project_name, discussion_step, story_id=story_id)
            st.success("已保存全书讨论结论。")
            st.rerun()
        except Exception as exc:
            st.error(f"保存失败：{exc}")
    if clear_col.button("清除全书结论", key=scoped_widget_key("clear_outline_discussion", project_name, story_id), use_container_width=True):
        if clear_outline_discussion_approval(project_name, story_id=story_id):
            st.success("已清除全书讨论结论。")
            st.rerun()
        else:
            st.warning("当前没有可清除的全书结论。")
    st.markdown("##### 已保存全书结论")
    _render_approved_discussion_artifact(discussion_context["approved_artifact"], "当前全书还没有保存讨论结论。")


def _render_outline_discussion_area(project_name: str, story_id: str, user_idea: str, discussion_context: dict, render_discussion_asset_candidates) -> None:
    def render_input_panel(_stream_container) -> None:
        messages_key = discussion_context["messages_key"]
        input_key = discussion_context["input_key"]
        current_messages = st.session_state.get(messages_key, [])
        if not current_messages and user_idea.strip() and input_key not in st.session_state:
            st.session_state[input_key] = user_idea.strip()

        st.markdown("##### 讨论全书方向")
        _render_discussion_decision_hint(
            ["主线", "主题", "整体结构", "避雷点"],
            "全书大纲、分卷规划和剧情段规划",
            note="会自动带入上方小说想法。",
        )
        if current_messages:
            _render_discussion_chat(current_messages, height=260)
        else:
            _render_discussion_empty_hint("说说全书方向，也可以直接补充上方想法。")
        live_turn_container = st.empty()
        user_input = st.text_area(
            "大纲讨论输入",
            key=input_key,
            height=120,
            placeholder="例如：我更想突出成长线，但不要太早进入主线冲突。",
            label_visibility="collapsed",
        )
        has_started = bool(st.session_state.get(discussion_context["result_key"]) or current_messages)
        send_label = "发送" if has_started else "开始讨论"
        send_col, reset_col = st.columns([3, 1])
        if send_col.button(send_label, key=scoped_widget_key("send_outline_discussion", project_name, story_id), use_container_width=True):
            submitted = str(user_input or "").strip()
            if not submitted:
                st.warning("讨论消息不能为空。")
            else:
                try:
                    existing_messages = list(st.session_state.get(messages_key, []))
                    _append_discussion_message(messages_key, "user", submitted)
                    updated_messages = st.session_state.get(messages_key, [])
                    if has_started:
                        seed_idea = _discussion_initial_user_message(existing_messages, user_idea or submitted)
                        result = _run_discussion_chat_stream(
                            live_turn_container,
                            submitted,
                            "继续讨论大纲",
                            discuss_outline_turn,
                            project_name,
                            seed_idea,
                            updated_messages,
                            st.session_state.get(discussion_context["result_key"], {}).get("data", {}).get("discussion", {}),
                            submitted,
                            story_id=story_id,
                        )
                        assistant_message = result.get("data", {}).get("assistant_message", "") or "我已经根据你的补充更新了全书方向结论。"
                    else:
                        seed_idea = submitted or user_idea
                        result = _run_discussion_chat_stream(
                            live_turn_container,
                            submitted,
                            "讨论大纲方向",
                            discuss_outline,
                            project_name,
                            seed_idea,
                            story_id=story_id,
                        )
                        assistant_message = result.get("data", {}).get("discussion", {}).get("current_understanding", "") or "我先整理了当前理解、可选方向和待确认问题，我们可以继续往下细化。"
                    st.session_state[discussion_context["result_key"]] = result
                    _append_discussion_message(messages_key, "assistant", assistant_message)
                    st.session_state[discussion_context["clear_input_flag_key"]] = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"讨论失败：{exc}")
        if reset_col.button("重置讨论", key=scoped_widget_key("reset_outline_discussion", project_name, story_id), use_container_width=True):
            st.session_state[discussion_context["result_key"]] = {}
            st.session_state[messages_key] = []
            st.session_state[discussion_context["clear_input_flag_key"]] = True
            st.rerun()

    def render_output_panel() -> None:
        _render_outline_discussion_summary_panel(project_name, story_id, discussion_context, render_discussion_asset_candidates)

    _render_discussion_workspace(f"outline:{project_name}:{story_id}", render_input_panel, render_output_panel)

def _render_outline_prompt_options(project_name: str, story_id: str) -> None:
    with st.expander("高级：全书大纲提示词选项", expanded=False):
        _render_prompt_option_capability_tools(
            project_name,
            story_id,
            "outline",
            scoped_widget_key("outline_prompt_options", project_name, story_id),
        )


def _render_outline_generation(project_name: str, story_id: str, user_idea: str) -> dict:
    step_key = scoped_session_key("outline_step", project_name, story_id)
    outline_key = scoped_session_key("outline", project_name, story_id)
    step_result = st.session_state.get(step_key, {})
    if st.button("生成全书大纲", key=scoped_widget_key("generate_outline", project_name, story_id), type="primary", use_container_width=True):
        result = _run_with_stream(
            "正在生成全书大纲...",
            generate_outline,
            project_name,
            user_idea,
            story_id=story_id,
        )
        st.session_state[step_key] = result
        st.session_state[outline_key] = result.get("data", {}).get("outline", "")
        step_result = result
    return step_result


def _render_outline_editor(project_name: str, story_id: str, existing_outline: str) -> None:
    outline_key = scoped_session_key("outline", project_name, story_id)
    if outline_key not in st.session_state:
        st.session_state[outline_key] = existing_outline
    outline_text = st.text_area(
        "大纲内容",
        key=outline_key,
        height=500,
    )

    if st.button("保存大纲", key=scoped_widget_key("save_outline", project_name, story_id), use_container_width=True):
        save_outline(project_name, outline_text, story_id=story_id)
        st.success("大纲已保存")


def render_outline_page(project_name: str, *, render_discussion_asset_candidates):
    story_id = st.session_state.get("active_story_id", "default")

    existing_outline = load_outline(project_name, story_id=story_id)
    render_section_heading("小说想法", "先把作品方向放在这里，后续讨论和正式大纲都会围绕这段输入。")
    with st.container(border=True):
        user_idea = st.text_area("你的小说想法", key=scoped_widget_key("outline_user_idea", project_name, story_id), height=200)
    discussion_context = _prepare_outline_discussion_context(project_name, story_id)
    render_section_heading("讨论全书方向", "先定主线、主题和整体结构，再保存为后续规划依据。")
    _render_outline_discussion_area(project_name, story_id, user_idea, discussion_context, render_discussion_asset_candidates)
    _render_outline_prompt_options(project_name, story_id)
    render_section_heading("生成与编辑", "正式生成会写入下方编辑区，你仍可以手动修改后再保存。")
    step_result = _render_outline_generation(project_name, story_id, user_idea)
    _render_outline_editor(project_name, story_id, existing_outline)
    render_step_validation(step_result)
    render_step_retrieval(step_result, "本次大纲生成参考的资料", get_retrieval_trace(f"outline:{project_name}:{story_id}"))
