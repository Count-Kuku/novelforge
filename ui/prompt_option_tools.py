"""Shared prompt option UI helpers."""
from __future__ import annotations

import hashlib
import json

import streamlit as st

from context_assembly import assemble_generation_context
from memory import (
    load_global_prompt_options,
    load_project_prompt_options,
    load_story_prompt_options,
    upsert_prompt_option,
    delete_prompt_option,
)
from prompt_options import (
    PROMPT_OPTION_CAPABILITIES,
    PROMPT_OPTION_CATEGORIES,
    PROMPT_OPTION_SLOTS,
    builtin_prompt_options,
    filter_prompt_options,
    merge_prompt_option_layers,
    normalize_prompt_option,
)
from ui.common import scoped_widget_key


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


def _build_generation_injection_preview(
    project_name: str,
    story_id: str,
    scope: str,
    prompt_option_ids: list[str] | None,
    generation_guidance: dict,
    *,
    query: str = "",
    chapter_no: int | None = None,
) -> dict:
    profile_by_scope = {
        "write": "drafting",
        "chapter_outline": "chapter_planning",
        "outline": "outline_generation",
        "review": "review",
    }
    assembly = assemble_generation_context(
        project_name,
        story_id=story_id,
        capability=scope,
        query=query or json.dumps(generation_guidance or {}, ensure_ascii=False),
        chapter_no=chapter_no,
        generation_guidance=generation_guidance,
        prompt_option_ids=prompt_option_ids,
        manual_knowledge_ids=list((generation_guidance or {}).get("manual_knowledge_ids") or []),
        retrieval_profile=profile_by_scope.get(scope),
        allowed_scopes=["project", "canon", "reference"],
    )
    return assembly.model_dump()


def _render_generation_injection_preview(
    project_name: str,
    story_id: str,
    scope: str,
    prompt_option_ids: list[str] | None,
    generation_guidance: dict,
    *,
    query: str = "",
    chapter_no: int | None = None,
):
    with st.expander("本次生成注入预览", expanded=False):
        st.caption("点击刷新后，会使用与实际生成相同的装配器计算规则、设定、导演注、检索命中、预算与省略项。预览不会消耗一次性导演注。")
        request_payload = {
            "project_name": project_name,
            "story_id": story_id,
            "scope": scope,
            "prompt_option_ids": prompt_option_ids,
            "generation_guidance": generation_guidance,
            "query": query,
            "chapter_no": chapter_no,
        }
        request_fingerprint = hashlib.sha256(
            json.dumps(request_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        preview_state_key = scoped_widget_key(
            "generation_context_preview_state",
            project_name,
            story_id,
            scope,
            chapter_no if chapter_no is not None else "none",
        )
        if st.button(
            "刷新真实上下文预览",
            key=scoped_widget_key(
                "generation_context_preview_refresh",
                project_name,
                story_id,
                scope,
                chapter_no if chapter_no is not None else "none",
            ),
        ):
            try:
                st.session_state[preview_state_key] = {
                    "request_fingerprint": request_fingerprint,
                    "assembly": _build_generation_injection_preview(
                        project_name,
                        story_id,
                        scope,
                        prompt_option_ids,
                        generation_guidance,
                        query=query,
                        chapter_no=chapter_no,
                    ),
                }
            except Exception as exc:
                st.error(f"上下文预览失败：{exc}")

        preview_state = st.session_state.get(preview_state_key, {})
        assembly = preview_state.get("assembly") if isinstance(preview_state, dict) else None
        if not isinstance(assembly, dict):
            st.info("尚未计算预览。")
            return
        if preview_state.get("request_fingerprint") != request_fingerprint:
            st.warning("写作输入或选项已变化，当前预览已过期，请重新刷新。")

        metric_a, metric_b, metric_c = st.columns(3)
        metric_a.metric("预计上下文", f"{int(assembly.get('total_estimated_tokens') or 0)} tokens")
        metric_b.metric("预算", f"{int(assembly.get('context_budget') or 0)} tokens")
        metric_c.metric("检索命中", len(assembly.get("retrieval_hits") or []))
        st.caption(f"上下文指纹：`{assembly.get('fingerprint') or '-'}`")
        for warning in assembly.get("warnings", []):
            st.warning(str(warning))

        blocks = assembly.get("blocks") or []
        if not blocks:
            st.info("当前没有额外注入内容。")
        for index, block in enumerate(blocks, start=1):
            st.markdown(f"#### {index}. {block.get('category') or block.get('source_type')}")
            st.caption(
                f"位置：{block.get('placement') or '-'} · 来源：{block.get('source_type') or '-'} · "
                f"预计 {int(block.get('estimated_tokens') or 0)} tokens · 原因：{block.get('activation_reason') or '-'}"
            )
            st.code(str(block.get("content") or ""), language="markdown")

        omitted = assembly.get("omitted_blocks") or []
        if omitted:
            with st.expander(f"已省略上下文（{len(omitted)}）", expanded=False):
                for block in omitted:
                    st.markdown(f"- `{block.get('block_id')}`：{block.get('omission_reason') or '未说明'}")


def render_context_assembly_summary(assembly: dict, title: str = "实际生成上下文") -> None:
    if not isinstance(assembly, dict) or not assembly:
        return
    with st.expander(title, expanded=False):
        metric_a, metric_b, metric_c = st.columns(3)
        metric_a.metric("预计上下文", f"{int(assembly.get('total_estimated_tokens') or 0)} tokens")
        metric_b.metric("预算", f"{int(assembly.get('context_budget') or 0)} tokens")
        metric_c.metric("检索命中", len(assembly.get("retrieval_hits") or []))
        st.caption(f"上下文指纹：`{assembly.get('fingerprint') or '-'}`")
        for warning in assembly.get("warnings", []):
            st.warning(str(warning))
        for index, block in enumerate(assembly.get("blocks") or [], start=1):
            st.markdown(
                f"{index}. **{block.get('category') or block.get('source_type')}** · "
                f"{block.get('placement') or '-'} · {int(block.get('estimated_tokens') or 0)} tokens"
            )
            if block.get("activation_reason"):
                st.caption(str(block.get("activation_reason")))
        omitted = assembly.get("omitted_blocks") or []
        if omitted:
            st.caption(f"另有 {len(omitted)} 个上下文块因预算被省略。")
