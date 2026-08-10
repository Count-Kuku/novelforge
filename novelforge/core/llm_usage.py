"""Provider-neutral LLM usage normalization, attribution, and cost snapshots."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterator
from urllib.parse import urlparse
from uuid import uuid4

from novelforge.core.cost_currency import (
    cost_display_preferences,
    normalize_cost_currency,
    normalize_usd_to_cny_rate,
)
from novelforge.core.token_estimation import estimate_text_tokens


LOGGER = logging.getLogger("novelforge.llm_usage")
_USAGE_CONTEXT: ContextVar[dict[str, Any]] = ContextVar("novelforge_llm_usage_context", default={})


def _clean_context_value(value: object) -> str:
    return str(value or "").strip()


def current_llm_usage_context() -> dict[str, Any]:
    return dict(_USAGE_CONTEXT.get())


@contextmanager
def llm_usage_scope(**values: object) -> Iterator[dict[str, Any]]:
    """Merge attribution into the current execution context.

    Child scopes inherit task and operation IDs while remaining free to refine
    the operation or agent role. ContextVars keep concurrent threads/tasks from
    sharing mutable attribution state.
    """

    merged = current_llm_usage_context()
    for key, value in values.items():
        if key == "metadata" and isinstance(value, dict):
            merged[key] = {**dict(merged.get(key) or {}), **value}
            continue
        clean = _clean_context_value(value)
        if clean:
            merged[str(key)] = clean
    if merged.get("operation") and not merged.get("operation_id"):
        merged["operation_id"] = f"op_{uuid4().hex}"
    token = _USAGE_CONTEXT.set(merged)
    try:
        yield dict(merged)
    finally:
        _USAGE_CONTEXT.reset(token)


def detect_provider(profile: dict | None) -> str:
    raw = dict(profile or {})
    explicit = str(raw.get("provider_type") or "auto").strip().lower()
    if explicit and explicit != "auto":
        return explicit
    host = (urlparse(str(raw.get("base_url") or "")).hostname or "").lower()
    if host.endswith("deepseek.com"):
        return "deepseek"
    if host.endswith("openrouter.ai"):
        return "openrouter"
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return "ollama"
    if host.endswith("openai.com"):
        return "openai"
    if "dashscope" in host:
        return "qwen"
    if "siliconflow" in host:
        return "siliconflow"
    return "openai_compatible"


def _as_mapping(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    result: dict[str, Any] = {}
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "input_tokens",
        "output_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
        "prompt_tokens_details",
        "input_tokens_details",
        "completion_tokens_details",
        "output_tokens_details",
        "cost",
        "cost_details",
    ):
        if hasattr(value, key):
            result[key] = getattr(value, key)
    return result


def _nonnegative_int(value: object) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(number, 0)


def _safe_decimal(value: object) -> Decimal:
    try:
        number = Decimal(str(value or 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)
    if not number.is_finite() or number < 0:
        return Decimal(0)
    return number


def _estimate_tokens(text: str) -> int:
    return estimate_text_tokens(text)


def normalize_usage(
    usage: object,
    *,
    endpoint_type: str,
    input_text: str = "",
    output_text: str = "",
) -> dict:
    raw = _as_mapping(usage)
    prompt_details = _as_mapping(raw.get("prompt_tokens_details") or raw.get("input_tokens_details"))
    completion_details = _as_mapping(
        raw.get("completion_tokens_details") or raw.get("output_tokens_details")
    )
    endpoint = str(endpoint_type or "chat")
    usage_present = bool(raw)

    input_tokens = _nonnegative_int(raw.get("prompt_tokens", raw.get("input_tokens")))
    output_tokens = _nonnegative_int(raw.get("completion_tokens", raw.get("output_tokens")))
    cached_input_tokens = _nonnegative_int(
        raw.get(
            "prompt_cache_hit_tokens",
            prompt_details.get("cached_tokens", prompt_details.get("cache_read_tokens")),
        )
    )
    cache_write_tokens = _nonnegative_int(
        prompt_details.get("cache_write_tokens", raw.get("input_cache_write_tokens"))
    )
    reasoning_tokens = _nonnegative_int(completion_details.get("reasoning_tokens"))
    total_tokens = _nonnegative_int(raw.get("total_tokens"))

    if endpoint == "embedding":
        embedding_tokens = input_tokens or total_tokens
        if not embedding_tokens:
            embedding_tokens = _estimate_tokens(input_text)
            usage_present = False
        input_tokens = 0
        output_tokens = 0
        cached_input_tokens = 0
        cache_write_tokens = 0
        total_tokens = embedding_tokens
    else:
        embedding_tokens = 0
        if not input_tokens:
            input_tokens = _estimate_tokens(input_text)
            usage_present = False
        if not output_tokens and output_text:
            output_tokens = _estimate_tokens(output_text)
            usage_present = False
        if not total_tokens:
            total_tokens = input_tokens + output_tokens

    provider_cost = raw.get("cost")
    provider_cost_decimal = None
    if provider_cost is not None:
        parsed_cost = _safe_decimal(provider_cost)
        provider_cost_decimal = parsed_cost

    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": min(cached_input_tokens, input_tokens),
        "cache_write_tokens": min(cache_write_tokens, input_tokens),
        "output_tokens": output_tokens,
        "reasoning_tokens": min(reasoning_tokens, output_tokens),
        "embedding_tokens": embedding_tokens,
        "total_tokens": total_tokens,
        "usage_status": "exact" if usage_present else "estimated",
        "provider_cost": provider_cost_decimal,
        "raw_usage": raw,
    }


def _rate_snapshot(profile: dict) -> dict[str, object]:
    preferences = cost_display_preferences(profile)
    return {
        "currency": preferences["pricing_currency"],
        "display_currency": preferences["display_currency"],
        "usd_to_cny_rate": preferences["usd_to_cny_rate"],
        "currency_rate_updated_at": preferences["currency_rate_updated_at"],
        "currency_rate_source_url": preferences["currency_rate_source_url"],
        "input_price_per_million": float(_safe_decimal(profile.get("input_price_per_million"))),
        "cached_input_price_per_million": float(
            _safe_decimal(profile.get("cached_input_price_per_million"))
        ),
        "cache_write_price_per_million": float(
            _safe_decimal(profile.get("cache_write_price_per_million"))
        ),
        "output_price_per_million": float(_safe_decimal(profile.get("output_price_per_million"))),
        "embedding_price_per_million": float(
            _safe_decimal(profile.get("embedding_price_per_million"))
        ),
        "pricing_updated_at": str(profile.get("pricing_updated_at") or ""),
        "pricing_source_url": str(profile.get("pricing_source_url") or ""),
    }


def _decimal_to_microusd(value: Decimal | None) -> int | None:
    if value is None:
        return None
    return int((value * Decimal(1_000_000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_configured_cost_microusd(usage: dict, profile: dict) -> int | None:
    input_rate = _safe_decimal(profile.get("input_price_per_million"))
    cached_rate = _safe_decimal(profile.get("cached_input_price_per_million"))
    cache_write_rate = _safe_decimal(profile.get("cache_write_price_per_million"))
    output_rate = _safe_decimal(profile.get("output_price_per_million"))
    embedding_rate = _safe_decimal(profile.get("embedding_price_per_million"))

    embedding_tokens = _nonnegative_int(usage.get("embedding_tokens"))
    if embedding_tokens:
        if embedding_rate <= 0:
            return None
        cost_microprice = Decimal(embedding_tokens) * embedding_rate
        if normalize_cost_currency(profile.get("pricing_currency")) == "CNY":
            cost_microprice /= Decimal(
                str(normalize_usd_to_cny_rate(profile.get("usd_to_cny_rate")))
            )
        return int(cost_microprice.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    input_tokens = _nonnegative_int(usage.get("input_tokens"))
    cached_tokens = min(_nonnegative_int(usage.get("cached_input_tokens")), input_tokens)
    cache_write_tokens = min(
        _nonnegative_int(usage.get("cache_write_tokens")),
        max(input_tokens - cached_tokens, 0),
    )
    uncached_tokens = max(input_tokens - cached_tokens - cache_write_tokens, 0)
    output_tokens = _nonnegative_int(usage.get("output_tokens"))

    if uncached_tokens and input_rate <= 0:
        return None
    if cached_tokens and cached_rate <= 0:
        cached_rate = input_rate
    if cache_write_tokens and cache_write_rate <= 0:
        cache_write_rate = input_rate
    if cached_tokens and cached_rate <= 0:
        return None
    if cache_write_tokens and cache_write_rate <= 0:
        return None
    if output_tokens and output_rate <= 0:
        return None

    cost_microprice = (
        Decimal(uncached_tokens) * input_rate
        + Decimal(cached_tokens) * cached_rate
        + Decimal(cache_write_tokens) * cache_write_rate
        + Decimal(output_tokens) * output_rate
    )
    if cost_microprice <= 0 and (input_tokens or output_tokens):
        return None
    if normalize_cost_currency(profile.get("pricing_currency")) == "CNY":
        cost_microprice /= Decimal(
            str(normalize_usd_to_cny_rate(profile.get("usd_to_cny_rate")))
        )
    return int(cost_microprice.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build_llm_usage_event(
    *,
    usage: object,
    profile: dict,
    endpoint_type: str,
    requested_model: str,
    reported_model: str = "",
    provider_request_id: str = "",
    input_text: str = "",
    output_text: str = "",
    context: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    normalized = normalize_usage(
        usage,
        endpoint_type=endpoint_type,
        input_text=input_text,
        output_text=output_text,
    )
    active_context = current_llm_usage_context()
    if isinstance(context, dict):
        active_context.update({str(key): _clean_context_value(value) for key, value in context.items() if value})
    provider = detect_provider(profile)
    tracking_mode = str(profile.get("cost_tracking_mode") or "auto").strip().lower()
    provider_cost_microusd = _decimal_to_microusd(normalized.pop("provider_cost"))
    calculated_cost_microusd = calculate_configured_cost_microusd(normalized, profile)

    cost_microusd: int | None = None
    cost_source = "tokens_only" if tracking_mode == "tokens_only" else "unpriced"
    if tracking_mode != "tokens_only":
        if provider_cost_microusd is not None and (
            tracking_mode == "provider_reported" or (tracking_mode == "auto" and provider == "openrouter")
        ):
            cost_microusd = provider_cost_microusd
            cost_source = "provider_reported"
        elif tracking_mode in {"auto", "manual"} and calculated_cost_microusd is not None:
            cost_microusd = calculated_cost_microusd
            cost_source = "configured_rates"
    if provider == "ollama" and tracking_mode == "auto":
        cost_microusd = 0
        cost_source = "local_zero"

    event_metadata = dict(active_context.get("metadata") or {})
    event_metadata.update(dict(metadata or {}))
    event_metadata.setdefault("cost_tracking_mode", tracking_mode)
    event_metadata.setdefault("usage_payload_available", normalized["usage_status"] == "exact")
    return {
        "event_id": f"usage_{uuid4().hex}",
        "provider_request_id": str(provider_request_id or ""),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "project_name": active_context.get("project_name", ""),
        "story_id": active_context.get("story_id", ""),
        "workflow_run_id": active_context.get("workflow_run_id", ""),
        "task_id": active_context.get("task_id", ""),
        "operation_id": active_context.get("operation_id", ""),
        "operation": active_context.get("operation", "unattributed") or "unattributed",
        "agent_role": active_context.get("agent_role", ""),
        "profile_id": str(profile.get("profile_id") or profile.get("id") or ""),
        "provider": provider,
        "endpoint_type": str(endpoint_type or "chat"),
        "requested_model": str(requested_model or ""),
        "reported_model": str(reported_model or requested_model or ""),
        **{key: value for key, value in normalized.items() if key != "raw_usage"},
        "cost_microusd": cost_microusd,
        "provider_cost_microusd": provider_cost_microusd,
        "calculated_cost_microusd": calculated_cost_microusd,
        "cost_source": cost_source,
        "price_snapshot": _rate_snapshot(profile),
        "metadata": event_metadata,
    }


def persist_llm_usage_event(event: dict) -> bool:
    """Persist best-effort; observability must never break generation."""

    try:
        from novelforge.services.llm_usage import record_llm_usage_event

        return bool(record_llm_usage_event(event))
    except Exception as exc:
        LOGGER.warning("Failed to persist LLM usage event: %s", exc, exc_info=True)
        return False
