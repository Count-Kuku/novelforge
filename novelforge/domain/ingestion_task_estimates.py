"""Explainable call, token, and cost estimates for source-ingestion tasks."""
from __future__ import annotations

import math


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


def _safe_float(value: object) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(number, 0.0)


def _token_estimate(char_count: int) -> int:
    # Mixed Chinese/English source text commonly falls around 1.6-2.0
    # characters per token. 1.8 is deliberately conservative without a
    # model-specific tokenizer.
    return max(1, math.ceil(max(int(char_count), 0) / 1.8))


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
) -> dict:
    segments = batch.get("segments", []) if isinstance(batch.get("segments", []), list) else []
    valid_indices = []
    for raw_index in segment_indices:
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(segments) and index not in valid_indices:
            valid_indices.append(index)

    source_chars = sum(len(str(segments[index].get("content") or "")) for index in valid_indices)
    category_count = max(len(enabled_categories), 1)
    segment_count = len(valid_indices)
    mode_factor = MODE_OUTPUT_FACTORS.get(str(extraction_mode or "general"), 1.0)
    instruction_tokens = _token_estimate(len(str(custom_instructions or ""))) if custom_instructions else 0
    prompt_overhead_per_call = 850 + category_count * 65 + instruction_tokens
    estimated_input_tokens = _token_estimate(source_chars) + segment_count * prompt_overhead_per_call
    estimated_output_tokens = math.ceil(segment_count * (360 + category_count * 105) * mode_factor)
    llm_call_count = segment_count

    if consolidate_after_extract and segment_count:
        llm_call_count += 1
        estimated_input_tokens += min(math.ceil(estimated_output_tokens * 0.75), 24000) + 700
        estimated_output_tokens += min(800 + category_count * 100, 3000)

    estimated_embedding_tokens = _token_estimate(source_chars) if import_to_index and source_chars else 0
    profile = dict(model_profile or {})
    input_rate = _safe_float(profile.get("input_price_per_million"))
    output_rate = _safe_float(profile.get("output_price_per_million"))
    embedding_rate = _safe_float(profile.get("embedding_price_per_million"))
    missing_price_components = []
    if estimated_input_tokens and not input_rate:
        missing_price_components.append("输入 Token")
    if estimated_output_tokens and not output_rate:
        missing_price_components.append("输出 Token")
    if estimated_embedding_tokens and not embedding_rate:
        missing_price_components.append("Embedding Token")
    pricing_configured = not missing_price_components
    estimated_cost_usd = (
        estimated_input_tokens * input_rate
        + estimated_output_tokens * output_rate
        + estimated_embedding_tokens * embedding_rate
    ) / 1_000_000

    return {
        "segment_count": segment_count,
        "source_char_count": source_chars,
        "llm_call_count": llm_call_count,
        "estimated_input_tokens": int(estimated_input_tokens),
        "estimated_output_tokens": int(estimated_output_tokens),
        "estimated_embedding_tokens": int(estimated_embedding_tokens),
        "estimated_total_tokens": int(
            estimated_input_tokens + estimated_output_tokens + estimated_embedding_tokens
        ),
        "estimated_cost_usd": round(estimated_cost_usd, 6),
        "pricing_configured": pricing_configured,
        "missing_price_components": missing_price_components,
        "model_profile_id": str(profile.get("id") or ""),
        "model_name": str(profile.get("model_name") or ""),
        "embedding_model_name": str(profile.get("embedding_model_name") or ""),
        "price_snapshot": {
            "input_price_per_million": input_rate,
            "output_price_per_million": output_rate,
            "embedding_price_per_million": embedding_rate,
        },
        "assumptions": [
            "按平均 1.8 字符/Token 估算，实际值受模型 tokenizer 影响。",
            "每个资料片段估算一次知识提取调用。",
            "知识整理开启时额外估算一次整理调用。",
            "这是执行前估算，不是供应商实际账单。",
        ],
    }
