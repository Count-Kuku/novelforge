"""Verify real relationship extraction, endpoint disambiguation and graph isolation."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.verify_utils import isolated_workspace
from novelforge.services import memory
from novelforge.services.memory import project_path
from novelforge.workflows import interactive_writing as writing, skills
from novelforge.workflows.interactive_writing._fragment_ops import resolve_fragment_entity_candidate
from storage.repositories.knowledge import _upsert_graph_relationship_edges
from storage.repositories.story_reference_libraries import mark_story_reference_strict


def main() -> int:
    checks: list[str] = []
    old = os.environ.get("NOVELFORGE_DISABLE_BACKGROUND_TASKS")
    os.environ["NOVELFORGE_DISABLE_BACKGROUND_TASKS"] = "1"
    try:
        with isolated_workspace("novelforge_relationship_endpoint_review_"):
            project = memory.create_project("relationship_review")
            story_id = memory.create_story(project, "关系故事", creation_mode="conversational")["story_id"]
            main_branch_id = memory.ensure_story_branch(project, story_id)["branch_id"]
            for item_id, name, worldline, label in (
                ("source_a", "Same", "world-a", "World A"),
                ("source_b", "Same", "world-b", "World B"),
            ):
                memory.upsert_knowledge_category_item_record(
                    project,
                    "characters",
                    {
                        "id": item_id,
                        "name": name,
                        "summary": item_id,
                        "story_id": story_id,
                        "branch_id": main_branch_id,
                        "setting_scope": "story",
                        "worldline_id": worldline,
                        "worldline_label": label,
                        "version_scope": "canon",
                        "setting_field": "status",
                        "status": "confirmed",
                    },
                )
            entity_ids = {
                (row["name"], row["worldline_id"]): row["entity_id"]
                for row in memory.load_knowledge_category(project, "characters")
            }
            source_a = entity_ids[("Same", "world-a")]
            source_b = entity_ids[("Same", "world-b")]

            # A strict side branch is required for the isolation assertion.
            # Marking the legacy story as confirmed is the same gate used by
            # the production branch service; no model or external source is
            # involved in this fixture.
            with memory.open_project_db(project_path(project).resolve()) as conn:
                conn.execute("BEGIN IMMEDIATE")
                mark_story_reference_strict(conn, story_id=story_id)
                conn.commit()
            fork = memory.fork_story_branch(
                project,
                story_id,
                parent_branch_id=main_branch_id,
                name="关系旁支",
                allow_current_state=True,
                create_session=False,
            )
            branch_id = fork["branch"]["branch_id"]

            session = writing.create_writing_session(
                project,
                story_id,
                session_goal="关系端点审查",
                branch_id=branch_id,
                auto_extract_mode="manual",
            )
            turn = memory.begin_creative_turn(
                project,
                session["session_id"],
                "write",
                action_type="generate",
                parent_fragment_id=None,
                story_id=story_id,
            )
            fragment = memory.complete_creative_turn(
                project,
                turn["turn_id"],
                {"session_id": session["session_id"], "content": "Same and Other ally."},
                story_id=story_id,
            )
            writing.accept_writing_fragment(
                project,
                story_id,
                session["session_id"],
                fragment["fragment_id"],
                extract_if_enabled=False,
                branch_id=branch_id,
            )
            extraction = {
                "success": True,
                "data": {
                    "knowledge_extraction": {
                        "items": [{
                            "category": "relationships",
                            "name": "Same-Other",
                            "summary": "ally",
                            "source": "Same",
                            "target": "Same",
                            "relation": "ally",
                            "details": {"subject": "Same", "object": "Other"},
                        }],
                    },
                },
            }
            with patch.object(skills, "extract_reference_knowledge", return_value=extraction):
                result = writing.extract_fragment_knowledge(
                    project,
                    story_id,
                    session["session_id"],
                    fragment["fragment_id"],
                    branch_id=branch_id,
                )
            candidate = result["candidates"][0]
            assert candidate["entity_resolution_status"] == "pending_confirmation"
            assert candidate["entity_resolution_endpoint"] == "source"
            assert set(candidate["entity_resolution_candidates"]) == {
                entity_ids[("Same", "world-a")],
                entity_ids[("Same", "world-b")],
            }
            assert {option.get("worldline_label") for option in candidate["entity_resolution_options"]} == {"World A", "World B"}
            checks.append("真实关系提炼在同名来源下先挂起 source 端点并保留可读来源")

            selected = resolve_fragment_entity_candidate(
                project,
                story_id,
                branch_id,
                candidate["pending_id"],
                source_b,
            )
            assert selected["entity_resolution_status"] == "pending_confirmation"
            assert selected["entity_resolution_endpoint"] == "target"
            assert selected["source_origin_entity_id"] == source_b
            assert set(selected["entity_resolution_candidates"]) == {source_a, source_b}
            checks.append("选择 source 后只推进到 target，双方歧义按端点逐次确认")

            selected = resolve_fragment_entity_candidate(
                project,
                story_id,
                branch_id,
                candidate["pending_id"],
                source_a,
            )
            assert selected["entity_resolution_status"] == "resolved"
            assert selected["target_origin_entity_id"] == source_a
            assert memory.confirm_pending_knowledge_items(project, [candidate["pending_id"]]) == 1
            checks.append("用户逐次选择两个端点后无需再次调用模型即可完成解析")


            graph = memory.load_knowledge_graph(project, story_id=story_id, branch_id=branch_id)
            edges = [edge for edge in graph["edges"] if edge.get("relation_type") == "ally"]
            assert len(edges) == 1
            edge = edges[0]
            assert edge["source_name"] == "Same" and edge["target_name"] == "Same"
            assert edge["source_node_id"] != edge["target_node_id"]
            assert edge["source_node_id"] not in {source_a, source_b}
            assert edge["target_node_id"] not in {source_a, source_b}
            checks.append("load_knowledge_graph 返回的图边使用当前旁支私有物理端点且保留名称")

            with memory.open_project_db(project_path(project).resolve()) as conn:
                _upsert_graph_relationship_edges(
                    conn,
                    knowledge_id="unmapped-relationship",
                    story_id=story_id,
                    item={
                        "category": "relationships",
                        "branch_id": branch_id,
                        "worldline_id": "unknown-world",
                        "version_scope": "project_main",
                        "source": "Same",
                        "target": "Unknown",
                        "relation": "ally",
                    },
                )
                assert conn.execute(
                    "SELECT COUNT(*) FROM graph_edges WHERE json_extract(metadata_json, '$.knowledge_id') = 'unmapped-relationship' AND deleted_at IS NULL"
                ).fetchone()[0] == 0
                checks.append("非主线裸名称关系不会静默创建第三端点")
    finally:
        if old is None:
            os.environ.pop("NOVELFORGE_DISABLE_BACKGROUND_TASKS", None)
        else:
            os.environ["NOVELFORGE_DISABLE_BACKGROUND_TASKS"] = old
    print(json.dumps({"ok": True, "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
