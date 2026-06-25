from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.verify_utils import isolated_workspace, retry_unlink

os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = "1"

from memory import (
    _project_prompt_options_path,
    _story_chapter_summaries_path,
    _story_prompt_options_path,
    _story_rules_overrides_path,
    auto_review_policy_path,
    auto_review_runs_path,
    character_entities_path,
    create_long_reference_batch,
    create_project,
    creative_profile_path,
    entity_aliases_path,
    evaluation_path,
    extraction_plan_templates_path,
    inspect_project_database,
    knowledge_category_path,
    load_auto_review_policy,
    load_auto_review_runs,
    load_arc_chapter_plan,
    load_arc_discussion_artifact,
    load_arc_metadata,
    load_chapter_discussion_artifact,
    load_chapter_outline_metadata,
    load_character_entities,
    load_creative_profile,
    load_creative_profile_discussion_artifact,
    load_entity_aliases,
    load_evaluation_json,
    load_extraction_plan_templates,
    load_knowledge_category,
    load_long_reference_batch,
    load_memory,
    load_pending_knowledge_items,
    load_pipeline_run,
    load_project_prompt_options,
    load_project_rules,
    load_rule_conflict_resolutions,
    load_retrieval_eval_cases,
    load_retrieval_eval_runs,
    load_retrieval_feedback,
    load_retrieval_manifest,
    load_retrieval_vectors,
    load_review_json,
    load_setting_entities,
    load_stories_index,
    load_story_chapter_summaries,
    load_story_prompt_options,
    load_story_rules,
    load_outline_discussion_artifact,
    load_volume_discussion_artifact,
    load_volume_metadata,
    list_arcs,
    list_volumes,
    long_reference_batch_path,
    pending_knowledge_path,
    project_path,
    retrieval_eval_cases_path,
    retrieval_eval_runs_path,
    retrieval_feedback_path,
    retrieval_path,
    runs_path,
    save_auto_review_policy,
    append_auto_review_run,
    append_retrieval_eval_run,
    append_retrieval_feedback,
    save_arc_chapter_plan,
    save_arc_discussion_artifact,
    save_arc_metadata,
    save_chapter_discussion_artifact,
    save_chapter_outline_metadata,
    save_character_entities,
    save_creative_profile,
    save_creative_profile_discussion_artifact,
    save_entity_aliases,
    save_evaluation_json,
    save_extraction_plan_templates,
    save_knowledge_category,
    save_memory,
    save_outline_discussion_artifact,
    save_pending_knowledge_items,
    save_pipeline_run,
    save_project_prompt_options,
    save_project_rules,
    save_rule_conflict_resolutions,
    save_retrieval_manifest,
    save_retrieval_vectors,
    save_review_json,
    save_setting_entities,
    save_story_chapter_summaries,
    save_story_prompt_options,
    save_story_rules,
    save_volume_discussion_artifact,
    save_volume_metadata,
    setting_entities_path,
    stories_index_path,
    upsert_retrieval_eval_case,
)
from project_manager import list_chapter_inventory, list_project_runs
from retrieval import rebuild_retrieval_assets


def _project_name_from_args() -> str:
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        name = sys.argv[1].strip()
        if not name.startswith("_db_first_verify_"):
            raise SystemExit("Project name must start with _db_first_verify_ to avoid deleting real JSON mirrors.")
        return name
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"_db_first_verify_{stamp}"


def _safe_unlink(project_root: Path, file: Path) -> bool:
    return retry_unlink(project_root, file)


def _expect(condition: bool, label: str, failures: list[str]) -> None:
    if not condition:
        failures.append(label)


def _run_verification() -> int:
    project_name = _project_name_from_args()
    create_project(project_name)

    save_memory(project_name, {"title": "DB First Verify", "genre": "verify"})
    save_creative_profile(project_name, {"is_configured": True, "genre": "verify", "tone": "clean"})
    save_creative_profile_discussion_artifact(
        project_name,
        {"approval_ready": True, "marker": "creative_discussion"},
        "creative discussion report",
    )
    save_project_rules(project_name, {"write": ["project rule"], "review": []})
    save_story_rules(project_name, "default", {"review": ["story rule"]})
    save_rule_conflict_resolutions(project_name, "project", [{
        "id": "project_conflict_verify",
        "scope": "write",
        "title": "Project Conflict Verify",
        "decision": "project conflict decision",
    }])
    save_rule_conflict_resolutions(project_name, "story", [{
        "id": "story_conflict_verify",
        "scope": "review",
        "title": "Story Conflict Verify",
        "decision": "story conflict decision",
    }])
    save_project_prompt_options(project_name, [{
        "id": "project_prompt_verify",
        "name": "Project Prompt Verify",
        "capability": "write",
        "category": "custom",
        "slot": "custom",
        "content": "project prompt",
        "enabled": True,
    }])
    save_story_prompt_options(project_name, "default", [{
        "id": "story_prompt_verify",
        "name": "Story Prompt Verify",
        "capability": "review",
        "category": "custom",
        "slot": "custom",
        "content": "story prompt",
        "enabled": True,
    }])
    save_story_chapter_summaries(project_name, "default", [{"chapter_no": 1, "summary": "chapter summary"}])
    save_outline_discussion_artifact(project_name, {"approval_ready": True, "marker": "outline_discussion"}, "outline discussion report")
    save_volume_metadata(project_name, 1, {"title": "Volume Verify", "summary": "volume summary", "status": "approved"})
    save_volume_discussion_artifact(project_name, 1, {"approval_ready": True, "marker": "volume_discussion"}, "volume discussion report")
    save_arc_metadata(project_name, 1, {"volume_no": 1, "title": "Arc Verify", "summary": "arc summary", "status": "approved"})
    save_arc_discussion_artifact(project_name, 1, {"approval_ready": True, "marker": "arc_discussion"}, "arc discussion report")
    save_arc_chapter_plan(project_name, 1, {"marker": "arc_plan", "chapters": [{"chapter_no": 2}]}, "arc plan report")
    save_chapter_outline_metadata(project_name, 2, {"volume_no": 1, "arc_no": 1})
    save_chapter_discussion_artifact(project_name, 2, {"approval_ready": True, "marker": "chapter_discussion"}, "chapter discussion report")
    save_character_entities(project_name, [{"name": "Character Verify"}])
    save_setting_entities(project_name, [{"name": "Setting Verify"}])
    save_extraction_plan_templates(project_name, [{"name": "Template Verify"}])

    save_knowledge_category(project_name, "characters", [{"id": "char_verify", "name": "Character Verify"}])
    save_pending_knowledge_items(project_name, [{"pending_id": "pending_verify", "category": "items", "name": "Item Verify"}])
    save_entity_aliases(project_name, [{"id": "alias_verify", "canonical_name": "Character Verify", "aliases": ["CV"]}])

    batch = create_long_reference_batch(
        project_name,
        title="Batch Verify",
        scope="reference",
        authority="curated",
        source_type="canon",
        content_fingerprint="batch_verify",
        segments=[{"title": "Segment Verify", "content": "source text"}],
    )

    save_auto_review_policy(project_name, {"min_confidence": 0.5, "manual_review_categories": ["constraints"]})
    append_auto_review_run(project_name, {"run_id": "auto_read_verify", "status": "active"})
    upsert_retrieval_eval_case(project_name, {
        "case_id": "case_read_verify",
        "query": "Character Verify",
        "expected_terms": ["Character"],
    })
    append_retrieval_eval_run(project_name, {
        "run_id": "eval_read_verify",
        "case_id": "case_read_verify",
        "status": "passed",
    })

    save_review_json(project_name, 1, {"score": 9})
    save_evaluation_json(project_name, 1, {"overall_score": 9})
    save_pipeline_run(project_name, "workflow_read_verify", json.dumps({
        "run_id": "workflow_read_verify",
        "project_name": project_name,
        "chapter_no": 1,
        "success": True,
        "steps": {"verify": {"status": "completed"}},
    }, ensure_ascii=False, indent=2))

    manifest = {
        "project_name": project_name,
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "documents": [{
            "doc_id": "doc_read_verify",
            "project_name": project_name,
            "source_type": "reference",
            "scope": "project",
            "title": "Read Verify Document",
            "content": "retrieval document",
            "metadata": {},
        }],
        "chunks": [{
            "chunk_id": "doc_read_verify#chunk001",
            "document_id": "doc_read_verify",
            "project_name": project_name,
            "source_type": "reference",
            "scope": "project",
            "title": "Read Verify Document",
            "content": "retrieval chunk",
            "metadata": {"chunk_index": 1},
        }],
    }
    save_retrieval_manifest(project_name, json.dumps(manifest, ensure_ascii=False, indent=2))
    save_retrieval_vectors(project_name, json.dumps({
        "project_name": project_name,
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "embedding_model": "verify-embedding",
        "vectors": {"doc_read_verify#chunk001": [0.1, 0.2, 0.3]},
    }, ensure_ascii=False, indent=2))
    append_retrieval_feedback(project_name, {
        "feedback_id": "feedback_read_verify",
        "chunk_id": "doc_read_verify#chunk001",
        "rating": "helpful",
        "note": "feedback",
    })

    root = project_path(project_name)
    mirrors = [
        root / "memory.json",
        stories_index_path(project_name),
        creative_profile_path(project_name),
        root / "stories" / "default" / "creative_profile.discussion.json",
        root / "rules.json",
        _story_rules_overrides_path(project_name, "default"),
        root / "rule_conflict_resolutions.json",
        root / "stories" / "default" / "rule_conflict_resolutions.json",
        _project_prompt_options_path(project_name),
        _story_prompt_options_path(project_name, "default"),
        _story_chapter_summaries_path(project_name, "default"),
        root / "stories" / "default" / "outline.discussion.json",
        root / "stories" / "default" / "volumes" / "volume_001.meta.json",
        root / "stories" / "default" / "volumes" / "volume_001.discussion.json",
        root / "stories" / "default" / "arcs" / "arc_001.meta.json",
        root / "stories" / "default" / "arcs" / "arc_001.discussion.json",
        root / "stories" / "default" / "arcs" / "arc_001.chapter_plan.json",
        root / "stories" / "default" / "chapter_outlines" / "chapter_002.meta.json",
        root / "stories" / "default" / "chapter_outlines" / "chapter_002.discussion.json",
        character_entities_path(project_name),
        setting_entities_path(project_name),
        extraction_plan_templates_path(project_name),
        knowledge_category_path(project_name, "characters"),
        pending_knowledge_path(project_name),
        entity_aliases_path(project_name),
        long_reference_batch_path(project_name, batch["batch_id"]),
        auto_review_policy_path(project_name),
        auto_review_runs_path(project_name),
        retrieval_eval_cases_path(project_name),
        retrieval_eval_runs_path(project_name),
        retrieval_feedback_path(project_name),
        retrieval_path(project_name) / "manifest.json",
        retrieval_path(project_name) / "vectors.json",
        root / "stories" / "default" / "reviews" / "chapter_001.json",
        evaluation_path(project_name, "default") / "chapter_001.json",
        runs_path(project_name, "default") / "workflow_read_verify.json",
    ]
    deleted = []
    for file in mirrors:
        if _safe_unlink(root, file):
            deleted.append(str(file.relative_to(root)))

    failures: list[str] = []
    _expect(load_memory(project_name).get("title") == "DB First Verify", "memory", failures)
    _expect(load_stories_index(project_name).get("stories"), "stories_index", failures)
    _expect(load_creative_profile(project_name).get("is_configured") is True, "creative_profile", failures)
    _expect(load_creative_profile_discussion_artifact(project_name).get("discussion", {}).get("marker") == "creative_discussion", "creative_profile_discussion", failures)
    _expect(load_project_rules(project_name).get("write") == ["project rule"], "project_rules", failures)
    _expect(load_story_rules(project_name, "default").get("review") == ["story rule"], "story_rules", failures)
    _expect(load_rule_conflict_resolutions(project_name, "project")[0].get("decision") == "project conflict decision", "project_rule_conflicts", failures)
    _expect(load_rule_conflict_resolutions(project_name, "story")[0].get("decision") == "story conflict decision", "story_rule_conflicts", failures)
    _expect(load_project_prompt_options(project_name)[0].get("id") == "project_prompt_verify", "project_prompt_options", failures)
    _expect(load_story_prompt_options(project_name, "default")[0].get("id") == "story_prompt_verify", "story_prompt_options", failures)
    _expect(load_story_chapter_summaries(project_name, "default")[0].get("summary") == "chapter summary", "chapter_summaries", failures)
    _expect(load_outline_discussion_artifact(project_name).get("discussion", {}).get("marker") == "outline_discussion", "outline_discussion", failures)
    _expect(load_volume_metadata(project_name, 1).get("title") == "Volume Verify", "volume_metadata", failures)
    _expect(load_volume_discussion_artifact(project_name, 1).get("discussion", {}).get("marker") == "volume_discussion", "volume_discussion", failures)
    _expect(any(volume.get("volume_no") == 1 for volume in list_volumes(project_name)), "volume_list", failures)
    _expect(load_arc_metadata(project_name, 1).get("title") == "Arc Verify", "arc_metadata", failures)
    _expect(load_arc_discussion_artifact(project_name, 1).get("discussion", {}).get("marker") == "arc_discussion", "arc_discussion", failures)
    _expect(load_arc_chapter_plan(project_name, 1).get("plan", {}).get("marker") == "arc_plan", "arc_chapter_plan", failures)
    _expect(any(arc.get("arc_no") == 1 for arc in list_arcs(project_name)), "arc_list", failures)
    _expect(load_chapter_outline_metadata(project_name, 2).get("volume_no") == 1, "chapter_outline_metadata", failures)
    _expect(load_chapter_discussion_artifact(project_name, 2).get("discussion", {}).get("marker") == "chapter_discussion", "chapter_discussion", failures)
    _expect(load_character_entities(project_name)[0].get("name") == "Character Verify", "character_entities", failures)
    _expect(load_setting_entities(project_name)[0].get("name") == "Setting Verify", "setting_entities", failures)
    _expect(load_extraction_plan_templates(project_name)[0].get("name") == "Template Verify", "extraction_templates", failures)
    _expect(load_knowledge_category(project_name, "characters")[0].get("name") == "Character Verify", "knowledge", failures)
    _expect(load_pending_knowledge_items(project_name)[0].get("pending_id") == "pending_verify", "pending_knowledge", failures)
    _expect(load_entity_aliases(project_name)[0].get("canonical_name") == "Character Verify", "entity_aliases", failures)
    _expect(load_long_reference_batch(project_name, batch["batch_id"]).get("title") == "Batch Verify", "long_reference_batch", failures)
    _expect(load_auto_review_policy(project_name).get("min_confidence") == 0.5, "auto_review_policy", failures)
    _expect(load_auto_review_runs(project_name)[0].get("run_id") == "auto_read_verify", "auto_review_runs", failures)
    _expect(load_retrieval_eval_cases(project_name)[0].get("case_id") == "case_read_verify", "retrieval_eval_cases", failures)
    _expect(load_retrieval_eval_runs(project_name)[0].get("run_id") == "eval_read_verify", "retrieval_eval_runs", failures)
    _expect(load_retrieval_feedback(project_name)[0].get("feedback_id") == "feedback_read_verify", "retrieval_feedback", failures)
    _expect("doc_read_verify" in load_retrieval_manifest(project_name), "retrieval_manifest", failures)
    _expect("doc_read_verify#chunk001" in load_retrieval_vectors(project_name), "retrieval_vectors", failures)
    _expect(load_review_json(project_name, 1).get("score") == 9, "review_json", failures)
    _expect(load_evaluation_json(project_name, 1).get("overall_score") == 9, "evaluation_json", failures)
    _expect("workflow_read_verify" in load_pipeline_run(project_name, "workflow_read_verify"), "workflow_run", failures)
    project_runs = list_project_runs(project_name)
    inventory = list_chapter_inventory(project_name)
    _expect(any(run.get("run_id") == "workflow_read_verify" for run in project_runs), "project_manager_runs", failures)
    _expect(any(
        item.get("chapter_no") == 1
        and item.get("has_review_json") is True
        and item.get("has_evaluation") is True
        and item.get("run_count") == 1
        for item in inventory
    ), "project_manager_inventory", failures)
    _expect(any(
        item.get("chapter_no") == 2
        and item.get("metadata", {}).get("volume_no") == 1
        and item.get("metadata", {}).get("arc_no") == 1
        for item in inventory
    ), "project_manager_chapter_metadata_inventory", failures)
    rebuilt_manifest = rebuild_retrieval_assets(project_name, build_vectors=False)
    rebuilt_source_types = {document.source_type for document in rebuilt_manifest.documents}
    _expect("review_payload" in rebuilt_source_types, "retrieval_review_payload", failures)
    _expect("evaluation_payload" in rebuilt_source_types, "retrieval_evaluation_payload", failures)
    _expect("volume_discussion" in rebuilt_source_types, "retrieval_volume_discussion", failures)
    _expect("arc_discussion" in rebuilt_source_types, "retrieval_arc_discussion", failures)
    _expect("arc_chapter_plan" in rebuilt_source_types, "retrieval_arc_chapter_plan", failures)
    _expect("chapter_discussion" in rebuilt_source_types, "retrieval_chapter_discussion", failures)

    health = inspect_project_database(project_name)
    result = {
        "project_name": project_name,
        "ok": not failures and health.get("ok"),
        "deleted_json_mirrors": deleted,
        "failures": failures,
        "health": health,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def main() -> int:
    with isolated_workspace("novelforge_db_first_reads_"):
        return _run_verification()


if __name__ == "__main__":
    raise SystemExit(main())
