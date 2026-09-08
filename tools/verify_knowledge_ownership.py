"""离线验证资料批次、任务和提取上下文的显式归属。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.domain.ingestion_tasks import create_ingestion_task
from novelforge.services import memory
from novelforge.workflows.skills import common
from novelforge.services.memory import story_rules
from novelforge.services.memory.long_reference_batches import create_long_reference_batch, load_long_reference_batch
from novelforge.workflows.source_workflows.consolidation import enrich_consolidated_knowledge_items
from tools.verify_utils import isolated_workspace


CHECKS: list[str] = []


def check(value: bool, label: str) -> None:
    if not value:
        raise AssertionError(label)
    CHECKS.append(label)


def verify() -> None:
    # Project extraction/recall/consolidation must never turn an empty story id
    # into the legacy default story through a loader's own default argument.
    def story_loader_must_not_run(*_args, **_kwargs):
        raise AssertionError("project extraction unexpectedly loaded story context")

    def conflict_loader(project_name, layer, story_id=""):
        if layer == "story":
            raise AssertionError("project extraction unexpectedly loaded story conflict decisions")
        return []

    with (
        patch.object(common, "load_story_rules", story_loader_must_not_run),
        patch.object(story_rules, "load_rule_conflict_resolutions", conflict_loader),
        patch.object(common, "load_creative_profile", story_loader_must_not_run),
        patch.object(common, "load_story_prompt_options", story_loader_must_not_run),
        patch.object(common, "_call_json_llm", return_value={"items": []}),
    ):
        extraction = common.extract_reference_knowledge("ownership", "资料", "文本", story_id="")
        recall = common.recall_missed_knowledge("ownership", "资料", "文本", [], story_id="")
        consolidation = common.consolidate_extracted_knowledge("ownership", "资料", [], story_id="")
    check(extraction.get("success") and recall.get("success") and consolidation.get("success"), "项目提取整理召回不访问故事加载器")

    with patch.object(
        common,
        "load_entity_aliases",
        return_value=[
            {"canonical_name": "全局实体", "aliases": ["全局别名"], "story_id": ""},
            {"canonical_name": "故事A实体", "aliases": ["A别名"], "story_id": "story_a"},
            {"canonical_name": "故事B实体", "aliases": ["B别名"], "story_id": "story_b"},
        ],
    ):
        project_aliases = common._format_entity_alias_context("ownership", story_id="", limit=10)
        story_aliases = common._format_entity_alias_context("ownership", story_id="story_a", limit=10)
    check("全局实体" in project_aliases and "故事A实体" not in project_aliases, "项目提取只使用项目/全局别名")
    check("全局实体" in story_aliases and "故事A实体" in story_aliases and "故事B实体" not in story_aliases, "故事提取只使用共享及同故事别名")

    with isolated_workspace("novelforge_knowledge_ownership_"):
        project_name = "knowledge_ownership_verify"
        memory.create_project(project_name)
        story = memory.create_story(project_name, "故事A")
        story_id = str(story["story_id"])
        batch_project = create_long_reference_batch(
            project_name,
            title="项目资料",
            scope="reference",
            authority="curated",
            source_type="external_source",
            story_id="",
            target_scope="project",
            segments=[{"title": "片段", "content": "项目事实"}],
        )
        batch_story = create_long_reference_batch(
            project_name,
            title="故事资料",
            scope="reference",
            authority="curated",
            source_type="external_source",
            story_id=story_id,
            target_scope="story",
            segments=[{"title": "片段", "content": "故事事实"}],
        )
        project_loaded = load_long_reference_batch(project_name, str(batch_project["batch_id"]))
        story_loaded = load_long_reference_batch(project_name, str(batch_story["batch_id"]))
        check(project_loaded.get("target_scope") == "project" and project_loaded.get("story_id", "") == "", "项目批次保存恢复归属")
        check(story_loaded.get("target_scope") == "story" and story_loaded.get("story_id") == story_id, "故事批次保存恢复归属")

        task = create_ingestion_task(
            batch_project,
            [0],
            configuration={
                "enabled_categories": ["characters"],
                "extraction_mode": "general",
                "target_scope": "project",
                "target_story_id": "",
            },
            story_id="",
        )
        saved_task = memory.save_source_ingestion_task(project_name, task)
        loaded_task = memory.load_source_ingestion_task(project_name, str(saved_task["task_id"]))
        config = loaded_task.get("configuration") or {}
        check(config.get("target_scope") == "project" and config.get("target_story_id", "") == "", "项目任务配置保存恢复归属")

    project_items = common.build_pending_knowledge_from_reference_extraction(
        [{"category": "characters", "name": "项目角色", "summary": "事实"}],
        scope="reference",
        setting_scope="project",
        story_id="",
    )
    story_items = common.build_pending_knowledge_from_reference_extraction(
        [{"category": "characters", "name": "故事角色", "summary": "事实"}],
        scope="reference",
        setting_scope="story",
        story_id="story_a",
    )
    check(project_items[0]["setting_scope"] == "project" and project_items[0].get("story_id", "") == "", "项目提取条目保持项目归属")
    check(story_items[0]["setting_scope"] == "story" and story_items[0]["story_id"] == "story_a", "故事提取条目保持故事归属")

    separated = enrich_consolidated_knowledge_items(
        [
            {"category": "characters", "name": "甲", "summary": "甲事实"},
            {"category": "characters", "name": "乙", "summary": "乙事实"},
        ],
        [
            {"pending_id": "p-a", "category": "characters", "name": "甲", "aliases": ["甲别名"], "setting_field": "status", "source_segment_id": "seg-a"},
            {"pending_id": "p-b", "category": "characters", "name": "乙", "aliases": ["乙别名"], "setting_field": "location", "source_segment_id": "seg-b"},
        ],
        "balanced",
    )
    check(
        separated[0].get("aliases") == ["甲别名"]
        and separated[0].get("setting_field") == "status"
        and separated[0].get("source_segment_ids") == ["seg-a"]
        and separated[1].get("aliases") == ["乙别名"]
        and separated[1].get("setting_field") == "location"
        and separated[1].get("source_segment_ids") == ["seg-b"],
        "整理按同名条目继承别名、事实槽和来源不串批次",
    )
    pending_separated = common.build_pending_knowledge_from_reference_extraction(
        separated,
        scope="reference",
        setting_scope="project",
        story_id="",
    )
    check(
        pending_separated[0].get("setting_field") == "status"
        and pending_separated[0].get("source_segment_id") == "seg-a"
        and pending_separated[0].get("source_segment_ids") == ["seg-a"]
        and pending_separated[0].get("merged_from_pending_ids") == ["p-a"],
        "整理后的条目持久化保留事实槽和可追溯片段",
    )


def main() -> int:
    try:
        verify()
    except Exception as exc:
        print(json.dumps({"ok": False, "checks": CHECKS, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "checks": CHECKS}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
