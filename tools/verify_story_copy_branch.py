"""Offline regression for copying branch owned story state."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage.db import open_project_db
from storage.repositories.knowledge import upsert_knowledge_category_item
from storage.repositories.story_copy import clone_story_storage_rows
from storage.repositories.story_reference_libraries import bind_story_library, create_reference_library, create_reference_library_release


def _story(conn: sqlite3.Connection, story_id: str) -> None:
    conn.execute("INSERT INTO stories (story_id, name, status) VALUES (?, ?, 'active')", (story_id, story_id))
    conn.execute("INSERT INTO story_branches (branch_id, story_id, name, source_worldline_id) VALUES (?, ?, '主线', 'main')", (f"branch_main_{story_id}", story_id))


def verify() -> None:
    with tempfile.TemporaryDirectory(prefix="_verify_story_copy_branch_") as temp:
        with open_project_db(Path(temp)) as conn:
            _story(conn, "source")
            _story(conn, "target")
            conn.execute("INSERT INTO story_branches (branch_id, story_id, name, parent_branch_id, source_worldline_id) VALUES ('branch_alt_source', 'source', '另一线', 'branch_main_source', 'alt')")
            conn.execute("INSERT INTO creative_sessions (session_id, story_id, title, branch_id) VALUES ('session_source', 'source', '源会话', 'branch_alt_source')")
            conn.execute("INSERT INTO creative_turns (turn_id, session_id, branch_id, turn_index, user_message) VALUES ('turn_source', 'session_source', 'branch_alt_source', 1, '继续')")
            conn.execute("INSERT INTO creative_fragments (fragment_id, session_id, branch_id, turn_id, content, status, content_hash) VALUES ('fragment_source', 'session_source', 'branch_alt_source', 'turn_source', '副本正文', 'accepted', 'hash')")
            upsert_knowledge_category_item(conn, "characters", {
                "id": "knowledge_source", "category": "characters", "name": "源角色",
                "summary": "源知识", "setting_scope": "story", "story_id": "source",
                "branch_id": "branch_alt_source", "status": "confirmed", "aliases": ["源别名"],
            })
            upsert_knowledge_category_item(conn, "characters", {
                "id": "knowledge_project", "category": "characters", "name": "公共角色",
                "summary": "公共知识", "setting_scope": "project", "status": "confirmed",
            })
            conn.execute(
                """
                INSERT INTO asset_files
                    (asset_id, story_id, asset_type, logical_key, title, relative_path, metadata_json)
                VALUES ('asset_source', 'source', 'chapter', 'chapter-1', '源章节',
                        'stories/source/chapters/chapter-1.md', ?)
                """,
                (json.dumps({
                    "branch_id": "branch_alt_source",
                    "knowledge_id": "knowledge_source",
                    "context_snapshot_id": "asset_source",
                }, ensure_ascii=False),),
            )
            conn.execute(
                "INSERT INTO asset_payloads (asset_id, payload_json) VALUES ('asset_source', ?)",
                (json.dumps({"story_id": "source", "branch_id": "branch_alt_source", "knowledge_id": "knowledge_source"}, ensure_ascii=False),),
            )
            library = create_reference_library(conn, project_name="copy", title="公共资料")
            release = create_reference_library_release(conn, library_id=library["library_id"], knowledge_ids=["knowledge_project"])
            source_binding = bind_story_library(conn, story_id="source", library_id=library["library_id"], release_id=release["release_id"], branch_id="branch_alt_source")
            result = clone_story_storage_rows(conn, "source", "target")
            target_branch = result["branch_id_map"]["branch_alt_source"]
            assert target_branch != "branch_alt_source"
            session_row = conn.execute("SELECT story_id, branch_id FROM creative_sessions WHERE session_id = ?", (result["creative_sessions"]["session_id_map"]["session_source"],)).fetchone()
            assert tuple(session_row) == ("target", target_branch)
            copied_id = result["knowledge_id_map"]["knowledge_source"]
            copied = conn.execute("SELECT story_id, branch_id, content_json FROM knowledge_items WHERE knowledge_id = ?", (copied_id,)).fetchone()
            assert copied[0] == "target" and copied[1] == target_branch
            assert json.loads(copied[2])["story_id"] == "target"
            target_asset_id = conn.execute(
                "SELECT asset_id FROM asset_files WHERE story_id = 'target' AND logical_key = 'chapter-1'"
            ).fetchone()[0]
            target_asset = conn.execute(
                "SELECT relative_path, metadata_json FROM asset_files WHERE asset_id = ?",
                (target_asset_id,),
            ).fetchone()
            assert target_asset[0] == "stories/target/chapters/chapter-1.md"
            asset_metadata = json.loads(target_asset[1])
            assert asset_metadata["branch_id"] == target_branch
            assert asset_metadata["knowledge_id"] == copied_id
            assert asset_metadata["context_snapshot_id"] == target_asset_id
            target_binding = conn.execute("SELECT binding_id, story_id, branch_id, release_id FROM story_library_bindings WHERE story_id = 'target'").fetchone()
            assert target_binding is not None
            assert target_binding[0] != source_binding["binding_id"] and target_binding[1:] == ("target", target_branch, release["release_id"])
            target_link = conn.execute("SELECT local_knowledge_id FROM story_library_item_links WHERE binding_id = ?", (target_binding[0],)).fetchone()
            assert target_link is not None and target_link[0] != source_binding["items"][0]["local_knowledge_id"]
        print("verify_story_copy_branch: PASS")


if __name__ == "__main__":
    verify()
