"""Small process-local operation registry for SSE lifecycle metadata.

Durable workflow rows remain authoritative for long tasks. This registry only
keeps the short-lived subscription state needed to inspect a stream and its
last events during the current API process.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from uuid import uuid4


class OperationRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, dict] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._retention = timedelta(minutes=30)
        self._max_records = 500

    def _prune_locked(self) -> None:
        now = datetime.now(timezone.utc)
        expired: list[str] = []
        for operation_id, record in self._records.items():
            finished_at = record.get("finished_at")
            if not finished_at:
                continue
            try:
                finished = datetime.fromisoformat(str(finished_at))
            except ValueError:
                continue
            if now - finished > self._retention:
                expired.append(operation_id)
        for operation_id in expired:
            self._records.pop(operation_id, None)
            self._cancel_events.pop(operation_id, None)
        if len(self._records) <= self._max_records:
            return
        terminal = sorted(
            (
                (record.get("finished_at", ""), operation_id)
                for operation_id, record in self._records.items()
                if record.get("finished_at")
            )
        )
        for _, operation_id in terminal[: max(0, len(self._records) - self._max_records)]:
            self._records.pop(operation_id, None)
            self._cancel_events.pop(operation_id, None)

    def start(self, operation_type: str) -> str:
        operation_id = f"op_{uuid4().hex}"
        with self._lock:
            self._prune_locked()
            self._records[operation_id] = {
                "operation_id": operation_id,
                "operation_type": operation_type,
                "status": "running",
                "sequence": 0,
                "events": [],
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            self._cancel_events[operation_id] = threading.Event()
        return operation_id

    def publish(self, operation_id: str, event: str, data: dict) -> int:
        with self._lock:
            record = self._records[operation_id]
            record["sequence"] += 1
            sequence = record["sequence"]
            record["events"].append({"id": sequence, "event": event, "data": dict(data or {})})
            record["events"] = record["events"][-100:]
            return sequence

    def finish(self, operation_id: str, status: str) -> None:
        with self._lock:
            record = self._records.get(operation_id)
            if record:
                # A cancel request wins over a late worker completion. The
                # worker may still unwind in the background, but clients see
                # a stable terminal cancellation state.
                cancelled = self._cancel_events.get(operation_id)
                record["status"] = "cancelled" if cancelled and cancelled.is_set() else status
                record["finished_at"] = datetime.now(timezone.utc).isoformat()

    def is_cancel_requested(self, operation_id: str) -> bool:
        with self._lock:
            event = self._cancel_events.get(operation_id)
            return bool(event and event.is_set())

    def cancel(self, operation_id: str) -> bool:
        with self._lock:
            record = self._records.get(operation_id)
            if not record or record.get("status") not in {"running", "cancel_requested"}:
                return False
            record["status"] = "cancel_requested"
            event = self._cancel_events.get(operation_id)
            if event:
                event.set()
            return True

    def snapshot(self, operation_id: str) -> dict | None:
        with self._lock:
            record = self._records.get(operation_id)
            return dict(record) if record else None

    def events_after(self, operation_id: str, after: int = 0) -> list[dict]:
        """Return the bounded in-memory replay window after ``after``.

        This is intentionally process-local. Durable workflow rows remain the
        source of truth; the bounded window only makes a dropped SSE client
        able to catch up without restarting a generation.
        """
        with self._lock:
            record = self._records.get(operation_id)
            if not record:
                return []
            return [dict(item) for item in record.get("events", []) if int(item.get("id", 0)) > int(after or 0)]


operation_registry = OperationRegistry()
