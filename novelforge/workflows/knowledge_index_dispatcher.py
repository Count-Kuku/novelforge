"""Process-local dispatcher for durable knowledge index refresh requests."""

from __future__ import annotations

import logging
import os
import threading


LOGGER = logging.getLogger("novelforge.knowledge_index_dispatcher")


class KnowledgeIndexDispatcher:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._projects: set[str] = set()
        self._stop = False
        self.thread: threading.Thread | None = None
        self.active_project = ""
        self.last_error = ""

    @property
    def is_running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def start(self) -> "KnowledgeIndexDispatcher":
        if self.is_running:
            return self
        self._stop = False
        self.thread = threading.Thread(
            target=self._loop, name="novelforge-knowledge-index-dispatcher", daemon=True,
        )
        self.thread.start()
        return self

    def wake(self, project_name: str) -> None:
        clean = str(project_name or "").strip()
        if not clean:
            return
        with self._condition:
            self._projects.add(clean)
            self._condition.notify()

    def stop(self, timeout: float = 5.0) -> None:
        with self._condition:
            self._stop = True
            self._condition.notify_all()
        if self.thread:
            self.thread.join(timeout=max(float(timeout), 0.0))

    def _next_project(self) -> str:
        with self._condition:
            while not self._stop and not self._projects:
                self._condition.wait(timeout=2.0)
            return "" if self._stop else self._projects.pop()

    def _refresh(self, project_name: str) -> None:
        from novelforge.services.memory import (
            load_knowledge_center_index_state,
            process_knowledge_center_index,
            set_knowledge_retrieval_index_state,
        )
        from novelforge.services.retrieval import rebuild_retrieval_assets

        self.active_project = project_name
        try:
            while True:
                batch = process_knowledge_center_index(project_name, limit=1000)
                if batch.get("failed_total"):
                    raise RuntimeError(f"有 {batch.get('failed_total')} 条知识索引更新失败。")
                if not batch.get("remaining"):
                    break
            state = load_knowledge_center_index_state(project_name)
            requested_revision = int(state.get("requested_revision") or 0)
            set_knowledge_retrieval_index_state(project_name, "running")
            rebuild_retrieval_assets(project_name, build_vectors=False)
            latest = load_knowledge_center_index_state(project_name)
            if int(latest.get("requested_revision") or 0) > requested_revision:
                set_knowledge_retrieval_index_state(
                    project_name, "queued", indexed_revision=requested_revision,
                )
                self.wake(project_name)
            else:
                set_knowledge_retrieval_index_state(
                    project_name, "completed", indexed_revision=requested_revision,
                )
            self.last_error = ""
        except Exception as exc:
            self.last_error = str(exc)
            LOGGER.exception("知识检索索引后台刷新失败：%s", project_name)
            try:
                from novelforge.services.memory import set_knowledge_retrieval_index_state
                set_knowledge_retrieval_index_state(project_name, "failed", error_text=str(exc))
            except Exception:
                LOGGER.exception("知识检索索引失败状态写入失败：%s", project_name)
        finally:
            self.active_project = ""

    def _loop(self) -> None:
        while not self._stop:
            project_name = self._next_project()
            if project_name:
                self._refresh(project_name)

    def status(self) -> dict:
        with self._condition:
            pending_projects = sorted(self._projects)
        return {
            "running": self.is_running,
            "active_project": self.active_project,
            "pending_projects": pending_projects,
            "last_error": self.last_error,
        }


_LOCK = threading.Lock()
_DISPATCHER: KnowledgeIndexDispatcher | None = None


def ensure_knowledge_index_dispatcher() -> KnowledgeIndexDispatcher | None:
    if os.getenv("NOVELFORGE_DISABLE_BACKGROUND_TASKS", "").strip().lower() in {"1", "true", "yes"}:
        return None
    global _DISPATCHER
    with _LOCK:
        if _DISPATCHER is None:
            _DISPATCHER = KnowledgeIndexDispatcher()
        _DISPATCHER.start()
        return _DISPATCHER


def wake_knowledge_index_dispatcher(project_name: str) -> None:
    dispatcher = ensure_knowledge_index_dispatcher()
    if dispatcher:
        dispatcher.wake(project_name)


def get_knowledge_index_dispatcher_status() -> dict:
    return _DISPATCHER.status() if _DISPATCHER else {"running": False}


def wake_running_knowledge_index_dispatcher(project_name: str) -> bool:
    dispatcher = _DISPATCHER
    if not dispatcher or not dispatcher.is_running:
        return False
    dispatcher.wake(project_name)
    return True


def prime_knowledge_index_dispatcher(project_names: list[str]) -> int:
    dispatcher = ensure_knowledge_index_dispatcher()
    if not dispatcher:
        return 0
    queued = 0
    from novelforge.services.memory import load_knowledge_center_index_state

    for project_name in project_names:
        try:
            state = load_knowledge_center_index_state(project_name)
        except Exception:
            continue
        if str(state.get("retrieval_status") or "") in {"queued", "running"}:
            dispatcher.wake(project_name)
            queued += 1
    return queued
