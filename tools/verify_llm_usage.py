from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.core import llm as llm_module
from novelforge.core.llm_usage import (
    build_llm_usage_event,
    current_llm_usage_context,
    llm_usage_scope,
    normalize_usage,
)
from storage.repositories.llm_usage import (
    delete_llm_usage_event_rows,
    insert_llm_usage_event_row,
    list_daily_llm_usage_rows,
    list_llm_usage_breakdown_rows,
    rename_llm_usage_project_rows,
    summarize_llm_usage_rows,
)
from storage.schema import CURRENT_SCHEMA_VERSION, ensure_schema


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def _profile(**overrides) -> dict:
    profile = {
        "id": "usage-test",
        "profile_id": "usage-test",
        "base_url": "https://api.deepseek.com",
        "provider_type": "deepseek",
        "cost_tracking_mode": "manual",
        "input_price_per_million": 0.14,
        "cached_input_price_per_million": 0.0028,
        "cache_write_price_per_million": 0,
        "output_price_per_million": 0.28,
        "embedding_price_per_million": 0.02,
        "pricing_updated_at": "2026-08-10",
        "pricing_source_url": "https://api-docs.deepseek.com/quick_start/pricing/",
    }
    profile.update(overrides)
    return profile


def verify_normalization_and_costs() -> None:
    normalized = normalize_usage(
        {
            "prompt_tokens": 1000,
            "prompt_cache_hit_tokens": 400,
            "prompt_cache_miss_tokens": 600,
            "completion_tokens": 500,
            "total_tokens": 1500,
            "completion_tokens_details": {"reasoning_tokens": 200},
        },
        endpoint_type="chat",
    )
    check(normalized["cached_input_tokens"] == 400, "DeepSeek 缓存命中 Token 被标准化")
    check(normalized["reasoning_tokens"] == 200, "推理 Token 被标准化")
    event = build_llm_usage_event(
        usage={
            "prompt_tokens": 1000,
            "prompt_cache_hit_tokens": 400,
            "completion_tokens": 500,
            "total_tokens": 1500,
        },
        profile=_profile(),
        endpoint_type="chat",
        requested_model="deepseek-v4-flash",
    )
    check(event["calculated_cost_microusd"] == 225, "缓存输入和输出价格按微美元精确计算")
    check(event["cost_source"] == "configured_rates", "手动价格标记为配置估算")
    check(event["price_snapshot"]["pricing_updated_at"] == "2026-08-10", "调用保存价格快照")

    cny_event = build_llm_usage_event(
        usage={
            "prompt_tokens": 1000,
            "prompt_cache_hit_tokens": 400,
            "completion_tokens": 500,
            "total_tokens": 1500,
        },
        profile=_profile(
            pricing_currency="CNY",
            display_currency="CNY",
            usd_to_cny_rate=7.142857,
            input_price_per_million=1.0,
            cached_input_price_per_million=0.02,
            output_price_per_million=2.0,
        ),
        endpoint_type="chat",
        requested_model="deepseek-v4-flash",
    )
    check(cny_event["calculated_cost_microusd"] == 225, "人民币单价按快照系数写入美元账本")
    check(cny_event["price_snapshot"]["currency"] == "CNY", "价格快照保留人民币币种")

    openrouter = build_llm_usage_event(
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.012345},
        profile=_profile(
            provider_type="openrouter",
            base_url="https://openrouter.ai/api/v1",
            cost_tracking_mode="provider_reported",
        ),
        endpoint_type="chat",
        requested_model="test/model",
    )
    check(openrouter["cost_microusd"] == 12345, "OpenRouter 供应商费用优先使用")
    check(openrouter["cost_source"] == "provider_reported", "供应商费用来源被标记")

    estimated = build_llm_usage_event(
        usage=None,
        profile=_profile(cost_tracking_mode="tokens_only"),
        endpoint_type="chat",
        requested_model="fallback",
        input_text="这是没有 usage 字段的输入",
        output_text="这是输出",
    )
    check(estimated["usage_status"] == "estimated" and estimated["total_tokens"] > 0, "缺少 usage 时回退估算 Token")
    check(estimated["cost_microusd"] is None and estimated["cost_source"] == "tokens_only", "仅 Token 模式不伪造零费用")


def verify_context_attribution() -> None:
    check(current_llm_usage_context() == {}, "初始归因上下文为空")
    with llm_usage_scope(
        project_name="demo",
        story_id="story-a",
        task_id="task-1",
        operation="workflow.run",
        agent_role="orchestrator",
        metadata={"source": "ui"},
    ) as parent:
        operation_id = parent["operation_id"]
        with llm_usage_scope(operation="workflow.extract", agent_role="extractor", metadata={"page": 3}):
            event = build_llm_usage_event(
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                profile=_profile(),
                endpoint_type="chat",
                requested_model="model",
            )
    check(event["project_name"] == "demo" and event["task_id"] == "task-1", "子 Agent 继承项目和任务归因")
    check(event["operation_id"] == operation_id and event["operation"] == "workflow.extract", "子 Agent 细化操作并继承操作 ID")
    check(event["metadata"]["source"] == "ui" and event["metadata"]["page"] == 3, "嵌套元数据被合并")
    check(current_llm_usage_context() == {}, "退出作用域后归因上下文复原")


def verify_repository() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    check(ensure_schema(conn) == CURRENT_SCHEMA_VERSION == 10, "数据库迁移升级到版本 10")
    base = build_llm_usage_event(
        usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        profile=_profile(),
        endpoint_type="chat",
        requested_model="deepseek-v4-flash",
        provider_request_id="provider-request-1",
        context={"project_name": "demo", "story_id": "story-a", "operation": "chapter.write"},
    )
    second = dict(base)
    second.update(
        event_id="usage-second",
        provider_request_id="provider-request-2",
        endpoint_type="embedding",
        operation="web_research.index",
        agent_role="indexer",
        input_tokens=0,
        output_tokens=0,
        embedding_tokens=80,
        total_tokens=80,
        cost_microusd=2,
        calculated_cost_microusd=2,
    )
    check(insert_llm_usage_event_row(conn, base), "用量事件可追加")
    check(not insert_llm_usage_event_row(conn, base), "事件 ID 重复时幂等")
    duplicate_request = dict(base, event_id="usage-duplicate-request")
    check(not insert_llm_usage_event_row(conn, duplicate_request), "供应商请求 ID 重复时幂等")
    check(insert_llm_usage_event_row(conn, second), "第二条用量事件可追加")
    summary = summarize_llm_usage_rows(conn, project_name="demo", story_id="story-a")
    check(summary["request_count"] == 2 and summary["total_tokens"] == 230, "项目故事用量可聚合")
    check(len(list_daily_llm_usage_rows(conn, project_name="demo", utc_offset_minutes=480)) == 1, "用量可按本地日期聚合")
    model_rows = list_llm_usage_breakdown_rows(conn, dimension="model", project_name="demo")
    check(model_rows[0]["request_count"] == 2, "用量可按模型拆分")
    check(rename_llm_usage_project_rows(conn, "demo", "renamed-demo") == 2, "项目重命名同步历史用量归因")
    check(summarize_llm_usage_rows(conn, project_name="renamed-demo")["request_count"] == 2, "重命名后历史用量可继续查询")
    check(delete_llm_usage_event_rows(conn, event_ids=[second["event_id"]]) == 1, "显式事件范围可清理")
    try:
        delete_llm_usage_event_rows(conn)
    except ValueError:
        CHECKS.append("无范围清理被拒绝")
    else:
        raise AssertionError("无范围清理必须被拒绝")
    conn.close()


class _Completions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class _RejectUsageOptionCompletions(_Completions):
    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise RuntimeError("unknown field: stream_options")
        return self.responses.pop(0)


def _chat_response(content: str, *, request_id: str = "chat-1"):
    return SimpleNamespace(
        id=request_id,
        model="reported-model",
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=8, total_tokens=20),
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
    )


def verify_llm_integration() -> None:
    original = {
        name: getattr(llm_module, name)
        for name in (
            "_get_api_key",
            "_get_model_name",
            "_get_embedding_model_name",
            "_get_client",
            "_require_openai",
            "load_llm_settings",
            "persist_llm_usage_event",
        )
    }
    captured: list[dict] = []
    try:
        llm_module._get_api_key = lambda: "test-key"
        llm_module._get_model_name = lambda: "patched-chat-model"
        llm_module._get_embedding_model_name = lambda: "patched-embedding-model"
        llm_module._require_openai = lambda: None
        llm_module.load_llm_settings = lambda: _profile()
        llm_module.persist_llm_usage_event = lambda event: captured.append(event) or True

        completions = _Completions([_chat_response("普通响应")])
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        llm_module._get_client = lambda: client
        check(llm_module.call_llm("输入") == "普通响应", "普通对话调用保持原返回值")
        check(captured[-1]["requested_model"] == "patched-chat-model" and captured[-1]["total_tokens"] == 20, "普通响应 usage 被记录且尊重模型钩子")

        chunks = [
            SimpleNamespace(id="stream-1", model="reported-model", usage=None, choices=[SimpleNamespace(delta=SimpleNamespace(content="流式"))]),
            SimpleNamespace(id="stream-1", model="reported-model", usage=SimpleNamespace(prompt_tokens=9, completion_tokens=3, total_tokens=12), choices=[]),
        ]
        completions = _Completions([chunks])
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        llm_module._get_client = lambda: client
        emitted: list[str] = []
        check(llm_module.call_llm("输入", stream_callback=emitted.append) == "流式", "usage-only 末尾分片不影响流式内容")
        check(completions.calls[0]["stream_options"] == {"include_usage": True}, "流式请求主动申请 usage")
        check(captured[-1]["provider_request_id"] == "stream-1" and captured[-1]["total_tokens"] == 12, "流式末尾 usage 被记录")

        retry_chunks = [
            SimpleNamespace(id="stream-compat", model="compat-model", usage=None, choices=[SimpleNamespace(delta=SimpleNamespace(content="兼容流式"))]),
        ]
        completions = _RejectUsageOptionCompletions([retry_chunks])
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        llm_module._get_client = lambda: client
        check(llm_module.call_llm("输入", stream_callback=lambda _delta: None) == "兼容流式", "不支持 stream_options 的接口自动重试")
        check("stream_options" not in completions.calls[1], "兼容重试移除 usage 扩展参数")
        check(captured[-1]["usage_status"] == "estimated", "兼容流式缺少 usage 时明确标记估算")

        embedding_response = SimpleNamespace(
            id="embedding-1",
            model="reported-embedding",
            usage=SimpleNamespace(prompt_tokens=7, total_tokens=7),
            data=[SimpleNamespace(embedding=[0.1, 0.2])],
        )
        embedding_create_calls: list[dict] = []
        client = SimpleNamespace(
            embeddings=SimpleNamespace(
                create=lambda **kwargs: embedding_create_calls.append(kwargs) or embedding_response
            )
        )
        llm_module._get_client = lambda: client
        check(llm_module.get_embedding("向量输入") == [0.1, 0.2], "Embedding 调用保持原返回值")
        check(captured[-1]["endpoint_type"] == "embedding" and captured[-1]["embedding_tokens"] == 7, "Embedding usage 被记录")
        check(embedding_create_calls[0]["model"] == "patched-embedding-model", "Embedding 模型钩子保持兼容")
    finally:
        for name, value in original.items():
            setattr(llm_module, name, value)


def main() -> int:
    try:
        verify_normalization_and_costs()
        verify_context_attribution()
        verify_repository()
        verify_llm_integration()
    except Exception as exc:
        print({"ok": False, "checks": CHECKS, "error": str(exc)})
        return 1
    print({"ok": True, "checks": len(CHECKS)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
