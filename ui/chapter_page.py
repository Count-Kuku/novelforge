"""Chapter writing page."""
from __future__ import annotations

import streamlit as st

from memory import (
    load_chapter,
    load_chapter_discussion_artifact,
    load_chapter_outline,
    load_creative_profile,
    load_global_prompt_options,
    load_project_prompt_options,
    load_story_prompt_options,
    save_chapter,
)
from prompt_options import filter_prompt_options, merge_prompt_option_layers
from skills import (
    extract_setting_candidates_from_chapter,
    generate_chapter_outline,
    get_retrieval_trace,
    pipeline_plan_write_review_update,
    review_chapter,
    write_chapter,
)
from ui.common import scoped_session_key, scoped_widget_key
from ui.discussion import (
    _format_discussion_artifact_as_guidance,
    _render_approved_discussion_artifact,
)
from ui.labels import label_status
from ui.layout import render_section_heading
from ui.prompt_option_tools import (
    _prompt_option_label,
    _render_generation_injection_preview,
    _render_prompt_option_capability_tools,
    _render_prompt_option_inline_tools,
)
from ui.step_views import (
    render_step_json_expander,
    render_step_retrieval,
    render_step_status_message,
    render_step_validation,
)
from ui.streaming import (
    GenerationCancelled,
    make_stream_preview as _make_stream_preview,
    run_with_stream as _run_with_stream,
    safe_stream_emit as _safe_stream_emit,
)


def _run_chapter_inline_pipeline(
    project_name: str,
    story_id: str,
    chapter_no: int,
    chapter_outline: str,
    writing_guidance: dict,
    word_count: str,
) -> dict:
    stream_callback, complete_stream, cancel_stream, fail_stream = _make_stream_preview("正在执行流水线...")
    try:
        steps_result = {}
        _safe_stream_emit(stream_callback, "\n\n## 正文\n\n")
        write_result = write_chapter(
            project_name,
            chapter_no,
            chapter_outline,
            writing_guidance,
            word_count,
            story_id=story_id,
            stream_callback=stream_callback,
        )
        steps_result["write_chapter"] = write_result
        chapter = write_result.get("data", {}).get("chapter", "")
        if not chapter:
            raise RuntimeError(write_result.get("error", "正文生成失败"))

        _safe_stream_emit(stream_callback, "\n\n## 审阅\n\n")
        review_result = review_chapter(project_name, chapter_no, chapter, story_id=story_id, stream_callback=stream_callback)
        steps_result["review_chapter"] = review_result
        review_markdown = review_result.get("data", {}).get("review_markdown", "")

        review_success = bool(review_result.get("success")) and review_result.get("status") not in {"failed", "rejected", "blocked"}
        if review_success:
            _safe_stream_emit(stream_callback, "\n\n## 设定提炼\n\n")
            memory_result = extract_setting_candidates_from_chapter(
                project_name,
                chapter_no,
                chapter,
                story_id=story_id,
                stream_callback=stream_callback,
            )
        else:
            memory_result = {
                "step_name": "setting_extraction",
                "success": False,
                "status": "skipped",
                "warnings": ["章节审阅未通过或未完成，已跳过设定提炼。"],
            }
        steps_result["setting_extraction"] = memory_result
        complete_stream("流水线执行完成。")
        return {
            "chapter": chapter,
            "review_markdown": review_markdown,
            "steps": steps_result,
        }
    except GenerationCancelled:
        cancel_stream()
        st.stop()
    except Exception as exc:
        fail_stream(f"流水线执行失败：{exc}")
        raise


def _render_chapter_write_settings(
    project_name: str,
    story_id: str,
    chapter_scope: tuple,
    discussion_guidance: str,
) -> tuple[dict, list[str] | None]:
    write_settings_ui = st.expander("高级：写作设置", expanded=False)
    write_settings_ui.markdown("### 当前写作设置")
    write_settings_ui.caption("提示词选项只影响本次生成会额外采用哪些写作提示。没有选项也能生成；需要时可在下方直接新增。")
    try:
        effective_prompt_options = merge_prompt_option_layers(
            load_global_prompt_options(),
            load_project_prompt_options(project_name),
            load_story_prompt_options(project_name, story_id),
        )
        write_prompt_options = filter_prompt_options(effective_prompt_options, "write", enabled_only=False)
    except Exception as exc:
        write_settings_ui.warning(f"提示词选项加载失败：{exc}")
        write_prompt_options = []
    selected_prompt_option_ids = None
    if write_prompt_options:
        option_ids = [option.get("id", "") for option in write_prompt_options]
        option_labels = {option.get("id", ""): _prompt_option_label(option) for option in write_prompt_options}
        default_option_ids = [option.get("id", "") for option in write_prompt_options if option.get("enabled", True)]
        selected_prompt_option_ids = write_settings_ui.multiselect(
            "本次使用提示词选项",
            options=option_ids,
            default=default_option_ids,
            format_func=lambda option_id: option_labels.get(option_id, option_id),
            key=scoped_widget_key("write_prompt_option_ids", *chapter_scope),
            help="默认勾选已启用选项；也可以临时选择未启用的预设，仅影响本次生成。",
        )
    else:
        write_settings_ui.info("还没有可用于正文写作的提示词选项。它不是讨论后才会出现；展开下面的管理区就能新增，或去工作台的「提示词选项」页复制内置预设。")
    write_settings_ui.markdown("#### 提示词选项")
    with write_settings_ui.container():
        _render_prompt_option_inline_tools(
            project_name,
            story_id,
            write_prompt_options,
            capability="write",
            key_prefix=scoped_widget_key("write_prompt_option_tools", *chapter_scope),
        )
    tone = write_settings_ui.selectbox(
        "文风/基调",
        options=["", "克制", "热血", "轻快", "压抑", "爽文推进"],
        format_func=lambda value: value or "未特别指定",
        key=scoped_widget_key("write_tone", *chapter_scope),
    )
    pacing = write_settings_ui.selectbox(
        "节奏",
        options=["", "慢铺", "均衡", "快推"],
        format_func=lambda value: value or "未特别指定",
        key=scoped_widget_key("write_pacing", *chapter_scope),
    )
    dialogue_density = write_settings_ui.selectbox(
        "对话密度",
        options=["", "低", "中", "高"],
        format_func=lambda value: value or "未特别指定",
        key=scoped_widget_key("write_dialogue_density", *chapter_scope),
    )
    focus = write_settings_ui.multiselect(
        "描写重点",
        options=["动作", "心理", "环境", "关系拉扯", "战斗", "信息揭示"],
        key=scoped_widget_key("write_focus", *chapter_scope),
    )
    ending_strength = write_settings_ui.selectbox(
        "结尾力度",
        options=["", "轻钩子", "强钩子", "悬念断点"],
        format_func=lambda value: value or "未特别指定",
        key=scoped_widget_key("write_ending_strength", *chapter_scope),
    )
    extra_requirements = write_settings_ui.text_area(
        "写作补充要求",
        height=120,
        key=scoped_widget_key("write_extra_requirements", *chapter_scope),
        placeholder="例如：减少说明性段落，多写试探性对话，结尾用短句收束。",
    )
    combined_extra_requirements_parts = []
    if discussion_guidance.strip():
        combined_extra_requirements_parts.append(f"写作提示：\n{discussion_guidance.strip()}")
    if extra_requirements.strip():
        combined_extra_requirements_parts.append(f"补充要求：\n{extra_requirements.strip()}")
    combined_extra_requirements = "\n\n".join(combined_extra_requirements_parts)

    writing_guidance = {
        "tone": tone,
        "pacing": pacing,
        "dialogue_density": dialogue_density,
        "focus": focus,
        "ending_strength": ending_strength,
        "extra_requirements": combined_extra_requirements,
    }
    if selected_prompt_option_ids is not None:
        writing_guidance["prompt_option_ids"] = selected_prompt_option_ids
    return writing_guidance, selected_prompt_option_ids


def _render_missing_outline_actions(
    project_name: str,
    story_id: str,
    chapter_no: int,
    word_count: str,
    chapter_scope: tuple,
    chapter_outline_gen_key: str,
    chapter_outline_editor_key: str,
    pipeline_result_key: str,
    chapter_text_key: str,
    chapter_text_editor_key: str,
):
    st.info("没有已有细纲，可直接编写、从需求生成细纲、或从需求完整执行。")
    with st.expander("从需求自动执行", expanded=True):
        gen_requirement = st.text_area(
            "创作需求",
            height=100,
            key=scoped_widget_key("auto_full_req", *chapter_scope),
            placeholder="例如：主角在废弃车站发现线索，与搭档产生分歧。",
        )
        col_gen_outline, col_full_pipeline = st.columns(2)
        with col_gen_outline:
            if st.button("仅生成细纲", use_container_width=True, key=scoped_widget_key("gen_outline_btn", *chapter_scope)):
                if not gen_requirement.strip():
                    st.warning("请先填写创作需求。")
                else:
                    try:
                        outline_result = _run_with_stream(
                            "正在生成细纲...",
                            generate_chapter_outline,
                            project_name,
                            chapter_no,
                            gen_requirement,
                            story_id=story_id,
                        )
                        outline_text = outline_result.get("data", {}).get("chapter_outline", "")
                        if outline_text:
                            st.session_state[chapter_outline_gen_key] = outline_text
                            st.session_state[chapter_outline_editor_key] = outline_text
                            st.success("细纲已生成，将在上方细纲文本框中显示。")
                            st.rerun()
                        else:
                            st.error("细纲生成失败，请手工编写。")
                    except Exception as exc:
                        st.error(f"细纲生成失败：{exc}")
        with col_full_pipeline:
            if st.button("细纲→写作→审阅→提炼设定", use_container_width=True, type="primary", key=scoped_widget_key("full_pipeline_btn", *chapter_scope)):
                if not gen_requirement.strip():
                    st.warning("请先填写创作需求。")
                else:
                    try:
                        pipeline_result = _run_with_stream(
                            "正在完整执行...",
                            pipeline_plan_write_review_update,
                            project_name,
                            chapter_no,
                            gen_requirement,
                            word_count,
                            story_id=story_id,
                        )
                        st.session_state[pipeline_result_key] = pipeline_result
                        chapter = pipeline_result.get("chapter", "") or pipeline_result.get("steps", {}).get("write_chapter", {}).get("data", {}).get("chapter", "")
                        if chapter:
                            st.session_state[chapter_text_key] = chapter
                            st.session_state[chapter_text_editor_key] = chapter
                        st.rerun()
                    except Exception as exc:
                        st.error(f"完整流水线执行失败：{exc}")


def _render_chapter_discussion_guidance(
    is_chapter_mode: bool,
    chapter_scope: tuple,
    discussion_guidance_default: str,
    approved_discussion_artifact: dict,
) -> str:
    if not is_chapter_mode:
        st.markdown("### 写作提示（可选）")
        return st.text_area(
            "补充提示",
            height=80,
            key=scoped_widget_key("write_notes", *chapter_scope),
            placeholder="例如：整体语气轻松，结尾留悬念。",
        )

    st.markdown("### 本章讨论与写作提示")
    st.caption("这里适合写临时想法、需要特别执行的写法、和已保存章节结论的收束结论；生成正文时会并入写作补充要求。")
    discussion_guidance_key = scoped_widget_key("write_discussion_guidance", *chapter_scope)
    if discussion_guidance_default and discussion_guidance_key not in st.session_state:
        st.session_state[discussion_guidance_key] = discussion_guidance_default
    action_col, preview_col = st.columns([1, 1])
    if action_col.button("用已保存章节结论填入", key=scoped_widget_key("fill_discussion_guidance", *chapter_scope)):
        if discussion_guidance_default:
            st.session_state[discussion_guidance_key] = discussion_guidance_default
            st.success("已填入已保存章节结论。")
        else:
            st.warning("当前章节还没有保存讨论结论。")
    with preview_col.expander("查看已保存章节结论", expanded=False):
        _render_approved_discussion_artifact(approved_discussion_artifact, "当前章节还没有保存讨论结论。")
    return st.text_area(
        "讨论/指导提示",
        height=160,
        key=discussion_guidance_key,
        placeholder="例如：这一章重点写两人关系试探；冲突先压住，不急着摊牌；结尾让主角意识到线索来自旧案。",
    )


def _render_chapter_generation_actions(
    project_name: str,
    story_id: str,
    chapter_no: int,
    chapter_scope: tuple,
    has_outline: bool,
    chapter_outline: str,
    writing_guidance: dict,
    word_count: str,
    chapter_step_key: str,
    chapter_text_key: str,
    chapter_text_editor_key: str,
    pipeline_result_key: str,
    review_markdown_key: str,
):
    col_write, col_pipeline = st.columns([1, 1])
    with col_write:
        write_clicked = st.button(
            "写正文" if has_outline else "需要先填写或生成细纲",
            type="primary" if has_outline else "secondary",
            disabled=not has_outline,
            use_container_width=True,
            key=scoped_widget_key("write_chapter_btn", *chapter_scope),
        )
    with col_pipeline:
        pipeline_clicked = st.button(
            "细纲→写作→审阅→提炼设定" if has_outline else "需要先填写或生成细纲",
            disabled=not has_outline,
            use_container_width=True,
            key=scoped_widget_key("inline_pipeline_btn", *chapter_scope),
        )

    if write_clicked:
        result = _run_with_stream(
            "正在写正文...",
            write_chapter,
            project_name,
            chapter_no,
            chapter_outline,
            writing_guidance,
            word_count,
            story_id=story_id,
        )
        chapter = result.get("data", {}).get("chapter", "")
        st.session_state[chapter_step_key] = result
        st.session_state[chapter_text_key] = chapter
        st.session_state[chapter_text_editor_key] = chapter
        st.rerun()

    if pipeline_clicked and has_outline:
        try:
            pipeline_payload = _run_chapter_inline_pipeline(
                project_name,
                story_id,
                chapter_no,
                chapter_outline,
                writing_guidance,
                word_count,
            )
            chapter = pipeline_payload.get("chapter", "")
            review_markdown = pipeline_payload.get("review_markdown", "")
            st.session_state[chapter_text_key] = chapter
            st.session_state[chapter_text_editor_key] = chapter
            st.session_state[pipeline_result_key] = {
                "steps": pipeline_payload.get("steps", {}),
                "review_markdown": review_markdown,
            }
            if review_markdown:
                st.session_state[review_markdown_key] = review_markdown
            st.rerun()
        except Exception as exc:
            st.error(f"流水线执行失败：{exc}")


def _render_review_memory_prompt_tools(project_name: str, story_id: str, chapter_scope: tuple):
    with st.expander("高级：审阅与设定提炼提示词选项", expanded=False):
        tab_review_prompts, tab_memory_prompts = st.tabs(["章节审阅", "设定提炼"])
        with tab_review_prompts:
            _render_prompt_option_capability_tools(
                project_name,
                story_id,
                "review",
                scoped_widget_key("review_prompt_options", *chapter_scope),
            )
        with tab_memory_prompts:
            _render_prompt_option_capability_tools(
                project_name,
                story_id,
                "setting_extraction",
                scoped_widget_key("setting_extraction_prompt_options", *chapter_scope),
            )


def _render_chapter_review_memory_actions(
    project_name: str,
    story_id: str,
    chapter_no: int,
    chapter_scope: tuple,
    chapter_text: str,
    review_inline_step_key: str,
    review_markdown_key: str,
    setting_extraction_step_key: str,
):
    save_col, review_col, memory_col = st.columns(3)
    with save_col:
        if st.button("保存正文", use_container_width=True):
            save_chapter(project_name, chapter_no, chapter_text, story_id=story_id)
            st.success("正文已保存")

    has_chapter = bool(chapter_text.strip())
    with review_col:
        do_review = st.button(
            "审阅正文" if has_chapter else "需要先生成正文",
            disabled=not has_chapter,
            key=scoped_widget_key("review_inline", *chapter_scope),
            use_container_width=True,
        )
        if do_review and has_chapter:
            try:
                result = _run_with_stream(
                    "正在审阅正文...",
                    review_chapter,
                    project_name,
                    chapter_no,
                    chapter_text,
                    story_id=story_id,
                    preview_language="json",
                )
                st.session_state[review_inline_step_key] = result
                st.session_state[review_markdown_key] = result.get("data", {}).get("review_markdown", "")
                st.rerun()
            except Exception as exc:
                st.error(f"审阅失败：{exc}")

    with memory_col:
        do_memory = st.button(
            "提炼待确认设定" if has_chapter else "需要先生成正文",
            disabled=not has_chapter,
            key=scoped_widget_key("memory_inline", *chapter_scope),
            use_container_width=True,
        )
        if do_memory and has_chapter:
            try:
                result = _run_with_stream(
                    "正在提炼待确认设定...",
                    extract_setting_candidates_from_chapter,
                    project_name,
                    chapter_no,
                    chapter_text,
                    story_id=story_id,
                    preview_language="json",
                )
                st.session_state[setting_extraction_step_key] = result
                queued_count = result.get("data", {}).get("queued_knowledge_count", 0)
                render_step_status_message(result, f"已提炼 {queued_count} 条候选设定，等待确认后生效", "设定提炼失败：")
                render_step_validation(result)
                render_step_json_expander("章节设定提炼详细数据", result)
            except Exception as exc:
                st.error(f"设定提炼失败：{exc}")


def _render_chapter_result_details(
    project_name: str,
    story_id: str,
    chapter_no: int,
    chapter_step: dict,
    pipeline_result_key: str,
    review_markdown_key: str,
    review_inline_step_key: str,
    setting_extraction_step_key: str,
):
    review_markdown = st.session_state.get(review_markdown_key, "")
    if review_markdown:
        with st.expander("审阅结果", expanded=True):
            st.markdown(review_markdown)

    pipeline_result = st.session_state.get(pipeline_result_key, {})
    if pipeline_result:
        expanded_by_default = bool(pipeline_result.get("steps", {}).get("write_chapter", {}).get("success"))
        with st.expander("流水线执行详情", expanded=not expanded_by_default):
            pipeline_steps = pipeline_result.get("steps", {})
            for step_label, step_key in [("细纲", "chapter_outline"), ("写作", "write_chapter"), ("审阅", "review_chapter"), ("设定提炼", "setting_extraction")]:
                step_result = pipeline_steps.get(step_key, {})
                if step_result:
                    status = step_result.get("status", "-")
                    st.caption(f"{step_label}：{label_status(status)}")
                    render_step_validation(step_result)
            pipeline_markdown = pipeline_result.get("review_markdown", "") or pipeline_steps.get("review_chapter", {}).get("data", {}).get("review_markdown", "")
            if pipeline_markdown:
                st.markdown("#### 审阅结果")
                st.markdown(pipeline_markdown)

    render_step_validation(chapter_step)
    render_step_retrieval(
        chapter_step,
        "本次正文生成参考的资料",
        get_retrieval_trace(f"write:{project_name}:{story_id}:{chapter_no}")
    )
    render_step_retrieval(
        st.session_state.get(review_inline_step_key, {}),
        "本次审阅参考的资料",
        get_retrieval_trace(f"review:{project_name}:{story_id}:{chapter_no}")
    )
    render_step_retrieval(
        st.session_state.get(setting_extraction_step_key, {}),
        "本次设定提炼参考的资料",
        get_retrieval_trace(f"setting_extraction:{project_name}:{story_id}:{chapter_no}")
    )


def _prepare_chapter_page_context(project_name: str) -> dict:
    story_id = st.session_state.get("active_story_id", "default")
    profile = load_creative_profile(project_name, story_id=story_id) or {}
    workflow_depth = profile.get("workflow_depth", "")
    is_chapter_mode = workflow_depth in {"完整长篇流程", "分卷/剧情段/章节", "章节计划+正文"}
    mode_hint = "章节模式" if is_chapter_mode else "自由模式"

    render_section_heading(
        "当前生成对象",
        f"当前为{mode_hint}。章节模式会按编号读写细纲和正文；自由模式填 1 即可。",
    )

    meta_col_a, meta_col_b = st.columns(2)
    chapter_no = meta_col_a.number_input(
        "编号" if not is_chapter_mode else "章节编号",
        min_value=1 if is_chapter_mode else 0,
        value=1,
        help="章节模式下按编号读写已有细纲和正文；自由模式下填 1 即可",
    )
    if not is_chapter_mode and chapter_no < 1:
        chapter_no = 1
    chapter_no = int(chapter_no)
    chapter_scope = (project_name, story_id, chapter_no)
    word_count = meta_col_b.text_input(
        "目标字数（如 2000-2500）",
        value="2000-2500",
        key=scoped_widget_key("content_word_count", *chapter_scope),
    )

    chapter_step_key = scoped_session_key("chapter_step", *chapter_scope)
    chapter_outline_gen_key = scoped_session_key("chapter_outline_gen", *chapter_scope)
    chapter_text_key = scoped_session_key("chapter_text", *chapter_scope)
    pipeline_result_key = scoped_session_key("pipeline_result", *chapter_scope)
    review_markdown_key = scoped_session_key("review_markdown", *chapter_scope)
    review_inline_step_key = scoped_session_key("review_step_inline", *chapter_scope)
    setting_extraction_step_key = scoped_session_key("setting_extraction_step", *chapter_scope)
    chapter_outline_editor_key = scoped_widget_key("chapter_write_outline_editor", *chapter_scope)
    chapter_text_editor_key = scoped_widget_key("chapter_text_editor", *chapter_scope)

    existing_outline = load_chapter_outline(project_name, chapter_no, story_id=story_id)
    existing_chapter = load_chapter(project_name, chapter_no, story_id=story_id)
    approved_discussion_artifact = load_chapter_discussion_artifact(project_name, chapter_no, story_id=story_id) if is_chapter_mode else {}
    discussion_guidance_default = _format_discussion_artifact_as_guidance(approved_discussion_artifact) if is_chapter_mode else ""
    chapter_step = st.session_state.get(chapter_step_key, {})

    return {
        "story_id": story_id,
        "is_chapter_mode": is_chapter_mode,
        "chapter_no": chapter_no,
        "chapter_scope": chapter_scope,
        "chapter_step_key": chapter_step_key,
        "chapter_outline_gen_key": chapter_outline_gen_key,
        "chapter_text_key": chapter_text_key,
        "pipeline_result_key": pipeline_result_key,
        "review_markdown_key": review_markdown_key,
        "review_inline_step_key": review_inline_step_key,
        "setting_extraction_step_key": setting_extraction_step_key,
        "chapter_outline_editor_key": chapter_outline_editor_key,
        "chapter_text_editor_key": chapter_text_editor_key,
        "existing_outline": existing_outline,
        "existing_chapter": existing_chapter,
        "approved_discussion_artifact": approved_discussion_artifact,
        "discussion_guidance_default": discussion_guidance_default,
        "chapter_step": chapter_step,
        "word_count": word_count,
    }


def _render_chapter_outline_input(
    project_name: str,
    story_id: str,
    chapter_no: int,
    word_count: str,
    chapter_scope: tuple,
    is_chapter_mode: bool,
    existing_outline: str,
    chapter_outline_gen_key: str,
    chapter_outline_editor_key: str,
    pipeline_result_key: str,
    chapter_text_key: str,
    chapter_text_editor_key: str,
) -> str:
    has_existing_outline = bool(existing_outline or st.session_state.get(chapter_outline_gen_key))
    if not has_existing_outline:
        _render_missing_outline_actions(
            project_name,
            story_id,
            chapter_no,
            word_count,
            chapter_scope,
            chapter_outline_gen_key,
            chapter_outline_editor_key,
            pipeline_result_key,
            chapter_text_key,
            chapter_text_editor_key,
        )

    chapter_outline_value = st.session_state.get(chapter_outline_gen_key, existing_outline)
    return st.text_area(
        "内容细纲" if not is_chapter_mode else "章节细纲",
        value=chapter_outline_value,
        height=250,
        key=chapter_outline_editor_key,
    )


def _render_current_writing_guidance(discussion_guidance: str, writing_guidance: dict):
    with st.expander("当前写作指导", expanded=False):
        if discussion_guidance.strip():
            st.markdown("#### 写作提示")
            st.markdown(discussion_guidance)
        render_step_json_expander("写作指导参数", writing_guidance)


def _render_chapter_text_input(
    is_chapter_mode: bool,
    chapter_text_key: str,
    existing_chapter: str,
    chapter_text_editor_key: str,
) -> str:
    return st.text_area(
        "正文" if not is_chapter_mode else "章节正文",
        value=st.session_state.get(chapter_text_key, existing_chapter),
        height=600,
        key=chapter_text_editor_key,
    )


def _render_chapter_outline_section(project_name: str, context: dict) -> str:
    return _render_chapter_outline_input(
        project_name,
        context["story_id"],
        context["chapter_no"],
        context["word_count"],
        context["chapter_scope"],
        context["is_chapter_mode"],
        context["existing_outline"],
        context["chapter_outline_gen_key"],
        context["chapter_outline_editor_key"],
        context["pipeline_result_key"],
        context["chapter_text_key"],
        context["chapter_text_editor_key"],
    )


def _render_chapter_generation_section(project_name: str, context: dict, chapter_outline: str) -> str:
    discussion_guidance = _render_chapter_discussion_guidance(
        context["is_chapter_mode"],
        context["chapter_scope"],
        context["discussion_guidance_default"],
        context["approved_discussion_artifact"],
    )
    writing_guidance, selected_prompt_option_ids = _render_chapter_write_settings(
        project_name,
        context["story_id"],
        context["chapter_scope"],
        discussion_guidance,
    )
    has_outline = bool(chapter_outline.strip())
    _render_generation_injection_preview(
        project_name,
        context["story_id"],
        "write",
        selected_prompt_option_ids,
        writing_guidance,
    )

    _render_chapter_generation_actions(
        project_name,
        context["story_id"],
        context["chapter_no"],
        context["chapter_scope"],
        has_outline,
        chapter_outline,
        writing_guidance,
        context["word_count"],
        context["chapter_step_key"],
        context["chapter_text_key"],
        context["chapter_text_editor_key"],
        context["pipeline_result_key"],
        context["review_markdown_key"],
    )
    _render_current_writing_guidance(discussion_guidance, writing_guidance)
    render_section_heading("正文编辑区", "生成结果会直接进入这里，也可以手动修改后再保存、审阅或提炼设定。")
    return _render_chapter_text_input(
        context["is_chapter_mode"],
        context["chapter_text_key"],
        context["existing_chapter"],
        context["chapter_text_editor_key"],
    )


def _render_chapter_review_section(project_name: str, context: dict, chapter_text: str) -> None:
    _render_review_memory_prompt_tools(project_name, context["story_id"], context["chapter_scope"])
    _render_chapter_review_memory_actions(
        project_name,
        context["story_id"],
        context["chapter_no"],
        context["chapter_scope"],
        chapter_text,
        context["review_inline_step_key"],
        context["review_markdown_key"],
        context["setting_extraction_step_key"],
    )
    _render_chapter_result_details(
        project_name,
        context["story_id"],
        context["chapter_no"],
        context["chapter_step"],
        context["pipeline_result_key"],
        context["review_markdown_key"],
        context["review_inline_step_key"],
        context["setting_extraction_step_key"],
    )


def render_chapter_page(project_name: str):
    context = _prepare_chapter_page_context(project_name)
    render_section_heading("细纲输入", "可以读取已有细纲，也可以从需求自动生成细纲或完整执行。")
    chapter_outline = _render_chapter_outline_section(project_name, context)
    render_section_heading("写作控制", "先确认临时写作提示和高级写作设置，再启动正文或完整流水线。")
    chapter_text = _render_chapter_generation_section(project_name, context, chapter_outline)
    render_section_heading("审阅与设定提炼", "正文稳定后可以保存、审阅，并把长期设定提炼到待确认队列。")
    _render_chapter_review_section(project_name, context, chapter_text)
