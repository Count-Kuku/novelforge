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


from ._helpers import (
    _envelope,
    _error_payload,
    _project_meta,
    _request_id,
    _resolve_project_name,
    _sse,
    _story,
    _threaded_stream,
)

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

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        """未分类异常的统一出口。

        前端 client 依赖 `{error:{code,message}}` 结构取错误文案；FastAPI 默认对未捕获
        异常返回 `{"detail":...}`，会让前端读不到 message 而显示笼统提示。这里统一成
        约定结构，同时落服务端日志保留堆栈，便于追踪真实缺陷（不静默吞错）。
        异常明细不外传，避免泄漏内部路径等实现信息。
        """
        LOGGER.exception("Unhandled API error: %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=_error_payload(request, "internal_error", "服务器处理请求时发生未预期的错误，请查看服务端日志。"),
        )

    from .routers.meta import router as meta_router
    app.include_router(meta_router)

    from .routers.content_works import router as content_works_router
    from .routers.ingestion import router as ingestion_router
    from .routers.sources_research import router as sources_research_router
    from .routers.knowledge import router as knowledge_router
    from .routers.projects_stories import router as projects_stories_router
    from .routers.structure import router as structure_router
    from .routers.discussions_sessions import router as discussions_sessions_router
    from .routers.operations import router as operations_router
    from .routers.story_reference_libraries import router as story_reference_libraries_router
    app.include_router(content_works_router)
    app.include_router(ingestion_router)
    app.include_router(sources_research_router)
    app.include_router(knowledge_router)
    app.include_router(projects_stories_router)
    app.include_router(structure_router)
    app.include_router(discussions_sessions_router)
    app.include_router(operations_router)
    app.include_router(story_reference_libraries_router)

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if (frontend_dist / "index.html").exists():
        app.mount("/", SPAStaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


app = create_app()
