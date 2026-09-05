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
    return load_entity_facts_for_entities(conn, [entity_id], chapter_no=chapter_no)


def load_entity_facts_for_entities(
    conn: sqlite3.Connection,
    entity_ids: list[str],
    *,
    chapter_no: int | None = None,
) -> list[dict]:
    """Load facts for multiple entities in one query, honoring chapter-scoped validity."""
    clean_ids = [str(item) for item in entity_ids if str(item)]
    if not clean_ids:
        return []
    clauses = ["entity_id IN (%s)" % ", ".join("?" * len(clean_ids)), "deleted_at IS NULL"]
    params: list[Any] = [*clean_ids]
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
    chapter_no: int | None = None,
) -> list[dict]:
    """Load the world timeline: event entities ordered by world_t (chapter fallback)."""
    events = load_entities(conn, entity_type="event", story_id=story_id, worldline_id=worldline_id)
    for event in events:
        facts = load_entity_facts(conn, event["entity_id"], chapter_no=chapter_no)
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
    chapter_no: int | None = None,
) -> list[dict]:
    """合并「项目库 canon 基线」与「故事作用域当前事实」为有效知识（B 期/D1/D12）。

    对同名实体（entity_type + canonical_name）跨 setting_scope（project vs story）与
    version_scope（canon vs project_main/au）双维度叠加：优先级 au > project_main > canon；
    replace 槽位取最高优先级、append 槽位各层 union（按 summary 去重）。

    时序语义（refactor 2 P0，修 G20）：`chapter_no` 提供时，各层内部按
    `valid_from_chapter <= chapter_no < valid_to_chapter` 只取「截至当前章仍有效」的事实，
    已失效（被同槽位取代）的旧事实不会进入叠加，避免「身在京城与身在洛阳并存」。

    世界线语义（refactor 2 遗留 #9 收口）：`worldline_mode="strict"` 时只叠加
    「空/共享世界线 + 目标世界线」的实体，剔除 `main` 及其它世界线；prefer（默认）保留
    `load_entities` 的宽松语义（空/main/目标均算）。纯读取函数；接入生成上下文装配属 refactor 2。
    """
    strict_target = str(worldline_id or "").strip() if str(worldline_mode or "prefer").strip().lower() == "strict" else None
    canon_entities = [
        e for e in load_entities(conn, worldline_id=worldline_id)
        if e["setting_scope"] == "project" and e["version_scope"] == "canon"
        and (strict_target is None or str(e.get("worldline_id") or "") in ("", strict_target))
    ]
    current_entities = [
        e for e in load_entities(conn, story_id=story_id, worldline_id=worldline_id)
        if e["setting_scope"] == "story" and e["version_scope"] in ("project_main", "au")
        and (strict_target is None or str(e.get("worldline_id") or "") in ("", strict_target))
    ]
    groups: dict[tuple[str, str], dict] = {}
    for e in canon_entities:
        key = (e["entity_type"], e["canonical_name"])
        slot_map = groups.setdefault(key, {"entity_type": e["entity_type"], "canonical_name": e["canonical_name"], "slots": {}})["slots"]
        for fact in load_entity_facts(conn, e["entity_id"], chapter_no=chapter_no):
            slot_map.setdefault(_fact_slot(fact), []).append((_FACT_PRECEDENCE["canon"], fact))
    for e in current_entities:
        key = (e["entity_type"], e["canonical_name"])
        rank = _FACT_PRECEDENCE.get(e["version_scope"], _FACT_PRECEDENCE["project_main"])
        slot_map = groups.setdefault(key, {"entity_type": e["entity_type"], "canonical_name": e["canonical_name"], "slots": {}})["slots"]
        for fact in load_entity_facts(conn, e["entity_id"], chapter_no=chapter_no):
            slot_map.setdefault(_fact_slot(fact), []).append((rank, fact))
    merged: list[dict] = []
    for key, group in groups.items():
        effective: list[dict] = []
        for slot, ranked in group["slots"].items():
            is_replace = slot != "_slotless" and bool(ranked) and ranked[0][1].get("merge_policy") == "replace"
            if is_replace:
                # Replace 槽位取「优先级最高」且「生效区间最晚」的那条：同层（相同 version_scope）
                # 的多条时序事实（京城→洛阳）只保留最新一条，避免写入方已置 valid_to 的旧值复活。
                ranked.sort(key=lambda x: (x[0], _fact_chapter_start(x[1])), reverse=True)
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


def _fact_chapter_start(fact: dict):
    value = fact.get("valid_from_chapter")
    return value if isinstance(value, (int, float)) else -1


def resolve_entity_ids_by_names(
    conn: sqlite3.Connection,
    names: list[str],
    *,
    story_id: str | None = None,
    worldline_id: str | None = None,
) -> dict[str, dict]:
    """把 LLM/检索识别出的「实体名」解析为库内 entity_id（D2）。

    匹配顺序：
    1. 规范化名等值匹配 `entities.canonical_name`；
    2. 未命中时查 `entity_alias_groups` 的 canonical_name/aliases（normalize 匹配），
       用组 canonical_name 再查一次 entities；
    3. 仍未命中 → 该名 unresolved（冷启动/别名缺失），调用方降级处理。

    返回 {原始名: {entity_id, canonical_name, entity_type, matched_via, story_id}}
    限定在传入 story_id/worldline_id 隔离域内的实体（复用 load_entities 过滤语义）。
    """
    from storage.repositories.knowledge import load_entity_alias_group_rows

    from storage.repositories.entity_identity import normalize_name

    if not names:
        return {}
    clean_names = [str(item).strip() for item in names if str(item).strip()]
    if not clean_names:
        return {}
    # 隔离域内实体主档一次取回，Python 端做规范化匹配（实体量级小，避免逐名 SQL）。
    entities = load_entities(conn, story_id=story_id, worldline_id=worldline_id)
    # canonical normalized -> 主档行（同 story 同 canonical 应唯一；保留首条）
    by_normalized: dict[str, dict] = {}
    for entity in entities:
        key = normalize_name(entity.get("canonical_name"))
        if key and key not in by_normalized:
            by_normalized[key] = entity
    # 别名组：alias normalized -> canonical_name（组级不绑定 entity_id，回落到 canonical 查询）
    alias_to_canonical: dict[str, str] = {}
    alias_groups = []
    try:
        alias_groups = load_entity_alias_group_rows(conn)
    except Exception:
        alias_groups = []
    for group in alias_groups:
        canonical = str(group.get("canonical_name") or "").strip()
        if not canonical:
            continue
        keys = {canonical, *(str(a).strip() for a in (group.get("aliases") or []) if str(a).strip())}
        for candidate in keys:
            normalized = normalize_name(candidate)
            if normalized:
                alias_to_canonical.setdefault(normalized, canonical)
    result: dict[str, dict] = {}
    for raw in clean_names:
        normalized = normalize_name(raw)
        if not normalized:
            result[raw] = {}
            continue
        entity = by_normalized.get(normalized)
        matched_via = "canonical"
        if entity is None:
            canonical = alias_to_canonical.get(normalized)
            if canonical:
                canonical_normalized = normalize_name(canonical)
                entity = by_normalized.get(canonical_normalized)
                matched_via = "alias"
        if entity is None:
            result[raw] = {}
            continue
        result[raw] = {
            "entity_id": str(entity.get("entity_id") or ""),
            "canonical_name": str(entity.get("canonical_name") or ""),
            "entity_type": str(entity.get("entity_type") or ""),
            "story_id": str(entity.get("story_id") or ""),
            "matched_via": matched_via,
        }
    return result
