from __future__ import annotations

import re
import sqlite3
from pathlib import Path


CURRENT_SCHEMA_VERSION = 5
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


def ensure_schema(conn: sqlite3.Connection) -> int:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
        """
    )
    current_version = get_schema_version(conn)
    for version, path in _migration_files():
        if version <= current_version:
            continue
        script = path.read_text(encoding="utf-8")
        conn.executescript(script)
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))",
            (version,),
        )
        current_version = version
    conn.commit()
    return current_version
