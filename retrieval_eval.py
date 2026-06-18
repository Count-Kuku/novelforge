from memory import append_retrieval_eval_run
from retrieval import build_retrieval_briefing, retrieve_context


def parse_multiline_or_comma_values(value: str) -> list[str]:
    normalized = str(value or "").replace("，", ",")
    parts: list[str] = []
    for line in normalized.splitlines():
        parts.extend(item.strip() for item in line.split(",") if item.strip())
    return [item for item in parts if item]


def retrieval_profile_label(value: str) -> str:
    return {
        "": "通用",
        "creative_profile_discussion": "创作配置讨论",
        "outline_discussion": "全书大纲讨论",
        "volume_discussion": "分卷讨论",
        "arc_discussion": "剧情段讨论",
        "chapter_discussion": "章节讨论",
        "outline_generation": "大纲生成",
        "chapter_planning": "章节规划",
        "drafting": "正文写作",
        "review": "审阅/评价",
    }.get(value, value)


def build_retrieval_usage_report_from_payload(
    hits: list[dict],
    *,
    label_source_type_func=None,
    label_scope_func=None,
    label_authority_func=None,
) -> dict:
    label_source_type_func = label_source_type_func or (lambda value: str(value or "未知资料"))
    label_scope_func = label_scope_func or (lambda value: str(value or "未知范围"))
    label_authority_func = label_authority_func or (lambda value: str(value or "未标明"))
    if not hits:
        return {
            "hit_count": 0,
            "source_type_counts": {},
            "scope_counts": {},
            "priority_sources": [],
            "constraints": [],
            "conflicts": [],
            "risk_notes": ["本次没有检索到可用资料，生成内容更依赖当前输入、核心设定和模型推断。"],
        }

    source_type_counts: dict[str, int] = {}
    scope_counts: dict[str, int] = {}
    priority_sources = []
    constraints = []
    conflicts = []
    risk_notes = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        chunk = hit.get("chunk", {}) if isinstance(hit.get("chunk", {}), dict) else {}
        source_type = str(chunk.get("source_type") or "unknown")
        scope = str(chunk.get("scope") or "project")
        source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
        scope_counts[scope] = scope_counts.get(scope, 0) + 1
        title = str(chunk.get("title") or chunk.get("document_id") or "未命名")
        content = str(chunk.get("content") or "")
        meta = chunk.get("metadata", {}) if isinstance(chunk.get("metadata", {}), dict) else {}
        priority_sources.append({
            "来源类型": label_source_type_func(source_type),
            "范围": label_scope_func(scope),
            "标题": title,
            "相关度": f"{float(hit.get('score') or 0):.2f}",
            "可信度": label_authority_func(meta.get("authority", "unknown")),
            "命中词": "、".join(str(term) for term in hit.get("matched_terms", [])[:6]),
        })
        if source_type in {"knowledge_constraints", "memory_active_constraint", "entity_setting_card"}:
            constraints.append({
                "来源": f"{label_source_type_func(source_type)} / {title}",
                "内容": content[:260],
            })
        if source_type == "conflict_resolution":
            conflicts.append({
                "来源": title,
                "内容": content[:260],
            })

    if not constraints:
        risk_notes.append("本次召回中没有明显的硬性约束条目；涉及原作边界时建议检查正式知识库或提高资料参考强度。")
    if conflicts:
        risk_notes.append("本次召回包含已保存冲突裁决，生成时应优先遵守裁决结论。")
    if scope_counts.get("canon", 0) or scope_counts.get("reference", 0):
        risk_notes.append("本次包含原作/参考资料证据，适合用于校验角色、事件和设定边界。")

    return {
        "hit_count": len(hits),
        "source_type_counts": source_type_counts,
        "scope_counts": scope_counts,
        "priority_sources": priority_sources[:8],
        "constraints": constraints[:5],
        "conflicts": conflicts[:5],
        "risk_notes": risk_notes,
    }


def evaluate_retrieval_case(project_name: str, case: dict) -> dict:
    expected_terms = [str(item).strip() for item in case.get("expected_terms", []) if str(item).strip()]
    expected_chunk_ids = [str(item).strip() for item in case.get("expected_chunk_ids", []) if str(item).strip()]
    expected_source_types = [str(item).strip() for item in case.get("expected_source_types", []) if str(item).strip()]
    hits = retrieve_context(
        project_name,
        str(case.get("query") or ""),
        top_k=int(case.get("top_k") or 6),
        allowed_scopes=case.get("allowed_scopes") or None,
        allowed_source_types=case.get("allowed_source_types") or None,
        retrieval_mode=str(case.get("retrieval_mode") or "hybrid"),
        retrieval_profile=str(case.get("retrieval_profile") or "") or None,
        worldline_id=str(case.get("worldline_id") or "") or None,
        worldline_mode=str(case.get("worldline_mode") or "prefer"),
    )
    hit_payloads = [hit.model_dump() for hit in hits]
    matched_terms = []
    for term in expected_terms:
        needle = term.lower()
        if any(
            needle in str(hit.chunk.title or "").lower()
            or needle in str(hit.chunk.content or "").lower()
            or needle in " ".join(hit.matched_terms).lower()
            for hit in hits
        ):
            matched_terms.append(term)
    hit_chunk_ids = [hit.chunk.chunk_id for hit in hits]
    hit_source_types = [hit.chunk.source_type for hit in hits]
    matched_chunk_ids = [chunk_id for chunk_id in expected_chunk_ids if chunk_id in hit_chunk_ids]
    matched_source_types = [source_type for source_type in expected_source_types if source_type in hit_source_types]
    matched_count = len(matched_terms) + len(matched_chunk_ids) + len(matched_source_types)
    expectation_count = len(expected_terms) + len(expected_chunk_ids) + len(expected_source_types)
    min_expected_matches = max(1, int(case.get("min_expected_matches") or 1))
    passed = expectation_count > 0 and matched_count >= min_expected_matches
    top_hit = hits[0] if hits else None
    return {
        "case_id": case.get("case_id", ""),
        "name": case.get("name", ""),
        "query": case.get("query", ""),
        "passed": passed,
        "matched_count": matched_count,
        "expectation_count": expectation_count,
        "min_expected_matches": min_expected_matches,
        "matched_terms": matched_terms,
        "matched_chunk_ids": matched_chunk_ids,
        "matched_source_types": matched_source_types,
        "hit_count": len(hits),
        "top_hit": top_hit.model_dump() if top_hit else {},
        "hits": hit_payloads,
        "briefing": build_retrieval_briefing(hits),
    }


def run_retrieval_eval_cases(project_name: str, cases: list[dict], note: str = "") -> dict:
    active_cases = [
        case for case in cases
        if str(case.get("status") or "active") == "active" and str(case.get("query") or "").strip()
    ]
    results = []
    for case in active_cases:
        try:
            results.append(evaluate_retrieval_case(project_name, case))
        except Exception as exc:
            results.append({
                "case_id": case.get("case_id", ""),
                "name": case.get("name", ""),
                "query": case.get("query", ""),
                "passed": False,
                "error": str(exc),
                "matched_count": 0,
                "expectation_count": 0,
                "hits": [],
            })
    passed_count = sum(1 for item in results if item.get("passed"))
    return append_retrieval_eval_run(project_name, {
        "note": note,
        "case_count": len(active_cases),
        "passed_count": passed_count,
        "failed_count": len(active_cases) - passed_count,
        "pass_rate": (passed_count / len(active_cases)) if active_cases else 0,
        "results": results,
    })
