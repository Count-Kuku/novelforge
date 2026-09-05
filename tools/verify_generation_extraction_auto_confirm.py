"""Verify refactor 2 · P4: generation-time extraction auto-confirm.

覆盖「生成时提取 → 自动确认」机制（D10）：

1. 章节设定提炼产物（build_pending_knowledge_from_setting_extraction）入队后，
   经 auto_confirm_pending_items_without_risk 自动确认：条目从 pending 转入已确认知识。
2. 自动确认保留两道硬门槛：结构校验失败（缺必填 typed 字段）的候选仍被挡下（blocked）。
3. P4 修改点（generation.extract_setting_candidates_from_chapter / interactive_writing.
   extract_fragment_knowledge）所在模块可导入、符号存在。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = "0"

from novelforge.domain.knowledge_workflows import evaluate_pending_auto_review_decision
from novelforge.domain.knowledge_types import validate_typed_knowledge_item
from novelforge.services.memory import (
    create_project,
    create_story,
    load_knowledge_category,
    load_pending_knowledge_items,
    queue_pending_knowledge_items,
)
from novelforge.workflows.source_workflows import auto_confirm_pending_items_without_risk
from tools.verify_utils import isolated_workspace

_PASS = 0
_FAIL = 0


def check(label: str, ok: bool, detail: str = ""):
    global _PASS, _FAIL
    if ok:
        _PASS += 1
        print(f"  PASS  {label}")
    else:
        _FAIL += 1
        print(f"  FAIL  {label}  {detail}")


def main() -> int:
    print("=== Refactor2 P4 · 生成时提取自动确认 ===\n")
    with isolated_workspace("novelforge_p4_autoconfirm_"):
        project_name = create_project("p4-autoconfirm")
        story_id = str(create_story(project_name, "主线").get("story_id") or "default")

        print("[1] 章节设定提炼产物自动确认")
        from novelforge.workflows.skills.common import build_pending_knowledge_from_setting_extraction

        update_data = {
            "chapter_no": 3,
            "chapter_summary": "第3章 林越在洛阳遭袭",
            "new_characters": [{"name": "林越", "location": "洛阳"}],
            "world_updates": ["青云门封山"],
            "timeline_updates": [],
            "foreshadowing_updates": [],
        }
        pending_items = build_pending_knowledge_from_setting_extraction(
            update_data, story_id, chapter_no=3, project_name=project_name
        )
        check("提炼产物带 pending_id", all(str(i.get("pending_id")) for i in pending_items), str(len(pending_items)))
        queued = queue_pending_knowledge_items(
            project_name, pending_items, scope="project", authority="project",
            source_title="第 3 章正文", source_origin="chapter_update",
        )
        check("入队成功", queued == len(pending_items), f"queued={queued}")
        ids = [str(i["pending_id"]) for i in pending_items]
        result = auto_confirm_pending_items_without_risk(
            project_name, ids, source_type="chapter_update", source_title="第 3 章正文",
            note="verify P4",
        )
        confirmed_ids = result.get("confirmed_ids") or []
        blocked_ids = result.get("blocked_ids") or []
        # 角色林越条目自动确认；world_updates「青云门封山」缺 world_rules 必填 typed 字段 rule，
        # 被硬门槛拦截（结构校验失败）——这正是两道硬门槛该保护的对象。
        check("合法候选自动确认（characters）", len(confirmed_ids) >= 1,
              f"confirmed={len(confirmed_ids)} blocked={len(blocked_ids)}")
        check("结构非法候选被硬门槛拦截（world_rules 缺必填）", len(blocked_ids) == 1,
              f"blocked={len(blocked_ids)} reasons={result.get('blocked_reasons')}")
        check("确认结果含审计 run_id", bool(result.get("run_id")), str(result.get("run_id")))
        remaining = load_pending_knowledge_items(project_name)
        check("仅非法候选滞留 pending（1 条）", len(remaining) == 1, str(len(remaining)))
        chars = load_knowledge_category(project_name, "characters")
        check("林越事实已入库", any("林越" in str(item.get("name")) for item in chars), str(len(chars)))

        print("\n[2] 两道硬门槛仍拦截结构非法候选")
        invalid = {
            "pending_id": "invalid_1",
            "category": "items",
            "name": "缺字段道具",
            "summary": "缺少 typed 必填字段 functions",
            "confidence": 0.9,
            "evidence_strength": 0.9,
            "evidence": [{"quote": "x"}],
        }
        typed_errors = validate_typed_knowledge_item(invalid, "items")
        decision = evaluate_pending_auto_review_decision(invalid, {}, {})
        check("结构校验失败被拦截", bool(typed_errors) and decision.get("decision") == "blocked",
              f"decision={decision.get('decision')} errors={typed_errors}")

        print("\n[3] P4 修改点模块符号存在")
        import inspect
        import novelforge.workflows.interactive_writing
        import novelforge.workflows.skills.generation

        from novelforge.workflows.interactive_writing import extract_fragment_knowledge
        from novelforge.workflows.skills.generation import extract_setting_candidates_from_chapter

        check("extract_setting_candidates_from_chapter 存在", callable(extract_setting_candidates_from_chapter))
        check("extract_fragment_knowledge 存在", callable(extract_fragment_knowledge))
        src_auto_confirm = inspect.getsource(extract_setting_candidates_from_chapter)
        frag_auto_confirm = inspect.getsource(extract_fragment_knowledge)
        check("章节提炼已接入 auto_confirm", "auto_confirm_pending_items_without_risk" in src_auto_confirm)
        check("片段提炼已接入 auto_confirm", "auto_confirm_pending_items_without_risk" in frag_auto_confirm)

    print(f"\n结果：{_PASS} 通过，{_FAIL} 失败")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
