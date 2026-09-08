"""Offline verification for immutable project releases and story-local copies."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage.db import open_existing_project_db, open_project_db
from storage.repositories.knowledge import upsert_knowledge_category_item
from storage.repositories.stories import purge_story_scoped_rows
from storage.repositories.story_reference_libraries import (
    bind_story_library,
    create_reference_library,
    create_reference_library_release,
    load_reference_library_release_sources,
    load_story_reference_state,
    resolve_story_reference_context,
    unbind_story_library,
)
from novelforge.services.memory import create_project, create_story
from novelforge.services.memory.project_registry import project_path
from novelforge.workflows.creative_attachments import import_creative_pasted_text
from tools.verify_utils import isolated_workspace


def _insert_story(conn: sqlite3.Connection, story_id: str, name: str) -> None:
    conn.execute(
        "INSERT INTO stories (story_id, name, status, is_active) VALUES (?, ?, 'active', 0)",
        (story_id, name),
    )
    conn.execute(
        """
        INSERT INTO story_branches
            (branch_id, story_id, name, description, source_worldline_id)
        VALUES (?, ?, '主线', '', 'main')
        """,
        (f"branch_{story_id}", story_id),
    )


def verify() -> None:
    with tempfile.TemporaryDirectory(prefix="_verify_story_library_") as temp:
        fixture_db_path = Path(temp)
        with open_project_db(fixture_db_path) as conn:
            conn.execute("INSERT INTO project_meta (project_id, name) VALUES ('verify', 'verify')")
            _insert_story(conn, "story_a", "A")
            _insert_story(conn, "story_b", "B")
            _insert_story(conn, "story_c", "C")
            conn.execute(
                """
                INSERT INTO source_documents
                    (source_id, story_id, title, source_type, content_hash, metadata_json)
                VALUES ('source_shared', 'story_a', '共享原文', 'text', 'source-hash', '{}')
                """
            )
            conn.execute(
                """
                INSERT INTO source_revisions
                    (revision_id, source_id, content_hash, char_count, metadata_json)
                VALUES ('source_rev_1', 'source_shared', 'source-hash', 3, '{}')
                """
            )
            conn.execute(
                """
                INSERT INTO source_segments
                    (segment_id, source_id, segment_index, title, text_hash, source_revision_id)
                VALUES ('segment_1', 'source_shared', 1, '第一段', 'segment-hash', 'source_rev_1')
                """
            )
            item = {
                "id": "origin_knowledge",
                "category": "characters",
                "name": "林越",
                "title": "林越",
                "summary": "公共资料中的角色",
                "setting_scope": "project",
                "version_scope": "canon",
                "aliases": ["林公子"],
                "source_id": "source_shared",
                "source_segment_id": "segment_1",
                "source_revision_id": "source_rev_1",
                "evidence": [{"quote": "林越在城门前停下。", "start_offset": 0, "end_offset": 9}],
                "evidence_contexts": [{"quote": "林越在城门前停下。", "start_offset": 0, "end_offset": 9}],
                "status": "confirmed",
                "typed_data": {"occupation": "斥候"},
            }
            conn.execute(
                """
                INSERT INTO entity_alias_groups
                    (alias_group_id, canonical_name, aliases_json, entity_type, worldline_id, metadata_json)
                VALUES ('alias_linyue_main', '林越', '[\"林公子\"]', 'character', NULL, ?)
                """,
                (json.dumps({"knowledge_id": "origin_knowledge"}, ensure_ascii=False),),
            )
            upsert_knowledge_category_item(conn, "characters", item)
            origin_entity_id = conn.execute(
                "SELECT entity_id FROM knowledge_items WHERE knowledge_id = 'origin_knowledge'"
            ).fetchone()[0]
            conn.execute(
                "UPDATE entities SET alias_group_id = 'alias_linyue_main' WHERE entity_id = ?",
                (origin_entity_id,),
            )
            conn.commit()

            library = create_reference_library(conn, project_name="verify", title="原著资料")
            release = create_reference_library_release(
                conn,
                library_id=library["library_id"],
                knowledge_ids=["origin_knowledge"],
            )
            conn.commit()
            source_snapshot = load_reference_library_release_sources(conn, release_id=release["release_id"])
            assert source_snapshot and source_snapshot[0]["source_json"]["title"] == "共享原文"
            assert source_snapshot[0]["segments_json"][0]["segment_id"] == "segment_1"

            # One release may cite two historical revisions of the same
            # source; neither revision may overwrite the other in the frozen
            # evidence table.
            conn.execute(
                """
                INSERT INTO source_revisions
                    (revision_id, source_id, content_hash, char_count, metadata_json)
                VALUES ('source_rev_2', 'source_shared', 'source-hash-2', 4, '{}')
                """
            )
            conn.execute(
                """
                INSERT INTO source_segments
                    (segment_id, source_id, segment_index, title, text_hash, source_revision_id)
                VALUES ('segment_2', 'source_shared', 2, '第二段', 'segment-hash-2', 'source_rev_2')
                """
            )
            revision_item = {
                **item,
                "id": "origin_revision_two",
                "title": "林越（修订）",
                "summary": "同一资料的历史修订知识",
                "source_segment_id": "segment_2",
                "source_revision_id": "source_rev_2",
            }
            upsert_knowledge_category_item(conn, "characters", revision_item)
            history_library = create_reference_library(conn, project_name="verify", title="历史版本资料")
            history_release = create_reference_library_release(
                conn,
                library_id=history_library["library_id"],
                knowledge_ids=["origin_knowledge", "origin_revision_two"],
            )
            history_sources = load_reference_library_release_sources(conn, release_id=history_release["release_id"], source_id="source_shared")
            assert {str(row["revision_id"]) for row in history_sources} == {"source_rev_1", "source_rev_2"}

            a = bind_story_library(
                conn,
                story_id="story_a",
                library_id=library["library_id"],
                release_id=release["release_id"],
                branch_id="branch_story_a",
            )
            b = bind_story_library(
                conn,
                story_id="story_b",
                library_id=library["library_id"],
                release_id=release["release_id"],
                branch_id="branch_story_b",
            )
            conn.commit()
            assert a["status"] == b["status"] == "ready"
            assert load_story_reference_state(conn, story_id="story_a")["read_mode"] == "strict"
            assert a["items"][0]["local_knowledge_id"] != b["items"][0]["local_knowledge_id"]
            a_local = conn.execute(
                "SELECT * FROM knowledge_items WHERE knowledge_id = ?",
                (a["items"][0]["local_knowledge_id"],),
            ).fetchone()
            assert a_local["setting_scope"] == "story"
            assert a_local["branch_id"] == "branch_story_a"
            payload = json.loads(a_local["content_json"])
            assert payload["_story_library"]["origin_knowledge_id"] == "origin_knowledge"
            assert payload["_story_library"]["source_revision_id"] == "source_rev_1"
            assert payload["aliases"] == ["林公子"]
            assert conn.execute(
                "SELECT COUNT(*) FROM knowledge_evidence WHERE knowledge_id = ?",
                (a["items"][0]["local_knowledge_id"],),
            ).fetchone()[0] == 1

            context_a = resolve_story_reference_context(conn, story_id="story_a", branch_id="branch_story_a")
            context_b = resolve_story_reference_context(conn, story_id="story_b", branch_id="branch_story_b")
            assert a["items"][0]["local_knowledge_id"] in context_a["visible_knowledge_ids"]
            assert b["items"][0]["local_knowledge_id"] in context_b["visible_knowledge_ids"]
            assert a["items"][0]["local_knowledge_id"] not in context_b["visible_knowledge_ids"]
            assert context_a["raw_sources_allowed"] is False

            # Repeating the same bind is idempotent and does not replace local edits.
            same_a = bind_story_library(
                conn,
                story_id="story_a",
                library_id=library["library_id"],
                release_id=release["release_id"],
                branch_id="branch_story_a",
            )
            assert same_a["binding_id"] == a["binding_id"]
            conn.execute(
                "UPDATE knowledge_items SET summary = 'A 的本地修改' WHERE knowledge_id = ?",
                (a["items"][0]["local_knowledge_id"],),
            )

            # Source edits after release do not alter B's frozen copy.
            item["summary"] = "公共资料的新版本"
            upsert_knowledge_category_item(conn, "characters", item)
            b_local = conn.execute(
                "SELECT summary FROM knowledge_items WHERE knowledge_id = ?",
                (b["items"][0]["local_knowledge_id"],),
            ).fetchone()[0]
            assert b_local == "公共资料中的角色"

            unbind_story_library(conn, a["binding_id"])
            conn.commit()
            assert a["items"][0]["local_knowledge_id"] not in resolve_story_reference_context(
                conn, story_id="story_a", branch_id="branch_story_a"
            )["visible_knowledge_ids"]
            assert b["items"][0]["local_knowledge_id"] in resolve_story_reference_context(
                conn, story_id="story_b", branch_id="branch_story_b"
            )["visible_knowledge_ids"]

            # Story cleanup must preserve a project copy's evidence and source.
            purge_story_scoped_rows(conn, "story_a")
            assert conn.execute("SELECT deleted_at FROM source_documents WHERE source_id = 'source_shared'").fetchone()[0] is None
            assert load_reference_library_release_sources(conn, release_id=release["release_id"])[0]["source_json"]["title"] == "共享原文"
            assert conn.execute(
                "SELECT COUNT(*) FROM knowledge_evidence WHERE knowledge_id = 'origin_knowledge'"
            ).fetchone()[0] == 1
            assert conn.execute(
                "SELECT summary FROM knowledge_items WHERE knowledge_id = ?",
                (b["items"][0]["local_knowledge_id"],),
            ).fetchone()[0] == "公共资料中的角色"

            # Rebinding after cleanup creates a new binding and does not revive
            # A's deleted local row or overwrite B.
            rebound = bind_story_library(
                conn,
                story_id="story_a",
                library_id=library["library_id"],
                release_id=release["release_id"],
                branch_id="branch_story_a",
            )
            assert rebound["binding_id"] != a["binding_id"]
            rebound_row = conn.execute(
                "SELECT deleted_at FROM knowledge_items WHERE knowledge_id = ?",
                (rebound["items"][0]["local_knowledge_id"],),
            ).fetchone()
            assert rebound_row is None or rebound_row[0] is not None

            # Copy aliases and relationship endpoints from the real entity and
            # graph tables. Same-name entities on another worldline must stay
            # distinct, and edge mapping must use endpoint identity.
            for alias_id, canonical_name, worldline, aliases in (
                ("alias_linyue_alt", "林越", "alt", ["林二公子"]),
                ("alias_suhuai", "苏槐", None, ["苏先生"]),
            ):
                conn.execute(
                    """
                    INSERT INTO entity_alias_groups
                        (alias_group_id, canonical_name, aliases_json, entity_type, worldline_id, metadata_json)
                    VALUES (?, ?, ?, 'character', ?, '{}')
                    """,
                    (alias_id, canonical_name, json.dumps(aliases, ensure_ascii=False), worldline),
                )
            entity_items = [
                {
                    "id": "origin_linyue_alt", "category": "characters", "name": "林越",
                    "title": "林越（另一世界线）", "summary": "另一世界线的林越",
                    "setting_scope": "project", "version_scope": "canon", "worldline_id": "alt",
                    "source_id": "source_shared", "source_segment_id": "segment_1", "source_revision_id": "source_rev_1",
                    "aliases": ["林二公子"], "status": "confirmed",
                },
                {
                    "id": "origin_suhuai", "category": "characters", "name": "苏槐",
                    "title": "苏槐", "summary": "林越的同伴", "setting_scope": "project", "version_scope": "canon",
                    "source_id": "source_shared", "source_segment_id": "segment_1", "source_revision_id": "source_rev_1",
                    "aliases": ["苏先生"], "status": "confirmed",
                },
                {
                    "id": "origin_relation_main", "category": "relationships", "name": "林越保护苏槐",
                    "summary": "主世界线关系", "source": "林越", "target": "苏槐", "relation": "protects",
                    "setting_scope": "project", "version_scope": "canon", "source_id": "source_shared",
                    "source_segment_id": "segment_1", "source_revision_id": "source_rev_1", "status": "confirmed",
                },
                {
                    "id": "origin_relation_alt", "category": "relationships", "name": "林越另一世界线保护苏槐",
                    "summary": "另一世界线关系", "source": "林越", "target": "苏槐", "relation": "protects_alt",
                    "worldline_id": "alt", "setting_scope": "project", "version_scope": "canon",
                    "source_id": "source_shared", "source_segment_id": "segment_1", "source_revision_id": "source_rev_1", "status": "confirmed",
                },
            ]
            for entity_item in entity_items:
                upsert_knowledge_category_item(conn, entity_item["category"], entity_item)
            conn.execute(
                "UPDATE entities SET alias_group_id = 'alias_linyue_alt' WHERE entity_id = (SELECT entity_id FROM knowledge_items WHERE knowledge_id = 'origin_linyue_alt')"
            )
            conn.execute(
                "UPDATE entities SET alias_group_id = 'alias_suhuai' WHERE entity_id = (SELECT entity_id FROM knowledge_items WHERE knowledge_id = 'origin_suhuai')"
            )
            graph_library = create_reference_library(conn, project_name="verify", title="关系资料")
            graph_release = create_reference_library_release(
                conn,
                library_id=graph_library["library_id"],
                knowledge_ids=["origin_linyue_alt", "origin_suhuai", "origin_relation_main", "origin_relation_alt"],
            )
            graph_binding = bind_story_library(
                conn,
                story_id="story_c",
                library_id=graph_library["library_id"],
                release_id=graph_release["release_id"],
                branch_id="branch_story_c",
            )
            conn.commit()
            c_linyue_entities = conn.execute(
                """
                SELECT e.entity_id, e.worldline_id, e.alias_group_id, a.aliases_json
                FROM entities AS e
                LEFT JOIN entity_alias_groups AS a ON a.alias_group_id = e.alias_group_id
                WHERE e.story_id = 'story_c' AND e.canonical_name = '林越' AND e.deleted_at IS NULL
                ORDER BY e.worldline_id
                """
            ).fetchall()
            assert len(c_linyue_entities) == 2
            assert c_linyue_entities[0][0] != c_linyue_entities[1][0]
            assert any("林二公子" in str(row[3] or "") for row in c_linyue_entities)
            relation_local_ids = {
                str(entry["origin_knowledge_id"]): str(entry["local_knowledge_id"])
                for entry in graph_binding["items"]
                if str(entry["origin_knowledge_id"]).startswith("origin_relation")
            }
            assert len(relation_local_ids) == 2
            copied_edges = conn.execute(
                """
                SELECT source_node_id, target_node_id, relation_type
                FROM graph_edges
                WHERE story_id = 'story_c' AND deleted_at IS NULL
                  AND json_extract(metadata_json, '$.knowledge_id') IN (?, ?)
                ORDER BY relation_type
                """,
                (relation_local_ids["origin_relation_alt"], relation_local_ids["origin_relation_main"]),
            ).fetchall()
            assert len(copied_edges) == 2
            assert copied_edges[0][0] != copied_edges[1][0]
            assert all(row[1] != row[0] for row in copied_edges)

        # Exercise the production pasted-material path.  The source ledger
        # keeps the JSON container hash while the revision metadata carries a
        # separately verifiable hash of the parsed body.  A release must keep
        # the readable historical body even when the live source is removed.
        with isolated_workspace("_verify_story_library_source_"):
            real_project = "verify_real_pasted_source"
            create_project(real_project)
            real_story = create_story(real_project, "真实资料故事")
            attachment = import_creative_pasted_text(
                real_project,
                str(real_story["story_id"]),
                "",
                "岚秋的秘密口令是银铃渡口。",
                title="真实粘贴资料",
                scope="project",
                schedule_knowledge=False,
            )
            source_id = str(attachment["source_id"])
            with open_existing_project_db(project_path(real_project)) as real_conn:
                segment_id = str(real_conn.execute(
                    "SELECT segment_id FROM source_segments WHERE source_id = ? AND deleted_at IS NULL",
                    (source_id,),
                ).fetchone()[0])
                real_item = {
                    "id": "real_project_knowledge",
                    "category": "characters",
                    "name": "岚秋",
                    "title": "岚秋",
                    "summary": "真实粘贴资料中的角色",
                    "setting_scope": "project",
                    "version_scope": "project_main",
                    "source_id": source_id,
                    "source_segment_id": segment_id,
                    "source_revision_id": str(attachment["source_revision_id"]),
                    "evidence": [{"quote": "岚秋的秘密口令是银铃渡口。", "start_offset": 0, "end_offset": 15}],
                    "status": "confirmed",
                    "typed_data": {"secret": "银铃渡口"},
                }
                upsert_knowledge_category_item(real_conn, "characters", real_item)
                real_library = create_reference_library(real_conn, project_name=real_project, title="真实粘贴资料库")
                real_release = create_reference_library_release(
                    real_conn,
                    library_id=real_library["library_id"],
                    knowledge_ids=["real_project_knowledge"],
                )
                real_conn.commit()
                snapshots = load_reference_library_release_sources(
                    real_conn,
                    release_id=real_release["release_id"],
                    source_id=source_id,
                )
                assert len(snapshots) == 1
                assert snapshots[0]["snapshot_status"] == "complete"
                assert snapshots[0]["content_hash_verified"] == 1
                assert "银铃渡口" in snapshots[0]["revision_json"]["raw_text"]
                real_conn.execute(
                    "UPDATE source_documents SET deleted_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE source_id = ?",
                    (source_id,),
                )
                real_conn.commit()
                frozen_after_delete = load_reference_library_release_sources(
                    real_conn,
                    release_id=real_release["release_id"],
                    source_id=source_id,
                )
                assert "银铃渡口" in frozen_after_delete[0]["revision_json"]["raw_text"]
        print("verify_story_library: PASS")


if __name__ == "__main__":
    verify()
