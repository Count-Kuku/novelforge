"""Verify P1e: event entities gain world_t + world_time_label; participants link via edges."""
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
    print("=== P1e 事件世界时间 + 参与者关联 ===\n")

    conn = make_db()
    try:
        # 事件：京城沦陷（第8章），参与者林越、苏婉
        sync_knowledge_category(conn, "timeline_events", [{
            "id": "t1", "category": "timeline_events", "name": "京城沦陷", "summary": "京城失守",
            "story_id": "s1", "setting_scope": "story", "setting_role": "core",
            "injection_policy": "retrieval", "status": "confirmed",
            "setting_field": "timeline", "source_chapter_no": 8,
            "time": "大齐三年三月初三",
            "participants": ["林越", "苏婉"],
            "importance": 0.8,
        }])

        print("[1] 事件实体 world_t / world_time_label")
        ev = conn.execute(
            "SELECT entity_type, canonical_name, world_t, world_time_label FROM entities WHERE entity_type='event'"
        ).fetchall()
        check("生成 1 个 event 实体", len(ev) == 1, f"got {len(ev)}")
        if ev:
            e = ev[0]
            check("world_t = 8（章号兜底）", e["world_t"] == 8.0, str(e["world_t"]))
            check("world_time_label = 时间字段", e["world_time_label"] == "大齐三年三月初三", str(e["world_time_label"]))

        print("\n[2] 参与者关联（participated_in 边）")
        edges = conn.execute(
            "SELECT relation_type, source_node_id, target_node_id FROM graph_edges WHERE deleted_at IS NULL"
        ).fetchall()
        participated = [e for e in edges if e["relation_type"] == "participated_in"]
        check("生成 2 条 participated_in 边", len(participated) == 2, f"got {len(participated)}")
        if participated:
            # 源是事件实体，目标是角色实体
            for e in participated:
                src = conn.execute("SELECT entity_type FROM entities WHERE entity_id=?", (e["source_node_id"],)).fetchone()
                tgt = conn.execute("SELECT entity_type, canonical_name FROM entities WHERE entity_id=?", (e["target_node_id"],)).fetchone()
                check("边源是 event", src and src["entity_type"] == "event", str(src))
                check("边目标是 character", tgt and tgt["entity_type"] == "character", str(tgt))

        print("\n[3] 时间线查询（按 world_t 排序）")
        conn.execute("INSERT INTO stories (story_id, name) VALUES ('s1b', '测试2')")
        sync_knowledge_category(conn, "timeline_events", [
            {"id": "t2", "category": "timeline_events", "name": "洛阳失守", "summary": "洛阳失守",
             "story_id": "s1", "setting_scope": "story", "setting_role": "core",
             "injection_policy": "retrieval", "status": "confirmed",
             "setting_field": "timeline", "source_chapter_no": 12, "time": "大齐三年四月初一",
             "participants": ["苏婉"], "importance": 0.7},
        ])
        timeline = conn.execute(
            "SELECT e.canonical_name, e.world_t FROM entities e WHERE e.entity_type='event' AND e.deleted_at IS NULL ORDER BY e.world_t"
        ).fetchall()
        check("事件按 world_t 升序", [t["canonical_name"] for t in timeline] == ["京城沦陷", "洛阳失守"],
              str([t["canonical_name"] for t in timeline]))

    finally:
        conn.close()

    print(f"\n结果：{_PASS} 通过，{_FAIL} 失败")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
