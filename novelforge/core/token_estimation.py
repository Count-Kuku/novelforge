"""Deterministic, provider-neutral Token estimation helpers."""
from __future__ import annotations

import math


def estimate_text_tokens(text: object) -> int:
    """Estimate mixed CJK/Latin text without a provider tokenizer dependency."""

    content = str(text or "")
    if not content:
        return 0
    cjk_count = sum(1 for char in content if "\u3400" <= char <= "\u9fff")
    non_cjk_count = len(content) - cjk_count
    return max(1, math.ceil(cjk_count / 1.6 + non_cjk_count / 4.0))


def estimate_chat_input_tokens(
    prompt: object,
    *,
    system_message: object = "",
    message_count: int = 1,
) -> int:
    """Estimate chat input including small role/message framing overhead."""

    content_tokens = estimate_text_tokens(prompt) + estimate_text_tokens(system_message)
    framing_tokens = max(int(message_count), 1) * 6 + (4 if system_message else 0)
    return content_tokens + framing_tokens
