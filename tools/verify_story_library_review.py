"""Independent story-copy regressions using real SQLite repositories."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from storage.schema import ensure_schema
from storage.repositories.branches import ensure_default_branch
from storage.repositories.knowledge import upsert_knowledge_category_item
from storage.repositories.stories import purge_story_scoped_rows
from storage.repositories.story_reference_libraries import (
    archive_reference_library,
    bind_story_library,
    create_reference_library,
    create_reference_library_release,
    ensure_reference_libraries_for_project,
    resolve_story_reference_context,
    unbind_story_library,
)


def main() -> int:
    failures: list[str] = []
    checks: list[str] = []

    def check(condition: bool, label: str) -> None:
        (checks if condition else failures).append(label)

    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        ensure_schema(conn)
        branches = {}
        for story in ("a", "b"):
            conn.execute("INSERT INTO stories(story_id,name) VALUES (?,?)", (story, story))
            branches[story] = ensure_default_branch(conn, story)["branch_id"]
        item = {
            "id": "project_character", "category": "characters", "name": "共享角色",
            "summary": "ORIGINAL_REFERENCE_FACT", "aliases": ["OldAlias"],
            "setting_scope": "project", "version_scope": "canon", "worldline_id": "original_world",
            "injection_policy": "always", "setting_role": "core", "setting_field": "status",
            "status": "confirmed", "source_origin": "uploaded_material",
            "chapter_no": 3, "source_chapter_no": 3, "valid_from_chapter": 3, "valid_to_chapter": 8,
            "evidence": [{"quote": "ORIGINAL_EVIDENCE_QUOTE", "source_title": "原始资料"}],
        }
        upsert_knowledge_category_item(conn, "characters", item)
        # The repository closes older facts in SQL during supersession. Its
        # editable JSON is not the authority for that historical interval.
        upsert_knowledge_category_item(conn, "characters", {
            **item, "id": "project_character_next", "summary": "LATER_SOURCE_STATE",
            "chapter_no": 8, "source_chapter_no": 8, "valid_from_chapter": 8, "valid_to_chapter": None,
        })
        source_interval = conn.execute("SELECT valid_from_chapter, valid_to_chapter FROM knowledge_items WHERE knowledge_id=?", (item["id"],)).fetchone()
        check(tuple(source_interval) == (3, 8), "fixture has a repository-superseded historical interval")
        library = create_reference_library(conn, project_name="review", title="共享资料")
        release = create_reference_library_release(conn, library_id=library["library_id"], knowledge_ids=[item["id"]])
        bindings = {}
        local_ids = {}
        for story in ("a", "b"):
            bindings[story] = bind_story_library(conn, story_id=story, branch_id=branches[story], library_id=library["library_id"], release_id=release["release_id"])
            local_ids[story] = conn.execute("SELECT local_knowledge_id FROM story_library_item_links WHERE binding_id=?", (bindings[story]["binding_id"],)).fetchone()[0]
        check(len({item["id"], *local_ids.values()}) == 3, "project and two stories have different knowledge IDs")
        row = conn.execute("SELECT * FROM knowledge_items WHERE knowledge_id=?", (local_ids["a"],)).fetchone()
        payload = json.loads(row["content_json"])
        check(payload.get("version_scope") == "canon", "copy preserves source version_scope")
        check(payload.get("aliases") == ["OldAlias"], "copy preserves aliases in editable payload")
        check(row["valid_from_chapter"] == 3 and row["valid_to_chapter"] == 8, "copy preserves complete validity interval")
        check(row["branch_id"] == branches["a"], "copy has target branch identity")
        quotes = [r[0] for r in conn.execute("SELECT quote FROM knowledge_evidence WHERE knowledge_id=?", (local_ids["a"],))]
        check("ORIGINAL_EVIDENCE_QUOTE" in quotes, "copy retains readable evidence quote")
        item["summary"] = "PROJECT_LATER_EDIT"
        upsert_knowledge_category_item(conn, "characters", item)
        check(conn.execute("SELECT summary FROM knowledge_items WHERE knowledge_id=?", (local_ids["a"],)).fetchone()[0] == "ORIGINAL_REFERENCE_FACT", "project edit does not update existing story copy")
        payload.update({"id": local_ids["a"], "story_id": "a", "setting_scope": "story", "branch_id": branches["a"], "summary": "STORY_A_EDIT"})
        upsert_knowledge_category_item(conn, "characters", payload)
        repeated = bind_story_library(conn, story_id="a", branch_id=branches["a"], library_id=library["library_id"], release_id=release["release_id"])
        check(repeated["binding_id"] == bindings["a"]["binding_id"], "repeated binding keeps identity")
        check(conn.execute("SELECT summary FROM knowledge_items WHERE knowledge_id=?", (local_ids["a"],)).fetchone()[0] == "STORY_A_EDIT", "repeated binding preserves local edits")
        check(conn.execute("SELECT summary FROM knowledge_items WHERE knowledge_id=?", (local_ids["b"],)).fetchone()[0] == "ORIGINAL_REFERENCE_FACT", "story A edit does not change story B")
        unbind_story_library(conn, bindings["a"]["binding_id"])
        a_context = resolve_story_reference_context(conn, story_id="a", branch_id=branches["a"])
        b_context = resolve_story_reference_context(conn, story_id="b", branch_id=branches["b"])
        check(local_ids["a"] not in a_context["visible_knowledge_ids"], "unbound copy leaves actual story visibility set")
        check(local_ids["b"] in b_context["visible_knowledge_ids"], "unbinding A keeps B visible")
        # A promoted project fact may retain an evidence chunk first indexed
        # for its source story. Purging that story must not delete the fact's
        # evidence merely because its retrieval projection was story-owned.
        conn.execute("INSERT INTO source_documents(source_id, story_id, title, source_type) VALUES ('shared_source', 'a', 'Imported source', 'creative_attachment')")
        conn.execute("INSERT INTO retrieval_documents(document_id, story_id, source_id, document_type, scope, title) VALUES ('source_doc', 'a', 'shared_source', 'creative_attachment', 'reference', 'Source')")
        conn.execute("INSERT INTO retrieval_chunks(chunk_id, document_id, chunk_index, text) VALUES ('source_chunk', 'source_doc', 0, 'SHARED_CHUNK_EVIDENCE')")
        upsert_knowledge_category_item(conn, "characters", {
            "id": "promoted_fact", "name": "Promoted person", "summary": "Shared fact",
            "setting_scope": "project", "source_id": "shared_source",
            "evidence": [{"quote": "SHARED_CHUNK_EVIDENCE", "source_id": "shared_source", "chunk_id": "source_chunk"}],
        })
        purge_story_scoped_rows(conn, "a")
        check(conn.execute("SELECT count(*) FROM knowledge_evidence WHERE knowledge_id='promoted_fact' AND quote='SHARED_CHUNK_EVIDENCE'").fetchone()[0] == 1, "deleting source story preserves project evidence with a story retrieval chunk")
        discovered = ensure_reference_libraries_for_project(conn, project_name="review")
        source_library = next(entry for entry in discovered if entry.get("source_id") == "shared_source")
        archive_reference_library(conn, source_library["library_id"])
        after_archive = ensure_reference_libraries_for_project(conn, project_name="review")
        check(not any(entry.get("source_id") == "shared_source" for entry in after_archive), "automatic discovery does not resurrect archived libraries")
        conn.execute("INSERT INTO stories(story_id,name) VALUES ('frozen','Frozen')")
        frozen_branch = ensure_default_branch(conn, "frozen")["branch_id"]
        upsert_knowledge_category_item(conn, "relationships", {
            "id": "frozen_relation", "name": "Frozen relation", "summary": "Alice protects Bob",
            "source": "Alice", "target": "Bob", "relation": "protects",
            "setting_scope": "project", "version_scope": "canon",
        })
        frozen_library = create_reference_library(conn, project_name="review", title="Frozen endpoints")
        frozen_release = create_reference_library_release(conn, library_id=frozen_library["library_id"], knowledge_ids=["frozen_relation"])
        conn.execute("UPDATE entities SET canonical_name='PARENT_FUTURE_BOB', display_name='PARENT_FUTURE_BOB', summary='FUTURE_SOURCE_ENTITY' WHERE setting_scope='project' AND canonical_name='Bob'")
        frozen_binding = bind_story_library(conn, story_id="frozen", branch_id=frozen_branch, library_id=frozen_library["library_id"], release_id=frozen_release["release_id"])
        endpoint_names = {row[0] for row in conn.execute("SELECT canonical_name FROM entities WHERE story_id='frozen'")}
        check("Bob" in endpoint_names and "PARENT_FUTURE_BOB" not in endpoint_names, "binding a historical release uses frozen graph endpoint identities")
        check(conn.execute("SELECT count(*) FROM graph_edges WHERE story_id='frozen' AND deleted_at IS NULL AND relation_type='protects'").fetchone()[0] == 1, "historical relationship remains connected to its frozen endpoints")
        temporal_release = create_reference_library_release(conn, library_id=frozen_library["library_id"], knowledge_ids=["project_character", "project_character_next"])
        conn.execute("INSERT INTO stories(story_id,name) VALUES ('temporal','Temporal')")
        temporal_branch = ensure_default_branch(conn, "temporal")["branch_id"]
        temporal_binding = bind_story_library(conn, story_id="temporal", branch_id=temporal_branch, library_id=frozen_library["library_id"], release_id=temporal_release["release_id"])
        temporal_ids = {item["origin_knowledge_id"]: item["local_knowledge_id"] for item in temporal_binding["items"]}
        check(conn.execute("SELECT superseded_by FROM knowledge_items WHERE knowledge_id=?", (temporal_ids["project_character"],)).fetchone()[0] == temporal_ids["project_character_next"], "library copy remaps temporal successor to the local story fact")
        for kid, owner, owner_branch in [("default_version_project", None, None), ("default_version_story", "frozen", frozen_branch)]:
            upsert_knowledge_category_item(conn, "world_rules", {"id": kid, "name": "Default version rule", "summary": "DEFAULT_VERSION", "worldline_id": "main", "setting_scope": "story" if owner else "project", "story_id": owner, "branch_id": owner_branch})
        default_library = create_reference_library(conn, project_name="review", title="Default version compatibility")
        default_release = create_reference_library_release(conn, library_id=default_library["library_id"], knowledge_ids=["default_version_project"])
        default_binding = bind_story_library(conn, story_id="frozen", branch_id=frozen_branch, library_id=default_library["library_id"], release_id=default_release["release_id"])
        check(bool(default_binding["items"]), "omitted legacy version_scope cannot cause a duplicate entity identity on binding")
    print(json.dumps({"ok": not failures, "checks": checks, "failures": failures}, ensure_ascii=False, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
