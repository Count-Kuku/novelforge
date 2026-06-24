"""Chapter evaluation page."""
from __future__ import annotations

import streamlit as st

from memory import load_chapter, load_evaluation_json, load_evaluation_report
from skills import evaluate_chapter_comprehensive, get_retrieval_trace
from ui.common import scoped_session_key, scoped_widget_key
from ui.labels import label_status
from ui.step_views import render_step_json_expander, render_step_retrieval, render_step_validation
from ui.streaming import run_with_stream as _run_with_stream

def run_comprehensive_chapter_evaluation(project_name: str, chapter_no: int, chapter_text: str, story_id: str = "default", stream_callback=None) -> dict:
    return evaluate_chapter_comprehensive(project_name, chapter_no, chapter_text, story_id=story_id, stream_callback=stream_callback)

def render_evaluation_page(project_name: str, render_prompt_option_capability_tools):
    story_id = st.session_state.get("active_story_id", "default")
    st.subheader("章节评价")
    st.caption("综合评价会一次性给出：通过/需改/阻塞结论、质量评分、一致性诊断和优先修改项。旧的审阅/专项分析能力仍保留给流水线和历史兼容。")

    chapter_no = st.number_input("章节编号", min_value=1, value=1, key=scoped_widget_key("evaluation_chapter_no", project_name, story_id))
    chapter_no = int(chapter_no)
    evaluation_scope = (project_name, story_id, chapter_no)
    existing_chapter = load_chapter(project_name, chapter_no, story_id=story_id)
    chapter_text = st.text_area(
        "待评估正文",
        value=existing_chapter,
        height=420,
        key=scoped_widget_key("evaluation_chapter_text", *evaluation_scope),
    )
    step_key = scoped_session_key("evaluation_step", *evaluation_scope)
    report_key = scoped_session_key("evaluation_report", *evaluation_scope)
    existing_report = load_evaluation_report(project_name, chapter_no, story_id=story_id)
    existing_json = load_evaluation_json(project_name, chapter_no, story_id=story_id) or {}

    with st.expander("高级：章节评价提示词选项", expanded=False):
        render_prompt_option_capability_tools(
            project_name,
            story_id,
            "review",
            scoped_widget_key("evaluation_prompt_options", *evaluation_scope),
        )

    if st.button("生成综合章节评价", key=scoped_widget_key("generate_evaluation", *evaluation_scope)):
        try:
            result = _run_with_stream(
                "正在生成章节综合评价...",
                run_comprehensive_chapter_evaluation,
                project_name,
                chapter_no,
                chapter_text,
                story_id=story_id,
                preview_language="json",
            )
            report = result.get("data", {}).get("report_markdown", "")
            st.session_state[step_key] = result
            st.session_state[report_key] = report
            st.rerun()
        except Exception as exc:
            st.error(f"章节评价失败：{exc}")

    report_text = st.text_area(
        "评价报告",
        value=st.session_state.get(report_key, existing_report),
        height=460,
        key=scoped_widget_key("evaluation_report_text", *evaluation_scope),
    )
    if report_text:
        st.markdown(report_text)

    evaluation_step = st.session_state.get(step_key, {})
    evaluation_payload = evaluation_step.get("data", {}).get("evaluation") or existing_json
    if evaluation_payload:
        cols = st.columns(5)
        cols[0].metric("状态", label_status(evaluation_payload.get("status", "-")))
        cols[1].metric("总分", evaluation_payload.get("overall_score", 0))
        cols[2].metric("剧情推进", evaluation_payload.get("plot_progression_score", 0))
        cols[3].metric("角色一致性", evaluation_payload.get("character_consistency_score", 0))
        cols[4].metric("文字完成度", evaluation_payload.get("prose_quality_score", 0))
        render_step_json_expander("评价结构化数据", evaluation_payload)
    render_step_validation(evaluation_step)
    render_step_retrieval(
        evaluation_step,
        "本次评价使用的检索上下文",
        get_retrieval_trace(f"evaluation:comprehensive:{project_name}:{story_id}:{chapter_no}") or get_retrieval_trace(f"evaluation:chapter:{project_name}:{story_id}:{chapter_no}")
    )

