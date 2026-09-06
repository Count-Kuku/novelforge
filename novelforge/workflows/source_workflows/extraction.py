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

"""Long-reference extraction queue, plan, and templates."""

def extract_long_reference_segments_to_queue(
    project_name: str,
    batch: dict,
    segment_indices: list[int],
    enabled_categories: list[str],
    extraction_mode: str = "general",
    custom_instructions: str = "",
    progress_callback=None,
    stream_callback=None,
    task_id: str = "",
    worker_id: str = "",
    story_id: str = "default",
    recall_enabled: bool = False,
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
            "stage": "extraction",
            "stage_status": "running",
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
                "stage": "extraction",
                "stage_status": "running",
                "segment_index": index,
                "segment_id": str(segment.get("segment_id") or ""),
        })
        try:
            _sw._safe_stream_emit(stream_callback, f"\n\n## {segment_title}\n\n")
            existing_related = _sw.get_segment_related_knowledge_items(project_name, segment, include_confirmed=False)["pending"]
            result = extract_reference_knowledge(
                project_name,
                segment.get("title", batch.get("title", "长篇资料")),
                segment.get("content", ""),
                enabled_categories,
                extraction_mode=extraction_mode,
                story_id=story_id,
                custom_instructions=custom_instructions,
                stream_callback=stream_callback,
                task_id=task_id,
            )
            payload = result.get("data", {}).get("knowledge_extraction", {})
            items = payload.get("items", []) if isinstance(payload, dict) else []
            if recall_enabled:
                recall_result = recall_missed_knowledge(
                    project_name,
                    segment.get("title", batch.get("title", "长篇资料")),
                    segment.get("content", ""),
                    items,
                    enabled_categories=enabled_categories,
                    story_id=story_id,
                    stream_callback=stream_callback,
                    task_id=task_id,
                )
                recall_payload = recall_result.get("data", {}).get("knowledge_extraction", {})
                recalled = recall_payload.get("items", []) if isinstance(recall_payload, dict) else []
                items = list(items) + list(recalled)
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
                enriched["source_id"] = str(batch.get("source_id") or f"long_batch_{batch.get('batch_id', '')}")
                enriched["source_revision_id"] = str(batch.get("source_revision_id") or "")
                enriched["story_id"] = str(story_id or "default")
                enriched["source_start_offset"] = segment.get("start_offset")
                enriched["source_end_offset"] = segment.get("end_offset")
                enriched["version_scope"] = str(enriched.get("version_scope") or ("canon" if batch.get("scope") == "canon" else "project_main"))
                # D10/D16：canon 原著按 source_id 派生独立世界线；非 canon（图鉴/参考）保持 main
                if batch.get("scope") == "canon":
                    enriched["worldline_id"] = str(enriched.get("worldline_id") or _sw.derive_worldline_id(batch.get("source_id")))
                    enriched["worldline_label"] = str(enriched.get("worldline_label") or batch.get("title") or "原著世界")
                else:
                    enriched["worldline_id"] = str(enriched.get("worldline_id") or _sw.DEFAULT_WORLDLINE_ID)
                    enriched["worldline_label"] = str(enriched.get("worldline_label") or _sw.DEFAULT_WORLDLINE_LABEL)
                evidence_contexts = locate_evidence_contexts(
                    segment.get("content", ""),
                    enriched.get("evidence", []),
                    base_offset=int(segment.get("start_offset") or 0),
                )
                if evidence_contexts:
                    enriched["evidence_contexts"] = evidence_contexts
                enriched_items.append(enriched)
            comparison = compare_extracted_items(existing_related, enriched_items)
            pending_items = build_pending_knowledge_from_reference_extraction(
                enriched_items, scope=batch.get("scope", "reference")
            )
            queued_count = queue_pending_knowledge_items(
                project_name,
                pending_items,
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
            save_long_reference_batch(
                project_name,
                batch,
                task_id=task_id,
                worker_id=worker_id,
            )
            queued_total += queued_count
            processed += 1
        except Exception as exc:
            segment["extract_status"] = "failed"
            segment["extract_error"] = str(exc)
            save_long_reference_batch(
                project_name,
                batch,
                task_id=task_id,
                worker_id=worker_id,
            )
            failed_titles.append(f"{segment.get('title', '未命名片段')}：{exc}")
            if progress_callback:
                progress_callback({
                    "current": position,
                    "total": total_targets or 1,
                    "message": f"提取失败：{segment_title}",
                    "stage": "extraction",
                    "segment_index": index,
                    "segment_id": str(segment.get("segment_id") or ""),
                })
        else:
            # Keep task-control and lease-loss signals outside the extraction
            # exception boundary. A pause after a successful durable save must
            # never rewrite that segment as failed.
            if progress_callback:
                progress_callback({
                    "current": position,
                    "total": total_targets or 1,
                    "message": f"已完成：{segment_title}，新增 {queued_count} 条",
                    "stage": "extraction",
                    "segment_index": index,
                    "segment_id": str(segment.get("segment_id") or ""),
                })
    batch = save_long_reference_batch(
        project_name,
        batch,
        task_id=task_id,
        worker_id=worker_id,
    )
    if progress_callback:
        progress_callback({
            "current": total_targets or 1,
            "total": total_targets or 1,
            "message": f"提取完成：成功 {processed} 段，失败 {len(failed_titles)} 段",
            "stage": "extraction",
        })
    return batch, processed, queued_total, failed_titles


def locate_evidence_contexts(raw_text: str, evidence: list, *, base_offset: int = 0) -> list[dict]:
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
                "start_offset": base_offset + char_index if char_index >= 0 else None,
                "end_offset": base_offset + char_index + len(quote_short) if char_index >= 0 else None,
                "prefix": raw_text[max(0, char_index - 80):char_index] if char_index >= 0 else "",
                "suffix": raw_text[char_index + len(quote_short):char_index + len(quote_short) + 80] if char_index >= 0 else "",
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
    stream_callback=None,
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
        _sw._safe_stream_emit(stream_callback, f"\n\n# {step_label}\n\n")

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
            stream_callback=stream_callback,
            story_id=str(current_batch.get("story_id") or "default"),
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
