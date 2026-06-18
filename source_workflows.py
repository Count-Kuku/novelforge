import hashlib
import json
import re
from datetime import datetime, timezone

from extraction_presets import (
    KNOWLEDGE_CONSOLIDATION_MODE_LABELS,
    KNOWLEDGE_EXTRACTION_EXPERT_PRESETS,
)
from knowledge_quality import (
    build_pending_issue_map,
    build_pending_knowledge_quality_issues,
    details_conflicts,
    fact_conflicts,
    merge_list_values,
    normalize_knowledge_match_name,
)
from knowledge_workflows import (
    evaluate_pending_auto_review_decision,
    safe_confidence,
    summarize_item_evidence,
)
from memory import (
    append_auto_review_run,
    confirm_pending_knowledge_items_with_records,
    discard_pending_knowledge_items,
    list_long_reference_batches,
    list_retrieval_source_files,
    load_auto_review_policy,
    load_character_entities,
    load_entity_aliases,
    load_extraction_plan_templates,
    load_knowledge_base,
    load_pending_knowledge_items,
    load_setting_entities,
    queue_pending_knowledge_items,
    retrieval_sources_path,
    save_extraction_plan_templates,
    save_long_reference_batch,
)
from retrieval import (
    build_structured_external_source_payload,
    ingest_external_source_file,
    rebuild_retrieval_assets,
)
from schemas import KNOWLEDGE_CATEGORY_LABELS, label_knowledge_category
from skills import consolidate_extracted_knowledge, extract_reference_knowledge


SCOPE_LABELS = {
    "project": "项目资料",
    "canon": "原作资料",
    "reference": "参考资料",
}

AUTHORITY_LABELS = {
    "project": "项目设定",
    "official": "官方资料",
    "curated": "人工整理",
    "community": "社区资料",
    "unknown": "未标明",
}

DEFAULT_WORLDLINE_ID = "main"
DEFAULT_WORLDLINE_LABEL = "本项目主线"

CHAPTER_TITLE_PATTERN = re.compile(
    r"^\s*(?:第\s*[0-9零一二三四五六七八九十百千万两〇]+\s*[章节卷回部篇]|Chapter\s+\d+|CHAPTER\s+\d+|番外|楔子|序章|终章).*$"
)


def label_scope(value: str) -> str:
    return SCOPE_LABELS.get(str(value or ""), str(value or "未知范围"))


def label_authority(value: str) -> str:
    return AUTHORITY_LABELS.get(str(value or ""), str(value or "未标明"))


def summarize_long_reference_resume_state(segments: list[dict]) -> dict:
    pending_import_indices = []
    pending_extract_indices = []
    imported_not_extracted_indices = []
    failed_indices = []
    completed_indices = []
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        import_status = str(segment.get("import_status") or "pending")
        extract_status = str(segment.get("extract_status") or "pending")
        if import_status != "imported":
            pending_import_indices.append(index)
        if extract_status in {"pending", ""}:
            pending_extract_indices.append(index)
            if import_status == "imported":
                imported_not_extracted_indices.append(index)
        if extract_status == "failed":
            failed_indices.append(index)
        if extract_status in {"queued", "extracted"}:
            completed_indices.append(index)
    unfinished_indices = sorted(set(pending_import_indices + pending_extract_indices + failed_indices))
    return {
        "pending_import_indices": pending_import_indices,
        "pending_extract_indices": pending_extract_indices,
        "imported_not_extracted_indices": imported_not_extracted_indices,
        "failed_indices": failed_indices,
        "completed_indices": completed_indices,
        "unfinished_indices": unfinished_indices,
    }


def format_knowledge_item_for_report(item: dict) -> list[str]:
    lines = [f"### {item.get('name', '未命名')}"]
    if item.get("summary"):
        lines.extend(["", str(item.get("summary", "")).strip()])
    meta_parts = []
    if item.get("scope"):
        meta_parts.append(f"范围：{label_scope(item.get('scope'))}")
    if item.get("authority"):
        meta_parts.append(f"可信度：{label_authority(item.get('authority'))}")
    if item.get("source_title"):
        meta_parts.append(f"来源：{item.get('source_title')}")
    if meta_parts:
        lines.extend(["", "- " + " / ".join(meta_parts)])
    details = item.get("details", {}) if isinstance(item.get("details"), dict) else {}
    for key, value in list(details.items())[:8]:
        if str(value).strip():
            lines.append(f"- {key}：{value}")
    tags = item.get("tags", []) if isinstance(item.get("tags"), list) else []
    if tags:
        lines.append(f"- 标签：{', '.join(str(tag) for tag in tags[:12])}")
    return lines


def build_source_package_report(project_name: str, max_items_per_category: int = 30) -> str:
    knowledge_base = load_knowledge_base(project_name)
    total_items = sum(len(items) for items in knowledge_base.values())
    lines = [
        f"# {project_name} 资料包报告",
        "",
        "## 总览",
        "",
        f"- 已确认结构化知识：{total_items} 条",
    ]
    for category, items in knowledge_base.items():
        lines.append(f"- {label_knowledge_category(category)}：{len(items)} 条")

    missing_categories = [label_knowledge_category(category) for category, items in knowledge_base.items() if not items]
    if missing_categories:
        lines.extend(["", "## 资料缺口", ""])
        lines.append("以下分类当前没有已确认知识，后续可以补充资料或重新提取：")
        lines.extend([f"- {item}" for item in missing_categories])

    for category, items in knowledge_base.items():
        if not items:
            continue
        lines.extend(["", f"## {label_knowledge_category(category)}", ""])
        shown_items = items[:max_items_per_category]
        for item in shown_items:
            lines.extend(format_knowledge_item_for_report(item))
            lines.append("")
        if len(items) > max_items_per_category:
            lines.append(f"> 当前分类仅列出前 {max_items_per_category} 条，共 {len(items)} 条。")

    constraints = knowledge_base.get("constraints", [])
    style_items = knowledge_base.get("writing_style", []) + knowledge_base.get("dialogue_style", []) + knowledge_base.get("narrative_techniques", [])
    if constraints or style_items:
        lines.extend(["", "## 同人写作注意事项", ""])
        for item in constraints[:20]:
            lines.append(f"- 硬性约束：{item.get('name', '未命名')}。{item.get('summary', '')}")
        for item in style_items[:20]:
            lines.append(f"- 风格参考：{item.get('name', '未命名')}。{item.get('summary', '')}")

    lines.extend([
        "",
        "## 后续整理建议",
        "",
        "- 如果角色、能力或地点存在重复条目，先在“结构化知识整理”中合并。",
        "- 如果关键分类为空，回到“长篇资料批次管理”继续提取对应分类。",
        "- 如果资料来自不同版本或存在冲突，优先在“检索中心”做冲突裁决。",
    ])
    return "\n".join(lines).strip() + "\n"


def decode_uploaded_text(uploaded_file) -> str:
    if uploaded_file is None:
        return ""
    data = uploaded_file.getvalue()
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            text = data.decode(encoding)
            if text.strip("\ufeff\x00\r\n\t "):
                return text.replace("\x00", "")
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def normalize_text_for_fingerprint(text: str) -> str:
    return re.sub(r"\s+", "\n", str(text or "").strip())


def calculate_text_fingerprint(text: str) -> str:
    normalized = normalize_text_for_fingerprint(text)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def find_matching_long_reference_batches(
    project_name: str,
    *,
    fingerprint: str,
    source_file_name: str,
    char_count: int,
    segment_count: int,
) -> list[dict]:
    matches = []
    for batch in list_long_reference_batches(project_name):
        score = 0
        reasons = []
        if fingerprint and batch.get("content_fingerprint") == fingerprint:
            score += 100
            reasons.append("内容指纹完全一致")
        if source_file_name and batch.get("source_file_name") == source_file_name:
            score += 20
            reasons.append("文件名一致")
        batch_char_count = int(batch.get("content_char_count") or 0)
        if char_count and batch_char_count and abs(batch_char_count - char_count) <= max(20, int(char_count * 0.01)):
            score += 20
            reasons.append("总字数接近")
        batch_segment_count = int(batch.get("summary", {}).get("segment_count") or 0)
        if segment_count and batch_segment_count == segment_count:
            score += 10
            reasons.append("切分片段数一致")
        if score >= 40:
            item = dict(batch)
            item["match_score"] = score
            item["match_reasons"] = reasons
            matches.append(item)
    return sorted(matches, key=lambda item: item.get("match_score", 0), reverse=True)


def split_long_reference_text(source_title: str, raw_text: str, max_chars: int = 6000) -> list[dict]:
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    lines = text.splitlines()
    chapter_starts = [
        index for index, line in enumerate(lines)
        if CHAPTER_TITLE_PATTERN.match(line.strip())
    ]

    segments: list[dict] = []
    if chapter_starts:
        if chapter_starts[0] > 0:
            preface = "\n".join(lines[:chapter_starts[0]]).strip()
            if preface:
                segments.append({
                    "title": f"{source_title} 序言/简介",
                    "content": preface,
                    "split_method": "章节标题",
                    "chapter_index": 0,
                    "char_count": len(preface),
                })
        for item_index, start in enumerate(chapter_starts):
            end = chapter_starts[item_index + 1] if item_index + 1 < len(chapter_starts) else len(lines)
            title = lines[start].strip() or f"{source_title} 第 {item_index + 1} 段"
            content = "\n".join(lines[start:end]).strip()
            if content:
                segments.append({
                    "title": title,
                    "content": content,
                    "split_method": "章节标题",
                    "chapter_index": item_index + 1,
                    "char_count": len(content),
                })

    if not segments:
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n+", text) if item.strip()]
        current: list[str] = []
        current_length = 0
        for paragraph in paragraphs or [text]:
            paragraph_length = len(paragraph)
            if current and current_length + paragraph_length + 2 > max_chars:
                content = "\n\n".join(current).strip()
                segments.append({
                    "title": f"{source_title} 片段 {len(segments) + 1:03d}",
                    "content": content,
                    "split_method": "字数切分",
                    "chapter_index": len(segments) + 1,
                    "char_count": len(content),
                })
                current = []
                current_length = 0
            if paragraph_length > max_chars:
                for start in range(0, paragraph_length, max_chars):
                    piece = paragraph[start:start + max_chars].strip()
                    if piece:
                        segments.append({
                            "title": f"{source_title} 片段 {len(segments) + 1:03d}",
                            "content": piece,
                            "split_method": "字数切分",
                            "chapter_index": len(segments) + 1,
                            "char_count": len(piece),
                        })
                continue
            current.append(paragraph)
            current_length += paragraph_length + 2
        if current:
            content = "\n\n".join(current).strip()
            segments.append({
                "title": f"{source_title} 片段 {len(segments) + 1:03d}",
                "content": content,
                "split_method": "字数切分",
                "chapter_index": len(segments) + 1,
                "char_count": len(content),
            })

    normalized = []
    for index, segment in enumerate(segments, start=1):
        item = dict(segment)
        item["index"] = index
        item["title"] = item.get("title") or f"{source_title} 片段 {index:03d}"
        item["char_count"] = len(item.get("content", ""))
        normalized.append(item)
    return normalized


def build_long_reference_source_name(base_title: str, segment: dict, fallback_order: int) -> str:
    short_title = re.sub(r"\s+", "_", str(segment.get("title", "segment")))[:40]
    return f"{base_title}_{int(segment.get('index', fallback_order)):04d}_{short_title}"


def import_long_reference_segments(
    project_name: str,
    batch: dict,
    segment_indices: list[int],
) -> tuple[dict, int]:
    imported = 0
    segments = batch.get("segments", [])
    base_title = str(batch.get("title") or "长篇资料")
    total_selected = len(segment_indices)
    for order, index in enumerate(segment_indices, start=1):
        if index < 0 or index >= len(segments):
            continue
        segment = segments[index]
        if segment.get("import_status") == "imported":
            continue
        payload = build_structured_external_source_payload(
            source_type=batch.get("source_type", "external_source"),
            scope=batch.get("scope", "reference"),
            title=segment.get("title", f"{base_title} 片段 {order:03d}"),
            summary=f"长篇资料片段 {segment.get('index')} / 共 {len(segments)} 段 / 字符数 {segment.get('char_count')}",
            content=segment.get("content", ""),
            tags=["长篇资料", "自动切分"],
            metadata={
                "authority": batch.get("authority", "curated"),
                "source_origin": batch.get("source_origin", ""),
                "long_reference": True,
                "batch_id": batch.get("batch_id", ""),
                "part_index": segment.get("index"),
                "part_count": len(segments),
                "split_method": segment.get("split_method"),
                "selected_order": order,
                "selected_count": total_selected,
            },
        )
        source_name = build_long_reference_source_name(base_title, segment, order)
        saved_source_name = ingest_external_source_file(
            project_name,
            source_name,
            json.dumps(payload, ensure_ascii=False, indent=2),
            overwrite=False,
        )
        segment["import_status"] = "imported"
        segment["imported_source_name"] = saved_source_name
        segment["import_error"] = ""
        imported += 1
    if imported:
        batch = save_long_reference_batch(project_name, batch)
        rebuild_retrieval_assets(project_name, build_vectors=True)
    return batch, imported


def import_organized_reference_entries(
    project_name: str,
    organized_result: dict,
    *,
    scope: str,
    authority: str,
    origin: str = "",
) -> int:
    entries = organized_result.get("entries", [])
    imported = 0
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue
        payload = build_structured_external_source_payload(
            source_type=entry.get("source_type", "external_source"),
            scope=scope,
            title=entry.get("title", f"entry_{index}"),
            summary=entry.get("summary", ""),
            content=entry.get("content", ""),
            tags=entry.get("tags", []),
            metadata={
                "authority": authority,
                "source_origin": origin,
                "organized_from_reference": True,
            },
            extra_fields=entry.get("extra_fields", {}),
        )
        entry_name = f"{organized_result.get('source_title', 'reference')}_{index:02d}"
        ingest_external_source_file(project_name, entry_name, json.dumps(payload, ensure_ascii=False, indent=2), overwrite=False)
        imported += 1
    if imported:
        rebuild_retrieval_assets(project_name, build_vectors=True)
    return imported


def save_manual_retrieval_source_card(
    project_name: str,
    *,
    source_name: str,
    source_type: str,
    scope: str,
    title: str,
    summary: str,
    content: str,
    tags: list[str],
    authority: str,
    origin: str = "",
) -> None:
    payload = build_structured_external_source_payload(
        source_type=source_type,
        scope=scope,
        title=title.strip() or source_name.strip(),
        summary=summary,
        content=content,
        tags=tags,
        metadata={
            "added_from_ui": True,
            "template": source_type,
            "authority": authority,
            "source_origin": origin.strip(),
        },
    )
    ingest_external_source_file(project_name, source_name, json.dumps(payload, ensure_ascii=False, indent=2), overwrite=False)
    rebuild_retrieval_assets(project_name, build_vectors=True)


def extract_pasted_reference_to_pending(
    project_name: str,
    *,
    title: str,
    text: str,
    enabled_categories: list[str],
    extraction_mode: str,
    custom_instructions: str,
    scope: str,
    authority: str,
    origin: str = "",
    auto_confirm_safe_items: bool = False,
) -> dict:
    before_pending_ids = {str(item.get("pending_id") or "") for item in load_pending_knowledge_items(project_name)}
    result = extract_reference_knowledge(
        project_name,
        title,
        text,
        enabled_categories,
        extraction_mode=extraction_mode,
        custom_instructions=custom_instructions,
    )
    payload = result.get("data", {}).get("knowledge_extraction", {})
    items = payload.get("items", []) if isinstance(payload, dict) else []
    queued_count = queue_pending_knowledge_items(
        project_name,
        items,
        scope=scope,
        authority=authority,
        source_title=payload.get("source_title", "") or title,
        source_origin=origin,
    )
    auto_summary = {}
    if auto_confirm_safe_items:
        after_pending = load_pending_knowledge_items(project_name)
        new_ids = [
            str(item.get("pending_id") or "")
            for item in after_pending
            if str(item.get("pending_id") or "") and str(item.get("pending_id") or "") not in before_pending_ids
        ]
        auto_summary = auto_confirm_pending_items_without_risk(
            project_name,
            new_ids,
            source_type="pasted_source_extraction",
            source_title=title,
            note="粘贴资料自动提取审核",
        )
    return {
        "result": result,
        "payload": payload if isinstance(payload, dict) else {},
        "item_count": len(items),
        "queued_count": queued_count,
        "auto_confirm": auto_summary,
    }


def extract_long_reference_segments_to_queue(
    project_name: str,
    batch: dict,
    segment_indices: list[int],
    enabled_categories: list[str],
    extraction_mode: str = "general",
    custom_instructions: str = "",
    progress_callback=None,
) -> tuple[dict, int, int, list[str]]:
    queued_total = 0
    processed = 0
    failed_titles = []
    segments = batch.get("segments", [])
    target_indices = [
        index for index in segment_indices
        if 0 <= index < len(segments)
    ]
    total_targets = len(target_indices)
    if progress_callback:
        progress_callback({
            "current": 0,
            "total": total_targets or 1,
            "message": "准备提取片段",
        })
    for position, index in enumerate(target_indices, start=1):
        if index < 0 or index >= len(segments):
            continue
        segment = segments[index]
        segment_title = str(segment.get("title") or f"片段 {position:03d}")
        if progress_callback:
            progress_callback({
                "current": position - 1,
                "total": total_targets or 1,
                "message": f"正在提取：{segment_title}",
            })
        try:
            existing_related = get_segment_related_knowledge_items(project_name, segment, include_confirmed=False)["pending"]
            result = extract_reference_knowledge(
                project_name,
                segment.get("title", batch.get("title", "长篇资料")),
                segment.get("content", ""),
                enabled_categories,
                extraction_mode=extraction_mode,
                custom_instructions=custom_instructions,
            )
            payload = result.get("data", {}).get("knowledge_extraction", {})
            items = payload.get("items", []) if isinstance(payload, dict) else []
            enriched_items = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                enriched = dict(item)
                identity_seed = "|".join([
                    str(segment.get("segment_id") or segment.get("title") or ""),
                    extraction_mode,
                    str(enriched.get("category") or ""),
                    str(enriched.get("name") or ""),
                    str(enriched.get("summary") or ""),
                ])
                enriched["pending_id"] = enriched.get("pending_id") or f"pending_reextract_{hashlib.sha1(identity_seed.encode('utf-8')).hexdigest()[:16]}"
                enriched["extraction_mode"] = extraction_mode
                enriched["source_segment_id"] = str(segment.get("segment_id") or "")
                enriched["source_segment_index"] = segment.get("index")
                enriched["source_segment_title"] = str(segment.get("title") or "")
                enriched["version_scope"] = str(enriched.get("version_scope") or ("canon" if batch.get("scope") == "canon" else "project_main"))
                enriched["worldline_id"] = str(enriched.get("worldline_id") or DEFAULT_WORLDLINE_ID)
                enriched["worldline_label"] = str(enriched.get("worldline_label") or DEFAULT_WORLDLINE_LABEL)
                evidence_contexts = locate_evidence_contexts(segment.get("content", ""), enriched.get("evidence", []))
                if evidence_contexts:
                    enriched["evidence_contexts"] = evidence_contexts
                enriched_items.append(enriched)
            comparison = compare_extracted_items(existing_related, enriched_items)
            queued_count = queue_pending_knowledge_items(
                project_name,
                enriched_items,
                scope=batch.get("scope", "reference"),
                authority=batch.get("authority", "curated"),
                source_title=payload.get("source_title", "") or segment.get("title", ""),
                source_origin=batch.get("source_origin", ""),
            )
            segment["extract_status"] = "queued"
            segment["queued_knowledge_count"] = int(segment.get("queued_knowledge_count") or 0) + queued_count
            segment["last_extract_mode"] = extraction_mode
            segment["last_extract_diff"] = comparison
            segment["extract_error"] = ""
            save_long_reference_batch(project_name, batch)
            queued_total += queued_count
            processed += 1
            if progress_callback:
                progress_callback({
                    "current": position,
                    "total": total_targets or 1,
                    "message": f"已完成：{segment_title}，新增 {queued_count} 条",
                })
        except Exception as exc:
            segment["extract_status"] = "failed"
            segment["extract_error"] = str(exc)
            save_long_reference_batch(project_name, batch)
            failed_titles.append(f"{segment.get('title', '未命名片段')}：{exc}")
            if progress_callback:
                progress_callback({
                    "current": position,
                    "total": total_targets or 1,
                    "message": f"提取失败：{segment_title}",
                })
    batch = save_long_reference_batch(project_name, batch)
    if progress_callback:
        progress_callback({
            "current": total_targets or 1,
            "total": total_targets or 1,
            "message": f"提取完成：成功 {processed} 段，失败 {len(failed_titles)} 段",
        })
    return batch, processed, queued_total, failed_titles


def locate_evidence_contexts(raw_text: str, evidence: list) -> list[dict]:
    if not raw_text or not isinstance(evidence, list):
        return []
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n+", raw_text) if paragraph.strip()]
    contexts = []
    for evidence_item in evidence[:8]:
        if isinstance(evidence_item, dict):
            quote = str(evidence_item.get("quote") or evidence_item.get("text") or "").strip()
        else:
            quote = str(evidence_item or "").strip()
        if not quote:
            continue
        quote_short = quote[:80]
        char_index = raw_text.find(quote) if quote in raw_text else raw_text.find(quote_short)
        paragraph_index = None
        paragraph_text = ""
        for index, paragraph in enumerate(paragraphs, start=1):
            if quote in paragraph or quote_short in paragraph:
                paragraph_index = index
                paragraph_text = paragraph
                break
        if char_index >= 0 or paragraph_index:
            start = max(0, char_index - 120) if char_index >= 0 else 0
            end = min(len(raw_text), char_index + len(quote_short) + 120) if char_index >= 0 else 0
            contexts.append({
                "quote": quote[:180],
                "char_index": char_index if char_index >= 0 else None,
                "paragraph_index": paragraph_index,
                "context": (raw_text[start:end] if char_index >= 0 else paragraph_text[:260]).strip(),
            })
    return contexts


def knowledge_identity(item: dict) -> str:
    return "|".join([
        str(item.get("category") or ""),
        normalize_knowledge_match_name(item.get("name", "")),
    ])


def compare_extracted_items(existing_items: list[dict], new_items: list[dict]) -> dict:
    existing_by_key = {
        knowledge_identity(item): item
        for item in existing_items
        if isinstance(item, dict) and knowledge_identity(item).strip("|")
    }
    new_by_key = {
        knowledge_identity(item): item
        for item in new_items
        if isinstance(item, dict) and knowledge_identity(item).strip("|")
    }
    added_keys = [key for key in new_by_key if key not in existing_by_key]
    matched_keys = [key for key in new_by_key if key in existing_by_key]
    missing_keys = [key for key in existing_by_key if key not in new_by_key]
    changed_keys = []
    for key in matched_keys:
        old_summary = normalize_knowledge_match_name(existing_by_key[key].get("summary", ""))
        new_summary = normalize_knowledge_match_name(new_by_key[key].get("summary", ""))
        old_status = str(existing_by_key[key].get("canon_status") or "unknown")
        new_status = str(new_by_key[key].get("canon_status") or "unknown")
        if old_summary and new_summary and old_summary != new_summary:
            changed_keys.append(key)
        elif old_status != new_status and "unknown" not in {old_status, new_status}:
            changed_keys.append(key)

    def compact_diff_item(item: dict) -> dict:
        details = item.get("details", {}) if isinstance(item.get("details", {}), dict) else {}
        return {
            "pending_id": item.get("pending_id", ""),
            "category": item.get("category", ""),
            "category_label": label_knowledge_category(item.get("category", "")),
            "name": item.get("name", "未命名"),
            "summary": item.get("summary", ""),
            "canon_status": item.get("canon_status", "unknown"),
            "confidence": safe_confidence(item.get("confidence", 0.7)),
            "evidence_strength": safe_confidence(item.get("evidence_strength", 0.5)),
            "source_title": item.get("source_title", ""),
            "source_segment_title": item.get("source_segment_title", ""),
            "details": {str(key): details[key] for key in list(details.keys())[:12]},
        }

    def changed_fields(old_item: dict, new_item: dict) -> list[str]:
        fields = []
        if normalize_knowledge_match_name(old_item.get("summary", "")) != normalize_knowledge_match_name(new_item.get("summary", "")):
            fields.append("summary")
        old_status = str(old_item.get("canon_status") or "unknown")
        new_status = str(new_item.get("canon_status") or "unknown")
        if old_status != new_status:
            fields.append("canon_status")
        fields.extend(f"details.{field}" for field in details_conflicts(old_item, new_item)[:8])
        fact_diffs = fact_conflicts(old_item, new_item)
        fields.extend(f"fact.{diff['fact']}" for diff in fact_diffs[:8])
        return merge_list_values([fields])

    def names_for(keys: list[str], source: dict[str, dict]) -> list[str]:
        names = []
        for key in keys[:12]:
            item = source.get(key, {})
            label = f"{label_knowledge_category(item.get('category', ''))}/{item.get('name', '未命名')}"
            names.append(label)
        return names

    return {
        "existing_count": len(existing_items),
        "new_count": len(new_items),
        "added_count": len(added_keys),
        "matched_count": len(matched_keys),
        "missing_count": len(missing_keys),
        "changed_count": len(changed_keys),
        "existing_pending_ids": [str(existing_by_key[key].get("pending_id") or "") for key in missing_keys + changed_keys if existing_by_key.get(key, {}).get("pending_id")],
        "new_pending_ids": [str(new_by_key[key].get("pending_id") or "") for key in added_keys + changed_keys if new_by_key.get(key, {}).get("pending_id")],
        "added": names_for(added_keys, new_by_key),
        "missing": names_for(missing_keys, existing_by_key),
        "changed": names_for(changed_keys, new_by_key),
        "added_items": [compact_diff_item(new_by_key[key]) for key in added_keys[:20]],
        "missing_items": [compact_diff_item(existing_by_key[key]) for key in missing_keys[:20]],
        "changed_items": [
            {
                "key": key,
                "label": f"{label_knowledge_category(new_by_key[key].get('category', ''))}/{new_by_key[key].get('name', '未命名')}",
                "changed_fields": changed_fields(existing_by_key[key], new_by_key[key]),
                "old": compact_diff_item(existing_by_key[key]),
                "new": compact_diff_item(new_by_key[key]),
            }
            for key in changed_keys[:20]
        ],
    }


def run_long_reference_extraction_plan(
    project_name: str,
    batch: dict,
    segment_indices: list[int],
    expert_steps: list[str],
    *,
    max_segments: int = 5,
    reextract_completed: bool = False,
    progress_callback=None,
) -> tuple[dict, dict]:
    segments = batch.get("segments", []) if isinstance(batch.get("segments", []), list) else []
    target_indices = []
    for index in segment_indices:
        if index < 0 or index >= len(segments):
            continue
        if not reextract_completed and segments[index].get("extract_status", "pending") not in {"pending", "", "failed"}:
            continue
        target_indices.append(index)
        if len(target_indices) >= max_segments:
            break

    summary = {
        "plan_steps": expert_steps,
        "segment_indices": target_indices,
        "processed_steps": [],
        "processed_segments": 0,
        "queued_total": 0,
        "failure_count": 0,
        "failures": [],
    }
    if not target_indices or not expert_steps:
        return batch, summary

    planned_steps = []
    for step_key in expert_steps:
        preset = KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.get(step_key)
        if not preset:
            continue
        categories = [category for category in preset.get("categories", []) if category in KNOWLEDGE_CATEGORY_LABELS]
        if not categories:
            continue
        planned_steps.append((step_key, preset, categories))

    total_work = max(1, len(target_indices) * len(planned_steps))
    completed_work = 0
    if progress_callback:
        progress_callback({
            "current": 0,
            "total": total_work,
            "message": f"准备执行 {len(planned_steps)} 个专家步骤",
        })

    current_batch = batch
    for step_key, preset, categories in planned_steps:
        step_label = preset.get("label", step_key)

        def step_progress(event: dict, *, offset=completed_work, label=step_label):
            if not progress_callback or not isinstance(event, dict):
                return
            progress_callback({
                **event,
                "current": min(offset + int(event.get("current") or 0), total_work),
                "total": total_work,
                "message": f"{label} / {event.get('message', '正在提取')}",
            })

        current_batch, processed, queued_total, failures = extract_long_reference_segments_to_queue(
            project_name,
            current_batch,
            target_indices,
            categories,
            extraction_mode=str(preset.get("mode") or "general"),
            progress_callback=step_progress,
        )
        completed_work += len(target_indices)
        step_summary = {
            "step": step_key,
            "label": step_label,
            "mode": preset.get("mode", "general"),
            "categories": categories,
            "processed": processed,
            "queued": queued_total,
            "failures": failures[:10],
        }
        summary["processed_steps"].append(step_summary)
        summary["processed_segments"] += processed
        summary["queued_total"] += queued_total
        summary["failure_count"] += len(failures)
        summary["failures"].extend(failures[:10])
        if progress_callback:
            progress_callback({
                "current": min(completed_work, total_work),
                "total": total_work,
                "message": f"{step_label} 完成",
            })

    if progress_callback:
        progress_callback({
            "current": total_work,
            "total": total_work,
            "message": f"计划完成：累计处理 {summary.get('processed_segments', 0)} 次片段",
        })

    history = current_batch.get("extraction_plan_runs", [])
    if not isinstance(history, list):
        history = []
    history.append(summary)
    current_batch["extraction_plan_runs"] = history[-20:]
    current_batch["last_extraction_plan"] = summary
    current_batch = save_long_reference_batch(project_name, current_batch)
    return current_batch, summary


def make_extraction_plan_template_id(name: str) -> str:
    key = normalize_knowledge_match_name(name)
    digest = hashlib.sha1((key or name or "plan").encode("utf-8")).hexdigest()[:10]
    return f"extract_plan_{digest}"


def upsert_extraction_plan_template(project_name: str, name: str, steps: list[str], notes: str = "") -> dict:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("模板名称不能为空。")
    clean_steps = [step for step in steps if step in KNOWLEDGE_EXTRACTION_EXPERT_PRESETS]
    if not clean_steps:
        raise ValueError("模板至少需要一个有效专家步骤。")
    templates = load_extraction_plan_templates(project_name)
    template_id = make_extraction_plan_template_id(clean_name)
    payload = {
        "id": template_id,
        "name": clean_name,
        "steps": clean_steps,
        "notes": str(notes or "").strip(),
        "status": "active",
    }
    replaced = False
    for index, item in enumerate(templates):
        if str(item.get("id") or "") == template_id:
            templates[index] = {**item, **payload}
            replaced = True
            break
    if not replaced:
        templates.append(payload)
    save_extraction_plan_templates(project_name, templates)
    return payload


def delete_extraction_plan_template(project_name: str, template_id: str) -> bool:
    templates = load_extraction_plan_templates(project_name)
    kept = [item for item in templates if str(item.get("id") or "") != str(template_id or "")]
    if len(kept) == len(templates):
        return False
    save_extraction_plan_templates(project_name, kept)
    return True


def get_batch_pending_knowledge_items(project_name: str, batch: dict) -> list[dict]:
    segment_ids = {
        str(segment.get("segment_id") or "")
        for segment in batch.get("segments", [])
        if isinstance(segment, dict) and segment.get("segment_id")
    }
    segment_titles = {
        str(segment.get("title") or "")
        for segment in batch.get("segments", [])
        if isinstance(segment, dict) and segment.get("title")
    }
    batch_title = str(batch.get("title") or "")
    candidates = []
    for item in load_pending_knowledge_items(project_name):
        if not isinstance(item, dict):
            continue
        item_segment_id = str(item.get("source_segment_id") or "")
        item_segment_title = str(item.get("source_segment_title") or "")
        item_source_title = str(item.get("source_title") or "")
        if item_segment_id and item_segment_id in segment_ids:
            candidates.append(item)
        elif item_segment_title and item_segment_title in segment_titles:
            candidates.append(item)
        elif batch_title and item_source_title == batch_title:
            candidates.append(item)
    return candidates


def build_extraction_coverage_report(project_name: str, batch: dict | None = None) -> dict:
    if batch:
        pending_items = get_batch_pending_knowledge_items(project_name, batch)
        segments = batch.get("segments", []) if isinstance(batch.get("segments", []), list) else []
        title = str(batch.get("title") or "当前批次")
    else:
        pending_items = load_pending_knowledge_items(project_name)
        segments = []
        title = "全部待确认知识"

    category_counts = {category: 0 for category in KNOWLEDGE_CATEGORY_LABELS}
    low_confidence = 0
    low_evidence = 0
    no_evidence = 0
    canon_counts: dict[str, int] = {}
    mode_counts: dict[str, int] = {}
    source_segments = set()

    for item in pending_items:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "")
        if category in category_counts:
            category_counts[category] += 1
        if safe_confidence(item.get("confidence", 0.7)) < 0.55:
            low_confidence += 1
        if safe_confidence(item.get("evidence_strength", 0.5)) < 0.45:
            low_evidence += 1
        if not summarize_item_evidence(item):
            no_evidence += 1
        canon_status = str(item.get("canon_status") or "unknown")
        canon_counts[canon_status] = canon_counts.get(canon_status, 0) + 1
        extraction_mode = str(item.get("extraction_mode") or "general")
        mode_counts[extraction_mode] = mode_counts.get(extraction_mode, 0) + 1
        segment_id = str(item.get("source_segment_id") or "")
        if segment_id:
            source_segments.add(segment_id)

    missing_categories = [category for category, count in category_counts.items() if count == 0]
    weak_categories = [category for category, count in category_counts.items() if 0 < count <= 2]
    extracted_segments = len([
        segment for segment in segments
        if isinstance(segment, dict) and segment.get("extract_status") in {"queued", "extracted"}
    ])
    failed_segments = len([
        segment for segment in segments
        if isinstance(segment, dict) and segment.get("extract_status") == "failed"
    ])
    total_segments = len(segments)
    return {
        "title": title,
        "pending_count": len(pending_items),
        "category_counts": category_counts,
        "missing_categories": missing_categories,
        "weak_categories": weak_categories,
        "low_confidence": low_confidence,
        "low_evidence": low_evidence,
        "no_evidence": no_evidence,
        "canon_counts": canon_counts,
        "mode_counts": mode_counts,
        "total_segments": total_segments,
        "extracted_segments": extracted_segments,
        "failed_segments": failed_segments,
        "covered_source_segments": len(source_segments),
    }


def build_ingestion_health_report(project_name: str) -> dict:
    batches = list_long_reference_batches(project_name)
    pending_items = load_pending_knowledge_items(project_name)
    knowledge = load_knowledge_base(project_name)
    quality_issues = build_pending_knowledge_quality_issues(project_name, pending_items)
    imported_not_extracted = 0
    failed_segments = 0
    total_segments = 0
    extracted_segments = 0
    for batch in batches:
        for segment in batch.get("segments", []):
            if not isinstance(segment, dict):
                continue
            total_segments += 1
            if segment.get("extract_status") in {"queued", "extracted"}:
                extracted_segments += 1
            if segment.get("import_status") == "imported" and segment.get("extract_status", "pending") in {"pending", ""}:
                imported_not_extracted += 1
            if segment.get("extract_status") == "failed":
                failed_segments += 1

    confirmed_counts = {category: len(items) for category, items in knowledge.items()}
    pending_counts = {category: 0 for category in KNOWLEDGE_CATEGORY_LABELS}
    low_evidence = 0
    low_confidence = 0
    no_evidence = 0
    worldline_counts: dict[str, int] = {}
    confirmed_worldline_counts: dict[str, int] = {}
    for item in pending_items:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "")
        if category in pending_counts:
            pending_counts[category] += 1
        if safe_confidence(item.get("evidence_strength", 0.5)) < 0.45:
            low_evidence += 1
        if safe_confidence(item.get("confidence", 0.7)) < 0.55:
            low_confidence += 1
        if not summarize_item_evidence(item):
            no_evidence += 1
        worldline = str(item.get("worldline_label") or item.get("worldline_id") or "未标明")
        worldline_counts[worldline] = worldline_counts.get(worldline, 0) + 1
    for items in knowledge.values():
        for item in items:
            if not isinstance(item, dict):
                continue
            worldline = str(item.get("worldline_label") or item.get("worldline_id") or "未标明")
            confirmed_worldline_counts[worldline] = confirmed_worldline_counts.get(worldline, 0) + 1

    missing_confirmed = [category for category, count in confirmed_counts.items() if count == 0]
    weak_confirmed = [category for category, count in confirmed_counts.items() if 0 < count <= 2]
    high_risk_issues = [issue for issue in quality_issues if issue.get("severity") == "高"]
    score = 100
    score -= min(25, len(missing_confirmed) * 3)
    score -= min(20, failed_segments * 2)
    score -= min(20, imported_not_extracted)
    score -= min(20, len(high_risk_issues) * 2)
    score -= min(15, low_evidence + low_confidence + no_evidence)
    return {
        "score": max(0, score),
        "batch_count": len(batches),
        "total_segments": total_segments,
        "extracted_segments": extracted_segments,
        "imported_not_extracted": imported_not_extracted,
        "failed_segments": failed_segments,
        "pending_count": len(pending_items),
        "confirmed_count": sum(confirmed_counts.values()),
        "missing_confirmed": missing_confirmed,
        "weak_confirmed": weak_confirmed,
        "low_evidence": low_evidence,
        "low_confidence": low_confidence,
        "no_evidence": no_evidence,
        "quality_issue_count": len(quality_issues),
        "high_risk_issue_count": len(high_risk_issues),
        "pending_counts": pending_counts,
        "confirmed_counts": confirmed_counts,
        "worldline_counts": worldline_counts,
        "confirmed_worldline_counts": confirmed_worldline_counts,
        "character_entity_count": len(load_character_entities(project_name)),
        "setting_entity_count": len(load_setting_entities(project_name)),
        "alias_group_count": len(load_entity_aliases(project_name)),
        "extraction_plan_template_count": len(load_extraction_plan_templates(project_name)),
    }


def get_segment_related_knowledge_items(project_name: str, segment: dict, *, include_confirmed: bool = True) -> dict[str, list[dict]]:
    segment_id = str(segment.get("segment_id") or "")
    segment_title = str(segment.get("title") or "")
    related_pending = []
    for item in load_pending_knowledge_items(project_name):
        if not isinstance(item, dict):
            continue
        if segment_id and str(item.get("source_segment_id") or "") == segment_id:
            related_pending.append(item)
        elif segment_title and str(item.get("source_segment_title") or "") == segment_title:
            related_pending.append(item)

    related_confirmed = []
    if include_confirmed:
        for category, items in load_knowledge_base(project_name).items():
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_segment_ids = [str(value) for value in item.get("source_segment_ids", []) if str(value).strip()]
                item_segment_titles = [str(value) for value in item.get("source_segment_titles", []) if str(value).strip()]
                if segment_id and (str(item.get("source_segment_id") or "") == segment_id or segment_id in item_segment_ids):
                    related = dict(item)
                    related["category"] = related.get("category") or category
                    related_confirmed.append(related)
                elif segment_title and (
                    str(item.get("source_segment_title") or "") == segment_title
                    or segment_title in item_segment_titles
                ):
                    related = dict(item)
                    related["category"] = related.get("category") or category
                    related_confirmed.append(related)

    return {"pending": related_pending, "confirmed": related_confirmed}


def summarize_source_knowledge_counts(project_name: str) -> dict[tuple[str, str], dict[str, int]]:
    counts: dict[tuple[str, str], dict[str, int]] = {}

    def add_count(source_title: str, source_origin: str, field: str):
        key = (str(source_title or ""), str(source_origin or ""))
        if not key[0] and not key[1]:
            return
        counts.setdefault(key, {"pending": 0, "confirmed": 0})
        counts[key][field] = counts[key].get(field, 0) + 1

    for item in load_pending_knowledge_items(project_name):
        if isinstance(item, dict):
            add_count(item.get("source_title", ""), item.get("source_origin", ""), "pending")

    for items in load_knowledge_base(project_name).values():
        for item in items:
            if isinstance(item, dict):
                add_count(item.get("source_title", ""), item.get("source_origin", ""), "confirmed")

    return counts


def read_retrieval_source_payload(project_name: str, relative_path: str) -> dict:
    base_path = retrieval_sources_path(project_name).resolve()
    target = (base_path / relative_path).resolve()
    if base_path not in target.parents and target != base_path:
        return {}
    if not target.exists() or not target.is_file():
        return {}
    try:
        raw_text = target.read_text(encoding="utf-8")
    except Exception:
        return {}
    try:
        payload = json.loads(raw_text)
    except Exception:
        return {
            "title": relative_path,
            "content": raw_text,
            "metadata": {},
            "_raw_char_count": len(raw_text),
        }
    if isinstance(payload, dict):
        payload["_raw_char_count"] = len(raw_text)
        return payload
    return {"title": relative_path, "content": raw_text, "metadata": {}, "_raw_char_count": len(raw_text)}


def build_ingestion_source_ledger(project_name: str) -> list[dict]:
    knowledge_counts = summarize_source_knowledge_counts(project_name)
    records: list[dict] = []

    for batch in list_long_reference_batches(project_name):
        summary = batch.get("summary", {})
        key = (str(batch.get("title") or ""), str(batch.get("source_origin") or ""))
        source_counts = knowledge_counts.get(key, {})
        records.append({
            "id": f"batch:{batch.get('batch_id', '')}",
            "kind": "long_batch",
            "kind_label": "长篇批次",
            "title": batch.get("title", "未命名批次"),
            "scope": batch.get("scope", "reference"),
            "authority": batch.get("authority", "curated"),
            "source_type": batch.get("source_type", "external_source"),
            "source_origin": batch.get("source_origin", ""),
            "updated_at": batch.get("updated_at", ""),
            "segment_count": int(summary.get("segment_count") or 0),
            "imported_count": int(summary.get("imported_count") or 0),
            "extracted_count": int(summary.get("extract_queued_count") or 0),
            "failed_count": int(summary.get("extract_failed_count") or 0),
            "pending_count": int(source_counts.get("pending") or 0),
            "confirmed_count": int(source_counts.get("confirmed") or 0),
            "batch_id": batch.get("batch_id", ""),
            "file_name": batch.get("file_name", ""),
        })

    for relative_path in list_retrieval_source_files(project_name):
        payload = read_retrieval_source_payload(project_name, relative_path)
        metadata = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
        title = str(payload.get("title") or relative_path)
        origin = str(metadata.get("source_origin") or payload.get("source_origin") or "")
        key = (title, origin)
        source_counts = knowledge_counts.get(key, {})
        records.append({
            "id": f"source:{relative_path}",
            "kind": "retrieval_source",
            "kind_label": "检索资料",
            "title": title,
            "scope": payload.get("scope", metadata.get("scope", "reference")),
            "authority": metadata.get("authority", payload.get("authority", "unknown")),
            "source_type": payload.get("source_type", metadata.get("template", "external_source")),
            "source_origin": origin,
            "updated_at": "",
            "segment_count": 1,
            "imported_count": 1,
            "extracted_count": 0,
            "failed_count": 0,
            "pending_count": int(source_counts.get("pending") or 0),
            "confirmed_count": int(source_counts.get("confirmed") or 0),
            "relative_path": relative_path,
            "char_count": int(payload.get("_raw_char_count") or len(str(payload.get("content") or ""))),
        })

    existing_ids = {record["id"] for record in records}
    for (source_title, source_origin), source_counts in knowledge_counts.items():
        synthetic_id = f"knowledge:{source_title}:{source_origin}"
        if synthetic_id in existing_ids:
            continue
        if any(record.get("title") == source_title and record.get("source_origin") == source_origin for record in records):
            continue
        records.append({
            "id": synthetic_id,
            "kind": "knowledge_only",
            "kind_label": "知识来源",
            "title": source_title or source_origin or "未命名来源",
            "scope": "",
            "authority": "",
            "source_type": "knowledge",
            "source_origin": source_origin,
            "updated_at": "",
            "segment_count": 0,
            "imported_count": 0,
            "extracted_count": 0,
            "failed_count": 0,
            "pending_count": int(source_counts.get("pending") or 0),
            "confirmed_count": int(source_counts.get("confirmed") or 0),
        })

    return sorted(records, key=lambda item: (item.get("updated_at") or "", item.get("title") or ""), reverse=True)


def enrich_consolidated_knowledge_items(items: list[dict], source_items: list[dict], consolidation_mode: str) -> list[dict]:
    source_pending_ids = [str(item.get("pending_id") or "") for item in source_items if item.get("pending_id")]
    source_segment_ids = merge_list_values([item.get("source_segment_ids", []) for item in source_items] + [[
        item.get("source_segment_id", "") for item in source_items if item.get("source_segment_id")
    ]])
    source_segment_titles = merge_list_values([item.get("source_segment_titles", []) for item in source_items] + [[
        item.get("source_segment_title", "") for item in source_items if item.get("source_segment_title")
    ]])
    enriched_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        enriched = dict(item)
        enriched["extraction_mode"] = str(enriched.get("extraction_mode") or f"consolidated:{consolidation_mode}")
        if not enriched.get("merged_from_pending_ids"):
            enriched["merged_from_pending_ids"] = source_pending_ids
        if not enriched.get("source_segment_ids"):
            enriched["source_segment_ids"] = source_segment_ids
        if not enriched.get("source_segment_titles"):
            enriched["source_segment_titles"] = source_segment_titles
        tags = merge_list_values([enriched.get("tags", []), [f"整理:{KNOWLEDGE_CONSOLIDATION_MODE_LABELS.get(consolidation_mode, consolidation_mode)}"]])
        enriched["tags"] = tags
        enriched_items.append(enriched)
    return enriched_items


def consolidate_batch_pending_items(
    project_name: str,
    batch: dict,
    *,
    categories: list[str],
    consolidation_mode: str,
    limit: int,
) -> dict:
    batch_pending_items = get_batch_pending_knowledge_items(project_name, batch)
    target_items = [
        item for item in batch_pending_items
        if not categories or item.get("category") in categories
    ][: int(limit)]
    if len(target_items) < 2:
        return {
            "success": False,
            "message": "当前批次中可整理的待确认知识不足 2 条。",
            "source_count": len(target_items),
            "queued_count": 0,
            "result": {},
        }

    result = consolidate_extracted_knowledge(
        project_name,
        batch.get("title", "长篇资料批次"),
        target_items,
        enabled_categories=categories,
        consolidation_mode=consolidation_mode,
    )
    payload = result.get("data", {}).get("knowledge_extraction", {})
    consolidated_items = payload.get("items", []) if isinstance(payload, dict) else []
    enriched_items = enrich_consolidated_knowledge_items(consolidated_items, target_items, consolidation_mode)
    if not enriched_items:
        return {
            "success": False,
            "message": "整理没有生成可保存的知识条目。",
            "source_count": len(target_items),
            "queued_count": 0,
            "result": result,
        }

    target_ids = [str(item.get("pending_id", "")) for item in target_items if item.get("pending_id")]
    discard_pending_knowledge_items(project_name, target_ids)
    queued_count = queue_pending_knowledge_items(
        project_name,
        enriched_items,
        scope=target_items[0].get("scope", batch.get("scope", "reference")),
        authority=target_items[0].get("authority", batch.get("authority", "curated")),
        source_title=batch.get("title", payload.get("source_title", "")),
        source_origin=batch.get("source_origin", ""),
    )
    return {
        "success": True,
        "message": f"已整理 {len(target_items)} 条散知识，生成 {queued_count} 条待确认知识。",
        "source_count": len(target_items),
        "queued_count": queued_count,
        "result": result,
    }


def auto_confirm_pending_items_without_risk(
    project_name: str,
    candidate_ids: list[str],
    *,
    source_type: str = "",
    source_title: str = "",
    batch_id: str = "",
    note: str = "",
) -> dict:
    id_set = {str(item) for item in candidate_ids if item}
    if not id_set:
        return {"confirmed_ids": [], "blocked_ids": [], "blocked_reasons": {}, "run_id": ""}
    pending_items = load_pending_knowledge_items(project_name)
    policy = load_auto_review_policy(project_name)
    candidate_items = [item for item in pending_items if str(item.get("pending_id") or "") in id_set]
    quality_issues = build_pending_knowledge_quality_issues(project_name, pending_items)
    issue_map = build_pending_issue_map(quality_issues)
    confirmed_ids = []
    blocked_ids = []
    blocked_reasons = {}
    decisions = []
    for item in candidate_items:
        pending_id = str(item.get("pending_id") or "")
        decision = evaluate_pending_auto_review_decision(item, issue_map, policy)
        decision.update({
            "category": item.get("category", ""),
            "name": item.get("name", ""),
            "source_title": item.get("source_title", ""),
            "source_origin": item.get("source_origin", ""),
        })
        decisions.append(decision)
        if decision.get("decision") != "confirm":
            blocked_ids.append(pending_id)
            blocked_reasons[pending_id] = decision.get("reason", "证据/置信不足")
        else:
            confirmed_ids.append(pending_id)

    id_digest = hashlib.sha1("|".join(sorted(id_set)).encode("utf-8")).hexdigest()[:10]
    run_id = f"auto_review_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{id_digest}"
    confirm_result = confirm_pending_knowledge_items_with_records(
        project_name,
        confirmed_ids,
        confirmation_metadata={
            "auto_review_run_id": run_id,
            "auto_reviewed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    saved_count = int(confirm_result.get("saved_count", 0))
    run = append_auto_review_run(project_name, {
        "run_id": run_id,
        "source_type": source_type or "auto_confirm",
        "source_title": source_title,
        "batch_id": batch_id,
        "note": note,
        "candidate_ids": sorted(id_set),
        "confirmed_ids": confirmed_ids,
        "blocked_ids": blocked_ids,
        "blocked_reasons": blocked_reasons,
        "decisions": decisions,
        "confirmed_records": confirm_result.get("confirmed_records", []),
        "pending_snapshots": confirm_result.get("pending_snapshots", []),
        "saved_count": saved_count,
        "policy": policy,
    })
    if saved_count:
        rebuild_retrieval_assets(project_name, build_vectors=True)
    return {
        "confirmed_ids": confirmed_ids,
        "blocked_ids": blocked_ids,
        "blocked_reasons": blocked_reasons,
        "saved_count": saved_count,
        "run_id": run.get("run_id", run_id),
        "decisions": decisions,
    }


def append_long_reference_quick_run(batch: dict, summary: dict) -> dict:
    history = batch.get("quick_process_runs", [])
    if not isinstance(history, list):
        history = []
    run = {
        **summary,
        "run_at": datetime.now(timezone.utc).isoformat(),
    }
    history.append(run)
    batch["quick_process_runs"] = history[-20:]
    batch["last_quick_process_run"] = run
    return batch


def run_long_reference_quick_process(
    project_name: str,
    batch: dict,
    segment_indices: list[int],
    *,
    enabled_categories: list[str],
    extraction_mode: str,
    extract_limit: int,
    import_to_index: bool,
    consolidate_after_extract: bool,
    auto_confirm_safe_items: bool,
    custom_instructions: str = "",
    progress_callback=None,
) -> tuple[dict, dict]:
    selected_indices = list(segment_indices)
    extract_indices = selected_indices[: int(extract_limit)]
    before_pending_ids = {str(item.get("pending_id") or "") for item in load_pending_knowledge_items(project_name)}
    imported = 0
    processed = 0
    queued_total = 0
    failed_titles: list[str] = []
    consolidation_summary: dict = {}
    auto_confirm_summary: dict = {}

    progress_total = max(1, len(extract_indices))
    if progress_callback:
        progress_callback({
            "current": 0,
            "total": progress_total,
            "message": "准备自动处理",
        })
    if import_to_index:
        if progress_callback:
            progress_callback({
                "current": 0,
                "total": progress_total,
                "message": "正在导入资料索引",
            })
        batch, imported = import_long_reference_segments(project_name, batch, selected_indices)
    if extract_indices:
        batch, processed, queued_total, failed_titles = extract_long_reference_segments_to_queue(
            project_name,
            batch,
            extract_indices,
            enabled_categories,
            extraction_mode=extraction_mode,
            custom_instructions=custom_instructions,
            progress_callback=progress_callback,
        )
    if consolidate_after_extract and queued_total:
        if progress_callback:
            progress_callback({
                "current": progress_total,
                "total": progress_total,
                "message": "正在整理散知识",
            })
        consolidation_summary = consolidate_batch_pending_items(
            project_name,
            batch,
            categories=enabled_categories,
            consolidation_mode="balanced",
            limit=max(20, min(120, queued_total)),
        )

    after_pending_items = load_pending_knowledge_items(project_name)
    new_pending_ids = [
        str(item.get("pending_id") or "")
        for item in after_pending_items
        if str(item.get("pending_id") or "") and str(item.get("pending_id") or "") not in before_pending_ids
    ]
    if auto_confirm_safe_items:
        if progress_callback:
            progress_callback({
                "current": progress_total,
                "total": progress_total,
                "message": "正在自动审核低风险知识",
            })
        auto_confirm_summary = auto_confirm_pending_items_without_risk(
            project_name,
            new_pending_ids,
            source_type="long_reference_quick_process",
            source_title=batch.get("title", ""),
            batch_id=batch.get("batch_id", ""),
            note="长篇资料自动处理审核",
        )

    summary = {
        "selected_segment_count": len(selected_indices),
        "extract_segment_count": len(extract_indices),
        "imported_count": imported,
        "processed_count": processed,
        "queued_count": queued_total,
        "new_pending_count": len(new_pending_ids),
        "auto_confirmed_count": len(auto_confirm_summary.get("confirmed_ids", [])) if auto_confirm_summary else 0,
        "blocked_count": len(auto_confirm_summary.get("blocked_ids", [])) if auto_confirm_summary else len(new_pending_ids),
        "failed_titles": failed_titles,
        "extraction_mode": extraction_mode,
        "categories": enabled_categories,
        "import_to_index": import_to_index,
        "consolidate_after_extract": consolidate_after_extract,
        "auto_confirm_safe_items": auto_confirm_safe_items,
        "custom_instructions": custom_instructions,
        "auto_confirm": auto_confirm_summary,
        "consolidation": consolidation_summary,
    }
    batch = append_long_reference_quick_run(batch, summary)
    batch = save_long_reference_batch(project_name, batch)
    if progress_callback:
        progress_callback({
            "current": progress_total,
            "total": progress_total,
            "message": f"自动处理完成：提取 {processed} 段，新增候选 {len(new_pending_ids)} 条",
        })
    return batch, summary
