"""Web-search provider adapters used by bounded research workflows."""

from __future__ import annotations

import hashlib
import os
from typing import Any
import httpx

from novelforge.core.schemas import WebSearchHit, WebSearchResult
from novelforge.services.web_research.fetch import WebFetchSecurityError, normalize_web_url


BRAVE_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
DEFAULT_SEARCH_TIMEOUT_SECONDS = 20.0


class WebSearchConfigurationError(ValueError):
    """Raised when a configured provider cannot be used."""


class WebSearchRequestError(RuntimeError):
    """Raised when a provider request or response is invalid."""


def available_web_search_providers() -> dict[str, str]:
    return {"brave": "Brave Search"}


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


def _search_brave(
    query: str,
    *,
    count: int,
    language: str,
    freshness: str,
    api_key: str,
    client: httpx.Client | None,
) -> WebSearchResult:
    token = str(api_key or os.getenv("BRAVE_SEARCH_API_KEY", "")).strip()
    if not token:
        raise WebSearchConfigurationError(
            "Brave Search API Key 为空。请设置 BRAVE_SEARCH_API_KEY。"
        )

    params: dict[str, Any] = {
        "q": query,
        "count": max(1, min(int(count), 20)),
        "safesearch": "moderate",
        "extra_snippets": "true",
    }
    if language:
        params["search_lang"] = language
    if freshness:
        params["freshness"] = freshness

    owns_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(DEFAULT_SEARCH_TIMEOUT_SECONDS),
        trust_env=False,
    )
    try:
        response = active_client.get(
            BRAVE_SEARCH_ENDPOINT,
            params=params,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": token,
            },
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        raise WebSearchRequestError(f"Brave Search 请求失败（HTTP {status}）。") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise WebSearchRequestError(f"Brave Search 请求失败：{exc}") from exc
    finally:
        if owns_client:
            active_client.close()

    if not isinstance(payload, dict):
        raise WebSearchRequestError("Brave Search 返回了无法识别的数据格式。")
    web_payload = payload.get("web", {})
    raw_results = web_payload.get("results", []) if isinstance(web_payload, dict) else []
    normalized: list[WebSearchHit] = []
    if isinstance(raw_results, list):
        for raw in raw_results:
            if not isinstance(raw, dict):
                continue
            url = _safe_http_url(raw.get("url"))
            if not url:
                continue
            snippets = raw.get("extra_snippets", [])
            if not isinstance(snippets, list):
                snippets = []
            snippets = [str(item)[:1000] for item in snippets[:5] if str(item)]
            normalized.append(
                WebSearchHit(
                    result_id=_result_id("brave", url),
                    provider="brave",
                    query=query,
                    title=str(raw.get("title") or "")[:500],
                    url=url,
                    description=str(raw.get("description") or "")[:2000],
                    extra_snippets=snippets,
                    language=str(raw.get("language") or ""),
                    published_at=str(raw.get("age") or raw.get("page_age") or ""),
                    rank=len(normalized) + 1,
                )
            )

    query_payload = payload.get("query", {})
    more_results = bool(
        isinstance(query_payload, dict)
        and query_payload.get("more_results_available")
    )
    return WebSearchResult(
        provider="brave",
        query=query,
        results=normalized,
        more_results_available=more_results,
        requested_count=params["count"],
    )


def search_web(
    query: str,
    *,
    provider: str = "brave",
    count: int = 8,
    language: str = "zh-hans",
    freshness: str = "",
    api_key: str = "",
    client: httpx.Client | None = None,
) -> WebSearchResult:
    """Search the public web through one normalized provider interface."""

    cleaned_query = _clean_query(query)
    provider_name = str(provider or "brave").strip().lower()
    if provider_name == "brave":
        return _search_brave(
            cleaned_query,
            count=count,
            language=str(language or "").strip(),
            freshness=str(freshness or "").strip(),
            api_key=api_key,
            client=client,
        )
    raise WebSearchConfigurationError(f"不支持的网络检索 Provider：{provider_name}")
