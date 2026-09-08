"""Verify conversational action execution and knowledge isolation by branch."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.verify_utils import isolated_workspace


def main() -> int:
    from fastapi.testclient import TestClient

    from novelforge.api.app import create_app
    from novelforge.services import memory
    from novelforge.workflows.interactive_writing import create_writing_session

    checks: list[str] = []
    failures: list[str] = []

    def check(value: bool, label: str) -> None:
        (checks if value else failures).append(label)

    previous = os.environ.get("NOVELFORGE_DISABLE_BACKGROUND_TASKS")
    os.environ["NOVELFORGE_DISABLE_BACKGROUND_TASKS"] = "1"
    try:
        with isolated_workspace("novelforge_creative_action_branch_"):
            client = TestClient(
                create_app(),
                headers={"x-novelforge-client": "vue"},
                raise_server_exceptions=False,
            )
            response = client.post("/api/v1/projects", json={"name": "action-branch-review"})
            assert response.status_code == 201, response.text
            project = response.json()["data"]["project"]
            project_name = project["name"]
            project_id = project["project_id"]
            response = client.post(
                f"/api/v1/projects/{project_id}/stories",
                json={"name": "Action Story", "creation_mode": "conversational"},
            )
            assert response.status_code == 201, response.text
            story_id = response.json()["data"]["story"]["story_id"]
            path = f"/api/v1/projects/{project_id}/stories/{story_id}"
            main_branch = memory.default_branch_id(story_id)
            memory.ensure_story_branch(project_name, story_id, main_branch)
            memory.upsert_knowledge_category_item_record(
                project_name,
                "characters",
                {
                    "id": "action-parent-k",
                    "name": "父线角色",
                    "summary": "父线原始设定",
                    "story_id": story_id,
                    "branch_id": main_branch,
                    "setting_scope": "story",
                    "status": "confirmed",
                },
            )
            for knowledge_id, name, summary, injection_policy in (
                ("action-core-k", "冻结核心", "核心原始设定", "always"),
                ("action-manual-k", "手动设定", "手动原始设定", "manual_only"),
                ("action-delete-k", "删除前设定", "删除前原始设定", "always"),
            ):
                memory.upsert_knowledge_category_item_record(
                    project_name,
                    "characters",
                    {
                        "id": knowledge_id,
                        "name": name,
                        "summary": summary,
                        "story_id": story_id,
                        "branch_id": main_branch,
                        "setting_scope": "story",
                        "status": "confirmed",
                        "injection_policy": injection_policy,
                    },
                )
            child_branch = memory.fork_story_branch(
                project_name,
                story_id,
                parent_branch_id=main_branch,
                name="Action Child",
                allow_current_state=True,
                create_session=False,
            )["branch"]["branch_id"]
            session = create_writing_session(
                project_name,
                story_id,
                session_goal="branch action",
                branch_id=child_branch,
            )
            session_id = session["session_id"]
            main_session = create_writing_session(
                project_name,
                story_id,
                session_goal="main action owner",
                branch_id=main_branch,
            )
            main_session_id = main_session["session_id"]

            # The child must search the frozen checkpoint after the parent is
            # edited.  This catches ID-only retrieval filters that still read
            # the parent's latest indexed text.
            memory.upsert_knowledge_category_item_record(
                project_name,
                "characters",
                {
                    "id": "action-parent-k",
                    "name": "父线角色",
                    "summary": "父线未来新设定",
                    "story_id": story_id,
                    "branch_id": main_branch,
                    "setting_scope": "story",
                    "status": "confirmed",
                },
            )
            for knowledge_id, name, summary in (
                ("action-core-k", "冻结核心", "核心未来设定"),
                ("action-manual-k", "手动设定", "手动未来设定"),
                ("action-delete-k", "删除前设定", "删除前未来设定"),
            ):
                memory.upsert_knowledge_category_item_record(
                    project_name,
                    "characters",
                    {
                        "id": knowledge_id,
                        "name": name,
                        "summary": summary,
                        "story_id": story_id,
                        "branch_id": main_branch,
                        "setting_scope": "story",
                        "status": "confirmed",
                    },
                )
            memory.update_confirmed_knowledge_item_record(
                project_name,
                "characters",
                "action-delete-k",
                {},
                delete_only=True,
            )
            query = client.post(
                f"{path}/sessions/{session_id}/actions/plan",
                json={"request": "/查资料 父线原始设定", "branch_id": child_branch},
            )
            assert query.status_code == 201, query.text
            query_id = query.json()["data"]["action"]["action_id"]
            query_done = client.post(
                f"{path}/sessions/{session_id}/actions/{query_id}/execute",
                json={"branch_id": child_branch},
            )
            check(query_done.status_code == 200, "旁支冻结查询动作执行成功")
            query_hits = query_done.json().get("data", {}).get("action", {}).get("result", {}).get("hits", [])
            query_text = "\n".join(
                str(hit.get("chunk", {}).get("content") or "")
                for hit in query_hits
                if isinstance(hit, dict)
            )
            check("父线原始设定" in query_text, "旁支查询读取分叉时冻结正文")
            check("父线未来新设定" not in query_text, "旁支查询不读取父线后续正文")

            def query_snapshot(term: str, old: str, future: str, label: str) -> None:
                planned_query = client.post(
                    f"{path}/sessions/{session_id}/actions/plan",
                    json={"request": f"/查资料 {term}", "branch_id": child_branch},
                )
                assert planned_query.status_code == 201, planned_query.text
                query_action_id = planned_query.json()["data"]["action"]["action_id"]
                done_query = client.post(
                    f"{path}/sessions/{session_id}/actions/{query_action_id}/execute",
                    json={"branch_id": child_branch},
                )
                hits = done_query.json().get("data", {}).get("action", {}).get("result", {}).get("hits", [])
                text = "\n".join(
                    str(hit.get("chunk", {}).get("content") or "")
                    for hit in hits if isinstance(hit, dict)
                )
                check(done_query.status_code == 200 and old in text, f"旁支查询冻结 {label} payload")
                check(future not in text, f"旁支查询不读取 {label} 父线未来内容")

            query_snapshot("冻结核心", "核心原始设定", "核心未来设定", "always 核心")
            query_snapshot("手动设定", "手动原始设定", "手动未来设定", "manual_only")
            query_snapshot("删除前设定", "删除前原始设定", "删除前未来设定", "父线删除")

            owner_child = client.post(
                f"{path}/sessions/{session_id}/actions/plan",
                json={
                    "request": "/未知命令",
                    "idempotency_key": "cross-session-owner-key",
                    "branch_id": child_branch,
                },
            )
            assert owner_child.status_code == 201, owner_child.text
            owner_child_action = owner_child.json()["data"]["action"]
            owner_main = client.post(
                f"{path}/sessions/{main_session_id}/actions/plan",
                json={
                    "request": "/未知命令",
                    "idempotency_key": "cross-session-owner-key",
                    "branch_id": main_branch,
                },
            )
            check(400 <= owner_main.status_code < 500, "跨会话复用幂等键被拒绝")
            try:
                memory.save_creative_action(
                    project_name,
                    {
                        "action_id": owner_child_action["action_id"],
                        "story_id": story_id,
                        "session_id": main_session_id,
                        "action_type": "clarify",
                        "status": "planned",
                        "idempotency_key": "cross-session-action-id",
                    },
                )
            except ValueError:
                check(True, "跨会话复用动作 ID 被拒绝")
            else:
                check(False, "跨会话复用动作 ID 被拒绝")
            try:
                memory.save_creative_message(
                    project_name,
                    {
                        "message_id": owner_child_action["request_message_id"],
                        "story_id": story_id,
                        "session_id": main_session_id,
                        "role": "user",
                        "content": "跨会话复用消息 ID",
                    },
                )
            except ValueError:
                check(True, "跨会话复用消息 ID 被拒绝")
            else:
                check(False, "跨会话复用消息 ID 被拒绝")
            try:
                memory.save_creative_config_revision(
                    project_name,
                    {
                        "action_id": owner_child_action["action_id"],
                        "story_id": story_id,
                        "session_id": main_session_id,
                        "branch_id": main_branch,
                        "config_scope": "session",
                    },
                )
            except ValueError:
                check(True, "跨会话复用配置修订动作被拒绝")
            else:
                check(False, "跨会话复用配置修订动作被拒绝")

            planned = client.post(
                f"{path}/sessions/{session_id}/actions/plan",
                json={"request": "/未知命令", "branch_id": child_branch},
            )
            check(planned.status_code == 201, "旁支动作计划接口可用")
            action_id = planned.json().get("data", {}).get("action", {}).get("action_id")
            executed = client.post(
                f"{path}/sessions/{session_id}/actions/{action_id}/execute",
                json={"confirmed": False, "branch_id": child_branch},
            )
            check(executed.status_code == 200, "旁支动作执行不再触发 branch_id TypeError")
            check(
                executed.json().get("data", {}).get("action", {}).get("branch_id") == child_branch,
                "动作账本保留会话所属旁支",
            )

            update = client.post(
                f"{path}/sessions/{session_id}/actions/plan",
                json={
                    "request": "/修改知识 characters:action-parent-k 摘要=旁支独立设定",
                    "branch_id": child_branch,
                },
            )
            assert update.status_code == 201, update.text
            update_id = update.json()["data"]["action"]["action_id"]
            update_response = client.post(
                f"{path}/sessions/{session_id}/actions/{update_id}/execute",
                json={"confirmed": True, "branch_id": child_branch},
            )
            check(update_response.status_code == 200, "旁支知识动作执行成功")
            parent = memory.load_knowledge_center_record(
                project_name, "knowledge", "action-parent-k",
                story_id=story_id, branch_id=main_branch,
            )
            child = memory.load_knowledge_center_record(
                project_name, "knowledge", "action-parent-k",
                story_id=story_id, branch_id=child_branch,
            )
            check(parent.get("payload", {}).get("summary") == "父线未来新设定", "旁支动作不修改父线知识")
            check(child.get("payload", {}).get("summary") == "旁支独立设定", "旁支动作生成独立知识内容")
            check(child.get("knowledge_id") != "action-parent-k", "旁支动作生成独立知识 ID")

            config = client.post(
                f"{path}/sessions/{session_id}/actions/plan",
                json={"request": "/配置 参考强度=旁支严格", "branch_id": child_branch},
            )
            assert config.status_code == 201, config.text
            config_id = config.json()["data"]["action"]["action_id"]
            config_done = client.post(
                f"{path}/sessions/{session_id}/actions/{config_id}/execute",
                json={"confirmed": True, "branch_id": child_branch},
            )
            check(config_done.status_code == 200, "旁支故事配置动作执行成功")
            parent_profile = memory.load_creative_profile(project_name, story_id)
            child_profile = memory.load_effective_story_branch_configuration(
                project_name, story_id, child_branch,
            ).get("profile", {})
            check(parent_profile.get("reference_strength") != "旁支严格", "旁支配置不污染主线 profile")
            check(child_profile.get("reference_strength") == "旁支严格", "旁支配置写入当前线 overlay")
            undone = client.post(
                f"{path}/sessions/{session_id}/actions/{config_id}/undo",
                params={"branch_id": child_branch},
            )
            check(undone.status_code == 200, "旁支故事配置动作可撤销")
            restored_child_profile = memory.load_effective_story_branch_configuration(
                project_name, story_id, child_branch,
            ).get("profile", {})
            check(restored_child_profile.get("reference_strength") != "旁支严格", "撤销只回滚当前线配置")

            wrong_branch = client.post(
                f"{path}/sessions/{session_id}/actions/{update_id}/execute",
                json={"confirmed": True, "branch_id": main_branch},
            )
            check(400 <= wrong_branch.status_code < 500, "执行接口拒绝跨线动作")

            pending_cancel = client.post(
                f"{path}/sessions/{session_id}/actions/plan",
                json={"request": "/调整配置 文风=克制", "branch_id": child_branch},
            )
            assert pending_cancel.status_code == 201, pending_cancel.text
            cancel_id = pending_cancel.json()["data"]["action"]["action_id"]
            memory.update_story_branch(project_name, story_id, child_branch, {"status": "archived"})
            archived_cancel = client.post(
                f"{path}/sessions/{session_id}/actions/{cancel_id}/cancel",
                params={"branch_id": child_branch},
            )
            check(400 <= archived_cancel.status_code < 500, "归档旁支拒绝取消动作写入")
            client.close()
    finally:
        if previous is None:
            os.environ.pop("NOVELFORGE_DISABLE_BACKGROUND_TASKS", None)
        else:
            os.environ["NOVELFORGE_DISABLE_BACKGROUND_TASKS"] = previous

    print(json.dumps({"ok": not failures, "checks": checks, "failures": failures}, ensure_ascii=False, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
