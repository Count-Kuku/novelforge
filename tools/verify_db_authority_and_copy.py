from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.verify_utils import isolated_workspace

os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = "0"

from memory import (  # noqa: E402
    auto_review_runs_path,
    conflict_resolutions_path,
    copy_story_settings,
    create_project,
    create_story,
    creative_profile_path,
    entity_aliases_path,
    knowledge_category_path,
    list_pipeline_runs,
    list_retrieval_source_files,
    load_auto_review_runs,
    load_conflict_resolutions,
    load_creative_profile,
    load_creative_profile_discussion_artifact,
    load_entity_aliases,
    load_knowledge_category,
    load_long_reference_batch,
    load_memory,
    load_pending_knowledge_items,
    load_pipeline_run,
    load_project_prompt_options,
    load_project_rules,
    load_retrieval_eval_cases,
    load_retrieval_eval_runs,
    load_retrieval_feedback,
    load_retrieval_manifest,
    load_retrieval_vectors,
    load_rule_conflict_resolutions,
    load_story_memory,
    load_story_prompt_options,
    load_story_rules,
    long_reference_batch_path,
    pending_knowledge_path,
    project_path,
    retrieval_eval_cases_path,
    retrieval_eval_runs_path,
    retrieval_feedback_path,
    retrieval_path,
    retrieval_sources_path,
    runs_path,
    save_auto_review_runs,
    save_creative_profile,
    save_creative_profile_discussion_artifact,
    save_entity_aliases,
    save_knowledge_category,
    save_memory,
    save_pending_knowledge_items,
    save_project_prompt_options,
    save_project_rules,
    save_rule_conflict_resolutions,
    save_story_memory,
    save_story_prompt_options,
    save_story_rules,
)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _expect(condition: bool, label: str, failures: list[str]) -> None:
    if not condition:
        failures.append(label)


def _rules_empty(rules: dict) -> bool:
    return isinstance(rules, dict) and all(not value for value in rules.values())


def _verify_empty_db_is_authoritative() -> list[str]:
    failures: list[str] = []
    project_name = "_db_authority_verify"
    create_project(project_name)

    save_knowledge_category(project_name, "characters", [{"id": "db_character", "name": "DB Character"}])
    save_knowledge_category(project_name, "characters", [])
    _write_json(knowledge_category_path(project_name, "characters"), [{"id": "stale_character", "name": "Stale"}])
    _expect(load_knowledge_category(project_name, "characters") == [], "knowledge_category_empty_db_wins", failures)

    save_entity_aliases(project_name, [{"id": "alias_db", "canonical_name": "DB", "aliases": ["D"]}])
    save_entity_aliases(project_name, [])
    _write_json(entity_aliases_path(project_name), [{"id": "alias_stale", "canonical_name": "Stale"}])
    _expect(load_entity_aliases(project_name) == [], "entity_alias_empty_db_wins", failures)

    save_pending_knowledge_items(project_name, [{"pending_id": "pending_db", "category": "items", "name": "DB"}])
    save_pending_knowledge_items(project_name, [])
    _write_json(pending_knowledge_path(project_name), [{"pending_id": "pending_stale", "category": "items", "name": "Stale"}])
    _expect(load_pending_knowledge_items(project_name) == [], "pending_knowledge_empty_db_wins", failures)

    save_auto_review_runs(project_name, [{"run_id": "auto_db", "status": "completed"}])
    save_auto_review_runs(project_name, [])
    _write_json(auto_review_runs_path(project_name), [{"run_id": "auto_stale", "status": "completed"}])
    _expect(load_auto_review_runs(project_name) == [], "auto_review_runs_empty_db_wins", failures)

    save_project_rules(project_name, {"write": ["project db rule"]})
    save_project_rules(project_name, {})
    _write_json(project_path(project_name) / "rules.json", {"write": ["project stale rule"]})
    _expect(_rules_empty(load_project_rules(project_name)), "project_rules_empty_db_wins", failures)

    save_story_rules(project_name, "default", {"review": ["story db rule"]})
    save_story_rules(project_name, "default", {})
    _write_json(project_path(project_name) / "stories" / "default" / "rules.json", {"review": ["story stale rule"]})
    _expect(_rules_empty(load_story_rules(project_name, "default")), "story_rules_empty_db_wins", failures)

    save_project_prompt_options(project_name, [{"id": "project_prompt_db", "name": "DB", "content": "db"}])
    save_project_prompt_options(project_name, [])
    _write_json(project_path(project_name) / "prompt_options.json", [{"id": "project_prompt_stale", "name": "Stale", "content": "stale"}])
    _expect(load_project_prompt_options(project_name) == [], "project_prompt_options_empty_db_wins", failures)

    save_story_prompt_options(project_name, "default", [{"id": "story_prompt_db", "name": "DB", "content": "db"}])
    save_story_prompt_options(project_name, "default", [])
    _write_json(project_path(project_name) / "stories" / "default" / "prompt_options.json", [{"id": "story_prompt_stale", "name": "Stale", "content": "stale"}])
    _expect(load_story_prompt_options(project_name, "default") == [], "story_prompt_options_empty_db_wins", failures)

    _write_json(conflict_resolutions_path(project_name), [{"conflict_id": "stale", "decision": "stale"}])
    _expect(load_conflict_resolutions(project_name) == [], "conflict_resolutions_empty_db_wins", failures)

    _write_json(retrieval_eval_cases_path(project_name), [{"case_id": "stale", "query": "stale", "expected_terms": ["x"]}])
    _write_json(retrieval_eval_runs_path(project_name), [{"run_id": "stale", "status": "passed"}])
    _write_json(retrieval_feedback_path(project_name), [{"feedback_id": "stale", "rating": "helpful", "chunk_id": "x"}])
    _expect(load_retrieval_eval_cases(project_name) == [], "retrieval_eval_cases_empty_db_wins", failures)
    _expect(load_retrieval_eval_runs(project_name) == [], "retrieval_eval_runs_empty_db_wins", failures)
    _expect(load_retrieval_feedback(project_name) == [], "retrieval_feedback_empty_db_wins", failures)

    _write_json(long_reference_batch_path(project_name, "stale_batch"), {"batch_id": "stale_batch", "title": "Stale"})
    _expect(load_long_reference_batch(project_name, "stale_batch") == {}, "long_reference_batch_missing_db_wins", failures)

    _write_json(runs_path(project_name) / "stale_run.json", {"run_id": "stale_run", "success": True})
    _expect(list_pipeline_runs(project_name) == [], "pipeline_run_list_empty_db_wins", failures)
    _expect(load_pipeline_run(project_name, "stale_run") == "", "pipeline_run_missing_db_wins", failures)

    _write_text(retrieval_sources_path(project_name) / "stale_source.md", "stale source")
    _expect(list_retrieval_source_files(project_name) == [], "retrieval_source_files_empty_db_wins", failures)

    _write_json(retrieval_path(project_name) / "manifest.json", {"documents": [{"doc_id": "stale"}], "chunks": []})
    _write_json(retrieval_path(project_name) / "vectors.json", {"vectors": {"stale": [0.1]}})
    _expect(load_retrieval_manifest(project_name) == "", "retrieval_manifest_empty_db_wins", failures)
    _expect(load_retrieval_vectors(project_name) == "", "retrieval_vectors_empty_db_wins", failures)

    return failures


def _verify_copy_story_settings_uses_db() -> list[str]:
    failures: list[str] = []
    project_name = "_db_copy_story_verify"
    create_project(project_name)
    source_story = create_story(project_name, "源故事")
    target_story = create_story(project_name, "目标故事")
    source_id = source_story["story_id"]
    target_id = target_story["story_id"]

    save_memory(project_name, {"title": "复制验证", "genre": "基础类型"})
    source_memory = load_memory(project_name)
    source_memory["genre"] = "源故事类型"
    source_memory["characters"] = [{"name": "复制角色"}]
    save_story_memory(project_name, source_id, source_memory)

    save_creative_profile(
        project_name,
        {
            "story_mode": "主线故事",
            "target_length": "短篇",
            "target_word_count": "12000",
            "notes": "copy profile notes",
        },
        source_id,
        mark_configured=True,
    )
    save_creative_profile_discussion_artifact(
        project_name,
        {"marker": "copy_discussion"},
        "copy discussion report",
        source_id,
    )
    save_story_rules(project_name, source_id, {"write": ["copy story rule"]})
    save_story_prompt_options(project_name, source_id, [{
        "id": "copy_prompt",
        "name": "Copy Prompt",
        "capability": "write",
        "category": "custom",
        "slot": "custom",
        "content": "copy prompt content",
        "enabled": True,
    }])
    save_rule_conflict_resolutions(project_name, "story", [{
        "id": "copy_conflict",
        "scope": "write",
        "title": "Copy Conflict",
        "decision": "copy conflict decision",
    }], source_id)

    copy_story_settings(project_name, source_id, target_id)

    target_profile = load_creative_profile(project_name, target_id)
    _expect(target_profile.get("is_configured") is True, "copy_profile_configured", failures)
    _expect(target_profile.get("target_word_count") == "12000", "copy_profile_word_count", failures)
    _expect(target_profile.get("notes") == "copy profile notes", "copy_profile_notes", failures)

    target_discussion = load_creative_profile_discussion_artifact(project_name, target_id)
    _expect(target_discussion.get("discussion", {}).get("marker") == "copy_discussion", "copy_discussion", failures)
    _expect(target_discussion.get("report_markdown") == "copy discussion report", "copy_discussion_report", failures)

    target_memory = load_story_memory(project_name, target_id)
    _expect(target_memory.get("genre") == "源故事类型", "copy_story_memory_genre", failures)
    _expect(any(item.get("name") == "复制角色" for item in target_memory.get("characters", [])), "copy_story_memory_characters", failures)

    _expect("copy story rule" in load_story_rules(project_name, target_id).get("write", []), "copy_story_rules", failures)
    _expect(any(item.get("id") == "copy_prompt" for item in load_story_prompt_options(project_name, target_id)), "copy_story_prompt_options", failures)
    _expect(any(item.get("decision") == "copy conflict decision" for item in load_rule_conflict_resolutions(project_name, "story", target_id)), "copy_story_rule_conflicts", failures)
    _expect(not creative_profile_path(project_name, target_id).exists(), "copy_does_not_require_profile_json_mirror", failures)

    return failures


def main() -> int:
    with isolated_workspace("novelforge_db_authority_copy_"):
        failures = []
        failures.extend(_verify_empty_db_is_authoritative())
        failures.extend(_verify_copy_story_settings_uses_db())
        result = {"ok": not failures, "failures": failures}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())