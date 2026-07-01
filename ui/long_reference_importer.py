"""Long reference ingestion panels."""
from __future__ import annotations

import hashlib

import streamlit as st

from extraction_presets import (
    KNOWLEDGE_EXTRACTION_EXPERT_PRESETS,
    KNOWLEDGE_EXTRACTION_MODE_HELP,
    KNOWLEDGE_EXTRACTION_MODE_LABELS,
    default_extraction_categories,
)
from memory import create_long_reference_batch, load_long_reference_batch
from source_workflows import (
    calculate_text_fingerprint,
    consolidate_batch_pending_items,
    decode_uploaded_text,
    extract_long_reference_segments_to_queue,
    find_matching_long_reference_batches,
    import_long_reference_segments,
    normalize_text_for_fingerprint,
    run_long_reference_quick_process,
    split_long_reference_text,
)
from ui.common import create_batch_progress_callback
from ui.labels import label_authority, label_knowledge_category, label_scope, label_source_type
from ui.streaming import run_with_stream as _run_with_stream


LONG_REFERENCE_PRESET_INFO = {
    "fanfic_foundation": {
        "label": "同人创作地基（推荐）",
        "button": "使用同人创作地基",
        "summary": "第一次导入整本原作时优先选。它会尽量整理后续写作反复要用的角色、关系、时间线、世界观、能力道具和硬约束。",
        "effect": "适合：搭完整资料库 / 范围=原作资料 / 可信度=官方资料 / 提取=平衡总管+深度提取 / 会自动整理散知识",
    },
    "canon_foundation": {
        "label": "严格原作校验",
        "button": "使用严格原作校验",
        "summary": "只想补一层“不能错、不能改”的原作硬事实时选。它更保守，尽量少推测，适合防止后续写作违背原作。",
        "effect": "适合：补硬事实和防错 / 范围=原作资料 / 可信度=官方资料 / 提取=原作审计+严格原作 / 不自动整理散知识",
    },
    "style_reference": {
        "label": "文风参考",
        "button": "使用文风参考",
        "summary": "导入样本文本或只想学原作表达方式时选。它关注叙事节奏、对白、氛围和描写习惯，不适合拿来补全世界观资料。",
        "effect": "适合：学文风 / 范围=参考资料 / 可信度=人工整理 / 提取=文风专家+文风专用 / 不自动整理散知识",
    },
}


def apply_long_reference_fanfic_preset(preset: str):
    if preset not in LONG_REFERENCE_PRESET_INFO:
        return
    if preset == "canon_foundation":
        st.session_state["long_reference_scope"] = "canon"
        st.session_state["long_reference_authority"] = "official"
        st.session_state["long_reference_source_type"] = "external_source"
        st.session_state["long_reference_quick_import_index"] = True
        st.session_state["long_reference_quick_auto_confirm"] = True
        st.session_state["long_reference_quick_consolidate"] = False
        st.session_state["long_reference_shared_expert_preset"] = "canon_auditor"
        st.session_state["long_reference_shared_category_strategy_canon_auditor"] = "preset"
        st.session_state["long_reference_shared_mode_canon_auditor"] = "strict_canon"
    elif preset == "fanfic_foundation":
        st.session_state["long_reference_scope"] = "canon"
        st.session_state["long_reference_authority"] = "official"
        st.session_state["long_reference_source_type"] = "external_source"
        st.session_state["long_reference_quick_import_index"] = True
        st.session_state["long_reference_quick_auto_confirm"] = True
        st.session_state["long_reference_quick_consolidate"] = True
        st.session_state["long_reference_shared_expert_preset"] = "balanced"
        st.session_state["long_reference_shared_category_strategy_balanced"] = "preset"
        st.session_state["long_reference_shared_mode_balanced"] = "deep"
    elif preset == "style_reference":
        st.session_state["long_reference_scope"] = "reference"
        st.session_state["long_reference_authority"] = "curated"
        st.session_state["long_reference_source_type"] = "external_source"
        st.session_state["long_reference_quick_import_index"] = True
        st.session_state["long_reference_quick_auto_confirm"] = True
        st.session_state["long_reference_quick_consolidate"] = False
        st.session_state["long_reference_shared_expert_preset"] = "style_expert"
        st.session_state["long_reference_shared_category_strategy_style_expert"] = "preset"
        st.session_state["long_reference_shared_mode_style_expert"] = "style"
    st.session_state["long_reference_active_preset"] = preset
    st.session_state["long_reference_preset_notice"] = f"已应用：{LONG_REFERENCE_PRESET_INFO[preset]['label']}"


def _render_long_reference_preset_selector():
    with st.expander("1. 选择处理方案", expanded=True):
        st.caption("先选资料用途。第一次整理整本原作，通常直接选“同人创作地基”。系统会自动设置资料范围、可信度、自动处理方式和提取模式，之后仍可手动调整。")
        active_preset = st.session_state.get("long_reference_active_preset", "")
        if active_preset in LONG_REFERENCE_PRESET_INFO:
            active_info = LONG_REFERENCE_PRESET_INFO[active_preset]
            st.success(st.session_state.get("long_reference_preset_notice", f"当前方案：{active_info['label']}"))
            st.caption(active_info["effect"])
        else:
            st.info("当前还没有套用处理方案。第一次整理整本原作，建议选“同人创作地基（推荐）”。")
        preset_cols = st.columns(3)
        for column, preset_key in zip(preset_cols, LONG_REFERENCE_PRESET_INFO):
            preset_info = LONG_REFERENCE_PRESET_INFO[preset_key]
            with column:
                is_active = active_preset == preset_key
                st.markdown(f"**{preset_info['label']}{'（当前）' if is_active else ''}**")
                st.caption(preset_info["summary"])
                st.caption(preset_info["effect"])
                if st.button(
                    "已应用" if is_active else preset_info["button"],
                    key=f"long_reference_preset_{preset_key}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    apply_long_reference_fanfic_preset(preset_key)
                    st.rerun()


def _render_long_reference_flow_notes():
    with st.expander("流程说明", expanded=False):
        st.markdown(
            """
1. **预览切分**：只把文本临时拆成章节/片段，方便检查切分是否合理，还不会写入资料库。
2. **保存为处理批次**：把这次切分结果保存下来。之后可以在“长篇批次”里继续导入、提取、重试或重新提取。
3. **导入资料索引**：把片段作为原文资料加入检索库。后续写作、规划、审阅可以匹配原文证据，但不会生成结构化角色/设定卡。
4. **提取知识库条目**：让模型从片段中提取角色、关系、时间线、设定、文风等候选知识，结果先进入“待确认知识”，需要审核后才会成为正式知识库。
            """.strip()
        )


def _render_long_reference_source_inputs(source_type_options: dict) -> dict:
    st.markdown("#### 2. 上传或粘贴资料")
    long_title = st.text_input("资料标题", key="long_reference_title", placeholder="例如：某某原作正文")
    with st.expander("资料属性与切分规则（可选）", expanded=False):
        col_a, col_b = st.columns(2)
        long_scope = col_a.selectbox("资料范围", options=["canon", "reference"], format_func=label_scope, key="long_reference_scope")
        long_authority = col_b.selectbox(
            "资料可信度",
            options=["official", "curated", "community", "unknown"],
            index=0,
            format_func=label_authority,
            key="long_reference_authority",
        )
        long_source_type = col_a.selectbox(
            "资料模板",
            options=list(source_type_options.keys()),
            index=0,
            format_func=lambda key: source_type_options.get(key, label_source_type(key)),
            key="long_reference_source_type",
        )
        long_origin = col_b.text_input("来源说明/链接（可选）", key="long_reference_origin")
        max_chars = st.slider("没有章节标题时，每段最多字数", min_value=2000, max_value=12000, value=6000, step=1000, key="long_reference_max_chars")
    uploaded_file = st.file_uploader("上传 txt/md 文件", type=["txt", "md"], key="long_reference_file")
    uploaded_text = decode_uploaded_text(uploaded_file)
    if uploaded_file is not None:
        upload_signature = hashlib.sha1(uploaded_file.getvalue()).hexdigest()
        if st.session_state.get("long_reference_uploaded_signature") != upload_signature:
            st.session_state["long_reference_uploaded_signature"] = upload_signature
            st.session_state["long_reference_text"] = uploaded_text
            st.session_state.pop("long_reference_segments", None)
            st.session_state.pop("long_reference_batch_id", None)
        st.caption(f"已读取文件：{uploaded_file.name} / {len(uploaded_file.getvalue())} 字节 / 解码后 {len(uploaded_text)} 字符")
        if not uploaded_text.strip():
            st.warning("文件已上传，但没有解码出文本内容。请确认文件不是二进制格式，或尝试另存为 UTF-8/UTF-16 txt。")
    pasted_text = st.text_area(
        "或直接粘贴资料正文",
        value=st.session_state.get("long_reference_text", uploaded_text),
        height=260,
        key="long_reference_text",
    )
    return {
        "long_title": long_title,
        "long_scope": long_scope,
        "long_authority": long_authority,
        "long_source_type": long_source_type,
        "long_origin": long_origin,
        "max_chars": max_chars,
        "uploaded_file": uploaded_file,
        "uploaded_text": uploaded_text,
        "pasted_text": pasted_text,
    }


def _long_reference_fallback_title(long_title: str, uploaded_file) -> str:
    return long_title.strip() or (uploaded_file.name.rsplit(".", 1)[0] if uploaded_file else "长篇资料")


def _render_long_reference_split_controls(long_title: str, uploaded_file, pasted_text: str, max_chars: int) -> list[dict] | None:
    # 自动切分：有文本且尚未切分时自动执行，省去手动点"预览切分"的步骤
    if pasted_text.strip() and "long_reference_segments" not in st.session_state:
        title = _long_reference_fallback_title(long_title, uploaded_file)
        segments = split_long_reference_text(title, pasted_text, max_chars=max_chars)
        st.session_state["long_reference_segments"] = segments
        st.session_state.pop("long_reference_batch_id", None)
        if segments:
            st.caption(f"已自动切分为 {len(segments)} 个资料片段。如需调整切分参数，修改后点击“重新生成切分预览”。")

    if st.button("重新生成切分预览", help="修改资料或切分参数后，重新生成片段预览。已有片段将被替换。"):
        title = _long_reference_fallback_title(long_title, uploaded_file)
        if not pasted_text.strip():
            st.error("没有可处理的文本内容。请上传 txt/md 文件，或把文本粘贴到输入框中。")
            return None
        segments = split_long_reference_text(title, pasted_text, max_chars=max_chars)
        st.session_state["long_reference_segments"] = segments
        st.session_state.pop("long_reference_batch_id", None)
        if segments:
            st.success(f"已切分为 {len(segments)} 个资料片段。")
        else:
            st.error("没有可切分的资料内容。")

    return st.session_state.get("long_reference_segments", [])


def _render_long_reference_segment_preview(
    project_name: str,
    uploaded_file,
    pasted_text: str,
    segments: list[dict],
) -> dict:
    total_chars = sum(int(item.get("char_count", 0)) for item in segments)
    source_file_name = uploaded_file.name if uploaded_file else ""
    content_fingerprint = calculate_text_fingerprint(pasted_text)
    matching_batches = find_matching_long_reference_batches(
        project_name,
        fingerprint=content_fingerprint,
        source_file_name=source_file_name,
        char_count=len(normalize_text_for_fingerprint(pasted_text)),
        segment_count=len(segments),
    )
    st.markdown("#### 3. 检查切分结果")
    st.caption(f"当前预览：{len(segments)} 个片段 / 共 {total_chars} 字符。")
    if content_fingerprint:
        st.caption(f"资料指纹：`{content_fingerprint[:12]}`")
    if matching_batches:
        best_match = matching_batches[0]
        st.warning(
            f"检测到可能已存在的资料批次：{best_match.get('title', '未命名批次')}。"
            f"匹配原因：{'、'.join(best_match.get('match_reasons', [])) or '相似'}。"
        )
        match_options = [batch.get("batch_id", "") for batch in matching_batches]
        selected_match_id = st.selectbox(
            "选择已有批次继续处理",
            options=match_options,
            format_func=lambda batch_id: next(
                (
                    f"{batch.get('title', '未命名批次')} / 匹配分={batch.get('match_score', 0)} / {batch.get('summary', {}).get('segment_count', 0)} 段"
                    for batch in matching_batches if batch.get("batch_id") == batch_id
                ),
                batch_id,
            ),
            key="long_reference_matching_batch",
        )
        if st.button("使用已有批次继续处理"):
            st.session_state["long_reference_batch_id"] = selected_match_id
            st.success("已绑定到已有批次。请在“长篇资料批次管理”里继续导入、提取或重试。")
            st.rerun()
    for segment in segments[:10]:
        st.markdown(f"#### {segment.get('index')}. {segment.get('title')}")
        st.caption(f"切分方式={segment.get('split_method')} / 字符数={segment.get('char_count')}")
        st.write(segment.get("content", "")[:320] + ("..." if len(segment.get("content", "")) > 320 else ""))
    if len(segments) > 10:
        st.caption(f"仅预览前 10 个片段，共 {len(segments)} 个。")

    segment_options = list(range(len(segments)))
    selected_indices = st.multiselect(
        "选择本次要处理的片段",
        options=segment_options,
        default=segment_options,
        format_func=lambda index: f"{segments[index].get('index')}. {segments[index].get('title')}（{segments[index].get('char_count')} 字符）",
        key="long_reference_selected_segments",
    )
    return {
        "source_file_name": source_file_name,
        "content_fingerprint": content_fingerprint,
        "selected_indices": selected_indices,
    }


def _get_or_create_long_reference_preview_batch(batch_context: dict) -> dict:
    batch_id = st.session_state.get("long_reference_batch_id")
    if batch_id:
        existing = load_long_reference_batch(batch_context["project_name"], batch_id)
        if existing:
            return existing
    uploaded_file = batch_context["uploaded_file"]
    fallback_title = uploaded_file.name.rsplit(".", 1)[0] if uploaded_file else "长篇资料"
    batch = create_long_reference_batch(
        batch_context["project_name"],
        title=batch_context["long_title"].strip() or fallback_title,
        scope=batch_context["long_scope"],
        authority=batch_context["long_authority"],
        source_type=batch_context["long_source_type"],
        source_origin=batch_context["long_origin"].strip(),
        source_file_name=batch_context["source_file_name"],
        content_fingerprint=batch_context["content_fingerprint"],
        content_char_count=len(normalize_text_for_fingerprint(batch_context["pasted_text"])),
        segments=batch_context["segments"],
    )
    st.session_state["long_reference_batch_id"] = batch.get("batch_id")
    return batch


def _render_long_reference_extraction_options(knowledge_category_options: list[str]) -> dict:
    with st.expander("提取参数设置", expanded=False):
        shared_expert_preset = st.selectbox(
            "专家提取预设",
            options=list(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.keys()),
            index=list(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.keys()).index("balanced"),
            format_func=lambda value: KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[value]["label"],
            key="long_reference_shared_expert_preset",
            help="预设会自动推荐提取分类和提取模式。第一次处理长篇资料建议使用“平衡总管”。",
        )
        shared_preset = KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[shared_expert_preset]
        shared_category_strategy = st.radio(
            "提取分类初始策略",
            options=["preset", "all", "none"],
            format_func=lambda value: {"preset": "按专家预设", "all": "全选分类", "none": "不预选分类"}.get(value, value),
            horizontal=True,
            key=f"long_reference_shared_category_strategy_{shared_expert_preset}",
            help="只影响当前控件的默认勾选。分类越多，覆盖越广；分类越少，输出越聚焦。",
        )
        shared_categories = st.multiselect(
            "提取分类",
            options=knowledge_category_options,
            default=default_extraction_categories(shared_category_strategy, shared_preset, knowledge_category_options),
            format_func=label_knowledge_category,
            key=f"long_reference_shared_categories_{shared_expert_preset}_{shared_category_strategy}",
            help="决定允许模型输出哪些类型的知识。没有选中的分类不会被主动提取。",
        )
        shared_extraction_mode = st.selectbox(
            "提取模式",
            options=list(KNOWLEDGE_EXTRACTION_MODE_LABELS.keys()),
            index=list(KNOWLEDGE_EXTRACTION_MODE_LABELS.keys()).index(shared_preset["mode"]) if shared_preset["mode"] in KNOWLEDGE_EXTRACTION_MODE_LABELS else 0,
            format_func=lambda value: KNOWLEDGE_EXTRACTION_MODE_LABELS.get(value, value),
            key=f"long_reference_shared_mode_{shared_expert_preset}",
            help="模式决定模型看资料时的优先级。通用更稳，深度更适合正式搭同人资料地基。",
        )
        st.info(KNOWLEDGE_EXTRACTION_MODE_HELP.get(shared_extraction_mode, "当前模式暂无说明。"))
        shared_custom_instructions = st.text_area(
            "补充提取要求（高级，可选）",
            height=90,
            key=f"long_reference_shared_custom_instructions_{shared_expert_preset}",
            placeholder="例如：优先提取主角相关关系；忽略普通战斗过程；保留所有称呼和口癖。",
        )
    return {
        "categories": shared_categories,
        "mode": shared_extraction_mode,
        "custom_instructions": shared_custom_instructions,
    }


def _render_long_reference_quick_processing(
    project_name: str,
    batch_context: dict,
    segments: list[dict],
    selected_indices: list[int],
    knowledge_category_options: list[str],
) -> dict:
    st.markdown("#### 4. 自动处理")
    st.caption("会自动保存批次、导入资料索引、提取知识库条目，并保存低风险条目；有冲突或证据不足的条目会留在“待确认知识”。")
    quick_extract_limit = st.number_input(
        "本次最多处理片段数",
        min_value=1,
        value=min(5, max(1, len(selected_indices))),
        key="long_reference_quick_limit",
        help="不设上限，超过 50 段需要额外确认。",
    )
    quick_quick_high_ok = True
    if quick_extract_limit > 50:
        st.warning(f"处理 {quick_extract_limit} 段将产生约 {quick_extract_limit} 次 LLM 调用，预计耗时会较长。")
        quick_quick_high_ok = st.checkbox(
            "我确认要大量处理",
            key="long_reference_quick_high_confirm",
        )
    selected_count = len(selected_indices)
    planned_quick_count = min(int(quick_extract_limit), selected_count)
    st.info(
        f"本次自动处理将按当前选择顺序处理 {planned_quick_count} 个片段；"
        f"已选择 {selected_count} 个，当前资料共 {len(segments)} 个片段。"
    )
    with st.expander("自动处理选项", expanded=False):
        quick_import_to_index = st.checkbox(
            "同时导入资料索引",
            value=True,
            key="long_reference_quick_import_index",
            help="开启后，原文片段会进入检索库，后续写作可以匹配原文证据。",
        )
        quick_auto_confirm = st.checkbox(
            "自动审核并保存低风险知识",
            value=True,
            key="long_reference_quick_auto_confirm",
            help="只自动确认没有冲突、证据存在、置信度尚可的条目；风险条目会留在待确认队列。",
        )
        quick_consolidate = st.checkbox(
            "提取后自动整理散知识",
            value=False,
            key="long_reference_quick_consolidate",
            help="会尝试把同一批次里的散知识合并成更稳定的角色/关系/设定条目。正式大批量处理时再开启更稳。",
        )

    extraction_options = _render_long_reference_extraction_options(knowledge_category_options)
    shared_categories = extraction_options["categories"]
    shared_extraction_mode = extraction_options["mode"]
    shared_custom_instructions = extraction_options["custom_instructions"]

    if st.button("开始处理所选片段", use_container_width=True, type="primary"):
        if not selected_indices:
            st.error("请先选择片段。")
        elif not shared_categories:
            st.error("请至少选择一个提取分类。")
        elif not quick_quick_high_ok:
            st.error("处理数量超过 50 段，请先勾选确认框。")
        else:
            progress_callback = create_batch_progress_callback("自动处理")
            batch = _get_or_create_long_reference_preview_batch(batch_context)
            updated_batch, quick_summary = _run_with_stream(
                "正在保存批次、导入索引、提取并自动审核低风险知识...",
                run_long_reference_quick_process,
                project_name,
                batch,
                selected_indices[: int(quick_extract_limit)],
                enabled_categories=shared_categories,
                extraction_mode=shared_extraction_mode,
                extract_limit=int(quick_extract_limit),
                import_to_index=quick_import_to_index,
                consolidate_after_extract=quick_consolidate,
                auto_confirm_safe_items=quick_auto_confirm,
                custom_instructions=shared_custom_instructions,
                progress_callback=progress_callback,
            )
            st.session_state["long_reference_quick_result"] = quick_summary
            st.success(
                f"自动处理完成：导入 {quick_summary.get('imported_count', 0)} 段，"
                f"提取 {quick_summary.get('processed_count', 0)} 段，"
                f"新增待确认 {quick_summary.get('new_pending_count', 0)} 条，"
                f"自动保存 {quick_summary.get('auto_confirmed_count', 0)} 条，"
                f"保留待确认 {quick_summary.get('blocked_count', 0)} 条。"
            )
            for failure in quick_summary.get("failed_titles", [])[:5]:
                st.warning(f"处理失败：{failure}")
            st.rerun()

    _render_long_reference_quick_result()
    return extraction_options


def _render_long_reference_quick_result():
    quick_result = st.session_state.get("long_reference_quick_result", {})
    if not quick_result:
        return
    with st.expander("上次自动处理结果", expanded=bool(quick_result.get("blocked_count"))):
        st.caption(
            f"模式={KNOWLEDGE_EXTRACTION_MODE_LABELS.get(quick_result.get('extraction_mode', ''), quick_result.get('extraction_mode', ''))} / "
            f"分类={'、'.join(label_knowledge_category(category) for category in quick_result.get('categories', []))}"
        )
        st.json({
            "导入片段": quick_result.get("imported_count", 0),
            "提取片段": quick_result.get("processed_count", 0),
            "新增候选": quick_result.get("new_pending_count", 0),
            "自动保存": quick_result.get("auto_confirmed_count", 0),
            "自动审核记录": quick_result.get("auto_confirm", {}).get("run_id", ""),
            "保留待确认": quick_result.get("blocked_count", 0),
            "失败": quick_result.get("failed_titles", []),
            "保留原因": quick_result.get("auto_confirm", {}).get("blocked_reasons", {}),
        })


def _render_long_reference_stepwise_processing(
    project_name: str,
    batch_context: dict,
    selected_indices: list[int],
    shared_categories: list[str],
    shared_extraction_mode: str,
    shared_custom_instructions: str,
):
    with st.expander("高级：分步处理", expanded=False):
        st.caption("适合调试或手动控制。保存批次、导入索引、提取知识可以分别执行。")
        if st.button("保存为处理批次", help="保存当前切分结果，方便之后继续处理、重试失败片段或重新提取。"):
            batch = _get_or_create_long_reference_preview_batch(batch_context)
            st.success(f"已保存批次：{batch.get('title')} / {batch.get('summary', {}).get('segment_count', 0)} 个片段。")
            st.rerun()

        if st.button(
            "导入资料索引",
            help="把所选片段作为可检索原文资料保存。适合让后续写作引用原文，但不会自动生成角色/设定知识。",
        ):
            if not selected_indices:
                st.error("请先选择片段。")
            else:
                batch = _get_or_create_long_reference_preview_batch(batch_context)
                _, imported = import_long_reference_segments(project_name, batch, selected_indices)
                st.success(f"已导入 {imported} 个长篇资料片段，并重建检索索引。")
                st.rerun()

        st.markdown("##### 手动提取知识库条目")
        batch_limit = st.number_input("本次最多提取片段数", min_value=1, value=3, key="long_reference_extract_limit")
        manual_extract_high_ok = True
        if batch_limit > 50:
            st.warning(f"提取 {batch_limit} 段将产生约 {batch_limit} 次 LLM 调用，预计耗时会较长。")
            manual_extract_high_ok = st.checkbox(
                "我确认要大量处理",
                key="long_reference_manual_extract_high_confirm",
            )
        manual_consolidate = st.checkbox(
            "提取后自动整理散知识",
            value=False,
            key="long_reference_manual_consolidate",
            help="提取完成后自动合并重复/同名的候选知识条目。提取片段数较多时建议开启。",
        )
        if st.button("提取知识库条目", use_container_width=True):
            if not selected_indices:
                st.error("请先选择片段。")
            elif not shared_categories:
                st.error("请至少选择一个提取分类。")
            elif not manual_extract_high_ok:
                st.error("处理数量超过 50 段，请先勾选确认框。")
            else:
                progress_callback = create_batch_progress_callback("手动提取知识库条目")
                batch = _get_or_create_long_reference_preview_batch(batch_context)
                _, processed, queued_total, failed_titles = _run_with_stream(
                    "正在分批提取知识库条目...",
                    extract_long_reference_segments_to_queue,
                    project_name,
                    batch,
                    selected_indices[: int(batch_limit)],
                    shared_categories,
                    extraction_mode=shared_extraction_mode,
                    custom_instructions=shared_custom_instructions,
                    progress_callback=progress_callback,
                )
                st.session_state["long_reference_manual_extract_result"] = {
                    "processed": processed,
                    "queued_total": queued_total,
                    "failed_titles": failed_titles,
                }
                if manual_consolidate and queued_total:
                    consolidation_summary = _run_with_stream(
                        "正在整理散知识...",
                        consolidate_batch_pending_items,
                        project_name,
                        batch,
                        categories=shared_categories,
                        consolidation_mode="balanced",
                        limit=max(20, min(120, queued_total)),
                        preview_language="json",
                    )
                    st.success(
                        f"追加整理：合并 {consolidation_summary.get('source_count', 0)} 条为 "
                        f"{consolidation_summary.get('queued_count', 0)} 条稳定知识。"
                    )
                    st.session_state["long_reference_manual_extract_result"]["consolidation"] = consolidation_summary
                st.rerun()

        manual_result = st.session_state.get("long_reference_manual_extract_result", {})
        if manual_result:
            with st.expander("上次手动提取结果", expanded=bool(manual_result.get("failed_titles"))):
                st.json({
                    "处理片段": manual_result.get("processed", 0),
                    "新增候选": manual_result.get("queued_total", 0),
                    "失败": manual_result.get("failed_titles", []),
                    "整理": manual_result.get("consolidation", {}),
                })


def render_long_reference_importer(project_name: str, source_type_options: dict, knowledge_category_options: list[str], expanded: bool = False):
    with st.expander("长篇文本导入", expanded=expanded):
        st.info("推荐顺序：选择处理方案 / 上传或粘贴文本 / 检查切分结果 / 自动处理。处理完成后，风险条目会留在“待确认知识”里。")
        _render_long_reference_preset_selector()
        _render_long_reference_flow_notes()

        source_inputs = _render_long_reference_source_inputs(source_type_options)
        long_title = source_inputs["long_title"]
        long_scope = source_inputs["long_scope"]
        long_authority = source_inputs["long_authority"]
        long_source_type = source_inputs["long_source_type"]
        long_origin = source_inputs["long_origin"]
        max_chars = source_inputs["max_chars"]
        uploaded_file = source_inputs["uploaded_file"]
        pasted_text = source_inputs["pasted_text"]

        segments = _render_long_reference_split_controls(long_title, uploaded_file, pasted_text, max_chars)
        if not segments:
            return

        preview_state = _render_long_reference_segment_preview(project_name, uploaded_file, pasted_text, segments)
        source_file_name = preview_state["source_file_name"]
        content_fingerprint = preview_state["content_fingerprint"]
        selected_indices = preview_state["selected_indices"]

        batch_context = {
            "project_name": project_name,
            "long_title": long_title,
            "long_scope": long_scope,
            "long_authority": long_authority,
            "long_source_type": long_source_type,
            "long_origin": long_origin,
            "uploaded_file": uploaded_file,
            "source_file_name": source_file_name,
            "content_fingerprint": content_fingerprint,
            "pasted_text": pasted_text,
            "segments": segments,
        }

        extraction_options = _render_long_reference_quick_processing(
            project_name,
            batch_context,
            segments,
            selected_indices,
            knowledge_category_options,
        )
        shared_categories = extraction_options["categories"]
        shared_extraction_mode = extraction_options["mode"]
        shared_custom_instructions = extraction_options["custom_instructions"]

        _render_long_reference_stepwise_processing(
            project_name,
            batch_context,
            selected_indices,
            shared_categories,
            shared_extraction_mode,
            shared_custom_instructions,
        )
