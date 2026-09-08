"""Frozen graph endpoints remain connected to their branch-local entity cards."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from novelforge.services.memory.knowledge_center import _snapshot_entity_cards, _snapshot_story_graph
from novelforge.workflows.interactive_writing._fragment_ops import _source_entity_candidates, _attach_source_entity_mapping
from storage.repositories.entity_identity import normalize_name


def main():
    def fact(entity_id, name, **extra):
        return {"knowledge_id": "fact_" + entity_id, "entity_id": entity_id, "name": name,
                "entity_type": "character", "summary": "frozen " + name,
                "entity": {"entity_id": entity_id, "canonical_name": name, "entity_type": "character"}, **extra}

    relation = {
        "knowledge_id": "relation", "entity_id": "relationship_record", "name": "联盟",
        "entity_type": "relationship", "branch_id": "child",
        "source_origin_entity_id": "public_a",
        "entity_relations": [{"edge_id": "alliance", "source_node_id": "child_a", "target_node_id": "only_endpoint", "relation_type": "ally"}],
        "related_entities": [
            {"entity_id": "child_a", "canonical_name": "同名角色", "entity_type": "character"},
            {"entity_id": "only_endpoint", "canonical_name": "仅有关系的角色", "entity_type": "character"},
        ],
    }
    visible = {
        "inherited": fact("parent_a", "同名角色", origin_entity_id="public_a", visible_from_checkpoint=True, origin_branch_id="parent", branch_id="child"),
        "other_source": fact("parent_b", "同名角色", origin_entity_id="public_b", visible_from_checkpoint=True, origin_branch_id="parent", branch_id="child"),
        "relation": relation,
    }
    graph = _snapshot_story_graph(visible)
    nodes = {node["node_id"]: node for node in graph["nodes"]}
    assert all(edge[side] in nodes for edge in graph["edges"] for side in ("source_node_id", "target_node_id"))
    assert graph["edges"][0]["target_name"] == "仅有关系的角色"
    assert "parent_a" not in nodes and "child_a" in nodes and "parent_b" in nodes
    cards = _snapshot_entity_cards(visible, entity_type="character", max_cards=80)
    selected = next(card for card in cards if card["id"] == "child_a")
    assert any("仅有关系的角色" in value for value in selected["relationships"])
    visible["new_fact"] = fact("child_a", "同名角色", origin_entity_id="public_a", branch_id="child")
    cards = _snapshot_entity_cards(visible, entity_type="character", max_cards=80)
    assert len(cards) == 2 and len(next(card for card in cards if card["id"] == "child_a")["source_knowledge_ids"]) == 2
    visible["new_fact"]["related_entities"] = list(relation["related_entities"])
    relation["fact_key"] = "relationship_status"
    candidates = _source_entity_candidates("unused", "story", "child", list(visible.values()))
    choices = candidates[("character", normalize_name("同名角色"))]
    assert {choice["entity_id"] for choice in choices} == {"public_a", "public_b"}
    endpoint = candidates[("character", normalize_name("仅有关系的角色"))][0]
    assert all(not fact["fact_key"] for fact in endpoint["facts"])
    mapped = _attach_source_entity_mapping("unused", "story", "child", {
        "category": "items", "name": "剑",
        "owners": [{"name": "同名角色", "entity_id": "forged", "worldline_id": "foreign"}],
        "users": ["仅有关系的角色"],
        "reference_origin_entities": {"owners": {"entity_id": "forged"}},
    }, candidates)
    assert mapped["owners"] == ["同名角色"] and mapped["reference_origin_entities"]["owners"] == [None]
    assert mapped["reference_origin_entities"]["users"][0]["entity_id"] == "only_endpoint"
    print(json.dumps({"ok": True, "checks": [
        "frozen relation endpoints exist as graph nodes without independent facts",
        "endpoint labels use frozen names instead of internal IDs",
        "explicit origin maps inherited nodes to the branch-local endpoint",
        "same-name entities from another source remain separate",
        "entity cards include branch-local relationships against frozen inherited facts",
        "inherited and new facts form one card through explicit origin identity",
        "frozen endpoint candidates reuse explicit origins without false same-source ambiguity",
        "an endpoint-only candidate cannot overwrite the relationship knowledge as an entity fact",
        "ambiguous reference text is retained without accepting model-forged graph identities",
        "unambiguous reference graph targets use the frozen source candidate",
    ]}, indent=2))


if __name__ == "__main__":
    main()
