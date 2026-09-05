"""Asset file and asset payload best-effort persistence for projects."""

from __future__ import annotations

import hashlib
from pathlib import Path

from storage.repositories import (
    list_asset_file_rows,
    list_asset_payload_rows,
    load_asset_payload,
    mark_asset_deleted,
    register_asset_file,
    upsert_asset_payload,
)

from .db_availability import (
    _load_project_db_best_effort,
    _mutate_project_db_best_effort,
)
from .project_registry import project_path


def _resolve_asset_file_record(project_name: str, file: Path, *, story_id: str | None, asset_type: str, logical_key: str):
    """Resolve the storage-side asset identity for a file-backed payload."""

    root = project_path(project_name).resolve()
    resolved_file = file.resolve()
    relative_path = str(resolved_file.relative_to(root)).replace("\\", "/")
    content_hash = ""
    if resolved_file.exists() and resolved_file.is_file():
        content_hash = hashlib.sha256(resolved_file.read_bytes()).hexdigest()
    asset_id_source = f"{story_id or 'project'}:{asset_type}:{logical_key}"
    asset_id = "asset_" + hashlib.sha256(asset_id_source.encode("utf-8")).hexdigest()[:24]
    return root, resolved_file, relative_path, content_hash, asset_id


def _register_asset_file_best_effort(
    project_name: str,
    file: Path,
    *,
    asset_type: str,
    logical_key: str,
    story_id: str | None = None,
    title: str = "",
    mime_type: str | None = None,
    source_kind: str | None = None,
    source_ref: str | None = None,
    metadata: dict | None = None,
) -> str | None:
    def action(conn):
        _, _, relative_path, content_hash, asset_id = _resolve_asset_file_record(
            project_name, file, story_id=story_id, asset_type=asset_type, logical_key=logical_key
        )
        register_asset_file(
            conn,
            asset_id=asset_id,
            story_id=story_id,
            asset_type=asset_type,
            logical_key=logical_key,
            title=title,
            relative_path=relative_path,
            content_hash=content_hash or None,
            mime_type=mime_type,
            source_kind=source_kind,
            source_ref=source_ref,
            metadata=metadata,
        )

    return _mutate_project_db_best_effort(
        project_name,
        action,
        action_label="register asset file",
    )


def register_asset_file_record(
    project_name: str,
    file: Path,
    *,
    asset_type: str,
    logical_key: str,
    story_id: str | None = None,
    title: str = "",
    mime_type: str | None = None,
    source_kind: str | None = None,
    source_ref: str | None = None,
    metadata: dict | None = None,
) -> None:
    _register_asset_file_best_effort(
        project_name,
        file,
        asset_type=asset_type,
        logical_key=logical_key,
        story_id=story_id,
        title=title,
        mime_type=mime_type,
        source_kind=source_kind,
        source_ref=source_ref,
        metadata=metadata,
    )


def _sync_asset_payload_to_db_best_effort(
    project_name: str,
    file: Path,
    *,
    asset_type: str,
    logical_key: str,
    payload,
    story_id: str | None = None,
    title: str = "",
    mime_type: str = "application/json",
    source_kind: str | None = None,
    source_ref: str | None = None,
    metadata: dict | None = None,
) -> str | None:
    def action(conn):
        _, _, relative_path, content_hash, asset_id = _resolve_asset_file_record(
            project_name, file, story_id=story_id, asset_type=asset_type, logical_key=logical_key
        )
        asset_record = register_asset_file(
            conn,
            asset_id=asset_id,
            story_id=story_id,
            asset_type=asset_type,
            logical_key=logical_key,
            title=title,
            relative_path=relative_path,
            content_hash=content_hash or None,
            mime_type=mime_type,
            source_kind=source_kind,
            source_ref=source_ref,
            metadata=metadata,
        )
        actual_asset_id = str(asset_record.get("asset_id") or asset_id)
        upsert_asset_payload(
            conn,
            asset_type=asset_type,
            logical_key=logical_key,
            story_id=story_id,
            payload=payload,
        )
        return actual_asset_id

    return _mutate_project_db_best_effort(
        project_name,
        action,
        action_label="sync asset payload to project database",
    )


def _load_asset_payload_from_db_best_effort(
    project_name: str,
    *,
    asset_type: str,
    logical_key: str,
    story_id: str | None = None,
):
    return _load_project_db_best_effort(
        project_name,
        lambda conn: load_asset_payload(
            conn,
            asset_type=asset_type,
            logical_key=logical_key,
            story_id=story_id,
        ),
        action_label="load asset payload from project database",
        subject=f"{project_name}/{asset_type}/{logical_key}",
    )


def list_asset_records(
    project_name: str,
    *,
    asset_type: str | None = None,
    story_id: str | None = None,
    include_deleted: bool = False,
) -> list[dict]:
    return _load_project_db_best_effort(
        project_name,
        lambda conn: list_asset_file_rows(
            conn,
            asset_type=asset_type,
            story_id=story_id,
            include_deleted=include_deleted,
        ),
        action_label="list asset records",
    ) or []


def list_asset_payload_records(
    project_name: str,
    *,
    asset_type: str | None = None,
    story_id: str | None = None,
    include_deleted: bool = False,
) -> list[dict]:
    return _load_project_db_best_effort(
        project_name,
        lambda conn: list_asset_payload_rows(
            conn,
            asset_type=asset_type,
            story_id=story_id,
            include_deleted=include_deleted,
        ),
        action_label="list asset payload records",
    ) or []


def _asset_payload_exists(
    project_name: str,
    *,
    asset_type: str,
    logical_key: str,
    story_id: str | None = None,
) -> bool:
    for record in list_asset_payload_records(project_name, asset_type=asset_type, story_id=story_id):
        if str(record.get("logical_key") or "") == logical_key:
            return True
    return False


def _mark_asset_deleted_best_effort(
    project_name: str,
    *,
    asset_type: str,
    logical_key: str,
    story_id: str | None = None,
) -> None:
    _mutate_project_db_best_effort(
        project_name,
        lambda conn: mark_asset_deleted(
            conn,
            asset_type=asset_type,
            logical_key=logical_key,
            story_id=story_id,
        ),
        action_label="mark asset deleted",
        drain_mirrors=False,
    )


def mark_asset_deleted_record(
    project_name: str,
    *,
    asset_type: str,
    logical_key: str,
    story_id: str | None = None,
) -> None:
    _mark_asset_deleted_best_effort(
        project_name,
        asset_type=asset_type,
        logical_key=logical_key,
        story_id=story_id,
    )
