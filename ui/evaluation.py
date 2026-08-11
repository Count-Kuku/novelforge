"""Chapter evaluation page."""
from __future__ import annotations

import streamlit as st

from novelforge.services.memory import load_chapter, load_evaluation_json, load_evaluation_report
from novelforge.workflows.skills import evaluate_chapter_comprehensive, get_retrieval_trace
from ui.common import scoped_session_key, scoped_widget_key
from ui.labels import label_status
from ui.layout import render_empty_state, render_stat_strip
from ui.step_views import render_step_json_expander, render_step_retrieval, render_step_validation
from ui.streaming import run_with_stream as _run_with_stream

def run_comprehensive_chapter_evaluation(project_name: str, chapter_no: int, chapter_text: str, story_id: str = "default", stream_callback=None) -> dict:
    return evaluate_chapter_comprehensive(project_name, chapter_no, chapter_text, story_id=story_id, stream_callback=stream_callback)

def render_evaluation_page(project_name: str, render_prompt_option_capability_tools):
    story_id = st.session_state.get("active_story_id", "default")

    chapter_no = st.number_input("章节编号", min_value=1, value=1, key=scoped_widget_key("evaluation_chapter_no", project_name, story_id))
    chapter_no = int(chapter_no)
    evaluation_scope = (project_name, story_id, chapter_no)
    existing_chapter = load_chapter(project_name, chapter_no, story_id=story_id)
    step_key = scoped_session_key("evaluation_step", *evaluation_scope)
    report_key = scoped_session_key("evaluation_report", *evaluation_scope)
    existing_report = load_evaluation_report(project_name, chapter_no, story_id=story_id)
    existing_json = load_evaluation_json(project_name, chapter_no, story_id=story_id) or {}
    view_key = scoped_widget_key("evaluation_view", *evaluation_scope)
    if view_key not in st.session_state:
        st.session_state[view_key] = "评价结果" if existing_report or existing_json else "开始评价"
    view = st.segmented_control(
        "章节审阅视图",
        options=["开始评价", "评价结果"],
        key=view_key,
        label_visibility="collapsed",
    )

    if view == "开始评价":
        chapter_text = st.text_area(
            "待评估正文",
            value=existing_chapter,
            height=420,
            key=scoped_widget_key("evaluation_chapter_text", *evaluation_scope),
        )

        with st.expander("高级：章节评价提示词选项", expanded=False):
            render_prompt_option_capability_tools(
                project_name,
                story_id,
                "review",
                scoped_widget_key("evaluation_prompt_options", *evaluation_scope),
            )

        if st.button("开始综合评价", key=scoped_widget_key("generate_evaluation", *evaluation_scope), type="primary", width="stretch"):
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
                st.session_state[view_key] = "评价结果"
                st.rerun()
            except Exception as exc:
                st.error(f"章节评价失败：{exc}")
        return

    evaluation_step = st.session_state.get(step_key, {})
    evaluation_payload = evaluation_step.get("data", {}).get("evaluation") or existing_json
    report_value = st.session_state.get(report_key, existing_report)
    if not report_value and not evaluation_payload:
        render_empty_state("还没有评价结果", "切换到“开始评价”，粘贴或加载章节正文后开始审阅。")
        return
    report_text = st.text_area(
        "评价报告",
        value=report_value,
        height=460,
        key=scoped_widget_key("evaluation_report_text", *evaluation_scope),
    )
    if report_text:
        st.markdown(report_text)

    if evaluation_payload:
        render_stat_strip([
            ("状态", label_status(evaluation_payload.get("status", "-")), "综合结论"),
            ("总分", evaluation_payload.get("overall_score", 0), "分"),
            ("剧情推进", evaluation_payload.get("plot_progression_score", 0), "分"),
            ("角色一致", evaluation_payload.get("character_consistency_score", 0), "分"),
            ("文字完成度", evaluation_payload.get("prose_quality_score", 0), "分"),
        ])
        render_step_json_expander("评价详细数据", evaluation_payload)
    render_step_validation(evaluation_step)
    render_step_retrieval(
        evaluation_step,
        "本次评价参考的资料",
        get_retrieval_trace(f"evaluation:comprehensive:{project_name}:{story_id}:{chapter_no}") or get_retrieval_trace(f"evaluation:chapter:{project_name}:{story_id}:{chapter_no}")
    )
