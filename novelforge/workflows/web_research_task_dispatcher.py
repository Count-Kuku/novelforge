"""Process-local dispatcher for durable web-research tasks."""

from __future__ import annotations

import os
import threading

from novelforge.services.memory import (
    claim_next_web_research_task,
    heartbeat_web_research_task,
    list_projects,
    settle_stale_web_research_controls,
)
from novelforge.workflows.ingestion_task_dispatcher import IngestionTaskDispatcher
from novelforge.workflows.web_research_tasks import (
    DEFAULT_WEB_RESEARCH_LEASE_SECONDS,
    run_web_research_task,
)


_DISPATCHER_LOCK = threading.Lock()
_DISPATCHER: IngestionTaskDispatcher | None = None


def ensure_web_research_task_dispatcher() -> IngestionTaskDispatcher | None:
    if os.getenv("NOVELFORGE_DISABLE_BACKGROUND_TASKS", "").strip().lower() in {"1", "true", "yes"}:
        return None
    global _DISPATCHER
    with _DISPATCHER_LOCK:
        if _DISPATCHER is None:
            _DISPATCHER = IngestionTaskDispatcher(
                project_provider=list_projects,
                claim_func=claim_next_web_research_task,
                settle_func=settle_stale_web_research_controls,
                heartbeat_func=heartbeat_web_research_task,
                runner=run_web_research_task,
                lease_seconds=DEFAULT_WEB_RESEARCH_LEASE_SECONDS,
                worker_id="",
                task_label="网络研究",
            )
        _DISPATCHER.start()
        return _DISPATCHER


def wake_web_research_task_dispatcher() -> None:
    dispatcher = ensure_web_research_task_dispatcher()
    if dispatcher:
        dispatcher.wake()


def get_web_research_task_dispatcher_status() -> dict:
    return _DISPATCHER.status() if _DISPATCHER else {"running": False}
