from __future__ import annotations

import re
import sqlite3
from pathlib import Path


CURRENT_SCHEMA_VERSION = 13
MIGRATIONS_DIR = Path(__file__).parent / "migrations"
MIGRATION_NAME_PATTERN = re.compile(r"^(\d+)_.*\.sql$")


def get_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if not row:
        return 0
    value = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]
    return int(value or 0)


def _migration_files() -> list[tuple[int, Path]]:
    files: list[tuple[int, Path]] = []
    for path in MIGRATIONS_DIR.glob("*.sql"):
        match = MIGRATION_NAME_PATTERN.match(path.name)
        if not match:
            continue
        files.append((int(match.group(1)), path))
    return sorted(files, key=lambda item: item[0])


def _execute_migration_script(conn: sqlite3.Connection, script: str) -> None:
    """Execute a SQL script without ``executescript``'s implicit commit."""

    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if not sqlite3.complete_statement(buffer):
            continue
        statement = buffer.strip()
        buffer = ""
        if statement:
            conn.execute(statement)
    if buffer.strip():
        raise sqlite3.OperationalError("Incomplete SQL statement in migration script.")


def ensure_schema(conn: sqlite3.Connection) -> int:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
        """
    )
    conn.commit()

    migrations = _migration_files()
    versions = [version for version, _ in migrations]
    expected_versions = list(range(1, CURRENT_SCHEMA_VERSION + 1))
    if versions != expected_versions:
        raise RuntimeError(
            f"Migration files must be continuous through version {CURRENT_SCHEMA_VERSION}; found {versions}."
        )

    current_version = get_schema_version(conn)
    if current_version > CURRENT_SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {current_version} is newer than supported version {CURRENT_SCHEMA_VERSION}."
        )

    for version, path in migrations:
        if version <= current_version:
            continue
        try:
            # Serialize fresh-database initialization and re-check the version
            # after acquiring the write lock so concurrent launchers cannot
            # both attempt the same non-idempotent ALTER migration.
            conn.execute("BEGIN IMMEDIATE")
            locked_version = get_schema_version(conn)
            if locked_version >= version:
                conn.commit()
                current_version = locked_version
                continue
            if version != locked_version + 1:
                raise RuntimeError(
                    f"Cannot apply migration {version} after database version {locked_version}."
                )
            _execute_migration_script(conn, path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))",
                (version,),
            )
            conn.commit()
            current_version = version
        except Exception:
            conn.rollback()
            raise
    return current_version
