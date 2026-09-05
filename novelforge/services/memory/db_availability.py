"""Database availability state, legacy bootstrap and best-effort DB access.

All project-level "open, mutate, commit, drain mirrors" and
"open, read" flows in the memory package funnel through the two generic
helpers at the bottom of this module so failure semantics stay identical:
mark the database unavailable, log a warning, and re-raise in DB-only mode.
"""

from __future__ import annotations

import logging
from pathlib import Path

from novelforge.services import memory as _memory_api
from storage import (
    initialize_global_db,
    initialize_project_db,
    open_global_db,
    open_project_db,
)

from .json_mirrors import (
    _delete_pending_mirrors,
    _take_global_pending_mirror_deletions,
    _take_project_pending_mirror_deletions,
    _write_json_mirrors_enabled,
)
from .project_registry import (
    _project_dir_looks_like_project,
    ensure_project_path,
    normalize_project_name,
    project_path,
)

_DB_UNAVAILABLE_PROJECTS: set[str] = set()
_GLOBAL_DB_UNAVAILABLE = False
_PROJECT_DB_BOOTSTRAP_IN_PROGRESS: set[str] = set()
_GLOBAL_DB_BOOTSTRAP_IN_PROGRESS = False


def _db_only_storage_required() -> bool:
    return not _write_json_mirrors_enabled()


def _raise_if_db_only(message: str, exc: Exception | None = None) -> None:
    if not _db_only_storage_required():
        return
    if exc is None:
        raise RuntimeError(message)
    raise RuntimeError(message) from exc


def _project_db_marked_unavailable(project_name: str) -> bool:
    _bootstrap_project_database_if_needed(project_name)
    if project_name not in _DB_UNAVAILABLE_PROJECTS:
        return False
    _initialize_project_db_best_effort(project_name)
    if project_name not in _DB_UNAVAILABLE_PROJECTS:
        return False
    _raise_if_db_only(f"Project database is unavailable for {project_name}.")
    return True


def _global_db_marked_unavailable() -> bool:
    _bootstrap_global_database_if_needed()
    if not _GLOBAL_DB_UNAVAILABLE:
        return False
    _initialize_global_db_best_effort()
    if not _GLOBAL_DB_UNAVAILABLE:
        return False
    _raise_if_db_only("Global database is unavailable.")
    return True


def _bootstrap_project_database_if_needed(project_name: str) -> None:
    """Import a legacy file-backed project before the first DB-first read.

    Opening SQLite creates an empty database.  If that happens before legacy
    JSON has been imported, valid file-backed data is indistinguishable from
    an intentionally empty authoritative database and is silently hidden.
    """

    normalized_name = normalize_project_name(project_name)
    root = project_path(normalized_name)
    db_path = root / "project.db"
    if normalized_name in _PROJECT_DB_BOOTSTRAP_IN_PROGRESS:
        return
    if not root.exists() or not _project_dir_looks_like_project(root):
        return
    if db_path.exists():
        try:
            if db_path.stat().st_size > 0:
                return
        except OSError:
            return
        raise RuntimeError(
            f"Legacy project {normalized_name} has a zero-byte project.db. "
            "Automatic import was stopped to avoid racing a running app. "
            "Close NovelForge, move the empty database aside, then reopen the project."
        )

    _PROJECT_DB_BOOTSTRAP_IN_PROGRESS.add(normalized_name)
    try:
        result = _memory_api.sync_project_database_from_files(normalized_name)
        if not result.get("ok"):
            error = str(result.get("error") or "unknown legacy import error")
            raise RuntimeError(f"Failed to import legacy project storage for {normalized_name}: {error}")
    finally:
        _PROJECT_DB_BOOTSTRAP_IN_PROGRESS.discard(normalized_name)


def _bootstrap_global_database_if_needed() -> None:
    """Import legacy global JSON/.env settings before creating global.db."""

    global _GLOBAL_DB_BOOTSTRAP_IN_PROGRESS
    database_path = Path("data") / "global.db"
    if _GLOBAL_DB_BOOTSTRAP_IN_PROGRESS:
        return
    if database_path.exists():
        try:
            if database_path.stat().st_size > 0:
                return
        except OSError:
            return
        raise RuntimeError(
            "data/global.db is zero bytes. Automatic import was stopped to avoid "
            "racing a running app. Close NovelForge, move the empty database aside, "
            "then restart."
        )
    _GLOBAL_DB_BOOTSTRAP_IN_PROGRESS = True
    try:
        result = _memory_api.sync_global_database_from_files()
        if not result.get("ok"):
            error = str(result.get("error") or "unknown legacy import error")
            raise RuntimeError(f"Failed to import legacy global storage: {error}")
    finally:
        _GLOBAL_DB_BOOTSTRAP_IN_PROGRESS = False


def _initialize_global_db_best_effort() -> None:
    global _GLOBAL_DB_UNAVAILABLE
    try:
        initialize_global_db(Path("data"))
        _GLOBAL_DB_UNAVAILABLE = False
    except Exception as exc:
        _GLOBAL_DB_UNAVAILABLE = True
        logging.getLogger("novelforge.storage").warning(
            "Failed to initialize global database: %s",
            exc,
        )
        _raise_if_db_only("Failed to initialize global database.", exc)


def _sync_global_to_db_best_effort(callback) -> None:
    global _GLOBAL_DB_UNAVAILABLE
    if _global_db_marked_unavailable():
        return
    try:
        with open_global_db(Path("data")) as conn:
            callback(conn)
            conn.commit()
    except Exception as exc:
        _GLOBAL_DB_UNAVAILABLE = True
        logging.getLogger("novelforge.storage").warning(
            "Failed to sync global record to database: %s",
            exc,
        )
        _raise_if_db_only("Failed to sync global record to database.", exc)
    else:
        _delete_pending_mirrors(_take_global_pending_mirror_deletions())


def _load_global_from_db_best_effort(loader, description: str):
    global _GLOBAL_DB_UNAVAILABLE
    if _global_db_marked_unavailable():
        return None
    try:
        with open_global_db(Path("data")) as conn:
            return loader(conn)
    except Exception as exc:
        _GLOBAL_DB_UNAVAILABLE = True
        logging.getLogger("novelforge.storage").warning(
            "Failed to load %s from global database: %s",
            description,
            exc,
        )
        _raise_if_db_only(f"Failed to load {description} from global database.", exc)
        return None


def _initialize_project_db_best_effort(project_name: str) -> None:
    try:
        initialize_project_db(ensure_project_path(project_name), project_name)
        _DB_UNAVAILABLE_PROJECTS.discard(project_name)
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to initialize project database for %s: %s",
            project_name,
            exc,
        )
        _raise_if_db_only(f"Failed to initialize project database for {project_name}.", exc)


def _mutate_project_db_best_effort(
    project_name: str,
    action,
    *,
    action_label: str,
    subject: str | None = None,
    drain_mirrors: bool = True,
):
    """Run one atomic project-db mutation with the shared failure policy.

    Marks the project database unavailable on error, re-raises under DB-only
    semantics, and (unless suppressed) drains pending JSON-mirror deletions
    after a successful commit.
    """

    if _project_db_marked_unavailable(project_name):
        return None
    subject = subject or project_name
    try:
        with open_project_db(project_path(project_name).resolve()) as conn:
            result = action(conn)
            conn.commit()
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to %s for %s: %s",
            action_label,
            subject,
            exc,
        )
        _raise_if_db_only(f"Failed to {action_label} for {subject}.", exc)
        return None
    if drain_mirrors:
        _delete_pending_mirrors(_take_project_pending_mirror_deletions(project_name))
    return result


def _load_project_db_best_effort(project_name: str, loader, *, action_label: str, subject: str | None = None):
    """Run one read-only project-db query with the shared failure policy."""

    if _project_db_marked_unavailable(project_name):
        return None
    subject = subject or project_name
    try:
        with open_project_db(project_path(project_name).resolve()) as conn:
            return loader(conn)
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to %s for %s: %s",
            action_label,
            subject,
            exc,
        )
        _raise_if_db_only(f"Failed to {action_label} for {subject}.", exc)
        return None
