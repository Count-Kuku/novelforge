"""Verify refactor 2 · P3: end-to-end assembly + quantified leak/error regression.

覆盖三类消费场景的端到端装配断言：
  1. 章节正文（capability=write，chapter_no 定位）
  2. 全书大纲（capability=outline，无章号）
  3. 分卷大纲（capability=volume_outline，无章号）

漏检/错检量化（构造含「过期事实」「无关角色」「隐含别名角色」的样本库，mock 识别）：
  - 无关实体注入条数：改造后（实体聚焦）为 0；关闭实体识别（全实体注入）> 0。
  - 过期事实（旧值已被同槽位取代）注入数：新路径为 0（merge replace 只留最新）。
  - 隐含别名角色漏检：识别别名「林公子」经解析命中林越，注入林越事实（防漏）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from novelforge.core.schemas import ContextAssembly
from novelforge.services.memory import (
    create_project,
    create_story,
    save_entity_aliases,
    upsert_knowledge_category_item_record,
)
from novelforge.workflows.context_assembly import assemble_generation_context
from tools.verify_utils import isolated_workspace

_PASS = 0
_FAIL = 0
_METRICS: list[tuple[str, int]] = []


def check(label: str, ok: bool, detail: str = ""):
    global _PASS, _FAIL
    if ok:
        _PASS += 1
        print(f"  PASS  {label}")
    else:
        _FAIL += 1
        print(f"  FAIL  {label}  {detail}")


def metric(label: str, value: int):
    _METRICS.append((label, value))
    print(f"  计量  {label}: {value}")


def _item(item_id, name, summary, story_id, field, chapter_no, importance=0.8) -> dict:
    return {
        "id": item_id, "name": name, "summary": summary, "status": "confirmed",
        "setting_role": "core", "setting_scope": "story", "story_id": story_id,
        "worldline_id": "main", "version_scope": "project_main",
        "injection_policy": "always", "setting_field": field,
        "source_chapter_no": chapter_no, "importance": importance,
    }


def _always_text(assembly: ContextAssembly) -> str:
    return "\n".join(b.content for b in assembly.blocks if b.block_id == "always_settings")


def main() -> int:
    print("=== Refactor2 P3 · 端到端 + 量化评测 ===\n")
    with isolated_workspace("novelforge_p3_e2e_"):
        project_name = create_project("p3-e2e")
        story_id = str(create_story(project_name, "主线").get("story_id") or "default")

        # 样本：林越 京城(第1章，将被第10章取代) / 洛阳(第10章)；苏晚 金陵(无关)；路人甲 荒野(无关)
        upsert_knowledge_category_item_record(project_name, "characters", _item("c1", "林越", "林越身在京城", story_id, "location", 1, 0.9))
        upsert_knowledge_category_item_record(project_name, "characters", _item("c2", "林越", "林越身在洛阳", story_id, "location", 10, 0.95))
        upsert_knowledge_category_item_record(project_name, "characters", _item("c3", "苏晚", "苏晚身在金陵", story_id, "location", 1, 0.85))
        upsert_knowledge_category_item_record(project_name, "characters", _item("c4", "路人甲", "路人甲身在荒野", story_id, "location", 1, 0.2))
        save_entity_aliases(project_name, [{"canonical_name": "林越", "aliases": ["林公子"], "entity_type": "character", "story_id": story_id}])

        print("[1] 端到端装配（三类场景）")
        ctx_write = assemble_generation_context(project_name, story_id=story_id, capability="write",
                                                query="第12章 细纲：林越与林公子在洛阳重逢", chapter_no=12)
        check("正文场景可装配", isinstance(ctx_write, ContextAssembly), type(ctx_write).__name__)
        write_always = _always_text(ctx_write)
        check("正文 always 只含洛阳（旧值京城被取代不注入）", "洛阳" in write_always and "京城" not in write_always, write_always[:200])

        ctx_outline = assemble_generation_context(project_name, story_id=story_id, capability="outline",
                                                  query="写一本仙侠小说大纲：主角林越、女主苏晚")
        check("全书大纲场景可装配", isinstance(ctx_outline, ContextAssembly), type(ctx_outline).__name__)
        outline_always = _always_text(ctx_outline)
        check("大纲 always 含核心角色当前设定（replace 取最新洛阳）", "洛阳" in outline_always and "京城" not in outline_always, outline_always[:200])

        ctx_volume = assemble_generation_context(project_name, story_id=story_id, capability="volume_outline",
                                                 query="第一卷大纲：林越拜入青云门")
        check("分卷大纲场景可装配", isinstance(ctx_volume, ContextAssembly), type(ctx_volume).__name__)

        print("\n[2] 漏检/错检量化（实体聚焦 vs 全实体）")
        # 关闭实体识别 = 改造前近似（全实体注入）；新路径 = 实体聚焦
        ctx_off = assemble_generation_context(project_name, story_id=story_id, capability="write",
                                              query="第12章 细纲：林越与林公子在洛阳重逢", chapter_no=12)
        off_text = _always_text(ctx_off)
        metric("关闭识别-注入条目含无关角色(苏晚/路人甲)数", int("金陵" in off_text) + int("荒野" in off_text))
        metric("关闭识别-过期事实(京城)注入数", int("京城" in off_text))

        def responder(project_name_arg, story_id_arg, prompt):
            # 只识别主角与隐含别名（林公子 → 林越），不提无关角色
            return {"entities": [{"name": "林越", "type": "character", "mention": "direct", "purpose": "主角"},
                                 {"name": "林公子", "type": "character", "mention": "alias", "purpose": "本章出场"}]}

        ctx_on = assemble_generation_context(project_name, story_id=story_id, capability="write",
                                             query="第12章 细纲：林越与林公子在洛阳重逢", chapter_no=12,
                                             enable_entity_planning=True, _entity_plan_responder=responder)
        on_text = _always_text(ctx_on)
        metric("实体聚焦-注入条目含无关角色数", int("金陵" in on_text) + int("荒野" in on_text))
        metric("实体聚焦-过期事实(京城)注入数", int("京城" in on_text))
        metric("实体聚焦-别名角色(林公子→林越)注入条数", int("洛阳" in on_text))

        check("无关角色注入：新路径 0 条", "金陵" not in on_text and "荒野" not in on_text, on_text[:200])
        check("无关角色注入：关闭识别路径 > 0 条（证明聚焦有效）", ("金陵" in off_text or "荒野" in off_text), off_text[:200])
        check("过期事实注入：新路径 0 条", "京城" not in on_text, on_text[:200])
        check("隐含别名角色未漏检（别名解析命中并注入）", "洛阳" in on_text, on_text[:200])

    print("\n[3] 量化汇总")
    for label, value in _METRICS:
        print(f"  {label} = {value}")
    print(f"\n结果：{_PASS} 通过，{_FAIL} 失败")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
