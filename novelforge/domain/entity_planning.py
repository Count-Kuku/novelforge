"""Refactor 2 · P1：实体识别与查询规划编排。

把「这一次生成/规划该带哪些实体」从无机制变为可执行步骤：

- `plan_entity_context`：LLM 读本次文本（大纲/细纲/创作想法）识别所需实体（D1）；
- 两段式：识别名 → `resolve_entity_ids_by_names` 归一/解析 entity_id（D2），unresolved 记录；
- 冷启动降级：无已确认实体库时返回空计划，调用方回退单查询（D9）；
- 路由分组：把实体按 §3.1 的类别归到角色/世界观/时间线三类召回路由，供分路由检索。

纯编排、无 sqlite 依赖；检索与注入由调用方（context_assembly）执行。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from novelforge.core.prompts import plan_entity_context_query_prompt
from novelforge.services.memory import (
    load_creative_profile,
    resolve_entity_ids_by_names,
)

LOGGER = logging.getLogger("novelforge.entity_planning")

# 识别出的实体类别 → §3.1 检索路由
ROUTE_BY_TYPE = {
    "character": "character",
    "organization": "character",
    "location": "world",
    "item": "world",
    "ability": "world",
    "event": "timeline",
    "rule": "world",
}

# 每个路由的检索 source_types 白名单（§3.1：memory_* 与 knowledge_* 三套都要覆盖）
ROUTE_SOURCE_TYPES = {
    "character": [
        "knowledge_characters",
        "knowledge_relationships",
        "knowledge_items",
        "memory_character",
        "memory_relationship",
        "entity_character_card",
    ],
    "world": [
        "knowledge_world_rules",
        "knowledge_locations",
        "knowledge_organizations",
        "knowledge_items",
        "knowledge_abilities",
        "memory_world",
        "memory_active_constraint",
        "memory_au_rule",
        "entity_setting_card",
    ],
    "timeline": [
        "knowledge_timeline_events",
        "memory_timeline",
    ],
}


@dataclass
class EntityPlan:
    """一次生成/规划的实体识别结果。"""

    entities: list[dict] = field(default_factory=list)          # resolved: {name, entity_id, ...}
    entity_ids: list[str] = field(default_factory=list)
    unresolved_names: list[dict] = field(default_factory=list)   # {name, mention, purpose, reason}
    route_names: dict[str, list[str]] = field(default_factory=dict)
    raw_response: str = ""
    skipped: bool = False                                        # 冷启动/无文本 → True


def _extract_entities_from_response(raw: str, parsed: dict) -> list[dict]:
    del raw
    if not isinstance(parsed, dict):
        return []
    items = parsed.get("entities")
    if not isinstance(items, list):
        return []
    entities: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        entity_type = str(item.get("type") or "character").strip()
        entities.append({
            "name": name,
            "type": entity_type,
            "mention": str(item.get("mention") or "direct").strip(),
            "purpose": str(item.get("purpose") or "").strip(),
            "target_origin_entity_id": str(
                item.get("target_origin_entity_id") or item.get("origin_entity_id") or ""
            ).strip(),
        })
    return entities


def _known_entities_text(
    project_name: str,
    *,
    story_id: str | None = None,
    worldline_id: str | None = None,
    branch_id: str | None = None,
    snapshot_items: dict[str, dict] | None = None,
) -> str:
    """给 LLM 的已确认实体名单（供名称对齐，不照单全收）。"""
    try:
        if snapshot_items is not None:
            rows = []
            for item in snapshot_items.values():
                if not isinstance(item, dict):
                    continue
                entity_id = str(item.get("entity_id") or "").strip()
                name = str(
                    item.get("canonical_name")
                    or item.get("entity_canonical_name")
                    or (item.get("entity") or {}).get("canonical_name")
                    or item.get("name")
                    or ""
                ).strip()
                if name:
                    rows.append({"entity_id": entity_id, "canonical_name": name})
        else:
            from novelforge.services.memory import load_entity_master_rows

            rows = load_entity_master_rows(
                project_name,
                story_id=story_id,
                worldline_id=worldline_id,
                branch_id=branch_id,
            )
    except Exception:
        return ""
    names = [str(row.get("canonical_name") or "") for row in rows if str(row.get("canonical_name") or "")]
    names = [name for name in dict.fromkeys(names) if name][:80]
    return "\n".join(f"- {name}" for name in names) if names else ""


def plan_entity_context(
    project_name: str,
    story_id: str,
    *,
    capability: str,
    query_text: str,
    chapter_no: int | None = None,
    worldline_id: str | None = None,
    worldline_mode: str = "prefer",
    branch_id: str | None = None,
    snapshot_items: dict[str, dict] | None = None,
    responder=None,
) -> EntityPlan:
    """识别「本次生成/规划需要的实体」，解析 entity_id 并按路由分组。

    responder 可注入用于测试；默认走 `_call_generation_llm` + `_extract_json_object`。
    """
    plan = EntityPlan()
    text = str(query_text or "").strip()
    # 冷启动降级（D9）：无实体库时不做无谓的 LLM 识别
    try:
        if snapshot_items is not None:
            known_rows = [
                item for item in snapshot_items.values()
                if isinstance(item, dict)
                and str(
                    item.get("canonical_name")
                    or item.get("entity_canonical_name")
                    or (item.get("entity") or {}).get("canonical_name")
                    or item.get("name")
                    or ""
                ).strip()
            ]
        else:
            from novelforge.services.memory import load_entity_master_rows

            known_rows = load_entity_master_rows(
                project_name,
                story_id=story_id,
                worldline_id=worldline_id,
                branch_id=branch_id,
            )
        if not known_rows:
            plan.skipped = True
            return plan
    except Exception as exc:
        LOGGER.warning("entity planning pre-check failed: %s", exc)
        plan.skipped = True
        return plan
    if not text:
        plan.skipped = True
        return plan

    prompt = plan_entity_context_query_prompt(
        capability=str(capability or "write"),
        query_text=text,
        known_entities_text=_known_entities_text(
            project_name,
            story_id=story_id,
            worldline_id=worldline_id,
            branch_id=branch_id,
            snapshot_items=snapshot_items,
        ),
    )
    try:
        if responder is not None:
            # 测试注入：responder(project_name, story_id, prompt) -> dict（LLM 解析后的 JSON）
            parsed = responder(project_name, story_id, prompt)
        else:
            from novelforge.workflows.skills.common import _call_json_llm

            parsed = _call_json_llm(
                prompt,
                "实体识别失败：模型返回空响应。",
                usage_context={"project_name": project_name, "story_id": story_id, "operation": "context.plan_entities"},
            )
    except Exception as exc:
        LOGGER.warning("entity planning LLM call failed: %s", exc)
        return plan
    if not isinstance(parsed, dict):
        return plan
    entities = _extract_entities_from_response("", parsed)
    return _finalize(
        plan,
        project_name,
        story_id,
        entities,
        worldline_id,
        worldline_mode,
        branch_id=branch_id,
        snapshot_items=snapshot_items,
    )


def _finalize(
    plan: EntityPlan,
    project_name: str,
    story_id: str,
    entities: list[dict],
    worldline_id: str | None,
    worldline_mode: str,
    *,
    branch_id: str | None = None,
    snapshot_items: dict[str, dict] | None = None,
) -> EntityPlan:
    names = [str(item["name"]) for item in entities]
    ambiguous_names: set[str] = set()
    if snapshot_items is not None:
        resolved_map = {}
        by_name: dict[str, list[dict]] = {}
        for snapshot in snapshot_items.values():
            if not isinstance(snapshot, dict):
                continue
            entity = snapshot.get("entity") if isinstance(snapshot.get("entity"), dict) else {}
            entity_id = str(snapshot.get("entity_id") or entity.get("entity_id") or "").strip()
            canonical = str(
                snapshot.get("canonical_name")
                or snapshot.get("entity_canonical_name")
                or entity.get("canonical_name")
                or snapshot.get("name")
                or ""
            ).strip()
            if not entity_id or not canonical:
                continue
            aliases = snapshot.get("entity_aliases")
            if not isinstance(aliases, list):
                aliases = []
            for candidate in [canonical, *aliases]:
                key = str(candidate or "").strip().casefold()
                if key:
                    by_name.setdefault(key, []).append(snapshot)
        for name in names:
            candidates = by_name.get(str(name).strip().casefold()) or []
            item = next((value for value in entities if value.get("name") == name), {})
            origin_id = str(item.get("target_origin_entity_id") or "").strip()
            if origin_id:
                candidates = [
                    row for row in candidates
                    if str(row.get("entity_id") or (row.get("entity") or {}).get("entity_id") or "") == origin_id
                ]
            unique_ids = {
                str(row.get("entity_id") or (row.get("entity") or {}).get("entity_id") or "").strip()
                for row in candidates
            }
            # 同名跨来源实体没有明确来源目标时不能碰巧选一条。
            if len(unique_ids) > 1:
                ambiguous_names.add(name)
                plan.unresolved_names.append({
                    **item,
                    "reason": "同名实体来源不唯一，需明确 target_origin_entity_id",
                })
                continue
            row = candidates[0] if len(unique_ids) == 1 and candidates else None
            if row:
                entity = row.get("entity") if isinstance(row.get("entity"), dict) else {}
                resolved_map[name] = {
                    "entity_id": str(row.get("entity_id") or entity.get("entity_id") or ""),
                    "canonical_name": str(
                        row.get("canonical_name")
                        or row.get("entity_canonical_name")
                        or entity.get("canonical_name")
                        or row.get("name")
                        or ""
                    ),
                    "entity_type": str(
                        row.get("entity_type")
                        or row.get("entity_master_type")
                        or entity.get("entity_type")
                        or ""
                    ),
                    "story_id": story_id,
                    "matched_via": "checkpoint",
                }
    else:
        try:
            resolved_map = resolve_entity_ids_by_names(
                project_name,
                names,
                story_id=story_id,
                worldline_id=worldline_id,
                branch_id=branch_id,
            )
        except Exception as exc:
            LOGGER.warning("entity resolution failed: %s", exc)
            resolved_map = {}
    route_names: dict[str, list[str]] = {"character": [], "world": [], "timeline": []}
    resolved_entities: list[dict] = []
    seen_ids: set[str] = set()
    seen_canonical: set[str] = set()
    for item in entities:
        info = resolved_map.get(item["name"]) or {}
        entity_id = str(info.get("entity_id") or "")
        canonical = str(info.get("canonical_name") or "")
        if not entity_id:
            if item["name"] in ambiguous_names:
                continue
            plan.unresolved_names.append({
                "name": item["name"],
                "type": item.get("type", "character"),
                "mention": item.get("mention", "direct"),
                "purpose": item.get("purpose", ""),
                "reason": "库内无该实体记录",
            })
            continue
        if entity_id in seen_ids:
            # 别名/重复识别归一到同一实体：去重，不算 unresolved
            if canonical and canonical not in seen_canonical:
                seen_canonical.add(canonical)
                route = ROUTE_BY_TYPE.get(str(item.get("type") or "character"), "character")
                if canonical not in route_names[route]:
                    route_names[route].append(canonical)
            continue
        seen_ids.add(entity_id)
        resolved_entities.append({**item, **info})
        if canonical:
            seen_canonical.add(canonical)
            route = ROUTE_BY_TYPE.get(str(item.get("type") or "character"), "character")
            if canonical not in route_names[route]:
                route_names[route].append(canonical)
    plan.entities = resolved_entities
    plan.entity_ids = list(seen_ids)
    plan.route_names = {k: v for k, v in route_names.items() if v}
    return plan


def enrich_plan_via_retrieval(
    project_name: str,
    story_id: str,
    plan: EntityPlan,
    *,
    worldline_id: str | None = None,
    worldline_mode: str = "prefer",
    branch_id: str | None = None,
    visible_knowledge_ids: set[str] | None = None,
    snapshot_items: dict[str, dict] | None = None,
) -> EntityPlan:
    """P1 两段式「检索反查」兜底（遗留 #7 收口）。

    对 LLM 识别失败（unresolved）的名字做一次确定性词法检索，命中知识行后反查其归属
    实体（knowledge_id → entity_id），把库中确实存在的相关实体补进 plan（别名组没覆盖、
    但知识正文命中它的场景）。检索不可用/无命中时静默 no-op，绝不引入无关实体。

    说明：仅把「反查到的、库里真实存在的实体」补入；原 unresolved 名保留用于人工复核，
    不静默丢弃（D1a 规则③）。
    """
    unresolved_names = [u.get("name") for u in plan.unresolved_names if u.get("name")]
    if not unresolved_names or plan.skipped:
        return plan
    known_canonical = {
        str(item.get("canonical_name") or "") for item in plan.entities
    } | {name for route_names in plan.route_names.values() for name in route_names}
    try:
        from novelforge.services.memory import fetch_knowledge_entity_map
        from novelforge.services.retrieval import retrieve_context
        from novelforge.services.retrieval.common import KNOWLEDGE_SOURCE_TYPES

        query = " ".join(str(name) for name in unresolved_names[:8])
        hits = retrieve_context(
            project_name,
            query,
            top_k=5,
            allowed_scopes=["project", "canon"],
            allowed_source_types=list(KNOWLEDGE_SOURCE_TYPES),
            retrieval_mode="lexical",
            worldline_id=worldline_id,
            worldline_mode=worldline_mode,
            story_id=story_id,
            branch_id=branch_id,
            visible_knowledge_ids=visible_knowledge_ids,
        )
    except Exception:
        return plan
    knowledge_ids: list[str] = []
    for hit in hits:
        metadata = hit.chunk.metadata if isinstance(hit.chunk.metadata, dict) else {}
        knowledge_id = str(metadata.get("knowledge_id") or "")
        if knowledge_id:
            knowledge_ids.append(knowledge_id)
    if not knowledge_ids:
        return plan
    if snapshot_items is not None:
        # Strict branch resolution must use the checkpoint's entity projection;
        # looking up the live knowledge row can resolve a parent edit or a
        # different branch's same-named entity.
        mapping = {}
        for knowledge_id in knowledge_ids:
            item = snapshot_items.get(knowledge_id)
            if not isinstance(item, dict):
                continue
            entity = item.get("entity") if isinstance(item.get("entity"), dict) else {}
            canonical = str(
                item.get("canonical_name")
                or item.get("entity_canonical_name")
                or entity.get("canonical_name")
                or ""
            ).strip()
            entity_id = str(item.get("entity_id") or entity.get("entity_id") or "").strip()
            if canonical and entity_id:
                mapping[knowledge_id] = {
                    "entity_id": entity_id,
                    "canonical_name": canonical,
                    "entity_type": str(item.get("entity_type") or entity.get("entity_type") or ""),
                }
    else:
        try:
            mapping = fetch_knowledge_entity_map(project_name, knowledge_ids)
        except Exception:
            return plan
    existing_ids = set(plan.entity_ids)
    for value in mapping.values():
        canonical = str(value.get("canonical_name") or "")
        entity_id = str(value.get("entity_id") or "")
        if not canonical or not entity_id or entity_id in existing_ids or canonical in known_canonical:
            continue
        existing_ids.add(entity_id)
        known_canonical.add(canonical)
        route = ROUTE_BY_TYPE.get(str(value.get("entity_type") or "character"), "character")
        plan.entities.append({**value, "name": canonical, "mention": "retrieval", "purpose": "检索反查补集"})
        plan.route_names.setdefault(route, []).append(canonical)
    plan.entity_ids = list(existing_ids)
    return plan
