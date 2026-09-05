"""Verify refactor 2 · P1: entity planning + routing for generation context.

构造含多角色知识库（林越/苏晚/路人甲），mock 实体识别，断言：

1. `resolve_entity_ids_by_names`：规范名命中 + 别名组（林公子→林越）命中。
2. `plan_entity_context`：识别名解析为库内 entity_id；路由分组（character）正确；
   无关/库内不存在的名称进 unresolved（不静默丢弃）。
3. `build_entity_scoped_setting_context(["林越"])`：只注入林越事实，不含苏晚/路人甲。
4. `assemble_generation_context(enable_entity_planning=True)`：always 块只含本章识别实体；
   `enable=False` 回退全实体注入，且不报错（关闭实体识别时回退单查询）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from novelforge.core.schemas import ContextAssembly
from novelforge.domain.entity_planning import plan_entity_context
from novelforge.domain.setting_knowledge import build_entity_scoped_setting_context
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


def check(label: str, ok: bool, detail: str = ""):
    global _PASS, _FAIL
    if ok:
        _PASS += 1
        print(f"  PASS  {label}")
    else:
        _FAIL += 1
        print(f"  FAIL  {label}  {detail}")


def _char_item(item_id: str, name: str, summary: str, story_id: str, importance: float = 0.8) -> dict:
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
        "source_chapter_no": 1,
        "importance": importance,
    }


def main() -> int:
    print("=== Refactor2 P1 · 实体识别 + 分路由 ===\n")

    with isolated_workspace("novelforge_p1_planning_"):
        project_name = create_project("p1-planning")
        story_id = str(create_story(project_name, "主线").get("story_id") or "default")

        upsert_knowledge_category_item_record(project_name, "characters", _char_item("ly1", "林越", "林越身在洛阳", story_id, 0.95))
        upsert_knowledge_category_item_record(project_name, "characters", _char_item("sw1", "苏晚", "苏晚身在金陵", story_id, 0.85))
        upsert_knowledge_category_item_record(project_name, "characters", _char_item("pa1", "路人甲", "路人甲身在荒野", story_id, 0.2))
        save_entity_aliases(project_name, [{
            "canonical_name": "林越",
            "aliases": ["林公子", "阿越"],
            "entity_type": "character",
            "story_id": story_id,
        }])

        print("[1] resolve_entity_ids_by_names（别名解析，D2）")
        from novelforge.services.memory import resolve_entity_ids_by_names

        resolved = resolve_entity_ids_by_names(
            project_name, ["林越", "林公子", "不存在的人"], story_id=story_id
        )
        check("规范名命中", bool(resolved.get("林越", {}).get("entity_id")), str(resolved))
        alias_info = resolved.get("林公子", {})
        check("别名命中且归一规范名", alias_info.get("canonical_name") == "林越", str(alias_info))
        check("别名命中 entity_id 与规范名一致", alias_info.get("entity_id") == resolved.get("林越", {}).get("entity_id"),
              f"{alias_info.get('entity_id')} vs {resolved.get('林越', {}).get('entity_id')}")
        check("不存在名 unresolved", not resolved.get("不存在的人"), str(resolved))

        print("\n[2] plan_entity_context（mock LLM 识别）")
        response = {"entities": [
            {"name": "林越", "type": "character", "mention": "direct", "purpose": "主角"},
            {"name": "苏晚", "type": "character", "mention": "implicit", "purpose": "女配"},
            {"name": "不存在的人", "type": "character", "mention": "direct", "purpose": "漏识别验证"},
        ]}

        def responder(project_name_arg, story_id_arg, prompt):
            return response

        plan = plan_entity_context(
            project_name, story_id, capability="write",
            query_text="第10章：林越在洛阳与苏晚重逢",
            responder=responder,
        )
        check("识别出 2 个库内实体", len(plan.entity_ids) == 2, f"{plan.entity_ids}")
        check("unresolved 记录 1 个（不静默丢弃）", len(plan.unresolved_names) == 1,
              f"{[u['name'] for u in plan.unresolved_names]}")
        char_route = plan.route_names.get("character", [])
        check("character 路由含林越/苏晚", set(char_route) >= {"林越", "苏晚"}, str(char_route))

        print("\n[3] 实体聚焦 always 注入（build_entity_scoped_setting_context）")
        scoped = build_entity_scoped_setting_context(
            project_name, story_id, canonical_names=["林越"], chapter_no=10
        )
        text = str(scoped.get("text") or "")
        check("只注入林越事实", "洛阳" in text and "金陵" not in text and "荒野" not in text, text)
        check("返回去重 knowledge ids", len(scoped.get("ids") or []) == 1, str(scoped.get("ids")))

        print("\n[4] assemble_generation_context（enable on/off）")
        query = "第10章 大纲：林越在洛阳与苏晚重逢"
        # enable=False：关闭实体识别，回退全实体注入，不报错
        ctx_off = assemble_generation_context(project_name, story_id=story_id, capability="write", query=query, chapter_no=10)
        check("关闭实体识别可正常装配", isinstance(ctx_off, ContextAssembly), type(ctx_off).__name__)
        off_blocks = [b.content for b in ctx_off.blocks if b.block_id == "always_settings"]
        off_text = "\n".join(off_blocks)
        check("关闭时全实体注入（含苏晚/路人甲）", "金陵" in off_text and "荒野" in off_text, off_text[:200])
        # enable=True：mock 只识别林越
        plan_response_only_lin = {"entities": [{"name": "林越", "type": "character", "mention": "direct", "purpose": "主角"}]}

        def responder_only_lin(project_name_arg, story_id_arg, prompt):
            return plan_response_only_lin

        ctx_on = assemble_generation_context(
            project_name, story_id=story_id, capability="write", query=query, chapter_no=10,
            enable_entity_planning=True, _entity_plan_responder=responder_only_lin,
        )
        on_blocks = [b.content for b in ctx_on.blocks if b.block_id == "always_settings"]
        on_text = "\n".join(on_blocks)
        check("开启时 always 只含林越（无关实体的设定被剔除）", "洛阳" in on_text and "金陵" not in on_text and "荒野" not in on_text,
              on_text[:300])

    print(f"\n结果：{_PASS} 通过，{_FAIL} 失败")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
