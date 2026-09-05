from __future__ import annotations

import json
import re
import sqlite3
from hashlib import sha256
from typing import Any

from .entity_identity import (
    entity_id_for,
    entity_type_for_category,
    isolation_domain,
    merge_policy_for,
    normalize_name,
    supersession_enabled,
)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _chapter_no_from_item(item: dict) -> int | None:
    """Extract the source chapter number from an item, tolerant of its absence.

    Prefers the explicit ``source_chapter_no`` field; falls back to parsing
    ``chapter:{n}`` out of the ``tags`` list (which survives inside content_json).
    """
    raw = item.get("source_chapter_no")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    tags = item.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            text = str(tag or "").strip()
            match = re.match(r"^chapter:(\d+)$", text)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    return None
    return None


def _stable_id(prefix: str, payload: dict, fallback_index: int) -> str:
    raw = _json_dumps(payload)
    digest = sha256(f"{fallback_index}:{raw}".encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _story_id_or_none(conn: sqlite3.Connection, story_id: Any) -> str | None:
    clean_story_id = str(story_id or "").strip()
    if not clean_story_id:
        return None
    row = conn.execute(
        "SELECT story_id FROM stories WHERE story_id = ? AND deleted_at IS NULL",
        (clean_story_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"Knowledge row references an unknown or archived story: {clean_story_id}")
    return clean_story_id


def _item_title(item: dict) -> str:
    for key in ("title", "name", "canonical_name"):
        text = str(item.get(key) or "").strip()
        if text:
            return text
    return ""


def _item_summary(item: dict) -> str:
    for key in ("summary", "description", "content", "value"):
        text = str(item.get(key) or "").strip()
        if text:
            return text[:1000]
    return ""


def _existing_id(conn: sqlite3.Connection, table: str, column: str, value: Any) -> str | None:
    clean_value = str(value or "").strip()
    if not clean_value:
        return None
    if table not in {"source_documents", "source_segments", "retrieval_chunks", "source_revisions"}:
        raise ValueError("Unsupported reference table.")
    row = conn.execute(
        f"SELECT {column} FROM {table} WHERE {column} = ?",
        (clean_value,),
    ).fetchone()
    return clean_value if row else None


def _sync_knowledge_revision(
    conn: sqlite3.Connection,
    *,
    knowledge_id: str,
    item: dict,
    previous_snapshot: str | None,
) -> None:
    snapshot = _json_dumps(item)
    if previous_snapshot == snapshot:
        return
    row = conn.execute(
        "SELECT COALESCE(MAX(revision_no), 0) FROM knowledge_revisions WHERE knowledge_id = ?",
        (knowledge_id,),
    ).fetchone()
    revision_no = int(row[0] or 0) + 1
    revision_id = f"knowledge_revision_{sha256(f'{knowledge_id}|{revision_no}|{snapshot}'.encode('utf-8')).hexdigest()[:24]}"
    source_revision_id = _existing_id(
        conn, "source_revisions", "revision_id", item.get("source_revision_id")
    )
    conn.execute(
        """
        INSERT INTO knowledge_revisions (
            revision_id, knowledge_id, revision_no, change_type, snapshot_json,
            source_revision_id, reason, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        """,
        (
            revision_id,
            knowledge_id,
            revision_no,
            "create" if previous_snapshot is None else "update",
            snapshot,
            source_revision_id,
            str(item.get("revision_reason") or item.get("confirmation_note") or ""),
        ),
    )


def _sync_item_evidence(
    conn: sqlite3.Connection,
    *,
    item: dict,
    knowledge_id: str | None = None,
    pending_id: str | None = None,
) -> None:
    """Persist traceable quotes already carried by knowledge payloads."""

    if "evidence" not in item:
        return
    raw_evidence = item.get("evidence")
    if not isinstance(raw_evidence, list):
        return
    if knowledge_id:
        conn.execute("DELETE FROM knowledge_evidence WHERE knowledge_id = ?", (knowledge_id,))
    if pending_id:
        conn.execute("DELETE FROM knowledge_evidence WHERE pending_id = ?", (pending_id,))
    contexts = item.get("evidence_contexts") if isinstance(item.get("evidence_contexts"), list) else []
    for index, raw_item in enumerate(raw_evidence, start=1):
        if isinstance(raw_item, str):
            raw_item = {"quote": raw_item}
        if not isinstance(raw_item, dict):
            continue
        quote = str(raw_item.get("quote") or "").strip()
        if not quote:
            continue
        positional_context = contexts[index - 1] if index <= len(contexts) and isinstance(contexts[index - 1], dict) else {}
        positional_quote = str(positional_context.get("quote") or "").strip()
        context = positional_context if positional_quote and (positional_quote in quote or quote in positional_quote) else next(
            (
                value for value in contexts
                if isinstance(value, dict)
                and str(value.get("quote") or "").strip()
                and (
                    str(value.get("quote") or "").strip() in quote
                    or quote in str(value.get("quote") or "").strip()
                )
            ),
            {},
        )
        location = {
            key: raw_item.get(key)
            for key in (
                "source_title", "note", "source_url", "source_kind", "authority",
                "content_hash", "location", "source_relative_path", "claim_id", "stance",
            )
            if raw_item.get(key) is not None and raw_item.get(key) != ""
        }
        source_id = _existing_id(
            conn, "source_documents", "source_id", raw_item.get("source_id") or item.get("source_id")
        )
        segment_id = _existing_id(
            conn, "source_segments", "segment_id", raw_item.get("segment_id") or item.get("source_segment_id")
        )
        chunk_id = _existing_id(
            conn, "retrieval_chunks", "chunk_id", raw_item.get("chunk_id") or item.get("source_chunk_id")
        )
        source_revision_id = _existing_id(
            conn, "source_revisions", "revision_id", raw_item.get("source_revision_id") or item.get("source_revision_id")
        )
        if segment_id:
            segment_row = conn.execute(
                "SELECT source_id, source_revision_id FROM source_segments WHERE segment_id = ? AND deleted_at IS NULL",
                (segment_id,),
            ).fetchone()
            if segment_row:
                source_id = str(segment_row[0] or "") or source_id
                source_revision_id = source_revision_id or str(segment_row[1] or "") or None
        if chunk_id:
            chunk_row = conn.execute(
                """
                SELECT doc.source_id, COALESCE(chunk.source_revision_id, doc.source_revision_id)
                FROM retrieval_chunks AS chunk
                JOIN retrieval_documents AS doc ON doc.document_id = chunk.document_id
                WHERE chunk.chunk_id = ? AND chunk.deleted_at IS NULL AND doc.deleted_at IS NULL
                """,
                (chunk_id,),
            ).fetchone()
            if chunk_row:
                chunk_source_id = str(chunk_row[0] or "")
                chunk_revision_id = str(chunk_row[1] or "")
                if source_id and chunk_source_id and source_id != chunk_source_id:
                    chunk_id = None
                else:
                    source_id = source_id or chunk_source_id or None
                    source_revision_id = source_revision_id or chunk_revision_id or None
        if source_revision_id:
            revision_row = conn.execute(
                "SELECT source_id FROM source_revisions WHERE revision_id = ?",
                (source_revision_id,),
            ).fetchone()
            revision_source_id = str(revision_row[0] or "") if revision_row else ""
            if source_id and revision_source_id and source_id != revision_source_id:
                source_revision_id = None
            elif revision_source_id:
                source_id = source_id or revision_source_id

        context_start = context.get("start_offset", context.get("char_index"))
        context_end = context.get("end_offset")
        start_offset = context_start if context_start is not None else raw_item.get("start_offset")
        end_offset = context_end if context_end is not None else raw_item.get("end_offset")
        try:
            start_offset = int(start_offset) if start_offset is not None else None
        except (TypeError, ValueError):
            start_offset = None
        try:
            end_offset = int(end_offset) if end_offset is not None else (start_offset + len(quote) if start_offset is not None else None)
        except (TypeError, ValueError):
            end_offset = start_offset + len(quote) if start_offset is not None else None
        if start_offset is not None and (start_offset < 0 or end_offset is None or end_offset < start_offset):
            start_offset = None
            end_offset = None
        prefix = str(raw_item.get("prefix") or context.get("prefix") or "")[-160:]
        suffix = str(raw_item.get("suffix") or context.get("suffix") or "")[:160]
        quote_hash = sha256(quote.encode("utf-8")).hexdigest()
        requested_validation = str(raw_item.get("validation_status") or "").strip().lower()
        has_stable_provenance = bool(source_revision_id and source_id)
        if start_offset is not None and has_stable_provenance:
            validation_status = requested_validation or "anchored"
        else:
            validation_status = "quote_only"
        owner = knowledge_id or pending_id or "unknown"
        digest = sha256(
            f"{owner}|{index}|{quote}|{_json_dumps(location)}".encode("utf-8")
        ).hexdigest()[:24]
        conn.execute(
            """
            INSERT INTO knowledge_evidence (
                evidence_id, knowledge_id, pending_id, source_id, segment_id,
                chunk_id, quote, location_json, confidence, evidence_strength,
                source_revision_id, quote_hash, start_offset, end_offset, prefix,
                suffix, validation_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(evidence_id) DO UPDATE SET
                knowledge_id = excluded.knowledge_id,
                pending_id = excluded.pending_id,
                source_id = excluded.source_id,
                segment_id = excluded.segment_id,
                chunk_id = excluded.chunk_id,
                quote = excluded.quote,
                location_json = excluded.location_json,
                confidence = excluded.confidence,
                evidence_strength = excluded.evidence_strength,
                source_revision_id = excluded.source_revision_id,
                quote_hash = excluded.quote_hash,
                start_offset = excluded.start_offset,
                end_offset = excluded.end_offset,
                prefix = excluded.prefix,
                suffix = excluded.suffix,
                validation_status = excluded.validation_status
            """,
            (
                f"evidence_{digest}", knowledge_id, pending_id, source_id, segment_id,
                chunk_id, quote, _json_dumps(location),
                _float_or_none(raw_item.get("confidence") if raw_item.get("confidence") is not None else item.get("confidence")),
                _float_or_none(raw_item.get("evidence_strength") if raw_item.get("evidence_strength") is not None else item.get("evidence_strength")),
                source_revision_id, quote_hash, start_offset, end_offset, prefix, suffix,
                validation_status,
            ),
        )


def _compute_entity_fact(category: str, item: dict) -> dict:
    """Compute the Entity-Fact linkage fields for a knowledge item.

    Returns a dict with entity_type, entity_id, fact_key, chapter_no,
    merge_policy, valid_from_chapter. Shared by both write paths so grouping
    and supersession semantics never drift.
    """
    entity_type = entity_type_for_category(category)
    name = str(item.get("name") or item.get("canonical_name") or "").strip()
    entity_id = entity_id_for(entity_type, name, isolation_domain(item)) if entity_type and name else None
    fact_key = str(item.get("setting_field") or item.get("fact_key") or "").strip() or None
    chapter_no = _chapter_no_from_item(item)
    return {
        "entity_type": entity_type,
        "name": name,
        "entity_id": entity_id,
        "fact_key": fact_key,
        "chapter_no": chapter_no,
        "merge_policy": merge_policy_for(fact_key),
        "valid_from_chapter": chapter_no,
    }


def _apply_supersession(
    conn: sqlite3.Connection,
    *,
    entity_id: str,
    fact_key: str | None,
    valid_from_chapter: int | None,
    knowledge_id: str,
) -> None:
    """Invalidate the currently-active fact in the same (entity, fact_key) slot.

    Only fires for replace-policy facts; append-policy and slotless facts are
    left untouched so multiple values can coexist where that is the intended
    semantics.
    """
    if not entity_id or not supersession_enabled(fact_key) or valid_from_chapter is None:
        return
    conn.execute(
        """
        UPDATE knowledge_items
        SET valid_to_chapter = ?, superseded_by = ?,
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE entity_id = ? AND fact_key = ?
          AND knowledge_id != ?
          AND deleted_at IS NULL
          AND valid_to_chapter IS NULL
          AND valid_from_chapter IS NOT NULL
          AND valid_from_chapter < ?
        """,
        (valid_from_chapter, knowledge_id, entity_id, fact_key, knowledge_id, valid_from_chapter),
    )


def sync_knowledge_category(conn: sqlite3.Connection, category: str, items: list[dict]) -> list[dict]:
    clean_category = str(category or "").strip()
    normalized_items = [dict(item) for item in items if isinstance(item, dict)]
    active_ids: list[str] = []
    graph_edges_by_owner = _active_graph_edges_by_owner(conn)
    for index, item in enumerate(normalized_items, start=1):
        knowledge_id = str(item.get("id") or item.get("knowledge_id") or "").strip()
        if not knowledge_id:
            knowledge_id = _stable_id(f"knowledge_{clean_category}", item, index)
        active_ids.append(knowledge_id)
        story_id = _story_id_or_none(conn, item.get("story_id"))
        previous = conn.execute(
            "SELECT content_json FROM knowledge_items WHERE knowledge_id = ?",
            (knowledge_id,),
        ).fetchone()
        previous_snapshot = str(previous[0]) if previous else None
        source_id = _existing_id(conn, "source_documents", "source_id", item.get("source_id"))
        segment_id = _existing_id(
            conn, "source_segments", "segment_id", item.get("source_segment_id") or item.get("segment_id")
        )
        typed_data = item.get("typed_data") if isinstance(item.get("typed_data"), dict) else {}
        ef = _compute_entity_fact(clean_category, item)
        entity_type = ef["entity_type"]
        name = ef["name"]
        entity_id = ef["entity_id"]
        fact_key = ef["fact_key"]
        chapter_no = ef["chapter_no"]
        merge_policy = ef["merge_policy"]
        valid_from_chapter = ef["valid_from_chapter"]

        _apply_supersession(
            conn, entity_id=entity_id, fact_key=fact_key,
            valid_from_chapter=valid_from_chapter, knowledge_id=knowledge_id,
        )
        conn.execute(
            """
            INSERT INTO knowledge_items (
                knowledge_id, story_id, category, name, title, summary, content_json,
                canon_status, worldline_id, worldline_name, confidence, importance,
                evidence_strength, source_id, segment_id, extraction_mode, setting_scope,
                setting_role, injection_policy, status, schema_version, structured_json,
                entity_id, fact_key, chapter_no, valid_from_chapter, valid_to_chapter,
                merge_policy, sequence_order,
                created_at, updated_at, deleted_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, NULL, ?, ?,
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                NULL
            )
            ON CONFLICT(knowledge_id) DO UPDATE SET
                story_id = excluded.story_id,
                category = excluded.category,
                name = excluded.name,
                title = excluded.title,
                summary = excluded.summary,
                content_json = excluded.content_json,
                canon_status = excluded.canon_status,
                worldline_id = excluded.worldline_id,
                worldline_name = excluded.worldline_name,
                confidence = excluded.confidence,
                importance = excluded.importance,
                evidence_strength = excluded.evidence_strength,
                source_id = excluded.source_id,
                segment_id = excluded.segment_id,
                extraction_mode = excluded.extraction_mode,
                setting_scope = excluded.setting_scope,
                setting_role = excluded.setting_role,
                injection_policy = excluded.injection_policy,
                status = excluded.status,
                schema_version = excluded.schema_version,
                structured_json = excluded.structured_json,
                entity_id = excluded.entity_id,
                fact_key = excluded.fact_key,
                chapter_no = excluded.chapter_no,
                valid_from_chapter = excluded.valid_from_chapter,
                merge_policy = excluded.merge_policy,
                sequence_order = excluded.sequence_order,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                deleted_at = NULL
            """,
            (
                knowledge_id,
                story_id,
                clean_category,
                str(item.get("name") or item.get("canonical_name") or "").strip(),
                _item_title(item),
                _item_summary(item),
                _json_dumps(item),
                str(item.get("canon_status") or item.get("scope") or "").strip() or None,
                str(item.get("worldline_id") or "").strip() or None,
                str(item.get("worldline_label") or item.get("worldline_name") or "").strip() or None,
                _float_or_none(item.get("confidence")),
                _float_or_none(item.get("importance")),
                _float_or_none(item.get("evidence_strength")),
                source_id,
                segment_id,
                str(item.get("extraction_mode") or "").strip() or None,
                str(item.get("setting_scope") or "").strip() or None,
                str(item.get("setting_role") or "").strip() or None,
                str(item.get("injection_policy") or "").strip() or None,
                str(item.get("status") or "confirmed"),
                int(item.get("schema_version") or 1),
                _json_dumps(typed_data),
                entity_id,
                fact_key,
                chapter_no,
                valid_from_chapter,
                merge_policy,
                _int_or_none(item.get("sequence_order")),
            ),
        )
        if entity_id:
            _upsert_entity_master(
                conn,
                entity_id=entity_id,
                entity_type=entity_type,
                canonical_name=name,
                item=item,
                story_id=story_id,
            )
        _sync_knowledge_revision(
            conn,
            knowledge_id=knowledge_id,
            item=item,
            previous_snapshot=previous_snapshot,
        )
        # Graph projection is entity-centric: entities is the node set and
        # graph_edges endpoints are entity_id. A knowledge item owns its projected
        # edges (relationship + references); clear previous projections first so
        # edits/category moves cannot leave stale edges.
        _soft_delete_graph_edge_ids(conn, graph_edges_by_owner.pop(knowledge_id, []))
        if clean_category == "relationships":
            _upsert_graph_relationship_edges(
                conn,
                knowledge_id=knowledge_id,
                item=item,
                story_id=story_id,
            )
        else:
            _upsert_entity_reference_edges(
                conn,
                knowledge_id=knowledge_id,
                category=clean_category,
                item=item,
                story_id=story_id,
                source_entity_id=entity_id,
            )
        _sync_item_evidence(conn, item=item, knowledge_id=knowledge_id)
    if active_ids:
        placeholders = ",".join("?" for _ in active_ids)
        conn.execute(
            f"""
            UPDATE knowledge_items
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE category = ? AND knowledge_id NOT IN ({placeholders}) AND deleted_at IS NULL
            """,
            (clean_category, *active_ids),
        )
    else:
        conn.execute(
            """
            UPDATE knowledge_items
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE category = ? AND deleted_at IS NULL
            """,
            (clean_category,),
        )
    if clean_category == "relationships":
        _soft_delete_inactive_graph_edges(conn)
    return normalized_items


def _json_loads_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _json_loads_list(value: Any) -> list:
    if isinstance(value, list):
        return list(value)
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return list(parsed) if isinstance(parsed, list) else []


def _row_value(row: Any, index: int, key: str) -> Any:
    if isinstance(row, sqlite3.Row):
        return row[key]
    return row[index]


def fetch_knowledge_entity_rows(conn: sqlite3.Connection, knowledge_ids: list[str]) -> list[dict]:
    """按 knowledge_id 反查其归属实体的规范名/类型（refactor 2 两段式反查用）。

    只返回 entities 主档仍存在（未 soft delete）且 knowledge 行活跃的结果。
    """
    clean_ids = [str(item) for item in knowledge_ids if str(item)]
    if not clean_ids:
        return []
    rows = conn.execute(
        f"""
        SELECT ki.knowledge_id, e.entity_id, e.canonical_name, e.entity_type,
               e.story_id, e.worldline_id, e.version_scope
        FROM knowledge_items AS ki
        JOIN entities AS e ON e.entity_id = ki.entity_id
        WHERE ki.knowledge_id IN ({", ".join("?" * len(clean_ids))})
          AND ki.deleted_at IS NULL AND e.deleted_at IS NULL
        """,
        tuple(clean_ids),
    ).fetchall()
    items: list[dict] = []
    for row in rows:
        items.append({
            "knowledge_id": _row_value(row, 0, "knowledge_id"),
            "entity_id": _row_value(row, 1, "entity_id"),
            "canonical_name": _row_value(row, 2, "canonical_name"),
            "entity_type": _row_value(row, 3, "entity_type"),
            "story_id": _row_value(row, 4, "story_id"),
            "worldline_id": _row_value(row, 5, "worldline_id"),
            "version_scope": _row_value(row, 6, "version_scope"),
        })
    return items


def load_knowledge_category_rows(conn: sqlite3.Connection, category: str) -> list[dict]:
    clean_category = str(category or "").strip()
    rows = conn.execute(
        """
        SELECT knowledge_id, story_id, category, name, title, summary, content_json,
               canon_status, worldline_id, worldline_name, confidence, importance,
               evidence_strength, extraction_mode, setting_scope, setting_role,
               injection_policy, created_at, updated_at,
               entity_id, fact_key, chapter_no, valid_from_chapter, valid_to_chapter, merge_policy
        FROM knowledge_items
        WHERE category = ? AND deleted_at IS NULL
        ORDER BY created_at, knowledge_id
        """,
        (clean_category,),
    ).fetchall()
    items: list[dict] = []
    for row in rows:
        payload = _json_loads_dict(_row_value(row, 6, "content_json"))
        if not payload:
            keys = [
                "knowledge_id",
                "story_id",
                "category",
                "name",
                "title",
                "summary",
                "content_json",
                "canon_status",
                "worldline_id",
                "worldline_name",
                "confidence",
                "importance",
                "evidence_strength",
                "extraction_mode",
                "setting_scope",
                "setting_role",
                "injection_policy",
                "created_at",
                "updated_at",
            ]
            payload = {
                key: value
                for key, value in zip(keys, row)
                if value is not None and key not in {"content_json", "deleted_at"}
            }
        # Merge the entity-fact columns (added in 017) onto the item so the
        # chapter-scoped validity and slot identity are visible to readers.
        payload["entity_id"] = _row_value(row, 19, "entity_id") or None
        payload["fact_key"] = _row_value(row, 20, "fact_key") or None
        payload["chapter_no"] = _row_value(row, 21, "chapter_no")
        payload["valid_from_chapter"] = _row_value(row, 22, "valid_from_chapter")
        payload["valid_to_chapter"] = _row_value(row, 23, "valid_to_chapter")
        payload["merge_policy"] = _row_value(row, 24, "merge_policy") or "append"
        knowledge_id = _row_value(row, 0, "knowledge_id")
        if "id" not in payload:
            payload["id"] = knowledge_id
        if "knowledge_id" not in payload:
            payload["knowledge_id"] = knowledge_id
        items.append(payload)
    return items


def load_knowledge_revision_rows(conn: sqlite3.Connection, knowledge_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT revision_id, knowledge_id, revision_no, change_type, snapshot_json,
               source_revision_id, reason, created_at
        FROM knowledge_revisions
        WHERE knowledge_id = ?
        ORDER BY revision_no DESC
        """,
        (str(knowledge_id or "").strip(),),
    ).fetchall()
    result: list[dict] = []
    for row in rows:
        values = dict(row) if isinstance(row, sqlite3.Row) else {
            "revision_id": row[0], "knowledge_id": row[1], "revision_no": row[2],
            "change_type": row[3], "snapshot_json": row[4], "source_revision_id": row[5],
            "reason": row[6], "created_at": row[7],
        }
        values["snapshot"] = _json_loads_dict(values.pop("snapshot_json", "{}"))
        result.append(values)
    return result


def load_knowledge_evidence_rows(conn: sqlite3.Connection, knowledge_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT evidence_id, source_id, segment_id, chunk_id, source_revision_id,
               quote, quote_hash, start_offset, end_offset, prefix, suffix,
               validation_status, location_json, confidence, evidence_strength, created_at
        FROM knowledge_evidence
        WHERE knowledge_id = ?
        ORDER BY created_at, evidence_id
        """,
        (str(knowledge_id or "").strip(),),
    ).fetchall()
    result: list[dict] = []
    for row in rows:
        values = dict(row) if isinstance(row, sqlite3.Row) else {}
        values["location"] = _json_loads_dict(values.pop("location_json", "{}"))
        result.append(values)
    return result


def summarize_knowledge_storage_health(conn: sqlite3.Connection) -> dict:
    def scalar(sql: str) -> int:
        row = conn.execute(sql).fetchone()
        return int(row[0] or 0) if row else 0

    return {
        "confirmed_total": scalar("SELECT COUNT(*) FROM knowledge_items WHERE deleted_at IS NULL"),
        "typed_total": scalar("SELECT COUNT(*) FROM knowledge_items WHERE deleted_at IS NULL AND schema_version >= 2 AND structured_json <> '{}'"),
        "evidence_total": scalar("SELECT COUNT(*) FROM knowledge_evidence WHERE knowledge_id IS NOT NULL"),
        "anchored_evidence_total": scalar("SELECT COUNT(*) FROM knowledge_evidence WHERE knowledge_id IS NOT NULL AND validation_status = 'anchored' AND start_offset IS NOT NULL"),
        "source_revision_total": scalar("SELECT COUNT(*) FROM source_revisions"),
        "knowledge_revision_total": scalar("SELECT COUNT(*) FROM knowledge_revisions"),
        "retrieval_chunk_total": scalar("SELECT COUNT(*) FROM retrieval_chunks WHERE deleted_at IS NULL"),
        "fts_chunk_total": scalar("SELECT COUNT(*) FROM retrieval_chunks_fts"),
    }


def upsert_knowledge_category_item(
    conn: sqlite3.Connection,
    category: str,
    item: dict,
) -> tuple[dict, list[dict]]:
    """Serialize a single-item category update to prevent lost writes."""

    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    clean_category = str(category or "").strip()
    normalized = dict(item or {})
    item_id = str(normalized.get("id") or normalized.get("knowledge_id") or "").strip()
    if not clean_category or not item_id:
        raise ValueError("Knowledge category and item ID are required.")
    normalized["id"] = item_id
    previous = conn.execute(
        "SELECT content_json, created_at FROM knowledge_items WHERE knowledge_id = ?",
        (item_id,),
    ).fetchone()
    previous_snapshot = str(previous[0]) if previous else None
    if previous and not normalized.get("created_at"):
        normalized["created_at"] = previous[1]
    normalized.update({
        "id": item_id,
        "knowledge_id": item_id,
        "category": clean_category,
    })
    story_id = _story_id_or_none(conn, normalized.get("story_id"))
    source_id = _existing_id(conn, "source_documents", "source_id", normalized.get("source_id"))
    segment_id = _existing_id(
        conn, "source_segments", "segment_id",
        normalized.get("source_segment_id") or normalized.get("segment_id"),
    )
    typed_data = normalized.get("typed_data") if isinstance(normalized.get("typed_data"), dict) else {}
    ef = _compute_entity_fact(clean_category, normalized)
    entity_type = ef["entity_type"]
    name = ef["name"]
    entity_id = ef["entity_id"]
    fact_key = ef["fact_key"]
    chapter_no = ef["chapter_no"]
    merge_policy = ef["merge_policy"]
    valid_from_chapter = ef["valid_from_chapter"]

    _apply_supersession(
        conn, entity_id=entity_id, fact_key=fact_key,
        valid_from_chapter=valid_from_chapter, knowledge_id=item_id,
    )
    conn.execute(
        """
        INSERT INTO knowledge_items (
            knowledge_id, story_id, category, name, title, summary, content_json,
            canon_status, worldline_id, worldline_name, confidence, importance,
            evidence_strength, source_id, segment_id, extraction_mode, setting_scope,
            setting_role, injection_policy, status, schema_version, structured_json,
            entity_id, fact_key, chapter_no, valid_from_chapter, valid_to_chapter, merge_policy,
            created_at, updated_at, deleted_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, NULL, ?,
            COALESCE(?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL
        )
        ON CONFLICT(knowledge_id) DO UPDATE SET
            story_id=excluded.story_id, category=excluded.category, name=excluded.name,
            title=excluded.title, summary=excluded.summary, content_json=excluded.content_json,
            canon_status=excluded.canon_status, worldline_id=excluded.worldline_id,
            worldline_name=excluded.worldline_name, confidence=excluded.confidence,
            importance=excluded.importance, evidence_strength=excluded.evidence_strength,
            source_id=excluded.source_id, segment_id=excluded.segment_id,
            extraction_mode=excluded.extraction_mode, setting_scope=excluded.setting_scope,
            setting_role=excluded.setting_role, injection_policy=excluded.injection_policy,
            status=excluded.status, schema_version=excluded.schema_version,
            structured_json=excluded.structured_json,
            entity_id=excluded.entity_id, fact_key=excluded.fact_key,
            chapter_no=excluded.chapter_no, valid_from_chapter=excluded.valid_from_chapter,
            merge_policy=excluded.merge_policy,
            updated_at=strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), deleted_at=NULL
        """,
        (
            item_id, story_id, clean_category,
            str(normalized.get("name") or normalized.get("canonical_name") or "").strip(),
            _item_title(normalized), _item_summary(normalized), _json_dumps(normalized),
            str(normalized.get("canon_status") or normalized.get("scope") or "").strip() or None,
            str(normalized.get("worldline_id") or "").strip() or None,
            str(normalized.get("worldline_label") or normalized.get("worldline_name") or "").strip() or None,
            _float_or_none(normalized.get("confidence")), _float_or_none(normalized.get("importance")),
            _float_or_none(normalized.get("evidence_strength")), source_id, segment_id,
            str(normalized.get("extraction_mode") or "").strip() or None,
            str(normalized.get("setting_scope") or "").strip() or None,
            str(normalized.get("setting_role") or "").strip() or None,
            str(normalized.get("injection_policy") or "").strip() or None,
            str(normalized.get("status") or "confirmed"), int(normalized.get("schema_version") or 1),
            _json_dumps(typed_data),
            entity_id, fact_key, chapter_no, valid_from_chapter, merge_policy,
            normalized.get("created_at"),
        ),
    )
    if entity_id:
        _upsert_entity_master(
            conn, entity_id=entity_id, entity_type=entity_type, canonical_name=name,
            item=normalized, story_id=story_id,
        )
    _sync_knowledge_revision(
        conn, knowledge_id=item_id, item=normalized, previous_snapshot=previous_snapshot,
    )
    _soft_delete_graph_edge_ids(conn, _active_graph_edges_by_owner(conn).get(item_id, []))
    if clean_category == "relationships":
        _upsert_graph_relationship_edges(
            conn, knowledge_id=item_id, item=normalized, story_id=story_id,
        )
    else:
        _upsert_entity_reference_edges(
            conn, knowledge_id=item_id, category=clean_category, item=normalized,
            story_id=story_id, source_entity_id=entity_id,
        )
    _sync_item_evidence(conn, item=normalized, knowledge_id=item_id)
    return normalized, load_knowledge_category_rows(conn, clean_category)


def delete_knowledge_category_item(
    conn: sqlite3.Connection,
    category: str,
    item_id: str,
) -> tuple[bool, list[dict]]:
    """Serialize a single-item category delete to prevent lost writes."""

    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    clean_category = str(category or "").strip()
    clean_item_id = str(item_id or "").strip()
    if not clean_category or not clean_item_id:
        return False, load_knowledge_category_rows(conn, clean_category) if clean_category else []
    row = conn.execute(
        "SELECT category FROM knowledge_items WHERE knowledge_id = ? AND category = ? AND deleted_at IS NULL",
        (clean_item_id, clean_category),
    ).fetchone()
    if not row:
        return False, load_knowledge_category_rows(conn, clean_category)
    conn.execute(
        """
        UPDATE knowledge_items
        SET deleted_at=COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
        WHERE knowledge_id=? AND category=? AND deleted_at IS NULL
        """,
        (clean_item_id, clean_category),
    )
    _soft_delete_graph_edge_ids(conn, _active_graph_edges_by_owner(conn).get(clean_item_id, []))
    return True, load_knowledge_category_rows(conn, clean_category)


def _upsert_entity_master(
    conn: sqlite3.Connection,
    *,
    entity_id: str,
    entity_type: str,
    canonical_name: str,
    item: dict,
    story_id: str | None,
) -> None:
    """Create or refresh the entity master row for a fact's owning entity.

    Only additive: it never deletes or rewrites history. The summary is the
    fact's summary (the most recently written fact becomes the current summary);
    importance is carried over when the incoming item has one.
    """
    if not entity_id or not entity_type or not canonical_name:
        return
    domain = isolation_domain(item)
    setting_scope, entity_story_id, worldline_id, version_scope = domain
    summary = str(item.get("summary") or item.get("name") or "").strip()
    importance = _float_or_none(item.get("importance"))
    if importance is None:
        importance = 0
    display_name = str(item.get("display_name") or canonical_name).strip() or canonical_name
    # Event entities carry a world-time sort key (world_t) and human label.
    world_t = None
    world_time_label = None
    if entity_type == "event":
        details = item.get("details", {}) if isinstance(item.get("details"), dict) else {}
        typed_data = item.get("typed_data", {}) if isinstance(item.get("typed_data"), dict) else {}
        raw_t = item.get("world_t") or typed_data.get("world_t")
        if raw_t is not None:
            try:
                world_t = float(raw_t)
            except (TypeError, ValueError):
                world_t = None
        if world_t is None:
            chapter = _chapter_no_from_item(item)
            if chapter is not None:
                world_t = float(chapter)
        label = (
            item.get("time")
            or typed_data.get("time")
            or details.get("time")
            or details.get("时间")
        )
        if label:
            world_time_label = str(label).strip()[:80]
    conn.execute(
        """
        INSERT INTO entities (
            entity_id, entity_type, canonical_name, display_name, story_id, worldline_id,
            setting_scope, version_scope, summary, importance,
            world_t, world_time_label,
            created_at, updated_at, deleted_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            NULL
        )
        ON CONFLICT(entity_id) DO UPDATE SET
            canonical_name = excluded.canonical_name,
            display_name = excluded.display_name,
            summary = CASE WHEN excluded.summary != '' THEN excluded.summary ELSE entities.summary END,
            importance = COALESCE(excluded.importance, entities.importance),
            world_t = COALESCE(excluded.world_t, entities.world_t),
            world_time_label = COALESCE(excluded.world_time_label, entities.world_time_label),
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            deleted_at = NULL
        """,
        (
            entity_id, entity_type, canonical_name, display_name,
            entity_story_id or None, worldline_id or None,
            setting_scope or "project", version_scope or "project_main",
            summary, importance, world_t, world_time_label,
        ),
    )


def _resolve_entity_id(
    conn: sqlite3.Connection,
    *,
    name: str,
    entity_type: str,
    story_id: str | None,
    worldline_id: str | None = None,
    setting_scope: str = "story",
    version_scope: str = "project_main",
) -> str | None:
    """Resolve an entity name to an entity_id, creating the master row if absent.

    Matches an existing entity by normalized name within the same entity_type and
    isolation domain first (so "林越" and "林公子" only merge if they are the same
    type and continuity); otherwise creates a deterministic entity_id and master.
    """
    clean_name = str(name or "").strip()
    if not clean_name:
        return None
    domain = (setting_scope, story_id or "", worldline_id or "", version_scope or "project_main")
    # Look for an existing entity with the same normalized name + type + domain.
    normalized = normalize_name(clean_name)
    if normalized:
        rows = conn.execute(
            "SELECT entity_id, canonical_name FROM entities WHERE entity_type = ? AND deleted_at IS NULL",
            (entity_type,),
        ).fetchall()
        for entity_id, canonical in rows:
            if normalize_name(canonical) == normalized:
                # domain must also match (story/worldline/scope).
                edom = conn.execute(
                    "SELECT setting_scope, story_id, worldline_id FROM entities WHERE entity_id = ?",
                    (entity_id,),
                ).fetchone()
                if edom:
                    existing_domain = (edom[0] or "project", edom[1] or "", edom[2] or "", version_scope or "project_main")
                    if existing_domain == domain:
                        return entity_id
    eid = entity_id_for(entity_type, clean_name, domain)
    conn.execute(
        """
        INSERT INTO entities (
            entity_id, entity_type, canonical_name, display_name, story_id, worldline_id,
            setting_scope, version_scope, summary, importance, created_at, updated_at, deleted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', 0,
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL)
        ON CONFLICT(entity_id) DO UPDATE SET deleted_at = NULL
        """,
        (eid, entity_type, clean_name, clean_name, story_id or None, worldline_id or None, setting_scope, version_scope or "project_main"),
    )
    return eid


def _relationship_fields(item: dict) -> tuple[str, str, str]:
    details = item.get("details", {}) if isinstance(item.get("details"), dict) else {}
    typed_data = item.get("typed_data", {}) if isinstance(item.get("typed_data"), dict) else {}
    source = (
        item.get("source")
        or item.get("from")
        or item.get("subject")
        or item.get("character_a")
        or item.get("person_a")
        or typed_data.get("subject")
        or typed_data.get("source")
        or details.get("source")
        or details.get("from")
        or details.get("subject")
        or details.get("character_a")
        or details.get("角色A")
        or details.get("人物A")
    )
    target = (
        item.get("target")
        or item.get("to")
        or item.get("object")
        or item.get("character_b")
        or item.get("person_b")
        or typed_data.get("object")
        or typed_data.get("target")
        or details.get("target")
        or details.get("to")
        or details.get("object")
        or details.get("character_b")
        or details.get("角色B")
        or details.get("人物B")
    )
    relation = (
        item.get("relation")
        or item.get("relationship")
        or item.get("relation_type")
        or item.get("type")
        or typed_data.get("relation_type")
        or typed_data.get("relation")
        or details.get("relation")
        or details.get("relationship")
        or details.get("关系")
        or item.get("summary")
        or item.get("name")
    )
    if not source or not target:
        source, target, inferred_relation = _infer_relationship_from_text(item)
        relation = relation or inferred_relation
    return str(source or "").strip(), str(target or "").strip(), str(relation or "related_to").strip()


def _infer_relationship_from_text(item: dict) -> tuple[str, str, str]:
    text = "\n".join(
        str(value or "")
        for value in (item.get("name"), item.get("summary"), item.get("content"))
        if str(value or "").strip()
    )
    if not text:
        return "", "", ""
    for separator in ("->", "→", "=>", "—", "-", "：", ":"):
        if separator not in text:
            continue
        left, right = text.split(separator, 1)
        left = left.strip()
        right = right.strip()
        if not left or not right:
            continue
        relation = ""
        match = re.match(r"(.+?)[是为属于拥有师承敌对同盟相关]+(.+)", right)
        if match:
            relation = right
            right = match.group(1).strip() or right
        return left[:80], right[:80], relation or "related_to"
    return "", "", ""


def _soft_delete_graph_edge_ids(conn: sqlite3.Connection, edge_ids: list[str]) -> None:
    clean_ids = [str(edge_id).strip() for edge_id in edge_ids if str(edge_id).strip()]
    if not clean_ids:
        return
    placeholders = ",".join("?" for _ in clean_ids)
    conn.execute(
        f"""
        UPDATE graph_edges
        SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE edge_id IN ({placeholders}) AND deleted_at IS NULL
        """,
        tuple(clean_ids),
    )


def _active_graph_edge_owners(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    owners: list[tuple[str, str]] = []
    rows = conn.execute(
        "SELECT edge_id, metadata_json FROM graph_edges WHERE deleted_at IS NULL"
    ).fetchall()
    for row in rows:
        metadata = _json_loads_dict(row[1])
        knowledge_id = str(metadata.get("knowledge_id") or "").strip()
        if knowledge_id:
            owners.append((str(row[0]), knowledge_id))
    return owners


def _active_graph_edges_by_owner(conn: sqlite3.Connection) -> dict[str, list[str]]:
    by_owner: dict[str, list[str]] = {}
    for edge_id, owner_id in _active_graph_edge_owners(conn):
        by_owner.setdefault(owner_id, []).append(edge_id)
    return by_owner


def _soft_delete_inactive_graph_edges(conn: sqlite3.Connection) -> None:
    """Soft-delete orphaned relationship edges (not reference edges).

    Reference edges (metadata carries `reference_field`) are owned by their
    originating knowledge item and are cleaned by the per-item logic; they must
    not be swept here. This function only reaps relationship-projection edges
    whose owning relationship item is gone.
    """
    active_relationship_ids = {
        str(row[0])
        for row in conn.execute(
            """
            SELECT knowledge_id
            FROM knowledge_items
            WHERE category = 'relationships' AND deleted_at IS NULL
            """
        ).fetchall()
    }
    stale_relationship_edges: list[str] = []
    rows = conn.execute(
        "SELECT edge_id, metadata_json FROM graph_edges WHERE deleted_at IS NULL"
    ).fetchall()
    for row in rows:
        metadata = _json_loads_dict(row[1])
        if metadata.get("reference_field"):
            continue  # reference edge, owned by its item, not a relationship projection
        owner_id = str(metadata.get("knowledge_id") or "").strip()
        if owner_id and owner_id not in active_relationship_ids:
            stale_relationship_edges.append(str(row[0]))
    _soft_delete_graph_edge_ids(conn, stale_relationship_edges)


def _upsert_graph_relationship_edges(
    conn: sqlite3.Connection,
    *,
    knowledge_id: str,
    item: dict,
    story_id: str | None,
) -> None:
    source_name, target_name, relation = _relationship_fields(item)
    if not source_name or not target_name:
        return
    worldline_id = str(item.get("worldline_id") or "").strip() or None
    setting_scope = str(item.get("setting_scope") or "story").strip() or "story"
    version_scope = str(item.get("version_scope") or "project_main").strip() or "project_main"
    # Relationship endpoints are bare names; resolve them to entities (character
    # is the default; organization relationships resolve by existing entity).
    source_node_id = _resolve_entity_id(
        conn, name=source_name, entity_type="character",
        story_id=story_id, worldline_id=worldline_id, setting_scope=setting_scope,
        version_scope=version_scope,
    )
    target_node_id = _resolve_entity_id(
        conn, name=target_name, entity_type="character",
        story_id=story_id, worldline_id=worldline_id, setting_scope=setting_scope,
        version_scope=version_scope,
    )
    if not source_node_id or not target_node_id:
        return
    relation_type = re.sub(r"\s+", "_", relation.lower())[:80] or "related_to"
    typed_data = item.get("typed_data", {}) if isinstance(item.get("typed_data"), dict) else {}
    raw_direction = str(item.get("direction") or typed_data.get("direction") or "directed").strip().lower()
    direction = raw_direction if raw_direction in {"directed", "bidirectional", "undirected"} else "directed"
    edge_id_source = f"{knowledge_id}:{source_node_id}:{target_node_id}:{relation_type}:{direction}"
    edge_id = "edge_" + sha256(edge_id_source.encode("utf-8")).hexdigest()[:24]
    conn.execute(
        """
        INSERT INTO graph_edges (
            edge_id, story_id, source_node_id, target_node_id, relation_type,
            direction, confidence, evidence_id, metadata_json, created_at, updated_at, deleted_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, NULL, ?,
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            NULL
        )
        ON CONFLICT(edge_id) DO UPDATE SET
            story_id = excluded.story_id,
            source_node_id = excluded.source_node_id,
            target_node_id = excluded.target_node_id,
            relation_type = excluded.relation_type,
            direction = excluded.direction,
            confidence = excluded.confidence,
            metadata_json = excluded.metadata_json,
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            deleted_at = NULL
        """,
        (
            edge_id,
            story_id,
            source_node_id,
            target_node_id,
            relation_type,
            direction,
            _float_or_none(item.get("confidence")),
            _json_dumps({"knowledge_id": knowledge_id, "item": item}),
        ),
    )


# Reference-field -> (relation_type, target_entity_type). When a knowledge item
# carries one of these list fields, each value becomes a graph edge from the
# item's owning entity to the referenced entity.
_REFERENCE_FIELD_SPECS: dict[str, tuple[str, str]] = {
    "owners": ("owns", "character"),
    "users": ("wields", "character"),
    "leaders": ("leads", "character"),
    "members": ("member_of", "character"),
    "inhabitants": ("inhabits", "character"),
    "participants": ("participated_in", "character"),
    "affiliations": ("affiliated_with", "organization"),
    "parent_location": ("located_in", "location"),
    "relations": ("related_to", "organization"),
}


def _upsert_entity_reference_edges(
    conn: sqlite3.Connection,
    *,
    knowledge_id: str,
    category: str,
    item: dict,
    story_id: str | None,
    source_entity_id: str | None,
) -> None:
    """Project an item's reference fields (owners/members/participants/...) into graph edges.

    The source endpoint is the item's owning entity (already computed by the
    caller); each referenced name resolves to a target entity via _resolve_entity_id.
    Reference fields are additive — edges are keyed by (knowledge_id, field, value).
    """
    if not source_entity_id:
        return
    worldline_id = str(item.get("worldline_id") or "").strip() or None
    setting_scope = str(item.get("setting_scope") or "story").strip() or "story"
    version_scope = str(item.get("version_scope") or "project_main").strip() or "project_main"
    details = item.get("details", {}) if isinstance(item.get("details"), dict) else {}
    typed_data = item.get("typed_data", {}) if isinstance(item.get("typed_data"), dict) else {}
    for field, (relation_type, target_type) in _REFERENCE_FIELD_SPECS.items():
        raw_values = item.get(field) or typed_data.get(field) or details.get(field)
        if not isinstance(raw_values, list):
            if raw_values:
                raw_values = [raw_values]
            else:
                continue
        for value in raw_values:
            target_name = str(value or "").strip()
            if not target_name:
                continue
            # parent_location is a single-value location reference.
            target_entity_id = _resolve_entity_id(
                conn, name=target_name, entity_type=target_type,
                story_id=story_id, worldline_id=worldline_id, setting_scope=setting_scope,
                version_scope=version_scope,
            )
            if not target_entity_id or target_entity_id == source_entity_id:
                continue
            edge_id_source = f"{knowledge_id}:{field}:{target_entity_id}"
            edge_id = "edge_" + sha256(edge_id_source.encode("utf-8")).hexdigest()[:24]
            conn.execute(
                """
                INSERT INTO graph_edges (
                    edge_id, story_id, source_node_id, target_node_id, relation_type,
                    direction, confidence, evidence_id, metadata_json, created_at, updated_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, 'directed', ?, NULL, ?,
                    strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                    strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL)
                ON CONFLICT(edge_id) DO UPDATE SET
                    story_id = excluded.story_id,
                    source_node_id = excluded.source_node_id,
                    target_node_id = excluded.target_node_id,
                    relation_type = excluded.relation_type,
                    metadata_json = excluded.metadata_json,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                    deleted_at = NULL
                """,
                (
                    edge_id, story_id, source_entity_id, target_entity_id, relation_type,
                    _float_or_none(item.get("confidence")),
                    _json_dumps({"knowledge_id": knowledge_id, "reference_field": field}),
                ),
            )


def sync_pending_knowledge(conn: sqlite3.Connection, items: list[dict]) -> list[dict]:
    normalized_items = [dict(item) for item in items if isinstance(item, dict)]
    active_ids: list[str] = []
    for index, item in enumerate(normalized_items, start=1):
        pending_id = str(item.get("pending_id") or "").strip()
        if not pending_id:
            pending_id = _stable_id("pending", item, index)
        active_ids.append(pending_id)
        category = str(item.get("category") or "").strip()
        story_id = _story_id_or_none(conn, item.get("story_id"))
        source_id = _existing_id(conn, "source_documents", "source_id", item.get("source_id"))
        segment_id = _existing_id(
            conn, "source_segments", "segment_id", item.get("source_segment_id") or item.get("segment_id")
        )
        source_revision_id = _existing_id(
            conn, "source_revisions", "revision_id", item.get("source_revision_id")
        )
        typed_data = item.get("typed_data") if isinstance(item.get("typed_data"), dict) else {}
        quality_payload = {
            key: item.get(key)
            for key in ("quality", "quality_issues", "risk_label", "risk_reasons")
            if key in item
        }
        conn.execute(
            """
            INSERT INTO pending_knowledge_items (
                pending_id, story_id, category, name, title, summary, content_json,
                canon_status, worldline_id, confidence, importance, evidence_strength,
                source_id, segment_id, extraction_mode, quality_json, status,
                schema_version, structured_json, source_revision_id,
                created_at, updated_at, deleted_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                NULL
            )
            ON CONFLICT(pending_id) DO UPDATE SET
                story_id = excluded.story_id,
                category = excluded.category,
                name = excluded.name,
                title = excluded.title,
                summary = excluded.summary,
                content_json = excluded.content_json,
                canon_status = excluded.canon_status,
                worldline_id = excluded.worldline_id,
                confidence = excluded.confidence,
                importance = excluded.importance,
                evidence_strength = excluded.evidence_strength,
                source_id = excluded.source_id,
                segment_id = excluded.segment_id,
                extraction_mode = excluded.extraction_mode,
                quality_json = excluded.quality_json,
                status = excluded.status,
                schema_version = excluded.schema_version,
                structured_json = excluded.structured_json,
                source_revision_id = excluded.source_revision_id,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                deleted_at = NULL
            """,
            (
                pending_id,
                story_id,
                category,
                str(item.get("name") or item.get("canonical_name") or "").strip(),
                _item_title(item),
                _item_summary(item),
                _json_dumps(item),
                str(item.get("canon_status") or item.get("scope") or "").strip() or None,
                str(item.get("worldline_id") or "").strip() or None,
                _float_or_none(item.get("confidence")),
                _float_or_none(item.get("importance")),
                _float_or_none(item.get("evidence_strength")),
                source_id,
                segment_id,
                str(item.get("extraction_mode") or "").strip() or None,
                _json_dumps(quality_payload),
                str(item.get("status") or "pending"),
                int(item.get("schema_version") or 1),
                _json_dumps(typed_data),
                source_revision_id,
            ),
        )
        _sync_item_evidence(conn, item=item, pending_id=pending_id)
    if active_ids:
        placeholders = ",".join("?" for _ in active_ids)
        conn.execute(
            f"""
            UPDATE pending_knowledge_items
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE pending_id NOT IN ({placeholders}) AND deleted_at IS NULL
            """,
            tuple(active_ids),
        )
        conn.execute(
            f"DELETE FROM knowledge_evidence WHERE pending_id IS NOT NULL AND pending_id NOT IN ({placeholders})",
            tuple(active_ids),
        )
    else:
        conn.execute(
            """
            UPDATE pending_knowledge_items
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE deleted_at IS NULL
            """
        )
        conn.execute("DELETE FROM knowledge_evidence WHERE pending_id IS NOT NULL")
    return normalized_items


def load_pending_knowledge_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT pending_id, story_id, category, name, title, summary, content_json,
               canon_status, worldline_id, confidence, importance, evidence_strength,
               extraction_mode, quality_json, status, created_at, updated_at
        FROM pending_knowledge_items
        WHERE deleted_at IS NULL
        ORDER BY created_at, pending_id
        """
    ).fetchall()
    items: list[dict] = []
    for row in rows:
        payload = _json_loads_dict(_row_value(row, 6, "content_json"))
        if not payload:
            quality = _json_loads_dict(_row_value(row, 13, "quality_json"))
            payload = {
                "pending_id": _row_value(row, 0, "pending_id"),
                "story_id": _row_value(row, 1, "story_id"),
                "category": _row_value(row, 2, "category"),
                "name": _row_value(row, 3, "name"),
                "title": _row_value(row, 4, "title"),
                "summary": _row_value(row, 5, "summary"),
                "canon_status": _row_value(row, 7, "canon_status"),
                "worldline_id": _row_value(row, 8, "worldline_id"),
                "confidence": _row_value(row, 9, "confidence"),
                "importance": _row_value(row, 10, "importance"),
                "evidence_strength": _row_value(row, 11, "evidence_strength"),
                "extraction_mode": _row_value(row, 12, "extraction_mode"),
                "status": _row_value(row, 14, "status"),
            }
            payload.update(quality)
            payload = {key: value for key, value in payload.items() if value is not None}
        pending_id = _row_value(row, 0, "pending_id")
        if "pending_id" not in payload:
            payload["pending_id"] = pending_id
        items.append(payload)
    return items


def upsert_pending_knowledge_items(
    conn: sqlite3.Connection,
    items: list[dict],
) -> tuple[int, list[dict]]:
    """Merge pending candidates under a write lock instead of replacing peers."""

    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    current = load_pending_knowledge_rows(conn)
    index_by_id = {
        str(item.get("pending_id") or ""): index
        for index, item in enumerate(current)
        if str(item.get("pending_id") or "").strip()
    }
    added_count = 0
    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        pending_id = str(item.get("pending_id") or "").strip()
        if not pending_id:
            raise ValueError("Pending knowledge ID cannot be empty.")
        existing_index = index_by_id.get(pending_id)
        if existing_index is None:
            current.append(item)
            index_by_id[pending_id] = len(current) - 1
            added_count += 1
            continue
        existing = current[existing_index]
        item["queued_at"] = existing.get("queued_at") or item.get("queued_at")
        current[existing_index] = item
    sync_pending_knowledge(conn, current)
    return added_count, current


def delete_pending_knowledge_items(
    conn: sqlite3.Connection,
    pending_ids: set[str],
) -> tuple[int, list[dict]]:
    """Delete selected pending candidates under a serialized write lock."""

    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    clean_ids = {str(item or "").strip() for item in pending_ids if str(item or "").strip()}
    current = load_pending_knowledge_rows(conn)
    if not clean_ids:
        return 0, current
    remaining = [item for item in current if str(item.get("pending_id") or "") not in clean_ids]
    removed_count = len(current) - len(remaining)
    if removed_count:
        sync_pending_knowledge(conn, remaining)
    return removed_count, remaining


def sync_entity_alias_groups(conn: sqlite3.Connection, items: list[dict]) -> list[dict]:
    normalized_items = [dict(item) for item in items if isinstance(item, dict)]
    active_ids: list[str] = []
    for index, item in enumerate(normalized_items, start=1):
        alias_group_id = str(item.get("alias_group_id") or item.get("id") or "").strip()
        if not alias_group_id:
            alias_group_id = _stable_id("alias_group", item, index)
        active_ids.append(alias_group_id)
        aliases = item.get("aliases", [])
        if not isinstance(aliases, list):
            aliases = []
        story_id = _story_id_or_none(conn, item.get("story_id"))
        conn.execute(
            """
            INSERT INTO entity_alias_groups (
                alias_group_id, canonical_name, aliases_json, entity_type, story_id,
                worldline_id, metadata_json, created_at, updated_at, deleted_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                NULL
            )
            ON CONFLICT(alias_group_id) DO UPDATE SET
                canonical_name = excluded.canonical_name,
                aliases_json = excluded.aliases_json,
                entity_type = excluded.entity_type,
                story_id = excluded.story_id,
                worldline_id = excluded.worldline_id,
                metadata_json = excluded.metadata_json,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                deleted_at = NULL
            """,
            (
                alias_group_id,
                str(item.get("canonical_name") or item.get("name") or "").strip(),
                _json_dumps(aliases),
                str(item.get("entity_type") or item.get("category") or "").strip() or None,
                story_id,
                str(item.get("worldline_id") or "").strip() or None,
                _json_dumps(item),
            ),
        )
    if active_ids:
        placeholders = ",".join("?" for _ in active_ids)
        conn.execute(
            f"""
            UPDATE entity_alias_groups
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE alias_group_id NOT IN ({placeholders}) AND deleted_at IS NULL
            """,
            tuple(active_ids),
        )
    else:
        conn.execute(
            """
            UPDATE entity_alias_groups
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE deleted_at IS NULL
            """
        )
    return normalized_items


def load_entity_alias_group_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT alias_group_id, canonical_name, aliases_json, entity_type, story_id,
               worldline_id, metadata_json, created_at, updated_at
        FROM entity_alias_groups
        WHERE deleted_at IS NULL
        ORDER BY created_at, alias_group_id
        """
    ).fetchall()
    items: list[dict] = []
    for row in rows:
        payload = _json_loads_dict(_row_value(row, 6, "metadata_json"))
        if not payload:
            payload = {}
        alias_group_id = _row_value(row, 0, "alias_group_id")
        payload.setdefault("id", alias_group_id)
        payload.setdefault("alias_group_id", alias_group_id)
        payload.setdefault("canonical_name", _row_value(row, 1, "canonical_name"))
        payload.setdefault("aliases", _json_loads_list(_row_value(row, 2, "aliases_json")))
        entity_type = _row_value(row, 3, "entity_type")
        story_id = _row_value(row, 4, "story_id")
        worldline_id = _row_value(row, 5, "worldline_id")
        if entity_type is not None and "entity_type" not in payload:
            payload["entity_type"] = entity_type
        if story_id is not None and "story_id" not in payload:
            payload["story_id"] = story_id
        if worldline_id is not None and "worldline_id" not in payload:
            payload["worldline_id"] = worldline_id
        items.append(payload)
    return items
