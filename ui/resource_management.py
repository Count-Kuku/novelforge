"""Project resource browser page."""
from __future__ import annotations

import json
import logging

import streamlit as st

from memory import delete_retrieval_source_file, list_arcs, list_volumes
from project_manager import (
    delete_chapter_bundle,
    delete_pipeline_run,
    list_chapter_inventory,
    list_project_runs,
    list_retrieval_sources,
)
from resource_browser import (
    _build_resource_browser_items,
    _delete_browser_resource,
    _save_browser_resource,
)
from retrieval import rebuild_retrieval_assets
from ui.common import confirmed_button, navigate_to, scoped_widget_key
from ui.labels import label_status
from ui.resource_browser_state import (
    RESOURCE_BROWSER_GROUPS,
    RESOURCE_BROWSER_GROUP_LABELS,
    _consume_resource_browser_focus,
    _get_resource_browser_selection,
    _resource_browser_selection_key,
    _set_resource_browser_selection,
)
from ui.step_views import render_step_json_expander


LOGGER = logging.getLogger("novelforge.ui.resource_management")


DISCUSSION_RESOURCE_GROUPS = {
    "outline_discussion",
    "creative_profile_discussion",
    "volume_discussion",
    "arc_discussion",
    "chapter_discussion",
    "arc_chapter_plan",
}
READONLY_RESOURCE_GROUPS = {"knowledge_item", "pending_knowledge", "long_reference_batch"}
STATUS_OPTIONS = ["draft", "approved", "archived"]
GLOBAL_FILTER_PASSTHROUGH_GROUPS = {
    "outline",
    "outline_discussion",
    "creative_profile_discussion",
    "run",
    "analysis",
    "evaluation",
    "source",
    "review",
    "chapter_content",
    "knowledge_item",
    "pending_knowledge",
    "long_reference_batch",
}
ARC_FILTER_PASSTHROUGH_GROUPS = GLOBAL_FILTER_PASSTHROUGH_GROUPS | {"volume_outline", "volume_discussion"}


def _reset_resource_browser_selection(project_name: str) -> None:
    st.session_state[_resource_browser_selection_key(project_name)] = {}


def _status_index(status: str) -> int:
    return STATUS_OPTIONS.index(status) if status in STATUS_OPTIONS else 0


def _render_run_resource_detail(project_name: str, story_id: str, resource: dict) -> None:
    st.code(resource.get("content", ""), language="json")
    delete_key = scoped_widget_key("browser_delete", project_name, story_id, resource.get("id"))
    if confirmed_button(st, "删除该运行记录", "确认删除该运行记录", delete_key):
        if _delete_browser_resource(project_name, resource, story_id=story_id):
            st.success("运行记录已删除。")
            _reset_resource_browser_selection(project_name)
            st.rerun()


def _render_discussion_resource_detail(project_name: str, story_id: str, resource: dict) -> None:
    if resource.get("content"):
        st.markdown(resource.get("content", ""))
    render_step_json_expander("结构化数据", resource.get("discussion_payload", {}) or resource.get("chapter_plan_payload", {}))
    delete_key = scoped_widget_key("browser_delete", project_name, story_id, resource.get("id"))
    if confirmed_button(st, "删除该工件", "确认删除该讨论/计划工件", delete_key):
        if _delete_browser_resource(project_name, resource, story_id=story_id):
            st.success("工件已删除。")
            _reset_resource_browser_selection(project_name)
            st.rerun()


def _render_readonly_resource_detail(project_name: str, story_id: str, resource: dict) -> None:
    st.caption("该资源在浏览器中只读；编辑和批量处理请回到「资料导入」。")
    st.code(resource.get("content", ""), language="json")
    if st.button(
        "前往资料导入",
        key=scoped_widget_key("browser_goto_ingestion", project_name, story_id, resource.get("id")),
        use_container_width=True,
    ):
        navigate_to("资料导入")


def _render_volume_metadata_editor(resource: dict) -> None:
    metadata = dict(resource.get("volume_metadata", {}) or {})
    volume_title = st.text_input("分卷标题", value=metadata.get("title", ""), key=f"browser_volume_title_{resource.get('id')}")
    volume_summary = st.text_area(
        "分卷摘要",
        value=metadata.get("summary", ""),
        height=120,
        key=f"browser_volume_summary_{resource.get('id')}",
    )
    volume_status = st.selectbox(
        "分卷状态",
        options=STATUS_OPTIONS,
        index=_status_index(metadata.get("status", "draft")),
        format_func=label_status,
        key=f"browser_volume_status_{resource.get('id')}",
    )
    resource["volume_metadata"] = {
        "volume_no": int(resource.get("volume_no", 0)),
        "title": volume_title,
        "summary": volume_summary,
        "status": volume_status,
    }


def _render_arc_metadata_editor(project_name: str, story_id: str, resource: dict) -> None:
    metadata = dict(resource.get("arc_metadata", {}) or {})
    arc_title = st.text_input("剧情段标题", value=metadata.get("title", ""), key=f"browser_arc_title_{resource.get('id')}")
    arc_summary = st.text_area(
        "剧情段摘要",
        value=metadata.get("summary", ""),
        height=120,
        key=f"browser_arc_summary_{resource.get('id')}",
    )
    volume_options = [0] + [int(item.get("volume_no", 0)) for item in list_volumes(project_name, story_id=story_id)]
    current_volume = int(metadata.get("volume_no") or 0)
    arc_volume_no = st.selectbox(
        "所属分卷",
        options=volume_options,
        index=volume_options.index(current_volume) if current_volume in volume_options else 0,
        format_func=lambda value: "未指定分卷" if value == 0 else f"第 {value} 卷",
        key=f"browser_arc_volume_{resource.get('id')}",
    )
    arc_status = st.selectbox(
        "剧情段状态",
        options=STATUS_OPTIONS,
        index=_status_index(metadata.get("status", "draft")),
        format_func=label_status,
        key=f"browser_arc_status_{resource.get('id')}",
    )
    estimated_chapter_count = st.number_input(
        "预计章节数",
        min_value=0,
        value=int(metadata.get("estimated_chapter_count") or 0),
        key=f"browser_arc_estimated_chapters_{resource.get('id')}",
    )
    target_word_count_range = st.text_input(
        "目标总字数范围",
        value=metadata.get("target_word_count_range", ""),
        key=f"browser_arc_word_range_{resource.get('id')}",
    )
    resource["arc_metadata"] = {
        "arc_no": int(resource.get("arc_no", 0)),
        "volume_no": arc_volume_no or None,
        "title": arc_title,
        "summary": arc_summary,
        "status": arc_status,
        "estimated_chapter_count": estimated_chapter_count or None,
        "target_word_count_range": target_word_count_range,
    }


def _render_structured_payload_editor(resource: dict) -> str:
    if resource.get("group") == "review":
        return st.text_area(
            "审阅结构化数据",
            value=json.dumps(resource.get("review_payload", {}), ensure_ascii=False, indent=2),
            height=220,
            key=f"browser_json_{resource.get('id')}",
        )
    if resource.get("group") == "evaluation":
        return st.text_area(
            "评估结构化数据",
            value=json.dumps(resource.get("evaluation_payload", {}), ensure_ascii=False, indent=2),
            height=220,
            key=f"browser_json_{resource.get('id')}",
        )
    return ""


def _render_editable_resource_actions(project_name: str, story_id: str, resource: dict, edited_content: str, edited_json_text: str) -> None:
    save_col, delete_col = st.columns(2)
    if resource.get("editable") and save_col.button("保存当前资源", key=f"browser_save_{resource.get('id')}"):
        try:
            _save_browser_resource(project_name, resource, edited_content, edited_json_text, story_id=story_id)
            st.success("资源已保存。")
            st.rerun()
        except json.JSONDecodeError as exc:
            st.error(f"结构化数据格式错误：{exc}")
        except Exception as exc:
            st.error(f"保存资源失败：{exc}")

    delete_key = scoped_widget_key("browser_delete", project_name, story_id, resource.get("id"))
    if resource.get("deletable") and confirmed_button(delete_col, "删除当前资源", "确认删除当前资源", delete_key):
        try:
            if _delete_browser_resource(project_name, resource, story_id=story_id):
                st.success("资源已删除。")
                _reset_resource_browser_selection(project_name)
                st.rerun()
            else:
                st.warning("目标资源不存在。")
        except Exception as exc:
            st.error(f"删除资源失败：{exc}")


def _render_resource_browser_detail(project_name: str, resource: dict):
    story_id = st.session_state.get("active_story_id", "default")
    if not resource:
        st.caption("请先从左侧选择一个资源。")
        return

    st.markdown(f"### {resource.get('label', '')}")
    st.caption(resource.get("path_label", ""))

    group = resource.get("group")
    if group == "run":
        _render_run_resource_detail(project_name, story_id, resource)
        return

    if group in DISCUSSION_RESOURCE_GROUPS:
        _render_discussion_resource_detail(project_name, story_id, resource)
        return

    if group in READONLY_RESOURCE_GROUPS:
        _render_readonly_resource_detail(project_name, story_id, resource)
        return

    edited_content = st.text_area(
        "内容",
        value=resource.get("content", ""),
        height=520,
        key=f"browser_editor_{resource.get('id')}"
    )

    if group == "volume_outline":
        _render_volume_metadata_editor(resource)
    if group == "arc_outline":
        _render_arc_metadata_editor(project_name, story_id, resource)
    edited_json_text = _render_structured_payload_editor(resource)
    _render_editable_resource_actions(project_name, story_id, resource, edited_content, edited_json_text)

def _render_resource_browser_filters(project_name: str, story_id: str) -> dict:
    search_value = st.text_input("搜索资源", key=f"resource_browser_search_{project_name}")
    group_filter_key = f"resource_browser_group_filter_{project_name}"
    group_filter_options = [group_key for group_key, _ in RESOURCE_BROWSER_GROUPS]
    existing_group_filter = st.session_state.get(group_filter_key)
    if not isinstance(existing_group_filter, list) or any(group not in group_filter_options for group in existing_group_filter):
        st.session_state[group_filter_key] = group_filter_options
    browser_group_filter = st.multiselect(
        "资源类型",
        options=group_filter_options,
        format_func=lambda value: RESOURCE_BROWSER_GROUP_LABELS.get(value, value),
        key=group_filter_key,
    )
    volume_filter_options = [0] + [int(item.get("volume_no", 0)) for item in list_volumes(project_name, story_id=story_id)]
    browser_volume_filter = st.selectbox(
        "按分卷过滤",
        options=volume_filter_options,
        format_func=lambda value: "全部分卷" if value == 0 else f"第 {value} 卷",
        key=f"resource_browser_volume_filter_{project_name}",
    )
    arc_filter_candidates = list_arcs(project_name, volume_no=browser_volume_filter or None, story_id=story_id)
    arc_filter_options = [0] + [int(item.get("arc_no", 0)) for item in arc_filter_candidates]
    browser_arc_filter = st.selectbox(
        "按剧情段过滤",
        options=arc_filter_options,
        format_func=lambda value: "全部剧情段" if value == 0 else f"剧情段 {value:03d}",
        key=f"resource_browser_arc_filter_{project_name}",
    )
    return {
        "search_lower": search_value.strip().lower(),
        "active_group_filter": set(browser_group_filter),
        "volume_filter": browser_volume_filter,
        "arc_filter": browser_arc_filter,
    }


def _render_bulk_chapter_cleanup(project_name: str, story_id: str) -> None:
    chapter_inventory = list_chapter_inventory(project_name, story_id=story_id)
    if not chapter_inventory:
        return
    chapter_numbers = [item.get("chapter_no") for item in chapter_inventory]
    bulk_chapter_selection = st.multiselect(
        "批量章节清理",
        options=chapter_numbers,
        format_func=lambda value: f"第 {int(value)} 章",
        key=f"resource_bulk_chapters_{project_name}",
    )
    if bulk_chapter_selection and confirmed_button(
        st,
        "清理所选章节",
        "确认清理所选章节的细纲、正文、审阅、分析、评价和运行记录",
        scoped_widget_key("bulk_delete_chapters", project_name, story_id),
    ):
        results = [
            {
                "chapter_no": int(chapter_no),
                "result": delete_chapter_bundle(project_name, int(chapter_no), story_id=story_id),
            }
            for chapter_no in bulk_chapter_selection
        ]
        st.success(f"已批量清理章节资源：{json.dumps(results, ensure_ascii=False)}")
        st.rerun()


def _render_bulk_run_cleanup(project_name: str, story_id: str) -> None:
    runs = list_project_runs(project_name, story_id=story_id)
    if not runs:
        return
    bulk_runs = st.multiselect(
        "批量删除运行记录",
        options=[run.get("run_id") for run in runs],
        key=f"resource_bulk_runs_{project_name}",
    )
    if bulk_runs and confirmed_button(
        st,
        "删除所选运行记录",
        "确认删除所选运行记录",
        scoped_widget_key("bulk_delete_runs", project_name, story_id),
    ):
        deleted_count = 0
        for run_id in bulk_runs:
            if delete_pipeline_run(project_name, str(run_id), story_id=story_id):
                deleted_count += 1
        st.success(f"已删除 {deleted_count} 条运行记录。")
        st.rerun()


def _render_bulk_source_cleanup(project_name: str) -> None:
    sources = list_retrieval_sources(project_name)
    if not sources:
        return
    bulk_sources = st.multiselect(
        "批量删除外部资料",
        options=[source.get("relative_path") for source in sources],
        key=f"resource_bulk_sources_{project_name}",
    )
    if bulk_sources and confirmed_button(
        st,
        "删除所选外部资料",
        "确认删除所选外部资料并重建索引",
        scoped_widget_key("bulk_delete_sources", project_name),
    ):
        deleted_count = 0
        failed_sources = []
        for relative_path in bulk_sources:
            try:
                if delete_retrieval_source_file(project_name, str(relative_path)):
                    deleted_count += 1
            except Exception as exc:
                failed_sources.append(str(relative_path))
                LOGGER.warning(
                    "Failed to delete retrieval source for project=%s path=%s: %s",
                    project_name,
                    relative_path,
                    exc,
                )
        if deleted_count:
            rebuild_retrieval_assets(project_name, build_vectors=True)
        if failed_sources:
            st.warning(f"有 {len(failed_sources)} 份外部资料删除失败，已保留并写入日志。")
        st.success(f"已删除 {deleted_count} 份外部资料。")
        st.rerun()


def _render_bulk_cleanup(project_name: str, story_id: str) -> None:
    with st.expander("批量清理（可选）", expanded=False):
        st.caption("用于一次删除多项资源。普通浏览和编辑不需要打开这里。")
        _render_bulk_chapter_cleanup(project_name, story_id)
        _render_bulk_run_cleanup(project_name, story_id)
        _render_bulk_source_cleanup(project_name)


def _resource_item_volume_no(item: dict):
    item_volume_no = item.get("volume_no")
    if item_volume_no is None:
        item_volume_no = (item.get("volume_metadata") or {}).get("volume_no")
    if item_volume_no is None:
        item_volume_no = (item.get("arc_metadata") or {}).get("volume_no")
    if item_volume_no is None:
        item_volume_no = (item.get("chapter_metadata") or {}).get("volume_no")
    return item_volume_no


def _resource_item_arc_no(item: dict):
    item_arc_no = item.get("arc_no")
    if item_arc_no is None:
        item_arc_no = (item.get("arc_metadata") or {}).get("arc_no")
    if item_arc_no is None:
        item_arc_no = (item.get("chapter_metadata") or {}).get("arc_no")
    return item_arc_no


def _filter_resource_group_items(browser_items: list[dict], group_key: str, filters: dict) -> list[dict]:
    group_items = [item for item in browser_items if item.get("group") == group_key]
    if filters["volume_filter"]:
        group_items = [
            item
            for item in group_items
            if item.get("group") in GLOBAL_FILTER_PASSTHROUGH_GROUPS
            or _resource_item_volume_no(item) == filters["volume_filter"]
        ]
    if filters["arc_filter"]:
        group_items = [
            item
            for item in group_items
            if item.get("group") in ARC_FILTER_PASSTHROUGH_GROUPS
            or _resource_item_arc_no(item) == filters["arc_filter"]
        ]
    if filters["search_lower"]:
        search_lower = filters["search_lower"]
        group_items = [
            item
            for item in group_items
            if search_lower in str(item.get("label", "")).lower()
            or search_lower in str(item.get("path_label", "")).lower()
        ]
    return group_items


def _render_visible_resource_groups(project_name: str, browser_items: list[dict], selected: dict, filters: dict) -> list[dict]:
    visible_items = []
    for group_key, group_label in RESOURCE_BROWSER_GROUPS:
        if group_key not in filters["active_group_filter"]:
            continue
        group_items = _filter_resource_group_items(browser_items, group_key, filters)
        if not group_items:
            continue
        visible_items.extend(group_items)
        st.markdown(f"**{group_label}**")
        for item in group_items:
            selected_flag = selected.get("id") == item.get("id")
            button_label = f"> {item.get('label')}" if selected_flag else item.get("label")
            if st.button(button_label, key=f"resource_select_{item.get('id')}", use_container_width=True):
                _set_resource_browser_selection(project_name, item)
                st.rerun()
    if not visible_items:
        st.caption("当前筛选下没有可显示的资源。")
    return visible_items


def _render_resource_browser_sidebar(project_name: str, story_id: str, browser_items: list[dict], selected: dict) -> list[dict]:
    st.markdown("### 资源浏览器")
    filters = _render_resource_browser_filters(project_name, story_id)
    _render_bulk_cleanup(project_name, story_id)
    return _render_visible_resource_groups(project_name, browser_items, selected, filters)


def _resolve_browser_selection(project_name: str, selected: dict, browser_items: list[dict], visible_items: list[dict]) -> dict:
    if selected and not any(item.get("id") == selected.get("id") for item in browser_items):
        selected = {}
        _reset_resource_browser_selection(project_name)
    visible_ids = {item.get("id") for item in visible_items}
    if selected and not visible_ids:
        selected = {}
        _reset_resource_browser_selection(project_name)
    if selected and visible_ids and selected.get("id") not in visible_ids:
        selected = {}
        _reset_resource_browser_selection(project_name)
    if not selected and visible_items:
        selected = visible_items[0]
        _set_resource_browser_selection(project_name, selected)
    return selected


def render_resource_management_page(project_name: str):
    st.subheader("资源浏览器")
    story_id = st.session_state.get("active_story_id", "default")
    browser_items = _build_resource_browser_items(project_name, story_id=story_id)
    selected = _get_resource_browser_selection(project_name)
    focused_selected, focus_warning = _consume_resource_browser_focus(project_name, browser_items)
    if focused_selected:
        selected = focused_selected
    if focus_warning:
        st.info(focus_warning)

    left_col, right_col = st.columns([1, 2])
    with left_col:
        visible_items = _render_resource_browser_sidebar(project_name, story_id, browser_items, selected)
    with right_col:
        st.markdown("### 资源详情")
        selected = _resolve_browser_selection(project_name, selected, browser_items, visible_items)
        _render_resource_browser_detail(project_name, selected)

