"""Retrieval ingestion page panels."""
from __future__ import annotations

import streamlit as st

from novelforge.workflows.source_workflows import (
    build_ingestion_workbench,
    save_manual_retrieval_source_card,
)
from ui.common import navigate_to, scoped_widget_key
from ui.labels import label_authority, label_scope, label_source_type
from ui.layout import render_empty_state, render_section_heading, render_stat_strip
from ui.web_research import render_web_research_import


INGESTION_WORKSPACE_SECTIONS = ["概览", "导入", "处理", "管理"]

INGESTION_WORKSPACE_DESCRIPTIONS = {
    "概览": "查看资料准备状态和当前最需要完成的一件事。",
    "导入": "上传文件、粘贴文本、整理网络资料或新增手动条目。",
    "处理": "跟踪后台任务，继续长篇批次或重试失败片段。",
    "管理": "维护原文来源、知识库辅助视图、资料健康度和资料包。",
}

_WORKSPACE_TARGET_MAP = {
    "导入向导": "导入",
    "导入资料": "导入",
    "资料任务": "处理",
    "处理任务": "处理",
    "处理进度": "处理",
    "长篇批次": "处理",
    "待审核设定": "审核",
    "待审核知识": "审核",
    "待审核": "审核",
    "处理记录": "审核",
    "资料来源": "管理",
    "资料库": "管理",
    "资料包": "管理",
    "知识整理": "管理",
    "知识库": "管理",
}

_MANAGEMENT_VIEW_MAP = {
    "资料来源": "原文资料",
    "资料库": "原文资料",
    "资料包": "资料包",
    "知识整理": "知识条目",
    "知识库": "知识条目",
}


def _ingestion_workspace_key(project_name: str, story_id: str) -> str:
    return scoped_widget_key("ingestion_workspace_section", project_name, story_id)


def _migrate_ingestion_subview_state(project_name: str, story_id: str, legacy_workspace: str) -> None:
    if legacy_workspace in {"资料任务", "处理任务", "处理进度", "长篇批次"}:
        st.session_state[scoped_widget_key("ingestion_task_view", project_name, story_id)] = (
            "长篇批次" if legacy_workspace == "长篇批次" else "后台任务"
        )
    elif legacy_workspace in {"待审核设定", "待审核知识", "待审核", "处理记录"}:
        st.session_state[scoped_widget_key("knowledge_library_view", project_name, story_id)] = "待审核知识"
        st.session_state[scoped_widget_key("knowledge_library_review_view", project_name, story_id)] = (
            "处理记录" if legacy_workspace == "处理记录" else "审核队列"
        )
    elif legacy_workspace in _MANAGEMENT_VIEW_MAP:
        legacy_management_view = _MANAGEMENT_VIEW_MAP[legacy_workspace]
        if legacy_management_view == "知识条目":
            st.session_state[scoped_widget_key("knowledge_library_view", project_name, story_id)] = "全部知识"
            st.session_state[scoped_widget_key("knowledge_library_all_view", project_name, story_id)] = "知识条目"
        else:
            st.session_state[scoped_widget_key("ingestion_management_view", project_name, story_id)] = legacy_management_view


def _render_ingestion_metrics(workbench: dict) -> None:
    render_stat_strip(
        [
            ("资料健康度", f"{workbench.get('health_score', 0)} / 100"),
            ("处理中", workbench.get("needs_processing_count", 0), "后台任务与未完成批次"),
            ("待审核知识", workbench.get("pending_review_count", 0), "确认后才会用于生成"),
            ("可匹配原文", workbench.get("ready_source_count", 0)),
            ("正式知识", workbench.get("confirmed_knowledge_count", 0)),
        ]
    )


def _activate_ingestion_action(project_name: str, story_id: str, action: dict) -> None:
    target_section = str(action.get("target_section") or "")
    if target_section in {"待审核设定", "待审核知识", "待审核", "处理记录"}:
        st.session_state[scoped_widget_key("knowledge_library_view", project_name, story_id)] = "待审核知识"
        st.session_state[scoped_widget_key("knowledge_library_review_view", project_name, story_id)] = (
            "处理记录" if target_section == "处理记录" else "审核队列"
        )
        navigate_to("知识库")
    workspace = _WORKSPACE_TARGET_MAP.get(target_section, target_section)
    if workspace in INGESTION_WORKSPACE_SECTIONS:
        st.session_state[_ingestion_workspace_key(project_name, story_id)] = workspace
    if target_section in {"资料任务", "处理任务", "处理进度", "长篇批次"}:
        st.session_state[scoped_widget_key("ingestion_task_view", project_name, story_id)] = (
            "长篇批次" if target_section == "长篇批次" else "后台任务"
        )
    if target_section in _MANAGEMENT_VIEW_MAP:
        st.session_state[scoped_widget_key("ingestion_management_view", project_name, story_id)] = (
            _MANAGEMENT_VIEW_MAP[target_section]
        )
    batch_id = str(action.get("batch_id") or "")
    if batch_id:
        st.session_state[scoped_widget_key("long_reference_batch_select", project_name)] = batch_id
    task_id = str(action.get("task_id") or "")
    if task_id:
        st.session_state[scoped_widget_key("source_ingestion_task_select", project_name, story_id)] = task_id
    st.rerun()


def _render_ingestion_workbench(project_name: str, story_id: str, workbench: dict) -> None:
    render_section_heading("资料概况", "导入内容会保存在当前项目，并自动供后续规划、写作和审阅匹配使用。")
    overall_status = str(workbench.get("overall_status") or "empty")
    if overall_status == "attention":
        st.warning("当前有失败片段或高风险知识需要处理。已成功保存的内容不会因为重试而丢失。")

    _render_ingestion_metrics(workbench)
    actions = workbench.get("actions", [])
    if actions:
        action = actions[0]
        with st.container(border=True):
            copy_col, action_col = st.columns([4, 1], vertical_alignment="center")
            copy_col.markdown(f"**推荐：{action.get('title', '继续处理资料')}**")
            copy_col.caption(str(action.get("detail") or ""))
            if action_col.button(
                str(action.get("button_label") or "前往处理"),
                key=scoped_widget_key(
                    "ingestion_workbench_action",
                    project_name,
                    story_id,
                    action.get("action_id", ""),
                ),
                width="stretch",
                type="primary" if action.get("tone") == "error" else "secondary",
            ):
                _activate_ingestion_action(project_name, story_id, action)
    elif overall_status == "empty":
        render_empty_state("还没有资料", "从下方“导入资料”开始，可以上传文件或直接粘贴文本。", icon="↥")


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
        width="stretch",
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
    source_type_options: dict[str, str],
    knowledge_category_options: list[str],
    *,
    render_long_reference_importer,
    render_ingestion_health_panel,
    render_ingestion_task_manager,
    render_source_ledger_page,
    render_long_reference_batch_manager,
    render_source_package_report_page,
    workbench: dict,
) -> None:
    render_section_heading("资料准备流程", "按“导入 → 处理 → 管理”完成资料准备；候选内容统一到“知识库 → 待审核知识”确认。")
    workspace_key = _ingestion_workspace_key(project_name, story_id)
    default_workspace = "导入" if str(workbench.get("overall_status") or "empty") == "empty" else "概览"
    if workspace_key in st.session_state:
        raw_value = str(st.session_state.get(workspace_key) or "")
        _migrate_ingestion_subview_state(project_name, story_id, raw_value)
        if raw_value in {"待审核设定", "待审核知识", "待审核", "处理记录", "知识整理", "知识库"}:
            navigate_to("知识库")
        current_value = _WORKSPACE_TARGET_MAP.get(raw_value, raw_value)
        st.session_state[workspace_key] = (
            current_value if current_value in INGESTION_WORKSPACE_SECTIONS else default_workspace
        )
    selected_section = st.segmented_control(
        "资料处理阶段",
        options=INGESTION_WORKSPACE_SECTIONS,
        default=default_workspace if workspace_key not in st.session_state else None,
        key=workspace_key,
        width="stretch",
        label_visibility="collapsed",
    )
    selected_section = str(selected_section or default_workspace)
    st.caption(INGESTION_WORKSPACE_DESCRIPTIONS[selected_section])
    if selected_section == "概览":
        _render_ingestion_workbench(project_name, story_id, workbench)
    elif selected_section == "导入":
        _render_ingestion_wizard(
            project_name,
            story_id,
            source_type_options,
            knowledge_category_options,
            render_long_reference_importer=render_long_reference_importer,
        )
    elif selected_section == "处理":
        task_view_key = scoped_widget_key("ingestion_task_view", project_name, story_id)
        task_view = st.segmented_control(
            "任务类型",
            options=["后台任务", "长篇批次"],
            default="后台任务" if task_view_key not in st.session_state else None,
            key=task_view_key,
            label_visibility="collapsed",
        )
        if task_view == "长篇批次":
            render_long_reference_batch_manager(project_name, knowledge_category_options, expanded=True)
        else:
            render_ingestion_task_manager(project_name, story_id)
    else:
        management_view_key = scoped_widget_key("ingestion_management_view", project_name, story_id)
        management_options = ["原文资料", "健康检查", "资料包"]
        if str(st.session_state.get(management_view_key) or "") not in management_options:
            st.session_state.pop(management_view_key, None)
        management_view = st.segmented_control(
            "管理内容",
            options=management_options,
            default="原文资料" if management_view_key not in st.session_state else None,
            key=management_view_key,
            width="stretch",
            label_visibility="collapsed",
        )
        st.caption(
            {
                "原文资料": "查看保存的原文、切分片段、来源证据与修订记录。",
                "健康检查": "检查资料覆盖率、冲突、缺失证据和索引状态。",
                "资料包": "汇总项目资料，便于整体检查、归档或迁移。",
            }.get(str(management_view), "")
        )
        if management_view == "健康检查":
            render_ingestion_health_panel(project_name)
        elif management_view == "资料包":
            render_source_package_report_page(project_name)
        else:
            render_source_ledger_page(project_name)


def _render_ingestion_wizard(
    project_name: str,
    story_id: str,
    source_type_options: dict[str, str],
    knowledge_category_options: list[str],
    *,
    render_long_reference_importer,
) -> None:
    render_section_heading("导入资料", "上传文件和粘贴文本使用同一套解析、拆分与提取流程。")
    source_choice_key = scoped_widget_key("ingestion_source_choice", project_name, story_id)
    source_choice_map = {
        "长篇文本": "上传或粘贴",
        "长篇文件": "上传或粘贴",
        "粘贴资料": "上传或粘贴",
        "直接粘贴": "上传或粘贴",
        "网络检索": "网络资料",
        "手动资料卡": "手动条目",
    }
    if source_choice_key in st.session_state:
        raw_source_choice = str(st.session_state.get(source_choice_key) or "")
        normalized_source_choice = source_choice_map.get(raw_source_choice, raw_source_choice)
        st.session_state[source_choice_key] = (
            normalized_source_choice
            if normalized_source_choice in {"上传或粘贴", "网络资料", "手动条目"}
            else "上传或粘贴"
        )
    source_choice = st.segmented_control(
        "选择内容来源",
        options=["上传或粘贴", "网络资料", "手动条目"],
        default="上传或粘贴" if source_choice_key not in st.session_state else None,
        key=source_choice_key,
        width="stretch",
    )

    if source_choice == "上传或粘贴":
        render_long_reference_importer(
            project_name,
            source_type_options,
            knowledge_category_options,
        )
    elif source_choice == "网络资料":
        render_web_research_import(project_name, story_id)
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
    render_long_reference_batch_manager,
    render_source_package_report_page,
):
    current_story_id = str(st.session_state.get("active_story_id") or "default")
    workbench = build_ingestion_workbench(project_name)
    _render_ingestion_workspace(
        project_name,
        current_story_id,
        source_type_options,
        knowledge_category_options,
        render_long_reference_importer=render_long_reference_importer,
        render_ingestion_health_panel=render_ingestion_health_panel,
        render_ingestion_task_manager=render_ingestion_task_manager,
        render_source_ledger_page=render_source_ledger_page,
        render_long_reference_batch_manager=render_long_reference_batch_manager,
        render_source_package_report_page=render_source_package_report_page,
        workbench=workbench,
    )
