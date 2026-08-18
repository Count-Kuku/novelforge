"""Application shell helpers: project initialization and sidebar navigation."""
from __future__ import annotations

import importlib
import logging

import streamlit as st

from novelforge.services.memory import (
    copy_story_settings,
    create_project,
    create_story,
    get_active_project_name,
    get_active_story_id,
    list_projects,
    project_data_exists,
    list_stories,
    load_creative_profile,
    migrate_project_to_stories,
    set_active_project_name,
    set_active_story,
)
from novelforge.services.project_manager import get_project_summary
from ui.common import developer_mode_enabled, scoped_widget_key
from ui.llm_usage import render_sidebar_usage_summary
from ui import navigation as _navigation


_NAVIGATION_CONTRACT = (
    "TOP_LEVEL_PAGES",
    "DEFAULT_PAGE",
    "LEGACY_PAGE_ALIASES",
    "build_navigation_intent",
    "canonical_legacy_page",
    "PAGE_DESCRIPTIONS",
    "PAGE_ICONS",
    "PAGE_LABELS",
    "page_groups_for_story",
)
if not all(hasattr(_navigation, name) for name in _NAVIGATION_CONTRACT):
    # A running Streamlit process may keep the pre-refactor module object in
    # sys.modules. Repair it before binding the shell's navigation constants.
    _navigation = importlib.reload(_navigation)

TOP_LEVEL_PAGES = _navigation.TOP_LEVEL_PAGES
DEFAULT_PAGE = _navigation.DEFAULT_PAGE
LEGACY_PAGE_ALIASES = _navigation.LEGACY_PAGE_ALIASES
PAGE_DESCRIPTIONS = _navigation.PAGE_DESCRIPTIONS
PAGE_ICONS = _navigation.PAGE_ICONS
PAGE_LABELS = _navigation.PAGE_LABELS
build_navigation_intent = _navigation.build_navigation_intent
canonical_legacy_page = _navigation.canonical_legacy_page
navigation_page_groups_for_story = _navigation.page_groups_for_story


LOGGER = logging.getLogger("novelforge.ui.app_shell")

NEW_PROJECT_INPUT_KEY = "new_project_name_input"

# 兼容旧规划状态读取；普通侧栏不再展示这组页面。
PAGE_GROUPS = _navigation.LEGACY_PAGE_GROUPS

NEW_PROJECT_DIALOG_FLAG = "show_new_project_dialog"
PROJECT_CREATION_NOTICE_KEY = "project_creation_notice"
PENDING_PROJECT_SWITCH_KEY = "pending_project_switch"
PROJECT_LOAD_ERROR_KEY = "project_load_error"
STORY_CREATION_NOTICE_KEY = "story_creation_notice"
PENDING_STORY_SWITCH_KEY = "pending_story_switch"


def _open_new_project_dialog() -> None:
    st.session_state[NEW_PROJECT_DIALOG_FLAG] = True
    st.session_state[NEW_PROJECT_INPUT_KEY] = ""


def _close_new_project_dialog() -> None:
    st.session_state.pop(NEW_PROJECT_DIALOG_FLAG, None)
    st.session_state.pop(NEW_PROJECT_INPUT_KEY, None)


def consume_project_creation_notice() -> str:
    notice = st.session_state.pop(PROJECT_CREATION_NOTICE_KEY, "")
    if isinstance(notice, dict):
        return str(notice.get("project_name") or "").strip()
    return str(notice or "").strip()


def consume_story_creation_notice() -> str:
    notice = st.session_state.pop(STORY_CREATION_NOTICE_KEY, "")
    if not isinstance(notice, dict):
        return str(notice or "").strip()
    story_name = str(notice.get("story_name") or notice.get("story_id") or "").strip()
    action = str(notice.get("action") or "created")
    if not story_name:
        return ""
    if action == "copied":
        return f"已复制并进入故事：{story_name}"
    return f"已创建并进入故事：{story_name}"


def _set_project_load_error(project_name: str, message: str) -> None:
    st.session_state[PROJECT_LOAD_ERROR_KEY] = {
        "project_name": str(project_name or ""),
        "message": str(message or ""),
    }


def _clear_project_load_error() -> None:
    st.session_state.pop(PROJECT_LOAD_ERROR_KEY, None)


def get_project_load_error() -> dict:
    error = st.session_state.get(PROJECT_LOAD_ERROR_KEY)
    return error if isinstance(error, dict) else {}


def switch_to_story(project_name: str, story_id: str, *, target_page: str | None = None) -> None:
    set_active_story(project_name, story_id)
    st.session_state["active_story_id"] = story_id
    st.session_state[PENDING_STORY_SWITCH_KEY] = story_id
    if target_page:
        st.session_state["pending_navigation_intent"] = build_navigation_intent(
            target_page,
            developer_mode=developer_mode_enabled(),
        )


def activate_story_after_creation(
    project_name: str,
    story_meta: dict,
    *,
    target_page: str = "创作配置",
    notice_action: str = "created",
) -> None:
    story_id = str(story_meta.get("story_id") or "default")
    story_name = str(story_meta.get("name") or story_id)
    switch_to_story(project_name, story_id, target_page=target_page)
    st.session_state[STORY_CREATION_NOTICE_KEY] = {
        "story_id": story_id,
        "story_name": story_name,
        "action": notice_action,
    }


def is_story_creative_profile_configured(project_name: str | None, story_id: str = "default") -> bool:
    if not project_name:
        return False
    try:
        profile = load_creative_profile(project_name, story_id=story_id)
        return bool(profile.get("is_configured"))
    except Exception as exc:
        LOGGER.warning(
            "Failed to inspect creative profile for project=%s story=%s: %s",
            project_name,
            story_id,
            exc,
        )
        return False

def planning_pages_for_story(project_name: str | None, story_id: str = "default") -> list[str]:
    return list(PAGE_GROUPS.get("规划", ["创作配置", "生成大纲", "分卷大纲", "剧情段大纲", "生成细纲"]))

def page_groups_for_story(project_name: str | None, story_id: str = "default") -> dict[str, list[str]]:
    return navigation_page_groups_for_story(
        project_name=project_name,
        planning_pages=planning_pages_for_story(project_name, story_id),
        developer_mode=developer_mode_enabled(),
    )

def _project_creation_error_message(exc: Exception) -> str:
    message = str(exc)
    if isinstance(exc, FileExistsError):
        if "not recognized as a project" in message:
            return "\u540c\u540d\u6570\u636e\u76ee\u5f55\u5df2\u5b58\u5728\uff0c\u4f46\u7f3a\u5c11\u53ef\u8bc6\u522b\u7684\u9879\u76ee\u6570\u636e\u6807\u8bb0\u3002\u8bf7\u5148\u91cd\u547d\u540d\u6216\u79fb\u8d70\u8be5\u76ee\u5f55\uff0c\u6216\u8865\u5168 stories/memory/rules/retrieval \u7b49\u9879\u76ee\u6570\u636e\u3002"
        if "already exists" in message:
            return "\u8be5\u9879\u76ee\u5df2\u5b58\u5728\uff0c\u8bf7\u4f7f\u7528\u9879\u76ee\u5207\u6362\u3002"
    return f"\u9879\u76ee\u521b\u5efa\u5931\u8d25\uff1a{message}"


@st.dialog("新建项目")
def render_new_project_dialog(existing_projects: list[str]):
    candidate_name = st.text_input("\u9879\u76ee\u540d", key=NEW_PROJECT_INPUT_KEY).strip()
    col1, col2 = st.columns(2)

    if col1.button("\u786e\u8ba4\u521b\u5efa", width="stretch"):
        if not candidate_name:
            st.error("\u9879\u76ee\u540d\u4e0d\u80fd\u4e3a\u7a7a\u3002")
            return
        if candidate_name in existing_projects:
            st.error("\u8be5\u9879\u76ee\u5df2\u5b58\u5728\uff0c\u8bf7\u4f7f\u7528\u9879\u76ee\u5207\u6362\u3002")
            return

        try:
            created_project = create_project(candidate_name)
            st.session_state["project_name"] = created_project
            set_active_project_name(created_project)
            st.session_state["active_story_id"] = get_active_story_id(created_project)
        except Exception as exc:
            st.error(_project_creation_error_message(exc))
            return

        _clear_project_load_error()
        st.session_state[PENDING_PROJECT_SWITCH_KEY] = created_project
        st.session_state[PROJECT_CREATION_NOTICE_KEY] = {"project_name": created_project}
        st.session_state["pending_navigation_intent"] = build_navigation_intent(
            DEFAULT_PAGE,
            developer_mode=developer_mode_enabled(),
        )
        _close_new_project_dialog()
        st.rerun()

    if col2.button("\u53d6\u6d88", width="stretch"):
        _close_new_project_dialog()
        st.rerun()

def init_project_state() -> str | None:
    projects = list_projects()
    project_name = str(st.session_state.get("project_name") or "").strip()
    if not project_name:
        project_name = get_active_project_name()

    if not project_name:
        st.session_state.pop("active_story_id", None)
        return None

    if project_name not in projects:
        if project_data_exists(project_name):
            _set_project_load_error(project_name, "\u9879\u76ee\u76ee\u5f55\u4e0d\u662f\u53ef\u6253\u5f00\u9879\u76ee\uff08\u53ef\u80fd\u662f\u5185\u90e8\u9a8c\u8bc1\u76ee\u5f55\uff0c\u6216\u7f3a\u5c11 stories/memory/rules/retrieval \u7b49\u9879\u76ee\u6570\u636e\u6807\u8bb0\uff09\u3002")
        else:
            _set_project_load_error(project_name, "\u9879\u76ee\u6570\u636e\u76ee\u5f55\u4e0d\u5b58\u5728\uff0c\u53ef\u80fd\u5df2\u88ab\u5220\u9664\u6216\u79fb\u52a8\u3002")
        st.session_state.pop("project_name", None)
        st.session_state.pop("active_story_id", None)
        st.session_state["project_switcher"] = ""
        return None

    if not project_data_exists(project_name):
        _set_project_load_error(project_name, "\u9879\u76ee\u6570\u636e\u76ee\u5f55\u4e0d\u5b58\u5728\uff0c\u53ef\u80fd\u5df2\u88ab\u5220\u9664\u6216\u79fb\u52a8\u3002")
        st.session_state["project_name"] = project_name
        st.session_state.pop("active_story_id", None)
        st.session_state["project_switcher"] = ""
        return None

    try:
        migrate_project_to_stories(project_name)
        if "active_story_id" not in st.session_state:
            st.session_state["active_story_id"] = get_active_story_id(project_name)
    except Exception as exc:
        _set_project_load_error(project_name, str(exc))
        st.session_state["project_name"] = project_name
        st.session_state.pop("active_story_id", None)
        st.session_state["project_switcher"] = ""
        return None

    _clear_project_load_error()
    st.session_state["project_name"] = project_name
    set_active_project_name(project_name)
    return project_name

def copy_story_workspace_settings(project_name: str, source_story_id: str, target_story_id: str) -> dict:
    result = copy_story_settings(project_name, source_story_id, target_story_id)
    return result if isinstance(result, dict) else {"copied": 0, "updated": 0, "skipped": 0}


def _render_sidebar_brand() -> None:
    st.sidebar.markdown(
        """
        <div class="nf-sidebar-brand">
            <div class="nf-sidebar-mark">NF</div>
            <div>
                <div class="nf-sidebar-title">NovelForge</div>
                <div class="nf-sidebar-meta">长篇创作工作台</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_project_switcher(project_name: str | None, projects: list[str]) -> None:
    if projects:
        pending_project = st.session_state.pop(PENDING_PROJECT_SWITCH_KEY, "")
        if pending_project in projects:
            st.session_state["project_switcher"] = pending_project
        elif project_name in projects:
            st.session_state.setdefault("project_switcher", project_name)
        else:
            st.session_state.setdefault("project_switcher", "")

        options = [""] + projects
        current_value = st.session_state.get("project_switcher", "")
        if current_value not in options:
            current_value = project_name if project_name in projects else ""
            st.session_state["project_switcher"] = current_value

        st.sidebar.caption("\u5df2\u6709\u9879\u76ee")
        selected_project = st.sidebar.selectbox(
            "\u5feb\u901f\u5207\u6362",
            options=options,
            format_func=lambda value: "\u8bf7\u9009\u62e9\u9879\u76ee" if not value else value,
            key="project_switcher",
        )
        if selected_project and selected_project != project_name:
            _close_new_project_dialog()
            if project_name:
                st.session_state.pop(scoped_widget_key("story_switcher", project_name), None)
            st.session_state.pop("story_switcher", None)
            st.session_state["project_name"] = selected_project
            set_active_project_name(selected_project)
            try:
                active_story_id = get_active_story_id(selected_project)
                st.session_state["active_story_id"] = active_story_id
                st.session_state[scoped_widget_key("story_switcher", selected_project)] = active_story_id
                _clear_project_load_error()
            except Exception as exc:
                st.session_state.pop("active_story_id", None)
                _set_project_load_error(selected_project, str(exc))
            st.rerun()
    else:
        st.sidebar.info("\u8fd8\u6ca1\u6709\u9879\u76ee\u3002\u53ef\u4ee5\u5148\u914d\u7f6e\u6a21\u578b\uff0c\u4e5f\u53ef\u4ee5\u76f4\u63a5\u65b0\u5efa\u9879\u76ee\u3002")


def _render_new_project_entry(projects: list[str]) -> None:
    if st.sidebar.button("新建项目", width="stretch"):
        _open_new_project_dialog()
    if st.session_state.get(NEW_PROJECT_DIALOG_FLAG):
        render_new_project_dialog(projects)


def _render_story_switcher(project_name: str, stories: list[dict]) -> None:
    if len(stories) > 1:
        st.sidebar.divider()
        st.sidebar.caption("当前故事")
        active_id = st.session_state.get("active_story_id", "default")
        story_options = [s["story_id"] for s in stories]
        switcher_key = scoped_widget_key("story_switcher", project_name)
        pending_story = st.session_state.pop(PENDING_STORY_SWITCH_KEY, "")
        if pending_story in story_options:
            st.session_state[switcher_key] = pending_story
            active_id = pending_story
        elif switcher_key not in st.session_state:
            st.session_state[switcher_key] = active_id if active_id in story_options else story_options[0]
        elif st.session_state.get(switcher_key) not in story_options:
            st.session_state[switcher_key] = active_id if active_id in story_options else story_options[0]
        st.session_state.pop("story_switcher", None)
        story_labels = {s["story_id"]: f'{s.get("name", s["story_id"])}' for s in stories}
        selected_story = st.sidebar.selectbox(
            "切换故事",
            options=story_options,
            format_func=lambda sid: story_labels.get(sid, sid),
            key=switcher_key,
        )
        if selected_story != active_id:
            switch_to_story(project_name, selected_story)
            st.rerun()
    else:
        only_story_id = stories[0]["story_id"] if stories else "default"
        st.session_state["active_story_id"] = only_story_id


def _render_new_story_popover(project_name: str) -> None:
    with st.sidebar.popover("新故事", width="stretch"):
        new_story_name = st.text_input("故事名称", key="new_story_name_input")
        new_story_desc = st.text_area("故事描述", key="new_story_desc_input", height=80, placeholder="例如：原作线续写、平行世界、角色穿越...")
        copy_from = st.checkbox("从当前故事复制创作配置和优先设定", value=True, key="sidebar_copy_from")
        if st.button("创建故事", key="sidebar_create_story", width="stretch"):
            if new_story_name.strip():
                meta = create_story(project_name, new_story_name.strip(), new_story_desc.strip())
                if copy_from:
                    copy_story_workspace_settings(project_name, st.session_state.get("active_story_id", "default"), meta["story_id"])
                activate_story_after_creation(project_name, meta)
                st.rerun()
            else:
                st.error("故事名称不能为空。")

def _render_story_controls(project_name: str | None) -> None:
    if project_name:
        stories = list_stories(project_name)
        _render_story_switcher(project_name, stories)
        _render_new_story_popover(project_name)


def _apply_navigation_state(intent: dict, project_name: str | None, story_id: str) -> None:
    """把导航意图写入 Hub 和旧页面的 scoped 状态，必须在控件创建前调用。"""

    page = str(intent.get("page") or DEFAULT_PAGE)
    view = str(intent.get("view") or "")
    subview = str(intent.get("subview") or "")
    payload = intent.get("payload") if isinstance(intent.get("payload"), dict) else {}
    # 设置 Hub 的当前视图不依赖项目；无项目时从旧的“模型配置”或
    # “生成规则”状态迁移，也要准确落到对应设置视图。项目级子视图仍
    # 只在项目已加载后写入 scoped 状态。
    if page == "设置":
        st.session_state["settings_hub_view"] = view or "模型与费用"
        if not project_name:
            return
        if view == "高级创作":
            st.session_state[scoped_widget_key("settings_advanced_view", project_name, story_id)] = subview or "生成规则"
        elif view == "开发工具":
            st.session_state[scoped_widget_key("settings_developer_view", project_name, story_id)] = subview or "资料检索"
        return

    if not project_name:
        return
    if page == "工作台":
        st.session_state[scoped_widget_key("workbench_hub_view", project_name, story_id)] = view or "概览"
    elif page == "创作":
        creation_key = scoped_widget_key("creation_hub_view", project_name, story_id)
        st.session_state[creation_key] = view or "章节写作"
        if view == "小说规划":
            st.session_state[scoped_widget_key("creation_planning_view", project_name, story_id)] = subview or "全书"
        if view == "章节写作" and subview:
            try:
                chapter_no = int(payload.get("chapter_no") or st.session_state.get("active_chapter_no") or 1)
            except (TypeError, ValueError):
                chapter_no = 1
            chapter_no = max(chapter_no, 1)
            st.session_state[scoped_widget_key("chapter_page_view", project_name, story_id, chapter_no)] = (
                "3 · 保存与审阅" if subview == "保存与审阅" else "1 · 章节需求"
            )
    elif page == "资料库":
        st.session_state[scoped_widget_key("library_hub_view", project_name, story_id)] = view or "查找与编辑"
        if view == "导入与来源":
            st.session_state[scoped_widget_key("ingestion_workspace_section", project_name, story_id)] = subview or "导入"
        elif view == "查找与编辑":
            st.session_state[scoped_widget_key("knowledge_library_view", project_name, story_id)] = "全部知识"
            st.session_state[scoped_widget_key("knowledge_library_all_view", project_name, story_id)] = "统一搜索"
        elif view == "优先设定":
            st.session_state[scoped_widget_key("knowledge_library_view", project_name, story_id)] = "优先设定"
        elif view == "待审核":
            st.session_state[scoped_widget_key("knowledge_library_view", project_name, story_id)] = "待审核知识"
            st.session_state[scoped_widget_key("knowledge_library_review_view", project_name, story_id)] = subview or "审核队列"
def _apply_pending_navigation(project_name: str | None, story_id: str, available_pages: list[str]) -> None:
    intent = st.session_state.pop("pending_navigation_intent", None)
    legacy_page = st.session_state.pop("pending_nav_page", "")
    if not isinstance(intent, dict):
        if legacy_page:
            intent = build_navigation_intent(
                legacy_page,
                developer_mode=developer_mode_enabled(),
            )
        else:
            current = st.session_state.get("active_page", DEFAULT_PAGE)
            if current not in available_pages:
                intent = build_navigation_intent(current, developer_mode=developer_mode_enabled())
    if not isinstance(intent, dict):
        return
    target_page = str(intent.get("page") or DEFAULT_PAGE)
    if target_page not in available_pages:
        target_page = "设置" if "设置" in available_pages else available_pages[0]
        intent = build_navigation_intent(target_page, developer_mode=developer_mode_enabled())
    st.session_state["active_page"] = target_page
    _apply_navigation_state(intent, project_name, story_id)
    st.session_state["nav_revision"] = int(st.session_state.get("nav_revision", 0)) + 1


def _resolve_active_page(available_pages: list[str]) -> str:
    active_page = st.session_state.get("active_page", DEFAULT_PAGE)
    if active_page not in available_pages:
        active_page = "设置" if "设置" in available_pages else available_pages[0]
    return active_page


def _render_top_level_navigation(visible_pages: list[str], active_page: str) -> str:
    nav_revision = int(st.session_state.get("nav_revision", 0))
    selected_page = st.sidebar.radio(
        "工作区",
        options=visible_pages,
        index=visible_pages.index(active_page),
        key=f"active_top_level_page_{nav_revision}",
        format_func=lambda page: f"{PAGE_ICONS.get(page, '•')}  {PAGE_LABELS.get(page, page)}",
    )
    st.session_state["active_page"] = selected_page
    return selected_page


def _render_page_description(selected_page: str) -> None:
    description = PAGE_DESCRIPTIONS.get(selected_page, "")
    if description:
        st.sidebar.caption(description)


def _render_sidebar_project_summary(project_name: str | None) -> None:
    if project_name:
        try:
            summary = get_project_summary(project_name, story_id=st.session_state.get("active_story_id", "default"))
            st.sidebar.divider()
            st.sidebar.caption(
                f"正文 {summary.get('chapter_count', 0)} / 细纲 {summary.get('chapter_outline_count', 0)} / 资料 {summary.get('retrieval_source_count', 0)}"
            )
            updated_at = str(summary.get("updated_at") or "-").replace("T", " ")[:16]
            st.sidebar.caption(f"最近更新：{updated_at}")
            render_sidebar_usage_summary(
                project_name,
                str(st.session_state.get("active_story_id") or "default"),
            )
        except Exception as exc:
            LOGGER.warning(
                "Failed to load sidebar project summary for project=%s story=%s: %s",
                project_name,
                st.session_state.get("active_story_id", "default"),
                exc,
            )
            st.sidebar.caption("项目摘要暂不可用。")


def _render_sidebar_navigation(project_name: str | None) -> str:
    st.sidebar.divider()
    current_story_id = st.session_state.get("active_story_id", "default")
    visible_page_groups = page_groups_for_story(project_name, current_story_id)
    visible_pages = [page for pages in visible_page_groups.values() for page in pages]
    _apply_pending_navigation(project_name, current_story_id, visible_pages)
    active_page = _resolve_active_page(visible_pages)
    selected_page = _render_top_level_navigation(visible_pages, active_page)
    _render_page_description(selected_page)
    return selected_page


def render_sidebar(project_name: str | None, projects: list[str]) -> str:
    _render_sidebar_brand()
    _render_project_switcher(project_name, projects)
    _render_new_project_entry(projects)
    _render_story_controls(project_name)
    selected_page = _render_sidebar_navigation(project_name)
    _render_sidebar_project_summary(project_name)
    return selected_page
