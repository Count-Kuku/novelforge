"""Independent regression checks for branch migration and historical anchors.

Uses only in-memory SQLite and real repositories; no user data or model calls.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from storage.schema import _execute_migration_script, ensure_schema
from storage.repositories.branches import (
    create_checkpoint_row,
    default_branch_id,
    ensure_default_branch,
    fork_branch_rows,
)
from storage.repositories.knowledge import (
    upsert_knowledge_category_item, upsert_pending_knowledge_items,
    delete_pending_knowledge_items, delete_knowledge_category_item,
)


def main() -> int:
    failures: list[str] = []
    checks: list[str] = []

    def check(condition: bool, label: str) -> None:
        (checks if condition else failures).append(label)

    def rejects(callback, label: str) -> None:
        try:
            callback()
        except ValueError:
            checks.append(label)
        else:
            failures.append(label)

    with sqlite3.connect(":memory:") as legacy:
        legacy.row_factory = sqlite3.Row
        legacy.execute("PRAGMA foreign_keys=ON")
        paths = sorted((ROOT / "storage/migrations").glob("*.sql"))
        for path in paths:
            if int(path.name.split("_", 1)[0]) <= 20:
                _execute_migration_script(legacy, path.read_text(encoding="utf-8"))
        story_ids = ["a-b", "ab", "A", "a", "中文故事"]
        for story in story_ids:
            legacy.execute("INSERT INTO stories(story_id, name) VALUES (?, ?)", (story, story))
        old_identity = "|".join(("character", "legacycharacter", "story", "a-b", "legacy_world", "project_main"))
        old_entity = "entity_" + hashlib.sha256(old_identity.encode()).hexdigest()[:24]
        legacy.execute("INSERT INTO entities(entity_id,entity_type,canonical_name,story_id,worldline_id,setting_scope,version_scope) VALUES (?, 'character', 'Legacy character', 'a-b', 'legacy_world', 'story', 'project_main')", (old_entity,))
        legacy.execute("INSERT INTO knowledge_items(knowledge_id,story_id,category,name,setting_scope,worldline_id,entity_id,fact_key,valid_from_chapter,chapter_no) VALUES ('legacy_status','a-b','characters','Legacy character','story','legacy_world',?,'status',1,1)", (old_entity,))
        for path in paths:
            if int(path.name.split("_", 1)[0]) > 20:
                _execute_migration_script(legacy, path.read_text(encoding="utf-8"))
        for story in story_ids:
            branch = ensure_default_branch(legacy, story)
            check(branch["story_id"] == story, f"migration preserves story identity: {story}")
            check(branch["branch_id"] == default_branch_id(story), f"migration/service IDs agree: {story}")
        try:
            upsert_knowledge_category_item(legacy, "characters", {
                "id": "legacy_next_status", "name": "Legacy character", "summary": "Later status",
                "story_id": "a-b", "branch_id": default_branch_id("a-b"), "setting_scope": "story",
                "worldline_id": "legacy_world", "version_scope": "project_main",
                "setting_field": "status", "source_chapter_no": 9,
            })
        except sqlite3.IntegrityError:
            check(False, "schema-20 entity can accept a new main-branch fact after migration")
        else:
            new_entity = legacy.execute("SELECT entity_id FROM knowledge_items WHERE knowledge_id='legacy_next_status'").fetchone()[0]
            check(new_entity == old_entity, "schema-20 entity identity is preserved for main-branch continuation")
            check(legacy.execute("SELECT valid_to_chapter FROM knowledge_items WHERE knowledge_id='legacy_status'").fetchone()[0] == 9, "legacy fact supersession continues after migration")

    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        ensure_schema(conn)
        conn.execute("INSERT INTO stories(story_id, name) VALUES ('story', 'Story')")
        branch_id = ensure_default_branch(conn, "story")["branch_id"]
        conn.execute("INSERT INTO creative_sessions(session_id, story_id, branch_id) VALUES ('session', 'story', ?)", (branch_id,))

        def fragment(fragment_id: str, parent: str | None, order: int) -> None:
            conn.execute(
                "INSERT INTO creative_turns(turn_id, session_id, turn_index, user_message, action_type, status, branch_id) VALUES (?, 'session', ?, '', 'generate', 'completed', ?)",
                (f"turn_{fragment_id}", order, branch_id),
            )
            conn.execute(
                "INSERT INTO creative_fragments(fragment_id, session_id, turn_id, parent_fragment_id, content, status, content_hash, branch_id) VALUES (?, 'session', ?, ?, ?, 'accepted', ?, ?)",
                (fragment_id, f"turn_{fragment_id}", parent, fragment_id, hashlib.sha256(fragment_id.encode()).hexdigest(), branch_id),
            )

        def fact(summary: str) -> None:
            upsert_knowledge_category_item(conn, "characters", {
                "id": "character_state", "name": "角色", "summary": summary,
                "story_id": "story", "setting_scope": "story", "branch_id": branch_id,
                "worldline_id": "source_world", "status": "confirmed",
            })
            conn.execute("UPDATE knowledge_items SET branch_id=? WHERE knowledge_id='character_state'", (branch_id,))

        fragment("f1", None, 1)
        fact("ALIVE_AT_F1")
        cp1 = create_checkpoint_row(conn, branch_id=branch_id, frontier_fragment_id="f1")
        fragment("f2", "f1", 2)
        fact("DEAD_AT_F2")
        cp2 = create_checkpoint_row(conn, branch_id=branch_id, frontier_fragment_id="f2")
        child = fork_branch_rows(conn, story_id="story", parent_branch_id=branch_id, name="F1 fork", fork_fragment_id="f1")
        check(child["fork_checkpoint_id"] == cp1["checkpoint_id"], "fork selects exact F1 checkpoint, not a later prefix containing F1")
        frozen = "\n".join(row[0] for row in conn.execute("SELECT payload_json FROM branch_checkpoint_items WHERE checkpoint_id=?", (child["head_checkpoint_id"],)))
        check("ALIVE_AT_F1" in frozen and "DEAD_AT_F2" not in frozen, "historical fork excludes future facts")
        check('"f2"' not in frozen, "historical fork excludes future prose")
        rejects(lambda: fork_branch_rows(conn, story_id="story", parent_branch_id=branch_id, name="Wrong explicit anchor", fork_fragment_id="f1", fork_checkpoint_id=cp2["checkpoint_id"]), "explicit checkpoint must match frontier exactly")
        rejects(lambda: create_checkpoint_row(conn, branch_id=branch_id, frontier_fragment_id="missing"), "missing frontier cannot silently snapshot all fragments")
        fragment("f3", "f2", 3)
        pending = create_checkpoint_row(conn, branch_id=branch_id, frontier_fragment_id="f3", extraction_status="pending")
        rejects(lambda: fork_branch_rows(conn, story_id="story", parent_branch_id=branch_id, name="Unready fork", fork_checkpoint_id=pending["checkpoint_id"]), "pending checkpoint is not a ready fork anchor")
        current_before = create_checkpoint_row(conn, branch_id=branch_id, allow_current_state=True)
        fact("LATER_EDIT")
        revised = create_checkpoint_row(conn, branch_id=branch_id, allow_current_state=True)
        check(current_before["snapshot_hash"] != revised["snapshot_hash"], "snapshot hash changes with content even if knowledge IDs stay the same")
        repeated = create_checkpoint_row(conn, branch_id=branch_id, frontier_fragment_id="f2")
        check(repeated["snapshot_hash"] == cp2["snapshot_hash"], "repeated historical checkpoint does not absorb later edits")
        still_frozen = "\n".join(row[0] for row in conn.execute("SELECT payload_json FROM branch_checkpoint_items WHERE checkpoint_id=?", (child["head_checkpoint_id"],)))
        check(still_frozen == frozen, "parent edit leaves child snapshot unchanged")
        common_fact = {
            "category": "characters", "name": "Same character across branches",
            "story_id": "story", "setting_scope": "story", "worldline_id": "source_world",
            "version_scope": "project_main", "setting_field": "status", "status": "confirmed",
        }
        upsert_knowledge_category_item(conn, "characters", {
            **common_fact, "id": "parent_status", "summary": "Parent alive",
            "branch_id": branch_id, "source_chapter_no": 1,
        })
        upsert_knowledge_category_item(conn, "characters", {
            **common_fact, "id": "child_status", "summary": "Child dead",
            "branch_id": child["branch_id"], "source_chapter_no": 9,
        })
        parent_status = conn.execute("SELECT entity_id, valid_to_chapter, branch_id FROM knowledge_items WHERE knowledge_id='parent_status'").fetchone()
        child_status = conn.execute("SELECT entity_id, valid_to_chapter, branch_id FROM knowledge_items WHERE knowledge_id='child_status'").fetchone()
        check(parent_status["entity_id"] != child_status["entity_id"], "same character gets independent physical entity identity in each branch")
        check(parent_status["valid_to_chapter"] is None, "child supersession never closes a parent fact")
        check(parent_status["branch_id"] == branch_id and child_status["branch_id"] == child["branch_id"], "normal knowledge writes persist branch ownership")
        rejects(lambda: upsert_knowledge_category_item(conn, "characters", {
            **common_fact, "id": "parent_status", "branch_id": child["branch_id"],
        }), "existing knowledge identity cannot be moved to another branch")
        conn.execute("INSERT INTO stories(story_id,name) VALUES ('other_story','Other story')")
        other_branch = ensure_default_branch(conn, "other_story")["branch_id"]
        rejects(lambda: upsert_knowledge_category_item(conn, "characters", {
            **common_fact, "id": "cross_story_write", "name": "Cross story",
            "branch_id": other_branch,
        }), "knowledge repository rejects a branch owned by another story")
        rejects(lambda: upsert_knowledge_category_item(conn, "characters", {
            "id": "invalid_project_branch", "name": "Project fact", "setting_scope": "project",
            "branch_id": branch_id,
        }), "project knowledge cannot acquire private branch ownership")
        upsert_pending_knowledge_items(conn, [{
            **common_fact, "pending_id": "retained_pending", "branch_id": child["branch_id"], "status": "pending",
        }])
        rejects(lambda: upsert_pending_knowledge_items(conn, [{
            **common_fact, "pending_id": "retained_pending", "branch_id": branch_id, "status": "pending",
        }]), "existing pending identity cannot be moved to another branch")
        conn.execute("UPDATE story_branches SET status='archived' WHERE branch_id=?", (child["branch_id"],))
        try:
            upsert_pending_knowledge_items(conn, [{
                **common_fact, "pending_id": "active_pending", "branch_id": branch_id, "status": "pending",
            }])
            removed, _ = delete_pending_knowledge_items(conn, {"active_pending"})
        except ValueError:
            check(False, "archived branch pending items do not block another branch queue")
        else:
            check(removed == 1, "archived branch pending items do not block another branch queue")
        rejects(lambda: delete_pending_knowledge_items(conn, {"retained_pending"}), "archived pending candidates cannot be discarded through unscoped legacy calls")
        rejects(lambda: upsert_knowledge_category_item(conn, "characters", {
            **common_fact, "id": "archived_write", "name": "Archived write", "branch_id": child["branch_id"],
        }), "late knowledge write to archived branch is rejected")
        rejects(lambda: delete_knowledge_category_item(conn, "characters", "child_status"), "archived knowledge cannot be deleted through legacy service calls")
        from novelforge.services.memory.pending_knowledge import _append_knowledge_items_in_transaction
        try:
            saved, _, _ = _append_knowledge_items_in_transaction(conn, [{
                **common_fact, "id": "active_confirmation", "name": "Active confirmation",
                "branch_id": branch_id,
            }], scope="story", authority="curated")
        except ValueError:
            check(False, "archived confirmed facts do not block confirmation in another branch")
        else:
            check(saved == 1, "archived confirmed facts do not block confirmation in another branch")
        conn.execute("UPDATE story_branches SET status='archived' WHERE branch_id=?", (branch_id,))
        rejects(lambda: upsert_knowledge_category_item(conn, "characters", {
            **common_fact, "id": "archived_default_write", "name": "Default archived write",
        }), "omitting branch cannot bypass archived main write protection")

    print(json.dumps({"ok": not failures, "checks": checks, "failures": failures}, ensure_ascii=False, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
