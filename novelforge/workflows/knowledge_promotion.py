"""Promote story-scoped imported knowledge into the project scope.

This workflow deliberately operates on the authoritative SQLite rows.  It
does not re-extract source text and does not call an LLM.  A project copy is a
new knowledge row whose payload carries an immutable association to the story
row that produced it; retries therefore never overwrite a user's project
edits.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import re
from pathlib import Path
from typing import Any

from novelforge.domain.knowledge_promotion import check_knowledge_promotion_eligibility as _domain_check_knowledge_promotion_eligibility
from novelforge.domain.knowledge_types import KNOWLEDGE_TYPE_FIELDS
from novelforge.domain.knowledge_quality import (
    _knowledge_domains_compatible,
    canon_status_conflict,
    details_conflicts,
    fact_conflicts,
)
from novelforge.domain.knowledge_workflows import evaluate_pending_auto_review_decision
from novelforge.workflows.knowledge_index_dispatcher import (
    wake_running_knowledge_index_dispatcher,
)
from storage import open_existing_project_db
from storage.repositories.knowledge import (
    load_knowledge_evidence_rows,
    upsert_knowledge_category_item,
)
from storage.repositories.entity_identity import entity_type_for_category


LOGGER = logging.getLogger("novelforge.knowledge_promotion")

_REJECTED_ORIGINS = {
    "interactive_fragment",
    "creative_fragment",
}
_REJECTED_SEGMENT_STATUSES = {"failed", "error", "deleted", "archived"}
_REJECTED_SOURCE_TYPES = {
    "chapter_content",
    "chapter_summary",
    "creative_session_fragment",
    "creative_session_summary",
    "interactive_fragment",
}


def _json_object(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _clean_id(value: Any) -> str:
    return str(value or "").strip()


def _row_value(row: sqlite3.Row | tuple | dict, key: str, index: int = 0) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    if isinstance(row, sqlite3.Row):
        return row[key]
    return row[index]


def _source_payload(item: dict, source: sqlite3.Row | None) -> dict:
    """Return the latest source metadata without replacing user-edited fields."""

    metadata = _json_object(source["metadata_json"] if source is not None else "{}")
    # Metadata written by both long-reference and creative-attachment import
    # paths is intentionally copied only for trace fields.  The knowledge row
    # itself remains the source of truth for content and evidence.
    result = dict(item)
    for key in (
        "batch_id",
        "creative_attachment_id",
        "source_origin",
        "source_type",
        "source_revision_id",
    ):
        if not _clean_id(result.get(key)) and metadata.get(key) not in (None, "", [], {}):
            result[key] = metadata.get(key)
    if not _clean_id(result.get("source_title")) and source is not None:
        result["source_title"] = _clean_id(source["title"])
    return result


def _item_from_row(row: sqlite3.Row) -> dict:
    payload = _json_object(row["content_json"])
    # Old rows may have incomplete content_json.  Fill only storage columns;
    # current rows retain every edited payload field verbatim.
    defaults = {
        "id": _clean_id(row["knowledge_id"]),
        "knowledge_id": _clean_id(row["knowledge_id"]),
        "story_id": _clean_id(row["story_id"]),
        "category": _clean_id(row["category"]),
        "name": _clean_id(row["name"]),
        "title": _clean_id(row["title"]),
        "summary": _clean_id(row["summary"]),
        "canon_status": row["canon_status"],
        "worldline_id": row["worldline_id"],
        "worldline_name": row["worldline_name"],
        "confidence": row["confidence"],
        "importance": row["importance"],
        "evidence_strength": row["evidence_strength"],
        "source_id": row["source_id"],
        "source_segment_id": row["segment_id"],
        "extraction_mode": row["extraction_mode"],
        "setting_scope": row["setting_scope"],
        "setting_role": row["setting_role"],
        "injection_policy": row["injection_policy"],
        "status": row["status"],
        "schema_version": row["schema_version"],
        "typed_data": _json_object(row["structured_json"]),
        "entity_id": row["entity_id"] if "entity_id" in row.keys() else None,
        "fact_key": row["fact_key"] if "fact_key" in row.keys() else None,
        "chapter_no": row["chapter_no"] if "chapter_no" in row.keys() else None,
        "valid_from_chapter": row["valid_from_chapter"] if "valid_from_chapter" in row.keys() else None,
        "valid_to_chapter": row["valid_to_chapter"] if "valid_to_chapter" in row.keys() else None,
        "merge_policy": row["merge_policy"] if "merge_policy" in row.keys() else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    for key, value in defaults.items():
        if key not in payload or payload.get(key) in (None, ""):
            if value not in (None, ""):
                payload[key] = value
    payload["id"] = _clean_id(row["knowledge_id"])
    payload["knowledge_id"] = _clean_id(row["knowledge_id"])
    payload["category"] = _clean_id(row["category"])
    return payload


def _ensure_payload_evidence(conn: sqlite3.Connection, item: dict, source_id: str) -> dict:
    """Keep DB evidence available when a legacy payload omitted its evidence key."""

    if "evidence" in item:
        return item
    rows = load_knowledge_evidence_rows(conn, source_id)
    if not rows:
        return item
    item["evidence"] = [
        {
            "quote": str(row.get("quote") or ""),
            "source_id": row.get("source_id"),
            "segment_id": row.get("segment_id"),
            "chunk_id": row.get("chunk_id"),
            "source_revision_id": row.get("source_revision_id"),
            "start_offset": row.get("start_offset"),
            "end_offset": row.get("end_offset"),
            "prefix": row.get("prefix") or "",
            "suffix": row.get("suffix") or "",
            "validation_status": row.get("validation_status") or "",
            "confidence": row.get("confidence"),
            "evidence_strength": row.get("evidence_strength"),
            "location": row.get("location") or {},
        }
        for row in rows
        if str(row.get("quote") or "").strip()
    ]
    return item


def _origin_kind(item: dict, source: sqlite3.Row | None) -> str:
    values = (
        item.get("source_origin"),
        item.get("extraction_mode"),
        item.get("source_type"),
        source["source_type"] if source is not None else "",
    )
    return " ".join(str(value or "").strip().lower() for value in values)


def _reject_non_imported_fragment(item: dict, source: sqlite3.Row | None) -> None:
    haystack = _origin_kind(item, source)
    if any(token in haystack for token in _REJECTED_ORIGINS):
        raise ValueError(
            f"知识条目 {item.get('id') or item.get('knowledge_id')} 来自互动/创作片段，不能提升到项目知识。"
        )


def check_knowledge_promotion_eligibility(
    item: dict,
    *,
    source: sqlite3.Row | dict | None = None,
) -> dict:
    """Compatibility export; the actual pure helper lives under ``domain``."""

    return _domain_check_knowledge_promotion_eligibility(item, source=source)


def _story_row(conn: sqlite3.Connection, story_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT story_id FROM stories WHERE story_id = ? AND deleted_at IS NULL",
        (story_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"知识条目引用的故事不存在或已归档：{story_id}")
    return row


def _source_row(conn: sqlite3.Connection, source_id: str) -> sqlite3.Row:
    if not source_id:
        raise ValueError("故事知识缺少可靠 source_id，不能确认资料导入来源。")
    row = conn.execute(
        "SELECT * FROM source_documents WHERE source_id = ? AND deleted_at IS NULL",
        (source_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"知识条目的资料来源不存在或已归档：{source_id}")
    return row


def _attachment_row(conn: sqlite3.Connection, attachment_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM creative_attachments WHERE attachment_id = ?",
        (attachment_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"创作附件不存在：{attachment_id}")
    story_id = _clean_id(row["story_id"])
    if not story_id:
        raise ValueError("项目级附件没有 story 来源，不能从 story 提升知识。")
    _story_row(conn, story_id)
    return row


def _source_belongs_to_story(
    source: sqlite3.Row,
    story_id: str,
    *,
    attachment: sqlite3.Row | None = None,
) -> bool:
    source_story_id = _clean_id(source["story_id"])
    if source_story_id == story_id:
        return True
    metadata = _json_object(source["metadata_json"])
    if _clean_id(metadata.get("story_id")) == story_id:
        return True
    if attachment is not None:
        if _clean_id(attachment["story_id"]) != story_id:
            return False
        attachment_id = _clean_id(attachment["attachment_id"])
        return (
            _clean_id(attachment["source_id"]) == _clean_id(source["source_id"])
            or _clean_id(metadata.get("creative_attachment_id")) == attachment_id
        )
    return False


def _validate_story_item(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    attachment: sqlite3.Row | None = None,
) -> tuple[dict, sqlite3.Row]:
    knowledge_id = _clean_id(row["knowledge_id"])
    story_id = _clean_id(row["story_id"])
    scope = _clean_id(row["setting_scope"]).lower()
    if not story_id or scope != "story":
        raise ValueError(f"知识条目不是 story 作用域，不能提升：{knowledge_id}")
    _story_row(conn, story_id)
    item = _item_from_row(row)
    category = _clean_id(item.get("category"))
    if category not in KNOWLEDGE_TYPE_FIELDS:
        raise ValueError(f"知识条目分类无效：{category or knowledge_id}")
    source_id = _clean_id(row["source_id"]) or _clean_id(item.get("source_id"))
    source = _source_row(conn, source_id)
    if not _source_belongs_to_story(source, story_id, attachment=attachment):
        raise ValueError(f"知识条目的资料来源不属于 story：{knowledge_id}")
    if attachment is not None:
        attachment_id = _clean_id(attachment["attachment_id"])
        source_metadata = _json_object(source["metadata_json"])
        belongs_to_attachment = (
            source_id == _clean_id(attachment["source_id"])
            or _clean_id(item.get("creative_attachment_id")) == attachment_id
            or _clean_id(source_metadata.get("creative_attachment_id")) == attachment_id
        )
        if not belongs_to_attachment:
            raise ValueError(f"知识条目不属于指定附件：{knowledge_id}")
    segment_id = _clean_id(row["segment_id"]) or _clean_id(item.get("source_segment_id"))
    segment = conn.execute(
        "SELECT source_id, import_status FROM source_segments WHERE segment_id = ? AND deleted_at IS NULL",
        (segment_id,),
    ).fetchone()
    if segment is None or _clean_id(segment["source_id"]) != source_id:
        raise ValueError(f"知识条目缺少有效的资料导入片段：{knowledge_id}")
    if _clean_id(segment["import_status"]).lower() in _REJECTED_SEGMENT_STATUSES:
        raise ValueError(f"知识条目的资料片段导入已失败或失效：{knowledge_id}")
    source_type = _clean_id(source["source_type"]).lower()
    metadata = _json_object(source["metadata_json"])
    if source_type in _REJECTED_SOURCE_TYPES:
        raise ValueError(f"知识条目来源不是资料导入：{knowledge_id}")
    if not (
        source_type
        or _clean_id(metadata.get("batch_id"))
        or _clean_id(metadata.get("creative_attachment_id"))
    ):
        raise ValueError(f"知识条目缺少可确认的资料导入来源：{knowledge_id}")
    _reject_non_imported_fragment(item, source)
    status = _clean_id(row["status"]) or _clean_id(item.get("status"))
    if status and status.lower() not in {"confirmed", "active"}:
        raise ValueError(f"知识条目尚未确认，不能提升：{knowledge_id}")
    eligibility = check_knowledge_promotion_eligibility(item, source=source)
    if not eligibility.get("eligible"):
        raise ValueError(f"知识条目提升资格校验未通过：{knowledge_id}；{eligibility.get('reason')}")
    item["source_id"] = source_id
    item["source_segment_id"] = _clean_id(row["segment_id"]) or _clean_id(item.get("source_segment_id"))
    item = _source_payload(item, source)
    item = _ensure_payload_evidence(conn, item, knowledge_id)
    return item, source


def _promotion_origin(item: dict, source: sqlite3.Row, *, story_id: str, source_knowledge_id: str, attachment_id: str = "") -> dict:
    return {
        "kind": "story_knowledge",
        "story_id": story_id,
        "knowledge_id": source_knowledge_id,
        "source_id": _clean_id(item.get("source_id")) or _clean_id(source["source_id"]),
        "source_segment_id": _clean_id(item.get("source_segment_id")),
        "source_revision_id": _clean_id(item.get("source_revision_id")) or _clean_id(source["active_revision_id"]),
        "creative_attachment_id": attachment_id or _clean_id(item.get("creative_attachment_id")),
        "batch_id": _clean_id(item.get("batch_id")),
    }


def _copy_id(project_name: str, story_id: str, source_knowledge_id: str, salt: int = 0) -> str:
    seed = f"{project_name}|{story_id}|{source_knowledge_id}|{salt}"
    return "knowledge_project_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _payload_origin_ids(item: dict) -> set[str]:
    values = {
        item.get("source_story_knowledge_id"),
        item.get("promoted_from_knowledge_id"),
        item.get("promoted_from_story_knowledge_id"),
    }
    promotion = item.get("promotion_origin")
    if isinstance(promotion, dict):
        values.add(promotion.get("knowledge_id"))
    return {_clean_id(value) for value in values if _clean_id(value)}


def _find_existing_copy(project_index: list[dict], source_knowledge_id: str) -> dict | None:
    for payload in project_index:
        if source_knowledge_id in _payload_origin_ids(payload):
            return payload
    return None


def _promoted_payload(
    source_item: dict,
    *,
    project_name: str,
    story_id: str,
    source_knowledge_id: str,
    copy_id: str,
    source: sqlite3.Row,
    attachment_id: str = "",
) -> dict:
    result = dict(source_item)
    source_timing = {
        key: result.get(key)
        for key in ("chapter_no", "source_chapter_no", "valid_from_chapter", "valid_to_chapter", "setting_field", "fact_key")
        if result.get(key) not in (None, "", [], {})
    }
    # These fields describe the story copy's storage projection and must never
    # leak into the independent project entity/fact/revision identity.
    for key in (
        "entity_id",
        "fact_id",
        "revision_id",
        "knowledge_revision_id",
        "revision_ids",
        "valid_to_chapter",
        "superseded_by",
        "chapter_no",
        "source_chapter_no",
        "valid_from_chapter",
        "valid_to_chapter",
    ):
        result.pop(key, None)
    if isinstance(result.get("tags"), list):
        result["tags"] = [
            tag for tag in result["tags"]
            if not re.match(r"^chapter:\d+$", str(tag or "").strip(), flags=re.IGNORECASE)
        ]
    result.update({
        "id": copy_id,
        "knowledge_id": copy_id,
        "story_id": None,
        "setting_scope": "project",
        "scope": "project",
        "version_scope": "project_main",
        "status": "confirmed",
        "promotion_origin": _promotion_origin(
            result,
            source,
            story_id=story_id,
            source_knowledge_id=source_knowledge_id,
            attachment_id=attachment_id,
        ),
        "source_story_knowledge_id": source_knowledge_id,
        "promoted_from_knowledge_id": source_knowledge_id,
        "promoted_from_story_knowledge_id": source_knowledge_id,
        "source_story_id": story_id,
        "promoted_from_story_id": story_id,
        "promotion_project_name": project_name,
        "promotion_snapshot": True,
    })
    result.pop("branch_id", None)
    if source_timing:
        result["promotion_origin"]["source_story_timing"] = source_timing
    if attachment_id:
        result["creative_attachment_id"] = attachment_id
    return result


def _selected_rows(
    conn: sqlite3.Connection,
    project_name: str,
    knowledge_ids: list[str] | None,
    attachment_id: str | None,
) -> list[tuple[sqlite3.Row, sqlite3.Row | None, str]]:
    requested = list(dict.fromkeys(_clean_id(value) for value in (knowledge_ids or []) if _clean_id(value)))
    attachment: sqlite3.Row | None = None
    if attachment_id:
        attachment = _attachment_row(conn, _clean_id(attachment_id))
        attachment_source_id = _clean_id(attachment["source_id"])
        rows = conn.execute(
            """
            SELECT * FROM knowledge_items
            WHERE deleted_at IS NULL AND story_id = ? AND setting_scope = 'story'
              AND (
                  source_id = ?
                  OR json_extract(content_json, '$.creative_attachment_id') = ?
                  OR EXISTS (
                      SELECT 1 FROM source_documents AS source
                      WHERE source.source_id = knowledge_items.source_id
                        AND source.deleted_at IS NULL
                        AND json_extract(source.metadata_json, '$.creative_attachment_id') = ?
                  )
              )
            ORDER BY knowledge_id
            """,
            (_clean_id(attachment["story_id"]), attachment_source_id, _clean_id(attachment["attachment_id"]), _clean_id(attachment["attachment_id"])),
        ).fetchall()
        selected_by_id = {_clean_id(row["knowledge_id"]): row for row in rows}
        if requested:
            missing = [value for value in requested if value not in selected_by_id]
            if missing:
                raise ValueError(f"指定知识条目不属于附件或不存在：{', '.join(missing)}")
            rows = [selected_by_id[value] for value in requested]
    else:
        if not requested:
            raise ValueError("请提供 knowledge_ids 或 attachment_id。")
        placeholders = ",".join("?" for _ in requested)
        rows = conn.execute(
            f"SELECT * FROM knowledge_items WHERE knowledge_id IN ({placeholders}) AND deleted_at IS NULL",
            tuple(requested),
        ).fetchall()
        found = {_clean_id(row["knowledge_id"]): row for row in rows}
        missing = [value for value in requested if value not in found]
        if missing:
            raise ValueError(f"知识条目不存在、已归档或不属于当前项目：{', '.join(missing)}")
        rows = [found[value] for value in requested]
    if not rows:
        raise ValueError("指定来源没有已确认的 story 知识条目。")
    return [(row, attachment, _clean_id(attachment["attachment_id"]) if attachment is not None else "") for row in rows]


def _normalized_name(value: Any) -> str:
    return "".join(re.findall(r"[a-z0-9\u4e00-\u9fff]+", str(value or "").lower()))


def _normalized_worldline(value: Any) -> str:
    normalized = _clean_id(value).lower()
    if normalized in {"", "all", "global", "shared", "common", "canon", "unknown"}:
        return ""
    return normalized


def _project_candidate(item: dict) -> dict:
    """Project a source-shaped item into the comparison domain only."""

    candidate = dict(item or {})
    candidate["setting_scope"] = "project"
    candidate["story_id"] = None
    candidate.pop("branch_id", None)
    candidate["version_scope"] = "project_main"
    candidate["worldline_id"] = _normalized_worldline(candidate.get("worldline_id"))
    return candidate


def _fact_slot(item: dict) -> str:
    promotion = item.get("promotion_origin")
    timing = promotion.get("source_story_timing") if isinstance(promotion, dict) else {}
    if not isinstance(timing, dict):
        timing = {}
    return _normalized_name(
        item.get("setting_field")
        or item.get("fact_key")
        or timing.get("setting_field")
        or timing.get("fact_key")
    )


def _load_project_index(conn: sqlite3.Connection) -> list[dict]:
    """Load active project rows once for idempotency and conflict checks."""

    rows = conn.execute(
        "SELECT * FROM knowledge_items WHERE setting_scope = 'project' AND deleted_at IS NULL"
    ).fetchall()
    result = []
    for row in rows:
        payload = _item_from_row(row)
        payload["_storage_knowledge_id"] = _clean_id(row["knowledge_id"])
        result.append(payload)
    return result


def _blocking_project_conflict(
    conn: sqlite3.Connection | None,
    *,
    source_item: dict,
    source_knowledge_id: str,
    project_candidates: list[dict] | None = None,
    batch_candidates: list[dict] | None = None,
) -> str:
    """Return a reason for a real target-domain conflict.

    The repository's entity/fact projection uses ``setting_field`` as the
    fact slot.  Different slots on the same entity are compatible; a same-slot
    disagreement is checked with the shared quality primitives.  The source
    story id is deliberately removed from comparison so a batch can be
    compared with existing project rows, while worldline remains part of the
    isolation domain.
    """

    category = _clean_id(source_item.get("category"))
    name_key = _normalized_name(source_item.get("name") or source_item.get("canonical_name"))
    if not category or not name_key:
        return ""
    candidates = list(project_candidates or []) + list(batch_candidates or [])
    source_candidate = _project_candidate(source_item)
    source_slot = _fact_slot(source_candidate)
    for candidate in candidates:
        candidate = _project_candidate(candidate)
        candidate_id = _clean_id(candidate.get("_storage_knowledge_id") or candidate.get("knowledge_id") or candidate.get("id"))
        if source_knowledge_id in _payload_origin_ids(candidate):
            continue
        if candidate_id == source_knowledge_id:
            continue
        if _clean_id(candidate.get("category")) != category:
            continue
        if _normalized_name(candidate.get("name") or candidate.get("canonical_name")) != name_key:
            continue
        if not _knowledge_domains_compatible(source_candidate, candidate):
            # Explicitly separate continuities.  In particular, an entity in
            # another worldline must never block this promotion.
            continue
        candidate_slot = _fact_slot(candidate)
        if source_slot and candidate_slot and source_slot != candidate_slot:
            continue

        fact_diffs = fact_conflicts(source_candidate, candidate)
        detail_diffs = details_conflicts(source_candidate, candidate)
        status_diff = canon_status_conflict(source_candidate, candidate)
        if fact_diffs or detail_diffs or status_diff:
            details = []
            if fact_diffs:
                details.append("事实冲突：" + "、".join(str(diff.get("fact") or "") for diff in fact_diffs[:4]))
            if detail_diffs:
                details.append("字段差异：" + "、".join(detail_diffs[:4]))
            if status_diff:
                details.append("原作状态不一致")
            return (
                f"项目目标域存在同分类同名同事实槽冲突（{'; '.join(details)}），"
                f"未覆盖既有条目 {_clean_id(candidate.get('_storage_knowledge_id') or candidate.get('knowledge_id'))}。"
            )

        # Even equivalent content from a different source is not silently
        # merged: one promotion is one immutable project snapshot.
        if not source_slot or not candidate_slot or source_slot == candidate_slot:
            return (
                f"项目已有同分类同名同事实槽知识，来源不同，未覆盖既有条目："
                f"{_clean_id(candidate.get('_storage_knowledge_id') or candidate.get('knowledge_id'))}。"
            )
    return ""


def _sync_project_aliases(conn: sqlite3.Connection, item: dict) -> int:
    """Merge aliases into the project alias group without a destructive full sync."""

    aliases = item.get("aliases")
    if not isinstance(aliases, list):
        return 0
    clean_aliases = list(dict.fromkeys(str(value).strip() for value in aliases if str(value).strip()))
    canonical = _clean_id(item.get("name") or item.get("canonical_name"))
    entity_type = entity_type_for_category(item.get("category"))
    if not clean_aliases or not canonical or not entity_type:
        return 0
    row = conn.execute(
        """
        SELECT alias_group_id, aliases_json FROM entity_alias_groups
        WHERE canonical_name = ? AND entity_type = ? AND story_id IS NULL
          AND COALESCE(worldline_id, '') = ? AND deleted_at IS NULL
        ORDER BY updated_at DESC, alias_group_id LIMIT 1
        """,
        (canonical, entity_type, _normalized_worldline(item.get("worldline_id"))),
    ).fetchone()
    if row is not None:
        existing = _json_object({"aliases": row["aliases_json"]}).get("aliases")
        if not isinstance(existing, list):
            try:
                existing = json.loads(row["aliases_json"] or "[]")
            except (TypeError, ValueError):
                existing = []
        merged = list(dict.fromkeys([str(value).strip() for value in existing if str(value).strip()] + clean_aliases))
        if merged == existing:
            return 0
        conn.execute(
            "UPDATE entity_alias_groups SET aliases_json = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE alias_group_id = ?",
            (json.dumps(merged, ensure_ascii=False, sort_keys=True), row["alias_group_id"]),
        )
        return len(clean_aliases)
    alias_group_id = "alias_project_" + hashlib.sha256(
        f"{entity_type}|{_normalized_name(canonical)}|{_normalized_worldline(item.get('worldline_id'))}|project".encode("utf-8")
    ).hexdigest()[:24]
    conn.execute(
        """
        INSERT INTO entity_alias_groups (
            alias_group_id, canonical_name, aliases_json, entity_type, story_id,
            worldline_id, metadata_json, created_at, updated_at, deleted_at
        ) VALUES (?, ?, ?, ?, NULL, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'), strftime('%Y-%m-%dT%H:%M:%SZ','now'), NULL)
        ON CONFLICT(alias_group_id) DO UPDATE SET
            aliases_json = excluded.aliases_json,
            updated_at = excluded.updated_at,
            deleted_at = NULL
        """,
        (
            alias_group_id,
            canonical,
            json.dumps(clean_aliases, ensure_ascii=False, sort_keys=True),
            entity_type,
            _normalized_worldline(item.get("worldline_id")) or None,
            json.dumps({"source_knowledge_id": _clean_id(item.get("source_story_knowledge_id"))}, ensure_ascii=False),
        ),
    )
    return len(clean_aliases)


def promote_knowledge_to_project(
    project_name: str,
    knowledge_ids: list[str] | None = None,
    attachment_id: str | None = None,
) -> dict:
    """Create immutable project snapshots of confirmed story-import knowledge.

    All source validation and writes happen under one ``BEGIN IMMEDIATE``
    transaction.  A source row is promoted at most once; an existing project
    snapshot is returned as ``already_promoted`` and is never overwritten.
    """

    clean_project = str(project_name or "").strip()
    if not clean_project:
        raise ValueError("项目名称不能为空。")
    db_path = Path(clean_project)
    # ``project_name`` is the public API, not a filesystem path.  The memory
    # facade's project_path performs the same normalization and points at the
    # configured data directory, so import it lazily to avoid path creation.
    from novelforge.services.memory import project_path

    project_db_path = project_path(clean_project).resolve()
    if not (project_db_path / "project.db").is_file():
        raise ValueError(f"项目不存在：{clean_project}")

    promoted: list[dict] = []
    reused: list[dict] = []
    alias_count = 0
    policy: dict = {}
    try:
        # Read the current automatic-review policy once.  The decision is
        # evaluated against each latest story snapshot below; no confirmation
        # or model call is made by this workflow.
        from novelforge.services.memory import load_auto_review_policy

        policy = dict(load_auto_review_policy(clean_project) or {})
    except Exception:
        policy = {}
    try:
        with open_existing_project_db(project_db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            selections = _selected_rows(conn, clean_project, knowledge_ids, attachment_id)
            # One bounded read supplies both idempotency and target-domain
            # quality checks.  Do not scan all project rows once per source.
            project_index = _load_project_index(conn)
            prepared: list[tuple[sqlite3.Row, sqlite3.Row | None, str, dict, sqlite3.Row]] = []
            batch_candidates: list[dict] = []
            for row, attachment, selected_attachment_id in selections:
                item, source = _validate_story_item(conn, row, attachment=attachment)
                source_id = _clean_id(row["knowledge_id"])
                existing = _find_existing_copy(project_index, source_id)
                conflict_reason = ""
                if existing is None:
                    conflict_reason = _blocking_project_conflict(
                        conn,
                        source_item=item,
                        source_knowledge_id=source_id,
                        project_candidates=project_index,
                        batch_candidates=batch_candidates,
                    )
                review_item = {**item, "pending_id": source_id}
                quality_issue_map = {}
                if conflict_reason:
                    quality_issue_map[source_id] = {
                        "types": {"same_name_conflict"},
                        "severity": "高",
                    }
                # The shared confirmation primitive still applies evidence,
                # confidence, category policy, and typed validation.  The
                # issue map is populated from the real target/batch checks;
                # this is not an unconditional empty-map approval path.
                decision = evaluate_pending_auto_review_decision(review_item, quality_issue_map, policy)
                if decision.get("decision") != "confirm":
                    conn.rollback()
                    return {
                        "promoted_count": 0,
                        "already_promoted_count": 0,
                        "items": [],
                        "promoted_items": [],
                        "already_promoted": [],
                        "requested_count": len(selections),
                        "project_name": clean_project,
                        "blocked": True,
                        "blocked_ids": [source_id],
                        "reason": conflict_reason or str(decision.get("reason") or "资料知识未通过自动审核门槛。"),
                    }
                prepared.append((row, attachment, selected_attachment_id, item, source))
                if existing is None:
                    batch_candidates.append(_project_candidate(item))

            for row, attachment, selected_attachment_id, source_item, source in prepared:
                source_id = _clean_id(row["knowledge_id"])
                story_id = _clean_id(row["story_id"])
                existing = _find_existing_copy(project_index, source_id)
                if existing is not None:
                    existing_item = {
                        key: value for key, value in existing.items()
                        if not key.startswith("_")
                    }
                    reused.append({
                        "knowledge_id": _clean_id(existing.get("knowledge_id") or existing.get("id")),
                        "source_story_knowledge_id": source_id,
                        "already_promoted": True,
                        "item": existing_item,
                    })
                    continue

                conflict_reason = _blocking_project_conflict(
                    conn,
                    source_item=source_item,
                    source_knowledge_id=source_id,
                )
                if conflict_reason:
                    conn.rollback()
                    return {
                        "promoted_count": 0,
                        "already_promoted_count": 0,
                        "items": [],
                        "promoted_items": [],
                        "already_promoted": [],
                        "requested_count": len(selections),
                        "project_name": clean_project,
                        "blocked": True,
                        "blocked_ids": [source_id],
                        "reason": conflict_reason,
                    }

                salt = 0
                copy_id = _copy_id(clean_project, story_id, source_id, salt)
                while conn.execute(
                    "SELECT 1 FROM knowledge_items WHERE knowledge_id = ? AND deleted_at IS NULL",
                    (copy_id,),
                ).fetchone() is not None:
                    salt += 1
                    copy_id = _copy_id(clean_project, story_id, source_id, salt)
                category = _clean_id(row["category"])
                payload = _promoted_payload(
                    source_item,
                    project_name=clean_project,
                    story_id=story_id,
                    source_knowledge_id=source_id,
                    copy_id=copy_id,
                    source=source,
                    attachment_id=selected_attachment_id,
                )
                saved, _ = upsert_knowledge_category_item(conn, category, payload)
                alias_count += _sync_project_aliases(conn, saved)
                project_index.append(dict(saved))
                promoted.append({
                    "knowledge_id": copy_id,
                    "source_story_knowledge_id": source_id,
                    "already_promoted": False,
                    "item": saved,
                })
            conn.commit()
    except Exception:
        # The context manager also rolls back, but this explicit rollback is
        # needed for exceptions raised before its __exit__ sees the connection.
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        raise

    if promoted:
        wake_running_knowledge_index_dispatcher(clean_project)
    all_items = [
        {
            **dict(entry.get("item") or {}),
            "already_promoted": bool(entry.get("already_promoted")),
            "source_story_knowledge_id": entry.get("source_story_knowledge_id"),
        }
        for entry in [*promoted, *reused]
    ]
    return {
        "promoted_count": len(promoted),
        "already_promoted_count": len(reused),
        "items": all_items,
        "promoted_items": [dict(entry.get("item") or {}) for entry in promoted],
        "already_promoted": reused,
        "alias_count": alias_count,
        "requested_count": len(all_items),
        "project_name": clean_project,
    }
