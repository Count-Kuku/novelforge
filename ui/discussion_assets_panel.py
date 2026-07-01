"""Discussion-derived reusable asset review panel."""
from __future__ import annotations

import hashlib
import html
import logging

import streamlit as st

from asset_guardrails import (
    analyze_prompt_option_candidate,
    analyze_rule_candidate,
    analyze_setting_candidate,
)
from discussion_assets import build_discussion_asset_candidates
from memory import (
    load_global_prompt_options,
    load_global_rules,
    load_project_prompt_options,
    load_project_rules,
    load_story_prompt_options,
    load_story_rules,
    upsert_prompt_option,
)
from prompt_options import merge_prompt_option_layers
from setting_knowledge import SETTING_FIELD_SPECS, list_setting_items, upsert_setting_item
from skills import save_rule_text
from ui.common import scoped_widget_key
from ui.labels import label_knowledge_category
from ui.prompt_option_tools import _prompt_option_label
from ui.rules_page import RULE_SCOPE_OPTIONS


APP_LOGGER = logging.getLogger("novelforge.ui.discussion_assets_panel")


def _setting_field_label(field_name: str) -> str:
    spec = SETTING_FIELD_SPECS.get(str(field_name or ""), {})
    return str(spec.get("label") or field_name or "未知字段")


ASSET_GUARDRAIL_LEVEL_LABELS = {
    "duplicate": "可能重复",
    "warning": "需要确认",
    "related": "相关内容",
}


def _guardrail_item_label(item: dict) -> str:
    name = str(item.get("name") or item.get("title") or item.get("summary") or item.get("content") or "-").strip()
    return name[:80] + ("..." if len(name) > 80 else "")


def _render_asset_guardrail_issues(issues: list[dict]):
    if not issues:
        return
    duplicate_count = sum(1 for item in issues if item.get("level") == "duplicate")
    warning_count = sum(1 for item in issues if item.get("level") == "warning")
    if duplicate_count:
        st.warning(f"检测到 {duplicate_count} 个可能重复项，确认前建议检查是否需要覆盖。")
    elif warning_count:
        st.warning("检测到名称或同类内容相近的已有项，确认前建议检查。")
    else:
        st.info("检测到相关已有内容，可确认是并列补充还是重复记录。")
    for issue in issues:
        existing = issue.get("item") if isinstance(issue.get("item"), dict) else {}
        layer = str(issue.get("layer") or "")
        layer_text = f" / {layer}" if layer else ""
        label = ASSET_GUARDRAIL_LEVEL_LABELS.get(issue.get("level", ""), "相关内容")
        score = issue.get("score")
        score_text = f" / 相似度 {score}" if score else ""
        st.caption(f"{label}{layer_text}{score_text}：{issue.get('reason', '')} {_guardrail_item_label(existing)}")


def _guardrail_replace_target(issues: list[dict]) -> dict | None:
    for level in ["duplicate", "warning", "related"]:
        for issue in issues:
            if issue.get("level") != level:
                continue
            item = issue.get("item")
            if isinstance(item, dict) and item.get("id"):
                return item
    return None


def _setting_scope_pair(item: dict, fallback_story_id: str = "default") -> tuple[str, str]:
    scope = str(item.get("setting_scope") or "project").strip() or "project"
    if scope not in {"project", "story"}:
        scope = "project"
    item_story_id = str(item.get("story_id") or fallback_story_id).strip() if scope == "story" else ""
    return scope, item_story_id


def _same_setting_scope(candidate: dict, existing: dict, story_id: str) -> bool:
    normalized_candidate = dict(candidate)
    normalized_candidate["setting_scope"] = str(normalized_candidate.get("setting_scope") or "story")
    if normalized_candidate["setting_scope"] == "story":
        normalized_candidate["story_id"] = str(normalized_candidate.get("story_id") or story_id)
    candidate_scope, candidate_story_id = _setting_scope_pair(normalized_candidate, story_id)
    existing_scope, existing_story_id = _setting_scope_pair(existing, story_id)
    return candidate_scope == existing_scope and (candidate_scope != "story" or candidate_story_id == existing_story_id)


def _setting_replace_target(issues: list[dict], candidate: dict, story_id: str) -> dict | None:
    for level in ["duplicate", "warning", "related"]:
        for issue in issues:
            if issue.get("level") != level:
                continue
            item = issue.get("item")
            if isinstance(item, dict) and item.get("id") and _same_setting_scope(candidate, item, story_id):
                return item
    return None


def _setting_candidate_has_blocked_id_conflict(issues: list[dict], candidate_id: str, replace_target: dict | None) -> bool:
    target_id = str((replace_target or {}).get("id") or "")
    for issue in issues:
        item = issue.get("item")
        if not isinstance(item, dict):
            continue
        existing_id = str(item.get("id") or "")
        if existing_id and existing_id == candidate_id and existing_id != target_id:
            return True
    return False


def _fork_setting_candidate_id(item: dict, story_id: str) -> str:
    base_id = str(item.get("id") or "discussion_setting").strip() or "discussion_setting"
    raw = f"{story_id}:{item.get('category', '')}:{item.get('setting_field', '')}:{item.get('name', '')}:{item.get('summary', '')}"
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]
    return f"{base_id}_{digest}"


def _discussion_guardrail_inputs(project_name: str, story_id: str) -> tuple[list[dict], list[dict], list[tuple[str, dict]]]:
    try:
        existing_settings = list_setting_items(project_name, story_id, core_only=True)
    except Exception as exc:
        APP_LOGGER.warning(
            "Failed to load discussion setting guardrail inputs for project=%s story=%s: %s",
            project_name,
            story_id,
            exc,
        )
        existing_settings = []
    try:
        existing_prompt_options = merge_prompt_option_layers(
            load_global_prompt_options(),
            load_project_prompt_options(project_name),
            load_story_prompt_options(project_name, story_id),
        )
    except Exception as exc:
        APP_LOGGER.warning(
            "Failed to load discussion prompt-option guardrail inputs for project=%s story=%s: %s",
            project_name,
            story_id,
            exc,
        )
        existing_prompt_options = []
    rule_layers: list[tuple[str, dict]] = []
    for label, loader in [
        ("故事", lambda: load_story_rules(project_name, story_id)),
        ("项目", lambda: load_project_rules(project_name)),
        ("全局", load_global_rules),
    ]:
        try:
            rule_layers.append((label, loader()))
        except Exception as exc:
            APP_LOGGER.warning(
                "Failed to load %s discussion rule guardrail inputs for project=%s story=%s: %s",
                label,
                project_name,
                story_id,
                exc,
            )
            rule_layers.append((label, {}))
    return existing_settings, existing_prompt_options, rule_layers


def _discussion_asset_candidate_groups(discussion_step: dict, discussion_kind: str, story_id: str, source_ref: str) -> tuple[list[dict], list[dict], list[dict]]:
    candidates = build_discussion_asset_candidates(discussion_step, discussion_kind, story_id=story_id, source_ref=source_ref)
    return candidates.get("settings", []), candidates.get("prompt_options", []), candidates.get("rules", [])


def _apply_setting_candidate(project_name: str, story_id: str, item: dict, issues: list[dict], replace_target: dict | None, replace_existing: bool) -> None:
    payload = dict(item)
    target_category = str(payload.get("category") or "")
    if replace_existing and replace_target:
        payload["id"] = str(replace_target.get("id") or payload.get("id") or "")
        payload["setting_scope"] = str(replace_target.get("setting_scope") or payload.get("setting_scope") or "story")
        payload["story_id"] = str(replace_target.get("story_id") or payload.get("story_id") or story_id) if payload["setting_scope"] == "story" else ""
        target_category = str(replace_target.get("category") or target_category)
    else:
        payload["setting_scope"] = "story"
        payload["story_id"] = str(payload.get("story_id") or story_id)
        if _setting_candidate_has_blocked_id_conflict(issues, str(payload.get("id") or ""), replace_target):
            payload["id"] = _fork_setting_candidate_id(payload, story_id)
    saved = upsert_setting_item(project_name, target_category, payload)
    st.success(f"已保存核心设定：{saved.get('name')}")
    st.rerun()


def _render_setting_asset_candidate(project_name: str, story_id: str, key_prefix: str, item: dict, existing_settings: list[dict]) -> None:
    issues = analyze_setting_candidate(item, existing_settings)
    replace_target = _setting_replace_target(issues, item, story_id)
    st.markdown(f"**{html.escape(str(item.get('name') or '未命名设定'))}**")
    st.caption(
        f"{label_knowledge_category(str(item.get('category') or ''))} / "
        f"{_setting_field_label(str(item.get('setting_field') or ''))}"
    )
    st.write(str(item.get("summary") or ""))
    _render_asset_guardrail_issues(issues)
    replace_existing = False
    if replace_target:
        replace_existing = st.checkbox(
            f"用这个候选覆盖：{_guardrail_item_label(replace_target)}",
            value=False,
            key=scoped_widget_key("replace_discussion_setting", key_prefix, item.get("id", "")),
        )
    elif issues:
        st.caption("相近设定属于项目级或其他故事，不会被当前故事候选覆盖；如需调整，请到对应层级的核心设定页编辑。")
    if st.button(
        "保存为核心设定",
        key=scoped_widget_key("apply_discussion_setting", key_prefix, item.get("id", "")),
        use_container_width=True,
    ):
        _apply_setting_candidate(project_name, story_id, item, issues, replace_target, replace_existing)


def _render_setting_asset_candidates(project_name: str, story_id: str, key_prefix: str, setting_candidates: list[dict], existing_settings: list[dict]) -> None:
    if not setting_candidates:
        return
    st.markdown("#### 核心设定候选")
    for item in setting_candidates:
        _render_setting_asset_candidate(project_name, story_id, key_prefix, item, existing_settings)


def _apply_prompt_option_candidate(project_name: str, story_id: str, option: dict, replace_target: dict | None, replace_existing: bool, option_enabled: bool) -> None:
    payload = dict(option)
    if replace_existing and replace_target:
        payload["id"] = str(replace_target.get("id") or payload.get("id") or "")
    payload["scope"] = "story"
    payload["enabled"] = option_enabled
    payload["source"] = "discussion"
    upsert_prompt_option(project_name, "story", payload, story_id=story_id)
    st.success("已保存为当前故事的提示词要求。")
    st.rerun()


def _render_prompt_option_asset_candidate(project_name: str, story_id: str, key_prefix: str, option: dict, existing_prompt_options: list[dict]) -> None:
    issues = analyze_prompt_option_candidate(option, existing_prompt_options)
    replace_target = _guardrail_replace_target(issues)
    st.markdown(f"**{_prompt_option_label(option)}**")
    st.code(option.get("content", ""), language="markdown")
    _render_asset_guardrail_issues(issues)
    option_enabled = st.checkbox(
        "保存后启用",
        value=True,
        key=scoped_widget_key("enable_discussion_prompt_option", key_prefix, option.get("id", "")),
    )
    replace_existing = False
    if replace_target:
        replace_existing = st.checkbox(
            f"在当前故事层覆盖：{_guardrail_item_label(replace_target)}",
            value=False,
            key=scoped_widget_key("replace_discussion_prompt_option", key_prefix, option.get("id", "")),
        )
    if st.button(
        "保存为提示词要求",
        key=scoped_widget_key("apply_discussion_prompt_option", key_prefix, option.get("id", "")),
        use_container_width=True,
    ):
        _apply_prompt_option_candidate(project_name, story_id, option, replace_target, replace_existing, option_enabled)


def _render_prompt_option_asset_candidates(project_name: str, story_id: str, key_prefix: str, prompt_option_candidates: list[dict], existing_prompt_options: list[dict]) -> None:
    if not prompt_option_candidates:
        return
    st.markdown("#### 提示词要求候选")
    for option in prompt_option_candidates:
        _render_prompt_option_asset_candidate(project_name, story_id, key_prefix, option, existing_prompt_options)


def _apply_rule_candidate(project_name: str, story_id: str, rule: dict) -> None:
    result = save_rule_text(
        project_name,
        str(rule.get("scope") or "all"),
        "story",
        str(rule.get("content") or ""),
        story_id=story_id,
    )
    if result.get("status") == "saved":
        st.success(f"已保存 {len(result.get('saved_rules', []))} 条故事规则。")
    else:
        st.info("没有新增规则，可能已经存在。")
    st.rerun()


def _render_rule_asset_candidate(project_name: str, story_id: str, key_prefix: str, rule: dict, rule_layers: list[tuple[str, dict]]) -> None:
    issues = analyze_rule_candidate(rule, rule_layers)
    st.markdown(f"**{html.escape(str(rule.get('title') or '讨论规则'))}**")
    st.caption(f"作用范围：{RULE_SCOPE_OPTIONS.get(rule.get('scope', 'all'), rule.get('scope', 'all'))} / 目标：当前故事")
    st.code(rule.get("content", ""), language="markdown")
    _render_asset_guardrail_issues(issues)
    if st.button(
        "保存为故事规则",
        key=scoped_widget_key("apply_discussion_rule", key_prefix, rule.get("id", "")),
        use_container_width=True,
    ):
        _apply_rule_candidate(project_name, story_id, rule)


def _render_rule_asset_candidates(project_name: str, story_id: str, key_prefix: str, rule_candidates: list[dict], rule_layers: list[tuple[str, dict]]) -> None:
    if not rule_candidates:
        return
    st.markdown("#### 故事规则候选")
    for rule in rule_candidates:
        _render_rule_asset_candidate(project_name, story_id, key_prefix, rule, rule_layers)


def render_discussion_asset_candidates(
    project_name: str,
    story_id: str,
    discussion_step: dict,
    discussion_kind: str,
    source_ref: str,
    key_prefix: str,
):
    setting_candidates, prompt_option_candidates, rule_candidates = _discussion_asset_candidate_groups(
        discussion_step, discussion_kind, story_id, source_ref
    )
    if not (setting_candidates or prompt_option_candidates or rule_candidates):
        return
    existing_settings, existing_prompt_options, rule_layers = _discussion_guardrail_inputs(project_name, story_id)
    with st.expander("讨论产生的生成依据", expanded=False):
        st.caption("把本次讨论中明确下来的设定、提示词要求或故事规则保存下来，后续生成会使用。")
        _render_setting_asset_candidates(project_name, story_id, key_prefix, setting_candidates, existing_settings)
        _render_prompt_option_asset_candidates(project_name, story_id, key_prefix, prompt_option_candidates, existing_prompt_options)
        _render_rule_asset_candidates(project_name, story_id, key_prefix, rule_candidates, rule_layers)
