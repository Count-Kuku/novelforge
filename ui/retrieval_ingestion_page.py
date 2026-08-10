"""Retrieval ingestion page panels."""
from __future__ import annotations

import streamlit as st

from novelforge.domain.extraction_presets import (
    KNOWLEDGE_EXTRACTION_EXPERT_PRESETS,
    KNOWLEDGE_EXTRACTION_MODE_HELP,
    KNOWLEDGE_EXTRACTION_MODE_LABELS,
    default_extraction_categories,
)
from novelforge.workflows.skills import organize_reference_text
from novelforge.workflows.source_workflows import (
    build_ingestion_workbench,
    extract_pasted_reference_to_pending,
    import_organized_reference_entries,
    save_manual_retrieval_source_card,
)
from ui.common import scoped_session_key, scoped_widget_key
from ui.labels import label_authority, label_knowledge_category, label_scope, label_source_type
from ui.step_views import render_step_json_expander, render_step_validation
from ui.streaming import run_with_stream as _run_with_stream
from ui.web_research import render_web_research_import


INGESTION_WORKSPACE_SECTIONS = ["资料任务", "资料来源", "待审核设定", "处理记录", "长篇批次", "知识整理", "资料包"]

INGESTION_WORKSPACE_DESCRIPTIONS = {
    "资料任务": "查看持久化执行进度，继续中断任务，或只重试失败片段。",
    "资料来源": "查看资料健康度、批次和原文来源账本。",
    "待审核设定": "审核提取结果，处理重复、冲突和证据不足的条目。",
    "处理记录": "检查自动审核决策，并在需要时回滚处理记录。",
    "长篇批次": "继续未完成批次，重试失败片段或执行专项提取。",
    "知识整理": "维护已经进入正式知识库的角色、关系、事件与规则。",
    "资料包": "生成供人工检查和后续使用的项目资料汇总。",
}


def _ingestion_workspace_key(project_name: str, story_id: str) -> str:
    return scoped_widget_key("ingestion_workspace_section", project_name, story_id)


def _render_ingestion_metrics(workbench: dict) -> None:
    st.caption(
        f"资料健康度 {workbench.get('health_score', 0)} / 100。"
        "导入内容会保存在当前项目中，并自动供后续规划、写作和审阅匹配使用。"
    )
    metric_cols = st.columns(6)
    metric_cols[0].metric("待处理任务", workbench.get("needs_processing_count", 0))
    metric_cols[1].metric("待审核设定", workbench.get("pending_review_count", 0))
    metric_cols[2].metric("风险项", workbench.get("risk_count", 0))
    metric_cols[3].metric("长篇批次", len(workbench.get("batch_rows", [])))
    metric_cols[4].metric("可匹配原文", workbench.get("ready_source_count", 0))
    metric_cols[5].metric("正式知识", workbench.get("confirmed_knowledge_count", 0))


def _activate_ingestion_action(project_name: str, story_id: str, action: dict) -> None:
    target_section = str(action.get("target_section") or "")
    if target_section in INGESTION_WORKSPACE_SECTIONS:
        st.session_state[_ingestion_workspace_key(project_name, story_id)] = target_section
    batch_id = str(action.get("batch_id") or "")
    if batch_id:
        st.session_state[scoped_widget_key("long_reference_batch_select", project_name)] = batch_id
    task_id = str(action.get("task_id") or "")
    if task_id:
        st.session_state[scoped_widget_key("source_ingestion_task_select", project_name, story_id)] = task_id
    if target_section == "导入向导":
        st.session_state[scoped_session_key("ingestion_import_hint", project_name, story_id)] = True
    st.rerun()


def _render_ingestion_workbench(project_name: str, story_id: str, workbench: dict) -> None:
    st.markdown("### 资料处理工作台")
    overall_status = str(workbench.get("overall_status") or "empty")
    if overall_status == "attention":
        st.warning("当前有失败片段或高风险知识需要处理。已成功保存的内容不会因为重试而丢失。")
    elif overall_status == "processing":
        st.info("资料已经进入处理流程；优先完成下面的推荐操作，就可以逐步转为正式知识。")
    elif overall_status == "ready":
        st.success("当前资料已经可以用于检索和写作。仍可继续补充薄弱分类或导入新来源。")
    else:
        st.info("当前还没有可复用资料。可以从整本原作、少量设定或手动资料卡开始。")

    _render_ingestion_metrics(workbench)
    actions = workbench.get("actions", [])
    if actions:
        st.markdown("#### 推荐下一步")
        for action in actions[:6]:
            with st.container(border=True):
                copy_col, action_col = st.columns([4, 1])
                copy_col.markdown(f"**{action.get('title', '继续处理资料')}**")
                copy_col.caption(str(action.get("detail") or ""))
                if action_col.button(
                    str(action.get("button_label") or "前往处理"),
                    key=scoped_widget_key(
                        "ingestion_workbench_action",
                        project_name,
                        story_id,
                        action.get("action_id", ""),
                    ),
                    use_container_width=True,
                    type="primary" if action.get("tone") == "error" else "secondary",
                ):
                    _activate_ingestion_action(project_name, story_id, action)

    batch_rows = workbench.get("batch_rows", [])
    if batch_rows:
        with st.expander("查看全部长篇批次状态", expanded=False):
            st.dataframe(
                [
                    {
                        "资料批次": row.get("title", ""),
                        "状态": row.get("status_label", ""),
                        "片段": row.get("segment_count", 0),
                        "已完成": row.get("completed_count", 0),
                        "待导入": row.get("pending_import_count", 0),
                        "待整理": row.get("pending_extract_count", 0),
                        "失败": row.get("failed_count", 0),
                        "更新时间": row.get("updated_at", ""),
                    }
                    for row in batch_rows
                ],
                use_container_width=True,
                hide_index=True,
            )


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


def _render_ingestion_workspace(
    project_name: str,
    story_id: str,
    knowledge_category_options: list[str],
    *,
    render_ingestion_health_panel,
    render_ingestion_task_manager,
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
    selected_section = st.radio(
        "处理工作区",
        options=INGESTION_WORKSPACE_SECTIONS,
        horizontal=True,
        key=_ingestion_workspace_key(project_name, story_id),
    )
    st.caption(INGESTION_WORKSPACE_DESCRIPTIONS[selected_section])
    if selected_section == "资料任务":
        render_ingestion_task_manager(project_name, story_id)
    elif selected_section == "资料来源":
        render_ingestion_health_panel(project_name)
        render_source_ledger_page(project_name)
    elif selected_section == "待审核设定":
        render_auto_review_policy_panel(project_name)
        render_pending_knowledge_queue(project_name)
    elif selected_section == "处理记录":
        render_auto_review_runs_panel(project_name)
    elif selected_section == "长篇批次":
        render_long_reference_batch_manager(project_name, knowledge_category_options, expanded=True)
    elif selected_section == "知识整理":
        render_knowledge_organizer(project_name, knowledge_category_options)
    else:
        render_source_package_report_page(project_name)


def _render_ingestion_wizard(
    project_name: str,
    story_id: str,
    source_type_options: dict[str, str],
    knowledge_category_options: list[str],
    *,
    render_long_reference_importer,
    expanded: bool,
) -> None:
    st.markdown("### 导入向导")
    if expanded:
        st.success("请在下面选择资料来源并开始导入。整本资料建议使用“长篇文本”。")
    st.caption("先选择资料的输入方式。整本原作等大段文本用“长篇文本”，少量内容可直接粘贴或填写资料卡。")
    source_choice = st.radio(
        "资料来源",
        options=["网络检索", "长篇文本", "粘贴资料", "手动资料卡"],
        horizontal=True,
        key=scoped_widget_key("ingestion_source_choice", project_name, story_id),
    )

    if source_choice == "网络检索":
        render_web_research_import(project_name, story_id)
    elif source_choice == "长篇文本":
        render_long_reference_importer(
            project_name,
            source_type_options,
            knowledge_category_options,
            expanded=expanded,
        )
    elif source_choice == "粘贴资料":
        _render_pasted_ingestion(project_name, story_id, knowledge_category_options)
    else:
        _render_manual_retrieval_source_card(project_name, story_id, source_type_options)


def render_retrieval_ingestion_page(
    project_name: str,
    source_type_options: dict[str, str],
    knowledge_category_options: list[str],
    *,
    render_long_reference_importer,
    render_ingestion_task_manager,
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
    workbench = build_ingestion_workbench(project_name)
    _render_ingestion_workbench(project_name, current_story_id, workbench)
    import_hint_key = scoped_session_key("ingestion_import_hint", project_name, current_story_id)
    prioritize_import = bool(st.session_state.pop(import_hint_key, False)) or workbench.get("overall_status") == "empty"

    def render_wizard() -> None:
        _render_ingestion_wizard(
            project_name,
            current_story_id,
            source_type_options,
            knowledge_category_options,
            render_long_reference_importer=render_long_reference_importer,
            expanded=prioritize_import,
        )

    def render_workspace() -> None:
        _render_ingestion_workspace(
            project_name,
            current_story_id,
            knowledge_category_options,
            render_ingestion_health_panel=render_ingestion_health_panel,
            render_ingestion_task_manager=render_ingestion_task_manager,
            render_source_ledger_page=render_source_ledger_page,
            render_auto_review_policy_panel=render_auto_review_policy_panel,
            render_pending_knowledge_queue=render_pending_knowledge_queue,
            render_auto_review_runs_panel=render_auto_review_runs_panel,
            render_long_reference_batch_manager=render_long_reference_batch_manager,
            render_knowledge_organizer=render_knowledge_organizer,
            render_source_package_report_page=render_source_package_report_page,
        )

    if prioritize_import:
        render_wizard()
        render_workspace()
    else:
        render_workspace()
        st.divider()
        render_wizard()
    return
