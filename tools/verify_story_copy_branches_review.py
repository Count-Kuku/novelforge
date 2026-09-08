"""Verify a copied story owns its branch chapters, sessions and knowledge."""

from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from novelforge.services import memory
from tools.verify_utils import isolated_workspace


@patch.dict("os.environ", {"NOVELFORGE_DISABLE_BACKGROUND_TASKS": "1"})
def main() -> int:
    checks: list[str] = []
    failures: list[str] = []

    def check(value: bool, label: str) -> None:
        (checks if value else failures).append(label)

    with isolated_workspace("novelforge_story_copy_branches_"):
        project = memory.create_project("story_copy_branches")
        source = memory.create_story(project, "Source story", creation_mode="conversational")["story_id"]
        main_branch = memory.default_branch_id(source)
        child = memory.fork_story_branch(project, source, parent_branch_id=main_branch, name="Side story", allow_current_state=True)["branch"]["branch_id"]
        memory.save_chapter(project, 1, "SOURCE_MAIN_CHAPTER", source, main_branch)
        memory.save_chapter(project, 1, "SOURCE_CHILD_CHAPTER", source, child)
        for identifier, branch, summary in [("main_fact", main_branch, "SOURCE_MAIN_FACT"), ("child_fact", child, "SOURCE_CHILD_FACT")]:
            memory.upsert_knowledge_category_item_record(project, "characters", {
                "id": identifier, "name": "Shared character", "summary": summary,
                "story_id": source, "branch_id": branch, "setting_scope": "story",
                "worldline_id": "main", "version_scope": "project_main",
                "status": "confirmed", "setting_field": "status", "injection_policy": "retrieval",
            })
        memory.upsert_knowledge_category_item_record(project, "world_rules", {
            "id": "copy_core", "name": "Core rule", "summary": "CORE_COPY_ONCE",
            "story_id": source, "branch_id": main_branch, "setting_scope": "story",
            "setting_role": "core", "setting_field": "world", "injection_policy": "always",
        })
        copied = memory.copy_story(project, source, "Copied story")["story_id"]
        copied_core = [item for item in memory.load_knowledge_category(project, "world_rules") if item.get("story_id") == copied and item.get("summary") == "CORE_COPY_ONCE"]
        check(len(copied_core) == 1 and copied_core[0].get("branch_id") == memory.default_branch_id(copied), "core settings copy once through the same branch identity remapping")
        branches = memory.list_story_branches(project, copied, include_archived=True)
        with memory.open_project_db(memory.project_path(project).resolve()) as conn:
            checkpoints = conn.execute("SELECT cp.snapshot_manifest_json, cp.snapshot_hash FROM branch_checkpoints cp JOIN story_branches branch ON branch.branch_id=cp.branch_id WHERE branch.story_id=?", (copied,)).fetchall()
            check(bool(checkpoints) and all(hashlib.sha256(json.dumps(json.loads(row[0]), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest() == row[1] for row in checkpoints), "copied checkpoint hashes match their remapped manifests")
        by_name = {item["name"]: item for item in branches}
        check(len(branches) == 2 and all(item["branch_id"] not in {main_branch, child} for item in branches), "copy remaps all branches into the target story")
        copied_child = by_name.get("Side story", {}).get("branch_id")
        check(memory.load_chapter(project, 1, copied, memory.default_branch_id(copied)) == "SOURCE_MAIN_CHAPTER", "copied main chapter is readable")
        if copied_child:
            check(memory.load_chapter(project, 1, copied, copied_child) == "SOURCE_CHILD_CHAPTER", "copied branch chapter path follows remapped branch identity")
        else:
            check(False, "copied branch chapter path follows remapped branch identity")
        try:
            sessions = memory.list_creative_sessions(project, copied, include_archived=True)
            check(bool(sessions) and all(item["branch_id"] in {row["branch_id"] for row in branches} for item in sessions), "copied sessions reference only target-story branches")
        except Exception as exc:
            check(False, f"copied session can be read: {exc}")
        copied_facts = [item for item in memory.load_knowledge_category(project, "characters") if item.get("story_id") == copied]
        check({item.get("summary") for item in copied_facts} == {"SOURCE_MAIN_FACT", "SOURCE_CHILD_FACT"}, "whole-story copy includes all branch facts beyond core settings")
        child_fact = next((item for item in copied_facts if item.get("summary") == "SOURCE_CHILD_FACT"), None)
        if child_fact:
            check(child_fact.get("branch_id") == copied_child and child_fact.get("id") != "child_fact", "copied child fact has independent identity and ownership")
            memory.upsert_knowledge_category_item_record(project, "characters", {**child_fact, "summary": "COPY_EDIT"})
            original = next(item for item in memory.load_knowledge_category(project, "characters") if item.get("id") == "child_fact")
            check(original["summary"] == "SOURCE_CHILD_FACT", "editing copied branch knowledge leaves source story unchanged")
    print(json.dumps({"ok": not failures, "checks": checks, "failures": failures}, ensure_ascii=False, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
