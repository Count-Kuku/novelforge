"""验证旧版 schema 15 项目升级到 schema 16 时的数据保持与前向拒绝。"""
from __future__ import annotations

import hashlib
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage.schema import (  # noqa: E402
    CURRENT_SCHEMA_VERSION,
    MIGRATIONS_DIR,
    _execute_migration_script,
    ensure_schema,
    get_schema_version,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def apply_through(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        number = int(path.name.split("_", 1)[0])
        if number > version:
            break
        _execute_migration_script(conn, path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, 'fixture')",
            (number,),
        )
    conn.commit()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="novelforge-legacy-upgrade-") as temp_dir:
        db_path = Path(temp_dir) / "legacy.sqlite3"
        conn = sqlite3.connect(db_path)
        try:
            apply_through(conn, CURRENT_SCHEMA_VERSION - 1)
            check(get_schema_version(conn) == 15, "fixture 从旧数据库 schema 15 开始")
            content = "旧项目正文：保留段落、修订和资产哈希。"
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            conn.execute(
                "INSERT INTO project_meta(project_id, name, title) VALUES ('p1', 'legacy-project', '旧项目')"
            )
            conn.execute(
                "INSERT INTO stories(story_id, name, description, is_active) VALUES ('s1', '旧故事', '旧描述', 1)"
            )
            conn.execute(
                "INSERT INTO asset_files(asset_id, story_id, asset_type, logical_key, title, relative_path, content_hash) "
                "VALUES ('a1', 's1', 'chapter', 'chapter-1', '第一章', 'stories/s1/chapter-1.md', ?)"
                ,
                (content_hash,),
            )
            conn.commit()

            upgraded = ensure_schema(conn)
            check(upgraded == CURRENT_SCHEMA_VERSION, "旧数据库升级到当前 schema 16")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(stories)")}
            check("creation_mode" in columns, "stories 增加 creation_mode 字段")
            story = conn.execute(
                "SELECT name, description, is_active, creation_mode FROM stories WHERE story_id = 's1'"
            ).fetchone()
            check(story == ("旧故事", "旧描述", 1, "planned"), "旧故事字段与默认规划模式保持")
            asset = conn.execute(
                "SELECT relative_path, content_hash FROM asset_files WHERE asset_id = 'a1'"
            ).fetchone()
            check(asset == ("stories/s1/chapter-1.md", content_hash), "旧资产路径与内容 hash 保持")
            check(ensure_schema(conn) == CURRENT_SCHEMA_VERSION, "schema 16 重复启动保持幂等")

        finally:
            conn.close()

        future_path = Path(temp_dir) / "future.sqlite3"
        conn = sqlite3.connect(future_path)
        try:
            apply_through(conn, CURRENT_SCHEMA_VERSION)
            conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (17, 'fixture')")
            conn.commit()
            try:
                ensure_schema(conn)
            except RuntimeError as exc:
                check("newer than supported" in str(exc), "未来 schema 版本会被安全拒绝")
            else:
                raise AssertionError("schema 17 未被拒绝")
        finally:
            conn.close()

    print("Legacy database upgrade verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
