import streamlit as st

from memory import list_projects
from setting_knowledge import build_generation_setting_context
from ui.app_shell import init_project_state, render_sidebar
from ui.arc_outline_page import render_arc_outline_page
from ui.chapter_page import render_chapter_page
from ui.chapter_outline_page import render_chapter_outline_page
from ui.evaluation import render_evaluation_page
from ui.dynamic_generation import render_dynamic_generation_page
from ui.discussion_assets_panel import render_discussion_asset_candidates
from ui.creative_profile_page import render_creative_profile_page
from ui.knowledge_management import (
    render_auto_review_policy_panel,
    render_auto_review_runs_panel,
    render_ingestion_health_panel,
    render_knowledge_organizer,
    render_pending_knowledge_queue,
    render_source_ledger_page,
    render_source_package_report_page,
)
from ui.labels import (
    KNOWLEDGE_CATEGORY_LABELS,
)
from ui.layout import apply_app_style, render_app_header
from ui.llm_settings import render_llm_settings_page
from ui.long_reference_batch import render_long_reference_batch_manager
from ui.long_reference_importer import render_long_reference_importer
from ui.project_overview import render_project_overview_page
from ui.outline_page import render_outline_page
from ui.prompt_options_page import render_prompt_options_page
from ui.prompt_option_tools import _render_prompt_option_capability_tools
from ui.retrieval_center_page import render_retrieval_center_page
from ui.retrieval_ingestion_page import render_retrieval_ingestion_page
from ui.rules_page import render_rules_page
from ui.resource_management import render_resource_management_page
from ui.settings_page import render_setting_items_editor, render_settings_page
from ui.volume_outline_page import render_volume_outline_page


WEB_REFERENCE_INGESTION_ENABLED = False


def render_memory_page(project_name: str, memory: dict, embedded: bool = False):
    current_story_id = st.session_state.get("active_story_id", "default")
    render_setting_items_editor(project_name, current_story_id, "story")


def render_retrieval_page(project_name: str, mode: str = "center"):
    current_story_id = st.session_state.get("active_story_id", "default")
    if mode == "ingestion":
        st.subheader("资料导入")
        st.caption("导入原作资料、参考资料和样本文本，并把资料整理为检索条目或结构化知识。")
    else:
        st.subheader("检索中心")
        st.caption("管理检索索引、测试资料召回，并处理项目资料与原作/参考资料之间的潜在冲突。")

    source_type_options = {
        "external_source": "通用资料",
        "external_character_sheet": "角色资料",
        "external_location_sheet": "地点资料",
        "external_organization_sheet": "组织资料",
        "external_timeline_note": "时间线资料",
        "external_canon_event": "原作事件",
        "external_world_rule": "世界规则",
        "external_artifact_note": "道具资料",
    }
    knowledge_category_options = list(KNOWLEDGE_CATEGORY_LABELS.keys())

    if mode == "ingestion":
        render_retrieval_ingestion_page(
            project_name,
            source_type_options,
            knowledge_category_options,
            render_long_reference_importer=render_long_reference_importer,
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

    render_retrieval_center_page(project_name, current_story_id)


def main():
    st.set_page_config(page_title="NovelForge", layout="wide")
    apply_app_style()

    project_name = init_project_state()
    projects = list_projects()
    page = render_sidebar(project_name, projects)

    if project_name:
        story_id = st.session_state.get("active_story_id", "default")
        memory = build_generation_setting_context(project_name, story_id)
    else:
        memory = None
        st.info("当前还没有项目。可先进入“模型配置”填写服务地址与密钥，或点击侧边栏“新建项目”开始创建。")

    render_app_header(project_name, page, memory)

    if not project_name and page != "模型配置":
        st.stop()
    elif page == "模型配置":
        render_llm_settings_page()
    elif page == "项目总览":
        render_project_overview_page(project_name)
    elif page == "创作配置":
        render_creative_profile_page(project_name, render_discussion_asset_candidates=render_discussion_asset_candidates)
    elif page == "核心设定":
        render_settings_page(project_name, render_memory_page=render_memory_page)
    elif page == "快速生成":
        render_dynamic_generation_page(project_name, _render_prompt_option_capability_tools)
    elif page == "资源浏览器":
        render_resource_management_page(project_name)
    elif page == "资料导入":
        render_retrieval_page(project_name, mode="ingestion")
    elif page == "检索中心":
        render_retrieval_page(project_name, mode="center")
    elif page == "生成规则":
        render_rules_page(project_name)
    elif page == "提示词选项":
        render_prompt_options_page(project_name)
    elif page == "生成大纲":
        render_outline_page(project_name, render_discussion_asset_candidates=render_discussion_asset_candidates)
    elif page == "分卷大纲":
        render_volume_outline_page(project_name, render_discussion_asset_candidates=render_discussion_asset_candidates)
    elif page == "剧情段大纲":
        render_arc_outline_page(project_name, render_discussion_asset_candidates=render_discussion_asset_candidates)
    elif page == "生成细纲":
        render_chapter_outline_page(project_name, render_discussion_asset_candidates=render_discussion_asset_candidates)
    elif page == "正文生成":
        render_chapter_page(project_name)
    elif page == "章节评价":
        render_evaluation_page(project_name, _render_prompt_option_capability_tools)


if __name__ == "__main__":
    main()

