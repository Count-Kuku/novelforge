"""Long reference batch management panels."""
from __future__ import annotations

import json

import streamlit as st

from extraction_presets import (
    KNOWLEDGE_CONSOLIDATION_MODE_LABELS,
    KNOWLEDGE_EXTRACTION_EXPERT_PRESETS,
    KNOWLEDGE_EXTRACTION_MODE_HELP,
    KNOWLEDGE_EXTRACTION_MODE_LABELS,
    KNOWLEDGE_EXTRACTION_PLAN_PRESETS,
    default_extraction_categories,
)
from memory import (
    delete_long_reference_batch,
    discard_pending_knowledge_items,
    list_long_reference_batches,
    load_extraction_plan_templates,
    load_long_reference_batch,
    save_extraction_plan_templates,
    save_long_reference_batch,
)
from source_workflows import (
    build_extraction_coverage_report,
    consolidate_batch_pending_items,
    delete_extraction_plan_template,
    extract_long_reference_segments_to_queue,
    get_batch_pending_knowledge_items,
    import_long_reference_segments,
    run_long_reference_extraction_plan,
    run_long_reference_quick_process,
    summarize_long_reference_resume_state,
    upsert_extraction_plan_template,
)
from knowledge_workflows import safe_confidence
from ui.common import (
    confirmed_button,
    create_batch_progress_callback,
    scoped_widget_key,
    stable_widget_suffix,
)
from ui.labels import (
    label_authority,
    label_batch_segment_status,
    label_knowledge_category,
    label_scope,
)
from ui.step_views import render_step_json_expander, render_step_validation
from ui.streaming import run_with_stream as _run_with_stream


def render_knowledge_diff_item(item: dict, prefix: str):
    st.markdown(f"**{item.get('category_label') or label_knowledge_category(item.get('category', ''))} / {item.get('name', '未命名')}**")
    st.caption(
        f"原作状态={item.get('canon_status', 'unknown')} / 置信度={safe_confidence(item.get('confidence', 0.7)):.2f} / "
        f"证据强度={safe_confidence(item.get('evidence_strength', 0.5)):.2f} / 来源={item.get('source_title') or item.get('source_segment_title') or '-'}"
    )
    if item.get("summary"):
        st.write(str(item.get("summary"))[:500])
    details = item.get("details", {})
    if isinstance(details, dict) and details:
        st.caption(f"{prefix} details")
        st.json(details)


def render_extraction_diff_detail(project_name: str, diff: dict, key_prefix: str):
    if not isinstance(diff, dict) or not diff:
        return
    with st.expander("查看重提取差异详情", expanded=False):
        cols = st.columns(4)
        cols[0].metric("新增", diff.get("added_count", 0))
        cols[1].metric("匹配", diff.get("matched_count", 0))
        cols[2].metric("可能遗漏", diff.get("missing_count", 0))
        cols[3].metric("变化", diff.get("changed_count", 0))
        old_ids = [str(item) for item in diff.get("existing_pending_ids", []) if str(item).strip()]
        new_ids = [str(item) for item in diff.get("new_pending_ids", []) if str(item).strip()]
        if old_ids or new_ids:
            action_cols = st.columns(2)
            if action_cols[0].button("采用新版：删除旧待确认条目", key=f"{key_prefix}_accept_new", use_container_width=True):
                removed = discard_pending_knowledge_items(project_name, old_ids)
                st.success(f"已删除旧待确认条目 {removed} 条，保留本次重提取结果。")
                st.rerun()
            if action_cols[1].button("保留旧版：删除本次新增条目", key=f"{key_prefix}_keep_old", use_container_width=True):
                removed = discard_pending_knowledge_items(project_name, new_ids)
                st.success(f"已删除本次重提取新增/变化条目 {removed} 条，保留旧待确认结果。")
                st.rerun()

        tabs = st.tabs(["新增", "变化", "可能遗漏"])
        with tabs[0]:
            items = diff.get("added_items", [])
            if not items:
                st.caption("没有新增条目。")
            for index, item in enumerate(items[:10], start=1):
                render_knowledge_diff_item(item, f"{key_prefix}_added_{index}")
        with tabs[1]:
            items = diff.get("changed_items", [])
            if not items:
                st.caption("没有变化条目。")
            for index, pair in enumerate(items[:10], start=1):
                st.markdown(f"**{pair.get('label', '未命名条目')}**")
                if pair.get("changed_fields"):
                    st.caption("变化字段：" + "、".join(str(field) for field in pair.get("changed_fields", [])))
                old_col, new_col = st.columns(2)
                with old_col:
                    st.caption("旧提取")
                    render_knowledge_diff_item(pair.get("old", {}), f"{key_prefix}_old_{index}")
                with new_col:
                    st.caption("新提取")
                    render_knowledge_diff_item(pair.get("new", {}), f"{key_prefix}_new_{index}")
        with tabs[2]:
            items = diff.get("missing_items", [])
            if not items:
                st.caption("没有可能遗漏条目。")
            for index, item in enumerate(items[:10], start=1):
                render_knowledge_diff_item(item, f"{key_prefix}_missing_{index}")


def render_extraction_coverage_report(project_name: str, batch: dict | None = None, key_prefix: str = "coverage"):
    report = build_extraction_coverage_report(project_name, batch)
    with st.expander(f"提取覆盖率报告：{report['title']}", expanded=False):
        cols = st.columns(5)
        cols[0].metric("待确认知识", report["pending_count"])
        cols[1].metric("缺失分类", len(report["missing_categories"]))
        cols[2].metric("低证据", report["low_evidence"])
        cols[3].metric("低置信", report["low_confidence"])
        cols[4].metric("无证据", report["no_evidence"])
        if report["total_segments"]:
            st.caption(
                f"批次片段：已提取 {report['extracted_segments']} / {report['total_segments']}，失败 {report['failed_segments']}，"
                f"已有待确认知识覆盖片段 {report['covered_source_segments']}"
            )

        category_rows = [
            {"分类": label_knowledge_category(category), "待确认条目": count}
            for category, count in report["category_counts"].items()
        ]
        st.dataframe(category_rows, use_container_width=True, hide_index=True)
        if report["missing_categories"]:
            st.warning("缺失分类：" + "、".join(label_knowledge_category(category) for category in report["missing_categories"]))
        if report["weak_categories"]:
            st.caption("薄弱分类：" + "、".join(label_knowledge_category(category) for category in report["weak_categories"]))
        col_a, col_b = st.columns(2)
        col_a.json(report["canon_counts"])
        col_b.json(report["mode_counts"])


def _load_selected_long_reference_batch(project_name: str) -> tuple[str | None, dict | None]:
    batches = list_long_reference_batches(project_name)
    if not batches:
        st.caption("当前还没有长篇资料批次。请先在“长篇文本导入”里上传或粘贴整本资料并创建批次。")
        return None, None

    selected_batch_id = st.selectbox(
        "选择资料批次",
        options=[batch.get("batch_id", "") for batch in batches],
        format_func=lambda batch_id: next(
            (
                f"{batch.get('title', '未命名批次')} / {batch.get('summary', {}).get('segment_count', 0)} 段 / 更新时间 {batch.get('updated_at', '-')}"
                for batch in batches if batch.get("batch_id") == batch_id
            ),
            batch_id,
        ),
        key="long_reference_batch_select",
    )
    batch = load_long_reference_batch(project_name, selected_batch_id)
    if not batch:
        st.warning("批次记录读取失败。")
        return selected_batch_id, None
    return selected_batch_id, batch


def _render_batch_overview(project_name: str, batch: dict, selected_batch_id: str) -> tuple[list[dict], dict]:
    summary = batch.get("summary", {})
    cols = st.columns(5)
    cols[0].metric("总片段", summary.get("segment_count", 0))
    cols[1].metric("已导入", summary.get("imported_count", 0))
    cols[2].metric("待导入", summary.get("import_pending_count", 0))
    cols[3].metric("已提取", summary.get("extract_queued_count", 0))
    cols[4].metric("失败", summary.get("extract_failed_count", 0))
    st.caption(
        f"范围={label_scope(batch.get('scope', 'reference'))} / 可信度={label_authority(batch.get('authority', 'curated'))} / 来源={batch.get('source_origin', '-') or '-'}"
    )
    if batch.get("source_file_name") or batch.get("content_fingerprint"):
        st.caption(
            f"文件={batch.get('source_file_name', '-') or '-'} / 资料指纹={str(batch.get('content_fingerprint', ''))[:12] or '-'} / 字符数={batch.get('content_char_count', 0)}"
        )
    segments = batch.get("segments", [])
    resume_state = summarize_long_reference_resume_state(segments)
    unfinished_indices = resume_state["unfinished_indices"]
    imported_not_extracted_indices = resume_state["imported_not_extracted_indices"]
    failed_indices = resume_state["failed_indices"]
    pending_import_indices = resume_state["pending_import_indices"]
    if unfinished_indices:
        st.warning(
            f"检测到这个批次还没处理完：未导入 {len(pending_import_indices)} 段，"
            f"已导入但未提取 {len(imported_not_extracted_indices)} 段，"
            f"提取失败 {len(failed_indices)} 段。"
        )
        st.info(
            "怎么继续：下面已经默认切到“未完成（推荐续跑）”。保持默认选择，点击“继续处理所选片段”。"
            "系统会跳过已导入片段的重复导入，只继续未完成的提取；失败片段会按当前设置重试。"
        )
    else:
        st.success("这个批次的片段都已经完成提取。下一步可以去“待确认知识”审核，或按需重跑已提取片段。")

    render_extraction_coverage_report(project_name, batch, key_prefix=f"batch_{selected_batch_id}")
    return segments, resume_state


def _filter_batch_segment_indices(segments: list[dict], filter_mode: str, resume_state: dict) -> list[int]:
    unfinished_indices = set(resume_state["unfinished_indices"])
    imported_not_extracted_indices = set(resume_state["imported_not_extracted_indices"])
    failed_indices = set(resume_state["failed_indices"])
    pending_import_indices = set(resume_state["pending_import_indices"])

    filtered_indices = []
    for index, segment in enumerate(segments):
        if filter_mode == "未完成（推荐续跑）" and index not in unfinished_indices:
            continue
        if filter_mode == "已导入未提取" and index not in imported_not_extracted_indices:
            continue
        if filter_mode == "未导入" and index not in pending_import_indices:
            continue
        if filter_mode == "提取失败" and index not in failed_indices:
            continue
        if filter_mode == "已提取" and segment.get("extract_status") not in {"queued", "extracted"}:
            continue
        filtered_indices.append(index)
    return filtered_indices


def _render_batch_segment_selector(
    project_name: str,
    selected_batch_id: str,
    segments: list[dict],
    resume_state: dict,
) -> tuple[list[int], list[int]]:
    unfinished_indices = resume_state["unfinished_indices"]
    filter_key = f"long_reference_batch_filter_{selected_batch_id}"
    if filter_key not in st.session_state:
        st.session_state[filter_key] = "未完成（推荐续跑）" if unfinished_indices else "全部"
    elif not unfinished_indices and st.session_state.get(filter_key) == "未完成（推荐续跑）":
        st.session_state[filter_key] = "全部"

    filter_mode = st.selectbox(
        "查看哪些片段",
        options=["未完成（推荐续跑）", "已导入未提取", "未导入", "提取失败", "已提取", "全部"],
        key=filter_key,
    )
    filtered_indices = _filter_batch_segment_indices(segments, filter_mode, resume_state)

    selected_segments_key = f"long_reference_batch_selected_segments_{selected_batch_id}_{stable_widget_suffix(filter_mode)}"
    selected_indices = st.multiselect(
        "选择要继续处理的片段",
        options=filtered_indices,
        default=filtered_indices[: min(20, len(filtered_indices))],
        format_func=lambda index: (
            f"{segments[index].get('index')}. {segments[index].get('title')}"
            f" / 导入={label_batch_segment_status(segments[index].get('import_status', 'pending'))}"
            f" / 提取={label_batch_segment_status(segments[index].get('extract_status', 'pending'))}"
        ),
        key=selected_segments_key,
    )

    for index in filtered_indices[:12]:
        segment = segments[index]
        st.markdown(f"#### {segment.get('index')}. {segment.get('title')}")
        st.caption(
            f"字符数={segment.get('char_count')} / 导入={label_batch_segment_status(segment.get('import_status', 'pending'))} / 提取={label_batch_segment_status(segment.get('extract_status', 'pending'))} / 待确认知识={segment.get('queued_knowledge_count', 0)}"
        )
        if segment.get("extract_error"):
            st.warning(segment.get("extract_error"))
        extract_diff = segment.get("last_extract_diff", {})
        if isinstance(extract_diff, dict) and extract_diff:
            st.caption(
                f"上次提取对比：新增 {extract_diff.get('added_count', 0)} / 匹配 {extract_diff.get('matched_count', 0)} / "
                f"可能遗漏 {extract_diff.get('missing_count', 0)} / 变化 {extract_diff.get('changed_count', 0)}"
            )
            render_extraction_diff_detail(project_name, extract_diff, key_prefix=f"segment_diff_{selected_batch_id}_{index}")
    if len(filtered_indices) > 12:
        st.caption(f"仅预览前 12 个匹配片段，共 {len(filtered_indices)} 个。")
    return filtered_indices, selected_indices


def _render_quick_continue_options(
    selected_batch_id: str,
    selected_indices: list[int],
    pending_import_indices: list[int],
    knowledge_category_options: list[str],
) -> tuple[list[str], str, bool, bool, str]:
    selected_needs_import = any(index in pending_import_indices for index in selected_indices)
    with st.expander("批次自动处理策略（可选）", expanded=False):
        quick_continue_auto_confirm = st.checkbox(
            "自动审核并保存低风险知识",
            value=True,
            key=f"batch_quick_auto_confirm_{selected_batch_id}",
        )
        quick_continue_import = st.checkbox(
            "同时导入资料索引",
            value=selected_needs_import,
            key=f"batch_quick_import_{selected_batch_id}",
            help="断点续跑时，已导入片段会自动跳过，不会重复写入资料索引。",
        )
        quick_continue_preset_key = st.selectbox(
            "专家提取预设",
            options=list(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.keys()),
            index=list(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.keys()).index("balanced"),
            format_func=lambda value: KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[value]["label"],
            key=f"batch_quick_preset_{selected_batch_id}",
        )
        quick_continue_preset = KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[quick_continue_preset_key]
        quick_continue_categories = st.multiselect(
            "提取分类",
            options=knowledge_category_options,
            default=default_extraction_categories("preset", quick_continue_preset, knowledge_category_options),
            format_func=label_knowledge_category,
            key=f"batch_quick_categories_{selected_batch_id}_{quick_continue_preset_key}",
        )
        quick_continue_mode = st.selectbox(
            "提取模式",
            options=list(KNOWLEDGE_EXTRACTION_MODE_LABELS.keys()),
            index=list(KNOWLEDGE_EXTRACTION_MODE_LABELS.keys()).index(quick_continue_preset["mode"]) if quick_continue_preset["mode"] in KNOWLEDGE_EXTRACTION_MODE_LABELS else 0,
            format_func=lambda value: KNOWLEDGE_EXTRACTION_MODE_LABELS.get(value, value),
            key=f"batch_quick_mode_{selected_batch_id}_{quick_continue_preset_key}",
        )
        st.info(KNOWLEDGE_EXTRACTION_MODE_HELP.get(quick_continue_mode, "当前模式暂无说明。"))
        quick_continue_custom_instructions = st.text_area(
            "补充提取要求（高级，可选）",
            height=90,
            key=f"batch_quick_custom_instructions_{selected_batch_id}_{quick_continue_preset_key}",
            placeholder="例如：只保留稳定设定；角色心理推断必须标为 inferred。",
        )
    return (
        quick_continue_categories,
        quick_continue_mode,
        quick_continue_auto_confirm,
        quick_continue_import,
        quick_continue_custom_instructions,
    )


def _render_batch_quick_result(selected_batch_id: str):
    batch_quick_result = st.session_state.get(f"batch_quick_result_{selected_batch_id}", {})
    if not batch_quick_result:
        return
    with st.expander("上次批次自动处理结果", expanded=bool(batch_quick_result.get("blocked_count"))):
        st.json({
            "导入片段": batch_quick_result.get("imported_count", 0),
            "提取片段": batch_quick_result.get("processed_count", 0),
            "新增候选": batch_quick_result.get("new_pending_count", 0),
            "自动保存": batch_quick_result.get("auto_confirmed_count", 0),
            "自动审核记录": batch_quick_result.get("auto_confirm", {}).get("run_id", ""),
            "保留待确认": batch_quick_result.get("blocked_count", 0),
            "保留原因": batch_quick_result.get("auto_confirm", {}).get("blocked_reasons", {}),
            "失败": batch_quick_result.get("failed_titles", []),
        })


def _render_batch_quick_continue(
    project_name: str,
    batch: dict,
    selected_batch_id: str,
    selected_indices: list[int],
    filtered_indices: list[int],
    resume_state: dict,
    knowledge_category_options: list[str],
):
    unfinished_indices = resume_state["unfinished_indices"]
    pending_import_indices = resume_state["pending_import_indices"]
    st.markdown("#### 推荐操作")
    st.caption("想继续推进这个批次时，优先用自动处理：未导入片段会进入资料索引，片段会被提取成候选知识，低风险条目会自动入库，风险条目保留待确认。")
    quick_continue_limit = st.number_input(
        "本次最多自动处理片段数",
        min_value=1,
        value=min(5, max(1, len(selected_indices))),
        key=f"batch_quick_limit_{selected_batch_id}",
    )
    quick_continue_high_ok = True
    if quick_continue_limit > 50:
        st.warning(f"处理 {quick_continue_limit} 段将产生约 {quick_continue_limit} 次 LLM 调用，预计耗时会较长。")
        quick_continue_high_ok = st.checkbox(
            "我确认要大量处理",
            key=f"batch_quick_high_confirm_{selected_batch_id}",
        )
    selected_count = len(selected_indices)
    planned_quick_count = min(int(quick_continue_limit), selected_count)
    st.info(
        f"本次继续处理将按当前选择顺序处理 {planned_quick_count} 个片段；"
        f"已选择 {selected_count} 个，当前过滤结果共 {len(filtered_indices)} 个片段。"
    )
    (
        quick_continue_categories,
        quick_continue_mode,
        quick_continue_auto_confirm,
        quick_continue_import,
        quick_continue_custom_instructions,
    ) = _render_quick_continue_options(
        selected_batch_id,
        selected_indices,
        pending_import_indices,
        knowledge_category_options,
    )
    if st.button("继续处理所选片段", key=f"batch_quick_process_{selected_batch_id}", use_container_width=True, type="primary" if unfinished_indices else "secondary"):
        if not selected_indices:
            st.error("请先选择片段。")
        elif not quick_continue_categories:
            st.error("请至少选择一个提取分类。")
        elif not quick_continue_high_ok:
            st.error("处理数量超过 50 段，请先勾选确认框。")
        else:
            progress_callback = create_batch_progress_callback("批次自动处理")
            batch, quick_summary = _run_with_stream(
                "正在继续处理批次...",
                run_long_reference_quick_process,
                project_name,
                batch,
                selected_indices[: int(quick_continue_limit)],
                enabled_categories=quick_continue_categories,
                extraction_mode=quick_continue_mode,
                extract_limit=int(quick_continue_limit),
                import_to_index=quick_continue_import,
                consolidate_after_extract=False,
                auto_confirm_safe_items=quick_continue_auto_confirm,
                custom_instructions=quick_continue_custom_instructions,
                progress_callback=progress_callback,
            )
            st.session_state[f"batch_quick_result_{selected_batch_id}"] = quick_summary
            st.success(
                f"已处理：导入 {quick_summary.get('imported_count', 0)} 段，"
                f"提取 {quick_summary.get('processed_count', 0)} 段，"
                f"自动保存 {quick_summary.get('auto_confirmed_count', 0)} 条，"
                f"保留待确认 {quick_summary.get('blocked_count', 0)} 条。"
            )
            st.rerun()
    _render_batch_quick_result(selected_batch_id)


def _run_batch_manual_extraction(
    project_name: str,
    batch: dict,
    selected_batch_id: str,
    target_indices: list[int],
    enabled_categories: list[str],
    extraction_mode: str,
    action_label: str,
    empty_message: str,
    progress_label: str,
    stream_message: str,
):
    if not target_indices:
        st.error(empty_message)
        return
    if not enabled_categories:
        st.error("请至少选择一个提取分类。")
        return

    progress_callback = create_batch_progress_callback(progress_label)
    _, processed, queued_total, failures = _run_with_stream(
        stream_message,
        extract_long_reference_segments_to_queue,
        project_name,
        batch,
        target_indices,
        enabled_categories,
        extraction_mode=extraction_mode,
        progress_callback=progress_callback,
    )
    st.session_state[f"batch_manual_extract_result_{selected_batch_id}"] = {
        "action": action_label,
        "processed": processed,
        "queued_total": queued_total,
        "failures": failures,
    }
    st.rerun()


def _render_manual_extraction_options(
    selected_batch_id: str,
    knowledge_category_options: list[str],
) -> tuple[int, bool, list[str], str]:
    extract_limit = st.number_input("本次最多提取片段数", min_value=1, value=5, key=f"batch_extract_limit_{selected_batch_id}")
    batch_extract_high_ok = True
    if extract_limit > 50:
        st.warning(f"提取 {extract_limit} 段将产生约 {extract_limit} 次 LLM 调用，预计耗时会较长。")
        batch_extract_high_ok = st.checkbox(
            "我确认要大量处理",
            key=f"batch_extract_high_confirm_{selected_batch_id}",
        )
    expert_preset = st.selectbox(
        "专家提取预设",
        options=list(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.keys()),
        format_func=lambda value: KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[value]["label"],
        key=f"batch_extract_expert_{selected_batch_id}",
        help="预设会自动推荐提取分类和提取模式。第一次处理长篇资料建议使用“平衡总管”。",
    )
    preset = KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[expert_preset]
    category_default_strategy = st.radio(
        "提取分类初始策略",
        options=["preset", "all", "none"],
        format_func=lambda value: {"preset": "按专家预设", "all": "全选分类", "none": "不预选分类"}.get(value, value),
        horizontal=True,
        key=f"batch_extract_category_strategy_{selected_batch_id}_{expert_preset}",
        help="只影响当前控件的默认勾选。分类越多，覆盖越广；分类越少，输出越聚焦。",
    )
    enabled_categories = st.multiselect(
        "提取分类",
        options=knowledge_category_options,
        default=default_extraction_categories(category_default_strategy, preset, knowledge_category_options),
        format_func=label_knowledge_category,
        key=f"batch_extract_categories_{selected_batch_id}_{expert_preset}_{category_default_strategy}",
        help="决定允许模型输出哪些类型的知识。没有选中的分类不会被主动提取。",
    )
    extraction_mode = st.selectbox(
        "提取模式",
        options=list(KNOWLEDGE_EXTRACTION_MODE_LABELS.keys()),
        index=list(KNOWLEDGE_EXTRACTION_MODE_LABELS.keys()).index(preset["mode"]) if preset["mode"] in KNOWLEDGE_EXTRACTION_MODE_LABELS else 0,
        format_func=lambda value: KNOWLEDGE_EXTRACTION_MODE_LABELS.get(value, value),
        key=f"batch_extract_mode_{selected_batch_id}_{expert_preset}",
        help="模式决定模型看资料时的优先级。通用更稳，深度更适合正式搭同人资料地基。",
    )
    st.info(KNOWLEDGE_EXTRACTION_MODE_HELP.get(extraction_mode, "当前模式暂无说明。"))
    return int(extract_limit), batch_extract_high_ok, enabled_categories, extraction_mode


def _render_manual_extract_result(selected_batch_id: str):
    manual_extract_result = st.session_state.get(f"batch_manual_extract_result_{selected_batch_id}", {})
    if not manual_extract_result:
        return
    with st.expander("上次手动提取结果", expanded=bool(manual_extract_result.get("failures"))):
        st.json({
            "操作": manual_extract_result.get("action", ""),
            "处理片段": manual_extract_result.get("processed", 0),
            "新增候选": manual_extract_result.get("queued_total", 0),
            "失败": manual_extract_result.get("failures", []),
        })


def _render_batch_manual_processing(
    project_name: str,
    batch: dict,
    selected_batch_id: str,
    segments: list[dict],
    selected_indices: list[int],
    knowledge_category_options: list[str],
):
    st.markdown("#### 高级：手动处理")
    col_import, col_extract, col_retry, col_reextract = st.columns(4)
    if col_import.button("导入所选未导入片段", key=f"batch_import_{selected_batch_id}"):
        target_indices = [index for index in selected_indices if segments[index].get("import_status") != "imported"]
        if not target_indices:
            st.error("没有可导入的未导入片段。")
        else:
            _, imported = import_long_reference_segments(project_name, batch, target_indices)
            st.success(f"已导入 {imported} 个片段，并重建检索索引。")
            st.rerun()

    extract_limit, batch_extract_high_ok, enabled_categories, extraction_mode = _render_manual_extraction_options(
        selected_batch_id,
        knowledge_category_options,
    )
    if col_extract.button("提取所选未提取片段", key=f"batch_extract_{selected_batch_id}"):
        if not batch_extract_high_ok:
            st.error("处理数量超过 50 段，请先勾选确认框。")
        else:
            _run_batch_manual_extraction(
                project_name,
                batch,
                selected_batch_id,
                [
                    index for index in selected_indices
                    if segments[index].get("extract_status", "pending") in {"pending", ""}
                ][:extract_limit],
                enabled_categories,
                extraction_mode,
                "提取所选未提取片段",
                "没有可提取的未提取片段。",
                "批量提取",
                "正在提取所选片段...",
            )

    if col_retry.button("重试失败片段", key=f"batch_retry_{selected_batch_id}"):
        _run_batch_manual_extraction(
            project_name,
            batch,
            selected_batch_id,
            [
                index for index in selected_indices
                if segments[index].get("extract_status") == "failed"
            ][:extract_limit],
            enabled_categories,
            extraction_mode,
            "重试失败片段",
            "没有选中的失败片段。",
            "重试提取",
            "正在重试失败片段...",
        )

    if col_reextract.button("重新提取已提取片段", key=f"batch_reextract_{selected_batch_id}"):
        _run_batch_manual_extraction(
            project_name,
            batch,
            selected_batch_id,
            [
                index for index in selected_indices
                if segments[index].get("extract_status") in {"queued", "extracted"}
            ][:extract_limit],
            enabled_categories,
            extraction_mode,
            "重新提取已提取片段",
            "没有选中的已提取片段。",
            "重新提取",
            "正在重新提取片段...",
        )

    _render_manual_extract_result(selected_batch_id)


def _render_extraction_plan_template_editor(
    project_name: str,
    selected_batch_id: str,
    plan_preset: dict,
    plan_steps: list[str],
    project_plan_templates: list[dict],
):
    with st.expander("保存当前专家步骤为项目模板", expanded=False):
        template_name = st.text_input("模板名称", value=plan_preset.get("label", "自定义提取计划"), key=f"batch_extract_plan_template_name_{selected_batch_id}")
        template_notes = st.text_area("模板备注", value="", height=80, key=f"batch_extract_plan_template_notes_{selected_batch_id}")
        if st.button("保存提取计划模板", key=f"batch_save_extract_plan_template_{selected_batch_id}", use_container_width=True):
            try:
                saved_template = upsert_extraction_plan_template(project_name, template_name, plan_steps, template_notes)
                st.success(f"已保存项目提取计划模板：{saved_template.get('name')}")
                st.rerun()
            except Exception as exc:
                st.error(f"保存模板失败：{exc}")
        if project_plan_templates:
            st.markdown("##### 已保存模板")
            st.dataframe(
                [
                    {
                        "名称": item.get("name", ""),
                        "步骤": " / ".join(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.get(step, {}).get("label", step) for step in item.get("steps", [])),
                        "备注": item.get("notes", ""),
                    }
                    for item in project_plan_templates
                ],
                use_container_width=True,
                hide_index=True,
            )
            delete_template_id = st.selectbox(
                "删除模板",
                options=["__none__"] + [str(item.get("id") or "") for item in project_plan_templates if item.get("id")],
                format_func=lambda value: "不删除" if value == "__none__" else next((item.get("name", value) for item in project_plan_templates if item.get("id") == value), value),
                key=f"batch_delete_extract_plan_template_select_{selected_batch_id}",
            )
            if delete_template_id != "__none__" and confirmed_button(
                st,
                "删除所选提取计划模板",
                "确认删除所选模板",
                scoped_widget_key("batch_delete_extract_plan_template", project_name, selected_batch_id),
            ):
                if delete_extraction_plan_template(project_name, delete_template_id):
                    st.success("已删除提取计划模板。")
                    st.rerun()
                else:
                    st.error("删除失败：模板不存在。")
            templates_json = st.text_area(
                "模板库 JSON",
                value=json.dumps(project_plan_templates, ensure_ascii=False, indent=2),
                height=180,
                key=f"batch_extract_plan_templates_json_{selected_batch_id}",
            )
            if st.button("保存模板库 JSON", key=f"batch_save_extract_plan_templates_json_{selected_batch_id}", use_container_width=True):
                try:
                    parsed = json.loads(templates_json)
                    if not isinstance(parsed, list):
                        st.error("模板库必须是列表结构。")
                    else:
                        save_extraction_plan_templates(project_name, parsed)
                        st.success("已保存提取计划模板库。")
                        st.rerun()
                except json.JSONDecodeError as exc:
                    st.error(f"模板库 JSON 格式错误：{exc}")


def _render_plan_auto_consolidation_options(
    selected_batch_id: str,
    knowledge_category_options: list[str],
) -> tuple[bool, str, int, list[str]]:
    auto_consolidate = st.checkbox(
        "计划完成后自动整理当前批次待确认知识",
        value=False,
        key=f"batch_extract_plan_auto_consolidate_{selected_batch_id}",
    )
    auto_consolidation_mode = "balanced"
    auto_consolidation_limit = 80
    auto_consolidation_categories = [
        category for category in ["characters", "relationships", "timeline_events", "world_rules", "abilities", "items"]
        if category in knowledge_category_options
    ]
    if auto_consolidate:
        auto_col_a, auto_col_b = st.columns(2)
        auto_consolidation_mode = auto_col_a.selectbox(
            "自动整理模式",
            options=list(KNOWLEDGE_CONSOLIDATION_MODE_LABELS.keys()),
            format_func=lambda value: KNOWLEDGE_CONSOLIDATION_MODE_LABELS.get(value, value),
            key=f"batch_extract_plan_auto_consolidation_mode_{selected_batch_id}",
        )
        auto_consolidation_limit = auto_col_b.number_input(
            "自动整理最多条目数",
            min_value=5,
            max_value=200,
            value=80,
            step=5,
            key=f"batch_extract_plan_auto_consolidation_limit_{selected_batch_id}",
        )
        auto_consolidation_categories = st.multiselect(
            "自动整理分类",
            options=knowledge_category_options,
            default=auto_consolidation_categories,
            format_func=label_knowledge_category,
            key=f"batch_extract_plan_auto_consolidation_categories_{selected_batch_id}",
        )
    return auto_consolidate, auto_consolidation_mode, int(auto_consolidation_limit), auto_consolidation_categories


def _run_batch_extraction_plan(
    project_name: str,
    batch: dict,
    selected_batch_id: str,
    selected_indices: list[int],
    plan_steps: list[str],
    plan_limit: int,
    plan_reextract: bool,
    batch_plan_high_ok: bool,
    auto_consolidate: bool,
    auto_consolidation_mode: str,
    auto_consolidation_limit: int,
    auto_consolidation_categories: list[str],
):
    if not st.button("执行多专家提取计划", key=f"batch_run_extract_plan_{selected_batch_id}", use_container_width=True):
        return
    if not selected_indices:
        st.error("请先选择要处理的片段。")
        return
    if not plan_steps:
        st.error("请至少选择一个专家步骤。")
        return
    if not batch_plan_high_ok:
        st.error("处理数量超过 50 次模型调用，请先勾选确认框。")
        return

    progress_callback = create_batch_progress_callback("多专家提取计划")
    updated_batch, plan_summary = _run_with_stream(
        "正在按专家计划提取资料...",
        run_long_reference_extraction_plan,
        project_name,
        batch,
        selected_indices,
        plan_steps,
        max_segments=int(plan_limit),
        reextract_completed=plan_reextract,
        progress_callback=progress_callback,
    )
    auto_result = {}
    if auto_consolidate and plan_summary.get("queued_total", 0):
        auto_result = _run_with_stream(
            "正在自动整理散知识...",
            consolidate_batch_pending_items,
            project_name,
            updated_batch,
            categories=auto_consolidation_categories,
            consolidation_mode=auto_consolidation_mode,
            limit=int(auto_consolidation_limit),
            preview_language="json",
        )
        plan_summary["auto_consolidation"] = {
            "enabled": True,
            "success": auto_result.get("success", False),
            "message": auto_result.get("message", ""),
            "source_count": auto_result.get("source_count", 0),
            "queued_count": auto_result.get("queued_count", 0),
            "mode": auto_consolidation_mode,
            "categories": auto_consolidation_categories,
        }
        if auto_result.get("result"):
            st.session_state[f"batch_consolidation_result_{selected_batch_id}"] = auto_result.get("result")
    elif auto_consolidate:
        plan_summary["auto_consolidation"] = {
            "enabled": True,
            "success": False,
            "message": "本次计划没有新增待确认知识，已跳过自动整理。",
            "source_count": 0,
            "queued_count": 0,
            "mode": auto_consolidation_mode,
            "categories": auto_consolidation_categories,
        }
    if auto_consolidate:
        history = updated_batch.get("extraction_plan_runs", [])
        if isinstance(history, list) and history:
            history[-1] = plan_summary
            updated_batch["extraction_plan_runs"] = history
        updated_batch["last_extraction_plan"] = plan_summary
        save_long_reference_batch(project_name, updated_batch)
    st.session_state[f"batch_extract_plan_result_{selected_batch_id}"] = plan_summary
    if not plan_summary.get("segment_indices"):
        st.warning("没有可执行的目标片段。若要重跑已提取片段，请勾选“允许重跑已提取片段”。")
        return

    st.success(
        f"计划完成：执行 {len(plan_summary.get('processed_steps', []))} 个专家步骤，"
        f"累计处理 {plan_summary.get('processed_segments', 0)} 次片段，加入 {plan_summary.get('queued_total', 0)} 条待确认知识。"
    )
    if plan_summary.get("auto_consolidation", {}).get("enabled"):
        auto_info = plan_summary.get("auto_consolidation", {})
        if auto_info.get("success"):
            st.success(auto_info.get("message", "自动整理已完成。"))
        else:
            st.warning(auto_info.get("message", "自动整理没有生成结果。"))
    for failure in plan_summary.get("failures", [])[:5]:
        st.warning(f"计划步骤失败：{failure}")
    st.rerun()


def _render_batch_extraction_plan_result(selected_batch_id: str, batch: dict):
    plan_result = st.session_state.get(f"batch_extract_plan_result_{selected_batch_id}") or batch.get("last_extraction_plan", {})
    if not isinstance(plan_result, dict) or not plan_result:
        return

    with st.expander("上次多专家提取计划结果", expanded=False):
        step_rows = []
        for step in plan_result.get("processed_steps", []):
            step_rows.append({
                "专家": step.get("label", step.get("step", "")),
                "模式": KNOWLEDGE_EXTRACTION_MODE_LABELS.get(step.get("mode", ""), step.get("mode", "")),
                "分类": "、".join(label_knowledge_category(category) for category in step.get("categories", [])),
                "处理片段": step.get("processed", 0),
                "入队知识": step.get("queued", 0),
                "失败": len(step.get("failures", [])),
            })
        if step_rows:
            st.dataframe(step_rows, use_container_width=True, hide_index=True)
        st.caption(
            f"目标片段数={len(plan_result.get('segment_indices', []))} / "
            f"累计处理={plan_result.get('processed_segments', 0)} / "
            f"入队知识={plan_result.get('queued_total', 0)} / "
            f"失败={plan_result.get('failure_count', 0)}"
        )
        auto_info = plan_result.get("auto_consolidation", {})
        if isinstance(auto_info, dict) and auto_info.get("enabled"):
            st.caption(
                f"自动整理：{KNOWLEDGE_CONSOLIDATION_MODE_LABELS.get(auto_info.get('mode', ''), auto_info.get('mode', ''))} / "
                f"来源条目={auto_info.get('source_count', 0)} / 生成={auto_info.get('queued_count', 0)} / "
                f"结果={'成功' if auto_info.get('success') else '未完成'}"
            )
            if auto_info.get("message"):
                st.info(auto_info.get("message"))


def _render_batch_extraction_plan(
    project_name: str,
    batch: dict,
    selected_batch_id: str,
    selected_indices: list[int],
    knowledge_category_options: list[str],
):
    st.markdown("#### 多专家提取计划")
    plan_col_a, plan_col_b, plan_col_c = st.columns(3)
    plan_key = plan_col_a.selectbox(
        "计划预设",
        options=list(KNOWLEDGE_EXTRACTION_PLAN_PRESETS.keys()),
        format_func=lambda value: KNOWLEDGE_EXTRACTION_PLAN_PRESETS[value]["label"],
        key=f"batch_extract_plan_{selected_batch_id}",
    )
    plan_preset = KNOWLEDGE_EXTRACTION_PLAN_PRESETS[plan_key]
    project_plan_templates = load_extraction_plan_templates(project_name)
    template_options = ["__none__"] + [str(item.get("id") or "") for item in project_plan_templates if item.get("id")]
    selected_template_id = st.selectbox(
        "项目提取计划模板",
        options=template_options,
        format_func=lambda value: "不使用项目模板" if value == "__none__" else next(
            (f"{item.get('name', value)} / {' / '.join(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.get(step, {}).get('label', step) for step in item.get('steps', []))}" for item in project_plan_templates if item.get("id") == value),
            value,
        ),
        key=f"batch_extract_plan_template_{selected_batch_id}",
    )
    selected_template = next((item for item in project_plan_templates if item.get("id") == selected_template_id), {})
    plan_limit = plan_col_b.number_input(
        "计划最多处理片段数",
        min_value=1,
        value=min(3, max(1, len(selected_indices) or 1)),
        key=f"batch_extract_plan_limit_{selected_batch_id}",
    )
    plan_reextract = plan_col_c.checkbox(
        "允许重跑已提取片段",
        value=False,
        key=f"batch_extract_plan_reextract_{selected_batch_id}",
    )
    plan_steps = st.multiselect(
        "专家步骤顺序",
        options=list(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.keys()),
        default=[
            step for step in (selected_template.get("steps") if selected_template else plan_preset["steps"])
            if step in KNOWLEDGE_EXTRACTION_EXPERT_PRESETS
        ],
        format_func=lambda value: KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[value]["label"],
        key=f"batch_extract_plan_steps_{selected_batch_id}_{plan_key}_{selected_template_id}",
    )
    _render_extraction_plan_template_editor(
        project_name,
        selected_batch_id,
        plan_preset,
        plan_steps,
        project_plan_templates,
    )
    if plan_steps:
        st.caption("计划顺序：" + " / ".join(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[step]["label"] for step in plan_steps))

    estimated_plan_calls = int(plan_limit) * max(1, len(plan_steps))
    batch_plan_high_ok = True
    if estimated_plan_calls > 50:
        st.warning(
            f"计划将产生约 {estimated_plan_calls} 次 LLM 调用"
            f"（{int(plan_limit)} 段 × {max(1, len(plan_steps))} 个专家步骤），预计耗时会较长。"
        )
        batch_plan_high_ok = st.checkbox(
            "我确认要大量处理",
            key=f"batch_plan_high_confirm_{selected_batch_id}",
        )

    (
        auto_consolidate,
        auto_consolidation_mode,
        auto_consolidation_limit,
        auto_consolidation_categories,
    ) = _render_plan_auto_consolidation_options(
        selected_batch_id,
        knowledge_category_options,
    )
    _run_batch_extraction_plan(
        project_name,
        batch,
        selected_batch_id,
        selected_indices,
        plan_steps,
        int(plan_limit),
        plan_reextract,
        batch_plan_high_ok,
        auto_consolidate,
        auto_consolidation_mode,
        auto_consolidation_limit,
        auto_consolidation_categories,
    )

    _render_batch_extraction_plan_result(selected_batch_id, batch)


def _render_batch_consolidation(
    project_name: str,
    batch: dict,
    selected_batch_id: str,
    knowledge_category_options: list[str],
):
    st.markdown("#### 批次级整理")
    batch_pending_items = get_batch_pending_knowledge_items(project_name, batch)
    st.caption(f"当前批次关联待确认知识 {len(batch_pending_items)} 条。整理会合并同一实体/关系/事件，并用整理后的条目替换这些散条目。")
    col_mode, col_limit = st.columns(2)
    consolidation_mode = col_mode.selectbox(
        "整理模式",
        options=list(KNOWLEDGE_CONSOLIDATION_MODE_LABELS.keys()),
        format_func=lambda value: KNOWLEDGE_CONSOLIDATION_MODE_LABELS.get(value, value),
        key=f"batch_consolidation_mode_{selected_batch_id}",
    )
    consolidation_limit = col_limit.number_input(
        "本次最多整理条目数",
        min_value=5,
        max_value=200,
        value=60,
        step=5,
        key=f"batch_consolidation_limit_{selected_batch_id}",
    )
    consolidation_categories = st.multiselect(
        "整理分类",
        options=knowledge_category_options,
        default=[category for category in ["characters", "relationships", "timeline_events", "world_rules", "abilities", "items"] if category in knowledge_category_options],
        format_func=label_knowledge_category,
        key=f"batch_consolidation_categories_{selected_batch_id}",
    )
    if st.button("整理当前批次待确认知识", key=f"batch_consolidate_pending_{selected_batch_id}", use_container_width=True):
        try:
            consolidation_summary = _run_with_stream(
                "正在整理当前批次待确认知识...",
                consolidate_batch_pending_items,
                project_name,
                batch,
                categories=consolidation_categories,
                consolidation_mode=consolidation_mode,
                limit=int(consolidation_limit),
                preview_language="json",
            )
            if consolidation_summary.get("result"):
                st.session_state[f"batch_consolidation_result_{selected_batch_id}"] = consolidation_summary.get("result")
            if consolidation_summary.get("success"):
                st.success(consolidation_summary.get("message", "批次整理已完成。"))
                st.rerun()
            else:
                st.error(consolidation_summary.get("message", "批次整理没有生成结果。"))
        except Exception as exc:
            st.error(f"批次整理失败：{exc}")

    consolidation_result = st.session_state.get(f"batch_consolidation_result_{selected_batch_id}", {})
    if consolidation_result:
        with st.expander("上次批次整理结果", expanded=False):
            st.markdown(consolidation_result.get("data", {}).get("report_markdown", ""))
            render_step_validation(consolidation_result)
            render_step_json_expander(
                "批次整理结构化数据",
                consolidation_result.get("data", {}).get("knowledge_extraction", {}),
            )


def _render_batch_advanced_actions(project_name: str, batch: dict, selected_batch_id: str):
    with st.expander("高级操作", expanded=False):
        if confirmed_button(
            st,
            "删除当前批次记录",
            "确认删除当前批次记录",
            scoped_widget_key("batch_delete", project_name, selected_batch_id),
        ):
            delete_long_reference_batch(project_name, selected_batch_id)
            st.success("已删除批次记录。已导入的资料文件和结构化知识不会被删除。")
            st.rerun()
        raw_batch_json = st.text_area(
            "批次原始数据",
            value=json.dumps(batch, ensure_ascii=False, indent=2),
            height=360,
            key=f"batch_raw_json_{selected_batch_id}",
        )
        if st.button("保存批次原始数据", key=f"batch_save_raw_{selected_batch_id}"):
            try:
                parsed = json.loads(raw_batch_json)
                if not isinstance(parsed, dict):
                    st.error("批次数据必须是对象结构。")
                else:
                    save_long_reference_batch(project_name, parsed)
                    st.success("批次数据已保存。")
                    st.rerun()
            except json.JSONDecodeError as exc:
                st.error(f"结构化数据格式错误：{exc}")


def render_long_reference_batch_manager(project_name: str, knowledge_category_options: list[str]):
    with st.expander("长篇资料批次管理", expanded=False):
        selected_batch_id, batch = _load_selected_long_reference_batch(project_name)
        if not selected_batch_id or not batch:
            return

        segments, resume_state = _render_batch_overview(project_name, batch, selected_batch_id)
        filtered_indices, selected_indices = _render_batch_segment_selector(
            project_name,
            selected_batch_id,
            segments,
            resume_state,
        )
        _render_batch_quick_continue(
            project_name,
            batch,
            selected_batch_id,
            selected_indices,
            filtered_indices,
            resume_state,
            knowledge_category_options,
        )
        _render_batch_manual_processing(
            project_name,
            batch,
            selected_batch_id,
            segments,
            selected_indices,
            knowledge_category_options,
        )
        _render_batch_extraction_plan(
            project_name,
            batch,
            selected_batch_id,
            selected_indices,
            knowledge_category_options,
        )
        _render_batch_consolidation(project_name, batch, selected_batch_id, knowledge_category_options)
        _render_batch_advanced_actions(project_name, batch, selected_batch_id)
