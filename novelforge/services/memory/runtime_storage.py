"""Non-creating access to authoritative project runtime storage."""

from __future__ import annotations

import logging
from pathlib import Path

from novelforge.services import memory as _memory_api


def _recover_existing_project_db_if_needed(project_name: str, root: Path) -> bool:
    """Retry a failed project DB without recreating a moved/deleted path."""
    unavailable_projects = _memory_api._DB_UNAVAILABLE_PROJECTS
    if project_name not in unavailable_projects:
        return True
    try:
        _memory_api.initialize_project_db(root, project_name, require_existing=True)
    except FileNotFoundError:
        # A concurrent rename/delete is authoritative. Keep the failure mark
        # for a future real project with this name, but never recreate its path.
        return False
    except Exception as exc:
        unavailable_projects.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to recover existing project database for %s: %s",
            project_name,
            exc,
        )
        _memory_api._raise_if_db_only(f"Project database is unavailable for {project_name}.", exc)
        return False
    unavailable_projects.discard(project_name)
    return True


def _existing_runtime_project(project_name: str) -> tuple[str, Path] | None:
    """Resolve and recover a project without ever creating its path."""
    normalized_name = _memory_api.normalize_project_name(project_name)
    root = _memory_api.project_path(normalized_name).resolve()
    if not root.is_dir():
        return None
    _memory_api._bootstrap_project_database_if_needed(normalized_name)
    if not root.is_dir():
        return None
    if not _recover_existing_project_db_if_needed(normalized_name, root):
        return None
    return normalized_name, root


def _load_runtime_from_db_best_effort(project_name: str, loader, description: str):
    project = _existing_runtime_project(project_name)
    if project is None:
        return None
    normalized_name, root = project
    try:
        with _memory_api.open_existing_project_db(root) as conn:
            result = loader(conn)
            _memory_api._DB_UNAVAILABLE_PROJECTS.discard(normalized_name)
            return result
    except FileNotFoundError:
        return None
    except Exception as exc:
        _memory_api._DB_UNAVAILABLE_PROJECTS.add(normalized_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to load %s from project database for %s: %s",
            description,
            normalized_name,
            exc,
        )
        _memory_api._raise_if_db_only(
            f"Failed to load {description} from project database for {normalized_name}.",
            exc,
        )
        return None


def _sync_runtime_to_db_best_effort(project_name: str, callback) -> None:
    project = _existing_runtime_project(project_name)
    if project is None:
        return
    normalized_name, root = project
    try:
        with _memory_api.open_existing_project_db(root) as conn:
            callback(conn)
            conn.commit()
            _memory_api._DB_UNAVAILABLE_PROJECTS.discard(normalized_name)
    except FileNotFoundError:
        return
    except Exception as exc:
        _memory_api._DB_UNAVAILABLE_PROJECTS.add(normalized_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to sync runtime record to project database for %s: %s",
            normalized_name,
            exc,
        )
        _memory_api._raise_if_db_only(
            f"Failed to sync runtime record to project database for {normalized_name}.",
            exc,
        )
    else:
        pending = _memory_api._take_project_pending_mirror_deletions(normalized_name)
        _memory_api._delete_pending_mirrors(pending)


def _mutate_workflow_in_db(project_name: str, callback, description: str):
    """Run an authoritative workflow mutation without recreating project paths."""
    project = _existing_runtime_project(project_name)
    if project is None:
        return None
    normalized_name, root = project
    try:
        with _memory_api.open_existing_project_db(root) as conn:
            result = callback(conn)
            conn.commit()
            _memory_api._DB_UNAVAILABLE_PROJECTS.discard(normalized_name)
            return result
    except FileNotFoundError:
        # A project lifecycle operation won the race after a worker took its
        # project-name snapshot. Missing paths are authoritative here.
        return None
    except ValueError:
        # Domain/state conflicts are authoritative rejections, not DB outages.
        raise
    except Exception as exc:
        _memory_api._DB_UNAVAILABLE_PROJECTS.add(normalized_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to mutate %s in project database for %s: %s",
            description,
            normalized_name,
            exc,
        )
        _memory_api._raise_if_db_only(
            f"Failed to mutate {description} in project database for {normalized_name}.",
            exc,
        )
        return None
