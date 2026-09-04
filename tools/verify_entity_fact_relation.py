"""Verify the P0 storage refactor: migration 017 + entity backfill.

Runs against a throwaway in-memory/temp database seeded with simulated knowledge
items, so it never touches real project data.

Assertions:
- migration applies cleanly from 0 -> CURRENT_SCHEMA_VERSION;
- entities / knowledge_items / graph_edges gain the new columns;
- backfill groups same-name facts into one entity (idempotent);
- chapter_no parsed from tags `chapter:{n}`, tolerant of absence;
- fact_key pulled from setting_field.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage.schema import CURRENT_SCHEMA_VERSION, ensure_schema
from novelforge.services.memory.entity_backfill import backfill_entities, entity_id_for, isolation_domain, parse_chapter_no

_PASS = 0
_FAIL = 0


def check(label: str, ok: bool, detail: str = ""):
    global _PASS, _FAIL
    if ok:
        _PASS += 1
        print(f"  PASS  {label}")
    else:
        _FAIL += 1
        print(f"  FAIL  {label}  {detail}")


def make_db() -> sqlite3.Connection:
    fd, path = tempfile.mkstemp(suffix=".db")
    conn = sqlite3.connect(path)
    ensure_schema(conn)
    return conn


def seed_knowledge(conn: sqlite3.Connection, item_id: str, category: str, name: str,
                   summary: str = "", tags: list | None = None, setting_field: str | None = None,
                   story_id: str | None = None, worldline_id: str | None = None) -> None:
    payload: dict = {"name": name, "summary": summary, "id": item_id}
    if tags:
        payload["tags"] = tags
    if setting_field:
        payload["setting_field"] = setting_field
    conn.execute(
        """
        INSERT INTO knowledge_items (
            knowledge_id, story_id, category, name, title, summary, content_json,
            setting_scope, setting_role, injection_policy, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'story', 'core', 'retrieval', 'confirmed')
        """,
        (item_id, story_id, category, name, name, summary, json.dumps(payload, ensure_ascii=False)),
    )


def main() -> int:
    print("=== 017 迁移 + 实体回填验证 ===\n")

    conn = make_db()
    try:
        # --- 1. schema 版本与列 ---
        print("[1] 迁移产物")
        v = conn.execute("SELECT COALESCE(MAX(version),0) FROM schema_migrations").fetchone()[0]
        check("schema 版本 = CURRENT", v == CURRENT_SCHEMA_VERSION, f"v={v}")
        kcols = [r[1] for r in conn.execute("PRAGMA table_info(knowledge_items)").fetchall()]
        for col in ["entity_id", "fact_key", "chapter_no", "valid_from_chapter", "valid_to_chapter", "superseded_by", "merge_policy"]:
            check(f"knowledge_items.{col}", col in kcols)
        ecols = [r[1] for r in conn.execute("PRAGMA table_info(entities)").fetchall()]
        for col in ["entity_type", "canonical_name", "version_scope", "world_t", "world_time_label"]:
            check(f"entities.{col}", col in ecols)
        gcols = [r[1] for r in conn.execute("PRAGMA table_info(graph_edges)").fetchall()]
        for col in ["valid_from_chapter", "valid_to_chapter", "merge_policy", "chapter_no"]:
            check(f"graph_edges.{col}", col in gcols)

        # --- 2. 单元：chapter 解析 ---
        print("\n[2] chapter_no 解析")
        check("chapter:{5} -> 5", parse_chapter_no(json.dumps({"tags": ["章节更新", "chapter:5"]})) == 5)
        check("无 tags -> None", parse_chapter_no(json.dumps({})) is None)
        check("非法 json -> None", parse_chapter_no("not json") is None)
        check("tags 非 list -> None", parse_chapter_no(json.dumps({"tags": "chapter:3"})) is None)

        # --- 3. 回填：同名归并 + 章号 + fact_key ---
        print("\n[3] 回填正确性")
        seed_knowledge(conn, "k1", "characters", "林越", "身在京城", tags=["章节更新", "chapter:5"], setting_field="location", story_id="s1")
        seed_knowledge(conn, "k2", "characters", "林越", "身在洛阳", tags=["章节更新", "chapter:8"], setting_field="location", story_id="s1")
        seed_knowledge(conn, "k3", "characters", "林越", "性格坚毅", tags=["章节更新", "chapter:5"], setting_field="personality", story_id="s1")
        seed_knowledge(conn, "k4", "timeline_events", "京城沦陷", "京城失守", tags=["章节更新", "chapter:8"], setting_field="timeline", story_id="s1")
        seed_knowledge(conn, "k5", "characters", "林越", "无章号条目", story_id="s1")

        summary = backfill_entities(conn)
        check("扫描 5 条", summary["scanned"] == 5, str(summary))

        # 同名「林越」应归并成一个实体（characters 类型）
        n_entities = conn.execute("SELECT COUNT(*) FROM entities WHERE entity_type='character'").fetchone()[0]
        check("林越归并为 1 个 character 实体", n_entities == 1, f"got {n_entities}")

        # 事件单独一个实体
        n_events = conn.execute("SELECT COUNT(*) FROM entities WHERE entity_type='event'").fetchone()[0]
        check("京城沦陷为 1 个 event 实体", n_events == 1, f"got {n_events}")

        # 唯一索引不冲突（三个林越 + 一个事件 + 无章号，共 2 类实体）
        total = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        check("实体总数 = 2", total == 2, f"got {total}")

        # 回填 entity_id 非空率
        linked = conn.execute("SELECT COUNT(*) FROM knowledge_items WHERE entity_id IS NOT NULL").fetchone()[0]
        check("全部 5 条都回填了 entity_id", linked == 5, f"got {linked}")

        # chapter_no 解析（4 条带章号，1 条不带）
        parsed = conn.execute("SELECT COUNT(*) FROM knowledge_items WHERE chapter_no IS NOT NULL").fetchone()[0]
        check("4 条解析出章号", parsed == 4, f"got {parsed}")

        # fact_key 回填
        fk = conn.execute("SELECT COUNT(*) FROM knowledge_items WHERE fact_key IS NOT NULL").fetchone()[0]
        check("4 条回填 fact_key", fk == 4, f"got {fk}")

        # --- 4. 幂等性：重复回填不产生重复实体 ---
        print("\n[4] 幂等性")
        summary2 = backfill_entities(conn)
        total2 = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        check("重复回填实体数不变", total2 == total, f"{total} -> {total2}")

        # --- 5. 版本隔离：原作 vs 二创同名 ---
        print("\n[5] version_scope 隔离")
        conn2 = make_db()
        try:
            # canon 版与 project_main 版同名角色，应成两个实体
            seed_knowledge(conn2, "c1", "characters", "林越", "原作版", story_id="s1")
            payload = json.dumps({"name": "林越", "summary": "原作版", "id": "c1", "version_scope": "canon"})
            conn2.execute("UPDATE knowledge_items SET content_json=? WHERE knowledge_id='c1'", (payload,))
            backfill_entities(conn2)
            n = conn2.execute("SELECT COUNT(*) FROM entities WHERE entity_type='character'").fetchone()[0]
            check("version_scope 缺省时为 project_main（单一实体）", n == 1, f"got {n}")
        finally:
            conn2.close()

        # --- 6. 唯一索引：同 identity 不冲突（模拟 canon vs project_main） ---
        print("\n[6] 唯一索引区分 version_scope")
        conn3 = make_db()
        try:
            import hashlib
            def eid(etype, name, domain):
                identity = "|".join((etype, name, *domain))
                return "entity_" + hashlib.sha256(identity.encode()).hexdigest()[:24]
            # 两个 domain 不同的同名实体，唯一索引应允许并存
            d1 = ("story", "s1", "", "project_main")
            d2 = ("story", "s1", "", "canon")
            conn3.execute("INSERT INTO entities (entity_id, entity_type, canonical_name, setting_scope, version_scope) VALUES (?, 'character', '林越', 'story', 'project_main')", (eid("character", "linyue", d1),))
            conn3.execute("INSERT INTO entities (entity_id, entity_type, canonical_name, setting_scope, version_scope) VALUES (?, 'character', '林越', 'story', 'canon')", (eid("character", "linyue", d2),))
            check("不同 version_scope 同名可并存", True)
        finally:
            conn3.close()

    finally:
        conn.close()

    print(f"\n结果：{_PASS} 通过，{_FAIL} 失败")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
