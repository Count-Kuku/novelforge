"""Explainable call, Token, and cost estimates for source-ingestion tasks."""
from __future__ import annotations

import math

from novelforge.core.token_estimation import estimate_text_tokens
from novelforge.domain.llm_preflight import build_preflight_estimate, build_stage_estimate


MODE_OUTPUT_FACTORS = {
    "general": 1.0,
    "deep": 1.45,
    "characters": 1.15,
    "relationships": 1.15,
    "timeline": 1.15,
    "world": 1.15,
    "style": 1.1,
    "strict_canon": 1.2,
    "fanfic_reference": 1.2,
}


def estimate_ingestion_task(
    batch: dict,
    segment_indices: list[int],
    *,
    enabled_categories: list[str],
    extraction_mode: str,
    import_to_index: bool,
    consolidate_after_extract: bool,
    custom_instructions: str = "",
    model_profile: dict | None = None,
    calibrations: dict | None = None,
) -> dict:
    """Estimate a durable ingestion workflow without performing any model call."""

    segments = batch.get("segments", []) if isinstance(batch.get("segments", []), list) else []
    valid_indices: list[int] = []
    for raw_index in segment_indices:
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(segments) and index not in valid_indices:
            valid_indices.append(index)

    source_chars = sum(len(str(segments[index].get("content") or "")) for index in valid_indices)
    source_tokens = estimate_text_tokens(
        "\n".join(str(segments[index].get("content") or "") for index in valid_indices)
    )
    category_count = max(len(enabled_categories), 1)
    segment_count = len(valid_indices)
    mode_factor = MODE_OUTPUT_FACTORS.get(str(extraction_mode or "general"), 1.0)
    instruction_tokens = estimate_text_tokens(custom_instructions)
    prompt_overhead_per_call = 850 + category_count * 65 + instruction_tokens
    average_source_tokens = math.ceil(source_tokens / segment_count) if segment_count else 0
    output_per_call = math.ceil((360 + category_count * 105) * mode_factor)
    history = dict(calibrations or {})

    stages = [
        build_stage_estimate(
            "知识提取",
            operation="source_ingestion.run",
            agent_role="ingestion",
            call_count=segment_count,
            input_tokens_per_call={
                "low": math.ceil((average_source_tokens + prompt_overhead_per_call) * 0.85),
                "expected": average_source_tokens + prompt_overhead_per_call,
                "high": math.ceil((average_source_tokens + prompt_overhead_per_call) * 1.2),
            },
            output_tokens_per_call={
                "low": math.ceil(output_per_call * 0.65),
                "expected": output_per_call,
                "high": math.ceil(output_per_call * 1.55),
            },
            calibration=history.get("chat"),
            calibrate_input=False,
            calibrate_output=True,
            confidence="medium",
            assumptions=["每个所选资料片段预计触发一次知识提取调用。"],
        )
    ]

    expected_extraction_output = segment_count * output_per_call
    if consolidate_after_extract and segment_count:
        consolidation_input = min(math.ceil(expected_extraction_output * 0.75), 24000) + 700
        consolidation_output = min(800 + category_count * 100, 3000)
        stages.append(
            build_stage_estimate(
                "知识整理",
                operation="source_ingestion.run",
                agent_role="ingestion",
                call_count=1,
                input_tokens_per_call={
                    "low": math.ceil(consolidation_input * 0.75),
                    "expected": consolidation_input,
                    "high": math.ceil(consolidation_input * 1.3),
                },
                output_tokens_per_call={
                    "low": math.ceil(consolidation_output * 0.65),
                    "expected": consolidation_output,
                    "high": math.ceil(consolidation_output * 1.5),
                },
                calibration=history.get("chat"),
                calibrate_input=False,
                calibrate_output=True,
                confidence="medium",
                assumptions=["开启提取后整理时，额外预计一次汇总调用。"],
            )
        )

    if import_to_index and source_tokens:
        stages.append(
            build_stage_estimate(
                "原文向量索引",
                operation="source_ingestion.run",
                agent_role="ingestion",
                endpoint_type="embedding",
                call_count=1,
                embedding_tokens_per_call={
                    "low": math.ceil(source_tokens * 0.9),
                    "expected": source_tokens,
                    "high": math.ceil(source_tokens * 1.15),
                },
                calibration=history.get("embedding"),
                calibrate_output=False,
                confidence="high",
                assumptions=["Embedding Token 按所选原文长度估算。"],
            )
        )

    result = build_preflight_estimate(
        stages,
        profile=model_profile,
        estimate_kind="source_ingestion",
        assumptions=[
            "Token 按中英文混合文本启发式估算，实际值受模型 tokenizer 影响。",
            "输出量以所选分类和提取模式为基线，并以区间表达不确定性。",
            "费用使用当前模型配置快照，不代表供应商最终账单。",
        ],
    )
    result.update(
        {
            "segment_count": segment_count,
            "source_char_count": source_chars,
            # Existing task repositories store a numeric compatibility field.
            "estimated_cost_usd": float(result.get("estimated_cost_usd") or 0.0),
        }
    )
    return result
