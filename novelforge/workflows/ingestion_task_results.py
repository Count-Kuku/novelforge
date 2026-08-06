"""Durable result summaries for source-ingestion tasks."""
from __future__ import annotations

from novelforge.domain.ingestion_tasks import normalize_ingestion_task


def _safe_int(value: object) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def build_ingestion_task_result(task: dict, batch: dict, summary: dict | None = None) -> dict:
    """Merge the latest run summary with durable task and batch checkpoints."""
    normalized = normalize_ingestion_task(task)
    result = dict(summary) if isinstance(summary, dict) else {}
    segments = batch.get("segments", []) if isinstance(batch.get("segments", []), list) else []
    segments_by_id = {
        str(segment.get("segment_id") or ""): segment
        for segment in segments
        if isinstance(segment, dict) and str(segment.get("segment_id") or "")
    }
    selected_segments: list[dict] = []
    for item in normalized.get("items", []):
        segment = segments_by_id.get(str(item.get("segment_id") or ""))
        try:
            index = int(item.get("segment_index", -1))
        except (TypeError, ValueError):
            index = -1
        if segment is None and 0 <= index < len(segments) and isinstance(segments[index], dict):
            segment = segments[index]
        if segment is not None:
            selected_segments.append(segment)

    imported_count = sum(segment.get("import_status") == "imported" for segment in selected_segments)
    processed_count = sum(
        segment.get("extract_status") in {"queued", "extracted"}
        for segment in selected_segments
    )
    queued_count = sum(_safe_int(segment.get("queued_knowledge_count")) for segment in selected_segments)
    stages = normalized.get("execution", {}).get("stages", {})
    candidate_ids = normalized.get("execution", {}).get("candidate_ids", [])
    failed_items = [
        {
            "item_id": item.get("item_id", ""),
            "segment_index": item.get("segment_index", -1),
            "title": item.get("title", ""),
            "error": item.get("error", ""),
            "failure_stages": list(item.get("failure_stages") or []),
        }
        for item in normalized.get("items", [])
        if item.get("status") == "failed"
    ]
    configuration = normalized.get("configuration", {})
    extraction_result = stages.get("extraction", {}).get("result", {})
    import_result = stages.get("import", {}).get("result", {})
    consolidation_result = stages.get("consolidation", {}).get("result", {})
    auto_confirm_result = stages.get("auto_confirm", {}).get("result", {})
    result.update({
        "selected_segment_count": len(normalized.get("items", [])),
        "extract_segment_count": len(normalized.get("items", [])),
        "imported_count": max(imported_count, _safe_int(import_result.get("imported_count"))),
        "processed_count": max(processed_count, _safe_int(extraction_result.get("processed_count"))),
        "queued_count": max(queued_count, _safe_int(extraction_result.get("queued_count"))),
        "candidate_count": max(len(candidate_ids), _safe_int(result.get("candidate_count"))),
        "auto_confirmed_count": max(
            len(auto_confirm_result.get("confirmed_ids", [])) if isinstance(auto_confirm_result, dict) else 0,
            _safe_int(result.get("auto_confirmed_count")),
        ),
        "blocked_count": max(
            len(auto_confirm_result.get("blocked_ids", [])) if isinstance(auto_confirm_result, dict) else 0,
            _safe_int(result.get("blocked_count")),
        ),
        "failed_titles": [str(item.get("title") or "") for item in failed_items],
        "failed_items": failed_items,
        "extraction_mode": str(configuration.get("extraction_mode") or result.get("extraction_mode") or "general"),
        "categories": list(configuration.get("enabled_categories") or result.get("categories") or []),
        "import_to_index": bool(configuration.get("import_to_index", result.get("import_to_index", True))),
        "consolidate_after_extract": bool(configuration.get("consolidate_after_extract", result.get("consolidate_after_extract", False))),
        "auto_confirm_safe_items": bool(configuration.get("auto_confirm_safe_items", result.get("auto_confirm_safe_items", True))),
        "custom_instructions": str(configuration.get("custom_instructions") or result.get("custom_instructions") or ""),
        "consolidation": dict(consolidation_result) if isinstance(consolidation_result, dict) else {},
        "auto_confirm": dict(auto_confirm_result) if isinstance(auto_confirm_result, dict) else {},
        "stage_statuses": {
            name: str(stage.get("status") or "")
            for name, stage in stages.items()
            if isinstance(stage, dict)
        },
    })
    return result
