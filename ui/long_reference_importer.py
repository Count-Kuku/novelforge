"""Long reference ingestion panels."""
from __future__ import annotations

import hashlib
import html

import streamlit as st

from novelforge.domain.extraction_presets import (
    KNOWLEDGE_EXTRACTION_EXPERT_PRESETS,
    KNOWLEDGE_EXTRACTION_MODE_HELP,
    KNOWLEDGE_EXTRACTION_MODE_LABELS,
    default_extraction_categories,
)
from novelforge.services.memory import create_long_reference_batch, load_long_reference_batch
from novelforge.services.document_parsing import (
    DocumentParsingError,
    combine_parsed_documents,
    parse_document_bytes,
)
from novelforge.workflows.source_workflows import (
    calculate_text_fingerprint,
    consolidate_batch_pending_items,
    extract_long_reference_segments_to_queue,
    find_matching_long_reference_batches,
    import_long_reference_segments,
    normalize_text_for_fingerprint,
    split_long_reference_text,
)
from novelforge.workflows.ingestion_tasks import (
    build_long_reference_ingestion_estimate,
    create_long_reference_ingestion_task,
)
from novelforge.workflows.ingestion_task_dispatcher import wake_ingestion_task_dispatcher
from ui.common import create_batch_progress_callback, scoped_widget_key
from ui.labels import label_authority, label_knowledge_category, label_scope, label_source_type
from ui.ingestion_task_estimate import render_ingestion_task_estimate
from ui.ingestion_batch_guard import render_batch_write_guard
from ui.streaming import run_with_stream as _run_with_stream


LONG_REFERENCE_PRESET_INFO = {
    "fanfic_foundation": {
        "label": "同人资料准备（推荐）",
        "button": "使用同人资料准备方案",
        "summary": "第一次导入整本原作时优先选。它会尽量整理后续写作反复要用的角色、关系、时间线、世界观、能力道具和硬约束。",
        "effect": "按官方原作资料处理，进行较完整的深度整理，并自动合并重复或零散内容。",
    },
    "canon_foundation": {
        "label": "严格原作校验",
        "button": "使用严格原作校验",
        "summary": "只想补一层“不能错、不能改”的原作硬事实时选。它更保守，尽量少推测，适合防止后续写作违背原作。",
        "effect": "只整理有明确证据的原作事实，减少推测，适合补充不能写错的内容。",
    },
    "style_reference": {
        "label": "文风参考",
        "button": "使用文风参考",
        "summary": "导入样本文本或只想学原作表达方式时选。它关注叙事节奏、对白、氛围和描写习惯，不适合拿来补全世界观资料。",
        "effect": "按参考文本处理，重点学习叙事节奏、对白、氛围和描写习惯。",
    },
}

StateScope = tuple[str, str]


def _long_reference_key(base: str, state_scope: StateScope, *parts: object) -> str:
    return scoped_widget_key(base, *state_scope, *parts)


def apply_long_reference_fanfic_preset(preset: str, state_scope: StateScope):
    if preset not in LONG_REFERENCE_PRESET_INFO:
        return
    if preset == "canon_foundation":
        st.session_state[_long_reference_key("long_reference_scope", state_scope)] = "canon"
        st.session_state[_long_reference_key("long_reference_authority", state_scope)] = "official"
        st.session_state[_long_reference_key("long_reference_source_type", state_scope)] = "external_source"
        st.session_state[_long_reference_key("long_reference_quick_import_index", state_scope)] = True
        st.session_state[_long_reference_key("long_reference_quick_auto_confirm", state_scope)] = True
        st.session_state[_long_reference_key("long_reference_quick_consolidate", state_scope)] = False
        st.session_state[_long_reference_key("long_reference_shared_expert_preset", state_scope)] = "canon_auditor"
        st.session_state[_long_reference_key("long_reference_shared_category_strategy", state_scope, "canon_auditor")] = "preset"
        st.session_state[_long_reference_key("long_reference_shared_mode", state_scope, "canon_auditor")] = "strict_canon"
    elif preset == "fanfic_foundation":
        st.session_state[_long_reference_key("long_reference_scope", state_scope)] = "canon"
        st.session_state[_long_reference_key("long_reference_authority", state_scope)] = "official"
        st.session_state[_long_reference_key("long_reference_source_type", state_scope)] = "external_source"
        st.session_state[_long_reference_key("long_reference_quick_import_index", state_scope)] = True
        st.session_state[_long_reference_key("long_reference_quick_auto_confirm", state_scope)] = True
        st.session_state[_long_reference_key("long_reference_quick_consolidate", state_scope)] = True
        st.session_state[_long_reference_key("long_reference_shared_expert_preset", state_scope)] = "balanced"
        st.session_state[_long_reference_key("long_reference_shared_category_strategy", state_scope, "balanced")] = "preset"
        st.session_state[_long_reference_key("long_reference_shared_mode", state_scope, "balanced")] = "deep"
    elif preset == "style_reference":
        st.session_state[_long_reference_key("long_reference_scope", state_scope)] = "reference"
        st.session_state[_long_reference_key("long_reference_authority", state_scope)] = "curated"
        st.session_state[_long_reference_key("long_reference_source_type", state_scope)] = "external_source"
        st.session_state[_long_reference_key("long_reference_quick_import_index", state_scope)] = True
        st.session_state[_long_reference_key("long_reference_quick_auto_confirm", state_scope)] = True
        st.session_state[_long_reference_key("long_reference_quick_consolidate", state_scope)] = False
        st.session_state[_long_reference_key("long_reference_shared_expert_preset", state_scope)] = "style_expert"
        st.session_state[_long_reference_key("long_reference_shared_category_strategy", state_scope, "style_expert")] = "preset"
        st.session_state[_long_reference_key("long_reference_shared_mode", state_scope, "style_expert")] = "style"
    st.session_state[_long_reference_key("long_reference_active_preset", state_scope)] = preset
    st.session_state[_long_reference_key("long_reference_preset_notice", state_scope)] = f"已应用：{LONG_REFERENCE_PRESET_INFO[preset]['label']}"


def _render_long_reference_preset_selector(state_scope: StateScope):
    with st.expander("1. 选择处理方案", expanded=True):
        st.caption("先说明这批资料准备用来做什么。第一次整理整本原作，通常直接选“同人资料准备”。系统会自动设置资料范围、可信度和整理方式，之后仍可手动调整。")
        active_preset = st.session_state.get(_long_reference_key("long_reference_active_preset", state_scope), "")
        if active_preset in LONG_REFERENCE_PRESET_INFO:
            active_info = LONG_REFERENCE_PRESET_INFO[active_preset]
            st.success(st.session_state.get(_long_reference_key("long_reference_preset_notice", state_scope), f"当前方案：{active_info['label']}"))
            st.caption(active_info["effect"])
        else:
            st.info("当前还没有选择处理方案。第一次整理整本原作，建议选“同人资料准备（推荐）”。")
        preset_cols = st.columns(3)
        for column, preset_key in zip(preset_cols, LONG_REFERENCE_PRESET_INFO):
            preset_info = LONG_REFERENCE_PRESET_INFO[preset_key]
            with column:
                is_active = active_preset == preset_key
                with st.container(border=True):
                    st.markdown(
                        f"""
                        <div class="nf-preset-card">
                            <div class="nf-preset-card-title">{html.escape(preset_info['label'])}{'（当前）' if is_active else ''}</div>
                            <div class="nf-preset-card-copy">{html.escape(preset_info['summary'])}</div>
                            <div class="nf-preset-card-effect">{html.escape(preset_info['effect'])}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        "已使用此方案" if is_active else preset_info["button"],
                        key=_long_reference_key("long_reference_preset", state_scope, preset_key),
                        use_container_width=True,
                        type="primary" if is_active else "secondary",
                    ):
                        apply_long_reference_fanfic_preset(preset_key, state_scope)
                        st.rerun()


def _render_long_reference_flow_notes():
    with st.expander("流程说明", expanded=False):
        st.markdown(
            """
1. **预览切分**：只把文本临时拆成章节/片段，方便检查切分是否合理，还不会写入资料库。
2. **保存为处理批次**：保存这次切分结果，之后可以在“长篇批次”中继续处理或重试失败片段。
3. **保存为可匹配原文**：让后续规划、写作和审阅能找到相关原文证据；这一步不会自动生成角色卡或世界设定卡。
4. **整理为知识条目**：从原文中整理角色、关系、时间线、世界观和文风等内容。结果会先进入“待审核设定”，确认后才成为正式知识。
            """.strip()
        )


def _render_long_reference_source_inputs(source_type_options: dict, state_scope: StateScope) -> dict:
    st.markdown("#### 2. 上传或粘贴资料")
    long_title = st.text_input("资料标题", key=_long_reference_key("long_reference_title", state_scope), placeholder="例如：某某原作正文")
    with st.expander("资料属性与切分规则（可选）", expanded=False):
        col_a, col_b = st.columns(2)
        long_scope = col_a.selectbox("资料范围", options=["canon", "reference"], format_func=label_scope, key=_long_reference_key("long_reference_scope", state_scope))
        long_authority = col_b.selectbox(
            "资料可信度",
            options=["official", "curated", "community", "unknown"],
            index=0,
            format_func=label_authority,
            key=_long_reference_key("long_reference_authority", state_scope),
        )
        long_source_type = col_a.selectbox(
            "资料模板",
            options=list(source_type_options.keys()),
            index=0,
            format_func=lambda key: source_type_options.get(key, label_source_type(key)),
            key=_long_reference_key("long_reference_source_type", state_scope),
        )
        long_origin = col_b.text_input("来源说明/链接（可选）", key=_long_reference_key("long_reference_origin", state_scope))
        max_chars = st.slider("没有章节标题时，每段最多字数", min_value=2000, max_value=12000, value=6000, step=1000, key=_long_reference_key("long_reference_max_chars", state_scope))
    uploaded_files = st.file_uploader(
        "上传资料文件（支持多选）",
        type=["txt", "md", "markdown", "docx", "epub", "pdf"],
        accept_multiple_files=True,
        key=_long_reference_key("long_reference_file", state_scope),
        help="可一次上传多份资料。系统会保留 Markdown/Word/EPUB 的标题层级；PDF 按页提取文本，扫描版 PDF 会提示需要 OCR。",
    )
    uploaded_files = list(uploaded_files or [])
    parsed_documents = []
    parse_errors: list[str] = []
    for uploaded_file in uploaded_files:
        try:
            parsed_documents.append(parse_document_bytes(uploaded_file.name, uploaded_file.getvalue()))
        except DocumentParsingError as exc:
            parse_errors.append(str(exc))
    uploaded_text = combine_parsed_documents(parsed_documents)
    upload_signature_key = _long_reference_key("long_reference_uploaded_signature", state_scope)
    text_key = _long_reference_key("long_reference_text", state_scope)
    segments_key = _long_reference_key("long_reference_segments", state_scope)
    batch_id_key = _long_reference_key("long_reference_batch_id", state_scope)
    if uploaded_files:
        digest = hashlib.sha256()
        for uploaded_file in uploaded_files:
            digest.update(uploaded_file.name.encode("utf-8", errors="ignore"))
            digest.update(b"\0")
            digest.update(uploaded_file.getvalue())
        upload_signature = digest.hexdigest()
        if st.session_state.get(upload_signature_key) != upload_signature:
            st.session_state[upload_signature_key] = upload_signature
            st.session_state[text_key] = uploaded_text
            st.session_state.pop(segments_key, None)
            st.session_state.pop(batch_id_key, None)
        total_bytes = sum(len(item.getvalue()) for item in uploaded_files)
        st.caption(f"已读取 {len(parsed_documents)}/{len(uploaded_files)} 个文件 / {total_bytes} 字节 / 提取后 {len(uploaded_text)} 字符")
        for document in parsed_documents:
            st.caption(
                f"{document.filename}：{document.parser_name} / {len(document.sections)} 个结构段"
                + (f" / 提示：{'；'.join(document.warnings)}" if document.warnings else "")
            )
        for error in parse_errors:
            st.error(error)
        if not uploaded_text.strip():
            st.warning("文件已上传，但没有提取出正文。扫描版 PDF 需先 OCR；加密或损坏的文件请转换后重试。")
    pasted_text = st.text_area(
        "或直接粘贴资料正文",
        value=st.session_state.get(text_key, uploaded_text),
        height=260,
        key=text_key,
    )
    return {
        "long_title": long_title,
        "long_scope": long_scope,
        "long_authority": long_authority,
        "long_source_type": long_source_type,
        "long_origin": long_origin,
        "max_chars": max_chars,
        "uploaded_files": uploaded_files,
        "uploaded_text": uploaded_text,
        "parsed_documents": [item.to_dict() for item in parsed_documents],
        "parse_errors": parse_errors,
        "pasted_text": pasted_text,
    }


def _long_reference_fallback_title(long_title: str, uploaded_files) -> str:
    files = list(uploaded_files or [])
    if long_title.strip():
        return long_title.strip()
    if len(files) == 1:
        return files[0].name.rsplit(".", 1)[0]
    if files:
        return f"{files[0].name.rsplit('.', 1)[0]} 等 {len(files)} 份资料"
    return "长篇资料"


def _render_long_reference_split_controls(
    long_title: str,
    uploaded_files,
    pasted_text: str,
    max_chars: int,
    source_type: str,
    state_scope: StateScope,
) -> list[dict] | None:
    segments_key = _long_reference_key("long_reference_segments", state_scope)
    batch_id_key = _long_reference_key("long_reference_batch_id", state_scope)
    split_signature_key = _long_reference_key("long_reference_split_signature", state_scope)
    split_signature = hashlib.sha256(
        f"{long_title}\0{max_chars}\0{source_type}\0{pasted_text}".encode("utf-8")
    ).hexdigest()
    # 文本、标题、模板或上限变化后立即废弃旧预览，避免把新原文哈希
    # 与旧片段/旧证据位置保存到同一批次。
    if pasted_text.strip() and st.session_state.get(split_signature_key) != split_signature:
        title = _long_reference_fallback_title(long_title, uploaded_files)
        segments = split_long_reference_text(
            title,
            pasted_text,
            max_chars=max_chars,
            source_type=source_type,
        )
        st.session_state[segments_key] = segments
        st.session_state[split_signature_key] = split_signature
        st.session_state.pop(batch_id_key, None)
        if segments:
            st.caption(f"已自动切分为 {len(segments)} 个资料片段。如需调整切分参数，修改后点击“重新生成切分预览”。")

    if st.button(
        "重新生成切分预览",
        help="修改资料或切分参数后，重新生成片段预览。已有片段将被替换。",
        key=_long_reference_key("long_reference_resplit", state_scope),
    ):
        title = _long_reference_fallback_title(long_title, uploaded_files)
        if not pasted_text.strip():
            st.error("没有可处理的文本内容。请上传资料文件，或把文本粘贴到输入框中。")
            return None
        segments = split_long_reference_text(
            title,
            pasted_text,
            max_chars=max_chars,
            source_type=source_type,
        )
        st.session_state[segments_key] = segments
        st.session_state[split_signature_key] = split_signature
        st.session_state.pop(batch_id_key, None)
        if segments:
            st.success(f"已切分为 {len(segments)} 个资料片段。")
        else:
            st.error("没有可切分的资料内容。")

    return st.session_state.get(segments_key, [])


def _render_long_reference_segment_preview(
    project_name: str,
    uploaded_files,
    pasted_text: str,
    segments: list[dict],
    state_scope: StateScope,
) -> dict:
    total_chars = sum(int(item.get("char_count", 0)) for item in segments)
    files = list(uploaded_files or [])
    source_file_name = files[0].name if len(files) == 1 else "；".join(item.name for item in files)
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
            key=_long_reference_key("long_reference_matching_batch", state_scope),
        )
        if st.button(
            "使用已有批次继续处理",
            key=_long_reference_key("long_reference_use_matching_batch", state_scope),
        ):
            st.session_state[_long_reference_key("long_reference_batch_id", state_scope)] = selected_match_id
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
        key=_long_reference_key("long_reference_selected_segments", state_scope),
    )
    return {
        "source_file_name": source_file_name,
        "content_fingerprint": content_fingerprint,
        "selected_indices": selected_indices,
    }


def _get_or_create_long_reference_preview_batch(batch_context: dict) -> dict:
    state_scope = batch_context["state_scope"]
    batch_id_key = _long_reference_key("long_reference_batch_id", state_scope)
    batch_id = st.session_state.get(batch_id_key)
    if batch_id:
        existing = load_long_reference_batch(batch_context["project_name"], batch_id)
        if existing:
            return existing
    uploaded_files = list(batch_context.get("uploaded_files") or [])
    fallback_title = _long_reference_fallback_title("", uploaded_files)
    batch = create_long_reference_batch(
        batch_context["project_name"],
        title=batch_context["long_title"].strip() or fallback_title,
        scope=batch_context["long_scope"],
        authority=batch_context["long_authority"],
        source_type=batch_context["long_source_type"],
        source_origin=batch_context["long_origin"].strip(),
        source_file_name=batch_context["source_file_name"],
        content_fingerprint=batch_context["content_fingerprint"],
        source_content_hash=batch_context["source_content_hash"],
        content_char_count=len(batch_context["pasted_text"]),
        segments=batch_context["segments"],
        story_id=batch_context.get("story_id", "default"),
        parser_metadata={"documents": batch_context.get("parsed_documents", [])},
        source_files=[
            {
                "name": item.name,
                "size": len(item.getvalue()),
                "sha256": hashlib.sha256(item.getvalue()).hexdigest(),
            }
            for item in uploaded_files
        ],
    )
    st.session_state[batch_id_key] = batch.get("batch_id")
    return batch


def _render_long_reference_extraction_options(
    knowledge_category_options: list[str],
    state_scope: StateScope,
) -> dict:
    with st.expander("提取参数设置", expanded=False):
        shared_expert_preset = st.selectbox(
            "专家提取预设",
            options=list(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.keys()),
            index=list(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.keys()).index("balanced"),
            format_func=lambda value: KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[value]["label"],
            key=_long_reference_key("long_reference_shared_expert_preset", state_scope),
            help="预设会自动推荐提取分类和提取模式。第一次处理长篇资料建议使用“平衡总管”。",
        )
        shared_preset = KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[shared_expert_preset]
        shared_category_strategy = st.radio(
            "提取分类初始策略",
            options=["preset", "all", "none"],
            format_func=lambda value: {"preset": "按专家预设", "all": "全选分类", "none": "不预选分类"}.get(value, value),
            horizontal=True,
            key=_long_reference_key("long_reference_shared_category_strategy", state_scope, shared_expert_preset),
            help="只影响当前控件的默认勾选。分类越多，覆盖越广；分类越少，输出越聚焦。",
        )
        shared_categories = st.multiselect(
            "提取分类",
            options=knowledge_category_options,
            default=default_extraction_categories(shared_category_strategy, shared_preset, knowledge_category_options),
            format_func=label_knowledge_category,
            key=_long_reference_key(
                "long_reference_shared_categories",
                state_scope,
                shared_expert_preset,
                shared_category_strategy,
            ),
            help="决定允许模型输出哪些类型的知识。没有选中的分类不会被主动提取。",
        )
        shared_extraction_mode = st.selectbox(
            "提取模式",
            options=list(KNOWLEDGE_EXTRACTION_MODE_LABELS.keys()),
            index=list(KNOWLEDGE_EXTRACTION_MODE_LABELS.keys()).index(shared_preset["mode"]) if shared_preset["mode"] in KNOWLEDGE_EXTRACTION_MODE_LABELS else 0,
            format_func=lambda value: KNOWLEDGE_EXTRACTION_MODE_LABELS.get(value, value),
            key=_long_reference_key("long_reference_shared_mode", state_scope, shared_expert_preset),
            help="模式决定模型整理资料时的细致程度。通用模式更稳，深度模式更适合建立完整的同人创作资料库。",
        )
        st.info(KNOWLEDGE_EXTRACTION_MODE_HELP.get(shared_extraction_mode, "当前模式暂无说明。"))
        shared_custom_instructions = st.text_area(
            "补充提取要求（高级，可选）",
            height=90,
            key=_long_reference_key("long_reference_shared_custom_instructions", state_scope, shared_expert_preset),
            placeholder="例如：优先提取主角相关关系；忽略普通战斗过程；保留所有称呼和口癖。",
        )
    return {
        "categories": shared_categories,
        "mode": shared_extraction_mode,
        "custom_instructions": shared_custom_instructions,
    }


def _render_long_reference_quick_processing(
    project_name: str,
    state_scope: StateScope,
    batch_context: dict,
    segments: list[dict],
    selected_indices: list[int],
    knowledge_category_options: list[str],
) -> dict:
    st.markdown("#### 4. 自动处理")
    st.caption("系统会依次保存批次、保存可匹配原文、整理知识条目，并自动确认低风险内容；有冲突或证据不足的内容会留在“待审核设定”。")
    quick_extract_limit = st.number_input(
        "本次最多处理片段数",
        min_value=1,
        value=min(5, max(1, len(selected_indices))),
        key=_long_reference_key("long_reference_quick_limit", state_scope),
        help="不设上限，超过 50 段需要额外确认。",
    )
    quick_quick_high_ok = True
    if quick_extract_limit > 50:
        st.warning(f"处理 {quick_extract_limit} 段将产生约 {quick_extract_limit} 次 LLM 调用，预计耗时会较长。")
        quick_quick_high_ok = st.checkbox(
            "我确认要大量处理",
            key=_long_reference_key("long_reference_quick_high_confirm", state_scope),
        )
    selected_count = len(selected_indices)
    planned_quick_count = min(int(quick_extract_limit), selected_count)
    st.info(
        f"本次自动处理将按当前选择顺序处理 {planned_quick_count} 个片段；"
        f"已选择 {selected_count} 个，当前资料共 {len(segments)} 个片段。"
    )
    with st.expander("自动处理选项", expanded=False):
        quick_import_to_index = st.checkbox(
            "同时保存为可匹配原文",
            value=True,
            key=_long_reference_key("long_reference_quick_import_index", state_scope),
            help="开启后，原文片段会成为可匹配资料，后续写作可以找到相关原文证据。",
        )
        quick_auto_confirm = st.checkbox(
            "自动审核并保存低风险知识",
            value=True,
            key=_long_reference_key("long_reference_quick_auto_confirm", state_scope),
            help="只自动确认没有冲突、有证据且可信度较高的内容；风险内容会留在待审核设定中。",
        )
        quick_consolidate = st.checkbox(
            "提取后自动整理散知识",
            value=False,
            key=_long_reference_key("long_reference_quick_consolidate", state_scope),
            help="会尝试把同一批次里的散知识合并成更稳定的角色/关系/设定条目。正式大批量处理时再开启更稳。",
        )

    extraction_options = _render_long_reference_extraction_options(knowledge_category_options, state_scope)
    shared_categories = extraction_options["categories"]
    shared_extraction_mode = extraction_options["mode"]
    shared_custom_instructions = extraction_options["custom_instructions"]
    planned_indices = selected_indices[: int(quick_extract_limit)]
    estimate = build_long_reference_ingestion_estimate(
        {"segments": segments},
        planned_indices,
        enabled_categories=shared_categories,
        extraction_mode=shared_extraction_mode,
        import_to_index=quick_import_to_index,
        consolidate_after_extract=quick_consolidate,
        custom_instructions=shared_custom_instructions,
    )
    estimate_approved = render_ingestion_task_estimate(
        estimate,
        expanded=planned_quick_count > 20,
        confirmation_key=_long_reference_key(
            "long_reference_quick_budget_confirm", state_scope
        ),
    )

    if st.button(
        "开始处理所选片段",
        use_container_width=True,
        type="primary",
        key=_long_reference_key("long_reference_quick_process", state_scope),
    ):
        if not selected_indices:
            st.error("请先选择片段。")
        elif not shared_categories:
            st.error("请至少选择一个提取分类。")
        elif not quick_quick_high_ok:
            st.error("处理数量超过 50 段，请先勾选确认框。")
        elif not estimate_approved:
            st.error("本次预估超过预算确认阈值，请先确认 Token 与费用上界。")
        else:
            try:
                batch = _get_or_create_long_reference_preview_batch(batch_context)
                task = create_long_reference_ingestion_task(
                    project_name,
                    batch,
                    planned_indices,
                    enabled_categories=shared_categories,
                    extraction_mode=shared_extraction_mode,
                    extract_limit=int(quick_extract_limit),
                    import_to_index=quick_import_to_index,
                    consolidate_after_extract=quick_consolidate,
                    auto_confirm_safe_items=quick_auto_confirm,
                    custom_instructions=shared_custom_instructions,
                    story_id=str(st.session_state.get("active_story_id") or "default"),
                )
            except Exception as exc:
                st.error(f"无法创建资料任务：{exc}")
                return extraction_options
            st.session_state[_long_reference_key("long_reference_quick_result", state_scope)] = {
                "task_id": task.get("task_id", ""),
                "queued": True,
                "estimate": task.get("estimate", {}),
            }
            story_id = str(st.session_state.get("active_story_id") or "default")
            st.session_state[scoped_widget_key("source_ingestion_task_select", project_name, story_id)] = task["task_id"]
            st.session_state[scoped_widget_key("ingestion_workspace_section", project_name, story_id)] = "资料任务"
            wake_ingestion_task_dispatcher()
            st.rerun()

    _render_long_reference_quick_result(state_scope)
    return extraction_options


def _render_long_reference_quick_result(state_scope: StateScope):
    quick_result = st.session_state.get(_long_reference_key("long_reference_quick_result", state_scope), {})
    if not quick_result:
        return
    with st.expander("上次自动处理结果", expanded=bool(quick_result.get("blocked_count"))):
        if quick_result.get("queued"):
            st.info(f"后台任务已创建：{quick_result.get('task_id', '')}。请在“资料任务”中查看实时状态。")
            return
        st.caption(
            f"模式={KNOWLEDGE_EXTRACTION_MODE_LABELS.get(quick_result.get('extraction_mode', ''), quick_result.get('extraction_mode', ''))} / "
            f"分类={'、'.join(label_knowledge_category(category) for category in quick_result.get('categories', []))}"
        )
        st.json({
            "任务 ID": quick_result.get("task_id", ""),
            "导入片段": quick_result.get("imported_count", 0),
            "提取片段": quick_result.get("processed_count", 0),
            "新增候选": quick_result.get("new_pending_count", 0),
            "自动保存": quick_result.get("auto_confirmed_count", 0),
            "自动审核记录": quick_result.get("auto_confirm", {}).get("run_id", ""),
            "保留待审核": quick_result.get("blocked_count", 0),
            "失败": quick_result.get("failed_titles", []),
            "保留原因": quick_result.get("auto_confirm", {}).get("blocked_reasons", {}),
        })


def _render_long_reference_stepwise_processing(
    project_name: str,
    state_scope: StateScope,
    batch_context: dict,
    selected_indices: list[int],
    shared_categories: list[str],
    shared_extraction_mode: str,
    shared_custom_instructions: str,
):
    with st.expander("高级：分步处理", expanded=False):
        st.caption("适合调试或手动控制。保存批次、导入索引、提取知识可以分别执行。")
        if st.button(
            "保存为处理批次",
            help="保存当前切分结果，方便之后继续处理、重试失败片段或重新提取。",
            key=_long_reference_key("long_reference_save_batch", state_scope),
        ):
            batch = _get_or_create_long_reference_preview_batch(batch_context)
            st.success(f"已保存批次：{batch.get('title')} / {batch.get('summary', {}).get('segment_count', 0)} 个片段。")
            st.rerun()

        if st.button(
            "保存为可匹配原文",
            help="把所选片段作为可检索原文资料保存。适合让后续写作引用原文，但不会自动生成角色/设定知识。",
            key=_long_reference_key("long_reference_import_segments", state_scope),
        ):
            if not selected_indices:
                st.error("请先选择片段。")
            else:
                batch = _get_or_create_long_reference_preview_batch(batch_context)
                _, imported = import_long_reference_segments(project_name, batch, selected_indices)
                st.success(f"已导入 {imported} 个长篇资料片段，并重建检索索引。")
                st.rerun()

        st.markdown("##### 手动提取知识库条目")
        batch_limit = st.number_input(
            "本次最多提取片段数",
            min_value=1,
            value=3,
            key=_long_reference_key("long_reference_extract_limit", state_scope),
        )
        manual_extract_high_ok = True
        if batch_limit > 50:
            st.warning(f"提取 {batch_limit} 段将产生约 {batch_limit} 次 LLM 调用，预计耗时会较长。")
            manual_extract_high_ok = st.checkbox(
                "我确认要大量处理",
                key=_long_reference_key("long_reference_manual_extract_high_confirm", state_scope),
            )
        manual_consolidate = st.checkbox(
            "提取后自动整理散知识",
            value=False,
            key=_long_reference_key("long_reference_manual_consolidate", state_scope),
            help="提取完成后自动合并重复/同名的候选知识条目。提取片段数较多时建议开启。",
        )
        if st.button(
            "提取知识库条目",
            use_container_width=True,
            key=_long_reference_key("long_reference_manual_extract", state_scope),
        ):
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
                    story_id=str(st.session_state.get("active_story_id") or "default"),
                )
                manual_result_key = _long_reference_key("long_reference_manual_extract_result", state_scope)
                st.session_state[manual_result_key] = {
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
                        story_id=str(st.session_state.get("active_story_id") or "default"),
                        preview_language="json",
                    )
                    st.success(
                        f"追加整理：合并 {consolidation_summary.get('source_count', 0)} 条为 "
                        f"{consolidation_summary.get('queued_count', 0)} 条稳定知识。"
                    )
                    st.session_state[manual_result_key]["consolidation"] = consolidation_summary
                st.rerun()

        manual_result = st.session_state.get(
            _long_reference_key("long_reference_manual_extract_result", state_scope),
            {},
        )
        if manual_result:
            with st.expander("上次手动提取结果", expanded=bool(manual_result.get("failed_titles"))):
                st.json({
                    "处理片段": manual_result.get("processed", 0),
                    "新增候选": manual_result.get("queued_total", 0),
                    "失败": manual_result.get("failed_titles", []),
                    "整理": manual_result.get("consolidation", {}),
                })


def render_long_reference_importer(project_name: str, source_type_options: dict, knowledge_category_options: list[str], expanded: bool = False):
    current_story_id = str(st.session_state.get("active_story_id") or "default")
    state_scope = (project_name, current_story_id)
    with st.expander("长篇文本导入", expanded=expanded):
        st.info("推荐顺序：选择处理方案 → 上传或粘贴文本 → 检查切分结果 → 自动处理。有冲突或证据不足的内容会留在“待审核设定”中。")
        _render_long_reference_preset_selector(state_scope)
        _render_long_reference_flow_notes()

        source_inputs = _render_long_reference_source_inputs(source_type_options, state_scope)
        long_title = source_inputs["long_title"]
        long_scope = source_inputs["long_scope"]
        long_authority = source_inputs["long_authority"]
        long_source_type = source_inputs["long_source_type"]
        long_origin = source_inputs["long_origin"]
        max_chars = source_inputs["max_chars"]
        uploaded_files = source_inputs["uploaded_files"]
        pasted_text = source_inputs["pasted_text"]

        segments = _render_long_reference_split_controls(
            long_title,
            uploaded_files,
            pasted_text,
            max_chars,
            long_source_type,
            state_scope,
        )
        if not segments:
            return

        preview_state = _render_long_reference_segment_preview(
            project_name,
            uploaded_files,
            pasted_text,
            segments,
            state_scope,
        )
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
            "uploaded_files": uploaded_files,
            "parsed_documents": source_inputs.get("parsed_documents", []),
            "story_id": current_story_id,
            "source_file_name": source_file_name,
            "content_fingerprint": content_fingerprint,
            "source_content_hash": hashlib.sha256(pasted_text.encode("utf-8")).hexdigest(),
            "pasted_text": pasted_text,
            "segments": segments,
            "state_scope": state_scope,
        }

        bound_batch_id = str(
            st.session_state.get(_long_reference_key("long_reference_batch_id", state_scope)) or ""
        )
        if bound_batch_id and load_long_reference_batch(project_name, bound_batch_id):
            if render_batch_write_guard(
                project_name,
                bound_batch_id,
                widget_scope="importer",
            ):
                return

        extraction_options = _render_long_reference_quick_processing(
            project_name,
            state_scope,
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
            state_scope,
            batch_context,
            selected_indices,
            shared_categories,
            shared_extraction_mode,
            shared_custom_instructions,
        )
