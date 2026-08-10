from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.domain.ingestion_task_estimates import estimate_ingestion_task
from novelforge.domain.llm_preflight import (
    build_preflight_estimate,
    build_stage_estimate,
    parse_requested_output_range,
    token_range,
)
from novelforge.domain.web_research_tasks import build_web_research_estimate
from storage.repositories.llm_usage import (
    insert_llm_usage_event_row,
    list_llm_usage_calibration_rows,
)
from storage.schema import ensure_schema


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def _profile(**overrides) -> dict:
    result = {
        "id": "preflight-profile",
        "model_name": "test-chat",
        "embedding_model_name": "test-embedding",
        "provider_type": "deepseek",
        "base_url": "https://api.deepseek.com",
        "cost_tracking_mode": "manual",
        "input_price_per_million": 1.0,
        "output_price_per_million": 2.0,
        "embedding_price_per_million": 0.5,
        "preflight_enabled": True,
        "preflight_warning_tokens": 1000,
        "preflight_confirmation_tokens": 2000,
        "preflight_warning_cost_usd": 0,
        "preflight_confirmation_cost_usd": 0,
        "preflight_require_confirmation": True,
    }
    result.update(overrides)
    return result


def verify_ranges_and_pricing() -> None:
    check(
        token_range({"low": 20, "expected": 10, "high": 5})
        == {"low": 10, "expected": 10, "high": 10},
        "Token 区间始终有序",
    )
    check(parse_requested_output_range("800-1200 字") == (800, 1200), "解析写作长度区间")
    stage = build_stage_estimate(
        "测试阶段",
        operation="test.operation",
        agent_role="tester",
        input_tokens_per_call={"low": 100, "expected": 200, "high": 300},
        output_tokens_per_call={"low": 50, "expected": 100, "high": 200},
        embedding_tokens_per_call={"low": 10, "expected": 20, "high": 30},
        calibrate_output=False,
    )
    estimate = build_preflight_estimate([stage], profile=_profile())
    check(estimate["total_tokens"] == {"low": 160, "expected": 320, "high": 530}, "汇总三类 Token 区间")
    expected_cost = (200 * 1.0 + 100 * 2.0 + 20 * 0.5) / 1_000_000
    check(
        abs(estimate["cost_range_usd"]["expected"] - expected_cost) < 1e-12,
        "按当前价格快照计算预计费用",
    )
    check(
        abs(estimate["cost_range_cny"]["expected"] - expected_cost * 7.142857)
        < 1e-8,
        "预估同时提供人民币主显示金额",
    )
    check(estimate["budget"]["status"] == "within_budget", "预算使用区间上界判断")

    large = build_stage_estimate(
        "大任务",
        operation="test.large",
        agent_role="tester",
        input_tokens_per_call={"low": 1000, "expected": 1500, "high": 2500},
        calibrate_output=False,
    )
    large_estimate = build_preflight_estimate([large], profile=_profile())
    check(large_estimate["budget"]["confirmation_required"], "超过确认阈值要求显式确认")

    unpriced = build_preflight_estimate(
        [stage],
        profile=_profile(output_price_per_million=0),
    )
    check(unpriced["cost_range_usd"] is None, "缺少必要价格时不伪造金额")
    check("输出 Token" in unpriced["missing_price_components"], "说明缺失价格组件")
    tokens_only = build_preflight_estimate(
        [stage], profile=_profile(cost_tracking_mode="tokens_only")
    )
    check(tokens_only["cost_range_usd"] is None, "仅 Token 模式不显示费用")
    local = build_preflight_estimate(
        [stage],
        profile=_profile(
            provider_type="ollama",
            base_url="http://localhost:11434/v1",
            cost_tracking_mode="auto",
            input_price_per_million=0,
            output_price_per_million=0,
            embedding_price_per_million=0,
        ),
    )
    check(local["cost_range_usd"]["high"] == 0, "本地 Ollama 自动模式按零 API 费用展示")
    cny_priced = build_preflight_estimate(
        [stage],
        profile=_profile(
            pricing_currency="CNY",
            display_currency="CNY",
            usd_to_cny_rate=7.142857,
            input_price_per_million=7.142857,
            output_price_per_million=14.285714,
            embedding_price_per_million=3.5714285,
        ),
    )
    check(
        abs(cny_priced["cost_range_usd"]["expected"] - expected_cost) < 1e-8,
        "人民币单价会标准化为美元账本金额",
    )
    check(
        cny_priced["price_snapshot"]["currency"] == "CNY",
        "预估快照保留原始价格币种",
    )


def verify_history_calibration() -> None:
    baseline = {"low": 50, "expected": 100, "high": 150}
    insufficient = build_stage_estimate(
        "历史不足",
        operation="history.test",
        agent_role="tester",
        output_tokens_per_call=baseline,
        calibration={"sample_count": 4, "output_p50": 300, "output_p90": 500},
    )
    check(not insufficient["history_calibrated"], "少于五条样本不校准")
    calibrated = build_stage_estimate(
        "历史充分",
        operation="history.test",
        agent_role="tester",
        output_tokens_per_call=baseline,
        calibration={"sample_count": 20, "output_p50": 300, "output_p90": 500},
    )
    check(calibrated["history_calibrated"], "充分样本启用历史校准")
    check(calibrated["output_tokens"]["expected"] == 200, "模板与历史 P50 平滑合并")
    check(calibrated["output_tokens"]["high"] == 500, "P90 扩展保守上界")

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    for index in range(7):
        insert_llm_usage_event_row(
            conn,
            {
                "event_id": f"calibration-{index}",
                "occurred_at": f"2026-08-10T00:00:0{index}+00:00",
                "operation": "creative.fragment" if index < 6 else "other",
                "agent_role": "generator",
                "profile_id": "preflight-profile",
                "endpoint_type": "chat",
                "requested_model": "test-chat",
                "reported_model": "test-chat",
                "input_tokens": 100 + index,
                "output_tokens": 50 + index,
                "total_tokens": 150 + index * 2,
                "usage_status": "exact",
            },
        )
    rows = list_llm_usage_calibration_rows(
        conn,
        operation="creative.fragment",
        agent_role="generator",
        profile_id="preflight-profile",
        endpoint_type="chat",
        model_name="test-chat",
    )
    check(len(rows) == 6, "历史查询严格匹配操作、Agent、方案和模型")
    conn.close()


def verify_workflow_estimates() -> None:
    ingestion = estimate_ingestion_task(
        {"segments": [{"content": "设定文本" * 300}, {"content": "第二段" * 200}]},
        [0, 1],
        enabled_categories=["characters", "world_rules"],
        extraction_mode="deep",
        import_to_index=True,
        consolidate_after_extract=True,
        model_profile=_profile(),
    )
    check(ingestion["segment_count"] == 2, "资料导入保留任务规模")
    check(len(ingestion["stages"]) == 3, "资料导入拆分提取、整理和索引阶段")
    check(ingestion["cost_range_usd"] is not None, "资料导入提供费用区间")

    research = build_web_research_estimate(
        {
            "max_pages": 4,
            "source_kinds": ["official", "fanon"],
            "use_llm_planner": True,
            "use_llm_verifier": True,
            "enabled_categories": ["characters", "world_rules"],
        },
        model_profile=_profile(),
    )
    check(research["estimated_model_calls"] == 6, "网络研究汇总多 Agent 模型调用")
    check(len(research["stages"]) == 4, "网络研究拆分规划、提取、验证和索引")
    check(research["estimated_embedding_tokens"] > 0, "网络研究纳入向量索引 Token")
    check(len(research["external_calls"]) == 2, "网络研究单列搜索和抓取外部调用")


def main() -> int:
    try:
        verify_ranges_and_pricing()
        verify_history_calibration()
        verify_workflow_estimates()
    except Exception as exc:
        print({"ok": False, "checks": CHECKS, "error": str(exc)})
        return 1
    print({"ok": True, "checks": len(CHECKS)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
