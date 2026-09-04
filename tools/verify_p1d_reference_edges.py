"""Verify P1d: entity-reference edges + relationship edges point at entities.

Asserts:
- a character item with `affiliations` projects a graph edge to an organization entity;
- a relationship item projects an edge between two character entities;
- edges' endpoints are entities.entity_id (not graph_nodes.node_id);
- the graph read path (load_knowledge_graph_rows) joins entities correctly.
"""
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
from storage.repositories.knowledge_center import load_knowledge_graph_rows

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
    print("=== P1d 引用边收编 + 关系边指向 entities ===\n")

    conn = make_db()
    try:
        # 角色林越，隶属于青云门（affiliations → affiliated_with 边）
        sync_knowledge_category(conn, "characters", [{
            "id": "c1", "category": "characters", "name": "林越", "summary": "主角",
            "story_id": "s1", "setting_scope": "story", "setting_role": "core",
            "injection_policy": "retrieval", "status": "confirmed",
            "setting_field": "affiliations", "affiliations": ["青云门"], "importance": 0.8,
        }])

        print("[1] 引用边（affiliations）")
        edges = conn.execute(
            "SELECT source_node_id, target_node_id, relation_type FROM graph_edges WHERE deleted_at IS NULL"
        ).fetchall()
        check("生成 1 条边", len(edges) == 1, f"got {len(edges)}")
        if edges:
            src, tgt, rel = edges[0]
            # 源是林越的 entity，目标是青云门的 entity
            src_ent = conn.execute("SELECT entity_type, canonical_name FROM entities WHERE entity_id=?", (src,)).fetchone()
            tgt_ent = conn.execute("SELECT entity_type, canonical_name FROM entities WHERE entity_id=?", (tgt,)).fetchone()
            check("源实体是 character 林越", src_ent and src_ent[1] == "林越", str(src_ent))
            check("目标实体是 organization 青云门", tgt_ent and tgt_ent[1] == "青云门" and tgt_ent[0] == "organization", str(tgt_ent))
            check("relation_type = affiliated_with", rel == "affiliated_with", rel)
            # 端点必须是 entity_id（不是 graph_nodes 的 node_id）
            check("端点格式为 entity_ 前缀", src.startswith("entity_") and tgt.startswith("entity_"), f"{src}, {tgt}")

        print("\n[2] 关系边（relationships）")
        sync_knowledge_category(conn, "relationships", [{
            "id": "r1", "category": "relationships", "name": "林越-苏婉",
            "summary": "林越与苏婉是师徒", "subject": "林越", "object": "苏婉",
            "relation_type": "师徒", "story_id": "s1", "setting_scope": "story",
            "setting_role": "core", "injection_policy": "retrieval", "status": "confirmed",
        }])
        edges2 = conn.execute(
            "SELECT source_node_id, target_node_id, relation_type FROM graph_edges WHERE deleted_at IS NULL ORDER BY edge_id"
        ).fetchall()
        rel_edges = [e for e in edges2 if e[2] == "shitu" or "师徒" in e[2] or e[2] == "师徒"]
        check("生成关系边", len(edges2) >= 2, f"got {len(edges2)}")
        # 师徒关系边两端都是 character 实体
        if rel_edges:
            src, tgt, rel = rel_edges[0]
            s = conn.execute("SELECT entity_type FROM entities WHERE entity_id=?", (src,)).fetchone()
            t = conn.execute("SELECT entity_type FROM entities WHERE entity_id=?", (tgt,)).fetchone()
            check("关系边两端都是 character", s and t and s[0] == "character" and t[0] == "character", f"{s},{t}")

        print("\n[3] 图读取路径（JOIN entities）")
        graph = load_knowledge_graph_rows(conn, story_id="s1")
        check("图有节点", len(graph.get("nodes", [])) > 0, str(len(graph.get("nodes", []))))
        check("图有边", len(graph.get("edges", [])) > 0, str(len(graph.get("edges", []))))
        node_ids = {n["node_id"] for n in graph.get("nodes", [])}
        check("节点是 entity_id", all(n.startswith("entity_") for n in node_ids), str(node_ids))

    finally:
        conn.close()

    print(f"\n结果：{_PASS} 通过，{_FAIL} 失败")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
