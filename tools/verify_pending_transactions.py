from __future__ import annotations

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = "0"

from novelforge.services import memory
from novelforge.domain.knowledge_workflows import execute_pending_clear_plan
from novelforge.services.memory import (
    create_project,
    create_story,
    list_stories,
    load_auto_review_runs,
    load_knowledge_category,
    load_pending_knowledge_items,
    load_stories_index,
    project_path,
    queue_pending_knowledge_items,
    story_path,
)
from tools.verify_utils import isolated_workspace


def _expect(condition: bool, label: str, failures: list[str]) -> None:
    if not condition:
        failures.append(label)


def _expect_raises(callback, exception_type: type[BaseException], label: str, failures: list[str]) -> None:
    try:
        callback()
    except exception_type:
        return
    except Exception as exc:
        failures.append(f"{label}:wrong_exception:{type(exc).__name__}")
        return
    failures.append(f"{label}:missing_exception")


def _queue(project_name: str, rows: list[dict]) -> int:
    return queue_pending_knowledge_items(
        project_name,
        rows,
        scope="project",
        authority="curated",
    )


def _verify_audit_transaction(project_name: str, failures: list[str]) -> None:
    _queue(project_name, [
        {"pending_id": "audit-fail-confirm", "category": "items", "name": "Confirm rollback"},
        {"pending_id": "audit-fail-discard", "category": "items", "name": "Discard rollback"},
    ])
    with patch.object(memory, "sync_auto_review_runs", side_effect=OSError("injected audit failure")):
        _expect_raises(
            lambda: memory.confirm_pending_knowledge_items_with_records(
                project_name,
                ["audit-fail-confirm"],
                discard_pending_ids=["audit-fail-discard"],
                audit_run={"run_id": "audit-must-rollback", "source_type": "verification"},
            ),
            OSError,
            "audit_failure_propagates",
            failures,
        )
    pending_ids = {item.get("pending_id") for item in load_pending_knowledge_items(project_name)}
    _expect(
        {"audit-fail-confirm", "audit-fail-discard"}.issubset(pending_ids),
        "audit_failure_restores_pending_rows",
        failures,
    )
    _expect(
        not any(
            item.get("source_pending_id") == "audit-fail-confirm"
            for item in load_knowledge_category(project_name, "items")
        ),
        "audit_failure_rolls_back_confirmed_knowledge",
        failures,
    )
    _expect(
        not any(item.get("run_id") == "audit-must-rollback" for item in load_auto_review_runs(project_name)),
        "audit_failure_rolls_back_audit_row",
        failures,
    )


def _run_clear_plan(project_name: str, suffix: str) -> dict:
    rows = [
        {"pending_id": f"batch-confirm-{suffix}", "category": "items", "name": f"Confirmed {suffix}"},
        {"pending_id": f"batch-archive-{suffix}", "category": "items", "name": f"Archived {suffix}"},
        {"pending_id": f"batch-manual-{suffix}", "category": "items", "name": f"Manual {suffix}"},
    ]
    _queue(project_name, rows)
    plan = {
        "decisions": [
            {"pending_id": rows[0]["pending_id"], "action": "confirm", "reason": "safe"},
            {"pending_id": rows[1]["pending_id"], "action": "archive", "reason": "weak"},
            {"pending_id": rows[2]["pending_id"], "action": "manual_review", "reason": "risk"},
        ]
    }
    with (
        patch.object(memory, "sync_project_retrieval_assets", return_value=None),
        patch("novelforge.services.retrieval.rebuild_retrieval_assets", return_value={}),
    ):
        return execute_pending_clear_plan(project_name, plan, note="transaction verification")


def _verify_clear_plan(project_name: str, failures: list[str]) -> None:
    first = _run_clear_plan(project_name, "same")
    _expect(first.get("success") is True, "clear_plan_succeeds", failures)
    _expect(
        (first.get("confirmed_count"), first.get("archived_count"), first.get("manual_review_count")) == (1, 1, 1),
        "clear_plan_reports_committed_counts",
        failures,
    )
    processed_ids = {"batch-confirm-same", "batch-archive-same", "batch-manual-same"}
    pending_ids = {item.get("pending_id") for item in load_pending_knowledge_items(project_name)}
    _expect(not (processed_ids & pending_ids), "clear_plan_removes_only_committed_rows", failures)

    runs = load_auto_review_runs(project_name)
    run = next((item for item in runs if item.get("run_id") == first.get("run_id")), {})
    _expect(len(run.get("pending_snapshots", [])) == 3, "clear_plan_audit_contains_all_snapshots", failures)
    _expect(
        len(run.get("archived_snapshots", [])) == 1
        and len(run.get("manual_review_snapshots", [])) == 1,
        "clear_plan_audit_classifies_discarded_snapshots",
        failures,
    )

    second = _run_clear_plan(project_name, "same")
    _expect(first.get("run_id") != second.get("run_id"), "batch_run_ids_are_collision_resistant", failures)
    _expect(
        len({item.get("run_id") for item in load_auto_review_runs(project_name) if item.get("source_type") == "pending_batch_process"}) == 2,
        "batch_audit_history_is_append_only",
        failures,
    )


def _verify_atomic_replacement(project_name: str, failures: list[str]) -> None:
    _queue(project_name, [
        {"pending_id": "replace-old-a", "category": "items", "name": "Old A"},
        {"pending_id": "replace-old-b", "category": "items", "name": "Old B"},
    ])
    replacement = {"pending_id": "replace-new", "category": "items", "name": "Replacement"}
    with patch.object(memory, "delete_pending_knowledge_items", side_effect=OSError("injected replacement failure")):
        _expect_raises(
            lambda: _queue_with_replacement(project_name, replacement),
            OSError,
            "replacement_failure_propagates",
            failures,
        )
    pending_ids = {item.get("pending_id") for item in load_pending_knowledge_items(project_name)}
    _expect(
        {"replace-old-a", "replace-old-b"}.issubset(pending_ids) and "replace-new" not in pending_ids,
        "replacement_failure_rolls_back_both_sides",
        failures,
    )
    _queue_with_replacement(project_name, replacement)
    pending_ids = {item.get("pending_id") for item in load_pending_knowledge_items(project_name)}
    _expect(
        "replace-new" in pending_ids and not ({"replace-old-a", "replace-old-b"} & pending_ids),
        "replacement_commits_add_and_remove_together",
        failures,
    )

    import ui.knowledge_management as knowledge_management_ui

    selected_items = [
        {"pending_id": "ui-a", "category": "items", "name": "UI A"},
        {"pending_id": "ui-b", "category": "items", "name": "UI B"},
    ]
    with (
        patch.object(
            knowledge_management_ui,
            "build_merged_knowledge_item",
            return_value={"pending_id": "ui-merged", "category": "items", "name": "UI Merged"},
        ),
        patch.object(knowledge_management_ui, "queue_pending_knowledge_items", return_value=1),
        patch.object(knowledge_management_ui.st, "success") as success,
        patch.object(knowledge_management_ui.st, "rerun", return_value=None),
    ):
        knowledge_management_ui._merge_pending_quality_issue(project_name, selected_items)
    _expect(
        success.call_count == 1 and "已合并 2 条" in str(success.call_args.args[0]),
        "pending_merge_ui_reports_atomic_replacement",
        failures,
    )


def _queue_with_replacement(project_name: str, replacement: dict) -> int:
    return queue_pending_knowledge_items(
        project_name,
        [replacement],
        scope="project",
        authority="curated",
        replace_pending_ids=["replace-old-a", "replace-old-b"],
    )


def _verify_destructive_compensation(project_name: str, failures: list[str]) -> None:
    guarded_story = create_story(project_name, "Guarded Delete")
    guarded_file = story_path(project_name, guarded_story["story_id"]) / "user-note.txt"
    guarded_file.write_text("keep on DB failure", encoding="utf-8")
    with (
        patch.dict(os.environ, {"NOVELFORGE_WRITE_JSON_MIRRORS": "1"}),
        patch.object(memory, "purge_story_scoped_rows", side_effect=OSError("injected purge failure")),
    ):
        _expect_raises(
            lambda: memory.delete_story(project_name, guarded_story["story_id"]),
            OSError,
            "story_delete_db_failure_propagates",
            failures,
        )
    _expect(
        guarded_file.exists()
        and guarded_story["story_id"] in {item.get("story_id") for item in list_stories(project_name)},
        "story_delete_db_failure_preserves_files_and_index",
        failures,
    )

    original_index = load_stories_index(project_name)
    rollback_target = create_story(project_name, "Rollback Target")
    concurrent_story = create_story(project_name, "Concurrent Story")
    with patch.object(memory, "sync_project_retrieval_assets", return_value=None):
        rollback_errors = memory._rollback_story_copy(
            project_name,
            rollback_target["story_id"],
            original_index,
        )
    story_ids = {item.get("story_id") for item in list_stories(project_name)}
    _expect(not rollback_errors, "story_copy_compensation_completes", failures)
    _expect(
        concurrent_story["story_id"] in story_ids and rollback_target["story_id"] not in story_ids,
        "story_copy_compensation_preserves_concurrent_story",
        failures,
    )

    race_target = create_story(project_name, "Delete Race Target")
    delete_holds_lock = threading.Event()
    allow_delete_to_continue = threading.Event()
    original_list_story_rows = memory.list_story_rows
    first_call_lock = threading.Lock()
    first_call = {"pending": True}

    def gated_list_story_rows(conn):
        rows = original_list_story_rows(conn)
        with first_call_lock:
            should_gate = first_call["pending"]
            first_call["pending"] = False
        if should_gate:
            delete_holds_lock.set()
            if not allow_delete_to_continue.wait(timeout=10):
                raise TimeoutError("delete concurrency gate timed out")
        return rows

    with patch.object(memory, "list_story_rows", side_effect=gated_list_story_rows):
        with ThreadPoolExecutor(max_workers=2) as executor:
            delete_future = executor.submit(memory.delete_story, project_name, race_target["story_id"])
            _expect(delete_holds_lock.wait(timeout=10), "story_delete_acquires_lock_before_read", failures)
            create_future = executor.submit(memory.create_story, project_name, "Created During Delete")
            allow_delete_to_continue.set()
            deleted = delete_future.result(timeout=15)
            created_during_delete = create_future.result(timeout=15)
    final_story_ids = {item.get("story_id") for item in list_stories(project_name)}
    _expect(
        deleted
        and race_target["story_id"] not in final_story_ids
        and created_during_delete["story_id"] in final_story_ids,
        "story_delete_and_create_do_not_overwrite_each_other",
        failures,
    )


def main() -> int:
    with isolated_workspace("novelforge_pending_transactions_"):
        failures: list[str] = []
        project_name = "pending_transactions"
        create_project(project_name)
        _verify_audit_transaction(project_name, failures)
        _verify_clear_plan(project_name, failures)
        _verify_atomic_replacement(project_name, failures)
        _verify_destructive_compensation(project_name, failures)
        result = {"ok": not failures, "failures": failures, "checks": 21}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
