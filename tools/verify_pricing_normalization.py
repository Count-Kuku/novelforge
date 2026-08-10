from __future__ import annotations

import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.services.memory.core import _normalize_llm_profile


def main() -> None:
    profile = _normalize_llm_profile(
        {
            "input_price_per_million": float("nan"),
            "cached_input_price_per_million": float("inf"),
            "cache_write_price_per_million": float("-inf"),
            "output_price_per_million": float("inf"),
            "embedding_price_per_million": float("-inf"),
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
    print("Pricing normalization verification passed: 4 checks")


if __name__ == "__main__":
    main()
