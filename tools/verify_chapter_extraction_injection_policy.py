from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from novelforge.domain.setting_knowledge import (
    build_generation_setting_context,
    list_setting_items,
    upsert_setting_item,
)
from novelforge.services.memory import create_project
from novelforge.workflows.skills.common import build_pending_knowledge_from_setting_extraction
from tools.verify_utils import isolated_workspace


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


# 同一槽位（timeline）在不同章节被写入不同值，用来复现「跨章多版本」场景。
CHAPTER_SUMMARIES = {
    1: "林越身在京城",
    2: "林越身在洛阳",
    3: "林越身在江南",
}


def verify_extraction_default(project_name: str, story_id: str) -> list[dict]:
    """章节设定抽取的产物默认不应强制注入每一章。"""
    items: list[dict] = []
    for chapter_no, summary in CHAPTER_SUMMARIES.items():
        items.extend(
            build_pending_knowledge_from_setting_extraction(
                {"timeline_updates": [summary]},
                story_id,
                chapter_no,
                project_name=project_name,
            )
        )
    check(len(items) == len(CHAPTER_SUMMARIES), f"每章产出一条时间线条目（共 {len(CHAPTER_SUMMARIES)} 条）")
    for item in items:
        chapter_no = item.get("source_chapter_no")
        check(
            item.get("injection_policy") == "retrieval",
            f"第 {chapter_no} 章抽取条目默认走检索，不再强制注入",
        )
        check(item.get("setting_role") == "core", f"第 {chapter_no} 章抽取条目仍是正式结构化设定")
        check(item.get("setting_field") == "timeline", f"第 {chapter_no} 章抽取条目仍归属 timeline 槽位")
    names = {str(item.get("name") or "") for item in items}
    check(len(names) == len(items), "跨章同槽位条目名称仍各不相同（归并缺失，属已知待办）")
    return items


def verify_injection_behavior(project_name: str, story_id: str, items: list[dict]) -> None:
    """写入正式库后：不进 always 块，但仍留在知识库可被召回。"""
    for index, item in enumerate(items):
        upsert_setting_item(
            project_name,
            str(item.get("category") or ""),
            dict(item, id=f"chapter_extracted_{index}", status="confirmed", story_id=story_id),
        )

    # 正向对照：手工设定的 always 条目必须出现，否则说明断言本身不灵敏。
    upsert_setting_item(
        project_name,
        "timeline_events",
        {
            "id": "control_always",
            "name": "对照条目",
            "summary": "手工确认的主线起点",
            "status": "confirmed",
            "setting_role": "core",
            "setting_scope": "story",
            "setting_field": "timeline",
            "story_id": story_id,
            "injection_policy": "always",
            "worldline_id": "main",
            "worldline_label": "主线",
        },
    )

    setting_context = str(build_generation_setting_context(project_name, story_id).get("_setting_context") or "")
    check("手工确认的主线起点" in setting_context, "对照组：always 条目仍然注入（断言有效）")
    for summary in CHAPTER_SUMMARIES.values():
        check(summary not in setting_context, f"「{summary}」不再进入生成设定上下文")

    always_rows = list_setting_items(project_name, story_id, injection_policies={"always"})
    always_summaries = {str(row.get("summary") or "") for row in always_rows}
    for summary in CHAPTER_SUMMARIES.values():
        check(summary not in always_summaries, f"「{summary}」不再占用 always 硬约束预算")

    core_rows = list_setting_items(project_name, story_id, core_only=True)
    core_summaries = {str(row.get("summary") or "") for row in core_rows}
    for summary in CHAPTER_SUMMARIES.values():
        check(summary in core_summaries, f"「{summary}」仍留在知识库，可被检索或手工选入")


def main() -> int:
    with isolated_workspace("novelforge_chapter_extraction_policy_"):
        project_name = create_project("chapter-extraction-policy")
        story_id = "default"
        items = verify_extraction_default(project_name, story_id)
        verify_injection_behavior(project_name, story_id, items)
    print(json.dumps({"ok": True, "checks": len(CHECKS)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
