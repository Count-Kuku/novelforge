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
    _discussion_context_text,
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
from ui.labels import label_status
from ui.layout import render_section_heading
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
    title_col, status_col = st.columns([2, 1])
    title = title_col.text_input("分卷标题", value=metadata.get("title", ""), key=scoped_widget_key("volume_title", *volume_scope))
    status = status_col.selectbox(
        "分卷状态",
        options=VOLUME_STATUS_OPTIONS,
        index=_status_index(metadata.get("status", "draft")),
        format_func=label_status,
        key=scoped_widget_key("volume_status", *volume_scope),
    )
    summary_col, requirement_col = st.columns(2)
    summary = summary_col.text_area("分卷摘要", value=metadata.get("summary", ""), height=150, key=scoped_widget_key("volume_summary", *volume_scope))
    requirement = requirement_col.text_area("本卷要求", height=150, key=scoped_widget_key("volume_requirement", *volume_scope))
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
    st.markdown("##### 分卷方向结论")
    _render_discussion_summary(discussion_step, "开始讨论后，这里显示本卷定位、推进目标和关键约束。")
    render_step_retrieval(discussion_step, "本次分卷讨论参考的资料")
    render_discussion_asset_candidates(
        project_name,
        story_id,
        discussion_step,
        "volume",
        f"volume:{project_name}:{story_id}:{volume_no}",
        scoped_widget_key("volume_discussion_prompt_options", *volume_scope),
    )
    approve_col, clear_col = st.columns(2)
    if approve_col.button("保存分卷结论", key=scoped_widget_key("approve_volume_discussion", *volume_scope), use_container_width=True):
        try:
            result = approve_volume_discussion(project_name, volume_no, discussion_step, story_id=story_id)
            st.success("已保存分卷讨论结论。")
            st.rerun()
        except Exception as exc:
            st.error(f"保存失败：{exc}")
    if clear_col.button("清除分卷结论", key=scoped_widget_key("clear_volume_discussion", *volume_scope), use_container_width=True):
        if clear_volume_discussion_approval(project_name, volume_no, story_id=story_id):
            st.success("已清除分卷讨论结论。")
            st.rerun()
        else:
            st.warning("当前没有可清除的分卷结论。")
    st.markdown("##### 已保存分卷结论")
    _render_approved_discussion_artifact(discussion_context["approved_artifact"], "当前分卷还没有保存讨论结论。")


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
    volume_no = context["volume_no"]
    volume_scope = context["volume_scope"]

    def render_input_panel(_stream_container) -> None:
        messages_key = discussion_context["messages_key"]
        current_messages = st.session_state.get(messages_key, [])
        st.markdown("##### 讨论分卷方向")
        _render_discussion_decision_hint(
            ["本卷目标", "节奏", "承接", "边界"],
            "分卷大纲、剧情段规划和章节细纲",
            note="标题、摘要和本卷要求会自动带入。",
        )
        if current_messages:
            _render_discussion_chat(current_messages, height=260)
        else:
            _render_discussion_empty_hint("说说本卷要推进什么，也可以补充标题、摘要和要求。")
        live_turn_container = st.empty()
        user_input = st.text_area(
            "分卷讨论输入",
            key=discussion_context["input_key"],
            height=120,
            placeholder="例如：这一卷我想更偏升级与站稳脚跟，不要太早引爆终局矛盾。",
            label_visibility="collapsed",
        )
        has_started = bool(st.session_state.get(discussion_context["result_key"]) or current_messages)
        send_label = "发送" if has_started else "开始讨论"
        send_col, reset_col = st.columns([3, 1])
        if send_col.button(send_label, key=scoped_widget_key("send_volume_discussion", *volume_scope), use_container_width=True):
            submitted = str(user_input or "").strip()
            if not submitted:
                st.warning("讨论消息不能为空。")
            else:
                try:
                    _append_discussion_message(messages_key, "user", submitted)
                    updated_messages = st.session_state.get(messages_key, [])
                    if has_started:
                        result = _run_discussion_chat_stream(
                            live_turn_container,
                            submitted,
                            "继续讨论分卷",
                            discuss_volume_turn,
                            project_name,
                            volume_no,
                            title,
                            summary,
                            requirement,
                            updated_messages,
                            st.session_state.get(discussion_context["result_key"], {}).get("data", {}).get("discussion", {}),
                            submitted,
                            story_id=story_id,
                        )
                        assistant_message = result.get("data", {}).get("assistant_message", "") or "我已经根据你的补充更新了本卷讨论结论。"
                    else:
                        result = _run_discussion_chat_stream(
                            live_turn_container,
                            submitted,
                            "讨论分卷方向",
                            discuss_volume,
                            project_name,
                            volume_no,
                            title,
                            summary,
                            _discussion_context_text(requirement, submitted),
                            story_id=story_id,
                        )
                        assistant_message = result.get("data", {}).get("discussion", {}).get("current_understanding", "") or "我先整理了本卷的定位、可选结构和待确认问题，我们可以继续细化。"
                    st.session_state[discussion_context["result_key"]] = result
                    _append_discussion_message(messages_key, "assistant", assistant_message)
                    st.session_state[discussion_context["clear_input_flag_key"]] = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"讨论失败：{exc}")
        if reset_col.button("重置", key=scoped_widget_key("reset_volume_discussion", *volume_scope), use_container_width=True):
            st.session_state[discussion_context["result_key"]] = {}
            st.session_state[messages_key] = []
            st.session_state[discussion_context["clear_input_flag_key"]] = True
            st.rerun()

    def render_output_panel() -> None:
        _render_volume_discussion_summary_panel(
            project_name, story_id, context, discussion_context, render_discussion_asset_candidates
        )

    _render_discussion_workspace(
        f"volume-{project_name}-{story_id}-{context['volume_no']}",
        render_input_panel,
        render_output_panel,
    )

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
    if st.button("生成分卷大纲", key=scoped_widget_key("generate_volume_outline", *context["volume_scope"]), type="primary", use_container_width=True):
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
    if col1.button("保存分卷大纲", key=scoped_widget_key("save_volume", *context["volume_scope"]), use_container_width=True):
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
        st.caption("当前还没有分卷。")
        return
    for item in volumes:
        approval_label = "已有分卷结论" if item.get("has_approved_discussion") else "暂无分卷结论"
        st.caption(f"第 {int(item.get('volume_no', 0))} 卷 / {item.get('title', '') or '未命名'} / 状态={label_status(item.get('status', 'draft'))} / {approval_label}")


def render_volume_outline_page(project_name: str, *, render_discussion_asset_candidates):
    story_id = st.session_state.get("active_story_id", "default")

    render_section_heading("分卷信息", "先确定分卷定位、摘要和要求，再进入讨论或直接生成。")
    context = _prepare_volume_outline_context(project_name, story_id)
    title, summary, status, requirement = _render_volume_metadata_fields(context)
    discussion_context = _prepare_volume_discussion_context(project_name, story_id, context["volume_no"])
    render_section_heading("讨论分卷方向", "明确本卷负责什么、推进到哪里，再保存为后续规划依据。")
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
    render_section_heading("生成与编辑", "生成结果会写入编辑区，可人工修改后保存为正式分卷大纲。")
    step_result = _render_volume_generation(project_name, story_id, context, title, summary, requirement, status)
    _render_volume_editor_and_actions(project_name, story_id, context, title, summary, status)
    render_section_heading("现有分卷")
    _render_existing_volumes(project_name, story_id)
    render_step_validation(step_result)
    render_step_retrieval(
        step_result,
        "本次分卷大纲生成参考的资料",
        get_retrieval_trace(f"volume_outline:{project_name}:{story_id}:{context['volume_no']}"),
    )
