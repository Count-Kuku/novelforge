from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
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


def main() -> None:
    workspace = make_workspace("novelforge_ingestion_runtime_")
    previous_cwd = Path.cwd()
    previous_background_flag = os.environ.get("NOVELFORGE_DISABLE_BACKGROUND_TASKS")
    os.environ["NOVELFORGE_DISABLE_BACKGROUND_TASKS"] = "1"
    os.chdir(workspace)
    try:
        from novelforge.domain.ingestion_task_estimates import estimate_ingestion_task
        from novelforge.domain.ingestion_tasks import set_ingestion_task_status
        from novelforge.services.memory import (
            create_long_reference_batch,
            create_project,
            claim_next_source_ingestion_task,
            list_source_ingestion_tasks,
            load_source_ingestion_task,
            project_path,
            save_long_reference_batch,
            save_source_ingestion_task,
        )
        from novelforge.workflows import ingestion_tasks
        from novelforge.workflows.ingestion_task_dispatcher import IngestionTaskDispatcher
        from novelforge.services.project_manager import delete_project
        from storage import CURRENT_SCHEMA_VERSION, open_project_db
        from storage.repositories import (
            claim_source_ingestion_task_row,
            heartbeat_source_ingestion_task_row,
            load_source_ingestion_task_row,
            release_source_ingestion_task_lease_row,
            request_source_ingestion_task_control_row,
            set_source_ingestion_task_archived_row,
            settle_stale_source_ingestion_controls_row,
        )

        project_name = create_project("runtime_verify")
        batch = create_long_reference_batch(
            project_name,
            title="后台运行验证",
            scope="canon",
            authority="official",
            source_type="external_source",
            segments=[
                {"title": "第一段", "content": "甲" * 1800},
                {"title": "第二段", "content": "乙" * 900},
            ],
        )

        estimate_without_price = estimate_ingestion_task(
            batch,
            [0, 1],
            enabled_categories=["characters", "events"],
            extraction_mode="general",
            import_to_index=True,
            consolidate_after_extract=False,
            model_profile={"id": "no-price", "model_name": "verify"},
        )
        check(estimate_without_price["segment_count"] == 2, "estimate counts selected segments")
        check(estimate_without_price["llm_call_count"] == 2, "estimate counts one extraction call per segment")
        check(estimate_without_price["estimated_input_tokens"] > 0, "estimate includes input tokens")
        check(estimate_without_price["estimated_embedding_tokens"] > 0, "estimate includes embedding tokens")
        check(not estimate_without_price["pricing_configured"], "estimate does not invent missing prices")
        check(estimate_without_price["estimated_cost_usd"] == 0, "missing prices produce no fake cost")

        priced_profile = {
            "id": "priced",
            "model_name": "verify-chat",
            "embedding_model_name": "verify-embed",
            "input_price_per_million": 1.0,
            "output_price_per_million": 2.0,
            "embedding_price_per_million": 0.5,
        }
        priced_estimate = estimate_ingestion_task(
            batch,
            [0, 1],
            enabled_categories=["characters", "events"],
            extraction_mode="deep",
            import_to_index=True,
            consolidate_after_extract=True,
            model_profile=priced_profile,
        )
        expected_cost = (
            priced_estimate["estimated_input_tokens"]
            + priced_estimate["estimated_output_tokens"] * 2
            + priced_estimate["estimated_embedding_tokens"] * 0.5
        ) / 1_000_000
        check(priced_estimate["pricing_configured"], "configured rates enable cost estimate")
        check(priced_estimate["llm_call_count"] == 3, "consolidation adds one estimated call")
        check(abs(priced_estimate["estimated_cost_usd"] - expected_cost) < 0.000001, "cost estimate uses rate snapshot")
        check(priced_estimate["estimated_output_tokens"] > estimate_without_price["estimated_output_tokens"], "deep consolidated mode estimates more output")

        with open_project_db(project_path(project_name)) as conn:
            schema_version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            workflow_columns = {row[1] for row in conn.execute("PRAGMA table_info(workflow_runs)").fetchall()}
        check(CURRENT_SCHEMA_VERSION == 10 and schema_version == 10, "schema v10 is applied")
        check({"worker_id", "lease_expires_at", "heartbeat_at", "control_requested", "archived_at"}.issubset(workflow_columns), "runtime columns exist")

        lease_task = ingestion_tasks.create_long_reference_ingestion_task(
            project_name,
            batch,
            [0, 1],
            enabled_categories=["characters"],
            extraction_mode="general",
            extract_limit=2,
            import_to_index=False,
            consolidate_after_extract=False,
            auto_confirm_safe_items=False,
        )
        t0 = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)
        with open_project_db(project_path(project_name)) as conn:
            claimed_a = claim_source_ingestion_task_row(
                conn,
                task_id=lease_task["task_id"],
                worker_id="worker-a",
                lease_seconds=10,
                now=t0,
            )
            conn.commit()
        check(claimed_a.get("worker_id") == "worker-a", "first worker atomically claims task")
        with open_project_db(project_path(project_name)) as conn:
            claimed_b_early = claim_source_ingestion_task_row(
                conn,
                task_id=lease_task["task_id"],
                worker_id="worker-b",
                lease_seconds=10,
                now=t0 + timedelta(seconds=1),
            )
            conn.commit()
        check(not claimed_b_early, "second worker cannot claim a live lease")
        with open_project_db(project_path(project_name)) as conn:
            renewed = heartbeat_source_ingestion_task_row(
                conn,
                task_id=lease_task["task_id"],
                worker_id="worker-a",
                lease_seconds=10,
                now=t0 + timedelta(seconds=5),
            )
            conn.commit()
        check(renewed, "owner heartbeat renews lease")
        with open_project_db(project_path(project_name)) as conn:
            still_blocked = claim_source_ingestion_task_row(
                conn,
                task_id=lease_task["task_id"],
                worker_id="worker-b",
                lease_seconds=10,
                now=t0 + timedelta(seconds=12),
            )
            conn.commit()
        check(not still_blocked, "renewed lease remains exclusive")
        with open_project_db(project_path(project_name)) as conn:
            claimed_b_stale = claim_source_ingestion_task_row(
                conn,
                task_id=lease_task["task_id"],
                worker_id="worker-b",
                lease_seconds=10,
                now=t0 + timedelta(seconds=16),
            )
            conn.commit()
        check(claimed_b_stale.get("worker_id") == "worker-b", "expired lease is automatically reclaimable")

        with open_project_db(project_path(project_name)) as conn:
            pause_request = request_source_ingestion_task_control_row(
                conn,
                task_id=lease_task["task_id"],
                control="pause",
                now=t0 + timedelta(seconds=17),
            )
            conn.commit()
        check(not pause_request["immediate"] and pause_request["control_requested"] == "pause", "live worker receives durable pause request")
        with open_project_db(project_path(project_name)) as conn:
            settled = settle_stale_source_ingestion_controls_row(conn, now=t0 + timedelta(seconds=27))
            paused_row = load_source_ingestion_task_row(conn, lease_task["task_id"])
            conn.commit()
        check(settled == 1, "stale controlled task is settled")
        check(paused_row["status"] == "paused" and not paused_row["worker_id"], "stale pause clears lease")
        with open_project_db(project_path(project_name)) as conn:
            resumed = request_source_ingestion_task_control_row(
                conn,
                task_id=lease_task["task_id"],
                control="resume",
                now=t0 + timedelta(seconds=28),
            )
            conn.commit()
        check(resumed["status"] == "queued", "paused task returns to queue")

        pause_batch = create_long_reference_batch(
            project_name,
            title="运行中暂停验证",
            scope="reference",
            authority="curated",
            source_type="external_source",
            segments=[
                {"title": "已完成", "content": "一" * 100},
                {"title": "待继续", "content": "二" * 100},
            ],
        )
        pause_task = ingestion_tasks.create_long_reference_ingestion_task(
            project_name,
            pause_batch,
            [0, 1],
            enabled_categories=["events"],
            extraction_mode="general",
            extract_limit=2,
            import_to_index=False,
            consolidate_after_extract=False,
            auto_confirm_safe_items=False,
        )

        def pause_after_first(project_name, batch, segment_indices, **kwargs):
            first = segment_indices[0]
            batch["segments"][first]["extract_status"] = "queued"
            batch = save_long_reference_batch(
                project_name,
                batch,
                task_id=str(kwargs.get("task_id") or ""),
                worker_id=str(kwargs.get("worker_id") or ""),
            )
            ingestion_tasks.pause_long_reference_ingestion_task(project_name, pause_task["task_id"])
            kwargs["progress_callback"]({"current": 1, "total": len(segment_indices), "message": "第一段完成"})
            raise AssertionError("pause signal should stop processor")

        with patch.object(ingestion_tasks, "run_long_reference_quick_process", side_effect=pause_after_first):
            paused_task, _ = ingestion_tasks.run_long_reference_ingestion_task(project_name, pause_task["task_id"])
        check(paused_task["status"] == "paused", "running task pauses at checkpoint")
        check(paused_task["progress"]["completed"] == 1, "pause preserves completed checkpoint")
        check(paused_task["progress"]["queued"] == 1, "pause returns unfinished item to queue")
        check(not load_source_ingestion_task(project_name, pause_task["task_id"])["worker_id"], "pause releases worker lease")

        executed_indices: list[list[int]] = []

        def complete_remaining(project_name, batch, segment_indices, **kwargs):
            executed_indices.append(list(segment_indices))
            for index in segment_indices:
                batch["segments"][index]["extract_status"] = "queued"
            batch = save_long_reference_batch(
                project_name,
                batch,
                task_id=str(kwargs.get("task_id") or ""),
                worker_id=str(kwargs.get("worker_id") or ""),
            )
            return batch, {"processed_count": len(segment_indices), "failed_titles": []}

        ingestion_tasks.resume_long_reference_ingestion_task(project_name, pause_task["task_id"])
        with patch.object(ingestion_tasks, "run_long_reference_quick_process", side_effect=complete_remaining):
            resumed_task, _ = ingestion_tasks.run_long_reference_ingestion_task(project_name, pause_task["task_id"])
        check(executed_indices == [[1]], "resume executes only unfinished item")
        check(resumed_task["status"] == "completed", "resumed background task completes")

        cancel_batch = create_long_reference_batch(
            project_name,
            title="运行中取消验证",
            scope="reference",
            authority="curated",
            source_type="external_source",
            segments=[
                {"title": "取消前完成", "content": "甲" * 100},
                {"title": "取消项", "content": "乙" * 100},
            ],
        )
        cancel_task = ingestion_tasks.create_long_reference_ingestion_task(
            project_name,
            cancel_batch,
            [0, 1],
            enabled_categories=["events"],
            extraction_mode="general",
            extract_limit=2,
            import_to_index=False,
            consolidate_after_extract=False,
            auto_confirm_safe_items=False,
        )

        def cancel_after_first(project_name, batch, segment_indices, **kwargs):
            first = segment_indices[0]
            batch["segments"][first]["extract_status"] = "queued"
            batch = save_long_reference_batch(
                project_name,
                batch,
                task_id=str(kwargs.get("task_id") or ""),
                worker_id=str(kwargs.get("worker_id") or ""),
            )
            ingestion_tasks.cancel_long_reference_ingestion_task(project_name, cancel_task["task_id"])
            kwargs["progress_callback"]({"current": 1, "total": len(segment_indices), "message": "请求取消"})
            raise AssertionError("cancel signal should stop processor")

        with patch.object(ingestion_tasks, "run_long_reference_quick_process", side_effect=cancel_after_first):
            cancelled_task, _ = ingestion_tasks.run_long_reference_ingestion_task(project_name, cancel_task["task_id"])
        check(cancelled_task["status"] == "cancelled", "running task cancels at checkpoint")
        check(cancelled_task["progress"]["completed"] == 1, "cancel preserves completed checkpoint")
        check(cancelled_task["progress"]["cancelled"] == 1, "cancel marks unfinished item")
        check(not load_source_ingestion_task(project_name, cancel_task["task_id"])["worker_id"], "cancel releases worker lease")

        completed_for_archive = set_ingestion_task_status(lease_task, "completed", message="完成")
        save_source_ingestion_task(project_name, completed_for_archive)
        with open_project_db(project_path(project_name)) as conn:
            # Clear the synthetic worker-b lease before archiving.
            release_source_ingestion_task_lease_row(
                conn,
                task_id=lease_task["task_id"],
                worker_id="worker-b",
                status="completed",
                now=t0 + timedelta(seconds=30),
            )
            archived = set_source_ingestion_task_archived_row(
                conn,
                task_id=lease_task["task_id"],
                archived=True,
                now=t0 + timedelta(seconds=31),
            )
            conn.commit()
        check(archived, "terminal task can be archived")
        active_ids = {task["task_id"] for task in list_source_ingestion_tasks(project_name)}
        all_tasks = list_source_ingestion_tasks(project_name, include_archived=True)
        check(lease_task["task_id"] not in active_ids, "archived task leaves active list")
        check(any(task["task_id"] == lease_task["task_id"] and task["archived_at"] for task in all_tasks), "archived task remains in history")
        check(ingestion_tasks.restore_long_reference_ingestion_task(project_name, lease_task["task_id"]), "archived task can be restored")
        check(not load_source_ingestion_task(project_name, lease_task["task_id"])["archived_at"], "restored task returns to active history")
        check(ingestion_tasks.archive_long_reference_ingestion_task(project_name, lease_task["task_id"]), "restored terminal task can be archived again")
        check(ingestion_tasks.delete_long_reference_ingestion_task(project_name, lease_task["task_id"]), "individual archived task can be permanently deleted")
        check(not load_source_ingestion_task(project_name, lease_task["task_id"]), "permanent deletion removes task snapshot and steps")

        check(ingestion_tasks.archive_long_reference_ingestion_task(project_name, resumed_task["task_id"]), "completed task enters cleanup archive")
        with open_project_db(project_path(project_name)) as conn:
            conn.execute(
                "UPDATE workflow_runs SET archived_at = ? WHERE run_id = ?",
                ("2020-01-01T00:00:00+00:00", resumed_task["task_id"]),
            )
            conn.commit()
        cleaned = ingestion_tasks.cleanup_long_reference_ingestion_tasks(
            project_name,
            before=datetime(2020, 2, 1, tzinfo=timezone.utc),
        )
        check(cleaned == 1, "batch cleanup deletes old archived tasks")
        check(not load_source_ingestion_task(project_name, resumed_task["task_id"]), "cleaned task is no longer loadable")

        dispatch_batch = create_long_reference_batch(
            project_name,
            title="真实调度验证",
            scope="reference",
            authority="curated",
            source_type="external_source",
            segments=[{"title": "后台片段", "content": "后台" * 60}],
        )
        dispatch_task = ingestion_tasks.create_long_reference_ingestion_task(
            project_name,
            dispatch_batch,
            [0],
            enabled_categories=["events"],
            extraction_mode="general",
            extract_limit=1,
            import_to_index=False,
            consolidate_after_extract=False,
            auto_confirm_safe_items=False,
        )
        real_dispatcher = IngestionTaskDispatcher(
            project_provider=lambda: [project_name],
            heartbeat_seconds=0.02,
            poll_seconds=0.02,
            lease_seconds=2,
            worker_id="real-dispatcher",
        )
        with patch.object(ingestion_tasks, "run_long_reference_quick_process", side_effect=complete_remaining):
            check(real_dispatcher.run_once(), "real dispatcher claims persisted queued task")
        check(load_source_ingestion_task(project_name, dispatch_task["task_id"])["status"] == "completed", "real dispatcher completes persisted task")

        fake_claims = [{"task_id": "dispatcher-task"}]
        runner_calls = []
        heartbeat_calls = []

        def fake_claim(project_name, worker_id, **kwargs):
            return fake_claims.pop(0) if fake_claims else {}

        def fake_heartbeat(project_name, task_id, worker_id, **kwargs):
            heartbeat_calls.append((project_name, task_id, worker_id))
            return True

        def fake_runner(project_name, task_id, **kwargs):
            runner_calls.append((project_name, task_id, kwargs.get("lease_already_claimed")))
            deadline = time.time() + 0.5
            while len(heartbeat_calls) < 2 and time.time() < deadline:
                time.sleep(0.01)

        dispatcher = IngestionTaskDispatcher(
            project_provider=lambda: ["dispatcher-project"],
            claim_func=fake_claim,
            settle_func=lambda project_name: 0,
            heartbeat_func=fake_heartbeat,
            runner=fake_runner,
            heartbeat_seconds=0.02,
            poll_seconds=0.02,
            lease_seconds=1,
            worker_id="dispatcher-worker",
        )
        check(dispatcher.run_once(), "dispatcher claims and executes available task")
        check(runner_calls == [("dispatcher-project", "dispatcher-task", True)], "dispatcher passes claimed lease to runner")
        check(len(heartbeat_calls) >= 2, "dispatcher renews heartbeat while task runs")
        check(not dispatcher.run_once(), "dispatcher reports idle queue")

        fake_claims.append({"task_id": "background-task"})
        dispatcher.start()
        deadline = time.time() + 2
        while len(runner_calls) < 2 and time.time() < deadline:
            time.sleep(0.02)
        dispatcher.stop()
        check(len(runner_calls) == 2, "background thread executes without Streamlit request")
        check(not dispatcher.is_running, "dispatcher stops cleanly")

        stale_project = create_project("stale_dispatcher_snapshot")
        stale_path = project_path(stale_project)
        check(delete_project(stale_project), "stale-snapshot fixture project is deleted")
        check(not stale_path.exists(), "deleted project path is moved away")
        stale_claim = claim_next_source_ingestion_task(
            stale_project,
            "stale-dispatcher",
            lease_seconds=5,
        )
        check(not stale_claim, "stale dispatcher snapshot cannot claim a moved project")
        check(not stale_path.exists(), "stale dispatcher snapshot cannot recreate a ghost project")
        try:
            save_source_ingestion_task(
                stale_project,
                {
                    "task_id": "stale-create",
                    "batch_id": "stale-batch",
                    "status": "queued",
                    "items": [],
                },
            )
        except FileNotFoundError:
            check(True, "stale task creation reports the moved project")
        else:
            raise AssertionError("stale task creation reports the moved project")
        check(not stale_path.exists(), "stale task fallback load cannot recreate a ghost project")

        print(f"Ingestion task runtime verification passed: {len(CHECKS)} checks")
    finally:
        os.chdir(previous_cwd)
        if previous_background_flag is None:
            os.environ.pop("NOVELFORGE_DISABLE_BACKGROUND_TASKS", None)
        else:
            os.environ["NOVELFORGE_DISABLE_BACKGROUND_TASKS"] = previous_background_flag
        retry_rmtree(workspace)


if __name__ == "__main__":
    main()
