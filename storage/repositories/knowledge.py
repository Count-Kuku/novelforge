from __future__ import annotations

import json
import re
import sqlite3
from hashlib import sha256
from typing import Any


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
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
    for index, raw_item in enumerate(raw_evidence, start=1):
        if isinstance(raw_item, str):
            raw_item = {"quote": raw_item}
        if not isinstance(raw_item, dict):
            continue
        quote = str(raw_item.get("quote") or "").strip()
        if not quote:
            continue
        location = {
            key: raw_item.get(key)
            for key in (
                "source_title",
                "note",
                "source_url",
                "source_kind",
                "authority",
                "content_hash",
                "location",
                "source_relative_path",
                "claim_id",
                "stance",
            )
            if raw_item.get(key) is not None and raw_item.get(key) != ""
        }
        owner = knowledge_id or pending_id or "unknown"
        digest = sha256(
            f"{owner}|{index}|{quote}|{_json_dumps(location)}".encode("utf-8")
        ).hexdigest()[:24]
        conn.execute(
            """
            INSERT INTO knowledge_evidence (
                evidence_id, knowledge_id, pending_id, source_id, segment_id,
                chunk_id, quote, location_json, confidence, evidence_strength
            )
            VALUES (?, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?)
            ON CONFLICT(evidence_id) DO UPDATE SET
                knowledge_id = excluded.knowledge_id,
                pending_id = excluded.pending_id,
                quote = excluded.quote,
                location_json = excluded.location_json,
                confidence = excluded.confidence,
                evidence_strength = excluded.evidence_strength
            """,
            (
                f"evidence_{digest}",
                knowledge_id,
                pending_id,
                quote,
                _json_dumps(location),
                _float_or_none(
                    raw_item.get("confidence")
                    if raw_item.get("confidence") is not None
                    else item.get("confidence")
                ),
                _float_or_none(
                    raw_item.get("evidence_strength")
                    if raw_item.get("evidence_strength") is not None
                    else item.get("evidence_strength")
                ),
            ),
        )


def sync_knowledge_category(conn: sqlite3.Connection, category: str, items: list[dict]) -> list[dict]:
    clean_category = str(category or "").strip()
    normalized_items = [dict(item) for item in items if isinstance(item, dict)]
    active_ids: list[str] = []
    for index, item in enumerate(normalized_items, start=1):
        knowledge_id = str(item.get("id") or item.get("knowledge_id") or "").strip()
        if not knowledge_id:
            knowledge_id = _stable_id(f"knowledge_{clean_category}", item, index)
        active_ids.append(knowledge_id)
        story_id = _story_id_or_none(conn, item.get("story_id"))
        conn.execute(
            """
            INSERT INTO knowledge_items (
                knowledge_id, story_id, category, name, title, summary, content_json,
                canon_status, worldline_id, worldline_name, confidence, importance,
                evidence_strength, source_id, segment_id, extraction_mode, setting_scope,
                setting_role, injection_policy, created_at, updated_at, deleted_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?,
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
                extraction_mode = excluded.extraction_mode,
                setting_scope = excluded.setting_scope,
                setting_role = excluded.setting_role,
                injection_policy = excluded.injection_policy,
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
                str(item.get("extraction_mode") or "").strip() or None,
                str(item.get("setting_scope") or "").strip() or None,
                str(item.get("setting_role") or "").strip() or None,
                str(item.get("injection_policy") or "").strip() or None,
            ),
        )
        _upsert_graph_node_for_knowledge(
            conn,
            knowledge_id=knowledge_id,
            category=clean_category,
            item=item,
            story_id=story_id,
        )
        if clean_category == "relationships":
            _upsert_graph_relationship_edges(
                conn,
                knowledge_id=knowledge_id,
                item=item,
                story_id=story_id,
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
        conn.execute(
            f"""
            UPDATE graph_nodes
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE knowledge_id IN (
                SELECT knowledge_id FROM knowledge_items
                WHERE category = ? AND knowledge_id NOT IN ({placeholders})
            )
              AND deleted_at IS NULL
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
        conn.execute(
            """
            UPDATE graph_nodes
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE knowledge_id IN (
                SELECT knowledge_id FROM knowledge_items WHERE category = ?
            )
              AND deleted_at IS NULL
            """,
            (clean_category,),
        )
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


def load_knowledge_category_rows(conn: sqlite3.Connection, category: str) -> list[dict]:
    clean_category = str(category or "").strip()
    rows = conn.execute(
        """
        SELECT knowledge_id, story_id, category, name, title, summary, content_json,
               canon_status, worldline_id, worldline_name, confidence, importance,
               evidence_strength, extraction_mode, setting_scope, setting_role,
               injection_policy, created_at, updated_at
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
        knowledge_id = _row_value(row, 0, "knowledge_id")
        if "id" not in payload:
            payload["id"] = knowledge_id
        if "knowledge_id" not in payload:
            payload["knowledge_id"] = knowledge_id
        items.append(payload)
    return items


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
    items = load_knowledge_category_rows(conn, clean_category)
    replaced = False
    for index, existing in enumerate(items):
        existing_id = str(existing.get("id") or existing.get("knowledge_id") or "").strip()
        if existing_id != item_id:
            continue
        normalized["created_at"] = existing.get("created_at") or normalized.get("created_at")
        items[index] = normalized
        replaced = True
        break
    if not replaced:
        items.append(normalized)
    sync_knowledge_category(conn, clean_category, items)
    return normalized, items


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
    items = load_knowledge_category_rows(conn, clean_category)
    remaining = [
        item for item in items
        if str(item.get("id") or item.get("knowledge_id") or "").strip() != clean_item_id
    ]
    if len(remaining) == len(items):
        return False, items
    sync_knowledge_category(conn, clean_category, remaining)
    return True, remaining


def _graph_node_type_for_category(category: str) -> str:
    return {
        "characters": "character",
        "items": "item",
        "abilities": "ability",
        "world_rules": "world_rule",
        "locations": "location",
        "organizations": "organization",
        "timeline_events": "event",
        "relationships": "relationship",
        "writing_style": "style",
        "dialogue_style": "style",
        "narrative_techniques": "style",
        "constraints": "constraint",
    }.get(category, "knowledge")


def _upsert_graph_node_for_knowledge(
    conn: sqlite3.Connection,
    *,
    knowledge_id: str,
    category: str,
    item: dict,
    story_id: str | None,
) -> str | None:
    name = str(item.get("name") or item.get("canonical_name") or item.get("title") or "").strip()
    if not name:
        return None
    node_id = f"knowledge_node_{knowledge_id}"
    conn.execute(
        """
        INSERT INTO graph_nodes (
            node_id, story_id, node_type, canonical_name, display_name,
            knowledge_id, alias_group_id, canon_status, worldline_id,
            metadata_json, created_at, updated_at, deleted_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?,
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            NULL
        )
        ON CONFLICT(node_id) DO UPDATE SET
            story_id = excluded.story_id,
            node_type = excluded.node_type,
            canonical_name = excluded.canonical_name,
            display_name = excluded.display_name,
            knowledge_id = excluded.knowledge_id,
            canon_status = excluded.canon_status,
            worldline_id = excluded.worldline_id,
            metadata_json = excluded.metadata_json,
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            deleted_at = NULL
        """,
        (
            node_id,
            story_id,
            _graph_node_type_for_category(category),
            name,
            name,
            knowledge_id,
            str(item.get("canon_status") or item.get("scope") or "").strip() or None,
            str(item.get("worldline_id") or "").strip() or None,
            _json_dumps({"category": category, "item": item}),
        ),
    )
    return node_id


def _entity_node_id(name: str) -> str:
    digest = sha256(name.strip().lower().encode("utf-8")).hexdigest()[:24]
    return f"entity_node_{digest}"


def _upsert_named_entity_node(
    conn: sqlite3.Connection,
    *,
    name: str,
    story_id: str | None,
    worldline_id: str | None,
    canon_status: str | None,
) -> str | None:
    clean_name = str(name or "").strip()
    if not clean_name:
        return None
    node_id = _entity_node_id(clean_name)
    conn.execute(
        """
        INSERT INTO graph_nodes (
            node_id, story_id, node_type, canonical_name, display_name,
            knowledge_id, alias_group_id, canon_status, worldline_id,
            metadata_json, created_at, updated_at, deleted_at
        )
        VALUES (
            ?, ?, 'entity', ?, ?, NULL, NULL, ?, ?, '{}',
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            NULL
        )
        ON CONFLICT(node_id) DO UPDATE SET
            story_id = COALESCE(excluded.story_id, story_id),
            canonical_name = excluded.canonical_name,
            display_name = excluded.display_name,
            canon_status = COALESCE(excluded.canon_status, canon_status),
            worldline_id = COALESCE(excluded.worldline_id, worldline_id),
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            deleted_at = NULL
        """,
        (node_id, story_id, clean_name, clean_name, canon_status, worldline_id),
    )
    return node_id


def _relationship_fields(item: dict) -> tuple[str, str, str]:
    details = item.get("details", {}) if isinstance(item.get("details"), dict) else {}
    source = (
        item.get("source")
        or item.get("from")
        or item.get("subject")
        or item.get("character_a")
        or item.get("person_a")
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
        or item.get("type")
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
    canon_status = str(item.get("canon_status") or item.get("scope") or "").strip() or None
    source_node_id = _upsert_named_entity_node(
        conn,
        name=source_name,
        story_id=story_id,
        worldline_id=worldline_id,
        canon_status=canon_status,
    )
    target_node_id = _upsert_named_entity_node(
        conn,
        name=target_name,
        story_id=story_id,
        worldline_id=worldline_id,
        canon_status=canon_status,
    )
    if not source_node_id or not target_node_id:
        return
    relation_type = re.sub(r"\s+", "_", relation.lower())[:80] or "related_to"
    edge_id_source = f"{knowledge_id}:{source_node_id}:{target_node_id}:{relation_type}"
    edge_id = "edge_" + sha256(edge_id_source.encode("utf-8")).hexdigest()[:24]
    conn.execute(
        """
        INSERT INTO graph_edges (
            edge_id, story_id, source_node_id, target_node_id, relation_type,
            direction, confidence, evidence_id, metadata_json, created_at, updated_at, deleted_at
        )
        VALUES (
            ?, ?, ?, ?, ?, 'directed', ?, NULL, ?,
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            NULL
        )
        ON CONFLICT(edge_id) DO UPDATE SET
            story_id = excluded.story_id,
            source_node_id = excluded.source_node_id,
            target_node_id = excluded.target_node_id,
            relation_type = excluded.relation_type,
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
            _float_or_none(item.get("confidence")),
            _json_dumps({"knowledge_id": knowledge_id, "item": item}),
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
                created_at, updated_at, deleted_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?,
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
                extraction_mode = excluded.extraction_mode,
                quality_json = excluded.quality_json,
                status = excluded.status,
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
                str(item.get("extraction_mode") or "").strip() or None,
                _json_dumps(quality_payload),
                str(item.get("status") or "pending"),
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
