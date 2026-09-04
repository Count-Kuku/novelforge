"""Verify P3: entity-centric read queries (entities/facts/relations/timeline)."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage.schema import ensure_schema
from storage.repositories.knowledge import sync_knowledge_category
from storage.repositories.entity_query import (
    load_entities,
    load_entity_facts,
    load_entity_relations,
    load_timeline,
)

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
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    conn.execute("INSERT INTO stories (story_id, name) VALUES ('s1', '测试')")
    conn.commit()
    return conn


def main() -> int:
    print("=== P3 实体中心查询 ===\n")

    conn = make_db()
    try:
        # 角色林越（location 京→洛），隶属青云门
        sync_knowledge_category(conn, "characters", [{
            "id": "c1", "category": "characters", "name": "林越", "summary": "主角",
            "story_id": "s1", "setting_scope": "story", "setting_role": "core",
            "injection_policy": "retrieval", "status": "confirmed",
            "setting_field": "location", "source_chapter_no": 5, "affiliations": ["青云门"],
            "importance": 0.8,
        }])
        sync_knowledge_category(conn, "characters", [
            {"id": "c1", "category": "characters", "name": "林越", "summary": "主角",
             "story_id": "s1", "setting_scope": "story", "setting_role": "core",
             "injection_policy": "retrieval", "status": "confirmed",
             "setting_field": "location", "source_chapter_no": 5, "affiliations": ["青云门"],
             "importance": 0.8},
            {"id": "c2", "category": "characters", "name": "林越", "summary": "林越身在洛阳",
             "story_id": "s1", "setting_scope": "story", "setting_role": "core",
             "injection_policy": "retrieval", "status": "confirmed",
             "setting_field": "location", "source_chapter_no": 8, "importance": 0.8},
        ])
        # 事件
        sync_knowledge_category(conn, "timeline_events", [{
            "id": "t1", "category": "timeline_events", "name": "京城沦陷", "summary": "京城失守",
            "story_id": "s1", "setting_scope": "story", "setting_role": "core",
            "injection_policy": "retrieval", "status": "confirmed",
            "setting_field": "timeline", "source_chapter_no": 8, "time": "大齐三年三月初三",
            "participants": ["林越"], "importance": 0.9,
        }])

        print("[1] load_entities")
        chars = load_entities(conn, entity_type="character")
        check("1 个 character 实体", len(chars) == 1, f"got {len(chars)}")
        check("实体名林越", chars and chars[0]["canonical_name"] == "林越")

        print("\n[2] load_entity_facts（章号过滤）")
        lin = chars[0]["entity_id"]
        facts_ch5 = load_entity_facts(conn, lin, chapter_no=5)
        facts_ch8 = load_entity_facts(conn, lin, chapter_no=8)
        check("第5章只1条有效事实", len(facts_ch5) == 1, f"got {len(facts_ch5)}")
        check("第8章1条有效事实（旧值被取代）", len(facts_ch8) == 1, f"got {len(facts_ch8)}")
        check("第8章事实是洛阳", facts_ch8[0]["summary"] == "林越身在洛阳", facts_ch8[0]["summary"])

        print("\n[3] load_entity_relations（关联边）")
        rels = load_entity_relations(conn, lin)
        # 林越有 2 条关联：affiliated_with 出边（青云门）+ participated_in 入边（京城沦陷）
        check("林越有 2 条关联", len(rels) == 2, f"got {len(rels)}")
        rel_types = {r["relation_type"] for r in rels}
        check("含 affiliated_with", "affiliated_with" in rel_types, str(rel_types))
        check("含 participated_in", "participated_in" in rel_types, str(rel_types))
        aff = next((r for r in rels if r["relation_type"] == "affiliated_with"), None)
        if aff:
            check("affiliated_with 对象是青云门", aff["other_name"] == "青云门", aff["other_name"])
            check("affiliated_with 对象类型 organization", aff["other_type"] == "organization", aff["other_type"])

        print("\n[4] load_timeline（world_t 排序）")
        timeline = load_timeline(conn, story_id="s1")
        check("1 个事件", len(timeline) == 1, f"got {len(timeline)}")
        check("事件 world_t=8", timeline and timeline[0]["world_t"] == 8.0, str(timeline[0]["world_t"] if timeline else None))

    finally:
        conn.close()

    print(f"\n结果：{_PASS} 通过，{_FAIL} 失败")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
