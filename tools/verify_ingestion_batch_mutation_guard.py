from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.verify_utils import make_workspace, retry_rmtree


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def expect_value_error(callback, label: str) -> str:
    try:
        callback()
    except ValueError as exc:
        check(True, label)
        return str(exc)
    raise AssertionError(label)


def main() -> None:
    workspace = make_workspace("novelforge_batch_mutation_guard_")
    previous_cwd = Path.cwd()
    previous_mirror_setting = os.environ.get("NOVELFORGE_WRITE_JSON_MIRRORS")
    os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = "1"
    os.chdir(workspace)
    try:
        from novelforge.domain.ingestion_tasks import create_ingestion_task, set_ingestion_task_status
        from novelforge.services import memory as memory_api
        from novelforge.services.memory import (
            claim_source_ingestion_task,
            create_long_reference_batch,
            create_project,
            delete_long_reference_batch,
            finalize_source_ingestion_task,
            load_long_reference_batch,
            load_source_ingestion_task,
            long_reference_batch_path,
            project_path,
            save_long_reference_batch,
            save_source_ingestion_task,
            set_project_maintenance,
        )
        from novelforge.workflows.ingestion_tasks import (
            archive_long_reference_ingestion_task,
            restore_long_reference_ingestion_task,
        )
        from novelforge.workflows.long_reference_quick_process import run_long_reference_quick_process
        from novelforge.workflows import source_workflows
        from storage import open_project_db
        from storage.repositories import (
            load_source_ingestion_task_row,
            persist_long_reference_batch_row,
            persist_source_ingestion_task_row,
        )

        project_name = create_project("batch_guard_verify")

        def new_batch(title: str) -> dict:
            return create_long_reference_batch(
                project_name,
                title=title,
                scope="reference",
                authority="curated",
                source_type="external_source",
                segments=[{"title": f"{title}片段", "content": title * 20}],
            )

        def new_task(batch: dict) -> dict:
            return create_ingestion_task(
                batch,
                [0],
                configuration={
                    "import_to_index": False,
                    "consolidate_after_extract": False,
                    "auto_confirm_safe_items": False,
                },
            )

        batch = new_batch("权限批次")
        task = save_source_ingestion_task(project_name, new_task(batch))
        mirror_path = long_reference_batch_path(project_name, batch["batch_id"])
        mirror_before = mirror_path.read_text(encoding="utf-8")

        manual_payload = {**load_long_reference_batch(project_name, batch["batch_id"]), "title": "人工越权"}
        message = expect_value_error(
            lambda: save_long_reference_batch(project_name, manual_payload),
            "active task atomically rejects manual save",
        )
        check(task["task_id"] in message, "manual save rejection names the occupying task")
        check(load_long_reference_batch(project_name, batch["batch_id"])["title"] == "权限批次", "rejected save preserves DB batch")
        check(mirror_path.read_text(encoding="utf-8") == mirror_before, "rejected save does not alter JSON mirror")

        expect_value_error(
            lambda: save_long_reference_batch(
                project_name,
                manual_payload,
                task_id="different-task",
            ),
            "cross-task batch save is rejected",
        )
        expect_value_error(
            lambda: save_long_reference_batch(
                project_name,
                manual_payload,
                task_id=task["task_id"],
            ),
            "queued task cannot bypass worker ownership with task ID alone",
        )
        expect_value_error(
            lambda: delete_long_reference_batch(project_name, batch["batch_id"]),
            "active task atomically rejects batch deletion",
        )
        check(bool(load_long_reference_batch(project_name, batch["batch_id"])), "rejected deletion preserves DB batch")
        check(mirror_path.exists(), "rejected deletion preserves JSON mirror")

        claimed_a = claim_source_ingestion_task(
            project_name,
            task["task_id"],
            "worker-a",
            lease_seconds=120,
        )
        worker_payload = {**load_long_reference_batch(project_name, batch["batch_id"]), "title": "worker-a 写入"}
        save_long_reference_batch(
            project_name,
            worker_payload,
            task_id=task["task_id"],
            worker_id="worker-a",
        )
        check(load_long_reference_batch(project_name, batch["batch_id"])["title"] == "worker-a 写入", "live owning worker can save its batch")

        with open_project_db(project_path(project_name)) as conn:
            conn.execute(
                "UPDATE workflow_runs SET lease_expires_at = ? WHERE run_id = ?",
                ("2000-01-01T00:00:00+00:00", task["task_id"]),
            )
            conn.commit()
        claimed_b = claim_source_ingestion_task(
            project_name,
            task["task_id"],
            "worker-b",
            lease_seconds=120,
        )
        check(claimed_b.get("worker_id") == "worker-b", "replacement worker reclaims expired task lease")
        stale_payload = {**load_long_reference_batch(project_name, batch["batch_id"]), "title": "stale worker overwrite"}
        expect_value_error(
            lambda: save_long_reference_batch(
                project_name,
                stale_payload,
                task_id=task["task_id"],
                worker_id="worker-a",
            ),
            "expired worker cannot save with the same task ID",
        )
        check(load_long_reference_batch(project_name, batch["batch_id"])["title"] == "worker-a 写入", "stale worker rejection preserves authoritative batch")
        current_payload = {**load_long_reference_batch(project_name, batch["batch_id"]), "title": "worker-b 写入"}
        save_long_reference_batch(
            project_name,
            current_payload,
            task_id=task["task_id"],
            worker_id="worker-b",
        )
        check(load_long_reference_batch(project_name, batch["batch_id"])["title"] == "worker-b 写入", "replacement worker can save its batch")

        terminal = set_ingestion_task_status(load_source_ingestion_task(project_name, task["task_id"]), "completed")
        finalize_source_ingestion_task(project_name, terminal, "worker-b")
        original_unlink = Path.unlink

        def fail_batch_mirror_unlink(path: Path, *args, **kwargs):
            if path.resolve() == mirror_path.resolve():
                raise OSError("synthetic mirror lock")
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", new=fail_batch_mirror_unlink):
            check(delete_long_reference_batch(project_name, batch["batch_id"]), "terminal task releases batch deletion")
        check(not load_long_reference_batch(project_name, batch["batch_id"]), "DB deletion commits despite mirror cleanup failure")
        check(mirror_path.exists(), "failed mirror unlink leaves the file for retry")
        check(mirror_path in memory_api._PENDING_MIRROR_DELETIONS, "failed mirror unlink remains queued for retry")
        original_unlink(mirror_path)
        memory_api._discard_pending_mirror_deletion(mirror_path)

        deleted_first_batch = new_batch("先删除")
        stale_task = new_task(deleted_first_batch)
        check(delete_long_reference_batch(project_name, deleted_first_batch["batch_id"]), "unoccupied batch can be deleted")
        message = expect_value_error(
            lambda: save_source_ingestion_task(project_name, stale_task),
            "task creation rejects a batch deleted first",
        )
        check("不存在" in message or "删除" in message, "missing-batch creation gives a clear error")

        changed_batch = new_batch("片段替换")
        stale_selection = new_task(changed_batch)
        replacement = load_long_reference_batch(project_name, changed_batch["batch_id"])
        replacement["segments"] = [{
            "segment_id": "replacement-segment",
            "index": 1,
            "title": "替换后片段",
            "content": "replacement",
        }]
        save_long_reference_batch(project_name, replacement)
        message = expect_value_error(
            lambda: save_source_ingestion_task(project_name, stale_selection),
            "task creation rejects a stale segment selection",
        )
        check("刷新" in message or "变化" in message, "stale-selection creation gives refresh guidance")

        revision_batch = new_batch("内容版本")
        stale_revision_task = new_task(revision_batch)
        revised = load_long_reference_batch(project_name, revision_batch["batch_id"])
        revised["segments"][0]["content"] = "同一片段 ID 的新内容"
        save_long_reference_batch(project_name, revised)
        message = expect_value_error(
            lambda: save_source_ingestion_task(project_name, stale_revision_task),
            "task creation rejects a stale batch revision",
        )
        check("刷新" in message or "变化" in message, "stale-revision creation gives refresh guidance")

        restore_batch = new_batch("恢复孤儿")
        restore_task = save_source_ingestion_task(project_name, new_task(restore_batch))
        restore_task = set_ingestion_task_status(restore_task, "failed", error="synthetic")
        save_source_ingestion_task(project_name, restore_task)
        check(archive_long_reference_ingestion_task(project_name, restore_task["task_id"]), "failed task can be archived")
        check(delete_long_reference_batch(project_name, restore_batch["batch_id"]), "archived task releases batch deletion")
        check(not restore_long_reference_ingestion_task(project_name, restore_task["task_id"]), "unfinished archived task cannot restore without its batch")

        maintenance_batch = new_batch("维护模式")
        maintenance_task = save_source_ingestion_task(project_name, new_task(maintenance_batch))
        maintenance_claim = claim_source_ingestion_task(
            project_name,
            maintenance_task["task_id"],
            "maintenance-worker",
            lease_seconds=120,
        )
        check(set_project_maintenance(project_name, True), "project enters maintenance mode")
        expect_value_error(
            lambda: save_long_reference_batch(project_name, {**maintenance_batch, "title": "维护写入"}),
            "maintenance mode rejects batch save",
        )
        expect_value_error(
            lambda: delete_long_reference_batch(project_name, maintenance_batch["batch_id"]),
            "maintenance mode rejects batch deletion",
        )
        maintenance_worker_payload = {
            **load_long_reference_batch(project_name, maintenance_batch["batch_id"]),
            "title": "维护期 worker 检查点",
        }
        save_long_reference_batch(
            project_name,
            maintenance_worker_payload,
            task_id=maintenance_task["task_id"],
            worker_id="maintenance-worker",
        )
        check(
            load_long_reference_batch(project_name, maintenance_batch["batch_id"])["title"] == "维护期 worker 检查点",
            "maintenance mode still permits the live owner's checkpoint",
        )
        check(set_project_maintenance(project_name, False), "project leaves maintenance mode")
        maintenance_terminal = set_ingestion_task_status(maintenance_claim, "completed")
        finalize_source_ingestion_task(project_name, maintenance_terminal, "maintenance-worker")

        quick_batch = new_batch("合法快速流程")
        quick_task = save_source_ingestion_task(project_name, new_task(quick_batch))
        quick_claim = claim_source_ingestion_task(
            project_name,
            quick_task["task_id"],
            "quick-worker",
            lease_seconds=120,
        )
        with (
            patch.object(source_workflows, "extract_reference_knowledge", return_value={
                "data": {"knowledge_extraction": {"items": [], "source_title": ""}}
            }),
            patch.object(source_workflows, "get_segment_related_knowledge_items", return_value={"pending": []}),
            patch.object(source_workflows, "queue_pending_knowledge_items", return_value=0),
        ):
            quick_saved_batch, quick_summary = run_long_reference_quick_process(
                project_name,
                quick_batch,
                [0],
                enabled_categories=["events"],
                extraction_mode="general",
                extract_limit=1,
                import_to_index=False,
                consolidate_after_extract=False,
                auto_confirm_safe_items=False,
                task_id=quick_task["task_id"],
                worker_id="quick-worker",
                run_key=quick_task["task_id"],
            )
        check(quick_saved_batch["segments"][0]["extract_status"] == "queued", "quick-process checkpoint carries task and worker authority")
        check(quick_summary["processed_count"] == 1, "quick-process final batch save remains authorized")
        quick_terminal = set_ingestion_task_status(quick_claim, "completed")
        finalize_source_ingestion_task(project_name, quick_terminal, "quick-worker")

        trigger_batch = new_batch("事务回滚")
        trigger_path = long_reference_batch_path(project_name, trigger_batch["batch_id"])
        trigger_mirror_before = trigger_path.read_text(encoding="utf-8")
        source_id = f"long_batch_{trigger_batch['batch_id']}"
        with open_project_db(project_path(project_name)) as conn:
            conn.execute(
                f"""
                CREATE TRIGGER reject_batch_save
                BEFORE UPDATE ON source_documents
                WHEN NEW.source_id = '{source_id}' AND NEW.title = '触发回滚'
                BEGIN
                    SELECT RAISE(ABORT, 'synthetic batch save failure');
                END
                """
            )
            conn.commit()
        try:
            save_long_reference_batch(project_name, {**trigger_batch, "title": "触发回滚"})
        except RuntimeError:
            check(True, "DB save failure is surfaced after atomic rollback")
        else:
            raise AssertionError("DB save failure is surfaced after atomic rollback")
        check(load_long_reference_batch(project_name, trigger_batch["batch_id"])["title"] == "事务回滚", "failed DB save rolls back batch")
        check(trigger_path.read_text(encoding="utf-8") == trigger_mirror_before, "failed DB save leaves mirror unchanged")
        with open_project_db(project_path(project_name)) as conn:
            conn.execute("DROP TRIGGER reject_batch_save")
            conn.execute(
                f"""
                CREATE TRIGGER reject_batch_delete
                BEFORE UPDATE OF deleted_at ON source_documents
                WHEN OLD.source_id = '{source_id}'
                BEGIN
                    SELECT RAISE(ABORT, 'synthetic batch delete failure');
                END
                """
            )
            conn.commit()
        try:
            delete_long_reference_batch(project_name, trigger_batch["batch_id"])
        except RuntimeError:
            check(True, "DB delete failure is surfaced after atomic rollback")
        else:
            raise AssertionError("DB delete failure is surfaced after atomic rollback")
        check(bool(load_long_reference_batch(project_name, trigger_batch["batch_id"])), "failed DB delete preserves batch")
        check(trigger_path.read_text(encoding="utf-8") == trigger_mirror_before, "failed DB delete leaves mirror unchanged")
        with open_project_db(project_path(project_name)) as conn:
            conn.execute("DROP TRIGGER reject_batch_delete")
            conn.commit()

        race_batch = new_batch("TOCTOU")
        race_task = new_task(race_batch)
        race_snapshot = {
            **race_task,
            "project_name": project_name,
            "steps": {
                str(item["item_id"]): {**item, "step_name": str(item["item_id"])}
                for item in race_task["items"]
            },
        }
        creator_locked = threading.Event()
        release_creator = threading.Event()
        mutation_started = threading.Event()
        mutation_done = threading.Event()
        race_errors: list[Exception] = []

        def create_task_holding_write_lock() -> None:
            with open_project_db(project_path(project_name)) as conn:
                persist_source_ingestion_task_row(conn, task=race_snapshot)
                creator_locked.set()
                release_creator.wait(timeout=5)
                conn.commit()

        def race_manual_save() -> None:
            creator_locked.wait(timeout=5)
            mutation_started.set()
            try:
                with open_project_db(project_path(project_name)) as conn:
                    persist_long_reference_batch_row(
                        conn,
                        batch={**race_batch, "title": "竞态人工覆盖"},
                    )
                    conn.commit()
            except Exception as exc:
                race_errors.append(exc)
            finally:
                mutation_done.set()

        creator_thread = threading.Thread(target=create_task_holding_write_lock, daemon=True)
        mutation_thread = threading.Thread(target=race_manual_save, daemon=True)
        creator_thread.start()
        check(creator_locked.wait(timeout=5), "task creation acquires its write transaction")
        mutation_thread.start()
        check(mutation_started.wait(timeout=5), "concurrent batch mutation starts")
        time.sleep(0.1)
        check(not mutation_done.is_set(), "batch mutation waits for task creation transaction")
        release_creator.set()
        creator_thread.join(timeout=5)
        mutation_thread.join(timeout=5)
        check(mutation_done.is_set(), "concurrent batch mutation settles after task commit")
        check(len(race_errors) == 1 and isinstance(race_errors[0], ValueError), "TOCTOU loser is atomically rejected")
        check(load_long_reference_batch(project_name, race_batch["batch_id"])["title"] == "TOCTOU", "TOCTOU rejection prevents stale batch overwrite")
        with open_project_db(project_path(project_name)) as conn:
            check(bool(load_source_ingestion_task_row(conn, race_task["task_id"])), "TOCTOU winner task remains durable")

        print(f"Ingestion batch mutation guard verification passed: {len(CHECKS)} checks")
    finally:
        os.chdir(previous_cwd)
        if previous_mirror_setting is None:
            os.environ.pop("NOVELFORGE_WRITE_JSON_MIRRORS", None)
        else:
            os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = previous_mirror_setting
        retry_rmtree(workspace)


if __name__ == "__main__":
    main()
