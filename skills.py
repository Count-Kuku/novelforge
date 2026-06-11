import json
import re
from llm import call_llm
from pydantic import ValidationError
from prompts import (
    character_analysis_prompt,
    consistency_check_prompt,
    foreshadowing_analysis_prompt,
    format_rules_for_prompt,
    merge_retrieval_context,
    outline_prompt,
    chapter_outline_prompt,
    timeline_analysis_prompt,
    write_chapter_prompt,
    update_memory_prompt,
    review_chapter_prompt,
    compact_memory_prompt,
)
from memory import (
    chapter_count,
    get_recent_chapter_summaries,
    load_chapter_outline,
    load_global_rules,
    load_memory,
    load_outline,
    load_project_rules,
    save_chapter,
    save_chapter_outline,
    save_global_rules,
    save_analysis_report,
    save_memory,
    save_outline,
    save_project_rules,
    save_review,
    save_review_json,
)
from schemas import (
    ChapterPipelineState,
    CharacterAnalysisResult,
    ConsistencyAnalysisResult,
    ForeshadowingAnalysisResult,
    WorkflowError,
    WorkflowPipelineResult,
    WorkflowStepResult,
    RetrievalConflict,
    ReviewResult,
    TimelineAnalysisResult,
    ValidationStatus,
    format_schema_validation_error,
    render_character_analysis_markdown,
    render_consistency_analysis_markdown,
    render_foreshadowing_analysis_markdown,
    render_timeline_analysis_markdown,
    validate_memory_update_result,
    validate_review_result,
)
from retrieval import format_retrieval_context, retrieve_context


_LAST_RETRIEVAL_TRACES: dict[str, list[dict]] = {}


def _set_retrieval_trace(trace_key: str | None, hits: list) -> None:
    if not trace_key:
        return
    _LAST_RETRIEVAL_TRACES[trace_key] = [hit.model_dump() for hit in hits]


def get_retrieval_trace(trace_key: str) -> list[dict]:
    return list(_LAST_RETRIEVAL_TRACES.get(trace_key, []))


def _make_validation_status(
    status: str = "not_applicable",
    schema_name: str = "",
    message: str = "",
    errors: list[str] | None = None,
) -> ValidationStatus:
    return ValidationStatus(
        status=status,
        schema_name=schema_name,
        message=message,
        errors=errors or [],
    )


def _make_step_result(
    step_name: str,
    *,
    success: bool,
    status: str,
    data: dict | None = None,
    error: str = "",
    warnings: list[str] | None = None,
    retrieval_hits: list[dict] | None = None,
    validation: ValidationStatus | None = None,
    artifacts: dict | None = None,
) -> WorkflowStepResult:
    return WorkflowStepResult(
        step_name=step_name,
        success=success,
        status=status,
        data=data or {},
        error=error,
        warnings=warnings or [],
        retrieval_hits=retrieval_hits or [],
        validation=validation or _make_validation_status(),
        artifacts=artifacts or {},
    )


def _record_pipeline_step(state: ChapterPipelineState, step_result: WorkflowStepResult) -> None:
    state.steps[step_result.step_name] = step_result
    if step_result.status == "completed":
        if step_result.step_name not in state.completed_steps:
            state.completed_steps.append(step_result.step_name)
    elif step_result.status in {"failed", "rejected"}:
        if step_result.step_name not in state.failed_steps:
            state.failed_steps.append(step_result.step_name)
    elif step_result.status == "skipped":
        warning = step_result.warnings[0] if step_result.warnings else f"{step_result.step_name} skipped."
        state.warnings.append(warning)


def _record_pipeline_error(
    state: ChapterPipelineState,
    *,
    step_name: str,
    message: str,
    error_type: str = "unknown",
    recoverable: bool = True,
) -> None:
    state.errors.append(WorkflowError(
        step_name=step_name,
        error_type=error_type,
        message=message,
        recoverable=recoverable,
    ))


def _halt_pipeline(state: ChapterPipelineState, reason: str) -> None:
    state.halted = True
    state.halt_reason = reason


def _group_hits_by_scope_and_type(hits: list[dict]) -> dict[str, dict[str, list[dict]]]:
    grouped: dict[str, dict[str, list[dict]]] = {}
    for hit in hits:
        chunk = hit.get("chunk", {})
        scope = chunk.get("scope", "project") or "project"
        source_type = chunk.get("source_type", "unknown") or "unknown"
        grouped.setdefault(scope, {}).setdefault(source_type, []).append(hit)
    return grouped


def _conflict_severity(project_hit: dict, external_hit: dict, overlap: set[str]) -> tuple[str, str]:
    project_chunk = project_hit.get("chunk", {})
    external_chunk = external_hit.get("chunk", {})
    project_authority = str(project_chunk.get("metadata", {}).get("authority", "project") or "project")
    external_authority = str(external_chunk.get("metadata", {}).get("authority", "unknown") or "unknown")
    project_type = project_chunk.get("source_type", "")
    external_type = external_chunk.get("source_type", "")

    if project_authority == "project" and external_authority == "official":
        return "high", "Project truth overlaps with official external evidence on the same retrieval terms."
    if project_type != external_type and len(overlap) >= 2:
        return "medium", "Project and external evidence overlap across multiple retrieval terms but come from different evidence categories."
    return "low", "Project and external evidence share retrieval terms and may need manual comparison."


def _detect_potential_conflicts(hits: list[dict], limit: int = 4) -> list[RetrievalConflict]:
    project_hits = []
    external_hits = []
    for hit in hits:
        chunk = hit.get("chunk", {})
        scope = chunk.get("scope", "project") or "project"
        if scope == "project":
            project_hits.append(hit)
        else:
            external_hits.append(hit)

    conflicts = []
    seen = set()
    for project_hit in project_hits:
        project_chunk = project_hit.get("chunk", {})
        project_terms = set(hit_term.lower() for hit_term in project_hit.get("matched_terms", []))
        if not project_terms:
            continue
        for external_hit in external_hits:
            external_chunk = external_hit.get("chunk", {})
            external_terms = set(hit_term.lower() for hit_term in external_hit.get("matched_terms", []))
            if not external_terms:
                continue
            overlap = project_terms & external_terms
            if not overlap:
                continue

            project_type = project_chunk.get("source_type", "")
            external_type = external_chunk.get("source_type", "")
            project_authority = str(project_chunk.get("metadata", {}).get("authority", "project") or "project")
            external_authority = str(external_chunk.get("metadata", {}).get("authority", "unknown") or "unknown")
            if project_type == external_type and project_authority == external_authority:
                continue

            key = (
                project_chunk.get("title", project_type),
                external_chunk.get("title", external_type),
                tuple(sorted(overlap)),
            )
            if key in seen:
                continue
            seen.add(key)

            severity, rationale = _conflict_severity(project_hit, external_hit, overlap)
            conflicts.append(RetrievalConflict(
                shared_terms=sorted(overlap),
                project_hit=project_hit,
                external_hit=external_hit,
                project_authority=project_authority,
                external_authority=external_authority,
                severity=severity,
                rationale=rationale,
            ))
            if len(conflicts) >= limit:
                return conflicts
    return conflicts


def detect_potential_conflicts(hits: list[dict], limit: int = 4) -> list[dict]:
    return [conflict.model_dump() for conflict in _detect_potential_conflicts(hits, limit=limit)]


def _select_supporting_sources(hits: list[dict], limit: int = 4) -> list[dict]:
    selected = []
    seen = set()
    for hit in hits:
        chunk = hit.get("chunk", {})
        key = (
            chunk.get("source_type", ""),
            chunk.get("scope", ""),
            chunk.get("title", ""),
            chunk.get("path", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        selected.append(hit)
        if len(selected) >= limit:
            break
    return selected


def _format_supporting_sources_markdown(hits: list[dict], title: str = "Supporting Sources") -> str:
    selected = _select_supporting_sources(hits)
    if not selected:
        return ""

    grouped = _group_hits_by_scope_and_type(selected)
    scope_order = ["project", "canon", "reference"]
    scope_labels = {
        "project": "Project Sources",
        "canon": "Canon Sources",
        "reference": "Reference Sources",
    }

    lines = [f"## {title}", ""]
    item_index = 1
    for scope in scope_order:
        source_groups = grouped.get(scope)
        if not source_groups:
            continue
        lines.append(f"### {scope_labels.get(scope, scope.title())}")
        lines.append("")
        for source_type, source_hits in source_groups.items():
            lines.append(f"- {source_type}")
            for hit in source_hits:
                chunk = hit.get("chunk", {})
                authority = str(chunk.get("metadata", {}).get("authority", "unknown") or "unknown")
                detail = f"  - [{item_index}]"
                if chunk.get("title"):
                    detail += f" {chunk.get('title')}"
                else:
                    detail += f" {source_type}"
                if chunk.get("chapter_no") is not None:
                    detail += f" / chapter {int(chunk.get('chapter_no')):03d}"
                detail += f" / authority={authority}"
                detail += f" / score={hit.get('score', 0):.2f}"
                lines.append(detail)
                item_index += 1
            lines.append("")
    return "\n".join(lines)


def _format_potential_conflicts_markdown(hits: list[dict], title: str = "Potential Conflicts") -> str:
    conflicts = _detect_potential_conflicts(hits)
    if not conflicts:
        return ""

    lines = [f"## {title}", ""]
    for index, conflict in enumerate(conflicts, start=1):
        shared_terms = ", ".join(conflict.shared_terms) or "(无)"
        project_chunk = conflict.project_hit.chunk.model_dump()
        external_chunk = conflict.external_hit.chunk.model_dump()
        lines.append(f"- [{index}] severity={conflict.severity} / shared_terms={shared_terms}")
        lines.append(
            f"  - project: {project_chunk.get('source_type', 'unknown')} / {project_chunk.get('title', 'untitled')} / authority={conflict.project_authority}"
        )
        lines.append(
            f"  - external: {external_chunk.get('scope', 'reference')} / {external_chunk.get('source_type', 'unknown')} / {external_chunk.get('title', 'untitled')} / authority={conflict.external_authority}"
        )
        lines.append(f"  - rationale: {conflict.rationale}")
    return "\n".join(lines)


def _extract_json_object(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        return json.loads(match.group(0))


def _dedupe_list_items(items: list) -> list:
    seen = set()
    result = []

    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)

    return result


def _build_rules_text(project_name: str, scope: str) -> str:
    global_rules = load_global_rules()
    project_rules = load_project_rules(project_name)
    return format_rules_for_prompt(global_rules, project_rules, scope)


def _build_retrieval_context(
    project_name: str,
    query: str,
    *,
    allowed_source_types: list[str] | None = None,
    allowed_scopes: list[str] | None = None,
    top_k: int = 6,
    retrieval_mode: str = "hybrid",
    trace_key: str | None = None,
) -> str:
    hits = retrieve_context(
        project_name,
        query,
        top_k=top_k,
        allowed_scopes=allowed_scopes,
        allowed_source_types=allowed_source_types,
        retrieval_mode=retrieval_mode,
    )
    _set_retrieval_trace(trace_key, hits)
    return format_retrieval_context(hits)


def _call_analysis(prompt: str, empty_error: str) -> str:
    result = call_llm(prompt)
    if not result.strip():
        raise RuntimeError(empty_error)
    return result


def _call_json_llm(prompt: str, empty_error: str) -> dict:
    result = call_llm(prompt)
    if not result.strip():
        raise RuntimeError(empty_error)
    return _extract_json_object(result)


def _extract_rule_lines(text: str) -> list[str]:
    candidates = []
    for line in text.splitlines():
        cleaned = line.strip().lstrip("-*	 ").strip()
        if cleaned:
            candidates.append(cleaned)

    if not candidates and text.strip():
        candidates = [segment.strip() for segment in re.split(r"[\n;；]+", text) if segment.strip()]

    seen = set()
    result = []
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def save_rule_text(project_name: str, scope: str, target: str, rule_text: str) -> dict:
    if target not in {"global", "project"}:
        raise ValueError("Rule target must be 'global' or 'project'.")

    rules = load_global_rules() if target == "global" else load_project_rules(project_name)
    if scope not in rules:
        raise ValueError(f"Unknown rule scope: {scope}")

    new_rules = _extract_rule_lines(rule_text)
    if not new_rules:
        return {"status": "ignored", "reason": "empty_rule"}

    existing = rules.get(scope, [])
    merged = []
    seen = set()
    for item in existing + new_rules:
        if item in seen:
            continue
        seen.add(item)
        merged.append(item)

    rules[scope] = merged

    if target == "global":
        save_global_rules(rules)
    else:
        save_project_rules(project_name, rules)

    return {
        "status": "saved",
        "target": target,
        "scope": scope,
        "saved_rules": new_rules,
        "total_rules": len(merged),
    }


def _format_review_markdown(review: ReviewResult | dict) -> str:
    if isinstance(review, ReviewResult):
        review = review.model_dump()

    strengths = "\n".join([f"- {item}" for item in review["strengths"]]) or "- 无"
    issues = "\n".join([f"- {item}" for item in review["issues"]]) or "- 无"

    return f"""# Chapter Review

Status: `{review['status']}`

## Summary

{review['summary'] or '无'}

## Strengths

{strengths}

## Issues

{issues}

## Consistency Checks

- Characters: {review['consistency_checks']['characters'] or '无'}
- World: {review['consistency_checks']['world'] or '无'}
- Timeline: {review['consistency_checks']['timeline'] or '无'}
- Foreshadowing: {review['consistency_checks']['foreshadowing'] or '无'}

## Pacing

{review['pacing'] or '无'}

## Next Action

{review['next_action'] or '无'}
"""

def generate_outline(project_name: str, user_idea: str) -> dict:
    memory = load_memory(project_name)
    trace_key = f"outline:{project_name}"
    retrieval_context = _build_retrieval_context(
        project_name,
        user_idea,
        allowed_source_types=["outline", "memory_character", "memory_world", "memory_timeline", "memory_foreshadowing", "external_source"],
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        outline_prompt(memory, user_idea, _build_rules_text(project_name, "outline")),
        retrieval_context,
    )
    outline = call_llm(prompt)
    if not outline.strip():
        raise RuntimeError("LLM returned empty outline.")
    save_outline(project_name, outline)
    return _make_step_result(
        "outline",
        success=True,
        status="completed",
        data={"outline": outline},
        retrieval_hits=get_retrieval_trace(trace_key),
        artifacts={"saved_path": f"data/projects/{project_name}/outline.md"},
    ).model_dump()

def generate_chapter_outline(
    project_name: str,
    chapter_no: int,
    user_requirement: str
) -> dict:
    memory = load_memory(project_name)
    outline = load_outline(project_name)
    trace_key = f"chapter_outline:{project_name}:{chapter_no}"
    recent_summaries = get_recent_chapter_summaries(project_name)
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章 {user_requirement} {outline}",
        allowed_source_types=[
            "outline",
            "chapter_summary",
            "chapter_outline",
            "memory_character",
            "memory_world",
            "memory_timeline",
            "memory_foreshadowing",
            "external_source",
        ],
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(chapter_outline_prompt(
        memory,
        outline,
        recent_summaries,
        chapter_no,
        user_requirement,
        _build_rules_text(project_name, "chapter_outline"),
    ), retrieval_context)
    outline = call_llm(prompt)
    if not outline.strip():
        raise RuntimeError("LLM returned empty chapter outline.")
    save_chapter_outline(project_name, chapter_no, outline)
    return _make_step_result(
        "chapter_outline",
        success=True,
        status="completed",
        data={"chapter_outline": outline},
        retrieval_hits=get_retrieval_trace(trace_key),
        artifacts={"saved_path": f"data/projects/{project_name}/chapter_outlines/chapter_{chapter_no:03d}.md"},
    ).model_dump()

def write_chapter(
    project_name: str,
    chapter_no: int,
    chapter_outline: str,
    word_count: str = "2000-2500"
) -> dict:
    memory = load_memory(project_name)
    trace_key = f"write:{project_name}:{chapter_no}"
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章 {chapter_outline}",
        allowed_source_types=[
            "chapter_summary",
            "chapter_outline",
            "chapter_content",
            "memory_character",
            "memory_world",
            "memory_timeline",
            "memory_foreshadowing",
            "review_issue",
            "analysis_consistency",
            "analysis_characters",
            "analysis_timeline",
            "analysis_foreshadowing",
            "external_source",
        ],
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        write_chapter_prompt(memory, chapter_outline, word_count, _build_rules_text(project_name, "write")),
        retrieval_context,
    )
    chapter = call_llm(prompt)
    if not chapter.strip():
        raise RuntimeError("LLM returned empty chapter content.")
    save_chapter(project_name, chapter_no, chapter)
    return _make_step_result(
        "write_chapter",
        success=True,
        status="completed",
        data={"chapter": chapter},
        retrieval_hits=get_retrieval_trace(trace_key),
        artifacts={"saved_path": f"data/projects/{project_name}/chapters/chapter_{chapter_no:03d}.md"},
    ).model_dump()

def update_memory_from_chapter(
    project_name: str,
    chapter_no: int,
    chapter: str
) -> dict:
    memory = load_memory(project_name)
    trace_key = f"memory_update:{project_name}:{chapter_no}"
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章设定更新 {chapter}",
        allowed_source_types=["memory_character", "memory_world", "memory_timeline", "memory_foreshadowing", "chapter_summary", "external_source"],
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        update_memory_prompt(memory, chapter, _build_rules_text(project_name, "memory_update")),
        retrieval_context,
    )
    result = call_llm(prompt)
    retrieval_hits = get_retrieval_trace(trace_key)

    try:
        updates = validate_memory_update_result(_extract_json_object(result), chapter_no)
    except ValidationError as exc:
        reason = format_schema_validation_error(exc)
        return _make_step_result(
            "memory_update",
            success=False,
            status="rejected",
            error=reason,
            retrieval_hits=retrieval_hits,
            validation=_make_validation_status(
                status="failed",
                schema_name="MemoryUpdateResult",
                message="Memory update payload validation failed.",
                errors=[reason],
            ),
            artifacts={"raw_response": result},
        ).model_dump()
    except Exception as exc:
        return _make_step_result(
            "memory_update",
            success=False,
            status="rejected",
            error=str(exc),
            retrieval_hits=retrieval_hits,
            validation=_make_validation_status(
                status="failed",
                schema_name="MemoryUpdateResult",
                message="Memory update payload extraction failed.",
                errors=[str(exc)],
            ),
            artifacts={"raw_response": result},
        ).model_dump()

    update_data = updates.model_dump()

    memory["world"].extend(update_data["world_updates"])
    memory["characters"].extend(update_data["new_characters"])
    memory["timeline"].extend(update_data["timeline_updates"])
    memory["foreshadowing"].extend(update_data["foreshadowing_updates"])
    memory["world"] = _dedupe_list_items(memory["world"])
    memory["characters"] = _dedupe_list_items(memory["characters"])
    memory["timeline"] = _dedupe_list_items(memory["timeline"])
    memory["foreshadowing"] = _dedupe_list_items(memory["foreshadowing"])

    memory["chapter_summaries"] = [
        item for item in memory["chapter_summaries"]
        if not isinstance(item, dict) or item.get("chapter_no") != chapter_no
    ]
    memory["chapter_summaries"].append({
        "chapter_no": update_data["chapter_no"],
        "summary": update_data["chapter_summary"]
    })

    save_memory(project_name, memory)
    return _make_step_result(
        "memory_update",
        success=True,
        status="completed",
        data={"applied_updates": update_data},
        retrieval_hits=retrieval_hits,
        validation=_make_validation_status(
            status="passed",
            schema_name="MemoryUpdateResult",
            message="Memory update payload validated and applied.",
        ),
        artifacts={"memory_saved": True},
    ).model_dump()


def review_chapter(project_name: str, chapter_no: int, chapter: str) -> dict:
    memory = load_memory(project_name)
    chapter_outline = load_chapter_outline(project_name, chapter_no)
    trace_key = f"review:{project_name}:{chapter_no}"
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章审阅 {chapter_outline} {chapter}",
        allowed_source_types=[
            "chapter_summary",
            "chapter_outline",
            "chapter_content",
            "memory_character",
            "memory_world",
            "memory_timeline",
            "memory_foreshadowing",
            "review_issue",
            "review_timeline_check",
            "review_foreshadowing_check",
            "analysis_consistency",
            "analysis_characters",
            "analysis_timeline",
            "analysis_foreshadowing",
            "external_source",
        ],
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        review_chapter_prompt(memory, chapter_outline, chapter, _build_rules_text(project_name, "review")),
        retrieval_context,
    )
    result = call_llm(prompt)
    retrieval_hits = get_retrieval_trace(trace_key)

    try:
        review = validate_review_result(_extract_json_object(result))
    except ValidationError as exc:
        reason = format_schema_validation_error(exc)
        fallback_review = ReviewResult(
            status="blocked",
            summary=f"审阅结果解析失败：{reason}",
            strengths=[],
            issues=["模型未按要求返回合法 Schema 的审阅结果。"],
            pacing="未知",
            next_action="检查原始审阅结果并重新生成。",
        )
        sources_md = _format_supporting_sources_markdown(retrieval_hits)
        conflict_md = _format_potential_conflicts_markdown(retrieval_hits)
        markdown = _format_review_markdown(fallback_review)
        if sources_md:
            markdown += f"\n\n{sources_md}"
        if conflict_md:
            markdown += f"\n\n{conflict_md}"
        markdown += f"\n\n## Raw Response\n\n```text\n{result}\n```"
        save_review_json(project_name, chapter_no, fallback_review.model_dump())
        save_review(project_name, chapter_no, markdown)
        return _make_step_result(
            "review_chapter",
            success=False,
            status="rejected",
            data={
                "review": fallback_review.model_dump(),
                "review_markdown": markdown,
            },
            error=reason,
            warnings=["Review markdown fallback was generated and persisted."],
            retrieval_hits=retrieval_hits,
            validation=_make_validation_status(
                status="failed",
                schema_name="ReviewResult",
                message="Review payload schema validation failed.",
                errors=[reason],
            ),
            artifacts={"review_saved": True, "raw_response": result},
        ).model_dump()
    except Exception as exc:
        fallback_review = ReviewResult(
            status="blocked",
            summary=f"审阅结果解析失败：{exc}",
            strengths=[],
            issues=["模型未按要求返回合法 JSON 审阅结果。"],
            pacing="未知",
            next_action="检查原始审阅结果并重新生成。",
        )
        sources_md = _format_supporting_sources_markdown(retrieval_hits)
        conflict_md = _format_potential_conflicts_markdown(retrieval_hits)
        markdown = _format_review_markdown(fallback_review)
        if sources_md:
            markdown += f"\n\n{sources_md}"
        if conflict_md:
            markdown += f"\n\n{conflict_md}"
        markdown += f"\n\n## Raw Response\n\n```text\n{result}\n```"
        save_review_json(project_name, chapter_no, fallback_review.model_dump())
        save_review(project_name, chapter_no, markdown)
        return _make_step_result(
            "review_chapter",
            success=False,
            status="rejected",
            data={
                "review": fallback_review.model_dump(),
                "review_markdown": markdown,
            },
            error=str(exc),
            warnings=["Review markdown fallback was generated and persisted."],
            retrieval_hits=retrieval_hits,
            validation=_make_validation_status(
                status="failed",
                schema_name="ReviewResult",
                message="Review payload extraction failed.",
                errors=[str(exc)],
            ),
            artifacts={"review_saved": True, "raw_response": result},
        ).model_dump()

    sources_md = _format_supporting_sources_markdown(retrieval_hits)
    conflict_md = _format_potential_conflicts_markdown(retrieval_hits)
    markdown = _format_review_markdown(review)
    if sources_md:
        markdown += f"\n\n{sources_md}"
    if conflict_md:
        markdown += f"\n\n{conflict_md}"
    save_review_json(project_name, chapter_no, review.model_dump())
    save_review(project_name, chapter_no, markdown)
    return _make_step_result(
        "review_chapter",
        success=True,
        status="completed",
        data={
            "review": review.model_dump(),
            "review_markdown": markdown,
        },
        retrieval_hits=retrieval_hits,
        validation=_make_validation_status(
            status="passed",
            schema_name="ReviewResult",
            message="Review payload validated and persisted.",
        ),
        artifacts={"review_saved": True},
    ).model_dump()


def compact_memory(project_name: str) -> dict:
    memory = load_memory(project_name)
    count = chapter_count(project_name)
    prompt = compact_memory_prompt(memory, count)
    result = call_llm(prompt)

    try:
        updates = _extract_json_object(result)
        save_memory(project_name, updates)
        return {"status": "accepted"}
    except Exception as exc:
        return {"status": "rejected", "reason": str(exc), "raw_response": result}


def _run_analysis(
    prompt: str,
    empty_error: str,
    schema,
    renderer,
) -> tuple[object, str]:
    payload = _call_json_llm(prompt, empty_error)
    try:
        result = schema.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"Analysis schema validation failed: {format_schema_validation_error(exc)}") from exc
    return result, renderer(result)


def _finalize_analysis_step(
    step_name: str,
    analysis_type: str,
    project_name: str,
    chapter_no: int,
    result_model,
    markdown: str,
    trace_key: str,
    schema_name: str,
) -> dict:
    retrieval_hits = get_retrieval_trace(trace_key)
    sources_md = _format_supporting_sources_markdown(retrieval_hits)
    conflict_md = _format_potential_conflicts_markdown(retrieval_hits)
    report_markdown = markdown
    if sources_md:
        report_markdown = f"{report_markdown}\n\n{sources_md}"
    if conflict_md:
        report_markdown = f"{report_markdown}\n\n{conflict_md}"

    save_analysis_report(project_name, analysis_type, chapter_no, report_markdown)
    return _make_step_result(
        step_name,
        success=True,
        status="completed",
        data={
            "analysis": result_model.model_dump(),
            "report_markdown": report_markdown,
            "analysis_type": analysis_type,
        },
        retrieval_hits=retrieval_hits,
        validation=_make_validation_status(
            status="passed",
            schema_name=schema_name,
            message="Analysis payload validated and report persisted.",
        ),
        artifacts={
            "report_saved": True,
            "saved_path": f"data/projects/{project_name}/analysis/{analysis_type}_chapter_{chapter_no:03d}.md",
        },
    ).model_dump()


def analyze_characters(project_name: str, chapter_no: int, chapter: str) -> dict:
    memory = load_memory(project_name)
    trace_key = f"analysis:characters:{project_name}:{chapter_no}"
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章角色分析 {chapter}",
        allowed_source_types=["chapter_summary", "chapter_content", "memory_character", "review_issue", "analysis_characters", "external_source"],
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        character_analysis_prompt(memory, chapter, _build_rules_text(project_name, "review")),
        retrieval_context,
    )
    result_model, markdown = _run_analysis(
        prompt,
        "LLM returned empty character analysis.",
        CharacterAnalysisResult,
        render_character_analysis_markdown,
    )
    return _finalize_analysis_step(
        "analysis_characters",
        "characters",
        project_name,
        chapter_no,
        result_model,
        markdown,
        trace_key,
        "CharacterAnalysisResult",
    )


def analyze_timeline(project_name: str, chapter_no: int, chapter: str) -> dict:
    memory = load_memory(project_name)
    trace_key = f"analysis:timeline:{project_name}:{chapter_no}"
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章时间线分析 {chapter}",
        allowed_source_types=["chapter_summary", "chapter_content", "memory_timeline", "review_timeline_check", "analysis_timeline", "external_source"],
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        timeline_analysis_prompt(memory, chapter, _build_rules_text(project_name, "review")),
        retrieval_context,
    )
    result_model, markdown = _run_analysis(
        prompt,
        "LLM returned empty timeline analysis.",
        TimelineAnalysisResult,
        render_timeline_analysis_markdown,
    )
    return _finalize_analysis_step(
        "analysis_timeline",
        "timeline",
        project_name,
        chapter_no,
        result_model,
        markdown,
        trace_key,
        "TimelineAnalysisResult",
    )


def analyze_foreshadowing(project_name: str, chapter_no: int, chapter: str) -> dict:
    memory = load_memory(project_name)
    trace_key = f"analysis:foreshadowing:{project_name}:{chapter_no}"
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章伏笔分析 {chapter}",
        allowed_source_types=["chapter_summary", "chapter_content", "memory_foreshadowing", "review_foreshadowing_check", "analysis_foreshadowing", "external_source"],
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        foreshadowing_analysis_prompt(memory, chapter, _build_rules_text(project_name, "review")),
        retrieval_context,
    )
    result_model, markdown = _run_analysis(
        prompt,
        "LLM returned empty foreshadowing analysis.",
        ForeshadowingAnalysisResult,
        render_foreshadowing_analysis_markdown,
    )
    return _finalize_analysis_step(
        "analysis_foreshadowing",
        "foreshadowing",
        project_name,
        chapter_no,
        result_model,
        markdown,
        trace_key,
        "ForeshadowingAnalysisResult",
    )


def run_consistency_check(project_name: str, chapter_no: int, chapter: str) -> dict:
    memory = load_memory(project_name)
    trace_key = f"analysis:consistency:{project_name}:{chapter_no}"
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章一致性检查 {chapter}",
        allowed_source_types=[
            "chapter_summary",
            "chapter_content",
            "memory_character",
            "memory_world",
            "memory_timeline",
            "memory_foreshadowing",
            "review_issue",
            "analysis_characters",
            "analysis_timeline",
            "analysis_foreshadowing",
            "external_source",
        ],
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        consistency_check_prompt(memory, chapter, _build_rules_text(project_name, "review")),
        retrieval_context,
    )
    result_model, markdown = _run_analysis(
        prompt,
        "LLM returned empty consistency check.",
        ConsistencyAnalysisResult,
        render_consistency_analysis_markdown,
    )
    return _finalize_analysis_step(
        "analysis_consistency",
        "consistency",
        project_name,
        chapter_no,
        result_model,
        markdown,
        trace_key,
        "ConsistencyAnalysisResult",
    )


def pipeline_plan_write_review_update(
    project_name: str,
    chapter_no: int,
    user_requirement: str,
    word_count: str = "2000-2500"
) -> dict:
    state = ChapterPipelineState(
        project_name=project_name,
        chapter_no=chapter_no,
        user_requirement=user_requirement,
        word_count=word_count,
        current_step="chapter_outline",
    )

    try:
        outline = generate_chapter_outline(project_name, chapter_no, user_requirement)
        outline_step = WorkflowStepResult.model_validate(outline)
    except Exception as exc:
        outline_step = _make_step_result(
            "chapter_outline",
            success=False,
            status="failed",
            error=str(exc),
            retrieval_hits=get_retrieval_trace(f"chapter_outline:{project_name}:{chapter_no}"),
        )
        _record_pipeline_error(state, step_name="chapter_outline", message=str(exc), error_type="llm")

    _record_pipeline_step(state, outline_step)
    state.chapter_outline = outline_step.data.get("chapter_outline", "")

    if outline_step.success:
        state.current_step = "write_chapter"
        try:
            chapter = write_chapter(project_name, chapter_no, state.chapter_outline, word_count)
            chapter_step = WorkflowStepResult.model_validate(chapter)
        except Exception as exc:
            chapter_step = _make_step_result(
                "write_chapter",
                success=False,
                status="failed",
                error=str(exc),
                retrieval_hits=get_retrieval_trace(f"write:{project_name}:{chapter_no}"),
            )
            _record_pipeline_error(state, step_name="write_chapter", message=str(exc), error_type="llm")
    else:
        chapter_step = _make_step_result(
            "write_chapter",
            success=False,
            status="skipped",
            warnings=["Skipped because chapter outline step did not complete successfully."],
            retrieval_hits=get_retrieval_trace(f"write:{project_name}:{chapter_no}"),
        )
        _halt_pipeline(state, "chapter_outline_failed")

    _record_pipeline_step(state, chapter_step)
    state.chapter = chapter_step.data.get("chapter", "")

    if chapter_step.success:
        state.current_step = "review_chapter"
        try:
            review_step_data = review_chapter(project_name, chapter_no, state.chapter)
            review_step = WorkflowStepResult.model_validate(review_step_data)
        except Exception as exc:
            review_step = _make_step_result(
                "review_chapter",
                success=False,
                status="failed",
                error=str(exc),
                retrieval_hits=get_retrieval_trace(f"review:{project_name}:{chapter_no}"),
            )
            _record_pipeline_error(state, step_name="review_chapter", message=str(exc), error_type="llm")
    else:
        review_step = _make_step_result(
            "review_chapter",
            success=False,
            status="skipped",
            warnings=["Skipped because chapter writing step did not complete successfully."],
            retrieval_hits=get_retrieval_trace(f"review:{project_name}:{chapter_no}"),
        )
        if not state.halted:
            _halt_pipeline(state, "write_chapter_failed")

    _record_pipeline_step(state, review_step)
    state.review = review_step.data.get("review", {})
    state.review_markdown = review_step.data.get("review_markdown", "")

    if chapter_step.success:
        state.current_step = "memory_update"
        try:
            memory_step_data = update_memory_from_chapter(project_name, chapter_no, state.chapter)
            memory_step = WorkflowStepResult.model_validate(memory_step_data)
        except Exception as exc:
            memory_step = _make_step_result(
                "memory_update",
                success=False,
                status="failed",
                error=str(exc),
                retrieval_hits=get_retrieval_trace(f"memory_update:{project_name}:{chapter_no}"),
            )
            _record_pipeline_error(state, step_name="memory_update", message=str(exc), error_type="llm")
    else:
        memory_step = _make_step_result(
            "memory_update",
            success=False,
            status="skipped",
            warnings=["Skipped because chapter writing step did not complete successfully."],
            retrieval_hits=get_retrieval_trace(f"memory_update:{project_name}:{chapter_no}"),
        )
        if not state.halted:
            _halt_pipeline(state, "write_chapter_failed")

    _record_pipeline_step(state, memory_step)
    state.memory_update = memory_step.data.get("applied_updates", {})

    state.current_step = "completed" if not state.halted else state.current_step
    state.success = all(step.success for step in state.steps.values() if step.status != "skipped")

    pipeline_result = WorkflowPipelineResult(
        success=state.success,
        steps=state.steps,
        warnings=state.warnings,
    )
    result = state.model_dump()
    result["pipeline"] = pipeline_result.model_dump()
    return result
