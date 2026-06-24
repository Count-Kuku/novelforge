"""Volume outline page."""
from __future__ import annotations

import streamlit as st

from memory import (
    delete_volume,
    list_volumes,
    load_volume_discussion_artifact,
    load_volume_metadata,
    load_volume_outline,
    save_volume_metadata,
    save_volume_outline,
)
from skills import (
    approve_volume_discussion,
    clear_volume_discussion_approval,
    discuss_volume,
    discuss_volume_turn,
    generate_volume_outline,
    get_retrieval_trace,
)
from ui.common import confirmed_button, scoped_session_key, scoped_widget_key
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
from ui.labels import label_status
from ui.prompt_option_tools import _render_prompt_option_capability_tools
from ui.step_views import render_step_retrieval, render_step_validation
from ui.streaming import run_with_stream as _run_with_stream


VOLUME_STATUS_OPTIONS = ["draft", "approved", "archived"]


def _status_index(status: str) -> int:
    return VOLUME_STATUS_OPTIONS.index(status) if status in VOLUME_STATUS_OPTIONS else 0


def _prepare_volume_outline_context(project_name: str, story_id: str) -> dict:
    volume_no = st.number_input("分卷编号", min_value=1, value=1, key=scoped_widget_key("volume_outline_no", project_name, story_id))
    volume_no = int(volume_no)
    volume_scope = (project_name, story_id, volume_no)
    metadata = load_volume_metadata(project_name, volume_no, story_id=story_id)
    return {
        "volume_no": volume_no,
        "volume_scope": volume_scope,
        "step_key": scoped_session_key("volume_outline_step", *volume_scope),
        "text_key": scoped_session_key("volume_outline", *volume_scope),
        "editor_key": scoped_widget_key("volume_outline_editor", *volume_scope),
        "metadata": metadata,
        "existing_outline": load_volume_outline(project_name, volume_no, story_id=story_id),
    }


def _render_volume_metadata_fields(context: dict) -> tuple[str, str, str, str]:
    metadata = context["metadata"]
    volume_scope = context["volume_scope"]
    title = st.text_input("分卷标题", value=metadata.get("title", ""), key=scoped_widget_key("volume_title", *volume_scope))
    summary = st.text_area("分卷摘要", value=metadata.get("summary", ""), height=120, key=scoped_widget_key("volume_summary", *volume_scope))
    status = st.selectbox(
        "分卷状态",
        options=VOLUME_STATUS_OPTIONS,
        index=_status_index(metadata.get("status", "draft")),
        format_func=label_status,
        key=scoped_widget_key("volume_status", *volume_scope),
    )
    requirement = st.text_area("本卷要求", height=180, key=scoped_widget_key("volume_requirement", *volume_scope))
    return title, summary, status, requirement


def _prepare_volume_discussion_context(project_name: str, story_id: str, volume_no: int) -> dict:
    suffix = f"{project_name}:{story_id}:{volume_no}"
    messages_key = _discussion_messages_key("volume", suffix)
    result_key = _discussion_result_key("volume", suffix)
    input_key = _discussion_input_key("volume", suffix)
    clear_input_flag_key = _discussion_input_clear_flag_key("volume", suffix)
    _consume_discussion_input_clear("volume", suffix)
    return {
        "messages_key": messages_key,
        "result_key": result_key,
        "input_key": input_key,
        "clear_input_flag_key": clear_input_flag_key,
        "discussion_step": st.session_state.get(result_key, {}),
        "approved_artifact": load_volume_discussion_artifact(project_name, volume_no, story_id=story_id),
    }


def _render_volume_discussion_actions(
    project_name: str,
    story_id: str,
    context: dict,
    discussion_context: dict,
    title: str,
    summary: str,
    requirement: str,
) -> None:
    volume_no = context["volume_no"]
    volume_scope = context["volume_scope"]
    col_action_1, col_action_2 = st.columns(2)
    if col_action_1.button("开始讨论分卷方向", key=scoped_widget_key("start_volume_discussion", *volume_scope)):
        try:
            result = _run_with_stream(
                "正在讨论分卷方向...",
                discuss_volume,
                project_name,
                volume_no,
                title,
                summary,
                requirement,
                story_id=story_id,
                preview_language="json",
            )
            st.session_state[discussion_context["result_key"]] = result
            st.session_state[discussion_context["messages_key"]] = []
            assistant_message = result.get("data", {}).get("discussion", {}).get("current_understanding", "") or "我先整理了本卷的定位、可选结构和待确认问题，我们可以继续细化。"
            _append_discussion_message(discussion_context["messages_key"], "assistant", assistant_message)
            st.rerun()
        except Exception as exc:
            st.error(f"讨论失败：{exc}")

    if col_action_2.button("重置分卷讨论", key=scoped_widget_key("reset_volume_discussion", *volume_scope)):
        st.session_state[discussion_context["result_key"]] = {}
        st.session_state[discussion_context["messages_key"]] = []
        st.session_state[discussion_context["clear_input_flag_key"]] = True
        st.rerun()


def _render_volume_discussion_summary_panel(
    project_name: str,
    story_id: str,
    context: dict,
    discussion_context: dict,
    render_discussion_asset_candidates,
) -> None:
    volume_no = context["volume_no"]
    volume_scope = context["volume_scope"]
    discussion_step = discussion_context["discussion_step"]
    st.markdown("### 当前讨论结论")
    _render_discussion_summary(discussion_step, "开始讨论后，这里会持续显示当前分卷方向的结论。")
    render_step_retrieval(discussion_step, "本次分卷讨论参考的检索上下文")
    render_discussion_asset_candidates(
        project_name,
        story_id,
        discussion_step,
        "volume",
        f"volume:{project_name}:{story_id}:{volume_no}",
        scoped_widget_key("volume_discussion_prompt_options", *volume_scope),
    )
    approve_col, clear_col = st.columns(2)
    if approve_col.button("批准当前讨论", key=scoped_widget_key("approve_volume_discussion", *volume_scope)):
        try:
            result = approve_volume_discussion(project_name, volume_no, discussion_step, story_id=story_id)
            st.success(f"已保存分卷讨论工件：{result.get('saved_path', '')}")
            st.rerun()
        except Exception as exc:
            st.error(f"批准失败：{exc}")
    if clear_col.button("清除已批准版本", key=scoped_widget_key("clear_volume_discussion", *volume_scope)):
        if clear_volume_discussion_approval(project_name, volume_no, story_id=story_id):
            st.success("已清除分卷已批准讨论工件。")
            st.rerun()
        else:
            st.warning("当前没有可清除的已批准讨论工件。")
    st.markdown("### 已批准讨论版本")
    _render_approved_discussion_artifact(discussion_context["approved_artifact"], "当前分卷还没有已批准讨论工件。")


def _render_volume_discussion_chat_panel(
    project_name: str,
    story_id: str,
    context: dict,
    discussion_context: dict,
    title: str,
    summary: str,
    requirement: str,
) -> None:
    volume_no = context["volume_no"]
    volume_scope = context["volume_scope"]
    messages_key = discussion_context["messages_key"]
    st.markdown("### 讨论对话")
    messages = st.session_state.get(messages_key, [])
    _render_discussion_chat(messages)
    follow_up = st.text_area(
        "继续讨论分卷",
        key=discussion_context["input_key"],
        height=120,
        placeholder="例如：这一卷我想更偏升级与站稳脚跟，不要太早引爆终局矛盾。",
    )
    if st.button("发送分卷讨论消息", key=scoped_widget_key("send_volume_discussion", *volume_scope)):
        if not follow_up.strip():
            st.warning("讨论消息不能为空。")
        else:
            try:
                _append_discussion_message(messages_key, "user", follow_up)
                messages = st.session_state.get(messages_key, [])
                result = _run_with_stream(
                    "正在继续讨论分卷...",
                    discuss_volume_turn,
                    project_name,
                    volume_no,
                    title,
                    summary,
                    requirement,
                    messages,
                    discussion_context["discussion_step"].get("data", {}).get("discussion", {}),
                    follow_up,
                    story_id=story_id,
                    preview_language="json",
                )
                st.session_state[discussion_context["result_key"]] = result
                assistant_message = result.get("data", {}).get("assistant_message", "") or "我已经根据你的补充更新了本卷讨论结论。"
                _append_discussion_message(messages_key, "assistant", assistant_message)
                st.session_state[discussion_context["clear_input_flag_key"]] = True
                st.rerun()
            except Exception as exc:
                st.error(f"继续讨论失败：{exc}")


def _render_volume_discussion_area(
    project_name: str,
    story_id: str,
    context: dict,
    discussion_context: dict,
    title: str,
    summary: str,
    requirement: str,
    render_discussion_asset_candidates,
) -> None:
    _render_volume_discussion_actions(project_name, story_id, context, discussion_context, title, summary, requirement)
    summary_col, chat_col = st.columns([1, 1])
    with summary_col:
        _render_volume_discussion_summary_panel(
            project_name, story_id, context, discussion_context, render_discussion_asset_candidates
        )
    with chat_col:
        _render_volume_discussion_chat_panel(project_name, story_id, context, discussion_context, title, summary, requirement)


def _render_volume_prompt_options(project_name: str, story_id: str, context: dict) -> None:
    with st.expander("高级：分卷大纲提示词选项", expanded=False):
        _render_prompt_option_capability_tools(
            project_name,
            story_id,
            "outline",
            scoped_widget_key("volume_outline_prompt_options", *context["volume_scope"]),
        )


def _render_volume_generation(
    project_name: str,
    story_id: str,
    context: dict,
    title: str,
    summary: str,
    requirement: str,
    status: str,
) -> dict:
    step_result = st.session_state.get(context["step_key"], {})
    if st.button("生成分卷大纲", key=scoped_widget_key("generate_volume_outline", *context["volume_scope"])):
        try:
            result = _run_with_stream(
                "正在生成分卷大纲...",
                generate_volume_outline,
                project_name,
                context["volume_no"],
                title,
                summary,
                requirement,
                status=status,
                story_id=story_id,
            )
            outline_value = result.get("data", {}).get("volume_outline", "")
            st.session_state[context["step_key"]] = result
            st.session_state[context["text_key"]] = outline_value
            st.session_state[context["editor_key"]] = outline_value
            st.rerun()
        except Exception as exc:
            st.error(f"生成分卷大纲失败：{exc}")
    return step_result


def _render_volume_editor_and_actions(
    project_name: str,
    story_id: str,
    context: dict,
    title: str,
    summary: str,
    status: str,
) -> None:
    outline_text = st.text_area(
        "分卷大纲内容",
        value=st.session_state.get(context["text_key"], context["existing_outline"]),
        height=500,
        key=context["editor_key"],
    )

    col1, col2 = st.columns(2)
    if col1.button("保存分卷大纲", key=scoped_widget_key("save_volume", *context["volume_scope"])):
        save_volume_outline(project_name, context["volume_no"], outline_text, story_id=story_id)
        save_volume_metadata(
            project_name,
            context["volume_no"],
            {"title": title, "summary": summary, "status": status},
            story_id=story_id,
        )
        st.success(f"第 {context['volume_no']} 卷大纲已保存")
        st.rerun()
    if confirmed_button(
        col2,
        "删除分卷",
        f"确认删除第 {context['volume_no']} 卷",
        scoped_widget_key("delete_volume", project_name, story_id, context["volume_no"]),
    ):
        if delete_volume(project_name, context["volume_no"], story_id=story_id):
            st.success(f"第 {context['volume_no']} 卷已删除")
            st.rerun()
        else:
            st.warning("目标分卷不存在。")


def _render_existing_volumes(project_name: str, story_id: str) -> None:
    volumes = list_volumes(project_name, story_id=story_id)
    if not volumes:
        return
    st.markdown("### 现有分卷")
    for item in volumes:
        approval_label = "已有批准讨论" if item.get("has_approved_discussion") else "暂无批准讨论"
        st.caption(f"第 {int(item.get('volume_no', 0))} 卷 / {item.get('title', '') or '未命名'} / 状态={label_status(item.get('status', 'draft'))} / {approval_label}")


def render_volume_outline_page(project_name: str, *, render_discussion_asset_candidates):
    story_id = st.session_state.get("active_story_id", "default")
    st.subheader("分卷大纲")

    context = _prepare_volume_outline_context(project_name, story_id)
    title, summary, status, requirement = _render_volume_metadata_fields(context)
    discussion_context = _prepare_volume_discussion_context(project_name, story_id, context["volume_no"])
    _render_volume_discussion_area(
        project_name,
        story_id,
        context,
        discussion_context,
        title,
        summary,
        requirement,
        render_discussion_asset_candidates,
    )
    _render_volume_prompt_options(project_name, story_id, context)
    step_result = _render_volume_generation(project_name, story_id, context, title, summary, requirement, status)
    _render_volume_editor_and_actions(project_name, story_id, context, title, summary, status)
    _render_existing_volumes(project_name, story_id)
    render_step_validation(step_result)
    render_step_retrieval(
        step_result,
        "本次分卷大纲生成使用的检索上下文",
        get_retrieval_trace(f"volume_outline:{project_name}:{story_id}:{context['volume_no']}"),
    )

