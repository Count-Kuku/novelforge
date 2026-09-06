"""Health, version, capabilities, settings, usage, bootstrap and project routes."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from starlette.concurrency import run_in_threadpool

from novelforge.services import memory
from novelforge.services import project_manager
from storage.repositories.projects import upsert_project_meta
from storage.schema import CURRENT_SCHEMA_VERSION

from ..schemas import (
    ActiveModelProfileRequest,
    AutoConfigurationRequest,
    CreateProjectRequest,
    DiscoverModelsRequest,
    ModelProfileRequest,
    PromptOptionsUpdateRequest,
    RulesUpdateRequest,
)
from .._helpers import (
    API_PREFIX,
    LOGGER,
    _envelope,
    _project_meta,
    _resolve_project_name,
    _story,
)

router = APIRouter()


@router.get("/health/live", include_in_schema=False)
async def live() -> dict[str, Any]:
    return {"status": "ok", "service": "novelforge-api", "time": datetime.now(timezone.utc).isoformat()}


@router.get(f"{API_PREFIX}/health/live")
async def api_live(request: Request) -> dict[str, Any]:
    return _envelope({"status": "ok", "service": "novelforge-api"}, request)


@router.get(f"{API_PREFIX}/health/ready")
async def ready(request: Request) -> dict[str, Any]:
    return _envelope({"status": "ready", "schema_version": CURRENT_SCHEMA_VERSION, "dispatchers": [item.status() for item in getattr(request.app.state, "dispatchers", [])]}, request)


@router.get(f"{API_PREFIX}/version")
async def version(request: Request) -> dict[str, Any]:
    return _envelope({"version": "0.7.1", "api_version": "v1", "schema_version": CURRENT_SCHEMA_VERSION}, request)


@router.get(f"{API_PREFIX}/capabilities")
async def capabilities(request: Request) -> dict[str, Any]:
    """Expose read-only provider readiness for settings and task guards."""
    from novelforge.services.capabilities import build_default_capability_registry

    return _envelope({"capabilities": build_default_capability_registry().snapshot()}, request)


@router.get(f"{API_PREFIX}/settings/developer")
async def developer_settings(request: Request) -> dict[str, Any]:
    """Expose developer projections only when enabled by the server environment."""
    enabled = str(os.getenv("NOVELFORGE_DEVELOPER_MODE") or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return _envelope({"enabled": enabled, "projections": ["raw_json", "retrieval_trace", "operation_payload"] if enabled else []}, request)


@router.get(f"{API_PREFIX}/usage")
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


@router.get(f"{API_PREFIX}/usage/breakdown")
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


@router.get(f"{API_PREFIX}/settings/models")
async def model_profiles(request: Request) -> dict[str, Any]:
    profiles_payload = await run_in_threadpool(memory.load_llm_profiles)
    safe_profiles: list[dict[str, Any]] = []
    for profile in profiles_payload.get("profiles", []):
        safe_profiles.append({
            key: value for key, value in dict(profile).items()
            if key not in {"api_key", "embedding_api_key", "secret", "embedding_secret"}
        })
    return _envelope({"active_profile_id": profiles_payload.get("active_profile_id", ""), "profiles": safe_profiles}, request)


@router.post(f"{API_PREFIX}/settings/models/discover")
async def discover_models(payload: DiscoverModelsRequest, request: Request) -> dict[str, Any]:
    from novelforge.services.model_catalog import discover_openai_compatible_models

    try:
        catalog = await run_in_threadpool(
            discover_openai_compatible_models,
            payload.base_url,
            payload.api_key,
            provider_type=payload.provider_type,
        )
    except RuntimeError as exc:
        return _error_payload(str(exc), request=request)
    return _envelope(catalog, request)


@router.put(f"{API_PREFIX}/settings/models")
async def update_model_profile(payload: ModelProfileRequest, request: Request) -> dict[str, Any]:
    profile = payload.model_dump()
    profile["id"] = profile.pop("profile_id", "")
    updated = await run_in_threadpool(memory.upsert_llm_profile, profile)
    safe = {key: value for key, value in dict(updated).items() if key not in {"api_key", "embedding_api_key", "secret", "embedding_secret"}}
    return _envelope({"profile": safe, "saved": True}, request)


@router.post(f"{API_PREFIX}/settings/models/active")
async def activate_model_profile(payload: ActiveModelProfileRequest, request: Request) -> dict[str, Any]:
    active = await run_in_threadpool(memory.set_active_llm_profile, payload.profile_id)
    safe = {key: value for key, value in dict(active).items() if key not in {"api_key", "embedding_api_key", "secret", "embedding_secret"}}
    return _envelope({"profile": safe, "active_profile_id": payload.profile_id}, request)


@router.get(f"{API_PREFIX}/settings/rules")
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


@router.put(f"{API_PREFIX}/settings/rules/{{scope}}")
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


@router.get(f"{API_PREFIX}/settings/prompt-options")
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


@router.put(f"{API_PREFIX}/settings/prompt-options/{{layer}}")
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


@router.get(f"{API_PREFIX}/settings/auto-configuration")
async def auto_configuration(request: Request, operation: str = "chapter_write", project_id: str | None = None, story_id: str = "default") -> dict[str, Any]:
    if not project_id:
        return _envelope({"state": {}, "revisions": []}, request)
    project_name = _resolve_project_name(project_id)
    from novelforge.services.automatic_configuration import load_automatic_configuration, list_automatic_configuration_revisions
    return _envelope({
        "state": await run_in_threadpool(load_automatic_configuration, project_name, story_id, operation),
        "revisions": await run_in_threadpool(list_automatic_configuration_revisions, project_name, story_id, operation),
    }, request)


@router.post(f"{API_PREFIX}/settings/auto-configuration")
async def configure_auto_configuration(payload: AutoConfigurationRequest, request: Request, project_id: str | None = None, story_id: str = "default") -> dict[str, Any]:
    if not project_id:
        raise ValueError("自动配置需要项目上下文。")
    project_name = _resolve_project_name(project_id)
    from novelforge.services.automatic_configuration import configure_operation_automatically
    result = await run_in_threadpool(configure_operation_automatically, project_name, story_id, payload.operation, goal=payload.goal, source_chars=payload.source_chars, locked_fields=payload.locked_fields)
    return _envelope(result, request)


@router.get(f"{API_PREFIX}/bootstrap")
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


@router.get(f"{API_PREFIX}/projects")
async def projects(request: Request) -> dict[str, Any]:
    return await bootstrap(request)


@router.post(f"{API_PREFIX}/projects", status_code=status.HTTP_201_CREATED)
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


@router.get(f"{API_PREFIX}/projects/{{project_id}}")
async def project_detail(project_id: str, request: Request) -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    meta = _project_meta(name)
    stories = memory.list_stories(name)
    return _envelope({"project": meta, "stories": stories}, request)


@router.get(f"{API_PREFIX}/projects/{{project_id}}/summary")
async def project_summary(project_id: str, request: Request, story_id: str = "default") -> dict[str, Any]:
    name = _resolve_project_name(project_id)
    _story(name, story_id)
    summary = await run_in_threadpool(project_manager.get_project_summary, name, story_id)
    return _envelope(summary, request)
