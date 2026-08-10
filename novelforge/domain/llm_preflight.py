"""Pure execution-time Token, cost, confidence, and budget estimates."""
from __future__ import annotations

import math
import re
from collections.abc import Iterable
from urllib.parse import urlparse

from novelforge.core.cost_currency import (
    convert_cost_range,
    cost_display_preferences,
)

CONFIDENCE_ORDER = {"high": 3, "medium": 2, "low": 1}
CONFIDENCE_LABELS = {"high": "较高", "medium": "中等", "low": "较低"}


def _safe_float(value: object) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return number if math.isfinite(number) and number >= 0 else 0.0


def _safe_int(value: object) -> int:
    try:
        return max(int(math.ceil(float(value or 0))), 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def token_range(
    value: object = 0,
    *,
    low_factor: float = 0.75,
    high_factor: float = 1.35,
) -> dict[str, int]:
    """Normalize a scalar or mapping into an ordered low/expected/high range."""

    if isinstance(value, dict):
        expected = _safe_int(value.get("expected", value.get("mid", value.get("high", 0))))
        low = _safe_int(value.get("low", expected))
        high = _safe_int(value.get("high", expected))
    else:
        expected = _safe_int(value)
        low = _safe_int(expected * max(low_factor, 0))
        high = _safe_int(expected * max(high_factor, 0))
    low = min(low, expected)
    high = max(high, expected)
    return {"low": low, "expected": expected, "high": high}


def scale_token_range(value: object, multiplier: int) -> dict[str, int]:
    normalized = token_range(value)
    count = max(int(multiplier), 0)
    return {key: amount * count for key, amount in normalized.items()}


def add_token_ranges(values: Iterable[object]) -> dict[str, int]:
    total = {"low": 0, "expected": 0, "high": 0}
    for value in values:
        normalized = token_range(value, low_factor=1.0, high_factor=1.0)
        for key in total:
            total[key] += normalized[key]
    return total


def parse_requested_output_range(
    value: object,
    *,
    default_low: int = 800,
    default_high: int = 1200,
) -> tuple[int, int]:
    """Extract a practical output character range from values such as 800-1200."""

    numbers = [int(item) for item in re.findall(r"\d+", str(value or ""))]
    if not numbers:
        return max(default_low, 1), max(default_high, default_low)
    if len(numbers) == 1:
        target = max(numbers[0], 1)
        return max(int(target * 0.8), 1), max(int(target * 1.2), target)
    low, high = sorted(numbers[:2])
    return max(low, 1), max(high, low)


def _history_adjusted_range(
    baseline: dict[str, int],
    calibration: dict | None,
    token_kind: str,
) -> tuple[dict[str, int], bool]:
    history = dict(calibration or {})
    sample_count = _safe_int(history.get("sample_count"))
    if sample_count < 5:
        return baseline, False
    p50 = _safe_int(history.get(f"{token_kind}_p50"))
    p90 = _safe_int(history.get(f"{token_kind}_p90"))
    if p50 <= 0:
        return baseline, False
    adjusted = {
        "low": min(baseline["low"], max(_safe_int(p50 * 0.7), 1)),
        "expected": max(_safe_int((baseline["expected"] + p50) / 2), 1),
        "high": max(baseline["high"], p90 or p50),
    }
    adjusted["low"] = min(adjusted["low"], adjusted["expected"])
    adjusted["high"] = max(adjusted["high"], adjusted["expected"])
    return adjusted, True


def build_stage_estimate(
    stage_name: str,
    *,
    operation: str,
    agent_role: str,
    call_count: int = 1,
    endpoint_type: str = "chat",
    input_tokens_per_call: object = 0,
    output_tokens_per_call: object = 0,
    embedding_tokens_per_call: object = 0,
    calibration: dict | None = None,
    calibrate_input: bool = False,
    calibrate_output: bool = True,
    confidence: str = "medium",
    assumptions: list[str] | None = None,
) -> dict:
    """Build one explainable stage estimate, optionally calibrated by history."""

    calls = max(int(call_count), 0)
    input_per_call = token_range(input_tokens_per_call)
    output_per_call = token_range(output_tokens_per_call)
    embedding_per_call = token_range(embedding_tokens_per_call)
    input_calibrated = False
    output_calibrated = False
    if calibrate_input:
        input_per_call, input_calibrated = _history_adjusted_range(
            input_per_call, calibration, "input"
        )
    if calibrate_output:
        output_per_call, output_calibrated = _history_adjusted_range(
            output_per_call, calibration, "output"
        )
    history_used = input_calibrated or output_calibrated
    effective_confidence = confidence if confidence in CONFIDENCE_ORDER else "medium"
    if history_used and _safe_int(dict(calibration or {}).get("sample_count")) >= 20:
        effective_confidence = "high" if effective_confidence == "medium" else effective_confidence
    return {
        "stage_name": str(stage_name or operation or "模型调用"),
        "operation": str(operation or "unattributed"),
        "agent_role": str(agent_role or ""),
        "endpoint_type": str(endpoint_type or "chat"),
        "call_count": calls,
        "input_tokens": scale_token_range(input_per_call, calls),
        "output_tokens": scale_token_range(output_per_call, calls),
        "embedding_tokens": scale_token_range(embedding_per_call, calls),
        "per_call": {
            "input_tokens": input_per_call,
            "output_tokens": output_per_call,
            "embedding_tokens": embedding_per_call,
        },
        "confidence": effective_confidence,
        "confidence_label": CONFIDENCE_LABELS[effective_confidence],
        "history_sample_count": _safe_int(dict(calibration or {}).get("sample_count")),
        "history_calibrated": history_used,
        "assumptions": [str(item) for item in (assumptions or []) if str(item)],
    }


def _provider_is_local(profile: dict) -> bool:
    provider = str(profile.get("provider_type") or "").strip().lower()
    hostname = (urlparse(str(profile.get("base_url") or "")).hostname or "").lower()
    return provider == "ollama" or hostname in {"localhost", "127.0.0.1", "::1"}


def _cost_for_range(tokens: dict[str, int], rate: float) -> dict[str, float]:
    return {key: round(value * rate / 1_000_000, 8) for key, value in tokens.items()}


def _budget_assessment(
    total_tokens: dict,
    cost_range_usd: dict | None,
    cost_range_cny: dict | None,
    profile: dict,
) -> dict:
    display_currency = str(
        cost_display_preferences(profile)["display_currency"]
    )
    warning_tokens = _safe_int(profile.get("preflight_warning_tokens"))
    confirmation_tokens = _safe_int(profile.get("preflight_confirmation_tokens"))
    threshold_suffix = display_currency.lower()
    warning_cost = _safe_float(profile.get(f"preflight_warning_cost_{threshold_suffix}"))
    confirmation_cost = _safe_float(
        profile.get(f"preflight_confirmation_cost_{threshold_suffix}")
    )
    cost_range = cost_range_cny if display_currency == "CNY" else cost_range_usd
    currency_symbol = "¥" if display_currency == "CNY" else "$"
    require_confirmation = bool(profile.get("preflight_require_confirmation", False))

    warning_reasons: list[str] = []
    confirmation_reasons: list[str] = []
    if warning_tokens and total_tokens["high"] >= warning_tokens:
        warning_reasons.append(
            f"Token 上界达到 {total_tokens['high']:,}，超过提醒阈值 {warning_tokens:,}"
        )
    if confirmation_tokens and total_tokens["high"] >= confirmation_tokens:
        confirmation_reasons.append(
            f"Token 上界达到 {total_tokens['high']:,}，超过确认阈值 {confirmation_tokens:,}"
        )
    if cost_range is not None and warning_cost and cost_range["high"] >= warning_cost:
        warning_reasons.append(
            f"费用上界约 {currency_symbol}{cost_range['high']:.4f}，"
            f"超过提醒阈值 {currency_symbol}{warning_cost:.4f}"
        )
    if cost_range is not None and confirmation_cost and cost_range["high"] >= confirmation_cost:
        confirmation_reasons.append(
            f"费用上界约 {currency_symbol}{cost_range['high']:.4f}，"
            f"超过确认阈值 {currency_symbol}{confirmation_cost:.4f}"
        )
    confirmation_required = require_confirmation and bool(confirmation_reasons)
    if confirmation_required:
        status = "confirmation_required"
    elif warning_reasons or confirmation_reasons:
        status = "warning"
    else:
        status = "within_budget"
    return {
        "status": status,
        "warning_reasons": warning_reasons,
        "confirmation_reasons": confirmation_reasons,
        "confirmation_required": confirmation_required,
        "thresholds": {
            "warning_tokens": warning_tokens,
            "confirmation_tokens": confirmation_tokens,
            "warning_cost_usd": _safe_float(
                profile.get("preflight_warning_cost_usd")
            ),
            "confirmation_cost_usd": _safe_float(
                profile.get("preflight_confirmation_cost_usd")
            ),
            "warning_cost_cny": _safe_float(
                profile.get("preflight_warning_cost_cny")
            ),
            "confirmation_cost_cny": _safe_float(
                profile.get("preflight_confirmation_cost_cny")
            ),
            "currency": display_currency,
        },
    }


def build_preflight_estimate(
    stages: list[dict],
    *,
    profile: dict | None = None,
    estimate_kind: str = "llm_workflow",
    external_calls: list[dict] | None = None,
    assumptions: list[str] | None = None,
) -> dict:
    """Aggregate stages into one provider-neutral estimate and price snapshot."""

    clean_stages = [dict(stage) for stage in stages if isinstance(stage, dict)]
    input_range = add_token_ranges(stage.get("input_tokens", {}) for stage in clean_stages)
    output_range = add_token_ranges(stage.get("output_tokens", {}) for stage in clean_stages)
    embedding_range = add_token_ranges(
        stage.get("embedding_tokens", {}) for stage in clean_stages
    )
    total_range = add_token_ranges((input_range, output_range, embedding_range))
    active_profile = dict(profile or {})
    currency_preferences = cost_display_preferences(active_profile)
    pricing_currency = str(currency_preferences["pricing_currency"])
    usd_to_cny_rate = float(currency_preferences["usd_to_cny_rate"])
    tracking_mode = str(active_profile.get("cost_tracking_mode") or "auto").lower()
    input_rate = _safe_float(active_profile.get("input_price_per_million"))
    output_rate = _safe_float(active_profile.get("output_price_per_million"))
    embedding_rate = _safe_float(active_profile.get("embedding_price_per_million"))
    missing: list[str] = []
    local_zero = _provider_is_local(active_profile) and tracking_mode == "auto"
    if not local_zero and tracking_mode != "tokens_only":
        if input_range["high"] and input_rate <= 0:
            missing.append("输入 Token")
        if output_range["high"] and output_rate <= 0:
            missing.append("输出 Token")
        if embedding_range["high"] and embedding_rate <= 0:
            missing.append("Embedding Token")

    pricing_configured = local_zero or (tracking_mode != "tokens_only" and not missing)
    source_cost_range: dict[str, float] | None = None
    if pricing_configured:
        input_cost = _cost_for_range(input_range, input_rate)
        output_cost = _cost_for_range(output_range, output_rate)
        embedding_cost = _cost_for_range(embedding_range, embedding_rate)
        source_cost_range = {
            key: round(input_cost[key] + output_cost[key] + embedding_cost[key], 8)
            for key in ("low", "expected", "high")
        }
    cost_range_usd = convert_cost_range(
        source_cost_range,
        source_currency=pricing_currency,
        target_currency="USD",
        usd_to_cny_rate=usd_to_cny_rate,
    )
    cost_range_cny = convert_cost_range(
        source_cost_range,
        source_currency=pricing_currency,
        target_currency="CNY",
        usd_to_cny_rate=usd_to_cny_rate,
    )

    for stage in clean_stages:
        stage_input = token_range(
            stage.get("input_tokens", {}), low_factor=1.0, high_factor=1.0
        )
        stage_output = token_range(
            stage.get("output_tokens", {}), low_factor=1.0, high_factor=1.0
        )
        stage_embedding = token_range(
            stage.get("embedding_tokens", {}), low_factor=1.0, high_factor=1.0
        )
        if pricing_configured:
            stage_source_cost = {
                key: round(
                    stage_input[key] * input_rate / 1_000_000
                    + stage_output[key] * output_rate / 1_000_000
                    + stage_embedding[key] * embedding_rate / 1_000_000,
                    8,
                )
                for key in ("low", "expected", "high")
            }
            stage["cost_range_usd"] = convert_cost_range(
                stage_source_cost,
                source_currency=pricing_currency,
                target_currency="USD",
                usd_to_cny_rate=usd_to_cny_rate,
            )
            stage["cost_range_cny"] = convert_cost_range(
                stage_source_cost,
                source_currency=pricing_currency,
                target_currency="CNY",
                usd_to_cny_rate=usd_to_cny_rate,
            )
        else:
            stage["cost_range_usd"] = None
            stage["cost_range_cny"] = None

    if clean_stages:
        confidence = min(
            (str(stage.get("confidence") or "medium") for stage in clean_stages),
            key=lambda item: CONFIDENCE_ORDER.get(item, 2),
        )
    else:
        confidence = "low"
    history_samples = max(
        (_safe_int(stage.get("history_sample_count")) for stage in clean_stages),
        default=0,
    )
    model_calls = sum(
        _safe_int(stage.get("call_count"))
        for stage in clean_stages
        if str(stage.get("endpoint_type") or "chat") != "embedding"
    )
    embedding_calls = sum(
        _safe_int(stage.get("call_count"))
        for stage in clean_stages
        if str(stage.get("endpoint_type") or "chat") == "embedding"
    )
    result = {
        "estimate_version": 1,
        "estimate_kind": str(estimate_kind or "llm_workflow"),
        "enabled": bool(active_profile.get("preflight_enabled", True)),
        "profile_id": str(
            active_profile.get("id") or active_profile.get("profile_id") or ""
        ),
        "model_name": str(active_profile.get("model_name") or ""),
        "embedding_model_name": str(active_profile.get("embedding_model_name") or ""),
        "estimated_model_calls": model_calls,
        "estimated_embedding_calls": embedding_calls,
        "input_tokens": input_range,
        "output_tokens": output_range,
        "embedding_tokens": embedding_range,
        "total_tokens": total_range,
        "cost_range_usd": cost_range_usd,
        "cost_range_cny": cost_range_cny,
        "display_currency": currency_preferences["display_currency"],
        "usd_to_cny_rate": usd_to_cny_rate,
        "pricing_configured": pricing_configured,
        "missing_price_components": missing,
        "tracking_mode": tracking_mode,
        "price_snapshot": {
            "currency": pricing_currency,
            "display_currency": currency_preferences["display_currency"],
            "usd_to_cny_rate": usd_to_cny_rate,
            "currency_rate_updated_at": currency_preferences[
                "currency_rate_updated_at"
            ],
            "currency_rate_source_url": currency_preferences[
                "currency_rate_source_url"
            ],
            "input_price_per_million": input_rate,
            "cached_input_price_per_million": _safe_float(
                active_profile.get("cached_input_price_per_million")
            ),
            "cache_write_price_per_million": _safe_float(
                active_profile.get("cache_write_price_per_million")
            ),
            "output_price_per_million": output_rate,
            "embedding_price_per_million": embedding_rate,
            "pricing_updated_at": str(active_profile.get("pricing_updated_at") or ""),
            "pricing_source_url": str(active_profile.get("pricing_source_url") or ""),
        },
        "confidence": confidence,
        "confidence_label": CONFIDENCE_LABELS.get(confidence, "中等"),
        "history_sample_count": history_samples,
        "history_calibrated": any(
            bool(stage.get("history_calibrated")) for stage in clean_stages
        ),
        "stages": clean_stages,
        "external_calls": [
            dict(item) for item in (external_calls or []) if isinstance(item, dict)
        ],
        "assumptions": list(
            dict.fromkeys(
                [str(item) for item in (assumptions or []) if str(item)]
                + [
                    str(item)
                    for stage in clean_stages
                    for item in stage.get("assumptions", [])
                    if str(item)
                ]
            )
        ),
    }
    if input_range["high"] and _safe_float(
        active_profile.get("cached_input_price_per_million")
    ):
        result["assumptions"] = list(
            dict.fromkeys(
                [
                    *result["assumptions"],
                    "执行前无法确定缓存命中量，输入费用按普通输入价格保守估算。",
                ]
            )
        )
    result["budget"] = _budget_assessment(
        total_range, cost_range_usd, cost_range_cny, active_profile
    )
    # Compatibility fields for durable tasks and existing UI/repositories.
    result.update(
        {
            "llm_call_count": model_calls,
            "estimated_input_tokens": input_range["expected"],
            "estimated_output_tokens": output_range["expected"],
            "estimated_embedding_tokens": embedding_range["expected"],
            "estimated_total_tokens": total_range["expected"],
            "estimated_cost_usd": None
            if cost_range_usd is None
            else cost_range_usd["expected"],
            "estimated_cost_cny": None
            if cost_range_cny is None
            else cost_range_cny["expected"],
        }
    )
    return result
