from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import PurePosixPath
from typing import Any

from .creative_sessions import clone_creative_session_rows


_CHAPTER_ASSET_TYPES = {
    "chapter_outline",
    "chapter_outline_metadata",
    "chapter_discussion",
    "chapter",
    "review_markdown",
    "review_json",
    "analysis_markdown",
    "evaluation_markdown",
    "evaluation_json",
    "workflow_run_snapshot",
    "generation_context_snapshot",
}

_DISCUSSION_ASSET_TYPES = {
    "creative_profile_discussion",
    "outline_discussion",
    "chapter_discussion",
    "volume_discussion",
    "arc_discussion",
}

_VOLUME_ARC_ASSET_TYPES = {
    "volume_outline",
    "volume_metadata",
    "volume_discussion",
    "arc_outline",
    "arc_metadata",
    "arc_discussion",
    "arc_chapter_plan",
}

_PATH_FIELD_NAMES = {
    "directory",
    "directories",
    "dir_path",
    "dir_paths",
    "file_path",
    "file_paths",
    "filepath",
    "filepaths",
    "path",
    "paths",
}


def _is_path_field(key: str) -> bool:
    snake_key = re.sub(r"(?<!^)(?=[A-Z])", "_", str(key or ""))
    snake_key = re.sub(r"[^a-zA-Z0-9]+", "_", snake_key).strip("_").lower()
    return (
        snake_key in _PATH_FIELD_NAMES
        or snake_key.endswith("_path")
        or snake_key.endswith("_paths")
    )


def _rewrite_story_path_string(
    value: str,
    *,
    source_story_id: str,
    target_story_id: str,
    explicit_path_field: bool,
) -> str:
    """Rewrite an exact story directory segment in path-like strings only.

    An explicit path field may contain spaces. Outside such a field, the value
    must look like a standalone path (no whitespace), which keeps prose such as
    ``see stories/source/chapter.md`` unchanged.
    """

    if not explicit_path_field and any(char.isspace() for char in value):
        return value
    pattern = re.compile(
        rf"(?P<prefix>^|[\\/])stories(?P<story_sep>[\\/])"
        rf"{re.escape(source_story_id)}(?P<tail_sep>[\\/])"
    )
    if not pattern.search(value):
        return value
    return pattern.sub(
        lambda match: (
            f"{match.group('prefix')}stories{match.group('story_sep')}"
            f"{target_story_id}{match.group('tail_sep')}"
        ),
        value,
    )


def _active_story_exists(conn: sqlite3.Connection, story_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM stories WHERE story_id = ? AND deleted_at IS NULL",
        (story_id,),
    ).fetchone() is not None


def _copy_run_id(conn: sqlite3.Connection, source_run_id: str, target_story_id: str) -> str:
    digest = hashlib.sha256(f"{target_story_id}:{source_run_id}".encode("utf-8")).hexdigest()[:10]
    safe_source = "".join(
        char if (char.isalnum() or char in {"_", "-", "."}) else "_"
        for char in source_run_id
    ).strip(".")
    safe_source = safe_source[:96] or "workflow_run"
    base = f"{safe_source}__copy_{digest}"
    candidate = base
    counter = 2
    while conn.execute("SELECT 1 FROM workflow_runs WHERE run_id = ?", (candidate,)).fetchone():
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def _rewrite_structured_value(
    value: Any,
    *,
    source_story_id: str,
    target_story_id: str,
    run_id_map: dict[str, str],
    asset_id_map: dict[str, str],
    _path_context: bool = False,
) -> Any:
    if isinstance(value, list):
        return [
            _rewrite_structured_value(
                item,
                source_story_id=source_story_id,
                target_story_id=target_story_id,
                run_id_map=run_id_map,
                asset_id_map=asset_id_map,
                _path_context=_path_context,
            )
            for item in value
        ]
    if isinstance(value, str):
        return _rewrite_story_path_string(
            value,
            source_story_id=source_story_id,
            target_story_id=target_story_id,
            explicit_path_field=_path_context,
        )
    if not isinstance(value, dict):
        return value

    rewritten: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key)
        nested = _rewrite_structured_value(
            raw_value,
            source_story_id=source_story_id,
            target_story_id=target_story_id,
            run_id_map=run_id_map,
            asset_id_map=asset_id_map,
            _path_context=_is_path_field(key),
        )
        if key == "story_id" and nested == source_story_id:
            nested = target_story_id
        elif key in {"run_id", "parent_run_id"} and isinstance(nested, str):
            nested = run_id_map.get(nested, nested)
        elif key.endswith("asset_id") and isinstance(nested, str):
            nested = asset_id_map.get(nested, nested)
        rewritten[key] = nested
    return rewritten


def _rewrite_json_text(
    raw: Any,
    *,
    source_story_id: str,
    target_story_id: str,
    run_id_map: dict[str, str],
    asset_id_map: dict[str, str],
) -> str:
    text = str(raw or "")
    try:
        parsed = json.loads(text)
    except Exception:
        return text
    rewritten = _rewrite_structured_value(
        parsed,
        source_story_id=source_story_id,
        target_story_id=target_story_id,
        run_id_map=run_id_map,
        asset_id_map=asset_id_map,
    )
    return json.dumps(rewritten, ensure_ascii=False, sort_keys=True)


def _asset_is_included(
    asset_type: str,
    *,
    include_discussions: bool,
    include_summaries: bool,
    include_chapters: bool,
) -> bool:
    if not include_chapters and asset_type in _CHAPTER_ASSET_TYPES:
        return False
    if not include_summaries and asset_type == "chapter_summaries":
        return False
    if not include_discussions and (
        asset_type in _DISCUSSION_ASSET_TYPES or asset_type in _VOLUME_ARC_ASSET_TYPES
    ):
        return False
    return True


def _target_relative_path(
    relative_path: str,
    *,
    source_story_id: str,
    target_story_id: str,
    source_run_id: str = "",
    target_run_id: str = "",
) -> str:
    normalized = str(relative_path or "").replace("\\", "/")
    source_path = PurePosixPath(normalized)
    source_parts = source_path.parts
    if (
        source_path.is_absolute()
        or any(part in {"", ".", ".."} or ":" in part for part in source_parts)
        or len(source_parts) < 3
        or source_parts[:2] != ("stories", source_story_id)
    ):
        raise ValueError(f"Story asset path is outside its story directory: {relative_path}")

    target_parts = ["stories", target_story_id, *source_parts[2:]]
    if (
        source_run_id
        and target_run_id
        and len(target_parts) >= 4
        and target_parts[-2] == "runs"
        and target_parts[-1] == f"{source_run_id}.json"
    ):
        target_parts[-1] = f"{target_run_id}.json"
    return PurePosixPath(*target_parts).as_posix()


def clone_story_storage_rows(
    conn: sqlite3.Connection,
    source_story_id: str,
    target_story_id: str,
    *,
    include_discussions: bool = True,
    include_summaries: bool = True,
    include_chapters: bool = True,
) -> dict:
    """Clone DB-only story assets and workflow history into a new story.

    The caller owns the surrounding transaction. IDs that are global primary
    keys are remapped so a copy never moves or overwrites records belonging to
    the source story.
    """

    source_story_id = str(source_story_id or "").strip()
    target_story_id = str(target_story_id or "").strip()
    if not source_story_id or not target_story_id:
        raise ValueError("Source and target story IDs are required.")
    if source_story_id == target_story_id:
        raise ValueError("Source and target story IDs must differ.")
    if not _active_story_exists(conn, source_story_id):
        raise ValueError(f"Source story does not exist: {source_story_id}")
    if not _active_story_exists(conn, target_story_id):
        raise ValueError(f"Target story does not exist: {target_story_id}")

    workflow_rows = []
    run_id_map: dict[str, str] = {}
    if include_chapters:
        workflow_rows = conn.execute(
            """
            SELECT run_id, workflow_type, status, parent_run_id, input_json,
                   output_json, error_json, started_at, finished_at
            FROM workflow_runs
            WHERE story_id = ?
            ORDER BY created_at, run_id
            """,
            (source_story_id,),
        ).fetchall()
        for row in workflow_rows:
            source_run_id = str(row["run_id"])
            run_id_map[source_run_id] = _copy_run_id(conn, source_run_id, target_story_id)

    asset_rows = conn.execute(
        """
        SELECT asset.asset_id, asset.asset_type, asset.logical_key, asset.title,
               asset.relative_path, asset.content_hash, asset.mime_type,
               asset.source_kind, asset.source_ref, asset.metadata_json,
               payload.payload_json
        FROM asset_files AS asset
        LEFT JOIN asset_payloads AS payload ON payload.asset_id = asset.asset_id
        WHERE asset.story_id = ? AND asset.deleted_at IS NULL
        ORDER BY asset.created_at, asset.asset_id
        """,
        (source_story_id,),
    ).fetchall()

    included_assets = [
        row
        for row in asset_rows
        if _asset_is_included(
            str(row["asset_type"]),
            include_discussions=include_discussions,
            include_summaries=include_summaries,
            include_chapters=include_chapters,
        )
    ]
    asset_id_map: dict[str, str] = {}
    for row in included_assets:
        source_asset_id = str(row["asset_id"])
        asset_type = str(row["asset_type"])
        source_logical_key = str(row["logical_key"])
        target_logical_key = (
            run_id_map.get(source_logical_key, source_logical_key)
            if asset_type == "workflow_run_snapshot"
            else source_logical_key
        )
        seed = f"{target_story_id}:{asset_type}:{target_logical_key}"
        asset_id_map[source_asset_id] = "asset_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]

    for row in included_assets:
        source_asset_id = str(row["asset_id"])
        target_asset_id = asset_id_map[source_asset_id]
        asset_type = str(row["asset_type"])
        source_logical_key = str(row["logical_key"])
        target_logical_key = (
            run_id_map.get(source_logical_key, source_logical_key)
            if asset_type == "workflow_run_snapshot"
            else source_logical_key
        )
        target_relative_path = _target_relative_path(
            str(row["relative_path"]),
            source_story_id=source_story_id,
            target_story_id=target_story_id,
            source_run_id=source_logical_key if asset_type == "workflow_run_snapshot" else "",
            target_run_id=target_logical_key if asset_type == "workflow_run_snapshot" else "",
        )
        metadata_json = _rewrite_json_text(
            row["metadata_json"],
            source_story_id=source_story_id,
            target_story_id=target_story_id,
            run_id_map=run_id_map,
            asset_id_map=asset_id_map,
        )
        conn.execute(
            """
            INSERT INTO asset_files (
                asset_id, story_id, asset_type, logical_key, title, relative_path,
                content_hash, mime_type, source_kind, source_ref, metadata_json,
                created_at, updated_at, deleted_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL
            )
            """,
            (
                target_asset_id,
                target_story_id,
                asset_type,
                target_logical_key,
                str(row["title"] or ""),
                target_relative_path,
                row["content_hash"],
                row["mime_type"],
                row["source_kind"],
                row["source_ref"],
                metadata_json,
            ),
        )
        if row["payload_json"] is not None:
            if asset_type == "generation_context_snapshot":
                # A context snapshot is an immutable record of the source
                # generation. Rewriting embedded story IDs would make its
                # persisted fingerprint inconsistent with the saved payload.
                payload_json = str(row["payload_json"])
            else:
                payload_json = _rewrite_json_text(
                    row["payload_json"],
                    source_story_id=source_story_id,
                    target_story_id=target_story_id,
                    run_id_map=run_id_map,
                    asset_id_map=asset_id_map,
                )
            conn.execute(
                """
                INSERT INTO asset_payloads (asset_id, payload_json, created_at, updated_at)
                VALUES (
                    ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                    strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                )
                """,
                (target_asset_id, payload_json),
            )

    for row in workflow_rows:
        source_run_id = str(row["run_id"])
        target_run_id = run_id_map[source_run_id]
        parent_run_id = str(row["parent_run_id"] or "")
        conn.execute(
            """
            INSERT INTO workflow_runs (
                run_id, story_id, workflow_type, status, parent_run_id,
                input_json, output_json, error_json, started_at, finished_at, created_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            )
            """,
            (
                target_run_id,
                target_story_id,
                str(row["workflow_type"] or "chapter_pipeline"),
                str(row["status"] or "unknown"),
                run_id_map.get(parent_run_id) if parent_run_id else None,
                _rewrite_json_text(
                    row["input_json"],
                    source_story_id=source_story_id,
                    target_story_id=target_story_id,
                    run_id_map=run_id_map,
                    asset_id_map=asset_id_map,
                ),
                _rewrite_json_text(
                    row["output_json"],
                    source_story_id=source_story_id,
                    target_story_id=target_story_id,
                    run_id_map=run_id_map,
                    asset_id_map=asset_id_map,
                ),
                _rewrite_json_text(
                    row["error_json"],
                    source_story_id=source_story_id,
                    target_story_id=target_story_id,
                    run_id_map=run_id_map,
                    asset_id_map=asset_id_map,
                ),
                row["started_at"],
                row["finished_at"],
            ),
        )
        steps = conn.execute(
            """
            SELECT step_name, step_order, status, input_json, output_json,
                   error_json, artifact_asset_id, started_at, finished_at
            FROM workflow_steps
            WHERE run_id = ?
            ORDER BY step_order, step_id
            """,
            (source_run_id,),
        ).fetchall()
        for step in steps:
            step_name = str(step["step_name"] or "")
            step_id = f"{target_run_id}:{step_name}"
            conn.execute(
                """
                INSERT INTO workflow_steps (
                    step_id, run_id, step_name, step_order, status, input_json,
                    output_json, error_json, artifact_asset_id, started_at, finished_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step_id,
                    target_run_id,
                    step_name,
                    int(step["step_order"] or 0),
                    str(step["status"] or "unknown"),
                    _rewrite_json_text(
                        step["input_json"],
                        source_story_id=source_story_id,
                        target_story_id=target_story_id,
                        run_id_map=run_id_map,
                        asset_id_map=asset_id_map,
                    ),
                    _rewrite_json_text(
                        step["output_json"],
                        source_story_id=source_story_id,
                        target_story_id=target_story_id,
                        run_id_map=run_id_map,
                        asset_id_map=asset_id_map,
                    ),
                    _rewrite_json_text(
                        step["error_json"],
                        source_story_id=source_story_id,
                        target_story_id=target_story_id,
                        run_id_map=run_id_map,
                        asset_id_map=asset_id_map,
                    ),
                    asset_id_map.get(str(step["artifact_asset_id"] or "")),
                    step["started_at"],
                    step["finished_at"],
                ),
            )

    creative_session_result = (
        clone_creative_session_rows(conn, source_story_id, target_story_id)
        if include_chapters
        else {
            "session_count": 0,
            "turn_count": 0,
            "fragment_count": 0,
            "session_id_map": {},
        }
    )

    return {
        "asset_count": len(included_assets),
        "workflow_count": len(workflow_rows),
        "run_id_map": run_id_map,
        "creative_sessions": creative_session_result,
    }
