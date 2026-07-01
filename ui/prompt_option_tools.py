"""Shared prompt option UI helpers."""
from __future__ import annotations

import json
import logging

import streamlit as st

from memory import (
    load_creative_profile,
    load_effective_rule_conflict_resolutions,
    load_global_prompt_options,
    load_global_rules,
    load_project_prompt_options,
    load_project_rules,
    load_story_prompt_options,
    load_story_rules,
    upsert_prompt_option,
    delete_prompt_option,
)
from prompt_options import (
    PROMPT_OPTION_CAPABILITIES,
    PROMPT_OPTION_CATEGORIES,
    PROMPT_OPTION_SLOTS,
    builtin_prompt_options,
    filter_prompt_options,
    format_prompt_options_for_prompt,
    merge_prompt_option_layers,
    normalize_prompt_option,
)
from prompts import format_rules_for_prompt
from setting_knowledge import build_generation_setting_context
from ui.common import scoped_widget_key


APP_LOGGER = logging.getLogger("novelforge.ui.prompt_option_tools")


PROMPT_OPTION_LAYER_LABELS = {
    "story": "故事",
    "project": "项目",
    "global": "全局",
    "builtin": "内置预设",
}


def _prompt_option_label(option: dict) -> str:
    capability = PROMPT_OPTION_CAPABILITIES.get(option.get("capability", ""), option.get("capability", ""))
    category = PROMPT_OPTION_CATEGORIES.get(option.get("category", ""), option.get("category", ""))
    enabled = "启用" if option.get("enabled", True) else "停用"
    return f"{option.get('name') or option.get('id')} · {capability} · {category} · {enabled}"


def _load_prompt_option_layer(project_name: str, layer: str, story_id: str) -> list[dict]:
    if layer == "global":
        return load_global_prompt_options()
    if layer == "project":
        return load_project_prompt_options(project_name)
    if layer == "builtin":
        return builtin_prompt_options()
    return load_story_prompt_options(project_name, story_id)


def _render_prompt_option_create_form(
    project_name: str,
    story_id: str,
    layer: str,
    key_prefix: str,
    *,
    default_capability: str = "write",
    submit_label: str | None = None,
):
    capability_keys = list(PROMPT_OPTION_CAPABILITIES.keys())
    category_keys = list(PROMPT_OPTION_CATEGORIES.keys())
    slot_keys = list(PROMPT_OPTION_SLOTS.keys())
    capability_index = capability_keys.index(default_capability) if default_capability in capability_keys else capability_keys.index("write")
    with st.form(key_prefix):
        name = st.text_input("名称", placeholder="例如：冷峻悬疑文风", key=f"{key_prefix}_name")
        option_id = st.text_input("ID（可留空自动生成）", placeholder="例如：style_cold_suspense", key=f"{key_prefix}_id")
        capability = st.selectbox(
            "适用能力",
            options=capability_keys,
            format_func=lambda value: PROMPT_OPTION_CAPABILITIES.get(value, value),
            index=capability_index,
            key=f"{key_prefix}_capability",
        )
        category = st.selectbox(
            "类型",
            options=category_keys,
            format_func=lambda value: PROMPT_OPTION_CATEGORIES.get(value, value),
            index=category_keys.index("custom"),
            key=f"{key_prefix}_category",
        )
        slot = st.selectbox(
            "插槽",
            options=slot_keys,
            format_func=lambda value: PROMPT_OPTION_SLOTS.get(value, value),
            index=slot_keys.index("custom"),
            key=f"{key_prefix}_slot",
        )
        enabled = st.checkbox("保存后立即启用", value=True, key=f"{key_prefix}_enabled")
        priority = st.number_input("优先级", value=50, step=1, key=f"{key_prefix}_priority")
        content = st.text_area(
            "选项内容（可复用写作提示）",
            height=180,
            placeholder="例如：多写角色的即时心理反应；战斗段落保持动作连续；日常对话更口语化。",
            help="这里的内容应该是可开关、可替换的写作偏好，而不是长期设定或硬性禁忌。",
            key=f"{key_prefix}_content",
        )
        submitted = st.form_submit_button(submit_label or f"保存到{PROMPT_OPTION_LAYER_LABELS.get(layer, layer)}")
    if submitted:
        if not content.strip():
            st.warning("选项内容不能为空。")
            return
        payload = normalize_prompt_option(
            {
                "id": option_id,
                "name": name,
                "capability": capability,
                "category": category,
                "slot": slot,
                "enabled": enabled,
                "priority": priority,
                "content": content,
                "source": "manual",
            },
            scope=layer,
        )
        upsert_prompt_option(project_name, layer, payload, story_id=story_id)
        st.success(f"已保存到{PROMPT_OPTION_LAYER_LABELS.get(layer, layer)}。")
        st.rerun()


def _render_prompt_option_edit_form(project_name: str, story_id: str, layer: str, option: dict, key_prefix: str):
    original_option_id = str(option.get("id") or "")
    with st.form(key_prefix):
        option_id = st.text_input("ID", value=option.get("id", ""), disabled=bool(option.get("built_in")), key=f"{key_prefix}_id")
        name = st.text_input("名称", value=option.get("name", ""), key=f"{key_prefix}_name")
        capability_keys = list(PROMPT_OPTION_CAPABILITIES.keys())
        category_keys = list(PROMPT_OPTION_CATEGORIES.keys())
        slot_keys = list(PROMPT_OPTION_SLOTS.keys())
        capability = st.selectbox(
            "适用能力",
            options=capability_keys,
            index=capability_keys.index(option.get("capability", "write")) if option.get("capability", "write") in capability_keys else 0,
            format_func=lambda value: PROMPT_OPTION_CAPABILITIES.get(value, value),
            key=f"{key_prefix}_capability",
        )
        category = st.selectbox(
            "类型",
            options=category_keys,
            index=category_keys.index(option.get("category", "custom")) if option.get("category", "custom") in category_keys else category_keys.index("custom"),
            format_func=lambda value: PROMPT_OPTION_CATEGORIES.get(value, value),
            key=f"{key_prefix}_category",
        )
        slot = st.selectbox(
            "插槽",
            options=slot_keys,
            index=slot_keys.index(option.get("slot", "custom")) if option.get("slot", "custom") in slot_keys else slot_keys.index("custom"),
            format_func=lambda value: PROMPT_OPTION_SLOTS.get(value, value),
            key=f"{key_prefix}_slot",
        )
        priority = st.number_input("优先级（数字越小越靠前）", value=int(option.get("priority", 50)), step=1, key=f"{key_prefix}_priority")
        enabled = st.checkbox("启用", value=bool(option.get("enabled", True)), key=f"{key_prefix}_enabled")
        content = st.text_area(
            "选项内容（可复用写作提示）",
            value=option.get("content", ""),
            height=180,
            help="适合放可切换的写作偏好，例如文风、节奏、描写重点、审稿关注点；不适合放必须长期遵守的设定事实或禁忌。",
            key=f"{key_prefix}_content",
        )
        tags = st.text_input("标签（逗号分隔）", value=", ".join(option.get("tags", []) or []), key=f"{key_prefix}_tags")
        delete_checked = st.checkbox("删除这个选项", value=False, disabled=bool(option.get("built_in")), key=f"{key_prefix}_delete_checked")
        col_save, col_delete = st.columns(2)
        save_clicked = col_save.form_submit_button("保存", use_container_width=True)
        delete_clicked = col_delete.form_submit_button("删除", use_container_width=True, disabled=bool(option.get("built_in")) or not delete_checked)

    if save_clicked:
        payload = normalize_prompt_option(
            {
                **option,
                "id": option_id,
                "name": name,
                "capability": capability,
                "category": category,
                "slot": slot,
                "priority": priority,
                "enabled": enabled,
                "content": content,
                "tags": [item.strip() for item in tags.split(",") if item.strip()],
                "source": option.get("source") or "manual",
            },
            scope=layer,
        )
        new_option_id = str(payload.get("id") or "")
        if new_option_id != original_option_id:
            existing_options = _load_prompt_option_layer(project_name, layer, story_id)
            if any(str(item.get("id") or "") == new_option_id for item in existing_options):
                st.warning("这个 ID 已经存在。请换一个 ID，或先删除同名选项。")
                return
        upsert_prompt_option(project_name, layer, payload, story_id=story_id)
        if original_option_id and new_option_id != original_option_id:
            delete_prompt_option(project_name, layer, original_option_id, story_id=story_id)
        st.success("提示词选项已保存。")
        st.rerun()
    if delete_clicked:
        if delete_prompt_option(project_name, layer, option.get("id", ""), story_id=story_id):
            st.success("提示词选项已删除。")
            st.rerun()
        else:
            st.warning("没有找到要删除的选项。")


def _render_prompt_option_inline_tools(
    project_name: str,
    story_id: str,
    options: list[dict],
    *,
    capability: str,
    key_prefix: str,
):
    st.caption("需要新的写作偏好时，可以在这里直接新增；想微调已有选项，也可以直接修改。")
    add_tab, edit_tab = st.tabs(["新增选项", "修改已有"])
    with add_tab:
        tab_story, tab_project, tab_global = st.tabs(["新增到当前故事", "新增到项目", "新增到全局"])
        with tab_story:
            _render_prompt_option_create_form(
                project_name,
                story_id,
                "story",
                scoped_widget_key("inline_prompt_option_create_story", key_prefix, project_name, story_id),
                default_capability=capability,
            )
        with tab_project:
            _render_prompt_option_create_form(
                project_name,
                story_id,
                "project",
                scoped_widget_key("inline_prompt_option_create_project", key_prefix, project_name, story_id),
                default_capability=capability,
            )
        with tab_global:
            _render_prompt_option_create_form(
                project_name,
                story_id,
                "global",
                scoped_widget_key("inline_prompt_option_create_global", key_prefix, project_name, story_id),
                default_capability=capability,
            )
    with edit_tab:
        editable_options = [option for option in options if not option.get("built_in") and option.get("scope") in {"story", "project", "global"}]
        if editable_options:
            selected_id = st.selectbox(
                "选择要修改的提示词",
                options=[f"{option.get('scope')}::{option.get('id')}" for option in editable_options],
                format_func=lambda value: next(
                    (
                        f"{PROMPT_OPTION_LAYER_LABELS.get(option.get('scope', ''), option.get('scope', ''))} / {_prompt_option_label(option)}"
                        for option in editable_options
                        if value == f"{option.get('scope')}::{option.get('id')}"
                    ),
                    value,
                ),
                key=scoped_widget_key("inline_prompt_option_edit_select", key_prefix, project_name, story_id),
            )
            selected_option = next(
                option for option in editable_options
                if selected_id == f"{option.get('scope')}::{option.get('id')}"
            )
            st.caption(f"正在修改：{PROMPT_OPTION_LAYER_LABELS.get(selected_option.get('scope', ''), selected_option.get('scope', ''))}层级")
            _render_prompt_option_edit_form(
                project_name,
                story_id,
                selected_option.get("scope", "story"),
                selected_option,
                scoped_widget_key("inline_prompt_option_edit", key_prefix, project_name, story_id, selected_option.get("scope", ""), selected_option.get("id", "")),
            )
        else:
            st.caption("还没有可修改的自定义提示词。内置预设需要先复制到当前故事后再修改。")
        builtin_options_for_capability = [
            option for option in options
            if option.get("built_in") and option.get("capability") in {capability, "all"}
        ]
        if builtin_options_for_capability:
            st.markdown("##### 复制内置预设后修改")
            builtin_id = st.selectbox(
                "选择内置预设",
                options=[option.get("id", "") for option in builtin_options_for_capability],
                format_func=lambda option_id: next((_prompt_option_label(option) for option in builtin_options_for_capability if option.get("id") == option_id), option_id),
                key=scoped_widget_key("inline_prompt_option_builtin_select", key_prefix, project_name, story_id),
            )
            selected_builtin = next(option for option in builtin_options_for_capability if option.get("id") == builtin_id)
            st.code(selected_builtin.get("content", ""), language="markdown")
            if st.button("复制到当前故事并启用", key=scoped_widget_key("inline_prompt_option_copy_builtin", key_prefix, project_name, story_id, builtin_id), use_container_width=True):
                payload = dict(selected_builtin)
                payload["scope"] = "story"
                payload["built_in"] = False
                payload["enabled"] = True
                payload["source"] = "builtin_copy"
                upsert_prompt_option(project_name, "story", payload, story_id=story_id)
                st.success("已复制到当前故事，可以继续修改。")
                st.rerun()


def _load_prompt_options_for_capability(project_name: str, story_id: str, capability: str) -> tuple[list[dict], str]:
    try:
        effective_prompt_options = merge_prompt_option_layers(
            load_global_prompt_options(),
            load_project_prompt_options(project_name),
            load_story_prompt_options(project_name, story_id),
        )
        return filter_prompt_options(effective_prompt_options, capability, enabled_only=False), ""
    except Exception as exc:
        return [], str(exc)


def _render_prompt_option_capability_tools(
    project_name: str,
    story_id: str,
    capability: str,
    key_prefix: str,
    *,
    select_for_run: bool = False,
) -> list[str] | None:
    capability_label = PROMPT_OPTION_CAPABILITIES.get(capability, capability)
    prompt_options, error = _load_prompt_options_for_capability(project_name, story_id, capability)
    st.markdown(f"#### {capability_label}提示词选项")
    if select_for_run:
        st.caption("这里可以临时选择本次生成使用哪些提示词，也可以直接新增或修改正文写作提示词。")
    else:
        st.caption("这里管理该能力默认生效的提示词。保存并启用后，会影响后续同类生成。")
    if error:
        st.warning(f"提示词选项加载失败：{error}")

    selected_prompt_option_ids = None
    if select_for_run and prompt_options:
        option_ids = [option.get("id", "") for option in prompt_options]
        option_labels = {option.get("id", ""): _prompt_option_label(option) for option in prompt_options}
        default_option_ids = [option.get("id", "") for option in prompt_options if option.get("enabled", True)]
        selected_prompt_option_ids = st.multiselect(
            f"本次使用{capability_label}提示词选项",
            options=option_ids,
            default=default_option_ids,
            format_func=lambda option_id: option_labels.get(option_id, option_id),
            key=scoped_widget_key("prompt_option_run_ids", key_prefix, project_name, story_id, capability),
            help="默认勾选已启用选项；也可以临时选择未启用的预设，仅影响本次生成。",
        )
    elif prompt_options:
        enabled_count = len([option for option in prompt_options if option.get("enabled", True)])
        st.caption(f"当前可用 {len(prompt_options)} 个，其中已启用 {enabled_count} 个。")
    else:
        st.info(f"还没有{capability_label}提示词选项。可以在下面新增，或复制内置预设后修改。")

    _render_prompt_option_inline_tools(
        project_name,
        story_id,
        prompt_options,
        capability=capability,
        key_prefix=scoped_widget_key("prompt_option_tools", key_prefix, project_name, story_id, capability),
    )
    return selected_prompt_option_ids


def _render_prompt_option_layer(project_name: str, story_id: str, layer: str):
    options = _load_prompt_option_layer(project_name, layer, story_id)
    if not options:
        st.caption("当前层级还没有自定义提示词选项。")
        return
    for option in options:
        with st.expander(_prompt_option_label(option), expanded=False):
            st.caption(f"ID: {option.get('id')} / 来源: {option.get('source') or 'manual'}")
            _render_prompt_option_edit_form(
                project_name,
                story_id,
                layer,
                option,
                scoped_widget_key("prompt_option_edit", project_name, story_id, layer, option.get("id", "")),
            )


def _format_creative_profile_for_preview(project_name: str, story_id: str) -> str:
    try:
        profile = load_creative_profile(project_name, story_id)
    except Exception as exc:
        APP_LOGGER.warning(
            "Failed to load creative profile preview for project=%s story=%s: %s",
            project_name,
            story_id,
            exc,
        )
        profile = {}
    if not profile:
        return ""
    lines = [
        "项目创作配置：",
        f"- 任务性质：{profile.get('story_mode', '-')}",
        f"- 目标篇幅：{profile.get('target_length', '-')}",
        f"- 目标字数：{profile.get('target_word_count', '') or '未设置'}",
        f"- 生成层级：{profile.get('workflow_depth', '-')}",
        f"- 资料参考强度：{profile.get('reference_strength', '-')}",
        f"- 重点参考方向：{', '.join(profile.get('reference_focus', []) or []) or '未设置'}",
        f"- 允许改写原设：{'是' if profile.get('allow_canon_deviation', True) else '否'}",
        f"- 资料冲突处理：{profile.get('conflict_policy', '-')}",
        f"- 当前世界线：{profile.get('worldline_label') or profile.get('worldline_id') or '未设置'}",
        f"- 世界线检索模式：{profile.get('worldline_retrieval_mode', 'prefer')}",
    ]
    notes = str(profile.get("notes", "") or "").strip()
    if notes:
        lines.append(f"- 补充说明：{notes}")
    return "\n".join(lines)


def _build_generation_injection_preview(
    project_name: str,
    story_id: str,
    scope: str,
    prompt_option_ids: list[str] | None,
    generation_guidance: dict,
) -> dict[str, str]:
    sections: dict[str, str] = {}
    try:
        setting_context = str(build_generation_setting_context(project_name, story_id).get("_setting_context") or "").strip()
    except Exception as exc:
        setting_context = f"核心设定预览失败：{exc}"
    if setting_context:
        sections["核心设定"] = setting_context

    try:
        rules_text = format_rules_for_prompt(
            load_global_rules(),
            load_project_rules(project_name),
            scope,
            story_rules=load_story_rules(project_name, story_id),
            conflict_resolutions=load_effective_rule_conflict_resolutions(project_name, story_id, scope),
        )
    except Exception as exc:
        rules_text = f"规则预览失败：{exc}"
    if rules_text:
        sections["生成规则与人工裁决"] = rules_text

    profile_text = _format_creative_profile_for_preview(project_name, story_id)
    if profile_text:
        sections["创作配置"] = profile_text

    try:
        options = merge_prompt_option_layers(
            load_global_prompt_options(),
            load_project_prompt_options(project_name),
            load_story_prompt_options(project_name, story_id),
        )
        option_text = format_prompt_options_for_prompt(options, scope, selected_ids=prompt_option_ids)
    except Exception as exc:
        option_text = f"提示词选项预览失败：{exc}"
    if option_text:
        sections["提示词选项"] = option_text

    cleaned_guidance = {
        key: value
        for key, value in (generation_guidance or {}).items()
        if value not in ("", [], {}, None)
    }
    if cleaned_guidance:
        sections["本次临时写作参数"] = json.dumps(cleaned_guidance, ensure_ascii=False, indent=2)
    return sections


def _render_generation_injection_preview(
    project_name: str,
    story_id: str,
    scope: str,
    prompt_option_ids: list[str] | None,
    generation_guidance: dict,
):
    with st.expander("本次生成注入预览", expanded=False):
        st.caption("这是点击生成前的只读检查。它不会保存新内容，只展示本次会影响模型的设定、规则、提示词选项和临时参数。")
        sections = _build_generation_injection_preview(
            project_name,
            story_id,
            scope,
            prompt_option_ids,
            generation_guidance,
        )
        if not sections:
            st.info("当前没有额外注入内容。")
            return
        for title, content in sections.items():
            st.markdown(f"#### {title}")
            st.code(content, language="markdown")
