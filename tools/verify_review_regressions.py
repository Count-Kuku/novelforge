from __future__ import annotations

import json
import os
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = "0"

from novelforge.domain import knowledge_entities, knowledge_quality
import novelforge.services.memory as memory_module
import novelforge.services.project_manager as project_manager_module
import novelforge.services.retrieval as retrieval_module
import storage.schema as storage_schema
from novelforge.services.memory import (
    copy_story,
    create_project,
    create_story,
    delete_story,
    load_project_registry,
    list_stories,
    list_pipeline_run_summaries,
    load_chapter,
    load_memory,
    load_pipeline_run,
    load_retrieval_manifest,
    load_retrieval_vectors,
    load_review_json,
    load_story_chapter_summaries,
    load_story_prompt_options,
    normalize_project_name,
    pending_knowledge_path,
    project_path,
    knowledge_category_path,
    queue_pending_knowledge_items,
    save_chapter,
    save_memory,
    save_pipeline_run,
    save_retrieval_manifest,
    save_retrieval_vectors,
    save_review_json,
    save_story_chapter_summaries,
    save_story_prompt_options,
    upsert_knowledge_category_item_record,
)
from novelforge.services.project_manager import rename_project
from novelforge.services.retrieval import build_retrieval_index
from novelforge.workflows.source_workflows import split_long_reference_text
from storage import open_project_db
from storage.repositories import (
    load_knowledge_category_rows,
    load_pending_knowledge_rows,
    upsert_knowledge_category_item,
    upsert_pending_knowledge_items,
)
from tools.verify_utils import isolated_workspace, make_workspace, retry_rmtree


def _expect(condition: bool, label: str, failures: list[str]) -> None:
    if not condition:
        failures.append(label)


def _expect_raises(callback, exception_type: type[BaseException], label: str, failures: list[str]) -> None:
    try:
        callback()
    except exception_type:
        return
    except Exception as exc:
        failures.append(f"{label}:wrong_exception:{type(exc).__name__}")
        return
    failures.append(f"{label}:missing_exception")


def _verify_storage_and_story_guards(failures: list[str]) -> None:
    _expect_raises(lambda: normalize_project_name("."), ValueError, "project_dot_rejected", failures)
    _expect_raises(lambda: normalize_project_name("CON"), ValueError, "project_reserved_name_rejected", failures)
    _expect_raises(lambda: normalize_project_name("bad*name"), ValueError, "project_invalid_char_rejected", failures)

    project_name = "review_guards"
    create_project(project_name)
    story_a = create_story(project_name, "Story A")["story_id"]
    story_b = create_story(project_name, "Story B")["story_id"]

    shared_id = "same-logical-option"
    save_story_prompt_options(project_name, story_a, [{"id": shared_id, "name": "A", "content": "alpha"}])
    save_story_prompt_options(project_name, story_b, [{"id": shared_id, "name": "B", "content": "beta"}])
    _expect(load_story_prompt_options(project_name, story_a)[0]["content"] == "alpha", "prompt_story_a_isolated", failures)
    _expect(load_story_prompt_options(project_name, story_b)[0]["content"] == "beta", "prompt_story_b_isolated", failures)

    source_posix_path = f"stories/{story_a}/chapters/chapter_001.md"
    source_windows_path = rf"D:\Novel Forge\stories\{story_a}\exports\chapter_001.md"
    source_standalone_path = rf"stories\{story_a}\artifacts\chapter_001.json"
    source_path_in_prose = f"说明文字保留 stories/{story_a}/examples/sample.md，不是实际路径。"
    workflow_payload = {
        "run_id": "strict-run",
        "story_id": story_a,
        "saved_path": source_posix_path,
        "outputPaths": [source_windows_path],
        "artifact_ref": source_standalone_path,
        "note": source_path_in_prose,
        "steps": {
            "persist": {
                "status": "completed",
                "output_path": source_posix_path,
                "artifact_ref": source_standalone_path,
                "note": source_path_in_prose,
            }
        },
    }
    save_pipeline_run(project_name, "strict-run", json.dumps(workflow_payload), story_id=story_a)
    _expect(load_pipeline_run(project_name, "strict-run", story_id=story_b) == "", "workflow_cross_story_read_rejected", failures)
    _expect(bool(load_pipeline_run(project_name, "strict-run", story_id=story_a)), "workflow_owner_read_preserved", failures)

    save_chapter(project_name, 1, "source chapter", story_id=story_a)
    save_review_json(project_name, 1, {"score": 99}, story_id=story_a)
    save_story_chapter_summaries(project_name, story_a, [{"chapter_no": 1, "summary": "source summary"}])
    copied = copy_story(project_name, story_a, "Story A Copy")
    copied_id = copied["story_id"]
    _expect(load_chapter(project_name, 1, story_id=copied_id) == "source chapter", "story_copy_chapter", failures)
    _expect((load_review_json(project_name, 1, story_id=copied_id) or {}).get("score") == 99, "story_copy_review_payload", failures)
    _expect(load_story_chapter_summaries(project_name, copied_id)[0]["summary"] == "source summary", "story_copy_summary", failures)
    copied_runs = list_pipeline_run_summaries(project_name, story_id=copied_id)
    _expect(bool(copied_runs), "story_copy_workflow", failures)
    copied_run_id = copied_runs[0]["run_id"]
    copied_payload = json.loads(load_pipeline_run(project_name, copied_run_id, story_id=copied_id))
    target_posix_path = f"stories/{copied_id}/chapters/chapter_001.md"
    target_windows_path = rf"D:\Novel Forge\stories\{copied_id}\exports\chapter_001.md"
    target_standalone_path = rf"stories\{copied_id}\artifacts\chapter_001.json"
    _expect(copied_payload.get("saved_path") == target_posix_path, "story_copy_rewrites_posix_path_field", failures)
    _expect(copied_payload.get("outputPaths") == [target_windows_path], "story_copy_rewrites_windows_path_list", failures)
    _expect(copied_payload.get("artifact_ref") == target_standalone_path, "story_copy_rewrites_standalone_path_value", failures)
    _expect(copied_payload.get("note") == source_path_in_prose, "story_copy_preserves_path_text_in_prose", failures)
    with open_project_db(project_path(project_name).resolve()) as conn:
        copied_step_row = conn.execute(
            "SELECT output_json FROM workflow_steps WHERE run_id = ? AND step_name = 'persist'",
            (copied_run_id,),
        ).fetchone()
    copied_step = json.loads(copied_step_row["output_json"]) if copied_step_row else {}
    _expect(copied_step.get("output_path") == target_posix_path, "story_copy_rewrites_step_path_field", failures)
    _expect(copied_step.get("artifact_ref") == target_standalone_path, "story_copy_rewrites_step_standalone_path", failures)
    _expect(copied_step.get("note") == source_path_in_prose, "story_copy_preserves_step_prose", failures)

    with open_project_db(project_path(project_name).resolve()) as conn:
        conn.execute(
            "INSERT INTO source_documents (source_id, story_id, title, source_type) VALUES (?, ?, ?, ?)",
            ("indirect-source", story_a, "Indirect source", "reference"),
        )
        conn.execute(
            "INSERT INTO source_segments (segment_id, source_id, segment_index) VALUES (?, ?, ?)",
            ("indirect-segment", "indirect-source", 1),
        )
        conn.execute(
            "INSERT INTO retrieval_documents (document_id, story_id, document_type) VALUES (?, ?, ?)",
            ("indirect-document", story_a, "reference"),
        )
        conn.execute(
            "INSERT INTO retrieval_chunks (chunk_id, document_id, chunk_index, text) VALUES (?, ?, ?, ?)",
            ("indirect-chunk", "indirect-document", 1, "indirect"),
        )
        conn.execute(
            "INSERT INTO knowledge_evidence (evidence_id, segment_id) VALUES (?, ?)",
            ("segment-only-evidence", "indirect-segment"),
        )
        conn.execute(
            "INSERT INTO knowledge_evidence (evidence_id, chunk_id) VALUES (?, ?)",
            ("chunk-only-evidence", "indirect-chunk"),
        )
        conn.execute(
            "INSERT INTO retrieval_feedback (feedback_id, chunk_id, feedback_type) VALUES (?, ?, ?)",
            ("legacy-chunk-feedback", "indirect-chunk", "wrong"),
        )
        conn.commit()

    _expect(delete_story(project_name, story_a), "story_delete_returns_true", failures)
    with open_project_db(project_path(project_name).resolve()) as conn:
        indirect_rows = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM knowledge_evidence
                 WHERE evidence_id IN ('segment-only-evidence', 'chunk-only-evidence')) AS evidence_count,
                (SELECT COUNT(*) FROM retrieval_feedback
                 WHERE feedback_id = 'legacy-chunk-feedback') AS feedback_count
            """
        ).fetchone()
    _expect(
        bool(indirect_rows)
        and indirect_rows["evidence_count"] == 0
        and indirect_rows["feedback_count"] == 0,
        "story_delete_purges_indirect_evidence_and_feedback",
        failures,
    )
    recreated_id = create_story(project_name, "Story A")["story_id"]
    _expect(recreated_id == story_a, "story_id_reused_for_purge_check", failures)
    _expect(load_review_json(project_name, 1, story_id=recreated_id) is None, "deleted_story_payload_not_revived", failures)
    _expect(load_story_chapter_summaries(project_name, recreated_id) == [], "deleted_story_summary_not_revived", failures)

    with open_project_db(project_path(project_name).resolve()) as conn:
        pass
    _expect_raises(lambda: conn.execute("SELECT 1"), sqlite3.ProgrammingError, "db_context_closes_connection", failures)

    def concurrent_upsert(item_id: str) -> None:
        with open_project_db(project_path(project_name).resolve()) as thread_conn:
            upsert_knowledge_category_item(
                thread_conn,
                "characters",
                {"id": item_id, "name": item_id, "category": "characters"},
            )
            thread_conn.commit()

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(concurrent_upsert, ["concurrent-a", "concurrent-b"]))
    with open_project_db(project_path(project_name).resolve()) as conn:
        concurrent_ids = {item.get("id") for item in load_knowledge_category_rows(conn, "characters")}
    _expect({"concurrent-a", "concurrent-b"}.issubset(concurrent_ids), "concurrent_setting_upserts_do_not_lose_rows", failures)

    def concurrent_pending(pending_id: str) -> None:
        with open_project_db(project_path(project_name).resolve()) as thread_conn:
            upsert_pending_knowledge_items(
                thread_conn,
                [{"pending_id": pending_id, "category": "items", "name": pending_id, "status": "pending"}],
            )
            thread_conn.commit()

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(concurrent_pending, ["pending-a", "pending-b"]))
    with open_project_db(project_path(project_name).resolve()) as conn:
        pending_ids = {item.get("pending_id") for item in load_pending_knowledge_rows(conn)}
    _expect({"pending-a", "pending-b"}.issubset(pending_ids), "concurrent_pending_upserts_do_not_lose_rows", failures)

    reserved_story = create_story(project_name, "CON")
    _expect(reserved_story.get("story_id") == "story_con", "reserved_story_name_gets_safe_slug", failures)
    _expect(
        memory_module.story_path(project_name, reserved_story["story_id"]).is_dir(),
        "reserved_story_directory_created",
        failures,
    )

    rollback_story_path = memory_module.story_path(project_name, "rollback_story")
    with patch.object(memory_module, "sync_stories_index", side_effect=OSError("injected create failure")):
        _expect_raises(
            lambda: memory_module.create_story(project_name, "Rollback Story"),
            OSError,
            "story_create_failure_propagates",
            failures,
        )
    _expect(not rollback_story_path.exists(), "story_create_failure_removes_directory", failures)
    _expect(
        "rollback_story" not in {item.get("story_id") for item in list_stories(project_name)},
        "story_create_failure_leaves_no_index_row",
        failures,
    )

    stale_category_mirror = knowledge_category_path(project_name, "items")
    stale_category_mirror.parent.mkdir(parents=True, exist_ok=True)
    stale_category_mirror.write_text("[]", encoding="utf-8")
    upsert_knowledge_category_item_record(
        project_name,
        "items",
        {"id": "mirror-cleanup", "name": "Mirror Cleanup", "category": "items"},
    )
    _expect(not stale_category_mirror.exists(), "atomic_upsert_removes_stale_category_mirror", failures)

    stale_pending_mirror = pending_knowledge_path(project_name)
    stale_pending_mirror.parent.mkdir(parents=True, exist_ok=True)
    stale_pending_mirror.write_text("[]", encoding="utf-8")
    queue_pending_knowledge_items(
        project_name,
        [{"pending_id": "mirror-pending", "category": "items", "name": "Mirror Pending"}],
        scope="project",
        authority="curated",
    )
    _expect(not stale_pending_mirror.exists(), "atomic_pending_upsert_removes_stale_mirror", failures)

    upsert_knowledge_category_item_record(
        project_name,
        "locations",
        {"id": "locations_0001", "name": "One", "category": "locations"},
    )
    upsert_knowledge_category_item_record(
        project_name,
        "locations",
        {"id": "locations_0003", "name": "Three", "category": "locations"},
    )
    memory_module.append_knowledge_items_with_records(
        project_name,
        [{"category": "locations", "name": "After Gap"}],
        scope="project",
        authority="curated",
    )
    with open_project_db(project_path(project_name).resolve()) as conn:
        location_rows = load_knowledge_category_rows(conn, "locations")
    location_ids = {item.get("id") for item in location_rows}
    _expect("locations_0003" in location_ids, "append_after_id_gap_preserves_existing_row", failures)
    _expect(
        len(location_ids) == 3 and any(item.get("name") == "After Gap" for item in location_rows),
        "append_after_id_gap_uses_noncolliding_id",
        failures,
    )

    with open_project_db(project_path(project_name).resolve()) as conn:
        upsert_pending_knowledge_items(
            conn,
            [
                {
                    "pending_id": "confirm-valid",
                    "category": "items",
                    "name": "Confirmed Item",
                    "scope": "project",
                    "authority": "curated",
                    "status": "pending",
                },
                {
                    "pending_id": "confirm-invalid",
                    "category": "items",
                    "name": "",
                    "scope": "project",
                    "authority": "curated",
                    "status": "pending",
                },
            ],
        )
        conn.commit()
    confirmation = memory_module.confirm_pending_knowledge_items_with_records(
        project_name,
        ["confirm-valid", "confirm-invalid"],
    )
    _expect(confirmation.get("saved_count") == 1, "confirm_saves_only_valid_pending_rows", failures)
    _expect(
        confirmation.get("skipped_pending_ids") == ["confirm-invalid"],
        "confirm_reports_skipped_pending_rows",
        failures,
    )
    with open_project_db(project_path(project_name).resolve()) as conn:
        pending_after_confirm = {item.get("pending_id") for item in load_pending_knowledge_rows(conn)}
    _expect(
        "confirm-invalid" in pending_after_confirm and "confirm-valid" not in pending_after_confirm,
        "confirm_keeps_invalid_pending_row",
        failures,
    )

    with open_project_db(project_path(project_name).resolve()) as conn:
        upsert_pending_knowledge_items(
            conn,
            [{
                "pending_id": "confirm-rollback",
                "category": "items",
                "name": "Rollback Candidate",
                "scope": "project",
                "authority": "curated",
                "status": "pending",
            }],
        )
        conn.commit()
    with patch.object(memory_module, "sync_pending_knowledge", side_effect=OSError("injected pending failure")):
        _expect_raises(
            lambda: memory_module.confirm_pending_knowledge_items_with_records(
                project_name,
                ["confirm-rollback"],
            ),
            OSError,
            "confirm_transaction_failure_propagates",
            failures,
        )
    with open_project_db(project_path(project_name).resolve()) as conn:
        pending_after_rollback = {item.get("pending_id") for item in load_pending_knowledge_rows(conn)}
        item_rows_after_rollback = load_knowledge_category_rows(conn, "items")
    _expect(
        "confirm-rollback" in pending_after_rollback,
        "confirm_transaction_failure_restores_pending",
        failures,
    )
    _expect(
        not any(item.get("source_pending_id") == "confirm-rollback" for item in item_rows_after_rollback),
        "confirm_transaction_failure_rolls_back_knowledge",
        failures,
    )

    def concurrent_append(name: str) -> None:
        memory_module.append_knowledge_items_with_records(
            project_name,
            [{"category": "organizations", "name": name}],
            scope="project",
            authority="curated",
        )

    with patch.object(memory_module, "sync_project_retrieval_assets", return_value=None):
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(concurrent_append, ["Concurrent Org A", "Concurrent Org B"]))
    with open_project_db(project_path(project_name).resolve()) as conn:
        organization_names = {item.get("name") for item in load_knowledge_category_rows(conn, "organizations")}
    _expect(
        {"Concurrent Org A", "Concurrent Org B"}.issubset(organization_names),
        "concurrent_knowledge_appends_do_not_lose_rows",
        failures,
    )

    with open_project_db(project_path(project_name).resolve()) as conn:
        _expect_raises(
            lambda: upsert_knowledge_category_item(
                conn,
                "items",
                {"id": "orphan-story", "name": "Orphan", "story_id": "missing-story"},
            ),
            ValueError,
            "knowledge_unknown_story_rejected",
            failures,
        )


def _verify_project_rename_and_legacy_bootstrap(failures: list[str]) -> None:
    create_project("rename_source")
    memory_payload = load_memory("rename_source")
    memory_payload.update({"title": "Custom Title", "genre": "Custom Genre"})
    save_memory("rename_source", memory_payload)
    rename_project("rename_source", "rename_target")
    renamed = load_memory("rename_target")
    _expect(renamed.get("title") == "Custom Title", "rename_preserves_title", failures)
    _expect(renamed.get("genre") == "Custom Genre", "rename_preserves_genre", failures)

    create_project("rename_retrieval_failure")
    with patch.object(
        project_manager_module,
        "sync_project_retrieval_assets",
        side_effect=OSError("injected retrieval rebuild failure"),
    ):
        renamed_after_retrieval_failure = rename_project("rename_retrieval_failure", "rename_retrieval_done")
    _expect(
        renamed_after_retrieval_failure == "rename_retrieval_done"
        and project_path("rename_retrieval_done").is_dir(),
        "derived_retrieval_failure_keeps_core_rename",
        failures,
    )
    _expect(
        "rename_retrieval_done" in {item.get("name") for item in load_project_registry().get("projects", [])},
        "derived_retrieval_failure_keeps_registry_rename",
        failures,
    )

    create_project("rename_core_source")
    core_registry_snapshot = load_project_registry()
    original_registry_rename = project_manager_module.rename_registered_project

    def mutate_registry_then_fail(old_name: str, new_name: str) -> str:
        original_registry_rename(old_name, new_name)
        raise OSError("injected registry failure")

    with patch.object(
        project_manager_module,
        "rename_registered_project",
        side_effect=mutate_registry_then_fail,
    ):
        _expect_raises(
            lambda: rename_project("rename_core_source", "rename_core_target"),
            OSError,
            "core_rename_failure_propagates",
            failures,
        )
    _expect(
        project_path("rename_core_source").is_dir() and not project_path("rename_core_target").exists(),
        "core_rename_failure_restores_directory",
        failures,
    )
    _expect(load_project_registry() == core_registry_snapshot, "core_rename_failure_restores_registry", failures)
    _expect(bool(load_memory("rename_core_source")), "core_rename_failure_restores_database_identity", failures)

    legacy_root = Path("data/projects/legacy_files")
    legacy_root.mkdir(parents=True, exist_ok=True)
    (legacy_root / "memory.json").write_text(
        json.dumps({"title": "Legacy Imported", "genre": "Legacy Genre"}, ensure_ascii=False),
        encoding="utf-8",
    )
    imported = load_memory("legacy_files")
    _expect(imported.get("title") == "Legacy Imported", "legacy_files_auto_imported", failures)
    _expect((legacy_root / "project.db").stat().st_size > 0, "legacy_database_created", failures)

    zero_root = Path("data/projects/legacy_zero")
    zero_root.mkdir(parents=True, exist_ok=True)
    (zero_root / "memory.json").write_text('{"title":"Legacy Zero"}', encoding="utf-8")
    (zero_root / "project.db").write_bytes(b"")
    _expect_raises(lambda: load_memory("legacy_zero"), RuntimeError, "zero_byte_db_stops_safely", failures)
    _expect((zero_root / "project.db").exists() and (zero_root / "project.db").stat().st_size == 0, "zero_byte_db_not_moved", failures)


def _verify_migration_atomicity(failures: list[str]) -> None:
    migration_workspace = make_workspace("novelforge_review_migration_")
    try:
        migration_path = migration_workspace / "001_broken.sql"
        migration_path.write_text("CREATE TABLE should_rollback(id INTEGER);\nCREATE TABLE broken(\n", encoding="utf-8")
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        with patch.object(storage_schema, "CURRENT_SCHEMA_VERSION", 1), patch.object(
            storage_schema, "_migration_files", return_value=[(1, migration_path)]
        ):
            _expect_raises(lambda: storage_schema.ensure_schema(conn), sqlite3.OperationalError, "broken_migration_raises", failures)
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='should_rollback'"
        ).fetchone()
        _expect(table is None, "broken_migration_rolls_back_prior_statements", failures)
        _expect(storage_schema.get_schema_version(conn) == 0, "broken_migration_version_not_recorded", failures)
        conn.close()
    finally:
        retry_rmtree(migration_workspace)


def _verify_retrieval_guards(failures: list[str]) -> None:
    project_name = "retrieval_guards"
    create_project(project_name)
    chunk_id = "stable-doc#chunk001"
    title = "Stable title"
    old_content = "old apple content"
    manifest = {
        "project_name": project_name,
        "built_at": "2026-01-01T00:00:00",
        "documents": [{
            "doc_id": "stable-doc",
            "project_name": project_name,
            "source_type": "outline",
            "scope": "project",
            "title": title,
            "content": old_content,
            "metadata": {},
        }],
        "chunks": [{
            "chunk_id": chunk_id,
            "document_id": "stable-doc",
            "project_name": project_name,
            "source_type": "outline",
            "scope": "project",
            "title": title,
            "content": old_content,
            "metadata": {"chunk_index": 1},
        }],
    }
    save_retrieval_manifest(project_name, json.dumps(manifest))
    old_hash = sha256(f"{title}\n{old_content}".encode("utf-8")).hexdigest()
    save_retrieval_vectors(project_name, json.dumps({
        "project_name": project_name,
        "embedding_model": "model-a",
        "vectors": {chunk_id: [1.0, 0.0]},
        "content_hashes": {chunk_id: old_hash},
    }))
    _expect(chunk_id in load_retrieval_vectors(project_name), "fresh_vector_saved", failures)

    new_content = "new banana content"
    manifest["documents"][0]["content"] = new_content
    manifest["chunks"][0]["content"] = new_content
    save_retrieval_manifest(project_name, json.dumps(manifest))
    _expect(chunk_id not in load_retrieval_vectors(project_name), "edited_chunk_invalidates_vector", failures)

    old_manifest = load_retrieval_manifest(project_name)
    with patch("novelforge.services.retrieval.list_stories", return_value=[{"story_id": "a"}, {"story_id": "b"}]), patch(
        "novelforge.services.retrieval._documents_from_project_files",
        side_effect=lambda _project, story_id: [] if story_id == "a" else (_ for _ in ()).throw(OSError("story b failed")),
    ):
        _expect_raises(lambda: build_retrieval_index(project_name), OSError, "partial_manifest_build_raises", failures)
    _expect(load_retrieval_manifest(project_name) == old_manifest, "partial_manifest_does_not_replace_old_index", failures)

    conflict_rows = [
        {"conflict_id": "shared", "story_id": "story_a", "decision": "use_project"},
        {"conflict_id": "shared", "story_id": "story_b", "decision": "use_external"},
        {"conflict_id": "shared", "story_id": "", "decision": "merge"},
    ]
    document_helpers = [
        "_documents_from_memory",
        "_documents_from_knowledge",
        "_documents_from_character_entities",
        "_documents_from_entity_aliases",
        "_documents_from_setting_entities",
        "_documents_from_external_sources",
    ]
    with ExitStack() as stack:
        for helper_name in document_helpers:
            stack.enter_context(patch.object(retrieval_module, helper_name, return_value=[]))
        stack.enter_context(patch.object(retrieval_module, "load_conflict_resolutions", return_value=conflict_rows))
        stack.enter_context(patch.object(retrieval_module, "list_stories", return_value=[]))
        conflict_docs = retrieval_module.gather_retrieval_documents(project_name)
    _expect(len({doc.doc_id for doc in conflict_docs}) == 3, "conflict_document_ids_include_story", failures)
    _expect(
        {doc.metadata.get("story_id") for doc in conflict_docs} == {"", "story_a", "story_b"},
        "conflict_documents_preserve_story_metadata",
        failures,
    )
    conflict_chunks = [
        chunk
        for document in conflict_docs
        for chunk in retrieval_module.chunk_document(document)
    ]
    allowed_for_a = {
        chunk.metadata.get("story_id")
        for chunk in conflict_chunks
        if retrieval_module._story_scope_allowed(chunk, "story_a")
    }
    _expect(allowed_for_a == {"", "story_a"}, "conflict_chunks_are_story_filtered", failures)

    feedback_rows = [
        {"chunk_id": "shared-chunk", "rating": "helpful", "story_id": ""},
        {"chunk_id": "shared-chunk", "rating": "priority", "story_id": "story_a"},
        {"chunk_id": "shared-chunk", "rating": "wrong", "story_id": "story_b"},
    ]
    with patch.object(retrieval_module, "load_retrieval_feedback", return_value=feedback_rows):
        story_a_feedback = retrieval_module._build_feedback_stats(project_name, "story_a")
        story_b_feedback = retrieval_module._build_feedback_stats(project_name, "story_b")
    _expect(
        story_a_feedback["shared-chunk"]["score"] == 0.85,
        "feedback_stats_include_global_and_current_story",
        failures,
    )
    _expect(
        story_b_feedback["shared-chunk"]["score"] == -0.55,
        "feedback_stats_exclude_other_stories",
        failures,
    )


def _verify_isolation_and_splitting(failures: list[str]) -> None:
    knowledge = {
        "characters": [
            {"id": "a", "name": "Alice", "summary": "MAIN_DOCTOR", "story_id": "story_a", "setting_scope": "story", "worldline_id": "main"},
            {"id": "b", "name": "Alice", "summary": "AU_ASSASSIN", "story_id": "story_b", "setting_scope": "story", "worldline_id": "au"},
        ],
        "world_rules": [
            {"id": "m", "name": "MoonGate", "summary": "MAIN_NIGHT", "story_id": "story_a", "setting_scope": "story", "worldline_id": "main"},
            {"id": "u", "name": "MoonGate", "summary": "AU_DAY", "story_id": "story_a", "setting_scope": "story", "worldline_id": "au"},
        ],
    }
    with patch.object(knowledge_entities, "load_knowledge_base", return_value=knowledge), patch.object(
        knowledge_entities, "load_entity_aliases", return_value=[]
    ):
        character_cards = knowledge_entities.build_character_entity_cards("unused")
        setting_cards = knowledge_entities.build_setting_entity_cards("unused")
    _expect(len(character_cards) == 2, "character_cards_are_story_isolated", failures)
    _expect(all("MAIN_DOCTOR" not in card["summary"] or "AU_ASSASSIN" not in card["summary"] for card in character_cards), "character_card_summaries_not_mixed", failures)
    moon_cards = [card for card in setting_cards if card.get("name") == "MoonGate"]
    _expect(len(moon_cards) == 2, "setting_cards_are_worldline_isolated", failures)
    _expect(all("MAIN_NIGHT" not in card["summary"] or "AU_DAY" not in card["summary"] for card in moon_cards), "setting_card_summaries_not_mixed", failures)

    pending = [
        {"pending_id": "pa", "category": "characters", "name": "Alice", "summary": "doctor", "story_id": "story_a", "setting_scope": "story", "worldline_id": "main"},
        {"pending_id": "pb", "category": "characters", "name": "Alice", "summary": "assassin", "story_id": "story_b", "setting_scope": "story", "worldline_id": "au"},
    ]
    with patch.object(knowledge_quality, "load_knowledge_base", return_value={}):
        issues = knowledge_quality.build_pending_knowledge_quality_issues("unused", pending)
    _expect(not issues, "quality_does_not_conflict_across_stories", failures)

    segments = split_long_reference_text("Long", "第1章\n" + "x" * 13000, max_chars=6000)
    _expect(len(segments) == 3, "long_chapter_is_split", failures)
    _expect(max(segment["char_count"] for segment in segments) <= 6000, "long_chapter_respects_max_chars", failures)


def main() -> int:
    with isolated_workspace("novelforge_review_regressions_"):
        failures: list[str] = []
        _verify_storage_and_story_guards(failures)
        _verify_project_rename_and_legacy_bootstrap(failures)
        _verify_migration_atomicity(failures)
        _verify_retrieval_guards(failures)
        _verify_isolation_and_splitting(failures)
        result = {"ok": not failures, "failures": failures, "checks": 73}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
