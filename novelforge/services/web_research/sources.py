"""Import fetched web pages through the existing retrieval-source facade."""

from __future__ import annotations

import hashlib
import json
from urllib.parse import urlsplit
from uuid import uuid4

from novelforge.core.schemas import FetchedWebPage
from novelforge.services.memory import retrieval_sources_path
from novelforge.services.retrieval import (
    ingest_external_source_file,
    rebuild_retrieval_assets,
)


def _web_source_name(url: str, namespace: str) -> str:
    host = str(urlsplit(url).hostname or "web").replace(".", "_")
    digest = hashlib.sha256(f"{namespace}:{url}".encode("utf-8")).hexdigest()[:20]
    return f"web_{host}_{digest}"[:120]


def _atomic_write_json(target, payload: dict) -> None:
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()


def import_fetched_web_pages(
    project_name: str,
    pages: list[FetchedWebPage | dict],
    *,
    query: str,
    provider: str,
    scope: str = "reference",
    authority: str = "unknown",
    build_vectors: bool = True,
    rebuild_assets: bool = True,
    extra_metadata: dict | None = None,
) -> list[dict]:
    """Save several pages and rebuild retrieval assets once after the batch."""

    if scope not in {"project", "canon", "reference"}:
        raise ValueError(f"不支持的网络资料范围：{scope}")
    if authority not in {"official", "curated", "community", "unknown"}:
        raise ValueError(f"不支持的网络资料可信度：{authority}")
    imported: list[dict] = []
    seen_urls: set[str] = set()
    metadata_overrides = dict(extra_metadata) if isinstance(extra_metadata, dict) else {}
    research_task_id = str(metadata_overrides.get("research_task_id") or "").strip()
    manual_story_id = str(metadata_overrides.get("story_id") or "").strip()
    namespace = research_task_id or f"manual:{manual_story_id or 'project'}"
    for raw_page in pages:
        page = raw_page if isinstance(raw_page, FetchedWebPage) else FetchedWebPage.model_validate(raw_page)
        actual_content_hash = hashlib.sha256(page.text.encode("utf-8")).hexdigest()
        if page.content_hash != actual_content_hash:
            page = page.model_copy(update={"content_hash": actual_content_hash})
        if page.final_url in seen_urls:
            continue
        seen_urls.add(page.final_url)
        source_name = _web_source_name(page.final_url, namespace)
        payload = {
            "source_type": "web_source",
            "scope": scope,
            "title": page.title[:500],
            "content": page.text,
            "tags": [item for item in ["web", str(provider or "")[:80], authority] if item],
            "metadata": {
                **metadata_overrides,
                "authority": authority,
                "description": page.description[:2000],
                "source_origin": page.final_url,
                "requested_url": page.requested_url,
                "canonical_url": page.final_url,
                "domain": str(urlsplit(page.final_url).hostname or ""),
                "search_query": str(query or "")[:400],
                "search_provider": str(provider or "")[:80],
                "fetched_at": page.fetched_at,
                "content_hash": page.content_hash,
                "http_status": page.status_code,
                "content_type": page.content_type,
                "web_metadata": page.metadata,
                "source_snapshot_namespace": namespace,
            },
        }
        relative_path = ingest_external_source_file(
            project_name,
            source_name,
            json.dumps(payload, ensure_ascii=False, indent=2),
            overwrite=True,
        )
        imported.append(
            {
                "source_name": source_name,
                "relative_path": relative_path,
                "title": page.title[:500],
                "url": page.final_url,
                "content_hash": page.content_hash,
                "authority": authority,
            }
        )
    if imported and rebuild_assets:
        rebuild_retrieval_assets(project_name, build_vectors=build_vectors)
    return imported


def load_imported_web_page(project_name: str, relative_path: str) -> FetchedWebPage:
    """Rehydrate a fetched page from its durable external-source asset."""

    source_root = retrieval_sources_path(project_name).resolve()
    target = (source_root / str(relative_path or "")).resolve()
    if source_root != target and source_root not in target.parents:
        raise ValueError("网络资料路径超出项目来源目录。")
    if not target.is_file():
        raise FileNotFoundError(f"网络资料文件不存在：{relative_path}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("网络资料文件不是结构化来源。")
    metadata = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
    content = str(payload.get("content") or "")
    stored_content_hash = str(metadata.get("content_hash") or "")
    actual_content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if stored_content_hash and stored_content_hash != actual_content_hash:
        raise ValueError("网络资料正文与持久化内容哈希不一致。")
    return FetchedWebPage(
        requested_url=str(metadata.get("requested_url") or metadata.get("canonical_url") or ""),
        final_url=str(metadata.get("canonical_url") or metadata.get("source_origin") or ""),
        title=str(payload.get("title") or "网络资料")[:500],
        description=str(metadata.get("description") or ""),
        text=content,
        content_hash=stored_content_hash or actual_content_hash,
        fetched_at=str(metadata.get("fetched_at") or ""),
        status_code=int(metadata.get("http_status") or 200),
        content_type=str(metadata.get("content_type") or "text/plain"),
        byte_count=len(content.encode("utf-8")),
        metadata={
            **dict(metadata.get("web_metadata") or {}),
            "source_relative_path": str(relative_path or ""),
            "research_task_id": str(metadata.get("research_task_id") or ""),
        },
    )


def set_imported_web_pages_retrieval_status(
    project_name: str,
    relative_paths: list[str],
    *,
    status: str,
    build_vectors: bool = True,
    research_task_id: str = "",
) -> int:
    """Activate or quarantine durable web-source assets, then rebuild once."""

    if status not in {"active", "quarantine"}:
        raise ValueError("网络资料检索状态必须是 active 或 quarantine。")
    source_root = retrieval_sources_path(project_name).resolve()
    changed = 0
    for relative_path in dict.fromkeys(str(item or "") for item in relative_paths):
        target = (source_root / relative_path).resolve()
        if source_root != target and source_root not in target.parents:
            raise ValueError("网络资料路径超出项目来源目录。")
        if not target.is_file() or target.suffix.lower() != ".json":
            continue
        payload = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        metadata = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
        source_task_id = str(metadata.get("research_task_id") or "")
        if research_task_id and source_task_id != str(research_task_id):
            continue
        if not research_task_id and source_task_id:
            continue
        if metadata.get("retrieval_status") == status:
            continue
        payload["metadata"] = {**metadata, "retrieval_status": status}
        _atomic_write_json(target, payload)
        changed += 1
    if changed:
        rebuild_retrieval_assets(project_name, build_vectors=build_vectors)
    return changed


def get_imported_web_pages_retrieval_statuses(
    project_name: str,
    relative_paths: list[str],
    *,
    research_task_id: str = "",
) -> dict[str, str]:
    """Read current task-owned source status without changing retrieval assets."""

    source_root = retrieval_sources_path(project_name).resolve()
    statuses: dict[str, str] = {}
    for relative_path in dict.fromkeys(str(item or "") for item in relative_paths):
        target = (source_root / relative_path).resolve()
        if source_root != target and source_root not in target.parents:
            raise ValueError("网络资料路径超出项目来源目录。")
        if not target.is_file() or target.suffix.lower() != ".json":
            continue
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict) else {}
        source_task_id = str(metadata.get("research_task_id") or "")
        if research_task_id and source_task_id != str(research_task_id):
            continue
        if not research_task_id and source_task_id:
            continue
        statuses[relative_path] = str(metadata.get("retrieval_status") or "active")
    return statuses


def delete_imported_web_pages(
    project_name: str,
    relative_paths: list[str],
    *,
    research_task_id: str,
    build_vectors: bool = True,
) -> int:
    """Delete only source snapshots owned by one research task."""

    clean_task_id = str(research_task_id or "").strip()
    if not clean_task_id:
        raise ValueError("删除网络资料必须提供研究任务 ID。")
    source_root = retrieval_sources_path(project_name).resolve()
    deleted = 0
    for relative_path in dict.fromkeys(str(item or "") for item in relative_paths):
        target = (source_root / relative_path).resolve()
        if source_root != target and source_root not in target.parents:
            raise ValueError("网络资料路径超出项目来源目录。")
        if not target.is_file() or target.suffix.lower() != ".json":
            continue
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict) else {}
        if str(metadata.get("research_task_id") or "") != clean_task_id:
            continue
        target.unlink()
        deleted += 1
    if deleted:
        rebuild_retrieval_assets(project_name, build_vectors=build_vectors)
    return deleted
