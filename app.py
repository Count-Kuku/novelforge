import importlib

import streamlit as st

import novelforge.services.memory as memory_module
memory_module = importlib.reload(memory_module)
list_projects = memory_module.list_projects
import novelforge.services.project_manager as project_manager_module
project_manager_module = importlib.reload(project_manager_module)
import novelforge.workflows.skills as skills_module
from novelforge.domain.setting_knowledge import build_generation_setting_context
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
    discussion_assets_panel as ui_discussion_assets_panel,
    evaluation as ui_evaluation,
    free_writing as ui_free_writing,
    ingestion_batch_guard as ui_ingestion_batch_guard,
    ingestion_task_estimate as ui_ingestion_task_estimate,
    ingestion_tasks as ui_ingestion_tasks,
    knowledge_management as ui_knowledge_management,
    layout as ui_layout,
    llm_settings as ui_llm_settings,
    long_reference_batch as ui_long_reference_batch,
    long_reference_importer as ui_long_reference_importer,
    navigation as ui_navigation,
    outline_page as ui_outline_page,
    prompt_option_tools as ui_prompt_option_tools,
    prompt_options_page as ui_prompt_options_page,
    project_overview as ui_project_overview,
    resource_browser_state as ui_resource_browser_state,
    resource_management as ui_resource_management,
    retrieval_center_page as ui_retrieval_center_page,
    retrieval_ingestion_page as ui_retrieval_ingestion_page,
    rules_page as ui_rules_page,
    settings_page as ui_settings_page,
    step_views as ui_step_views,
    streaming as ui_streaming,
    volume_outline_page as ui_volume_outline_page,
    web_research as ui_web_research,
)
from novelforge.workflows.ingestion_task_dispatcher import (
    ensure_ingestion_task_dispatcher,
    get_ingestion_task_dispatcher_status,
)
from novelforge.workflows.web_research_task_dispatcher import (
    ensure_web_research_task_dispatcher,
    get_web_research_task_dispatcher_status,
)

def _reload_live_ui_modules() -> dict[str, object]:
    global list_projects
    background_runtime_active = bool(
        get_ingestion_task_dispatcher_status().get("running")
        or get_web_research_task_dispatcher_status().get("running")
    )
    memory_helpers = memory_module if background_runtime_active else memory_module.reload_implementation_modules()
    list_projects = memory_helpers.list_projects
    importlib.reload(project_manager_module)
    if not background_runtime_active:
        skills_module.reload_implementation_modules()
    importlib.reload(ui_streaming)
    importlib.reload(ui_resource_browser_state)
    layout_helpers = importlib.reload(ui_layout)
    importlib.reload(ui_step_views)
    importlib.reload(ui_ingestion_batch_guard)
    importlib.reload(ui_ingestion_task_estimate)
    importlib.reload(ui_web_research)
    prompt_option_helpers = importlib.reload(ui_prompt_option_tools)
    importlib.reload(ui_discussion)
    # Streamlit keeps imported modules alive between script reruns. Reload the
    # navigation contract before app_shell so a long-running process cannot
    # combine an old navigation module with a newly edited shell module.
    importlib.reload(ui_navigation)
    return {
        "app_shell": importlib.reload(ui_app_shell),
        "layout": layout_helpers,
        "resource_management": importlib.reload(ui_resource_management),
        "settings": importlib.reload(ui_settings_page),
        "chapter": importlib.reload(ui_chapter_page),
        "creative_profile": importlib.reload(ui_creative_profile_page),
        "discussion_assets": importlib.reload(ui_discussion_assets_panel),
        "evaluation": importlib.reload(ui_evaluation),
        "free_writing": ui_free_writing.reload_components(),
        "ingestion_tasks": importlib.reload(ui_ingestion_tasks),
        "knowledge_management": importlib.reload(ui_knowledge_management),
        "llm_settings": importlib.reload(ui_llm_settings),
        "long_reference_batch": importlib.reload(ui_long_reference_batch),
        "long_reference_importer": importlib.reload(ui_long_reference_importer),
        "outline": importlib.reload(ui_outline_page),
        "prompt_option_tools": prompt_option_helpers,
        "prompt_options_page": importlib.reload(ui_prompt_options_page),
        "project_overview": importlib.reload(ui_project_overview),
        "retrieval_center": importlib.reload(ui_retrieval_center_page),
        "retrieval_ingestion": importlib.reload(ui_retrieval_ingestion_page),
        "rules": importlib.reload(ui_rules_page),
        "volume_outline": importlib.reload(ui_volume_outline_page),
        "arc_outline": importlib.reload(ui_arc_outline_page),
        "chapter_outline": importlib.reload(ui_chapter_outline_page),
    }


def render_memory_page(project_name: str, memory: dict, embedded: bool = False):
    current_story_id = st.session_state.get("active_story_id", "default")
    ui_settings_page.render_setting_items_editor(project_name, current_story_id, "story")


def render_retrieval_page(project_name: str, ui_modules: dict[str, object], mode: str = "center"):
    current_story_id = st.session_state.get("active_story_id", "default")

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
        knowledge_management = ui_modules["knowledge_management"]
        ui_modules["retrieval_ingestion"].render_retrieval_ingestion_page(
            project_name,
            source_type_options,
            knowledge_category_options,
            render_long_reference_importer=ui_modules["long_reference_importer"].render_long_reference_importer,
            render_ingestion_task_manager=ui_modules["ingestion_tasks"].render_ingestion_task_manager,
            render_ingestion_health_panel=knowledge_management.render_ingestion_health_panel,
            render_source_ledger_page=knowledge_management.render_source_ledger_page,
            render_auto_review_policy_panel=knowledge_management.render_auto_review_policy_panel,
            render_pending_knowledge_queue=knowledge_management.render_pending_knowledge_queue,
            render_auto_review_runs_panel=knowledge_management.render_auto_review_runs_panel,
            render_long_reference_batch_manager=ui_modules["long_reference_batch"].render_long_reference_batch_manager,
            render_knowledge_organizer=knowledge_management.render_knowledge_organizer,
            render_source_package_report_page=knowledge_management.render_source_package_report_page,
        )
        return

    ui_modules["retrieval_center"].render_retrieval_center_page(project_name, current_story_id)


def main():
    st.set_page_config(page_title="NovelForge", layout="wide")
    ui_modules = _reload_live_ui_modules()
    ensure_ingestion_task_dispatcher()
    ensure_web_research_task_dispatcher()
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
        ui_modules["llm_settings"].render_llm_settings_page()
    elif page == "项目总览":
        ui_modules["project_overview"].render_project_overview_page(project_name)
    elif page == "创作配置":
        ui_modules["creative_profile"].render_creative_profile_page(
            project_name,
            render_discussion_asset_candidates=ui_modules["discussion_assets"].render_discussion_asset_candidates,
        )
    elif page == "核心设定":
        ui_modules["settings"].render_settings_page(project_name, render_memory_page=render_memory_page)
    elif page == "自由创作":
        ui_modules["free_writing"].render_dynamic_generation_page(
            project_name,
            ui_modules["prompt_option_tools"]._render_prompt_option_capability_tools,
        )
    elif page == "项目资源":
        ui_modules["resource_management"].render_resource_management_page(project_name)
    elif page == "资料导入":
        render_retrieval_page(project_name, ui_modules, mode="ingestion")
    elif page == "检索中心":
        render_retrieval_page(project_name, ui_modules, mode="center")
    elif page == "生成规则":
        ui_modules["rules"].render_rules_page(project_name)
    elif page == "提示词选项":
        ui_modules["prompt_options_page"].render_prompt_options_page(project_name)
    elif page == "生成大纲":
        ui_modules["outline"].render_outline_page(
            project_name,
            render_discussion_asset_candidates=ui_modules["discussion_assets"].render_discussion_asset_candidates,
        )
    elif page == "分卷大纲":
        ui_modules["volume_outline"].render_volume_outline_page(
            project_name,
            render_discussion_asset_candidates=ui_modules["discussion_assets"].render_discussion_asset_candidates,
        )
    elif page == "剧情段大纲":
        ui_modules["arc_outline"].render_arc_outline_page(
            project_name,
            render_discussion_asset_candidates=ui_modules["discussion_assets"].render_discussion_asset_candidates,
        )
    elif page == "生成细纲":
        ui_modules["chapter_outline"].render_chapter_outline_page(
            project_name,
            render_discussion_asset_candidates=ui_modules["discussion_assets"].render_discussion_asset_candidates,
        )
    elif page == "正文生成":
        ui_modules["chapter"].render_chapter_page(project_name)
    elif page == "章节评价":
        ui_modules["evaluation"].render_evaluation_page(
            project_name,
            ui_modules["prompt_option_tools"]._render_prompt_option_capability_tools,
        )


if __name__ == "__main__":
    main()
