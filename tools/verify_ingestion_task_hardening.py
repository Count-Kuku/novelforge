from __future__ import annotations

import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from novelforge.workflows.ingestion_task_dispatcher import (  # noqa: E402
    IngestionTaskDispatcher,
    _TaskHeartbeat,
)
from storage.repositories import (  # noqa: E402
    claim_source_ingestion_task_row,
    finalize_source_ingestion_task_row,
    heartbeat_source_ingestion_task_row,
    load_source_ingestion_task_row,
    persist_source_ingestion_task_row,
    release_source_ingestion_task_lease_row,
    request_source_ingestion_task_control_row,
    set_source_ingestion_task_archived_row,
    sync_long_reference_batch,
    sync_workflow_run_snapshot,
)
from storage.schema import CURRENT_SCHEMA_VERSION, ensure_schema  # noqa: E402


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def task(task_id: str, batch_id: str, *, status: str = "queued") -> dict:
    now = datetime(2026, 8, 6, tzinfo=timezone.utc).isoformat()
    return {
        "task_id": task_id,
        "run_id": task_id,
        "workflow_type": "source_ingestion",
        "batch_id": batch_id,
        "status": status,
        "items": [],
        "steps": {},
        "created_at": now,
        "updated_at": now,
    }


def main() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    check(CURRENT_SCHEMA_VERSION >= 9, "runtime hardening schema is active")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(project_meta)")}
    check("maintenance_mode" in columns, "project maintenance fence column exists")
    for batch_id in {
        "batch-a",
        "batch-control",
        "batch-fenced",
        "batch-finalize",
        "batch-maintenance",
        "batch-maintenance-create",
        "batch-maintenance-resume",
        "batch-restore",
        "batch-rollback",
        "batch-shared",
    }:
        sync_long_reference_batch(conn, {"batch_id": batch_id, "title": batch_id, "segments": []})
    conn.commit()

    t0 = datetime(2026, 8, 6, tzinfo=timezone.utc)
    missing_batch = persist_source_ingestion_task_row(
        conn,
        task=task("missing-batch-task", "batch-missing"),
        now=t0,
    )
    conn.commit()
    check(missing_batch.get("persistence_conflict") == "batch_missing", "task creation rejects a deleted or missing batch")
    check(not load_source_ingestion_task_row(conn, "missing-batch-task"), "missing-batch rejection leaves no task row")

    first = persist_source_ingestion_task_row(conn, task=task("batch-a-1", "batch-a"), now=t0)
    conn.commit()
    check(first.get("task_id") == "batch-a-1", "first unfinished batch task is created")
    conflict = persist_source_ingestion_task_row(conn, task=task("batch-a-2", "batch-a"), now=t0)
    conn.commit()
    check(conflict.get("persistence_conflict") == "unfinished_batch", "second unfinished batch task is rejected")
    check(conflict.get("conflict_task_id") == "batch-a-1", "batch conflict identifies authoritative task")

    sync_workflow_run_snapshot(
        conn,
        run_id="shared-run-id",
        payload={
            "run_id": "shared-run-id",
            "workflow_type": "chapter_pipeline",
            "status": "completed",
        },
    )
    conn.commit()
    run_id_conflict = persist_source_ingestion_task_row(
        conn,
        task=task("shared-run-id", "batch-shared"),
        now=t0,
    )
    conn.commit()
    preserved_type = conn.execute(
        "SELECT workflow_type FROM workflow_runs WHERE run_id = 'shared-run-id'"
    ).fetchone()[0]
    check(run_id_conflict.get("persistence_conflict") == "run_id", "foreign workflow run ID is rejected")
    check(preserved_type == "chapter_pipeline", "run ID collision cannot rewrite another workflow type")

    archived_task = persist_source_ingestion_task_row(
        conn,
        task=task("restore-a", "batch-restore", status="failed"),
        now=t0,
    )
    conn.commit()
    check(
        set_source_ingestion_task_archived_row(conn, task_id="restore-a", archived=True, now=t0),
        "unfinished task can be archived",
    )
    conn.commit()
    persist_source_ingestion_task_row(
        conn,
        task=task("restore-b", "batch-restore"),
        now=t0,
    )
    conn.commit()
    restored_conflict = set_source_ingestion_task_archived_row(
        conn,
        task_id="restore-a",
        archived=False,
        now=t0,
    )
    conn.commit()
    check(not restored_conflict, "archive restore cannot create a second unfinished batch task")
    check(
        bool(load_source_ingestion_task_row(conn, "restore-a").get("archived_at")),
        "conflicting restore keeps the original task archived",
    )

    conn.execute("INSERT INTO project_meta (project_id, name, maintenance_mode) VALUES ('p', 'p', 0)")
    conn.commit()
    persist_source_ingestion_task_row(
        conn,
        task=task("maintenance-resume", "batch-maintenance-resume", status="failed"),
        now=t0,
    )
    conn.commit()
    conn.execute("UPDATE project_meta SET maintenance_mode = 1")
    conn.commit()
    maintenance_conflict = persist_source_ingestion_task_row(
        conn,
        task=task("maintenance-create", "batch-maintenance-create"),
        now=t0,
    )
    conn.commit()
    check(
        maintenance_conflict.get("persistence_conflict") == "project_maintenance",
        "maintenance mode rejects new task creation",
    )
    check(
        not load_source_ingestion_task_row(conn, "maintenance-create"),
        "maintenance task rejection leaves no partial row",
    )
    try:
        request_source_ingestion_task_control_row(
            conn,
            task_id="maintenance-resume",
            control="resume",
            now=t0,
        )
    except ValueError:
        check(True, "maintenance mode rejects task resume")
        conn.rollback()
    else:
        raise AssertionError("maintenance mode rejects task resume")
    queued_during_maintenance = persist_source_ingestion_task_row(
        conn,
        task={**load_source_ingestion_task_row(conn, "maintenance-resume"), "status": "queued"},
        now=t0,
    )
    conn.commit()
    check(
        queued_during_maintenance.get("persistence_conflict") == "project_maintenance",
        "maintenance mode rejects retry transition to queued",
    )
    check(
        load_source_ingestion_task_row(conn, "maintenance-resume").get("status") == "failed",
        "maintenance rejection preserves failed task state",
    )
    conn.execute("UPDATE project_meta SET maintenance_mode = 0")
    conn.commit()

    fenced = persist_source_ingestion_task_row(conn, task=task("fenced", "batch-fenced"), now=t0)
    conn.commit()
    claimed_a = claim_source_ingestion_task_row(
        conn,
        task_id="fenced",
        worker_id="worker-a",
        lease_seconds=10,
        now=t0,
    )
    conn.commit()
    check(claimed_a.get("worker_id") == "worker-a", "first worker claims fenced task")
    claimed_b = claim_source_ingestion_task_row(
        conn,
        task_id="fenced",
        worker_id="worker-b",
        lease_seconds=10,
        now=t0 + timedelta(seconds=11),
    )
    conn.commit()
    check(claimed_b.get("worker_id") == "worker-b", "replacement worker reclaims expired lease")
    stale_payload = {**fenced, "status": "failed", "current_message": "stale overwrite"}
    stale_save = persist_source_ingestion_task_row(
        conn,
        task=stale_payload,
        expected_worker_id="worker-a",
        now=t0 + timedelta(seconds=12),
    )
    conn.commit()
    authoritative = load_source_ingestion_task_row(conn, "fenced")
    check(not stale_save, "expired worker snapshot is rejected")
    check(authoritative.get("worker_id") == "worker-b", "replacement worker ownership is preserved")
    check(authoritative.get("status") == "running", "stale worker cannot overwrite replacement status")
    check(authoritative.get("current_message") != "stale overwrite", "stale worker cannot overwrite output snapshot")

    def rejects_empty_worker(callback, label: str) -> None:
        try:
            callback()
        except ValueError:
            check(True, label)
        else:
            raise AssertionError(label)

    rejects_empty_worker(
        lambda: claim_source_ingestion_task_row(
            conn,
            task_id="batch-a-1",
            worker_id="",
            lease_seconds=10,
            now=t0,
        ),
        "claim rejects empty worker ID",
    )
    rejects_empty_worker(
        lambda: heartbeat_source_ingestion_task_row(
            conn,
            task_id="fenced",
            worker_id="",
            lease_seconds=10,
            now=t0,
        ),
        "heartbeat rejects empty worker ID",
    )
    rejects_empty_worker(
        lambda: finalize_source_ingestion_task_row(
            conn,
            task={**authoritative, "status": "completed"},
            worker_id="",
            now=t0,
        ),
        "finalize rejects empty worker ID",
    )
    rejects_empty_worker(
        lambda: release_source_ingestion_task_lease_row(
            conn,
            task_id="fenced",
            worker_id="",
            status="running",
            now=t0,
        ),
        "lease release rejects empty worker ID",
    )

    late_heartbeat = heartbeat_source_ingestion_task_row(
        conn,
        task_id="fenced",
        worker_id="worker-b",
        lease_seconds=10,
        now=t0 + timedelta(seconds=22),
    )
    conn.commit()
    check(not late_heartbeat, "heartbeat cannot resurrect an expired lease")
    stale_release = release_source_ingestion_task_lease_row(
        conn,
        task_id="fenced",
        worker_id="worker-b",
        status="completed",
        now=t0 + timedelta(seconds=22),
    )
    conn.commit()
    check(not stale_release, "expired worker cannot finalize through lease release")
    check(
        load_source_ingestion_task_row(conn, "fenced").get("status") == "running",
        "lease release cannot replace the atomic terminal snapshot",
    )

    persist_source_ingestion_task_row(conn, task=task("finalize", "batch-finalize"), now=t0)
    conn.commit()
    claimed_final = claim_source_ingestion_task_row(
        conn,
        task_id="finalize",
        worker_id="worker-final",
        lease_seconds=30,
        now=t0,
    )
    conn.commit()
    finalized = finalize_source_ingestion_task_row(
        conn,
        task={**claimed_final, "status": "completed", "current_message": "done"},
        worker_id="worker-final",
        now=t0 + timedelta(seconds=1),
    )
    conn.commit()
    check(finalized.get("status") == "completed", "finalize persists terminal status")
    check(not finalized.get("worker_id"), "finalize clears worker in the same transaction")
    check(not finalized.get("lease_expires_at"), "finalize clears lease in the same transaction")
    stored_final = load_source_ingestion_task_row(conn, "finalize")
    check(stored_final.get("current_message") == "done", "finalize persists terminal output snapshot")

    persist_source_ingestion_task_row(conn, task=task("control-finalize", "batch-control"), now=t0)
    conn.commit()
    claimed_control = claim_source_ingestion_task_row(
        conn,
        task_id="control-finalize",
        worker_id="worker-control",
        lease_seconds=30,
        now=t0,
    )
    conn.commit()
    request_source_ingestion_task_control_row(
        conn,
        task_id="control-finalize",
        control="cancel",
        now=t0 + timedelta(seconds=1),
    )
    conn.commit()
    blocked_finalize = finalize_source_ingestion_task_row(
        conn,
        task={**claimed_control, "status": "completed"},
        worker_id="worker-control",
        now=t0 + timedelta(seconds=2),
    )
    conn.commit()
    check(blocked_finalize.get("status") == "running", "pending control fences ordinary finalize")
    check(blocked_finalize.get("control_requested") == "cancel", "fenced finalize preserves cancel request")
    controlled_finalize = finalize_source_ingestion_task_row(
        conn,
        task={**claimed_control, "status": "cancelled"},
        worker_id="worker-control",
        now=t0 + timedelta(seconds=3),
    )
    conn.commit()
    check(controlled_finalize.get("status") == "cancelled", "matching control can finalize atomically")
    check(not controlled_finalize.get("control_requested"), "controlled finalize clears handled request")

    persist_source_ingestion_task_row(conn, task=task("finalize-rollback", "batch-rollback"), now=t0)
    conn.commit()
    claimed_rollback = claim_source_ingestion_task_row(
        conn,
        task_id="finalize-rollback",
        worker_id="worker-rollback",
        lease_seconds=30,
        now=t0,
    )
    conn.commit()
    conn.execute(
        """
        CREATE TRIGGER reject_finalize_release
        BEFORE UPDATE OF worker_id ON workflow_runs
        WHEN NEW.run_id = 'finalize-rollback' AND NEW.worker_id IS NULL
        BEGIN
            SELECT RAISE(ABORT, 'synthetic finalize failure');
        END
        """
    )
    conn.commit()
    finalize_failed = False
    try:
        finalize_source_ingestion_task_row(
            conn,
            task={**claimed_rollback, "status": "completed", "current_message": "must roll back"},
            worker_id="worker-rollback",
            now=t0 + timedelta(seconds=1),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        finalize_failed = True
        conn.rollback()
    conn.execute("DROP TRIGGER reject_finalize_release")
    conn.commit()
    rolled_back = load_source_ingestion_task_row(conn, "finalize-rollback")
    check(finalize_failed, "synthetic finalize failure is surfaced")
    check(
        rolled_back.get("status") == "running"
        and rolled_back.get("worker_id") == "worker-rollback"
        and rolled_back.get("current_message") != "must roll back",
        "terminal snapshot and lease release roll back together",
    )

    persist_source_ingestion_task_row(conn, task=task("maintenance", "batch-maintenance"), now=t0)
    conn.commit()
    conn.execute("UPDATE project_meta SET maintenance_mode = 1")
    conn.commit()
    blocked = claim_source_ingestion_task_row(
        conn,
        task_id="maintenance",
        worker_id="worker-maintenance",
        lease_seconds=30,
        now=t0,
    )
    conn.commit()
    check(not blocked, "maintenance mode blocks new task claims")
    conn.execute("UPDATE project_meta SET maintenance_mode = 0")
    conn.commit()
    reopened = claim_source_ingestion_task_row(
        conn,
        task_id="maintenance",
        worker_id="worker-maintenance",
        lease_seconds=30,
        now=t0,
    )
    conn.commit()
    check(reopened.get("worker_id") == "worker-maintenance", "claims resume after maintenance")
    conn.close()

    project_calls: list[str] = []
    sequence = {"value": 0}

    def fair_claim(project_name: str, worker_id: str, **kwargs):
        project_calls.append(project_name)
        sequence["value"] += 1
        return {"task_id": f"fair-{sequence['value']}"}

    fair_dispatcher = IngestionTaskDispatcher(
        project_provider=lambda: ["project-a", "project-b"],
        claim_func=fair_claim,
        settle_func=lambda project_name: 0,
        heartbeat_func=lambda *args, **kwargs: True,
        runner=lambda *args, **kwargs: None,
        heartbeat_seconds=10,
        lease_seconds=3,
    )
    for _ in range(4):
        fair_dispatcher.run_once()
    check(
        project_calls == ["project-a", "project-b", "project-a", "project-b"],
        "dispatcher rotates fairly across projects with continuous work",
    )
    check(fair_dispatcher.heartbeat_seconds <= 1.0, "heartbeat interval is capped to one third of lease")

    heartbeat_calls = {"value": 0}

    def transient_heartbeat(*args, **kwargs):
        heartbeat_calls["value"] += 1
        if heartbeat_calls["value"] <= 2:
            raise sqlite3.OperationalError("temporary busy")
        return True

    heartbeat = _TaskHeartbeat(
        project_name="p",
        task_id="transient",
        worker_id="w",
        lease_seconds=1,
        interval_seconds=0.02,
        heartbeat_func=transient_heartbeat,
    )
    with heartbeat:
        deadline = time.time() + 0.5
        while heartbeat_calls["value"] < 3 and time.time() < deadline:
            time.sleep(0.01)
    check(heartbeat_calls["value"] >= 3, "transient heartbeat failures are retried")
    check(not heartbeat.lost, "transient heartbeat failures do not immediately lose ownership")

    print(f"Ingestion task hardening verification passed: {len(CHECKS)} checks")


if __name__ == "__main__":
    main()
