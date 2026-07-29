"""Retrieval ingestion page panels."""
from __future__ import annotations

import streamlit as st

from extraction_presets import (
    KNOWLEDGE_EXTRACTION_EXPERT_PRESETS,
    KNOWLEDGE_EXTRACTION_MODE_HELP,
    KNOWLEDGE_EXTRACTION_MODE_LABELS,
    default_extraction_categories,
)
from memory import (
    list_long_reference_batches,
    list_retrieval_source_files,
    load_knowledge_base,
    load_pending_knowledge_items,
)
from skills import organize_reference_text
from source_workflows import (
    extract_pasted_reference_to_pending,
    import_organized_reference_entries,
    save_manual_retrieval_source_card,
)
from ui.common import scoped_session_key, scoped_widget_key
from ui.labels import label_authority, label_knowledge_category, label_scope, label_source_type
from ui.step_views import render_step_json_expander, render_step_validation
from ui.streaming import run_with_stream as _run_with_stream


def _render_ingestion_metrics(project_name: str) -> None:
    pending_count = len(load_pending_knowledge_items(project_name))
    batch_count = len(list_long_reference_batches(project_name))
    source_count = len(list_retrieval_source_files(project_name))
    knowledge_base = load_knowledge_base(project_name)
    knowledge_count = sum(len(items) for items in knowledge_base.values())

    st.caption("导入的资料会保存在当前项目中，并自动供后续规划、写作和审阅匹配使用。")
    metric_cols = st.columns(4)
    metric_cols[0].metric("待审核设定", pending_count)
    metric_cols[1].metric("长篇处理批次", batch_count)
    metric_cols[2].metric("已导入原文资料", source_count)
    metric_cols[3].metric("正式知识条目", knowledge_count)


def _render_organized_reference_result(
    project_name: str,
    current_story_id: str,
    paste_scope: str,
    paste_authority: str,
    paste_origin: str,
) -> None:
    result_key = scoped_session_key("organized_reference_result", project_name, current_story_id)
    organized_result = st.session_state.get(result_key, {})
    organized_payload = organized_result.get("data", {}).get("organized_reference", {})
    if not organized_payload:
        return

    st.markdown("#### 整理预览")
    st.markdown(organized_result.get("data", {}).get("report_markdown", ""))
    render_step_validation(organized_result)
    render_step_json_expander("整理结果详细数据", organized_payload)
    if st.button(
        "保存为可匹配资料",
        use_container_width=True,
        type="primary",
        key=scoped_widget_key("save_organized_reference", project_name, current_story_id),
    ):
        imported = import_organized_reference_entries(
            project_name,
            organized_payload,
            scope=paste_scope,
            authority=paste_authority,
            origin=paste_origin,
        )
        st.success(f"已导入 {imported} 条资料并重建索引。")
        st.rerun()


def _render_organized_reference_ingestion(project_name: str, current_story_id: str) -> None:
    state_scope = (project_name, current_story_id)
    result_key = scoped_session_key("organized_reference_result", *state_scope)
    st.markdown("#### 粘贴并整理为可匹配资料")
    paste_title = st.text_input(
        "资料标题",
        key=scoped_widget_key("organized_reference_title", *state_scope),
    )
    col_scope, col_auth = st.columns(2)
    paste_scope = col_scope.selectbox(
        "资料范围",
        options=["canon", "reference"],
        format_func=label_scope,
        key=scoped_widget_key("organized_reference_scope", *state_scope),
    )
    paste_authority = col_auth.selectbox(
        "资料可信度",
        options=["official", "curated", "community", "unknown"],
        index=1,
        format_func=label_authority,
        key=scoped_widget_key("organized_reference_authority", *state_scope),
    )
    paste_origin = st.text_input(
        "来源说明（可选）",
        key=scoped_widget_key("organized_reference_origin", *state_scope),
    )
    paste_text = st.text_area(
        "资料正文",
        height=240,
        key=scoped_widget_key("organized_reference_text", *state_scope),
    )
    if st.button(
        "整理并预览",
        use_container_width=True,
        key=scoped_widget_key("organize_reference_preview", *state_scope),
    ):
        if not paste_text.strip():
            st.error("请先粘贴资料正文。")
        else:
            try:
                st.session_state[result_key] = _run_with_stream(
                    "正在整理资料...",
                    organize_reference_text,
                    project_name,
                    paste_title,
                    paste_text,
                    preview_language="json",
                )
            except Exception as exc:
                st.error(f"整理失败：{exc}")

    _render_organized_reference_result(
        project_name,
        current_story_id,
        paste_scope,
        paste_authority,
        paste_origin,
    )


def _render_knowledge_extraction_settings(
    knowledge_category_options: list[str],
    project_name: str,
    current_story_id: str,
) -> tuple[list[str], str, str]:
    state_scope = (project_name, current_story_id)
    with st.expander("提取设置", expanded=False):
        expert_preset = st.selectbox(
            "专家提取预设",
            options=list(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.keys()),
            format_func=lambda value: KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[value]["label"],
            key=scoped_widget_key("knowledge_extract_expert_preset", *state_scope),
        )
        preset = KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[expert_preset]
        enabled_categories = st.multiselect(
            "提取分类",
            options=knowledge_category_options,
            default=default_extraction_categories("preset", preset, knowledge_category_options),
            format_func=label_knowledge_category,
            key=scoped_widget_key("knowledge_extract_categories", *state_scope, expert_preset),
        )
        extraction_modes = list(KNOWLEDGE_EXTRACTION_MODE_LABELS.keys())
        extraction_mode = st.selectbox(
            "提取模式",
            options=extraction_modes,
            index=extraction_modes.index(preset["mode"]) if preset["mode"] in KNOWLEDGE_EXTRACTION_MODE_LABELS else 0,
            format_func=lambda value: KNOWLEDGE_EXTRACTION_MODE_LABELS.get(value, value),
            key=scoped_widget_key("knowledge_extract_mode", *state_scope, expert_preset),
        )
        st.info(KNOWLEDGE_EXTRACTION_MODE_HELP.get(extraction_mode, "当前模式暂无说明。"))
        custom_instructions = st.text_area(
            "补充提取要求（可选）",
            height=90,
            key=scoped_widget_key("knowledge_extract_custom_instructions", *state_scope, expert_preset),
            placeholder="例如：只保留长期复用的事实；不确定内容标为 ambiguous。",
        )
    return enabled_categories, extraction_mode, custom_instructions


def _run_pasted_knowledge_extraction(
    project_name: str,
    current_story_id: str,
    *,
    knowledge_title: str,
    knowledge_text: str,
    enabled_categories: list[str],
    extraction_mode: str,
    custom_instructions: str,
    knowledge_scope: str,
    knowledge_authority: str,
    knowledge_origin: str,
    run_auto: bool,
) -> None:
    extraction_summary = _run_with_stream(
        "正在提取知识库条目...",
        extract_pasted_reference_to_pending,
        project_name,
        title=knowledge_title,
        text=knowledge_text,
        enabled_categories=enabled_categories,
        extraction_mode=extraction_mode,
        custom_instructions=custom_instructions,
        scope=knowledge_scope,
        authority=knowledge_authority,
        origin=knowledge_origin,
        auto_confirm_safe_items=run_auto,
        preview_language="json",
    )
    result = extraction_summary.get("result", {})
    result_key = scoped_session_key("knowledge_extraction_result", project_name, current_story_id)
    st.session_state[result_key] = result
    if run_auto:
        auto_summary = extraction_summary.get("auto_confirm", {})
        st.success(
            f"已整理 {extraction_summary.get('item_count', 0)} 条，加入待审核设定 {extraction_summary.get('queued_count', 0)} 条，"
            f"自动保存 {len(auto_summary.get('confirmed_ids', []))} 条，"
            f"保留待审核 {len(auto_summary.get('blocked_ids', []))} 条。"
        )
        st.rerun()
    st.success(
        f"已提取 {extraction_summary.get('item_count', 0)} 条，"
        f"并加入待审核设定 {extraction_summary.get('queued_count', 0)} 条。"
    )
    st.rerun()


def _render_knowledge_extraction_result(project_name: str, current_story_id: str) -> None:
    result_key = scoped_session_key("knowledge_extraction_result", project_name, current_story_id)
    extraction_result = st.session_state.get(result_key, {})
    extraction_payload = extraction_result.get("data", {}).get("knowledge_extraction", {})
    if not extraction_payload:
        return

    st.markdown("#### 最近一次提取预览")
    st.markdown(extraction_result.get("data", {}).get("report_markdown", ""))
    render_step_validation(extraction_result)
    render_step_json_expander("知识提取详细数据", extraction_payload)


def _render_knowledge_extraction_ingestion(
    project_name: str,
    current_story_id: str,
    knowledge_category_options: list[str],
) -> None:
    state_scope = (project_name, current_story_id)
    st.markdown("#### 粘贴资料 / 提取为知识库条目")
    st.caption("整理结果默认先进入待审核设定；也可以自动保存低风险条目。")
    knowledge_title = st.text_input(
        "资料标题",
        key=scoped_widget_key("knowledge_extract_title", *state_scope),
    )
    col_scope, col_auth = st.columns(2)
    knowledge_scope = col_scope.selectbox(
        "知识范围",
        options=["canon", "reference", "project"],
        index=0,
        format_func=label_scope,
        key=scoped_widget_key("knowledge_extract_scope", *state_scope),
    )
    knowledge_authority = col_auth.selectbox(
        "知识可信度",
        options=["official", "curated", "community", "project", "unknown"],
        index=1,
        format_func=label_authority,
        key=scoped_widget_key("knowledge_extract_authority", *state_scope),
    )
    knowledge_origin = st.text_input(
        "来源说明（可选）",
        key=scoped_widget_key("knowledge_extract_origin", *state_scope),
    )
    enabled_categories, extraction_mode, custom_instructions = _render_knowledge_extraction_settings(
        knowledge_category_options,
        project_name,
        current_story_id,
    )
    knowledge_text = st.text_area(
        "资料正文",
        height=260,
        key=scoped_widget_key("knowledge_extract_text", *state_scope),
    )

    action_cols = st.columns(2)
    run_extract = action_cols[0].button(
        "提取并预览",
        use_container_width=True,
        key=scoped_widget_key("extract_knowledge_preview", *state_scope),
    )
    run_auto = action_cols[1].button(
        "自动提取并保存低风险",
        use_container_width=True,
        type="primary",
        key=scoped_widget_key("extract_knowledge_auto", *state_scope),
    )
    if run_extract or run_auto:
        if not knowledge_text.strip():
            st.error("请先粘贴资料正文。")
        elif not enabled_categories:
            st.error("请至少选择一个提取分类。")
        else:
            try:
                _run_pasted_knowledge_extraction(
                    project_name,
                    current_story_id,
                    knowledge_title=knowledge_title,
                    knowledge_text=knowledge_text,
                    enabled_categories=enabled_categories,
                    extraction_mode=extraction_mode,
                    custom_instructions=custom_instructions,
                    knowledge_scope=knowledge_scope,
                    knowledge_authority=knowledge_authority,
                    knowledge_origin=knowledge_origin,
                    run_auto=run_auto,
                )
            except Exception as exc:
                st.error(f"知识提取失败：{exc}")

    _render_knowledge_extraction_result(project_name, current_story_id)


def _render_pasted_ingestion(
    project_name: str,
    current_story_id: str,
    knowledge_category_options: list[str],
) -> None:
    target_choice = st.radio(
        "处理方式",
        options=["整理为可匹配资料", "提取为知识库条目"],
        horizontal=True,
        key=scoped_widget_key("paste_ingestion_target", project_name, current_story_id),
    )
    if target_choice == "整理为可匹配资料":
        _render_organized_reference_ingestion(project_name, current_story_id)
    else:
        _render_knowledge_extraction_ingestion(project_name, current_story_id, knowledge_category_options)


def _render_manual_retrieval_source_card(
    project_name: str,
    current_story_id: str,
    source_type_options: dict[str, str],
) -> None:
    state_scope = (project_name, current_story_id)
    st.markdown("#### 手动资料卡")
    st.caption("适合少量已经整理好的设定卡、角色卡或事件卡。保存后，后续生成可以按内容自动匹配。")
    source_name = st.text_input("资料名称", key=scoped_widget_key("retrieval_source_name", *state_scope))
    col_scope, col_auth = st.columns(2)
    source_scope = col_scope.selectbox(
        "资料范围",
        options=["reference", "canon"],
        format_func=label_scope,
        key=scoped_widget_key("retrieval_source_scope", *state_scope),
    )
    source_authority = col_auth.selectbox(
        "资料可信度",
        options=["official", "curated", "community", "unknown"],
        index=1,
        format_func=label_authority,
        key=scoped_widget_key("retrieval_source_authority", *state_scope),
    )
    source_origin = st.text_input(
        "来源说明/链接（可选）",
        key=scoped_widget_key("retrieval_source_origin", *state_scope),
    )
    source_type = st.selectbox(
        "资料模板",
        options=list(source_type_options.keys()),
        format_func=lambda key: source_type_options.get(key, label_source_type(key)),
        key=scoped_widget_key("retrieval_source_type", *state_scope),
    )
    source_title = st.text_input("显示标题（可选）", key=scoped_widget_key("retrieval_source_title", *state_scope))
    source_summary = st.text_area(
        "资料摘要（可选）",
        height=100,
        key=scoped_widget_key("retrieval_source_summary", *state_scope),
    )
    source_tags = st.text_input("标签（逗号分隔，可选）", key=scoped_widget_key("retrieval_source_tags", *state_scope))
    source_content = st.text_area(
        "资料正文",
        height=220,
        key=scoped_widget_key("retrieval_source_content", *state_scope),
    )
    if st.button(
        "保存资料卡",
        use_container_width=True,
        type="primary",
        key=scoped_widget_key("save_retrieval_source_card", *state_scope),
    ):
        if not source_name.strip() or not source_content.strip():
            st.error("资料名称和资料正文不能为空。")
        else:
            save_manual_retrieval_source_card(
                project_name,
                source_name=source_name,
                source_type=source_type,
                scope=source_scope,
                title=source_title,
                summary=source_summary,
                content=source_content,
                tags=[item.strip() for item in source_tags.split(",") if item.strip()],
                authority=source_authority,
                origin=source_origin,
            )
            st.success("资料卡已保存，后续生成已可以匹配使用。")
            st.rerun()


def _render_ingestion_followup_tabs(
    project_name: str,
    knowledge_category_options: list[str],
    *,
    render_ingestion_health_panel,
    render_source_ledger_page,
    render_auto_review_policy_panel,
    render_pending_knowledge_queue,
    render_auto_review_runs_panel,
    render_long_reference_batch_manager,
    render_knowledge_organizer,
    render_source_package_report_page,
) -> None:
    st.divider()
    st.markdown("### 待处理与整理")
    ledger_tab, queue_tab, record_tab, batch_tab, knowledge_tab, package_tab = st.tabs(
        ["资料来源", "待审核设定", "处理记录", "长篇批次", "知识整理", "资料包"]
    )
    with ledger_tab:
        render_ingestion_health_panel(project_name)
        render_source_ledger_page(project_name)
    with queue_tab:
        render_auto_review_policy_panel(project_name)
        render_pending_knowledge_queue(project_name)
    with record_tab:
        render_auto_review_runs_panel(project_name)
    with batch_tab:
        render_long_reference_batch_manager(project_name, knowledge_category_options)
    with knowledge_tab:
        render_knowledge_organizer(project_name, knowledge_category_options)
    with package_tab:
        render_source_package_report_page(project_name)


def render_retrieval_ingestion_page(
    project_name: str,
    source_type_options: dict[str, str],
    knowledge_category_options: list[str],
    *,
    render_long_reference_importer,
    render_ingestion_health_panel,
    render_source_ledger_page,
    render_auto_review_policy_panel,
    render_pending_knowledge_queue,
    render_auto_review_runs_panel,
    render_long_reference_batch_manager,
    render_knowledge_organizer,
    render_source_package_report_page,
):
    current_story_id = str(st.session_state.get("active_story_id") or "default")
    _render_ingestion_metrics(project_name)

    st.markdown("### 导入向导")
    st.caption("先选择资料的输入方式。整本原作等大段文本用“长篇文本”，少量内容可直接粘贴或填写资料卡。")
    source_choice = st.radio(
        "资料来源",
        options=["长篇文本", "粘贴资料", "手动资料卡"],
        horizontal=True,
        key=scoped_widget_key("ingestion_source_choice", project_name, current_story_id),
    )

    if source_choice == "长篇文本":
        render_long_reference_importer(project_name, source_type_options, knowledge_category_options, expanded=True)
    elif source_choice == "粘贴资料":
        _render_pasted_ingestion(project_name, current_story_id, knowledge_category_options)
    else:
        _render_manual_retrieval_source_card(project_name, current_story_id, source_type_options)

    _render_ingestion_followup_tabs(
        project_name,
        knowledge_category_options,
        render_ingestion_health_panel=render_ingestion_health_panel,
        render_source_ledger_page=render_source_ledger_page,
        render_auto_review_policy_panel=render_auto_review_policy_panel,
        render_pending_knowledge_queue=render_pending_knowledge_queue,
        render_auto_review_runs_panel=render_auto_review_runs_panel,
        render_long_reference_batch_manager=render_long_reference_batch_manager,
        render_knowledge_organizer=render_knowledge_organizer,
        render_source_package_report_page=render_source_package_report_page,
    )
    return
