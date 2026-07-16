from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = "0"

import memory as memory_module
from knowledge_workflows import (
    delete_confirmed_knowledge_items,
    merge_confirmed_knowledge_items,
    save_confirmed_knowledge_item,
)
from memory import (
    create_project,
    load_knowledge_category,
    save_knowledge_category,
    upsert_knowledge_category_item_record,
)
from tools.verify_utils import isolated_workspace


def _ids(project_name: str, category: str) -> set[str]:
    return {
        str(item.get("id") or item.get("knowledge_id") or "")
        for item in load_knowledge_category(project_name, category)
    }


def _expect(condition: bool, label: str, failures: list[str]) -> None:
    if not condition:
        failures.append(label)


def _run_concurrently(first, second) -> tuple[object, object]:
    barrier = Barrier(2)

    def wrapped(callback):
        barrier.wait()
        return callback()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(wrapped, first)
        second_future = executor.submit(wrapped, second)
        return first_future.result(), second_future.result()


def main() -> int:
    failures: list[str] = []
    with isolated_workspace("novelforge_confirmed_atomicity_"):
        with patch.object(memory_module, "sync_project_retrieval_assets", return_value=None):
            project_name = create_project("confirmed_atomicity")

            save_knowledge_category(project_name, "characters", [
                {"id": "move", "name": "Move", "category": "characters"},
            ])
            save_knowledge_category(project_name, "locations", [
                {"id": "location-peer", "name": "Peer", "category": "locations"},
            ])
            try:
                save_confirmed_knowledge_item(
                    project_name,
                    "characters",
                    0,
                    {
                        "id": "move",
                        "name": "Broken move",
                        "category": "locations",
                        "story_id": "missing-story",
                    },
                )
            except ValueError:
                pass
            else:
                failures.append("cross_category_failure_is_reported")
            _expect("move" in _ids(project_name, "characters"), "failed_move_keeps_source", failures)
            _expect(
                _ids(project_name, "locations") == {"location-peer"},
                "failed_move_keeps_target",
                failures,
            )

            moved = save_confirmed_knowledge_item(
                project_name,
                "characters",
                0,
                {"id": "move", "name": "Moved", "category": "locations"},
            )
            _expect(moved, "cross_category_move_succeeds", failures)
            _expect("move" not in _ids(project_name, "characters"), "move_removes_source", failures)
            _expect(
                _ids(project_name, "locations") == {"move", "location-peer"},
                "move_preserves_target_peers",
                failures,
            )

            save_knowledge_category(project_name, "characters", [
                {"id": "update", "name": "Before", "category": "characters"},
                {"id": "peer", "name": "Peer", "category": "characters"},
            ])
            update_result, _ = _run_concurrently(
                lambda: save_confirmed_knowledge_item(
                    project_name,
                    "characters",
                    0,
                    {"id": "update", "name": "After", "category": "characters"},
                ),
                lambda: upsert_knowledge_category_item_record(
                    project_name,
                    "characters",
                    {"id": "late-update", "name": "Late", "category": "characters"},
                ),
            )
            _expect(bool(update_result), "concurrent_update_succeeds", failures)
            _expect(
                _ids(project_name, "characters") == {"update", "peer", "late-update"},
                "concurrent_update_preserves_peer_write",
                failures,
            )

            save_knowledge_category(project_name, "characters", [
                {"id": "merge-a", "name": "A", "category": "characters"},
                {"id": "merge-b", "name": "B", "category": "characters"},
                {"id": "merge-peer", "name": "Peer", "category": "characters"},
            ])
            merge_result, _ = _run_concurrently(
                lambda: merge_confirmed_knowledge_items(
                    project_name,
                    "characters",
                    [0, 1],
                    {"id": "merge-a", "name": "Merged", "category": "characters"},
                    selected_item_ids=["merge-a", "merge-b"],
                ),
                lambda: upsert_knowledge_category_item_record(
                    project_name,
                    "characters",
                    {"id": "late-merge", "name": "Late", "category": "characters"},
                ),
            )
            _expect(bool(merge_result), "concurrent_merge_succeeds", failures)
            _expect(
                _ids(project_name, "characters") == {"merge-a", "merge-peer", "late-merge"},
                "concurrent_merge_preserves_peer_write",
                failures,
            )

            stale_merge = merge_confirmed_knowledge_items(
                project_name,
                "characters",
                [],
                {"id": "merge-a", "name": "Should not save"},
                selected_item_ids=["merge-a", "missing"],
            )
            _expect(not stale_merge, "stale_merge_is_rejected", failures)
            _expect(
                _ids(project_name, "characters") == {"merge-a", "merge-peer", "late-merge"},
                "stale_merge_does_not_mutate",
                failures,
            )

            save_knowledge_category(project_name, "characters", [
                {"id": "delete-a", "name": "A", "category": "characters"},
                {"id": "delete-b", "name": "B", "category": "characters"},
                {"id": "delete-peer", "name": "Peer", "category": "characters"},
            ])
            delete_result, _ = _run_concurrently(
                lambda: delete_confirmed_knowledge_items(
                    project_name,
                    "characters",
                    [0, 1],
                    selected_item_ids=["delete-a", "delete-b"],
                ),
                lambda: upsert_knowledge_category_item_record(
                    project_name,
                    "characters",
                    {"id": "late-delete", "name": "Late", "category": "characters"},
                ),
            )
            _expect(delete_result == 2, "concurrent_delete_reports_actual_count", failures)
            _expect(
                _ids(project_name, "characters") == {"delete-peer", "late-delete"},
                "concurrent_delete_preserves_peer_write",
                failures,
            )

    result = {"ok": not failures, "failures": failures, "checks": 14}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
