"""Project path resolution, the startup project registry and maintenance locks."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from novelforge.services import memory as _memory_api
from storage import (
    inspect_global_db,
    inspect_project_db,
    open_existing_project_db,
    open_project_db,
)
from storage.repositories import (
    project_maintenance_mode,
    rename_project_meta,
    set_project_maintenance_mode,
)

from .paths import (
    BASE_DIR,
    DELETED_PROJECTS_DIR,
    PROJECT_DATA_MARKERS,
    PROJECT_REGISTRY_PATH,
    WINDOWS_INVALID_PATH_CHARS,
    WINDOWS_RESERVED_PATH_NAMES,
)

__all__ = [
    "DELETED_PROJECTS_DIR",
    "normalize_project_name",
    "normalize_storage_component",
    "project_dir",
    "project_path",
    "ensure_project_path",
    "project_data_exists",
    "load_project_registry",
    "restore_project_registry",
    "list_projects",
    "project_is_discoverable",
    "project_is_registered",
    "register_project",
    "unregister_project",
    "rename_registered_project",
    "get_active_project_name",
    "set_active_project_name",
    "inspect_project_database",
    "inspect_global_database",
    "rename_project_database_record",
    "set_project_maintenance",
    "is_project_in_maintenance",
]


def normalize_project_name(project_name: str) -> str:
    normalized = project_name.strip()
    if not normalized:
        raise ValueError("Project name cannot be empty.")
    if (
        normalized in {".", ".."}
        or ".." in normalized
        or any(char in WINDOWS_INVALID_PATH_CHARS for char in normalized)
        or any(ord(char) < 32 for char in normalized)
        or normalized.endswith(".")
        or normalized.split(".", 1)[0].upper() in WINDOWS_RESERVED_PATH_NAMES
    ):
        raise ValueError("Invalid project name: path traversal characters not allowed.")
    return normalized


def normalize_storage_component(value: str, label: str = "Storage key") -> str:
    """Validate a user/data supplied value before using it in a filename."""

    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} cannot be empty.")
    if (
        normalized in {".", ".."}
        or any(char in WINDOWS_INVALID_PATH_CHARS for char in normalized)
        or any(ord(char) < 32 for char in normalized)
        or normalized.endswith(".")
        or normalized.split(".", 1)[0].upper() in WINDOWS_RESERVED_PATH_NAMES
    ):
        raise ValueError(f"Invalid {label.lower()}: path characters are not allowed.")
    return normalized


def project_dir(project_name: str) -> Path:
    return BASE_DIR / normalize_project_name(project_name)


def project_path(project_name: str) -> Path:
    return project_dir(project_name)


def ensure_project_path(project_name: str) -> Path:
    path = project_dir(project_name)
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_data_exists(project_name: str) -> bool:
    return project_dir(project_name).is_dir()


def _project_registry_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_project_registry(payload: dict | None) -> dict:
    raw_payload = payload if isinstance(payload, dict) else {}
    raw_projects = raw_payload.get("projects", [])
    projects: list[dict] = []
    seen: set[str] = set()
    if isinstance(raw_projects, list):
        for item in raw_projects:
            raw = item if isinstance(item, dict) else {"name": item}
            try:
                name = normalize_project_name(str(raw.get("name") or ""))
            except ValueError:
                continue
            if name in seen:
                continue
            seen.add(name)
            now = _project_registry_now()
            projects.append({
                "name": name,
                "status": str(raw.get("status") or "active"),
                "created_at": str(raw.get("created_at") or now),
                "updated_at": str(raw.get("updated_at") or now),
            })

    try:
        active_project = normalize_project_name(str(raw_payload.get("active_project") or ""))
    except ValueError:
        active_project = ""

    return {
        "version": 1,
        "active_project": active_project,
        "projects": projects,
    }


def _project_db_marker_is_valid(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _project_dir_looks_like_project(path: Path) -> bool:
    if not path.is_dir():
        return False
    if path.name.startswith("."):
        return False
    if any((path / marker).exists() for marker in PROJECT_DATA_MARKERS):
        return True
    return _project_db_marker_is_valid(path / "project.db")


def _discover_legacy_project_names() -> list[str]:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for path in BASE_DIR.iterdir():
        if not _project_dir_looks_like_project(path):
            continue
        try:
            names.append(normalize_project_name(path.name))
        except ValueError:
            continue
    return sorted(set(names), key=str.lower)


def _save_project_registry(registry: dict) -> dict:
    normalized = _normalize_project_registry(registry)
    PROJECT_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROJECT_REGISTRY_PATH.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def _backup_corrupt_project_registry(exc: Exception) -> None:
    if not PROJECT_REGISTRY_PATH.exists():
        return
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = PROJECT_REGISTRY_PATH.with_name(f"{PROJECT_REGISTRY_PATH.name}.corrupt-{timestamp}")
    counter = 1
    while backup_path.exists():
        backup_path = PROJECT_REGISTRY_PATH.with_name(f"{PROJECT_REGISTRY_PATH.name}.corrupt-{timestamp}-{counter}")
        counter += 1
    try:
        PROJECT_REGISTRY_PATH.replace(backup_path)
    except OSError:
        logging.getLogger("novelforge.storage").warning(
            "Failed to back up corrupt project registry %s after %s",
            PROJECT_REGISTRY_PATH,
            exc,
        )
    else:
        logging.getLogger("novelforge.storage").warning(
            "Backed up corrupt project registry %s to %s after %s",
            PROJECT_REGISTRY_PATH,
            backup_path,
            exc,
        )


def _build_project_registry_from_directories() -> dict:
    project_names = _discover_legacy_project_names()
    now = _project_registry_now()
    return {
        "version": 1,
        "active_project": "",
        "projects": [
            {"name": name, "status": "active", "created_at": now, "updated_at": now}
            for name in project_names
        ],
    }


def load_project_registry() -> dict:
    if PROJECT_REGISTRY_PATH.exists():
        try:
            raw = json.loads(PROJECT_REGISTRY_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            _backup_corrupt_project_registry(exc)
            return _save_project_registry(_build_project_registry_from_directories())
        registry = _normalize_project_registry(raw)
        if raw != registry:
            registry = _save_project_registry(registry)
        return registry

    return _save_project_registry(_build_project_registry_from_directories())


def restore_project_registry(registry: dict) -> dict:
    """Restore a previously loaded registry snapshot during compensation."""

    return _save_project_registry(registry)


def list_projects() -> list[str]:
    return _discover_legacy_project_names()


def project_is_discoverable(project_name: str) -> bool:
    try:
        normalized_name = normalize_project_name(project_name)
    except ValueError:
        return False
    return _project_dir_looks_like_project(project_dir(normalized_name))


def project_is_registered(project_name: str) -> bool:
    return project_is_discoverable(project_name)


def register_project(project_name: str, *, make_active: bool = False) -> str:
    normalized_name = normalize_project_name(project_name)
    registry = load_project_registry()
    now = _project_registry_now()
    updated = False
    for item in registry.get("projects", []):
        if item.get("name") == normalized_name:
            item["status"] = "active"
            item["updated_at"] = now
            updated = True
            break
    if not updated:
        registry.setdefault("projects", []).append({
            "name": normalized_name,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        })
    if make_active:
        registry["active_project"] = normalized_name
    _save_project_registry(registry)
    return normalized_name


def unregister_project(project_name: str) -> bool:
    normalized_name = normalize_project_name(project_name)
    registry = load_project_registry()
    original_projects = list(registry.get("projects", []))
    registry["projects"] = [item for item in original_projects if item.get("name") != normalized_name]
    removed = len(registry["projects"]) != len(original_projects)
    if registry.get("active_project") == normalized_name:
        registry["active_project"] = ""
    _save_project_registry(registry)
    return removed


def rename_registered_project(old_name: str, new_name: str) -> str:
    old_normalized = normalize_project_name(old_name)
    new_normalized = normalize_project_name(new_name)
    registry = load_project_registry()
    if old_normalized != new_normalized:
        registry["projects"] = [
            item for item in registry.get("projects", []) if item.get("name") != new_normalized
        ]
    now = _project_registry_now()
    renamed = False
    for item in registry.get("projects", []):
        if item.get("name") == old_normalized:
            item["name"] = new_normalized
            item["updated_at"] = now
            renamed = True
            break
    if registry.get("active_project") == old_normalized:
        registry["active_project"] = new_normalized
    if not renamed:
        registry.setdefault("projects", []).append({
            "name": new_normalized,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        })
    _save_project_registry(registry)
    return new_normalized


def get_active_project_name() -> str:
    registry = load_project_registry()
    active_project = str(registry.get("active_project") or "").strip()
    return active_project if active_project in set(list_projects()) else ""


def set_active_project_name(project_name: str | None) -> None:
    registry = load_project_registry()
    if project_name:
        normalized_name = normalize_project_name(project_name)
        if normalized_name not in set(list_projects()):
            return
        registry["active_project"] = normalized_name
    else:
        registry["active_project"] = ""
    _save_project_registry(registry)


def inspect_project_database(project_name: str) -> dict:
    return inspect_project_db(project_dir(project_name))


def inspect_global_database() -> dict:
    return inspect_global_db(Path("data"))


def rename_project_database_record(project_name: str, old_name: str, new_name: str) -> dict:
    """Rename the project metadata row inside an already moved project DB."""

    normalized_project_name = normalize_project_name(project_name)
    normalized_old_name = normalize_project_name(old_name)
    normalized_new_name = normalize_project_name(new_name)
    with open_project_db(project_path(normalized_project_name).resolve()) as conn:
        result = rename_project_meta(conn, normalized_old_name, normalized_new_name)
        conn.commit()
    return result


def set_project_maintenance(project_name: str, enabled: bool) -> bool:
    """Atomically fence or reopen background work for a project."""
    normalized_name = normalize_project_name(project_name)
    root = project_path(normalized_name).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Project does not exist: {normalized_name}")
    _memory_api._bootstrap_project_database_if_needed(normalized_name)
    with open_existing_project_db(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        changed = set_project_maintenance_mode(conn, normalized_name, enabled)
        conn.commit()
    return changed


def is_project_in_maintenance(project_name: str) -> bool:
    normalized_name = normalize_project_name(project_name)
    root = project_path(normalized_name).resolve()
    if not root.is_dir():
        return False
    _memory_api._bootstrap_project_database_if_needed(normalized_name)
    with open_existing_project_db(root) as conn:
        return project_maintenance_mode(conn, normalized_name)
