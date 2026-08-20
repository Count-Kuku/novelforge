"""Small process-local operation registry for SSE lifecycle metadata.

Durable workflow rows remain authoritative for long tasks. This registry only
keeps the short-lived subscription state needed to inspect a stream and its
last events during the current API process.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from uuid import uuid4


class OperationRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, dict] = {}

    def start(self, operation_type: str) -> str:
        operation_id = f"op_{uuid4().hex}"
        with self._lock:
            self._records[operation_id] = {
                "operation_id": operation_id,
                "operation_type": operation_type,
                "status": "running",
                "sequence": 0,
                "events": [],
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
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
                record["status"] = "cancelled" if record.get("status") == "cancel_requested" and status == "completed" else status
                record["finished_at"] = datetime.now(timezone.utc).isoformat()

    def cancel(self, operation_id: str) -> bool:
        with self._lock:
            record = self._records.get(operation_id)
            if not record or record.get("status") not in {"running", "cancel_requested"}:
                return False
            record["status"] = "cancel_requested"
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
