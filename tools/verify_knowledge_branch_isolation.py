"""Verify knowledge-center search and edit isolation across story branches."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from novelforge.services import memory
from novelforge.services.memory.knowledge_center import assert_story_knowledge_writable
from tools.verify_utils import isolated_workspace


def main() -> int:
    failures: list[str] = []
    checks: list[str] = []

    def check(condition: bool, label: str) -> None:
        (checks if condition else failures).append(label)

    with isolated_workspace("novelforge_knowledge_branch_"):
        project = memory.create_project("knowledge_branch")
        story_id = memory.create_story(project, "知识隔离", creation_mode="conversational")["story_id"]
        main_branch = memory.default_branch_id(story_id)
        memory.ensure_story_branch(project, story_id, main_branch)
        memory.upsert_knowledge_category_item_record(
            project,
            "characters",
            {
                "id": "k-main",
                "name": "主线角色",
                "summary": "主线设定",
                "setting_scope": "story",
                "story_id": story_id,
                "branch_id": main_branch,
                "status": "confirmed",
                "evidence": [{"quote": "主线证据"}],
            },
        )
        memory.upsert_knowledge_category_item_record(
            project,
            "world_rules",
            {
                "id": "k-world-rule",
                "name": "世界规则",
                "summary": "分叉前规则",
                "rule": "分叉前规则",
                "setting_scope": "story",
                "story_id": story_id,
                "branch_id": main_branch,
                "status": "confirmed",
            },
        )
        child_branch = memory.fork_story_branch(
            project,
            story_id,
            parent_branch_id=main_branch,
            name="子线",
            allow_current_state=True,
            create_session=False,
        )["branch"]["branch_id"]
        memory.upsert_knowledge_category_item_record(
            project,
            "characters",
            {
                "id": "k-child",
                "name": "子线角色",
                "summary": "子线设定",
                "setting_scope": "story",
                "story_id": story_id,
                "branch_id": child_branch,
                "status": "confirmed",
            },
        )
        # A parent edit after the fork must not alter the child's frozen view.
        memory.upsert_knowledge_category_item_record(
            project,
            "characters",
            {
                "id": "k-main",
                "name": "主线角色",
                "summary": "父线后来修订",
                "setting_scope": "story",
                "story_id": story_id,
                "branch_id": main_branch,
                "status": "confirmed",
                "evidence": [{"quote": "父线未来证据"}],
            },
        )
        memory.upsert_knowledge_category_item_record(
            project,
            "world_rules",
            {
                "id": "k-world-rule",
                "name": "世界规则",
                "summary": "父线未来规则",
                "rule": "父线未来规则",
                "setting_scope": "story",
                "story_id": story_id,
                "branch_id": main_branch,
                "status": "confirmed",
            },
        )

        child_character_cards = memory.load_character_entity_cards(
            project, story_id=story_id, branch_id=child_branch,
        )
        child_setting_cards = memory.load_setting_entity_cards(
            project, story_id=story_id, branch_id=child_branch,
        )
        child_graph = memory.load_knowledge_graph(
            project, story_id=story_id, branch_id=child_branch,
        )
        check(
            any(card.get("summary") == "主线设定" for card in child_character_cards)
            and not any(card.get("summary") == "父线后来修订" for card in child_character_cards),
            "子线角色卡使用分叉时冻结的实体摘要",
        )
        check(
            any(card.get("summary") == "分叉前规则" for card in child_setting_cards)
            and not any(card.get("summary") == "父线未来规则" for card in child_setting_cards),
            "子线设定卡使用分叉时冻结的实体摘要",
        )
        check("父线后来修订" not in json.dumps(child_graph, ensure_ascii=False), "子线图谱不读取父线未来实体投影")

        main_result = memory.search_knowledge_center(project, query="主线角色", story_id=story_id)
        child_result = memory.search_knowledge_center(
            project, query="主线角色", story_id=story_id, branch_id=child_branch
        )
        child_only = memory.search_knowledge_center(project, query="子线角色", story_id=story_id)
        check(any(item.get("record_id") == "k-main" for item in main_result["items"]), "主线可搜索主线知识")
        check(not any(item.get("record_id") == "k-child" for item in main_result["items"]), "主线不混入子线知识")
        check(any(item.get("record_id") == "k-main" for item in child_result["items"]), "子线可读冻结继承知识")
        check(not any(item.get("record_id") == "k-child" for item in child_only["items"]), "主线不读子线私有知识")

        inherited = memory.load_knowledge_center_record(
            project, "knowledge", "k-main", story_id=story_id, branch_id=child_branch
        )
        check(inherited.get("visible_from_checkpoint") is True, "子线详情标识冻结继承")
        frozen_revisions = memory.load_visible_story_knowledge_revisions(
            project, "k-main", story_id=story_id, branch_id=child_branch
        )
        frozen_evidence = memory.load_visible_story_knowledge_evidence(
            project, "k-main", story_id=story_id, branch_id=child_branch
        )
        check(len(frozen_revisions) == 1 and frozen_revisions[0].get("frozen") is True, "子线修订历史冻结在分叉基线")
        check(any(item.get("quote") == "主线证据" for item in frozen_evidence), "子线证据读取冻结快照")
        try:
            assert_story_knowledge_writable(project, story_id, child_branch, "k-main")
        except ValueError:
            check(True, "子线编辑父线继承知识被拒绝")
        else:
            check(False, "子线编辑父线继承知识被拒绝")

        override = memory.create_story_knowledge_override(
            project,
            inherited,
            {"summary": "子线独立修订"},
            story_id=story_id,
            branch_id=child_branch,
        )
        override_id = str(override.get("knowledge_id") or override.get("id") or "")
        check(bool(override_id) and override_id != "k-main", "编辑继承知识创建本线新 ID")
        child_after_override = memory.load_knowledge_center_record(
            project, "knowledge", "k-main", story_id=story_id, branch_id=child_branch
        )
        override_evidence = memory.load_visible_story_knowledge_evidence(
            project, override_id, story_id=story_id, branch_id=child_branch
        )
        parent_after_override = memory.load_knowledge_center_record(
            project, "knowledge", "k-main", story_id=story_id, branch_id=main_branch
        )
        check(child_after_override.get("knowledge_id") == override_id, "子线按 origin 显示独立副本")
        check(child_after_override.get("payload", {}).get("summary") == "子线独立修订", "子线独立副本修订生效")
        check(any(item.get("quote") == "主线证据" for item in override_evidence), "独立副本保留冻结证据")
        check(not any(item.get("quote") == "父线未来证据" for item in override_evidence), "独立副本不读取父线未来证据")
        check(parent_after_override.get("payload", {}).get("summary") == "父线后来修订", "父线后续修订独立保留")
        override_again = memory.create_story_knowledge_override(
            project,
            inherited,
            {"summary": "子线再次修订"},
            story_id=story_id,
            branch_id=child_branch,
        )
        check(str(override_again.get("knowledge_id") or "") == override_id, "并发式重复 override 复用当前线副本")

        own = memory.load_knowledge_center_record(
            project, "knowledge", "k-child", story_id=story_id, branch_id=child_branch
        )
        check(own.get("branch_id") == child_branch, "子线私有知识归属正确")

    print(json.dumps({"ok": not failures, "checks": checks, "failures": failures}, ensure_ascii=False, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
