"""Pure promotion eligibility shared by API projections and write workflow."""

from __future__ import annotations

import json
from typing import Any

from novelforge.domain.knowledge_types import KNOWLEDGE_TYPE_FIELDS, validate_typed_knowledge_item


_REJECTED_ORIGINS = {
    "interactive_fragment",
    "creative_fragment",
}

# These are the source kinds emitted by the reference/document ingestion
# chain.  A source type alone is not enough for long batches: those sources
# must also retain their stable ``long_batch_*`` source id (or a batch marker).
# Keeping this positive allow-list prevents an arbitrary memory/chapter source
# from becoming promotable merely because it happens to have a segment row.
_IMPORTED_SOURCE_TYPES = {
    "creative_attachment",
    "external_source",
    "long_form_source",
    "reference",
}
_IMPORTED_SOURCE_PREFIXES = ("external_",)
_IMPORTED_SOURCE_ID_PREFIXES = ("long_batch_", "source_file_")


def _source_value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    try:
        return source[key]
    except (KeyError, IndexError, TypeError):
        return ""


def _origin_kind(item: dict, source: Any = None) -> str:
    values = (
        item.get("source_origin"),
        item.get("extraction_mode"),
        item.get("source_type"),
        _source_value(source, "source_type") if source is not None else "",
    )
    return " ".join(str(value or "").strip().lower() for value in values)


def _source_metadata(source: Any) -> dict:
    value = _source_value(source, "metadata_json") if source is not None else {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            parsed = {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _has_import_source_marker(source: Any, source_type: str, metadata: dict) -> bool:
    source_id = str(_source_value(source, "source_id") or "").strip().lower()
    normalized_type = str(source_type or "").strip().lower()
    if normalized_type in _IMPORTED_SOURCE_TYPES:
        return True
    if any(normalized_type.startswith(prefix) for prefix in _IMPORTED_SOURCE_PREFIXES):
        return True
    if any(source_id.startswith(prefix) for prefix in _IMPORTED_SOURCE_ID_PREFIXES):
        return bool(
            str(metadata.get("batch_id") or "").strip()
            or str(metadata.get("relative_path") or "").strip()
            or normalized_type in _IMPORTED_SOURCE_TYPES
            or any(normalized_type.startswith(prefix) for prefix in _IMPORTED_SOURCE_PREFIXES)
        )
    # The persisted long-reference metadata is the authoritative link for a
    # custom source type supplied by an importer.  A batch marker is accepted
    # only on the stable long-batch source id; a free-form source_origin or a
    # copied ``batch_id`` on an arbitrary memory source is insufficient.
    return bool(
        str(metadata.get("batch_id") or "").strip()
        and source_id.startswith("long_batch_")
    )


def check_knowledge_promotion_eligibility(item: dict, *, source: Any = None) -> dict:
    """Return deterministic eligibility without memory, workflow, or SQLite imports."""

    payload = item if isinstance(item, dict) else {}
    knowledge_id = str(payload.get("id") or payload.get("knowledge_id") or "").strip()
    scope = str(payload.get("setting_scope") or "").strip().lower()
    story_id = str(payload.get("story_id") or "").strip()
    category = str(payload.get("category") or "").strip()
    status = str(payload.get("status") or "").strip().lower()
    if not knowledge_id:
        return {"eligible": False, "reason": "缺少 knowledge_id。", "code": "missing_id"}
    if scope != "story" or not story_id:
        return {"eligible": False, "reason": "条目不是 story 作用域。", "code": "not_story_scope"}
    if category not in KNOWLEDGE_TYPE_FIELDS:
        return {"eligible": False, "reason": "知识分类无效。", "code": "invalid_category"}
    if status and status not in {"confirmed", "active"}:
        return {"eligible": False, "reason": "条目尚未确认。", "code": "not_confirmed"}
    source_id = str(payload.get("source_id") or _source_value(source, "source_id") or "").strip()
    segment_id = str(
        payload.get("source_segment_id")
        or payload.get("segment_id")
        or _source_value(source, "segment_id")
        or ""
    ).strip()
    if not source_id or not segment_id:
        return {
            "eligible": False,
            "reason": "缺少资料导入来源 ID 或片段 ID。",
            "code": "missing_import_source",
        }
    source_segment_id = str(_source_value(source, "segment_id") or "").strip()
    if source_segment_id and source_segment_id != segment_id:
        return {
            "eligible": False,
            "reason": "资料片段不属于该知识条目的来源。",
            "code": "source_segment_mismatch",
        }
    segment_source_id = str(_source_value(source, "segment_source_id") or "").strip()
    if segment_source_id and segment_source_id != source_id:
        return {
            "eligible": False,
            "reason": "资料片段不属于该资料来源。",
            "code": "source_segment_mismatch",
        }
    segment_status = str(_source_value(source, "import_status") or "").strip().lower()
    if segment_status in {"failed", "error", "deleted", "archived"}:
        return {
            "eligible": False,
            "reason": "资料知识片段导入已失败或失效。",
            "code": "invalid_import_segment",
        }
    origin = _origin_kind(payload, source)
    if any(token in origin for token in _REJECTED_ORIGINS):
        return {"eligible": False, "reason": "互动/创作片段条目不能提升。", "code": "fragment_origin"}
    source_type = str(_source_value(source, "source_type") or payload.get("source_type") or "").strip().lower()
    source_metadata = _source_metadata(source)
    if source_type in {"chapter_content", "chapter_summary", "creative_session_fragment", "creative_session_summary", "interactive_fragment"}:
        return {"eligible": False, "reason": "来源不是资料导入。", "code": "non_imported_source"}
    if not _has_import_source_marker(source, source_type, source_metadata):
        return {
            "eligible": False,
            "reason": "来源未通过资料导入来源链校验。",
            "code": "non_imported_source",
        }
    typed_errors = validate_typed_knowledge_item(payload, category)
    if typed_errors:
        return {
            "eligible": False,
            "reason": "；".join(typed_errors),
            "code": "typed_validation",
        }
    return {"eligible": True, "reason": "", "code": "eligible"}
