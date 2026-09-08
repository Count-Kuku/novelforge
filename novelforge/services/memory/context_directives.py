"""Context directives (导演注) and generation context snapshots."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from uuid import uuid4

from novelforge.core.schemas import ContextDirective
from novelforge.services import memory as _memory_api

from .asset_records import (
    _mark_asset_deleted_best_effort,
    _sync_asset_payload_to_db_best_effort,
    list_asset_payload_records,
)
from .project_registry import project_path

CONTEXT_DIRECTIVE_ASSET_TYPE = "context_directive"
GENERATION_CONTEXT_SNAPSHOT_ASSET_TYPE = "generation_context_snapshot"


def _validate_context_asset_key(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", normalized):
        raise ValueError(f"{label} 只能包含字母、数字、下划线和连字符，且长度不能超过 96。")
    return normalized


def _context_directive_record_story_id(scope: str, story_id: str | None) -> str | None:
    if str(scope or "").strip().lower() == "project":
        return None
    return _memory_api.normalize_story_id(str(story_id or "default"))


def _context_asset_path(
    project_name: str,
    asset_type: str,
    logical_key: str,
    story_id: str | None,
):
    if story_id is None:
        return project_path(project_name) / asset_type / f"{logical_key}.json"
    return _memory_api.story_path(project_name, story_id) / asset_type / f"{logical_key}.json"


def save_context_directive(
    project_name: str,
    directive: dict,
    *,
    story_id: str | None = None,
    branch_id: str | None = None,
) -> dict:
    raw = dict(directive or {})
    directive_id = _validate_context_asset_key(
        str(raw.get("directive_id") or f"directive_{uuid4().hex}"),
        "导演注 ID",
    )
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    raw["directive_id"] = directive_id
    raw["created_at"] = str(raw.get("created_at") or now)
    raw["updated_at"] = now
    normalized = ContextDirective.model_validate(raw).model_dump()
    normalized["content"] = str(normalized.get("content") or "").strip()
    normalized["name"] = str(normalized.get("name") or "").strip()
    if not normalized["content"]:
        raise ValueError("导演注内容不能为空。")
    if not normalized["name"]:
        normalized["name"] = str(normalized["content"]).splitlines()[0][:48] or "未命名导演注"

    if branch_id:
        if str(normalized.get("scope") or "story") == "project":
            raise ValueError("分支不能修改项目级导演注。")
        target_story_id = _memory_api.normalize_story_id(str(story_id or normalized.get("story_id") or "default"))
        # The default branch is the existing story scope. Persisting its
        # one-shot consumption in a branch overlay would make the ordinary
        # story asset stale and leave the directive apparently unconsumed.
        if str(branch_id) == _memory_api.default_branch_id(target_story_id):
            branch_id = None
        if branch_id:
            normalized["story_id"] = target_story_id
            configuration = _memory_api.load_effective_story_branch_configuration(
                project_name, target_story_id, branch_id
            )
            directives = [
                dict(item) for item in (configuration.get("context_directives") or [])
                if isinstance(item, dict) and str(item.get("directive_id") or "") != directive_id
            ]
            directives.append(normalized)
            _memory_api.save_story_branch_configuration(
                project_name, target_story_id, branch_id, {"context_directives": directives}
            )
            return normalized

    record_story_id = _context_directive_record_story_id(normalized["scope"], story_id or normalized.get("story_id"))
    normalized["story_id"] = record_story_id
    path = _context_asset_path(
        project_name,
        CONTEXT_DIRECTIVE_ASSET_TYPE,
        directive_id,
        record_story_id,
    )
    asset_id = _sync_asset_payload_to_db_best_effort(
        project_name,
        path,
        asset_type=CONTEXT_DIRECTIVE_ASSET_TYPE,
        logical_key=directive_id,
        story_id=record_story_id,
        title=str(normalized.get("name") or "导演注"),
        payload=normalized,
        source_kind="internal",
        metadata={
            "scope": normalized["scope"],
            "placement": normalized["placement"],
            "capabilities": normalized["capabilities"],
        },
    )
    if not asset_id:
        raise RuntimeError("导演注未能写入项目数据库。")
    return normalized


def load_context_directives(project_name: str, story_id: str = "default") -> list[dict]:
    target_story_id = _memory_api.normalize_story_id(story_id)
    directives: list[dict] = []
    records = list_asset_payload_records(project_name, asset_type=CONTEXT_DIRECTIVE_ASSET_TYPE)
    for record in records:
        record_story_id = str(record.get("story_id") or "").strip() or None
        if record_story_id not in {None, target_story_id}:
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        try:
            directive = ContextDirective.model_validate(payload).model_dump()
        except Exception as exc:
            logging.getLogger("novelforge.storage").warning(
                "Skipping invalid context directive %s: %s",
                record.get("logical_key"),
                exc,
            )
            continue
        if (directive["scope"] == "project") != (record_story_id is None):
            logging.getLogger("novelforge.storage").warning(
                "Skipping context directive with mismatched scope and owner: %s",
                record.get("logical_key"),
            )
            continue
        directive["story_id"] = record_story_id
        directives.append(directive)
    directives.sort(
        key=lambda item: (
            0 if item.get("scope") == "project" else 1,
            -int(item.get("priority") or 0),
            str(item.get("updated_at") or ""),
            str(item.get("directive_id") or ""),
        )
    )
    return directives


def _directive_not_expired(expires_at: str | None, now: datetime) -> bool:
    text = str(expires_at or "").strip()
    if not text:
        return True
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed > now
    except ValueError:
        return False


def load_effective_context_directives(
    project_name: str,
    story_id: str = "default",
    *,
    capability: str = "",
    chapter_no: int | None = None,
    branch_id: str | None = None,
) -> list[dict]:
    now = datetime.now(timezone.utc)
    normalized_capability = str(capability or "").strip()
    effective: list[dict] = []
    if branch_id and str(branch_id) == _memory_api.default_branch_id(story_id):
        branch_id = None
    if branch_id:
        configuration = _memory_api.load_effective_story_branch_configuration(project_name, story_id, branch_id)
        source_directives = configuration.get("context_directives") or []
    else:
        source_directives = load_context_directives(project_name, story_id)
    for directive in source_directives:
        if not directive.get("enabled", True):
            continue
        remaining_uses = directive.get("remaining_uses")
        if remaining_uses is not None and int(remaining_uses) <= 0:
            continue
        if not _directive_not_expired(directive.get("expires_at"), now):
            continue
        capabilities = [str(value).strip() for value in directive.get("capabilities", []) if str(value).strip()]
        if capabilities and normalized_capability and normalized_capability not in capabilities:
            continue
        scope = str(directive.get("scope") or "story")
        if scope == "chapter":
            if chapter_no is None:
                continue
            start = directive.get("chapter_start")
            end = directive.get("chapter_end")
            if start is not None and chapter_no < int(start):
                continue
            if end is not None and chapter_no > int(end):
                continue
        effective.append(directive)
    return effective


def delete_context_directive(
    project_name: str,
    directive_id: str,
    *,
    story_id: str = "default",
    branch_id: str | None = None,
) -> bool:
    target_id = str(directive_id or "").strip()
    if not target_id:
        return False
    if branch_id and str(branch_id) == _memory_api.default_branch_id(story_id):
        branch_id = None
    if branch_id:
        configuration = _memory_api.load_effective_story_branch_configuration(project_name, story_id, branch_id)
        directives = [dict(item) for item in (configuration.get("context_directives") or []) if isinstance(item, dict)]
    else:
        directives = load_context_directives(project_name, story_id)
    for directive in directives:
        if str(directive.get("directive_id") or "") != target_id:
            continue
        if branch_id:
            remaining = [item for item in directives if str(item.get("directive_id") or "") != target_id]
            _memory_api.save_story_branch_configuration(
                project_name, story_id, branch_id, {"context_directives": remaining}
            )
            return True
        record_story_id = directive.get("story_id")
        _mark_asset_deleted_best_effort(
            project_name,
            asset_type=CONTEXT_DIRECTIVE_ASSET_TYPE,
            logical_key=target_id,
            story_id=record_story_id,
        )
        return True
    return False


def consume_context_directives(
    project_name: str,
    story_id: str,
    directive_ids: list[str],
    branch_id: str | None = None,
) -> list[dict]:
    target_ids = {str(value or "").strip() for value in directive_ids if str(value or "").strip()}
    if not target_ids:
        return []
    consumed: list[dict] = []
    if branch_id and str(branch_id) == _memory_api.default_branch_id(story_id):
        branch_id = None
    if branch_id:
        configuration = _memory_api.load_effective_story_branch_configuration(project_name, story_id, branch_id)
        source_directives = [dict(item) for item in (configuration.get("context_directives") or []) if isinstance(item, dict)]
    else:
        source_directives = load_context_directives(project_name, story_id)
    for directive in source_directives:
        if str(directive.get("directive_id") or "") not in target_ids:
            continue
        remaining_uses = directive.get("remaining_uses")
        if remaining_uses is None or int(remaining_uses) <= 0:
            continue
        updated = dict(directive)
        updated["remaining_uses"] = max(int(remaining_uses) - 1, 0)
        if updated["remaining_uses"] == 0:
            updated["enabled"] = False
        consumed.append(save_context_directive(
            project_name,
            updated,
            story_id=directive.get("story_id"),
            branch_id=branch_id,
        ))
    return consumed


def save_generation_context_snapshot(
    project_name: str,
    story_id: str,
    payload: dict,
) -> str:
    normalized_story_id = _memory_api.normalize_story_id(story_id)
    snapshot = dict(payload or {})
    fingerprint = str(snapshot.get("fingerprint") or "").strip()
    assembly_id = _validate_context_asset_key(
        str(snapshot.get("assembly_id") or f"assembly_{uuid4().hex}"),
        "上下文装配 ID",
    )
    logical_key = f"{assembly_id}_{fingerprint[:12]}" if fingerprint else assembly_id
    path = _context_asset_path(
        project_name,
        GENERATION_CONTEXT_SNAPSHOT_ASSET_TYPE,
        logical_key,
        normalized_story_id,
    )
    asset_id = _sync_asset_payload_to_db_best_effort(
        project_name,
        path,
        asset_type=GENERATION_CONTEXT_SNAPSHOT_ASSET_TYPE,
        logical_key=logical_key,
        story_id=normalized_story_id,
        title=f"生成上下文 {snapshot.get('capability') or ''} {snapshot.get('chapter_no') or ''}".strip(),
        payload=snapshot,
        source_kind="generation",
        source_ref=fingerprint or None,
        metadata={
            "capability": snapshot.get("capability"),
            "chapter_no": snapshot.get("chapter_no"),
            "fingerprint": fingerprint,
        },
    )
    if not asset_id:
        raise RuntimeError("生成上下文快照未能写入项目数据库。")
    return logical_key
