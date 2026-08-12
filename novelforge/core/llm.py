from __future__ import annotations

import functools

import logging
import math
import os
from collections.abc import Callable
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from novelforge.services.memory import load_llm_settings
from novelforge.core.llm_usage import build_llm_usage_event, persist_llm_usage_event

load_dotenv()

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"
LOGGER = logging.getLogger("novelforge.llm")

APIConnectionError = None
APIStatusError = None
APITimeoutError = None
AuthenticationError = None
BadRequestError = None
NotFoundError = None
OpenAI = None
PermissionDeniedError = None
RateLimitError = None


class _InvalidLLMResponseError(RuntimeError):
    """模型服务成功响应，但响应体不满足调用方契约。"""


def _require_openai():
    global APIConnectionError
    global APIStatusError
    global APITimeoutError
    global AuthenticationError
    global BadRequestError
    global NotFoundError
    global OpenAI
    global PermissionDeniedError
    global RateLimitError

    if OpenAI is not None:
        return OpenAI
    try:
        from openai import (  # type: ignore[import-not-found]
            APIConnectionError as ImportedAPIConnectionError,
            APIStatusError as ImportedAPIStatusError,
            APITimeoutError as ImportedAPITimeoutError,
            AuthenticationError as ImportedAuthenticationError,
            BadRequestError as ImportedBadRequestError,
            NotFoundError as ImportedNotFoundError,
            OpenAI as ImportedOpenAI,
            PermissionDeniedError as ImportedPermissionDeniedError,
            RateLimitError as ImportedRateLimitError,
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError("模型功能不可用：缺少 openai 依赖。请先安装 requirements.txt 中的依赖。") from exc

    APIConnectionError = ImportedAPIConnectionError
    APIStatusError = ImportedAPIStatusError
    APITimeoutError = ImportedAPITimeoutError
    AuthenticationError = ImportedAuthenticationError
    BadRequestError = ImportedBadRequestError
    NotFoundError = ImportedNotFoundError
    OpenAI = ImportedOpenAI
    PermissionDeniedError = ImportedPermissionDeniedError
    RateLimitError = ImportedRateLimitError
    return OpenAI


def _is_openai_error(exc: Exception, error_type) -> bool:
    return error_type is not None and isinstance(exc, error_type)


def _get_api_key() -> str:
    return load_llm_settings().get("api_key", "")


def _get_base_url() -> str:
    return load_llm_settings().get("base_url", DEFAULT_BASE_URL)


def _get_model_name() -> str:
    return load_llm_settings().get("model_name", DEFAULT_MODEL)


def _get_embedding_model_name() -> str:
    settings = load_llm_settings()
    if str(settings.get("embedding_mode") or "disabled") == "disabled":
        return ""
    if str(settings.get("embedding_status") or "unverified") != "ready":
        return ""
    return str(settings.get("embedding_model_name") or "")


def _get_embedding_client_config() -> tuple[str, str]:
    settings = load_llm_settings()
    mode = str(settings.get("embedding_mode") or "disabled")
    if mode == "disabled":
        raise RuntimeError("向量生成已关闭；当前资料检索使用关键词模式。")
    if str(settings.get("embedding_status") or "unverified") != "ready":
        raise RuntimeError("向量服务尚未验证可用；当前资料检索使用关键词模式。")
    if mode in {"separate_provider", "local"}:
        api_key = str(settings.get("embedding_api_key") or "").strip()
        base_url = str(settings.get("embedding_base_url") or "").strip()
        if mode == "local" and not api_key:
            api_key = "local"
    else:
        api_key = str(settings.get("api_key") or "").strip()
        base_url = str(settings.get("base_url") or "").strip()
    if not api_key or not base_url:
        raise RuntimeError("向量服务配置不完整；当前资料检索使用关键词模式。")
    return api_key, base_url


def _should_trust_env_proxy() -> bool:
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]
    for key in proxy_keys:
        value = os.environ.get(key, "")
        if not value:
            continue
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if host in {"127.0.0.1", "localhost"} and parsed.port == 9:
            return False
    return True


@functools.lru_cache(maxsize=8)
def _get_client_for_config(api_key: str, base_url: str, trust_env_proxy: bool):
    openai_client_class = _require_openai()
    return openai_client_class(
        api_key=api_key,
        base_url=base_url,
        http_client=httpx.Client(trust_env=trust_env_proxy),
    )


def clear_llm_client_cache():
    _get_client_for_config.cache_clear()


def _get_client():
    return _get_client_for_config(
        _get_api_key(),
        _get_base_url(),
        _should_trust_env_proxy(),
    )


def _record_model_usage(
    response_or_chunk,
    *,
    usage=None,
    profile: dict,
    endpoint_type: str,
    requested_model: str,
    input_text: str,
    output_text: str = "",
) -> None:
    event = build_llm_usage_event(
        usage=usage if usage is not None else getattr(response_or_chunk, "usage", None),
        profile=profile,
        endpoint_type=endpoint_type,
        requested_model=requested_model,
        reported_model=str(getattr(response_or_chunk, "model", "") or requested_model),
        provider_request_id=str(getattr(response_or_chunk, "id", "") or ""),
        input_text=input_text,
        output_text=output_text,
    )
    persist_llm_usage_event(event)


def _stream_usage_option_rejected(exc: Exception) -> bool:
    message = str(exc or "").lower()
    markers = ("stream_options", "include_usage", "unknown field", "extra inputs")
    return any(marker in message for marker in markers)

DEFAULT_TEMPERATURE = 0.7


def _format_llm_error(
    exc: Exception,
    *,
    action: str = "模型请求",
    base_url: str | None = None,
    model_name: str | None = None,
) -> str:
    base_url = base_url or _get_base_url()
    model_name = model_name or _get_model_name()
    if _is_openai_error(exc, APIConnectionError):
        return (
            f"{action}失败：无法连接到模型服务。"
            f"请检查服务地址 `{base_url}` 是否可访问、网络/代理是否正常，或服务商当前是否可用。"
        )
    if _is_openai_error(exc, APITimeoutError):
        return f"{action}失败：模型服务响应超时。可以稍后重试，或减少单次处理片段数量。"
    if _is_openai_error(exc, AuthenticationError):
        return f"{action}失败：接口密钥无效或已过期。请在模型配置里重新填写 API Key。"
    if _is_openai_error(exc, PermissionDeniedError):
        return f"{action}失败：当前密钥没有访问该模型或接口的权限。"
    if _is_openai_error(exc, NotFoundError):
        return f"{action}失败：模型或接口不存在。请检查模型名 `{model_name}` 和服务地址 `{base_url}`。"
    if _is_openai_error(exc, BadRequestError):
        return f"{action}失败：请求参数不被模型服务接受。请检查模型名 `{model_name}`、上下文长度和服务地址。"
    if _is_openai_error(exc, RateLimitError):
        return f"{action}失败：请求过于频繁或额度不足。请稍后重试，或降低批量提取数量。"
    if _is_openai_error(exc, APIStatusError):
        return f"{action}失败：模型服务返回 HTTP {exc.status_code}。请检查服务商状态、模型名和账号额度。"
    return f"{action}失败（{type(exc).__name__}）：{exc}"


def _emit_stream_delta(stream_callback: Callable[[str], None], content: str) -> None:
    try:
        stream_callback(content)
    except Exception as exc:
        if getattr(exc, "cancel_generation", False):
            raise
        LOGGER.warning("Stream callback failed; model request will continue: %s", exc, exc_info=True)


def _validate_chat_content(content, *, action: str = "模型请求") -> str:
    if not isinstance(content, str):
        raise _InvalidLLMResponseError(f"{action}失败：模型服务返回了非文本内容。")
    if not content.strip():
        raise _InvalidLLMResponseError(f"{action}失败：模型服务返回了空响应。")
    return content


def _extract_chat_content(response) -> str:
    choices = getattr(response, "choices", None)
    if not choices:
        raise _InvalidLLMResponseError("模型请求失败：模型服务没有返回任何候选结果。")

    try:
        first_choice = choices[0]
    except (KeyError, TypeError, IndexError) as exc:
        raise _InvalidLLMResponseError("模型请求失败：模型服务返回的候选结果格式无效。") from exc
    message = getattr(first_choice, "message", None)
    if message is None:
        raise _InvalidLLMResponseError("模型请求失败：模型服务返回的候选结果缺少消息内容。")
    return _validate_chat_content(getattr(message, "content", None))


def _extract_embedding(response) -> list[float]:
    data = getattr(response, "data", None)
    if not data:
        raise RuntimeError("向量生成失败：模型服务没有返回向量数据。")

    try:
        first_item = data[0]
    except (KeyError, TypeError, IndexError) as exc:
        raise RuntimeError("向量生成失败：模型服务返回的向量数据格式无效。") from exc
    embedding = getattr(first_item, "embedding", None)
    if not isinstance(embedding, (list, tuple)) or not embedding:
        raise RuntimeError("向量生成失败：模型服务返回了空向量。")

    normalized = []
    for value in embedding:
        if isinstance(value, bool):
            raise RuntimeError("向量生成失败：模型服务返回的向量包含非数值元素。")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("向量生成失败：模型服务返回的向量包含非数值元素。") from exc
        if not math.isfinite(number):
            raise RuntimeError("向量生成失败：模型服务返回的向量包含非有限数值。")
        normalized.append(number)
    return normalized


def call_llm(
    prompt: str,
    system_message: str = "",
    temperature: float = DEFAULT_TEMPERATURE,
    stream_callback: Callable[[str], None] | None = None,
):
    profile = load_llm_settings()
    if not _get_api_key():
        raise RuntimeError("模型请求失败：接口密钥为空。请先在“模型配置”里填写 API Key。")
    _require_openai()

    requested_model = str(_get_model_name() or DEFAULT_MODEL)

    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": prompt})

    fallback_to_non_streaming = False
    try:
        if stream_callback:
            try:
                try:
                    chunks = _get_client().chat.completions.create(
                        model=requested_model,
                        messages=messages,
                        temperature=temperature,
                        stream=True,
                        stream_options={"include_usage": True},
                    )
                except Exception as exc:
                    if not _stream_usage_option_rejected(exc):
                        raise
                    LOGGER.info("Streaming usage option is unsupported; retrying without it: %s", exc)
                    chunks = _get_client().chat.completions.create(
                        model=requested_model,
                        messages=messages,
                        temperature=temperature,
                        stream=True,
                    )
            except BadRequestError as exc:
                LOGGER.warning("Streaming request was rejected; falling back to non-streaming mode: %s", exc)
                _emit_stream_delta(stream_callback, "\n\n> 当前模型服务未接受流式输出，已切换为普通生成模式。\n\n")
                fallback_to_non_streaming = True
            else:
                parts = []
                usage_payload = None
                final_chunk = None
                for chunk in chunks:
                    final_chunk = chunk
                    chunk_usage = getattr(chunk, "usage", None)
                    if chunk_usage is not None:
                        usage_payload = chunk_usage
                    choices = getattr(chunk, "choices", None)
                    if not choices:
                        continue
                    delta = getattr(choices[0], "delta", None)
                    content = getattr(delta, "content", None)
                    if content is None or content == "":
                        continue
                    if not isinstance(content, str):
                        raise _InvalidLLMResponseError("模型请求失败：模型服务返回了非文本流式内容。")
                    parts.append(content)
                    _emit_stream_delta(stream_callback, content)
                content = _validate_chat_content("".join(parts))
                _record_model_usage(
                    final_chunk,
                    usage=usage_payload,
                    profile=profile,
                    endpoint_type="chat",
                    requested_model=requested_model,
                    input_text="\n".join(
                        str(message.get("content") or "") for message in messages
                    ),
                    output_text=content,
                )
                return content

        response = _get_client().chat.completions.create(
            model=requested_model,
            messages=messages,
            temperature=temperature,
        )
    except _InvalidLLMResponseError as exc:
        raise RuntimeError(str(exc)) from exc
    except Exception as exc:
        if getattr(exc, "cancel_generation", False):
            raise
        raise RuntimeError(_format_llm_error(exc)) from exc

    content = _extract_chat_content(response)
    _record_model_usage(
        response,
        profile=profile,
        endpoint_type="chat",
        requested_model=requested_model,
        input_text="\n".join(str(message.get("content") or "") for message in messages),
        output_text=content,
    )
    if fallback_to_non_streaming and content:
        _emit_stream_delta(stream_callback, content)
    return content


def get_embedding(text: str) -> list[float]:
    profile = load_llm_settings()
    api_key, base_url = _get_embedding_client_config()
    _require_openai()

    requested_model = str(_get_embedding_model_name() or "")
    if not requested_model:
        raise RuntimeError("向量生成失败：未设置语义向量模型；当前资料检索使用关键词模式。")

    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Embedding input text cannot be empty.")

    try:
        response = _get_client_for_config(api_key, base_url, _should_trust_env_proxy()).embeddings.create(
            model=requested_model,
            input=cleaned,
        )
    except Exception as exc:
        raise RuntimeError(_format_llm_error(exc, action="向量生成")) from exc
    embedding = _extract_embedding(response)
    _record_model_usage(
        response,
        profile=profile,
        endpoint_type="embedding",
        requested_model=requested_model,
        input_text=cleaned,
    )
    return embedding


PROVIDER_PRESETS = {
    "DeepSeek": {
        "base_url": "https://api.deepseek.com",
        "model_name": "deepseek-v4-flash",
        "embedding_mode": "disabled",
        "embedding_model_name": "",
        "provider_type": "deepseek",
        "cost_tracking_mode": "manual",
        "pricing_currency": "CNY",
        "display_currency": "CNY",
        "usd_to_cny_rate": 7.142857,
        "input_price_per_million": 1.0,
        "cached_input_price_per_million": 0.02,
        "cache_write_price_per_million": 0.0,
        "output_price_per_million": 2.0,
        "embedding_price_per_million": 0.0,
        "pricing_updated_at": "2026-08-10",
        "pricing_source_url": "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
        "currency_rate_updated_at": "2026-08-10",
        "currency_rate_source_url": "https://api-docs.deepseek.com/quick_start/pricing/",
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "model_name": "gpt-4o",
        "embedding_mode": "same_provider",
        "embedding_model_name": "text-embedding-3-small",
        "provider_type": "openai",
        "cost_tracking_mode": "manual",
    },
    "OpenRouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model_name": "auto",
        "embedding_mode": "disabled",
        "embedding_model_name": "",
        "provider_type": "openrouter",
        "cost_tracking_mode": "provider_reported",
    },
    "阿里云通义千问 (Qwen)": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_name": "qwen-plus",
        "embedding_mode": "same_provider",
        "embedding_model_name": "text-embedding-v3",
        "provider_type": "qwen",
        "cost_tracking_mode": "manual",
    },
    "硅基流动 (SiliconFlow)": {
        "base_url": "https://api.siliconflow.cn/v1",
        "model_name": "deepseek-v4-flash",
        "embedding_mode": "same_provider",
        "embedding_model_name": "BAAI/bge-m3",
        "provider_type": "siliconflow",
        "cost_tracking_mode": "manual",
    },
    "本地 Ollama": {
        "base_url": "http://localhost:11434/v1",
        "model_name": "llama3",
        "embedding_mode": "local",
        "embedding_base_url": "http://localhost:11434/v1",
        "embedding_model_name": "nomic-embed-text",
        "provider_type": "ollama",
        "cost_tracking_mode": "auto",
    },
    "自定义": {
        "base_url": "",
        "model_name": "",
        "embedding_mode": "disabled",
        "embedding_model_name": "",
        "provider_type": "auto",
        "cost_tracking_mode": "auto",
    },
}


def test_llm_connection(base_url: str, api_key: str, model_name: str) -> str:
    if not api_key:
        raise RuntimeError("接口密钥不能为空。")
    if not base_url:
        raise RuntimeError("模型服务网址不能为空。")
    try:
        openai_client_class = _require_openai()
        test_client = openai_client_class(
            api_key=api_key,
            base_url=base_url,
            http_client=httpx.Client(
                trust_env=_should_trust_env_proxy(),
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=30.0),
            ),
        )
        test_client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "回复 OK 即可。"}],
            max_tokens=8,
            temperature=0,
        )
        return "连接成功。"
    except Exception as exc:
        message = _format_llm_error(
            exc,
            action="连接测试",
            base_url=base_url,
            model_name=model_name,
        )
        raise RuntimeError(message) from exc


def test_llm_capabilities(
    base_url: str,
    api_key: str,
    model_name: str,
    *,
    embedding_mode: str = "disabled",
    embedding_model_name: str = "",
    embedding_base_url: str = "",
    embedding_api_key: str = "",
) -> dict:
    """Test chat and embedding independently without hiding partial readiness."""

    verified_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        chat_message = test_llm_connection(base_url, api_key, model_name)
        chat_status = "ready"
    except Exception as exc:
        chat_status = "failed"
        chat_message = str(exc)

    clean_mode = str(embedding_mode or "disabled").strip()
    if clean_mode == "disabled":
        embedding_status = "disabled"
        embedding_message = "语义向量已关闭，资料检索将使用关键词模式。"
    elif not str(embedding_model_name or "").strip():
        embedding_status = "failed"
        embedding_message = "未设置语义向量模型，资料检索将使用关键词模式。"
    else:
        if clean_mode == "separate_provider":
            vector_url = str(embedding_base_url or "").strip()
            vector_key = str(embedding_api_key or "").strip()
        elif clean_mode == "local":
            vector_url = str(embedding_base_url or base_url).strip()
            vector_key = str(embedding_api_key or "local").strip()
        else:
            vector_url = str(base_url or "").strip()
            vector_key = str(api_key or "").strip()
        if not vector_url or not vector_key:
            return {
                "chat_status": chat_status,
                "chat_status_message": chat_message,
                "embedding_status": "failed",
                "embedding_status_message": "向量服务地址或密钥不完整，资料检索将使用关键词模式。",
                "capabilities_verified_at": verified_at,
            }
        try:
            openai_client_class = _require_openai()
            vector_client = openai_client_class(
                api_key=vector_key,
                base_url=vector_url,
                http_client=httpx.Client(
                    trust_env=_should_trust_env_proxy(),
                    timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=30.0),
                ),
            )
            response = vector_client.embeddings.create(
                model=str(embedding_model_name).strip(),
                input="NovelForge capability check",
            )
            _extract_embedding(response)
            embedding_status = "ready"
            embedding_message = "语义向量连接成功。"
        except Exception as exc:
            embedding_status = "failed"
            embedding_message = _format_llm_error(
                exc,
                action="向量连接测试",
                base_url=vector_url,
                model_name=str(embedding_model_name).strip(),
            )

    return {
        "chat_status": chat_status,
        "chat_status_message": chat_message,
        "embedding_status": embedding_status,
        "embedding_status_message": embedding_message,
        "capabilities_verified_at": verified_at,
    }
