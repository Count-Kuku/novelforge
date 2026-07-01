"""Quick dynamic generation page."""
from __future__ import annotations

import streamlit as st

from memory import load_creative_profile
from skills import run_dynamic_generation_task
from ui.common import scoped_session_key, scoped_widget_key
from ui.labels import label_status, label_step_name
from ui.layout import render_section_heading
from ui.step_views import render_step_json_expander, render_step_retrieval, render_step_validation
from ui.streaming import run_with_stream as _run_with_stream


def _render_dynamic_profile_caption(profile: dict) -> None:
    if profile.get("is_configured"):
        st.caption(f"当前故事配置：{profile.get('story_mode', '主线故事')} / {profile.get('target_length', '长篇')} / 参考 {profile.get('reference_strength', '中参考')}")


def _render_dynamic_requirement(project_name: str, story_id: str) -> str:
    return st.text_area(
        "创作提示词",
        height=200,
        key=scoped_widget_key("quick_gen_requirement", project_name, story_id),
        placeholder="例如：写一个 500 字的开场，主角在雨中遇到神秘人，气氛要压抑。",
    )


def _render_dynamic_writing_parameters(project_name: str, story_id: str) -> dict:
    st.markdown("#### 写作参数")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        tone = st.selectbox(
            "文风/基调",
            options=["", "克制", "热血", "轻快", "压抑", "爽文推进"],
            format_func=lambda v: v or "未指定",
            key=scoped_widget_key("quick_gen_tone", project_name, story_id),
        )
    with col_b:
        pacing = st.selectbox(
            "节奏",
            options=["", "慢铺", "均衡", "快推"],
            format_func=lambda v: v or "未指定",
            key=scoped_widget_key("quick_gen_pacing", project_name, story_id),
        )
    with col_c:
        dialogue_density = st.selectbox(
            "对话密度",
            options=["", "低", "中", "高"],
            format_func=lambda v: v or "未指定",
            key=scoped_widget_key("quick_gen_dialogue", project_name, story_id),
        )
    focus = st.multiselect(
        "描写重点",
        options=["动作", "心理", "环境", "关系拉扯", "战斗", "信息揭示"],
        key=scoped_widget_key("quick_gen_focus", project_name, story_id),
    )
    col_d, col_e = st.columns(2)
    with col_d:
        ending_strength = st.selectbox(
            "结尾力度",
            options=["", "轻钩子", "强钩子", "悬念断点"],
            format_func=lambda v: v or "未指定",
            key=scoped_widget_key("quick_gen_ending", project_name, story_id),
        )
    with col_e:
        extra_requirements = st.text_area(
            "补充要求",
            height=80,
            key=scoped_widget_key("quick_gen_extra", project_name, story_id),
            placeholder="例如：减少说明性段落，多用短句。",
        )
    return {
        "tone": tone,
        "pacing": pacing,
        "dialogue_density": dialogue_density,
        "focus": focus,
        "ending_strength": ending_strength,
        "extra_requirements": extra_requirements,
    }


def _render_dynamic_prompt_options(project_name: str, story_id: str, render_prompt_option_capability_tools):
    tab_quick_write_prompts, tab_quick_plan_prompts = st.tabs(["正文写作提示词", "章节计划提示词"])
    with tab_quick_write_prompts:
        selected_quick_prompt_option_ids = render_prompt_option_capability_tools(
            project_name,
            story_id,
            "write",
            scoped_widget_key("quick_write_prompt_options", project_name, story_id),
            select_for_run=True,
        )
    with tab_quick_plan_prompts:
        render_prompt_option_capability_tools(
            project_name,
            story_id,
            "chapter_outline",
            scoped_widget_key("quick_plan_prompt_options", project_name, story_id),
        )
    return selected_quick_prompt_option_ids


def _render_dynamic_advanced_config(project_name: str, story_id: str, profile: dict, render_prompt_option_capability_tools) -> dict:
    with st.expander("高级配置", expanded=False):
        default_word_count = profile.get("target_word_count", "") or "2000-2500"
        word_count = st.text_input("目标字数", value=default_word_count, key=scoped_widget_key("quick_gen_word_count", project_name, story_id))
        workflow_depth_options = ["只生成正文", "短篇结构+正文", "章节计划+正文"]
        workflow_depth = st.selectbox("生成层级", options=workflow_depth_options, index=0, key=scoped_widget_key("quick_gen_workflow_depth", project_name, story_id))
        st.caption("短篇结构会先生成创作结构再写正文；章节计划会先生成细纲再写正文。只生成正文则直接输出。")
        writing_guidance = _render_dynamic_writing_parameters(project_name, story_id)
        selected_prompt_option_ids = _render_dynamic_prompt_options(project_name, story_id, render_prompt_option_capability_tools)
    return {
        "word_count": word_count,
        "workflow_depth": workflow_depth,
        "writing_guidance": writing_guidance,
        "selected_prompt_option_ids": selected_prompt_option_ids,
    }


def _run_dynamic_generation(project_name: str, story_id: str, requirement: str, chapter_no: int, config: dict) -> None:
    result_key = scoped_session_key("dynamic_generation_result", project_name, story_id)
    requested_chapter_no = int(chapter_no or 0)
    save_outputs = requested_chapter_no > 0
    writing_guidance = dict(config["writing_guidance"])
    if config["selected_prompt_option_ids"] is not None:
        writing_guidance["prompt_option_ids"] = config["selected_prompt_option_ids"]
    result = _run_with_stream(
        "正在生成...",
        run_dynamic_generation_task,
        project_name,
        requested_chapter_no,
        requirement,
        config["word_count"],
        config["workflow_depth"],
        story_id=story_id,
        writing_guidance=writing_guidance,
        save_outputs=save_outputs,
    )
    st.session_state[result_key] = result
    st.rerun()


def _render_dynamic_generation_action(project_name: str, story_id: str, requirement: str, chapter_no: int, config: dict, col_run) -> None:
    if col_run.button(
        "生成",
        key=scoped_widget_key("dynamic_generation_run", project_name, story_id),
        use_container_width=True,
        type="primary",
    ):
        if not requirement.strip():
            st.error("请先填写创作提示词。")
        else:
            try:
                _run_dynamic_generation(project_name, story_id, requirement, chapter_no, config)
            except Exception as exc:
                st.error(f"生成失败：{exc}")


def _render_dynamic_generation_steps(result: dict) -> None:
    steps = result.get("steps", {}) or {}
    if not steps:
        return
    st.markdown("### 执行步骤")
    for step_name, step_result in steps.items():
        status_text = label_status(step_result.get("status", "-"))
        st.caption(f"{label_step_name(step_name)}：{status_text}")
        render_step_validation(step_result)
        render_step_retrieval(step_result, f"{label_step_name(step_name)}参考的资料")


def _render_dynamic_generation_result(project_name: str, story_id: str) -> None:
    result = st.session_state.get(scoped_session_key("dynamic_generation_result", project_name, story_id), {})
    if not result:
        return
    render_section_heading("输出结果", "生成内容会保留在本页，方便继续调整提示词或复制到正式章节。")
    if result.get("success"):
        st.success("生成完成。")
    else:
        st.error(f"生成未完成：{result.get('status', '未知状态')}")

    for warning in result.get("warnings", []):
        st.warning(warning)

    _render_dynamic_generation_steps(result)
    creative_structure = result.get("creative_structure", "")
    if creative_structure:
        with st.expander("创作结构 / 章节计划", expanded=True):
            st.markdown(creative_structure)

    chapter = result.get("chapter", "")
    if chapter:
        with st.expander("生成正文", expanded=True):
            st.markdown(chapter)

    render_step_json_expander("生成详细数据", result)


def render_dynamic_generation_page(project_name: str, render_prompt_option_capability_tools):
    story_id = st.session_state.get("active_story_id", "default")
    profile = load_creative_profile(project_name, story_id=story_id) or {}
    _render_dynamic_profile_caption(profile)

    render_section_heading("输入创作需求", "可以只写一句提示，也可以写完整场景要求；高级配置会在下一段统一调整。")
    with st.container(border=True):
        requirement = _render_dynamic_requirement(project_name, story_id)

    render_section_heading("运行设置", "保存章节、目标字数、生成层级和写作偏好集中在这里，减少生成前来回寻找。")
    control_col, action_col = st.columns([1, 2])
    with control_col:
        chapter_no = st.number_input(
            "保存到章节",
            min_value=0,
            value=0,
            key=scoped_widget_key("quick_gen_chapter_no", project_name, story_id),
            help="0 表示不保存，仅预览。",
        )
    config = _render_dynamic_advanced_config(project_name, story_id, profile, render_prompt_option_capability_tools)
    action_col.write("")
    action_col.write("")
    _render_dynamic_generation_action(project_name, story_id, requirement, int(chapter_no), config, action_col)
    _render_dynamic_generation_result(project_name, story_id)
