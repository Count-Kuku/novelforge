"""Unified chapter review center with quick and comprehensive modes."""
from __future__ import annotations

import streamlit as st

from novelforge.services.memory import (
    load_chapter,
    load_evaluation_json,
    load_evaluation_report,
    load_review,
    load_review_json,
)
from novelforge.workflows.skills import get_retrieval_trace
from ui.chapter_review_runtime import run_chapter_review_by_mode
from ui.common import scoped_session_key, scoped_widget_key
from ui.labels import label_status
from ui.layout import render_empty_state, render_section_heading, render_stat_strip
from ui.step_views import render_step_json_expander, render_step_retrieval, render_step_validation
from ui.streaming import run_with_stream as _run_with_stream


REVIEW_MODE_LABELS = {
    "quick": "快速审阅",
    "comprehensive": "综合审阅",
}


def run_chapter_review(
    project_name: str,
    chapter_no: int,
    chapter_text: str,
    *,
    mode: str = "quick",
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    return run_chapter_review_by_mode(
        project_name,
        chapter_no,
        chapter_text,
        mode=mode,
        story_id=story_id,
        stream_callback=stream_callback,
    )


def run_comprehensive_chapter_evaluation(
    project_name: str,
    chapter_no: int,
    chapter_text: str,
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    """Compatibility entry retained for integrations using the old page API."""

    return run_chapter_review(
        project_name,
        chapter_no,
        chapter_text,
        mode="comprehensive",
        story_id=story_id,
        stream_callback=stream_callback,
    )


def _load_persisted_review(project_name: str, story_id: str, chapter_no: int, mode: str) -> tuple[str, dict]:
    if mode == "comprehensive":
        return (
            load_evaluation_report(project_name, chapter_no, story_id=story_id),
            load_evaluation_json(project_name, chapter_no, story_id=story_id) or {},
        )
    return (
        load_review(project_name, chapter_no, story_id=story_id),
        load_review_json(project_name, chapter_no, story_id=story_id) or {},
    )


def _mode_help(mode: str) -> str:
    if mode == "comprehensive":
        return "综合审阅会在门禁判断之外，提供多维评分、详细一致性诊断和按优先级排列的改稿建议。"
    return "快速审阅用于逐章写作门禁，只定位最关键的问题并判断是否可以继续，不进行量化评分。"


def _render_review_report(
    project_name: str,
    story_id: str,
    chapter_no: int,
    mode: str,
) -> None:
    scope = (project_name, story_id, chapter_no, mode)
    step = st.session_state.get(scoped_session_key("chapter_review_step", *scope), {})
    session_report = st.session_state.get(scoped_session_key("chapter_review_report", *scope), "")
    persisted_report, persisted_payload = _load_persisted_review(project_name, story_id, chapter_no, mode)
    payload = (step.get("data") or {}).get("review_payload") or persisted_payload
    report = session_report or persisted_report

    if not report and not payload:
        render_empty_state(
            f"还没有{REVIEW_MODE_LABELS[mode]}报告",
            "切换到“开始审阅”，选择对应深度后生成报告。",
        )
        return

    render_section_heading(REVIEW_MODE_LABELS[mode], _mode_help(mode))
    if payload:
        if mode == "comprehensive":
            render_stat_strip([
                ("状态", label_status(payload.get("status", "-")), "综合结论"),
                ("总分", payload.get("overall_score", 0), "分"),
                ("剧情推进", payload.get("plot_progression_score", 0), "分"),
                ("角色一致", payload.get("character_consistency_score", 0), "分"),
                ("文字完成度", payload.get("prose_quality_score", 0), "分"),
            ])
        else:
            render_stat_strip([
                ("状态", label_status(payload.get("status", "-")), "门禁结论"),
                ("关键问题", len(payload.get("issues", []) or []), "项"),
                ("优点", len(payload.get("strengths", []) or []), "项"),
            ])

    if report:
        st.markdown(report)
    if payload:
        render_step_json_expander(f"{REVIEW_MODE_LABELS[mode]}详细数据", payload)
    render_step_validation(step)
    trace_key = (
        f"evaluation:comprehensive:{project_name}:{story_id}:{chapter_no}"
        if mode == "comprehensive"
        else f"review:{project_name}:{story_id}:{chapter_no}"
    )
    render_step_retrieval(step, "本次审阅参考的资料", get_retrieval_trace(trace_key))


def render_evaluation_page(project_name: str, render_prompt_option_capability_tools):
    story_id = st.session_state.get("active_story_id", "default")
    chapter_no = int(st.number_input(
        "章节编号",
        min_value=1,
        value=1,
        key=scoped_widget_key("evaluation_chapter_no", project_name, story_id),
    ))
    review_scope = (project_name, story_id, chapter_no)
    existing_chapter = load_chapter(project_name, chapter_no, story_id=story_id)
    quick_report, quick_payload = _load_persisted_review(project_name, story_id, chapter_no, "quick")
    comprehensive_report, comprehensive_payload = _load_persisted_review(
        project_name,
        story_id,
        chapter_no,
        "comprehensive",
    )
    has_any_report = bool(quick_report or quick_payload or comprehensive_report or comprehensive_payload)

    view_key = scoped_widget_key("evaluation_view", *review_scope)
    legacy_view_aliases = {"开始评价": "开始审阅", "评价结果": "审阅报告"}
    if view_key in st.session_state:
        st.session_state[view_key] = legacy_view_aliases.get(st.session_state[view_key], st.session_state[view_key])
    else:
        st.session_state[view_key] = "审阅报告" if has_any_report else "开始审阅"
    view = st.segmented_control(
        "章节审阅视图",
        options=["开始审阅", "审阅报告"],
        key=view_key,
        label_visibility="collapsed",
    )

    if view == "开始审阅":
        chapter_text = st.text_area(
            "待审阅正文",
            value=existing_chapter,
            height=420,
            key=scoped_widget_key("evaluation_chapter_text", *review_scope),
        )
        mode = st.radio(
            "审阅深度",
            options=["quick", "comprehensive"],
            horizontal=True,
            format_func=lambda value: REVIEW_MODE_LABELS[value],
            key=scoped_widget_key("evaluation_review_mode", *review_scope),
        )
        st.caption(_mode_help(mode))

        with st.expander("高级：章节审阅提示词选项", expanded=False):
            render_prompt_option_capability_tools(
                project_name,
                story_id,
                "review",
                scoped_widget_key("evaluation_prompt_options", *review_scope),
            )

        button_label = f"开始{REVIEW_MODE_LABELS[mode]}"
        if st.button(
            button_label,
            key=scoped_widget_key("generate_evaluation", *review_scope),
            type="primary",
            width="stretch",
            disabled=not chapter_text.strip(),
        ):
            try:
                result = _run_with_stream(
                    f"正在生成{REVIEW_MODE_LABELS[mode]}报告...",
                    run_chapter_review,
                    project_name,
                    chapter_no,
                    chapter_text,
                    mode=mode,
                    story_id=story_id,
                    preview_language="json",
                )
                mode_scope = (*review_scope, mode)
                st.session_state[scoped_session_key("chapter_review_step", *mode_scope)] = result
                st.session_state[scoped_session_key("chapter_review_report", *mode_scope)] = (
                    result.get("data", {}).get("review_report", "")
                )
                st.session_state[scoped_widget_key("evaluation_report_mode", *review_scope)] = mode
                st.session_state[view_key] = "审阅报告"
                st.rerun()
            except Exception as exc:
                st.error(f"章节审阅失败：{exc}")
        return

    available_modes = []
    if quick_report or quick_payload or st.session_state.get(scoped_session_key("chapter_review_report", *review_scope, "quick")):
        available_modes.append("quick")
    if comprehensive_report or comprehensive_payload or st.session_state.get(scoped_session_key("chapter_review_report", *review_scope, "comprehensive")):
        available_modes.append("comprehensive")
    if not available_modes:
        render_empty_state("还没有章节审阅报告", "切换到“开始审阅”，选择快速或综合模式生成报告。")
        return

    report_mode_key = scoped_widget_key("evaluation_report_mode", *review_scope)
    if st.session_state.get(report_mode_key) not in available_modes:
        st.session_state[report_mode_key] = available_modes[-1]
    report_mode = st.radio(
        "报告类型",
        options=available_modes,
        horizontal=True,
        format_func=lambda value: REVIEW_MODE_LABELS[value],
        key=report_mode_key,
    )
    _render_review_report(project_name, story_id, chapter_no, report_mode)
