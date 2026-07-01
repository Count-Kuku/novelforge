"""Settings and core setting management pages."""
from __future__ import annotations

import html

import streamlit as st

from memory import (
    KNOWLEDGE_CATEGORIES,
    confirm_pending_knowledge_items,
    create_story,
    discard_pending_knowledge_items,
    list_stories,
    load_knowledge_base,
    load_memory,
    load_pending_knowledge_items,
    rename_story,
    save_memory,
)
from retrieval import rebuild_retrieval_assets
from setting_knowledge import (
    SETTING_FIELD_SPECS,
    build_generation_setting_context,
    copy_project_core_settings_to_story,
    copy_story_core_settings_to_project,
    copy_story_core_settings_to_story,
    delete_setting_item,
    list_setting_items,
    migrate_core_settings_to_knowledge,
    upsert_setting_item,
)
from knowledge_workflows import (
    parse_comma_tags,
    safe_confidence,
    summarize_item_evidence,
    update_pending_knowledge_item,
)
from ui.app_shell import activate_story_after_creation, copy_story_workspace_settings, switch_to_story
from ui.common import navigate_to, scoped_widget_key
from ui.labels import label_knowledge_category
from ui.llm_settings import render_llm_settings_page


def _setting_field_label(field_name: str) -> str:
    spec = SETTING_FIELD_SPECS.get(str(field_name or ""), {})
    return str(spec.get("label") or field_name or "设定")


def _setting_scope_label(scope: str) -> str:
    return {"project": "项目级", "story": "当前故事级"}.get(str(scope or ""), str(scope or "未知层级"))


def _setting_injection_label(policy: str) -> str:
    return {
        "always": "总是注入",
        "retrieval": "检索命中时注入",
        "manual_only": "仅手动管理",
    }.get(str(policy or ""), str(policy or "未设置"))


def _setting_item_title(item: dict) -> str:
    field_label = _setting_field_label(str(item.get("setting_field") or ""))
    scope_label = _setting_scope_label(str(item.get("setting_scope") or "project"))
    policy_label = _setting_injection_label(str(item.get("injection_policy") or "always"))
    name = str(item.get("name") or "未命名设定")
    return f"{name} · {field_label} · {scope_label} · {policy_label}"


def _render_setting_item_form(project_name: str, story_id: str, setting_scope: str, item: dict | None, key_prefix: str):
    current = dict(item or {})
    field_options = list(SETTING_FIELD_SPECS.keys())
    current_field = str(current.get("setting_field") or "world")
    if current_field not in field_options:
        current_field = "world"
    default_category = str(current.get("category") or SETTING_FIELD_SPECS[current_field]["category"])
    category_options = list(KNOWLEDGE_CATEGORIES.keys())
    if default_category not in category_options:
        category_options.append(default_category)

    with st.form(key_prefix):
        field_name = st.selectbox(
            "设定类型",
            options=field_options,
            index=field_options.index(current_field),
            format_func=_setting_field_label,
        )
        category = st.selectbox(
            "知识分类",
            options=category_options,
            index=category_options.index(default_category) if default_category in category_options else 0,
            format_func=label_knowledge_category,
        )
        name = st.text_input("名称", value=str(current.get("name") or ""))
        summary = st.text_area("设定内容", value=str(current.get("summary") or ""), height=120)
        injection_policy = st.selectbox(
            "生成注入方式",
            options=["always", "retrieval", "manual_only"],
            index=["always", "retrieval", "manual_only"].index(str(current.get("injection_policy") or "always")) if str(current.get("injection_policy") or "always") in {"always", "retrieval", "manual_only"} else 0,
            format_func=_setting_injection_label,
        )
        importance = st.slider("重要性", min_value=0.0, max_value=1.0, value=float(current.get("importance", 0.9) or 0.9), step=0.05)
        tags = st.text_input("标签（逗号分隔）", value=", ".join(current.get("tags", []) or []))
        delete_checked = st.checkbox("删除这个设定", value=False, disabled=not bool(current.get("id")))
        col_save, col_delete = st.columns(2)
        save_clicked = col_save.form_submit_button("保存设定", type="primary", use_container_width=True)
        delete_clicked = col_delete.form_submit_button("删除设定", use_container_width=True, disabled=not bool(current.get("id")) or not delete_checked)

    if save_clicked:
        if not summary.strip():
            st.warning("设定内容不能为空。")
            return
        payload = {
            **current,
            "category": category,
            "name": name.strip() or summary.strip()[:36],
            "summary": summary.strip(),
            "setting_field": field_name,
            "setting_scope": setting_scope,
            "story_id": story_id if setting_scope == "story" else "",
            "setting_role": "core",
            "injection_policy": injection_policy,
            "importance": importance,
            "source_origin": current.get("source_origin") or "manual_setting",
            "tags": [part.strip() for part in tags.split(",") if part.strip()],
            "details": {
                **(current.get("details") if isinstance(current.get("details"), dict) else {}),
                "原始设定": summary.strip(),
                "来源字段": field_name,
            },
        }
        saved = upsert_setting_item(project_name, category, payload)
        old_category = str(current.get("category") or "")
        if current.get("id") and old_category and old_category != category:
            delete_setting_item(project_name, old_category, str(current.get("id") or ""))
        st.success(f"已保存设定：{saved.get('name')}")
        st.rerun()

    if delete_clicked:
        if delete_setting_item(project_name, str(current.get("category") or category), str(current.get("id") or "")):
            st.success("设定已删除。")
            st.rerun()
        st.warning("没有找到要删除的设定。")


def render_setting_items_editor(project_name: str, story_id: str, setting_scope: str):
    all_items = list_setting_items(project_name, story_id, core_only=True)
    editable_items_all = [
        item for item in all_items
        if str(item.get("setting_scope") or "project") == setting_scope
        and (setting_scope != "story" or str(item.get("story_id") or "") == story_id)
    ]
    inherited_items = [
        item for item in all_items
        if setting_scope == "story" and str(item.get("setting_scope") or "project") == "project"
    ]

    metric_cols = st.columns(3)
    metric_cols[0].metric("当前可用核心设定", len(all_items))
    metric_cols[1].metric(f"{_setting_scope_label(setting_scope)}设定", len(editable_items_all))
    metric_cols[2].metric("总是注入", len([item for item in all_items if str(item.get("injection_policy") or "") == "always"]))

    filter_cols = st.columns([1, 1, 1.3])
    available_categories = sorted({str(item.get("category") or "") for item in editable_items_all if item.get("category")})
    category_filter = filter_cols[0].selectbox(
        "分类筛选",
        options=[""] + available_categories,
        format_func=lambda value: "全部分类" if not value else label_knowledge_category(value),
        key=scoped_widget_key("setting_category_filter", project_name, story_id, setting_scope),
    )
    policy_filter = filter_cols[1].selectbox(
        "注入方式",
        options=["", "always", "retrieval", "manual_only"],
        format_func=lambda value: "全部方式" if not value else _setting_injection_label(value),
        key=scoped_widget_key("setting_policy_filter", project_name, story_id, setting_scope),
    )
    keyword_filter = filter_cols[2].text_input(
        "关键词",
        key=scoped_widget_key("setting_keyword_filter", project_name, story_id, setting_scope),
        placeholder="按名称或内容过滤",
    ).strip()
    editable_items = []
    for item in editable_items_all:
        if category_filter and str(item.get("category") or "") != category_filter:
            continue
        if policy_filter and str(item.get("injection_policy") or "") != policy_filter:
            continue
        if keyword_filter:
            haystack = f"{item.get('name', '')}\n{item.get('summary', '')}".casefold()
            if keyword_filter.casefold() not in haystack:
                continue
        editable_items.append(item)

    with st.expander(f"新增{_setting_scope_label(setting_scope)}设定", expanded=False):
        _render_setting_item_form(
            project_name,
            story_id,
            setting_scope,
            None,
            scoped_widget_key("new_setting_item", project_name, story_id, setting_scope),
        )

    if inherited_items:
        with st.expander("继承的项目级核心设定", expanded=False):
            for item in inherited_items:
                st.markdown(f"- **{html.escape(str(item.get('name') or '-'))}**：{html.escape(str(item.get('summary') or ''))}")

    if not editable_items:
        if editable_items_all:
            st.info("当前筛选条件下没有匹配的核心设定。")
        else:
            st.info(f"当前还没有{_setting_scope_label(setting_scope)}核心设定。可以直接新增，底层会保存为正式知识条目。")
        return

    for item in editable_items:
        with st.expander(_setting_item_title(item), expanded=False):
            st.caption(f"ID: {item.get('id', '')} / 分类: {label_knowledge_category(str(item.get('category') or ''))} / 来源: {item.get('source_origin') or 'manual_setting'}")
            _render_setting_item_form(
                project_name,
                story_id,
                setting_scope,
                item,
                scoped_widget_key("edit_setting_item", project_name, story_id, item.get("category", ""), item.get("id", "")),
            )


def render_generation_setting_context_preview(project_name: str, story_id: str):
    with st.expander("当前生成会看到的核心设定", expanded=False):
        try:
            context = build_generation_setting_context(project_name, story_id)
        except Exception as exc:
            st.warning(f"生成上下文预览失败：{exc}")
            return
        setting_context = str(context.get("_setting_context") or "").strip()
        if not setting_context:
            st.caption("当前没有会优先注入生成的核心设定。")
            return
        st.caption("这里是统一设定知识合成后的只读预览。正文、细纲、审阅等生成流程会优先参考这些内容。")
        st.code(setting_context, language="markdown")


def _pending_core_items_for_scope(project_name: str, story_id: str, setting_scope: str) -> list[dict]:
    setting_scope = str(setting_scope or "project")
    rows: list[dict] = []
    for item in load_pending_knowledge_items(project_name):
        if not isinstance(item, dict):
            continue
        role = str(item.get("setting_role") or "")
        policy = str(item.get("injection_policy") or "")
        if role != "core" and policy != "always":
            continue
        item_scope = str(item.get("setting_scope") or "project")
        item_story_id = str(item.get("story_id") or "")
        if item_scope != setting_scope:
            continue
        if setting_scope == "story" and item_story_id != story_id:
            continue
        rows.append(item)
    rows.sort(key=lambda item: (
        str(item.get("source_chapter_no") or ""),
        str(item.get("category") or ""),
        str(item.get("name") or ""),
    ))
    return rows


def _pending_core_setting_editor_options(item: dict) -> dict:
    current_field = str(item.get("setting_field") or "world")
    field_options = list(SETTING_FIELD_SPECS.keys())
    if current_field not in field_options:
        field_options.append(current_field)
    current_category = str(item.get("category") or SETTING_FIELD_SPECS.get(current_field, {}).get("category") or "world_rules")
    category_options = list(KNOWLEDGE_CATEGORIES.keys())
    if current_category not in category_options:
        category_options.append(current_category)
    current_policy = str(item.get("injection_policy") or "always")
    policy_options = ["always", "retrieval", "manual_only"]
    if current_policy not in policy_options:
        policy_options.append(current_policy)
    return {
        "current_field": current_field,
        "field_options": field_options,
        "current_category": current_category,
        "category_options": category_options,
        "current_policy": current_policy,
        "policy_options": policy_options,
    }


def _render_pending_core_setting_header(item: dict, current_category: str, current_field: str) -> None:
    st.markdown(f"**{html.escape(str(item.get('name') or '未命名设定'))}**")
    st.caption(
        f"{label_knowledge_category(current_category)} / "
        f"{_setting_field_label(current_field)} / "
        f"来源：{item.get('source_title') or '-'}"
    )
    evidence_lines = summarize_item_evidence(item)
    if evidence_lines:
        st.caption("证据：" + "；".join(evidence_lines[:2]))


def _render_pending_core_setting_form(item: dict, pending_id: str, key_prefix: str, options: dict) -> tuple[dict, bool, bool, bool]:
    with st.form(f"{key_prefix}_form_{pending_id}"):
        col_meta_1, col_meta_2, col_meta_3 = st.columns([1, 1, 1])
        field_name = col_meta_1.selectbox(
            "设定类型",
            options=options["field_options"],
            index=options["field_options"].index(options["current_field"]),
            format_func=_setting_field_label,
            key=f"{key_prefix}_field_{pending_id}",
        )
        default_category = options["current_category"] if options["current_category"] in options["category_options"] else options["category_options"][0]
        category = col_meta_2.selectbox(
            "知识分类",
            options=options["category_options"],
            index=options["category_options"].index(default_category),
            format_func=label_knowledge_category,
            key=f"{key_prefix}_category_{pending_id}",
        )
        injection_policy = col_meta_3.selectbox(
            "注入方式",
            options=options["policy_options"],
            index=options["policy_options"].index(options["current_policy"]),
            format_func=_setting_injection_label,
            key=f"{key_prefix}_policy_{pending_id}",
        )
        name = st.text_input("名称", value=str(item.get("name") or ""), key=f"{key_prefix}_name_{pending_id}")
        summary = st.text_area("设定内容", value=str(item.get("summary") or ""), height=100, key=f"{key_prefix}_summary_{pending_id}")
        col_quality_1, col_quality_2 = st.columns([1, 1])
        importance = col_quality_1.slider(
            "重要性",
            min_value=0.0,
            max_value=1.0,
            value=safe_confidence(item.get("importance", 0.75)),
            step=0.05,
            key=f"{key_prefix}_importance_{pending_id}",
        )
        tags = col_quality_2.text_input(
            "标签（逗号分隔）",
            value=", ".join(str(tag) for tag in item.get("tags", []) if str(tag).strip()) if isinstance(item.get("tags"), list) else "",
            key=f"{key_prefix}_tags_{pending_id}",
        )
        col_save, col_confirm, col_discard = st.columns(3)
        save_clicked = col_save.form_submit_button("保存修改", use_container_width=True)
        confirm_clicked = col_confirm.form_submit_button("保存并确认", type="primary", use_container_width=True)
        discard_clicked = col_discard.form_submit_button("丢弃", use_container_width=True)
    values = {
        "field_name": field_name,
        "category": category,
        "injection_policy": injection_policy,
        "name": name,
        "summary": summary,
        "importance": importance,
        "tags": tags,
    }
    return values, save_clicked, confirm_clicked, discard_clicked


def _handle_pending_core_setting_editor_action(
    project_name: str,
    item: dict,
    pending_id: str,
    values: dict,
    *,
    confirm_clicked: bool,
    discard_clicked: bool,
) -> None:
    if discard_clicked:
        removed_count = discard_pending_knowledge_items(project_name, [pending_id])
        st.success(f"已丢弃 {removed_count} 条候选设定。")
        st.rerun()
    if not values["summary"].strip():
        st.warning("设定内容不能为空。")
        return
    updated_item = {
        **item,
        "category": values["category"],
        "name": values["name"].strip() or values["summary"].strip()[:36],
        "summary": values["summary"].strip(),
        "setting_field": values["field_name"],
        "setting_role": "core",
        "injection_policy": values["injection_policy"],
        "importance": values["importance"],
        "tags": parse_comma_tags(values["tags"]),
        "details": {
            **(item.get("details") if isinstance(item.get("details"), dict) else {}),
            "原始设定": values["summary"].strip(),
            "来源字段": values["field_name"],
        },
    }
    update_pending_knowledge_item(project_name, pending_id, updated_item)
    if confirm_clicked:
        saved_count = confirm_pending_knowledge_items(project_name, [pending_id])
        if saved_count:
            rebuild_retrieval_assets(project_name, build_vectors=True)
        st.success(f"已确认 {saved_count} 条核心设定。")
    else:
        st.success("候选设定已保存。")
    st.rerun()


def _render_pending_core_setting_item_editor(project_name: str, item: dict, key_prefix: str):
    pending_id = str(item.get("pending_id") or "")
    if not pending_id:
        return
    options = _pending_core_setting_editor_options(item)
    _render_pending_core_setting_header(item, options["current_category"], options["current_field"])
    values, save_clicked, confirm_clicked, discard_clicked = _render_pending_core_setting_form(item, pending_id, key_prefix, options)
    if not (save_clicked or confirm_clicked or discard_clicked):
        return
    _handle_pending_core_setting_editor_action(
        project_name,
        item,
        pending_id,
        values,
        confirm_clicked=confirm_clicked,
        discard_clicked=discard_clicked,
    )


def render_pending_core_setting_panel(project_name: str, story_id: str, setting_scope: str = "story"):
    pending_items = _pending_core_items_for_scope(project_name, story_id, setting_scope)
    if not pending_items:
        return

    scope_label = _setting_scope_label(setting_scope)
    key_prefix = scoped_widget_key("pending_core_settings", project_name, story_id, setting_scope)
    with st.expander(f"待确认{scope_label}设定（{len(pending_items)}）", expanded=True):
        st.caption("这些条目来自章节设定提炼或讨论生成依据。确认后会成为正式知识条目，并按注入方式影响后续生成。")
        pending_ids = [str(item.get("pending_id") or "") for item in pending_items if item.get("pending_id")]
        selected_ids = st.multiselect(
            "选择要处理的候选设定",
            options=pending_ids,
            default=pending_ids[: min(8, len(pending_ids))],
            format_func=lambda pending_id: next(
                (
                    f"{label_knowledge_category(item.get('category', ''))} / {item.get('name', '未命名')}"
                    for item in pending_items
                    if str(item.get("pending_id") or "") == pending_id
                ),
                pending_id,
            ),
            key=f"{key_prefix}_selected",
        )
        preview_limit = min(8, len(pending_items))
        st.caption(f"下方可直接编辑前 {preview_limit} 条候选设定；完整队列仍可在资料导入页批量处理。")
        for index, item in enumerate(pending_items[:preview_limit], start=1):
            st.divider()
            _render_pending_core_setting_item_editor(project_name, item, f"{key_prefix}_{index}")
        if len(pending_items) > preview_limit:
            st.caption(f"这里只展示前 {preview_limit} 条，共 {len(pending_items)} 条。")

        col_confirm, col_discard = st.columns(2)
        if col_confirm.button("确认所选设定", key=f"{key_prefix}_confirm", use_container_width=True):
            if not selected_ids:
                st.warning("请先选择候选设定。")
            else:
                saved_count = confirm_pending_knowledge_items(project_name, selected_ids)
                if saved_count:
                    rebuild_retrieval_assets(project_name, build_vectors=True)
                st.success(f"已确认 {saved_count} 条核心设定。")
                st.rerun()
        if col_discard.button("丢弃所选候选", key=f"{key_prefix}_discard", use_container_width=True):
            if not selected_ids:
                st.warning("请先选择候选设定。")
            else:
                removed_count = discard_pending_knowledge_items(project_name, selected_ids)
                st.success(f"已丢弃 {removed_count} 条候选设定。")
                st.rerun()


def render_settings_page(project_name: str, *, render_memory_page):
    story_id = st.session_state.get("active_story_id", "default")
    stories = list_stories(project_name)
    current_story_name = "默认"
    for s in stories:
        if s.get("story_id") == story_id:
            current_story_name = s.get("name", story_id)
            break

    st.subheader(f"核心设定 · {current_story_name}")
    migration_key = f"setting_knowledge_migration:{project_name}"
    if not st.session_state.get(migration_key):
        try:
            migration_result = migrate_core_settings_to_knowledge(project_name)
            st.session_state[migration_key] = True
            if migration_result.get("migrated") or migration_result.get("updated"):
                st.success(
                    f"已将旧核心设定同步为统一知识条目：新增 {migration_result.get('migrated', 0)} 条，更新 {migration_result.get('updated', 0)} 条。"
                )
        except Exception as exc:
            st.warning(f"旧核心设定迁移失败，当前仍可继续编辑新的统一设定：{exc}")
    st.caption("正式设定现在统一保存为知识条目。核心设定页只展示会优先影响生成的高优先级设定。")

    story_tab, project_tab = st.tabs(["故事设定", "项目设定"])

    with story_tab:
        _render_story_settings_tab(project_name, story_id, current_story_name, render_memory_page=render_memory_page)

    with project_tab:
        _render_project_settings_tab(project_name)


def _render_story_settings_tab(project_name: str, story_id: str, story_name: str, *, render_memory_page):
    st.markdown("#### 设定复制与导入")
    st.caption("这里复制的是正式知识条目里的核心设定；创作配置、生成规则和提示词选项仍通过故事复制入口复制。")
    col_a, col_b, col_c = st.columns(3)
    if col_a.button("复制项目设定到当前故事", use_container_width=True):
        result = copy_project_core_settings_to_story(project_name, story_id)
        st.success(f"已处理项目核心设定：新增 {result.get('copied', 0)} 条，更新 {result.get('updated', 0)} 条。")
        st.rerun()

    other_stories = [s for s in list_stories(project_name) if s.get("story_id") != story_id]
    if other_stories:
        sel_story = col_b.selectbox(
            "从其他故事导入",
            options=[s.get("story_id") for s in other_stories],
            format_func=lambda sid: next((s.get("name", sid) for s in other_stories if s["story_id"] == sid), sid),
            key="settings_import_story",
            label_visibility="collapsed",
        )
        if col_b.button("复制该故事设定", use_container_width=True, key="import_other_story"):
            result = copy_story_core_settings_to_story(project_name, sel_story, story_id)
            st.success(f"已复制故事核心设定：新增 {result.get('copied', 0)} 条，更新 {result.get('updated', 0)} 条。")
            st.rerun()
    else:
        col_b.caption("暂无其他故事可复制。")

    if col_c.button("提升为项目设定", use_container_width=True):
        result = copy_story_core_settings_to_project(project_name, story_id)
        st.success(f"已提升当前故事核心设定：新增 {result.get('copied', 0)} 条，更新 {result.get('updated', 0)} 条。")
        st.rerun()

    st.divider()
    st.markdown(f"#### {story_name} 的核心设定")
    render_pending_core_setting_panel(project_name, story_id)
    render_generation_setting_context_preview(project_name, story_id)
    render_memory_page(project_name, {}, embedded=True)


def _render_project_settings_tab(project_name: str):
    base_memory = load_memory(project_name)
    st.markdown("#### 项目基础设定（所有故事共享）")
    changed = False
    new_memory = dict(base_memory)

    new_title = st.text_input("书名", value=base_memory.get("title", ""), key=scoped_widget_key("project_title", project_name))
    if new_title != base_memory.get("title"):
        new_memory["title"] = new_title
        changed = True
    new_genre = st.text_input("类型", value=base_memory.get("genre", ""), key=scoped_widget_key("project_genre", project_name))
    if new_genre != base_memory.get("genre"):
        new_memory["genre"] = new_genre
        changed = True

    if st.button("保存项目元信息", key=scoped_widget_key("save_project_meta", project_name), disabled=not changed):
        save_memory(project_name, new_memory)
        st.success("项目元信息已保存。")
        st.rerun()
    if not changed:
        st.caption("书名和类型没有未保存改动。")

    st.divider()
    render_pending_core_setting_panel(project_name, "default", "project")
    render_generation_setting_context_preview(project_name, "default")
    render_setting_items_editor(project_name, "default", "project")

    st.divider()
    st.markdown("#### 项目知识库")
    knowledge = load_knowledge_base(project_name)
    total_items = sum(len(items) for items in knowledge.values())
    st.caption(f"共 {len(knowledge)} 个分类，{total_items} 条知识条目。详细管理请到「资料导入」页面。")
    for cat, items in knowledge.items():
        if items:
            with st.expander(f"{label_knowledge_category(cat)}（{len(items)} 条）", expanded=False):
                for item in items:
                    summary = str(item.get("summary") or item.get("content") or "")[:200]
                    st.markdown(f"- **{item.get('name', '-')}**：{summary}")
    if st.button("前往资料导入", use_container_width=True, key="goto_ingestion"):
        navigate_to("资料导入")


def _render_story_management_tab(project_name: str):
    stories = list_stories(project_name)
    st.markdown(f"#### 故事列表（共 {len(stories)} 个）")

    for s in stories:
        story_id = str(s.get("story_id") or "")
        cols = st.columns([3, 1, 1, 1, 1, 1])
        cols[0].write(f"**{s.get('name', s['story_id'])}**  ({s['story_id']})")
        cols[1].write(s.get("status", "active"))
        cols[2].write(s.get("created_at", "")[:10])

        is_active = story_id == st.session_state.get("active_story_id", "default")
        if cols[3].button("切换", key=f"switch_{story_id}", disabled=is_active, use_container_width=True):
            switch_to_story(project_name, story_id)
            st.rerun()

        with cols[4].popover("编辑", use_container_width=True):
            st.caption(f"故事 ID：`{story_id}`")
            new_story_name = st.text_input(
                "故事名称",
                value=str(s.get("name") or story_id),
                key=f"rename_story_name_{story_id}",
            )
            new_story_description = st.text_area(
                "故事描述",
                value=str(s.get("description") or ""),
                height=80,
                key=f"rename_story_desc_{story_id}",
            )
            if st.button("保存故事信息", key=f"save_story_meta_{story_id}", use_container_width=True):
                try:
                    rename_story(project_name, story_id, new_story_name, new_story_description)
                    st.success("故事信息已更新。")
                    st.rerun()
                except Exception as exc:
                    st.error(f"保存失败：{exc}")

        if cols[5].button("复制", key=f"copy_{story_id}", use_container_width=True):
            try:
                new_story_name = f"{s.get('name') or story_id} 副本"
                meta = create_story(project_name, new_story_name, str(s.get("description") or ""))
                copy_story_workspace_settings(project_name, story_id, meta["story_id"])
                activate_story_after_creation(project_name, meta, notice_action="copied")
                st.rerun()
            except Exception as exc:
                st.error(f"复制失败：{exc}")

    st.divider()
    st.markdown("#### 创建新故事")
    with st.popover("新故事", use_container_width=True):
        new_story_name = st.text_input("故事名称", key="settings_new_story_name")
        new_story_desc = st.text_area("故事描述", height=80, key="settings_new_story_desc",
                                       placeholder="例如：原作线续写、平行世界、角色穿越...")
        copy_from = st.checkbox("从当前故事复制创作配置和核心设定", value=True, key="settings_copy_story_workspace")
        if st.button("创建故事", key="settings_create_story", use_container_width=True):
            if new_story_name.strip():
                meta = create_story(project_name, new_story_name.strip(), new_story_desc.strip())
                if copy_from:
                    copy_story_workspace_settings(project_name, st.session_state.get("active_story_id", "default"), meta["story_id"])
                activate_story_after_creation(project_name, meta)
                st.rerun()
            else:
                st.error("故事名称不能为空。")

    st.divider()
    st.markdown("#### 模型配置")
    render_llm_settings_page()
