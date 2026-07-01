import importlib

import streamlit as st

import memory as memory_module
memory_module = importlib.reload(memory_module)
list_projects = memory_module.list_projects
import project_manager as project_manager_module
project_manager_module = importlib.reload(project_manager_module)
import skills as skills_module
from setting_knowledge import build_generation_setting_context
from ui.evaluation import render_evaluation_page
from ui.dynamic_generation import render_dynamic_generation_page
from ui.discussion_assets_panel import render_discussion_asset_candidates
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
from ui import (
    app_shell as ui_app_shell,
    arc_outline_page as ui_arc_outline_page,
    chapter_outline_page as ui_chapter_outline_page,
    chapter_page as ui_chapter_page,
    creative_profile_page as ui_creative_profile_page,
    discussion as ui_discussion,
    layout as ui_layout,
    outline_page as ui_outline_page,
    project_overview as ui_project_overview,
    resource_browser_state as ui_resource_browser_state,
    resource_management as ui_resource_management,
    settings_page as ui_settings_page,
    streaming as ui_streaming,
    volume_outline_page as ui_volume_outline_page,
)
from ui.llm_settings import render_llm_settings_page
from ui.long_reference_batch import render_long_reference_batch_manager
from ui.long_reference_importer import render_long_reference_importer
from ui.prompt_options_page import render_prompt_options_page
from ui.prompt_option_tools import _render_prompt_option_capability_tools
from ui.retrieval_center_page import render_retrieval_center_page
from ui.retrieval_ingestion_page import render_retrieval_ingestion_page
from ui.rules_page import render_rules_page

def _reload_live_ui_modules() -> dict[str, object]:
    global list_projects
    memory_helpers = importlib.reload(memory_module)
    list_projects = memory_helpers.list_projects
    importlib.reload(project_manager_module)
    importlib.reload(skills_module)
    importlib.reload(ui_streaming)
    importlib.reload(ui_resource_browser_state)
    layout_helpers = importlib.reload(ui_layout)
    importlib.reload(ui_discussion)
    return {
        "app_shell": importlib.reload(ui_app_shell),
        "layout": layout_helpers,
        "resource_management": importlib.reload(ui_resource_management),
        "settings": importlib.reload(ui_settings_page),
        "chapter": importlib.reload(ui_chapter_page),
        "creative_profile": importlib.reload(ui_creative_profile_page),
        "outline": importlib.reload(ui_outline_page),
        "project_overview": importlib.reload(ui_project_overview),
        "volume_outline": importlib.reload(ui_volume_outline_page),
        "arc_outline": importlib.reload(ui_arc_outline_page),
        "chapter_outline": importlib.reload(ui_chapter_outline_page),
    }


def render_memory_page(project_name: str, memory: dict, embedded: bool = False):
    current_story_id = st.session_state.get("active_story_id", "default")
    ui_settings_page.render_setting_items_editor(project_name, current_story_id, "story")


def render_retrieval_page(project_name: str, mode: str = "center"):
    current_story_id = st.session_state.get("active_story_id", "default")
    if mode == "ingestion":
        st.subheader("资料导入")
        st.caption("导入原作资料、参考资料和样本文本，并把资料整理为检索条目或知识库条目。")
    else:
        st.subheader("检索中心")
        st.caption("管理检索索引、测试资料匹配，并处理项目资料与原作/参考资料之间的潜在冲突。")

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
    ui_modules = _reload_live_ui_modules()
    layout_helpers = ui_modules["layout"]
    layout_helpers.apply_app_style()

    app_shell = ui_modules["app_shell"]
    project_name = app_shell.init_project_state()
    projects = list_projects()
    page = app_shell.render_sidebar(project_name, projects)

    if project_name:
        story_id = st.session_state.get("active_story_id", "default")
        memory = build_generation_setting_context(project_name, story_id)
    else:
        memory = None
        st.info("当前还没有项目。可先进入“模型配置”填写服务地址与密钥，或点击侧边栏“新建项目”开始创建。")

    layout_helpers.render_app_header(project_name, page, memory)
    project_load_error = app_shell.get_project_load_error()
    if project_load_error and not project_name:
        error_project = str(project_load_error.get("project_name") or "")
        error_message = str(project_load_error.get("message") or "")
        st.error(f"\u9879\u76ee {error_project} \u6682\u65f6\u4e0d\u53ef\u7528\uff1a{error_message}")
        st.caption("\u53ef\u4ee5\u5728\u4fa7\u8fb9\u680f\u5207\u6362\u5230\u5176\u5b83\u9879\u76ee\uff0c\u6216\u5728\u9879\u76ee\u6587\u4ef6\u6062\u590d\u540e\u5237\u65b0\u91cd\u8bd5\u3002")
    created_project_notice = app_shell.consume_project_creation_notice()
    if created_project_notice:
        st.success(f"已创建并进入项目：{created_project_notice}")
    created_story_notice = app_shell.consume_story_creation_notice()
    if created_story_notice:
        st.success(created_story_notice)

    if not project_name and page != "模型配置":
        st.stop()
    elif page == "模型配置":
        render_llm_settings_page()
    elif page == "项目总览":
        ui_modules["project_overview"].render_project_overview_page(project_name)
    elif page == "创作配置":
        ui_modules["creative_profile"].render_creative_profile_page(project_name, render_discussion_asset_candidates=render_discussion_asset_candidates)
    elif page == "核心设定":
        ui_modules["settings"].render_settings_page(project_name, render_memory_page=render_memory_page)
    elif page == "快速生成":
        render_dynamic_generation_page(project_name, _render_prompt_option_capability_tools)
    elif page == "项目资源":
        ui_modules["resource_management"].render_resource_management_page(project_name)
    elif page == "资料导入":
        render_retrieval_page(project_name, mode="ingestion")
    elif page == "检索中心":
        render_retrieval_page(project_name, mode="center")
    elif page == "生成规则":
        render_rules_page(project_name)
    elif page == "提示词选项":
        render_prompt_options_page(project_name)
    elif page == "生成大纲":
        ui_modules["outline"].render_outline_page(project_name, render_discussion_asset_candidates=render_discussion_asset_candidates)
    elif page == "分卷大纲":
        ui_modules["volume_outline"].render_volume_outline_page(project_name, render_discussion_asset_candidates=render_discussion_asset_candidates)
    elif page == "剧情段大纲":
        ui_modules["arc_outline"].render_arc_outline_page(project_name, render_discussion_asset_candidates=render_discussion_asset_candidates)
    elif page == "生成细纲":
        ui_modules["chapter_outline"].render_chapter_outline_page(project_name, render_discussion_asset_candidates=render_discussion_asset_candidates)
    elif page == "正文生成":
        ui_modules["chapter"].render_chapter_page(project_name)
    elif page == "章节评价":
        render_evaluation_page(project_name, _render_prompt_option_capability_tools)


if __name__ == "__main__":
    main()
