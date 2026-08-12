from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.services.document_parsing import parse_document_bytes
from novelforge.services.memory import (
    copy_story,
    create_project,
    create_story,
    list_creative_sessions,
    list_long_reference_batches,
    load_creative_session_bundle,
    load_source_ingestion_task,
)
from novelforge.services.retrieval import ingest_external_source_file, retrieve_context
from novelforge.workflows import interactive_writing
from novelforge.workflows.creative_attachments import (
    attach_existing_creative_source,
    import_creative_documents,
    import_creative_pasted_text,
    list_existing_creative_sources,
    schedule_creative_attachment_knowledge,
)
from tools.verify_utils import isolated_workspace


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def verify() -> None:
    with isolated_workspace("novelforge_creative_attachment_"):
        project_name = "creative_attachment_verify"
        create_project(project_name)
        first_story = create_story(project_name, "附件故事一")
        second_story = create_story(project_name, "附件故事二")
        story_id = str(first_story["story_id"])
        other_story_id = str(second_story["story_id"])
        first_session = interactive_writing.create_writing_session(
            project_name,
            story_id,
            session_goal="使用附件创作",
        )
        second_session = interactive_writing.create_writing_session(
            project_name,
            story_id,
            session_goal="隔离的同故事会话",
        )
        first_session_id = str(first_session["session_id"])
        second_session_id = str(second_session["session_id"])

        document = parse_document_bytes(
            "角色设定.md",
            "# 角色\n\n岚秋的秘密口令是银铃渡口。".encode("utf-8"),
        )
        imported = import_creative_documents(
            project_name,
            story_id,
            first_session_id,
            [document],
            scope="session",
            schedule_knowledge=False,
        )
        check(len(imported) == 1, "文件附件可从自由创作导入")
        repeated = import_creative_documents(
            project_name,
            story_id,
            first_session_id,
            [document],
            scope="session",
            schedule_knowledge=False,
        )
        check(
            repeated[0]["attachment_id"] == imported[0]["attachment_id"],
            "相同附件在同一作用域重复提交保持幂等",
        )

        first_hits = retrieve_context(
            project_name,
            "银铃渡口",
            retrieval_profile="drafting",
            story_id=story_id,
            session_id=first_session_id,
        )
        check(
            any("银铃渡口" in hit.chunk.content for hit in first_hits),
            "会话附件解析后立即进入关键词检索",
        )
        other_session_hits = retrieve_context(
            project_name,
            "银铃渡口",
            retrieval_profile="drafting",
            story_id=story_id,
            session_id=second_session_id,
        )
        check(not other_session_hits, "会话附件不会泄漏到同故事的其它会话")
        other_story_hits = retrieve_context(
            project_name,
            "银铃渡口",
            retrieval_profile="drafting",
            story_id=other_story_id,
        )
        check(not other_story_hits, "会话附件不会泄漏到其它故事")

        story_attachment = import_creative_pasted_text(
            project_name,
            story_id,
            first_session_id,
            "群星塔的守门规则是午夜前不得报出真名。",
            title="群星塔规则",
            scope="story",
            schedule_knowledge=False,
        )
        check(story_attachment["scope"] == "story", "粘贴长文可保存为故事级附件")
        story_hits = retrieve_context(
            project_name,
            "午夜前不得报出真名",
            retrieval_profile="drafting",
            story_id=story_id,
            session_id=second_session_id,
        )
        check(bool(story_hits), "故事级附件可被同故事其它会话使用")

        existing_source_path = ingest_external_source_file(
            project_name,
            "existing_reference",
            "资料中心已有事实：琥珀钟只在黎明响起。",
        )
        existing_sources = list_existing_creative_sources(project_name)
        check(
            any(item.get("relative_path") == existing_source_path for item in existing_sources),
            "自由创作可列出资料中心已有来源",
        )
        existing_attachment = attach_existing_creative_source(
            project_name,
            story_id,
            first_session_id,
            str(existing_source_path),
            scope="session",
        )
        check(
            existing_attachment.get("attachment_kind") == "existing_source",
            "已有资料可附加到当前创作而不重复导入来源",
        )

        background_attachment = import_creative_pasted_text(
            project_name,
            story_id,
            first_session_id,
            "北港城的通行规则是携带蓝色火漆印。",
            title="后台提取资料",
            scope="story",
            schedule_knowledge=False,
        )
        with (
            patch(
                "novelforge.workflows.creative_attachments.get_model_readiness",
                return_value={"chat_available": True, "chat_status": "ready"},
            ),
            patch(
                "novelforge.workflows.ingestion_tasks.require_chat_ready",
                return_value={"chat_available": True},
            ),
            patch(
                "novelforge.workflows.creative_attachments.wake_ingestion_task_dispatcher"
            ),
        ):
            scheduled = schedule_creative_attachment_knowledge(
                project_name,
                str(background_attachment["attachment_id"]),
            )
        background_task = load_source_ingestion_task(
            project_name,
            str(scheduled.get("ingestion_task_id") or ""),
        )
        background_batch = next(
            item
            for item in list_long_reference_batches(project_name)
            if item.get("creative_attachment_id") == background_attachment["attachment_id"]
        )
        check(
            scheduled.get("status") == "processing"
            and bool(background_task.get("items"))
            and len(background_task.get("items") or [])
            == len(background_batch.get("segments") or []),
            "默认后台计划覆盖附件的全部切分片段",
        )
        with patch(
            "novelforge.workflows.creative_attachments.get_model_readiness",
            return_value={
                "chat_available": False,
                "chat_status": "missing",
                "chat_message": "未配置聊天模型。",
            },
        ):
            no_model_attachment = import_creative_pasted_text(
                project_name,
                story_id,
                first_session_id,
                "没有模型时仍然应当可检索的原文：雾灯编号七。",
                title="降级资料",
                scope="session",
            )
        check(
            no_model_attachment.get("status") == "indexed"
            and no_model_attachment.get("metadata", {}).get("background_status")
            == "capability_unavailable",
            "聊天能力不可用时原文仍可检索且后台知识化显式降级",
        )

        turn_attachment = import_creative_pasted_text(
            project_name,
            story_id,
            first_session_id,
            "下一段唯一线索：青铜鸟会在钟声之后开口。",
            title="本轮线索",
            scope="turn",
            schedule_knowledge=False,
        )
        check(turn_attachment["remaining_uses"] == 1, "仅下一轮附件保存一次消费计数")
        with patch.object(
            interactive_writing,
            "call_llm",
            return_value="钟声落下，青铜鸟终于开口。",
        ):
            result = interactive_writing.generate_writing_fragment(
                project_name,
                story_id,
                first_session_id,
                "写出线索出现的场面",
                action_type="generate",
            )
        context_text = "\n".join(
            str(block.get("content") or "")
            for block in result["context_assembly"]["blocks"]
        )
        check("青铜鸟" in context_text, "仅下一轮附件直接注入目标轮次上下文")
        bundle = load_creative_session_bundle(
            project_name,
            first_session_id,
            story_id=story_id,
        ) or {}
        consumed = next(
            item
            for item in bundle.get("attachments", [])
            if item.get("attachment_id") == turn_attachment["attachment_id"]
        )
        check(consumed["remaining_uses"] == 0, "成功领取后仅下一轮附件不会再次生效")

        retry_attachment = import_creative_pasted_text(
            project_name,
            story_id,
            second_session_id,
            "失败后仍需保留的本轮提示：雨伞内侧刻着白鸦。",
            title="失败重试提示",
            scope="turn",
            schedule_knowledge=False,
        )
        with patch.object(
            interactive_writing,
            "call_llm",
            side_effect=RuntimeError("injected attachment generation failure"),
        ):
            try:
                interactive_writing.generate_writing_fragment(
                    project_name,
                    story_id,
                    second_session_id,
                    "触发失败",
                    action_type="generate",
                )
            except RuntimeError:
                pass
            else:
                raise AssertionError("附件失败重试测试未抛出")
        retry_bundle = load_creative_session_bundle(
            project_name,
            second_session_id,
            story_id=story_id,
        ) or {}
        restored = next(
            item
            for item in retry_bundle.get("attachments", [])
            if item.get("attachment_id") == retry_attachment["attachment_id"]
        )
        check(
            restored["remaining_uses"] == 1 and not restored.get("turn_id"),
            "生成失败会释放仅下一轮附件供重试",
        )

        copied_story = copy_story(project_name, story_id, "附件故事副本")
        copied_session = next(
            item
            for item in list_creative_sessions(
                project_name,
                str(copied_story["story_id"]),
                include_archived=True,
            )
            if item.get("session_goal") == "使用附件创作"
        )
        copied_hits = retrieve_context(
            project_name,
            "银铃渡口",
            retrieval_profile="drafting",
            story_id=str(copied_story["story_id"]),
            session_id=str(copied_session["session_id"]),
        )
        check(bool(copied_hits), "复制故事后的附件按新故事和新会话归属检索")


def main() -> int:
    try:
        verify()
    except Exception as exc:
        print(json.dumps({"ok": False, "checks": CHECKS, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "checks": CHECKS}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
