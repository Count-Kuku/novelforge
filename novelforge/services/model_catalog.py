"""OpenAI-compatible model discovery with best-effort capability annotation.

Model capabilities (context length / multimodal / native web search) are
best-effort heuristics keyed on the model id and the configured endpoint:
the standard ``GET {base}/models`` response only carries ids, so per-model
metadata here is a conservative default + prefix table. Unknown models keep
sane defaults and are flagged accordingly, never blocking usage.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import httpx

from novelforge.core.llm_usage import detect_provider

# Id-prefix -> context window (tokens). Conservative floor defaults apply.
_CONTEXT_TABLE: list[tuple[str, int]] = [
    ("deepseek", 65536),
    ("claude", 200000),
    ("gemini", 1000000),
    ("glm", 128000),
    ("kimi", 128000),
    ("moonshot", 128000),
    ("ernie", 128000),
    ("gpt", 128000),
    ("o1", 128000),
    ("o3", 128000),
    ("qwen", 32768),
    ("llama", 32768),
    ("mixtral", 32768),
    ("mistral", 32768),
    ("yi-", 32768),
]
DEFAULT_CONTEXT_WINDOW = 32768

_MULTIMODAL_TOKENS = (
    "vision", "-vl", "omni", "llava", "pixtral", "gemini",
    "gpt-4o", "gpt-4.1", "gpt-5", "gpt-4-turbo", "claude-3-5", "claude-3-opus",
    "qwen2.5-vl", "qwen2-vl", "glm-4v", "glm-5v", "internvl", "cogvlm",
)

NATIVE_SEARCH_HOSTS = ("deepseek.com", "openrouter.ai", "openai.com", "dashscope")


def _models_url_candidates(base_url: str) -> list[str]:
    cleaned = str(base_url or "").strip().rstrip("/")
    if not cleaned:
        return []
    if cleaned.endswith("/v1"):
        return [f"{cleaned}/models"]
    return [f"{cleaned}/models", f"{cleaned}/v1/models"]


def _annotate_model(model_id: str, *, provider_hint: str, host: str) -> dict[str, Any]:
    lowered = str(model_id or "").lower()
    context_window = DEFAULT_CONTEXT_WINDOW
    for prefix, size in _CONTEXT_TABLE:
        if lowered.startswith(prefix):
            context_window = size
            break
    multimodal = any(token in lowered for token in _MULTIMODAL_TOKENS)
    native_web_search = provider_hint in {
        "deepseek", "openai", "qwen", "openrouter",
    } and any(host.endswith(domain) for domain in NATIVE_SEARCH_HOSTS)
    return {
        "id": str(model_id or ""),
        "context_window": context_window,
        "multimodal": multimodal,
        "native_web_search": native_web_search,
        "provider_hint": provider_hint,
    }


def discover_openai_compatible_models(
    base_url: str,
    api_key: str = "",
    *,
    provider_type: str = "auto",
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Call ``GET {base}/models`` and return annotated rows.

    Raises a RuntimeError with a user-facing message when the endpoint is
    unreachable or does not implement the standard models listing.
    """
    cleaned_base = str(base_url or "").strip()
    if not cleaned_base:
        raise RuntimeError("请先填写 Base URL。")
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    parsed = urlsplit(cleaned_base)
    host = (parsed.hostname or "").lower()
    provider_hint = detect_provider({
        "provider_type": provider_type,
        "base_url": cleaned_base,
    })
    last_error: Exception | None = None
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for url in _models_url_candidates(cleaned_base):
            try:
                response = client.get(url, headers=headers)
            except Exception as exc:  # network level: try next candidate
                last_error = exc
                continue
            if response.status_code == 404:
                last_error = RuntimeError("该服务未实现模型列表接口（GET /models 返回 404）")
                continue
            if response.status_code in (401, 403):
                raise RuntimeError("API Key 无效或无权限访问模型列表（HTTP %s）。" % response.status_code)
            if response.status_code != 200:
                last_error = RuntimeError("模型列表请求失败：HTTP %s" % response.status_code)
                continue
            try:
                payload = response.json()
            except Exception:
                raise RuntimeError("模型列表返回的不是 JSON。")
            raw_models = payload.get("data") or payload.get("models") or []
            rows = [
                _annotate_model(
                    str(item.get("id") or "") if isinstance(item, dict) else str(item),
                    provider_hint=provider_hint,
                    host=host,
                )
                for item in raw_models
            ]
            rows = [row for row in rows if row["id"]]
            if not rows:
                raise RuntimeError("模型列表为空（该服务没有返回可用模型）。")
            return {
                "base_url": cleaned_base,
                "provider_hint": provider_hint,
                "models": sorted(rows, key=lambda row: row["id"]),
            }
    raise RuntimeError(f"无法获取模型列表：{last_error or '未知错误'}")
