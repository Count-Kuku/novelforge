from __future__ import annotations

import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.services.memory.core import _normalize_llm_profile
from novelforge.core.cost_currency import DEFAULT_USD_TO_CNY_RATE, convert_cost


def main() -> None:
    profile = _normalize_llm_profile(
        {
            "input_price_per_million": float("nan"),
            "cached_input_price_per_million": float("inf"),
            "cache_write_price_per_million": float("-inf"),
            "output_price_per_million": float("inf"),
            "embedding_price_per_million": float("-inf"),
            "preflight_warning_tokens": float("inf"),
            "preflight_confirmation_tokens": -100,
            "preflight_warning_cost_usd": float("nan"),
            "preflight_confirmation_cost_usd": float("-inf"),
            "preflight_warning_cost_cny": float("nan"),
            "preflight_confirmation_cost_cny": float("inf"),
            "pricing_currency": "EUR",
            "display_currency": "GBP",
            "usd_to_cny_rate": float("inf"),
            "provider_type": "invented-provider",
            "cost_tracking_mode": "free-money",
        },
        "pricing-test",
    )
    rates = [
        profile["input_price_per_million"],
        profile["cached_input_price_per_million"],
        profile["cache_write_price_per_million"],
        profile["output_price_per_million"],
        profile["embedding_price_per_million"],
    ]
    assert rates == [0.0, 0.0, 0.0, 0.0, 0.0]
    assert all(math.isfinite(value) for value in rates)
    assert profile["provider_type"] == "auto"
    assert profile["cost_tracking_mode"] == "auto"
    assert profile["preflight_warning_tokens"] == 0
    assert profile["preflight_confirmation_tokens"] == 0
    assert profile["preflight_warning_cost_usd"] == 0
    assert profile["preflight_confirmation_cost_usd"] == 0
    assert profile["preflight_warning_cost_cny"] == 0
    assert profile["preflight_confirmation_cost_cny"] == 0
    assert profile["pricing_currency"] == "USD"
    assert profile["display_currency"] == "CNY"
    assert profile["usd_to_cny_rate"] == DEFAULT_USD_TO_CNY_RATE
    defaults = _normalize_llm_profile({}, "defaults")
    assert defaults["preflight_enabled"] is True
    assert defaults["preflight_warning_tokens"] == 50000
    assert defaults["preflight_confirmation_tokens"] == 150000
    assert defaults["preflight_require_confirmation"] is False
    assert defaults["display_currency"] == "CNY"
    assert defaults["pricing_currency"] == "USD"
    assert convert_cost(
        1, source_currency="USD", target_currency="CNY", usd_to_cny_rate=7.2
    ) == 7.2
    print("Pricing normalization verification passed: 21 checks")


if __name__ == "__main__":
    main()
