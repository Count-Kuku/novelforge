"""Project overview page."""
from __future__ import annotations

import html

import streamlit as st

from project_manager import delete_project, get_project_summary, rename_project
from ui.common import render_quick_action
from ui.layout import render_section_heading
from ui.resource_browser_state import render_resource_metric_link


def _render_overview_status(summary: dict, project_name: str) -> None:
    status_items = [
        ("书名", summary.get("title", project_name) or project_name),
        ("类型", summary.get("genre", "-") or "-"),
        ("原作对齐", summary.get("canon_mode", "-") or "-"),
        ("最近更新", summary.get("updated_at", "-") or "-"),
    ]
    item_html = "\n".join(
        f"""
        <div class="nf-status-item">
            <div class="nf-status-label">{html.escape(str(label))}</div>
            <div class="nf-status-value">{html.escape(str(value))}</div>
        </div>
        """
        for label, value in status_items
    )
    st.markdown(
        f"""
        <div class="nf-card">
            <div class="nf-card-title">当前创作状态</div>
            <div class="nf-card-copy">这里汇总当前故事的基础信息，方便开始写作前快速确认上下文。</div>
            <div class="nf-status-grid">{item_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_project_overview_page(project_name: str):
    story_id = st.session_state.get("active_story_id", "default")
    summary = get_project_summary(project_name, story_id=story_id)

    _render_overview_status(summary, project_name)

    render_section_heading("常用入口", "按创作流程排列：先确认配置和资料，再进入生成与资源管理。")
    action_col1, action_col2, action_col3 = st.columns(3)
    with action_col1:
        render_quick_action("讨论配置", "创作配置", "用自然语言说明想写什么，由讨论结果自动确定配置。")
    with action_col2:
        render_quick_action("整理资料", "资料导入", "导入原作、参考和长文本资料。")
    with action_col3:
        render_quick_action("开始生成", "正文生成", "根据需求或细纲写正文，可串联审阅和设定提炼。")

    action_col4, action_col5 = st.columns(2)
    with action_col4:
        render_quick_action("查看资源", "资源浏览器", "集中管理章节、报告和来源文件。")
    with action_col5:
        render_quick_action("调提示词", "提示词选项", "新增、复制或修改可切换的写作偏好。")

    render_section_heading("项目指标", "指标可直接定位到资源浏览器，便于检查当前故事资产是否齐全。")
    col1, col2, col3, col4, col5 = st.columns(5)
    render_resource_metric_link(col1, project_name, story_id, "正文章节", summary.get("chapter_count", 0), ["chapter_content"])
    render_resource_metric_link(col2, project_name, story_id, "细纲章节", summary.get("chapter_outline_count", 0), ["chapter_outline"])
    render_resource_metric_link(col3, project_name, story_id, "审阅数量", summary.get("review_count", 0), ["review"])
    render_resource_metric_link(col4, project_name, story_id, "分析报告", summary.get("analysis_count", 0), ["analysis"])
    render_resource_metric_link(col5, project_name, story_id, "评估报告", summary.get("evaluation_count", 0), ["evaluation"])

    with st.expander("高级：更多项目指标", expanded=False):
        advanced_cols_a = st.columns(4)
        render_resource_metric_link(advanced_cols_a[0], project_name, story_id, "分卷数量", summary.get("volume_count", 0), ["volume_outline"])
        render_resource_metric_link(advanced_cols_a[1], project_name, story_id, "剧情段数量", summary.get("arc_count", 0), ["arc_outline"])
        render_resource_metric_link(advanced_cols_a[2], project_name, story_id, "流水线记录", summary.get("run_count", 0), ["run"])
        render_resource_metric_link(advanced_cols_a[3], project_name, story_id, "外部资料", summary.get("retrieval_source_count", 0), ["source"])

        advanced_cols_b = st.columns(3)
        render_resource_metric_link(advanced_cols_b[0], project_name, story_id, "结构化知识", summary.get("knowledge_item_count", 0), ["knowledge_item"])
        render_resource_metric_link(advanced_cols_b[1], project_name, story_id, "待确认知识", summary.get("pending_knowledge_count", 0), ["pending_knowledge"])
        render_resource_metric_link(advanced_cols_b[2], project_name, story_id, "资料批次", summary.get("long_reference_batch_count", 0), ["long_reference_batch"])

        col10, col11 = st.columns(2)
        render_resource_metric_link(col10, project_name, story_id, "已批准分卷讨论", summary.get("approved_volume_count", 0), ["volume_discussion"])
        render_resource_metric_link(col11, project_name, story_id, "已批准剧情段讨论", summary.get("approved_arc_count", 0), ["arc_discussion"])
        st.caption(f"章节摘要={summary.get('chapter_summary_count', 0)} / 资源文件数={summary.get('resource_file_count', 0)}")

    render_section_heading("项目维护")
    with st.expander("项目设置", expanded=False):
        new_name = st.text_input("重命名项目", value=project_name, key=f"rename_project_input_{project_name}")
        if st.button("保存新项目名"):
            try:
                renamed = rename_project(project_name, new_name)
                st.session_state["project_name"] = renamed
                st.success(f"项目已重命名为 `{renamed}`。")
                st.rerun()
            except Exception as exc:
                st.error(f"项目重命名失败：{exc}")

    with st.expander("危险操作", expanded=False):
        st.warning("删除项目会移除该项目下的全部设定、章节、审阅、分析、检索资料和运行记录。")
        confirm_value = st.text_input("输入项目名以确认删除", key=f"delete_project_confirm_{project_name}")
        if st.button("删除当前项目"):
            if confirm_value.strip() != project_name:
                st.error("项目名确认不匹配，已取消删除。")
            else:
                deleted = delete_project(project_name)
                if deleted:
                    st.session_state.pop("project_name", None)
                    st.success(f"项目 `{project_name}` 已删除。")
                    st.rerun()
                else:
                    st.error("项目删除失败，目标项目可能不存在。")

