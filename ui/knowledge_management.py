"""Knowledge management and ingestion review panels."""
from __future__ import annotations

import json

import streamlit as st

from novelforge.services.memory import (
    confirm_pending_knowledge_items,
    discard_pending_knowledge_items,
    load_auto_review_policy,
    load_auto_review_runs,
    load_entity_aliases,
    load_knowledge_base,
    load_knowledge_category,
    load_knowledge_revisions,
    load_knowledge_evidence,
    load_long_reference_batch,
    load_pending_knowledge_items,
    load_source_package_report,
    queue_pending_knowledge_items,
    restore_auto_review_snapshots_to_pending,
    return_confirmed_knowledge_item_to_pending,
    rollback_auto_review_run,
    save_auto_review_policy,
    save_entity_aliases,
    save_pending_knowledge_items,
    save_source_package_report,
)
from novelforge.services.retrieval import rebuild_retrieval_assets
from novelforge.workflows.source_workflows import (
    auto_confirm_pending_items_without_risk,
    build_ingestion_health_report,
    build_ingestion_source_ledger,
    build_source_package_report,
    get_segment_related_knowledge_items,
    read_retrieval_source_payload,
)
from novelforge.domain.knowledge_entities import (
    SETTING_ENTITY_CATEGORY_GROUPS,
    build_character_entity_cards,
    build_merged_knowledge_item,
    build_setting_entity_cards,
)
from novelforge.domain.knowledge_types import validate_typed_knowledge_item
from novelforge.domain.knowledge_quality import (
    build_pending_issue_map,
    build_pending_knowledge_quality_issues,
    find_duplicate_knowledge_groups,
    merge_list_values,
    upsert_entity_alias_group,
)
from novelforge.domain.knowledge_workflows import (
    build_pending_auto_review_preview,
    build_pending_clear_plan,
    build_pending_triage_summary,
    delete_confirmed_knowledge_items,
    execute_pending_clear_plan,
    filter_pending_knowledge_indices_by_values,
    merge_confirmed_knowledge_items,
    pending_quality_label,
    parse_comma_tags,
    replace_knowledge_category_items,
    safe_confidence,
    save_confirmed_knowledge_item,
    summarize_item_evidence,
    update_pending_knowledge_item,
)
from ui.common import confirmed_button, developer_mode_enabled, scoped_widget_key
from ui.knowledge_type_editor import render_typed_knowledge_fields
from ui.layout import render_empty_state, render_section_heading, render_stat_strip
from ui.labels import (
    KNOWLEDGE_CATEGORY_LABELS,
    label_authority,
    label_batch_segment_status,
    label_knowledge_category,
    label_scope,
    label_source_type,
)


VERSION_SCOPE_LABELS = {
    "canon": "原作/官方",
    "project_main": "本项目主线",
    "au": "AU/分支",
    "mixed": "混合/待拆分",
    "unknown": "未标明",
}


DEFAULT_WORLDLINE_ID = "main"


DEFAULT_WORLDLINE_LABEL = "本项目主线"


def _render_pending_queue_metrics(pending_items: list[dict], filtered_indices: list[int], issue_map: dict) -> None:
    st.caption(f"当前筛选结果：{len(filtered_indices)} / {len(pending_items)} 条")
    if not filtered_indices:
        return
    metric_cols = st.columns(4)
    metric_cols[0].metric("高风险", sum(1 for index in filtered_indices if issue_map.get(str(pending_items[index].get("pending_id", "")), {}).get("severity") == "高"))
    metric_cols[1].metric("低证据", sum(1 for index in filtered_indices if safe_confidence(pending_items[index].get("evidence_strength", 0.5)) < 0.45))
    metric_cols[2].metric("低置信", sum(1 for index in filtered_indices if safe_confidence(pending_items[index].get("confidence", 0.7)) < 0.55))
    metric_cols[3].metric("正式库重叠", sum(1 for index in filtered_indices if "confirmed_overlap" in issue_map.get(str(pending_items[index].get("pending_id", "")), {}).get("types", set())))


def _render_pending_selection(
    project_name: str,
    pending_items: list[dict],
    filtered_indices: list[int],
    issue_map: dict,
) -> list[int]:
    return st.multiselect(
        "选择要处理的条目",
        options=filtered_indices,
        default=filtered_indices[: min(10, len(filtered_indices))],
        format_func=lambda index: (
            f"{index + 1}. {label_knowledge_category(pending_items[index].get('category', ''))}"
            f" / {pending_items[index].get('name', '未命名')}"
            f" / {pending_quality_label(issue_map.get(str(pending_items[index].get('pending_id', '')), {}))}"
            f" / {label_scope(pending_items[index].get('scope', 'reference'))}"
        ),
        key=scoped_widget_key("pending_knowledge_selected_indices", project_name),
    )


def _render_pending_item_preview(index: int, item: dict, issue_map: dict) -> None:
    pending_id = str(item.get("pending_id", ""))
    issue_info = issue_map.get(pending_id, {})
    st.markdown(f"#### {index + 1}. {label_knowledge_category(item.get('category', ''))} / {item.get('name', '未命名')}")
    st.caption(
        f"{pending_quality_label(issue_info)} / 范围={label_scope(item.get('scope', 'reference'))} / "
        f"可信度={safe_confidence(item.get('confidence', 0.7)):.2f} / 证据={safe_confidence(item.get('evidence_strength', 0.5)):.2f} / "
        f"可信度={label_authority(item.get('authority', 'curated'))} / 来源={item.get('source_title', '-') or '-'}"
    )
    if item.get("source_segment_title") or item.get("source_segment_index") is not None:
        st.caption(f"片段：{item.get('source_segment_index', '-')}. {item.get('source_segment_title', '-')}")
    if item.get("summary"):
        st.write(item.get("summary"))
    evidence_lines = summarize_item_evidence(item)
    if evidence_lines:
        st.caption("证据：" + "；".join(evidence_lines[:2]))
    evidence_contexts = item.get("evidence_contexts", []) if isinstance(item.get("evidence_contexts", []), list) else []
    if evidence_contexts:
        context = evidence_contexts[0]
        st.caption(
            f"证据定位：段落 {context.get('paragraph_index', '-') or '-'} / 字符位置 {context.get('char_index', '-') if context.get('char_index') is not None else '-'}"
        )
        if context.get("context"):
            st.caption("上下文：" + str(context.get("context"))[:260])
    if issue_info.get("descriptions"):
        st.warning(" / ".join(issue_info.get("descriptions", [])[:2]))
    if item.get("tags"):
        st.caption(f"标签：{', '.join(str(tag) for tag in item.get('tags', []))}")


def _render_pending_preview_list(pending_items: list[dict], filtered_indices: list[int], issue_map: dict) -> None:
    preview_limit = st.slider(
        "预览条目数",
        min_value=5,
        max_value=80,
        value=min(30, max(5, len(filtered_indices))),
        step=5,
        key="pending_knowledge_preview_limit",
    )
    for index in filtered_indices[: int(preview_limit)]:
        _render_pending_item_preview(index, pending_items[index], issue_map)
    if len(filtered_indices) > int(preview_limit):
        st.caption(f"仅预览前 {int(preview_limit)} 条筛选结果，共 {len(filtered_indices)} 条。")


def _pending_selected_ids(pending_items: list[dict], selected_indices: list[int]) -> list[str]:
    return [
        str(pending_items[index].get("pending_id", ""))
        for index in selected_indices
        if 0 <= index < len(pending_items) and pending_items[index].get("pending_id")
    ]


def _render_pending_auto_review_preview(auto_preview: dict) -> None:
    preview_cols = st.columns(4)
    preview_cols[0].metric("候选条目", auto_preview.get("candidate_count", 0))
    preview_cols[1].metric("可自动确认", len(auto_preview.get("confirmed_ids", [])))
    preview_cols[2].metric("A 级", auto_preview.get("grade_counts", {}).get("A", 0))
    preview_cols[3].metric("保留待审核", len(auto_preview.get("blocked_ids", [])))
    reason_counts = auto_preview.get("blocked_reason_counts", {})
    if reason_counts:
        st.caption("主要保留原因：" + " / ".join(f"{reason}={count}" for reason, count in list(reason_counts.items())[:8]))
    preview_rows = auto_preview.get("rows", [])[:80]
    if preview_rows:
        st.dataframe(preview_rows, width="stretch", hide_index=True)
        if len(auto_preview.get("rows", [])) > len(preview_rows):
            st.caption(f"仅展示前 {len(preview_rows)} 条预检结果。")


def _render_pending_auto_review_panel(
    project_name: str,
    pending_items: list[dict],
    filtered_indices: list[int],
    selected_indices: list[int],
    issue_map: dict,
    policy: dict,
) -> None:
    with st.expander("自动审核预检与批量处理", expanded=False):
        st.caption("这里不会重新调用模型，只按当前自动审核策略和质检结果判断哪些条目可以自动保存，哪些仍保留给人工审核。")
        auto_scope = st.radio(
            "预检范围",
            options=["当前筛选结果", "已选择条目"],
            horizontal=True,
            key=scoped_widget_key("pending_auto_review_scope", project_name),
        )
        auto_candidate_indices = filtered_indices if auto_scope == "当前筛选结果" else selected_indices
        auto_candidate_items = [pending_items[index] for index in auto_candidate_indices if 0 <= index < len(pending_items)]
        auto_preview = build_pending_auto_review_preview(auto_candidate_items, issue_map, policy)
        _render_pending_auto_review_preview(auto_preview)
        auto_candidate_ids = [str(item.get("pending_id") or "") for item in auto_candidate_items if item.get("pending_id")]
        if st.button(
            "按当前策略自动确认低风险条目",
            key=scoped_widget_key(
                "pending_run_auto_review",
                project_name,
                "|".join(sorted(auto_candidate_ids)) or "__empty__",
            ),
            width="stretch",
        ):
            if not auto_candidate_ids:
                st.error("当前范围内没有可审核条目。")
            else:
                auto_summary = auto_confirm_pending_items_without_risk(
                    project_name,
                    auto_candidate_ids,
                    source_type="pending_queue_manual_auto_review",
                    source_title=f"待审核设定 / {auto_scope}",
                    note="用户在待审核设定中手动触发自动审核",
                )
                st.success(
                    f"自动审核完成：确认 {len(auto_summary.get('confirmed_ids', []))} 条，"
                    f"保留 {len(auto_summary.get('blocked_ids', []))} 条。"
                )
                if auto_summary.get("run_id"):
                    st.caption(f"处理记录 ID：{auto_summary.get('run_id')}")
                st.rerun()


def _render_pending_bulk_actions(project_name: str, selected_ids: list[str]) -> None:
    col_a, col_b = st.columns(2)
    selection_scope = "|".join(sorted(selected_ids)) or "__empty__"
    if col_a.button(
        "确认所选并写入知识库条目",
        key=scoped_widget_key("confirm_selected_pending_knowledge", project_name, selection_scope),
    ):
        if not selected_ids:
            st.error("请先选择条目。")
        else:
            saved_count = confirm_pending_knowledge_items(project_name, selected_ids)
            if saved_count:
                rebuild_retrieval_assets(project_name, build_vectors=True)
            st.success(f"已确认 {saved_count} 条知识库条目。")
            st.rerun()
    if confirmed_button(
        col_b,
        "丢弃所选待审核设定",
        "确认丢弃所选条目",
        scoped_widget_key("discard_selected_pending_knowledge", project_name, selection_scope),
    ):
        if not selected_ids:
            st.error("请先选择条目。")
        else:
            removed_count = discard_pending_knowledge_items(project_name, selected_ids)
            st.success(f"已丢弃 {removed_count} 条待审核设定。")
            st.rerun()


def _render_pending_raw_json_editor(project_name: str, pending_items: list[dict]) -> None:
    with st.expander("高级：待审核设定原始数据", expanded=False):
        serialized_pending = json.dumps(pending_items, ensure_ascii=False, indent=2)
        pending_json = st.text_area(
            "pending.json",
            value=serialized_pending,
            height=360,
            key=scoped_widget_key("pending_knowledge_raw_json", project_name, serialized_pending),
        )
        if st.button(
            "保存待审核设定修改",
            key=scoped_widget_key("save_pending_knowledge_raw_json", project_name),
        ):
            try:
                parsed = json.loads(pending_json)
                if not isinstance(parsed, list):
                    st.error("待审核设定必须是列表结构。")
                else:
                    save_pending_knowledge_items(project_name, parsed)
                    st.success("待审核设定已保存。")
                    st.rerun()
            except json.JSONDecodeError as exc:
                st.error(f"详细数据格式错误：{exc}")


def render_pending_knowledge_queue(project_name: str):
    pending_items = load_pending_knowledge_items(project_name)
    pending_count = len(pending_items)
    render_section_heading(
        "待审核知识",
        "提取结果只有在这里确认后，才会成为写作时可以检索的正式知识。",
    )
    if not pending_items:
        render_empty_state("暂无待审核内容", "新的资料提取结果会自动出现在这里。")
        return

    quality_issues = build_pending_knowledge_quality_issues(project_name, pending_items)
    issue_map = build_pending_issue_map(quality_issues)
    policy = load_auto_review_policy(project_name)
    high_risk_count = sum(1 for issue in quality_issues if issue.get("severity") == "高")
    render_stat_strip(
        [
            ("待审核", pending_count, "条"),
            ("高风险", high_risk_count, "优先处理"),
            ("自动审核", "已开启" if policy.get("enabled", True) else "未开启", "按当前策略"),
        ]
    )
    review_views = ["逐条审核", "批量处理", "质检问题"]
    if developer_mode_enabled():
        review_views.append("技术数据")
    view = st.segmented_control(
        "审核视图",
        options=review_views,
        default="逐条审核",
        key=scoped_widget_key("pending_knowledge_view", project_name),
        label_visibility="collapsed",
    )

    if view == "质检问题":
        render_pending_knowledge_quality_panel(project_name, pending_items)
        return
    if view == "技术数据":
        st.warning("原始数据编辑会跳过普通表单校验，只建议用于故障恢复。")
        _render_pending_raw_json_editor(project_name, pending_items)
        return

    filtered_indices = filter_pending_knowledge_indices(pending_items, issue_map)
    _render_pending_queue_metrics(pending_items, filtered_indices, issue_map)
    selected_indices = _render_pending_selection(project_name, pending_items, filtered_indices, issue_map)
    selected_ids = _pending_selected_ids(pending_items, selected_indices)
    if view == "批量处理":
        render_pending_triage_dashboard(project_name, pending_items, issue_map, policy)
        _render_pending_auto_review_panel(project_name, pending_items, filtered_indices, selected_indices, issue_map, policy)
        _render_pending_bulk_actions(project_name, selected_ids)
    else:
        _render_pending_preview_list(pending_items, filtered_indices, issue_map)
        render_pending_knowledge_item_editor(project_name, pending_items, filtered_indices)
        _render_pending_bulk_actions(project_name, selected_ids)


def render_auto_review_policy_panel(project_name: str):
    policy = load_auto_review_policy(project_name)
    with st.expander("自动审核策略", expanded=False):
        st.caption("控制低风险设定是否自动保存。策略越严格，保留待审核的内容越多；策略越宽松，人工审核负担越低。")
        col_conf, col_evidence = st.columns(2)
        min_confidence = col_conf.slider(
            "自动确认最低置信度",
            min_value=0.0,
            max_value=1.0,
            value=float(policy.get("min_confidence", 0.45)),
            step=0.05,
            key="auto_review_policy_min_confidence",
        )
        min_evidence_strength = col_evidence.slider(
            "自动确认最低证据强度",
            min_value=0.0,
            max_value=1.0,
            value=float(policy.get("min_evidence_strength", 0.35)),
            step=0.05,
            key="auto_review_policy_min_evidence",
        )
        col_grade_a, col_grade_e = st.columns(2)
        grade_a_confidence = col_grade_a.slider(
            "A 级置信度阈值",
            min_value=0.0,
            max_value=1.0,
            value=float(policy.get("grade_a_confidence", 0.75)),
            step=0.05,
            key="auto_review_policy_grade_a_confidence",
        )
        grade_a_evidence_strength = col_grade_e.slider(
            "A 级证据阈值",
            min_value=0.0,
            max_value=1.0,
            value=float(policy.get("grade_a_evidence_strength", 0.65)),
            step=0.05,
            key="auto_review_policy_grade_a_evidence",
        )
        allow_grade_b_auto_confirm = st.checkbox(
            "允许 B 级条目自动确认",
            value=bool(policy.get("allow_grade_b_auto_confirm", True)),
            key="auto_review_policy_allow_grade_b",
            help="关闭后，只有 A 级条目会自动保存，B 级会保留用于抽查。",
        )
        require_evidence = st.checkbox(
            "自动确认必须有证据",
            value=bool(policy.get("require_evidence", True)),
            key="auto_review_policy_require_evidence",
        )
        manual_review_categories = st.multiselect(
            "必须人工审核的分类",
            options=list(KNOWLEDGE_CATEGORY_LABELS.keys()),
            default=[
                category
                for category in policy.get("manual_review_categories", ["constraints"])
                if category in KNOWLEDGE_CATEGORY_LABELS
            ],
            format_func=label_knowledge_category,
            key="auto_review_policy_manual_categories",
            help="这些分类永远不会自动确认，适合硬性约束、世界规则等高影响资料。",
        )
        if st.button("保存自动审核策略", key="save_auto_review_policy", width="stretch"):
            saved = save_auto_review_policy(project_name, {
                "min_confidence": min_confidence,
                "min_evidence_strength": min_evidence_strength,
                "grade_a_confidence": grade_a_confidence,
                "grade_a_evidence_strength": grade_a_evidence_strength,
                "allow_grade_b_auto_confirm": allow_grade_b_auto_confirm,
                "require_evidence": require_evidence,
                "manual_review_categories": manual_review_categories,
            })
            st.success("自动审核策略已保存。")
            if developer_mode_enabled():
                st.json(saved)


def _render_auto_review_run_metrics(runs: list[dict]) -> None:
    active_runs = [run for run in runs if str(run.get("status") or "active") != "rolled_back"]
    metric_cols = st.columns(4)
    metric_cols[0].metric("记录数", len(runs))
    metric_cols[1].metric("可回退", len(active_runs))
    metric_cols[2].metric("保存", sum(len(run.get("confirmed_ids", []) or []) for run in runs))
    metric_cols[3].metric("归档/复核", sum(len(run.get("archived_ids", []) or []) + len(run.get("manual_review_ids", []) or []) for run in runs))


def _auto_review_run_label(runs: list[dict], run_id: str) -> str:
    return next(
        (
            f"{run.get('created_at', '-')[:19]} / {run.get('source_title') or run.get('source_type') or '自动审核'}"
            f" / 保存 {len(run.get('confirmed_ids', []) or [])}"
            f" / 归档 {len(run.get('archived_ids', []) or [])}"
            f" / 复核 {len(run.get('manual_review_ids', []) or [])}"
            f" / {'已回退' if run.get('status') == 'rolled_back' else '可回退'}"
            for run in runs
            if str(run.get("run_id") or "") == run_id
        ),
        run_id,
    )


def _select_auto_review_run(runs: list[dict]) -> tuple[str, dict]:
    selected_run_id = st.selectbox(
        "选择处理记录",
        options=[str(run.get("run_id") or "") for run in runs],
        format_func=lambda run_id: _auto_review_run_label(runs, run_id),
        key="auto_review_run_select",
    )
    selected_run = next((run for run in runs if str(run.get("run_id") or "") == selected_run_id), {})
    return selected_run_id, selected_run


def _render_auto_review_run_header(selected_run: dict) -> None:
    st.caption(
        f"处理记录 ID={selected_run.get('run_id', '')} / 来源={selected_run.get('source_type', '-') or '-'} / "
        f"批次={selected_run.get('batch_id', '-') or '-'} / 状态={selected_run.get('status', 'active')}"
    )
    if selected_run.get("note"):
        st.info(str(selected_run.get("note")))


def _render_auto_review_batch_summary(selected_run: dict) -> None:
    batch_summary = selected_run.get("batch_summary", {}) if isinstance(selected_run.get("batch_summary", {}), dict) else {}
    if not batch_summary:
        return
    batch_cols = st.columns(4)
    batch_cols[0].metric("本批次", batch_summary.get("total", 0))
    batch_cols[1].metric("保存", batch_summary.get("confirmed", len(selected_run.get("confirmed_ids", []) or [])))
    batch_cols[2].metric("归档", batch_summary.get("archived", len(selected_run.get("archived_ids", []) or [])))
    batch_cols[3].metric("复核箱", batch_summary.get("manual_review", len(selected_run.get("manual_review_ids", []) or [])))


def _render_auto_review_reason_counts(selected_run: dict) -> None:
    reason_counts: dict[str, int] = {}
    for reason in (selected_run.get("blocked_reasons", {}) or {}).values():
        reason_counts[str(reason or "未说明")] = reason_counts.get(str(reason or "未说明"), 0) + 1
    if reason_counts:
        st.caption("保留原因：" + " / ".join(f"{reason}={count}" for reason, count in reason_counts.items()))


def _auto_review_decision_rows(selected_run: dict) -> list[dict]:
    rows = []
    for decision in selected_run.get("decisions", [])[:80] if isinstance(selected_run.get("decisions", []), list) else []:
        if not isinstance(decision, dict):
            continue
        action = str(decision.get("action") or "")
        decision_value = str(decision.get("decision") or "")
        decision_label = {
            "confirm": "自动保存",
            "archive": "归档丢弃",
            "manual_review": "人工复核箱",
        }.get(action) or ("自动确认" if decision_value == "confirm" else "保留待审核")
        rows.append({
            "决策": decision_label,
            "等级": decision.get("grade", ""),
            "分类": label_knowledge_category(decision.get("category", "")),
            "名称": decision.get("name", ""),
            "原因": decision.get("reason", ""),
        })
    return rows


def _render_auto_review_decisions(selected_run: dict) -> None:
    rows = _auto_review_decision_rows(selected_run)
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
        if len(selected_run.get("decisions", []) or []) > len(rows):
            st.caption(f"仅展示前 {len(rows)} 条决策。")


def _restored_manual_review_ids(selected_run: dict) -> set[str]:
    return {
        str(item or "")
        for item in selected_run.get("restored_pending_ids", [])
        if str(item or "").strip()
    }


def _manual_review_snapshot_rows(manual_snapshots: list[dict], restored_ids: set[str]) -> list[dict]:
    return [
        {
            "分类": label_knowledge_category(item.get("category", "")),
            "名称": item.get("name", ""),
            "摘要": str(item.get("summary", ""))[:120],
            "来源": item.get("source_title", "") or item.get("source_segment_title", ""),
            "状态": "已恢复" if str(item.get("pending_id") or "") in restored_ids else "待恢复",
        }
        for item in manual_snapshots[:120]
    ]


def _restorable_manual_review_snapshots(manual_snapshots: list[dict], restored_ids: set[str]) -> list[dict]:
    return [
        item for item in manual_snapshots
        if isinstance(item, dict)
        and str(item.get("pending_id") or "").strip()
        and str(item.get("pending_id") or "") not in restored_ids
    ]


def _restore_auto_review_snapshots(project_name: str, selected_run_id: str, pending_ids: list[str]) -> None:
    result = restore_auto_review_snapshots_to_pending(project_name, selected_run_id, pending_ids)
    if result.get("success"):
        st.success(result.get("message", "已恢复。"))
        st.rerun()
    else:
        st.error(result.get("message", "恢复失败。"))


def _render_manual_review_snapshots(project_name: str, selected_run_id: str, selected_run: dict) -> None:
    manual_snapshots = selected_run.get("manual_review_snapshots", []) if isinstance(selected_run.get("manual_review_snapshots", []), list) else []
    if not manual_snapshots:
        return
    with st.expander(f"人工复核箱预览（{len(manual_snapshots)}）", expanded=True):
        restored_ids = _restored_manual_review_ids(selected_run)
        st.dataframe(_manual_review_snapshot_rows(manual_snapshots, restored_ids), width="stretch", hide_index=True)
        if len(manual_snapshots) > 120:
            st.caption("仅展示前 120 条，完整快照保存在原始数据里。")
        restorable_snapshots = _restorable_manual_review_snapshots(manual_snapshots, restored_ids)
        selected_restore_ids = st.multiselect(
            "选择要恢复到待审核设定的复核条目",
            options=[str(item.get("pending_id") or "") for item in restorable_snapshots],
            format_func=lambda pending_id: next(
                (
                    f"{label_knowledge_category(item.get('category', ''))} / {item.get('name', pending_id)}"
                    for item in restorable_snapshots
                    if str(item.get("pending_id") or "") == pending_id
                ),
                pending_id,
            ),
            key=f"restore_manual_review_ids_{selected_run_id}",
        )
        restore_cols = st.columns(2)
        if restore_cols[0].button(
            "恢复所选到待审核设定",
            key=f"restore_manual_review_selected_{selected_run_id}",
            disabled=not selected_restore_ids,
            width="stretch",
        ):
            _restore_auto_review_snapshots(project_name, selected_run_id, selected_restore_ids)
        if restore_cols[1].button(
            f"恢复全部未恢复（{len(restorable_snapshots)}）",
            key=f"restore_manual_review_all_{selected_run_id}",
            disabled=not restorable_snapshots,
            width="stretch",
        ):
            _restore_auto_review_snapshots(project_name, selected_run_id, [str(item.get("pending_id") or "") for item in restorable_snapshots])


def _render_auto_review_rollback(project_name: str, selected_run_id: str, selected_run: dict) -> None:
    if selected_run.get("status") == "rolled_back":
        result = selected_run.get("rollback_result", {})
        st.warning(f"该记录已回退：删除 {result.get('removed_count', 0)} 条正式知识，恢复 {result.get('restored_count', 0)} 条待审核设定。")
        return
    confirm_text = st.text_input(
        "输入处理记录 ID 以确认回退",
        key=f"rollback_auto_review_confirm_{selected_run_id}",
        placeholder=selected_run_id,
    )
    if st.button("回退这次处理", key=f"rollback_auto_review_{selected_run_id}", width="stretch"):
        if confirm_text.strip() != selected_run_id:
            st.error("请先输入完整处理记录 ID，避免误回退。")
        else:
            result = rollback_auto_review_run(project_name, selected_run_id)
            if result.get("success"):
                st.success(result.get("message", "已回退。"))
                st.rerun()
            else:
                st.error(result.get("message", "回退失败。"))


def render_auto_review_runs_panel(project_name: str):
    runs = list(reversed(load_auto_review_runs(project_name)))
    with st.expander(f"处理记录与人工复核箱（{len(runs)}）", expanded=bool(runs)):
        st.caption("这里保存自动确认和批量处理方案的记录。发现误处理时，可以按批次回退。")
        if not runs:
            st.caption("当前还没有批量处理记录。")
            return

        _render_auto_review_run_metrics(runs)
        selected_run_id, selected_run = _select_auto_review_run(runs)
        if not selected_run:
            return
        _render_auto_review_run_header(selected_run)
        _render_auto_review_batch_summary(selected_run)
        _render_auto_review_reason_counts(selected_run)
        _render_auto_review_decisions(selected_run)
        _render_manual_review_snapshots(project_name, selected_run_id, selected_run)
        if developer_mode_enabled():
            with st.expander("高级：处理记录原始数据", expanded=False):
                st.json(selected_run)
        _render_auto_review_rollback(project_name, selected_run_id, selected_run)


def _select_pending_knowledge_item(
    project_name: str,
    pending_items: list[dict],
    filtered_indices: list[int],
) -> tuple[dict, str]:
    selected_index = st.selectbox(
        "选择要编辑的条目",
        options=filtered_indices,
        format_func=lambda index: (
            f"{index + 1}. {label_knowledge_category(pending_items[index].get('category', ''))}"
            f" / {pending_items[index].get('name', '未命名')}"
            f" / {pending_items[index].get('source_title', '-') or '-'}"
        ),
        key=scoped_widget_key("pending_item_editor_select", project_name),
    )
    item = dict(pending_items[selected_index])
    return item, str(item.get("pending_id") or "")


def _pending_item_json_defaults(item: dict) -> tuple[str, str, str, str]:
    details_value = json.dumps(item.get("details", {}) if isinstance(item.get("details", {}), dict) else {}, ensure_ascii=False, indent=2)
    evidence_value = json.dumps(item.get("evidence", []) if isinstance(item.get("evidence", []), list) else [], ensure_ascii=False, indent=2)
    evidence_contexts_value = json.dumps(item.get("evidence_contexts", []) if isinstance(item.get("evidence_contexts", []), list) else [], ensure_ascii=False, indent=2)
    tags_value = ", ".join(str(tag) for tag in item.get("tags", []) if str(tag).strip()) if isinstance(item.get("tags"), list) else ""
    return details_value, evidence_value, evidence_contexts_value, tags_value


def _render_pending_item_basic_fields(item: dict) -> dict:
    col_a, col_b = st.columns(2)
    category = col_a.selectbox(
        "分类",
        options=list(KNOWLEDGE_CATEGORY_LABELS.keys()),
        index=list(KNOWLEDGE_CATEGORY_LABELS.keys()).index(item.get("category")) if item.get("category") in KNOWLEDGE_CATEGORY_LABELS else 0,
        format_func=label_knowledge_category,
    )
    name = col_b.text_input("名称", value=str(item.get("name") or ""))
    summary = st.text_area("摘要", value=str(item.get("summary") or ""), height=110)
    return {"category": category, "name": name, "summary": summary}


def _render_pending_item_scope_fields(item: dict) -> dict:
    col_scope, col_authority, col_canon = st.columns(3)
    scope_options = ["project", "canon", "reference"]
    authority_options = ["project", "official", "curated", "community", "unknown"]
    canon_options = ["canon", "inferred", "ambiguous", "fanon", "user_override", "unknown"]
    return {
        "scope": col_scope.selectbox(
            "范围",
            options=scope_options,
            index=scope_options.index(item.get("scope")) if item.get("scope") in scope_options else 2,
            format_func=label_scope,
        ),
        "authority": col_authority.selectbox(
            "资料可信度",
            options=authority_options,
            index=authority_options.index(item.get("authority")) if item.get("authority") in authority_options else 2,
            format_func=label_authority,
        ),
        "canon_status": col_canon.selectbox(
            "原作状态",
            options=canon_options,
            index=canon_options.index(item.get("canon_status")) if item.get("canon_status") in canon_options else 5,
        ),
    }


def _render_pending_item_version_fields(item: dict) -> dict:
    col_version, col_worldline = st.columns(2)
    version_scope = col_version.selectbox(
        "资料版本范围",
        options=list(VERSION_SCOPE_LABELS.keys()),
        index=list(VERSION_SCOPE_LABELS.keys()).index(item.get("version_scope")) if item.get("version_scope") in VERSION_SCOPE_LABELS else 4,
        format_func=lambda value: VERSION_SCOPE_LABELS.get(value, value),
    )
    worldline_id = col_worldline.text_input("资料版本标识", value=str(item.get("worldline_id") or DEFAULT_WORLDLINE_ID))
    worldline_label = st.text_input("资料版本名称", value=str(item.get("worldline_label") or DEFAULT_WORLDLINE_LABEL))
    return {"version_scope": version_scope, "worldline_id": worldline_id, "worldline_label": worldline_label}


def _render_pending_item_score_fields(item: dict) -> dict:
    col_conf, col_imp, col_ev = st.columns(3)
    return {
        "confidence": col_conf.slider("置信度", 0.0, 1.0, safe_confidence(item.get("confidence", 0.7)), 0.05),
        "importance": col_imp.slider("重要性", 0.0, 1.0, safe_confidence(item.get("importance", 0.5)), 0.05),
        "evidence_strength": col_ev.slider("证据强度", 0.0, 1.0, safe_confidence(item.get("evidence_strength", 0.5)), 0.05),
    }


def _render_pending_item_source_fields(item: dict, tags_value: str) -> dict:
    col_source, col_origin = st.columns(2)
    col_seg_a, col_seg_b = st.columns(2)
    return {
        "source_title": col_source.text_input("来源标题", value=str(item.get("source_title") or "")),
        "source_origin": col_origin.text_input("来源说明/链接", value=str(item.get("source_origin") or "")),
        "tags": st.text_input("标签（逗号分隔）", value=tags_value),
        "source_segment_title": col_seg_a.text_input("来源片段标题", value=str(item.get("source_segment_title") or "")),
        "source_segment_id": col_seg_b.text_input("来源片段 ID（可选）", value=str(item.get("source_segment_id") or "")),
    }


def _render_pending_item_json_fields(details_value: str, evidence_value: str, evidence_contexts_value: str) -> dict:
    if not developer_mode_enabled():
        return {
            "details_json": details_value,
            "evidence_json": evidence_value,
            "evidence_contexts_json": evidence_contexts_value,
        }
    return {
        "details_json": st.text_area("详情 JSON（高级）", value=details_value, height=180),
        "evidence_json": st.text_area("证据 JSON（高级）", value=evidence_value, height=180),
        "evidence_contexts_json": st.text_area("证据上下文 JSON（高级）", value=evidence_contexts_value, height=120),
    }


def _render_pending_item_form(project_name: str, item: dict, pending_id: str) -> tuple[dict, bool, bool]:
    details_value, evidence_value, evidence_contexts_value, tags_value = _pending_item_json_defaults(item)
    with st.form(key=scoped_widget_key("pending_item_editor_form", project_name, pending_id)):
        values = {}
        values.update(_render_pending_item_basic_fields(item))
        values["typed_data"] = render_typed_knowledge_fields(values["category"], item)
        values.update(_render_pending_item_scope_fields(item))
        values.update(_render_pending_item_version_fields(item))
        values.update(_render_pending_item_score_fields(item))
        values.update(_render_pending_item_source_fields(item, tags_value))
        values.update(_render_pending_item_json_fields(details_value, evidence_value, evidence_contexts_value))
        col_save, col_confirm = st.columns(2)
        save_clicked = col_save.form_submit_button("保存修改到待审核设定", width="stretch")
        confirm_clicked = col_confirm.form_submit_button("保存并确认", width="stretch")
    return values, save_clicked, confirm_clicked


def _parse_pending_item_json_fields(values: dict):
    try:
        parsed_details = json.loads(values["details_json"] or "{}")
        if not isinstance(parsed_details, dict):
            st.error("详情必须是 JSON 对象。")
            return None
        parsed_evidence = json.loads(values["evidence_json"] or "[]")
        if not isinstance(parsed_evidence, list):
            st.error("证据必须是 JSON 列表。")
            return None
        parsed_evidence_contexts = json.loads(values["evidence_contexts_json"] or "[]")
        if not isinstance(parsed_evidence_contexts, list):
            st.error("证据上下文必须是 JSON 列表。")
            return None
        return parsed_details, parsed_evidence, parsed_evidence_contexts
    except json.JSONDecodeError as exc:
        st.error(f"JSON 格式错误：{exc}")
        return None


def _build_pending_item_update(item: dict, values: dict, parsed_json: tuple) -> dict:
    parsed_details, parsed_evidence, parsed_evidence_contexts = parsed_json
    return {
        **item,
        "category": values["category"],
        "name": values["name"].strip(),
        "summary": values["summary"].strip(),
        "details": parsed_details,
        "typed_data": values.get("typed_data", {}),
        "schema_version": 2,
        "evidence": parsed_evidence,
        "evidence_contexts": parsed_evidence_contexts,
        "confidence": values["confidence"],
        "importance": values["importance"],
        "evidence_strength": values["evidence_strength"],
        "canon_status": values["canon_status"],
        "version_scope": values["version_scope"],
        "worldline_id": values["worldline_id"].strip() or DEFAULT_WORLDLINE_ID,
        "worldline_label": values["worldline_label"].strip() or DEFAULT_WORLDLINE_LABEL,
        "scope": values["scope"],
        "authority": values["authority"],
        "source_title": values["source_title"].strip(),
        "source_origin": values["source_origin"].strip(),
        "source_segment_title": values["source_segment_title"].strip(),
        "source_segment_id": values["source_segment_id"].strip(),
        "tags": parse_comma_tags(values["tags"]),
        "edited_in_ui": True,
    }


def _save_pending_item_editor_result(project_name: str, pending_id: str, updated_item: dict, confirm_clicked: bool) -> None:
    if not update_pending_knowledge_item(project_name, pending_id, updated_item):
        st.error("保存失败：待审核设定不存在，可能已被其他操作处理。")
        return
    if confirm_clicked:
        saved_count = confirm_pending_knowledge_items(project_name, [pending_id])
        if saved_count:
            rebuild_retrieval_assets(project_name, build_vectors=True)
        st.success(f"已保存修改并确认 {saved_count} 条知识库条目。")
    else:
        st.success("已保存修改到待审核设定。")
    st.rerun()


def render_pending_knowledge_item_editor(project_name: str, pending_items: list[dict], filtered_indices: list[int]):
    with st.expander("表单编辑：单条待审核设定", expanded=False):
        if not filtered_indices:
            st.caption("当前筛选结果为空，没有可编辑条目。")
            return

        item, pending_id = _select_pending_knowledge_item(project_name, pending_items, filtered_indices)
        if not pending_id:
            st.warning("该条目缺少内部 ID，无法通过表单保存。")
            return
        values, save_clicked, confirm_clicked = _render_pending_item_form(project_name, item, pending_id)
        if not (save_clicked or confirm_clicked):
            return
        if not values["name"].strip():
            st.error("名称不能为空。")
            return
        updated_item = _build_pending_item_update(
            item,
            values,
            (item.get("details", {}), item.get("evidence", []), item.get("evidence_contexts", [])),
        )
        if confirm_clicked:
            typed_errors = validate_typed_knowledge_item(updated_item, values["category"])
            if typed_errors:
                st.error("；".join(typed_errors))
                return
        _save_pending_item_editor_result(project_name, pending_id, updated_item, confirm_clicked)


def _select_confirmed_knowledge_item(
    project_name: str,
    category: str,
    items: list[dict],
    candidate_indices: list[int],
) -> tuple[int, dict]:
    selected_index = st.selectbox(
        "选择要编辑的正式知识",
        options=candidate_indices,
        format_func=lambda index: (
            f"{index + 1}. {label_knowledge_category(items[index].get('category', category))}"
            f" / {items[index].get('name', '未命名')}"
            f" / {items[index].get('source_title', '-') or '-'}"
        ),
        key=scoped_widget_key("confirmed_item_editor_select", project_name, category),
    )
    return selected_index, dict(items[selected_index])


def _render_confirmed_item_basic_fields(item: dict, category: str) -> dict:
    category_keys = list(KNOWLEDGE_CATEGORY_LABELS.keys())
    col_a, col_b = st.columns(2)
    target_category = col_a.selectbox(
        "分类",
        options=category_keys,
        index=category_keys.index(item.get("category")) if item.get("category") in KNOWLEDGE_CATEGORY_LABELS else category_keys.index(category),
        format_func=label_knowledge_category,
    )
    name = col_b.text_input("名称", value=str(item.get("name") or ""))
    summary = st.text_area("摘要", value=str(item.get("summary") or ""), height=110)
    return {"target_category": target_category, "name": name, "summary": summary}


def _render_confirmed_item_form(project_name: str, category: str, selected_index: int, item: dict) -> tuple[dict, bool, bool]:
    details_value, evidence_value, evidence_contexts_value, tags_value = _pending_item_json_defaults(item)
    item_id = str(item.get("id") or item.get("knowledge_id") or selected_index)
    with st.form(key=scoped_widget_key("confirmed_item_editor_form", project_name, category, item_id)):
        values = {}
        values.update(_render_confirmed_item_basic_fields(item, category))
        values["typed_data"] = render_typed_knowledge_fields(values["target_category"], item)
        values.update(_render_pending_item_scope_fields(item))
        values.update(_render_pending_item_version_fields(item))
        values.update(_render_pending_item_score_fields(item))
        values.update(_render_pending_item_source_fields(item, tags_value))
        values.update(_render_pending_item_json_fields(details_value, evidence_value, evidence_contexts_value))
        col_save, col_delete = st.columns(2)
        save_clicked = col_save.form_submit_button("保存正式知识", width="stretch")
        delete_confirmed = col_delete.checkbox(
            "确认删除该条正式知识",
            key=scoped_widget_key("delete_confirmed_knowledge_confirm", project_name, category, item_id),
        )
        delete_clicked = col_delete.form_submit_button("删除该条正式知识", width="stretch", disabled=not delete_confirmed)
    return values, save_clicked, delete_clicked


def _render_return_confirmed_to_pending(project_name: str, category: str, selected_index: int, item: dict) -> bool:
    if not (item.get("auto_review_run_id") or item.get("source_pending_id")):
        return False
    st.caption(
        f"自动审核记录：{item.get('auto_review_run_id', '-') or '-'} / "
        f"原待审核设定：{item.get('source_pending_id', '-') or '-'}"
    )
    item_id = str(item.get("id") or item.get("knowledge_id") or selected_index)
    with st.expander("退回待审核", expanded=False):
        st.caption("只退回这一条正式知识，不影响同一次自动审核的其他条目。退回后可在待审核设定中重新编辑、确认或丢弃。")
        return_reason = st.text_input(
            "退回原因（可选）",
            key=scoped_widget_key("return_confirmed_reason", project_name, category, item_id),
            placeholder="例如：自动审核误判、证据需要复核、资料版本不对",
        )
        return_clicked = st.button(
            "将该条正式知识退回待审核",
            key=scoped_widget_key("return_confirmed_to_pending", project_name, category, item_id),
            width="stretch",
        )
    if not return_clicked:
        return False
    result = return_confirmed_knowledge_item_to_pending(project_name, category, str(item.get("id") or ""), reason=return_reason)
    if result.get("success"):
        st.success(result.get("message", "已退回待审核。"))
        st.rerun()
    st.error(result.get("message", "退回失败。"))
    return True


def _delete_confirmed_knowledge_item(project_name: str, category: str, selected_index: int, item: dict) -> None:
    if save_confirmed_knowledge_item(project_name, category, selected_index, item, delete_only=True):
        st.success("已删除该条正式知识；搜索索引将在后台更新。")
        st.rerun()
    st.error("删除失败：条目不存在或分类无效。")


def _build_confirmed_item_update(item: dict, values: dict, parsed_json: tuple) -> dict:
    parsed_details, parsed_evidence, parsed_evidence_contexts = parsed_json
    return {
        **item,
        "category": values["target_category"],
        "name": values["name"].strip(),
        "summary": values["summary"].strip(),
        "details": parsed_details,
        "typed_data": values.get("typed_data", {}),
        "schema_version": 2,
        "evidence": parsed_evidence,
        "evidence_contexts": parsed_evidence_contexts,
        "confidence": values["confidence"],
        "importance": values["importance"],
        "evidence_strength": values["evidence_strength"],
        "canon_status": values["canon_status"],
        "version_scope": values["version_scope"],
        "worldline_id": values["worldline_id"].strip() or DEFAULT_WORLDLINE_ID,
        "worldline_label": values["worldline_label"].strip() or DEFAULT_WORLDLINE_LABEL,
        "scope": values["scope"],
        "authority": values["authority"],
        "source_title": values["source_title"].strip(),
        "source_origin": values["source_origin"].strip(),
        "source_segment_title": values["source_segment_title"].strip(),
        "source_segment_id": values["source_segment_id"].strip(),
        "tags": parse_comma_tags(values["tags"]),
        "edited_in_ui": True,
        "status": item.get("status") or "confirmed",
    }


def _save_confirmed_item_editor_result(project_name: str, category: str, selected_index: int, updated_item: dict, target_category: str) -> None:
    if save_confirmed_knowledge_item(project_name, category, selected_index, updated_item):
        move_note = "，并移动分类" if target_category != category else ""
        st.success(f"已保存正式知识{move_note}；搜索索引将在后台增量更新。")
        st.rerun()
    st.error("保存失败：条目不存在或分类无效。")


def render_confirmed_knowledge_item_editor(
    project_name: str,
    category: str,
    items: list[dict],
    candidate_indices: list[int],
):
    with st.expander("表单编辑：正式知识库单条知识", expanded=False):
        if not candidate_indices:
            st.caption("当前分类没有可编辑条目。")
            return

        selected_index, item = _select_confirmed_knowledge_item(project_name, category, items, candidate_indices)
        values, save_clicked, delete_clicked = _render_confirmed_item_form(project_name, category, selected_index, item)
        knowledge_id = str(item.get("id") or item.get("knowledge_id") or "")
        if knowledge_id:
            revisions = load_knowledge_revisions(project_name, knowledge_id)
            evidence_rows = load_knowledge_evidence(project_name, knowledge_id)
            with st.expander(f"来源证据与修订历史（证据 {len(evidence_rows)} / 修订 {len(revisions)}）", expanded=False):
                if evidence_rows:
                    st.dataframe([
                        {
                            "状态": row.get("validation_status", ""),
                            "引文": str(row.get("quote") or "")[:160],
                            "来源": row.get("source_id", ""),
                            "片段": row.get("segment_id", ""),
                            "位置": f"{row.get('start_offset', '-')}-{row.get('end_offset', '-')}",
                        }
                        for row in evidence_rows
                    ], width="stretch", hide_index=True)
                if revisions:
                    st.dataframe([
                        {
                            "版本": row.get("revision_no"),
                            "类型": row.get("change_type", ""),
                            "时间": row.get("created_at", ""),
                            "来源修订": row.get("source_revision_id", ""),
                            "原因": row.get("reason", ""),
                        }
                        for row in revisions
                    ], width="stretch", hide_index=True)
        if _render_return_confirmed_to_pending(project_name, category, selected_index, item):
            return
        if not (save_clicked or delete_clicked):
            return
        if delete_clicked:
            _delete_confirmed_knowledge_item(project_name, category, selected_index, item)
            return
        if not values["name"].strip():
            st.error("名称不能为空。")
            return
        updated_item = _build_confirmed_item_update(
            item,
            values,
            (item.get("details", {}), item.get("evidence", []), item.get("evidence_contexts", [])),
        )
        typed_errors = validate_typed_knowledge_item(updated_item, values["target_category"])
        if typed_errors:
            st.error("；".join(typed_errors))
            return
        _save_confirmed_item_editor_result(project_name, category, selected_index, updated_item, values["target_category"])


def _render_pending_triage_metrics(summary: dict) -> None:
    metric_cols = st.columns(5)
    metric_cols[0].metric("待处理", summary["total"])
    metric_cols[1].metric("可自动确认", summary["auto_confirm_count"])
    metric_cols[2].metric("需人工看", summary["manual_count"])
    metric_cols[3].metric("事实/同名冲突", summary["risk_counts"]["fact_conflict"] + summary["risk_counts"]["same_name_conflict"])
    metric_cols[4].metric("低证据/无证据", summary["risk_counts"]["low_evidence"] + summary["risk_counts"]["no_evidence"])
    if summary["auto_confirm_count"]:
        st.success(
            f"建议先自动确认 {summary['auto_confirm_count']} 条低风险内容。"
            "自动审核会留下记录，后续发现误保存可以在自动审核记录里回退。"
        )
    else:
        st.info("当前策略下没有可自动确认的低风险条目。可以调宽自动审核策略，或先处理冲突/低证据条目。")


def _run_pending_triage_auto_confirm(project_name: str, pending_items: list[dict]) -> None:
    candidate_ids = [str(item.get("pending_id") or "") for item in pending_items if item.get("pending_id")]
    auto_summary = auto_confirm_pending_items_without_risk(
        project_name,
        candidate_ids,
        source_type="pending_queue_triage_auto_review",
        source_title="待审核设定 / 全量低风险",
        note="用户在待审核设定中触发全量低风险自动确认",
    )
    st.success(
        f"自动审核完成：确认 {len(auto_summary.get('confirmed_ids', []))} 条，"
        f"保留 {len(auto_summary.get('blocked_ids', []))} 条。"
    )
    st.rerun()


def _apply_pending_triage_filter(risks: list[str], sort_mode: str) -> None:
    st.session_state["pending_filter_risks"] = risks
    st.session_state["pending_sort_mode"] = sort_mode
    st.rerun()


def _clear_pending_triage_filters() -> None:
    for key in [
        "pending_filter_categories",
        "pending_filter_risks",
        "pending_filter_sources",
        "pending_filter_worldlines",
    ]:
        st.session_state[key] = []
    st.session_state["pending_filter_keyword"] = ""
    st.session_state["pending_sort_mode"] = "risk_first"
    st.rerun()


def _render_pending_triage_actions(project_name: str, pending_items: list[dict], summary: dict) -> None:
    action_cols = st.columns(4)
    if action_cols[0].button(
        f"自动确认低风险（{summary['auto_confirm_count']}）",
        key="pending_triage_auto_confirm_all",
        width="stretch",
        disabled=summary["auto_confirm_count"] == 0,
        type="primary" if summary["auto_confirm_count"] else "secondary",
    ):
        _run_pending_triage_auto_confirm(project_name, pending_items)
    if action_cols[1].button("只看冲突/已存在", key="pending_triage_show_conflicts", width="stretch"):
        _apply_pending_triage_filter(["fact_conflict", "same_name_conflict", "confirmed_overlap"], "risk_first")
    if action_cols[2].button("只看低证据", key="pending_triage_show_low_evidence", width="stretch"):
        _apply_pending_triage_filter(["low_evidence", "low_confidence", "no_evidence"], "low_evidence")
    if action_cols[3].button("只看重复/别名", key="pending_triage_show_duplicates", width="stretch"):
        _apply_pending_triage_filter(["duplicate", "alias_candidate"], "risk_first")
    if st.button("清空待审核筛选", key="pending_triage_clear_filters", width="stretch"):
        _clear_pending_triage_filters()


def _pending_clear_plan_preview_rows(clear_plan: dict) -> list[dict]:
    return [
        {
            "动作": {
                "confirm": "自动保存",
                "archive": "归档丢弃",
                "manual_review": "人工复核箱",
            }.get(decision.get("action", ""), decision.get("action", "")),
            "分类": decision.get("category_label", ""),
            "名称": decision.get("name", ""),
            "原因": decision.get("reason", ""),
            "置信度": f"{decision.get('confidence', 0):.2f}",
            "证据": f"{decision.get('evidence_strength', 0):.2f}",
        }
        for decision in clear_plan.get("decisions", [])[:120]
    ]


def _render_pending_clear_plan_preview(clear_plan: dict) -> None:
    preview_rows = _pending_clear_plan_preview_rows(clear_plan)
    with st.expander("查看处理方案样例", expanded=False):
        if preview_rows:
            st.dataframe(preview_rows, width="stretch", hide_index=True)
            if len(clear_plan.get("decisions", [])) > len(preview_rows):
                st.caption(f"仅展示前 {len(preview_rows)} 条，完整决策会写入批次记录。")
        else:
            st.caption("当前没有可处理的待审核设定。")


def _render_pending_clear_plan(project_name: str, pending_items: list[dict], issue_map: dict[str, dict], policy: dict) -> None:
    st.markdown("#### 批量处理方案（可回退）")
    archive_low_quality = st.checkbox(
        "低证据、低置信、无证据条目直接归档丢弃",
        value=True,
        key=scoped_widget_key("pending_clear_archive_low_quality", project_name),
        help="归档不会写入正式知识，但会保存在本次处理记录里；整批回退时会恢复到待审核设定。",
    )
    clear_plan = build_pending_clear_plan(pending_items, issue_map, policy, archive_low_quality=archive_low_quality)
    plan_counts = clear_plan.get("counts", {})
    plan_cols = st.columns(4)
    plan_cols[0].metric("本次覆盖", clear_plan.get("total", 0))
    plan_cols[1].metric("自动保存", plan_counts.get("confirm", 0))
    plan_cols[2].metric("归档丢弃", plan_counts.get("archive", 0))
    plan_cols[3].metric("人工复核箱", plan_counts.get("manual_review", 0))
    st.caption("执行后，本次处理的内容会离开待审核设定；保存、归档和复核结果都会写入一条可回退的处理记录。")
    _render_pending_clear_plan_preview(clear_plan)
    plan_scope = "|".join(
        sorted(str(item.get("pending_id") or "") for item in pending_items if item.get("pending_id"))
    ) or "__empty__"
    if confirmed_button(
        st,
        "执行批量处理方案",
        "确认执行本次批量处理方案",
        scoped_widget_key("pending_clear_execute_plan", project_name, plan_scope, archive_low_quality),
        type="primary",
    ):
        result = execute_pending_clear_plan(project_name, clear_plan, note="用户在待审核设定中执行批量处理方案")
        if result.get("success"):
            st.success(f"{result.get('message')} 批次记录：{result.get('run_id')}")
            st.rerun()
        else:
            st.error(result.get("message", "执行失败。"))


def _render_pending_triage_distribution(summary: dict) -> None:
    with st.expander("分布明细", expanded=False):
        dist_cols = st.columns(3)
        top_categories = sorted(summary["category_counts"].items(), key=lambda item: item[1], reverse=True)[:12]
        top_sources = sorted(summary["source_counts"].items(), key=lambda item: item[1], reverse=True)[:12]
        top_worldlines = sorted(summary["worldline_counts"].items(), key=lambda item: item[1], reverse=True)[:12]
        dist_cols[0].dataframe(
            [{"分类": label_knowledge_category(category), "数量": count} for category, count in top_categories],
            width="stretch",
            hide_index=True,
        )
        dist_cols[1].dataframe(
            [{"来源": source, "数量": count} for source, count in top_sources],
            width="stretch",
            hide_index=True,
        )
        dist_cols[2].dataframe(
            [{"资料版本": worldline, "数量": count} for worldline, count in top_worldlines],
            width="stretch",
            hide_index=True,
        )


def render_pending_triage_dashboard(project_name: str, pending_items: list[dict], issue_map: dict[str, dict], policy: dict):
    auto_preview = build_pending_auto_review_preview(pending_items, issue_map, policy)
    summary = build_pending_triage_summary(pending_items, issue_map, auto_preview)
    with st.expander("批量处理待审核设定", expanded=len(pending_items) >= 50):
        st.caption("数量较多时不必逐条阅读。推荐顺序：自动确认低风险内容 → 处理冲突和重复 → 再检查证据不足的内容。")
        _render_pending_triage_metrics(summary)
        _render_pending_triage_actions(project_name, pending_items, summary)
        _render_pending_clear_plan(project_name, pending_items, issue_map, policy)
        _render_pending_triage_distribution(summary)


def filter_pending_knowledge_indices(pending_items: list[dict], issue_map: dict[str, dict]) -> list[int]:
    categories = sorted({
        str(item.get("category") or "")
        for item in pending_items
        if str(item.get("category") or "").strip()
    })
    source_titles = sorted({
        str(item.get("source_title") or "")
        for item in pending_items
        if str(item.get("source_title") or "").strip()
    })
    worldlines = sorted({
        str(item.get("worldline_label") or item.get("worldline_id") or "")
        for item in pending_items
        if str(item.get("worldline_label") or item.get("worldline_id") or "").strip()
    })
    col_a, col_b, col_c = st.columns(3)
    selected_categories = col_a.multiselect(
        "筛选分类",
        options=categories,
        default=[],
        format_func=label_knowledge_category,
        key="pending_filter_categories",
    )
    risk_filter = col_b.multiselect(
        "筛选质检线索",
        options=["fact_conflict", "same_name_conflict", "confirmed_overlap", "duplicate", "alias_candidate", "low_evidence", "low_confidence", "no_evidence"],
        default=[],
        format_func=lambda value: {
            "fact_conflict": "事实冲突",
            "same_name_conflict": "同名冲突",
            "confirmed_overlap": "正式库已有",
            "duplicate": "同名重复",
            "alias_candidate": "疑似别名",
            "low_evidence": "低证据强度",
            "low_confidence": "低置信度",
            "no_evidence": "无证据摘录",
        }.get(value, value),
        key="pending_filter_risks",
    )
    sort_mode = col_c.selectbox(
        "排序",
        options=["risk_first", "low_evidence", "low_confidence", "high_importance", "newest", "category"],
        format_func=lambda value: {
            "risk_first": "高风险优先",
            "low_evidence": "低证据优先",
            "low_confidence": "低置信优先",
            "high_importance": "高重要性优先",
            "newest": "新加入优先",
            "category": "按分类/名称",
        }.get(value, value),
        key="pending_sort_mode",
    )

    keyword = st.text_input("搜索待审核设定", key="pending_filter_keyword", placeholder="名称、摘要、来源、标签、片段标题")
    selected_source_titles = st.multiselect(
        "筛选来源",
        options=source_titles,
        default=[],
        key="pending_filter_sources",
    )
    selected_worldlines = st.multiselect(
        "筛选资料版本",
        options=worldlines,
        default=[],
        key="pending_filter_worldlines",
    )

    return filter_pending_knowledge_indices_by_values(
        pending_items,
        issue_map,
        selected_categories=selected_categories,
        selected_source_titles=selected_source_titles,
        selected_worldlines=selected_worldlines,
        risk_filter=risk_filter,
        keyword=keyword,
        sort_mode=sort_mode,
    )


def _pending_quality_type_labels() -> dict[str, str]:
    return {
        "duplicate": "同名重复",
        "same_name_conflict": "同名冲突",
        "fact_conflict": "事实冲突",
        "alias_candidate": "疑似别名",
        "confirmed_overlap": "正式库已有",
    }


def _pending_quality_issue_rows(issues: list[dict], type_labels: dict[str, str]) -> list[dict]:
    return [
        {
            "序号": index,
            "级别": issue.get("severity", ""),
            "类型": type_labels.get(issue.get("type", ""), issue.get("type", "")),
            "对象": issue.get("title", ""),
            "说明": issue.get("description", ""),
            "关联待审核": len([item for item in issue.get("pending_ids", []) if item]),
        }
        for index, issue in enumerate(issues, start=1)
    ]


def _select_pending_quality_issue(issues: list[dict], type_labels: dict[str, str]) -> dict:
    selected_issue_index = st.selectbox(
        "查看质检线索",
        options=list(range(len(issues))),
        format_func=lambda index: f"{index + 1}. {type_labels.get(issues[index].get('type', ''), issues[index].get('type', ''))} / {issues[index].get('title', '')}",
        key="pending_quality_issue_select",
    )
    return issues[selected_issue_index]


def _pending_quality_selected_items(pending_items: list[dict], issue: dict) -> list[dict]:
    return [pending_items[index] for index in issue.get("indices", []) if 0 <= index < len(pending_items)]


def _render_pending_quality_selected_items(selected_items: list[dict]) -> None:
    for item in selected_items:
        st.markdown(f"**{label_knowledge_category(item.get('category', ''))} / {item.get('name', '未命名')}**")
        st.caption(
            f"内部 ID={item.get('pending_id', '-')} / 可信度={safe_confidence(item.get('confidence', 0.7)):.2f} / "
            f"证据强度={safe_confidence(item.get('evidence_strength', 0.5)):.2f} / 来源={item.get('source_title', '-') or '-'}"
        )
        if item.get("summary"):
            st.write(str(item.get("summary"))[:500])
        details = item.get("details", {})
        if isinstance(details, dict) and details:
            st.caption("详情：" + "；".join(f"{key}={value}" for key, value in list(details.items())[:8]))


def _render_pending_quality_alias_action(project_name: str, selected_items: list[dict]) -> None:
    alias_names = [str(item.get("name") or "").strip() for item in selected_items if str(item.get("name") or "").strip()]
    default_canonical = alias_names[0] if alias_names else ""
    alias_col_a, alias_col_b = st.columns(2)
    canonical_name = alias_col_a.text_input("别名组主名称", value=default_canonical, key="pending_quality_alias_canonical")
    alias_notes = alias_col_b.text_input("别名备注", value="由待审核设定中的疑似别名线索保存。", key="pending_quality_alias_notes")
    if st.button("保存为实体别名组", key="pending_quality_save_alias_group", width="stretch"):
        try:
            alias_group = upsert_entity_alias_group(
                project_name,
                category=str(selected_items[0].get("category") or "characters"),
                canonical_name=canonical_name,
                aliases=alias_names,
                notes=alias_notes,
                source_pending_ids=[str(item.get("pending_id") or "") for item in selected_items if item.get("pending_id")],
            )
            st.success(f"已保存别名组：{alias_group.get('canonical_name')} / {', '.join(alias_group.get('aliases', []))}")
            st.rerun()
        except Exception as exc:
            st.error(f"保存别名组失败：{exc}")


def _merge_pending_quality_issue(project_name: str, selected_items: list[dict]) -> None:
    category = str(selected_items[0].get("category") or "")
    merged_item = build_merged_knowledge_item(category, selected_items)
    merged_item["status"] = "pending"
    merged_item["tags"] = merge_list_values([merged_item.get("tags", []), ["质检合并"]])
    merged_item["merged_from_pending_ids"] = [str(item.get("pending_id") or "") for item in selected_items if item.get("pending_id")]
    target_ids = [str(item.get("pending_id") or "") for item in selected_items if item.get("pending_id")]
    queued_count = queue_pending_knowledge_items(
        project_name,
        [merged_item],
        scope=merged_item.get("scope", selected_items[0].get("scope", "reference")),
        authority=merged_item.get("authority", selected_items[0].get("authority", "curated")),
        source_title=merged_item.get("source_title", ""),
        source_origin=merged_item.get("source_origin", ""),
        replace_pending_ids=target_ids,
    )
    if queued_count <= 0:
        st.error("合并结果未能写入待审核设定，原内容已保留。")
        return
    st.success(f"已合并 {len(target_ids)} 条，生成 {queued_count} 条新的待审核设定。")
    st.rerun()


def _render_pending_quality_actions(project_name: str, issue: dict, selected_items: list[dict]) -> None:
    can_merge = issue.get("type") in {"duplicate", "same_name_conflict", "fact_conflict"} and len(selected_items) >= 2
    can_save_alias = issue.get("type") == "alias_candidate" and len(selected_items) >= 2
    if can_save_alias:
        _render_pending_quality_alias_action(project_name, selected_items)
    if can_merge and st.button("将这组同名内容合并为新的待审核设定", key="pending_quality_merge_issue", width="stretch"):
        _merge_pending_quality_issue(project_name, selected_items)


def render_pending_knowledge_quality_panel(project_name: str, pending_items: list[dict]):
    issues = build_pending_knowledge_quality_issues(project_name, pending_items)
    with st.expander(f"提取质检：重复 / 冲突 / 别名线索（{len(issues)}）", expanded=bool(issues)):
        st.caption("用于在确认保存前发现同名重复、字段冲突、疑似别名和已存在正式知识。这里只给出线索，正式保存仍由你确认。")
        if not issues:
            st.caption("当前没有发现明显的重复、冲突或别名线索。")
            return
        type_labels = _pending_quality_type_labels()
        st.dataframe(_pending_quality_issue_rows(issues, type_labels), width="stretch", hide_index=True)
        issue = _select_pending_quality_issue(issues, type_labels)
        if issue.get("recommendation"):
            st.info(str(issue.get("recommendation")))
        selected_items = _pending_quality_selected_items(pending_items, issue)
        _render_pending_quality_selected_items(selected_items)
        _render_pending_quality_actions(project_name, issue, selected_items)


def render_character_entity_card_panel(project_name: str):
    st.markdown("#### 角色资料卡")
    cards = build_character_entity_cards(project_name)
    st.caption("由正式知识实时聚合，不单独保存。请在角色中心编辑，变更会回写知识修订。")
    if not cards:
        render_empty_state("还没有角色", "先新增或确认一条角色知识，角色卡会自动出现。")
        return
    st.dataframe([
        {"角色": card.get("name", ""), "关系": len(card.get("relationships", [])),
         "能力/道具": len(card.get("abilities_and_items", [])), "事件": len(card.get("events", [])),
         "来源": len(card.get("sources", []))}
        for card in cards
    ], width="stretch", hide_index=True)


def render_setting_entity_card_panel(project_name: str):
    st.markdown("#### 世界设定卡")
    cards = build_setting_entity_cards(project_name)
    st.caption("由正式知识实时聚合，不单独保存。请在世界观中心编辑对应权威知识。")
    if not cards:
        render_empty_state("还没有世界设定", "先新增或确认规则、地点、组织或力量体系知识。")
        return
    st.dataframe([
        {"类型": SETTING_ENTITY_CATEGORY_GROUPS.get(card.get("setting_type", ""), card.get("setting_type", "")),
         "名称": card.get("name", ""), "冲突": len(card.get("conflicts", [])),
         "来源": len(card.get("sources", [])), "资料版本": card.get("worldline_label", "")}
        for card in cards
    ], width="stretch", hide_index=True)


def render_entity_alias_panel(project_name: str):
    alias_groups = load_entity_aliases(project_name)
    st.markdown("#### 实体别名库")
    st.caption("记录同一角色、地点或物品的不同称呼，帮助系统识别别名并减少重复资料。")
    cols = st.columns(3)
    cols[0].metric("别名组", len(alias_groups))
    cols[1].metric("别名总数", sum(len(item.get("aliases", [])) for item in alias_groups if isinstance(item.get("aliases", []), list)))
    cols[2].metric("角色别名组", sum(1 for item in alias_groups if item.get("category") == "characters"))

    with st.expander("新增 / 编辑别名组", expanded=False):
        edit_options = ["__new__"] + [str(item.get("id") or index) for index, item in enumerate(alias_groups)]
        selected_alias_id = st.selectbox(
            "选择别名组",
            options=edit_options,
            format_func=lambda value: "新增别名组" if value == "__new__" else next(
                (
                    f"{label_knowledge_category(item.get('category', ''))} / {item.get('canonical_name', '')}"
                    for index, item in enumerate(alias_groups)
                    if str(item.get("id") or index) == value
                ),
                value,
            ),
            key=scoped_widget_key("entity_alias_edit_select", project_name),
        )
        selected_group = {}
        if selected_alias_id != "__new__":
            selected_group = next(
                (item for index, item in enumerate(alias_groups) if str(item.get("id") or index) == selected_alias_id),
                {},
            )
        col_a, col_b = st.columns(2)
        category = col_a.selectbox(
            "实体分类",
            options=list(KNOWLEDGE_CATEGORY_LABELS.keys()),
            index=list(KNOWLEDGE_CATEGORY_LABELS.keys()).index(selected_group.get("category")) if selected_group.get("category") in KNOWLEDGE_CATEGORY_LABELS else 0,
            format_func=label_knowledge_category,
            key=scoped_widget_key("entity_alias_category", project_name, selected_alias_id),
        )
        canonical_name = col_b.text_input(
            "主名称",
            value=str(selected_group.get("canonical_name") or ""),
            key=scoped_widget_key("entity_alias_canonical", project_name, selected_alias_id),
        )
        aliases_text = st.text_area(
            "别名（每行一个）",
            value="\n".join(str(item) for item in selected_group.get("aliases", []) if str(item).strip()) if isinstance(selected_group.get("aliases", []), list) else "",
            height=120,
            key=scoped_widget_key("entity_alias_aliases", project_name, selected_alias_id),
        )
        notes = st.text_area(
            "备注",
            value=str(selected_group.get("notes") or ""),
            height=80,
            key=scoped_widget_key("entity_alias_notes", project_name, selected_alias_id),
        )
        col_save, col_delete = st.columns(2)
        if col_save.button(
            "保存别名组",
            key=scoped_widget_key("save_entity_alias_group", project_name, selected_alias_id),
            width="stretch",
        ):
            try:
                alias_group = upsert_entity_alias_group(
                    project_name,
                    category=category,
                    canonical_name=canonical_name,
                    aliases=[line.strip() for line in aliases_text.splitlines() if line.strip()],
                    notes=notes,
                    source_pending_ids=selected_group.get("source_pending_ids", []) if isinstance(selected_group.get("source_pending_ids", []), list) else [],
                )
                st.success(f"已保存别名组：{alias_group.get('canonical_name')}")
                st.rerun()
            except Exception as exc:
                st.error(f"保存失败：{exc}")
        if selected_alias_id != "__new__" and confirmed_button(
            col_delete,
            "删除别名组",
            "确认删除该别名组",
            scoped_widget_key("delete_entity_alias_group", project_name, selected_alias_id),
        ):
            kept = [
                item for index, item in enumerate(alias_groups)
                if str(item.get("id") or index) != selected_alias_id
            ]
            save_entity_aliases(project_name, kept)
            st.success("已删除别名组。")
            st.rerun()

    if alias_groups:
        rows = []
        for item in alias_groups:
            aliases = item.get("aliases", []) if isinstance(item.get("aliases", []), list) else []
            rows.append({
                "分类": label_knowledge_category(item.get("category", "")),
                "主名称": item.get("canonical_name", ""),
                "别名": "、".join(str(value) for value in aliases[:8]),
                "备注": item.get("notes", ""),
            })
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.caption("当前还没有实体别名组。")


def _render_knowledge_organizer_entity_sections(project_name: str) -> None:
    render_character_entity_card_panel(project_name)
    st.divider()
    render_setting_entity_card_panel(project_name)
    st.divider()
    render_entity_alias_panel(project_name)
    st.divider()


def _select_knowledge_organizer_category(project_name: str, knowledge_category_options: list[str]) -> str:
    return st.selectbox(
        "知识分类",
        options=knowledge_category_options,
        format_func=label_knowledge_category,
        key=scoped_widget_key("knowledge_organizer_category", project_name),
    )


def _render_duplicate_group_summary(items: list[dict], duplicate_groups: list[list[int]]) -> None:
    st.caption(f"当前分类共有 {len(items)} 条；检测到 {len(duplicate_groups)} 组同名/近似重复。")
    for group_index, group in enumerate(duplicate_groups[:8], start=1):
        names = " / ".join(items[index].get("name", "未命名") for index in group)
        st.caption(f"重复组 {group_index}：{names}")
    if len(duplicate_groups) > 8:
        st.caption(f"仅显示前 8 组，共 {len(duplicate_groups)} 组。")


def _knowledge_item_matches_keyword(item: dict, keyword_value: str) -> bool:
    if not keyword_value:
        return True
    search_text = " ".join([
        str(item.get("name", "")),
        str(item.get("summary", "")),
        str(item.get("source_title", "")),
        str(item.get("source_origin", "")),
        " ".join(str(tag) for tag in item.get("tags", []) if str(tag).strip()) if isinstance(item.get("tags"), list) else "",
    ]).lower()
    return keyword_value in search_text


def _filter_knowledge_organizer_indices(project_name: str, category: str, items: list[dict]) -> list[int]:
    keyword = st.text_input(
        "搜索正式知识",
        key=scoped_widget_key("knowledge_organizer_keyword", project_name, category),
        placeholder="名称、摘要、来源、标签",
    )
    worldline_options = sorted({
        str(item.get("worldline_label") or item.get("worldline_id") or "")
        for item in items
        if isinstance(item, dict) and str(item.get("worldline_label") or item.get("worldline_id") or "").strip()
    })
    selected_worldlines = st.multiselect(
        "筛选正式知识的资料版本",
        options=worldline_options,
        default=[],
        key=scoped_widget_key("knowledge_organizer_worldlines", project_name, category),
    )
    candidate_indices = []
    keyword_value = keyword.strip().lower()
    for index, item in enumerate(items):
        item_worldline = str(item.get("worldline_label") or item.get("worldline_id") or "")
        if selected_worldlines and item_worldline not in selected_worldlines:
            continue
        if not _knowledge_item_matches_keyword(item, keyword_value):
            continue
        candidate_indices.append(index)
    st.caption(f"当前筛选结果：{len(candidate_indices)} / {len(items)} 条")
    return candidate_indices


def _select_knowledge_organizer_items(
    project_name: str,
    category: str,
    items: list[dict],
    candidate_indices: list[int],
    duplicate_groups: list[list[int]],
) -> tuple[list[int], list[dict]]:
    default_indices = duplicate_groups[0] if duplicate_groups else []
    default_indices = [index for index in default_indices if index in candidate_indices]
    selected_indices = st.multiselect(
        "选择要合并或删除的条目",
        options=candidate_indices,
        default=default_indices,
        format_func=lambda index: f"{index + 1}. {items[index].get('name', '未命名')} / {items[index].get('summary', '')[:50]}",
        key=scoped_widget_key("knowledge_organizer_selected", project_name, category),
    )
    selected_items = [items[index] for index in selected_indices if 0 <= index < len(items)]
    return selected_indices, selected_items


def _render_selected_knowledge_items(selected_indices: list[int], selected_items: list[dict]) -> None:
    for index, item in zip(selected_indices[:10], selected_items[:10]):
        st.markdown(f"#### {index + 1}. {item.get('name', '未命名')}")
        st.caption(
            f"范围={label_scope(item.get('scope', 'reference'))} / 可信度={label_authority(item.get('authority', 'unknown'))} / 来源={item.get('source_title', '-') or '-'}"
        )
        if item.get("summary"):
            st.write(item.get("summary"))


def _render_knowledge_merge_editor(project_name: str, category: str, selected_indices: list[int], selected_items: list[dict]) -> None:
    if len(selected_items) < 2:
        return
    merged_item = build_merged_knowledge_item(category, selected_items)
    selected_item_ids = [
        str(item.get("id") or item.get("knowledge_id") or index)
        for index, item in zip(selected_indices, selected_items)
    ]
    selection_scope = "|".join(sorted(selected_item_ids))
    with st.form(scoped_widget_key("knowledge_organizer_merge_form", project_name, category, selection_scope)):
        merged_name = st.text_input(
            "合并后名称", value=str(merged_item.get("name") or ""),
            key=scoped_widget_key("knowledge_merge_name", project_name, category, selection_scope),
        )
        merged_summary = st.text_area(
            "合并后摘要", value=str(merged_item.get("summary") or ""), height=140,
            key=scoped_widget_key("knowledge_merge_summary", project_name, category, selection_scope),
        )
        merged_tags = st.text_input(
            "标签（逗号分隔）",
            value=", ".join(str(tag) for tag in merged_item.get("tags", []) if str(tag).strip()),
            key=scoped_widget_key("knowledge_merge_tags", project_name, category, selection_scope),
        )
        merge_clicked = st.form_submit_button("保存合并结果并归档原条目", width="stretch")
    if merge_clicked:
        parsed = {
            **merged_item,
            "name": merged_name.strip(),
            "summary": merged_summary.strip(),
            "tags": parse_comma_tags(merged_tags),
            "revision_reason": "在知识中心合并条目",
        }
        if not parsed["name"]:
            st.error("合并后名称不能为空。")
        elif merge_confirmed_knowledge_items(
            project_name,
            category,
            selected_indices,
            parsed,
            selected_item_ids=selected_item_ids,
        ):
            st.success(f"已合并 {len(selected_items)} 条知识库条目；原条目可在归档视图找到。")
            st.rerun()
        else:
            st.error("合并失败：条目不存在或分类无效。")


def _render_knowledge_delete_action(project_name: str, category: str, selected_indices: list[int], selected_items: list[dict]) -> None:
    if not selected_items:
        return
    selected_item_ids = [
        str(item.get("id") or item.get("knowledge_id") or index)
        for index, item in zip(selected_indices, selected_items)
    ]
    selection_scope = "|".join(sorted(selected_item_ids))
    if confirmed_button(
        st,
        "删除所选知识库条目",
        "确认删除所选知识库条目",
        scoped_widget_key("knowledge_organizer_delete", project_name, category, selection_scope),
    ):
        removed_count = delete_confirmed_knowledge_items(
            project_name,
            category,
            selected_indices,
            selected_item_ids=selected_item_ids,
        )
        if removed_count:
            st.success(f"已归档 {removed_count} 条知识库条目；搜索索引将在后台更新。")
            st.rerun()
        st.error("删除失败：条目不存在或分类无效。")


def _render_knowledge_raw_editor(project_name: str, category: str, items: list[dict]) -> None:
    with st.expander("高级编辑：当前分类原始数据", expanded=False):
        serialized_items = json.dumps(items, ensure_ascii=False, indent=2)
        raw_category_json = st.text_area(
            f"{category}.json",
            value=serialized_items,
            height=360,
            key=scoped_widget_key("knowledge_organizer_raw_json", project_name, category, serialized_items),
        )
        if st.button(
            "保存当前分类原始数据",
            key=scoped_widget_key("knowledge_organizer_save_raw", project_name, category),
        ):
            try:
                parsed = json.loads(raw_category_json)
                if not isinstance(parsed, list):
                    st.error("分类数据必须是列表结构。")
                else:
                    saved_count = replace_knowledge_category_items(project_name, category, parsed)
                    rebuild_retrieval_assets(project_name, build_vectors=True)
                    st.success(f"当前分类知识库条目已保存 {saved_count} 条，并重建检索索引。")
                    st.rerun()
            except json.JSONDecodeError as exc:
                st.error(f"详细数据格式错误：{exc}")


def render_knowledge_organizer(project_name: str, knowledge_category_options: list[str]):
    render_section_heading("知识库", "查看、编辑和整理已确认的知识，让后续写作检索更准确。")
    organizer_views = ["知识条目", "资料卡与别名"]
    if developer_mode_enabled():
        organizer_views.append("技术数据")
    view = st.segmented_control(
        "知识管理视图",
        options=organizer_views,
        default="知识条目",
        key=scoped_widget_key("knowledge_organizer_view", project_name),
        label_visibility="collapsed",
    )
    if view == "资料卡与别名":
        _render_knowledge_organizer_entity_sections(project_name)
        return

    category = _select_knowledge_organizer_category(project_name, knowledge_category_options)
    with st.expander("新增知识条目", expanded=False):
        with st.form(scoped_widget_key("knowledge_create_form", project_name, category)):
            new_name = st.text_input(
                "名称", key=scoped_widget_key("knowledge_create_name", project_name, category),
            )
            new_summary = st.text_area(
                "摘要", height=120,
                key=scoped_widget_key("knowledge_create_summary", project_name, category),
            )
            new_worldline = st.text_input(
                "资料版本标识", value=DEFAULT_WORLDLINE_ID,
                key=scoped_widget_key("knowledge_create_worldline", project_name, category),
            )
            create_clicked = st.form_submit_button("新增并保存", width="stretch")
        if create_clicked:
            if not new_name.strip():
                st.error("名称不能为空。")
            else:
                from uuid import uuid4
                from novelforge.services.memory import upsert_knowledge_category_item_record

                saved = upsert_knowledge_category_item_record(project_name, category, {
                    "id": f"{category}_{uuid4().hex}",
                    "category": category,
                    "name": new_name.strip(),
                    "summary": new_summary.strip(),
                    "worldline_id": new_worldline.strip() or DEFAULT_WORLDLINE_ID,
                    "worldline_label": DEFAULT_WORLDLINE_LABEL,
                    "scope": "project",
                    "authority": "project",
                    "status": "confirmed",
                    "revision_reason": "在知识中心新增",
                })
                st.success(f"已新增：{saved.get('name') or new_name.strip()}。")
                st.rerun()
    items = load_knowledge_category(project_name, category)
    if not items:
        render_empty_state("这个分类还没有知识", "可以先导入资料，再将提取结果确认到知识库。")
        return
    if view == "技术数据":
        st.warning("原始数据编辑适合高级维护，修改后会重建检索索引。")
        _render_knowledge_raw_editor(project_name, category, items)
        return

    duplicate_groups = find_duplicate_knowledge_groups(items)
    _render_duplicate_group_summary(items, duplicate_groups)
    candidate_indices = _filter_knowledge_organizer_indices(project_name, category, items)
    render_confirmed_knowledge_item_editor(project_name, category, items, candidate_indices)
    selected_indices, selected_items = _select_knowledge_organizer_items(
        project_name,
        category,
        items,
        candidate_indices,
        duplicate_groups,
    )
    _render_selected_knowledge_items(selected_indices, selected_items)
    _render_knowledge_merge_editor(project_name, category, selected_indices, selected_items)
    _render_knowledge_delete_action(project_name, category, selected_indices, selected_items)


def render_source_package_report_page(project_name: str):
    render_section_heading("资料包", "把已确认的知识整理为一份可阅读、可检索的项目资料总览。")
    with st.container(border=True):
        preview_key = scoped_widget_key("source_package_report_preview", project_name)
        preview_revision_key = scoped_widget_key("source_package_report_preview_revision", project_name)
        st.caption("基于正式知识条目生成项目资料总览，可保存为分析报告并加入资料检索。")
        knowledge_base = load_knowledge_base(project_name)
        total_items = sum(len(items) for items in knowledge_base.values())
        st.caption(f"当前正式知识条目：{total_items} 条")
        max_items = st.slider(
            "每类最多写入条目数",
            min_value=5,
            max_value=100,
            value=30,
            step=5,
            key=scoped_widget_key("source_package_max_items", project_name),
        )
        if st.button("生成资料包报告", key=scoped_widget_key("generate_source_package_report", project_name)):
            report = build_source_package_report(project_name, max_items_per_category=max_items)
            st.session_state[preview_key] = report
            st.session_state[preview_revision_key] = int(st.session_state.get(preview_revision_key, 0)) + 1

        existing_report = load_source_package_report(project_name)
        preview_report = st.session_state.get(preview_key, existing_report)
        report_text = st.text_area(
            "资料包报告",
            value=preview_report,
            height=520,
            key=scoped_widget_key(
                "source_package_report_text",
                project_name,
                st.session_state.get(preview_revision_key, 0),
                preview_report,
            ),
        )
        col_save, col_refresh = st.columns(2)
        if col_save.button("保存资料包报告", key=scoped_widget_key("save_source_package_report", project_name)):
            if not report_text.strip():
                st.error("报告内容不能为空。")
            else:
                save_source_package_report(project_name, report_text)
                rebuild_retrieval_assets(project_name, build_vectors=True)
                st.session_state[preview_key] = report_text
                st.session_state[preview_revision_key] = int(st.session_state.get(preview_revision_key, 0)) + 1
                st.success("资料包报告已保存，并重建检索索引。")
                st.rerun()
        if col_refresh.button(
            "用当前知识重新生成并覆盖预览",
            key=scoped_widget_key("refresh_source_package_report", project_name),
        ):
            st.session_state[preview_key] = build_source_package_report(
                project_name,
                max_items_per_category=max_items,
            )
            st.session_state[preview_revision_key] = int(st.session_state.get(preview_revision_key, 0)) + 1
            st.rerun()


def render_ingestion_health_panel(project_name: str):
    report = build_ingestion_health_report(project_name)
    render_section_heading("资料健康检查", "快速找到未提取、提取失败、证据不足和索引不完整的内容。")
    with st.container(border=True):
        render_stat_strip(
            [
                ("健康分", report["score"], "100 分制"),
                ("正式知识", report["confirmed_count"], "条"),
                ("待审核", report["pending_count"], "条"),
                ("未提取", report["imported_not_extracted"], "个片段"),
                ("失败", report["failed_segments"], "个片段"),
                ("高风险", report["high_risk_issue_count"], "条线索"),
            ]
        )
        storage_health = report.get("storage_health", {})
        with st.expander("查看资料卡与存储质量", expanded=False):
            render_stat_strip(
                [
                    ("角色卡", report["character_entity_count"], "张"),
                    ("设定卡", report["setting_entity_count"], "张"),
                    ("别名组", report["alias_group_count"], "组"),
                    ("类型化", f"{float(storage_health.get('typed_coverage') or 0):.0%}", "覆盖率"),
                    ("证据锚点", f"{float(storage_health.get('anchored_evidence_coverage') or 0):.0%}", "覆盖率"),
                    (
                        "全文索引",
                        f"{int(storage_health.get('fts_chunk_total') or 0)}/{int(storage_health.get('retrieval_chunk_total') or 0)}",
                        "片段",
                    ),
                ]
            )
        if report["total_segments"]:
            st.caption(f"长篇片段提取进度：{report['extracted_segments']} / {report['total_segments']}")
        warning_parts = []
        if report["missing_confirmed"]:
            warning_parts.append("正式库缺失分类：" + "、".join(label_knowledge_category(category) for category in report["missing_confirmed"]))
        if report["weak_confirmed"]:
            warning_parts.append("正式库薄弱分类：" + "、".join(label_knowledge_category(category) for category in report["weak_confirmed"]))
        if report["low_evidence"] or report["low_confidence"] or report["no_evidence"]:
            warning_parts.append(f"待审核质量风险：证据较少 {report['low_evidence']} / 可信度较低 {report['low_confidence']} / 无证据 {report['no_evidence']}")
        for text in warning_parts[:4]:
            st.warning(text)
        col_a, col_b = st.columns(2)
        col_a.dataframe(
            [{"分类": label_knowledge_category(category), "正式知识": report["confirmed_counts"].get(category, 0), "待审核设定": report["pending_counts"].get(category, 0)} for category in KNOWLEDGE_CATEGORY_LABELS],
            width="stretch",
            hide_index=True,
        )
        col_b.caption("资料版本分布")
        col_b.json({
            "待审核设定": report["worldline_counts"],
            "正式库": report["confirmed_worldline_counts"],
        })


def render_source_record_detail(project_name: str, record: dict):
    revisions = record.get("revisions") if isinstance(record.get("revisions"), list) else []
    if revisions:
        with st.expander(f"来源修订历史（{len(revisions)}）", expanded=False):
            st.dataframe([
                {
                    "修订 ID": item.get("revision_id", ""),
                    "上一个修订": item.get("previous_revision_id", ""),
                    "内容指纹": str(item.get("content_hash") or "")[:16],
                    "解析器": item.get("parser_name", ""),
                    "文件": item.get("filename", ""),
                    "字符": item.get("char_count", 0),
                    "时间": item.get("created_at", ""),
                }
                for item in revisions
            ], width="stretch", hide_index=True)
    if record.get("kind") == "long_batch":
        batch = load_long_reference_batch(project_name, record.get("batch_id", ""))
        if not batch:
            st.warning("批次记录读取失败。")
            return
        st.caption(
            f"范围={label_scope(batch.get('scope', 'reference'))} / 可信度={label_authority(batch.get('authority', 'curated'))} / "
            f"类型={label_source_type(batch.get('source_type', 'external_source'))}"
        )
        segments = batch.get("segments", [])
        segment_options = list(range(len(segments)))
        selected_index = st.selectbox(
            "查看片段原文与关联知识",
            options=segment_options,
            format_func=lambda index: (
                f"{segments[index].get('index')}. {segments[index].get('title')} / "
                f"导入={label_batch_segment_status(segments[index].get('import_status', 'pending'))} / "
                f"提取={label_batch_segment_status(segments[index].get('extract_status', 'pending'))}"
            ),
            key=f"source_ledger_segment_{record.get('id')}",
        ) if segment_options else None
        if selected_index is None:
            return
        segment = segments[selected_index]
        st.text_area(
            "片段原文",
            value=segment.get("content", ""),
            height=260,
            key=f"source_ledger_segment_content_{record.get('id')}_{segment.get('segment_id')}",
            disabled=True,
        )
        related = get_segment_related_knowledge_items(project_name, segment)
        cols = st.columns(2)
        cols[0].metric("关联待审核", len(related["pending"]))
        cols[1].metric("关联已确认", len(related["confirmed"]))
        for label, items in [("待审核设定", related["pending"][:12]), ("正式知识", related["confirmed"][:12])]:
            if not items:
                continue
            with st.expander(label, expanded=False):
                for item in items:
                    st.markdown(f"**{label_knowledge_category(item.get('category', ''))} / {item.get('name', '未命名')}**")
                    if item.get("summary"):
                        st.caption(str(item.get("summary"))[:260])
        return

    if record.get("kind") == "retrieval_source":
        payload = read_retrieval_source_payload(project_name, record.get("relative_path", ""))
        metadata = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
        st.caption(
            f"文件={record.get('relative_path', '-')} / 范围={label_scope(record.get('scope', 'reference'))} / "
            f"可信度={label_authority(record.get('authority', 'unknown'))} / 类型={label_source_type(record.get('source_type', 'external_source'))}"
        )
        if record.get("source_origin"):
            st.caption(f"来源：{record.get('source_origin')}")
        if payload.get("summary"):
            st.markdown("##### 摘要")
            st.write(payload.get("summary"))
        content = str(payload.get("content") or payload.get("body") or "")
        if metadata and developer_mode_enabled():
            with st.expander("元数据", expanded=False):
                st.json(metadata)
        if content:
            st.text_area(
                "资料正文",
                value=content,
                height=260,
                key=f"source_ledger_content_{record.get('id')}",
                disabled=True,
            )
        return

    st.caption("这个来源只在待审核设定或正式知识中出现，当前没有对应的原文批次或资料文件。")


def render_source_ledger_page(project_name: str):
    render_section_heading("资料库", "按来源追踪原文、切分片段、提取结果和修订历史。")
    with st.container(border=True):
        records = build_ingestion_source_ledger(project_name)
        if not records:
            st.caption("当前还没有可追踪的资料来源。")
            return

        kind_filter = st.multiselect(
            "来源类型",
            options=["long_batch", "retrieval_source", "knowledge_only"],
            default=["long_batch", "retrieval_source", "knowledge_only"],
            format_func=lambda value: {
                "long_batch": "长篇批次",
                "retrieval_source": "检索资料",
                "knowledge_only": "知识来源",
            }.get(value, value),
            key="source_ledger_kind_filter",
        )
        keyword = st.text_input("按标题或来源搜索", key="source_ledger_keyword")
        filtered_records = []
        for record in records:
            if kind_filter and record.get("kind") not in kind_filter:
                continue
            search_text = " ".join([
                str(record.get("title", "")),
                str(record.get("source_origin", "")),
                str(record.get("relative_path", "")),
                str(record.get("file_name", "")),
            ]).lower()
            if keyword.strip() and keyword.strip().lower() not in search_text:
                continue
            filtered_records.append(record)

        metric_cols = st.columns(4)
        metric_cols[0].metric("来源记录", len(filtered_records))
        metric_cols[1].metric("片段/资料", sum(int(item.get("segment_count") or 0) for item in filtered_records))
        metric_cols[2].metric("待审核设定", sum(int(item.get("pending_count") or 0) for item in filtered_records))
        metric_cols[3].metric("已确认", sum(int(item.get("confirmed_count") or 0) for item in filtered_records))

        table_rows = []
        for record in filtered_records:
            table_rows.append({
                "类型": record.get("kind_label", ""),
                "标题": record.get("title", ""),
                "范围": label_scope(record.get("scope", "")) if record.get("scope") else "-",
                "可信度": label_authority(record.get("authority", "")) if record.get("authority") else "-",
                "资料类型": label_source_type(record.get("source_type", "")),
                "片段": record.get("segment_count", 0),
                "已导入": record.get("imported_count", 0),
                "已提取": record.get("extracted_count", 0),
                "失败": record.get("failed_count", 0),
                "修订": record.get("revision_count", 0),
                "待审核设定": record.get("pending_count", 0),
                "已确认": record.get("confirmed_count", 0),
            })
        st.dataframe(table_rows, width="stretch", hide_index=True)

        selected_record_id = st.selectbox(
            "查看来源详情",
            options=[record.get("id", "") for record in filtered_records],
            format_func=lambda record_id: next(
                (f"{record.get('kind_label')} / {record.get('title')}" for record in filtered_records if record.get("id") == record_id),
                record_id,
            ),
            key="source_ledger_selected_record",
        )
        selected_record = next((record for record in filtered_records if record.get("id") == selected_record_id), {})
        if selected_record:
            render_source_record_detail(project_name, selected_record)
