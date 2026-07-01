"""Project overview page."""
from __future__ import annotations

import html

import streamlit as st

from project_manager import delete_project, get_project_summary, rename_project
from memory import set_active_project_name
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
        render_quick_action("查看资源", "项目资源", "集中管理章节、报告和资料。")
    with action_col5:
        render_quick_action("调提示词", "提示词选项", "新增、复制或修改可切换的写作偏好。")

    render_section_heading("项目指标", "点击有数量的指标即可查看对应内容。")
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
        render_resource_metric_link(advanced_cols_b[0], project_name, story_id, "知识库条目", summary.get("knowledge_item_count", 0), ["knowledge_item"])
        render_resource_metric_link(advanced_cols_b[1], project_name, story_id, "待确认知识", summary.get("pending_knowledge_count", 0), ["pending_knowledge"])
        render_resource_metric_link(advanced_cols_b[2], project_name, story_id, "资料批次", summary.get("long_reference_batch_count", 0), ["long_reference_batch"])

        col10, col11 = st.columns(2)
        render_resource_metric_link(col10, project_name, story_id, "已保存分卷讨论", summary.get("approved_volume_count", 0), ["volume_discussion"])
        render_resource_metric_link(col11, project_name, story_id, "已保存剧情段讨论", summary.get("approved_arc_count", 0), ["arc_discussion"])
        st.caption(f"章节摘要={summary.get('chapter_summary_count', 0)} / 资源文件数={summary.get('resource_file_count', 0)}")

    render_section_heading("\u9879\u76ee\u7ef4\u62a4")
    with st.expander("\u9879\u76ee\u8bbe\u7f6e", expanded=False):
        new_name = st.text_input("\u91cd\u547d\u540d\u9879\u76ee", value=project_name, key=f"rename_project_input_{project_name}")
        if st.button("\u4fdd\u5b58\u65b0\u9879\u76ee\u540d", key=f"save_project_rename_{project_name}"):
            try:
                renamed = rename_project(project_name, new_name)
                st.session_state["project_name"] = renamed
                st.session_state["project_switcher"] = renamed
                set_active_project_name(renamed)
                st.success(f"\u9879\u76ee\u5df2\u91cd\u547d\u540d\u4e3a `{renamed}`\u3002")
                st.rerun()
            except Exception as exc:
                st.error(f"\u9879\u76ee\u91cd\u547d\u540d\u5931\u8d25\uff1a{exc}")

    with st.expander("\u5371\u9669\u64cd\u4f5c", expanded=False):
        st.warning("\u5220\u9664\u9879\u76ee\u4f1a\u4ece\u9879\u76ee\u5217\u8868\u79fb\u9664\uff0c\u5e76\u628a\u9879\u76ee\u76ee\u5f55\u79fb\u52a8\u5230 data/deleted_projects \u4ee5\u4fbf\u9700\u8981\u65f6\u624b\u52a8\u6062\u590d\u3002")
        confirm_value = st.text_input("\u8f93\u5165\u9879\u76ee\u540d\u4ee5\u786e\u8ba4\u5220\u9664", key=f"delete_project_confirm_{project_name}")
        if st.button("\u5220\u9664\u5f53\u524d\u9879\u76ee", key=f"delete_project_{project_name}"):
            if confirm_value.strip() != project_name:
                st.error("\u9879\u76ee\u540d\u786e\u8ba4\u4e0d\u5339\u914d\uff0c\u5df2\u53d6\u6d88\u5220\u9664\u3002")
            else:
                deleted = delete_project(project_name)
                if deleted:
                    st.session_state.pop("project_name", None)
                    st.session_state.pop("active_story_id", None)
                    st.session_state["project_switcher"] = ""
                    set_active_project_name(None)
                    st.success(f"\u9879\u76ee `{project_name}` \u5df2\u79fb\u5165 data/deleted_projects\u3002")
                    st.rerun()
                else:
                    st.error("\u9879\u76ee\u5220\u9664\u5931\u8d25\uff0c\u76ee\u6807\u9879\u76ee\u53ef\u80fd\u4e0d\u5b58\u5728\u3002")
