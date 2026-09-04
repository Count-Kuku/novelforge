"""Verify P1a: entity_id/fact_key/chapter_no backfill + slot supersession on write.

Writes two same-slot facts (林越 location=京城 @ ch5, then 林越 location=洛阳 @ ch8)
and asserts the first is invalidated (valid_to_chapter=8) so contradictory values
never coexist in the generation context.
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

from storage.schema import ensure_schema
from storage.repositories.knowledge import sync_knowledge_category

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
    conn.execute("INSERT INTO stories (story_id, name) VALUES ('s1', '测试故事')")
    conn.commit()
    return conn


def make_item(item_id: str, name: str, summary: str, chapter_no: int,
              setting_field: str, story_id: str = "s1") -> dict:
    return {
        "id": item_id,
        "category": "characters",
        "name": name,
        "summary": summary,
        "story_id": story_id,
        "setting_scope": "story",
        "setting_role": "core",
        "injection_policy": "retrieval",
        "status": "confirmed",
        "setting_field": setting_field,
        "source_chapter_no": chapter_no,
        "tags": [f"chapter:{chapter_no}"],
        "importance": 0.75,
    }


def main() -> int:
    print("=== P1a 写入侧：entity 关联 + 同槽位取代 ===\n")

    conn = make_db()
    try:
        # 第 5 章：林越在京城（首批确认）
        sync_knowledge_category(conn, "characters", [make_item("k1", "林越", "身在京城", 5, "location")])
        # 第 8 章：林越在洛阳（第二批确认，模拟真实流程：加载 existing + append 完整列表）
        sync_knowledge_category(conn, "characters", [
            make_item("k1", "林越", "身在京城", 5, "location"),
            make_item("k2", "林越", "身在洛阳", 8, "location"),
        ])

        rows = conn.execute(
            "SELECT knowledge_id, entity_id, fact_key, chapter_no, valid_from_chapter, valid_to_chapter, merge_policy "
            "FROM knowledge_items WHERE category='characters' ORDER BY chapter_no"
        ).fetchall()

        print("[1] 同槽位取代")
        check("写入 2 条事实", len(rows) == 2, f"got {len(rows)}")
        by_id = {r[0]: r for r in rows}
        check("两条属于同一 entity", by_id["k1"][1] == by_id["k2"][1] and by_id["k1"][1] is not None)
        check("两条同 fact_key=location", by_id["k1"][2] == "location" and by_id["k2"][2] == "location")
        check("旧值(k1) valid_to_chapter=8", by_id["k1"][5] == 8, f"got {by_id['k1'][5]}")
        check("新值(k2) valid_to_chapter=NULL", by_id["k2"][5] is None)
        check("merge_policy=replace", by_id["k1"][6] == "replace" and by_id["k2"][6] == "replace")

        # 第 5 章视角：只应看到"身在京城"
        active = conn.execute(
            "SELECT summary FROM knowledge_items WHERE entity_id=? AND fact_key='location' "
            "AND valid_from_chapter <= 5 AND (valid_to_chapter IS NULL OR valid_to_chapter > 5) AND deleted_at IS NULL",
            (by_id["k1"][1],),
        ).fetchall()
        check("第5章只命中京城", len(active) == 1 and active[0][0] == "身在京城", str(active))
        # 第 8 章视角：只应看到"身在洛阳"
        active8 = conn.execute(
            "SELECT summary FROM knowledge_items WHERE entity_id=? AND fact_key='location' "
            "AND valid_from_chapter <= 8 AND (valid_to_chapter IS NULL OR valid_to_chapter > 8) AND deleted_at IS NULL",
            (by_id["k1"][1],),
        ).fetchall()
        check("第8章只命中洛阳", len(active8) == 1 and active8[0][0] == "身在洛阳", str(active8))

        print("\n[2] entities 主档")
        ents = conn.execute("SELECT entity_type, canonical_name, summary FROM entities").fetchall()
        check("生成 1 个 character 实体", len(ents) == 1, str(ents))
        if ents:
            check("实体名为林越", ents[0][1] == "林越", str(ents[0]))
            # summary 应是最近一次写入的"身在洛阳"
            check("summary 为最近事实", ents[0][2] == "身在洛阳", str(ents[0]))

        print("\n[3] append 语义不取代（abilities）")
        sync_knowledge_category(conn, "abilities", [
            {"id": "a1", "category": "abilities", "name": "御剑术", "summary": "学会御剑术",
             "story_id": "s1", "setting_scope": "story", "setting_role": "core",
             "injection_policy": "retrieval", "status": "confirmed",
             "setting_field": "abilities", "source_chapter_no": 5, "importance": 0.5},
        ])
        # 全量列表（真实流程：load existing + append）
        sync_knowledge_category(conn, "abilities", [
            {"id": "a1", "category": "abilities", "name": "御剑术", "summary": "学会御剑术",
             "story_id": "s1", "setting_scope": "story", "setting_role": "core",
             "injection_policy": "retrieval", "status": "confirmed",
             "setting_field": "abilities", "source_chapter_no": 5, "importance": 0.5},
            {"id": "a2", "category": "abilities", "name": "御剑术", "summary": "御剑术精进",
             "story_id": "s1", "setting_scope": "story", "setting_role": "core",
             "injection_policy": "retrieval", "status": "confirmed",
             "setting_field": "abilities", "source_chapter_no": 9, "importance": 0.5},
        ])
        arows = conn.execute(
            "SELECT knowledge_id, valid_to_chapter, merge_policy FROM knowledge_items WHERE category='abilities' ORDER BY chapter_no"
        ).fetchall()
        by_a = {r[0]: r for r in arows}
        check("append 不取代（a1 valid_to_chapter=NULL）", by_a["a1"][1] is None, str(by_a["a1"]))
        check("append 策略正确", by_a["a1"][2] == "append" and by_a["a2"][2] == "append")

        print("\n[4] 事件无取代（timeline）")
        sync_knowledge_category(conn, "timeline_events", [
            {"id": "t1", "category": "timeline_events", "name": "京城沦陷", "summary": "京城失守",
             "story_id": "s1", "setting_scope": "story", "setting_role": "core",
             "injection_policy": "retrieval", "status": "confirmed",
             "setting_field": "timeline", "source_chapter_no": 8, "importance": 0.8},
        ])
        trows = conn.execute(
            "SELECT merge_policy, valid_to_chapter FROM knowledge_items WHERE category='timeline_events'"
        ).fetchall()
        check("事件不参与取代（valid_to_chapter=NULL）", trows[0][1] is None)
        check("事件 fact_key 默认 append", trows[0][0] == "append")

    finally:
        conn.close()

    print(f"\n结果：{_PASS} 通过，{_FAIL} 失败")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
