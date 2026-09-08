"""Real SQL fact replacement follows narrative ancestry, never job completion."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage.schema import ensure_schema
from storage.repositories.branches import ensure_default_branch
from storage.repositories.knowledge import upsert_knowledge_category_item, filter_superseded_visible_items


def main():
    checks = []
    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        ensure_schema(conn)
        conn.execute("INSERT INTO stories(story_id,name) VALUES ('s','Story')")
        branch = ensure_default_branch(conn, "s")["branch_id"]
        conn.execute("INSERT INTO creative_sessions(session_id,story_id,branch_id) VALUES ('session','s',?)", (branch,))
        for order, (fid, parent) in enumerate([("f1", None), ("f2", "f1"), ("f3", "f2"), ("sibling", "f1")], 1):
            conn.execute("INSERT INTO creative_turns(turn_id,session_id,turn_index,user_message,action_type,status,branch_id) VALUES (?,'session',?,'','generate','completed',?)", (fid, order, branch))
            conn.execute("INSERT INTO creative_fragments(fragment_id,session_id,turn_id,parent_fragment_id,content,status,content_hash,branch_id) VALUES (?,'session',?,?,'prose','accepted','hash',?)", (fid, fid, parent, branch))

        def put(kid, fid, name, chapter=None, field="status"):
            upsert_knowledge_category_item(conn, "characters", {"id": kid, "name": name, "summary": kid, "story_id": "s", "branch_id": branch, "setting_scope": "story", "source_segment_id": fid, "source_chapter_no": chapter, "setting_field": field})

        def successor(kid):
            return conn.execute("SELECT superseded_by FROM knowledge_items WHERE knowledge_id=?", (kid,)).fetchone()[0]

        put("no_chapter_dead", "f2", "No chapter")
        put("no_chapter_alive", "f1", "No chapter")
        assert successor("no_chapter_alive") == "no_chapter_dead" and not successor("no_chapter_dead")
        checks.append("late F1 cannot override F2 without chapter numbers")
        put("same_alive", "f1", "Same chapter", 1)
        put("same_dead", "f2", "Same chapter", 1)
        assert successor("same_alive") == "same_dead"
        checks.append("same-chapter fragments replace by narrative order")
        put("third", "f3", "No chapter")
        assert successor("no_chapter_dead") == "third" and successor("no_chapter_alive") == "no_chapter_dead"
        checks.append("replacement keeps nearest narrative successor")
        put("sibling_base", "f1", "Sibling")
        put("sibling_a", "f2", "Sibling")
        put("sibling_b", "sibling", "Sibling")
        assert not successor("sibling_base") and not successor("sibling_a") and not successor("sibling_b")
        checks.append("sibling candidates are not ordered by completion")
        put("ability_a", "f1", "Append", field="abilities")
        put("ability_b", "f2", "Append", field="abilities")
        assert not successor("ability_a")
        checks.append("append facts retain coexistence")
        rows = [dict(row) for row in conn.execute("SELECT * FROM knowledge_items WHERE name='No chapter'")]
        assert [row["knowledge_id"] for row in filter_superseded_visible_items(rows)] == ["third"]
        assert filter_superseded_visible_items([row for row in rows if row["knowledge_id"] == "no_chapter_alive"])
        checks.append("current projection hides old facts while historical F1 retains its fact")
        put("no_chapter_alive", "f1", "No chapter")
        assert successor("no_chapter_alive") == "no_chapter_dead" and not successor("third")
        checks.append("retrying old extraction never resurrects it")
    print(json.dumps({"ok": True, "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
