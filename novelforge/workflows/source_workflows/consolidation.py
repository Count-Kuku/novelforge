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

"""Ingestion health, source ledger, and knowledge consolidation."""

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
    storage_health = load_knowledge_storage_health(project_name)
    confirmed_total = int(storage_health.get("confirmed_total") or 0)
    evidence_total = int(storage_health.get("evidence_total") or 0)
    storage_health["typed_coverage"] = (
        int(storage_health.get("typed_total") or 0) / confirmed_total if confirmed_total else 0.0
    )
    storage_health["anchored_evidence_coverage"] = (
        int(storage_health.get("anchored_evidence_total") or 0) / evidence_total if evidence_total else 0.0
    )
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
        "alias_group_count": len(load_entity_aliases(project_name)),
        "extraction_plan_template_count": len(load_extraction_plan_templates(project_name)),
        "storage_health": storage_health,
    }


def build_ingestion_workbench(project_name: str) -> dict:
    """Load ingestion state and build the user-oriented workbench summary."""
    batches = list_long_reference_batches(project_name)
    return build_ingestion_workbench_summary(
        batches,
        source_count=len(list_retrieval_source_files(project_name)),
        health=build_ingestion_health_report(project_name),
        tasks=list_source_ingestion_tasks(project_name),
    )


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
    revisions = load_source_revisions(project_name)
    revisions_by_source: dict[str, list[dict]] = {}
    revisions_by_path: dict[str, list[dict]] = {}
    for revision in revisions:
        if not isinstance(revision, dict):
            continue
        revisions_by_source.setdefault(str(revision.get("source_id") or ""), []).append(revision)
        metadata = revision.get("metadata") if isinstance(revision.get("metadata"), dict) else {}
        relative_path = str(metadata.get("relative_path") or "").replace("\\", "/")
        if relative_path:
            revisions_by_path.setdefault(relative_path, []).append(revision)
    records: list[dict] = []

    for batch in list_long_reference_batches(project_name):
        batch_source_id = str(batch.get("source_id") or f"long_batch_{batch.get('batch_id', '')}")
        source_revisions = revisions_by_source.get(batch_source_id, [])
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
            "source_id": batch_source_id,
            "source_revision_id": batch.get("source_revision_id", ""),
            "revision_count": len(source_revisions),
            "revisions": source_revisions,
        })

    for relative_path in list_retrieval_source_files(project_name):
        payload = read_retrieval_source_payload(project_name, relative_path)
        metadata = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
        title = str(payload.get("title") or relative_path)
        origin = str(metadata.get("source_origin") or payload.get("source_origin") or "")
        key = (title, origin)
        source_counts = knowledge_counts.get(key, {})
        source_revisions = revisions_by_path.get(relative_path, [])
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
            "source_id": source_revisions[0].get("source_id", "") if source_revisions else "",
            "source_revision_id": source_revisions[0].get("revision_id", "") if source_revisions else "",
            "revision_count": len(source_revisions),
            "revisions": source_revisions,
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
    enriched_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        enriched = dict(item)
        enriched["extraction_mode"] = str(enriched.get("extraction_mode") or f"consolidated:{consolidation_mode}")
        requested_ids = {
            str(value or "").strip()
            for value in (enriched.get("merged_from_pending_ids") or [])
            if str(value or "").strip()
        }
        if requested_ids:
            matches = [
                source for source in source_items
                if str(source.get("pending_id") or "").strip() in requested_ids
            ]
        else:
            target_category = str(enriched.get("category") or "").strip()
            target_name = " ".join(str(enriched.get("name") or "").split()).strip()
            matches = [
                source for source in source_items
                if str(source.get("category") or "").strip() == target_category
                and " ".join(str(source.get("name") or "").split()).strip() == target_name
            ]
            # A one-item batch is an unambiguous fallback.  Never use the
            # whole batch as a source for an item with no reliable identity.
            if not matches and len(source_items) == 1:
                matches = [source_items[0]]
        if matches and not enriched.get("merged_from_pending_ids"):
            enriched["merged_from_pending_ids"] = [
                str(source.get("pending_id") or "").strip()
                for source in matches
                if str(source.get("pending_id") or "").strip()
            ]
        if matches and not enriched.get("source_segment_ids"):
            enriched["source_segment_ids"] = merge_list_values([
                source.get("source_segment_ids", []) for source in matches
            ] + [[
                source.get("source_segment_id", "") for source in matches
                if source.get("source_segment_id")
            ]])
        if matches and not enriched.get("source_segment_titles"):
            enriched["source_segment_titles"] = merge_list_values([
                source.get("source_segment_titles", []) for source in matches
            ] + [[
                source.get("source_segment_title", "") for source in matches
                if source.get("source_segment_title")
            ]])
        for field in ("story_id", "source_id", "source_revision_id", "source_origin", "creative_attachment_id", "setting_scope", "version_scope", "setting_role", "injection_policy", "setting_field", "worldline_id", "worldline_label"):
            if enriched.get(field) or not matches:
                continue
            values = list(dict.fromkeys(
                str(source.get(field) or "").strip()
                for source in matches
                if str(source.get(field) or "").strip()
            ))
            if len(values) == 1:
                enriched[field] = values[0]
        if matches and not enriched.get("aliases"):
            enriched["aliases"] = merge_list_values([source.get("aliases", []) for source in matches])
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
    stream_callback=None,
    task_id: str = "",
    story_id: str = "",
    branch_id: str = "",
) -> dict:
    batch_pending_items = _sw.get_batch_pending_knowledge_items(project_name, batch)
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
        story_id=story_id,
        stream_callback=stream_callback,
        task_id=task_id,
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
    scope_value = target_items[0].get("scope", batch.get("scope", "reference"))
    target_scope = str(batch.get("target_scope") or ("story" if str(story_id or "").strip() else "project"))
    pending_items = build_pending_knowledge_from_reference_extraction(
        enriched_items,
        scope=scope_value,
        setting_scope=target_scope,
        story_id=str(story_id or ""),
        branch_id=str(branch_id or ""),
    )
    queued_count = queue_pending_knowledge_items(
        project_name,
        pending_items,
        scope=scope_value,
        authority=target_items[0].get("authority", batch.get("authority", "curated")),
        source_title=batch.get("title", payload.get("source_title", "")),
        source_origin=batch.get("source_origin", ""),
        branch_id=str(branch_id or ""),
        replace_pending_ids=target_ids,
    )
    if queued_count <= 0:
        return {
            "success": False,
            "message": "整理结果未能写入待确认知识，原始条目已保留。",
            "source_count": len(target_items),
            "queued_count": 0,
            "result": result,
        }
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

    reviewed_at = datetime.now(timezone.utc)
    id_digest = hashlib.sha1("|".join(sorted(id_set)).encode("utf-8")).hexdigest()[:10]
    run_id = (
        f"auto_review_{reviewed_at.strftime('%Y%m%d%H%M%S%f')}_"
        f"{id_digest}_{uuid4().hex[:8]}"
    )
    audit_payload = {
        "run_id": run_id,
        "source_type": source_type or "auto_confirm",
        "source_title": source_title,
        "batch_id": batch_id,
        "note": note,
        "candidate_ids": sorted(id_set),
        "blocked_ids": blocked_ids,
        "blocked_reasons": blocked_reasons,
        "decisions": decisions,
        "policy": policy,
    }
    confirm_result = confirm_pending_knowledge_items_with_records(
        project_name,
        confirmed_ids,
        confirmation_metadata={
            "auto_review_run_id": run_id,
            "auto_reviewed_at": reviewed_at.isoformat(),
        },
        audit_run=audit_payload,
    )
    saved_count = int(confirm_result.get("saved_count", 0))
    run = dict(confirm_result.get("audit_run") or audit_payload)
    confirmed_ids = [str(item) for item in run.get("confirmed_ids", []) if str(item)]
    blocked_ids = [str(item) for item in run.get("blocked_ids", []) if str(item)]
    blocked_reasons = dict(run.get("blocked_reasons") or {})
    if saved_count:
        try:
            rebuild_retrieval_assets(project_name, build_vectors=True)
        except Exception as exc:
            LOGGER.warning(
                "Auto-review commit succeeded, but vector rebuild failed for %s: %s",
                project_name,
                exc,
            )
        # 遗留 #1 收口：已确认条目携带的 aliases 同步进别名组（供别名解析命中）。
        try:
            confirmed_id_set = set(confirmed_ids)
            from novelforge.services.memory import sync_aliases_to_groups

            sync_aliases_to_groups(
                project_name,
                [item for item in candidate_items if str(item.get("pending_id") or "") in confirmed_id_set],
            )
        except Exception as exc:
            LOGGER.warning("Sync aliases to groups failed for %s: %s", project_name, exc)
    return {
        "confirmed_ids": confirmed_ids,
        "blocked_ids": blocked_ids,
        "blocked_reasons": blocked_reasons,
        "saved_count": saved_count,
        "run_id": run.get("run_id", run_id),
        "decisions": decisions,
    }


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
    stream_callback=None,
    execution_state: dict | None = None,
    run_key: str = "",
    task_id: str = "",
    worker_id: str = "",
    story_id: str = "",
) -> tuple[dict, dict]:
    from novelforge.workflows.long_reference_quick_process import (
        run_long_reference_quick_process as _run_long_reference_quick_process,
    )

    return _run_long_reference_quick_process(
        project_name,
        batch,
        segment_indices,
        enabled_categories=enabled_categories,
        extraction_mode=extraction_mode,
        extract_limit=extract_limit,
        import_to_index=import_to_index,
        consolidate_after_extract=consolidate_after_extract,
        auto_confirm_safe_items=auto_confirm_safe_items,
        custom_instructions=custom_instructions,
        progress_callback=progress_callback,
        stream_callback=stream_callback,
        execution_state=execution_state,
        run_key=run_key,
        task_id=task_id,
        worker_id=worker_id,
        story_id=story_id,
    )
