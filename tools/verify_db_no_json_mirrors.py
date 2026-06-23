from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _expect(condition: bool, label: str, failures: list[str]) -> None:
    if not condition:
        failures.append(label)


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    workspace = ROOT / ".tmp_db_no_json_mirrors" / stamp
    workspace.mkdir(parents=True, exist_ok=True)
    previous_cwd = Path.cwd()
    previous_flag = os.environ.get("NOVELFORGE_WRITE_JSON_MIRRORS")
    os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = "0"
    try:
        os.chdir(workspace)
        from memory import (
            GLOBAL_PROMPT_OPTIONS_PATH,
            GLOBAL_RULE_CONFLICT_RESOLUTIONS_PATH,
            GLOBAL_RULES_PATH,
            LLM_PROFILES_PATH,
            _DB_UNAVAILABLE_PROJECTS,
            _project_prompt_options_path,
            _story_prompt_options_path,
            _story_rules_overrides_path,
            append_auto_review_run,
            append_retrieval_eval_run,
            append_retrieval_feedback,
            auto_review_policy_path,
            auto_review_runs_path,
            character_entities_path,
            create_long_reference_batch,
            create_project,
            creative_profile_path,
            entity_aliases_path,
            evaluation_path,
            extraction_plan_templates_path,
            inspect_global_database,
            inspect_project_database,
            load_auto_review_policy,
            load_auto_review_runs,
            load_chapter_discussion_artifact,
            load_character_entities,
            load_creative_profile,
            load_entity_aliases,
            load_evaluation_json,
            load_global_prompt_options,
            load_global_rules,
            load_knowledge_category,
            load_llm_profiles,
            load_long_reference_batch,
            load_memory,
            load_outline_discussion_artifact,
            load_pending_knowledge_items,
            load_pipeline_run,
            load_project_prompt_options,
            load_project_rules,
            load_retrieval_eval_cases,
            load_retrieval_eval_runs,
            load_retrieval_feedback,
            load_retrieval_manifest,
            load_retrieval_vectors,
            load_review_json,
            load_rule_conflict_resolutions,
            load_setting_entities,
            load_story_prompt_options,
            load_story_rules,
            knowledge_category_path,
            long_reference_batch_path,
            pending_knowledge_path,
            project_path,
            retrieval_eval_cases_path,
            retrieval_eval_runs_path,
            retrieval_feedback_path,
            retrieval_path,
            runs_path,
            save_auto_review_policy,
            save_chapter_discussion_artifact,
            save_character_entities,
            save_creative_profile,
            save_entity_aliases,
            save_evaluation_json,
            save_extraction_plan_templates,
            save_global_prompt_options,
            save_global_rules,
            save_knowledge_category,
            save_llm_profiles,
            save_memory,
            save_outline_discussion_artifact,
            save_pending_knowledge_items,
            save_pipeline_run,
            save_project_prompt_options,
            save_project_rules,
            save_retrieval_manifest,
            save_retrieval_vectors,
            save_review_json,
            save_rule_conflict_resolutions,
            save_setting_entities,
            save_story_prompt_options,
            save_story_rules,
            setting_entities_path,
            stories_index_path,
            upsert_retrieval_eval_case,
        )
        from storage import open_project_db
        from storage.repositories import load_asset_payload, register_asset_file, upsert_asset_payload

        save_llm_profiles({
            "active_profile_id": "no_mirror_profile",
            "profiles": [{
                "id": "no_mirror_profile",
                "name": "No Mirror Profile",
                "base_url": "https://example.test",
                "api_key": "verify-key",
                "model_name": "verify-model",
                "embedding_model_name": "verify-embedding",
            }],
        })
        save_global_rules({"write": ["global no mirror rule"]})
        save_global_prompt_options([{
            "id": "global_prompt_no_mirror",
            "name": "Global Prompt No Mirror",
            "capability": "write",
            "category": "custom",
            "slot": "custom",
            "content": "global prompt",
            "enabled": True,
        }])
        save_rule_conflict_resolutions("_global_no_mirror_project", "global", [{
            "id": "global_conflict_no_mirror",
            "scope": "write",
            "title": "Global Conflict No Mirror",
            "decision": "global conflict decision",
        }])

        project_name = f"_db_no_mirror_verify_{stamp}"
        create_project(project_name)
        save_memory(project_name, {"title": "No Mirror Verify", "genre": "verify"})
        save_creative_profile(project_name, {"is_configured": True, "target_word_count": "88888", "notes": "no mirror profile"})
        save_project_rules(project_name, {"write": ["project no mirror rule"]})
        save_story_rules(project_name, "default", {"review": ["story no mirror rule"]})
        save_project_prompt_options(project_name, [{
            "id": "project_prompt_no_mirror",
            "name": "Project Prompt No Mirror",
            "capability": "write",
            "category": "custom",
            "slot": "custom",
            "content": "project prompt",
            "enabled": True,
        }])
        save_story_prompt_options(project_name, "default", [{
            "id": "story_prompt_no_mirror",
            "name": "Story Prompt No Mirror",
            "capability": "review",
            "category": "custom",
            "slot": "custom",
            "content": "story prompt",
            "enabled": True,
        }])
        save_outline_discussion_artifact(project_name, {"marker": "outline"}, "outline report")
        save_chapter_discussion_artifact(project_name, 1, {"marker": "chapter"}, "chapter report")
        save_character_entities(project_name, [{"name": "No Mirror Character"}])
        save_setting_entities(project_name, [{"name": "No Mirror Setting"}])
        save_extraction_plan_templates(project_name, [{"name": "No Mirror Template"}])
        save_pending_knowledge_items(project_name, [{"pending_id": "pending_no_mirror", "category": "items", "name": "No Mirror Item"}])
        save_entity_aliases(project_name, [{"id": "alias_no_mirror", "canonical_name": "No Mirror Character", "aliases": ["NMC"]}])
        batch = create_long_reference_batch(
            project_name,
            title="No Mirror Batch",
            scope="reference",
            authority="curated",
            source_type="canon",
            content_fingerprint="no_mirror_batch",
            segments=[{"title": "No Mirror Segment", "content": "batch source text"}],
        )
        save_auto_review_policy(project_name, {"min_confidence": 0.6, "manual_review_categories": ["characters"]})
        append_auto_review_run(project_name, {"run_id": "auto_no_mirror", "status": "completed"})
        upsert_retrieval_eval_case(project_name, {
            "case_id": "case_no_mirror",
            "query": "No Mirror Character",
            "expected_terms": ["Character"],
        })
        append_retrieval_eval_run(project_name, {"run_id": "eval_no_mirror", "case_id": "case_no_mirror", "status": "passed"})
        append_retrieval_feedback(project_name, {
            "feedback_id": "feedback_no_mirror",
            "rating": "helpful",
            "chunk_id": "doc_no_mirror#chunk001",
            "query": "No Mirror Character",
        })
        save_review_json(project_name, 1, {"score": 8})
        save_evaluation_json(project_name, 1, {"overall_score": 8})
        save_pipeline_run(project_name, "workflow_no_mirror", json.dumps({
            "run_id": "workflow_no_mirror",
            "project_name": project_name,
            "success": True,
            "steps": {"verify": {"status": "completed"}},
        }, ensure_ascii=False, indent=2))
        save_retrieval_manifest(project_name, json.dumps({
            "project_name": project_name,
            "documents": [{
                "doc_id": "doc_no_mirror",
                "project_name": project_name,
                "source_type": "reference",
                "scope": "project",
                "title": "No Mirror Document",
                "content": "retrieval document",
                "metadata": {},
            }],
            "chunks": [{
                "chunk_id": "doc_no_mirror#chunk001",
                "document_id": "doc_no_mirror",
                "project_name": project_name,
                "source_type": "reference",
                "scope": "project",
                "title": "No Mirror Document",
                "content": "retrieval chunk",
                "metadata": {"chunk_index": 1},
            }],
        }, ensure_ascii=False, indent=2))
        save_retrieval_vectors(project_name, json.dumps({
            "project_name": project_name,
            "embedding_model": "verify-embedding",
            "vectors": {"doc_no_mirror#chunk001": [0.1, 0.2, 0.3]},
        }, ensure_ascii=False, indent=2))

        root = project_path(project_name)
        mirror_paths = [
            LLM_PROFILES_PATH,
            GLOBAL_RULES_PATH,
            GLOBAL_PROMPT_OPTIONS_PATH,
            GLOBAL_RULE_CONFLICT_RESOLUTIONS_PATH,
            root / "memory.json",
            stories_index_path(project_name),
            creative_profile_path(project_name),
            root / "rules.json",
            _story_rules_overrides_path(project_name, "default"),
            _project_prompt_options_path(project_name),
            _story_prompt_options_path(project_name, "default"),
            root / "stories" / "default" / "outline.discussion.json",
            root / "stories" / "default" / "chapter_outlines" / "chapter_001.discussion.json",
            character_entities_path(project_name),
            setting_entities_path(project_name),
            extraction_plan_templates_path(project_name),
            knowledge_category_path(project_name, "items"),
            pending_knowledge_path(project_name),
            entity_aliases_path(project_name),
            long_reference_batch_path(project_name, batch["batch_id"]),
            auto_review_policy_path(project_name),
            auto_review_runs_path(project_name),
            retrieval_eval_cases_path(project_name),
            retrieval_eval_runs_path(project_name),
            retrieval_feedback_path(project_name),
            root / "stories" / "default" / "reviews" / "chapter_001.json",
            evaluation_path(project_name) / "chapter_001.json",
            runs_path(project_name) / "workflow_no_mirror.json",
            retrieval_path(project_name) / "manifest.json",
            retrieval_path(project_name) / "vectors.json",
        ]
        failures: list[str] = []
        _expect(load_llm_profiles().get("active_profile_id") == "no_mirror_profile", "load_llm_profiles", failures)
        _expect(load_global_rules().get("write") == ["global no mirror rule"], "load_global_rules", failures)
        _expect(load_global_prompt_options()[0].get("id") == "global_prompt_no_mirror", "load_global_prompt_options", failures)
        _expect(load_rule_conflict_resolutions("_global_no_mirror_project", "global")[0].get("decision") == "global conflict decision", "load_global_conflict", failures)
        _expect(load_memory(project_name).get("title") == "No Mirror Verify", "load_memory", failures)
        loaded_profile = load_creative_profile(project_name)
        _expect(loaded_profile.get("is_configured") is True and loaded_profile.get("target_word_count") == "88888", "load_creative_profile", failures)
        _expect(load_project_rules(project_name).get("write") == ["project no mirror rule"], "load_project_rules", failures)
        _expect(load_story_rules(project_name, "default").get("review") == ["story no mirror rule"], "load_story_rules", failures)
        _expect(load_project_prompt_options(project_name)[0].get("id") == "project_prompt_no_mirror", "load_project_prompt_options", failures)
        _expect(load_story_prompt_options(project_name, "default")[0].get("id") == "story_prompt_no_mirror", "load_story_prompt_options", failures)
        _expect(load_outline_discussion_artifact(project_name).get("discussion", {}).get("marker") == "outline", "load_outline_discussion", failures)
        _expect(load_chapter_discussion_artifact(project_name, 1).get("discussion", {}).get("marker") == "chapter", "load_chapter_discussion", failures)
        _expect(load_character_entities(project_name)[0].get("name") == "No Mirror Character", "load_character_entities", failures)
        _expect(load_setting_entities(project_name)[0].get("name") == "No Mirror Setting", "load_setting_entities", failures)
        _expect(load_pending_knowledge_items(project_name)[0].get("pending_id") == "pending_no_mirror", "load_pending", failures)
        _expect(load_entity_aliases(project_name)[0].get("canonical_name") == "No Mirror Character", "load_aliases", failures)
        _expect(load_long_reference_batch(project_name, batch["batch_id"]).get("title") == "No Mirror Batch", "load_long_batch", failures)
        _expect(load_auto_review_policy(project_name).get("min_confidence") == 0.6, "load_auto_policy", failures)
        _expect(load_auto_review_runs(project_name)[0].get("run_id") == "auto_no_mirror", "load_auto_runs", failures)
        _expect(load_retrieval_eval_cases(project_name)[0].get("case_id") == "case_no_mirror", "load_eval_cases", failures)
        _expect(load_retrieval_eval_runs(project_name)[0].get("run_id") == "eval_no_mirror", "load_eval_runs", failures)
        _expect(load_retrieval_feedback(project_name)[0].get("feedback_id") == "feedback_no_mirror", "load_feedback", failures)
        _expect(load_review_json(project_name, 1).get("score") == 8, "load_review_json", failures)
        _expect(load_evaluation_json(project_name, 1).get("overall_score") == 8, "load_evaluation_json", failures)
        try:
            pipeline_payload = json.loads(load_pipeline_run(project_name, "workflow_no_mirror") or "{}")
        except Exception:
            pipeline_payload = {}
        _expect(pipeline_payload.get("success") is True, "load_pipeline_run", failures)
        _expect("doc_no_mirror" in load_retrieval_manifest(project_name), "load_retrieval_manifest", failures)
        _expect("doc_no_mirror#chunk001" in load_retrieval_vectors(project_name), "load_retrieval_vectors", failures)
        save_retrieval_manifest(project_name, json.dumps({
            "project_name": project_name,
            "documents": [],
            "chunks": [{
                "chunk_id": "doc_no_mirror#chunk001",
                "document_id": "doc_no_mirror",
                "project_name": project_name,
                "source_type": "reference",
                "scope": "project",
                "title": "No Mirror Document",
                "content": "orphan retrieval chunk",
                "metadata": {"chunk_index": 1},
            }],
        }, ensure_ascii=False, indent=2))
        _expect("doc_no_mirror#chunk001" not in load_retrieval_manifest(project_name), "orphan_chunk_filtered_from_manifest", failures)
        save_retrieval_vectors(project_name, json.dumps({
            "project_name": project_name,
            "embedding_model": "verify-embedding",
            "vectors": {"doc_no_mirror#chunk001": [0.9, 0.8, 0.7]},
        }, ensure_ascii=False, indent=2))
        _expect("doc_no_mirror#chunk001" not in load_retrieval_vectors(project_name), "deleted_chunk_vectors_filtered", failures)
        stale_items_path = knowledge_category_path(project_name, "items")
        stale_items_path.parent.mkdir(parents=True, exist_ok=True)
        stale_items_path.write_text(json.dumps([{"id": "stale_item", "name": "Stale Item"}], ensure_ascii=False, indent=2), encoding="utf-8")
        save_knowledge_category(project_name, "items", [])
        _expect(load_knowledge_category(project_name, "items") == [], "empty_db_save_removes_stale_json_fallback", failures)
        try:
            with open_project_db(project_path(project_name)) as conn:
                register_asset_file(
                    conn,
                    asset_id="legacy_asset_id",
                    story_id="default",
                    asset_type="foreign_key_guard",
                    logical_key="same_key",
                    title="Legacy Asset",
                    relative_path="stories/default/legacy.json",
                    metadata={},
                )
                upsert_asset_payload(
                    conn,
                    asset_type="foreign_key_guard",
                    logical_key="same_key",
                    story_id="default",
                    payload={"version": 1},
                )
                conn.commit()
                register_asset_file(
                    conn,
                    asset_id="new_asset_id",
                    story_id="default",
                    asset_type="foreign_key_guard",
                    logical_key="same_key",
                    title="Updated Asset",
                    relative_path="stories/default/updated.json",
                    metadata={},
                )
                payload = load_asset_payload(
                    conn,
                    asset_type="foreign_key_guard",
                    logical_key="same_key",
                    story_id="default",
                )
                conn.commit()
            _expect(isinstance(payload, dict) and payload.get("version") == 1, "asset_reregister_preserves_fk_payload", failures)
        except Exception as exc:
            failures.append(f"asset_reregister_preserves_fk_payload:{exc}")
        try:
            legacy_run_id = "legacy_workflow_fk"
            with open_project_db(project_path(project_name)) as conn:
                register_asset_file(
                    conn,
                    asset_id="legacy_workflow_asset_id",
                    story_id="default",
                    asset_type="workflow_run_snapshot",
                    logical_key=legacy_run_id,
                    title="Legacy Workflow Asset",
                    relative_path=f"stories/default/runs/{legacy_run_id}.json",
                    metadata={"run_id": legacy_run_id},
                )
                conn.commit()
            save_pipeline_run(project_name, legacy_run_id, json.dumps({
                "run_id": legacy_run_id,
                "project_name": project_name,
                "story_id": "default",
                "success": True,
                "steps": {"verify": {"status": "completed"}},
            }, ensure_ascii=False, indent=2))
            with open_project_db(project_path(project_name)) as conn:
                row = conn.execute(
                    "SELECT artifact_asset_id FROM workflow_steps WHERE step_id = ?",
                    (f"{legacy_run_id}:verify",),
                ).fetchone()
            _expect(row is not None and row["artifact_asset_id"] == "legacy_workflow_asset_id", "workflow_uses_actual_asset_id", failures)
        except Exception as exc:
            failures.append(f"workflow_uses_actual_asset_id:{exc}")
        stale_project_mirror = root / "memory.json"
        stale_project_mirror.write_text(json.dumps({"title": "stale queued mirror"}, ensure_ascii=False), encoding="utf-8")
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        try:
            save_memory(project_name, {"title": "Should Fail Before Deleting Mirror"})
            failures.append("project_db_unavailable_raises_before_mirror_delete")
        except RuntimeError:
            pass
        save_global_rules({"write": ["global rule after project failure"]})
        _expect(stale_project_mirror.exists(), "pending_project_mirror_not_deleted_by_global_sync", failures)
        _DB_UNAVAILABLE_PROJECTS.discard(project_name)
        if stale_project_mirror.exists():
            stale_project_mirror.unlink()
        unexpected_mirrors = [str(path) for path in mirror_paths if path.exists()]
        _expect(not unexpected_mirrors, "no_json_mirrors_written", failures)

        global_health = inspect_global_database()
        project_health = inspect_project_database(project_name)
        result = {
            "ok": not failures and global_health.get("ok") and project_health.get("ok"),
            "workspace": str(workspace),
            "project_name": project_name,
            "unexpected_json_mirrors": unexpected_mirrors,
            "failures": failures,
            "global_health": global_health,
            "project_health": project_health,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    finally:
        os.chdir(previous_cwd)
        if previous_flag is None:
            os.environ.pop("NOVELFORGE_WRITE_JSON_MIRRORS", None)
        else:
            os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = previous_flag
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
