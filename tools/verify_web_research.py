from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from unittest.mock import patch

import httpx


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from novelforge.core.schemas import (
    FetchedWebPage,
    WebResearchPlan,
    WebSearchHit,
    WebSearchResult,
)
from novelforge.services.web_research import (
    WebFetchSecurityError,
    fetch_web_page,
    import_fetched_web_pages,
    normalize_web_url,
    search_web,
    validate_public_web_url,
)
from novelforge.services.web_research import sources as web_sources
from novelforge.workflows.web_research_graph import (
    build_default_web_research_plan,
    build_web_research_graph,
)


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def _public_resolver(host: str, port: int, *, type: int = 0) -> list[tuple]:
    return [(socket.AF_INET, type or socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


def _private_resolver(host: str, port: int, *, type: int = 0) -> list[tuple]:
    return [(socket.AF_INET, type or socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]


def verify_brave_search_normalization() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        check(request.headers.get("x-subscription-token") == "test-key", "search key stays in request header")
        check(request.url.params.get("q") == "坎瑞亚 官方设定", "search query is passed to provider")
        return httpx.Response(
            200,
            json={
                "query": {"more_results_available": True},
                "web": {
                    "results": [
                        {
                            "title": "官方设定页",
                            "url": "https://example.com/lore",
                            "description": "设定摘要",
                            "extra_snippets": ["补充片段"],
                            "language": "zh-hans",
                            "age": "2026-01-01",
                        },
                        {"title": "无效结果", "url": "file:///tmp/private"},
                    ]
                },
            },
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as client:
        result = search_web(
            "坎瑞亚  官方设定",
            api_key="test-key",
            count=8,
            client=client,
        )
    check(result.provider == "brave", "search result records provider")
    check(result.more_results_available, "search result keeps pagination hint")
    check(len(result.results) == 1, "search result drops non-http URLs")
    check(result.results[0].rank == 1, "search results receive stable display ranks")
    check(result.results[0].extra_snippets == ["补充片段"], "search result keeps extra snippets")


def verify_safe_fetch_and_text_extraction() -> FetchedWebPage:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/article"}, request=request)
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8", "etag": "v1"},
            text="""
                <html><head><title>坎瑞亚设定</title>
                <meta name="description" content="官方资料摘要"></head>
                <body><nav>导航噪声</nav><main><h1>坎瑞亚</h1>
                <p>这是需要导入的正文。</p><script>ignore_me()</script></main></body></html>
            """,
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as client:
        page = fetch_web_page(
            "https://example.com/start#fragment",
            resolver=_public_resolver,
            client=client,
        )
    check(page.final_url == "https://example.com/article", "redirect target is normalized")
    check(page.title == "坎瑞亚设定", "HTML title is extracted")
    check(page.description == "官方资料摘要", "HTML description is extracted")
    check("这是需要导入的正文" in page.text, "readable page text is retained")
    check("ignore_me" not in page.text, "script content is excluded")
    check(page.metadata.get("etag") == "v1", "fetch metadata keeps validators")
    return page


def verify_private_network_rejection() -> None:
    check(
        normalize_web_url("https://[2606:4700:4700::1111]:443/dns#fragment")
        == "https://[2606:4700:4700::1111]/dns",
        "IPv6 literals retain URL brackets during normalization",
    )
    check(
        normalize_web_url("https://example.com/设定?q=星 海#fragment")
        == "https://example.com/%E8%AE%BE%E5%AE%9A?q=%E6%98%9F%20%E6%B5%B7",
        "Unicode URL paths and queries are safely percent-encoded",
    )
    try:
        validate_public_web_url("http://localhost/admin", resolver=_public_resolver)
    except WebFetchSecurityError:
        pass
    else:
        raise AssertionError("localhost should be rejected")
    CHECKS.append("localhost is rejected")

    try:
        validate_public_web_url("https://example.test/private", resolver=_private_resolver)
    except WebFetchSecurityError:
        pass
    else:
        raise AssertionError("private DNS result should be rejected")
    CHECKS.append("private DNS addresses are rejected")


def verify_dns_rebinding_rejection() -> None:
    calls = 0

    def alternating_resolver(host: str, port: int, *, type: int = 0) -> list[tuple]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _public_resolver(host, port, type=type)
        return _private_resolver(host, port, type=type)

    try:
        fetch_web_page("https://example.test/rebinding", resolver=alternating_resolver)
    except WebFetchSecurityError:
        pass
    else:
        raise AssertionError("DNS rebinding to a private address should be rejected")
    check(calls >= 2, "fetch revalidates and pins the address used for the connection")


def verify_batch_source_import(page: FetchedWebPage) -> None:
    captured_payloads: list[dict] = []

    def fake_ingest(project_name: str, source_name: str, content: str, *, overwrite: bool = True) -> str:
        captured_payloads.append(json.loads(content))
        return f"{source_name}.json"

    with (
        patch.object(web_sources, "ingest_external_source_file", side_effect=fake_ingest),
        patch.object(web_sources, "rebuild_retrieval_assets") as rebuild,
    ):
        imported = import_fetched_web_pages(
            "demo",
            [page, page.model_dump()],
            query="坎瑞亚",
            provider="brave",
            authority="official",
        )
    check(len(imported) == 1, "duplicate final URLs are imported once per batch")
    check(rebuild.call_count == 1, "batch import rebuilds retrieval assets once")
    metadata = captured_payloads[0].get("metadata", {})
    check(captured_payloads[0].get("content") == page.text, "source payload preserves the exact fetched body")
    check(metadata.get("canonical_url") == page.final_url, "source payload persists canonical URL")
    check(metadata.get("content_hash") == page.content_hash, "source payload persists content hash")


def verify_research_plan_schema() -> None:
    plan = WebResearchPlan.model_validate(
        {
            "topic": "坎瑞亚",
            "branches": [
                {
                    "branch_id": "official",
                    "label": "官方来源",
                    "query": "坎瑞亚 官方设定",
                    "source_kind": "official",
                }
            ],
        }
    )
    check(plan.branches[0].source_kind == "official", "research plan validates bounded source roles")


def verify_parallel_research_graph() -> None:
    calls: list[tuple[str, str, int]] = []

    def fake_searcher(
        query: str,
        *,
        provider: str,
        count: int,
        language: str,
        freshness: str,
    ) -> WebSearchResult:
        calls.append((query, provider, count))
        kind = "official" if "official" in query else "community"
        return WebSearchResult(
            provider=provider,
            query=query,
            requested_count=count,
            results=[
                WebSearchHit(
                    result_id=f"{kind}-unique",
                    provider=provider,
                    query=query,
                    title=f"{kind} unique",
                    url=f"https://example.com/{kind}",
                    rank=1,
                ),
                WebSearchHit(
                    result_id=f"{kind}-shared",
                    provider=provider,
                    query=query,
                    title="shared source",
                    url="https://example.com/shared",
                    rank=2,
                ),
            ],
        )

    def english_planner(topic: str, source_kinds: list[str], count: int) -> WebResearchPlan:
        return WebResearchPlan.model_validate(
            {
                "topic": topic,
                "branches": [
                    {
                        "branch_id": "branch_01_official",
                        "label": "Official",
                        "query": f"{topic} official",
                        "source_kind": "official",
                        "max_results": count,
                    },
                    {
                        "branch_id": "branch_02_community",
                        "label": "Community",
                        "query": f"{topic} community",
                        "source_kind": "community",
                        "max_results": count,
                    },
                ],
            }
        )

    graph = build_web_research_graph(planner=english_planner, searcher=fake_searcher)
    state = graph.invoke(
        {
            "topic": "NovelForge",
            "source_kinds": ["official", "community"],
            "provider": "brave",
            "language": "en",
            "freshness": "",
            "max_results_per_branch": 2,
            "branch_results": [],
            "errors": [],
        },
        {"max_concurrency": 2},
    )
    check(len(calls) == 2, "research graph dispatches one collector per branch")
    check(len(state.get("search_hits") or []) == 3, "research graph deduplicates URLs across branches")
    shared = next(item for item in state["search_hits"] if item["url"].endswith("/shared"))
    check(
        set(shared.get("source_kinds") or []) == {"official", "community"},
        "research graph retains every source role for duplicate URLs",
    )
    check(not state.get("errors"), "research graph completes without collector errors")

    default_plan = build_default_web_research_plan(
        "坎瑞亚",
        ["official", "official", "unknown"],
        99,
    )
    check(len(default_plan.branches) == 2, "default planner deduplicates bounded source roles")
    check(default_plan.branches[0].max_results == 20, "default planner clamps provider result limits")


def verify_excluded_domains() -> None:
    queries: list[str] = []

    def planner(topic: str, source_kinds: list[str], count: int) -> WebResearchPlan:
        return WebResearchPlan.model_validate(
            {
                "topic": topic,
                "branches": [
                    {
                        "branch_id": "general",
                        "label": "General",
                        "query": topic,
                        "source_kind": "general",
                        "excluded_domains": ["blocked.example"],
                        "max_results": count,
                    }
                ],
            }
        )

    def searcher(query: str, **kwargs) -> WebSearchResult:
        queries.append(query)
        return WebSearchResult(
            provider="brave",
            query=query,
            requested_count=int(kwargs.get("count") or 1),
            results=[
                WebSearchHit(
                    result_id="blocked",
                    provider="brave",
                    query=query,
                    title="blocked",
                    url="https://sub.blocked.example/lore",
                    rank=1,
                ),
                WebSearchHit(
                    result_id="allowed",
                    provider="brave",
                    query=query,
                    title="allowed",
                    url="https://allowed.example/lore",
                    rank=2,
                ),
            ],
        )

    state = build_web_research_graph(planner=planner, searcher=searcher).invoke(
        {
            "topic": "NovelForge",
            "source_kinds": ["general"],
            "provider": "brave",
            "language": "en",
            "freshness": "",
            "max_results_per_branch": 2,
            "branch_results": [],
            "errors": [],
        },
        {"max_concurrency": 1},
    )
    check("-site:blocked.example" in queries[0], "excluded domains are sent to the search provider")
    check(
        [item["url"] for item in state["search_hits"]] == ["https://allowed.example/lore"],
        "excluded domains are also filtered from provider results",
    )


def main() -> int:
    try:
        verify_brave_search_normalization()
        page = verify_safe_fetch_and_text_extraction()
        verify_private_network_rejection()
        verify_dns_rebinding_rejection()
        verify_batch_source_import(page)
        verify_research_plan_schema()
        verify_parallel_research_graph()
        verify_excluded_domains()
    except Exception as exc:
        print(json.dumps({"ok": False, "checks": CHECKS, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "checks": CHECKS}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
