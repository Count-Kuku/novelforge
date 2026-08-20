"""Versioned FastAPI application used by the Vue frontend.

The application is intentionally mounted independently from the legacy
Streamlit entry point.  This allows the two clients to coexist during the
cutover and gives the launcher a reversible switch.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from novelforge.services import memory
from novelforge.services import project_manager
from novelforge.workflows.interactive_writing import (
    create_writing_session,
    generate_writing_fragment,
)
from storage.repositories.projects import upsert_project_meta
from storage.schema import CURRENT_SCHEMA_VERSION
from .operations import operation_registry

from .schemas import (
    ApiError,
    CreateProjectRequest,
    CreateAttachmentRequest,
    CreateUrlAttachmentRequest,
    CreateSessionRequest,
    CreateStoryRequest,
    CopyStoryRequest,
    DiscussionApprovalRequest,
    DiscussionRequest,
    ExecuteActionRequest,
    FragmentActionRequest,
    GenerateTurnRequest,
    RenameProjectRequest,
    RenameStoryRequest,
    SetStoryModeRequest,
    UpdateProfileRequest,
    UpdateChapterRequest,
    UpdateStructureAssetRequest,
    UpdateChapterPlanRequest,
    PlanActionRequest,
    PendingKnowledgeRequest,
    KnowledgeUpdateRequest,
    RestoreRevisionRequest,
    ModelProfileRequest,
    ActiveModelProfileRequest,
    RulesUpdateRequest,
    PromptOptionsUpdateRequest,
    AutoConfigurationRequest,
    ResearchClaimsReviewRequest,
    ChapterPlanValidationRequest,
    ContentDeleteRequest,
    ResearchTaskRequest,
    TaskControlRequest,
    UpdateOutlineRequest,
    UpdateSessionRequest,
)

LOGGER = logging.getLogger("novelforge.api")
API_PREFIX = "/api/v1"


class SPAStaticFiles(StaticFiles):
    """Serve Vue history routes through the compiled index document."""

    async def get_response(self, path: str, scope):  # type: ignore[no-untyped-def]
        # Never turn a typo under /api into the SPA shell; clients need a
        # real 404/error envelope rather than an HTML document.
        if str(scope.get("path") or "").startswith("/api/") or str(path).startswith("api/"):
            return await super().get_response(path, scope)
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise

    def file_response(self, full_path, stat_result, scope, status_code=200):  # type: ignore[no-untyped-def]
        response = super().file_response(full_path, stat_result, scope, status_code)
        if str(full_path).replace("\\", "/").split("/")[-1] == "index.html":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        else:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


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


def _threaded_stream(worker: Callable[[Callable[[str, Any], None]], Any]) -> AsyncIterator[str]:
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
                result = worker(emit)
                operation_registry.finish(operation_id, "completed")
                emit("done", {"operation_id": operation_id, "result": result})
            except Exception as exc:  # pragma: no cover - exercised by API smoke tests
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


@asynccontextmanager
async def _lifespan(app: FastAPI):
    dispatchers = []
    if os.environ.get("NOVELFORGE_DISABLE_BACKGROUND_TASKS", "").strip().lower() not in {"1", "true", "yes"}:
        from novelforge.workflows.ingestion_task_dispatcher import ensure_ingestion_task_dispatcher
        from novelforge.workflows.knowledge_index_dispatcher import ensure_knowledge_index_dispatcher, prime_knowledge_index_dispatcher
        from novelforge.workflows.web_research_task_dispatcher import ensure_web_research_task_dispatcher

        for ensure in (ensure_ingestion_task_dispatcher, ensure_knowledge_index_dispatcher, ensure_web_research_task_dispatcher):
            dispatcher = ensure()
            if dispatcher:
                dispatchers.append(dispatcher)
        try:
            prime_knowledge_index_dispatcher(memory.list_projects())
        except Exception as exc:
            LOGGER.warning("Failed to prime knowledge index dispatcher: %s", exc)
    app.state.dispatchers = dispatchers
    LOGGER.info("NovelForge FastAPI started with %s dispatcher(s)", len(dispatchers))
    try:
        yield
    finally:
        for dispatcher in dispatchers:
            try:
                dispatcher.stop()
            except Exception:
                LOGGER.exception("Failed to stop dispatcher during API shutdown")
        LOGGER.info("NovelForge FastAPI stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="NovelForge API",
        version="1.0.0",
        lifespan=_lifespan,
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=f"{API_PREFIX}/redoc",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.idempotency_cache = {}
    app.state.idempotency_lock = threading.RLock()

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id") or uuid4().hex
        host = (request.headers.get("host") or "").split(":", 1)[0].lower()
        if host and host not in {"127.0.0.1", "localhost", "testserver"} and os.environ.get("NOVELFORGE_ALLOW_REMOTE") != "1":
            return JSONResponse(status_code=400, content=_error_payload(request, "local_only", "NovelForge API 仅允许本机访问。"))
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("x-novelforge-client") != "vue":
            return JSONResponse(status_code=403, content=_error_payload(request, "client_header_required", "写操作需要 NovelForge 本地客户端标识。"))
        idempotency_key = request.headers.get("idempotency-key", "").strip()
        idempotency_cache_key = (request.method, request.url.path, idempotency_key) if idempotency_key and request.method not in {"GET", "HEAD", "OPTIONS"} and not request.url.path.endswith("/turns/stream") else None
        if idempotency_cache_key:
            with app.state.idempotency_lock:
                cached = app.state.idempotency_cache.get(idempotency_cache_key)
            if cached:
                replay = JSONResponse(status_code=cached["status_code"], content=cached["content"])
                replay.headers["x-request-id"] = request.state.request_id
                replay.headers["x-idempotency-replayed"] = "true"
                replay.headers["X-Content-Type-Options"] = "nosniff"
                replay.headers["Referrer-Policy"] = "no-referrer"
                replay.headers["X-Frame-Options"] = "DENY"
                replay.headers["Content-Security-Policy"] = "default-src 'self'; connect-src 'self' http://127.0.0.1:5173 http://localhost:5173; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'"
                return replay
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; connect-src 'self' http://127.0.0.1:5173 http://localhost:5173; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'"
        if idempotency_cache_key and response.headers.get("content-type", "").startswith("application/json"):
            chunks: list[bytes] = []
            async for chunk in response.body_iterator:
                chunks.append(chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8"))
            raw_body = b"".join(chunks)
            try:
                content = json.loads(raw_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return response
            with app.state.idempotency_lock:
                app.state.idempotency_cache[idempotency_cache_key] = {"status_code": response.status_code, "content": content}
                if len(app.state.idempotency_cache) > 500:
                    app.state.idempotency_cache.pop(next(iter(app.state.idempotency_cache)))
            replay = JSONResponse(status_code=response.status_code, content=content, headers=dict(response.headers))
            return replay
        return response

    @app.exception_handler(FileNotFoundError)
    async def not_found_handler(request: Request, exc: FileNotFoundError):
        return JSONResponse(status_code=404, content=_error_payload(request, "not_found", str(exc)))

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        code = "method_not_allowed" if exc.status_code == 405 else "http_error"
        return JSONResponse(status_code=exc.status_code, content=_error_payload(request, code, str(exc.detail)))

    @app.exception_handler(FileExistsError)
    async def conflict_handler(request: Request, exc: FileExistsError):
        return JSONResponse(status_code=409, content=_error_payload(request, "conflict", str(exc)))

    @app.exception_handler(ValueError)
    async def validation_handler(request: Request, exc: ValueError):
        return JSONResponse(status_code=422, content=_error_payload(request, "validation_error", str(exc)))

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content=_error_payload(request, "validation_error", "请求参数不符合接口契约。", exc.errors()))

    @app.exception_handler(RuntimeError)
    async def runtime_handler(request: Request, exc: RuntimeError):
        return JSONResponse(status_code=409, content=_error_payload(request, "operation_conflict", str(exc)))

    @app.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, Any]:
        return {"status": "ok", "service": "novelforge-api", "time": datetime.now(timezone.utc).isoformat()}

    @app.get(f"{API_PREFIX}/health/live")
    async def api_live(request: Request) -> dict[str, Any]:
        return _envelope({"status": "ok", "service": "novelforge-api"}, request)

    @app.get(f"{API_PREFIX}/health/ready")
    async def ready(request: Request) -> dict[str, Any]:
        return _envelope({"status": "ready", "schema_version": CURRENT_SCHEMA_VERSION, "dispatchers": [item.status() for item in getattr(app.state, "dispatchers", [])]}, request)

    @app.get(f"{API_PREFIX}/version")
    async def version(request: Request) -> dict[str, Any]:
        return _envelope({"version": "0.7.1", "api_version": "v1", "schema_version": CURRENT_SCHEMA_VERSION}, request)

    @app.get(f"{API_PREFIX}/capabilities")
    async def capabilities(request: Request) -> dict[str, Any]:
        """Expose read-only provider readiness for settings and task guards."""
        from novelforge.services.capabilities import build_default_capability_registry

        return _envelope({"capabilities": build_default_capability_registry().snapshot()}, request)

    @app.get(f"{API_PREFIX}/settings/developer")
    async def developer_settings(request: Request) -> dict[str, Any]:
        """Expose developer projections only when enabled by the server environment."""
        enabled = str(os.getenv("NOVELFORGE_DEVELOPER_MODE") or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}
        return _envelope({"enabled": enabled, "projections": ["raw_json", "retrieval_trace", "operation_payload"] if enabled else []}, request)

    @app.get(f"{API_PREFIX}/usage")
    async def usage_summary(request: Request, project_id: str | None = None, story_id: str | None = None) -> dict[str, Any]:
        project_name = _resolve_project_name(project_id) if project_id else None
        from novelforge.services.llm_usage import list_daily_llm_usage, list_recent_llm_usage_events, summarize_local_period

        filters = {"project_name": project_name, "story_id": story_id} if project_name or story_id else {}
        return _envelope({
            "today": await run_in_threadpool(summarize_local_period, "today", **filters),
            "month": await run_in_threadpool(summarize_local_period, "month", **filters),
            "daily": await run_in_threadpool(list_daily_llm_usage, **filters),
            "recent": await run_in_threadpool(list_recent_llm_usage_events, limit=30, **filters),
        }, request)

    @app.get(f"{API_PREFIX}/usage/breakdown")
    async def usage_breakdown(request: Request, dimension: str = "operation", project_id: str | None = None, story_id: str | None = None) -> dict[str, Any]:
        """Return a bounded usage breakdown for the settings cost inspector."""
        allowed_dimensions = {"project", "story", "model", "operation", "agent"}
        if dimension not in allowed_dimensions:
            raise HTTPException(status_code=400, detail=f"Unsupported usage dimension: {dimension}")
        project_name = _resolve_project_name(project_id) if project_id else None
        from novelforge.services.llm_usage import list_llm_usage_breakdown

        filters = {"project_name": project_name, "story_id": story_id} if project_name or story_id else {}
        rows = await run_in_threadpool(list_llm_usage_breakdown, dimension=dimension, **filters)
        return _envelope({"dimension": dimension, "rows": rows[:100]}, request)

    @app.get(f"{API_PREFIX}/settings/models")
    async def model_profiles(request: Request) -> dict[str, Any]:
        profiles_payload = await run_in_threadpool(memory.load_llm_profiles)
        safe_profiles: list[dict[str, Any]] = []
        for profile in profiles_payload.get("profiles", []):
            safe_profiles.append({
                key: value for key, value in dict(profile).items()
                if key not in {"api_key", "embedding_api_key", "secret", "embedding_secret"}
            })
        return _envelope({"active_profile_id": profiles_payload.get("active_profile_id", ""), "profiles": safe_profiles}, request)

    @app.put(f"{API_PREFIX}/settings/models")
    async def update_model_profile(payload: ModelProfileRequest, request: Request) -> dict[str, Any]:
        profile = payload.model_dump()
        profile["id"] = profile.pop("profile_id", "")
        updated = await run_in_threadpool(memory.upsert_llm_profile, profile)
        safe = {key: value for key, value in dict(updated).items() if key not in {"api_key", "embedding_api_key", "secret", "embedding_secret"}}
        return _envelope({"profile": safe, "saved": True}, request)

    @app.post(f"{API_PREFIX}/settings/models/active")
    async def activate_model_profile(payload: ActiveModelProfileRequest, request: Request) -> dict[str, Any]:
        active = await run_in_threadpool(memory.set_active_llm_profile, payload.profile_id)
        safe = {key: value for key, value in dict(active).items() if key not in {"api_key", "embedding_api_key", "secret", "embedding_secret"}}
        return _envelope({"profile": safe, "active_profile_id": payload.profile_id}, request)

    @app.get(f"{API_PREFIX}/settings/rules")
    async def settings_rules(request: Request, project_id: str | None = None, story_id: str | None = None) -> dict[str, Any]:
        """Return all rule layers without leaking unrelated project data."""
        project_name = _resolve_project_name(project_id) if project_id else ""
        story = _story(project_name, story_id or "default") if project_name and story_id else None
        return _envelope({
            "global": await run_in_threadpool(memory.load_global_rules),
            "project": await run_in_threadpool(memory.load_project_rules, project_name) if project_name else {},
            "story": await run_in_threadpool(memory.load_story_rules, project_name, str(story.get("story_id") if story else story_id or "default")) if project_name else {},
            "scope": {"project_id": project_id or "", "story_id": story.get("story_id", "") if story else story_id or ""},
        }, request)

    @app.put(f"{API_PREFIX}/settings/rules/{{scope}}")
    async def update_settings_rules(scope: str, payload: RulesUpdateRequest, request: Request, project_id: str | None = None, story_id: str | None = None) -> dict[str, Any]:
        normalized_scope = str(scope or "").strip().lower()
        project_name = _resolve_project_name(project_id) if project_id else ""
        if normalized_scope == "global":
            saved = await run_in_threadpool(memory.save_global_rules, payload.rules)
        elif normalized_scope == "project" and project_name:
            saved = await run_in_threadpool(memory.save_project_rules, project_name, payload.rules)
        elif normalized_scope == "story" and project_name:
            story_meta = _story(project_name, story_id or "default")
            saved = await run_in_threadpool(memory.save_story_rules, project_name, str(story_meta["story_id"]), payload.rules)
        else:
            raise ValueError("规则作用域或项目参数无效。")
        return _envelope({"scope": normalized_scope, "rules": saved or payload.rules, "saved": True}, request)

    @app.get(f"{API_PREFIX}/settings/prompt-options")
    async def prompt_options(request: Request, layer: str = "story", project_id: str | None = None, story_id: str | None = None) -> dict[str, Any]:
        normalized_layer = str(layer or "story").strip().lower()
        project_name = _resolve_project_name(project_id) if project_id else ""
        if normalized_layer == "global":
            options = await run_in_threadpool(memory.load_global_prompt_options)
        elif normalized_layer == "project" and project_name:
            options = await run_in_threadpool(memory.load_project_prompt_options, project_name)
        elif normalized_layer == "story" and project_name:
            options = await run_in_threadpool(memory.load_story_prompt_options, project_name, story_id or "default")
        else:
            raise ValueError("提示词选项作用域或项目参数无效。")
        return _envelope({"layer": normalized_layer, "options": options}, request)

    @app.put(f"{API_PREFIX}/settings/prompt-options/{{layer}}")
    async def update_prompt_options(layer: str, payload: PromptOptionsUpdateRequest, request: Request, project_id: str | None = None, story_id: str | None = None) -> dict[str, Any]:
        normalized_layer = str(layer or "story").strip().lower()
        project_name = _resolve_project_name(project_id) if project_id else ""
        if normalized_layer == "global":
            saved = await run_in_threadpool(memory.save_global_prompt_options, payload.options)
        elif normalized_layer == "project" and project_name:
            saved = await run_in_threadpool(memory.save_project_prompt_options, project_name, payload.options)
        elif normalized_layer == "story" and project_name:
            _story(project_name, story_id or "default")
            saved = await run_in_threadpool(memory.save_story_prompt_options, project_name, story_id or "default", payload.options)
        else:
            raise ValueError("提示词选项作用域或项目参数无效。")
        return _envelope({"layer": normalized_layer, "options": saved, "saved": True}, request)

    @app.get(f"{API_PREFIX}/settings/auto-configuration")
    async def auto_configuration(request: Request, operation: str = "chapter_write", project_id: str | None = None, story_id: str = "default") -> dict[str, Any]:
        if not project_id:
            return _envelope({"state": {}, "revisions": []}, request)
        project_name = _resolve_project_name(project_id)
        from novelforge.services.automatic_configuration import load_automatic_configuration, list_automatic_configuration_revisions
        return _envelope({
            "state": await run_in_threadpool(load_automatic_configuration, project_name, story_id, operation),
            "revisions": await run_in_threadpool(list_automatic_configuration_revisions, project_name, story_id, operation),
        }, request)

    @app.post(f"{API_PREFIX}/settings/auto-configuration")
    async def configure_auto_configuration(payload: AutoConfigurationRequest, request: Request, project_id: str | None = None, story_id: str = "default") -> dict[str, Any]:
        if not project_id:
            raise ValueError("自动配置需要项目上下文。")
        project_name = _resolve_project_name(project_id)
        from novelforge.services.automatic_configuration import configure_operation_automatically
        result = await run_in_threadpool(configure_operation_automatically, project_name, story_id, payload.operation, goal=payload.goal, source_chars=payload.source_chars, locked_fields=payload.locked_fields)
        return _envelope(result, request)

    @app.get(f"{API_PREFIX}/bootstrap")
    async def bootstrap(request: Request) -> dict[str, Any]:
        projects: list[dict[str, Any]] = []
        for name in memory.list_projects():
            try:
                meta = _project_meta(name)
                stories = memory.list_stories(name)
            except Exception as exc:
                LOGGER.warning("Skipping unreadable project %s: %s", name, exc)
                continue
            projects.append({
                "project_id": str(meta.get("project_id") or name),
                "name": name,
                "title": str(meta.get("title") or name),
                "genre": str(meta.get("genre") or ""),
                "description": str(meta.get("description") or ""),
                "updated_at": str(meta.get("updated_at") or ""),
                "story_count": len(stories),
            })
        return _envelope({"projects": projects, "frontend_modes": ["planned", "conversational"]}, request)

    @app.get(f"{API_PREFIX}/projects")
    async def projects(request: Request) -> dict[str, Any]:
        return await bootstrap(request)

    @app.post(f"{API_PREFIX}/projects", status_code=status.HTTP_201_CREATED)
    async def create_project_endpoint(payload: CreateProjectRequest, request: Request) -> dict[str, Any]:
        name = await run_in_threadpool(memory.create_project, payload.name)
        if payload.title or payload.genre or payload.description:
            current = memory.load_memory(name)
            current.update({"title": payload.title or current.get("title") or name, "genre": payload.genre or current.get("genre") or ""})
            await run_in_threadpool(memory.save_memory, name, current)
            with memory.open_project_db(memory.project_path(name).resolve()) as conn:
                upsert_project_meta(conn, project_name=name, title=current.get("title"), genre=current.get("genre", ""), description=payload.description)
                conn.commit()
        meta = _project_meta(name)
        return _envelope({"project": meta}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}")
    async def project_detail(project_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        meta = _project_meta(name)
        stories = memory.list_stories(name)
        return _envelope({"project": meta, "stories": stories}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/summary")
    async def project_summary(project_id: str, request: Request, story_id: str = "default") -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        summary = await run_in_threadpool(project_manager.get_project_summary, name, story_id)
        return _envelope(summary, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/content")
    async def project_content(project_id: str, request: Request, story_id: str = "default", cursor: int = 0, page_size: int = 40) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        from novelforge.services.resource_browser import list_resource_browser_items
        return _envelope(await run_in_threadpool(list_resource_browser_items, name, story_id, cursor=cursor, page_size=page_size), request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/content/delete")
    async def delete_project_content(project_id: str, payload: ContentDeleteRequest, request: Request, story_id: str = "default") -> dict[str, Any]:
        if not payload.confirm:
            raise ValueError("删除内容需要明确确认。")
        name = _resolve_project_name(project_id)
        from novelforge.services.resource_browser import delete_resource_browser_item
        deleted = await run_in_threadpool(delete_resource_browser_item, name, payload.resource, story_id)
        return _envelope({"deleted": bool(deleted)}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/tasks")
    async def project_tasks(project_id: str, request: Request, status_filter: str | None = None) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        statuses = [status_filter] if status_filter else None
        return _envelope({
            "ingestion": memory.list_source_ingestion_tasks(name, statuses=statuses),
            "web_research": memory.list_web_research_tasks(name, statuses=statuses),
        }, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/ingestion/workbench")
    async def ingestion_workbench_before_detail(project_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        from novelforge.workflows.source_workflows import build_ingestion_workbench
        return _envelope(await run_in_threadpool(build_ingestion_workbench, name), request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/ingestion/batch", status_code=status.HTTP_202_ACCEPTED)
    async def create_batch_ingestion(project_id: str, story_id: str, request: Request, files: list[UploadFile] = File(...), scope: str = Form("project"), use_ocr: bool = Form(False)) -> dict[str, Any]:
        """Import several reference files in one confirmed batch and queue knowledge work."""
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        if scope not in {"story", "project"}:
            raise ValueError("批量导入只支持故事或项目作用域。")
        if not files or len(files) > 20:
            raise ValueError("批量导入一次最多选择 20 个文件。")
        from novelforge.services.document_parsing import ocr_pdf_bytes, parse_document_bytes
        from novelforge.workflows.creative_attachments import import_creative_documents

        documents = []
        warnings: list[str] = []
        total_bytes = 0
        for file in files:
            content = await file.read()
            total_bytes += len(content)
            if total_bytes > 32 * 1024 * 1024:
                raise ValueError("批量资料总大小不能超过 32MB。")
            filename = file.filename or "attachment.txt"
            parser = ocr_pdf_bytes if use_ocr and filename.lower().endswith(".pdf") else parse_document_bytes
            document = await run_in_threadpool(parser, filename, content)
            documents.append(document)
            warnings.extend([f"{file.filename or '资料'}：{warning}" for warning in document.warnings])
        attachments = await run_in_threadpool(import_creative_documents, name, story_id, "", documents, scope=scope)
        return _envelope({"accepted_count": len(attachments), "attachments": attachments, "warnings": warnings, "scope": scope, "ocr_requested": bool(use_ocr)}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/ingestion/ocr-preview")
    async def preview_ocr(project_id: str, story_id: str, request: Request, file: UploadFile = File(...), languages: str = Form("chi_sim+eng"), dpi: int = Form(200)) -> dict[str, Any]:
        """Preview local OCR without persisting the source or scheduling extraction."""
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        filename = file.filename or "preview.pdf"
        if not filename.lower().endswith(".pdf"):
            raise ValueError("OCR 预览只支持 PDF 文件。")
        content = await file.read()
        progress: list[dict[str, Any]] = []
        from novelforge.services.document_parsing import ocr_pdf_bytes

        document = await run_in_threadpool(
            ocr_pdf_bytes,
            filename,
            content,
            languages=languages,
            dpi=max(72, min(int(dpi or 200), 600)),
            progress_callback=progress.append,
        )
        sections = [
            {
                "title": section.title,
                "page": section.location.get("page"),
                "confidence": section.location.get("ocr_confidence"),
                "char_count": len(section.text),
                "text_preview": section.text[:2_000],
            }
            for section in document.sections
        ]
        return _envelope(
            {
                "filename": document.filename,
                "parser_name": document.parser_name,
                "warnings": document.warnings,
                "metadata": document.metadata,
                "sections": sections,
                "progress": progress,
            },
            request,
        )

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/ingestion/{{task_id}}")
    async def ingestion_detail(project_id: str, task_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        task = await run_in_threadpool(memory.load_source_ingestion_task, name, task_id)
        if not task:
            raise FileNotFoundError(f"资料导入任务不存在：{task_id}")
        return _envelope({"task": task}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/ingestion/{{task_id}}/control")
    async def ingestion_control(project_id: str, task_id: str, payload: TaskControlRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        from novelforge.workflows import ingestion_tasks

        handlers = {
            "pause": ingestion_tasks.pause_long_reference_ingestion_task,
            "resume": ingestion_tasks.resume_long_reference_ingestion_task,
            "cancel": ingestion_tasks.cancel_long_reference_ingestion_task,
            "retry": ingestion_tasks.retry_failed_long_reference_ingestion_task,
        }
        task = await run_in_threadpool(handlers[payload.action], name, task_id)
        return _envelope({"task": task, "action": payload.action}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/sources")
    async def project_sources(project_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        from novelforge.workflows.source_workflows import build_ingestion_source_ledger

        return _envelope({"sources": await run_in_threadpool(build_ingestion_source_ledger, name)}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/research", status_code=status.HTTP_201_CREATED)
    async def create_research(project_id: str, payload: ResearchTaskRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        if payload.story_id:
            _story(name, payload.story_id)
        from novelforge.workflows.web_research_tasks import create_web_research_task

        task = await run_in_threadpool(
            create_web_research_task,
            name,
            payload.topic,
            objective=payload.objective,
            source_kinds=payload.source_kinds,
            official_domains=payload.official_domains,
            max_results_per_branch=payload.max_results_per_branch,
            max_pages=payload.max_pages,
            language=payload.language,
            freshness=payload.freshness,
            scope=payload.scope,
            story_id=payload.story_id,
        )
        return _envelope({"task": task}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/research/{{task_id}}")
    async def research_detail(project_id: str, task_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        task = await run_in_threadpool(memory.load_web_research_task, name, task_id)
        if not task:
            raise FileNotFoundError(f"网络研究任务不存在：{task_id}")
        return _envelope({"task": task}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/research/{{task_id}}/control")
    async def research_control(project_id: str, task_id: str, payload: TaskControlRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        from novelforge.workflows import web_research_tasks

        handlers = {
            "pause": web_research_tasks.pause_web_research_task,
            "resume": web_research_tasks.resume_web_research_task,
            "cancel": web_research_tasks.cancel_web_research_task,
            "retry": web_research_tasks.retry_web_research_task,
        }
        task = await run_in_threadpool(handlers[payload.action], name, task_id)
        return _envelope({"task": task, "action": payload.action}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/research/{{task_id}}/sources/activate")
    async def activate_research_sources(project_id: str, task_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        from novelforge.workflows.web_research_tasks import activate_web_research_sources

        result = await run_in_threadpool(activate_web_research_sources, name, task_id)
        task = await run_in_threadpool(memory.load_web_research_task, name, task_id)
        return _envelope({"result": result, "task": task}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/research/{{task_id}}/sources/quarantine")
    async def quarantine_research_sources(project_id: str, task_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        from novelforge.workflows.web_research_tasks import quarantine_web_research_sources

        result = await run_in_threadpool(quarantine_web_research_sources, name, task_id)
        task = await run_in_threadpool(memory.load_web_research_task, name, task_id)
        return _envelope({"result": result, "task": task}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/research/{{task_id}}/claims/review")
    async def review_research_claims(project_id: str, task_id: str, payload: ResearchClaimsReviewRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        from novelforge.workflows.web_research_tasks import queue_web_research_claims_for_review
        result = await run_in_threadpool(queue_web_research_claims_for_review, name, task_id, payload.claim_ids)
        task = await run_in_threadpool(memory.load_web_research_task, name, task_id)
        return _envelope({"result": result, "task": task}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/search")
    async def search_knowledge(project_id: str, request: Request, query: str = "", story_id: str | None = None, cursor: str = "", page_size: int = 40, record_type: str = "") -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        result = await run_in_threadpool(
            memory.search_knowledge_center,
            name,
            query=query,
            record_types=[record_type] if record_type.strip() else None,
            story_id=story_id,
            cursor=cursor,
            page_size=max(1, min(page_size, 100)),
        )
        return _envelope(result, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/pending")
    async def pending_knowledge(project_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        return _envelope({"items": await run_in_threadpool(memory.load_pending_knowledge_items, name)}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/knowledge/pending/confirm")
    async def confirm_pending_knowledge(project_id: str, payload: PendingKnowledgeRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        result = await run_in_threadpool(memory.confirm_pending_knowledge_items_with_records, name, payload.pending_ids)
        return _envelope(result, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/knowledge/pending/discard")
    async def discard_pending_knowledge(project_id: str, payload: PendingKnowledgeRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        removed = await run_in_threadpool(memory.discard_pending_knowledge_items, name, payload.pending_ids)
        return _envelope({"removed_count": removed}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/entities")
    async def knowledge_entities(project_id: str, request: Request, entity_type: str = "character") -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        from novelforge.domain.knowledge_entities import build_character_entity_cards, build_setting_entity_cards, timeline_item_sort_key
        if entity_type == "character":
            items = await run_in_threadpool(build_character_entity_cards, name)
        elif entity_type == "setting":
            items = await run_in_threadpool(build_setting_entity_cards, name)
        elif entity_type == "timeline":
            base = await run_in_threadpool(memory.load_knowledge_category, name, "timeline_events")
            items = sorted([item for item in base if isinstance(item, dict)], key=timeline_item_sort_key)
        else:
            raise ValueError("entity_type 只支持 character、setting 或 timeline。")
        return _envelope({"entity_type": entity_type, "items": items}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/{{record_type}}/{{record_id}}/evidence")
    async def knowledge_evidence(project_id: str, record_type: str, record_id: str, request: Request) -> dict[str, Any]:
        if record_type != "knowledge":
            raise ValueError("只有正式知识条目支持证据查看。")
        name = _resolve_project_name(project_id)
        return _envelope({"evidence": await run_in_threadpool(memory.load_knowledge_evidence, name, record_id)}, request)

    @app.get(f"{API_PREFIX}/knowledge/schema/{{category}}")
    async def knowledge_schema(category: str, request: Request) -> dict[str, Any]:
        from novelforge.domain.knowledge_types import KNOWLEDGE_TYPE_FIELDS
        fields = [{"key": field.key, "label": field.label, "kind": field.kind, "aliases": list(field.aliases), "required": field.required} for field in KNOWLEDGE_TYPE_FIELDS.get(category, ())]
        if not fields and category not in KNOWLEDGE_TYPE_FIELDS:
            raise ValueError("未知知识分类。")
        return _envelope({"category": category, "fields": fields, "schema_version": 2}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/{{record_type}}/{{record_id}}")
    async def knowledge_detail(project_id: str, record_type: str, record_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        record = await run_in_threadpool(memory.load_knowledge_center_record, name, record_type, record_id)
        if not record:
            raise FileNotFoundError(f"知识条目不存在：{record_type}/{record_id}")
        return _envelope(record, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/{{record_type}}/{{record_id}}/revisions")
    async def knowledge_revisions(project_id: str, record_type: str, record_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        if record_type != "knowledge":
            raise ValueError("只有正式知识条目支持修订历史。")
        return _envelope({"revisions": await run_in_threadpool(memory.load_knowledge_revisions, name, record_id)}, request)

    @app.put(f"{API_PREFIX}/projects/{{project_id}}/knowledge/{{record_type}}/{{record_id}}")
    async def update_knowledge_record(project_id: str, record_type: str, record_id: str, payload: KnowledgeUpdateRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        if record_type != "knowledge":
            raise ValueError("只有正式知识条目支持编辑。")
        current = await run_in_threadpool(memory.load_knowledge_center_record, name, record_type, record_id)
        if not current:
            raise FileNotFoundError(f"知识条目不存在：{record_id}")
        if payload.expected_revision_id:
            revisions = await run_in_threadpool(memory.load_knowledge_revisions, name, record_id)
            latest_revision_id = str(revisions[0].get("revision_id") or "") if revisions else ""
            if latest_revision_id and latest_revision_id != payload.expected_revision_id:
                raise RuntimeError("知识条目已被其它操作修改，请重新加载或选择手动合并。")
        source_category = str(current.get("category") or "").strip()
        current_payload = current.get("payload") if isinstance(current.get("payload"), dict) else current
        patch = {**dict(current_payload), **payload.patch, "revision_reason": payload.reason}
        updated = await run_in_threadpool(memory.update_confirmed_knowledge_item_record, name, source_category, record_id, patch, target_category=payload.target_category or source_category)
        if not updated:
            raise RuntimeError("知识编辑未能提交，可能已被其它操作修改。")
        return _envelope({"record": await run_in_threadpool(memory.load_knowledge_center_record, name, record_type, record_id), "saved": True}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/knowledge/{{record_type}}/{{record_id}}/restore")
    async def restore_knowledge_record(project_id: str, record_type: str, record_id: str, payload: RestoreRevisionRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        if record_type != "knowledge":
            raise ValueError("只有正式知识条目支持修订恢复。")
        result = await run_in_threadpool(memory.restore_knowledge_revision, name, record_id, payload.revision_id, reason=payload.reason)
        return _envelope(result, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/knowledge/graph")
    async def knowledge_graph(project_id: str, request: Request, story_id: str | None = None) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        return _envelope(await run_in_threadpool(memory.load_knowledge_graph, name, story_id=story_id), request)

    @app.patch(f"{API_PREFIX}/projects/{{project_id}}")
    async def rename_project_endpoint(project_id: str, payload: RenameProjectRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        renamed = await run_in_threadpool(project_manager.rename_project, name, payload.name)
        return _envelope({"project": _project_meta(renamed)}, request)

    @app.delete(f"{API_PREFIX}/projects/{{project_id}}")
    async def delete_project_endpoint(project_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        deleted = await run_in_threadpool(project_manager.delete_project, name)
        return _envelope({"deleted": bool(deleted), "project_id": project_id}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories")
    async def stories(project_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        return _envelope({"stories": memory.list_stories(name)}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories", status_code=status.HTTP_201_CREATED)
    async def create_story_endpoint(project_id: str, payload: CreateStoryRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        story = await run_in_threadpool(memory.create_story, name, payload.name, payload.description, payload.creation_mode)
        return _envelope({"story": story}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}")
    async def story_detail(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        story = _story(name, story_id)
        return _envelope({"story": story, "profile": memory.load_creative_profile(name, story_id)}, request)

    @app.patch(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}")
    async def rename_story_endpoint(project_id: str, story_id: str, payload: RenameStoryRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        story = await run_in_threadpool(memory.rename_story, name, story_id, payload.name, payload.description)
        return _envelope({"story": story}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/copy", status_code=status.HTTP_201_CREATED)
    async def copy_story_endpoint(project_id: str, story_id: str, payload: CopyStoryRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        story = await run_in_threadpool(
            memory.copy_story,
            name,
            story_id,
            payload.name,
            include_discussions=payload.include_discussions,
            include_summaries=payload.include_summaries,
            include_chapters=payload.include_chapters,
        )
        return _envelope({"story": story}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/archive")
    async def archive_story_endpoint(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        archived = await run_in_threadpool(memory.archive_story, name, story_id)
        return _envelope({"archived": bool(archived), "story_id": story_id}, request)

    @app.delete(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}")
    async def delete_story_endpoint(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        deleted = await run_in_threadpool(memory.delete_story, name, story_id)
        return _envelope({"deleted": bool(deleted), "story_id": story_id}, request)

    @app.patch(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/mode")
    async def set_story_mode(project_id: str, story_id: str, payload: SetStoryModeRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        updated = await run_in_threadpool(memory.set_story_creation_mode, name, story_id, payload.creation_mode)
        return _envelope({"story": updated}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/workspace")
    async def story_workspace(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        story = _story(name, story_id)
        return _envelope({
            "story": story,
            "profile": memory.load_creative_profile(name, story_id),
            "outline": memory.load_outline(name, story_id=story_id),
            "volumes": memory.list_volumes(name, story_id=story_id),
            "arcs": memory.list_arcs(name, story_id=story_id),
            "chapters": project_manager.list_chapter_inventory(name, story_id=story_id),
        }, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/structure")
    async def story_structure(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        return _envelope({
            "volumes": memory.list_volumes(name, story_id=story_id),
            "arcs": memory.list_arcs(name, story_id=story_id),
            "chapters": await run_in_threadpool(project_manager.list_chapter_inventory, name, story_id),
        }, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/context/preview")
    async def context_preview(project_id: str, story_id: str, request: Request, query: str = "", chapter_no: int | None = None, budget: int = 24_000) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        from novelforge.workflows.context_assembly import assemble_generation_context

        context = await run_in_threadpool(
            assemble_generation_context,
            name,
            story_id=story_id,
            capability="creative_writing",
            query=query or "当前故事上下文",
            chapter_no=chapter_no,
            context_budget=max(1_000, min(int(budget), 200_000)),
        )
        return _envelope(context.model_dump(), request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/rules")
    async def story_rules(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        return _envelope({"project": memory.load_project_rules(name), "story": memory.load_story_rules(name, story_id)}, request)

    @app.put(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/rules")
    async def update_story_rules(project_id: str, story_id: str, payload: RulesUpdateRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        saved = await run_in_threadpool(memory.save_story_rules, name, story_id, payload.rules)
        return _envelope({"story": saved, "saved": True}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/volumes/{{volume_no}}")
    async def volume_detail(project_id: str, story_id: str, volume_no: int, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        return _envelope({"metadata": memory.load_volume_metadata(name, volume_no, story_id), "outline": memory.load_volume_outline(name, volume_no, story_id), "discussion": memory.load_volume_discussion_artifact(name, volume_no, story_id)}, request)

    @app.put(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/volumes/{{volume_no}}")
    async def update_volume(project_id: str, story_id: str, volume_no: int, payload: UpdateStructureAssetRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        if payload.outline is not None:
            await run_in_threadpool(memory.save_volume_outline, name, volume_no, payload.outline, story_id)
        if payload.metadata:
            await run_in_threadpool(memory.save_volume_metadata, name, volume_no, payload.metadata, story_id)
        return _envelope({"metadata": memory.load_volume_metadata(name, volume_no, story_id), "outline": memory.load_volume_outline(name, volume_no, story_id), "saved": True}, request)

    @app.delete(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/volumes/{{volume_no}}")
    async def delete_volume(project_id: str, story_id: str, volume_no: int, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        deleted = await run_in_threadpool(memory.delete_volume, name, volume_no, story_id)
        return _envelope({"deleted": bool(deleted), "volume_no": volume_no}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/arcs/{{arc_no}}")
    async def arc_detail(project_id: str, story_id: str, arc_no: int, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        return _envelope({"metadata": memory.load_arc_metadata(name, arc_no, story_id), "outline": memory.load_arc_outline(name, arc_no, story_id), "discussion": memory.load_arc_discussion_artifact(name, arc_no, story_id)}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/arcs/{{arc_no}}/chapter-plan")
    async def arc_chapter_plan(project_id: str, story_id: str, arc_no: int, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        return _envelope(await run_in_threadpool(memory.load_arc_chapter_plan, name, arc_no, story_id), request)

    @app.put(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/arcs/{{arc_no}}/chapter-plan")
    async def update_arc_chapter_plan(project_id: str, story_id: str, arc_no: int, payload: UpdateChapterPlanRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        await run_in_threadpool(memory.save_arc_chapter_plan, name, arc_no, payload.plan, payload.report_markdown, story_id)
        saved = await run_in_threadpool(memory.load_arc_chapter_plan, name, arc_no, story_id)
        return _envelope({"plan": saved, "saved": True}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/arcs/{{arc_no}}/chapter-plan/validate")
    async def validate_arc_chapter_plan(project_id: str, story_id: str, arc_no: int, payload: ChapterPlanValidationRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        from novelforge.domain.structure_validation import validate_arc_chapter_plan
        result = await run_in_threadpool(validate_arc_chapter_plan, name, story_id, arc_no, payload.plan)
        return _envelope(result, request)

    @app.put(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/arcs/{{arc_no}}")
    async def update_arc(project_id: str, story_id: str, arc_no: int, payload: UpdateStructureAssetRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        if payload.outline is not None:
            await run_in_threadpool(memory.save_arc_outline, name, arc_no, payload.outline, story_id)
        if payload.metadata:
            await run_in_threadpool(memory.save_arc_metadata, name, arc_no, payload.metadata, story_id)
        return _envelope({"metadata": memory.load_arc_metadata(name, arc_no, story_id), "outline": memory.load_arc_outline(name, arc_no, story_id), "saved": True}, request)

    @app.delete(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/arcs/{{arc_no}}")
    async def delete_arc(project_id: str, story_id: str, arc_no: int, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        deleted = await run_in_threadpool(memory.delete_arc, name, arc_no, story_id)
        return _envelope({"deleted": bool(deleted), "arc_no": arc_no}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/outline")
    async def story_outline(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        return _envelope({"content": memory.load_outline(name, story_id=story_id)}, request)

    @app.put(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/outline")
    async def update_story_outline(project_id: str, story_id: str, payload: UpdateOutlineRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        await run_in_threadpool(memory.save_outline, name, payload.content, story_id)
        return _envelope({"content": payload.content, "saved": True}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/chapters/{{chapter_no}}")
    async def chapter_detail(project_id: str, story_id: str, chapter_no: int, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        inventory = await run_in_threadpool(project_manager.list_chapter_inventory, name, story_id)
        item = next((row for row in inventory if int(row.get("chapter_no", -1)) == chapter_no), {"chapter_no": chapter_no})
        return _envelope({"chapter": item, "outline": memory.load_chapter_outline(name, chapter_no, story_id), "content": memory.load_chapter(name, chapter_no, story_id), "review": memory.load_review(name, chapter_no, story_id)}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/chapters/{{chapter_no}}/versions")
    async def chapter_versions(project_id: str, story_id: str, chapter_no: int, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        runs = await run_in_threadpool(memory.list_pipeline_run_summaries, name, chapter_no, story_id)
        current = await run_in_threadpool(memory.load_chapter, name, chapter_no, story_id)
        versions: list[dict[str, Any]] = [{"version_id": "current", "label": "当前正文", "content": current, "updated_at": "", "source": "current"}]
        for run in runs:
            payload = run.get("payload") if isinstance(run.get("payload"), dict) else {}
            artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
            snapshot = artifacts.get("chapter_content") or artifacts.get("content") or payload.get("chapter_content")
            if isinstance(snapshot, str) and snapshot.strip():
                versions.append({"version_id": str(run.get("run_id") or ""), "label": str(run.get("workflow_type") or "历史运行"), "content": snapshot, "updated_at": run.get("updated_at", ""), "source": "workflow_run"})
        return _envelope({"versions": versions}, request)

    @app.put(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/chapters/{{chapter_no}}")
    async def update_chapter(project_id: str, story_id: str, chapter_no: int, payload: UpdateChapterRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        if payload.kind == "outline":
            await run_in_threadpool(memory.save_chapter_outline, name, chapter_no, payload.content, story_id)
        else:
            await run_in_threadpool(memory.save_chapter, name, chapter_no, payload.content, story_id)
        return _envelope({"chapter_no": chapter_no, "kind": payload.kind, "content": payload.content, "saved": True}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/profile")
    async def story_profile(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        return _envelope({"profile": memory.load_creative_profile(name, story_id)}, request)

    @app.put(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/profile")
    async def update_story_profile(project_id: str, story_id: str, payload: UpdateProfileRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        profile = await run_in_threadpool(memory.save_creative_profile, name, payload.profile, story_id, True)
        return _envelope({"profile": profile, "saved": True}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/discussions/{{asset_type}}")
    async def discussion_artifact(project_id: str, story_id: str, asset_type: str, request: Request, asset_no: int | None = None) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        if asset_type == "profile":
            artifact = memory.load_creative_profile_discussion_artifact(name, story_id)
        elif asset_type == "outline":
            artifact = memory.load_outline_discussion_artifact(name, story_id)
        elif asset_type == "volume" and asset_no:
            artifact = memory.load_volume_discussion_artifact(name, asset_no, story_id)
        elif asset_type == "arc" and asset_no:
            artifact = memory.load_arc_discussion_artifact(name, asset_no, story_id)
        elif asset_type == "chapter" and asset_no:
            artifact = memory.load_chapter_discussion_artifact(name, asset_no, story_id)
        else:
            raise ValueError("不支持的讨论资产类型。")
        return _envelope({"asset_type": asset_type, "artifact": artifact}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/discussions/{{asset_type}}/stream")
    async def discussion_stream(project_id: str, story_id: str, asset_type: str, payload: DiscussionRequest, request: Request, asset_no: int | None = None):
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        if asset_type not in {"profile", "outline", "volume", "arc", "chapter"}:
            raise ValueError("不支持的讨论资产类型。")
        if asset_type in {"volume", "arc", "chapter"} and not asset_no:
            raise ValueError("分卷或剧情段讨论需要 asset_no。")

        def worker(emit: Callable[[str, Any], None]) -> dict[str, Any]:
            from novelforge.workflows.skills import discussions

            stream_callback = lambda text: emit("delta", {"text": str(text or "")})
            if asset_type == "profile":
                return discussions.discuss_creative_profile(name, payload.idea, story_id, stream_callback=stream_callback)
            if asset_type == "outline":
                return discussions.discuss_outline(name, payload.idea, story_id, stream_callback=stream_callback)
            if asset_type == "volume":
                metadata = memory.load_volume_metadata(name, asset_no, story_id)
                return discussions.discuss_volume(name, asset_no, str(metadata.get("title") or ""), str(metadata.get("summary") or ""), payload.idea, story_id, stream_callback=stream_callback)
            if asset_type == "chapter":
                return discussions.discuss_chapter(name, asset_no, payload.idea, story_id, stream_callback=stream_callback)
            metadata = memory.load_arc_metadata(name, asset_no, story_id)
            if asset_type == "arc":
                return discussions.discuss_arc(name, asset_no, metadata.get("volume_no"), str(metadata.get("title") or ""), str(metadata.get("summary") or ""), metadata.get("estimated_chapter_count"), str(metadata.get("target_word_count_range") or ""), payload.idea, story_id, stream_callback=stream_callback)
            raise ValueError("不支持的讨论资产类型。")

        return StreamingResponse(_threaded_stream(worker), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/discussions/{{asset_type}}/approve")
    async def approve_discussion(project_id: str, story_id: str, asset_type: str, payload: DiscussionApprovalRequest, request: Request, asset_no: int | None = None) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        from novelforge.workflows.skills import discussions

        if asset_type == "profile":
            result = await run_in_threadpool(discussions.approve_creative_profile_discussion, name, payload.step, story_id)
        elif asset_type == "outline":
            result = await run_in_threadpool(discussions.approve_outline_discussion, name, payload.step, story_id)
        elif asset_type == "volume" and asset_no:
            result = await run_in_threadpool(discussions.approve_volume_discussion, name, asset_no, payload.step, story_id)
        elif asset_type == "arc" and asset_no:
            result = await run_in_threadpool(discussions.approve_arc_discussion, name, asset_no, payload.step, story_id)
        elif asset_type == "chapter" and asset_no:
            result = await run_in_threadpool(discussions.approve_chapter_discussion, name, asset_no, payload.step, story_id)
        else:
            raise ValueError("不支持的讨论资产类型。")
        return _envelope({"asset_type": asset_type, "result": result}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions", status_code=status.HTTP_201_CREATED)
    async def create_session(project_id: str, story_id: str, payload: CreateSessionRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        story = _story(name, story_id)
        auto_extract = payload.auto_extract_mode or ("on_accept" if story.get("creation_mode") == "conversational" else "manual")
        session = await run_in_threadpool(
            create_writing_session,
            name,
            story_id,
            session_goal=payload.session_goal,
            title=payload.title,
            auto_extract_mode=auto_extract,
        )
        return _envelope({"session": session}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions")
    async def list_sessions(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        sessions = await run_in_threadpool(memory.list_creative_sessions, name, story_id, include_archived=True)
        return _envelope({"sessions": sessions}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}")
    async def session_detail(project_id: str, story_id: str, session_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        bundle = await run_in_threadpool(memory.load_creative_session_bundle, name, session_id, story_id=story_id)
        if not bundle:
            raise FileNotFoundError(f"创作会话不存在：{session_id}")
        return _envelope(bundle, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/attachments")
    async def list_session_attachments(project_id: str, story_id: str, session_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        return _envelope({"attachments": await run_in_threadpool(memory.list_creative_attachments, name, story_id=story_id, session_id=session_id)}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/attachments", status_code=status.HTTP_201_CREATED)
    async def create_session_attachment(project_id: str, story_id: str, session_id: str, payload: CreateAttachmentRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        from novelforge.workflows.creative_attachments import import_creative_pasted_text

        attachment = await run_in_threadpool(import_creative_pasted_text, name, story_id, session_id, payload.text, title=payload.title, scope=payload.scope)
        return _envelope({"attachment": attachment}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/attachments/url", status_code=status.HTTP_201_CREATED)
    async def create_session_url_attachment(project_id: str, story_id: str, session_id: str, payload: CreateUrlAttachmentRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        from novelforge.workflows.creative_attachments import import_creative_url

        attachment = await run_in_threadpool(import_creative_url, name, story_id, session_id, payload.url, scope=payload.scope)
        return _envelope({"attachment": attachment}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/attachments/file", status_code=status.HTTP_201_CREATED)
    async def create_session_file_attachment(project_id: str, story_id: str, session_id: str, request: Request, file: UploadFile = File(...), scope: str = Form("session")) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        if scope not in {"turn", "session", "story", "project"}:
            raise ValueError("附件作用域无效。")
        content = await file.read()
        if len(content) > 8 * 1024 * 1024:
            raise ValueError("附件超过 8MB 限制。")
        from novelforge.services.document_parsing import parse_document_bytes
        from novelforge.workflows.creative_attachments import import_creative_documents

        document = await run_in_threadpool(parse_document_bytes, file.filename or "attachment.txt", content)
        attachments = await run_in_threadpool(import_creative_documents, name, story_id, session_id, [document], scope=scope)
        return _envelope({"attachment": attachments[0] if attachments else None, "warnings": document.warnings}, request)

    @app.patch(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}")
    async def update_session(project_id: str, story_id: str, session_id: str, payload: UpdateSessionRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        updates = {key: value for key, value in payload.model_dump().items() if value is not None}
        session = await run_in_threadpool(memory.update_creative_session, name, session_id, updates, story_id=story_id)
        return _envelope({"session": session}, request)

    @app.delete(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}")
    async def archive_session(project_id: str, story_id: str, session_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        session = await run_in_threadpool(memory.update_creative_session, name, session_id, {"status": "archived"}, story_id=story_id)
        return _envelope({"session": session, "archived": True}, request)

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/actions")
    async def list_session_actions(project_id: str, story_id: str, session_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        return _envelope({"actions": await run_in_threadpool(memory.list_creative_actions, name, story_id, session_id)}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/actions/plan", status_code=status.HTTP_201_CREATED)
    async def plan_session_action(project_id: str, story_id: str, session_id: str, payload: PlanActionRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        from novelforge.workflows.creative_actions import plan_creative_action

        action = await run_in_threadpool(plan_creative_action, name, story_id, session_id, payload.request, idempotency_key=payload.idempotency_key or request.headers.get("idempotency-key", ""))
        return _envelope({"action": action}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/actions/{{action_id}}/execute")
    async def execute_session_action(project_id: str, story_id: str, session_id: str, action_id: str, payload: ExecuteActionRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        from novelforge.workflows.creative_actions import execute_creative_action

        action = await run_in_threadpool(execute_creative_action, name, action_id, confirmed=payload.confirmed)
        return _envelope({"action": action}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/actions/{{action_id}}/cancel")
    async def cancel_session_action(project_id: str, story_id: str, session_id: str, action_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        from novelforge.workflows.creative_actions import cancel_creative_action

        action = await run_in_threadpool(cancel_creative_action, name, action_id)
        return _envelope({"action": action}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/actions/{{action_id}}/undo")
    async def undo_session_action(project_id: str, story_id: str, session_id: str, action_id: str, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        _story(name, story_id)
        from novelforge.workflows.creative_actions import undo_creative_action

        action = await run_in_threadpool(undo_creative_action, name, action_id, idempotency_key=request.headers.get("idempotency-key", ""))
        return _envelope({"action": action}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/fragments/accept")
    async def accept_fragment(project_id: str, story_id: str, session_id: str, payload: FragmentActionRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        saved = await run_in_threadpool(memory.accept_creative_fragment, name, session_id, payload.fragment_id, story_id=story_id)
        return _envelope({"fragment": saved}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/fragments/select")
    async def select_fragment(project_id: str, story_id: str, session_id: str, payload: FragmentActionRequest, request: Request) -> dict[str, Any]:
        name = _resolve_project_name(project_id)
        saved = await run_in_threadpool(memory.select_creative_fragment_variant, name, session_id, payload.fragment_id, story_id=story_id)
        return _envelope({"fragment": saved}, request)

    @app.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/sessions/{{session_id}}/turns/stream")
    async def generate_turn_stream(project_id: str, story_id: str, session_id: str, payload: GenerateTurnRequest, request: Request):
        name = _resolve_project_name(project_id)
        _story(name, story_id)

        def worker(emit: Callable[[str, Any], None]) -> dict[str, Any]:
            result = generate_writing_fragment(
                name,
                story_id,
                session_id,
                payload.user_message,
                action_type=payload.action_type,
                word_count=payload.word_count,
                branch_from_fragment_id=payload.branch_from_fragment_id,
                stream_callback=lambda text: emit("delta", {"text": str(text or "")}),
            )
            return result

        return StreamingResponse(
            _threaded_stream(worker),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/events")
    async def story_events(project_id: str, story_id: str, request: Request):
        name = _resolve_project_name(project_id)
        story = _story(name, story_id)

        async def events() -> AsyncIterator[str]:
            yield _sse("ready", {"story": story, "server_time": datetime.now(timezone.utc).isoformat()})
            yield _sse("done", {"reason": "snapshot"})

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.get(f"{API_PREFIX}/operations/demo-stream")
    async def demo_stream():
        async def events() -> AsyncIterator[str]:
            yield _sse("operation.started", {"operation_id": "demo", "status": "running"}, event_id="1")
            yield _sse("operation.delta", {"text": "SSE contract ready"}, event_id="2")
            yield _sse("operation.completed", {"operation_id": "demo", "status": "completed"}, event_id="3")

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.get(f"{API_PREFIX}/operations/{{operation_id}}")
    async def operation_detail(operation_id: str, request: Request) -> dict[str, Any]:
        snapshot = operation_registry.snapshot(operation_id)
        if snapshot is None:
            raise FileNotFoundError(f"操作不存在或已过期：{operation_id}")
        return _envelope(snapshot, request)

    @app.get(f"{API_PREFIX}/operations/{{operation_id}}/events")
    async def operation_events(operation_id: str, request: Request, after: int = 0) -> dict[str, Any]:
        snapshot = operation_registry.snapshot(operation_id)
        if snapshot is None:
            raise FileNotFoundError(f"操作不存在或已过期：{operation_id}")
        return _envelope({"operation_id": operation_id, "events": operation_registry.events_after(operation_id, after)}, request)

    @app.post(f"{API_PREFIX}/operations/{{operation_id}}/cancel")
    async def cancel_operation(operation_id: str, request: Request) -> dict[str, Any]:
        if not operation_registry.cancel(operation_id):
            raise ValueError(f"操作不存在或已结束：{operation_id}")
        return _envelope({"operation_id": operation_id, "status": "cancel_requested"}, request)

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if (frontend_dist / "index.html").exists():
        app.mount("/", SPAStaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


app = create_app()
