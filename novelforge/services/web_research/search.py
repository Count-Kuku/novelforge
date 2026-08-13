"""Automatic web-search routing for model-native and keyless providers."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import threading
from contextlib import contextmanager
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from novelforge.core.llm_usage import detect_provider
from novelforge.core.schemas import WebSearchHit, WebSearchResult
from novelforge.services.web_research.fetch import WebFetchSecurityError, normalize_web_url


DEFAULT_SEARCH_TIMEOUT_SECONDS = 20.0
NATIVE_SEARCH_PROVIDERS = frozenset({"deepseek", "openai", "openrouter", "qwen"})
PROVIDER_LABELS = {
    "deepseek": "DeepSeek 原生搜索",
    "openai": "OpenAI 原生搜索",
    "openrouter": "OpenRouter 联网搜索",
    "qwen": "通义千问原生搜索",
    "ddgs": "免密通用搜索",
}
DDGS_BACKENDS = ("auto", "bing", "duckduckgo")
_DDGS_ENV_LOCK = threading.RLock()
_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


class WebSearchConfigurationError(ValueError):
    """Raised when no automatic search route can be used."""


class WebSearchRequestError(RuntimeError):
    """Raised when every eligible search route fails."""


def available_web_search_providers() -> dict[str, str]:
    """Return user-facing routes.

    Search-provider selection is intentionally automatic: users configure one
    model credential, while NovelForge chooses native search or a keyless
    fallback internally.
    """

    return {"auto": "自动（模型原生 / 免密通用搜索）"}


def keyless_search_available() -> bool:
    """Report whether the bundled DDGS fallback can be imported."""

    return importlib.util.find_spec("ddgs") is not None


def native_search_provider(profile: dict | None = None) -> str:
    """Return the active provider when it has a supported native search API."""

    if profile is None:
        from novelforge.services.memory import load_llm_settings

        profile = load_llm_settings()
    provider = detect_provider(profile)
    return provider if provider in NATIVE_SEARCH_PROVIDERS else ""


def automatic_search_status(profile: dict | None = None) -> dict:
    """Build a non-networked description of the automatic search route."""

    if profile is None:
        from novelforge.services.memory import load_llm_settings

        profile = load_llm_settings()
    active_profile = dict(profile or {})
    native_provider = native_search_provider(active_profile)
    native_available = bool(native_provider and str(active_profile.get("api_key") or "").strip())
    fallback_available = keyless_search_available()
    available = native_available or fallback_available
    if native_available and fallback_available:
        message = (
            f"优先使用{PROVIDER_LABELS[native_provider]}，不可用时自动切换到"
            f"{PROVIDER_LABELS['ddgs']}，无需额外 API Key。"
        )
    elif native_available:
        message = f"使用{PROVIDER_LABELS[native_provider]}，复用当前模型 API Key。"
    elif fallback_available:
        message = f"当前模型无可用原生搜索时使用{PROVIDER_LABELS['ddgs']}，无需额外 API Key。"
    else:
        message = "当前模型没有可用的原生搜索，且缺少 ddgs 通用搜索依赖。"
    return {
        "available": available,
        "native_provider": native_provider,
        "native_available": native_available,
        "fallback_available": fallback_available,
        "message": message,
    }


def _clean_query(query: str) -> str:
    cleaned = " ".join(str(query or "").split())
    if not cleaned:
        raise ValueError("网络检索关键词不能为空。")
    if len(cleaned) > 400:
        raise ValueError("网络检索关键词不能超过 400 个字符。")
    return cleaned


def _safe_http_url(value: Any) -> str:
    cleaned = str(value or "").strip()
    try:
        return normalize_web_url(cleaned)
    except (UnicodeError, ValueError, WebFetchSecurityError):
        return ""


def _result_id(provider: str, url: str) -> str:
    digest = hashlib.sha256(f"{provider}:{url}".encode("utf-8")).hexdigest()[:24]
    return f"webhit_{digest}"


def _api_endpoint(base_url: str, suffix: str) -> str:
    cleaned = str(base_url or "").strip().rstrip("/")
    if not cleaned:
        raise WebSearchConfigurationError("当前模型服务网址为空。")
    return f"{cleaned}{suffix}"


def _deepseek_anthropic_endpoint(base_url: str) -> str:
    parsed = urlsplit(str(base_url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        raise WebSearchConfigurationError("当前 DeepSeek 服务网址无效。")
    path = parsed.path.rstrip("/")
    if path.endswith("/anthropic/v1"):
        path = f"{path}/messages"
    elif path.endswith("/anthropic"):
        path = f"{path}/v1/messages"
    else:
        path = "/anthropic/v1/messages"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _append_source(rows: list[dict], raw: Any) -> None:
    if not isinstance(raw, dict):
        return
    citation = raw.get("url_citation")
    if isinstance(citation, dict):
        raw = citation
    url = _safe_http_url(raw.get("url") or raw.get("href") or raw.get("link"))
    if not url:
        return
    rows.append(
        {
            "url": url,
            "title": str(raw.get("title") or raw.get("name") or "")[:500],
            "description": str(
                raw.get("content")
                or raw.get("description")
                or raw.get("snippet")
                or raw.get("body")
                or raw.get("text")
                or ""
            )[:2000],
            "published_at": str(
                raw.get("page_age") or raw.get("published_at") or raw.get("date") or ""
            )[:200],
        }
    )


def _extract_native_sources(payload: Any) -> list[dict]:
    """Extract traceable URL rows from common hosted-search response shapes."""

    rows: list[dict] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        node_type = str(node.get("type") or "").lower()
        if node_type in {"web_search_result", "search_result", "url_citation"}:
            _append_source(rows, node)
        citation = node.get("url_citation")
        if isinstance(citation, dict):
            _append_source(rows, citation)
        for key in ("search_results", "sources"):
            values = node.get(key)
            if isinstance(values, list):
                for value in values:
                    _append_source(rows, value)
        for value in node.values():
            if isinstance(value, (dict, list)):
                walk(value)

    walk(payload)
    deduplicated: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if row["url"] in seen:
            continue
        seen.add(row["url"])
        deduplicated.append(row)
    return deduplicated


def _native_request_spec(provider: str, profile: dict, query: str, count: int) -> tuple[str, dict, dict]:
    api_key = str(profile.get("api_key") or "").strip()
    base_url = str(profile.get("base_url") or "").strip()
    model_name = str(profile.get("model_name") or "").strip()
    if not api_key or not base_url or not model_name:
        raise WebSearchConfigurationError("当前模型配置不完整，无法调用模型原生搜索。")
    prompt = (
        f"请搜索公开网页以回答检索词：{query}\n"
        f"最多使用 {count} 个最相关来源；必须执行联网搜索并保留来源链接。"
    )
    if provider == "deepseek":
        return (
            _deepseek_anthropic_endpoint(base_url),
            {
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
                "x-api-key": api_key,
            },
            {
                "model": model_name,
                "max_tokens": 512,
                "messages": [{"role": "user", "content": prompt}],
                "tools": [
                    {"type": "web_search_20250305", "name": "web_search", "max_uses": 1}
                ],
            },
        )
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    if provider == "openrouter":
        return (
            _api_endpoint(base_url, "/chat/completions"),
            headers,
            {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "tools": [
                    {
                        "type": "openrouter:web_search",
                        "parameters": {
                            "engine": "auto",
                            "max_results": count,
                            "max_total_results": count,
                            "max_uses": 1,
                        },
                    }
                ],
            },
        )
    if provider == "qwen":
        return (
            _api_endpoint(base_url, "/chat/completions"),
            headers,
            {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "enable_search": True,
                "search_options": {"forced_search": True, "enable_source": True},
            },
        )
    if provider == "openai":
        return (
            _api_endpoint(base_url, "/responses"),
            headers,
            {
                "model": model_name,
                "input": prompt,
                "tools": [{"type": "web_search_preview", "search_context_size": "medium"}],
                "tool_choice": "required",
                "include": ["web_search_call.action.sources"],
                "max_output_tokens": 512,
            },
        )
    raise WebSearchConfigurationError(f"当前供应商不支持模型原生搜索：{provider}")


def _record_native_usage(payload: dict, *, profile: dict, provider: str, query: str) -> None:
    try:
        from novelforge.core.llm_usage import build_llm_usage_event, persist_llm_usage_event

        usage = payload.get("usage") or {}
        output_text = "\n".join(
            str(row.get("url") or "") for row in _extract_native_sources(payload)
        )
        event = build_llm_usage_event(
            usage=usage,
            profile=profile,
            endpoint_type="web_search",
            requested_model=str(profile.get("model_name") or ""),
            reported_model=str(payload.get("model") or profile.get("model_name") or ""),
            provider_request_id=str(payload.get("id") or payload.get("request_id") or ""),
            input_text=query,
            output_text=output_text,
            metadata={"search_provider": provider},
        )
        persist_llm_usage_event(event)
    except Exception:
        # Usage accounting must not turn a successful search into a user-visible failure.
        return


def _search_model_native(
    query: str,
    *,
    provider: str,
    profile: dict,
    count: int,
    client: httpx.Client | None,
) -> WebSearchResult:
    endpoint, headers, request_body = _native_request_spec(provider, profile, query, count)
    owns_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(DEFAULT_SEARCH_TIMEOUT_SECONDS),
        trust_env=False,
    )
    try:
        response = active_client.post(endpoint, headers=headers, json=request_body)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise WebSearchRequestError(
            f"{PROVIDER_LABELS[provider]}请求失败（HTTP {exc.response.status_code}）。"
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise WebSearchRequestError(f"{PROVIDER_LABELS[provider]}请求失败：{exc}") from exc
    finally:
        if owns_client:
            active_client.close()
    if not isinstance(payload, dict):
        raise WebSearchRequestError(f"{PROVIDER_LABELS[provider]}返回了无法识别的数据格式。")
    rows = _extract_native_sources(payload)[:count]
    if not rows:
        raise WebSearchRequestError(f"{PROVIDER_LABELS[provider]}没有返回可追踪的网页链接。")
    result_provider = f"{provider}_native"
    normalized = [
        WebSearchHit(
            result_id=_result_id(result_provider, row["url"]),
            provider=result_provider,
            query=query,
            title=row["title"],
            url=row["url"],
            description=row["description"],
            published_at=row["published_at"],
            rank=index,
        )
        for index, row in enumerate(rows, start=1)
    ]
    _record_native_usage(payload, profile=profile, provider=provider, query=query)
    return WebSearchResult(
        provider=result_provider,
        query=query,
        results=normalized,
        more_results_available=False,
        requested_count=count,
    )


def _load_ddgs_class():
    try:
        from ddgs import DDGS
    except ModuleNotFoundError as exc:
        raise WebSearchConfigurationError(
            "缺少免密通用搜索依赖 ddgs，请重新安装 requirements.txt。"
        ) from exc
    return DDGS


def _is_blocked_local_proxy(value: str) -> bool:
    try:
        parsed = urlsplit(str(value or "").strip())
    except ValueError:
        return False
    return (parsed.hostname or "").lower() in {"127.0.0.1", "localhost", "::1"} and parsed.port == 9


@contextmanager
def _ddgs_network_environment():
    """Ignore NovelForge's known offline-test proxy sentinel for DDGS only.

    DDGS/Primp does not expose an equivalent of ``trust_env=False``. The lock
    keeps temporary environment changes deterministic across parallel research
    collectors, and real user proxy settings remain untouched.
    """

    with _DDGS_ENV_LOCK:
        removed = {
            key: os.environ.pop(key)
            for key in _PROXY_ENV_KEYS
            if key in os.environ and _is_blocked_local_proxy(os.environ[key])
        }
        try:
            yield
        finally:
            os.environ.update(removed)


def _search_ddgs(
    query: str,
    *,
    count: int,
    language: str,
    freshness: str,
    ddgs_factory: Callable[..., Any] | None = None,
) -> WebSearchResult:
    factory = ddgs_factory or _load_ddgs_class()
    region = "cn-zh" if str(language or "").lower().startswith("zh") else "us-en"
    timelimit = {"pd": "d", "pw": "w", "pm": "m", "py": "y"}.get(
        str(freshness or "").strip().lower()
    )
    raw_results: Any = []
    errors: list[str] = []
    with _ddgs_network_environment():
        for backend in DDGS_BACKENDS:
            try:
                engine = factory(timeout=int(DEFAULT_SEARCH_TIMEOUT_SECONDS))
                raw_results = engine.text(
                    query,
                    region=region,
                    safesearch="moderate",
                    timelimit=timelimit,
                    max_results=count,
                    backend=backend,
                )
                if raw_results:
                    break
            except Exception as exc:
                errors.append(f"{backend}: {exc}")
    if not raw_results and errors:
        raise WebSearchRequestError(f"免密通用搜索请求失败：{'；'.join(errors)}")
    normalized: list[WebSearchHit] = []
    for raw in list(raw_results or []):
        if not isinstance(raw, dict):
            continue
        url = _safe_http_url(raw.get("href") or raw.get("url") or raw.get("link"))
        if not url:
            continue
        normalized.append(
            WebSearchHit(
                result_id=_result_id("ddgs", url),
                provider="ddgs",
                query=query,
                title=str(raw.get("title") or "")[:500],
                url=url,
                description=str(raw.get("body") or raw.get("description") or "")[:2000],
                published_at=str(raw.get("date") or raw.get("published") or "")[:200],
                rank=len(normalized) + 1,
            )
        )
        if len(normalized) >= count:
            break
    return WebSearchResult(
        provider="ddgs",
        query=query,
        results=normalized,
        more_results_available=False,
        requested_count=count,
    )


def search_web(
    query: str,
    *,
    provider: str = "auto",
    count: int = 8,
    language: str = "zh-hans",
    freshness: str = "",
    api_key: str = "",
    client: httpx.Client | None = None,
    profile: dict | None = None,
    ddgs_factory: Callable[..., Any] | None = None,
) -> WebSearchResult:
    """Search through the active model first, then fall back to keyless DDGS.

    ``api_key`` remains accepted for call-site compatibility but is never used
    as an independent search credential. When supplied, it only overrides the
    active model key for a model-native request.
    """

    cleaned_query = _clean_query(query)
    requested_count = max(1, min(int(count), 20))
    provider_name = str(provider or "auto").strip().lower()
    if provider_name not in {"auto", "ddgs", *NATIVE_SEARCH_PROVIDERS}:
        raise WebSearchConfigurationError(f"不支持的网络检索 Provider：{provider_name}")
    if profile is None:
        from novelforge.services.memory import load_llm_settings

        profile = load_llm_settings()
    active_profile = dict(profile or {})
    if api_key:
        active_profile["api_key"] = str(api_key).strip()
    detected_provider = native_search_provider(active_profile)
    native_target = provider_name if provider_name in NATIVE_SEARCH_PROVIDERS else detected_provider
    native_error: Exception | None = None
    if provider_name != "ddgs" and native_target and str(active_profile.get("api_key") or "").strip():
        try:
            return _search_model_native(
                cleaned_query,
                provider=native_target,
                profile=active_profile,
                count=requested_count,
                client=client,
            )
        except (WebSearchConfigurationError, WebSearchRequestError) as exc:
            native_error = exc
    try:
        return _search_ddgs(
            cleaned_query,
            count=requested_count,
            language=str(language or "").strip(),
            freshness=str(freshness or "").strip(),
            ddgs_factory=ddgs_factory,
        )
    except (WebSearchConfigurationError, WebSearchRequestError) as fallback_error:
        if native_error is not None:
            raise WebSearchRequestError(
                f"模型原生搜索不可用：{native_error}；通用搜索也不可用：{fallback_error}"
            ) from fallback_error
        raise
