"""Application shell helpers: project initialization and sidebar navigation."""
from __future__ import annotations

import logging

import streamlit as st

from memory import (
    copy_story_settings,
    create_project,
    create_story,
    creative_profile_path,
    get_active_story_id,
    list_projects,
    list_stories,
    load_creative_profile,
    migrate_project_to_stories,
    set_active_story,
)
from project_manager import get_project_summary
from ui.navigation import (
    ADVANCED_PAGE_GROUPS,
    DEFAULT_PAGE,
    LEGACY_PAGE_ALIASES,
    PAGE_DESCRIPTIONS,
    page_groups_for_story as navigation_page_groups_for_story,
)


LOGGER = logging.getLogger("novelforge.ui.app_shell")

PAGE_GROUPS = ADVANCED_PAGE_GROUPS

NEW_PROJECT_INPUT_KEY = "new_project_name_input"

NEW_PROJECT_DIALOG_FLAG = "show_new_project_dialog"

def is_story_creative_profile_configured(project_name: str | None, story_id: str = "default") -> bool:
    if not project_name:
        return False
    try:
        if not creative_profile_path(project_name, story_id).exists():
            return False
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
    )

@st.dialog("新建项目")
def render_new_project_dialog(existing_projects: list[str]):
    candidate_name = st.text_input("项目名", key=NEW_PROJECT_INPUT_KEY).strip()
    col1, col2 = st.columns(2)

    if col1.button("确认创建", use_container_width=True):
        if not candidate_name:
            st.error("项目名不能为空。")
            return
        if candidate_name in existing_projects:
            st.error("该项目已存在，请使用项目切换。")
            return

        created_project = create_project(candidate_name)
        st.session_state["project_name"] = created_project
        st.session_state[NEW_PROJECT_DIALOG_FLAG] = False
        st.rerun()

    if col2.button("取消", use_container_width=True):
        st.session_state[NEW_PROJECT_DIALOG_FLAG] = False
        st.rerun()

def init_project_state() -> str | None:
    projects = list_projects()

    project_name = st.session_state.get("project_name")
    if project_name:
        if project_name not in projects:
            create_project(project_name)
        migrate_project_to_stories(project_name)
        if "active_story_id" not in st.session_state:
            st.session_state["active_story_id"] = get_active_story_id(project_name)
        return project_name

    if projects:
        st.session_state["project_name"] = projects[0]
        return projects[0]

    return None

def copy_story_workspace_settings(project_name: str, source_story_id: str, target_story_id: str) -> dict:
    result = copy_story_settings(project_name, source_story_id, target_story_id)
    return result if isinstance(result, dict) else {"copied": 0, "updated": 0, "skipped": 0}


def _render_sidebar_brand() -> None:
    st.sidebar.markdown(
        """
        <div class="nf-sidebar-title">NovelForge</div>
        <div class="nf-sidebar-meta">长篇创作工作台</div>
        """,
        unsafe_allow_html=True,
    )


def _render_project_switcher(project_name: str | None, projects: list[str]) -> None:
    if projects:
        st.sidebar.caption("已有项目")
        selected_project = st.sidebar.selectbox(
            "快速切换",
            options=projects,
            index=projects.index(project_name) if project_name in projects else 0,
            key="project_switcher"
        )
        if selected_project != project_name:
            st.session_state["project_name"] = selected_project
            st.session_state["active_story_id"] = get_active_story_id(selected_project)
            st.rerun()
    else:
        st.sidebar.info("还没有项目。可以先配置模型，也可以直接新建项目。")


def _render_new_project_entry(projects: list[str]) -> None:
    if st.sidebar.button("新建项目", use_container_width=True):
        st.session_state[NEW_PROJECT_INPUT_KEY] = ""
        st.session_state[NEW_PROJECT_DIALOG_FLAG] = True

    if st.session_state.get(NEW_PROJECT_DIALOG_FLAG):
        render_new_project_dialog(projects)


def _render_story_switcher(project_name: str, stories: list[dict]) -> None:
    if len(stories) > 1:
        st.sidebar.divider()
        st.sidebar.caption("当前故事")
        active_id = st.session_state.get("active_story_id", "default")
        story_options = [s["story_id"] for s in stories]
        story_labels = {s["story_id"]: f'{s.get("name", s["story_id"])}' for s in stories}
        selected_story = st.sidebar.selectbox(
            "切换故事",
            options=story_options,
            index=story_options.index(active_id) if active_id in story_options else 0,
            format_func=lambda sid: story_labels.get(sid, sid),
            key="story_switcher",
        )
        if selected_story != active_id:
            set_active_story(project_name, selected_story)
            st.session_state["active_story_id"] = selected_story
            st.rerun()
    else:
        only_story_id = stories[0]["story_id"] if stories else "default"
        st.session_state["active_story_id"] = only_story_id


def _render_new_story_popover(project_name: str) -> None:
    with st.sidebar.popover("新故事", use_container_width=True):
        new_story_name = st.text_input("故事名称", key="new_story_name_input")
        new_story_desc = st.text_area("故事描述", key="new_story_desc_input", height=80, placeholder="例如：原作线续写、平行世界、角色穿越...")
        copy_from = st.checkbox("从当前故事复制创作配置和核心设定", value=True, key="sidebar_copy_from")
        if st.button("创建故事"):
            if new_story_name.strip():
                meta = create_story(project_name, new_story_name.strip(), new_story_desc.strip())
                if copy_from:
                    copy_story_workspace_settings(project_name, st.session_state.get("active_story_id", "default"), meta["story_id"])
                set_active_story(project_name, meta["story_id"])
                st.session_state["active_story_id"] = meta["story_id"]
                st.success(f"已创建故事：{new_story_name.strip()}")
                st.rerun()
            else:
                st.error("故事名称不能为空。")


def _render_story_controls(project_name: str | None) -> None:
    if project_name:
        stories = list_stories(project_name)
        _render_story_switcher(project_name, stories)
        _render_new_story_popover(project_name)


def _apply_pending_navigation(available_pages: list[str]) -> None:
    pending_nav_page = st.session_state.pop("pending_nav_page", "")
    pending_nav_page = LEGACY_PAGE_ALIASES.get(pending_nav_page, pending_nav_page)
    if pending_nav_page in available_pages:
        st.session_state["active_page"] = pending_nav_page
        st.session_state["nav_revision"] = int(st.session_state.get("nav_revision", 0)) + 1


def _resolve_active_page(available_pages: list[str]) -> str:
    active_page = LEGACY_PAGE_ALIASES.get(st.session_state.get("active_page", DEFAULT_PAGE), st.session_state.get("active_page", DEFAULT_PAGE))
    if active_page not in available_pages:
        if active_page in PAGE_GROUPS.get("规划", []) and "创作配置" in available_pages:
            active_page = "创作配置"
        elif DEFAULT_PAGE in available_pages:
            active_page = DEFAULT_PAGE
        else:
            active_page = available_pages[0]
    return active_page


def _render_navigation_radios(visible_page_groups: dict[str, list[str]], active_page: str) -> tuple[str, str]:
    group_names = list(visible_page_groups.keys())
    active_group = next(
        (group for group, pages in visible_page_groups.items() if active_page in pages),
        group_names[0],
    )
    nav_revision = int(st.session_state.get("nav_revision", 0))
    selected_group = st.sidebar.radio(
        "工作区",
        options=group_names,
        index=group_names.index(active_group),
        key=f"active_page_group_{nav_revision}",
    )
    group_pages = visible_page_groups[selected_group]
    if active_page not in group_pages:
        active_page = group_pages[0]

    selected_page = st.sidebar.radio(
        "页面",
        options=group_pages,
        index=group_pages.index(active_page),
        key=f"active_page_in_group_{selected_group}_{nav_revision}",
        format_func=lambda page: page,
    )
    st.session_state["active_page"] = selected_page
    return selected_group, selected_page


def _render_planning_profile_hint(project_name: str | None, current_story_id: str, selected_group: str) -> None:
    if selected_group == "规划" and project_name and not is_story_creative_profile_configured(project_name, current_story_id):
        st.sidebar.markdown(
            """
            <div class="nf-sidebar-note">
                <strong>建议先讨论配置</strong><br>
                规划页面都可以进入；先保存「创作配置」能让生成更贴合目标。
            </div>
            """,
            unsafe_allow_html=True,
        )


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
            updated_at = summary.get("updated_at") or "-"
            st.sidebar.caption(f"最近更新：{updated_at}")
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
    available_pages = [page for pages in visible_page_groups.values() for page in pages]
    _apply_pending_navigation(available_pages)
    active_page = _resolve_active_page(available_pages)
    selected_group, selected_page = _render_navigation_radios(visible_page_groups, active_page)
    _render_planning_profile_hint(project_name, current_story_id, selected_group)
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

