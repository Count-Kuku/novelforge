"""Project overview page."""
from __future__ import annotations

import html

import streamlit as st

from novelforge.services.project_manager import delete_project, get_project_summary, rename_project
from novelforge.services.memory import set_active_project_name
from novelforge.services.model_readiness import get_model_readiness
from ui.common import render_quick_action
from ui.layout import render_section_heading
from ui.llm_usage import render_usage_dashboard
from ui.resource_browser_state import render_resource_metric_link


def _format_updated_at(value) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    return text.replace("T", " ")[:16]


def _render_overview_status(summary: dict, project_name: str) -> None:
    status_items = [
        ("书名", summary.get("title", project_name) or project_name),
        ("类型", summary.get("genre", "-") or "-"),
        ("原作参考", summary.get("canon_mode", "-") or "-"),
        ("最近更新", _format_updated_at(summary.get("updated_at"))),
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
            <div class="nf-card-copy">先确认当前故事和作品信息，再从下方选择下一步要做的事。</div>
            <div class="nf-status-grid">{item_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_project_overview_page(project_name: str):
    story_id = st.session_state.get("active_story_id", "default")
    summary = get_project_summary(project_name, story_id=story_id)

    _render_overview_status(summary, project_name)

    readiness = get_model_readiness()
    if readiness.get("chat_status") in {"missing", "failed"}:
        st.error(
            f"模型尚未就绪：{readiness.get('chat_message') or '请先完成模型接入。'}"
            "前往“模型与费用”修复后即可继续当前项目。"
        )
    elif readiness.get("chat_status") == "unverified":
        st.info("对话模型配置尚未验证；建议先在“模型与费用”中测试连接。")
    if readiness.get("retrieval_mode") == "lexical":
        st.caption(
            f"资料检索：关键词模式。{readiness.get('embedding_message') or ''}"
        )
    else:
        st.caption("资料检索：语义 + 关键词混合模式。")

    render_section_heading("下一步做什么", "第一次使用可先确定创作方向和整理资料；想直接写，也可以进入自由创作。")
    action_col1, action_col2, action_col3 = st.columns(3)
    with action_col1:
        render_quick_action("确定创作方向", "创作配置", "说清楚想写什么，系统会整理篇幅、原作参考程度和推荐流程。")
    with action_col2:
        render_quick_action("导入与整理资料", "资料导入", "导入原作、参考文本或手动资料卡，让后续生成能够复用。")
    with action_col3:
        render_quick_action("自由创作", "自由创作", "输入要求立即生成片段，也可以继续交流、续写并整理新设定。")

    with st.expander("更多常用入口", expanded=False):
        action_col4, action_col5, action_col6 = st.columns(3)
        with action_col4:
            render_quick_action("按章节写正文", "正文生成", "根据章节需求或细纲写正式正文，并可继续快速或综合审阅。")
        with action_col5:
            render_quick_action("查找项目内容", "项目资源", "集中查找大纲、章节、报告、资料与创作记录。")
        with action_col6:
            render_quick_action("调整写作偏好", "提示词选项", "新增、复制或修改可切换的文风、节奏和描写重点。")

    render_section_heading("项目指标", "点击有数量的指标即可查看对应内容。")
    col1, col2, col3, col4, col5 = st.columns(5)
    render_resource_metric_link(col1, project_name, story_id, "正文章节", summary.get("chapter_count", 0), ["chapter_content"])
    render_resource_metric_link(col2, project_name, story_id, "细纲章节", summary.get("chapter_outline_count", 0), ["chapter_outline"])
    render_resource_metric_link(col3, project_name, story_id, "快速审阅", summary.get("review_count", 0), ["review"])
    render_resource_metric_link(col4, project_name, story_id, "分析报告", summary.get("analysis_count", 0), ["analysis"])
    render_resource_metric_link(col5, project_name, story_id, "综合审阅", summary.get("evaluation_count", 0), ["evaluation"])

    with st.expander("高级：更多项目指标", expanded=False):
        advanced_cols_a = st.columns(5)
        render_resource_metric_link(advanced_cols_a[0], project_name, story_id, "分卷数量", summary.get("volume_count", 0), ["volume_outline"])
        render_resource_metric_link(advanced_cols_a[1], project_name, story_id, "剧情段数量", summary.get("arc_count", 0), ["arc_outline"])
        render_resource_metric_link(advanced_cols_a[2], project_name, story_id, "自动生成记录", summary.get("run_count", 0), ["run"])
        render_resource_metric_link(advanced_cols_a[3], project_name, story_id, "外部资料", summary.get("retrieval_source_count", 0), ["source"])
        render_resource_metric_link(advanced_cols_a[4], project_name, story_id, "自由创作会话", summary.get("creative_session_count", 0), ["creative_session"])

        advanced_cols_b = st.columns(3)
        render_resource_metric_link(advanced_cols_b[0], project_name, story_id, "知识库条目", summary.get("knowledge_item_count", 0), ["knowledge_item"])
        render_resource_metric_link(advanced_cols_b[1], project_name, story_id, "待审核设定", summary.get("pending_knowledge_count", 0), ["pending_knowledge"])
        render_resource_metric_link(advanced_cols_b[2], project_name, story_id, "资料批次", summary.get("long_reference_batch_count", 0), ["long_reference_batch"])

        col10, col11 = st.columns(2)
        render_resource_metric_link(col10, project_name, story_id, "已保存分卷讨论", summary.get("approved_volume_count", 0), ["volume_discussion"])
        render_resource_metric_link(col11, project_name, story_id, "已保存剧情段讨论", summary.get("approved_arc_count", 0), ["arc_discussion"])
        st.caption(f"章节摘要：{summary.get('chapter_summary_count', 0)} · 资源文件：{summary.get('resource_file_count', 0)}")

    render_section_heading("模型用量", "查看当前故事的 Token、费用趋势和 Agent 调用分布。")
    with st.expander("查看用量详情", expanded=False):
        render_usage_dashboard(
            project_name=project_name,
            story_id=story_id,
            key_prefix=f"project_usage_{project_name}_{story_id}",
        )

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
        st.warning(
            "\u5220\u9664\u9879\u76ee\u4f1a\u4ece\u9879\u76ee\u5217\u79fb\u9664\uff0c\u5e76\u628a\u9879\u76ee\u76ee\u5f55\u9694\u79bb\u5230 "
            "data/deleted_projects \u4f5c\u4e3a\u5907\u4efd\u3002\u5f53\u524d\u6ca1\u6709\u4e00\u952e\u6062\u590d\u5165\u53e3\uff1b\u6062\u590d\u65f6\u8fd8\u9700\u6e05\u9664"
            "\u9879\u76ee\u7ef4\u62a4\u9501\u5e76\u91cd\u65b0\u767b\u8bb0\uff0c\u4e0d\u8981\u53ea\u5c06\u76ee\u5f55\u79fb\u56de\u3002"
        )
        confirm_value = st.text_input("\u8f93\u5165\u9879\u76ee\u540d\u4ee5\u786e\u8ba4\u5220\u9664", key=f"delete_project_confirm_{project_name}")
        if st.button("\u5220\u9664\u5f53\u524d\u9879\u76ee", key=f"delete_project_{project_name}"):
            if confirm_value.strip() != project_name:
                st.error("\u9879\u76ee\u540d\u786e\u8ba4\u4e0d\u5339\u914d\uff0c\u5df2\u53d6\u6d88\u5220\u9664\u3002")
            else:
                try:
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
                except Exception as exc:
                    st.error(f"\u9879\u76ee\u5220\u9664\u5931\u8d25\uff1a{exc}")
