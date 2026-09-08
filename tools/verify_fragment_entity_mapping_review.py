"""Real extraction keeps source identity, scope and ambiguity across async work."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.verify_utils import isolated_workspace
from novelforge.services import memory
from novelforge.workflows import interactive_writing as writing, skills, source_workflows


@patch.dict("os.environ", {"NOVELFORGE_DISABLE_BACKGROUND_TASKS": "1"})
def main():
    checks = []
    with isolated_workspace("novelforge_entity_mapping_review_"):
        project = memory.create_project("entity_mapping_review")
        story = memory.create_story(project, "Entity mapping", creation_mode="conversational")["story_id"]
        branch = memory.ensure_story_branch(project, story)["branch_id"]
        for world in ("source_a", "source_b"):
            memory.upsert_knowledge_category_item_record(project, "characters", {"id": world, "name": "同名角色", "summary": world, "story_id": story, "branch_id": branch, "setting_scope": "story", "worldline_id": world, "version_scope": "canon", "setting_field": "status"})
        entity_a = next(item["entity_id"] for item in memory.load_knowledge_category(project, "characters") if item["id"] == "source_a")
        session = writing.create_writing_session(project, story, session_goal="mapping", branch_id=branch, auto_extract_mode="manual")
        turn = memory.begin_creative_turn(project, session["session_id"], "write", action_type="generate", parent_fragment_id=None, story_id=story)
        fragment = memory.complete_creative_turn(project, turn["turn_id"], {"session_id": session["session_id"], "content": "同名角色已经改变了状态。"}, story_id=story)
        writing.accept_writing_fragment(project, story, session["session_id"], fragment["fragment_id"], extract_if_enabled=False, branch_id=branch)
        try:
            writing.extract_fragment_knowledge(project, story, session["session_id"], fragment["fragment_id"], branch_id="wrong_branch")
        except ValueError:
            checks.append("conflicting explicit branch is rejected before extraction")
        else:
            raise AssertionError("foreign extraction branch accepted")

        def extracted(*args, **kwargs):
            memory.save_creative_profile(project, {"worldline_id": "changed_during_model"}, story)
            return {"success": True, "data": {"knowledge_extraction": {"items": [
                {"category": "characters", "name": "同名角色", "summary": "AMBIGUOUS_SOURCE", "setting_field": "status"},
                {"category": "characters", "name": "同名角色", "summary": "EXPLICIT_SOURCE_A", "setting_field": "status", "target_origin_entity_id": entity_a},
                {"category": "characters", "name": "同名角色", "summary": "FORGED_SLOT", "setting_field": "appearance", "target_origin_entity_id": entity_a, "origin_knowledge_id": "source_b"},
                {"category": "characters", "name": "同名角色", "summary": "MODEL_NEW_BYPASS", "target_origin_entity_id": "__new_entity__"},
                {"category": "characters", "name": "全新角色", "summary": "UNKNOWN_ORIGIN", "target_origin_entity_id": "foreign_entity"},
                {"category": "world_rules", "name": "新增规则", "summary": "NEW_RULE"},
            ]}}}
        confirmed_inputs = []
        def confirm(project_name, pending_ids, **kwargs):
            confirmed_inputs.extend(pending_ids)
            return memory.confirm_pending_knowledge_items_with_records(project_name, pending_ids)
        with patch.object(skills, "extract_reference_knowledge", side_effect=extracted), patch.object(source_workflows, "auto_confirm_pending_items_without_risk", side_effect=confirm):
            result = writing.extract_fragment_knowledge(project, story, session["session_id"], fragment["fragment_id"], branch_id=branch)
        candidates = {item["summary"]: item for item in result["candidates"]}
        ambiguous = candidates["AMBIGUOUS_SOURCE"]
        assert ambiguous["pending_id"] not in confirmed_inputs and ambiguous["pending_id"] in result["auto_confirm"]["blocked_ids"]
        checks.append("same-name source ambiguity remains pending instead of auto-confirming")
        mapped = candidates["EXPLICIT_SOURCE_A"]
        assert mapped["worldline_id"] == "source_a" and mapped["version_scope"] == "canon" and mapped["origin_knowledge_id"] == "source_a"
        checks.append("verified origin selects the matching source world, version and fact")
        saved = next(item for item in memory.load_knowledge_category(project, "characters") if item["summary"] == "EXPLICIT_SOURCE_A")
        assert saved["entity_id"] == entity_a and saved["branch_id"] == branch
        checks.append("verified origin mapping is used by actual entity persistence")
        assert candidates["FORGED_SLOT"].get("origin_knowledge_id") != "source_b"
        checks.append("model cannot redirect an unrelated inherited fact through a forged origin knowledge ID")
        assert candidates["MODEL_NEW_BYPASS"]["entity_resolution_status"] == "pending_confirmation"
        assert candidates["MODEL_NEW_BYPASS"]["pending_id"] not in confirmed_inputs
        checks.append("model cannot bypass source ambiguity by declaring the manual new-entity sentinel")
        assert candidates["NEW_RULE"]["worldline_id"] != "changed_during_model"
        checks.append("model-time profile edits cannot change the captured extraction source")
        try:
            memory.confirm_pending_knowledge_items(project, [ambiguous["pending_id"]])
        except ValueError:
            checks.append("unresolved source ambiguity cannot bypass explicit source selection")
        else:
            raise AssertionError("ambiguous source confirmed without selecting origin")
        from novelforge.workflows.interactive_writing._fragment_ops import resolve_fragment_entity_candidate
        selected = resolve_fragment_entity_candidate(project, story, branch, ambiguous["pending_id"], entity_a)
        assert selected["entity_resolution_status"] == "resolved"
        assert memory.confirm_pending_knowledge_items(project, [ambiguous["pending_id"]]) == 1
        checks.append("user can select a frozen source and confirm without another model call")
        unknown = candidates["UNKNOWN_ORIGIN"]
        selected = resolve_fragment_entity_candidate(project, story, branch, unknown["pending_id"], "__new_entity__")
        assert selected["entity_resolution_status"] == "new" and not selected.get("origin_entity_id")
        assert memory.confirm_pending_knowledge_items(project, [unknown["pending_id"]]) == 1
        checks.append("unknown source can be explicitly recovered as a new entity without a forged origin")
    print(json.dumps({"ok": True, "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
