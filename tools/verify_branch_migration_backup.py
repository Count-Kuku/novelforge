"""Verify a real schema-20 database is recoverable after branch migration."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from storage.db import open_existing_project_db
from storage.schema import CURRENT_SCHEMA_VERSION, MIGRATIONS_DIR, _execute_migration_script, get_schema_version
from tools.verify_utils import isolated_workspace


def main() -> int:
    with isolated_workspace("novelforge_migration_backup_") as workspace:
        project = workspace / "project"
        project.mkdir()
        asset = project / "original.md"
        asset.write_text("ORIGINAL_ASSET", encoding="utf-8")
        source = sqlite3.connect(project / "project.db")
        source.execute("PRAGMA journal_mode=WAL")
        source.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)")
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = int(path.name.split("_", 1)[0])
            if version > 20:
                break
            _execute_migration_script(source, path.read_text(encoding="utf-8-sig"))
            source.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
        source.execute("INSERT INTO stories(story_id,name) VALUES ('legacy','BEFORE_UPGRADE')")
        source.commit()
        try:
            with open_existing_project_db(project) as upgraded:
                assert get_schema_version(upgraded) == CURRENT_SCHEMA_VERSION
                assert upgraded.execute("SELECT branch_id FROM story_branches WHERE story_id='legacy'").fetchone()[0] == "branch_main_legacy"
            backups = list((project / ".schema_backups").glob("*.sqlite3"))
            assert len(backups) == 1
            with sqlite3.connect(backups[0]) as backup:
                assert get_schema_version(backup) == 20
                assert backup.execute("SELECT name FROM stories WHERE story_id='legacy'").fetchone()[0] == "BEFORE_UPGRADE"
                assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            with open_existing_project_db(project):
                pass
            assert len(list((project / ".schema_backups").glob("*.sqlite3"))) == 1
            assert asset.read_text(encoding="utf-8") == "ORIGINAL_ASSET"

            # A backup failure must occur before any ALTER or backfill.
            failed = workspace / "failed"
            failed.mkdir()
            with sqlite3.connect(failed / "project.db") as target, sqlite3.connect(backups[0]) as original:
                original.backup(target)
            with patch("storage.db._backup_before_schema_upgrade", side_effect=OSError("injected backup failure")):
                try:
                    open_existing_project_db(failed)
                except OSError:
                    pass
                else:
                    raise AssertionError("backup failure did not stop migration")
            with sqlite3.connect(failed / "project.db") as unchanged:
                assert get_schema_version(unchanged) == 20
        finally:
            source.close()
    print(json.dumps({"ok": True, "checks": ["WAL-backed pre-upgrade snapshot is valid schema 20", "upgrade migrates branch ownership", "latest schema does not create duplicate backups", "file asset remains unchanged", "backup failure prevents migration"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
