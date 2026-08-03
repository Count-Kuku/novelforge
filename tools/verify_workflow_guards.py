"""聚焦验证模型响应、流水线隔离和设定提炼持久化保护。"""
from __future__ import annotations

import json
import sys
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.core import llm  # noqa: E402
from novelforge.workflows import skills  # noqa: E402


CHECKS: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    CHECKS.append(message)


def expect_runtime_error(callback, expected_text: str) -> None:
    try:
        callback()
    except RuntimeError as exc:
        check(expected_text in str(exc), f"RuntimeError 包含：{expected_text}")
        return
    raise AssertionError(f"预期 RuntimeError：{expected_text}")


def fake_client(*, chat_response=None, embedding_response=None):
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **_kwargs: chat_response),
        ),
        embeddings=SimpleNamespace(create=lambda **_kwargs: embedding_response),
    )


def verify_llm_guards() -> None:
    common_patches = {
        "_get_api_key": lambda: "test-key",
        "_require_openai": lambda: object,
        "_get_model_name": lambda: "test-model",
        "_get_embedding_model_name": lambda: "test-embedding-model",
    }

    with ExitStack() as stack:
        for name, replacement in common_patches.items():
            stack.enter_context(patch.object(llm, name, replacement))

        with patch.object(llm, "_get_client", lambda: fake_client(chat_response=SimpleNamespace(choices=[]))):
            expect_runtime_error(lambda: llm.call_llm("hello"), "没有返回任何候选结果")

        non_text = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=[{"text": "hello"}]))],
        )
        with patch.object(llm, "_get_client", lambda: fake_client(chat_response=non_text)):
            expect_runtime_error(lambda: llm.call_llm("hello"), "非文本内容")

        blank = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="   "))],
        )
        with patch.object(llm, "_get_client", lambda: fake_client(chat_response=blank)):
            expect_runtime_error(lambda: llm.call_llm("hello"), "空响应")

        empty_stream = [SimpleNamespace(choices=[])]
        with patch.object(llm, "_get_client", lambda: fake_client(chat_response=empty_stream)):
            expect_runtime_error(
                lambda: llm.call_llm("hello", stream_callback=lambda _delta: None),
                "空响应",
            )

        streamed_deltas: list[str] = []
        valid_stream = [
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="hello"))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=" world"))]),
        ]
        with patch.object(llm, "_get_client", lambda: fake_client(chat_response=valid_stream)):
            streamed = llm.call_llm("hello", stream_callback=streamed_deltas.append)
        check(streamed == "hello world", "合法流式文本仍正常拼接")
        check(streamed_deltas == ["hello", " world"], "合法流式文本仍逐段回调")

        with patch.object(
            llm,
            "_get_client",
            lambda: fake_client(embedding_response=SimpleNamespace(data=[])),
        ):
            expect_runtime_error(lambda: llm.get_embedding("hello"), "没有返回向量数据")

        for embedding, expected_text in [
            ([], "空向量"),
            ([0.25, float("nan")], "非有限数值"),
            ([0.25, float("inf")], "非有限数值"),
        ]:
            response = SimpleNamespace(data=[SimpleNamespace(embedding=embedding)])
            with patch.object(llm, "_get_client", lambda response=response: fake_client(embedding_response=response)):
                expect_runtime_error(lambda: llm.get_embedding("hello"), expected_text)

        valid_embedding = SimpleNamespace(data=[SimpleNamespace(embedding=[0.25, -0.5])])
        with patch.object(
            llm,
            "_get_client",
            lambda: fake_client(embedding_response=valid_embedding),
        ):
            check(llm.get_embedding("hello") == [0.25, -0.5], "合法有限向量仍正常返回")


def verify_json_extraction() -> None:
    payload = skills._extract_json_object(
        "说明里的空占位符 {} 不应抢占结果。\n"
        "```json\n"
        '{"status":"pass","nested":{"text":"右花括号 } 仍在字符串中"}}\n'
        "```\n"
        "尾注 {not-json}",
    )
    check(payload["status"] == "pass", "优先提取 fenced JSON，而不是说明中的占位对象")
    check(payload["nested"]["text"].startswith("右花括号"), "正确处理嵌套对象和字符串花括号")

    try:
        skills._extract_json_object("[1, 2, 3]")
    except ValueError as exc:
        check("JSON 对象" in str(exc), "拒绝顶层非对象 JSON")
    else:
        raise AssertionError("顶层数组应被拒绝")


def verify_pipeline_story_isolation() -> None:
    started_at = "2026-07-16T12:34:56.123456"
    first = skills._build_pipeline_run_id(7, "story-alpha", started_at=started_at)
    second = skills._build_pipeline_run_id(7, "story-alpha", started_at=started_at)
    other_story = skills._build_pipeline_run_id(7, "story-beta", started_at=started_at)
    resumed = skills._build_pipeline_run_id(7, "story-alpha", started_at=started_at, resumed=True)
    check(first != second, "同一微秒的流水线 run_id 仍保持唯一")
    check(first != other_story and "story-alpha" in first, "run_id 包含故事隔离标识")
    check("_resume_" in resumed, "恢复运行保留 resume 标识")

    saved_runs: list[dict] = []

    def fake_save_pipeline_run(project_name, run_id, content, story_id="default"):
        saved_runs.append({
            "project_name": project_name,
            "run_id": run_id,
            "story_id": story_id,
            "payload": json.loads(content),
        })

    failed_outline = skills._make_step_result(
        "chapter_outline",
        success=False,
        status="failed",
        error="expected test failure",
    ).model_dump()
    with patch.object(skills, "generate_chapter_outline", lambda *_args, **_kwargs: failed_outline), patch.object(
        skills,
        "get_retrieval_trace",
        lambda *_args, **_kwargs: [],
    ), patch.object(skills, "save_pipeline_run", fake_save_pipeline_run):
        result = skills.pipeline_plan_write_review_update(
            "demo-project",
            7,
            "test requirement",
            story_id="story-alpha",
        )

    check(result["story_id"] == "story-alpha", "序列化流水线状态包含 story_id")
    check(saved_runs[0]["payload"]["story_id"] == "story-alpha", "持久化流水线 payload 包含 story_id")
    check(saved_runs[0]["story_id"] == "story-alpha", "流水线写入目标故事命名空间")

    previous = json.dumps({
        "resumable": True,
        "story_id": "story-alpha",
        "chapter_no": 7,
    })
    with patch.object(skills, "load_pipeline_run", lambda *_args, **_kwargs: previous):
        expect_runtime_error(
            lambda: skills.resume_chapter_pipeline(
                "demo-project",
                "foreign-run",
                story_id="story-beta",
            ),
            "属于其他故事",
        )


def sample_update_data() -> dict:
    return {
        "chapter_no": 7,
        "chapter_summary": "主角进入现代城市。",
        "new_characters": ["林澈：本世界线的新角色"],
        "world_updates": [],
        "timeline_updates": [],
        "foreshadowing_updates": [],
    }


def verify_pending_knowledge_isolation() -> None:
    au_profile = {
        "worldline_id": "au_modern",
        "worldline_label": "现代 AU",
        "worldline_retrieval_mode": "strict",
        "version_scope": "au",
    }
    items = skills.build_pending_knowledge_from_setting_extraction(
        sample_update_data(),
        "story-au",
        7,
        creative_profile=au_profile,
    )
    check(bool(items), "AU 设定提炼生成待确认知识")
    check(items[0]["story_id"] == "story-au", "待确认知识继承 story_id")
    check(items[0]["worldline_id"] == "au_modern", "待确认知识继承 AU worldline_id")
    check(items[0]["version_scope"] == "au", "待确认知识继承 AU version_scope")
    check(items[0]["worldline_id"] != "main", "AU strict 不会被默认到 main 世界线")

    strict_without_worldline = {
        "worldline_id": "",
        "worldline_retrieval_mode": "strict",
        "version_scope": "au",
    }
    expect_runtime_error(
        lambda: skills.build_pending_knowledge_from_setting_extraction(
            sample_update_data(),
            "story-au",
            7,
            creative_profile=strict_without_worldline,
        ),
        "未设置世界线 ID",
    )


def verify_summary_save_failure() -> None:
    update_data = sample_update_data()
    au_profile = {
        "worldline_id": "au_modern",
        "worldline_label": "现代 AU",
        "worldline_retrieval_mode": "strict",
        "version_scope": "au",
    }
    replacements = {
        "build_generation_setting_context": lambda *_args, **_kwargs: {},
        "_build_retrieval_context": lambda *_args, **_kwargs: "",
        "_build_rules_text": lambda *_args, **_kwargs: "",
        "setting_extraction_prompt": lambda *_args, **_kwargs: "prompt",
        "merge_retrieval_context": lambda prompt, _context: prompt,
        "call_llm": lambda *_args, **_kwargs: "{}",
        "get_retrieval_trace": lambda *_args, **_kwargs: [],
        "validate_setting_extraction_result": lambda *_args, **_kwargs: SimpleNamespace(
            model_dump=lambda: update_data,
        ),
        "load_creative_profile": lambda *_args, **_kwargs: au_profile,
        "queue_pending_knowledge_items": lambda _project, items, **_kwargs: len(items),
        "load_story_chapter_summaries": lambda *_args, **_kwargs: [],
        "save_story_chapter_summaries": lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("disk full")
        ),
    }
    with ExitStack() as stack:
        for name, replacement in replacements.items():
            stack.enter_context(patch.object(skills, name, replacement))
        result = skills.extract_setting_candidates_from_chapter(
            "demo-project",
            7,
            "chapter text",
            story_id="story-au",
        )

    check(result["success"] is False, "章节摘要保存失败时步骤不再报告 success")
    check(result["status"] == "failed", "章节摘要保存失败时步骤状态为 failed")
    check(result["data"]["chapter_summary_saved"] is False, "章节摘要保存失败时 saved 标志为 false")
    check(result["artifacts"]["chapter_summary_saved"] is False, "产物元数据同步标记摘要未保存")
    check("章节摘要保存失败" in result["error"], "步骤错误明确说明章节摘要保存失败")
    pending = result["data"]["pending_knowledge_items"][0]
    check(pending["worldline_id"] == "au_modern", "真实设定提炼路径保留 AU 世界线")


def main() -> int:
    verify_llm_guards()
    verify_json_extraction()
    verify_pipeline_story_isolation()
    verify_pending_knowledge_isolation()
    verify_summary_save_failure()
    print(json.dumps({"ok": True, "checks": len(CHECKS)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
