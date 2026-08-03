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

from novelforge.workflows import interactive_writing
from novelforge.workflows.context_assembly import render_context_for_prompt
from novelforge.services.memory import (
    begin_creative_turn,
    confirm_pending_knowledge_items,
    copy_story,
    create_project,
    create_story,
    delete_story,
    list_creative_sessions,
    load_chapter,
    load_creative_session_bundle,
    load_knowledge_base,
    load_pending_knowledge_items,
    load_context_directives,
    fail_creative_turn,
    save_context_directive,
    update_creative_session,
)
from novelforge.domain.setting_knowledge import upsert_setting_item
from storage import open_project_db
from novelforge.services.memory import project_path
from tools.verify_utils import isolated_workspace


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def _setting(story_id: str) -> dict:
    return {
        "id": "interactive_world_rule",
        "name": "雨夜世界规则",
        "summary": "雨夜时城市结界会削弱。",
        "setting_role": "core",
        "setting_scope": "story",
        "setting_field": "world",
        "story_id": story_id,
        "injection_policy": "always",
        "status": "confirmed",
        "worldline_id": "main",
        "worldline_label": "主线",
    }


def _extraction_result() -> dict:
    return {
        "success": True,
        "status": "completed",
        "data": {
            "knowledge_extraction": {
                "source_title": "自由创作",
                "source_summary": "关系发生变化",
                "items": [{
                    "category": "relationships",
                    "name": "林雨与顾川",
                    "summary": "林雨认识顾川，却在雨夜假装初次见面。",
                    "details": {"关系阶段": "隐瞒身份"},
                    "evidence": [{
                        "source_title": "自由创作",
                        "quote": "她明明认识他，却移开视线。",
                        "note": "已接受正文明确表现。",
                    }],
                    "confidence": 0.95,
                    "importance": 0.9,
                    "evidence_strength": 0.9,
                    "canon_status": "user_override",
                    "tags": ["关系变化"],
                }],
                "notes": [],
            },
        },
    }


def verify() -> None:
    project_name = "interactive_writing_verify"
    create_project(project_name)
    story_id = create_story(project_name, "互动故事")["story_id"]
    upsert_setting_item(project_name, "world_rules", _setting(story_id))

    session = interactive_writing.create_writing_session(
        project_name,
        story_id,
        session_goal="写雨夜相遇并逐步揭示两人旧识关系",
        writing_guidance={"tone": "克制"},
        auto_extract_mode="manual",
    )
    session_id = str(session["session_id"])
    check(session["story_id"] == story_id, "会话属于当前故事")
    check(len(list_creative_sessions(project_name, story_id)) == 1, "会话持久化并可列出")

    with patch.object(interactive_writing, "call_llm", return_value="雨幕里，林雨第一次看见顾川似的停下脚步。"):
        first = interactive_writing.generate_writing_fragment(
            project_name,
            story_id,
            session_id,
            "写两人在雨夜相遇",
            action_type="generate",
        )
    first_id = str(first["fragment"]["fragment_id"])
    check(first["fragment"]["status"] == "proposed", "首个生成片段保持待接受")
    check(first["turn"]["status"] == "completed", "生成结果返回已完成的轮次状态")
    check(
        "雨夜时城市结界会削弱" in render_context_for_prompt(first["context_assembly"]),
        "自由创作复用始终注入的世界观",
    )
    check(bool(first["fragment"].get("context_snapshot_id")), "生成片段保存上下文快照")

    accepted = interactive_writing.accept_writing_fragment(
        project_name,
        story_id,
        session_id,
        first_id,
    )
    check(accepted["fragment"]["status"] == "accepted", "片段可以显式接受")

    with patch.object(interactive_writing, "call_llm", return_value="她明明认识他，却移开视线，只报出一个假名。"):
        second = interactive_writing.generate_writing_fragment(
            project_name,
            story_id,
            session_id,
            "继续写，让少女隐瞒认识主角的事实",
            action_type="continue",
        )
    second_id = str(second["fragment"]["fragment_id"])
    bundle = load_creative_session_bundle(project_name, session_id, story_id=story_id)
    chain = interactive_writing.active_fragment_chain(bundle or {})
    check([item["fragment_id"] for item in chain] == [first_id, second_id], "续写形成父子片段链")
    check(chain[0]["status"] == "accepted", "续写保持父片段已接受状态")

    with patch.object(interactive_writing, "call_llm", return_value="她抬眼看他，熟悉的称呼到了唇边又被咽下。"):
        rewritten = interactive_writing.generate_writing_fragment(
            project_name,
            story_id,
            session_id,
            "重写得更含蓄，不要直接提到假名",
            action_type="rewrite",
        )
    rewritten_id = str(rewritten["fragment"]["fragment_id"])
    bundle = load_creative_session_bundle(project_name, session_id, story_id=story_id)
    fragments = {
        item["fragment_id"]: item for item in (bundle or {}).get("fragments", [])
    }
    chain = interactive_writing.active_fragment_chain(bundle or {})
    check(fragments[second_id]["status"] == "superseded", "重写后旧候选标记为已替代")
    check([item["fragment_id"] for item in chain] == [first_id, rewritten_id], "当前分支排除被重写片段")

    try:
        interactive_writing.extract_fragment_knowledge(
            project_name,
            story_id,
            session_id,
            rewritten_id,
        )
    except ValueError as exc:
        check("已接受" in str(exc), "未接受片段禁止提炼知识")
    else:
        raise AssertionError("未接受片段被允许提炼知识")

    interactive_writing.accept_writing_fragment(
        project_name,
        story_id,
        session_id,
        rewritten_id,
    )
    try:
        interactive_writing.preview_writing_context(
            project_name,
            story_id,
            session_id,
            "从更早片段另开世界线",
            action_type="branch",
            branch_from_fragment_id=first_id,
        )
    except ValueError as exc:
        check("创作前沿" in str(exc), "会话内禁止回退已确认事实建立污染知识的旧节点分支")
    else:
        raise AssertionError("会话允许从旧已接受节点创建分支")
    with patch("novelforge.workflows.skills.extract_reference_knowledge", return_value=_extraction_result()):
        extraction = interactive_writing.extract_fragment_knowledge(
            project_name,
            story_id,
            session_id,
            rewritten_id,
        )
        repeated = interactive_writing.extract_fragment_knowledge(
            project_name,
            story_id,
            session_id,
            rewritten_id,
        )
    check(len(extraction["candidate_ids"]) == 1, "已接受片段提炼完整知识候选")
    check(repeated["queued_count"] == 0, "重复提炼使用稳定 ID 且不会重复入队")
    candidates = interactive_writing.pending_knowledge_for_fragment(
        project_name,
        rewritten_id,
    )
    check(len(candidates) == 1, "候选知识可按来源片段回查")
    candidate = candidates[0]
    check(candidate.get("setting_scope") == "story", "片段知识默认故事级隔离")
    check(candidate.get("story_id") == story_id, "片段知识记录故事 ID")
    check(candidate.get("injection_policy") == "retrieval", "片段知识默认按需检索")
    check(candidate.get("source_origin") == "interactive_fragment", "片段知识记录来源类型")

    pending_id = str(candidate["pending_id"])
    check(confirm_pending_knowledge_items(project_name, [pending_id]) == 1, "片段知识可以确认入库")
    confirmed = [
        item
        for item in load_knowledge_base(project_name).get("relationships", [])
        if item.get("name") == "林雨与顾川"
    ]
    check(len(confirmed) == 1, "确认后的片段知识进入正式知识库")
    check(not any(item.get("pending_id") == pending_id for item in load_pending_knowledge_items(project_name)), "确认后候选从队列移除")

    preview = interactive_writing.preview_writing_context(
        project_name,
        story_id,
        session_id,
        "继续描写林雨与顾川的试探",
        action_type="continue",
    )
    preview_text = render_context_for_prompt(preview)
    check("林雨认识顾川" in preview_text, "确认知识可被后续自由创作检索复用")
    check("她抬眼看他" in preview_text, "后续生成直接使用当前已接受片段")

    compiled = interactive_writing.save_writing_session_as_chapter(
        project_name,
        story_id,
        session_id,
        3,
    )
    chapter = load_chapter(project_name, 3, story_id=story_id)
    check(compiled["fragment_count"] == 2, "正式章节只统计当前分支已接受片段")
    check("雨幕里" in chapter and "她抬眼看他" in chapter, "正式章节合并当前分支")
    check("假名" not in chapter, "正式章节排除被重写版本")
    finalized_bundle = load_creative_session_bundle(
        project_name,
        session_id,
        story_id=story_id,
    )
    check(
        not interactive_writing.compile_session_text(finalized_bundle or {}),
        "已并入章节的片段不会再次进入汇编内容",
    )

    try:
        interactive_writing.save_writing_session_as_chapter(
            project_name,
            story_id,
            session_id,
            4,
        )
    except ValueError as exc:
        check("已接受片段" in str(exc), "没有新接受片段时禁止重复汇编")
    else:
        raise AssertionError("已并入章节的片段被重复汇编")

    copied_story = copy_story(project_name, story_id, "互动故事副本")
    copied_sessions = list_creative_sessions(
        project_name,
        copied_story["story_id"],
        include_archived=True,
    )
    check(len(copied_sessions) == 1, "复制故事会复制自由创作会话")
    copied_bundle = load_creative_session_bundle(
        project_name,
        copied_sessions[0]["session_id"],
        story_id=copied_story["story_id"],
    )
    check(len((copied_bundle or {}).get("fragments", [])) == 3, "复制故事保留会话版本历史")
    delete_story(project_name, copied_story["story_id"])
    with open_project_db(project_path(project_name)) as conn:
        copied_count = conn.execute(
            "SELECT COUNT(*) FROM creative_sessions WHERE story_id = ?",
            (copied_story["story_id"],),
        ).fetchone()[0]
    check(copied_count == 0, "删除故事会清理自由创作会话")

    overwrite_session = interactive_writing.create_writing_session(
        project_name,
        story_id,
        session_goal="测试章节覆盖保护",
    )
    with patch.object(interactive_writing, "call_llm", return_value="这是一段不能覆盖已有章节的正文。"):
        overwrite_fragment = interactive_writing.generate_writing_fragment(
            project_name,
            story_id,
            overwrite_session["session_id"],
            "生成覆盖测试片段",
            action_type="generate",
        )
    interactive_writing.accept_writing_fragment(
        project_name,
        story_id,
        overwrite_session["session_id"],
        overwrite_fragment["fragment"]["fragment_id"],
    )
    update_creative_session(
        project_name,
        overwrite_session["session_id"],
        {"status": "archived"},
        story_id=story_id,
    )
    try:
        interactive_writing.save_writing_session_as_chapter(
            project_name,
            story_id,
            overwrite_session["session_id"],
            5,
        )
    except ValueError as exc:
        check("已归档" in str(exc), "归档会话禁止继续写入章节")
    else:
        raise AssertionError("归档会话被允许写入章节")
    check(not load_chapter(project_name, 5, story_id=story_id), "归档校验发生在章节文件写入之前")
    update_creative_session(
        project_name,
        overwrite_session["session_id"],
        {"status": "active"},
        story_id=story_id,
    )
    try:
        interactive_writing.save_writing_session_as_chapter(
            project_name,
            story_id,
            overwrite_session["session_id"],
            3,
        )
    except FileExistsError:
        check(True, "章节合并禁止静默覆盖")
    else:
        raise AssertionError("已有章节被自由创作静默覆盖")

    failed_session = interactive_writing.create_writing_session(
        project_name,
        story_id,
        session_goal="测试失败记录",
    )
    with patch.object(interactive_writing, "call_llm", side_effect=RuntimeError("injected generation failure")):
        try:
            interactive_writing.generate_writing_fragment(
                project_name,
                story_id,
                failed_session["session_id"],
                "触发失败",
                action_type="generate",
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("生成失败没有抛出")
    failed_bundle = load_creative_session_bundle(
        project_name,
        failed_session["session_id"],
        story_id=story_id,
    )
    check((failed_bundle or {})["turns"][0]["status"] == "failed", "生成失败保留可审计轮次")
    check(not (failed_bundle or {})["fragments"], "生成失败不会创建空片段")

    directive = save_context_directive(
        project_name,
        {
            "name": "下一片段规则",
            "content": "下一片段必须保持主角视角。",
            "scope": "run",
            "story_id": story_id,
            "capabilities": ["write"],
            "placement": "chapter_direction",
            "remaining_uses": 1,
        },
        story_id=story_id,
    )
    directive_session = interactive_writing.create_writing_session(
        project_name,
        story_id,
        session_goal="测试导演注消费",
    )
    with patch.object(interactive_writing, "call_llm", return_value="他只看见雨水沿着窗沿落下。"):
        interactive_writing.generate_writing_fragment(
            project_name,
            story_id,
            directive_session["session_id"],
            "生成视角片段",
            action_type="generate",
        )
    stored_directive = next(
        item
        for item in load_context_directives(project_name, story_id)
        if item.get("directive_id") == directive.get("directive_id")
    )
    check(stored_directive.get("remaining_uses") == 0, "成功保存片段后消耗单次导演注")
    check(stored_directive.get("enabled") is False, "耗尽的单次导演注自动停用")

    guarded_session = interactive_writing.create_writing_session(
        project_name,
        story_id,
        session_goal="测试并发保护",
    )
    running_turn = begin_creative_turn(
        project_name,
        guarded_session["session_id"],
        "开始一个尚未完成的生成",
        action_type="generate",
        parent_fragment_id=None,
        story_id=story_id,
    )
    try:
        begin_creative_turn(
            project_name,
            guarded_session["session_id"],
            "并发触发第二个生成",
            action_type="generate",
            parent_fragment_id=None,
            story_id=story_id,
        )
    except ValueError as exc:
        check("正在运行" in str(exc), "同一会话禁止并发生成导致分支覆盖")
    else:
        raise AssertionError("同一会话允许了并发生成")
    try:
        update_creative_session(
            project_name,
            guarded_session["session_id"],
            {"status": "archived"},
            story_id=story_id,
        )
    except ValueError as exc:
        check("运行" in str(exc), "运行中的会话禁止归档，避免生成结果覆盖会话状态")
    else:
        raise AssertionError("运行中的会话被允许归档")
    running_copy = copy_story(
        project_name,
        story_id,
        "运行中会话复制",
        include_chapters=True,
    )
    copied_guard_session = next(
        item
        for item in list_creative_sessions(project_name, running_copy["story_id"])
        if item.get("session_goal") == "测试并发保护"
    )
    copied_guard_bundle = load_creative_session_bundle(
        project_name,
        copied_guard_session["session_id"],
        story_id=running_copy["story_id"],
    )
    check(
        (copied_guard_bundle or {})["turns"][-1]["status"] == "failed",
        "复制故事会终止源故事中尚在运行的轮次副本",
    )
    check(delete_story(project_name, running_copy["story_id"]), "运行中会话复制测试故事可清理")
    with open_project_db(project_path(project_name).resolve()) as conn:
        conn.execute(
            "UPDATE creative_turns SET updated_at = ? WHERE turn_id = ?",
            ("2000-01-01T00:00:00+00:00", running_turn["turn_id"]),
        )
        conn.commit()
    recovered_turn = begin_creative_turn(
        project_name,
        guarded_session["session_id"],
        "中断后重新开始生成",
        action_type="generate",
        parent_fragment_id=None,
        story_id=story_id,
    )
    recovered_bundle = load_creative_session_bundle(
        project_name,
        guarded_session["session_id"],
        story_id=story_id,
    )
    recovered_turns = (recovered_bundle or {})["turns"]
    check(recovered_turns[-2]["status"] == "failed", "超过一小时的中断轮次会自动释放")
    failed_turn = fail_creative_turn(
        project_name,
        recovered_turn["turn_id"],
        "测试结束",
        story_id=story_id,
    )
    check(failed_turn["status"] == "failed", "并发保护轮次可正常结束并释放会话")

    branch_guard_session = interactive_writing.create_writing_session(
        project_name,
        story_id,
        session_goal="测试当前候选保护",
    )
    with patch.object(interactive_writing, "call_llm", return_value="分支共同起点。"):
        branch_root = interactive_writing.generate_writing_fragment(
            project_name,
            story_id,
            branch_guard_session["session_id"],
            "生成起点",
            action_type="generate",
        )
    branch_root_id = branch_root["fragment"]["fragment_id"]
    interactive_writing.accept_writing_fragment(
        project_name,
        story_id,
        branch_guard_session["session_id"],
        branch_root_id,
    )
    with patch.object(interactive_writing, "call_llm", return_value="第一个未接受的方向。"):
        inactive_candidate = interactive_writing.generate_writing_fragment(
            project_name,
            story_id,
            branch_guard_session["session_id"],
            "写第一个方向",
            action_type="branch",
            branch_from_fragment_id=branch_root_id,
        )
    with patch.object(interactive_writing, "call_llm", return_value="第二个当前方向。"):
        interactive_writing.generate_writing_fragment(
            project_name,
            story_id,
            branch_guard_session["session_id"],
            "改走另一个方向",
            action_type="branch",
            branch_from_fragment_id=branch_root_id,
        )
    try:
        interactive_writing.accept_writing_fragment(
            project_name,
            story_id,
            branch_guard_session["session_id"],
            inactive_candidate["fragment"]["fragment_id"],
        )
    except ValueError as exc:
        check("当前分支" in str(exc), "只能接受当前分支候选，旧分支不会反向覆盖")
    else:
        raise AssertionError("非当前候选被允许接受")
    interactive_writing.select_writing_fragment_variant(
        project_name,
        story_id,
        branch_guard_session["session_id"],
        inactive_candidate["fragment"]["fragment_id"],
    )
    selected_bundle = load_creative_session_bundle(
        project_name,
        branch_guard_session["session_id"],
        story_id=story_id,
    )
    check(
        (selected_bundle or {})["session"]["active_fragment_id"]
        == inactive_candidate["fragment"]["fragment_id"],
        "未接受的同级版本可以重新设为当前候选",
    )
    interactive_writing.accept_writing_fragment(
        project_name,
        story_id,
        branch_guard_session["session_id"],
        inactive_candidate["fragment"]["fragment_id"],
    )
    accepted_variant_bundle = load_creative_session_bundle(
        project_name,
        branch_guard_session["session_id"],
        story_id=story_id,
    )
    sibling_statuses = {
        fragment["fragment_id"]: fragment["status"]
        for fragment in (accepted_variant_bundle or {})["fragments"]
    }
    check(
        "superseded" in sibling_statuses.values(),
        "接受候选后同父节点的其它未接受版本自动标记为已替代",
    )


def main() -> int:
    with isolated_workspace("novelforge_interactive_writing_verify"):
        verify()
    print(json.dumps({
        "ok": True,
        "checks": len(CHECKS),
        "labels": CHECKS,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
