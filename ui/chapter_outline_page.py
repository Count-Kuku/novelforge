"""Chapter outline page."""
from __future__ import annotations

import streamlit as st

from memory import (
    list_arcs,
    list_volumes,
    load_arc_discussion_artifact,
    load_arc_metadata,
    load_chapter_discussion_artifact,
    load_chapter_outline,
    load_chapter_outline_metadata,
    load_volume_discussion_artifact,
    load_volume_metadata,
    save_chapter_outline,
    save_chapter_outline_metadata,
)
from skills import (
    approve_chapter_discussion,
    clear_chapter_discussion_approval,
    discuss_chapter,
    discuss_chapter_turn,
    generate_chapter_outline,
    get_retrieval_trace,
)
from ui.common import scoped_session_key, scoped_widget_key
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
from ui.layout import render_section_heading
from ui.prompt_option_tools import _render_prompt_option_capability_tools
from ui.step_views import render_step_retrieval, render_step_validation
from ui.streaming import run_with_stream as _run_with_stream


def _render_chapter_volume_selector(project_name: str, story_id: str, chapter_scope, outline_metadata, container=st):
    volumes = list_volumes(project_name, story_id=story_id)
    volume_options = [0] + [int(item.get("volume_no", 0)) for item in volumes]
    default_volume = int(outline_metadata.get("volume_no") or 0)
    volume_no = container.selectbox(
        "所属分卷",
        options=volume_options,
        index=volume_options.index(default_volume) if default_volume in volume_options else 0,
        format_func=lambda value: "未指定分卷" if value == 0 else f"第 {value} 卷",
        key=scoped_widget_key("chapter_outline_volume", *chapter_scope),
    )
    if volume_no:
        volume_meta = load_volume_metadata(project_name, volume_no, story_id=story_id)
        volume_discussion_artifact = load_volume_discussion_artifact(project_name, volume_no, story_id=story_id)
        container.caption(f"当前分卷：第 {volume_no} 卷 / {volume_meta.get('title', '') or '未命名分卷'}")
    else:
        volume_meta = {}
        volume_discussion_artifact = {}
    return volume_no, volume_meta, volume_discussion_artifact


def _render_chapter_arc_selector(project_name: str, story_id: str, chapter_scope, outline_metadata, volume_no: int, container=st):
    arcs = list_arcs(project_name, volume_no=volume_no or None, story_id=story_id)
    arc_options = [0] + [int(item.get("arc_no", 0)) for item in arcs]
    default_arc = int(outline_metadata.get("arc_no") or 0)
    arc_no = container.selectbox(
        "所属剧情段",
        options=arc_options,
        index=arc_options.index(default_arc) if default_arc in arc_options else 0,
        format_func=lambda value: "未指定剧情段" if value == 0 else f"剧情段 {value:03d}",
        key=scoped_widget_key("chapter_outline_arc", *chapter_scope),
    )
    if arc_no:
        arc_meta = load_arc_metadata(project_name, arc_no, story_id=story_id)
        arc_discussion_artifact = load_arc_discussion_artifact(project_name, arc_no, story_id=story_id)
        container.caption(f"当前剧情段：剧情段 {arc_no:03d} / {arc_meta.get('title', '') or '未命名剧情段'}")
    else:
        arc_meta = {}
        arc_discussion_artifact = {}
    return arc_no, arc_meta, arc_discussion_artifact


def _render_chapter_hierarchy(volume_no: int, arc_no: int, chapter_no: int) -> None:
    hierarchy_parts = ["全书大纲"]
    if volume_no:
        hierarchy_parts.append(f"第 {volume_no} 卷")
    if arc_no:
        hierarchy_parts.append(f"剧情段 {arc_no:03d}")
    hierarchy_parts.append(f"第 {chapter_no} 章")
    st.info(" / ".join(hierarchy_parts))


def _render_chapter_context_summaries(volume_meta: dict, arc_meta: dict) -> None:
    if volume_meta.get("summary"):
        with st.expander("当前分卷摘要", expanded=False):
            st.markdown(volume_meta.get("summary", ""))
    if arc_meta.get("summary"):
        with st.expander("当前剧情段摘要", expanded=False):
            st.markdown(arc_meta.get("summary", ""))


def _prepare_chapter_outline_context(project_name: str, story_id: str):
    meta_col_a, meta_col_b, meta_col_c = st.columns(3)
    chapter_no = meta_col_a.number_input(
        "章节编号",
        min_value=1,
        value=1,
        key=scoped_widget_key("chapter_outline_no", project_name, story_id),
    )
    chapter_no = int(chapter_no)
    chapter_scope = (project_name, story_id, chapter_no)
    outline_metadata = load_chapter_outline_metadata(project_name, chapter_no, story_id=story_id)
    volume_no, volume_meta, volume_discussion_artifact = _render_chapter_volume_selector(
        project_name, story_id, chapter_scope, outline_metadata, meta_col_b
    )
    arc_no, arc_meta, arc_discussion_artifact = _render_chapter_arc_selector(
        project_name, story_id, chapter_scope, outline_metadata, volume_no, meta_col_c
    )
    _render_chapter_hierarchy(volume_no, arc_no, chapter_no)
    _render_chapter_context_summaries(volume_meta, arc_meta)
    return {
        "chapter_no": chapter_no,
        "chapter_scope": chapter_scope,
        "step_key": scoped_session_key("chapter_outline_step", *chapter_scope),
        "text_key": scoped_session_key("chapter_outline", *chapter_scope),
        "editor_key": scoped_widget_key("chapter_outline_editor", *chapter_scope),
        "existing_outline": load_chapter_outline(project_name, chapter_no, story_id=story_id),
        "volume_no": volume_no,
        "arc_no": arc_no,
        "volume_discussion_artifact": volume_discussion_artifact,
        "arc_discussion_artifact": arc_discussion_artifact,
    }


def _render_approved_planning_artifacts(project_name: str, story_id: str, context) -> None:
    with st.expander("当前使用的已批准规划工件", expanded=False):
        st.markdown("### 章节已批准讨论")
        _render_approved_discussion_artifact(
            load_chapter_discussion_artifact(project_name, context["chapter_no"], story_id=story_id),
            "当前章节没有已批准讨论工件。",
        )
        st.markdown("### 分卷已批准讨论")
        _render_approved_discussion_artifact(context["volume_discussion_artifact"], "当前分卷没有已批准讨论工件。")
        st.markdown("### 剧情段已批准讨论")
        _render_approved_discussion_artifact(context["arc_discussion_artifact"], "当前剧情段没有已批准讨论工件。")


def _prepare_chapter_discussion_context(project_name: str, story_id: str, chapter_no: int):
    suffix = f"{project_name}:{story_id}:{chapter_no}"
    messages_key = _discussion_messages_key("chapter", suffix)
    result_key = _discussion_result_key("chapter", suffix)
    input_key = _discussion_input_key("chapter", suffix)
    clear_input_flag_key = _discussion_input_clear_flag_key("chapter", suffix)
    _consume_discussion_input_clear("chapter", suffix)
    return {
        "messages_key": messages_key,
        "result_key": result_key,
        "input_key": input_key,
        "clear_input_flag_key": clear_input_flag_key,
        "discussion_step": st.session_state.get(result_key, {}),
        "chapter_discussion_artifact": load_chapter_discussion_artifact(project_name, chapter_no, story_id=story_id),
    }


def _render_chapter_discussion_actions(project_name: str, story_id: str, context, requirement: str, discussion_context) -> None:
    chapter_no = context["chapter_no"]
    chapter_scope = context["chapter_scope"]
    col_action_1, col_action_2 = st.columns(2)
    if col_action_1.button("开始讨论本章方向", key=scoped_widget_key("start_chapter_discussion", *chapter_scope)):
        try:
            save_chapter_outline_metadata(
                project_name,
                chapter_no,
                {"volume_no": context["volume_no"] or None, "arc_no": context["arc_no"] or None},
                story_id=story_id,
            )
            result = _run_with_stream(
                "正在讨论本章方向...",
                discuss_chapter,
                project_name,
                chapter_no,
                requirement,
                story_id=story_id,
                preview_language="json",
            )
            st.session_state[discussion_context["result_key"]] = result
            st.session_state[discussion_context["messages_key"]] = []
            assistant_message = result.get("data", {}).get("discussion", {}).get("current_understanding", "") or "我先整理了本章目标、可选方向和待确认问题，我们可以继续细化。"
            _append_discussion_message(discussion_context["messages_key"], "assistant", assistant_message)
            st.rerun()
        except Exception as exc:
            st.error(f"讨论失败：{exc}")

    if col_action_2.button("重置本章讨论", key=scoped_widget_key("reset_chapter_discussion", *chapter_scope)):
        st.session_state[discussion_context["result_key"]] = {}
        st.session_state[discussion_context["messages_key"]] = []
        st.session_state[discussion_context["clear_input_flag_key"]] = True
        st.rerun()


def _render_chapter_discussion_summary_panel(
    project_name: str,
    story_id: str,
    context,
    discussion_context,
    render_discussion_asset_candidates,
) -> None:
    chapter_no = context["chapter_no"]
    chapter_scope = context["chapter_scope"]
    discussion_step = discussion_context["discussion_step"]
    st.markdown("### 当前讨论结论")
    _render_discussion_summary(discussion_step, "开始讨论后，这里会持续显示本章方向的当前结论。")
    render_step_retrieval(discussion_step, "本次章节讨论参考的检索上下文")
    render_discussion_asset_candidates(
        project_name,
        story_id,
        discussion_step,
        "chapter",
        f"chapter:{project_name}:{story_id}:{chapter_no}",
        scoped_widget_key("chapter_discussion_prompt_options", *chapter_scope),
    )
    approve_col, clear_col = st.columns(2)
    if approve_col.button("批准当前章节讨论", key=scoped_widget_key("approve_chapter_discussion", *chapter_scope)):
        try:
            result = approve_chapter_discussion(project_name, chapter_no, discussion_step, story_id=story_id)
            st.success(f"已保存章节讨论工件：{result.get('saved_path', '')}")
            st.rerun()
        except Exception as exc:
            st.error(f"批准失败：{exc}")
    if clear_col.button("清除已批准章节讨论", key=scoped_widget_key("clear_chapter_discussion", *chapter_scope)):
        if clear_chapter_discussion_approval(project_name, chapter_no, story_id=story_id):
            st.success("已清除章节已批准讨论工件。")
            st.rerun()
        else:
            st.warning("当前没有可清除的已批准章节讨论工件。")
    st.markdown("### 已批准章节讨论")
    _render_approved_discussion_artifact(discussion_context["chapter_discussion_artifact"], "当前章节还没有已批准讨论工件。")


def _render_chapter_discussion_chat_panel(
    project_name: str,
    story_id: str,
    context,
    requirement: str,
    discussion_context,
) -> None:
    chapter_no = context["chapter_no"]
    chapter_scope = context["chapter_scope"]
    messages_key = discussion_context["messages_key"]
    st.markdown("### 讨论对话")
    messages = st.session_state.get(messages_key, [])
    _render_discussion_chat(messages)
    follow_up = st.text_area(
        "继续讨论本章",
        key=discussion_context["input_key"],
        height=120,
        placeholder="例如：我希望这章更偏日常拉扯，不要太快进入正面冲突。",
    )
    if st.button("发送本章讨论消息", key=scoped_widget_key("send_chapter_discussion", *chapter_scope)):
        if not follow_up.strip():
            st.warning("讨论消息不能为空。")
        elif not requirement.strip():
            st.warning("请先填写本章要求。")
        else:
            try:
                save_chapter_outline_metadata(
                    project_name,
                    chapter_no,
                    {"volume_no": context["volume_no"] or None, "arc_no": context["arc_no"] or None},
                    story_id=story_id,
                )
                _append_discussion_message(messages_key, "user", follow_up)
                messages = st.session_state.get(messages_key, [])
                result = _run_with_stream(
                    "正在继续讨论本章...",
                    discuss_chapter_turn,
                    project_name,
                    chapter_no,
                    requirement,
                    messages,
                    discussion_context["discussion_step"].get("data", {}).get("discussion", {}),
                    follow_up,
                    story_id=story_id,
                    preview_language="json",
                )
                st.session_state[discussion_context["result_key"]] = result
                assistant_message = result.get("data", {}).get("assistant_message", "") or "我已经根据你的补充更新了本章讨论结论。"
                _append_discussion_message(messages_key, "assistant", assistant_message)
                st.session_state[discussion_context["clear_input_flag_key"]] = True
                st.rerun()
            except Exception as exc:
                st.error(f"继续讨论失败：{exc}")


def _render_chapter_discussion_area(
    project_name: str,
    story_id: str,
    context,
    requirement: str,
    discussion_context,
    render_discussion_asset_candidates,
) -> None:
    _render_chapter_discussion_actions(project_name, story_id, context, requirement, discussion_context)
    summary_col, chat_col = st.columns([1, 1])
    with summary_col:
        _render_chapter_discussion_summary_panel(
            project_name, story_id, context, discussion_context, render_discussion_asset_candidates
        )
    with chat_col:
        _render_chapter_discussion_chat_panel(project_name, story_id, context, requirement, discussion_context)


def _render_chapter_outline_prompt_options(project_name: str, story_id: str, context) -> None:
    with st.expander("高级：章节细纲提示词选项", expanded=False):
        _render_prompt_option_capability_tools(
            project_name,
            story_id,
            "chapter_outline",
            scoped_widget_key("chapter_outline_prompt_options", *context["chapter_scope"]),
        )


def _generation_blocked_by_approval(approval_required: bool, context, discussion_context) -> bool:
    if not approval_required:
        return False
    if context["volume_no"] and not (context["volume_discussion_artifact"].get("discussion", {}) or {}).get("approval_ready"):
        st.error("当前分卷还没有已批准讨论工件，已阻止章节细纲生成。")
        return True
    if context["arc_no"] and not (context["arc_discussion_artifact"].get("discussion", {}) or {}).get("approval_ready"):
        st.error("当前剧情段还没有已批准讨论工件，已阻止章节细纲生成。")
        return True
    if not (discussion_context["chapter_discussion_artifact"].get("discussion", {}) or {}).get("approval_ready"):
        st.error("当前章节还没有已批准讨论工件，已阻止章节细纲生成。")
        return True
    return False


def _run_chapter_outline_generation(project_name: str, story_id: str, context, requirement: str) -> dict:
    result = _run_with_stream(
        "正在生成章节细纲...",
        generate_chapter_outline,
        project_name,
        context["chapter_no"],
        requirement,
        volume_no=context["volume_no"] or None,
        arc_no=context["arc_no"] or None,
        story_id=story_id,
    )
    outline_value = result.get("data", {}).get("chapter_outline", "")
    st.session_state[context["step_key"]] = result
    st.session_state[context["text_key"]] = outline_value
    st.session_state[context["editor_key"]] = outline_value
    return result


def _render_chapter_outline_generation(
    project_name: str,
    story_id: str,
    context,
    requirement: str,
    approval_required: bool,
    discussion_context,
) -> dict:
    step_result = st.session_state.get(context["step_key"], {})
    if st.button("生成章节细纲", key=scoped_widget_key("generate_chapter_outline", *context["chapter_scope"]), type="primary", use_container_width=True):
        if not _generation_blocked_by_approval(approval_required, context, discussion_context):
            step_result = _run_chapter_outline_generation(project_name, story_id, context, requirement)
    return step_result


def _render_chapter_outline_editor(project_name: str, story_id: str, context) -> None:
    outline_text = st.text_area(
        "章节细纲内容",
        value=st.session_state.get(context["text_key"], context["existing_outline"]),
        height=500,
        key=context["editor_key"],
    )

    if st.button("保存章节细纲", key=scoped_widget_key("save_chapter_outline", *context["chapter_scope"]), use_container_width=True):
        save_chapter_outline(project_name, context["chapter_no"], outline_text, story_id=story_id)
        save_chapter_outline_metadata(
            project_name,
            context["chapter_no"],
            {"volume_no": context["volume_no"] or None, "arc_no": context["arc_no"] or None},
            story_id=story_id,
        )
        st.success(f"第 {context['chapter_no']} 章细纲已保存")


def render_chapter_outline_page(project_name: str, *, render_discussion_asset_candidates):
    story_id = st.session_state.get("active_story_id", "default")

    render_section_heading("章节定位", "先确定章节编号和所属层级，细纲会按这个位置读写和保存。")
    context = _prepare_chapter_outline_context(project_name, story_id)
    render_section_heading("生成约束", "可选择必须先批准讨论，再正式生成本章细纲。")
    approval_required = st.checkbox(
        "要求已批准的章节/卷/剧情段讨论后再生成章节细纲",
        value=False,
        key=scoped_widget_key("chapter_outline_require_approval", *context["chapter_scope"]),
    )
    _render_approved_planning_artifacts(project_name, story_id, context)
    with st.container(border=True):
        requirement = st.text_area(
            "本章要求",
            height=200,
            key=scoped_widget_key("chapter_outline_requirement", *context["chapter_scope"]),
        )
    discussion_context = _prepare_chapter_discussion_context(project_name, story_id, context["chapter_no"])
    render_section_heading("讨论与批准", "章节讨论可以先收束冲突、节奏和结尾目标，再批准为生成依据。")
    _render_chapter_discussion_area(
        project_name,
        story_id,
        context,
        requirement,
        discussion_context,
        render_discussion_asset_candidates,
    )
    _render_chapter_outline_prompt_options(project_name, story_id, context)
    render_section_heading("生成与编辑", "生成结果会写入编辑区，可以手动修订后保存为正式细纲。")
    step_result = _render_chapter_outline_generation(
        project_name,
        story_id,
        context,
        requirement,
        approval_required,
        discussion_context,
    )
    _render_chapter_outline_editor(project_name, story_id, context)
    render_step_validation(step_result)
    render_step_retrieval(
        step_result,
        "本次细纲生成使用的检索上下文",
        get_retrieval_trace(f"chapter_outline:{project_name}:{story_id}:{context['chapter_no']}")
    )

