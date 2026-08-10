"""Process-local background dispatcher for durable source-ingestion tasks."""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
from uuid import uuid4

from novelforge.services.memory import (
    claim_next_source_ingestion_task,
    heartbeat_source_ingestion_task,
    list_projects,
    settle_stale_source_ingestion_controls,
)
from novelforge.workflows.ingestion_tasks import (
    DEFAULT_TASK_LEASE_SECONDS,
    run_long_reference_ingestion_task,
)


LOGGER = logging.getLogger("novelforge.ingestion_task_dispatcher")
DEFAULT_POLL_SECONDS = 1.0
DEFAULT_HEARTBEAT_SECONDS = 5.0


class _TaskHeartbeat:
    def __init__(
        self,
        *,
        project_name: str,
        task_id: str,
        worker_id: str,
        lease_seconds: int,
        interval_seconds: float,
        heartbeat_func,
        task_label: str = "资料",
    ) -> None:
        self.project_name = project_name
        self.task_id = task_id
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.interval_seconds = interval_seconds
        self.heartbeat_func = heartbeat_func
        self.task_label = str(task_label or "资料")
        self.stop_event = threading.Event()
        self.lost = False
        self.last_success_monotonic = time.monotonic()
        self.consecutive_errors = 0
        self.thread = threading.Thread(
            target=self._run,
            name=f"ingestion-heartbeat-{task_id[-8:]}",
            daemon=True,
        )

    def _run(self) -> None:
        while not self.stop_event.wait(self.interval_seconds):
            try:
                renewed = self.heartbeat_func(
                    self.project_name,
                    self.task_id,
                    self.worker_id,
                    lease_seconds=self.lease_seconds,
                )
            except Exception as exc:
                self.consecutive_errors += 1
                LOGGER.warning(
                    "%s任务心跳写入暂时失败（第 %s 次）：%s；%s",
                    self.task_label,
                    self.consecutive_errors,
                    self.task_id,
                    exc,
                )
                if time.monotonic() - self.last_success_monotonic >= self.lease_seconds:
                    self.lost = True
                    return
                continue
            if not renewed:
                self.lost = True
                return
            self.last_success_monotonic = time.monotonic()
            self.consecutive_errors = 0

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop_event.set()
        self.thread.join(timeout=max(self.interval_seconds * 2, 1.0))


class IngestionTaskDispatcher:
    """Single background worker; SQLite leases make multiple instances safe."""

    def __init__(
        self,
        *,
        project_provider=list_projects,
        claim_func=claim_next_source_ingestion_task,
        settle_func=settle_stale_source_ingestion_controls,
        heartbeat_func=heartbeat_source_ingestion_task,
        runner=run_long_reference_ingestion_task,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
        heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
        lease_seconds: int = DEFAULT_TASK_LEASE_SECONDS,
        worker_id: str = "",
        task_label: str = "资料",
    ) -> None:
        self.project_provider = project_provider
        self.claim_func = claim_func
        self.settle_func = settle_func
        self.heartbeat_func = heartbeat_func
        self.runner = runner
        self.lease_seconds = max(int(lease_seconds), 1)
        self.poll_seconds = max(float(poll_seconds), 0.05)
        heartbeat_safety_limit = max(self.lease_seconds / 3.0, 0.05)
        self.heartbeat_seconds = min(
            max(float(heartbeat_seconds), 0.05),
            heartbeat_safety_limit,
        )
        self.worker_id = worker_id or (
            f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:10]}"
        )
        self.task_label = str(task_label or "资料")
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.active_project = ""
        self.active_task_id = ""
        self.last_error = ""
        self._project_cursor = 0

    @property
    def is_running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def start(self) -> "IngestionTaskDispatcher":
        if self.is_running:
            return self
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._loop,
            name="novelforge-ingestion-dispatcher",
            daemon=True,
        )
        self.thread.start()
        return self

    def wake(self) -> None:
        self.wake_event.set()

    def stop(self, timeout: float = 5.0) -> None:
        self.stop_event.set()
        self.wake_event.set()
        if self.thread:
            self.thread.join(timeout=max(float(timeout), 0.0))

    def run_once(self) -> bool:
        try:
            projects = list(self.project_provider())
        except Exception as exc:
            self.last_error = str(exc)
            LOGGER.exception("无法列出%s任务项目", self.task_label)
            return False
        if not projects:
            return False
        start_index = self._project_cursor % len(projects)
        ordered_projects = [
            (start_index + offset) % len(projects)
            for offset in range(len(projects))
        ]
        for project_index in ordered_projects:
            project_name = projects[project_index]
            if self.stop_event.is_set():
                return False
            try:
                self.settle_func(project_name)
                task = self.claim_func(
                    project_name,
                    self.worker_id,
                    lease_seconds=self.lease_seconds,
                )
            except Exception as exc:
                self.last_error = str(exc)
                LOGGER.exception("领取%s任务失败：%s", self.task_label, project_name)
                continue
            if not task:
                continue
            self._project_cursor = (project_index + 1) % len(projects)
            task_id = str(task.get("task_id") or "")
            self.active_project = project_name
            self.active_task_id = task_id
            try:
                with _TaskHeartbeat(
                    project_name=project_name,
                    task_id=task_id,
                    worker_id=self.worker_id,
                    lease_seconds=self.lease_seconds,
                    interval_seconds=self.heartbeat_seconds,
                    heartbeat_func=self.heartbeat_func,
                    task_label=self.task_label,
                ) as heartbeat:
                    self.runner(
                        project_name,
                        task_id,
                        worker_id=self.worker_id,
                        lease_seconds=self.lease_seconds,
                        lease_already_claimed=True,
                    )
                    if heartbeat.lost:
                        raise RuntimeError(f"任务租约心跳已失效：{task_id}")
                self.last_error = ""
            except Exception as exc:
                self.last_error = str(exc)
                LOGGER.exception("后台%s任务执行失败：%s", self.task_label, task_id)
            finally:
                self.active_project = ""
                self.active_task_id = ""
            return True
        self._project_cursor = (start_index + 1) % len(projects)
        return False

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            processed = self.run_once()
            if processed:
                continue
            self.wake_event.wait(self.poll_seconds)
            self.wake_event.clear()

    def status(self) -> dict:
        return {
            "running": self.is_running,
            "worker_id": self.worker_id,
            "active_project": self.active_project,
            "active_task_id": self.active_task_id,
            "last_error": self.last_error,
        }


_DISPATCHER_LOCK = threading.Lock()
_DISPATCHER: IngestionTaskDispatcher | None = None


def ensure_ingestion_task_dispatcher() -> IngestionTaskDispatcher | None:
    if os.getenv("NOVELFORGE_DISABLE_BACKGROUND_TASKS", "").strip().lower() in {"1", "true", "yes"}:
        return None
    global _DISPATCHER
    with _DISPATCHER_LOCK:
        if _DISPATCHER is None:
            _DISPATCHER = IngestionTaskDispatcher()
        _DISPATCHER.start()
        return _DISPATCHER


def wake_ingestion_task_dispatcher() -> None:
    dispatcher = ensure_ingestion_task_dispatcher()
    if dispatcher:
        dispatcher.wake()


def get_ingestion_task_dispatcher_status() -> dict:
    dispatcher = _DISPATCHER
    return dispatcher.status() if dispatcher else {"running": False}
