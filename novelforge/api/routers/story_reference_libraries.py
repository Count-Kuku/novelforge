"""Reference library versions and story-local knowledge copy endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from starlette.concurrency import run_in_threadpool

from novelforge.services import memory

from .._helpers import API_PREFIX, _envelope, _resolve_project_name
from ..schemas import (
    ReferenceLibraryCreateRequest,
    ReferenceLibraryReleaseRequest,
    LegacyStoryLibraryMigrationRequest,
    StoryLibraryBindingRequest,
)

router = APIRouter()


@router.get(f"{API_PREFIX}/projects/{{project_id}}/reference-libraries")
async def list_libraries(project_id: str, request: Request, include_archived: bool = False) -> dict[str, Any]:
    project_name = _resolve_project_name(project_id)
    libraries = await run_in_threadpool(memory.list_reference_libraries, project_name, include_archived=include_archived)
    return _envelope({"libraries": libraries}, request)


@router.post(f"{API_PREFIX}/projects/{{project_id}}/reference-libraries", status_code=status.HTTP_201_CREATED)
async def create_library(project_id: str, payload: ReferenceLibraryCreateRequest, request: Request) -> dict[str, Any]:
    project_name = _resolve_project_name(project_id)
    library = await run_in_threadpool(
        memory.create_reference_library,
        project_name,
        payload.title,
        source_kind=payload.source_kind,
        source_id=payload.source_id,
    )
    return _envelope({"library": library}, request)


@router.post(f"{API_PREFIX}/projects/{{project_id}}/reference-libraries/{{library_id}}/archive")
async def archive_library(project_id: str, library_id: str, request: Request) -> dict[str, Any]:
    project_name = _resolve_project_name(project_id)
    archived = await run_in_threadpool(memory.archive_reference_library, project_name, library_id)
    return _envelope({"archived": bool(archived), "library_id": library_id}, request)


@router.get(f"{API_PREFIX}/projects/{{project_id}}/reference-libraries/{{library_id}}/releases")
async def list_releases(project_id: str, library_id: str, request: Request) -> dict[str, Any]:
    project_name = _resolve_project_name(project_id)
    releases = await run_in_threadpool(memory.list_reference_library_releases, project_name, library_id)
    return _envelope({"releases": releases}, request)


@router.post(f"{API_PREFIX}/projects/{{project_id}}/reference-libraries/{{library_id}}/releases", status_code=status.HTTP_201_CREATED)
async def create_release(project_id: str, library_id: str, payload: ReferenceLibraryReleaseRequest, request: Request) -> dict[str, Any]:
    project_name = _resolve_project_name(project_id)
    release = await run_in_threadpool(
        memory.create_reference_library_release,
        project_name,
        library_id,
        knowledge_ids=payload.knowledge_ids,
        release_id=payload.release_id,
        content_hash=payload.content_hash,
        manifest=payload.manifest,
    )
    return _envelope({"release": release}, request)


@router.get(f"{API_PREFIX}/projects/{{project_id}}/reference-libraries/{{library_id}}/releases/{{release_id}}/sources")
async def release_sources(
    project_id: str,
    library_id: str,
    release_id: str,
    request: Request,
    source_id: str | None = Query(default=None),
) -> dict[str, Any]:
    project_name = _resolve_project_name(project_id)
    library = await run_in_threadpool(memory.load_reference_library, project_name, library_id)
    release = await run_in_threadpool(memory.load_reference_library_release, project_name, release_id)
    if (
        library is None
        or str(library.get("project_name") or "") != project_name
        or release is None
        or str(release.get("library_id") or "") != library_id
    ):
        raise HTTPException(status_code=404, detail="资料版本不存在或不属于该资料库。")
    sources = await run_in_threadpool(
        memory.load_reference_library_release_sources,
        project_name,
        release_id,
        source_id=source_id,
    )
    return _envelope({"library_id": library_id, "release_id": release_id, "sources": sources}, request)


@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/reference-libraries")
async def list_story_bindings(
    project_id: str,
    story_id: str,
    request: Request,
    branch_id: str | None = Query(default=None),
    include_archived: bool = False,
) -> dict[str, Any]:
    project_name = _resolve_project_name(project_id)
    bindings = await run_in_threadpool(
        memory.list_story_library_bindings,
        project_name,
        story_id,
        branch_id=branch_id,
        include_archived=include_archived,
    )
    return _envelope({"bindings": bindings}, request)


@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/reference-libraries/{{library_id}}/bindings", status_code=status.HTTP_201_CREATED)
async def bind_story_library(
    project_id: str,
    story_id: str,
    library_id: str,
    payload: StoryLibraryBindingRequest,
    request: Request,
) -> dict[str, Any]:
    project_name = _resolve_project_name(project_id)
    binding = await run_in_threadpool(
        memory.bind_story_library,
        project_name,
        story_id,
        library_id,
        payload.release_id,
        branch_id=payload.branch_id,
        idempotency_key=payload.idempotency_key,
    )
    return _envelope({"binding": binding}, request)


@router.delete(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/reference-libraries/bindings/{{binding_id}}")
async def unbind_story_library(
    project_id: str,
    story_id: str,
    binding_id: str,
    request: Request,
    branch_id: str | None = Query(default=None),
) -> dict[str, Any]:
    project_name = _resolve_project_name(project_id)
    binding = await run_in_threadpool(
        memory.unbind_story_library,
        project_name,
        binding_id,
        story_id=story_id,
        branch_id=branch_id,
    )
    return _envelope({"binding": binding, "unbound": binding is not None}, request)


@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/reference-context")
async def story_reference_context(
    project_id: str,
    story_id: str,
    request: Request,
    branch_id: str | None = Query(default=None),
) -> dict[str, Any]:
    project_name = _resolve_project_name(project_id)
    context = await run_in_threadpool(memory.resolve_story_reference_context, project_name, story_id, branch_id=branch_id)
    return _envelope(context, request)


@router.get(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/legacy-reference-status")
async def legacy_reference_status(project_id: str, story_id: str, request: Request) -> dict[str, Any]:
    project_name = _resolve_project_name(project_id)
    result = await run_in_threadpool(memory.load_legacy_story_reference_status, project_name, story_id)
    return _envelope(result, request)


@router.post(f"{API_PREFIX}/projects/{{project_id}}/stories/{{story_id}}/legacy-reference-migration")
async def migrate_legacy_reference(
    project_id: str,
    story_id: str,
    payload: LegacyStoryLibraryMigrationRequest,
    request: Request,
) -> dict[str, Any]:
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="存量资料迁移需要明确确认。")
    selections = [item.model_dump() for item in payload.selections]
    if not selections and payload.library_id and payload.release_id:
        selections = [{"library_id": payload.library_id, "release_id": payload.release_id, "branch_id": payload.branch_id}]
    project_name = _resolve_project_name(project_id)
    binding = await run_in_threadpool(
        memory.migrate_legacy_story_libraries,
        project_name,
        story_id,
        selections,
    )
    return _envelope(binding, request)
