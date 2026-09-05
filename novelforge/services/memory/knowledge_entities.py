"""Implementation slice for the memory facade: entity master and fact queries."""

from __future__ import annotations

from novelforge.services import memory as _memory_api
from novelforge.domain.knowledge_types import normalize_typed_knowledge_item
from storage.repositories import entity_query
from storage.repositories.knowledge import (
    fetch_knowledge_entity_rows,
    load_knowledge_evidence_rows,
    load_knowledge_revision_rows,
    summarize_knowledge_storage_health,
)

def load_entity_master_rows(
    project_name: str,
    *,
    story_id: str | None = None,
    worldline_id: str | None = None,
) -> list[dict]:
    result = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: entity_query.load_entities(conn, story_id=story_id, worldline_id=worldline_id),
        "entities",
    )
    return result if isinstance(result, list) else []


def fetch_entity_facts(
    project_name: str,
    entity_id: str,
    *,
    chapter_no: int | None = None,
) -> list[dict]:
    result = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: entity_query.load_entity_facts(conn, entity_id, chapter_no=chapter_no),
        "entity facts",
    )
    return result if isinstance(result, list) else []


def load_entity_facts_for_entities(
    project_name: str,
    entity_ids: list[str],
    *,
    chapter_no: int | None = None,
) -> list[dict]:
    if not entity_ids:
        return []
    result = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: entity_query.load_entity_facts_for_entities(conn, entity_ids, chapter_no=chapter_no),
        "entity facts batch",
    )
    return result if isinstance(result, list) else []


def merge_worldline_baseline(
    project_name: str,
    *,
    story_id: str = "default",
    worldline_id: str | None = None,
    worldline_mode: str = "prefer",
    chapter_no: int | None = None,
) -> list[dict]:
    result = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: entity_query.merge_worldline_baseline(
            conn,
            story_id=story_id,
            worldline_id=worldline_id,
            worldline_mode=worldline_mode,
            chapter_no=chapter_no,
        ),
        "worldline baseline",
    )
    return result if isinstance(result, list) else []


def resolve_entity_ids_by_names(
    project_name: str,
    names: list[str],
    *,
    story_id: str | None = None,
    worldline_id: str | None = None,
) -> dict[str, dict]:
    result = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: entity_query.resolve_entity_ids_by_names(
            conn, names, story_id=story_id, worldline_id=worldline_id
        ),
        "entity name resolution",
    )
    return result if isinstance(result, dict) else {}


def fetch_knowledge_entity_map(project_name: str, knowledge_ids: list[str]) -> dict[str, dict]:
    """knowledge_id → {entity_id, canonical_name, entity_type}（两段式检索反查，遗留 #7 收口）。"""
    result = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: fetch_knowledge_entity_rows(conn, knowledge_ids),
        "knowledge entity map",
    )
    rows = result if isinstance(result, list) else []
    mapping: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("knowledge_id"):
            continue
        mapping.setdefault(str(row["knowledge_id"]), {
            "entity_id": str(row.get("entity_id") or ""),
            "canonical_name": str(row.get("canonical_name") or ""),
            "entity_type": str(row.get("entity_type") or ""),
        })
    return mapping


def load_chapter_world_snapshot(
    project_name: str,
    story_id: str,
    chapter_no: int,
    *,
    worldline_id: str | None = None,
    worldline_mode: str = "prefer",
) -> dict:
    """P4/遗留 #10 收口：只读「第 N 章世界快照」。

    聚合截至当前章仍有效的事实（跨 canon/story 叠加 + 章号过滤）与时间线事件，
    供「世界状态总览」等展示/评测直接取用。当前按需查询即够；若大规模实测成为瓶颈，
    再在此之上加物化缓存（经评估：当前规模不做物化）。
    """
    merged = merge_worldline_baseline(
        project_name,
        story_id=story_id,
        worldline_id=worldline_id,
        worldline_mode=worldline_mode,
        chapter_no=chapter_no,
    )
    entities: list[dict] = []
    for group in merged:
        if not isinstance(group, dict):
            continue
        facts = [
            str(fact.get("summary") or "")
            for fact in (group.get("facts") or [])
            if isinstance(fact, dict) and str(fact.get("summary") or "").strip()
        ]
        if facts:
            entities.append({
                "entity_type": str(group.get("entity_type") or ""),
                "canonical_name": str(group.get("canonical_name") or ""),
                "facts": facts,
            })
    timeline: list[dict] = []
    for entity in entities:
        if entity["entity_type"] == "event":
            timeline.append(entity)
    return {
        "chapter_no": chapter_no,
        "worldline_id": worldline_id,
        "story_id": story_id,
        "entities": sorted(entities, key=lambda e: (e["entity_type"], e["canonical_name"])),
        "timeline_events": sorted(timeline, key=lambda e: e["canonical_name"]),
    }


def sync_aliases_to_groups(project_name: str, items: list[dict]) -> int:
    """refactor 1 遗留 #1 收口：把条目携带的 aliases 同步进 `entity_alias_groups`。

    提取（`build_pending_knowledge_from_reference_extraction` 等）已把别名解析进条目的
    `aliases` 键；本条在条目确认入库后调用，把 aliases 合并进别名组，使别名解析
    （`resolve_entity_ids_by_names`）能覆盖提取别名。返回本次新增别名组数。
    """
    from storage.repositories.entity_identity import entity_type_for_category

    candidates: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        aliases = item.get("aliases")
        if not isinstance(aliases, list) or not aliases:
            continue
        clean_aliases = [str(a).strip() for a in aliases if str(a).strip()]
        if not clean_aliases:
            continue
        name = str(item.get("name") or "").strip()
        category = str(item.get("category") or "").strip()
        if not name or not category:
            continue
        entity_type = entity_type_for_category(category)
        if not entity_type:
            continue
        candidates.append({
            "canonical_name": name,
            "aliases": clean_aliases,
            "entity_type": entity_type,
            "story_id": str(item.get("story_id") or ""),
            "worldline_id": str(item.get("worldline_id") or ""),
        })
    if not candidates:
        return 0
    existing = _memory_api.load_entity_aliases(project_name)
    if not isinstance(existing, list):
        existing = []
    index: dict[tuple[str, str, str, str], dict] = {}
    for group in existing:
        if not isinstance(group, dict):
            continue
        key = (
            str(group.get("canonical_name") or ""),
            str(group.get("entity_type") or ""),
            str(group.get("story_id") or ""),
            str(group.get("worldline_id") or ""),
        )
        index.setdefault(key, group)
    added = 0
    changed_groups: list[dict] = []
    for candidate in candidates:
        key = (
            candidate["canonical_name"],
            candidate["entity_type"],
            candidate["story_id"],
            candidate["worldline_id"],
        )
        group = index.get(key)
        if group is None:
            index[key] = {
                "canonical_name": candidate["canonical_name"],
                "aliases": list(candidate["aliases"]),
                "entity_type": candidate["entity_type"],
                "story_id": candidate["story_id"] or None,
                "worldline_id": candidate["worldline_id"] or None,
            }
            changed_groups.append(index[key])
            added += 1
            continue
        merged_aliases = list(group.get("aliases") or [])
        seen = set(str(a) for a in merged_aliases)
        new_aliases = [a for a in candidate["aliases"] if a not in seen and not seen.add(a)]
        if new_aliases:
            group["aliases"] = merged_aliases + new_aliases
            changed_groups.append(group)
    if not changed_groups:
        return 0
    merged_existing = list(existing)
    for group in changed_groups:
        replaced = False
        for i, existing_group in enumerate(merged_existing):
            if not isinstance(existing_group, dict):
                continue
            if (
                str(existing_group.get("canonical_name") or "") == str(group.get("canonical_name") or "")
                and str(existing_group.get("entity_type") or "") == str(group.get("entity_type") or "")
                and str(existing_group.get("story_id") or "") == str(group.get("story_id") or "")
                and str(existing_group.get("worldline_id") or "") == str(group.get("worldline_id") or "")
            ):
                merged_existing[i] = group
                replaced = True
                break
        if not replaced:
            merged_existing.append(group)
    try:
        _memory_api.save_entity_aliases(project_name, merged_existing)
    except Exception as exc:
        _memory_api.logging.getLogger("novelforge").warning(
            "sync aliases to groups failed for %s: %s", project_name, exc
        )
        return 0
    return added
