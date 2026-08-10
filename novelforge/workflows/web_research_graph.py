"""Bounded LangGraph subgraph for parallel web discovery.

NovelForge remains the authority for durable task state.  This graph deliberately
compiles without a checkpointer and only coordinates one in-process research run.
"""

from __future__ import annotations

import operator
from typing import Annotated, Callable, TypedDict
from urllib.parse import urlsplit

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from novelforge.core.schemas import WebResearchBranch, WebResearchPlan, WebSearchResult
from novelforge.services.web_research import search_web


SOURCE_KIND_LABELS = {
    "official": "官方来源",
    "secondary": "百科与整理",
    "community": "社区考据",
    "fanon": "同人私设",
    "general": "综合资料",
}

SOURCE_KIND_QUERY_SUFFIXES = {
    "official": "官方 设定 官网",
    "secondary": "wiki 百科 设定",
    "community": "社区 讨论 考据",
    "fanon": "同人 私设 二创",
    "general": "资料 设定",
}


class WebResearchGraphState(TypedDict, total=False):
    topic: str
    provider: str
    language: str
    freshness: str
    source_kinds: list[str]
    max_results_per_branch: int
    plan: dict
    branch: dict
    branch_results: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]
    search_hits: list[dict]


Planner = Callable[[str, list[str], int], WebResearchPlan]
Searcher = Callable[..., WebSearchResult]


def build_default_web_research_plan(
    topic: str,
    source_kinds: list[str],
    max_results_per_branch: int,
) -> WebResearchPlan:
    """Build a deterministic first plan; an LLM planner can be injected later."""

    cleaned_topic = " ".join(str(topic or "").split())
    if not cleaned_topic:
        raise ValueError("网络研究主题不能为空。")
    if len(cleaned_topic) > 200:
        raise ValueError("网络研究主题不能超过 200 个字符。")
    normalized_kinds: list[str] = []
    for value in source_kinds or ["general"]:
        kind = str(value or "general").strip().lower()
        if kind not in SOURCE_KIND_LABELS:
            kind = "general"
        if kind not in normalized_kinds:
            normalized_kinds.append(kind)
    branches = [
        WebResearchBranch(
            branch_id=f"branch_{index:02d}_{kind}",
            label=SOURCE_KIND_LABELS[kind],
            query=f"{cleaned_topic} {SOURCE_KIND_QUERY_SUFFIXES[kind]}",
            source_kind=kind,
            max_results=max(1, min(int(max_results_per_branch), 20)),
        )
        for index, kind in enumerate(normalized_kinds, start=1)
    ]
    return WebResearchPlan(
        topic=cleaned_topic,
        objective=f"收集与“{cleaned_topic}”相关且可追溯的网络资料。",
        branches=branches,
        max_search_rounds=1,
        max_pages=min(sum(branch.max_results for branch in branches), 50),
        notes=["当前为确定性初始规划；后续阶段将接入受约束的 LLM Planner。"],
    )


def build_web_research_graph(
    *,
    planner: Planner = build_default_web_research_plan,
    searcher: Searcher = search_web,
):
    """Compile the in-process discovery graph without durable checkpointing."""

    def plan_node(state: WebResearchGraphState) -> dict:
        source_kinds = list(state.get("source_kinds") or ["general"])
        max_results = max(1, min(int(state.get("max_results_per_branch") or 5), 20))
        plan = planner(str(state.get("topic") or ""), source_kinds, max_results)
        return {"plan": plan.model_dump(), "branch_results": [], "errors": []}

    def dispatch_collectors(state: WebResearchGraphState) -> list[Send]:
        plan = WebResearchPlan.model_validate(state.get("plan") or {})
        shared = {
            "provider": str(state.get("provider") or "brave"),
            "language": str(state.get("language") or "zh-hans"),
            "freshness": str(state.get("freshness") or ""),
        }
        return [
            Send("collector", {**shared, "branch": branch.model_dump()})
            for branch in plan.branches
        ]

    def collector_node(state: WebResearchGraphState) -> dict:
        branch = WebResearchBranch.model_validate(state.get("branch") or {})
        search_query = branch.query
        if branch.preferred_domains:
            domain_terms: list[str] = []
            for domain in branch.preferred_domains:
                candidate_terms = [*domain_terms, f"site:{domain}"]
                candidate_query = f"{search_query} ({' OR '.join(candidate_terms)})"
                if len(candidate_query) > 380:
                    break
                domain_terms = candidate_terms
            if domain_terms:
                search_query = f"{search_query} ({' OR '.join(domain_terms)})"
        if branch.excluded_domains:
            for domain in branch.excluded_domains:
                candidate_query = f"{search_query} -site:{domain}"
                if len(candidate_query) > 400:
                    break
                search_query = candidate_query
        try:
            result = searcher(
                search_query,
                provider=str(state.get("provider") or "brave"),
                count=branch.max_results,
                language=str(state.get("language") or "zh-hans"),
                freshness=str(state.get("freshness") or ""),
            )
        except Exception as exc:
            return {
                "branch_results": [],
                "errors": [f"{branch.label}：{exc}"],
            }
        excluded_domains = {item.lower().rstrip(".") for item in branch.excluded_domains}
        filtered_results = [
            hit
            for hit in result.results
            if not any(
                str(urlsplit(hit.url).hostname or "").lower().rstrip(".") == domain
                or str(urlsplit(hit.url).hostname or "").lower().rstrip(".").endswith(f".{domain}")
                for domain in excluded_domains
            )
        ]
        result = result.model_copy(update={"results": filtered_results})
        return {
            "branch_results": [
                {
                    "branch": branch.model_dump(),
                    "search_result": result.model_dump(),
                }
            ],
            "errors": [],
        }

    def aggregate_node(state: WebResearchGraphState) -> dict:
        branch_results = list(state.get("branch_results") or [])
        branch_results.sort(
            key=lambda item: str((item.get("branch") or {}).get("branch_id") or "")
        )
        hits_by_url: dict[str, dict] = {}
        for branch_result in branch_results:
            branch = branch_result.get("branch") or {}
            result = WebSearchResult.model_validate(branch_result.get("search_result") or {})
            for hit in result.results:
                existing = hits_by_url.get(hit.url)
                source_kind = str(branch.get("source_kind") or "general")
                if existing is None:
                    payload = hit.model_dump()
                    payload["source_kinds"] = [source_kind]
                    payload["branch_ids"] = [str(branch.get("branch_id") or "")]
                    hits_by_url[hit.url] = payload
                    continue
                if source_kind not in existing["source_kinds"]:
                    existing["source_kinds"].append(source_kind)
                branch_id = str(branch.get("branch_id") or "")
                if branch_id and branch_id not in existing["branch_ids"]:
                    existing["branch_ids"].append(branch_id)
        ordered_hits = sorted(
            hits_by_url.values(),
            key=lambda item: (
                min(item.get("rank", 0) or 0, 999),
                str(item.get("url") or ""),
            ),
        )
        return {"search_hits": ordered_hits}

    builder = StateGraph(WebResearchGraphState)
    builder.add_node("plan", plan_node)
    builder.add_node("collector", collector_node)
    builder.add_node("aggregate", aggregate_node)
    builder.add_edge(START, "plan")
    builder.add_conditional_edges("plan", dispatch_collectors, ["collector"])
    builder.add_edge("collector", "aggregate")
    builder.add_edge("aggregate", END)
    return builder.compile()


def run_web_research_discovery(
    topic: str,
    *,
    source_kinds: list[str] | None = None,
    provider: str = "brave",
    language: str = "zh-hans",
    freshness: str = "",
    max_results_per_branch: int = 5,
    max_concurrency: int = 3,
) -> dict:
    """Run the bounded discovery graph and return JSON-serializable state."""

    graph = build_web_research_graph()
    return graph.invoke(
        {
            "topic": topic,
            "source_kinds": source_kinds or ["official", "secondary", "community", "fanon"],
            "provider": provider,
            "language": language,
            "freshness": freshness,
            "max_results_per_branch": max_results_per_branch,
            "branch_results": [],
            "errors": [],
        },
        {"max_concurrency": max(1, int(max_concurrency))},
    )
