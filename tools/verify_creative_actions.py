from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.domain.creative_actions import route_creative_action
from novelforge.services.memory import (
    confirm_pending_knowledge_items_with_records,
    create_project,
    create_story,
    list_creative_actions,
    list_creative_messages,
    load_creative_profile,
    load_creative_session_bundle,
    load_knowledge_category,
    queue_pending_knowledge_items,
)
from novelforge.workflows import interactive_writing
from novelforge.workflows.creative_actions import (
    execute_creative_action,
    plan_creative_action,
    undo_creative_action,
)
from tools.verify_utils import isolated_workspace


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def verify_router() -> None:
    check(route_creative_action("写一个雨夜开场")["action_type"] == "write", "普通自然语言保持正文写作意图")
    check(route_creative_action("/查资料 银铃渡口")["action_type"] == "query_knowledge", "明确查询命令确定性路由")
    check(route_creative_action("/提炼设定")["action_type"] == "extract_knowledge", "明确提炼命令确定性路由")
    check(route_creative_action("/导入资料")["action_type"] == "import_sources", "明确导入命令确定性路由")
    check(route_creative_action("/配置 文风=克制，节奏=快推")["action_type"] == "update_config", "会话配置命令生成结构化补丁")
    check(route_creative_action("/配置 文风=克制，参考强度=严格原作")["action_type"] == "clarify", "跨作用域配置要求先澄清")
    check(route_creative_action("/修改知识 characters:hero 摘要=新的摘要")["action_type"] == "update_knowledge", "知识更新命令生成目标与补丁")
    check(route_creative_action("/未知命令")["action_type"] == "clarify", "未知工具命令不会误当正文或直接写库")


def verify_protocol() -> None:
    with isolated_workspace("novelforge_creative_actions_"):
        project_name = "creative_actions_verify"
        create_project(project_name)
        story = create_story(project_name, "动作协议故事")
        story_id = str(story["story_id"])
        session = interactive_writing.create_writing_session(
            project_name, story_id, session_goal="测试统一动作协议",
        )
        session_id = str(session["session_id"])

        with patch.object(interactive_writing, "call_llm", return_value="雨落在旧桥上，旅人停住脚步。"), patch.object(
            interactive_writing,
            "require_operation_capabilities",
            return_value={"ready": True},
        ):
            generation = interactive_writing.generate_writing_fragment(
                project_name, story_id, session_id, "写一个雨夜开场", action_type="generate",
            )
        bundle = load_creative_session_bundle(project_name, session_id, story_id=story_id) or {}
        check(len(bundle.get("turns") or []) == 1, "正文仍只由 creative_turns 和 creative_fragments 承载")
        check(any(item.get("action_type") == "write" for item in list_creative_actions(project_name, story_id, session_id)), "正文生成同时留下独立动作账本")

        query_one = plan_creative_action(
            project_name, story_id, session_id, "/查资料 旧桥",
            idempotency_key="query-old-bridge",
        )
        query_two = plan_creative_action(
            project_name, story_id, session_id, "/查资料 旧桥",
            idempotency_key="query-old-bridge",
        )
        check(query_one["action_id"] == query_two["action_id"], "动作幂等键返回同一权威动作")
        query_done = execute_creative_action(project_name, query_one["action_id"])
        check(query_done["status"] == "completed" and "hits" in query_done["result"], "知识查询动作返回可审计证据结果")

        config = plan_creative_action(
            project_name, story_id, session_id, "/配置 文风=克制，节奏=快推",
            idempotency_key="config-session-one",
        )
        check(config["status"] == "awaiting_confirmation", "持久配置变更先进入确认状态")
        before_bundle = load_creative_session_bundle(project_name, session_id, story_id=story_id) or {}
        check(before_bundle["session"].get("writing_guidance", {}).get("tone") != "克制", "未确认动作不会提前修改配置")
        config_done = execute_creative_action(project_name, config["action_id"], confirmed=True)
        after_bundle = load_creative_session_bundle(project_name, session_id, story_id=story_id) or {}
        check(config_done["status"] == "completed" and after_bundle["session"]["writing_guidance"]["tone"] == "克制", "确认后原子保存会话配置差异")
        undo_creative_action(project_name, config["action_id"])
        undone_bundle = load_creative_session_bundle(project_name, session_id, story_id=story_id) or {}
        check(undone_bundle["session"].get("writing_guidance", {}).get("tone") != "克制", "配置动作可通过新动作撤销")

        story_config = plan_creative_action(
            project_name, story_id, session_id, "/配置 参考强度=严格原作",
            idempotency_key="config-story-one",
        )
        execute_creative_action(project_name, story_config["action_id"], confirmed=True)
        check(load_creative_profile(project_name, story_id)["reference_strength"] == "严格原作", "故事级配置补丁写入创作档案")

        queue_pending_knowledge_items(
            project_name,
            [{
                "pending_id": "pending_action_hero", "category": "characters", "name": "旅人",
                "summary": "旅人站在旧桥上。", "story_id": story_id, "setting_scope": "story",
                "canon_status": "user_override", "worldline_id": "main", "status": "pending",
            }],
            scope="project", authority="project", source_title="动作测试", source_origin="verify",
        )
        confirmed = confirm_pending_knowledge_items_with_records(project_name, ["pending_action_hero"])
        knowledge_id = str(confirmed["confirmed_records"][0]["knowledge_id"])
        knowledge_action = plan_creative_action(
            project_name, story_id, session_id,
            f"/修改知识 characters:{knowledge_id} 摘要=旅人已经离开旧桥。",
            idempotency_key="knowledge-update-one",
        )
        check(knowledge_action["status"] == "awaiting_confirmation", "知识覆盖动作先显示确认卡")
        execute_creative_action(project_name, knowledge_action["action_id"], confirmed=True)
        changed = next(item for item in load_knowledge_category(project_name, "characters") if item.get("id") == knowledge_id)
        check(changed["summary"] == "旅人已经离开旧桥。", "确认后知识更新进入正式修订链")
        undo_creative_action(project_name, knowledge_action["action_id"])
        restored = next(item for item in load_knowledge_category(project_name, "characters") if item.get("id") == knowledge_id)
        check(restored["summary"] == "旅人站在旧桥上。", "知识更新动作可撤销为新修订")

        clarify = plan_creative_action(
            project_name, story_id, session_id, "/不存在",
            idempotency_key="clarify-one",
        )
        execute_creative_action(project_name, clarify["action_id"])
        messages = list_creative_messages(project_name, story_id, session_id)
        check(any(item.get("message_kind") == "action_receipt" for item in messages), "普通回复和动作回执持久化在独立消息表")


def main() -> int:
    try:
        verify_router()
        verify_protocol()
    except Exception as exc:
        print(json.dumps({"ok": False, "checks": CHECKS, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "checks": CHECKS}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
