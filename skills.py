import json
import re
from datetime import datetime
from urllib.request import Request, urlopen
from llm import call_llm
from pydantic import ValidationError
from prompts import (
    discuss_chapter_prompt,
    discuss_chapter_turn_prompt,
    discuss_arc_prompt,
    discuss_arc_turn_prompt,
    arc_chapter_plan_prompt,
    evaluate_chapter_prompt,
    discuss_outline_prompt,
    discuss_outline_turn_prompt,
    discuss_volume_prompt,
    discuss_volume_turn_prompt,
    creative_structure_prompt,
    extract_reference_knowledge_prompt,
    organize_reference_prompt,
    character_analysis_prompt,
    consistency_check_prompt,
    foreshadowing_analysis_prompt,
    format_rules_for_prompt,
    merge_retrieval_context,
    arc_outline_prompt,
    outline_prompt,
    chapter_outline_prompt,
    volume_outline_prompt,
    timeline_analysis_prompt,
    write_chapter_prompt,
    update_memory_prompt,
    review_chapter_prompt,
    compact_memory_prompt,
)
from memory import (
    chapter_count,
    delete_chapter_discussion_artifact,
    delete_arc_discussion_artifact,
    delete_outline_discussion_artifact,
    delete_volume_discussion_artifact,
    get_recent_chapter_summaries,
    load_chapter_discussion_artifact,
    load_arc_discussion_artifact,
    load_arc_metadata,
    load_arc_outline,
    load_chapter_outline,
    load_chapter_outline_metadata,
    load_creative_profile,
    load_global_rules,
    load_memory,
    load_outline,
    load_outline_discussion_artifact,
    load_pipeline_run,
    load_project_rules,
    load_volume_discussion_artifact,
    load_volume_outline,
    save_arc_metadata,
    save_arc_chapter_plan,
    save_arc_discussion_artifact,
    save_arc_outline,
    save_chapter,
    save_chapter_discussion_artifact,
    save_chapter_outline,
    save_chapter_outline_metadata,
    save_global_rules,
    save_analysis_report,
    save_conflict_resolution,
    save_evaluation_json,
    save_evaluation_report,
    save_memory,
    save_outline,
    save_pipeline_run,
    save_project_rules,
    save_review,
    save_review_json,
    save_outline_discussion_artifact,
    save_volume_metadata,
    save_volume_discussion_artifact,
    save_volume_outline,
)
from schemas import (
    ChapterWritingGuidance,
    ArcChapterPlanResult,
    ArcDiscussionResult,
    ChapterPipelineState,
    ChapterEvaluationResult,
    CharacterAnalysisResult,
    ChapterDiscussionResult,
    ConsistencyAnalysisResult,
    ForeshadowingAnalysisResult,
    OutlineDiscussionResult,
    KnowledgeExtractionResult,
    OrganizedReferenceResult,
    VolumeDiscussionResult,
    WorkflowError,
    WorkflowPipelineResult,
    WorkflowStepResult,
    WorkflowTransition,
    RetrievalConflict,
    ReviewResult,
    TimelineAnalysisResult,
    ValidationStatus,
    format_schema_validation_error,
    render_character_analysis_markdown,
    render_arc_chapter_plan_markdown,
    render_chapter_evaluation_markdown,
    render_consistency_analysis_markdown,
    render_foreshadowing_analysis_markdown,
    render_discussion_markdown,
    render_knowledge_extraction_markdown,
    render_organized_reference_markdown,
    render_timeline_analysis_markdown,
    validate_memory_update_result,
    validate_review_result,
)
from retrieval import format_retrieval_context, retrieve_context


_LAST_RETRIEVAL_TRACES: dict[str, list[dict]] = {}

SCOPE_LABELS = {
    "project": "项目资料",
    "canon": "原作资料",
    "reference": "参考资料",
}

AUTHORITY_LABELS = {
    "project": "项目设定",
    "official": "官方资料",
    "curated": "人工整理",
    "community": "社区资料",
    "unknown": "未标明",
}

SOURCE_TYPE_LABELS = {
    "outline": "全书大纲",
    "volume_outline": "分卷大纲",
    "arc_outline": "剧情段大纲",
    "arc_chapter_plan": "剧情段章节分配",
    "chapter_outline": "章节细纲",
    "chapter_content": "章节正文",
    "chapter_summary": "章节摘要",
    "review_issue": "审阅问题",
    "analysis_consistency": "一致性分析",
    "analysis_characters": "角色分析",
    "analysis_timeline": "时间线分析",
    "analysis_foreshadowing": "伏笔分析",
    "evaluation_chapter": "章节评估",
    "conflict_resolution": "冲突裁决",
    "memory_character": "角色设定",
    "memory_world": "世界观设定",
    "memory_au_rule": "改写规则",
    "memory_relationship": "角色关系",
    "memory_timeline": "时间线设定",
    "memory_foreshadowing": "伏笔设定",
    "memory_active_constraint": "当前硬性约束",
    "external_source": "通用外部资料",
    "knowledge_characters": "知识库：角色",
    "knowledge_items": "知识库：物品与道具",
    "knowledge_abilities": "知识库：技能与能力",
    "knowledge_world_rules": "知识库：世界观规则",
    "knowledge_locations": "知识库：地点",
    "knowledge_organizations": "知识库：组织",
    "knowledge_timeline_events": "知识库：事件与时间线",
    "knowledge_relationships": "知识库：角色关系",
    "knowledge_writing_style": "知识库：写作风格",
    "knowledge_dialogue_style": "知识库：对白风格",
    "knowledge_narrative_techniques": "知识库：写作手法",
    "knowledge_constraints": "知识库：硬性约束",
}

KNOWLEDGE_SOURCE_TYPES = [
    "knowledge_characters",
    "knowledge_items",
    "knowledge_abilities",
    "knowledge_world_rules",
    "knowledge_locations",
    "knowledge_organizations",
    "knowledge_timeline_events",
    "knowledge_relationships",
    "knowledge_writing_style",
    "knowledge_dialogue_style",
    "knowledge_narrative_techniques",
    "knowledge_constraints",
]

COMMON_RETRIEVAL_SOURCE_TYPES = [
    "outline",
    "outline_discussion",
    "volume_outline",
    "volume_discussion",
    "arc_outline",
    "arc_discussion",
    "arc_chapter_plan",
    "chapter_summary",
    "chapter_outline",
    "chapter_discussion",
    "chapter_content",
    "memory_character",
    "memory_world",
    "memory_au_rule",
    "memory_relationship",
    "memory_timeline",
    "memory_foreshadowing",
    "memory_active_constraint",
    "review_issue",
    "analysis_consistency",
    "analysis_characters",
    "analysis_timeline",
    "analysis_foreshadowing",
    "conflict_resolution",
    "external_source",
] + KNOWLEDGE_SOURCE_TYPES

KNOWN_WORKFLOW_DEPTHS = {"只生成正文", "短篇结构+正文", "章节计划+正文", "分卷/剧情段/章节", "完整长篇流程"}
LIGHTWEIGHT_STORY_KEYWORDS = {"短篇", "中篇", "番外", "续写", "前传", "穿越", "转生", "异世界", "平行世界", "AU", "补完", "补全", "片段", "场景"}


def _is_lightweight_story_profile(profile: dict) -> bool:
    story_mode = str(profile.get("story_mode", "") or "")
    target_length = str(profile.get("target_length", "") or "")
    combined = f"{story_mode} {target_length}"
    return any(keyword in combined for keyword in LIGHTWEIGHT_STORY_KEYWORDS)


def _label_scope(value: str) -> str:
    return SCOPE_LABELS.get(str(value or ""), str(value or "未知范围"))


def _label_authority(value: str) -> str:
    return AUTHORITY_LABELS.get(str(value or ""), str(value or "未标明"))


def _label_source_type(value: str) -> str:
    return SOURCE_TYPE_LABELS.get(str(value or ""), str(value or "未知资料"))


def _set_retrieval_trace(trace_key: str | None, hits: list) -> None:
    if not trace_key:
        return
    _LAST_RETRIEVAL_TRACES[trace_key] = [hit.model_dump() for hit in hits]


def get_retrieval_trace(trace_key: str) -> list[dict]:
    return list(_LAST_RETRIEVAL_TRACES.get(trace_key, []))


def _format_discussion_context(artifact: dict | None, empty_message: str) -> str:
    if not isinstance(artifact, dict):
        return empty_message
    discussion = artifact.get("discussion", {})
    if not isinstance(discussion, dict) or not discussion:
        return empty_message
    if not discussion.get("approval_ready"):
        return empty_message

    lines = []
    goal = discussion.get("chapter_goal") or discussion.get("volume_goal") or discussion.get("arc_goal") or ""
    if goal:
        lines.append(f"目标：{goal}")
    current_understanding = str(discussion.get("current_understanding", "") or "").strip()
    if current_understanding:
        lines.append(f"当前理解：{current_understanding}")
    constraints = discussion.get("key_constraints") if isinstance(discussion.get("key_constraints"), list) else []
    if constraints:
        lines.append("关键约束：")
        lines.extend([f"- {str(item).strip()}" for item in constraints if str(item).strip()])
    recommended_direction = str(discussion.get("recommended_direction", "") or "").strip()
    if recommended_direction:
        lines.append(f"推荐方向：{recommended_direction}")
    risks = discussion.get("risks") if isinstance(discussion.get("risks"), list) else []
    if risks:
        lines.append("主要风险：")
        lines.extend([f"- {str(item).strip()}" for item in risks if str(item).strip()])
    return "\n".join(lines).strip() or empty_message


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
        state.retry_counts.setdefault(step_result.step_name, 0)
    elif step_result.status in {"failed", "rejected"}:
        if step_result.step_name not in state.failed_steps:
            state.failed_steps.append(step_result.step_name)
        state.retry_counts[step_result.step_name] = state.retry_counts.get(step_result.step_name, 0) + 1
        if step_result.error:
            _record_pipeline_error(
                state,
                step_name=step_result.step_name,
                message=step_result.error,
                error_type=_infer_error_type_from_step(step_result),
                recoverable=True,
            )
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
    for existing in state.errors:
        if existing.step_name == step_name and existing.message == message:
            return
    state.errors.append(WorkflowError(
        step_name=step_name,
        error_type=error_type,
        message=message,
        recoverable=recoverable,
    ))


def _halt_pipeline(state: ChapterPipelineState, reason: str) -> None:
    state.halted = True
    state.halt_reason = reason


def _transition_pipeline_state(state: ChapterPipelineState, to_step: str, reason: str) -> None:
    state.transition_log.append(WorkflowTransition(
        from_step=state.current_step,
        to_step=to_step,
        reason=reason,
        timestamp=datetime.now().isoformat(timespec="seconds"),
    ))
    state.current_step = to_step


def _infer_error_type_from_step(step_result: WorkflowStepResult) -> str:
    validation = step_result.validation
    if validation.status == "failed":
        return "validation"

    error_text = step_result.error.lower()
    if "retriev" in error_text:
        return "retrieval"
    if "save" in error_text or "persist" in error_text or "write" in error_text:
        return "persistence"
    if "input" in error_text or "empty" in error_text:
        return "input"
    if error_text:
        return "llm"
    return "unknown"


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


def _conflict_id(conflict: dict) -> str:
    project_chunk = conflict.get("project_hit", {}).get("chunk", {})
    external_chunk = conflict.get("external_hit", {}).get("chunk", {})
    terms = "_".join(conflict.get("shared_terms", []))
    raw = "|".join([
        str(project_chunk.get("path", "")),
        str(project_chunk.get("title", "")),
        str(external_chunk.get("path", "")),
        str(external_chunk.get("title", "")),
        terms,
    ])
    return re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "_", raw).strip("_")[:120] or "conflict"


def save_retrieval_conflict_resolution(
    project_name: str,
    conflict: dict,
    decision: str,
    note: str = "",
) -> dict:
    project_chunk = conflict.get("project_hit", {}).get("chunk", {})
    external_chunk = conflict.get("external_hit", {}).get("chunk", {})
    return save_conflict_resolution(project_name, {
        "conflict_id": _conflict_id(conflict),
        "shared_terms": conflict.get("shared_terms", []),
        "decision": decision,
        "note": note,
        "project_source": project_chunk.get("path") or project_chunk.get("title", ""),
        "external_source": external_chunk.get("path") or external_chunk.get("title", ""),
    })


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


def _format_supporting_sources_markdown(hits: list[dict], title: str = "支持来源") -> str:
    selected = _select_supporting_sources(hits)
    if not selected:
        return ""

    grouped = _group_hits_by_scope_and_type(selected)
    scope_order = ["project", "canon", "reference"]
    lines = [f"## {title}", ""]
    item_index = 1
    for scope in scope_order:
        source_groups = grouped.get(scope)
        if not source_groups:
            continue
        lines.append(f"### {_label_scope(scope)}")
        lines.append("")
        for source_type, source_hits in source_groups.items():
            lines.append(f"- {_label_source_type(source_type)}")
            for hit in source_hits:
                chunk = hit.get("chunk", {})
                authority = _label_authority(str(chunk.get("metadata", {}).get("authority", "unknown") or "unknown"))
                detail = f"  - [{item_index}]"
                if chunk.get("title"):
                    detail += f" {chunk.get('title')}"
                else:
                    detail += f" {_label_source_type(source_type)}"
                if chunk.get("chapter_no") is not None:
                    detail += f" / 第 {int(chunk.get('chapter_no')):03d} 章"
                detail += f" / 可信度={authority}"
                detail += f" / 相关度={hit.get('score', 0):.2f}"
                lines.append(detail)
                item_index += 1
            lines.append("")
    return "\n".join(lines)


def _format_potential_conflicts_markdown(hits: list[dict], title: str = "潜在冲突") -> str:
    conflicts = _detect_potential_conflicts(hits)
    if not conflicts:
        return ""

    lines = [f"## {title}", ""]
    for index, conflict in enumerate(conflicts, start=1):
        shared_terms = ", ".join(conflict.shared_terms) or "(无)"
        project_chunk = conflict.project_hit.chunk.model_dump()
        external_chunk = conflict.external_hit.chunk.model_dump()
        severity = {"low": "低", "medium": "中", "high": "高"}.get(conflict.severity, conflict.severity)
        lines.append(f"- [{index}] 严重程度={severity} / 共同命中词={shared_terms}")
        lines.append(
            f"  - 项目资料：{_label_source_type(project_chunk.get('source_type', 'unknown'))} / {project_chunk.get('title', '未命名')} / 可信度={_label_authority(conflict.project_authority)}"
        )
        lines.append(
            f"  - 外部资料：{_label_scope(external_chunk.get('scope', 'reference'))} / {_label_source_type(external_chunk.get('source_type', 'unknown'))} / {external_chunk.get('title', '未命名')} / 可信度={_label_authority(conflict.external_authority)}"
        )
        lines.append(f"  - 判断理由：{conflict.rationale}")
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
    rules_text = format_rules_for_prompt(global_rules, project_rules, scope)
    try:
        profile = load_creative_profile(project_name)
    except Exception:
        profile = {}
    if not profile:
        return rules_text

    profile_lines = [
        "项目创作配置：",
        f"- 任务性质：{profile.get('story_mode', '-')}",
        f"- 目标篇幅：{profile.get('target_length', '-')}",
        f"- 目标字数：{profile.get('target_word_count', '') or '未设置'}",
        f"- 生成层级：{profile.get('workflow_depth', '-')}",
        f"- 资料参考强度：{profile.get('reference_strength', '-')}",
        f"- 重点参考方向：{', '.join(profile.get('reference_focus', []) or []) or '未设置'}",
        f"- 允许改写原设：{'是' if profile.get('allow_canon_deviation', True) else '否'}",
        f"- 资料冲突处理：{profile.get('conflict_policy', '-')}",
    ]
    notes = str(profile.get("notes", "") or "").strip()
    if notes:
        profile_lines.append(f"- 补充说明：{notes}")
    return f"{rules_text}\n\n" + "\n".join(profile_lines)


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


def _extract_web_text_from_html(html: str) -> str:
    # Strip scripts/styles and flatten the page to a readable text block for later structuring.
    cleaned = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    cleaned = re.sub(r"<style[\s\S]*?</style>", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", "\n", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    return cleaned.strip()


def _fetch_web_page(url: str) -> str:
    request = Request(url, headers={"User-Agent": "NovelForge/1.0"})
    with urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="ignore")


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


def organize_reference_text(project_name: str, source_title: str, raw_text: str) -> dict:
    prompt = organize_reference_prompt(
        source_title.strip() or "未命名资料",
        raw_text,
        _build_rules_text(project_name, "all"),
    )
    payload = _call_json_llm(prompt, "模型没有返回可整理的资料结果。")
    try:
        result = OrganizedReferenceResult.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"资料整理结构校验失败：{format_schema_validation_error(exc)}") from exc

    return _make_step_result(
        "organize_reference",
        success=True,
        status="completed",
        data={
            "organized_reference": result.model_dump(),
            "report_markdown": render_organized_reference_markdown(result),
        },
        validation=_make_validation_status(
            status="passed",
            schema_name="OrganizedReferenceResult",
            message="资料已成功整理为结构化数据。",
        ),
    ).model_dump()


def extract_reference_knowledge(
    project_name: str,
    source_title: str,
    raw_text: str,
    enabled_categories: list[str] | None = None,
) -> dict:
    prompt = extract_reference_knowledge_prompt(
        source_title.strip() or "未命名资料",
        raw_text,
        enabled_categories or [],
        _build_rules_text(project_name, "all"),
    )
    payload = _call_json_llm(prompt, "模型没有返回可提取的知识结果。")
    try:
        result = KnowledgeExtractionResult.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"知识提取结构校验失败：{format_schema_validation_error(exc)}") from exc

    return _make_step_result(
        "extract_reference_knowledge",
        success=True,
        status="completed",
        data={
            "knowledge_extraction": result.model_dump(),
            "report_markdown": render_knowledge_extraction_markdown(result),
        },
        validation=_make_validation_status(
            status="passed",
            schema_name="KnowledgeExtractionResult",
            message="资料知识提取结果已通过结构校验。",
        ),
    ).model_dump()


def organize_reference_html(project_name: str, source_title: str, html: str, source_url: str) -> dict:
    extracted_text = _extract_web_text_from_html(html)
    if not extracted_text.strip():
        raise RuntimeError("抓取到的页面中没有提取出可阅读文本。")

    result = organize_reference_text(project_name, source_title, extracted_text)
    result.setdefault("artifacts", {})
    result["artifacts"]["source_url"] = source_url
    result["artifacts"]["raw_text_excerpt"] = extracted_text[:2000]
    return result


def organize_reference_url(project_name: str, source_title: str, source_url: str) -> dict:
    html = _fetch_web_page(source_url)
    return organize_reference_html(project_name, source_title, html, source_url)


def discuss_outline(project_name: str, user_idea: str) -> dict:
    memory = load_memory(project_name)
    prompt = discuss_outline_prompt(memory, user_idea, _build_rules_text(project_name, "outline"))
    payload = _call_json_llm(prompt, "模型没有返回全书讨论结果。")
    try:
        result = OutlineDiscussionResult.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"全书讨论结构校验失败：{format_schema_validation_error(exc)}") from exc

    return _make_step_result(
        "discuss_outline",
        success=True,
        status="completed",
        data={
            "discussion": result.model_dump(),
            "report_markdown": render_discussion_markdown(result),
        },
        validation=_make_validation_status(
            status="passed",
            schema_name="OutlineDiscussionResult",
            message="全书讨论结果已通过结构校验。",
        ),
    ).model_dump()


def discuss_chapter(project_name: str, chapter_no: int, user_requirement: str) -> dict:
    memory = load_memory(project_name)
    outline = load_outline(project_name)
    chapter_metadata = load_chapter_outline_metadata(project_name, chapter_no)
    volume_no = chapter_metadata.get("volume_no")
    arc_no = chapter_metadata.get("arc_no")
    volume_outline = load_volume_outline(project_name, int(volume_no)) if volume_no else ""
    arc_outline = load_arc_outline(project_name, int(arc_no)) if arc_no else ""
    volume_discussion_context = _format_discussion_context(
        load_volume_discussion_artifact(project_name, int(volume_no)) if volume_no else {},
        "当前分卷暂无已批准讨论结论。",
    )
    arc_discussion_context = _format_discussion_context(
        load_arc_discussion_artifact(project_name, int(arc_no)) if arc_no else {},
        "当前剧情段暂无已批准讨论结论。",
    )
    chapter_discussion_context = _format_discussion_context(
        load_chapter_discussion_artifact(project_name, chapter_no),
        "当前章节暂无已批准讨论结论。",
    )
    recent_summaries = get_recent_chapter_summaries(project_name)
    prompt = discuss_chapter_prompt(
        memory,
        outline,
        volume_outline,
        arc_outline,
        volume_discussion_context,
        arc_discussion_context,
        chapter_discussion_context,
        recent_summaries,
        chapter_no,
        user_requirement,
        _build_rules_text(project_name, "chapter_outline"),
    )
    payload = _call_json_llm(prompt, "模型没有返回章节讨论结果。")
    try:
        result = ChapterDiscussionResult.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"章节讨论结构校验失败：{format_schema_validation_error(exc)}") from exc

    return _make_step_result(
        "discuss_chapter",
        success=True,
        status="completed",
        data={
            "discussion": result.model_dump(),
            "report_markdown": render_discussion_markdown(result),
        },
        validation=_make_validation_status(
            status="passed",
            schema_name="ChapterDiscussionResult",
            message="章节讨论结果已通过结构校验。",
        ),
    ).model_dump()


def discuss_outline_turn(
    project_name: str,
    user_idea: str,
    messages: list[dict],
    current_discussion: dict | None,
    latest_user_message: str,
) -> dict:
    memory = load_memory(project_name)
    prompt = discuss_outline_turn_prompt(
        memory,
        user_idea,
        messages,
        current_discussion,
        latest_user_message,
        _build_rules_text(project_name, "outline"),
    )
    payload = _call_json_llm(prompt, "模型没有返回本轮全书讨论结果。")
    assistant_message = str(payload.get("assistant_message", "") or "").strip()
    discussion_payload = payload.get("discussion", {}) if isinstance(payload, dict) else {}

    try:
        result = OutlineDiscussionResult.model_validate(discussion_payload)
    except ValidationError as exc:
        raise RuntimeError(f"本轮全书讨论结构校验失败：{format_schema_validation_error(exc)}") from exc

    return _make_step_result(
        "discuss_outline_turn",
        success=True,
        status="completed",
        data={
            "assistant_message": assistant_message,
            "discussion": result.model_dump(),
            "report_markdown": render_discussion_markdown(result),
        },
        validation=_make_validation_status(
            status="passed",
            schema_name="OutlineDiscussionResult",
            message="本轮全书讨论结果已通过结构校验。",
        ),
    ).model_dump()


def discuss_chapter_turn(
    project_name: str,
    chapter_no: int,
    user_requirement: str,
    messages: list[dict],
    current_discussion: dict | None,
    latest_user_message: str,
) -> dict:
    memory = load_memory(project_name)
    outline = load_outline(project_name)
    chapter_metadata = load_chapter_outline_metadata(project_name, chapter_no)
    volume_no = chapter_metadata.get("volume_no")
    arc_no = chapter_metadata.get("arc_no")
    volume_outline = load_volume_outline(project_name, int(volume_no)) if volume_no else ""
    arc_outline = load_arc_outline(project_name, int(arc_no)) if arc_no else ""
    volume_discussion_context = _format_discussion_context(
        load_volume_discussion_artifact(project_name, int(volume_no)) if volume_no else {},
        "当前分卷暂无已批准讨论结论。",
    )
    arc_discussion_context = _format_discussion_context(
        load_arc_discussion_artifact(project_name, int(arc_no)) if arc_no else {},
        "当前剧情段暂无已批准讨论结论。",
    )
    chapter_discussion_context = _format_discussion_context(
        load_chapter_discussion_artifact(project_name, chapter_no),
        "当前章节暂无已批准讨论结论。",
    )
    recent_summaries = get_recent_chapter_summaries(project_name)
    prompt = discuss_chapter_turn_prompt(
        memory,
        outline,
        volume_outline,
        arc_outline,
        volume_discussion_context,
        arc_discussion_context,
        chapter_discussion_context,
        recent_summaries,
        chapter_no,
        user_requirement,
        messages,
        current_discussion,
        latest_user_message,
        _build_rules_text(project_name, "chapter_outline"),
    )
    payload = _call_json_llm(prompt, "模型没有返回本轮章节讨论结果。")
    assistant_message = str(payload.get("assistant_message", "") or "").strip()
    discussion_payload = payload.get("discussion", {}) if isinstance(payload, dict) else {}

    try:
        result = ChapterDiscussionResult.model_validate(discussion_payload)
    except ValidationError as exc:
        raise RuntimeError(f"本轮章节讨论结构校验失败：{format_schema_validation_error(exc)}") from exc

    return _make_step_result(
        "discuss_chapter_turn",
        success=True,
        status="completed",
        data={
            "assistant_message": assistant_message,
            "discussion": result.model_dump(),
            "report_markdown": render_discussion_markdown(result),
        },
        validation=_make_validation_status(
            status="passed",
            schema_name="ChapterDiscussionResult",
            message="本轮章节讨论结果已通过结构校验。",
        ),
    ).model_dump()


def discuss_volume(
    project_name: str,
    volume_no: int,
    volume_title: str,
    volume_summary: str,
    user_requirement: str,
) -> dict:
    memory = load_memory(project_name)
    story_outline = load_outline(project_name)
    prompt = discuss_volume_prompt(
        memory,
        story_outline,
        volume_no,
        volume_title,
        volume_summary,
        user_requirement,
        _build_rules_text(project_name, "outline"),
    )
    payload = _call_json_llm(prompt, "模型没有返回分卷讨论结果。")
    try:
        result = VolumeDiscussionResult.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"分卷讨论结构校验失败：{format_schema_validation_error(exc)}") from exc

    return _make_step_result(
        "discuss_volume",
        success=True,
        status="completed",
        data={
            "discussion": result.model_dump(),
            "report_markdown": render_discussion_markdown(result),
        },
        validation=_make_validation_status(
            status="passed",
            schema_name="VolumeDiscussionResult",
            message="分卷讨论结果已通过结构校验。",
        ),
    ).model_dump()


def discuss_volume_turn(
    project_name: str,
    volume_no: int,
    volume_title: str,
    volume_summary: str,
    user_requirement: str,
    messages: list[dict],
    current_discussion: dict | None,
    latest_user_message: str,
) -> dict:
    memory = load_memory(project_name)
    story_outline = load_outline(project_name)
    prompt = discuss_volume_turn_prompt(
        memory,
        story_outline,
        volume_no,
        volume_title,
        volume_summary,
        user_requirement,
        messages,
        current_discussion,
        latest_user_message,
        _build_rules_text(project_name, "outline"),
    )
    payload = _call_json_llm(prompt, "模型没有返回本轮分卷讨论结果。")
    assistant_message = str(payload.get("assistant_message", "") or "").strip()
    discussion_payload = payload.get("discussion", {}) if isinstance(payload, dict) else {}

    try:
        result = VolumeDiscussionResult.model_validate(discussion_payload)
    except ValidationError as exc:
        raise RuntimeError(f"本轮分卷讨论结构校验失败：{format_schema_validation_error(exc)}") from exc

    return _make_step_result(
        "discuss_volume_turn",
        success=True,
        status="completed",
        data={
            "assistant_message": assistant_message,
            "discussion": result.model_dump(),
            "report_markdown": render_discussion_markdown(result),
        },
        validation=_make_validation_status(
            status="passed",
            schema_name="VolumeDiscussionResult",
            message="本轮分卷讨论结果已通过结构校验。",
        ),
    ).model_dump()


def discuss_arc(
    project_name: str,
    arc_no: int,
    volume_no: int | None,
    arc_title: str,
    arc_summary: str,
    estimated_chapter_count: int | None,
    target_word_count_range: str,
    user_requirement: str,
) -> dict:
    memory = load_memory(project_name)
    story_outline = load_outline(project_name)
    volume_outline = load_volume_outline(project_name, int(volume_no)) if volume_no else ""
    prompt = discuss_arc_prompt(
        memory,
        story_outline,
        volume_outline,
        arc_no,
        arc_title,
        arc_summary,
        estimated_chapter_count,
        target_word_count_range,
        user_requirement,
        _build_rules_text(project_name, "outline"),
    )
    payload = _call_json_llm(prompt, "模型没有返回剧情段讨论结果。")
    try:
        result = ArcDiscussionResult.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"剧情段讨论结构校验失败：{format_schema_validation_error(exc)}") from exc

    return _make_step_result(
        "discuss_arc",
        success=True,
        status="completed",
        data={
            "discussion": result.model_dump(),
            "report_markdown": render_discussion_markdown(result),
        },
        validation=_make_validation_status(
            status="passed",
            schema_name="ArcDiscussionResult",
            message="剧情段讨论结果已通过结构校验。",
        ),
    ).model_dump()


def discuss_arc_turn(
    project_name: str,
    arc_no: int,
    volume_no: int | None,
    arc_title: str,
    arc_summary: str,
    estimated_chapter_count: int | None,
    target_word_count_range: str,
    user_requirement: str,
    messages: list[dict],
    current_discussion: dict | None,
    latest_user_message: str,
) -> dict:
    memory = load_memory(project_name)
    story_outline = load_outline(project_name)
    volume_outline = load_volume_outline(project_name, int(volume_no)) if volume_no else ""
    prompt = discuss_arc_turn_prompt(
        memory,
        story_outline,
        volume_outline,
        arc_no,
        arc_title,
        arc_summary,
        estimated_chapter_count,
        target_word_count_range,
        user_requirement,
        messages,
        current_discussion,
        latest_user_message,
        _build_rules_text(project_name, "outline"),
    )
    payload = _call_json_llm(prompt, "模型没有返回本轮剧情段讨论结果。")
    assistant_message = str(payload.get("assistant_message", "") or "").strip()
    discussion_payload = payload.get("discussion", {}) if isinstance(payload, dict) else {}

    try:
        result = ArcDiscussionResult.model_validate(discussion_payload)
    except ValidationError as exc:
        raise RuntimeError(f"本轮剧情段讨论结构校验失败：{format_schema_validation_error(exc)}") from exc

    return _make_step_result(
        "discuss_arc_turn",
        success=True,
        status="completed",
        data={
            "assistant_message": assistant_message,
            "discussion": result.model_dump(),
            "report_markdown": render_discussion_markdown(result),
        },
        validation=_make_validation_status(
            status="passed",
            schema_name="ArcDiscussionResult",
            message="本轮剧情段讨论结果已通过结构校验。",
        ),
    ).model_dump()


def approve_volume_discussion(project_name: str, volume_no: int, discussion_step: dict) -> dict:
    discussion = discussion_step.get("data", {}).get("discussion", {}) if isinstance(discussion_step, dict) else {}
    report_markdown = discussion_step.get("data", {}).get("report_markdown", "") if isinstance(discussion_step, dict) else ""
    if not isinstance(discussion, dict) or not discussion:
        raise RuntimeError("没有可批准的分卷讨论结果。")
    if not discussion.get("approval_ready"):
        raise RuntimeError("分卷讨论结果尚未达到可批准状态。")
    save_volume_discussion_artifact(project_name, volume_no, discussion, report_markdown)
    return {
        "volume_no": volume_no,
        "discussion": discussion,
        "report_markdown": report_markdown,
        "saved_path": f"data/projects/{project_name}/volumes/volume_{volume_no:03d}.discussion.json",
    }


def clear_volume_discussion_approval(project_name: str, volume_no: int) -> bool:
    return delete_volume_discussion_artifact(project_name, volume_no)


def approve_arc_discussion(project_name: str, arc_no: int, discussion_step: dict) -> dict:
    discussion = discussion_step.get("data", {}).get("discussion", {}) if isinstance(discussion_step, dict) else {}
    report_markdown = discussion_step.get("data", {}).get("report_markdown", "") if isinstance(discussion_step, dict) else ""
    if not isinstance(discussion, dict) or not discussion:
        raise RuntimeError("没有可批准的剧情段讨论结果。")
    if not discussion.get("approval_ready"):
        raise RuntimeError("剧情段讨论结果尚未达到可批准状态。")
    save_arc_discussion_artifact(project_name, arc_no, discussion, report_markdown)
    return {
        "arc_no": arc_no,
        "discussion": discussion,
        "report_markdown": report_markdown,
        "saved_path": f"data/projects/{project_name}/arcs/arc_{arc_no:03d}.discussion.json",
    }


def clear_arc_discussion_approval(project_name: str, arc_no: int) -> bool:
    return delete_arc_discussion_artifact(project_name, arc_no)


def approve_outline_discussion(project_name: str, discussion_step: dict) -> dict:
    discussion = discussion_step.get("data", {}).get("discussion", {}) if isinstance(discussion_step, dict) else {}
    report_markdown = discussion_step.get("data", {}).get("report_markdown", "") if isinstance(discussion_step, dict) else ""
    if not isinstance(discussion, dict) or not discussion:
        raise RuntimeError("没有可批准的全书讨论结果。")
    if not discussion.get("approval_ready"):
        raise RuntimeError("全书讨论结果尚未达到可批准状态。")
    save_outline_discussion_artifact(project_name, discussion, report_markdown)
    return {
        "discussion": discussion,
        "report_markdown": report_markdown,
        "saved_path": f"data/projects/{project_name}/outline.discussion.json",
    }


def clear_outline_discussion_approval(project_name: str) -> bool:
    return delete_outline_discussion_artifact(project_name)


def approve_chapter_discussion(project_name: str, chapter_no: int, discussion_step: dict) -> dict:
    discussion = discussion_step.get("data", {}).get("discussion", {}) if isinstance(discussion_step, dict) else {}
    report_markdown = discussion_step.get("data", {}).get("report_markdown", "") if isinstance(discussion_step, dict) else ""
    if not isinstance(discussion, dict) or not discussion:
        raise RuntimeError("没有可批准的章节讨论结果。")
    if not discussion.get("approval_ready"):
        raise RuntimeError("章节讨论结果尚未达到可批准状态。")
    save_chapter_discussion_artifact(project_name, chapter_no, discussion, report_markdown)
    return {
        "chapter_no": chapter_no,
        "discussion": discussion,
        "report_markdown": report_markdown,
        "saved_path": f"data/projects/{project_name}/chapter_outlines/chapter_{chapter_no:03d}.discussion.json",
    }


def clear_chapter_discussion_approval(project_name: str, chapter_no: int) -> bool:
    return delete_chapter_discussion_artifact(project_name, chapter_no)


def _format_review_markdown(review: ReviewResult | dict) -> str:
    if isinstance(review, ReviewResult):
        review = review.model_dump()

    strengths = "\n".join([f"- {item}" for item in review["strengths"]]) or "- 无"
    issues = "\n".join([f"- {item}" for item in review["issues"]]) or "- 无"

    status_label = {
        "pass": "通过",
        "revise": "需要修改",
        "blocked": "阻塞",
    }.get(review["status"], review["status"])

    return f"""# 章节审阅

状态：`{status_label}`

## 摘要

{review['summary'] or '无'}

## 优点

{strengths}

## 问题

{issues}

## 一致性检查

- 角色：{review['consistency_checks']['characters'] or '无'}
- 世界观：{review['consistency_checks']['world'] or '无'}
- 时间线：{review['consistency_checks']['timeline'] or '无'}
- 伏笔：{review['consistency_checks']['foreshadowing'] or '无'}

## 节奏

{review['pacing'] or '无'}

## 下一步建议

{review['next_action'] or '无'}
"""

def generate_outline(project_name: str, user_idea: str) -> dict:
    memory = load_memory(project_name)
    approved_discussion_context = _format_discussion_context(
        load_outline_discussion_artifact(project_name),
        "当前全书暂无已批准讨论结论。",
    )
    trace_key = f"outline:{project_name}"
    retrieval_context = _build_retrieval_context(
        project_name,
        f"{user_idea} {approved_discussion_context}",
        allowed_source_types=["outline", "outline_discussion", "memory_character", "memory_world", "memory_au_rule", "memory_relationship", "memory_timeline", "memory_foreshadowing", "memory_active_constraint", "external_source"] + KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        outline_prompt(memory, f"{user_idea}\n\n已批准讨论结论：\n{approved_discussion_context}".strip(), _build_rules_text(project_name, "outline")),
        retrieval_context,
    )
    outline = call_llm(prompt)
    if not outline.strip():
        raise RuntimeError("模型没有返回全书大纲。")
    save_outline(project_name, outline)
    return _make_step_result(
        "outline",
        success=True,
        status="completed",
        data={"outline": outline},
        retrieval_hits=get_retrieval_trace(trace_key),
        artifacts={"saved_path": f"data/projects/{project_name}/outline.md"},
    ).model_dump()


def generate_volume_outline(
    project_name: str,
    volume_no: int,
    volume_title: str,
    volume_summary: str,
    user_requirement: str,
    status: str = "draft",
) -> dict:
    memory = load_memory(project_name)
    story_outline = load_outline(project_name)
    approved_discussion_context = _format_discussion_context(
        load_volume_discussion_artifact(project_name, volume_no),
        "当前分卷暂无已批准讨论结论。",
    )
    trace_key = f"volume_outline:{project_name}:{volume_no}"
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{volume_no}卷 {volume_title} {volume_summary} {approved_discussion_context} {user_requirement} {story_outline}",
        allowed_source_types=[
            "outline",
            "volume_outline",
            "volume_discussion",
            "arc_outline",
            "arc_discussion",
            "chapter_summary",
            "memory_character",
            "memory_world",
            "memory_au_rule",
            "memory_relationship",
            "memory_timeline",
            "memory_foreshadowing",
            "memory_active_constraint",
            "external_source",
        ] + KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        volume_outline_prompt(
            memory,
            story_outline,
            volume_no,
            volume_title,
            volume_summary,
            approved_discussion_context,
            user_requirement,
            _build_rules_text(project_name, "outline"),
        ),
        retrieval_context,
    )
    outline = call_llm(prompt)
    if not outline.strip():
        raise RuntimeError("模型没有返回分卷大纲。")
    save_volume_outline(project_name, volume_no, outline)
    save_volume_metadata(project_name, volume_no, {"title": volume_title, "summary": volume_summary, "status": status})
    return _make_step_result(
        "volume_outline",
        success=True,
        status="completed",
        data={"volume_outline": outline, "volume_metadata": {"volume_no": volume_no, "title": volume_title, "summary": volume_summary, "status": status}},
        retrieval_hits=get_retrieval_trace(trace_key),
        artifacts={
            "saved_path": f"data/projects/{project_name}/volumes/volume_{volume_no:03d}.md",
            "metadata_path": f"data/projects/{project_name}/volumes/volume_{volume_no:03d}.meta.json",
        },
    ).model_dump()


def generate_arc_outline(
    project_name: str,
    arc_no: int,
    volume_no: int | None,
    arc_title: str,
    arc_summary: str,
    estimated_chapter_count: int | None,
    target_word_count_range: str,
    user_requirement: str,
    status: str = "draft",
) -> dict:
    memory = load_memory(project_name)
    story_outline = load_outline(project_name)
    volume_outline = load_volume_outline(project_name, int(volume_no)) if volume_no else ""
    approved_discussion_context = _format_discussion_context(
        load_arc_discussion_artifact(project_name, arc_no),
        "当前剧情段暂无已批准讨论结论。",
    )
    trace_key = f"arc_outline:{project_name}:{arc_no}"
    retrieval_context = _build_retrieval_context(
        project_name,
        f"剧情段 {arc_no:03d} 第{volume_no or 0}卷 {arc_title} {arc_summary} {approved_discussion_context} {user_requirement} {story_outline} {volume_outline}",
        allowed_source_types=[
            "outline",
            "volume_outline",
            "volume_discussion",
            "arc_outline",
            "arc_discussion",
            "chapter_summary",
            "chapter_outline",
            "memory_character",
            "memory_world",
            "memory_au_rule",
            "memory_relationship",
            "memory_timeline",
            "memory_foreshadowing",
            "memory_active_constraint",
            "external_source",
        ] + KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        arc_outline_prompt(
            memory,
            story_outline,
            volume_outline,
            arc_no,
            arc_title,
            arc_summary,
            estimated_chapter_count,
            target_word_count_range,
            approved_discussion_context,
            user_requirement,
            _build_rules_text(project_name, "outline"),
        ),
        retrieval_context,
    )
    outline = call_llm(prompt)
    if not outline.strip():
        raise RuntimeError("模型没有返回剧情段大纲。")
    save_arc_outline(project_name, arc_no, outline)
    save_arc_metadata(
        project_name,
        arc_no,
        {
            "volume_no": volume_no,
            "title": arc_title,
            "summary": arc_summary,
            "status": status,
            "estimated_chapter_count": estimated_chapter_count,
            "target_word_count_range": target_word_count_range,
        },
    )
    return _make_step_result(
        "arc_outline",
        success=True,
        status="completed",
        data={
            "arc_outline": outline,
            "arc_metadata": {
                "arc_no": arc_no,
                "volume_no": volume_no,
                "title": arc_title,
                "summary": arc_summary,
                "status": status,
                "estimated_chapter_count": estimated_chapter_count,
                "target_word_count_range": target_word_count_range,
            },
        },
        retrieval_hits=get_retrieval_trace(trace_key),
        artifacts={
            "saved_path": f"data/projects/{project_name}/arcs/arc_{arc_no:03d}.md",
            "metadata_path": f"data/projects/{project_name}/arcs/arc_{arc_no:03d}.meta.json",
        },
    ).model_dump()


def generate_arc_chapter_plan(
    project_name: str,
    arc_no: int,
    start_chapter_no: int,
    chapter_count: int,
    user_requirement: str = "",
) -> dict:
    arc_meta = load_arc_metadata(project_name, arc_no)
    volume_no = arc_meta.get("volume_no")
    memory = load_memory(project_name)
    story_outline = load_outline(project_name)
    volume_outline = load_volume_outline(project_name, int(volume_no)) if volume_no else ""
    arc_outline = load_arc_outline(project_name, arc_no)
    trace_key = f"arc_chapter_plan:{project_name}:{arc_no}"
    retrieval_context = _build_retrieval_context(
        project_name,
        f"剧情段 {arc_no:03d} 章节分配 {arc_meta.get('title', '')} {arc_meta.get('summary', '')} {arc_outline} {user_requirement}",
        allowed_source_types=[
            "outline",
            "volume_outline",
            "volume_discussion",
            "arc_outline",
            "arc_discussion",
            "chapter_summary",
            "chapter_outline",
            "memory_character",
            "memory_world",
            "memory_relationship",
            "memory_timeline",
            "memory_foreshadowing",
            "memory_active_constraint",
            "external_source",
            "conflict_resolution",
        ] + KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        arc_chapter_plan_prompt(
            memory,
            story_outline,
            volume_outline,
            arc_outline,
            arc_no,
            start_chapter_no,
            chapter_count,
            arc_meta.get("target_word_count_range", ""),
            user_requirement,
            _build_rules_text(project_name, "chapter_outline"),
        ),
        retrieval_context,
    )
    payload = _call_json_llm(prompt, "模型没有返回剧情段章节分配计划。")
    try:
        result = ArcChapterPlanResult.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"剧情段章节分配计划结构校验失败：{format_schema_validation_error(exc)}") from exc

    report_markdown = render_arc_chapter_plan_markdown(result)
    save_arc_chapter_plan(project_name, arc_no, result.model_dump(), report_markdown)
    return _make_step_result(
        "arc_chapter_plan",
        success=True,
        status="completed",
        data={
            "arc_chapter_plan": result.model_dump(),
            "report_markdown": report_markdown,
        },
        retrieval_hits=get_retrieval_trace(trace_key),
        validation=_make_validation_status(
            status="passed",
            schema_name="ArcChapterPlanResult",
            message="剧情段章节分配计划已通过结构校验并保存。",
        ),
        artifacts={
            "saved_path": f"data/projects/{project_name}/arcs/arc_{arc_no:03d}.chapter_plan.json",
        },
    ).model_dump()


def generate_creative_structure(
    project_name: str,
    chapter_no: int,
    user_requirement: str,
    *,
    save_as_chapter_outline: bool = True,
) -> dict:
    memory = load_memory(project_name)
    profile = load_creative_profile(project_name)
    trace_key = f"creative_structure:{project_name}:{chapter_no}"
    retrieval_context = _build_retrieval_context(
        project_name,
        f"{profile} {user_requirement}",
        allowed_source_types=COMMON_RETRIEVAL_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        top_k=8,
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        creative_structure_prompt(
            memory,
            profile,
            user_requirement,
            _build_rules_text(project_name, "chapter_outline"),
        ),
        retrieval_context,
    )
    structure = call_llm(prompt)
    if not structure.strip():
        raise RuntimeError("模型没有返回创作结构。")

    artifacts = {}
    if save_as_chapter_outline:
        save_chapter_outline(project_name, chapter_no, structure)
        artifacts["saved_path"] = f"data/projects/{project_name}/chapter_outlines/chapter_{chapter_no:03d}.md"

    return _make_step_result(
        "creative_structure",
        success=True,
        status="completed",
        data={
            "creative_structure": structure,
            "creative_profile": profile,
            "chapter_no": chapter_no,
        },
        retrieval_hits=get_retrieval_trace(trace_key),
        artifacts=artifacts,
    ).model_dump()


def generate_chapter_outline(
    project_name: str,
    chapter_no: int,
    user_requirement: str,
    volume_no: int | None = None,
    arc_no: int | None = None,
) -> dict:
    memory = load_memory(project_name)
    outline = load_outline(project_name)
    existing_metadata = load_chapter_outline_metadata(project_name, chapter_no)
    effective_volume_no = volume_no if volume_no is not None else existing_metadata.get("volume_no")
    effective_arc_no = arc_no if arc_no is not None else existing_metadata.get("arc_no")
    volume_outline = load_volume_outline(project_name, int(effective_volume_no)) if effective_volume_no else ""
    arc_outline = load_arc_outline(project_name, int(effective_arc_no)) if effective_arc_no else ""
    volume_discussion_context = _format_discussion_context(
        load_volume_discussion_artifact(project_name, int(effective_volume_no)) if effective_volume_no else {},
        "当前分卷暂无已批准讨论结论。",
    )
    arc_discussion_context = _format_discussion_context(
        load_arc_discussion_artifact(project_name, int(effective_arc_no)) if effective_arc_no else {},
        "当前剧情段暂无已批准讨论结论。",
    )
    chapter_discussion_context = _format_discussion_context(
        load_chapter_discussion_artifact(project_name, chapter_no),
        "当前章节暂无已批准讨论结论。",
    )
    trace_key = f"chapter_outline:{project_name}:{chapter_no}"
    recent_summaries = get_recent_chapter_summaries(project_name)
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章 {user_requirement} {outline} {volume_outline} {arc_outline} {volume_discussion_context} {arc_discussion_context} {chapter_discussion_context}",
        allowed_source_types=[
            "outline",
            "outline_discussion",
            "volume_outline",
            "volume_discussion",
            "arc_outline",
            "arc_discussion",
            "chapter_discussion",
            "chapter_summary",
            "chapter_outline",
            "memory_character",
            "memory_world",
            "memory_au_rule",
            "memory_relationship",
            "memory_timeline",
            "memory_foreshadowing",
            "memory_active_constraint",
            "external_source",
        ] + KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(chapter_outline_prompt(
        memory,
        outline,
        volume_outline,
        arc_outline,
        volume_discussion_context,
        arc_discussion_context,
        chapter_discussion_context,
        recent_summaries,
        chapter_no,
        user_requirement,
        _build_rules_text(project_name, "chapter_outline"),
    ), retrieval_context)
    outline = call_llm(prompt)
    if not outline.strip():
        raise RuntimeError("模型没有返回章节细纲。")
    save_chapter_outline(project_name, chapter_no, outline)
    save_chapter_outline_metadata(project_name, chapter_no, {"volume_no": effective_volume_no, "arc_no": effective_arc_no})
    return _make_step_result(
        "chapter_outline",
        success=True,
        status="completed",
        data={"chapter_outline": outline, "chapter_outline_metadata": {"chapter_no": chapter_no, "volume_no": effective_volume_no, "arc_no": effective_arc_no}},
        retrieval_hits=get_retrieval_trace(trace_key),
        artifacts={
            "saved_path": f"data/projects/{project_name}/chapter_outlines/chapter_{chapter_no:03d}.md",
            "metadata_path": f"data/projects/{project_name}/chapter_outlines/chapter_{chapter_no:03d}.meta.json",
        },
    ).model_dump()

def write_chapter(
    project_name: str,
    chapter_no: int,
    chapter_outline: str,
    writing_guidance: dict | None = None,
    word_count: str = "2000-2500"
) -> dict:
    memory = load_memory(project_name)
    normalized_guidance = ChapterWritingGuidance.model_validate(writing_guidance or {}).model_dump()
    trace_key = f"write:{project_name}:{chapter_no}"
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章 {chapter_outline} {normalized_guidance}",
        allowed_source_types=[
            "chapter_summary",
            "chapter_outline",
            "chapter_discussion",
            "chapter_content",
            "memory_character",
            "memory_world",
            "memory_au_rule",
            "memory_relationship",
            "memory_timeline",
            "memory_foreshadowing",
            "memory_active_constraint",
            "review_issue",
            "analysis_consistency",
            "analysis_characters",
            "analysis_timeline",
            "analysis_foreshadowing",
            "external_source",
        ] + KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        write_chapter_prompt(memory, chapter_outline, normalized_guidance, word_count, _build_rules_text(project_name, "write")),
        retrieval_context,
    )
    chapter = call_llm(prompt)
    if not chapter.strip():
        raise RuntimeError("模型没有返回章节正文。")
    save_chapter(project_name, chapter_no, chapter)
    return _make_step_result(
        "write_chapter",
        success=True,
        status="completed",
        data={"chapter": chapter, "writing_guidance": normalized_guidance},
        retrieval_hits=get_retrieval_trace(trace_key),
        artifacts={"saved_path": f"data/projects/{project_name}/chapters/chapter_{chapter_no:03d}.md"},
    ).model_dump()


def run_dynamic_generation_task(
    project_name: str,
    chapter_no: int,
    user_requirement: str,
    word_count: str = "",
    workflow_depth: str = "按创作配置",
) -> dict:
    profile = load_creative_profile(project_name)
    using_profile_depth = not workflow_depth or workflow_depth == "按创作配置"
    effective_depth = workflow_depth if not using_profile_depth else profile.get("workflow_depth", "短篇结构+正文")
    effective_word_count = word_count.strip() or profile.get("target_word_count", "") or "2000-2500"
    steps: dict[str, dict] = {}
    warnings: list[str] = []

    if effective_depth == "只生成正文":
        direct_outline = "\n\n".join([
            "# 直接正文生成任务",
            f"创作配置：{json.dumps(profile, ensure_ascii=False)}",
            f"用户需求：{user_requirement}",
            "请根据创作配置和检索上下文直接写正文，不需要输出大纲。",
        ])
        write_step = write_chapter(project_name, chapter_no, direct_outline, None, effective_word_count)
        steps["write_chapter"] = write_step
        return {
            "success": bool(write_step.get("success")),
            "status": write_step.get("status", "completed"),
            "workflow_depth": effective_depth,
            "chapter_no": chapter_no,
            "word_count": effective_word_count,
            "steps": steps,
            "creative_structure": "",
            "chapter": write_step.get("data", {}).get("chapter", ""),
            "warnings": warnings,
        }

    is_custom_depth = effective_depth not in KNOWN_WORKFLOW_DEPTHS

    if effective_depth in {"短篇结构+正文", "分卷/剧情段/章节"} or is_custom_depth or (
        using_profile_depth and _is_lightweight_story_profile(profile)
    ):
        structure_step = generate_creative_structure(project_name, chapter_no, user_requirement, save_as_chapter_outline=True)
        steps["creative_structure"] = structure_step
        if not structure_step.get("success"):
            return {
                "success": False,
                "status": structure_step.get("status", "failed"),
                "workflow_depth": effective_depth,
                "chapter_no": chapter_no,
                "word_count": effective_word_count,
                "steps": steps,
                "creative_structure": "",
                "chapter": "",
                "warnings": warnings,
            }
        structure_text = structure_step.get("data", {}).get("creative_structure", "")
        if effective_depth == "分卷/剧情段/章节":
            warnings.append("当前动态入口先生成可执行创作结构；完整分卷/剧情段拆分请继续使用对应长篇页面。")
        if is_custom_depth:
            warnings.append("本次使用自定义生成层级，系统会先生成适配结构，再继续生成正文。")
        write_step = write_chapter(project_name, chapter_no, structure_text, None, effective_word_count)
        steps["write_chapter"] = write_step
        return {
            "success": bool(write_step.get("success")),
            "status": write_step.get("status", "completed"),
            "workflow_depth": effective_depth,
            "chapter_no": chapter_no,
            "word_count": effective_word_count,
            "steps": steps,
            "creative_structure": structure_text,
            "chapter": write_step.get("data", {}).get("chapter", ""),
            "warnings": warnings,
        }

    if effective_depth == "章节计划+正文":
        outline_step = generate_chapter_outline(project_name, chapter_no, user_requirement)
        steps["chapter_outline"] = outline_step
        if not outline_step.get("success"):
            return {
                "success": False,
                "status": outline_step.get("status", "failed"),
                "workflow_depth": effective_depth,
                "chapter_no": chapter_no,
                "word_count": effective_word_count,
                "steps": steps,
                "creative_structure": "",
                "chapter": "",
                "warnings": warnings,
            }
        outline_text = outline_step.get("data", {}).get("chapter_outline", "")
        write_step = write_chapter(project_name, chapter_no, outline_text, None, effective_word_count)
        steps["write_chapter"] = write_step
        return {
            "success": bool(write_step.get("success")),
            "status": write_step.get("status", "completed"),
            "workflow_depth": effective_depth,
            "chapter_no": chapter_no,
            "word_count": effective_word_count,
            "steps": steps,
            "creative_structure": outline_text,
            "chapter": write_step.get("data", {}).get("chapter", ""),
            "warnings": warnings,
        }

    warnings.append("完整长篇流程建议继续使用全书大纲、分卷、剧情段、章节细纲和一键流水线页面分步执行。")
    structure_step = generate_creative_structure(project_name, chapter_no, user_requirement, save_as_chapter_outline=True)
    steps["creative_structure"] = structure_step
    return {
        "success": bool(structure_step.get("success")),
        "status": "completed" if structure_step.get("success") else structure_step.get("status", "failed"),
        "workflow_depth": effective_depth,
        "chapter_no": chapter_no,
        "word_count": effective_word_count,
        "steps": steps,
        "creative_structure": structure_step.get("data", {}).get("creative_structure", ""),
        "chapter": "",
        "warnings": warnings,
    }

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
        allowed_source_types=["memory_character", "memory_world", "memory_au_rule", "memory_relationship", "memory_timeline", "memory_foreshadowing", "memory_active_constraint", "chapter_summary", "external_source"] + KNOWLEDGE_SOURCE_TYPES,
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
                message="设定更新结构校验失败。",
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
                message="设定更新结果提取失败。",
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
            message="设定更新已通过结构校验并应用。",
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
            "memory_au_rule",
            "memory_relationship",
            "memory_timeline",
            "memory_foreshadowing",
            "memory_active_constraint",
            "review_issue",
            "review_timeline_check",
            "review_foreshadowing_check",
            "analysis_consistency",
            "analysis_characters",
            "analysis_timeline",
            "analysis_foreshadowing",
            "external_source",
        ] + KNOWLEDGE_SOURCE_TYPES,
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
            issues=["模型未按要求返回合法结构的审阅结果。"],
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
        markdown += f"\n\n## 模型原始返回\n\n```text\n{result}\n```"
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
            warnings=["已生成并保存审阅报告的兜底版本。"],
            retrieval_hits=retrieval_hits,
            validation=_make_validation_status(
                status="failed",
                schema_name="ReviewResult",
                message="审阅结果结构校验失败。",
                errors=[reason],
            ),
            artifacts={"review_saved": True, "raw_response": result},
        ).model_dump()
    except Exception as exc:
        fallback_review = ReviewResult(
            status="blocked",
            summary=f"审阅结果解析失败：{exc}",
            strengths=[],
            issues=["模型未按要求返回合法结构化审阅结果。"],
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
        markdown += f"\n\n## 模型原始返回\n\n```text\n{result}\n```"
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
            warnings=["已生成并保存审阅报告的兜底版本。"],
            retrieval_hits=retrieval_hits,
            validation=_make_validation_status(
                status="failed",
                schema_name="ReviewResult",
                message="审阅结果提取失败。",
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
            message="审阅结果已通过结构校验并保存。",
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
        raise RuntimeError(f"分析结果结构校验失败：{format_schema_validation_error(exc)}") from exc
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
            message="分析结果已通过结构校验并保存报告。",
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
        allowed_source_types=["chapter_summary", "chapter_content", "memory_character", "memory_relationship", "memory_active_constraint", "review_issue", "analysis_characters", "external_source"] + KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        character_analysis_prompt(memory, chapter, _build_rules_text(project_name, "review")),
        retrieval_context,
    )
    result_model, markdown = _run_analysis(
        prompt,
        "模型没有返回角色分析结果。",
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
        allowed_source_types=["chapter_summary", "chapter_content", "memory_timeline", "memory_active_constraint", "review_timeline_check", "analysis_timeline", "external_source"] + KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        timeline_analysis_prompt(memory, chapter, _build_rules_text(project_name, "review")),
        retrieval_context,
    )
    result_model, markdown = _run_analysis(
        prompt,
        "模型没有返回时间线分析结果。",
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
        allowed_source_types=["chapter_summary", "chapter_content", "memory_foreshadowing", "memory_active_constraint", "review_foreshadowing_check", "analysis_foreshadowing", "external_source"] + KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        foreshadowing_analysis_prompt(memory, chapter, _build_rules_text(project_name, "review")),
        retrieval_context,
    )
    result_model, markdown = _run_analysis(
        prompt,
        "模型没有返回伏笔分析结果。",
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
            "memory_au_rule",
            "memory_relationship",
            "memory_timeline",
            "memory_foreshadowing",
            "memory_active_constraint",
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
        "模型没有返回一致性检查结果。",
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


def evaluate_chapter(project_name: str, chapter_no: int, chapter: str) -> dict:
    memory = load_memory(project_name)
    chapter_outline = load_chapter_outline(project_name, chapter_no)
    trace_key = f"evaluation:chapter:{project_name}:{chapter_no}"
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章质量评估 {chapter_outline} {chapter}",
        allowed_source_types=[
            "outline",
            "volume_outline",
            "arc_outline",
            "arc_chapter_plan",
            "chapter_summary",
            "chapter_outline",
            "chapter_content",
            "memory_character",
            "memory_world",
            "memory_relationship",
            "memory_timeline",
            "memory_foreshadowing",
            "memory_active_constraint",
            "review_issue",
            "analysis_consistency",
            "analysis_characters",
            "analysis_timeline",
            "analysis_foreshadowing",
            "conflict_resolution",
            "external_source",
        ] + KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
    )
    prompt = merge_retrieval_context(
        evaluate_chapter_prompt(memory, chapter_outline, chapter, _build_rules_text(project_name, "review")),
        retrieval_context,
    )
    payload = _call_json_llm(prompt, "模型没有返回章节评估结果。")
    try:
        result = ChapterEvaluationResult.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"章节评估结构校验失败：{format_schema_validation_error(exc)}") from exc

    retrieval_hits = get_retrieval_trace(trace_key)
    report_markdown = render_chapter_evaluation_markdown(result)
    sources_md = _format_supporting_sources_markdown(retrieval_hits)
    conflict_md = _format_potential_conflicts_markdown(retrieval_hits)
    if sources_md:
        report_markdown += f"\n\n{sources_md}"
    if conflict_md:
        report_markdown += f"\n\n{conflict_md}"
    save_evaluation_json(project_name, chapter_no, result.model_dump())
    save_evaluation_report(project_name, chapter_no, report_markdown)
    return _make_step_result(
        "evaluate_chapter",
        success=True,
        status="completed",
        data={
            "evaluation": result.model_dump(),
            "report_markdown": report_markdown,
        },
        retrieval_hits=retrieval_hits,
        validation=_make_validation_status(
            status="passed",
            schema_name="ChapterEvaluationResult",
            message="章节评估已通过结构校验并保存。",
        ),
        artifacts={
            "report_saved": True,
            "saved_path": f"data/projects/{project_name}/evaluation/chapter_{chapter_no:03d}.md",
        },
    ).model_dump()


def pipeline_plan_write_review_update(
    project_name: str,
    chapter_no: int,
    user_requirement: str,
    word_count: str = "2000-2500"
) -> dict:
    started_at = datetime.now().isoformat(timespec="seconds")
    run_id = f"chapter_{chapter_no:03d}_{started_at.replace(':', '').replace('-', '').replace('T', '_')}"
    state = ChapterPipelineState(
        run_id=run_id,
        project_name=project_name,
        chapter_no=chapter_no,
        user_requirement=user_requirement,
        word_count=word_count,
        current_step="chapter_outline",
        next_step="chapter_outline",
        started_at=started_at,
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
        state.last_successful_step = "chapter_outline"

    if outline_step.success:
        state.next_step = "write_chapter"
        _transition_pipeline_state(state, "write_chapter", "chapter outline completed")
        try:
            chapter = write_chapter(project_name, chapter_no, state.chapter_outline, None, word_count)
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
        state.last_successful_step = "write_chapter"

    if chapter_step.success:
        state.next_step = "review_chapter"
        _transition_pipeline_state(state, "review_chapter", "chapter writing completed")
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
    if review_step.success:
        state.last_successful_step = "review_chapter"

    if chapter_step.success:
        state.next_step = "memory_update"
        _transition_pipeline_state(state, "memory_update", "review step completed")
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
    if memory_step.success:
        state.last_successful_step = "memory_update"
    elif not state.halted:
        _halt_pipeline(state, "memory_update_failed")

    if not state.halted:
        state.next_step = ""
        _transition_pipeline_state(state, "completed", "pipeline finished")
    state.finished_at = datetime.now().isoformat(timespec="seconds")
    state.success = all(step.success for step in state.steps.values() if step.status != "skipped")
    state.resumable = bool(state.halted and state.last_successful_step)

    pipeline_result = WorkflowPipelineResult(
        success=state.success,
        steps=state.steps,
        warnings=state.warnings,
    )
    result = state.model_dump()
    result["pipeline"] = pipeline_result.model_dump()
    save_pipeline_run(project_name, state.run_id, json.dumps(result, ensure_ascii=False, indent=2))
    return result


def resume_chapter_pipeline(project_name: str, run_id: str) -> dict:
    raw = load_pipeline_run(project_name, run_id)
    if not raw.strip():
        raise RuntimeError("没有找到该流水线运行记录。")
    previous = json.loads(raw)
    if not previous.get("resumable"):
        raise RuntimeError("选中的流水线运行记录没有标记为可恢复。")

    chapter_no = int(previous.get("chapter_no", 0))
    if chapter_no <= 0:
        raise RuntimeError("上一条运行记录缺少有效章节编号。")

    started_at = datetime.now().isoformat(timespec="seconds")
    resumed_run_id = f"chapter_{chapter_no:03d}_resume_{started_at.replace(':', '').replace('-', '').replace('T', '_')}"
    state = ChapterPipelineState(
        run_id=resumed_run_id,
        parent_run_id=run_id,
        project_name=project_name,
        chapter_no=chapter_no,
        user_requirement=str(previous.get("user_requirement", "")),
        word_count=str(previous.get("word_count", "2000-2500")),
        current_step="resume",
        next_step="",
        started_at=started_at,
        chapter_outline=str(previous.get("chapter_outline", "") or ""),
        chapter=str(previous.get("chapter", "") or ""),
        review=previous.get("review", {}) if isinstance(previous.get("review", {}), dict) else {},
        review_markdown=str(previous.get("review_markdown", "") or ""),
        memory_update=previous.get("memory_update", {}) if isinstance(previous.get("memory_update", {}), dict) else {},
        completed_steps=list(previous.get("completed_steps", [])),
    )
    _transition_pipeline_state(state, "resume", f"resuming from {run_id}")

    last_successful_step = str(previous.get("last_successful_step", "") or "")
    if last_successful_step == "chapter_outline":
        state.next_step = "write_chapter"
        _transition_pipeline_state(state, "write_chapter", "resuming after chapter outline")
        try:
            chapter_step = WorkflowStepResult.model_validate(
                write_chapter(project_name, chapter_no, state.chapter_outline, None, state.word_count)
            )
        except Exception as exc:
            chapter_step = _make_step_result("write_chapter", success=False, status="failed", error=str(exc))
        _record_pipeline_step(state, chapter_step)
        state.chapter = chapter_step.data.get("chapter", "")
        if not chapter_step.success:
            _halt_pipeline(state, "write_chapter_failed")
        else:
            state.last_successful_step = "write_chapter"
            last_successful_step = "write_chapter"

    if last_successful_step == "write_chapter":
        state.next_step = "review_chapter"
        _transition_pipeline_state(state, "review_chapter", "resuming after chapter writing")
        try:
            review_step = WorkflowStepResult.model_validate(review_chapter(project_name, chapter_no, state.chapter))
        except Exception as exc:
            review_step = _make_step_result("review_chapter", success=False, status="failed", error=str(exc))
        _record_pipeline_step(state, review_step)
        state.review = review_step.data.get("review", {})
        state.review_markdown = review_step.data.get("review_markdown", "")
        if review_step.success:
            state.last_successful_step = "review_chapter"
            last_successful_step = "review_chapter"

    if last_successful_step == "review_chapter":
        state.next_step = "memory_update"
        _transition_pipeline_state(state, "memory_update", "resuming after review")
        try:
            memory_step = WorkflowStepResult.model_validate(update_memory_from_chapter(project_name, chapter_no, state.chapter))
        except Exception as exc:
            memory_step = _make_step_result("memory_update", success=False, status="failed", error=str(exc))
        _record_pipeline_step(state, memory_step)
        state.memory_update = memory_step.data.get("applied_updates", {})
        if memory_step.success:
            state.last_successful_step = "memory_update"

    if state.last_successful_step == "memory_update":
        state.next_step = ""
        _transition_pipeline_state(state, "completed", "resume finished")
    elif not state.halted:
        _halt_pipeline(state, "resume_incomplete")

    state.finished_at = datetime.now().isoformat(timespec="seconds")
    state.success = state.last_successful_step == "memory_update" and not state.halted
    state.resumable = bool(state.halted and state.last_successful_step)
    pipeline_result = WorkflowPipelineResult(
        success=state.success,
        steps=state.steps,
        warnings=state.warnings,
    )
    result = state.model_dump()
    result["pipeline"] = pipeline_result.model_dump()
    save_pipeline_run(project_name, state.run_id, json.dumps(result, ensure_ascii=False, indent=2))
    return result
