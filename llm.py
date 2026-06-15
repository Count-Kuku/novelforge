import os
from urllib.parse import urlparse

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)
from dotenv import load_dotenv

from memory import load_llm_settings

load_dotenv()

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def _get_api_key() -> str:
    return load_llm_settings().get("api_key", "")


def _get_base_url() -> str:
    return load_llm_settings().get("base_url", DEFAULT_BASE_URL)


def _get_model_name() -> str:
    return load_llm_settings().get("model_name", DEFAULT_MODEL)


def _get_embedding_model_name() -> str:
    return load_llm_settings().get("embedding_model_name", DEFAULT_EMBEDDING_MODEL)


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


def _get_client() -> OpenAI:
    return OpenAI(
        api_key=_get_api_key(),
        base_url=_get_base_url(),
        http_client=httpx.Client(trust_env=_should_trust_env_proxy()),
    )

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
    if isinstance(exc, APIConnectionError):
        return (
            f"{action}失败：无法连接到模型服务。"
            f"请检查服务地址 `{base_url}` 是否可访问、网络/代理是否正常，或服务商当前是否可用。"
        )
    if isinstance(exc, APITimeoutError):
        return f"{action}失败：模型服务响应超时。可以稍后重试，或减少单次处理片段数量。"
    if isinstance(exc, AuthenticationError):
        return f"{action}失败：接口密钥无效或已过期。请在模型配置里重新填写 API Key。"
    if isinstance(exc, PermissionDeniedError):
        return f"{action}失败：当前密钥没有访问该模型或接口的权限。"
    if isinstance(exc, NotFoundError):
        return f"{action}失败：模型或接口不存在。请检查模型名 `{model_name}` 和服务地址 `{base_url}`。"
    if isinstance(exc, BadRequestError):
        return f"{action}失败：请求参数不被模型服务接受。请检查模型名 `{model_name}`、上下文长度和服务地址。"
    if isinstance(exc, RateLimitError):
        return f"{action}失败：请求过于频繁或额度不足。请稍后重试，或降低批量提取数量。"
    if isinstance(exc, APIStatusError):
        return f"{action}失败：模型服务返回 HTTP {exc.status_code}。请检查服务商状态、模型名和账号额度。"
    return f"{action}失败（{type(exc).__name__}）：{exc}"


def call_llm(prompt: str, system_message: str = "", temperature: float = DEFAULT_TEMPERATURE):
    if not _get_api_key():
        raise RuntimeError("模型请求失败：接口密钥为空。请先在“模型配置”里填写 API Key。")

    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": prompt})

    try:
        response = _get_client().chat.completions.create(
            model=_get_model_name(),
            messages=messages,
            temperature=temperature
        )
    except Exception as exc:
        raise RuntimeError(_format_llm_error(exc)) from exc

    return response.choices[0].message.content or ""


def get_embedding(text: str) -> list[float]:
    if not _get_api_key():
        raise RuntimeError("向量生成失败：接口密钥为空。请先在“模型配置”里填写 API Key。")

    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Embedding input text cannot be empty.")

    try:
        response = _get_client().embeddings.create(
            model=_get_embedding_model_name(),
            input=cleaned,
        )
    except Exception as exc:
        raise RuntimeError(_format_llm_error(exc, action="向量生成")) from exc
    return response.data[0].embedding


PROVIDER_PRESETS = {
    "DeepSeek": {
        "base_url": "https://api.deepseek.com",
        "model_name": "deepseek-v4-flash",
        "embedding_model_name": "text-embedding-3-small",
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "model_name": "gpt-4o",
        "embedding_model_name": "text-embedding-3-small",
    },
    "OpenRouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model_name": "auto",
        "embedding_model_name": "text-embedding-3-small",
    },
    "阿里云通义千问 (Qwen)": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_name": "qwen-plus",
        "embedding_model_name": "text-embedding-v3",
    },
    "硅基流动 (SiliconFlow)": {
        "base_url": "https://api.siliconflow.cn/v1",
        "model_name": "deepseek-v4-flash",
        "embedding_model_name": "BAAI/bge-m3",
    },
    "本地 Ollama": {
        "base_url": "http://localhost:11434/v1",
        "model_name": "llama3",
        "embedding_model_name": "nomic-embed-text",
    },
    "自定义": {
        "base_url": "",
        "model_name": "",
        "embedding_model_name": "",
    },
}


def test_llm_connection(base_url: str, api_key: str, model_name: str) -> str:
    if not api_key:
        raise RuntimeError("接口密钥不能为空。")
    if not base_url:
        raise RuntimeError("模型服务网址不能为空。")
    try:
        test_client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=httpx.Client(trust_env=_should_trust_env_proxy()),
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
