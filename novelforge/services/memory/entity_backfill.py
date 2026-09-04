"""Entity backfill for the Entity-Fact-Relation storage refactor (P0).

Reads existing ``knowledge_items`` rows and populates:

- ``entities`` rows (one per entity, grouped by normalized name + isolation domain);
- ``knowledge_items.entity_id`` (link each fact to its entity);
- ``knowledge_items.chapter_no`` (parsed from ``tags`` ``chapter:{n}``, tolerant of absence);
- ``knowledge_items.fact_key`` (from ``setting_field`` when present).

This module is intentionally light on imports so it can be invoked from a bare
``sqlite3.Connection`` without pulling in the full ``services.memory`` graph.

The grouping key is the single source of truth in ``storage.repositories.entity_identity``
(the same module the write path uses), so backfill and writes never drift.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Callable

from storage.repositories.entity_identity import (
    CATEGORY_TO_ENTITY_TYPE,
    entity_id_for,
    isolation_domain,
    normalize_name,
)


def parse_chapter_no(content_json: str | None) -> int | None:
    """Parse ``chapter:{n}`` out of the ``tags`` list inside content_json. Returns None if absent."""
    if not content_json:
        return None
    try:
        payload = json.loads(content_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    tags = payload.get("tags")
    if not isinstance(tags, list):
        return None
    for tag in tags:
        text = str(tag or "")
        match = re.match(r"^chapter:(\d+)$", text.strip())
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def _load_rows(conn: sqlite3.Connection) -> list[dict]:
    """Load all live knowledge_items rows with the columns backfill needs."""
    rows = conn.execute(
        """
        SELECT knowledge_id, story_id, category, name, summary, content_json,
               worldline_id, setting_scope, importance
        FROM knowledge_items
        WHERE deleted_at IS NULL
        ORDER BY created_at, knowledge_id
        """
    ).fetchall()
    out: list[dict] = []
    for row in rows:
        out.append({
            "knowledge_id": row[0],
            "story_id": row[1],
            "category": row[2],
            "name": row[3],
            "summary": row[4],
            "content_json": row[5],
            "worldline_id": row[6],
            "setting_scope": row[7],
            "importance": row[8],
        })
    return out


def _setting_field_from(content_json: str | None) -> str | None:
    if not content_json:
        return None
    try:
        payload = json.loads(content_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(payload, dict):
        value = payload.get("setting_field")
        if value:
            return str(value).strip() or None
    return None


def _entity_type_for(category: str) -> str | None:
    return CATEGORY_TO_ENTITY_TYPE.get(str(category or "").strip())


def backfill_entities(
    conn: sqlite3.Connection,
    *,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Backfill entities + entity_id + chapter_no + fact_key. Idempotent.

    Returns a summary dict with counts. Does NOT delete anything; purely additive.
    """
    rows = _load_rows(conn)
    summary = {"scanned": len(rows), "entities_created": 0, "linked": 0, "chapter_parsed": 0}

    # Group facts by entity identity so we can write one entity row per entity.
    entities: dict[str, dict] = {}
    for row in rows:
        entity_type = _entity_type_for(row["category"])
        if not entity_type:
            # Category without an entity mapping (e.g. project-level style) is skipped.
            continue
        domain = isolation_domain(row)
        name = str(row["name"] or "").strip()
        if not name:
            continue
        eid = entity_id_for(entity_type, name, domain)
        if eid not in entities:
            setting_scope, story_id, worldline_id, version_scope = domain
            entities[eid] = {
                "entity_id": eid,
                "entity_type": entity_type,
                "canonical_name": name,
                "story_id": story_id or None,
                "worldline_id": worldline_id or None,
                "setting_scope": setting_scope or "project",
                "version_scope": version_scope or "project_main",
                "summary": str(row["summary"] or "").strip(),
                "importance": row["importance"] if isinstance(row["importance"], (int, float)) else 0,
            }

    if not entities:
        if progress:
            progress("no backfillable entities found")
        return summary

    for eid, entity in entities.items():
        conn.execute(
            """
            INSERT INTO entities (
                entity_id, entity_type, canonical_name, display_name, story_id, worldline_id,
                setting_scope, version_scope, summary, importance
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_id) DO UPDATE SET
                canonical_name = excluded.canonical_name,
                summary = CASE WHEN excluded.summary != '' THEN excluded.summary ELSE entities.summary END,
                importance = excluded.importance,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                deleted_at = NULL
            """,
            (
                eid, entity["entity_type"], entity["canonical_name"], entity["canonical_name"],
                entity["story_id"], entity["worldline_id"], entity["setting_scope"],
                entity["version_scope"], entity["summary"], entity["importance"],
            ),
        )
        summary["entities_created"] += 1

    # Link facts back and parse chapter_no / fact_key.
    for row in rows:
        entity_type = _entity_type_for(row["category"])
        name = str(row["name"] or "").strip()
        if not entity_type or not name:
            continue
        eid = entity_id_for(entity_type, name, isolation_domain(row))
        chapter_no = parse_chapter_no(row["content_json"])
        fact_key = _setting_field_from(row["content_json"])
        conn.execute(
            """
            UPDATE knowledge_items
            SET entity_id = ?, chapter_no = COALESCE(?, chapter_no),
                fact_key = COALESCE(?, fact_key)
            WHERE knowledge_id = ? AND deleted_at IS NULL
            """,
            (eid, chapter_no, fact_key, row["knowledge_id"]),
        )
        summary["linked"] += 1
        if chapter_no is not None:
            summary["chapter_parsed"] += 1

    if progress:
        progress(
            f"scanned={summary['scanned']} entities={summary['entities_created']} "
            f"linked={summary['linked']} chapter_parsed={summary['chapter_parsed']}"
        )
    return summary
