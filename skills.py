import json
import hashlib
import logging
import re
from datetime import datetime
from urllib.request import Request, urlopen
from llm import call_llm
from pydantic import ValidationError
from prompts import (
    discuss_creative_profile_prompt,
    discuss_creative_profile_turn_prompt,
    discuss_chapter_prompt,
    discuss_chapter_turn_prompt,
    discuss_arc_prompt,
    discuss_arc_turn_prompt,
    arc_chapter_plan_prompt,
    comprehensive_chapter_evaluation_prompt,
    evaluate_chapter_prompt,
    discuss_outline_prompt,
    discuss_outline_turn_prompt,
    discuss_volume_prompt,
    discuss_volume_turn_prompt,
    creative_structure_prompt,
    extract_reference_knowledge_prompt,
    consolidate_extracted_knowledge_prompt,
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
    setting_extraction_prompt,
    review_chapter_prompt,
)
from memory import (
    delete_creative_profile_discussion_artifact,
    delete_chapter_discussion_artifact,
    delete_arc_discussion_artifact,
    delete_outline_discussion_artifact,
    delete_volume_discussion_artifact,
    get_recent_chapter_summaries,
    load_story_chapter_summaries,
    load_chapter_discussion_artifact,
    load_arc_discussion_artifact,
    load_arc_metadata,
    load_arc_outline,
    load_chapter_outline,
    load_chapter_outline_metadata,
    load_creative_profile,
    load_global_rules,
    load_global_prompt_options,
    load_entity_aliases,
    load_outline,
    load_outline_discussion_artifact,
    load_pipeline_run,
    load_project_rules,
    load_project_prompt_options,
    load_story_rules,
    load_story_prompt_options,
    queue_pending_knowledge_items,
    load_effective_rule_conflict_resolutions,
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
    save_creative_profile,
    save_creative_profile_discussion_artifact,
    save_global_rules,
    save_analysis_report,
    save_conflict_resolution,
    save_evaluation_json,
    save_evaluation_report,
    save_outline,
    save_pipeline_run,
    save_project_rules,
    save_review,
    save_review_json,
    save_outline_discussion_artifact,
    save_story_rules,
    save_story_chapter_summaries,
    save_volume_metadata,
    save_volume_discussion_artifact,
    save_volume_outline,
)
from prompt_options import format_prompt_options_for_prompt, merge_prompt_option_layers
from schemas import (
    ChapterWritingGuidance,
    ArcChapterPlanResult,
    ArcDiscussionResult,
    CreativeProfileDiscussionResult,
    ChapterPipelineState,
    ChapterEvaluationResult,
    ComprehensiveChapterEvaluationResult,
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
    render_comprehensive_chapter_evaluation_markdown,
    render_consistency_analysis_markdown,
    render_foreshadowing_analysis_markdown,
    render_discussion_markdown,
    render_knowledge_extraction_markdown,
    render_organized_reference_markdown,
    render_timeline_analysis_markdown,
    validate_setting_extraction_result,
    validate_review_result,
)
from retrieval import format_retrieval_context, retrieve_context
from setting_knowledge import build_generation_setting_context


_LAST_RETRIEVAL_TRACES: dict[str, list[dict]] = {}
SKILLS_LOGGER = logging.getLogger("novelforge.skills")


def _safe_stream_emit(stream_callback, text: str) -> None:
    if not stream_callback:
        return
    try:
        stream_callback(text)
    except Exception as exc:
        if getattr(exc, "cancel_generation", False):
            raise
        SKILLS_LOGGER.warning("Stream callback failed while emitting step marker: %s", exc, exc_info=True)


def _story_trace_key(prefix: str, project_name: str, story_id: str = "default", *parts: object) -> str:
    cleaned_parts = [prefix, project_name, str(story_id or "default")]
    cleaned_parts.extend(str(part) for part in parts)
    return ":".join(cleaned_parts)

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
    "memory_location": "地点设定",
    "memory_organization": "组织设定",
    "memory_power_system": "能力体系设定",
    "memory_relationship_graph": "关系图设定",
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
    "creative_profile_discussion",
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
    "memory_location",
    "memory_organization",
    "memory_power_system",
    "memory_relationship_graph",
    "review_issue",
    "analysis_consistency",
    "analysis_characters",
    "analysis_timeline",
    "analysis_foreshadowing",
    "conflict_resolution",
    "external_source",
] + KNOWLEDGE_SOURCE_TYPES

KNOWN_WORKFLOW_DEPTHS = {"只生成正文", "短篇结构+正文", "章节计划+正文", "分卷/剧情段/章节", "完整长篇流程"}
LIGHTWEIGHT_STORY_KEYWORDS = {"短篇", "中篇", "番外", "续写", "前传", "穿越", "转生", "异世界", "平行世界", "AU", "架空", "补完", "补全", "片段", "场景"}


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


SETTING_EXTRACTION_KNOWLEDGE_FIELDS = {
    "new_characters": ("characters", "characters", "角色"),
    "world_updates": ("world_rules", "world", "世界观"),
    "timeline_updates": ("timeline_events", "timeline", "时间线"),
    "foreshadowing_updates": ("narrative_techniques", "foreshadowing", "伏笔"),
}


def _stringify_knowledge_candidate(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ["summary", "content", "description", "name", "title", "event", "detail"]:
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _knowledge_candidate_name(text: str, fallback: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return fallback
    for separator in ["：", ":", "，", ",", "。", ".", "；", ";"]:
        if separator in cleaned:
            head = cleaned.split(separator, 1)[0].strip()
            if head:
                cleaned = head
                break
    return cleaned[:36].rstrip() or fallback


def _stable_pending_knowledge_id(story_id: str, chapter_no: int, field_name: str, index: int, summary: str) -> str:
    digest = hashlib.md5(f"{story_id}:{chapter_no}:{field_name}:{index}:{summary}".encode("utf-8")).hexdigest()[:12]
    return f"pending_chapter_update_{story_id}_{chapter_no:04d}_{field_name}_{index:03d}_{digest}"


def build_pending_knowledge_from_setting_extraction(update_data: dict, story_id: str, chapter_no: int) -> list[dict]:
    items: list[dict] = []
    for field_name, (category, setting_field, label) in SETTING_EXTRACTION_KNOWLEDGE_FIELDS.items():
        values = update_data.get(field_name, [])
        if not isinstance(values, list):
            values = [values]
        for index, value in enumerate(values, start=1):
            summary = _stringify_knowledge_candidate(value)
            if not summary:
                continue
            details = {
                "原始提炼": summary,
                "来源字段": setting_field,
                "来源章节": str(chapter_no),
            }
            if isinstance(value, dict):
                details.update({
                    str(key): _stringify_knowledge_candidate(item)
                    for key, item in value.items()
                    if _stringify_knowledge_candidate(item)
                })
            items.append({
                "pending_id": _stable_pending_knowledge_id(story_id, chapter_no, field_name, index, summary),
                "category": category,
                "name": _knowledge_candidate_name(summary, f"第 {chapter_no} 章{label}更新 {index}"),
                "summary": summary,
                "details": details,
                "evidence": [{
                    "source_title": f"第 {chapter_no} 章正文",
                    "quote": summary[:160],
                    "note": "由章节设定提炼流程生成，确认后成为故事级核心设定条目。",
                }],
                "confidence": 0.7,
                "importance": 0.75,
                "evidence_strength": 0.6,
                "canon_status": "project",
                "extraction_mode": "chapter_update",
                "tags": ["章节更新", label, f"chapter:{chapter_no}", setting_field],
                "setting_role": "core",
                "setting_scope": "story",
                "setting_field": setting_field,
                "story_id": story_id,
                "injection_policy": "always",
                "source_chapter_no": chapter_no,
            })
    return items


def build_pending_knowledge_from_memory_update(update_data: dict, story_id: str, chapter_no: int) -> list[dict]:
    return build_pending_knowledge_from_setting_extraction(update_data, story_id, chapter_no)


def _append_prompt_options_to_rules(
    rules_text: str,
    project_name: str,
    scope: str,
    story_id: str,
    prompt_option_ids: list[str] | None = None,
) -> str:
    try:
        options = merge_prompt_option_layers(
            load_global_prompt_options(),
            load_project_prompt_options(project_name),
            load_story_prompt_options(project_name, story_id),
        )
        option_text = format_prompt_options_for_prompt(options, scope, selected_ids=prompt_option_ids)
    except Exception as exc:
        logging.getLogger("novelforge").warning(
            "Failed to build prompt option text: project=%s story=%s scope=%s error=%s",
            project_name, story_id, scope, exc,
        )
        option_text = ""
    if not option_text:
        return rules_text
    return f"{rules_text}\n\n{option_text}"


def _build_rules_text(
    project_name: str,
    scope: str,
    story_id: str = "default",
    prompt_option_ids: list[str] | None = None,
) -> str:
    global_rules = load_global_rules()
    project_rules = load_project_rules(project_name)
    story_rules = load_story_rules(project_name, story_id)
    conflict_resolutions = load_effective_rule_conflict_resolutions(project_name, story_id, scope)
    rules_text = format_rules_for_prompt(
        global_rules,
        project_rules,
        scope,
        story_rules=story_rules,
        conflict_resolutions=conflict_resolutions,
    )
    try:
        profile = load_creative_profile(project_name, story_id)
    except Exception:
        profile = {}
    if not profile:
        return _append_prompt_options_to_rules(rules_text, project_name, scope, story_id, prompt_option_ids)

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
        f"- 当前世界线：{profile.get('worldline_label') or profile.get('worldline_id') or '未设置'}",
        f"- 世界线检索模式：{profile.get('worldline_retrieval_mode', 'prefer')}",
    ]
    return _append_prompt_options_to_rules(f"{rules_text}\n\n" + "\n".join(profile_lines), project_name, scope, story_id, prompt_option_ids)


def _build_retrieval_context(
    project_name: str,
    query: str,
    *,
    story_id: str = "default",
    allowed_source_types: list[str] | None = None,
    allowed_scopes: list[str] | None = None,
    top_k: int | None = None,
    retrieval_mode: str = "hybrid",
    trace_key: str | None = None,
    reference_focus: list[str] | None = None,
    reference_strength: str | None = None,
    retrieval_profile: str | None = None,
    worldline_id: str | None = None,
    worldline_mode: str | None = None,
) -> str:
    if reference_focus is None or reference_strength is None or worldline_id is None or worldline_mode is None:
        try:
            profile = load_creative_profile(project_name, story_id)
            if reference_focus is None:
                reference_focus = profile.get("reference_focus")
            if reference_strength is None:
                reference_strength = profile.get("reference_strength")
            if worldline_id is None:
                worldline_id = profile.get("worldline_id")
            if worldline_mode is None:
                worldline_mode = profile.get("worldline_retrieval_mode")
        except Exception as exc:
            logging.getLogger("novelforge").warning(
                "Failed to load creative profile for retrieval context: project=%s story=%s error=%s",
                project_name, story_id, exc,
            )
    hits = retrieve_context(
        project_name,
        query,
        top_k=top_k,
        allowed_scopes=allowed_scopes,
        allowed_source_types=allowed_source_types,
        retrieval_mode=retrieval_mode,
        reference_focus=reference_focus,
        reference_strength=reference_strength,
        retrieval_profile=retrieval_profile,
        worldline_id=worldline_id,
        worldline_mode=worldline_mode or "prefer",
        story_id=story_id,
    )
    _set_retrieval_trace(trace_key, hits)
    return format_retrieval_context(hits)


def _build_discussion_retrieval_context(
    project_name: str,
    query: str,
    *,
    story_id: str = "default",
    trace_key: str | None = None,
    top_k: int | None = None,
    retrieval_profile: str = "outline_discussion",
) -> str:
    return _build_retrieval_context(
        project_name,
        query,
        story_id=story_id,
        allowed_scopes=["project", "canon", "reference"],
        top_k=top_k,
        trace_key=trace_key,
        retrieval_profile=retrieval_profile,
    )


def _call_json_llm(prompt: str, empty_error: str, stream_callback=None) -> dict:
    result = call_llm(prompt, stream_callback=stream_callback)
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


def save_rule_text(project_name: str, scope: str, target: str, rule_text: str, story_id: str = "default") -> dict:
    if target not in {"global", "project", "story"}:
        raise ValueError("Rule target must be 'global', 'project', or 'story'.")

    if target == "story":
        rules = load_story_rules(project_name, story_id)
    elif target == "global":
        rules = load_global_rules()
    else:
        rules = load_project_rules(project_name)

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
    elif target == "story":
        save_story_rules(project_name, story_id, rules)
    else:
        save_project_rules(project_name, rules)

    return {
        "status": "saved",
        "target": target,
        "scope": scope,
        "saved_rules": new_rules,
        "total_rules": len(merged),
    }


def organize_reference_text(project_name: str, source_title: str, raw_text: str, story_id: str = "default", stream_callback=None) -> dict:
    prompt = organize_reference_prompt(
        source_title.strip() or "未命名资料",
        raw_text,
        _build_rules_text(project_name, "all", story_id=story_id),
    )
    payload = _call_json_llm(prompt, "模型没有返回可整理的资料结果。", stream_callback=stream_callback)
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


def _format_entity_alias_context(project_name: str, limit: int = 80) -> str:
    lines = []
    for group in load_entity_aliases(project_name)[:limit]:
        if not isinstance(group, dict):
            continue
        canonical_name = str(group.get("canonical_name") or "").strip()
        aliases = [
            str(alias).strip()
            for alias in group.get("aliases", [])
            if str(alias).strip() and str(alias).strip() != canonical_name
        ] if isinstance(group.get("aliases", []), list) else []
        if not canonical_name:
            continue
        category = str(group.get("category") or "unknown").strip()
        alias_text = "、".join(aliases[:8]) if aliases else "无"
        lines.append(f"- {category} / 主名称：{canonical_name} / 别名：{alias_text}")
    return "\n".join(lines) if lines else "当前无已知别名。"


def extract_reference_knowledge(
    project_name: str,
    source_title: str,
    raw_text: str,
    enabled_categories: list[str] | None = None,
    extraction_mode: str = "general",
    story_id: str = "default",
    custom_instructions: str = "",
    stream_callback=None,
) -> dict:
    prompt = extract_reference_knowledge_prompt(
        source_title.strip() or "未命名资料",
        raw_text,
        enabled_categories or [],
        _build_rules_text(project_name, "all", story_id=story_id),
        extraction_mode=extraction_mode,
        alias_context=_format_entity_alias_context(project_name),
        custom_instructions=custom_instructions,
    )
    payload = _call_json_llm(prompt, "模型没有返回可提取的知识结果。", stream_callback=stream_callback)
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
            "extraction_mode": extraction_mode,
        },
        validation=_make_validation_status(
            status="passed",
            schema_name="KnowledgeExtractionResult",
            message="资料知识提取结果已通过结构校验。",
        ),
    ).model_dump()


def consolidate_extracted_knowledge(
    project_name: str,
    source_title: str,
    extracted_items: list[dict],
    enabled_categories: list[str] | None = None,
    consolidation_mode: str = "balanced",
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    compact_items = []
    for item in extracted_items:
        if not isinstance(item, dict):
            continue
        compact_items.append({
            "pending_id": item.get("pending_id", ""),
            "category": item.get("category", ""),
            "name": item.get("name", ""),
            "summary": item.get("summary", ""),
            "details": item.get("details", {}),
            "evidence": item.get("evidence", []),
            "confidence": item.get("confidence", 0.7),
            "importance": item.get("importance", 0.5),
            "evidence_strength": item.get("evidence_strength", 0.5),
            "canon_status": item.get("canon_status", "unknown"),
            "tags": item.get("tags", []),
            "source_title": item.get("source_title", ""),
            "source_segment_id": item.get("source_segment_id", ""),
            "source_segment_index": item.get("source_segment_index"),
            "source_segment_title": item.get("source_segment_title", ""),
        })

    prompt = consolidate_extracted_knowledge_prompt(
        source_title.strip() or "未命名资料批次",
        json.dumps(compact_items, ensure_ascii=False, indent=2),
        enabled_categories or [],
        consolidation_mode=consolidation_mode,
        rules_text=_build_rules_text(project_name, "all", story_id=story_id),
    )
    payload = _call_json_llm(prompt, "模型没有返回可整理的知识结果。", stream_callback=stream_callback)
    try:
        result = KnowledgeExtractionResult.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"批次知识整理结构校验失败：{format_schema_validation_error(exc)}") from exc

    return _make_step_result(
        "consolidate_extracted_knowledge",
        success=True,
        status="completed",
        data={
            "knowledge_extraction": result.model_dump(),
            "report_markdown": render_knowledge_extraction_markdown(result),
            "consolidation_mode": consolidation_mode,
            "source_item_count": len(compact_items),
        },
        validation=_make_validation_status(
            status="passed",
            schema_name="KnowledgeExtractionResult",
            message="批次知识整理结果已通过结构校验。",
        ),
    ).model_dump()


def organize_reference_html(project_name: str, source_title: str, html: str, source_url: str, story_id: str = "default", stream_callback=None) -> dict:
    extracted_text = _extract_web_text_from_html(html)
    if not extracted_text.strip():
        raise RuntimeError("抓取到的页面中没有提取出可阅读文本。")

    result = organize_reference_text(project_name, source_title, extracted_text, story_id=story_id, stream_callback=stream_callback)
    result.setdefault("artifacts", {})
    result["artifacts"]["source_url"] = source_url
    result["artifacts"]["raw_text_excerpt"] = extracted_text[:2000]
    return result


def organize_reference_url(project_name: str, source_title: str, source_url: str, story_id: str = "default", stream_callback=None) -> dict:
    html = _fetch_web_page(source_url)
    return organize_reference_html(project_name, source_title, html, source_url, story_id=story_id, stream_callback=stream_callback)


def discuss_outline(project_name: str, user_idea: str, story_id: str = "default", stream_callback=None) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    trace_key = _story_trace_key("outline_discuss", project_name, story_id)
    retrieval_context = _build_discussion_retrieval_context(
        project_name,
        user_idea,
        story_id=story_id,
        trace_key=trace_key,
        retrieval_profile="outline_discussion",
    )
    prompt = discuss_outline_prompt(memory, user_idea, _build_rules_text(project_name, "outline", story_id=story_id), retrieval_context=retrieval_context)
    payload = _call_json_llm(prompt, "模型没有返回全书讨论结果。", stream_callback=stream_callback)
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
        retrieval_hits=get_retrieval_trace(trace_key),
        validation=_make_validation_status(
            status="passed",
            schema_name="OutlineDiscussionResult",
            message="全书讨论结果已通过结构校验。",
        ),
    ).model_dump()


def discuss_creative_profile(project_name: str, user_idea: str, story_id: str = "default", stream_callback=None) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    current_profile = load_creative_profile(project_name, story_id)
    trace_key = _story_trace_key("creative_profile_discuss", project_name, story_id)
    retrieval_context = _build_retrieval_context(
        project_name,
        user_idea,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
        story_id=story_id,
        retrieval_profile="creative_profile_discussion",
    )
    prompt = discuss_creative_profile_prompt(
        memory, current_profile, user_idea,
        _build_rules_text(project_name, "all", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_json_llm(prompt, "模型没有返回创作配置讨论结果。", stream_callback=stream_callback)
    try:
        result = CreativeProfileDiscussionResult.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"创作配置讨论结构校验失败：{format_schema_validation_error(exc)}") from exc

    return _make_step_result(
        "discuss_creative_profile",
        success=True,
        status="completed",
        data={
            "discussion": result.model_dump(),
            "report_markdown": render_discussion_markdown(result),
        },
        retrieval_hits=get_retrieval_trace(trace_key),
        validation=_make_validation_status(
            status="passed",
            schema_name="CreativeProfileDiscussionResult",
            message="创作配置讨论结果已通过结构校验。",
        ),
    ).model_dump()


def discuss_chapter(project_name: str, chapter_no: int, user_requirement: str, story_id: str = "default", stream_callback=None) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    outline = load_outline(project_name, story_id=story_id)
    chapter_metadata = load_chapter_outline_metadata(project_name, chapter_no, story_id=story_id)
    volume_no = chapter_metadata.get("volume_no")
    arc_no = chapter_metadata.get("arc_no")
    volume_outline = load_volume_outline(project_name, int(volume_no), story_id=story_id) if volume_no else ""
    arc_outline = load_arc_outline(project_name, int(arc_no), story_id=story_id) if arc_no else ""
    volume_discussion_context = _format_discussion_context(
        load_volume_discussion_artifact(project_name, int(volume_no), story_id=story_id) if volume_no else {},
        "当前分卷暂无已批准讨论结论。",
    )
    arc_discussion_context = _format_discussion_context(
        load_arc_discussion_artifact(project_name, int(arc_no), story_id=story_id) if arc_no else {},
        "当前剧情段暂无已批准讨论结论。",
    )
    chapter_discussion_context = _format_discussion_context(
        load_chapter_discussion_artifact(project_name, chapter_no, story_id=story_id),
        "当前章节暂无已批准讨论结论。",
    )
    recent_summaries = get_recent_chapter_summaries(project_name, story_id=story_id)
    trace_key = _story_trace_key("chapter_discuss", project_name, story_id, chapter_no)
    retrieval_context = _build_discussion_retrieval_context(
        project_name,
        f"第{chapter_no}章 {user_requirement} {outline} {volume_outline} {arc_outline} {volume_discussion_context} {arc_discussion_context} {chapter_discussion_context}",
        story_id=story_id,
        trace_key=trace_key,
        retrieval_profile="chapter_discussion",
    )
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
        _build_rules_text(project_name, "chapter_outline", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_json_llm(prompt, "模型没有返回章节讨论结果。", stream_callback=stream_callback)
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
        retrieval_hits=get_retrieval_trace(trace_key),
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
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    trace_key = _story_trace_key("outline_discuss_turn", project_name, story_id)
    retrieval_context = _build_discussion_retrieval_context(
        project_name,
        f"{user_idea} {latest_user_message} {current_discussion or {}}",
        story_id=story_id,
        trace_key=trace_key,
        retrieval_profile="outline_discussion",
    )
    prompt = discuss_outline_turn_prompt(
        memory,
        user_idea,
        messages,
        current_discussion,
        latest_user_message,
        _build_rules_text(project_name, "outline", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_json_llm(prompt, "模型没有返回本轮全书讨论结果。", stream_callback=stream_callback)
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
        retrieval_hits=get_retrieval_trace(trace_key),
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
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    outline = load_outline(project_name, story_id=story_id)
    chapter_metadata = load_chapter_outline_metadata(project_name, chapter_no, story_id=story_id)
    volume_no = chapter_metadata.get("volume_no")
    arc_no = chapter_metadata.get("arc_no")
    volume_outline = load_volume_outline(project_name, int(volume_no), story_id=story_id) if volume_no else ""
    arc_outline = load_arc_outline(project_name, int(arc_no), story_id=story_id) if arc_no else ""
    volume_discussion_context = _format_discussion_context(
        load_volume_discussion_artifact(project_name, int(volume_no), story_id=story_id) if volume_no else {},
        "当前分卷暂无已批准讨论结论。",
    )
    arc_discussion_context = _format_discussion_context(
        load_arc_discussion_artifact(project_name, int(arc_no), story_id=story_id) if arc_no else {},
        "当前剧情段暂无已批准讨论结论。",
    )
    chapter_discussion_context = _format_discussion_context(
        load_chapter_discussion_artifact(project_name, chapter_no, story_id=story_id),
        "当前章节暂无已批准讨论结论。",
    )
    recent_summaries = get_recent_chapter_summaries(project_name, story_id=story_id)
    trace_key = _story_trace_key("chapter_discuss_turn", project_name, story_id, chapter_no)
    retrieval_context = _build_discussion_retrieval_context(
        project_name,
        f"第{chapter_no}章 {user_requirement} {latest_user_message} {outline} {volume_outline} {arc_outline} {volume_discussion_context} {arc_discussion_context} {chapter_discussion_context} {current_discussion or {}}",
        story_id=story_id,
        trace_key=trace_key,
        retrieval_profile="chapter_discussion",
    )
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
        _build_rules_text(project_name, "chapter_outline", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_json_llm(prompt, "模型没有返回本轮章节讨论结果。", stream_callback=stream_callback)
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
        retrieval_hits=get_retrieval_trace(trace_key),
        validation=_make_validation_status(
            status="passed",
            schema_name="ChapterDiscussionResult",
            message="本轮章节讨论结果已通过结构校验。",
        ),
    ).model_dump()


def discuss_creative_profile_turn(
    project_name: str,
    user_idea: str,
    messages: list[dict],
    current_discussion: dict | None,
    latest_user_message: str,
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    current_profile = load_creative_profile(project_name, story_id)
    trace_key = _story_trace_key("creative_profile_discuss_turn", project_name, story_id)
    retrieval_context = _build_retrieval_context(
        project_name,
        latest_user_message,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
        story_id=story_id,
        retrieval_profile="creative_profile_discussion",
    )
    prompt = discuss_creative_profile_turn_prompt(
        memory,
        current_profile,
        user_idea,
        messages,
        current_discussion,
        latest_user_message,
        _build_rules_text(project_name, "all", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_json_llm(prompt, "模型没有返回本轮创作配置讨论结果。", stream_callback=stream_callback)
    assistant_message = str(payload.get("assistant_message", "") or "").strip()
    discussion_payload = payload.get("discussion", {}) if isinstance(payload, dict) else {}

    try:
        result = CreativeProfileDiscussionResult.model_validate(discussion_payload)
    except ValidationError as exc:
        raise RuntimeError(f"本轮创作配置讨论结构校验失败：{format_schema_validation_error(exc)}") from exc

    return _make_step_result(
        "discuss_creative_profile_turn",
        success=True,
        status="completed",
        data={
            "assistant_message": assistant_message,
            "discussion": result.model_dump(),
            "report_markdown": render_discussion_markdown(result),
        },
        retrieval_hits=get_retrieval_trace(trace_key),
        validation=_make_validation_status(
            status="passed",
            schema_name="CreativeProfileDiscussionResult",
            message="本轮创作配置讨论结果已通过结构校验。",
        ),
    ).model_dump()


def discuss_volume(
    project_name: str,
    volume_no: int,
    volume_title: str,
    volume_summary: str,
    user_requirement: str,
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    story_outline = load_outline(project_name, story_id=story_id)
    trace_key = _story_trace_key("volume_discuss", project_name, story_id, volume_no)
    retrieval_context = _build_discussion_retrieval_context(
        project_name,
        f"第{volume_no}卷 {volume_title} {volume_summary} {user_requirement} {story_outline}",
        story_id=story_id,
        trace_key=trace_key,
        retrieval_profile="volume_discussion",
    )
    prompt = discuss_volume_prompt(
        memory,
        story_outline,
        volume_no,
        volume_title,
        volume_summary,
        user_requirement,
        _build_rules_text(project_name, "outline", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_json_llm(prompt, "模型没有返回分卷讨论结果。", stream_callback=stream_callback)
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
        retrieval_hits=get_retrieval_trace(trace_key),
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
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    story_outline = load_outline(project_name, story_id=story_id)
    trace_key = _story_trace_key("volume_discuss_turn", project_name, story_id, volume_no)
    retrieval_context = _build_discussion_retrieval_context(
        project_name,
        f"第{volume_no}卷 {volume_title} {volume_summary} {user_requirement} {latest_user_message} {story_outline} {current_discussion or {}}",
        story_id=story_id,
        trace_key=trace_key,
        retrieval_profile="volume_discussion",
    )
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
        _build_rules_text(project_name, "outline", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_json_llm(prompt, "模型没有返回本轮分卷讨论结果。", stream_callback=stream_callback)
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
        retrieval_hits=get_retrieval_trace(trace_key),
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
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    story_outline = load_outline(project_name, story_id=story_id)
    volume_outline = load_volume_outline(project_name, int(volume_no), story_id=story_id) if volume_no else ""
    trace_key = _story_trace_key("arc_discuss", project_name, story_id, arc_no)
    retrieval_context = _build_discussion_retrieval_context(
        project_name,
        f"剧情段 {arc_no:03d} 第{volume_no or 0}卷 {arc_title} {arc_summary} {estimated_chapter_count or ''} {target_word_count_range} {user_requirement} {story_outline} {volume_outline}",
        story_id=story_id,
        trace_key=trace_key,
        retrieval_profile="arc_discussion",
    )
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
        _build_rules_text(project_name, "outline", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_json_llm(prompt, "模型没有返回剧情段讨论结果。", stream_callback=stream_callback)
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
        retrieval_hits=get_retrieval_trace(trace_key),
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
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    story_outline = load_outline(project_name, story_id=story_id)
    volume_outline = load_volume_outline(project_name, int(volume_no), story_id=story_id) if volume_no else ""
    trace_key = _story_trace_key("arc_discuss_turn", project_name, story_id, arc_no)
    retrieval_context = _build_discussion_retrieval_context(
        project_name,
        f"剧情段 {arc_no:03d} 第{volume_no or 0}卷 {arc_title} {arc_summary} {estimated_chapter_count or ''} {target_word_count_range} {user_requirement} {latest_user_message} {story_outline} {volume_outline} {current_discussion or {}}",
        story_id=story_id,
        trace_key=trace_key,
        retrieval_profile="arc_discussion",
    )
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
        _build_rules_text(project_name, "outline", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_json_llm(prompt, "模型没有返回本轮剧情段讨论结果。", stream_callback=stream_callback)
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
        retrieval_hits=get_retrieval_trace(trace_key),
        validation=_make_validation_status(
            status="passed",
            schema_name="ArcDiscussionResult",
            message="本轮剧情段讨论结果已通过结构校验。",
        ),
    ).model_dump()


def approve_volume_discussion(project_name: str, volume_no: int, discussion_step: dict, story_id: str = "default") -> dict:
    discussion = discussion_step.get("data", {}).get("discussion", {}) if isinstance(discussion_step, dict) else {}
    report_markdown = discussion_step.get("data", {}).get("report_markdown", "") if isinstance(discussion_step, dict) else ""
    if not isinstance(discussion, dict) or not discussion:
        raise RuntimeError("没有可批准的分卷讨论结果。")
    if not discussion.get("approval_ready"):
        raise RuntimeError("分卷讨论结果尚未达到可批准状态。")
    save_volume_discussion_artifact(project_name, volume_no, discussion, report_markdown, story_id)
    return {
        "volume_no": volume_no,
        "discussion": discussion,
        "report_markdown": report_markdown,
        "saved_path": f"data/projects/{project_name}/stories/{story_id}/volumes/volume_{volume_no:03d}.discussion.json",
    }


def clear_volume_discussion_approval(project_name: str, volume_no: int, story_id: str = "default") -> bool:
    return delete_volume_discussion_artifact(project_name, volume_no, story_id)


def approve_arc_discussion(project_name: str, arc_no: int, discussion_step: dict, story_id: str = "default") -> dict:
    discussion = discussion_step.get("data", {}).get("discussion", {}) if isinstance(discussion_step, dict) else {}
    report_markdown = discussion_step.get("data", {}).get("report_markdown", "") if isinstance(discussion_step, dict) else ""
    if not isinstance(discussion, dict) or not discussion:
        raise RuntimeError("没有可批准的剧情段讨论结果。")
    if not discussion.get("approval_ready"):
        raise RuntimeError("剧情段讨论结果尚未达到可批准状态。")
    save_arc_discussion_artifact(project_name, arc_no, discussion, report_markdown, story_id)
    return {
        "arc_no": arc_no,
        "discussion": discussion,
        "report_markdown": report_markdown,
        "saved_path": f"data/projects/{project_name}/stories/{story_id}/arcs/arc_{arc_no:03d}.discussion.json",
    }


def clear_arc_discussion_approval(project_name: str, arc_no: int, story_id: str = "default") -> bool:
    return delete_arc_discussion_artifact(project_name, arc_no, story_id)


def approve_outline_discussion(project_name: str, discussion_step: dict, story_id: str = "default") -> dict:
    discussion = discussion_step.get("data", {}).get("discussion", {}) if isinstance(discussion_step, dict) else {}
    report_markdown = discussion_step.get("data", {}).get("report_markdown", "") if isinstance(discussion_step, dict) else ""
    if not isinstance(discussion, dict) or not discussion:
        raise RuntimeError("没有可批准的全书讨论结果。")
    if not discussion.get("approval_ready"):
        raise RuntimeError("全书讨论结果尚未达到可批准状态。")
    save_outline_discussion_artifact(project_name, discussion, report_markdown, story_id)
    return {
        "discussion": discussion,
        "report_markdown": report_markdown,
        "saved_path": f"data/projects/{project_name}/stories/{story_id}/outline.discussion.json",
    }


def clear_outline_discussion_approval(project_name: str, story_id: str = "default") -> bool:
    return delete_outline_discussion_artifact(project_name, story_id)


def save_creative_profile_discussion_result(project_name: str, discussion_step: dict, story_id: str = "default") -> dict:
    discussion = discussion_step.get("data", {}).get("discussion", {}) if isinstance(discussion_step, dict) else {}
    report_markdown = discussion_step.get("data", {}).get("report_markdown", "") if isinstance(discussion_step, dict) else ""
    if not isinstance(discussion, dict) or not discussion:
        raise RuntimeError("没有可保存的创作配置讨论结果。")
    if not discussion.get("approval_ready"):
        raise RuntimeError("创作配置讨论尚未收敛，继续补充后再保存讨论结论。")
    discussion_result = CreativeProfileDiscussionResult.model_validate(discussion)
    discussion_payload = discussion_result.model_dump()
    save_creative_profile_discussion_artifact(project_name, discussion_payload, report_markdown, story_id)
    return {
        "discussion": discussion_payload,
        "report_markdown": report_markdown,
        "saved_path": f"data/projects/{project_name}/stories/{story_id}/creative_profile.discussion.json",
    }


def approve_creative_profile_discussion(project_name: str, discussion_step: dict, story_id: str = "default") -> dict:
    saved_discussion = save_creative_profile_discussion_result(project_name, discussion_step, story_id)
    recommended_profile = CreativeProfileDiscussionResult.model_validate(saved_discussion["discussion"]).recommended_profile.model_dump()
    recommended_profile.pop("notes", None)
    save_creative_profile(project_name, recommended_profile, story_id, mark_configured=True)
    return {
        **saved_discussion,
        "saved_profile": recommended_profile,
    }


def clear_creative_profile_discussion_approval(project_name: str, story_id: str = "default") -> bool:
    return delete_creative_profile_discussion_artifact(project_name, story_id)


def approve_chapter_discussion(project_name: str, chapter_no: int, discussion_step: dict, story_id: str = "default") -> dict:
    discussion = discussion_step.get("data", {}).get("discussion", {}) if isinstance(discussion_step, dict) else {}
    report_markdown = discussion_step.get("data", {}).get("report_markdown", "") if isinstance(discussion_step, dict) else ""
    if not isinstance(discussion, dict) or not discussion:
        raise RuntimeError("没有可批准的章节讨论结果。")
    if not discussion.get("approval_ready"):
        raise RuntimeError("章节讨论结果尚未达到可批准状态。")
    save_chapter_discussion_artifact(project_name, chapter_no, discussion, report_markdown, story_id)
    return {
        "chapter_no": chapter_no,
        "discussion": discussion,
        "report_markdown": report_markdown,
        "saved_path": f"data/projects/{project_name}/stories/{story_id}/chapter_outlines/chapter_{chapter_no:03d}.discussion.json",
    }


def clear_chapter_discussion_approval(project_name: str, chapter_no: int, story_id: str = "default") -> bool:
    return delete_chapter_discussion_artifact(project_name, chapter_no, story_id)


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

def generate_outline(project_name: str, user_idea: str, story_id: str = "default", stream_callback=None) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    approved_discussion_context = _format_discussion_context(
        load_outline_discussion_artifact(project_name, story_id=story_id),
        "当前全书暂无已批准讨论结论。",
    )
    trace_key = _story_trace_key("outline", project_name, story_id)
    retrieval_context = _build_retrieval_context(
        project_name,
        f"{user_idea} {approved_discussion_context}",
        allowed_source_types=["outline", "outline_discussion", "memory_character", "memory_world", "memory_au_rule", "memory_relationship", "memory_timeline", "memory_foreshadowing", "memory_active_constraint", "external_source"] + KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
        story_id=story_id,
        retrieval_profile="outline_generation",
    )
    prompt = merge_retrieval_context(
        outline_prompt(memory, f"{user_idea}\n\n已批准讨论结论：\n{approved_discussion_context}".strip(), _build_rules_text(project_name, "outline", story_id=story_id)),
        retrieval_context,
    )
    outline = call_llm(prompt, stream_callback=stream_callback)
    if not outline.strip():
        raise RuntimeError("模型没有返回全书大纲。")
    save_outline(project_name, outline, story_id=story_id)
    return _make_step_result(
        "outline",
        success=True,
        status="completed",
        data={"outline": outline},
        retrieval_hits=get_retrieval_trace(trace_key),
        artifacts={"saved_path": f"data/projects/{project_name}/stories/{story_id}/outline.md"},
    ).model_dump()


def generate_volume_outline(
    project_name: str,
    volume_no: int,
    volume_title: str,
    volume_summary: str,
    user_requirement: str,
    status: str = "draft",
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    story_outline = load_outline(project_name, story_id=story_id)
    approved_discussion_context = _format_discussion_context(
        load_volume_discussion_artifact(project_name, volume_no, story_id=story_id),
        "当前分卷暂无已批准讨论结论。",
    )
    trace_key = _story_trace_key("volume_outline", project_name, story_id, volume_no)
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
        story_id=story_id,
        retrieval_profile="outline_generation",
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
            _build_rules_text(project_name, "outline", story_id=story_id),
        ),
        retrieval_context,
    )
    outline = call_llm(prompt, stream_callback=stream_callback)
    if not outline.strip():
        raise RuntimeError("模型没有返回分卷大纲。")
    save_volume_outline(project_name, volume_no, outline, story_id=story_id)
    save_volume_metadata(project_name, volume_no, {"title": volume_title, "summary": volume_summary, "status": status}, story_id=story_id)
    return _make_step_result(
        "volume_outline",
        success=True,
        status="completed",
        data={"volume_outline": outline, "volume_metadata": {"volume_no": volume_no, "title": volume_title, "summary": volume_summary, "status": status}},
        retrieval_hits=get_retrieval_trace(trace_key),
        artifacts={
            "saved_path": f"data/projects/{project_name}/stories/{story_id}/volumes/volume_{volume_no:03d}.md",
            "metadata_path": f"data/projects/{project_name}/stories/{story_id}/volumes/volume_{volume_no:03d}.meta.json",
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
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    story_outline = load_outline(project_name, story_id=story_id)
    volume_outline = load_volume_outline(project_name, int(volume_no), story_id=story_id) if volume_no else ""
    approved_discussion_context = _format_discussion_context(
        load_arc_discussion_artifact(project_name, arc_no, story_id=story_id),
        "当前剧情段暂无已批准讨论结论。",
    )
    trace_key = _story_trace_key("arc_outline", project_name, story_id, arc_no)
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
        story_id=story_id,
        retrieval_profile="outline_generation",
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
            _build_rules_text(project_name, "outline", story_id=story_id),
        ),
        retrieval_context,
    )
    outline = call_llm(prompt, stream_callback=stream_callback)
    if not outline.strip():
        raise RuntimeError("模型没有返回剧情段大纲。")
    save_arc_outline(project_name, arc_no, outline, story_id=story_id)
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
        story_id=story_id,
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
            "saved_path": f"data/projects/{project_name}/stories/{story_id}/arcs/arc_{arc_no:03d}.md",
            "metadata_path": f"data/projects/{project_name}/stories/{story_id}/arcs/arc_{arc_no:03d}.meta.json",
        },
    ).model_dump()


def generate_arc_chapter_plan(
    project_name: str,
    arc_no: int,
    start_chapter_no: int,
    chapter_count: int,
    user_requirement: str = "",
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    arc_meta = load_arc_metadata(project_name, arc_no, story_id=story_id)
    volume_no = arc_meta.get("volume_no")
    memory = build_generation_setting_context(project_name, story_id)
    story_outline = load_outline(project_name, story_id=story_id)
    volume_outline = load_volume_outline(project_name, int(volume_no), story_id=story_id) if volume_no else ""
    arc_outline = load_arc_outline(project_name, arc_no, story_id=story_id)
    trace_key = _story_trace_key("arc_chapter_plan", project_name, story_id, arc_no)
    retrieval_context = _build_retrieval_context(
        project_name,
        f"剧情段 {arc_no:03d} 章节分配 {arc_meta.get('title', '')} {arc_meta.get('summary', '')} {arc_outline} {user_requirement}",
        story_id=story_id,
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
        retrieval_profile="chapter_planning",
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
            _build_rules_text(project_name, "chapter_outline", story_id=story_id),
        ),
        retrieval_context,
    )
    payload = _call_json_llm(prompt, "模型没有返回剧情段章节分配计划。", stream_callback=stream_callback)
    try:
        result = ArcChapterPlanResult.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"剧情段章节分配计划结构校验失败：{format_schema_validation_error(exc)}") from exc

    report_markdown = render_arc_chapter_plan_markdown(result)
    save_arc_chapter_plan(project_name, arc_no, result.model_dump(), report_markdown, story_id=story_id)
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
            "saved_path": f"data/projects/{project_name}/stories/{story_id}/arcs/arc_{arc_no:03d}.chapter_plan.json",
        },
    ).model_dump()


def generate_creative_structure(
    project_name: str,
    chapter_no: int,
    user_requirement: str,
    *,
    save_as_chapter_outline: bool = True,
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    profile = load_creative_profile(project_name, story_id)
    trace_key = _story_trace_key("creative_structure", project_name, story_id, chapter_no)
    retrieval_context = _build_retrieval_context(
        project_name,
        f"{profile} {user_requirement}",
        allowed_scopes=["project", "canon", "reference"],
        top_k=8,
        trace_key=trace_key,
        story_id=story_id,
        retrieval_profile="chapter_planning",
    )
    prompt = merge_retrieval_context(
        creative_structure_prompt(
            memory,
            profile,
            user_requirement,
            _build_rules_text(project_name, "chapter_outline", story_id=story_id),
        ),
        retrieval_context,
    )
    structure = call_llm(prompt, stream_callback=stream_callback)
    if not structure.strip():
        raise RuntimeError("模型没有返回创作结构。")

    artifacts = {}
    if save_as_chapter_outline:
        save_chapter_outline(project_name, chapter_no, structure, story_id=story_id)
        artifacts["saved_path"] = f"data/projects/{project_name}/stories/{story_id}/chapter_outlines/chapter_{chapter_no:03d}.md"

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
    story_id: str = "default",
    stream_callback=None,
    save_output: bool = True,
) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    outline = load_outline(project_name, story_id=story_id)
    existing_metadata = load_chapter_outline_metadata(project_name, chapter_no, story_id=story_id)
    effective_volume_no = volume_no if volume_no is not None else existing_metadata.get("volume_no")
    effective_arc_no = arc_no if arc_no is not None else existing_metadata.get("arc_no")
    volume_outline = load_volume_outline(project_name, int(effective_volume_no), story_id=story_id) if effective_volume_no else ""
    arc_outline = load_arc_outline(project_name, int(effective_arc_no), story_id=story_id) if effective_arc_no else ""
    volume_discussion_context = _format_discussion_context(
        load_volume_discussion_artifact(project_name, int(effective_volume_no), story_id=story_id) if effective_volume_no else {},
        "当前分卷暂无已批准讨论结论。",
    )
    arc_discussion_context = _format_discussion_context(
        load_arc_discussion_artifact(project_name, int(effective_arc_no), story_id=story_id) if effective_arc_no else {},
        "当前剧情段暂无已批准讨论结论。",
    )
    chapter_discussion_context = _format_discussion_context(
        load_chapter_discussion_artifact(project_name, chapter_no, story_id=story_id),
        "当前章节暂无已批准讨论结论。",
    )
    trace_key = _story_trace_key("chapter_outline", project_name, story_id, chapter_no)
    recent_summaries = get_recent_chapter_summaries(project_name, story_id=story_id)
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章 {user_requirement} {outline} {volume_outline} {arc_outline} {volume_discussion_context} {arc_discussion_context} {chapter_discussion_context}",
        allowed_source_types=[
            "outline",
            "creative_profile_discussion",
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
        story_id=story_id,
        retrieval_profile="chapter_planning",
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
        _build_rules_text(project_name, "chapter_outline", story_id=story_id),
    ), retrieval_context)
    outline = call_llm(prompt, stream_callback=stream_callback)
    if not outline.strip():
        raise RuntimeError("模型没有返回章节细纲。")
    artifacts = {"saved": False}
    if save_output:
        save_chapter_outline(project_name, chapter_no, outline, story_id=story_id)
        save_chapter_outline_metadata(project_name, chapter_no, {"volume_no": effective_volume_no, "arc_no": effective_arc_no}, story_id=story_id)
        artifacts = {
            "saved": True,
            "saved_path": f"data/projects/{project_name}/stories/{story_id}/chapter_outlines/chapter_{chapter_no:03d}.md",
            "metadata_path": f"data/projects/{project_name}/stories/{story_id}/chapter_outlines/chapter_{chapter_no:03d}.meta.json",
        }
    return _make_step_result(
        "chapter_outline",
        success=True,
        status="completed",
        data={"chapter_outline": outline, "chapter_outline_metadata": {"chapter_no": chapter_no, "volume_no": effective_volume_no, "arc_no": effective_arc_no}},
        retrieval_hits=get_retrieval_trace(trace_key),
        artifacts=artifacts,
    ).model_dump()

def write_chapter(
    project_name: str,
    chapter_no: int,
    chapter_outline: str,
    writing_guidance: dict | None = None,
    word_count: str = "2000-2500",
    story_id: str = "default",
    stream_callback=None,
    save_output: bool = True,
) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    raw_guidance = writing_guidance if isinstance(writing_guidance, dict) else {}
    selected_prompt_option_ids = raw_guidance.get("prompt_option_ids") if "prompt_option_ids" in raw_guidance else None
    normalized_guidance = ChapterWritingGuidance.model_validate(raw_guidance).model_dump()
    trace_key = _story_trace_key("write", project_name, story_id, chapter_no)
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章 {chapter_outline} {normalized_guidance}",
        allowed_source_types=[
            "creative_profile_discussion",
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
        story_id=story_id,
        retrieval_profile="drafting",
    )
    prompt = merge_retrieval_context(
        write_chapter_prompt(
            memory,
            chapter_outline,
            normalized_guidance,
            word_count,
            _build_rules_text(
                project_name,
                "write",
                story_id=story_id,
                prompt_option_ids=selected_prompt_option_ids,
            ),
        ),
        retrieval_context,
    )
    chapter = call_llm(prompt, stream_callback=stream_callback)
    if not chapter.strip():
        raise RuntimeError("模型没有返回章节正文。")
    artifacts = {"saved": False}
    if save_output:
        save_chapter(project_name, chapter_no, chapter, story_id=story_id)
        artifacts = {
            "saved": True,
            "saved_path": f"data/projects/{project_name}/stories/{story_id}/chapters/chapter_{chapter_no:03d}.md",
        }
    return _make_step_result(
        "write_chapter",
        success=True,
        status="completed",
        data={"chapter": chapter, "writing_guidance": normalized_guidance},
        retrieval_hits=get_retrieval_trace(trace_key),
        artifacts=artifacts,
    ).model_dump()


def run_dynamic_generation_task(
    project_name: str,
    chapter_no: int,
    user_requirement: str,
    word_count: str = "",
    workflow_depth: str = "按创作配置",
    story_id: str = "default",
    writing_guidance: dict | None = None,
    stream_callback=None,
    save_outputs: bool = True,
) -> dict:
    profile = load_creative_profile(project_name, story_id)
    using_profile_depth = not workflow_depth or workflow_depth == "按创作配置"
    effective_depth = workflow_depth if not using_profile_depth else profile.get("workflow_depth", "短篇结构+正文")
    effective_word_count = word_count.strip() or profile.get("target_word_count", "") or "2000-2500"
    requested_chapter_no = int(chapter_no or 0)
    save_outputs = bool(save_outputs and requested_chapter_no > 0)
    effective_chapter_no = requested_chapter_no if requested_chapter_no > 0 else 1
    steps: dict[str, dict] = {}
    warnings: list[str] = []
    if not save_outputs:
        warnings.append("本次为仅预览模式，生成结果不会写入章节、章节细纲或创作结构文件。")

    def emit_step_heading(title: str) -> None:
        _safe_stream_emit(stream_callback, f"\n\n## {title}\n\n")

    if effective_depth == "只生成正文":
        direct_outline = "\n\n".join([
            "# 直接正文生成任务",
            f"创作配置：{json.dumps(profile, ensure_ascii=False)}",
            f"用户需求：{user_requirement}",
            "请根据创作配置和检索上下文直接写正文，不需要输出大纲。",
        ])
        emit_step_heading("正文")
        write_step = write_chapter(
            project_name,
            effective_chapter_no,
            direct_outline,
            writing_guidance,
            effective_word_count,
            story_id=story_id,
            stream_callback=stream_callback,
            save_output=save_outputs,
        )
        steps["write_chapter"] = write_step
        return {
            "success": bool(write_step.get("success")),
            "status": write_step.get("status", "completed"),
            "workflow_depth": effective_depth,
            "chapter_no": requested_chapter_no,
            "effective_chapter_no": effective_chapter_no,
            "word_count": effective_word_count,
            "save_outputs": save_outputs,
            "steps": steps,
            "creative_structure": "",
            "chapter": write_step.get("data", {}).get("chapter", ""),
            "warnings": warnings,
        }

    is_custom_depth = effective_depth not in KNOWN_WORKFLOW_DEPTHS

    if effective_depth in {"短篇结构+正文", "分卷/剧情段/章节"} or is_custom_depth or (
        using_profile_depth and _is_lightweight_story_profile(profile)
    ):
        emit_step_heading("创作结构")
        structure_step = generate_creative_structure(
            project_name,
            effective_chapter_no,
            user_requirement,
            save_as_chapter_outline=save_outputs,
            story_id=story_id,
            stream_callback=stream_callback,
        )
        steps["creative_structure"] = structure_step
        if not structure_step.get("success"):
            return {
                "success": False,
                "status": structure_step.get("status", "failed"),
                "workflow_depth": effective_depth,
                "chapter_no": requested_chapter_no,
                "effective_chapter_no": effective_chapter_no,
                "word_count": effective_word_count,
                "save_outputs": save_outputs,
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
        emit_step_heading("正文")
        write_step = write_chapter(
            project_name,
            effective_chapter_no,
            structure_text,
            writing_guidance,
            effective_word_count,
            story_id=story_id,
            stream_callback=stream_callback,
            save_output=save_outputs,
        )
        steps["write_chapter"] = write_step
        return {
            "success": bool(write_step.get("success")),
            "status": write_step.get("status", "completed"),
            "workflow_depth": effective_depth,
            "chapter_no": requested_chapter_no,
            "effective_chapter_no": effective_chapter_no,
            "word_count": effective_word_count,
            "save_outputs": save_outputs,
            "steps": steps,
            "creative_structure": structure_text,
            "chapter": write_step.get("data", {}).get("chapter", ""),
            "warnings": warnings,
        }

    if effective_depth == "章节计划+正文":
        emit_step_heading("章节计划")
        outline_step = generate_chapter_outline(
            project_name,
            effective_chapter_no,
            user_requirement,
            story_id=story_id,
            stream_callback=stream_callback,
            save_output=save_outputs,
        )
        steps["chapter_outline"] = outline_step
        if not outline_step.get("success"):
            return {
                "success": False,
                "status": outline_step.get("status", "failed"),
                "workflow_depth": effective_depth,
                "chapter_no": requested_chapter_no,
                "effective_chapter_no": effective_chapter_no,
                "word_count": effective_word_count,
                "save_outputs": save_outputs,
                "steps": steps,
                "creative_structure": "",
                "chapter": "",
                "warnings": warnings,
            }
        outline_text = outline_step.get("data", {}).get("chapter_outline", "")
        emit_step_heading("正文")
        write_step = write_chapter(
            project_name,
            effective_chapter_no,
            outline_text,
            writing_guidance,
            effective_word_count,
            story_id=story_id,
            stream_callback=stream_callback,
            save_output=save_outputs,
        )
        steps["write_chapter"] = write_step
        return {
            "success": bool(write_step.get("success")),
            "status": write_step.get("status", "completed"),
            "workflow_depth": effective_depth,
            "chapter_no": requested_chapter_no,
            "effective_chapter_no": effective_chapter_no,
            "word_count": effective_word_count,
            "save_outputs": save_outputs,
            "steps": steps,
            "creative_structure": outline_text,
            "chapter": write_step.get("data", {}).get("chapter", ""),
            "warnings": warnings,
        }

    warnings.append("完整长篇流程建议继续使用全书大纲、分卷、剧情段、章节细纲和一键流水线页面分步执行。")
    emit_step_heading("创作结构")
    structure_step = generate_creative_structure(
        project_name,
        effective_chapter_no,
        user_requirement,
        save_as_chapter_outline=save_outputs,
        story_id=story_id,
        stream_callback=stream_callback,
    )
    steps["creative_structure"] = structure_step
    return {
        "success": bool(structure_step.get("success")),
        "status": "completed" if structure_step.get("success") else structure_step.get("status", "failed"),
        "workflow_depth": effective_depth,
        "chapter_no": requested_chapter_no,
        "effective_chapter_no": effective_chapter_no,
        "word_count": effective_word_count,
        "save_outputs": save_outputs,
        "steps": steps,
        "creative_structure": structure_step.get("data", {}).get("creative_structure", ""),
        "chapter": "",
        "warnings": warnings,
    }

def extract_setting_candidates_from_chapter(
    project_name: str,
    chapter_no: int,
    chapter: str,
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    trace_key = _story_trace_key("setting_extraction", project_name, story_id, chapter_no)
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章设定提炼 {chapter}",
        allowed_source_types=["memory_character", "memory_world", "memory_au_rule", "memory_relationship", "memory_timeline", "memory_foreshadowing", "memory_active_constraint", "chapter_summary", "external_source"] + KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
        story_id=story_id,
        retrieval_profile="review",
    )
    prompt = merge_retrieval_context(
        setting_extraction_prompt(memory, chapter, _build_rules_text(project_name, "setting_extraction", story_id=story_id)),
        retrieval_context,
    )
    result = call_llm(prompt, stream_callback=stream_callback)
    if not result.strip():
        raise RuntimeError("设定提炼失败：模型返回了空响应。")
    retrieval_hits = get_retrieval_trace(trace_key)

    try:
        updates = validate_setting_extraction_result(_extract_json_object(result), chapter_no)
    except ValidationError as exc:
        reason = format_schema_validation_error(exc)
        return _make_step_result(
            "setting_extraction",
            success=False,
            status="rejected",
            error=reason,
            retrieval_hits=retrieval_hits,
            validation=_make_validation_status(
                status="failed",
                schema_name="MemoryUpdateResult",
                message="设定提炼结构校验失败。",
                errors=[reason],
            ),
            artifacts={"raw_response": result},
        ).model_dump()
    except Exception as exc:
        return _make_step_result(
            "setting_extraction",
            success=False,
            status="rejected",
            error=str(exc),
            retrieval_hits=retrieval_hits,
            validation=_make_validation_status(
                status="failed",
                schema_name="MemoryUpdateResult",
                message="设定提炼结果提取失败。",
                errors=[str(exc)],
            ),
            artifacts={"raw_response": result},
        ).model_dump()

    update_data = updates.model_dump()
    pending_items = build_pending_knowledge_from_setting_extraction(update_data, story_id, chapter_no)
    queued_count = queue_pending_knowledge_items(
        project_name,
        pending_items,
        scope="project",
        authority="project",
        source_title=f"第 {chapter_no} 章正文",
        source_origin="chapter_update",
    )
    try:
        summaries = [
            item for item in load_story_chapter_summaries(project_name, story_id)
            if not isinstance(item, dict) or item.get("chapter_no") != chapter_no
        ]
        summaries.append({
            "chapter_no": update_data["chapter_no"],
            "summary": update_data["chapter_summary"]
        })
        save_story_chapter_summaries(project_name, story_id, summaries)
    except Exception as exc:
        logging.getLogger("novelforge").warning(
            "Failed to save story chapter summaries: project=%s story=%s chapter=%s error=%s",
            project_name, story_id, chapter_no, exc,
        )
    return _make_step_result(
        "setting_extraction",
        success=True,
        status="completed",
        data={
            "applied_updates": update_data,
            "pending_knowledge_items": pending_items,
            "queued_knowledge_count": queued_count,
            "chapter_summary_saved": True,
        },
        retrieval_hits=retrieval_hits,
        validation=_make_validation_status(
            status="passed",
            schema_name="MemoryUpdateResult",
            message="章节设定提炼已通过结构校验，候选设定已加入待确认知识队列。",
        ),
        artifacts={
            "memory_saved": False,
            "pending_knowledge_count": len(pending_items),
            "queued_knowledge_count": queued_count,
        },
    ).model_dump()


def update_memory_from_chapter(
    project_name: str,
    chapter_no: int,
    chapter: str,
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    return extract_setting_candidates_from_chapter(project_name, chapter_no, chapter, story_id=story_id, stream_callback=stream_callback)


def review_chapter(project_name: str, chapter_no: int, chapter: str, story_id: str = "default", stream_callback=None) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    chapter_outline = load_chapter_outline(project_name, chapter_no, story_id=story_id)
    trace_key = _story_trace_key("review", project_name, story_id, chapter_no)
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
        story_id=story_id,
        retrieval_profile="review",
    )
    prompt = merge_retrieval_context(
        review_chapter_prompt(memory, chapter_outline, chapter, _build_rules_text(project_name, "review", story_id=story_id)),
        retrieval_context,
    )
    result = call_llm(prompt, stream_callback=stream_callback)
    if not result.strip():
        raise RuntimeError("审阅失败：模型返回了空响应。")
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
        save_review_json(project_name, chapter_no, fallback_review.model_dump(), story_id=story_id)
        save_review(project_name, chapter_no, markdown, story_id=story_id)
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
        save_review_json(project_name, chapter_no, fallback_review.model_dump(), story_id=story_id)
        save_review(project_name, chapter_no, markdown, story_id=story_id)
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
    save_review_json(project_name, chapter_no, review.model_dump(), story_id=story_id)
    save_review(project_name, chapter_no, markdown, story_id=story_id)
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


def compact_memory(project_name: str, story_id: str = "default") -> dict:
    return {
        "status": "skipped",
        "reason": "memory_compaction_deprecated",
        "message": "核心设定已改为结构化知识管理；章节提炼会写入待确认知识队列，不再压缩写回 memory.json。",
        "project_name": project_name,
        "story_id": story_id,
    }


def _run_analysis(
    prompt: str,
    empty_error: str,
    schema,
    renderer,
    stream_callback=None,
) -> tuple[object, str]:
    payload = _call_json_llm(prompt, empty_error, stream_callback=stream_callback)
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
    story_id: str = "default",
) -> dict:
    retrieval_hits = get_retrieval_trace(trace_key)
    sources_md = _format_supporting_sources_markdown(retrieval_hits)
    conflict_md = _format_potential_conflicts_markdown(retrieval_hits)
    report_markdown = markdown
    if sources_md:
        report_markdown = f"{report_markdown}\n\n{sources_md}"
    if conflict_md:
        report_markdown = f"{report_markdown}\n\n{conflict_md}"

    save_analysis_report(project_name, analysis_type, chapter_no, report_markdown, story_id=story_id)
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
            "saved_path": f"data/projects/{project_name}/stories/{story_id}/analysis/{analysis_type}_chapter_{chapter_no:03d}.md",
        },
    ).model_dump()


def analyze_characters(project_name: str, chapter_no: int, chapter: str, story_id: str = "default", stream_callback=None) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    trace_key = _story_trace_key("analysis:characters", project_name, story_id, chapter_no)
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章角色分析 {chapter}",
        allowed_source_types=["chapter_summary", "chapter_content", "memory_character", "memory_relationship", "memory_active_constraint", "review_issue", "analysis_characters", "external_source"] + KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
            story_id=story_id)
    prompt = merge_retrieval_context(
        character_analysis_prompt(memory, chapter, _build_rules_text(project_name, "review", story_id=story_id)),
        retrieval_context,
    )
    result_model, markdown = _run_analysis(
        prompt,
        "模型没有返回角色分析结果。",
        CharacterAnalysisResult,
        render_character_analysis_markdown,
        stream_callback=stream_callback,
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
        story_id=story_id,
    )


def analyze_timeline(project_name: str, chapter_no: int, chapter: str, story_id: str = "default", stream_callback=None) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    trace_key = _story_trace_key("analysis:timeline", project_name, story_id, chapter_no)
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章时间线分析 {chapter}",
        allowed_source_types=["chapter_summary", "chapter_content", "memory_timeline", "memory_active_constraint", "review_timeline_check", "analysis_timeline", "external_source"] + KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
            story_id=story_id)
    prompt = merge_retrieval_context(
        timeline_analysis_prompt(memory, chapter, _build_rules_text(project_name, "review", story_id=story_id)),
        retrieval_context,
    )
    result_model, markdown = _run_analysis(
        prompt,
        "模型没有返回时间线分析结果。",
        TimelineAnalysisResult,
        render_timeline_analysis_markdown,
        stream_callback=stream_callback,
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
        story_id=story_id,
    )


def analyze_foreshadowing(project_name: str, chapter_no: int, chapter: str, story_id: str = "default", stream_callback=None) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    trace_key = _story_trace_key("analysis:foreshadowing", project_name, story_id, chapter_no)
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章伏笔分析 {chapter}",
        allowed_source_types=["chapter_summary", "chapter_content", "memory_foreshadowing", "memory_active_constraint", "review_foreshadowing_check", "analysis_foreshadowing", "external_source"] + KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
            story_id=story_id)
    prompt = merge_retrieval_context(
        foreshadowing_analysis_prompt(memory, chapter, _build_rules_text(project_name, "review", story_id=story_id)),
        retrieval_context,
    )
    result_model, markdown = _run_analysis(
        prompt,
        "模型没有返回伏笔分析结果。",
        ForeshadowingAnalysisResult,
        render_foreshadowing_analysis_markdown,
        stream_callback=stream_callback,
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
        story_id=story_id,
    )


def run_consistency_check(project_name: str, chapter_no: int, chapter: str, story_id: str = "default", stream_callback=None) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    trace_key = _story_trace_key("analysis:consistency", project_name, story_id, chapter_no)
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
            story_id=story_id)
    prompt = merge_retrieval_context(
        consistency_check_prompt(memory, chapter, _build_rules_text(project_name, "review", story_id=story_id)),
        retrieval_context,
    )
    result_model, markdown = _run_analysis(
        prompt,
        "模型没有返回一致性检查结果。",
        ConsistencyAnalysisResult,
        render_consistency_analysis_markdown,
        stream_callback=stream_callback,
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
        story_id=story_id,
    )


def evaluate_chapter(project_name: str, chapter_no: int, chapter: str, story_id: str = "default", stream_callback=None) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    chapter_outline = load_chapter_outline(project_name, chapter_no, story_id=story_id)
    trace_key = _story_trace_key("evaluation:chapter", project_name, story_id, chapter_no)
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
        story_id=story_id,
        retrieval_profile="review",
    )
    prompt = merge_retrieval_context(
        evaluate_chapter_prompt(memory, chapter_outline, chapter, _build_rules_text(project_name, "review", story_id=story_id)),
        retrieval_context,
    )
    payload = _call_json_llm(prompt, "模型没有返回章节评估结果。", stream_callback=stream_callback)
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
    save_evaluation_json(project_name, chapter_no, result.model_dump(), story_id=story_id)
    save_evaluation_report(project_name, chapter_no, report_markdown, story_id=story_id)
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
            "saved_path": f"data/projects/{project_name}/stories/{story_id}/evaluation/chapter_{chapter_no:03d}.md",
        },
    ).model_dump()


def evaluate_chapter_comprehensive(project_name: str, chapter_no: int, chapter: str, story_id: str = "default", stream_callback=None) -> dict:
    memory = build_generation_setting_context(project_name, story_id)
    chapter_outline = load_chapter_outline(project_name, chapter_no, story_id=story_id)
    trace_key = _story_trace_key("evaluation:comprehensive", project_name, story_id, chapter_no)
    retrieval_context = _build_retrieval_context(
        project_name,
        f"第{chapter_no}章综合评价 {chapter_outline} {chapter}",
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
            "conflict_resolution",
            "external_source",
        ] + KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
        story_id=story_id,
        retrieval_profile="review",
    )
    prompt = merge_retrieval_context(
        comprehensive_chapter_evaluation_prompt(
            memory,
            chapter_outline,
            chapter,
            _build_rules_text(project_name, "review", story_id=story_id),
        ),
        retrieval_context,
    )
    payload = _call_json_llm(prompt, "模型没有返回章节综合评价结果。", stream_callback=stream_callback)
    try:
        result = ComprehensiveChapterEvaluationResult.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"章节综合评价结构校验失败：{format_schema_validation_error(exc)}") from exc

    retrieval_hits = get_retrieval_trace(trace_key)
    report_markdown = render_comprehensive_chapter_evaluation_markdown(result)
    sources_md = _format_supporting_sources_markdown(retrieval_hits)
    conflict_md = _format_potential_conflicts_markdown(retrieval_hits)
    if sources_md:
        report_markdown += f"\n\n{sources_md}"
    if conflict_md:
        report_markdown += f"\n\n{conflict_md}"
    save_evaluation_json(project_name, chapter_no, result.model_dump(), story_id=story_id)
    save_evaluation_report(project_name, chapter_no, report_markdown, story_id=story_id)
    return _make_step_result(
        "evaluate_chapter_comprehensive",
        success=True,
        status="completed",
        data={
            "evaluation": result.model_dump(),
            "report_markdown": report_markdown,
        },
        retrieval_hits=retrieval_hits,
        validation=_make_validation_status(
            status="passed",
            schema_name="ComprehensiveChapterEvaluationResult",
            message="章节综合评价已通过结构校验并保存。",
        ),
        artifacts={
            "report_saved": True,
            "saved_path": f"data/projects/{project_name}/stories/{story_id}/evaluation/chapter_{chapter_no:03d}.md",
        },
    ).model_dump()


def pipeline_plan_write_review_update(
    project_name: str,
    chapter_no: int,
    user_requirement: str,
    word_count: str = "2000-2500",
    story_id: str = "default",
    stream_callback=None,
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

    def emit_step_heading(title: str) -> None:
        _safe_stream_emit(stream_callback, f"\n\n## {title}\n\n")

    try:
        emit_step_heading("章节细纲")
        outline = generate_chapter_outline(project_name, chapter_no, user_requirement, story_id=story_id, stream_callback=stream_callback)
        outline_step = WorkflowStepResult.model_validate(outline)
    except Exception as exc:
        outline_step = _make_step_result(
            "chapter_outline",
            success=False,
            status="failed",
            error=str(exc),
            retrieval_hits=get_retrieval_trace(_story_trace_key("chapter_outline", project_name, story_id, chapter_no)),
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
            emit_step_heading("正文")
            chapter = write_chapter(project_name, chapter_no, state.chapter_outline, None, word_count, story_id=story_id, stream_callback=stream_callback)
            chapter_step = WorkflowStepResult.model_validate(chapter)
        except Exception as exc:
            chapter_step = _make_step_result(
                "write_chapter",
                success=False,
                status="failed",
                error=str(exc),
                retrieval_hits=get_retrieval_trace(_story_trace_key("write", project_name, story_id, chapter_no)),
            )
            _record_pipeline_error(state, step_name="write_chapter", message=str(exc), error_type="llm")
    else:
        chapter_step = _make_step_result(
            "write_chapter",
            success=False,
            status="skipped",
            warnings=["Skipped because chapter outline step did not complete successfully."],
            retrieval_hits=get_retrieval_trace(_story_trace_key("write", project_name, story_id, chapter_no)),
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
            emit_step_heading("审阅")
            review_step_data = review_chapter(project_name, chapter_no, state.chapter, story_id=story_id, stream_callback=stream_callback)
            review_step = WorkflowStepResult.model_validate(review_step_data)
        except Exception as exc:
            review_step = _make_step_result(
                "review_chapter",
                success=False,
                status="failed",
                error=str(exc),
                retrieval_hits=get_retrieval_trace(_story_trace_key("review", project_name, story_id, chapter_no)),
            )
            _record_pipeline_error(state, step_name="review_chapter", message=str(exc), error_type="llm")
    else:
        review_step = _make_step_result(
            "review_chapter",
            success=False,
            status="skipped",
            warnings=["Skipped because chapter writing step did not complete successfully."],
            retrieval_hits=get_retrieval_trace(_story_trace_key("review", project_name, story_id, chapter_no)),
        )
        if not state.halted:
            _halt_pipeline(state, "write_chapter_failed")

    _record_pipeline_step(state, review_step)
    state.review = review_step.data.get("review", {})
    state.review_markdown = review_step.data.get("review_markdown", "")
    if review_step.success:
        state.last_successful_step = "review_chapter"

    if chapter_step.success and review_step.success:
        state.next_step = "setting_extraction"
        _transition_pipeline_state(state, "setting_extraction", "review step completed")
        try:
            emit_step_heading("设定提炼")
            memory_step_data = extract_setting_candidates_from_chapter(project_name, chapter_no, state.chapter, story_id=story_id, stream_callback=stream_callback)
            memory_step = WorkflowStepResult.model_validate(memory_step_data)
        except Exception as exc:
            memory_step = _make_step_result(
                "setting_extraction",
                success=False,
                status="failed",
                error=str(exc),
                retrieval_hits=get_retrieval_trace(_story_trace_key("setting_extraction", project_name, story_id, chapter_no)),
            )
            _record_pipeline_error(state, step_name="setting_extraction", message=str(exc), error_type="llm")
    else:
        skip_reason = "review_chapter_failed" if chapter_step.success else "write_chapter_failed"
        skip_warning = (
            "Skipped because chapter review step did not complete successfully."
            if chapter_step.success
            else "Skipped because chapter writing step did not complete successfully."
        )
        memory_step = _make_step_result(
            "setting_extraction",
            success=False,
            status="skipped",
            warnings=[skip_warning],
            retrieval_hits=get_retrieval_trace(_story_trace_key("setting_extraction", project_name, story_id, chapter_no)),
        )
        if not state.halted:
            _halt_pipeline(state, skip_reason)

    _record_pipeline_step(state, memory_step)
    state.setting_extraction = memory_step.data
    if memory_step.success:
        state.last_successful_step = "setting_extraction"
    elif not state.halted:
        _halt_pipeline(state, "setting_extraction_failed")

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
    save_pipeline_run(project_name, state.run_id, json.dumps(result, ensure_ascii=False, indent=2), story_id=story_id)
    return result


def resume_chapter_pipeline(project_name: str, run_id: str, story_id: str = "default", stream_callback=None) -> dict:
    raw = load_pipeline_run(project_name, run_id, story_id=story_id)
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
        setting_extraction=previous.get("setting_extraction", {}) if isinstance(previous.get("setting_extraction", {}), dict) else {},
        completed_steps=list(previous.get("completed_steps", [])),
    )
    _transition_pipeline_state(state, "resume", f"resuming from {run_id}")

    def emit_step_heading(title: str) -> None:
        _safe_stream_emit(stream_callback, f"\n\n## {title}\n\n")

    last_successful_step = str(previous.get("last_successful_step", "") or "")
    if last_successful_step == "chapter_outline":
        state.next_step = "write_chapter"
        _transition_pipeline_state(state, "write_chapter", "resuming after chapter outline")
        try:
            emit_step_heading("正文")
            chapter_step = WorkflowStepResult.model_validate(
                write_chapter(project_name, chapter_no, state.chapter_outline, None, state.word_count, story_id=story_id, stream_callback=stream_callback)
            )
        except Exception as exc:
            chapter_step = _make_step_result(
                "write_chapter", success=False, status="failed", error=str(exc),
                retrieval_hits=get_retrieval_trace(_story_trace_key("write", project_name, story_id, chapter_no)),
            )
            _record_pipeline_error(state, step_name="write_chapter", message=str(exc), error_type="llm")
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
            emit_step_heading("审阅")
            review_step = WorkflowStepResult.model_validate(review_chapter(project_name, chapter_no, state.chapter, story_id=story_id, stream_callback=stream_callback))
        except Exception as exc:
            review_step = _make_step_result(
                "review_chapter", success=False, status="failed", error=str(exc),
                retrieval_hits=get_retrieval_trace(_story_trace_key("review", project_name, story_id, chapter_no)),
            )
            _record_pipeline_error(state, step_name="review_chapter", message=str(exc), error_type="llm")
        _record_pipeline_step(state, review_step)
        state.review = review_step.data.get("review", {})
        state.review_markdown = review_step.data.get("review_markdown", "")
        if review_step.success:
            state.last_successful_step = "review_chapter"
            last_successful_step = "review_chapter"

    if last_successful_step == "review_chapter":
        state.next_step = "setting_extraction"
        _transition_pipeline_state(state, "setting_extraction", "resuming after review")
        try:
            emit_step_heading("设定提炼")
            memory_step = WorkflowStepResult.model_validate(extract_setting_candidates_from_chapter(project_name, chapter_no, state.chapter, story_id=story_id, stream_callback=stream_callback))
        except Exception as exc:
            memory_step = _make_step_result(
                "setting_extraction", success=False, status="failed", error=str(exc),
                retrieval_hits=get_retrieval_trace(_story_trace_key("setting_extraction", project_name, story_id, chapter_no)),
            )
            _record_pipeline_error(state, step_name="setting_extraction", message=str(exc), error_type="llm")
        _record_pipeline_step(state, memory_step)
        state.setting_extraction = memory_step.data
        if memory_step.success:
            state.last_successful_step = "setting_extraction"

    if state.last_successful_step == "setting_extraction":
        state.next_step = ""
        _transition_pipeline_state(state, "completed", "resume finished")
    elif not state.halted:
        _halt_pipeline(state, "resume_incomplete")

    state.finished_at = datetime.now().isoformat(timespec="seconds")
    state.success = state.last_successful_step == "setting_extraction" and not state.halted
    state.resumable = bool(state.halted and state.last_successful_step)
    pipeline_result = WorkflowPipelineResult(
        success=state.success,
        steps=state.steps,
        warnings=state.warnings,
    )
    result = state.model_dump()
    result["pipeline"] = pipeline_result.model_dump()
    save_pipeline_run(project_name, state.run_id, json.dumps(result, ensure_ascii=False, indent=2), story_id=story_id)
    return result
