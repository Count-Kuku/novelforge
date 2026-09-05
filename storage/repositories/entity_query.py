"""Entity-centric read queries for the Entity-Fact-Relation storage model.

These are the authoritative read paths for entity cards, timelines and
relationship graphs — replacing the previous name-based in-memory aggregation.
They operate directly on ``entities``, ``knowledge_items`` and ``graph_edges``.

All functions take a ``sqlite3.Connection``; the services layer wraps them with
the usual DB-first read helpers.
"""
from __future__ import annotations

import sqlite3
from typing import Any


def _json_loads_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    import json

    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def load_entities(
    conn: sqlite3.Connection,
    *,
    entity_type: str | None = None,
    story_id: str | None = None,
    worldline_id: str | None = None,
) -> list[dict]:
    """Load active entity master rows, optionally filtered."""
    clauses = ["deleted_at IS NULL"]
    params: list[Any] = []
    if entity_type:
        clauses.append("entity_type = ?")
        params.append(entity_type)
    if story_id is not None:
        clauses.append("COALESCE(story_id, '') IN ('', ?)")
        params.append(str(story_id))
    if worldline_id is not None:
        clauses.append("COALESCE(worldline_id, '') IN ('', 'main', ?)")
        params.append(str(worldline_id))
    rows = conn.execute(
        f"""
        SELECT entity_id, entity_type, canonical_name, display_name, story_id, worldline_id,
               setting_scope, version_scope, summary, importance, world_t, world_time_label,
               meta_json
        FROM entities
        WHERE {' AND '.join(clauses)}
        ORDER BY importance DESC, canonical_name
        """,
        tuple(params),
    ).fetchall()
    result: list[dict] = []
    for row in rows:
        result.append({
            "entity_id": row[0],
            "entity_type": row[1],
            "canonical_name": row[2],
            "display_name": row[3] or row[2],
            "story_id": row[4],
            "worldline_id": row[5],
            "setting_scope": row[6],
            "version_scope": row[7],
            "summary": row[8],
            "importance": row[9],
            "world_t": row[10],
            "world_time_label": row[11],
            "meta": _json_loads_dict(row[12]),
        })
    return result


def load_entity_facts(
    conn: sqlite3.Connection,
    entity_id: str,
    *,
    chapter_no: int | None = None,
) -> list[dict]:
    """Load a single entity's facts, honoring chapter-scoped validity."""
    clauses = ["entity_id = ?", "deleted_at IS NULL"]
    params: list[Any] = [entity_id]
    if chapter_no is not None:
        clauses.append("(valid_from_chapter IS NULL OR valid_from_chapter <= ?)")
        clauses.append("(valid_to_chapter IS NULL OR valid_to_chapter > ?)")
        params.extend([chapter_no, chapter_no])
    rows = conn.execute(
        f"""
        SELECT knowledge_id, category, name, summary, content_json, fact_key,
               chapter_no, valid_from_chapter, valid_to_chapter, merge_policy,
               setting_role, injection_policy, importance
        FROM knowledge_items
        WHERE {' AND '.join(clauses)}
        ORDER BY chapter_no, valid_from_chapter, knowledge_id
        """,
        tuple(params),
    ).fetchall()
    facts: list[dict] = []
    for row in rows:
        facts.append({
            "knowledge_id": row[0],
            "category": row[1],
            "name": row[2],
            "summary": row[3],
            "content_json": _json_loads_dict(row[4]),
            "fact_key": row[5],
            "chapter_no": row[6],
            "valid_from_chapter": row[7],
            "valid_to_chapter": row[8],
            "merge_policy": row[9],
            "setting_role": row[10],
            "injection_policy": row[11],
            "importance": row[12],
        })
    return facts


def load_entity_relations(
    conn: sqlite3.Connection,
    entity_id: str,
    *,
    chapter_no: int | None = None,
) -> list[dict]:
    """Load an entity's outgoing and incoming graph edges, resolved to entity names."""
    clauses = [
        "(source_node_id = ? OR target_node_id = ?)",
        "edge.deleted_at IS NULL",
    ]
    params: list[Any] = [entity_id, entity_id]
    if chapter_no is not None:
        clauses.append("(edge.valid_from_chapter IS NULL OR edge.valid_from_chapter <= ?)")
        clauses.append("(edge.valid_to_chapter IS NULL OR edge.valid_to_chapter > ?)")
        params.extend([chapter_no, chapter_no])
    rows = conn.execute(
        f"""
        SELECT edge.edge_id, edge.relation_type, edge.direction,
               edge.source_node_id, edge.target_node_id,
               src.canonical_name AS source_name, src.entity_type AS source_type,
               tgt.canonical_name AS target_name, tgt.entity_type AS target_type
        FROM graph_edges AS edge
        JOIN entities AS src ON src.entity_id = edge.source_node_id
        JOIN entities AS tgt ON tgt.entity_id = edge.target_node_id
        WHERE {' AND '.join(clauses)}
        ORDER BY edge.updated_at DESC, edge.edge_id
        """,
        tuple(params),
    ).fetchall()
    relations: list[dict] = []
    for row in rows:
        outgoing = row[3] == entity_id
        relations.append({
            "edge_id": row[0],
            "relation_type": row[1],
            "direction": row[2],
            "outgoing": outgoing,
            "other_entity_id": row[4] if outgoing else row[3],
            "other_name": row[7] if outgoing else row[5],
            "other_type": row[8] if outgoing else row[6],
        })
    return relations


def load_timeline(
    conn: sqlite3.Connection,
    *,
    story_id: str | None = None,
    worldline_id: str | None = None,
) -> list[dict]:
    """Load the world timeline: event entities ordered by world_t (chapter fallback)."""
    events = load_entities(conn, entity_type="event", story_id=story_id, worldline_id=worldline_id)
    for event in events:
        facts = load_entity_facts(conn, event["entity_id"])
        event["facts"] = facts
        event["summary"] = event["summary"] or (facts[0]["summary"] if facts else "")
    events.sort(key=lambda e: (
        e.get("world_t") if isinstance(e.get("world_t"), (int, float)) else float("inf"),
        e.get("canonical_name", ""),
    ))
    return events


_FACT_PRECEDENCE = {"au": 3, "project_main": 2, "canon": 1}


def _fact_slot(fact: dict) -> str:
    return str(fact.get("fact_key") or "_slotless")


def merge_worldline_baseline(
    conn: sqlite3.Connection,
    *,
    story_id: str | None,
    worldline_id: str | None = None,
    worldline_mode: str = "prefer",
) -> list[dict]:
    """合并「项目库 canon 基线」与「故事作用域当前事实」为有效知识（B 期/D1/D12）。

    对同名实体（entity_type + canonical_name）跨 setting_scope（project vs story）与
    version_scope（canon vs project_main/au）双维度叠加：优先级 au > project_main > canon；
    replace 槽位取最高优先级、append 槽位各层 union（按 summary 去重）。
    纯读取函数；接入生成上下文装配属 refactor 2。
    """
    del worldline_mode  # 保留参数位，prefer/strict 语义由消费层（setting/retrieval）处理
    canon_entities = [
        e for e in load_entities(conn, worldline_id=worldline_id)
        if e["setting_scope"] == "project" and e["version_scope"] == "canon"
    ]
    current_entities = [
        e for e in load_entities(conn, story_id=story_id, worldline_id=worldline_id)
        if e["setting_scope"] == "story" and e["version_scope"] in ("project_main", "au")
    ]
    groups: dict[tuple[str, str], dict] = {}
    for e in canon_entities:
        key = (e["entity_type"], e["canonical_name"])
        slot_map = groups.setdefault(key, {"entity_type": e["entity_type"], "canonical_name": e["canonical_name"], "slots": {}})["slots"]
        for fact in load_entity_facts(conn, e["entity_id"]):
            slot_map.setdefault(_fact_slot(fact), []).append((_FACT_PRECEDENCE["canon"], fact))
    for e in current_entities:
        key = (e["entity_type"], e["canonical_name"])
        rank = _FACT_PRECEDENCE.get(e["version_scope"], _FACT_PRECEDENCE["project_main"])
        slot_map = groups.setdefault(key, {"entity_type": e["entity_type"], "canonical_name": e["canonical_name"], "slots": {}})["slots"]
        for fact in load_entity_facts(conn, e["entity_id"]):
            slot_map.setdefault(_fact_slot(fact), []).append((rank, fact))
    merged: list[dict] = []
    for key, group in groups.items():
        effective: list[dict] = []
        for slot, ranked in group["slots"].items():
            is_replace = slot != "_slotless" and bool(ranked) and ranked[0][1].get("merge_policy") == "replace"
            if is_replace:
                ranked.sort(key=lambda x: x[0], reverse=True)
                effective.append(ranked[0][1])
            else:
                seen: set[str] = set()
                for _, fact in ranked:
                    summary = str(fact.get("summary") or "")
                    if summary not in seen:
                        seen.add(summary)
                        effective.append(fact)
        merged.append({
            "entity_type": group["entity_type"],
            "canonical_name": group["canonical_name"],
            "facts": effective,
        })
    return merged
