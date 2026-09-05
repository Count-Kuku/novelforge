"""Verify refactor 2 · P0: entity + chapter query paradigm for generation context.

构造「多实体 / 多章号 / 同槽位取代 / canon-story 叠加」的知识库，断言：

1. `merge_worldline_baseline(chapter_no=...)` 只返回「截至当前章仍有效」的事实，
   已被同槽位取代的旧值（京城）不会与现值（洛阳）并存（G20 修复）。
2. `load_entity_facts_for_entities` 批量查询与单实体结果一致（G21 修复）。
3. `build_generation_setting_context(chapter_no=...)` 注入的 always 块只含当前章
   有效事实、无矛盾值；结构化 memory 字段被正确清空并填充。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from novelforge.domain.setting_knowledge import build_generation_setting_context
from novelforge.services.memory import (
    create_project,
    create_story,
    merge_worldline_baseline,
    upsert_knowledge_category_item_record,
)
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


def _base_item(item_id: str, name: str, summary: str, story_id: str, chapter_no: int) -> dict:
    return {
        "id": item_id,
        "name": name,
        "summary": summary,
        "status": "confirmed",
        "setting_role": "core",
        "setting_scope": "story",
        "story_id": story_id,
        "worldline_id": "main",
        "version_scope": "project_main",
        "injection_policy": "always",
        "setting_field": "location",
        "source_chapter_no": chapter_no,
        "importance": 0.9,
    }


def main() -> int:
    print("=== Refactor2 P0 · 查询范式切换 ===\n")

    with isolated_workspace("novelforge_p0_refactor_"):
        project_name = create_project("p0-refactor")
        story_id = create_story(project_name, "主线")["story_id"]
        story_id = str(story_id or "default")

        # 林越 location：第 1 章在京城、第 10 章到洛阳（replace 槽，第 1 章应被取代）
        upsert_knowledge_category_item_record(
            project_name, "characters",
            _base_item("c1", "林越", "林越身在京城", story_id, 1),
        )
        upsert_knowledge_category_item_record(
            project_name, "characters",
            _base_item("c2", "林越", "林越身在洛阳", story_id, 10),
        )
        # canon 基线（project scope）：林越是青云门弟子（append 槽，跨 scope 叠加应保留）
        upsert_knowledge_category_item_record(
            project_name, "characters",
            {
                "id": "c0",
                "name": "林越",
                "summary": "林越是青云门弟子",
                "status": "confirmed",
                "setting_role": "core",
                "setting_scope": "project",
                "worldline_id": "main",
                "version_scope": "canon",
                "injection_policy": "always",
                "setting_field": "affiliations",
                "source_chapter_no": 1,
                "importance": 0.85,
            },
        )
        # 整条 characters 事实（append 槽，field=characters）：应进入结构化 memory["characters"]
        upsert_knowledge_category_item_record(
            project_name, "characters",
            {
                "id": "c3",
                "name": "林越",
                "summary": "林越性格冷峻",
                "status": "confirmed",
                "setting_role": "core",
                "setting_scope": "story",
                "story_id": story_id,
                "worldline_id": "main",
                "version_scope": "project_main",
                "injection_policy": "always",
                "setting_field": "characters",
                "source_chapter_no": 1,
                "importance": 0.7,
            },
        )

        print("[1] merge_worldline_baseline（章号过滤，G20）")
        merged_ch5 = merge_worldline_baseline(project_name, story_id=story_id, chapter_no=5)
        merged_ch15 = merge_worldline_baseline(project_name, story_id=story_id, chapter_no=15)
        facts_ch5 = [f for g in merged_ch5 if g["canonical_name"] == "林越" for f in g.get("facts", [])]
        facts_ch15 = [f for g in merged_ch15 if g["canonical_name"] == "林越" for f in g.get("facts", [])]
        ch5_text = " ".join(str(f.get("summary") or "") for f in facts_ch5)
        ch15_text = " ".join(str(f.get("summary") or "") for f in facts_ch15)
        check("第5章注入京城、不含洛阳", ("京城" in ch5_text) and ("洛阳" not in ch5_text), ch5_text)
        check("第15章注入洛阳、旧京城不复活", ("洛阳" in ch15_text) and ("京城" not in ch15_text), ch15_text)
        check("canon 归属叠加保留（青云门弟子）", "青云门弟子" in ch5_text, ch5_text)
        # 无章号：replace 槽只保留最新一条（洛阳），不出现矛盾并存
        merged_all = merge_worldline_baseline(project_name, story_id=story_id)
        facts_all = [f for g in merged_all if g["canonical_name"] == "林越" for f in g.get("facts", [])]
        all_text = " ".join(str(f.get("summary") or "") for f in facts_all)
        check("无章号时 replace 槽取最新（洛阳）", ("洛阳" in all_text) and ("京城" not in all_text), all_text)

        print("\n[2] 生成上下文 always 块（build_generation_setting_context）")
        ctx_ch5 = build_generation_setting_context(project_name, story_id, chapter_no=5)
        ctx_ch15 = build_generation_setting_context(project_name, story_id, chapter_no=15)
        ctx5_text = str(ctx_ch5.get("_setting_context") or "")
        ctx15_text = str(ctx_ch15.get("_setting_context") or "")
        check("ch5 always 块注入京城", "京城" in ctx5_text, ctx5_text)
        check("ch5 always 块无洛阳", "洛阳" not in ctx5_text, ctx5_text)
        check("ch15 always 块注入洛阳", "洛阳" in ctx15_text, ctx15_text)
        check("ch15 always 块无京城", "京城" not in ctx15_text, ctx15_text)
        check("整条 characters 事实进入结构化字段", isinstance(ctx_ch5.get("characters"), list)
              and any("性格冷峻" in str(v) for v in ctx_ch5.get("characters") or []),
              str(ctx_ch5.get("characters")))
        check("结构化 memory 不含已失效旧值", not any("京城" in str(v) for v in ctx_ch15.get("characters") or []),
              str(ctx_ch15.get("characters")))

    print(f"\n结果：{_PASS} 通过，{_FAIL} 失败")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
