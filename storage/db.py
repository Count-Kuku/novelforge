from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .schema import CURRENT_SCHEMA_VERSION, ensure_schema, get_schema_version
from .repositories.projects import upsert_project_meta


logger = logging.getLogger("novelforge.storage")


def get_project_db_path(project_path: Path) -> Path:
    return Path(project_path) / "project.db"


def get_global_db_path(data_path: Path = Path("data")) -> Path:
    return Path(data_path) / "global.db"


def _unique_backup_path(path: Path, timestamp: str) -> Path:
    candidate = path.with_name(f"{path.name}.corrupt-{timestamp}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.corrupt-{timestamp}-{counter}")
        counter += 1
    return candidate


def _quarantine_empty_db_artifacts(db_path: Path, exc: Exception) -> bool:
    try:
        if not db_path.exists() or db_path.stat().st_size != 0:
            return False
    except OSError:
        return False

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    moved_paths: list[str] = []
    for suffix in ["", "-journal", "-wal", "-shm"]:
        artifact = Path(f"{db_path}{suffix}")
        if not artifact.exists():
            continue
        backup_path = _unique_backup_path(artifact, timestamp)
        try:
            artifact.replace(backup_path)
        except OSError as replace_exc:
            raise RuntimeError(
                "SQLite database is empty or corrupt but could not be moved. "
                "Close the running app and restart it to allow recovery: "
                f"{db_path}"
            ) from replace_exc
        moved_paths.append(str(backup_path))
    logger.warning(
        "Recovered empty SQLite database at %s after %s; moved artifacts to %s",
        db_path,
        exc,
        moved_paths,
    )
    return True


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError as exc:
        logger.warning("SQLite WAL mode unavailable for %s: %s", db_path, exc)
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def open_project_db(project_path: Path) -> sqlite3.Connection:
    db_path = get_project_db_path(project_path)
    conn: sqlite3.Connection | None = None
    try:
        conn = _connect(db_path)
        ensure_schema(conn)
        return conn
    except Exception as exc:
        if conn is not None:
            conn.close()
        if _quarantine_empty_db_artifacts(db_path, exc):
            conn = _connect(db_path)
            try:
                ensure_schema(conn)
            except Exception:
                conn.close()
                raise
            return conn
        raise


def open_global_db(data_path: Path = Path("data")) -> sqlite3.Connection:
    db_path = get_global_db_path(data_path)
    conn: sqlite3.Connection | None = None
    try:
        conn = _connect(db_path)
        ensure_schema(conn)
        return conn
    except Exception as exc:
        if conn is not None:
            conn.close()
        if _quarantine_empty_db_artifacts(db_path, exc):
            conn = _connect(db_path)
            try:
                ensure_schema(conn)
            except Exception:
                conn.close()
                raise
            return conn
        raise


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        conn.execute("BEGIN")
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()


def initialize_project_db(project_path: Path, project_name: str) -> Path:
    db_path = get_project_db_path(project_path)
    with open_project_db(project_path) as conn:
        upsert_project_meta(conn, project_name=project_name)
        conn.commit()
    return db_path


def initialize_global_db(data_path: Path = Path("data")) -> Path:
    db_path = get_global_db_path(data_path)
    with open_global_db(data_path) as conn:
        conn.commit()
    return db_path


def inspect_project_db(project_path: Path) -> dict:
    db_path = get_project_db_path(project_path)
    table_names = [
        "project_meta",
        "stories",
        "story_profiles",
        "asset_files",
        "asset_payloads",
        "rules",
        "prompt_options",
        "knowledge_items",
        "pending_knowledge_items",
        "entity_alias_groups",
        "source_documents",
        "source_segments",
        "retrieval_documents",
        "retrieval_chunks",
        "retrieval_vectors",
        "graph_nodes",
        "graph_edges",
        "workflow_runs",
        "workflow_steps",
        "auto_review_runs",
        "retrieval_eval_cases",
        "retrieval_eval_runs",
        "retrieval_feedback",
    ]
    result = {
        "ok": False,
        "db_path": str(db_path),
        "exists": db_path.exists(),
        "schema_version": 0,
        "expected_schema_version": CURRENT_SCHEMA_VERSION,
        "writable": False,
        "journal_mode": "",
        "foreign_keys": False,
        "table_counts": {},
        "error": "",
    }
    try:
        with open_project_db(project_path) as conn:
            result["exists"] = db_path.exists()
            result["schema_version"] = get_schema_version(conn)
            result["journal_mode"] = str(conn.execute("PRAGMA journal_mode").fetchone()[0])
            result["foreign_keys"] = bool(conn.execute("PRAGMA foreign_keys").fetchone()[0])
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS db_healthcheck (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    checked_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO db_healthcheck (id, checked_at)
                VALUES (1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                ON CONFLICT(id) DO UPDATE SET checked_at = excluded.checked_at
                """
            )
            conn.commit()
            result["writable"] = True
            for table_name in table_names:
                exists = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table_name,),
                ).fetchone()
                if not exists:
                    result["table_counts"][table_name] = None
                    continue
                count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                result["table_counts"][table_name] = int(count or 0)
            result["ok"] = True
    except Exception as exc:
        result["error"] = str(exc)
    return result


def inspect_global_db(data_path: Path = Path("data")) -> dict:
    db_path = get_global_db_path(data_path)
    table_names = [
        "global_settings",
        "rules",
        "prompt_options",
    ]
    result = {
        "ok": False,
        "db_path": str(db_path),
        "exists": db_path.exists(),
        "schema_version": 0,
        "expected_schema_version": CURRENT_SCHEMA_VERSION,
        "writable": False,
        "journal_mode": "",
        "foreign_keys": False,
        "table_counts": {},
        "error": "",
    }
    try:
        with open_global_db(data_path) as conn:
            result["exists"] = db_path.exists()
            result["schema_version"] = get_schema_version(conn)
            result["journal_mode"] = str(conn.execute("PRAGMA journal_mode").fetchone()[0])
            result["foreign_keys"] = bool(conn.execute("PRAGMA foreign_keys").fetchone()[0])
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS db_healthcheck (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    checked_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO db_healthcheck (id, checked_at)
                VALUES (1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                ON CONFLICT(id) DO UPDATE SET checked_at = excluded.checked_at
                """
            )
            conn.commit()
            result["writable"] = True
            for table_name in table_names:
                exists = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table_name,),
                ).fetchone()
                if not exists:
                    result["table_counts"][table_name] = None
                    continue
                count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                result["table_counts"][table_name] = int(count or 0)
            result["ok"] = True
    except Exception as exc:
        result["error"] = str(exc)
    return result
