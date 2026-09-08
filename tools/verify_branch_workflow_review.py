"""Real write/accept/extract/fork regression with a deterministic late result."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.verify_utils import isolated_workspace
from novelforge.services import memory
from novelforge.services.memory import branches as branch_service
from storage.repositories import branches as branch_repository
from novelforge.workflows import interactive_writing as writing, skills, source_workflows
from novelforge.workflows.context_assembly import assemble_generation_context, render_context_for_prompt


def main() -> int:
    failures: list[str] = []
    checks: list[str] = []

    def check(condition: bool, label: str) -> None:
        (checks if condition else failures).append(label)

    previous = os.environ.get("NOVELFORGE_DISABLE_BACKGROUND_TASKS")
    os.environ["NOVELFORGE_DISABLE_BACKGROUND_TASKS"] = "1"
    try:
        with isolated_workspace("novelforge_branch_workflow_review_"):
            project = memory.create_project("branch_workflow_review")
            atomic_story = memory.create_story(project, "Atomic acceptance", creation_mode="conversational")["story_id"]
            atomic_session = writing.create_writing_session(project, atomic_story, session_goal="Atomic probe", auto_extract_mode="manual")
            atomic_turn = memory.begin_creative_turn(project, atomic_session["session_id"], "Atomic probe", action_type="generate", parent_fragment_id=None, story_id=atomic_story)
            atomic_fragment = memory.complete_creative_turn(project, atomic_turn["turn_id"], {
                "session_id": atomic_session["session_id"], "content": "ATOMIC_ACCEPTANCE_PROBE",
            }, story_id=atomic_story)
            with patch.object(branch_service, "create_checkpoint_row", side_effect=RuntimeError("injected checkpoint failure")), patch.object(branch_repository, "create_checkpoint_row", side_effect=RuntimeError("injected checkpoint failure")), patch.object(memory, "create_checkpoint_row", side_effect=RuntimeError("injected checkpoint failure")):
                try:
                    memory.accept_creative_fragment(project, atomic_session["session_id"], atomic_fragment["fragment_id"], story_id=atomic_story)
                except RuntimeError:
                    pass
                else:
                    check(False, "checkpoint failure propagates from acceptance")
            atomic_bundle = memory.load_creative_session_bundle(project, atomic_session["session_id"], story_id=atomic_story)
            saved_atomic = next(item for item in atomic_bundle["fragments"] if item["fragment_id"] == atomic_fragment["fragment_id"])
            check(saved_atomic["status"] == "proposed", "checkpoint failure rolls back acceptance in the same transaction")
            implicit_turn = memory.begin_creative_turn(project, atomic_session["session_id"], "Continue atomically", action_type="continue", parent_fragment_id=atomic_fragment["fragment_id"], story_id=atomic_story)
            implicit_payload = {"session_id": atomic_session["session_id"], "parent_fragment_id": atomic_fragment["fragment_id"], "content": "IMPLICIT_ACCEPTANCE_PROBE"}
            with patch.object(branch_repository, "create_checkpoint_row", side_effect=RuntimeError("injected implicit checkpoint failure")):
                try:
                    memory.complete_creative_turn(project, implicit_turn["turn_id"], implicit_payload, story_id=atomic_story, accept_fragment_id=atomic_fragment["fragment_id"])
                except RuntimeError:
                    pass
                else:
                    check(False, "implicit acceptance propagates checkpoint failure")
            atomic_bundle = memory.load_creative_session_bundle(project, atomic_session["session_id"], story_id=atomic_story)
            check(len(atomic_bundle["fragments"]) == 1 and atomic_bundle["fragments"][0]["status"] == "proposed", "checkpoint failure rolls back implicit acceptance and its generated child")
            memory.complete_creative_turn(project, implicit_turn["turn_id"], implicit_payload, story_id=atomic_story, accept_fragment_id=atomic_fragment["fragment_id"])
            implicit_checkpoints = memory.list_story_checkpoints(project, atomic_story, memory.default_branch_id(atomic_story))
            check(any(cp.get("frontier_fragment_id") == atomic_fragment["fragment_id"] for cp in implicit_checkpoints), "successful continuation seals its implicitly accepted parent base")
            story = memory.create_story(project, "Workflow story", creation_mode="conversational")["story_id"]
            branch = memory.ensure_story_branch(project, story)["branch_id"]

            def fact(knowledge_id: str, summary: str, fragment_id: str | None = None) -> None:
                memory.upsert_knowledge_category_item_record(project, "world_rules", {
                    "id": knowledge_id, "name": knowledge_id, "summary": summary,
                    "story_id": story, "setting_scope": "story", "branch_id": branch,
                    "worldline_id": "main", "version_scope": "project_main", "status": "confirmed",
                    "setting_role": "core", "setting_field": "world", "injection_policy": "always",
                    "source_segment_id": fragment_id, "source_origin": "interactive_fragment" if fragment_id else "manual",
                })

            fact("base_fact", "BASE_BEFORE_F1")
            session = writing.create_writing_session(project, story, session_goal="offline workflow", branch_id=branch, auto_extract_mode="manual")
            session_id = session["session_id"]

            def complete_fragment(content: str, parent: str | None) -> dict:
                turn = memory.begin_creative_turn(project, session_id, "Write a fragment", action_type="continue" if parent else "generate", parent_fragment_id=parent, story_id=story)
                return memory.complete_creative_turn(project, turn["turn_id"], {
                    "session_id": session_id, "parent_fragment_id": parent, "content": content,
                }, story_id=story)

            first = complete_fragment("ACCEPTED_F1_PROSE", None)
            writing.accept_writing_fragment(project, story, session_id, first["fragment_id"], extract_if_enabled=False, branch_id=branch)
            captured = memory.list_story_checkpoints(project, story, branch)
            check(any(cp.get("frontier_fragment_id") == first["fragment_id"] for cp in captured), "acceptance captures an immutable F1 base before extraction")

            def finish_after_f2(*_args, **_kwargs) -> dict:
                second = complete_fragment("FUTURE_F2_PROSE", first["fragment_id"])
                fact("future_fact", "FUTURE_KNOWLEDGE_FROM_F2", second["fragment_id"])
                writing.accept_writing_fragment(project, story, session_id, second["fragment_id"], extract_if_enabled=False, branch_id=branch)
                return {"success": True, "status": "completed", "data": {"knowledge_extraction": {"items": [
                    {"category": "world_rules", "name": "LATE_F1_RESULT", "summary": "LATE_F1_RESULT", "setting_field": "world"},
                ]}}}

            def confirm_extracted(project_name, pending_ids, **_kwargs):
                return memory.confirm_pending_knowledge_items_with_records(project_name, pending_ids)

            with patch.object(skills, "extract_reference_knowledge", side_effect=finish_after_f2), patch.object(source_workflows, "auto_confirm_pending_items_without_risk", side_effect=confirm_extracted):
                extraction = writing.extract_fragment_knowledge(project, story, session_id, first["fragment_id"], branch_id=branch)
            check(extraction.get("status") == "completed", "late F1 extraction completes through normal workflow")
            try:
                result = memory.fork_story_branch(project, story, parent_branch_id=branch, name="Historical F1", fork_fragment_id=first["fragment_id"])
            except ValueError as exc:
                check(False, f"completed F1 can fork without manually manufacturing a checkpoint: {exc}")
            else:
                child_branch = result.get("branch", result)["branch_id"]
                check(True, "completed F1 can fork without manually manufacturing a checkpoint")
                text = render_context_for_prompt(assemble_generation_context(project, story_id=story, branch_id=child_branch, capability="creative_writing", query="BASE_BEFORE_F1 FUTURE_KNOWLEDGE_FROM_F2 LATE_F1_RESULT", retrieval_mode="lexical", enable_entity_planning=False))
                check("BASE_BEFORE_F1" in text and "FUTURE_KNOWLEDGE_FROM_F2" not in text, "late extraction seals captured F1 state without F2 knowledge")
                check("LATE_F1_RESULT" in text, "sealed F1 checkpoint includes its own late confirmed extraction result")
                child_session = result.get("session") or {}
                child_bundle = memory.load_creative_session_bundle(project, child_session.get("session_id", ""), story_id=story) if child_session else None
                prose = "\n".join(fragment.get("content", "") for fragment in (child_bundle or {}).get("fragments", []))
                check("ACCEPTED_F1_PROSE" in prose and "FUTURE_F2_PROSE" not in prose, "fork returns a resumable session containing only the F1 prefix")
    finally:
        if previous is None:
            os.environ.pop("NOVELFORGE_DISABLE_BACKGROUND_TASKS", None)
        else:
            os.environ["NOVELFORGE_DISABLE_BACKGROUND_TASKS"] = previous
    print(json.dumps({"ok": not failures, "checks": checks, "failures": failures}, ensure_ascii=False, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
