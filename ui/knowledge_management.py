"""Knowledge management and ingestion review panels."""
from __future__ import annotations

import json

import streamlit as st

from memory import (
    confirm_pending_knowledge_items,
    discard_pending_knowledge_items,
    load_auto_review_policy,
    load_auto_review_runs,
    load_character_entities,
    load_entity_aliases,
    load_knowledge_base,
    load_knowledge_category,
    load_long_reference_batch,
    load_pending_knowledge_items,
    load_setting_entities,
    load_source_package_report,
    queue_pending_knowledge_items,
    restore_auto_review_snapshots_to_pending,
    return_confirmed_knowledge_item_to_pending,
    rollback_auto_review_run,
    save_auto_review_policy,
    save_character_entities,
    save_entity_aliases,
    save_pending_knowledge_items,
    save_setting_entities,
    save_source_package_report,
)
from retrieval import rebuild_retrieval_assets
from source_workflows import (
    auto_confirm_pending_items_without_risk,
    build_ingestion_health_report,
    build_ingestion_source_ledger,
    build_source_package_report,
    get_segment_related_knowledge_items,
    read_retrieval_source_payload,
)
from knowledge_entities import (
    SETTING_ENTITY_CATEGORY_GROUPS,
    build_character_entity_cards,
    build_merged_knowledge_item,
    build_setting_entity_cards,
)
from knowledge_quality import (
    build_pending_issue_map,
    build_pending_knowledge_quality_issues,
    find_duplicate_knowledge_groups,
    merge_list_values,
    upsert_entity_alias_group,
)
from knowledge_workflows import (
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
from ui.common import confirmed_button, scoped_widget_key
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


def _render_pending_selection(pending_items: list[dict], filtered_indices: list[int], issue_map: dict) -> list[int]:
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
        key="pending_knowledge_selected_indices",
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
    preview_cols[3].metric("保留待确认", len(auto_preview.get("blocked_ids", [])))
    reason_counts = auto_preview.get("blocked_reason_counts", {})
    if reason_counts:
        st.caption("主要保留原因：" + " / ".join(f"{reason}={count}" for reason, count in list(reason_counts.items())[:8]))
    preview_rows = auto_preview.get("rows", [])[:80]
    if preview_rows:
        st.dataframe(preview_rows, use_container_width=True, hide_index=True)
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
        auto_scope = st.radio("预检范围", options=["当前筛选结果", "已选择条目"], horizontal=True, key="pending_auto_review_scope")
        auto_candidate_indices = filtered_indices if auto_scope == "当前筛选结果" else selected_indices
        auto_candidate_items = [pending_items[index] for index in auto_candidate_indices if 0 <= index < len(pending_items)]
        auto_preview = build_pending_auto_review_preview(auto_candidate_items, issue_map, policy)
        _render_pending_auto_review_preview(auto_preview)
        auto_candidate_ids = [str(item.get("pending_id") or "") for item in auto_candidate_items if item.get("pending_id")]
        if st.button("按当前策略自动确认低风险条目", key="pending_run_auto_review", use_container_width=True):
            if not auto_candidate_ids:
                st.error("当前范围内没有可审核条目。")
            else:
                auto_summary = auto_confirm_pending_items_without_risk(
                    project_name,
                    auto_candidate_ids,
                    source_type="pending_queue_manual_auto_review",
                    source_title=f"待确认队列 / {auto_scope}",
                    note="用户在待确认队列手动触发自动审核",
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
    if col_a.button("确认所选并写入知识库条目"):
        if not selected_ids:
            st.error("请先选择条目。")
        else:
            saved_count = confirm_pending_knowledge_items(project_name, selected_ids)
            if saved_count:
                rebuild_retrieval_assets(project_name, build_vectors=True)
            st.success(f"已确认 {saved_count} 条知识库条目。")
            st.rerun()
    if confirmed_button(col_b, "丢弃所选待确认条目", "确认丢弃所选条目", "discard_selected_pending_knowledge"):
        if not selected_ids:
            st.error("请先选择条目。")
        else:
            removed_count = discard_pending_knowledge_items(project_name, selected_ids)
            st.success(f"已丢弃 {removed_count} 条待确认知识。")
            st.rerun()


def _render_pending_raw_json_editor(project_name: str, pending_items: list[dict]) -> None:
    with st.expander("高级：待确认队列原始数据", expanded=False):
        pending_json = st.text_area(
            "pending.json",
            value=json.dumps(pending_items, ensure_ascii=False, indent=2),
            height=360,
            key="pending_knowledge_raw_json",
        )
        if st.button("保存待确认队列修改"):
            try:
                parsed = json.loads(pending_json)
                if not isinstance(parsed, list):
                    st.error("待确认队列必须是列表结构。")
                else:
                    save_pending_knowledge_items(project_name, parsed)
                    st.success("待确认队列已保存。")
                    st.rerun()
            except json.JSONDecodeError as exc:
                st.error(f"详细数据格式错误：{exc}")


def render_pending_knowledge_queue(project_name: str):
    pending_items = load_pending_knowledge_items(project_name)
    pending_count = len(pending_items)
    with st.expander(f"待确认知识库条目（{pending_count}）", expanded=bool(pending_count)):
        st.caption("提取结果先进入这里。确认后才写入知识库条目并重建检索索引；不合适的条目可以丢弃。")
        if not pending_items:
            st.caption("当前没有待确认的知识条目。")
            return

        quality_issues = build_pending_knowledge_quality_issues(project_name, pending_items)
        issue_map = build_pending_issue_map(quality_issues)
        policy = load_auto_review_policy(project_name)
        render_pending_triage_dashboard(project_name, pending_items, issue_map, policy)
        render_pending_knowledge_quality_panel(project_name, pending_items)
        filtered_indices = filter_pending_knowledge_indices(pending_items, issue_map)
        _render_pending_queue_metrics(pending_items, filtered_indices, issue_map)
        selected_indices = _render_pending_selection(pending_items, filtered_indices, issue_map)
        _render_pending_preview_list(pending_items, filtered_indices, issue_map)
        render_pending_knowledge_item_editor(project_name, pending_items, filtered_indices)
        selected_ids = _pending_selected_ids(pending_items, selected_indices)
        _render_pending_auto_review_panel(project_name, pending_items, filtered_indices, selected_indices, issue_map, policy)
        _render_pending_bulk_actions(project_name, selected_ids)
        _render_pending_raw_json_editor(project_name, pending_items)


def render_auto_review_policy_panel(project_name: str):
    policy = load_auto_review_policy(project_name)
    with st.expander("自动审核策略", expanded=False):
        st.caption("控制低风险知识是否自动保存。策略越严格，保留待确认越多；策略越宽松，人工审核负担越低。")
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
        if st.button("保存自动审核策略", key="save_auto_review_policy", use_container_width=True):
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
        }.get(action) or ("自动确认" if decision_value == "confirm" else "保留待确认")
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
        st.dataframe(rows, use_container_width=True, hide_index=True)
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
        st.dataframe(_manual_review_snapshot_rows(manual_snapshots, restored_ids), use_container_width=True, hide_index=True)
        if len(manual_snapshots) > 120:
            st.caption("仅展示前 120 条，完整快照保存在原始数据里。")
        restorable_snapshots = _restorable_manual_review_snapshots(manual_snapshots, restored_ids)
        selected_restore_ids = st.multiselect(
            "选择要恢复到待确认队列的复核条目",
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
            "恢复所选到待确认",
            key=f"restore_manual_review_selected_{selected_run_id}",
            disabled=not selected_restore_ids,
            use_container_width=True,
        ):
            _restore_auto_review_snapshots(project_name, selected_run_id, selected_restore_ids)
        if restore_cols[1].button(
            f"恢复全部未恢复（{len(restorable_snapshots)}）",
            key=f"restore_manual_review_all_{selected_run_id}",
            disabled=not restorable_snapshots,
            use_container_width=True,
        ):
            _restore_auto_review_snapshots(project_name, selected_run_id, [str(item.get("pending_id") or "") for item in restorable_snapshots])


def _render_auto_review_rollback(project_name: str, selected_run_id: str, selected_run: dict) -> None:
    if selected_run.get("status") == "rolled_back":
        result = selected_run.get("rollback_result", {})
        st.warning(f"该记录已回退：删除 {result.get('removed_count', 0)} 条正式知识，恢复 {result.get('restored_count', 0)} 条待确认知识。")
        return
    confirm_text = st.text_input(
        "输入处理记录 ID 以确认回退",
        key=f"rollback_auto_review_confirm_{selected_run_id}",
        placeholder=selected_run_id,
    )
    if st.button("回退这次处理", key=f"rollback_auto_review_{selected_run_id}", use_container_width=True):
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
        with st.expander("高级：处理记录原始数据", expanded=False):
            st.json(selected_run)
        _render_auto_review_rollback(project_name, selected_run_id, selected_run)


def _select_pending_knowledge_item(pending_items: list[dict], filtered_indices: list[int]) -> tuple[dict, str]:
    selected_index = st.selectbox(
        "选择要编辑的条目",
        options=filtered_indices,
        format_func=lambda index: (
            f"{index + 1}. {label_knowledge_category(pending_items[index].get('category', ''))}"
            f" / {pending_items[index].get('name', '未命名')}"
            f" / {pending_items[index].get('source_title', '-') or '-'}"
        ),
        key="pending_item_editor_select",
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
        "版本 / 世界线范围",
        options=list(VERSION_SCOPE_LABELS.keys()),
        index=list(VERSION_SCOPE_LABELS.keys()).index(item.get("version_scope")) if item.get("version_scope") in VERSION_SCOPE_LABELS else 4,
        format_func=lambda value: VERSION_SCOPE_LABELS.get(value, value),
    )
    worldline_id = col_worldline.text_input("世界线 ID", value=str(item.get("worldline_id") or DEFAULT_WORLDLINE_ID))
    worldline_label = st.text_input("世界线名称", value=str(item.get("worldline_label") or DEFAULT_WORLDLINE_LABEL))
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
    return {
        "details_json": st.text_area("详情 JSON（高级）", value=details_value, height=180),
        "evidence_json": st.text_area("证据 JSON（高级）", value=evidence_value, height=180),
        "evidence_contexts_json": st.text_area("证据上下文 JSON（高级）", value=evidence_contexts_value, height=120),
    }


def _render_pending_item_form(item: dict, pending_id: str) -> tuple[dict, bool, bool]:
    details_value, evidence_value, evidence_contexts_value, tags_value = _pending_item_json_defaults(item)
    with st.form(key=f"pending_item_editor_form_{pending_id}"):
        values = {}
        values.update(_render_pending_item_basic_fields(item))
        values.update(_render_pending_item_scope_fields(item))
        values.update(_render_pending_item_version_fields(item))
        values.update(_render_pending_item_score_fields(item))
        values.update(_render_pending_item_source_fields(item, tags_value))
        values.update(_render_pending_item_json_fields(details_value, evidence_value, evidence_contexts_value))
        col_save, col_confirm = st.columns(2)
        save_clicked = col_save.form_submit_button("保存修改到待确认队列", use_container_width=True)
        confirm_clicked = col_confirm.form_submit_button("保存并确认", use_container_width=True)
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
        st.error("保存失败：待确认条目不存在，可能已被其他操作处理。")
        return
    if confirm_clicked:
        saved_count = confirm_pending_knowledge_items(project_name, [pending_id])
        if saved_count:
            rebuild_retrieval_assets(project_name, build_vectors=True)
        st.success(f"已保存修改并确认 {saved_count} 条知识库条目。")
    else:
        st.success("已保存修改到待确认队列。")
    st.rerun()


def render_pending_knowledge_item_editor(project_name: str, pending_items: list[dict], filtered_indices: list[int]):
    with st.expander("表单编辑：单条待确认知识", expanded=False):
        if not filtered_indices:
            st.caption("当前筛选结果为空，没有可编辑条目。")
            return

        item, pending_id = _select_pending_knowledge_item(pending_items, filtered_indices)
        if not pending_id:
            st.warning("该条目缺少内部 ID，无法通过表单保存。")
            return
        values, save_clicked, confirm_clicked = _render_pending_item_form(item, pending_id)
        if not (save_clicked or confirm_clicked):
            return
        if not values["name"].strip():
            st.error("名称不能为空。")
            return
        parsed_json = _parse_pending_item_json_fields(values)
        if parsed_json is None:
            return
        updated_item = _build_pending_item_update(item, values, parsed_json)
        _save_pending_item_editor_result(project_name, pending_id, updated_item, confirm_clicked)


def _select_confirmed_knowledge_item(category: str, items: list[dict], candidate_indices: list[int]) -> tuple[int, dict]:
    selected_index = st.selectbox(
        "选择要编辑的正式知识",
        options=candidate_indices,
        format_func=lambda index: (
            f"{index + 1}. {label_knowledge_category(items[index].get('category', category))}"
            f" / {items[index].get('name', '未命名')}"
            f" / {items[index].get('source_title', '-') or '-'}"
        ),
        key=f"confirmed_item_editor_select_{category}",
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
    with st.form(key=f"confirmed_item_editor_form_{category}_{selected_index}"):
        values = {}
        values.update(_render_confirmed_item_basic_fields(item, category))
        values.update(_render_pending_item_scope_fields(item))
        values.update(_render_pending_item_version_fields(item))
        values.update(_render_pending_item_score_fields(item))
        values.update(_render_pending_item_source_fields(item, tags_value))
        values.update(_render_pending_item_json_fields(details_value, evidence_value, evidence_contexts_value))
        col_save, col_delete = st.columns(2)
        save_clicked = col_save.form_submit_button("保存正式知识并重建索引", use_container_width=True)
        delete_confirmed = col_delete.checkbox(
            "确认删除该条正式知识",
            key=scoped_widget_key("delete_confirmed_knowledge_confirm", project_name, category, selected_index),
        )
        delete_clicked = col_delete.form_submit_button("删除该条正式知识", use_container_width=True, disabled=not delete_confirmed)
    return values, save_clicked, delete_clicked


def _render_return_confirmed_to_pending(project_name: str, category: str, selected_index: int, item: dict) -> bool:
    if not (item.get("auto_review_run_id") or item.get("source_pending_id")):
        return False
    st.caption(
        f"自动审核记录：{item.get('auto_review_run_id', '-') or '-'} / "
        f"原待确认条目：{item.get('source_pending_id', '-') or '-'}"
    )
    with st.expander("退回待确认", expanded=False):
        st.caption("只退回这一条正式知识，不影响同一次自动审核的其他条目。退回后可在待确认队列重新编辑、确认或丢弃。")
        return_reason = st.text_input(
            "退回原因（可选）",
            key=f"return_confirmed_reason_{category}_{selected_index}",
            placeholder="例如：自动审核误判、证据需要复核、世界线不对",
        )
        return_clicked = st.button(
            "将该条正式知识退回待确认",
            key=f"return_confirmed_to_pending_{category}_{selected_index}",
            use_container_width=True,
        )
    if not return_clicked:
        return False
    result = return_confirmed_knowledge_item_to_pending(project_name, category, str(item.get("id") or ""), reason=return_reason)
    if result.get("success"):
        rebuild_retrieval_assets(project_name, build_vectors=True)
        st.success(result.get("message", "已退回待确认。"))
        st.rerun()
    st.error(result.get("message", "退回失败。"))
    return True


def _delete_confirmed_knowledge_item(project_name: str, category: str, selected_index: int, item: dict) -> None:
    if save_confirmed_knowledge_item(project_name, category, selected_index, item, delete_only=True):
        rebuild_retrieval_assets(project_name, build_vectors=True)
        st.success("已删除该条正式知识，并重建检索索引。")
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
        rebuild_retrieval_assets(project_name, build_vectors=True)
        move_note = "，并移动分类" if target_category != category else ""
        st.success(f"已保存正式知识{move_note}，并重建检索索引。")
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

        selected_index, item = _select_confirmed_knowledge_item(category, items, candidate_indices)
        values, save_clicked, delete_clicked = _render_confirmed_item_form(project_name, category, selected_index, item)
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
        parsed_json = _parse_pending_item_json_fields(values)
        if parsed_json is None:
            return
        updated_item = _build_confirmed_item_update(item, values, parsed_json)
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
        source_title="待确认处理台 / 全量低风险",
        note="用户在待确认处理台触发全量低风险自动确认",
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
        use_container_width=True,
        disabled=summary["auto_confirm_count"] == 0,
        type="primary" if summary["auto_confirm_count"] else "secondary",
    ):
        _run_pending_triage_auto_confirm(project_name, pending_items)
    if action_cols[1].button("只看冲突/已存在", key="pending_triage_show_conflicts", use_container_width=True):
        _apply_pending_triage_filter(["fact_conflict", "same_name_conflict", "confirmed_overlap"], "risk_first")
    if action_cols[2].button("只看低证据", key="pending_triage_show_low_evidence", use_container_width=True):
        _apply_pending_triage_filter(["low_evidence", "low_confidence", "no_evidence"], "low_evidence")
    if action_cols[3].button("只看重复/别名", key="pending_triage_show_duplicates", use_container_width=True):
        _apply_pending_triage_filter(["duplicate", "alias_candidate"], "risk_first")
    if st.button("清空待确认筛选", key="pending_triage_clear_filters", use_container_width=True):
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
            st.dataframe(preview_rows, use_container_width=True, hide_index=True)
            if len(clear_plan.get("decisions", [])) > len(preview_rows):
                st.caption(f"仅展示前 {len(preview_rows)} 条，完整决策会写入批次记录。")
        else:
            st.caption("当前没有可执行的待确认条目。")


def _render_pending_clear_plan(project_name: str, pending_items: list[dict], issue_map: dict[str, dict], policy: dict) -> None:
    st.markdown("#### 批量处理方案（可回退）")
    archive_low_quality = st.checkbox(
        "低证据、低置信、无证据条目直接归档丢弃",
        value=True,
        key="pending_clear_archive_low_quality",
        help="归档不会写入正式知识，但会保存在本次处理批次记录里；整批回退时会恢复到待确认队列。",
    )
    clear_plan = build_pending_clear_plan(pending_items, issue_map, policy, archive_low_quality=archive_low_quality)
    plan_counts = clear_plan.get("counts", {})
    plan_cols = st.columns(4)
    plan_cols[0].metric("本次覆盖", clear_plan.get("total", 0))
    plan_cols[1].metric("自动保存", plan_counts.get("confirm", 0))
    plan_cols[2].metric("归档丢弃", plan_counts.get("archive", 0))
    plan_cols[3].metric("人工复核箱", plan_counts.get("manual_review", 0))
    st.caption("执行后，本次覆盖的条目会离开普通待确认队列；保存、归档和复核箱都会写进一条可回退的处理记录。")
    _render_pending_clear_plan_preview(clear_plan)
    if confirmed_button(st, "执行批量处理方案", "确认执行本次批量处理方案", "pending_clear_execute_plan", type="primary"):
        result = execute_pending_clear_plan(project_name, clear_plan, note="用户在待确认处理台执行批量处理方案")
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
            use_container_width=True,
            hide_index=True,
        )
        dist_cols[1].dataframe(
            [{"来源": source, "数量": count} for source, count in top_sources],
            use_container_width=True,
            hide_index=True,
        )
        dist_cols[2].dataframe(
            [{"世界线": worldline, "数量": count} for worldline, count in top_worldlines],
            use_container_width=True,
            hide_index=True,
        )


def render_pending_triage_dashboard(project_name: str, pending_items: list[dict], issue_map: dict[str, dict], policy: dict):
    auto_preview = build_pending_auto_review_preview(pending_items, issue_map, policy)
    summary = build_pending_triage_summary(pending_items, issue_map, auto_preview)
    with st.expander("待确认处理台", expanded=len(pending_items) >= 50):
        st.caption("大批量待确认不要逐条读。推荐顺序：自动确认低风险 / 处理冲突和重复 / 再看低证据条目。")
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

    keyword = st.text_input("搜索待确认知识", key="pending_filter_keyword", placeholder="名称、摘要、来源、标签、片段标题")
    selected_source_titles = st.multiselect(
        "筛选来源",
        options=source_titles,
        default=[],
        key="pending_filter_sources",
    )
    selected_worldlines = st.multiselect(
        "筛选世界线",
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
            "关联待确认": len([item for item in issue.get("pending_ids", []) if item]),
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
    alias_notes = alias_col_b.text_input("别名备注", value="由待确认质检的疑似别名线索保存。", key="pending_quality_alias_notes")
    if st.button("保存为实体别名组", key="pending_quality_save_alias_group", use_container_width=True):
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
    discard_pending_knowledge_items(project_name, target_ids)
    queued_count = queue_pending_knowledge_items(
        project_name,
        [merged_item],
        scope=merged_item.get("scope", selected_items[0].get("scope", "reference")),
        authority=merged_item.get("authority", selected_items[0].get("authority", "curated")),
        source_title=merged_item.get("source_title", ""),
        source_origin=merged_item.get("source_origin", ""),
    )
    st.success(f"已合并 {len(target_ids)} 条，生成 {queued_count} 条新的待确认知识。")
    st.rerun()


def _render_pending_quality_actions(project_name: str, issue: dict, selected_items: list[dict]) -> None:
    can_merge = issue.get("type") in {"duplicate", "same_name_conflict", "fact_conflict"} and len(selected_items) >= 2
    can_save_alias = issue.get("type") == "alias_candidate" and len(selected_items) >= 2
    if can_save_alias:
        _render_pending_quality_alias_action(project_name, selected_items)
    if can_merge and st.button("将这组同名条目合并为新的待确认条目", key="pending_quality_merge_issue", use_container_width=True):
        _merge_pending_quality_issue(project_name, selected_items)


def render_pending_knowledge_quality_panel(project_name: str, pending_items: list[dict]):
    issues = build_pending_knowledge_quality_issues(project_name, pending_items)
    with st.expander(f"提取质检：重复 / 冲突 / 别名线索（{len(issues)}）", expanded=bool(issues)):
        st.caption("用于在确认保存前发现同名重复、字段冲突、疑似别名和已存在正式知识。这里只给出线索，正式保存仍由你确认。")
        if not issues:
            st.caption("当前没有发现明显的重复、冲突或别名线索。")
            return
        type_labels = _pending_quality_type_labels()
        st.dataframe(_pending_quality_issue_rows(issues, type_labels), use_container_width=True, hide_index=True)
        issue = _select_pending_quality_issue(issues, type_labels)
        if issue.get("recommendation"):
            st.info(str(issue.get("recommendation")))
        selected_items = _pending_quality_selected_items(pending_items, issue)
        _render_pending_quality_selected_items(selected_items)
        _render_pending_quality_actions(project_name, issue, selected_items)


def render_character_entity_card_panel(project_name: str):
    existing_cards = load_character_entities(project_name)
    st.markdown("#### 角色实体卡")
    st.caption("从已确认的角色、关系、能力、对白风格、时间线和约束知识中聚合角色资料卡。角色卡保存后会进入检索索引。")
    col_limit, col_action = st.columns([1, 1])
    max_characters = col_limit.number_input(
        "最多生成角色数",
        min_value=5,
        max_value=200,
        value=80,
        step=5,
        key="character_entity_max_count",
    )
    if col_action.button("生成角色实体卡预览", key="generate_character_entities", use_container_width=True):
        cards = build_character_entity_cards(project_name, max_characters=int(max_characters))
        st.session_state["character_entity_preview"] = cards
        st.success(f"已生成 {len(cards)} 张角色实体卡预览。")

    preview_cards = st.session_state.get("character_entity_preview", existing_cards)
    st.caption(f"已保存 {len(existing_cards)} 张；当前预览 {len(preview_cards)} 张。")
    if preview_cards:
        for card in preview_cards[:5]:
            with st.expander(f"{card.get('name', '未命名角色')} · 角色卡预览", expanded=False):
                if card.get("summary"):
                    st.write(card.get("summary"))
                if card.get("relationships"):
                    st.markdown("**关系**")
                    st.write("\n".join(f"- {item}" for item in card.get("relationships", [])[:5]))
                if card.get("dialogue_style"):
                    st.markdown("**对白/风格**")
                    st.write("\n".join(f"- {item}" for item in card.get("dialogue_style", [])[:5]))
                if card.get("constraints"):
                    st.markdown("**约束**")
                    st.write("\n".join(f"- {item}" for item in card.get("constraints", [])[:5]))

    raw_cards_json = st.text_area(
        "角色实体卡 JSON",
        value=json.dumps(preview_cards, ensure_ascii=False, indent=2),
        height=320,
        key="character_entity_cards_json",
    )
    col_save, col_clear = st.columns(2)
    if col_save.button("保存角色实体卡并重建索引", key="save_character_entities", use_container_width=True):
        try:
            parsed = json.loads(raw_cards_json)
            if not isinstance(parsed, list):
                st.error("角色实体卡必须是列表结构。")
            else:
                save_character_entities(project_name, parsed)
                rebuild_retrieval_assets(project_name, build_vectors=True)
                st.session_state["character_entity_preview"] = parsed
                st.success(f"已保存 {len(parsed)} 张角色实体卡。")
                st.rerun()
        except json.JSONDecodeError as exc:
            st.error(f"角色实体卡 JSON 格式错误：{exc}")
    if col_clear.button("清空预览", key="clear_character_entity_preview", use_container_width=True):
        st.session_state.pop("character_entity_preview", None)
        st.rerun()


def render_setting_entity_card_panel(project_name: str):
    existing_cards = load_setting_entities(project_name)
    st.markdown("#### 设定实体卡")
    st.caption("从已确认的世界规则、地点、组织、能力、物品和硬性约束中聚合设定资料卡。保存后会进入检索索引。")
    col_limit, col_action = st.columns([1, 1])
    max_cards = col_limit.number_input(
        "最多生成设定卡数",
        min_value=5,
        max_value=300,
        value=120,
        step=5,
        key="setting_entity_max_count",
    )
    if col_action.button("生成设定实体卡预览", key="generate_setting_entities", use_container_width=True):
        cards = build_setting_entity_cards(project_name, max_cards=int(max_cards))
        st.session_state["setting_entity_preview"] = cards
        st.success(f"已生成 {len(cards)} 张设定实体卡预览。")

    preview_cards = st.session_state.get("setting_entity_preview", existing_cards)
    st.caption(f"已保存 {len(existing_cards)} 张；当前预览 {len(preview_cards)} 张。")
    if preview_cards:
        rows = [
            {
                "类型": SETTING_ENTITY_CATEGORY_GROUPS.get(card.get("setting_type", ""), card.get("setting_type", "")),
                "名称": card.get("name", ""),
                "重要性": safe_confidence(card.get("importance", 0.5)),
                "世界线": card.get("worldline_label", ""),
            }
            for card in preview_cards[:12]
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        for card in preview_cards[:5]:
            with st.expander(f"{SETTING_ENTITY_CATEGORY_GROUPS.get(card.get('setting_type', ''), card.get('setting_type', '设定'))} / {card.get('name', '未命名设定')}", expanded=False):
                if card.get("summary"):
                    st.write(str(card.get("summary"))[:900])
                for label, field in [("规则/资料", "rules"), ("时间线", "timeline"), ("关联实体", "related_entities")]:
                    values = card.get(field, [])
                    if isinstance(values, list) and values:
                        st.markdown(f"**{label}**")
                        st.write("\n".join(f"- {item}" for item in values[:8]))
                if card.get("profile"):
                    st.caption("profile")
                    st.json(card.get("profile"))

    raw_cards_json = st.text_area(
        "设定实体卡 JSON",
        value=json.dumps(preview_cards, ensure_ascii=False, indent=2),
        height=320,
        key="setting_entity_cards_json",
    )
    col_save, col_clear = st.columns(2)
    if col_save.button("保存设定实体卡并重建索引", key="save_setting_entities", use_container_width=True):
        try:
            parsed = json.loads(raw_cards_json)
            if not isinstance(parsed, list):
                st.error("设定实体卡必须是列表结构。")
            else:
                save_setting_entities(project_name, parsed)
                rebuild_retrieval_assets(project_name, build_vectors=True)
                st.session_state["setting_entity_preview"] = parsed
                st.success(f"已保存 {len(parsed)} 张设定实体卡。")
                st.rerun()
        except json.JSONDecodeError as exc:
            st.error(f"设定实体卡 JSON 格式错误：{exc}")
    if col_clear.button("清空设定卡预览", key="clear_setting_entity_preview", use_container_width=True):
        st.session_state.pop("setting_entity_preview", None)
        st.rerun()


def render_entity_alias_panel(project_name: str):
    alias_groups = load_entity_aliases(project_name)
    st.markdown("#### 实体别名库")
    st.caption("沉淀同一实体的不同称呼，后续可辅助提取质检、检索和实体卡整理。")
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
            key="entity_alias_edit_select",
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
            key="entity_alias_category",
        )
        canonical_name = col_b.text_input("主名称", value=str(selected_group.get("canonical_name") or ""), key="entity_alias_canonical")
        aliases_text = st.text_area(
            "别名（每行一个）",
            value="\n".join(str(item) for item in selected_group.get("aliases", []) if str(item).strip()) if isinstance(selected_group.get("aliases", []), list) else "",
            height=120,
            key="entity_alias_aliases",
        )
        notes = st.text_area("备注", value=str(selected_group.get("notes") or ""), height=80, key="entity_alias_notes")
        col_save, col_delete = st.columns(2)
        if col_save.button("保存别名组", key="save_entity_alias_group", use_container_width=True):
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
        if selected_alias_id != "__new__" and col_delete.button("删除别名组", key="delete_entity_alias_group", use_container_width=True):
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
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.caption("当前还没有实体别名组。")


def _render_knowledge_organizer_entity_sections(project_name: str) -> None:
    render_character_entity_card_panel(project_name)
    st.divider()
    render_setting_entity_card_panel(project_name)
    st.divider()
    render_entity_alias_panel(project_name)
    st.divider()


def _select_knowledge_organizer_category(knowledge_category_options: list[str]) -> str:
    return st.selectbox(
        "知识分类",
        options=knowledge_category_options,
        format_func=label_knowledge_category,
        key="knowledge_organizer_category",
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


def _filter_knowledge_organizer_indices(category: str, items: list[dict]) -> list[int]:
    keyword = st.text_input("搜索正式知识", key=f"knowledge_organizer_keyword_{category}", placeholder="名称、摘要、来源、标签")
    worldline_options = sorted({
        str(item.get("worldline_label") or item.get("worldline_id") or "")
        for item in items
        if isinstance(item, dict) and str(item.get("worldline_label") or item.get("worldline_id") or "").strip()
    })
    selected_worldlines = st.multiselect(
        "筛选正式知识世界线",
        options=worldline_options,
        default=[],
        key=f"knowledge_organizer_worldlines_{category}",
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


def _select_knowledge_organizer_items(category: str, items: list[dict], candidate_indices: list[int], duplicate_groups: list[list[int]]) -> tuple[list[int], list[dict]]:
    default_indices = duplicate_groups[0] if duplicate_groups else []
    default_indices = [index for index in default_indices if index in candidate_indices]
    selected_indices = st.multiselect(
        "选择要合并或删除的条目",
        options=candidate_indices,
        default=default_indices,
        format_func=lambda index: f"{index + 1}. {items[index].get('name', '未命名')} / {items[index].get('summary', '')[:50]}",
        key=f"knowledge_organizer_selected_{category}",
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
    raw_merged_json = st.text_area(
        "合并后详细数据，可在保存前修改",
        value=json.dumps(merged_item, ensure_ascii=False, indent=2),
        height=340,
        key=f"knowledge_organizer_merged_json_{category}",
    )
    if st.button("保存合并结果并移除原条目", key=f"knowledge_organizer_save_merge_{category}"):
        try:
            parsed = json.loads(raw_merged_json)
            if not isinstance(parsed, dict):
                st.error("合并结果必须是对象结构。")
            else:
                if merge_confirmed_knowledge_items(project_name, category, selected_indices, parsed):
                    rebuild_retrieval_assets(project_name, build_vectors=True)
                    st.success(f"已合并 {len(selected_items)} 条知识库条目，并重建检索索引。")
                    st.rerun()
                st.error("合并失败：条目不存在或分类无效。")
        except json.JSONDecodeError as exc:
            st.error(f"详细数据格式错误：{exc}")


def _render_knowledge_delete_action(project_name: str, category: str, selected_indices: list[int], selected_items: list[dict]) -> None:
    if not selected_items:
        return
    if confirmed_button(
        st,
        "删除所选知识库条目",
        "确认删除所选知识库条目",
        scoped_widget_key("knowledge_organizer_delete", project_name, category),
    ):
        removed_count = delete_confirmed_knowledge_items(project_name, category, selected_indices)
        if removed_count:
            rebuild_retrieval_assets(project_name, build_vectors=True)
            st.success(f"已删除 {removed_count} 条知识库条目，并重建检索索引。")
            st.rerun()
        st.error("删除失败：条目不存在或分类无效。")


def _render_knowledge_raw_editor(project_name: str, category: str, items: list[dict]) -> None:
    with st.expander("高级编辑：当前分类原始数据", expanded=False):
        raw_category_json = st.text_area(
            f"{category}.json",
            value=json.dumps(items, ensure_ascii=False, indent=2),
            height=360,
            key=f"knowledge_organizer_raw_json_{category}",
        )
        if st.button("保存当前分类原始数据", key=f"knowledge_organizer_save_raw_{category}"):
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
    with st.expander("知识库条目整理", expanded=False):
        st.caption("用于处理长篇资料导入后的重复条目。可以按分类查看、合并同名知识，或删除明显错误的条目。")
        _render_knowledge_organizer_entity_sections(project_name)
        category = _select_knowledge_organizer_category(knowledge_category_options)
        items = load_knowledge_category(project_name, category)
        if not items:
            st.caption("当前分类还没有知识库条目。")
            return

        duplicate_groups = find_duplicate_knowledge_groups(items)
        _render_duplicate_group_summary(items, duplicate_groups)
        candidate_indices = _filter_knowledge_organizer_indices(category, items)
        render_confirmed_knowledge_item_editor(project_name, category, items, candidate_indices)
        selected_indices, selected_items = _select_knowledge_organizer_items(category, items, candidate_indices, duplicate_groups)
        _render_selected_knowledge_items(selected_indices, selected_items)
        _render_knowledge_merge_editor(project_name, category, selected_indices, selected_items)
        _render_knowledge_delete_action(project_name, category, selected_indices, selected_items)
        _render_knowledge_raw_editor(project_name, category, items)


def render_source_package_report_page(project_name: str):
    with st.expander("资料包报告", expanded=False):
        st.caption("基于已确认知识库条目生成项目资料总览，可保存为分析报告并进入检索索引。")
        knowledge_base = load_knowledge_base(project_name)
        total_items = sum(len(items) for items in knowledge_base.values())
        st.caption(f"当前已确认知识库条目：{total_items} 条")
        max_items = st.slider("每类最多写入条目数", min_value=5, max_value=100, value=30, step=5, key="source_package_max_items")
        if st.button("生成资料包报告"):
            report = build_source_package_report(project_name, max_items_per_category=max_items)
            st.session_state["source_package_report_preview"] = report

        existing_report = load_source_package_report(project_name)
        report_text = st.text_area(
            "资料包报告",
            value=st.session_state.get("source_package_report_preview", existing_report),
            height=520,
            key="source_package_report_text",
        )
        col_save, col_refresh = st.columns(2)
        if col_save.button("保存资料包报告"):
            if not report_text.strip():
                st.error("报告内容不能为空。")
            else:
                save_source_package_report(project_name, report_text)
                rebuild_retrieval_assets(project_name, build_vectors=True)
                st.success("资料包报告已保存，并重建检索索引。")
                st.rerun()
        if col_refresh.button("用当前知识重新生成并覆盖预览"):
            st.session_state["source_package_report_preview"] = build_source_package_report(
                project_name,
                max_items_per_category=max_items,
            )
            st.rerun()


def render_ingestion_health_panel(project_name: str):
    report = build_ingestion_health_report(project_name)
    with st.expander("资料健康度总览", expanded=True):
        cols = st.columns(6)
        cols[0].metric("健康分", report["score"])
        cols[1].metric("已确认知识", report["confirmed_count"])
        cols[2].metric("待确认", report["pending_count"])
        cols[3].metric("导入未提取", report["imported_not_extracted"])
        cols[4].metric("提取失败", report["failed_segments"])
        cols[5].metric("高风险线索", report["high_risk_issue_count"])
        entity_cols = st.columns(4)
        entity_cols[0].metric("角色实体卡", report["character_entity_count"])
        entity_cols[1].metric("设定实体卡", report["setting_entity_count"])
        entity_cols[2].metric("别名组", report["alias_group_count"])
        entity_cols[3].metric("计划模板", report["extraction_plan_template_count"])
        if report["total_segments"]:
            st.caption(f"长篇片段提取进度：{report['extracted_segments']} / {report['total_segments']}")
        warning_parts = []
        if report["missing_confirmed"]:
            warning_parts.append("正式库缺失分类：" + "、".join(label_knowledge_category(category) for category in report["missing_confirmed"]))
        if report["weak_confirmed"]:
            warning_parts.append("正式库薄弱分类：" + "、".join(label_knowledge_category(category) for category in report["weak_confirmed"]))
        if report["low_evidence"] or report["low_confidence"] or report["no_evidence"]:
            warning_parts.append(f"待确认质量风险：低证据 {report['low_evidence']} / 低置信 {report['low_confidence']} / 无证据 {report['no_evidence']}")
        for text in warning_parts[:4]:
            st.warning(text)
        col_a, col_b = st.columns(2)
        col_a.dataframe(
            [{"分类": label_knowledge_category(category), "正式库": report["confirmed_counts"].get(category, 0), "待确认": report["pending_counts"].get(category, 0)} for category in KNOWLEDGE_CATEGORY_LABELS],
            use_container_width=True,
            hide_index=True,
        )
        col_b.caption("世界线分布")
        col_b.json({
            "待确认": report["worldline_counts"],
            "正式库": report["confirmed_worldline_counts"],
        })


def render_source_record_detail(project_name: str, record: dict):
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
        cols[0].metric("关联待确认", len(related["pending"]))
        cols[1].metric("关联已确认", len(related["confirmed"]))
        for label, items in [("待确认知识", related["pending"][:12]), ("已确认知识", related["confirmed"][:12])]:
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
        if metadata:
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

    st.caption("这个来源只在待确认或已确认知识中出现，当前没有对应的原文批次或检索资料文件。")


def render_source_ledger_page(project_name: str):
    with st.expander("资料来源台账", expanded=True):
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
        metric_cols[2].metric("待确认", sum(int(item.get("pending_count") or 0) for item in filtered_records))
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
                "待确认": record.get("pending_count", 0),
                "已确认": record.get("confirmed_count", 0),
            })
        st.dataframe(table_rows, use_container_width=True, hide_index=True)

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
