"""Shared helpers for the FastAPI route modules.

These were extracted from ``app.py`` so the route modules can import them
without creating an import cycle with the application factory.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import uuid4

from fastapi import Request

from novelforge.services import memory
from .operations import operation_registry
from .schemas import ApiError

LOGGER = logging.getLogger("novelforge.api")
API_PREFIX = "/api/v1"


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or uuid4().hex)


def _envelope(data: Any, request: Request, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "data": data,
        "meta": {
            "request_id": _request_id(request),
            "api_version": "v1",
            **(meta or {}),
        },
    }


def _error_payload(request: Request, code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "error": ApiError(code=code, message=message, details=details).model_dump(),
        "meta": {"request_id": _request_id(request), "api_version": "v1"},
    }


def _project_meta(project_name: str) -> dict[str, Any]:
    with memory.open_project_db(memory.project_path(project_name).resolve()) as conn:
        meta = memory.get_project_meta(conn, project_name)
    if not meta:
        raise FileNotFoundError(f"项目不存在：{project_name}")
    return meta


def _resolve_project_name(project_id: str) -> str:
    candidate = str(project_id or "").strip()
    if not candidate:
        raise FileNotFoundError("项目 ID 不能为空")
    for name in memory.list_projects():
        if name == candidate:
            return name
        try:
            meta = _project_meta(name)
        except Exception:
            continue
        if str(meta.get("project_id") or "") == candidate:
            return name
    raise FileNotFoundError(f"项目不存在：{candidate}")


def _story(project_name: str, story_id: str) -> dict[str, Any]:
    clean_story_id = memory.normalize_story_id(story_id)
    for item in memory.list_stories(project_name):
        if str(item.get("story_id") or "") == clean_story_id:
            return dict(item)
    raise FileNotFoundError(f"故事不存在：{clean_story_id}")


def _sse(event: str, data: Any, *, event_id: str | None = None) -> str:
    lines: list[str] = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append("retry: 3000")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


def _threaded_stream(worker: Callable[[Callable[[str, Any], None], Callable[[], bool]], Any]) -> AsyncIterator[str]:
    """Bridge a synchronous workflow callback into an async SSE iterator."""

    async def iterator() -> AsyncIterator[str]:
        events: queue.Queue[tuple[str, Any, int]] = queue.Queue()
        operation_id = operation_registry.start("creative_writing")
        started_sequence = operation_registry.publish(operation_id, "operation.started", {"operation_id": operation_id, "status": "running"})
        events.put(("operation.started", {"operation_id": operation_id, "status": "running"}, started_sequence))

        def emit(event: str, payload: Any) -> None:
            sequence = operation_registry.publish(operation_id, event, payload if isinstance(payload, dict) else {"value": payload})
            events.put((event, payload, sequence))

        def run() -> None:
            try:
                result = worker(emit, lambda: operation_registry.is_cancel_requested(operation_id))
                if operation_registry.is_cancel_requested(operation_id):
                    operation_registry.finish(operation_id, "cancelled")
                    return
                operation_registry.finish(operation_id, "completed")
                emit("done", {"operation_id": operation_id, "result": result})
            except Exception as exc:  # pragma: no cover - exercised by API smoke tests
                if operation_registry.is_cancel_requested(operation_id):
                    operation_registry.finish(operation_id, "cancelled")
                    return
                LOGGER.exception("SSE workflow failed")
                operation_registry.finish(operation_id, "failed")
                emit("error", {"operation_id": operation_id, "code": "workflow_failed", "message": str(exc)})

        threading.Thread(target=run, daemon=True, name="novelforge-api-sse").start()
        idle_seconds = 0
        while True:
            snapshot = operation_registry.snapshot(operation_id)
            if snapshot and snapshot.get("status") == "cancel_requested":
                sequence = operation_registry.publish(operation_id, "cancelled", {"operation_id": operation_id, "status": "cancelled"})
                operation_registry.finish(operation_id, "cancelled")
                yield _sse("cancelled", {"operation_id": operation_id, "status": "cancelled"}, event_id=str(sequence))
                break
            try:
                event, payload, sequence = events.get_nowait()
                idle_seconds = 0
            except queue.Empty:
                await asyncio.sleep(0.5)
                idle_seconds += 0.5
                if idle_seconds >= 10:
                    idle_seconds = 0
                    yield _sse("heartbeat", {"operation_id": operation_id, "status": "running"}, event_id=str(operation_registry.snapshot(operation_id).get("sequence", 0) if operation_registry.snapshot(operation_id) else 0))
                continue
            yield _sse(event, payload, event_id=str(sequence))
            if event in {"done", "error"}:
                break

    return iterator()
