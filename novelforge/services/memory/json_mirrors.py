"""Transitional JSON mirror layer for the DB-first storage contract.

SQLite is the authoritative store.  JSON mirrors are only written when the
``NOVELFORGE_WRITE_JSON_MIRRORS`` compatibility flag is explicitly enabled for
validating legacy integrations.  With the flag off (the default), every mirror
write is instead queued for deletion so stale JSON files cannot "resurrect"
old data.  This module is intentionally isolated so the whole compatibility
layer can be removed in one pass once the compatibility window closes.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .paths import (
    GLOBAL_PROMPT_OPTIONS_PATH,
    GLOBAL_RULE_CONFLICT_RESOLUTIONS_PATH,
    GLOBAL_RULES_PATH,
    LLM_PROFILES_PATH,
)
from .project_registry import project_path

_PENDING_MIRROR_DELETIONS: list[Path] = []


def _write_json_mirrors_enabled() -> bool:
    return str(os.getenv("NOVELFORGE_WRITE_JSON_MIRRORS", "0")).strip().lower() in {"1", "true", "yes", "on"}


def _queue_mirror_deletion(path: Path) -> None:
    if path.exists() and path.is_file() and path not in _PENDING_MIRROR_DELETIONS:
        _PENDING_MIRROR_DELETIONS.append(path)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _take_pending_mirror_deletions(predicate=None) -> list[Path]:
    if predicate is None:
        pending = list(_PENDING_MIRROR_DELETIONS)
        _PENDING_MIRROR_DELETIONS.clear()
        return pending
    pending: list[Path] = []
    remaining: list[Path] = []
    for path in _PENDING_MIRROR_DELETIONS:
        if predicate(path):
            pending.append(path)
        else:
            remaining.append(path)
    _PENDING_MIRROR_DELETIONS[:] = remaining
    return pending


def _take_global_pending_mirror_deletions() -> list[Path]:
    global_mirrors = {
        LLM_PROFILES_PATH.resolve(),
        GLOBAL_RULES_PATH.resolve(),
        GLOBAL_PROMPT_OPTIONS_PATH.resolve(),
        GLOBAL_RULE_CONFLICT_RESOLUTIONS_PATH.resolve(),
    }
    return _take_pending_mirror_deletions(lambda path: path.resolve() in global_mirrors)


def _take_project_pending_mirror_deletions(project_name: str) -> list[Path]:
    root = project_path(project_name).resolve()
    return _take_pending_mirror_deletions(lambda path: _is_relative_to(path, root))


def _delete_pending_mirrors(paths: list[Path]) -> None:
    for path in paths:
        if path.exists() and path.is_file():
            try:
                path.unlink()
            except OSError as exc:
                logging.getLogger("novelforge.storage").warning(
                    "Failed to delete JSON mirror %s; will retry later: %s",
                    path,
                    exc,
                )
                _queue_mirror_deletion(path)


def _discard_pending_mirror_deletion(path: Path) -> None:
    _PENDING_MIRROR_DELETIONS[:] = [item for item in _PENDING_MIRROR_DELETIONS if item != path]


def _write_json_mirror(path: Path, payload) -> None:
    if not _write_json_mirrors_enabled():
        _queue_mirror_deletion(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text_mirror(path: Path, content: str) -> None:
    if not _write_json_mirrors_enabled():
        _queue_mirror_deletion(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(content or ""), encoding="utf-8")
