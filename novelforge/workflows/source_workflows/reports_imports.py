import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from uuid import uuid4

from novelforge.domain.extraction_presets import (
    KNOWLEDGE_CONSOLIDATION_MODE_LABELS,
    KNOWLEDGE_EXTRACTION_EXPERT_PRESETS,
)
from novelforge.domain.knowledge_quality import (
    build_pending_issue_map,
    build_pending_knowledge_quality_issues,
    details_conflicts,
    fact_conflicts,
    merge_list_values,
    normalize_knowledge_match_name,
)
from novelforge.domain.knowledge_workflows import (
    evaluate_pending_auto_review_decision,
    safe_confidence,
    summarize_item_evidence,
)
from novelforge.domain.reference_chunking import split_reference_text
from novelforge.domain.ingestion_workbench import (
    build_ingestion_workbench_summary,
    summarize_long_reference_resume_state,
)
from novelforge.services.memory import (
    confirm_pending_knowledge_items_with_records,
    list_long_reference_batches,
    list_source_ingestion_tasks,
    list_retrieval_source_files,
    load_auto_review_policy,
    load_entity_aliases,
    load_extraction_plan_templates,
    load_knowledge_base,
    load_pending_knowledge_items,
    load_source_revisions,
    load_knowledge_storage_health,
    queue_pending_knowledge_items,
    retrieval_sources_path,
    save_extraction_plan_templates,
    save_long_reference_batch,
)
from novelforge.services.retrieval import (
    build_structured_external_source_payload,
    ingest_external_source_file,
    rebuild_retrieval_assets,
)
from novelforge.core.schemas import KNOWLEDGE_CATEGORY_LABELS, label_knowledge_category
from novelforge.workflows.skills import consolidate_extracted_knowledge, extract_reference_knowledge, build_pending_knowledge_from_reference_extraction, recall_missed_knowledge

LOGGER = logging.getLogger("novelforge.source_workflows")

import novelforge.workflows.source_workflows as _sw

"""Source package reports and long-reference import pipelines."""

def format_knowledge_item_for_report(item: dict) -> list[str]:
    lines = [f"### {item.get('name', '未命名')}"]
    if item.get("summary"):
        lines.extend(["", str(item.get("summary", "")).strip()])
    meta_parts = []
    if item.get("scope"):
        meta_parts.append(f"范围：{_sw.label_scope(item.get('scope'))}")
    if item.get("authority"):
        meta_parts.append(f"可信度：{_sw.label_authority(item.get('authority'))}")
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

    constraints = knowledge_base.get("world_rules", [])
    style_items = knowledge_base.get("writing_style", []) + knowledge_base.get("dialogue_style", []) + knowledge_base.get("narrative_techniques", [])
    if constraints or style_items:
        lines.extend(["", "## 同人写作注意事项", ""])
        for item in constraints[:20]:
            lines.append(f"- 世界规则：{item.get('name', '未命名')}。{item.get('summary', '')}")
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


def split_long_reference_text(
    source_title: str,
    raw_text: str,
    max_chars: int = 6000,
    *,
    source_type: str = "external_source",
) -> list[dict]:
    """兼容旧调用的结构感知切分入口。

    新实现会优先保留 Markdown 层级、章节标题和场景分隔，并为每个片段记录
    原文字符锚点、内容哈希及前后片段关系，供证据定位和父子检索使用。
    """

    return split_reference_text(
        source_title,
        raw_text,
        max_chars=max_chars,
        source_type=source_type,
    )


def build_long_reference_source_name(base_title: str, segment: dict, fallback_order: int, batch_id: str = "") -> str:
    short_title = re.sub(r"\s+", "_", str(segment.get("title", "segment")))[:40]
    batch_token = re.sub(r"[^A-Za-z0-9_-]+", "_", str(batch_id or "")).strip("_")[:20]
    batch_prefix = f"{batch_token}_" if batch_token else ""
    return f"{base_title}_{batch_prefix}{int(segment.get('index', fallback_order)):04d}_{short_title}"


def import_long_reference_segments(
    project_name: str,
    batch: dict,
    segment_indices: list[int],
    progress_callback=None,
    *,
    task_id: str = "",
    worker_id: str = "",
) -> tuple[dict, int]:
    imported = 0
    segments = batch.get("segments", [])
    base_title = str(batch.get("title") or "长篇资料")
    target_indices = [index for index in segment_indices if 0 <= index < len(segments)]
    total_selected = len(target_indices)
    for order, index in enumerate(target_indices, start=1):
        segment = segments[index]
        segment_title = str(segment.get("title") or f"{base_title} 片段 {order:03d}")
        if progress_callback:
            progress_callback({
                "current": order - 1,
                "total": total_selected or 1,
                "message": f"正在导入：{segment_title}",
                "stage": "import",
                "stage_status": "running",
                "segment_index": index,
                "segment_id": str(segment.get("segment_id") or ""),
            })
        if segment.get("import_status") == "imported":
            if progress_callback:
                progress_callback({
                    "current": order,
                    "total": total_selected or 1,
                    "message": f"已跳过已导入片段：{segment_title}",
                    "stage": "import",
                    "segment_index": index,
                    "segment_id": str(segment.get("segment_id") or ""),
                })
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
                "source_id": batch.get("source_id", f"long_batch_{batch.get('batch_id', '')}"),
                "source_revision_id": batch.get("source_revision_id", ""),
                "segment_id": segment.get("segment_id", ""),
                "story_id": batch.get("story_id", "default"),
                "heading_path": segment.get("heading_path", []),
                "content_kind": segment.get("content_kind", "section"),
                "start_offset": segment.get("start_offset"),
                "end_offset": segment.get("end_offset"),
                "part_index": segment.get("index"),
                "part_count": len(segments),
                "split_method": segment.get("split_method"),
                "selected_order": order,
                "selected_count": total_selected,
            },
        )
        source_name = build_long_reference_source_name(base_title, segment, order, str(batch.get("batch_id") or ""))
        try:
            saved_source_name = ingest_external_source_file(
                project_name,
                source_name,
                json.dumps(payload, ensure_ascii=False, indent=2),
                # batch/segment-derived names are deterministic; retries must
                # update the same source rather than create _02 duplicates.
                overwrite=True,
            )
            segment["import_status"] = "imported"
            segment["imported_source_name"] = saved_source_name
            segment["import_error"] = ""
            imported += 1
        except Exception as exc:
            segment["import_status"] = "failed"
            segment["import_error"] = str(exc)
        # Persist progress after every segment so a crash or page reload can
        # resume exactly where the import stopped.
        batch = save_long_reference_batch(
            project_name,
            batch,
            task_id=task_id,
            worker_id=worker_id,
        )
        if progress_callback:
            progress_callback({
                "current": order,
                "total": total_selected or 1,
                "message": (
                    f"已导入：{segment_title}"
                    if segment.get("import_status") == "imported"
                    else f"导入失败：{segment_title}"
                ),
                "stage": "import",
                "segment_index": index,
                "segment_id": str(segment.get("segment_id") or ""),
            })
    # Rebuild even when every selected source had already been imported. A
    # previous attempt may have committed source files and crashed during the
    # derived-index rebuild; retries must repair that state.
    if target_indices:
        if progress_callback:
            progress_callback({
                "current": total_selected,
                "total": total_selected or 1,
                "message": "正在重建资料索引",
                "stage": "import",
            })
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
    stream_callback=None,
    story_id: str = "default",
) -> dict:
    before_pending_ids = {str(item.get("pending_id") or "") for item in load_pending_knowledge_items(project_name)}
    result = extract_reference_knowledge(
        project_name,
        title,
        text,
        enabled_categories,
        extraction_mode=extraction_mode,
        story_id=story_id,
        custom_instructions=custom_instructions,
        stream_callback=stream_callback,
    )
    payload = result.get("data", {}).get("knowledge_extraction", {})
    items = payload.get("items", []) if isinstance(payload, dict) else []
    items = [
        {**item, "story_id": str(story_id or "default")}
        for item in items
        if isinstance(item, dict)
    ]
    items = build_pending_knowledge_from_reference_extraction(items, scope=scope)
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
        auto_summary = _sw.auto_confirm_pending_items_without_risk(
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
