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
from ui.common import scoped_widget_key
from ui.discussion import (
    _append_discussion_message,
    _consume_discussion_input_clear,
    _discussion_input_clear_flag_key,
    _discussion_input_key,
    _discussion_messages_key,
    _discussion_result_key,
    _render_approved_discussion_artifact,
    _render_discussion_chat,
    _render_discussion_summary,
)
from ui.prompt_option_tools import _render_prompt_option_capability_tools
from ui.step_views import render_step_retrieval, render_step_validation
from ui.streaming import run_with_stream as _run_with_stream


def _prepare_outline_discussion_context(project_name: str, story_id: str) -> dict:
    messages_key = _discussion_messages_key("outline")
    result_key = _discussion_result_key("outline")
    input_key = _discussion_input_key("outline")
    clear_input_flag_key = _discussion_input_clear_flag_key("outline")
    _consume_discussion_input_clear("outline")
    return {
        "messages_key": messages_key,
        "result_key": result_key,
        "input_key": input_key,
        "clear_input_flag_key": clear_input_flag_key,
        "discussion_step": st.session_state.get(result_key, {}),
        "approved_artifact": load_outline_discussion_artifact(project_name, story_id=story_id),
    }


def _render_outline_discussion_actions(project_name: str, story_id: str, user_idea: str, discussion_context: dict) -> None:
    col_action_1, col_action_2 = st.columns(2)
    if col_action_1.button("开始讨论大纲方向"):
        try:
            result = _run_with_stream(
                "正在讨论大纲方向...",
                discuss_outline,
                project_name,
                user_idea,
                story_id=story_id,
                preview_language="json",
            )
            st.session_state[discussion_context["result_key"]] = result
            st.session_state[discussion_context["messages_key"]] = []
            assistant_message = result.get("data", {}).get("discussion", {}).get("current_understanding", "") or "我先整理了当前理解、可选方向和待确认问题，我们可以继续往下细化。"
            _append_discussion_message(discussion_context["messages_key"], "assistant", assistant_message)
            st.rerun()
        except Exception as exc:
            st.error(f"讨论失败：{exc}")

    if col_action_2.button("重置讨论"):
        st.session_state[discussion_context["result_key"]] = {}
        st.session_state[discussion_context["messages_key"]] = []
        st.session_state[discussion_context["clear_input_flag_key"]] = True
        st.rerun()


def _render_outline_discussion_summary_panel(project_name: str, story_id: str, discussion_context: dict, render_discussion_asset_candidates) -> None:
    discussion_step = discussion_context["discussion_step"]
    st.markdown("### 当前讨论结论")
    _render_discussion_summary(discussion_step, "开始讨论后，这里会持续显示当前收敛出的结论。")
    render_step_retrieval(discussion_step, "本次大纲讨论参考的检索上下文")
    render_discussion_asset_candidates(
        project_name,
        story_id,
        discussion_step,
        "outline",
        f"outline:{project_name}:{story_id}",
        scoped_widget_key("outline_discussion_prompt_options", project_name, story_id),
    )
    approve_col, clear_col = st.columns(2)
    if approve_col.button("批准当前讨论", key="approve_outline_discussion"):
        try:
            result = approve_outline_discussion(project_name, discussion_step, story_id=story_id)
            st.success(f"已保存全书讨论工件：{result.get('saved_path', '')}")
            st.rerun()
        except Exception as exc:
            st.error(f"批准失败：{exc}")
    if clear_col.button("清除已批准版本", key="clear_outline_discussion"):
        if clear_outline_discussion_approval(project_name, story_id=story_id):
            st.success("已清除全书已批准讨论工件。")
            st.rerun()
        else:
            st.warning("当前没有可清除的已批准讨论工件。")
    st.markdown("### 已批准讨论版本")
    _render_approved_discussion_artifact(discussion_context["approved_artifact"], "当前全书还没有已批准讨论工件。")


def _render_outline_discussion_chat_panel(project_name: str, story_id: str, user_idea: str, discussion_context: dict) -> None:
    messages_key = discussion_context["messages_key"]
    st.markdown("### 讨论对话")
    messages = st.session_state.get(messages_key, [])
    _render_discussion_chat(messages)
    follow_up = st.text_area("继续讨论", key=discussion_context["input_key"], height=120, placeholder="例如：我更想突出成长线，但不要太早进入主线冲突。")
    if st.button("发送讨论消息", key="send_outline_discussion"):
        if not follow_up.strip():
            st.warning("讨论消息不能为空。")
        elif not user_idea.strip():
            st.warning("请先填写你的小说想法。")
        else:
            try:
                _append_discussion_message(messages_key, "user", follow_up)
                messages = st.session_state.get(messages_key, [])
                result = _run_with_stream(
                    "正在继续讨论大纲...",
                    discuss_outline_turn,
                    project_name,
                    user_idea,
                    messages,
                    discussion_context["discussion_step"].get("data", {}).get("discussion", {}),
                    follow_up,
                    story_id=story_id,
                    preview_language="json",
                )
                st.session_state[discussion_context["result_key"]] = result
                assistant_message = result.get("data", {}).get("assistant_message", "") or "我已经根据你的补充更新了当前讨论结论。"
                _append_discussion_message(messages_key, "assistant", assistant_message)
                st.session_state[discussion_context["clear_input_flag_key"]] = True
                st.rerun()
            except Exception as exc:
                st.error(f"继续讨论失败：{exc}")


def _render_outline_discussion_area(project_name: str, story_id: str, user_idea: str, discussion_context: dict, render_discussion_asset_candidates) -> None:
    _render_outline_discussion_actions(project_name, story_id, user_idea, discussion_context)
    summary_col, chat_col = st.columns([1, 1])
    with summary_col:
        _render_outline_discussion_summary_panel(project_name, story_id, discussion_context, render_discussion_asset_candidates)
    with chat_col:
        _render_outline_discussion_chat_panel(project_name, story_id, user_idea, discussion_context)


def _render_outline_prompt_options(project_name: str, story_id: str) -> None:
    with st.expander("高级：全书大纲提示词选项", expanded=False):
        _render_prompt_option_capability_tools(
            project_name,
            story_id,
            "outline",
            scoped_widget_key("outline_prompt_options", project_name, story_id),
        )


def _render_outline_generation(project_name: str, story_id: str, user_idea: str) -> dict:
    step_result = st.session_state.get("outline_step", {})
    if st.button("生成全书大纲"):
        result = _run_with_stream(
            "正在生成全书大纲...",
            generate_outline,
            project_name,
            user_idea,
            story_id=story_id,
        )
        st.session_state["outline_step"] = result
        st.session_state["outline"] = result.get("data", {}).get("outline", "")
        step_result = result
    return step_result


def _render_outline_editor(project_name: str, story_id: str, existing_outline: str) -> None:
    outline_text = st.text_area(
        "大纲内容",
        value=st.session_state.get("outline", existing_outline),
        height=500
    )

    if st.button("保存大纲"):
        save_outline(project_name, outline_text, story_id=story_id)
        st.success("大纲已保存")


def render_outline_page(project_name: str, *, render_discussion_asset_candidates):
    story_id = st.session_state.get("active_story_id", "default")
    st.subheader("全书大纲")

    existing_outline = load_outline(project_name, story_id=story_id)
    user_idea = st.text_area("你的小说想法", height=200)
    discussion_context = _prepare_outline_discussion_context(project_name, story_id)
    _render_outline_discussion_area(project_name, story_id, user_idea, discussion_context, render_discussion_asset_candidates)
    _render_outline_prompt_options(project_name, story_id)
    step_result = _render_outline_generation(project_name, story_id, user_idea)
    _render_outline_editor(project_name, story_id, existing_outline)
    render_step_validation(step_result)
    render_step_retrieval(step_result, "本次大纲生成使用的检索上下文", get_retrieval_trace(f"outline:{project_name}:{story_id}"))

