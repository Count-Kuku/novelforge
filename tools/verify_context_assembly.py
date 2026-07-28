from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = "0"

import skills
from context_assembly import (
    _apply_context_budget,
    assemble_generation_context,
    build_chapter_context_query,
    ensure_context_budget,
    render_context_for_prompt,
)
from memory import (
    GENERATION_CONTEXT_SNAPSHOT_ASSET_TYPE,
    consume_context_directives,
    copy_story,
    create_project,
    create_story,
    list_asset_payload_records,
    load_context_directives,
    load_effective_context_directives,
    save_context_directive,
    save_character_entities,
    save_project_prompt_options,
    upsert_knowledge_category_item_record,
)
from retrieval import debug_retrieve_context, resolve_retrieval_params
from schemas import ContextBlock
from setting_knowledge import build_generation_setting_context, upsert_setting_item
from tools.verify_utils import isolated_workspace


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def _setting_item(item_id: str, summary: str, policy: str, story_id: str) -> dict:
    return {
        "id": item_id,
        "name": summary,
        "summary": summary,
        "setting_role": "core",
        "setting_scope": "story",
        "setting_field": "world",
        "story_id": story_id,
        "injection_policy": policy,
        "status": "confirmed",
        "worldline_id": "main",
        "worldline_label": "主线",
    }


def verify_injection_policy(project_name: str, story_id: str) -> None:
    upsert_setting_item(
        project_name,
        "world_rules",
        _setting_item("setting_always", "始终注入的天空城", "always", story_id),
    )
    upsert_setting_item(
        project_name,
        "world_rules",
        _setting_item("setting_retrieval", "检索命中的地下河", "retrieval", story_id),
    )
    upsert_setting_item(
        project_name,
        "world_rules",
        _setting_item("setting_manual", "仅手动选择的密室", "manual_only", story_id),
    )
    supplemental = _setting_item("setting_supplemental", "必须保留的补充约束", "always", story_id)
    supplemental["setting_role"] = "supplemental"
    supplemental["setting_field"] = ""
    upsert_setting_item(project_name, "constraints", supplemental)
    upsert_knowledge_category_item_record(
        project_name,
        "characters",
        {
            "id": "ordinary_knowledge",
            "name": "普通角色知识",
            "summary": "这是一条普通检索知识。",
            "status": "confirmed",
        },
    )

    memory = build_generation_setting_context(project_name, story_id)
    setting_context = str(memory.get("_setting_context") or "")
    check("始终注入的天空城" in setting_context, "always 设定直接注入")
    check("检索命中的地下河" not in setting_context, "retrieval 设定不直接注入")
    check("仅手动选择的密室" not in setting_context, "manual_only 设定不直接注入")
    check("必须保留的补充约束" in setting_context, "非核心 always 条目保持直接注入")
    check("普通角色知识" not in setting_context, "未声明策略的普通知识默认走检索")
    check(memory.get("world") == ["始终注入的天空城"], "结构化设定成为生成时权威层")

    automatic = debug_retrieve_context(
        project_name,
        "仅手动选择的密室",
        allowed_source_types=["knowledge_world_rules"],
        retrieval_mode="lexical",
        story_id=story_id,
    )
    automatic_ids = {
        str(item.get("chunk", {}).get("metadata", {}).get("knowledge_id") or "")
        for item in automatic.get("reranked_hits", [])
    }
    check("setting_manual" not in automatic_ids, "manual_only 不会自动检索注入")
    check(int(automatic.get("manual_only_excluded_count") or 0) >= 1, "调试数据记录 manual_only 排除数量")

    explicit = debug_retrieve_context(
        project_name,
        "仅手动选择的密室",
        allowed_source_types=["knowledge_world_rules"],
        retrieval_mode="lexical",
        story_id=story_id,
        explicit_knowledge_ids=["setting_manual"],
    )
    explicit_ids = {
        str(item.get("chunk", {}).get("metadata", {}).get("knowledge_id") or "")
        for item in explicit.get("reranked_hits", [])
    }
    check("setting_manual" in explicit_ids, "明确手选可启用 manual_only 资料")
    empty_intersection = debug_retrieve_context(
        project_name,
        "天空城",
        allowed_source_types=["knowledge_world_rules"],
        retrieval_profile="drafting",
        source_type_strategy="intersect",
        retrieval_mode="lexical",
        story_id=story_id,
    )
    check(empty_intersection["source_type_filter"] == [], "无交集来源保持空过滤集合")
    check(empty_intersection["candidate_chunk_count"] == 0, "空来源交集不会退化为检索全部资料")


def verify_source_type_strategy(project_name: str, story_id: str) -> None:
    union_params = resolve_retrieval_params(
        allowed_source_types=["chapter_summary"],
        retrieval_profile="drafting",
        source_type_strategy="union",
    )
    check("entity_character_card" in union_params["allowed_source_types"], "union 保留 Profile 人物实体卡")
    check("chapter_summary" in union_params["allowed_source_types"], "union 保留显式来源")

    intersect_params = resolve_retrieval_params(
        allowed_source_types=["chapter_summary", "entity_character_card"],
        retrieval_profile="drafting",
        source_type_strategy="intersect",
    )
    check(
        intersect_params["allowed_source_types"] == ["chapter_summary", "entity_character_card"],
        "intersect 按 Profile 顺序收窄来源",
    )
    replace_params = resolve_retrieval_params(
        allowed_source_types=["chapter_summary"],
        retrieval_profile="drafting",
        source_type_strategy="replace",
    )
    check(replace_params["allowed_source_types"] == ["chapter_summary"], "replace 明确覆盖 Profile")
    save_character_entities(
        project_name,
        [{
            "id": "character_profile_probe",
            "name": "codexentityalpha",
            "summary": "用于验证正文 Profile 人物实体召回。",
            "story_id": story_id,
        }],
    )
    entity_result = debug_retrieve_context(
        project_name,
        "codexentityalpha",
        allowed_source_types=["chapter_summary"],
        retrieval_profile="drafting",
        source_type_strategy="union",
        retrieval_mode="lexical",
        story_id=story_id,
    )
    check(
        any(
            item.get("chunk", {}).get("source_type") == "entity_character_card"
            for item in entity_result.get("reranked_hits", [])
        ),
        "drafting Profile 与显式来源合并后能实际召回人物实体卡",
    )


def verify_budget_identity() -> None:
    duplicate_blocks = [
        ContextBlock(
            block_id="duplicate",
            category="test",
            content="A",
            source_type="test",
            estimated_tokens=8,
            priority=50,
        ),
        ContextBlock(
            block_id="duplicate",
            category="test",
            content="B",
            source_type="test",
            estimated_tokens=8,
            priority=50,
        ),
    ]
    included, omitted, _, exceeded = _apply_context_budget(duplicate_blocks, 8)
    check(len(included) == 1 and len(omitted) == 1, "重复块 ID 不会绕过上下文预算")
    check(exceeded is False, "可选块省略不会误报硬约束超预算")


def verify_directives(project_name: str, story_id: str, other_story_id: str) -> None:
    project_directive = save_context_directive(
        project_name,
        {
            "name": "项目文风",
            "content": "避免网络流行语。",
            "scope": "project",
            "capabilities": ["write"],
            "placement": "style",
        },
    )
    story_directive = save_context_directive(
        project_name,
        {
            "name": "故事方向",
            "content": "保持第一人称。",
            "scope": "story",
            "capabilities": ["write"],
            "placement": "chapter_direction",
        },
        story_id=story_id,
    )
    save_context_directive(
        project_name,
        {
            "name": "其他故事",
            "content": "这条不能出现在当前故事。",
            "scope": "story",
            "capabilities": ["write"],
            "placement": "chapter_direction",
        },
        story_id=other_story_id,
    )
    chapter_directive = save_context_directive(
        project_name,
        {
            "name": "第二章",
            "content": "第二章不要揭示真凶。",
            "scope": "chapter",
            "chapter_start": 2,
            "chapter_end": 2,
            "capabilities": ["write"],
            "placement": "hard_constraints",
        },
        story_id=story_id,
    )
    run_directive = save_context_directive(
        project_name,
        {
            "name": "下一次生成",
            "content": "下一次生成增加动作描写。",
            "scope": "run",
            "capabilities": ["write"],
            "placement": "chapter_direction",
        },
        story_id=story_id,
    )

    effective = load_effective_context_directives(
        project_name,
        story_id,
        capability="write",
        chapter_no=2,
    )
    effective_ids = {str(item.get("directive_id") or "") for item in effective}
    check(project_directive["directive_id"] in effective_ids, "项目导演注跨故事生效")
    check(story_directive["directive_id"] in effective_ids, "故事导演注在本故事生效")
    check(chapter_directive["directive_id"] in effective_ids, "章节导演注在范围内生效")
    check(run_directive["remaining_uses"] == 1, "run 导演注默认一次")
    check("这条不能出现在当前故事。" not in {item.get("content") for item in effective}, "故事导演注隔离")

    chapter_one = load_effective_context_directives(
        project_name,
        story_id,
        capability="write",
        chapter_no=1,
    )
    check(
        chapter_directive["directive_id"] not in {str(item.get("directive_id") or "") for item in chapter_one},
        "章节导演注在范围外不生效",
    )
    consume_context_directives(project_name, story_id, [run_directive["directive_id"]])
    consumed = {
        str(item.get("directive_id") or ""): item
        for item in load_context_directives(project_name, story_id)
    }[run_directive["directive_id"]]
    check(consumed["remaining_uses"] == 0 and consumed["enabled"] is False, "一次性导演注消费后停用")


def verify_assembly_and_write(project_name: str, story_id: str) -> None:
    save_project_prompt_options(
        project_name,
        [{
            "id": "default_write_style",
            "name": "默认正文风格",
            "content": "默认启用的正文风格选项。",
            "capability": "write",
            "category": "style",
            "slot": "style",
            "enabled": True,
            "priority": 50,
        }],
    )
    run_directive = save_context_directive(
        project_name,
        {
            "name": "保存后消费",
            "content": "本次结尾使用短句。",
            "scope": "run",
            "capabilities": ["write"],
            "placement": "chapter_direction",
        },
        story_id=story_id,
    )
    kwargs = {
        "story_id": story_id,
        "capability": "write",
        "query": "第一章 天空城相遇",
        "chapter_no": 1,
        "generation_guidance": {"tone": "克制"},
        "retrieval_profile": "drafting",
        "retrieval_mode": "lexical",
        "context_budget": 80,
    }
    first = assemble_generation_context(project_name, **kwargs)
    second = assemble_generation_context(project_name, **kwargs)
    check(first.fingerprint == second.fingerprint, "相同输入产生稳定上下文指纹")
    check(bool(first.blocks), "上下文装配产生有效块")
    check(bool(first.omitted_blocks), "预算不足时记录省略块")
    try:
        ensure_context_budget(first)
    except RuntimeError:
        CHECKS.append("硬约束超预算会阻止正式生成")
    else:
        raise AssertionError("硬约束超预算会阻止正式生成")
    full = assemble_generation_context(project_name, **{**kwargs, "context_budget": 12_000})
    check("本次结尾使用短句" in render_context_for_prompt(full), "导演注进入实际渲染上下文")
    check("默认启用的正文风格选项" in render_context_for_prompt(full), "未显式选择时保留默认启用的提示词选项")
    no_options = assemble_generation_context(
        project_name,
        **{**kwargs, "prompt_option_ids": [], "context_budget": 12_000},
    )
    check("默认启用的正文风格选项" not in render_context_for_prompt(no_options), "显式空选项列表会关闭提示词选项")

    expected_runtime_assembly = assemble_generation_context(
        project_name,
        story_id=story_id,
        capability="write",
        query=build_chapter_context_query(
            1,
            "主角抵达天空城。",
            {"tone": "克制", "manual_knowledge_ids": ["setting_manual"]},
        ),
        chapter_no=1,
        generation_guidance={"tone": "克制", "manual_knowledge_ids": ["setting_manual"]},
        retrieval_profile="drafting",
        allowed_scopes=["project", "canon", "reference"],
    )
    with patch.object(skills, "call_llm", return_value="这是生成的章节。"):
        preview_result = skills.write_chapter(
            project_name,
            1,
            "主角抵达天空城。",
            {"tone": "克制", "manual_knowledge_ids": ["setting_manual"]},
            story_id=story_id,
            save_output=False,
        )
    check(preview_result["success"] is True, "仅预览写作成功")
    check(
        preview_result["data"]["context_assembly"]["fingerprint"] == expected_runtime_assembly.fingerprint,
        "预览与实际写作入口复用同一上下文装配结果",
    )
    check(
        "默认启用的正文风格选项"
        in render_context_for_prompt(preview_result["data"]["context_assembly"]),
        "正文入口未显式传选项时仍使用默认启用项",
    )
    check(
        any(
            block.get("category") == "manual_knowledge"
            and block.get("source_ref") == "setting_manual"
            and block.get("hard_constraint") is True
            for block in preview_result["data"]["context_assembly"]["blocks"]
        ),
        "正文写作会把本次手选知识作为必需上下文直接注入",
    )
    after_preview = {
        str(item.get("directive_id") or ""): item
        for item in load_context_directives(project_name, story_id)
    }[run_directive["directive_id"]]
    check(after_preview["remaining_uses"] == 1, "未保存生成不消费一次性导演注")

    with patch.object(skills, "call_llm", return_value="这是正式保存的章节。"):
        saved_result = skills.write_chapter(
            project_name,
            1,
            "主角抵达天空城。",
            {"tone": "克制"},
            story_id=story_id,
            save_output=True,
        )
    check(saved_result["artifacts"]["saved"] is True, "正式章节成功保存")
    check(bool(saved_result["artifacts"].get("context_snapshot_id")), "正式生成保存上下文快照")
    after_save = {
        str(item.get("directive_id") or ""): item
        for item in load_context_directives(project_name, story_id)
    }[run_directive["directive_id"]]
    check(after_save["remaining_uses"] == 0, "正式保存后消费一次性导演注")
    snapshots = list_asset_payload_records(
        project_name,
        asset_type=GENERATION_CONTEXT_SNAPSHOT_ASSET_TYPE,
        story_id=story_id,
    )
    check(bool(snapshots), "上下文快照持久化到通用资产")
    check(
        saved_result["data"]["context_assembly"]["fingerprint"]
        == snapshots[0]["payload"]["fingerprint"],
        "步骤结果与持久化快照指纹一致",
    )
    copied_story_id = copy_story(project_name, story_id, "上下文副本")["story_id"]
    copied_directives = load_context_directives(project_name, copied_story_id)
    check(
        any(
            item.get("scope") != "project"
            and item.get("story_id") == copied_story_id
            and item.get("content") == "本次结尾使用短句。"
            for item in copied_directives
        ),
        "故事复制会重写故事级导演注归属",
    )
    copied_snapshots = list_asset_payload_records(
        project_name,
        asset_type=GENERATION_CONTEXT_SNAPSHOT_ASSET_TYPE,
        story_id=copied_story_id,
    )
    check(bool(copied_snapshots), "故事复制包含生成上下文快照")
    check(
        copied_snapshots[0]["payload"]["fingerprint"] == snapshots[0]["payload"]["fingerprint"],
        "复制后的历史上下文快照保持原始指纹",
    )


def verify_other_generation_entrypoints(project_name: str, story_id: str) -> None:
    with patch.object(skills, "call_llm", return_value="这是统一装配后的全书大纲。"):
        outline_result = skills.generate_outline(
            project_name,
            "主角探索天空城。",
            story_id=story_id,
        )
    check(bool(outline_result["data"].get("context_assembly")), "全书大纲使用统一上下文装配")

    with patch.object(skills, "call_llm", return_value="这是统一装配后的章节细纲。"):
        chapter_outline_result = skills.generate_chapter_outline(
            project_name,
            2,
            "主角发现地下河。",
            story_id=story_id,
        )
    check(
        bool(chapter_outline_result["data"].get("context_assembly")),
        "章节规划使用统一上下文装配",
    )

    review_payload = {
        "status": "pass",
        "summary": "结构稳定。",
        "strengths": ["方向明确"],
        "issues": [],
        "consistency_checks": {
            "characters": "通过",
            "world": "通过",
            "timeline": "通过",
            "foreshadowing": "通过",
        },
        "pacing": "稳定",
        "next_action": "继续下一章",
    }
    with patch.object(skills, "call_llm", return_value=json.dumps(review_payload, ensure_ascii=False)):
        review_result = skills.review_chapter(
            project_name,
            2,
            "主角沿地下河前行。",
            story_id=story_id,
        )
    check(review_result["success"] is True, "统一装配后的章节审阅成功")
    check(bool(review_result["data"].get("context_assembly")), "章节审阅使用统一上下文装配")


def main() -> int:
    with isolated_workspace("novelforge_context_assembly_"):
        project_name = create_project("context-verification")
        story_id = "default"
        other_story_id = create_story(project_name, "另一条故事")["story_id"]
        verify_injection_policy(project_name, story_id)
        verify_source_type_strategy(project_name, story_id)
        verify_budget_identity()
        verify_directives(project_name, story_id, other_story_id)
        verify_assembly_and_write(project_name, story_id)
        verify_other_generation_entrypoints(project_name, story_id)
    print(json.dumps({"ok": True, "checks": len(CHECKS)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
