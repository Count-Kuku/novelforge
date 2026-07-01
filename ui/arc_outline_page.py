"""Arc outline page."""
from __future__ import annotations

import streamlit as st

from memory import (
    delete_arc,
    list_arcs,
    list_volumes,
    load_arc_chapter_plan,
    load_arc_discussion_artifact,
    load_arc_metadata,
    load_arc_outline,
    save_arc_metadata,
    save_arc_outline,
)
from project_manager import list_chapter_inventory
from skills import (
    approve_arc_discussion,
    clear_arc_discussion_approval,
    discuss_arc,
    discuss_arc_turn,
    generate_arc_chapter_plan,
    generate_arc_outline,
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
from ui.step_views import render_step_json_expander, render_step_retrieval, render_step_validation
from ui.streaming import run_with_stream as _run_with_stream


def _prepare_arc_outline_context(project_name: str) -> dict:
    story_id = st.session_state.get("active_story_id", "default")

    arc_no = st.number_input("剧情段编号", min_value=1, value=1, key=scoped_widget_key("arc_outline_no", project_name, story_id))
    arc_no = int(arc_no)
    arc_scope = (project_name, story_id, arc_no)
    arc_outline_step_key = scoped_session_key("arc_outline_step", *arc_scope)
    arc_outline_text_key = scoped_session_key("arc_outline", *arc_scope)
    arc_outline_editor_key = scoped_widget_key("arc_outline_editor", *arc_scope)
    arc_chapter_plan_step_key = scoped_session_key("arc_chapter_plan_step", *arc_scope)
    metadata = load_arc_metadata(project_name, arc_no, story_id=story_id)
    existing_outline = load_arc_outline(project_name, arc_no, story_id=story_id)
    step_result = st.session_state.get(arc_outline_step_key, {})

    volume_options = [0] + [int(item.get("volume_no", 0)) for item in list_volumes(project_name, story_id=story_id)]
    current_volume = int(metadata.get("volume_no") or 0)
    meta_col_a, meta_col_b, meta_col_c = st.columns(3)
    volume_no = meta_col_a.selectbox(
        "所属分卷",
        options=volume_options,
        index=volume_options.index(current_volume) if current_volume in volume_options else 0,
        format_func=lambda value: "未指定分卷" if value == 0 else f"第 {value} 卷",
        key=scoped_widget_key("arc_volume", *arc_scope),
    )
    status = meta_col_b.selectbox(
        "剧情段状态",
        options=["draft", "approved", "archived"],
        index=["draft", "approved", "archived"].index(metadata.get("status", "draft")) if metadata.get("status", "draft") in ["draft", "approved", "archived"] else 0,
        format_func=label_status,
        key=scoped_widget_key("arc_status", *arc_scope),
    )
    estimated_chapter_count = meta_col_c.number_input("预计章节数", min_value=0, value=int(metadata.get("estimated_chapter_count") or 0), key=scoped_widget_key("arc_estimated_chapters", *arc_scope))
    title_col, word_col = st.columns([2, 1])
    title = title_col.text_input("剧情段标题", value=metadata.get("title", ""), key=scoped_widget_key("arc_title", *arc_scope))
    target_word_count_range = word_col.text_input("目标总字数范围", value=metadata.get("target_word_count_range", ""), key=scoped_widget_key("arc_word_range", *arc_scope))
    summary_col, requirement_col = st.columns(2)
    summary = summary_col.text_area("剧情段摘要", value=metadata.get("summary", ""), height=150, key=scoped_widget_key("arc_summary", *arc_scope))
    requirement = requirement_col.text_area("本剧情段要求", height=150, key=scoped_widget_key("arc_requirement", *arc_scope))

    return {
        "story_id": story_id,
        "arc_no": arc_no,
        "arc_scope": arc_scope,
        "arc_outline_step_key": arc_outline_step_key,
        "arc_outline_text_key": arc_outline_text_key,
        "arc_outline_editor_key": arc_outline_editor_key,
        "arc_chapter_plan_step_key": arc_chapter_plan_step_key,
        "metadata": metadata,
        "existing_outline": existing_outline,
        "step_result": step_result,
        "volume_no": volume_no,
        "title": title,
        "summary": summary,
        "status": status,
        "estimated_chapter_count": estimated_chapter_count,
        "target_word_count_range": target_word_count_range,
        "requirement": requirement,
    }

def _render_arc_discussion(project_name: str, context: dict, render_discussion_asset_candidates):
    story_id = context["story_id"]
    arc_no = context["arc_no"]
    arc_scope = context["arc_scope"]
    volume_no = context["volume_no"]
    title = context["title"]
    summary = context["summary"]
    estimated_chapter_count = context["estimated_chapter_count"]
    target_word_count_range = context["target_word_count_range"]
    requirement = context["requirement"]
    suffix = f"{project_name}:{story_id}:{arc_no}"
    messages_key = _discussion_messages_key("arc", suffix)
    result_key = _discussion_result_key("arc", suffix)
    input_key = _discussion_input_key("arc", suffix)
    clear_input_flag_key = _discussion_input_clear_flag_key("arc", suffix)
    _consume_discussion_input_clear("arc", suffix)
    discussion_step = st.session_state.get(result_key, {})
    approved_artifact = load_arc_discussion_artifact(project_name, arc_no, story_id=story_id)

    def render_output_panel() -> None:
        current_step = st.session_state.get(result_key, discussion_step)
        st.markdown("##### 剧情段推进结论")
        _render_discussion_summary(current_step, "开始讨论后，这里显示剧情段起伏、转折和关键约束。")
        render_step_retrieval(current_step, "本次剧情段讨论参考的资料")
        render_discussion_asset_candidates(
            project_name,
            story_id,
            current_step,
            "arc",
            f"arc:{project_name}:{story_id}:{arc_no}",
            scoped_widget_key("arc_discussion_prompt_options", *arc_scope),
        )
        approve_col, clear_col = st.columns(2)
        if approve_col.button("保存剧情段结论", key=scoped_widget_key("approve_arc_discussion", *arc_scope), use_container_width=True):
            try:
                result = approve_arc_discussion(project_name, arc_no, current_step, story_id=story_id)
                st.success("已保存剧情段讨论结论。")
                st.rerun()
            except Exception as exc:
                st.error(f"保存失败：{exc}")
        if clear_col.button("清除剧情段结论", key=scoped_widget_key("clear_arc_discussion", *arc_scope), use_container_width=True):
            if clear_arc_discussion_approval(project_name, arc_no, story_id=story_id):
                st.success("已清除剧情段讨论结论。")
                st.rerun()
            else:
                st.warning("当前没有可清除的剧情段结论。")
        st.markdown("##### 已保存剧情段结论")
        _render_approved_discussion_artifact(approved_artifact, "当前剧情段还没有保存讨论结论。")

    def render_input_panel(_stream_container) -> None:
        current_messages = st.session_state.get(messages_key, [])
        st.markdown("##### 讨论剧情段推进")
        _render_discussion_decision_hint(
            ["阶段冲突", "转折", "章节分配", "高潮边界"],
            "剧情段大纲、章节分配和章节细纲",
            note="标题、摘要、篇幅和要求会自动带入。",
        )
        if current_messages:
            _render_discussion_chat(current_messages, height=260)
        else:
            _render_discussion_empty_hint("说说这一段要怎样推进，也可以补充冲突、转折或高潮。")
        live_turn_container = st.empty()
        user_input = st.text_area(
            "剧情段讨论输入",
            key=input_key,
            height=120,
            placeholder="例如：这一段我想让冲突递进更快，但高潮不要提早透支。",
            label_visibility="collapsed",
        )
        has_started = bool(st.session_state.get(result_key) or current_messages)
        send_label = "发送" if has_started else "开始讨论"
        send_col, reset_col = st.columns([3, 1])
        if send_col.button(send_label, key=scoped_widget_key("send_arc_discussion", *arc_scope), use_container_width=True):
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
                            "继续讨论剧情段",
                            discuss_arc_turn,
                            project_name,
                            arc_no,
                            volume_no or None,
                            title,
                            summary,
                            estimated_chapter_count or None,
                            target_word_count_range,
                            requirement,
                            updated_messages,
                            st.session_state.get(result_key, {}).get("data", {}).get("discussion", {}),
                            submitted,
                            story_id=story_id,
                        )
                        assistant_message = result.get("data", {}).get("assistant_message", "") or "我已经根据你的补充更新了剧情段讨论结论。"
                    else:
                        result = _run_discussion_chat_stream(
                            live_turn_container,
                            submitted,
                            "讨论剧情段方向",
                            discuss_arc,
                            project_name,
                            arc_no,
                            volume_no or None,
                            title,
                            summary,
                            estimated_chapter_count or None,
                            target_word_count_range,
                            _discussion_context_text(requirement, submitted),
                            story_id=story_id,
                        )
                        assistant_message = result.get("data", {}).get("discussion", {}).get("current_understanding", "") or "我先整理了这个剧情段的目标、可选推进结构和待确认问题，我们可以继续细化。"
                    st.session_state[result_key] = result
                    _append_discussion_message(messages_key, "assistant", assistant_message)
                    st.session_state[clear_input_flag_key] = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"讨论失败：{exc}")
        if reset_col.button("重置", key=scoped_widget_key("reset_arc_discussion", *arc_scope), use_container_width=True):
            st.session_state[result_key] = {}
            st.session_state[messages_key] = []
            st.session_state[clear_input_flag_key] = True
            st.rerun()

    _render_discussion_workspace(
        f"arc-{project_name}-{story_id}-{arc_no}",
        render_input_panel,
        render_output_panel,
    )

def _render_arc_prompt_options(project_name: str, context: dict):
    story_id = context["story_id"]
    arc_scope = context["arc_scope"]
    with st.expander("高级：剧情段提示词选项", expanded=False):
        tab_arc_outline, tab_arc_plan = st.tabs(["剧情段大纲", "章节分配计划"])
        with tab_arc_outline:
            _render_prompt_option_capability_tools(
                project_name,
                story_id,
                "outline",
                scoped_widget_key("arc_outline_prompt_options", *arc_scope),
            )
        with tab_arc_plan:
            _render_prompt_option_capability_tools(
                project_name,
                story_id,
                "chapter_outline",
                scoped_widget_key("arc_chapter_plan_prompt_options", *arc_scope),
            )

def _render_arc_outline_editor(project_name: str, context: dict):
    story_id = context["story_id"]
    arc_no = context["arc_no"]
    arc_scope = context["arc_scope"]
    volume_no = context["volume_no"]
    title = context["title"]
    summary = context["summary"]
    status = context["status"]
    estimated_chapter_count = context["estimated_chapter_count"]
    target_word_count_range = context["target_word_count_range"]
    requirement = context["requirement"]
    arc_outline_step_key = context["arc_outline_step_key"]
    arc_outline_text_key = context["arc_outline_text_key"]
    arc_outline_editor_key = context["arc_outline_editor_key"]
    existing_outline = context["existing_outline"]
    if st.button("生成剧情段大纲", key=scoped_widget_key("generate_arc_outline", *arc_scope), type="primary", use_container_width=True):
        try:
            result = _run_with_stream(
                "正在生成剧情段大纲...",
                generate_arc_outline,
                project_name,
                arc_no,
                volume_no or None,
                title,
                summary,
                estimated_chapter_count or None,
                target_word_count_range,
                requirement,
                status=status,
                story_id=story_id,
            )
            outline_value = result.get("data", {}).get("arc_outline", "")
            st.session_state[arc_outline_step_key] = result
            st.session_state[arc_outline_text_key] = outline_value
            st.session_state[arc_outline_editor_key] = outline_value
            st.rerun()
        except Exception as exc:
            st.error(f"生成剧情段大纲失败：{exc}")

    outline_text = st.text_area(
        "剧情段大纲内容",
        value=st.session_state.get(arc_outline_text_key, existing_outline),
        height=500,
        key=arc_outline_editor_key,
    )

    col1, col2 = st.columns(2)
    if col1.button("保存剧情段大纲", key=scoped_widget_key("save_arc", *arc_scope), use_container_width=True):
        save_arc_outline(project_name, arc_no, outline_text, story_id=story_id)
        save_arc_metadata(project_name, arc_no, {
            "volume_no": volume_no or None,
            "title": title,
            "summary": summary,
            "status": status,
            "estimated_chapter_count": estimated_chapter_count or None,
            "target_word_count_range": target_word_count_range,
        }, story_id=story_id)
        st.success(f"剧情段 {arc_no:03d} 已保存")
        st.rerun()
    if confirmed_button(
        col2,
        "删除剧情段",
        f"确认删除剧情段 {arc_no:03d}",
        scoped_widget_key("delete_arc", *arc_scope),
    ):
        if delete_arc(project_name, arc_no, story_id=story_id):
            st.success(f"剧情段 {arc_no:03d} 已删除")
            st.rerun()
        else:
            st.warning("目标剧情段不存在。")

def _render_arc_inventory(project_name: str, context: dict) -> list[dict]:
    story_id = context["story_id"]
    arc_no = context["arc_no"]
    arcs = list_arcs(project_name, story_id=story_id)
    if arcs:
        st.markdown("### 现有剧情段")
        for item in arcs:
            volume_label = f" / 第 {int(item.get('volume_no'))} 卷" if item.get("volume_no") else ""
            status_label = label_status(item.get("status", "draft"))
            approval_label = "已有剧情段结论" if item.get("has_approved_discussion") else "暂无剧情段结论"
            st.caption(f"剧情段 {int(item.get('arc_no', 0)):03d}{volume_label} / {item.get('title', '') or '未命名'} / 状态={status_label} / {approval_label}")

    chapter_inventory = list_chapter_inventory(project_name, story_id=story_id)
    linked_chapters = [
        item for item in chapter_inventory
        if ((item.get("metadata") or {}).get("arc_no") == arc_no)
    ]
    st.markdown("### 当前剧情段下的章节")
    if not linked_chapters:
        st.caption("当前剧情段下还没有归属章节。")
    else:
        for item in linked_chapters:
            chapter_no = int(item.get("chapter_no", 0))
            status_parts = []
            if item.get("has_outline"):
                status_parts.append("细纲")
            if item.get("has_content"):
                status_parts.append("正文")
            if item.get("has_review_markdown") or item.get("has_review_json"):
                status_parts.append("审阅")
            status_text = " / ".join(status_parts) if status_parts else "尚无内容"
            st.caption(f"第 {chapter_no} 章 / {status_text}")
    return linked_chapters

def _render_arc_chapter_plan(project_name: str, context: dict, linked_chapters: list[dict]):
    story_id = context["story_id"]
    arc_no = context["arc_no"]
    arc_scope = context["arc_scope"]
    arc_chapter_plan_step_key = context["arc_chapter_plan_step_key"]
    metadata = context["metadata"]
    step_result = context["step_result"]
    render_section_heading("章节分配计划", "把剧情段目标拆成章节范围，方便后续细纲页逐章展开。")
    saved_plan = load_arc_chapter_plan(project_name, arc_no, story_id=story_id)
    plan_col1, plan_col2 = st.columns(2)
    start_chapter_no = plan_col1.number_input(
        "起始章节编号",
        min_value=1,
        value=min([int(item.get("chapter_no", 1)) for item in linked_chapters], default=1),
        key=scoped_widget_key("arc_plan_start", *arc_scope),
    )
    default_plan_count = int(metadata.get("estimated_chapter_count") or 5)
    plan_chapter_count = plan_col2.number_input(
        "计划章节数",
        min_value=1,
        value=max(default_plan_count, 1),
        key=scoped_widget_key("arc_plan_count", *arc_scope),
    )
    plan_requirement = st.text_area("章节分配补充要求", height=120, key=scoped_widget_key("arc_plan_requirement", *arc_scope))
    plan_step = st.session_state.get(arc_chapter_plan_step_key, {})
    if st.button("生成剧情段章节分配计划", key=scoped_widget_key("generate_arc_chapter_plan", *arc_scope), type="primary", use_container_width=True):
        try:
            result = _run_with_stream(
                "正在生成剧情段章节分配计划...",
                generate_arc_chapter_plan,
                project_name,
                arc_no,
                int(start_chapter_no),
                int(plan_chapter_count),
                plan_requirement,
                story_id=story_id,
                preview_language="json",
            )
            st.session_state[arc_chapter_plan_step_key] = result
            st.success("章节分配计划已生成并保存。")
            st.rerun()
        except Exception as exc:
            st.error(f"生成章节分配计划失败：{exc}")
    latest_plan = st.session_state.get(arc_chapter_plan_step_key, {}).get("data", {}).get("report_markdown", "") or saved_plan.get("report_markdown", "")
    if latest_plan:
        with st.expander("当前剧情段章节分配计划", expanded=False):
            st.markdown(latest_plan)
            render_step_json_expander("章节分配详细数据", saved_plan.get("plan", {}))
    render_step_validation(plan_step)
    render_step_retrieval(plan_step, "本次章节分配参考的资料", get_retrieval_trace(f"arc_chapter_plan:{project_name}:{story_id}:{arc_no}"))

    render_step_validation(step_result)
    render_step_retrieval(step_result, "本次剧情段大纲生成参考的资料", get_retrieval_trace(f"arc_outline:{project_name}:{story_id}:{arc_no}"))

def render_arc_outline_page(project_name: str, *, render_discussion_asset_candidates):
    render_section_heading("剧情段信息", "剧情段承接分卷结构，适合定义一段冲突、转折或阶段目标。")
    context = _prepare_arc_outline_context(project_name)
    render_section_heading("讨论剧情段推进", "明确这一段怎样起伏、在哪里转折，再保存为章节规划依据。")
    _render_arc_discussion(project_name, context, render_discussion_asset_candidates)
    _render_arc_prompt_options(project_name, context)
    render_section_heading("生成与编辑", "生成结果会进入编辑区，保存后可继续生成章节分配计划。")
    _render_arc_outline_editor(project_name, context)
    render_section_heading("库存与归属", "检查现有剧情段和当前剧情段下的章节归属。")
    linked_chapters = _render_arc_inventory(project_name, context)
    _render_arc_chapter_plan(project_name, context, linked_chapters)
