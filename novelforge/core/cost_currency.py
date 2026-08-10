"""Currency normalization and conversion for LLM cost display and pricing."""
from __future__ import annotations

import math


SUPPORTED_COST_CURRENCIES = {"CNY", "USD"}
DEFAULT_DISPLAY_CURRENCY = "CNY"
DEFAULT_PRICING_CURRENCY = "USD"
# DeepSeek's 2026-08-10 v4-flash CNY/USD price tables imply this display factor.
DEFAULT_USD_TO_CNY_RATE = 7.142857


def normalize_cost_currency(value: object, *, default: str = DEFAULT_PRICING_CURRENCY) -> str:
    normalized_default = str(default or DEFAULT_PRICING_CURRENCY).strip().upper()
    if normalized_default not in SUPPORTED_COST_CURRENCIES:
        normalized_default = DEFAULT_PRICING_CURRENCY
    currency = str(value or "").strip().upper()
    return currency if currency in SUPPORTED_COST_CURRENCIES else normalized_default


def normalize_usd_to_cny_rate(value: object) -> float:
    try:
        rate = float(value)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_USD_TO_CNY_RATE
    if not math.isfinite(rate) or rate <= 0:
        return DEFAULT_USD_TO_CNY_RATE
    return rate


def convert_cost(
    value: int | float,
    *,
    source_currency: str,
    target_currency: str,
    usd_to_cny_rate: object = DEFAULT_USD_TO_CNY_RATE,
) -> float:
    """Convert a non-negative cost between the supported ledger currencies."""

    amount = max(float(value or 0), 0.0)
    source = normalize_cost_currency(source_currency)
    target = normalize_cost_currency(target_currency)
    if source == target:
        return amount
    rate = normalize_usd_to_cny_rate(usd_to_cny_rate)
    if source == "USD" and target == "CNY":
        return amount * rate
    return amount / rate


def convert_cost_range(
    value: dict | None,
    *,
    source_currency: str,
    target_currency: str,
    usd_to_cny_rate: object = DEFAULT_USD_TO_CNY_RATE,
) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    return {
        key: round(
            convert_cost(
                value.get(key, value.get("expected", 0)),
                source_currency=source_currency,
                target_currency=target_currency,
                usd_to_cny_rate=usd_to_cny_rate,
            ),
            8,
        )
        for key in ("low", "expected", "high")
    }


def cost_display_preferences(profile: dict | None) -> dict[str, object]:
    raw = dict(profile or {})
    return {
        "display_currency": normalize_cost_currency(
            raw.get("display_currency"), default=DEFAULT_DISPLAY_CURRENCY
        ),
        "pricing_currency": normalize_cost_currency(raw.get("pricing_currency")),
        "usd_to_cny_rate": normalize_usd_to_cny_rate(raw.get("usd_to_cny_rate")),
        "currency_rate_updated_at": str(raw.get("currency_rate_updated_at") or "").strip(),
        "currency_rate_source_url": str(raw.get("currency_rate_source_url") or "").strip(),
    }
