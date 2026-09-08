"""Focused verification for story-to-project knowledge promotion."""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.services.memory import (  # noqa: E402
    create_project,
    create_story,
    load_knowledge_category,
    load_knowledge_center_record,
    update_confirmed_knowledge_item_record,
    upsert_knowledge_category_item_record,
)
from novelforge.workflows.knowledge_promotion import (  # noqa: E402
    promote_knowledge_to_project,
)
from novelforge.services.retrieval import rebuild_retrieval_assets, retrieve_context  # noqa: E402
from storage import open_existing_project_db, open_project_db  # noqa: E402
from tools.verify_utils import isolated_workspace  # noqa: E402


def _expect(condition: bool, label: str, failures: list[str]) -> None:
    if not condition:
        failures.append(label)


def _seed(project_name: str, story_id: str, attachment_id: str) -> None:
    with open_project_db(Path("data/projects") / project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO source_documents (
                source_id, story_id, title, source_type, authority, content_hash,
                metadata_json, active_revision_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "source_story_material",
                story_id,
                "资料原文",
                "creative_attachment",
                0.75,
                "hash-story-material",
                json.dumps({
                    "story_id": story_id,
                    "creative_attachment_id": attachment_id,
                    "batch_id": "batch_story_material",
                    "source_origin": "uploaded_material",
                }, ensure_ascii=False),
                "revision_story_material",
            ),
        )
        conn.execute(
            """
            INSERT INTO source_revisions (
                revision_id, source_id, content_hash, parser_name, metadata_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "revision_story_material",
                "source_story_material",
                "hash-story-material",
                "verify",
                json.dumps({"story_id": story_id}, ensure_ascii=False),
            ),
        )
        conn.execute(
            """
            INSERT INTO source_segments (
                segment_id, source_id, segment_index, title, text_hash,
                import_status, extraction_status, metadata_json, source_revision_id
            ) VALUES (?, ?, 1, ?, ?, 'pending', 'extracted', ?, ?)
            """,
            (
                "segment_story_material",
                "source_story_material",
                "资料片段",
                "hash-segment",
                json.dumps({"story_id": story_id}, ensure_ascii=False),
                "revision_story_material",
            ),
        )
        conn.execute(
            """
            INSERT INTO creative_attachments (
                attachment_id, content_hash, source_id, source_revision_id,
                relative_path, title, scope, story_id, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, 'story', ?, 'ready', ?)
            """,
            (
                attachment_id,
                "hash-story-material",
                "source_story_material",
                "revision_story_material",
                "sources/story_material.json",
                "资料原文",
                story_id,
                json.dumps({"background_batch_id": "batch_story_material"}, ensure_ascii=False),
            ),
        )
        conn.commit()


def _seed_source(
    project_name: str,
    story_id: str,
    source_id: str,
    segment_id: str,
    *,
    source_type: str = "external_source",
    metadata: dict | None = None,
    import_status: str = "pending",
) -> None:
    """Seed the durable source/segment chain used by extraction-confirmation tests."""

    source_metadata = {"story_id": story_id, **(metadata or {})}
    with open_project_db(Path("data/projects") / project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO source_documents (source_id, story_id, title, source_type, metadata_json) VALUES (?, ?, ?, ?, ?)",
            (source_id, story_id, source_id, source_type, json.dumps(source_metadata, ensure_ascii=False)),
        )
        conn.execute(
            "INSERT INTO source_segments (segment_id, source_id, segment_index, title, import_status, extraction_status, metadata_json) VALUES (?, ?, 1, ?, ?, 'extracted', ?)",
            (segment_id, source_id, f"{source_id}片段", import_status, json.dumps(source_metadata, ensure_ascii=False)),
        )
        conn.commit()


def main() -> int:
    failures: list[str] = []
    old_disable = os.environ.get("NOVELFORGE_DISABLE_BACKGROUND_TASKS")
    os.environ["NOVELFORGE_DISABLE_BACKGROUND_TASKS"] = "1"
    try:
        with isolated_workspace("novelforge_knowledge_promotion_"):
            project_name = create_project("promotion_verify")
            story = create_story(project_name, "资料故事")
            story_id = str(story.get("story_id") or "")
            attachment_id = "attachment_verify_material"
            _seed(project_name, story_id, attachment_id)

            source_item = {
                "id": "story_relation",
                "category": "relationships",
                "name": "甲与乙的关系",
                "summary": "旧摘要",
                "subject": "甲",
                "object": "乙",
                "relation_type": "同盟",
                "typed_data": {"subject": "甲", "object": "乙", "relation_type": "同盟"},
                "aliases": ["旧称呼"],
                "evidence": [{
                    "quote": "甲与乙结为同盟。",
                    "source_id": "source_story_material",
                    "segment_id": "segment_story_material",
                    "source_revision_id": "revision_story_material",
                }],
                "story_id": story_id,
                "setting_scope": "story",
                "source_id": "source_story_material",
                "source_segment_id": "segment_story_material",
                "source_revision_id": "revision_story_material",
                "source_origin": "uploaded_material",
                "status": "confirmed",
                "chapter_no": 7,
                "source_chapter_no": 7,
                "valid_from_chapter": 7,
                "setting_field": "status",
                "tags": ["chapter:7", "资料"],
            }
            upsert_knowledge_category_item_record(project_name, "relationships", source_item)

            # The input must be the latest saved story snapshot, including edits.
            current = load_knowledge_center_record(project_name, "knowledge", "story_relation")
            latest = dict(current.get("payload") or {})
            latest.update({"summary": "用户编辑后的摘要", "aliases": ["新称呼"]})
            _expect(
                update_confirmed_knowledge_item_record(
                    project_name, "relationships", "story_relation", latest,
                ),
                "story_edit_saved",
                failures,
            )
            before_story = load_knowledge_center_record(project_name, "knowledge", "story_relation")

            first = promote_knowledge_to_project(project_name, ["story_relation"])
            _expect(first.get("promoted_count") == 1, "first_promotes_one", failures)
            promoted_id = str(first["items"][0]["knowledge_id"])
            promoted = load_knowledge_center_record(project_name, "knowledge", promoted_id)
            promoted_payload = dict(promoted.get("payload") or {})
            _expect(promoted_payload.get("story_id") in (None, ""), "project_copy_is_storyless", failures)
            _expect(promoted_payload.get("setting_scope") == "project", "project_scope", failures)
            _expect(promoted_payload.get("summary") == "用户编辑后的摘要", "latest_edit_retained", failures)
            _expect(promoted_payload.get("aliases") == ["新称呼"], "latest_aliases_retained", failures)
            _expect(promoted_payload.get("source_story_knowledge_id") == "story_relation", "origin_link", failures)
            _expect("chapter_no" not in promoted_payload, "project_copy_clears_story_chapter", failures)
            _expect("source_chapter_no" not in promoted_payload, "project_copy_clears_source_chapter", failures)
            _expect(promoted_payload.get("setting_field") == "status", "project_copy_keeps_fact_slot", failures)
            _expect(promoted_payload.get("tags") == ["资料"], "project_copy_clears_chapter_tag", failures)
            with open_project_db(Path("data/projects") / project_name) as conn:
                project_row = conn.execute(
                    "SELECT chapter_no, valid_from_chapter, valid_to_chapter, fact_key FROM knowledge_items WHERE knowledge_id = ?",
                    (promoted_id,),
                ).fetchone()
            _expect(
                project_row is not None
                and all(project_row[key] is None for key in ("chapter_no", "valid_from_chapter", "valid_to_chapter"))
                and project_row["fact_key"] == "status",
                "project_copy_has_no_story_validity",
                failures,
            )
            _expect(
                before_story.get("payload") == load_knowledge_center_record(project_name, "knowledge", "story_relation").get("payload"),
                "story_row_unchanged",
                failures,
            )

            # Relationship projection must use project entities and no story edge.
            with open_project_db(Path("data/projects") / project_name) as conn:
                edge = conn.execute(
                    "SELECT story_id, source_node_id, target_node_id FROM graph_edges WHERE json_extract(metadata_json, '$.knowledge_id') = ? AND deleted_at IS NULL",
                    (promoted_id,),
                ).fetchone()
                endpoints = conn.execute(
                    "SELECT COUNT(*) FROM entities WHERE entity_id IN (?, ?) AND setting_scope = 'project' AND story_id IS NULL",
                    (edge["source_node_id"], edge["target_node_id"]) if edge else ("", ""),
                ).fetchone()[0] if edge else 0
            _expect(edge is not None, "project_relationship_edge", failures)
            _expect(edge is not None and edge["story_id"] is None, "project_edge_has_no_story", failures)
            _expect(endpoints == 2, "project_edge_endpoints", failures)

            # A retry reuses the same copy and never overwrites project edits.
            project_edit = dict(promoted_payload)
            project_edit["summary"] = "项目独立编辑"
            _expect(
                upsert_knowledge_category_item_record(project_name, "relationships", project_edit).get("summary") == "项目独立编辑",
                "project_edit_saved",
                failures,
            )
            retry = promote_knowledge_to_project(project_name, ["story_relation"])
            _expect(retry.get("promoted_count") == 0, "retry_does_not_promote", failures)
            _expect(retry.get("already_promoted_count") == 1, "retry_reuses", failures)
            after_retry = load_knowledge_center_record(project_name, "knowledge", promoted_id)
            _expect((after_retry.get("payload") or {}).get("summary") == "项目独立编辑", "retry_keeps_project_edit", failures)

            # Attachment selection follows source IDs/attachment metadata, not names.
            by_attachment = promote_knowledge_to_project(project_name, attachment_id=attachment_id)
            _expect(by_attachment.get("already_promoted_count") == 1, "attachment_selects_source", failures)
            with open_project_db(Path("data/projects") / project_name) as conn:
                alias_row = conn.execute(
                    "SELECT aliases_json FROM entity_alias_groups WHERE canonical_name = '甲与乙的关系' AND story_id IS NULL AND deleted_at IS NULL",
                ).fetchone()
            _expect(alias_row is not None and "新称呼" in str(alias_row["aliases_json"]), "project_aliases_synced", failures)

            # Different fact slots on one entity are compatible and must stay
            # as separate project facts.  This uses the normal pending source
            # segment state produced when extraction runs without indexing the
            # original text first.
            _seed_source(
                project_name, story_id, "source_character_identity", "segment_character_identity",
                metadata={"batch_id": "batch_character_identity"},
            )
            _seed_source(
                project_name, story_id, "source_character_affiliation", "segment_character_affiliation",
                metadata={"batch_id": "batch_character_affiliation"},
            )
            character_base = {
                "category": "characters",
                "name": "角色甲",
                "aliases": ["甲"],
                "story_id": story_id,
                "setting_scope": "story",
                "worldline_id": "main",
                "source_origin": "uploaded_material",
                "status": "confirmed",
                "confidence": 0.95,
                "evidence_strength": 0.95,
                "evidence": [{"quote": "角色甲的资料事实。"}],
            }
            identity_item = {
                **character_base,
                "id": "story_character_identity",
                "source_id": "source_character_identity",
                "source_segment_id": "segment_character_identity",
                "setting_field": "status",
                "details": {"status": "在职"},
                "typed_data": {"status": "在职"},
            }
            affiliation_item = {
                **character_base,
                "id": "story_character_affiliation",
                "source_id": "source_character_affiliation",
                "source_segment_id": "segment_character_affiliation",
                "setting_field": "affiliation",
                "details": {"affiliation": "甲组织"},
                "typed_data": {"affiliations": ["甲组织"]},
            }
            upsert_knowledge_category_item_record(project_name, "characters", identity_item)
            upsert_knowledge_category_item_record(project_name, "characters", affiliation_item)
            multi_slot = promote_knowledge_to_project(
                project_name, ["story_character_identity", "story_character_affiliation"],
            )
            _expect(multi_slot.get("promoted_count") == 2, "compatible_fact_slots_promoted", failures)
            character_project = [
                item for item in load_knowledge_category(project_name, "characters")
                if item.get("setting_scope") == "project" and item.get("name") == "角色甲"
            ]
            _expect(
                {str(item.get("fact_key") or item.get("setting_field") or "") for item in character_project}
                >= {"status", "affiliation"},
                "compatible_fact_slots_preserved",
                failures,
            )

            # The same entity and fact slot with different values is a real
            # quality conflict and is rejected atomically.
            _seed_source(
                project_name, story_id, "source_character_conflict", "segment_character_conflict",
                metadata={"batch_id": "batch_character_conflict"},
            )
            conflict_character = {
                **character_base,
                "id": "story_character_conflict",
                "source_id": "source_character_conflict",
                "source_segment_id": "segment_character_conflict",
                "setting_field": "status",
                "details": {"status": "已离职"},
                "typed_data": {"status": "已离职"},
            }
            upsert_knowledge_category_item_record(project_name, "characters", conflict_character)
            fact_conflict = promote_knowledge_to_project(project_name, ["story_character_conflict"])
            _expect(fact_conflict.get("blocked") is True, "same_fact_slot_conflict_blocked", failures)
            _expect("冲突" in str(fact_conflict.get("reason") or ""), "same_fact_slot_conflict_reason", failures)
            _expect(
                len([
                    item for item in load_knowledge_category(project_name, "characters")
                    if item.get("setting_scope") == "project" and item.get("name") == "角色甲"
                ]) == 2,
                "same_fact_slot_conflict_atomic",
                failures,
            )

            # An explicit alternate worldline is a separate target domain and
            # must not be rejected by the main-worldline fact conflict.
            _seed_source(
                project_name, story_id, "source_character_alt", "segment_character_alt",
                metadata={"batch_id": "batch_character_alt"},
            )
            alternate_character = {
                **conflict_character,
                "id": "story_character_alt",
                "source_id": "source_character_alt",
                "source_segment_id": "segment_character_alt",
                "worldline_id": "alternate",
                "details": {"status": "敌对"},
                "typed_data": {"status": "敌对"},
            }
            upsert_knowledge_category_item_record(project_name, "characters", alternate_character)
            alternate_result = promote_knowledge_to_project(project_name, ["story_character_alt"])
            _expect(alternate_result.get("promoted_count") == 1, "different_worldline_promoted", failures)
            _expect(
                len([
                    item for item in load_knowledge_category(project_name, "characters")
                    if item.get("setting_scope") == "project" and item.get("name") == "角色甲"
                ]) == 3,
                "different_worldline_kept_separate",
                failures,
            )

            # A same-name item from another imported source is blocked, so the
            # existing project knowledge cannot be silently replaced.
            with open_project_db(Path("data/projects") / project_name) as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO source_documents (source_id, story_id, title, source_type, metadata_json) VALUES (?, ?, ?, ?, ?)",
                    ("source_other", story_id, "其它资料", "creative_attachment", json.dumps({"story_id": story_id})),
                )
                conn.execute(
                    "INSERT INTO source_segments (segment_id, source_id, segment_index, title, import_status, extraction_status) VALUES (?, ?, 1, ?, 'imported', 'extracted')",
                    ("segment_other", "source_other", "其它资料片段"),
                )
                conn.commit()
            other = dict(source_item)
            other.update({"id": "story_relation_other_source", "source_id": "source_other", "source_segment_id": "segment_other"})
            upsert_knowledge_category_item_record(project_name, "relationships", other)
            conflict = promote_knowledge_to_project(project_name, ["story_relation_other_source"])
            _expect(conflict.get("blocked") is True, "same_name_conflict_blocked", failures)
            _expect(conflict.get("reason"), "same_name_conflict_reason", failures)
            _expect(
                len([item for item in load_knowledge_category(project_name, "relationships") if item.get("setting_scope") == "project"]) == 1,
                "same_name_conflict_no_extra_copy",
                failures,
            )

            # Unknown IDs are rejected before any row is written.
            try:
                promote_knowledge_to_project(project_name, ["story_relation", "missing-id"])
            except ValueError:
                pass
            else:
                failures.append("unknown_id_rejected")
            _expect(
                len([item for item in load_knowledge_category(project_name, "relationships") if item.get("setting_scope") == "project"]) == 1,
                "unknown_batch_is_atomic",
                failures,
            )

            # Interactive fragment entries cannot be promoted.
            fragment = dict(source_item)
            fragment.update({"id": "fragment_item", "source_origin": "interactive_fragment", "extraction_mode": "creative_fragment"})
            upsert_knowledge_category_item_record(project_name, "relationships", fragment)
            try:
                promote_knowledge_to_project(project_name, ["fragment_item"])
            except ValueError:
                pass
            else:
                failures.append("fragment_rejected")

            # A durable source/segment row with a non-import source type is
            # still not eligible; the shared domain helper uses the positive
            # import-source chain rather than accepting arbitrary source types.
            _seed_source(
                project_name, story_id, "source_manual_memory", "segment_manual_memory",
                source_type="memory_character",
                metadata={"batch_id": "copied_batch_marker"},
            )
            manual_item = dict(source_item)
            manual_item.update({
                "id": "manual_memory_item",
                "source_id": "source_manual_memory",
                "source_segment_id": "segment_manual_memory",
                "source_origin": "memory_projection",
            })
            upsert_knowledge_category_item_record(project_name, "relationships", manual_item)
            try:
                promote_knowledge_to_project(project_name, ["manual_memory_item"])
            except ValueError:
                pass
            else:
                failures.append("non_import_source_rejected")

            # BEGIN IMMEDIATE makes concurrent retries create one snapshot.
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: promote_knowledge_to_project(project_name, ["story_relation"]), range(2)))
            _expect(sum(int(result.get("promoted_count") or 0) for result in results) == 0, "concurrent_retry_no_duplicate", failures)
            _expect(
                len([item for item in load_knowledge_category(project_name, "relationships") if item.get("source_story_knowledge_id") == "story_relation"]) == 1,
                "concurrent_single_copy",
                failures,
            )

            # First-time concurrent promotion: one transaction creates the
            # snapshot and the other observes/reuses it.
            with open_project_db(Path("data/projects") / project_name) as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO source_documents (source_id, story_id, title, source_type, metadata_json) VALUES (?, ?, ?, ?, ?)",
                    ("source_concurrent", story_id, "并发资料", "creative_attachment", json.dumps({"story_id": story_id, "batch_id": "batch_concurrent"})),
                )
                conn.execute(
                    "INSERT INTO source_segments (segment_id, source_id, segment_index, title, import_status, extraction_status) VALUES (?, ?, 1, ?, 'imported', 'extracted')",
                    ("segment_concurrent", "source_concurrent", "并发资料片段"),
                )
                conn.commit()
            concurrent_item = dict(source_item)
            concurrent_item.update({
                "id": "story_relation_concurrent",
                "name": "并发关系",
                "source_id": "source_concurrent",
                "source_segment_id": "segment_concurrent",
                "summary": "并发创建摘要",
            })
            upsert_knowledge_category_item_record(project_name, "relationships", concurrent_item)
            with ThreadPoolExecutor(max_workers=2) as executor:
                first_time_results = list(executor.map(
                    lambda _: promote_knowledge_to_project(project_name, ["story_relation_concurrent"]),
                    range(2),
                ))
            _expect(
                sum(int(result.get("promoted_count") or 0) for result in first_time_results) == 1,
                "concurrent_first_create_once",
                failures,
            )
            _expect(
                sum(int(result.get("already_promoted_count") or 0) for result in first_time_results) == 1,
                "concurrent_second_reuses",
                failures,
            )
            concurrent_copies = [
                item for item in load_knowledge_category(project_name, "relationships")
                if item.get("source_story_knowledge_id") == "story_relation_concurrent"
            ]
            _expect(len(concurrent_copies) == 1, "concurrent_first_single_db_copy", failures)
            if concurrent_copies:
                concurrent_copy_id = str(concurrent_copies[0].get("id") or "")
                with open_existing_project_db(Path("data/projects") / project_name) as conn:
                    concurrent_edge = conn.execute(
                        "SELECT story_id, source_node_id, target_node_id FROM graph_edges WHERE json_extract(metadata_json, '$.knowledge_id') = ? AND deleted_at IS NULL",
                        (concurrent_copy_id,),
                    ).fetchone()
                    endpoint_count = conn.execute(
                        "SELECT COUNT(*) FROM entities WHERE entity_id IN (?, ?) AND setting_scope = 'project' AND story_id IS NULL",
                        (concurrent_edge["source_node_id"], concurrent_edge["target_node_id"]) if concurrent_edge else ("", ""),
                    ).fetchone()[0] if concurrent_edge else 0
                _expect(concurrent_edge is not None and concurrent_edge["story_id"] is None, "concurrent_project_edge", failures)
                _expect(endpoint_count == 2, "concurrent_project_endpoints", failures)

            # Rebuilt retrieval exposes project snapshots to a different story,
            # while story-scoped originals remain isolated to their own story.
            story_b = create_story(project_name, "另一个故事")
            story_b_id = str(story_b.get("story_id") or "")
            rebuild_retrieval_assets(project_name, build_vectors=False)
            retrieval_hits = retrieve_context(project_name, "用户编辑后的摘要", story_id=story_b_id, top_k=20)
            retrieval_ids = {
                str(hit.chunk.metadata.get("knowledge_id") or "")
                for hit in retrieval_hits
                if isinstance(hit.chunk.metadata, dict)
            }
            _expect(promoted_id in retrieval_ids, "project_copy_retrievable_for_other_story", failures)
            _expect("story_relation" not in retrieval_ids, "story_source_not_retrievable_for_other_story", failures)
    finally:
        if old_disable is None:
            os.environ.pop("NOVELFORGE_DISABLE_BACKGROUND_TASKS", None)
        else:
            os.environ["NOVELFORGE_DISABLE_BACKGROUND_TASKS"] = old_disable

    result = {"ok": not failures, "failures": failures}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
