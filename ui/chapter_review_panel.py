"""Unified review and independent setting-extraction panel for chapter writing."""
from __future__ import annotations

import streamlit as st

from novelforge.services.memory import (
    load_evaluation_json,
    load_evaluation_report,
    load_review,
    load_review_json,
    save_chapter,
)
from novelforge.workflows.skills import (
    extract_setting_candidates_from_chapter,
    get_retrieval_trace,
)
from ui.chapter_review_runtime import run_chapter_review_by_mode
from ui.common import scoped_session_key, scoped_widget_key
from ui.labels import label_status
from ui.layout import render_section_heading
from ui.prompt_option_tools import _render_prompt_option_capability_tools, render_context_assembly_summary
from ui.step_views import (
    render_step_json_expander,
    render_step_retrieval,
    render_step_status_message,
    render_step_validation,
)
from ui.streaming import run_with_stream as _run_with_stream


def _render_prompt_tools(project_name: str, story_id: str, chapter_scope: tuple) -> None:
    with st.expander("高级：章节审阅提示词选项", expanded=False):
        _render_prompt_option_capability_tools(
            project_name,
            story_id,
            "review",
            scoped_widget_key("review_prompt_options", *chapter_scope),
        )


def _render_actions(
    project_name: str,
    story_id: str,
    chapter_no: int,
    chapter_scope: tuple,
    chapter_text: str,
    review_inline_step_key: str,
    review_markdown_key: str,
    setting_extraction_step_key: str,
) -> None:
    review_mode = st.radio(
        "审阅深度",
        options=["quick", "comprehensive"],
        horizontal=True,
        format_func=lambda value: "快速审阅" if value == "quick" else "综合审阅",
        key=scoped_widget_key("chapter_review_mode", *chapter_scope),
        help="快速审阅用于写作门禁；综合审阅会额外提供多维评分、详细一致性诊断和修改优先级。",
    )
    if review_mode == "quick":
        st.caption("快速审阅：判断本章能否进入下一步，只列关键问题，不进行量化评分。")
    else:
        st.caption("综合审阅：生成完整章节体检，包含门禁结论、量化评分、一致性诊断和修改优先级。")

    has_chapter = bool(chapter_text.strip())
    save_col, review_col = st.columns(2)
    with save_col:
        if st.button("保存正文", width="stretch", key=scoped_widget_key("save_chapter_before_review", *chapter_scope)):
            save_chapter(project_name, chapter_no, chapter_text, story_id=story_id)
            st.success("正文已保存")
    with review_col:
        do_review = st.button(
            ("开始快速审阅" if review_mode == "quick" else "开始综合审阅") if has_chapter else "需要先生成正文",
            disabled=not has_chapter,
            key=scoped_widget_key("review_inline", *chapter_scope),
            width="stretch",
            type="primary",
        )
        if do_review and has_chapter:
            try:
                result = _run_with_stream(
                    "正在快速审阅正文..." if review_mode == "quick" else "正在生成章节综合审阅...",
                    run_chapter_review_by_mode,
                    project_name,
                    chapter_no,
                    chapter_text,
                    mode=review_mode,
                    story_id=story_id,
                    preview_language="json",
                )
                st.session_state[review_inline_step_key] = result
                st.session_state[review_markdown_key] = result.get("data", {}).get("review_report", "")
                st.rerun()
            except Exception as exc:
                st.error(f"审阅失败：{exc}")

    st.divider()
    render_section_heading("设定提炼", "这是独立的知识更新操作，不属于章节审阅；结果只进入待审核队列，确认后才会生效。")
    with st.expander("高级：设定提炼提示词选项", expanded=False):
        _render_prompt_option_capability_tools(
            project_name,
            story_id,
            "setting_extraction",
            scoped_widget_key("setting_extraction_prompt_options", *chapter_scope),
        )
    memory_col, _ = st.columns(2)
    with memory_col:
        do_memory = st.button(
            "提炼待审核知识" if has_chapter else "需要先生成正文",
            disabled=not has_chapter,
            key=scoped_widget_key("memory_inline", *chapter_scope),
            width="stretch",
        )
        if do_memory and has_chapter:
            try:
                result = _run_with_stream(
                    "正在提炼待审核知识...",
                    extract_setting_candidates_from_chapter,
                    project_name,
                    chapter_no,
                    chapter_text,
                    story_id=story_id,
                    preview_language="json",
                )
                st.session_state[setting_extraction_step_key] = result
                queued_count = result.get("data", {}).get("queued_knowledge_count", 0)
                render_step_status_message(result, f"已提炼 {queued_count} 条待审核知识，确认后生效", "设定提炼失败：")
                render_step_validation(result)
                render_step_json_expander("章节设定提炼详细数据", result)
            except Exception as exc:
                st.error(f"设定提炼失败：{exc}")


def _load_mode_result(project_name: str, story_id: str, chapter_no: int, mode: str) -> tuple[str, dict]:
    if mode == "comprehensive":
        return (
            load_evaluation_report(project_name, chapter_no, story_id=story_id),
            load_evaluation_json(project_name, chapter_no, story_id=story_id) or {},
        )
    return (
        load_review(project_name, chapter_no, story_id=story_id),
        load_review_json(project_name, chapter_no, story_id=story_id) or {},
    )


def _render_result_details(
    project_name: str,
    story_id: str,
    chapter_no: int,
    chapter_step: dict,
    pipeline_result_key: str,
    review_markdown_key: str,
    review_inline_step_key: str,
    setting_extraction_step_key: str,
) -> None:
    latest_review_step = st.session_state.get(review_inline_step_key, {})
    review_mode = str(st.session_state.get(
        scoped_widget_key("chapter_review_mode", project_name, story_id, chapter_no),
        "quick",
    ) or "quick")
    latest_review_mode = str((latest_review_step.get("data") or {}).get("review_mode") or "")
    review_step = latest_review_step if latest_review_mode == review_mode else {}
    persisted_report, _ = _load_mode_result(project_name, story_id, chapter_no, review_mode)
    session_report = st.session_state.get(review_markdown_key, "") if latest_review_mode == review_mode else ""
    review_markdown = session_report or persisted_report
    if review_markdown:
        result_label = "综合审阅结果" if review_mode == "comprehensive" else "快速审阅结果"
        with st.expander(result_label, expanded=True):
            st.markdown(review_markdown)

    other_modes = []
    for mode in ("quick", "comprehensive"):
        if mode == review_mode:
            continue
        report, payload = _load_mode_result(project_name, story_id, chapter_no, mode)
        if report or payload or st.session_state.get(
            scoped_session_key("chapter_review_report", project_name, story_id, chapter_no, mode)
        ):
            other_modes.append(mode)
    if other_modes:
        with st.expander("其它已保存审阅", expanded=False):
            history_mode = st.radio(
                "历史报告",
                options=other_modes,
                format_func=lambda value: "综合审阅" if value == "comprehensive" else "快速审阅",
                horizontal=True,
                key=scoped_widget_key("chapter_review_history_mode", project_name, story_id, chapter_no),
            )
            history_report, history_payload = _load_mode_result(
                project_name, story_id, chapter_no, history_mode,
            )
            if history_report:
                st.markdown(history_report)
            if history_payload:
                render_step_json_expander(
                    "历史审阅详细数据",
                    history_payload,
                )

    pipeline_result = st.session_state.get(pipeline_result_key, {})
    if pipeline_result:
        expanded_by_default = bool(pipeline_result.get("steps", {}).get("write_chapter", {}).get("success"))
        with st.expander("自动流程执行详情", expanded=not expanded_by_default):
            pipeline_steps = pipeline_result.get("steps", {})
            for step_label, step_key in [("细纲", "chapter_outline"), ("写作", "write_chapter"), ("快速审阅", "review_chapter")]:
                step_result = pipeline_steps.get(step_key, {})
                if step_result:
                    st.caption(f"{step_label}：{label_status(step_result.get('status', '-'))}")
                    render_step_validation(step_result)
            pipeline_review_data = pipeline_steps.get("review_chapter", {}).get("data", {})
            pipeline_markdown = (
                pipeline_result.get("review_markdown", "")
                or pipeline_review_data.get("review_report", "")
                or pipeline_review_data.get("review_markdown", "")
            )
            if pipeline_markdown:
                st.markdown("#### 审阅结果")
                st.markdown(pipeline_markdown)

    render_step_validation(chapter_step)
    render_context_assembly_summary(
        (chapter_step.get("data") or {}).get("context_assembly") or {},
        "本次正文使用的规则与资料",
    )
    render_step_retrieval(
        chapter_step,
        "本次正文生成参考的资料",
        get_retrieval_trace(f"write:{project_name}:{story_id}:{chapter_no}"),
    )
    render_context_assembly_summary(
        (review_step.get("data") or {}).get("context_assembly") or {},
        "本次审阅使用的规则与资料",
    )
    review_trace_key = (
        f"evaluation:comprehensive:{project_name}:{story_id}:{chapter_no}"
        if review_mode == "comprehensive"
        else f"review:{project_name}:{story_id}:{chapter_no}"
    )
    render_step_retrieval(review_step, "本次审阅参考的资料", get_retrieval_trace(review_trace_key))
    render_step_retrieval(
        st.session_state.get(setting_extraction_step_key, {}),
        "本次设定提炼参考的资料",
        get_retrieval_trace(f"setting_extraction:{project_name}:{story_id}:{chapter_no}"),
    )


def render_chapter_review_panel(
    project_name: str,
    story_id: str,
    chapter_no: int,
    chapter_scope: tuple,
    chapter_text: str,
    chapter_step: dict,
    pipeline_result_key: str,
    review_markdown_key: str,
    review_inline_step_key: str,
    setting_extraction_step_key: str,
) -> None:
    _render_prompt_tools(project_name, story_id, chapter_scope)
    _render_actions(
        project_name,
        story_id,
        chapter_no,
        chapter_scope,
        chapter_text,
        review_inline_step_key,
        review_markdown_key,
        setting_extraction_step_key,
    )
    _render_result_details(
        project_name,
        story_id,
        chapter_no,
        chapter_step,
        pipeline_result_key,
        review_markdown_key,
        review_inline_step_key,
        setting_extraction_step_key,
    )
