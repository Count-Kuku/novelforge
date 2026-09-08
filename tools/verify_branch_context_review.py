"""Exercise actual branch context assembly, beyond snapshot-table assertions."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.verify_utils import isolated_workspace
from storage import open_project_db
from novelforge.services import memory
from novelforge.workflows import interactive_writing
from novelforge.workflows.context_assembly import assemble_generation_context, render_context_for_prompt


def main() -> int:
    failures: list[str] = []
    checks: list[str] = []

    def check(condition: bool, label: str) -> None:
        (checks if condition else failures).append(label)

    previous = os.environ.get("NOVELFORGE_DISABLE_BACKGROUND_TASKS")
    os.environ["NOVELFORGE_DISABLE_BACKGROUND_TASKS"] = "1"
    try:
        with isolated_workspace("novelforge_branch_context_review_"):
            project = memory.create_project("branch_context_review")
            story = memory.create_story(project, "Context story", creation_mode="conversational")["story_id"]
            branch = memory.ensure_story_branch(project, story)["branch_id"]

            def write_fact(knowledge_id: str, summary: str, *, target: str | None = branch, policy: str = "always") -> None:
                memory.upsert_knowledge_category_item_record(project, "world_rules", {
                    "id": knowledge_id, "name": knowledge_id, "summary": summary,
                    "story_id": story if target else None,
                    "setting_scope": "story" if target else "project",
                    "branch_id": target, "worldline_id": "main", "version_scope": "project_main",
                    "status": "confirmed", "setting_role": "core", "setting_field": "world",
                    "injection_policy": policy,
                })

            write_fact("stable_fact", "STABLE_ALIVE")
            character = {"id": "card_character", "name": "Frozen card character", "summary": "FROZEN_CHARACTER_STATE", "story_id": story, "branch_id": branch, "setting_scope": "story", "injection_policy": "retrieval"}
            memory.upsert_knowledge_category_item_record(project, "characters", character)
            write_fact("private_manual", "MANUAL_SECRET", policy="manual_only")
            write_fact("unbound_public", "UNBOUND_PROJECT", target=None)
            memory.save_story_rules(project, story, {"all": ["RULE_BEFORE_FORK"]})
            session = interactive_writing.create_writing_session(project, story, session_goal="test context", branch_id=branch, auto_extract_mode="manual")
            with open_project_db(memory.project_path(project)) as conn:
                conn.execute("INSERT INTO creative_turns(turn_id,session_id,turn_index,user_message,action_type,status,branch_id) VALUES ('review_turn',?,1,'','generate','completed',?)", (session["session_id"], branch))
                conn.execute("INSERT INTO creative_fragments(fragment_id,session_id,turn_id,content,status,content_hash,branch_id) VALUES ('review_f1',?,'review_turn','F1 text','accepted','f1hash',?)", (session["session_id"], branch))
                conn.execute("UPDATE creative_sessions SET active_fragment_id='review_f1' WHERE session_id=?", (session["session_id"],))
                conn.commit()
            checkpoint = memory.create_story_checkpoint(project, story, branch, frontier_fragment_id="review_f1", extraction_status="ready")
            forked = memory.fork_story_branch(project, story, parent_branch_id=branch, name="Frozen fork", fork_fragment_id="review_f1", fork_checkpoint_id=checkpoint["checkpoint_id"])
            child = forked.get("branch", forked)
            child_branch = child["branch_id"]
            write_fact("stable_fact", "PARENT_DEAD")
            memory.upsert_knowledge_category_item_record(project, "characters", {**character, "summary": "FUTURE_CHARACTER_STATE"})
            memory.save_story_rules(project, story, {"all": ["RULE_AFTER_FORK"]})

            def context_text() -> str:
                return render_context_for_prompt(assemble_generation_context(
                    project, story_id=story, branch_id=child_branch,
                    capability="creative_writing", query="STABLE_ALIVE UNBOUND_PROJECT MANUAL_SECRET",
                    retrieval_mode="lexical", retrieval_profile="drafting", enable_entity_planning=False,
                ))

            text = context_text()
            check("STABLE_ALIVE" in text, "actual child prompt contains inherited frozen fact")
            check("PARENT_DEAD" not in text, "actual child prompt excludes later parent edit")
            check("UNBOUND_PROJECT" not in text, "actual child prompt excludes unbound project knowledge")
            check("MANUAL_SECRET" not in text, "manual-only knowledge is not silently always-injected")
            check("RULE_BEFORE_FORK" in text and "RULE_AFTER_FORK" not in text, "actual child prompt uses frozen story rules")
            setting_cards = json.dumps(memory.load_setting_entity_cards(project, story_id=story, branch_id=child_branch), ensure_ascii=False)
            character_cards = json.dumps(memory.load_character_entity_cards(project, story_id=story, branch_id=child_branch), ensure_ascii=False)
            graph = json.dumps(memory.load_knowledge_graph(project, story_id=story, branch_id=child_branch), ensure_ascii=False)
            check("STABLE_ALIVE" in setting_cards and "PARENT_DEAD" not in setting_cards, "setting entity cards read frozen facts instead of live parent rows")
            check("FROZEN_CHARACTER_STATE" in character_cards and "FUTURE_CHARACTER_STATE" not in character_cards, "character entity cards read frozen facts instead of live parent rows")
            check("FUTURE_CHARACTER_STATE" not in graph and "PARENT_DEAD" not in graph, "knowledge graph cannot expose post-fork parent state")
            planned_calls: list[bool] = []
            def identify_visible_entity(*_args, **_kwargs):
                planned_calls.append(True)
                return {"entities": [{"name": "stable_fact", "type": "rule", "mention": "direct", "purpose": "reference"}]}
            entity_context = render_context_for_prompt(assemble_generation_context(
                project, story_id=story, branch_id=child_branch, capability="creative_writing",
                query="stable_fact", retrieval_mode="lexical", enable_entity_planning=True,
                _entity_plan_responder=identify_visible_entity,
            ))
            check(bool(planned_calls), "entity planning remains available in a strict child branch")
            check("STABLE_ALIVE" in entity_context and "PARENT_DEAD" not in entity_context and "UNBOUND_PROJECT" not in entity_context, "entity planning uses frozen child facts rather than live parent projections")
            selected_manual = render_context_for_prompt(assemble_generation_context(
                project, story_id=story, branch_id=child_branch, capability="creative_writing", query="manual selection",
                manual_knowledge_ids=["private_manual"], retrieval_mode="lexical", enable_entity_planning=False,
            ))
            check("MANUAL_SECRET" in selected_manual, "explicit selection can include inherited manual-only knowledge")
            write_fact("child_addition", "CHILD_CURRENT_FACT", target=child_branch)
            check("CHILD_CURRENT_FACT" in context_text(), "new child knowledge becomes visible through normal write path")
            memory.create_story_checkpoint(project, story, child_branch, allow_current_state=True)
            check("STABLE_ALIVE" in context_text(), "new child checkpoint retains its inherited baseline")
            write_fact("child_addition", "CHILD_EDITED_FACT", target=child_branch)
            edited = context_text()
            check("CHILD_EDITED_FACT" in edited and "CHILD_CURRENT_FACT" not in edited, "local edits replace the current branch value after a checkpoint")
            memory.delete_knowledge_category_item_record(project, "world_rules", "child_addition")
            deleted = context_text()
            check("CHILD_EDITED_FACT" not in deleted and "CHILD_CURRENT_FACT" not in deleted, "deleted local knowledge is not resurrected by a checkpoint")
            child_session = forked["session"]["session_id"]
            with open_project_db(memory.project_path(project)) as conn:
                parent = str(forked["session"].get("active_fragment_id") or "") or None
                for index, fragment_id in enumerate(["temporal_f1", "temporal_f2"], 100):
                    conn.execute("INSERT INTO creative_turns(turn_id,session_id,turn_index,user_message,action_type,status,branch_id) VALUES (?,?,?,'','continue','completed',?)", (fragment_id, child_session, index, child_branch))
                    conn.execute("INSERT INTO creative_fragments(fragment_id,session_id,turn_id,parent_fragment_id,content,status,content_hash,branch_id) VALUES (?,?,?,?,?,'accepted','hash',?)", (fragment_id, child_session, fragment_id, parent, fragment_id, child_branch))
                    parent = fragment_id
                conn.commit()
            for fact_id, anchor, summary in [("temporal_dead", "temporal_f2", "CURRENT_DEAD"), ("temporal_alive", "temporal_f1", "OBSOLETE_ALIVE")]:
                memory.upsert_knowledge_category_item_record(project, "characters", {
                    "id": fact_id, "name": "时序人物", "summary": summary,
                    "story_id": story, "branch_id": child_branch, "setting_scope": "story",
                    "setting_field": "status", "setting_role": "core", "injection_policy": "always",
                    "source_segment_id": anchor,
                })
            temporal_text = context_text()
            check("CURRENT_DEAD" in temporal_text and "OBSOLETE_ALIVE" not in temporal_text, "actual generation uses F2 state even when no-chapter F1 extraction finishes later")
    finally:
        if previous is None:
            os.environ.pop("NOVELFORGE_DISABLE_BACKGROUND_TASKS", None)
        else:
            os.environ["NOVELFORGE_DISABLE_BACKGROUND_TASKS"] = previous
    print(json.dumps({"ok": not failures, "checks": checks, "failures": failures}, ensure_ascii=False, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
