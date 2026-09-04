"""Unified knowledge-center search, detail, revision, and index state."""

from __future__ import annotations

import difflib

from novelforge.services import memory as _memory_api
from storage.repositories import (
    load_entities,
    load_entity_facts,
    load_entity_relations,
    load_knowledge_graph_rows,
    load_knowledge_center_record_row,
    load_knowledge_index_state_row,
    mark_knowledge_retrieval_state,
    process_knowledge_index_jobs,
    retry_knowledge_index_jobs,
    search_knowledge_center_rows,
    load_timeline,
)


def load_knowledge_graph(
    project_name: str,
    *,
    story_id: str | None = None,
    worldline_id: str | None = None,
) -> dict:
    """Return the current relationship projection of authoritative knowledge."""

    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        return load_knowledge_graph_rows(
            conn, story_id=story_id, worldline_id=worldline_id,
        )


def search_knowledge_center(
    project_name: str,
    *,
    query: str = "",
    record_types: list[str] | None = None,
    categories: list[str] | None = None,
    story_id: str | None = None,
    worldline_id: str | None = None,
    include_archived: bool = False,
    archived_only: bool = False,
    cursor: str = "",
    page_size: int = 40,
) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        # FTS projection is small and local; process queued row-level changes
        # before searching so a committed edit is discoverable immediately.
        batch = process_knowledge_index_jobs(conn, limit=100)
        if batch.get("failed_total"):
            # Failed jobs stay failed and visible until the user explicitly
            # retries them; searching must not create an implicit retry loop.
            pass
        result = search_knowledge_center_rows(
            conn,
            query=query,
            record_types=record_types,
            categories=categories,
            story_id=story_id,
            worldline_id=worldline_id,
            include_archived=include_archived,
            archived_only=archived_only,
            cursor=cursor,
            page_size=page_size,
        )
        conn.commit()
        return result


def load_knowledge_center_record(
    project_name: str,
    record_type: str,
    record_id: str,
) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        return load_knowledge_center_record_row(conn, record_type, record_id)


def load_knowledge_center_index_state(project_name: str) -> dict:
    result = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        load_knowledge_index_state_row,
        "knowledge center index state",
    )
    return result if isinstance(result, dict) else {}


def process_knowledge_center_index(project_name: str, *, limit: int = 1000) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        result = process_knowledge_index_jobs(conn, limit=limit)
        conn.commit()
        return result


def retry_knowledge_center_index(project_name: str) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        retried = retry_knowledge_index_jobs(conn)
        conn.commit()
    from novelforge.workflows.knowledge_index_dispatcher import wake_knowledge_index_dispatcher

    wake_knowledge_index_dispatcher(project_name)
    return {"retried": retried, "state": load_knowledge_center_index_state(project_name)}


def set_knowledge_retrieval_index_state(
    project_name: str,
    status: str,
    *,
    indexed_revision: int | None = None,
    error_text: str = "",
) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        result = mark_knowledge_retrieval_state(
            conn, status, indexed_revision=indexed_revision, error_text=error_text,
        )
        conn.commit()
        return result


def knowledge_revision_diff(current: dict, revision: dict) -> str:
    import json

    before = revision.get("snapshot") if isinstance(revision.get("snapshot"), dict) else {}
    after = current if isinstance(current, dict) else {}
    return "\n".join(difflib.unified_diff(
        json.dumps(before, ensure_ascii=False, indent=2, sort_keys=True).splitlines(),
        json.dumps(after, ensure_ascii=False, indent=2, sort_keys=True).splitlines(),
        fromfile=f"修订 {revision.get('revision_no', '-')}",
        tofile="当前版本",
        lineterm="",
    ))


def restore_knowledge_revision(
    project_name: str,
    knowledge_id: str,
    revision_id: str,
    *,
    reason: str = "从历史修订恢复",
) -> dict:
    from novelforge.services.memory import load_knowledge_revisions, update_confirmed_knowledge_item_record

    revisions = load_knowledge_revisions(project_name, knowledge_id)
    target = next(
        (item for item in revisions if str(item.get("revision_id") or "") == str(revision_id or "")),
        None,
    )
    if not target or not isinstance(target.get("snapshot"), dict):
        raise ValueError("要恢复的知识修订不存在。")
    snapshot = dict(target["snapshot"])
    target_category = str(snapshot.get("category") or "").strip()
    current = load_knowledge_center_record(project_name, "knowledge", knowledge_id)
    current_category = str(current.get("category") or "").strip()
    if not target_category or not current_category:
        raise ValueError("历史修订缺少知识分类。")
    snapshot.update({
        "id": knowledge_id,
        "knowledge_id": knowledge_id,
        "category": target_category,
        "revision_reason": reason,
        "restored_from_revision_id": revision_id,
    })
    if not update_confirmed_knowledge_item_record(
        project_name, current_category, knowledge_id, snapshot, target_category=target_category,
    ):
        raise RuntimeError("知识修订恢复失败。")
    return {"knowledge_id": knowledge_id, "revision_id": revision_id, "restored": True}


def restore_archived_knowledge_item(
    project_name: str,
    knowledge_id: str,
    *,
    reason: str = "从归档恢复",
) -> dict:
    from novelforge.services.memory import upsert_knowledge_category_item_record

    record = load_knowledge_center_record(project_name, "knowledge", knowledge_id)
    if not record or not record.get("archived"):
        raise ValueError("要恢复的归档知识不存在。")
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    category = str(record.get("category") or payload.get("category") or "").strip()
    if not category:
        raise ValueError("归档知识缺少分类。")
    restored = upsert_knowledge_category_item_record(project_name, category, {
        **payload,
        "id": knowledge_id,
        "knowledge_id": knowledge_id,
        "category": category,
        "status": "confirmed",
        "revision_reason": reason,
        "restored_from_archive": True,
    })
    return {"knowledge_id": knowledge_id, "restored": True, "item": restored}


def load_character_entity_cards(project_name: str, *, max_characters: int = 80) -> list[dict]:
    """Entity-centric character cards read from the entities table (not name-based merge).

    Returns the same card shape as ``build_character_entity_cards`` so callers are
    unchanged, but the source of truth is now the entity master + its facts + edges.
    """
    if _memory_api._project_db_marked_unavailable(project_name):
        return []
    try:
        with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
            entities = load_entities(conn, entity_type="character")
    except Exception:
        return []
    cards: list[dict] = []
    for entity in entities[:max_characters]:
        entity_id = entity["entity_id"]
        try:
            with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
                facts = load_entity_facts(conn, entity_id)
                relations = load_entity_relations(conn, entity_id)
        except Exception:
            facts, relations = [], []
        # Group facts by fact_key into a profile; summary from entity master.
        profile: dict[str, str] = {}
        fact_summaries: list[str] = []
        for fact in facts:
            summary = str(fact.get("summary") or "").strip()
            if not summary:
                continue
            fact_summaries.append(summary)
            key = fact.get("fact_key")
            if key:
                profile[key] = summary
        # Classify edges by relation semantics. Incoming edges reference this
        # entity from the other side (ability -> character, item -> character,
        # event -> character); outgoing edges go from this entity to others
        # (character -> organization).
        abilities: list[str] = []
        items: list[str] = []
        events: list[str] = []
        affiliations: list[str] = []
        relationships: list[str] = []
        for r in relations:
            name = r["other_name"]
            otype = r["other_type"]
            rel = r["relation_type"]
            if not r["outgoing"] and otype == "ability":
                abilities.append(name)
            elif not r["outgoing"] and otype == "item":
                items.append(name)
            elif not r["outgoing"] and otype == "event":
                events.append(name)
            elif r["outgoing"] and otype == "organization":
                affiliations.append(name)
            else:
                relationships.append(f"{name}（{rel}）")
        # Source chips from the owning facts (source_title / source_origin).
        sources: list[dict] = []
        seen_sources: set[tuple[str, str, str]] = set()
        for fact in facts:
            payload = fact.get("content_json") if isinstance(fact.get("content_json"), dict) else {}
            key = (
                str(payload.get("source_title") or "").strip(),
                str(payload.get("source_origin") or "").strip(),
                str(payload.get("source_segment_id") or "").strip(),
            )
            if not any(key) or key in seen_sources:
                continue
            seen_sources.add(key)
            sources.append({
                "title": key[0] or "未命名来源",
                "origin": key[1],
                "segment_id": key[2],
                "knowledge_id": str(fact.get("knowledge_id") or ""),
            })
        cards.append({
            "id": entity_id,
            "entity_type": "character",
            "name": entity["canonical_name"],
            "aliases": [],
            "summary": entity.get("summary") or (fact_summaries[0] if fact_summaries else ""),
            "profile": profile,
            "relationships": relationships,
            "abilities": abilities,
            "items": items,
            "abilities_and_items": abilities + items,
            "dialogue_style": [],
            "constraints": [],
            "timeline": events,
            "events": events,
            "evidence": [],
            "sources": sources,
            "confidence": 0.7,
            "importance": entity.get("importance") or 0.5,
            "canon_status": "unknown",
            "scope": entity.get("setting_scope") or "project",
            "setting_scope": entity.get("setting_scope") or "project",
            "story_id": entity.get("story_id") or "",
            "version_scope": entity.get("version_scope") or "",
            "worldline_id": entity.get("worldline_id") or "",
            "worldline_label": "",
            "source_knowledge_ids": [f.get("knowledge_id") for f in facts if f.get("knowledge_id")],
            "primary_knowledge_id": facts[0].get("knowledge_id") if facts else "",
            "affiliations": affiliations,
            "tags": ["角色实体卡", "entity_character"],
            "status": "entity_card",
        })
    return cards


def load_setting_entity_cards(project_name: str, *, max_cards: int = 120) -> list[dict]:
    """Entity-centric setting cards (organizations/locations/items/abilities/world_rules)."""
    if _memory_api._project_db_marked_unavailable(project_name):
        return []
    setting_types = ("organization", "location", "item", "ability", "world_rule")
    try:
        with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
            entities = [e for e in load_entities(conn) if e["entity_type"] in setting_types]
    except Exception:
        return []
    cards: list[dict] = []
    for entity in entities[:max_cards]:
        entity_id = entity["entity_id"]
        try:
            with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
                facts = load_entity_facts(conn, entity_id)
                relations = load_entity_relations(conn, entity_id)
        except Exception:
            facts, relations = [], []
        fact_summaries = [str(f.get("summary") or "").strip() for f in facts if str(f.get("summary") or "").strip()]
        related = [
            f"{r['other_name']}（{r['relation_type']}）"
            for r in relations
        ]
        # setting_type mirrors the legacy category name (world_rules, not world_rule).
        setting_type = facts[0].get("category") if facts else entity["entity_type"]
        sources: list[dict] = []
        seen_sources: set[tuple[str, str, str]] = set()
        for fact in facts:
            payload = fact.get("content_json") if isinstance(fact.get("content_json"), dict) else {}
            key = (
                str(payload.get("source_title") or "").strip(),
                str(payload.get("source_origin") or "").strip(),
                str(payload.get("source_segment_id") or "").strip(),
            )
            if not any(key) or key in seen_sources:
                continue
            seen_sources.add(key)
            sources.append({
                "title": key[0] or "未命名来源",
                "origin": key[1],
                "segment_id": key[2],
                "knowledge_id": str(fact.get("knowledge_id") or ""),
            })
        cards.append({
            "id": entity_id,
            "entity_type": "setting",
            "setting_type": setting_type,
            "name": entity["canonical_name"],
            "summary": entity.get("summary") or (fact_summaries[0] if fact_summaries else ""),
            "profile": {},
            "rules": fact_summaries,
            "timeline": [],
            "related_entities": related,
            "conflicts": [],
            "evidence": [],
            "sources": sources,
            "confidence": 0.7,
            "importance": entity.get("importance") or 0.5,
            "canon_status": "unknown",
            "scope": entity.get("setting_scope") or "project",
            "setting_scope": entity.get("setting_scope") or "project",
            "story_id": entity.get("story_id") or "",
            "version_scope": entity.get("version_scope") or "",
            "worldline_id": entity.get("worldline_id") or "",
            "worldline_label": "",
            "source_knowledge_ids": [f.get("knowledge_id") for f in facts if f.get("knowledge_id")],
            "primary_knowledge_id": facts[0].get("knowledge_id") if facts else "",
            "tags": ["设定实体卡", "entity_setting"],
            "status": "entity_card",
        })
    return cards
