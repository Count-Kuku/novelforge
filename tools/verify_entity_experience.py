from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = "0"

from novelforge.domain.knowledge_entities import (
    build_character_entity_cards,
    build_setting_entity_cards,
    timeline_item_sort_key,
)
from novelforge.services.memory import (
    create_project,
    create_story,
    load_knowledge_graph,
    load_knowledge_revisions,
    save_character_entities,
    update_confirmed_knowledge_item_record,
    upsert_knowledge_category_item_record,
)
from novelforge.services.retrieval.documents import gather_retrieval_documents
from tools.verify_utils import isolated_workspace
from ui.common import developer_mode_enabled


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def _save(project_name: str, category: str, item_id: str, name: str, *, story_id: str, typed_data: dict | None = None, **extra) -> dict:
    return upsert_knowledge_category_item_record(project_name, category, {
        "id": item_id,
        "category": category,
        "name": name,
        "summary": extra.pop("summary", name),
        "story_id": story_id,
        "setting_scope": "story",
        "worldline_id": "main",
        "worldline_label": "主线",
        "scope": "project",
        "authority": "project",
        "confidence": 0.92,
        "status": "confirmed",
        "typed_data": typed_data or {},
        **extra,
    })


def verify_live_projections(project_name: str, story_id: str) -> None:
    _save(
        project_name, "characters", "char_linyao", "林遥", story_id=story_id,
        summary="守夜人学徒。", source_title="人物设定集",
        typed_data={"roles": ["守夜人学徒"], "abilities": ["听风"]},
    )
    _save(
        project_name, "abilities", "ability_wind", "听风", story_id=story_id,
        typed_data={"users": ["林遥"], "effects": ["感知远处脚步"]},
    )
    _save(
        project_name, "items", "item_lamp", "星灯", story_id=story_id,
        typed_data={"owners": ["林遥"], "functions": ["照见灵迹"]},
    )
    _save(
        project_name, "timeline_events", "event_gate", "城门夜袭", story_id=story_id,
        source_title="第一卷年表",
        typed_data={"time": "第3夜", "order_hint": "003", "participants": ["林遥"], "locations": ["北城门"]},
    )
    _save(
        project_name, "world_rules", "rule_shadow", "影潮规则", story_id=story_id,
        source_title="世界设定集", typed_data={"domain": "影潮", "rule": "月落后影潮上涨。"},
    )

    cards = build_character_entity_cards(project_name)
    card = next(item for item in cards if item.get("name") == "林遥")
    check(any("听风" in value for value in card.get("abilities", [])), "角色中心聚合能力")
    check(any("星灯" in value for value in card.get("items", [])), "角色中心聚合道具")
    check(any("城门夜袭" in value for value in card.get("events", [])), "角色中心聚合参与事件")
    check(any(item.get("title") == "人物设定集" for item in card.get("sources", [])), "角色中心投影来源 chip")

    legacy = [{"id": "legacy", "name": "漂移副本", "summary": "不应参与实时投影或检索"}]
    save_character_entities(project_name, legacy)
    cards_after_legacy = build_character_entity_cards(project_name)
    check(not any(item.get("name") == "漂移副本" for item in cards_after_legacy), "旧实体资产不影响实时角色投影")
    source_types = {document.source_type for document in gather_retrieval_documents(project_name)}
    check("entity_character_card" not in source_types and "entity_setting_card" not in source_types, "检索不索引漂移实体副本")

    # Update the authoritative item and assert that the next projection changes
    # without a separate card save.
    authoritative = upsert_knowledge_category_item_record(project_name, "characters", {
        "id": "char_linyao", "category": "characters", "name": "林遥",
        "summary": "守夜人正式成员。", "story_id": story_id, "setting_scope": "story",
        "worldline_id": "main", "scope": "project", "authority": "project",
        "confidence": 0.93, "status": "confirmed", "revision_reason": "实体视图编辑验证",
        "typed_data": {"roles": ["守夜人"]},
    })
    check(bool(authoritative), "权威角色更新成功")
    projected = next(item for item in build_character_entity_cards(project_name) if item.get("name") == "林遥")
    check("正式成员" in str(projected.get("summary")), "卡片实时反映权威知识修订")
    check(len(load_knowledge_revisions(project_name, "char_linyao")) >= 2, "实体编辑保留知识修订链")

    world_cards = build_setting_entity_cards(project_name)
    rule_card = next(item for item in world_cards if item.get("primary_knowledge_id") == "rule_shadow")
    check(rule_card.get("setting_type") == "world_rules", "世界观中心聚合规则")
    check(any(item.get("title") == "世界设定集" for item in rule_card.get("sources", [])), "世界观中心投影来源 chip")


def verify_graph_projection(project_name: str, story_id: str, other_story_id: str) -> None:
    rel = _save(
        project_name, "relationships", "rel_linyao_muchen", "林遥与穆辰", story_id=story_id,
        typed_data={
            "subject": "林遥", "object": "穆辰", "relation_type": "盟友",
            "direction": "bidirectional", "status": "进行中",
        },
    )
    graph = load_knowledge_graph(project_name, story_id=story_id)
    owned = [edge for edge in graph.get("edges", []) if edge.get("knowledge_id") == "rel_linyao_muchen"]
    check(len(owned) == 1, "每条关系知识只投影一条活动边")
    check(owned[0].get("direction") == "bidirectional", "关系方向完整投影")

    revised = {
        **rel,
        "typed_data": {
            "subject": "林遥", "object": "穆辰", "relation_type": "敌对",
            "direction": "directed", "status": "决裂",
        },
        "summary": "林遥开始追查穆辰。",
        "revision_reason": "关系图编辑验证",
    }
    check(update_confirmed_knowledge_item_record(project_name, "relationships", "rel_linyao_muchen", revised), "关系图编辑写回权威知识")
    graph_after = load_knowledge_graph(project_name, story_id=story_id)
    owned_after = [edge for edge in graph_after.get("edges", []) if edge.get("knowledge_id") == "rel_linyao_muchen"]
    check(len(owned_after) == 1 and owned_after[0].get("relation_type") == "敌对", "关系修订替换旧投影边")

    _save(
        project_name, "relationships", "rel_other_story", "林遥与穆辰", story_id=other_story_id,
        typed_data={"subject": "林遥", "object": "穆辰", "relation_type": "陌生人", "direction": "undirected"},
    )
    main_nodes = {node.get("node_id") for node in load_knowledge_graph(project_name, story_id=story_id).get("nodes", [])}
    other_nodes = {node.get("node_id") for node in load_knowledge_graph(project_name, story_id=other_story_id).get("nodes", [])}
    check(main_nodes.isdisjoint(other_nodes), "同名关系节点按故事隔离")


def verify_timeline_and_modes() -> None:
    events = [
        {"id": "c", "name": "三", "typed_data": {"time": "第10日", "order_hint": "10"}},
        {"id": "a", "name": "一", "typed_data": {"time": "第2日", "order_hint": "2"}},
        {"id": "b", "name": "二", "typed_data": {"time": "第3日", "order_hint": "3"}},
    ]
    check([item["id"] for item in sorted(events, key=timeline_item_sort_key)] == ["a", "b", "c"], "时间轴使用自然顺序排序")
    previous = os.environ.pop("NOVELFORGE_DEVELOPER_MODE", None)
    try:
        check(not developer_mode_enabled(), "普通模式默认隐藏技术数据")
        os.environ["NOVELFORGE_DEVELOPER_MODE"] = "true"
        check(developer_mode_enabled(), "开发者模式可显式开启")
    finally:
        if previous is None:
            os.environ.pop("NOVELFORGE_DEVELOPER_MODE", None)
        else:
            os.environ["NOVELFORGE_DEVELOPER_MODE"] = previous


def main() -> int:
    with isolated_workspace("novelforge-entity-experience-"):
        project_name = create_project("entity-experience")
        story_id = create_story(project_name, "主故事")["story_id"]
        other_story_id = create_story(project_name, "镜像故事")["story_id"]
        verify_live_projections(project_name, story_id)
        verify_graph_projection(project_name, story_id, other_story_id)
        verify_timeline_and_modes()
    print({"ok": True, "checks": CHECKS})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
