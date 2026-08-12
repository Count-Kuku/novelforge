"""Versioned provider presets, model discovery and capability negotiation."""

from __future__ import annotations

from dataclasses import dataclass


PROVIDER_PRESET_VERSION = "2026.08"


@dataclass(frozen=True, slots=True)
class ProviderAdapter:
    provider_type: str
    capabilities: tuple[str, ...]
    discovery: str = "openai_models"
    notes: str = ""


PROVIDER_ADAPTERS = {
    "deepseek": ProviderAdapter("deepseek", ("chat",), notes="当前预设仅声明对话能力。"),
    "openai": ProviderAdapter("openai", ("chat", "embedding")),
    "openrouter": ProviderAdapter("openrouter", ("chat",)),
    "qwen": ProviderAdapter("qwen", ("chat", "embedding")),
    "siliconflow": ProviderAdapter("siliconflow", ("chat", "embedding")),
    "ollama": ProviderAdapter("ollama", ("chat", "embedding")),
    "openai_compatible": ProviderAdapter("openai_compatible", ("chat", "embedding")),
    "auto": ProviderAdapter("auto", ("chat", "embedding")),
}


def get_versioned_provider_presets() -> dict:
    # Local import keeps the compatibility constant in novelforge.core.llm
    # while exposing a versioned adapter API to new workflows.
    from novelforge.core.llm import PROVIDER_PRESETS

    return {
        "version": PROVIDER_PRESET_VERSION,
        "presets": {name: dict(value) for name, value in PROVIDER_PRESETS.items()},
    }


def discover_provider_models(
    *,
    base_url: str,
    api_key: str,
    provider_type: str = "auto",
) -> dict:
    """Discover model IDs through an OpenAI-compatible ``/models`` endpoint."""

    if not str(base_url or "").strip() or not str(api_key or "").strip():
        raise ValueError("发现模型前需要服务网址和 API Key。")
    from openai import OpenAI

    client = OpenAI(api_key=api_key.strip(), base_url=base_url.strip())
    response = client.models.list()
    model_ids = sorted({str(item.id).strip() for item in response.data if str(item.id).strip()})
    adapter = PROVIDER_ADAPTERS.get(
        str(provider_type or "auto").strip().lower(), PROVIDER_ADAPTERS["auto"]
    )
    return {
        "provider_type": adapter.provider_type,
        "preset_version": PROVIDER_PRESET_VERSION,
        "models": model_ids,
        "declared_capabilities": list(adapter.capabilities),
    }


def capability_invalidation_hints(
    *, chat_status: str, chat_message: str, embedding_status: str, embedding_message: str,
) -> list[dict]:
    hints: list[dict] = []
    combined = f"{chat_message} {embedding_message}".lower()
    if "401" in combined or "unauthorized" in combined or "密钥" in combined:
        hints.append({"trigger": "credential_changed", "message": "密钥变更后需重新验证能力。"})
    if "404" in combined or "模型" in combined:
        hints.append({"trigger": "model_changed", "message": "模型名或供应商预设变更后需重新验证。"})
    if chat_status != "ready" or embedding_status == "failed":
        hints.append({"trigger": "endpoint_changed", "message": "服务网址变更后需重新验证。"})
    return hints


def negotiate_provider_capabilities(
    *,
    provider_type: str,
    chat_status: str,
    embedding_status: str,
) -> dict:
    adapter = PROVIDER_ADAPTERS.get(
        str(provider_type or "auto").strip().lower(), PROVIDER_ADAPTERS["auto"]
    )
    return {
        "provider_type": adapter.provider_type,
        "preset_version": PROVIDER_PRESET_VERSION,
        "declared": list(adapter.capabilities),
        "available": [
            capability
            for capability, ready in (
                ("chat", chat_status == "ready"),
                ("embedding", embedding_status == "ready"),
            )
            if ready
        ],
    }

