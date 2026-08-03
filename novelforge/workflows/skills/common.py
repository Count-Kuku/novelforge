"""Shared workflow imports, constants, and helper functions."""

from __future__ import annotations

from novelforge.workflows import skills as _skills_api

import json
import hashlib
import logging
import re
from datetime import datetime
from urllib.request import Request, urlopen
from uuid import uuid4
from novelforge.core.llm import call_llm
from pydantic import ValidationError
from novelforge.workflows.context_assembly import (
    assemble_generation_context,
    build_chapter_context_query,
    ensure_context_budget,
    render_context_for_prompt,
)
from novelforge.core.prompts import (
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
from novelforge.services.memory import (
    delete_creative_profile_discussion_artifact,
    delete_chapter_discussion_artifact,
    delete_arc_discussion_artifact,
    delete_outline_discussion_artifact,
    delete_volume_discussion_artifact,
    consume_context_directives,
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
    save_generation_context_snapshot,
)
from novelforge.core.prompt_options import format_prompt_options_for_prompt, merge_prompt_option_layers
from novelforge.core.schemas import (
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
from novelforge.services.retrieval import format_retrieval_context, retrieve_context
from novelforge.domain.setting_knowledge import build_generation_setting_context


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
    story_id: str = "",
) -> dict:
    project_chunk = conflict.get("project_hit", {}).get("chunk", {})
    external_chunk = conflict.get("external_hit", {}).get("chunk", {})
    return save_conflict_resolution(project_name, {
        "conflict_id": _conflict_id(conflict),
        "story_id": str(story_id or ""),
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
    if not isinstance(text, str):
        raise TypeError("模型响应必须是字符串。")

    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as direct_error:
        decoder = json.JSONDecoder()

        def decode_candidates(fragment: str) -> list[tuple[dict, int]]:
            candidates = []
            for match in re.finditer(r"\{", fragment):
                try:
                    value, end = decoder.raw_decode(fragment, match.start())
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    candidates.append((value, end - match.start()))
            return candidates

        fenced_candidates = []
        for fenced_match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", stripped, flags=re.IGNORECASE):
            fenced_candidates.extend(decode_candidates(fenced_match.group(1)))
        if fenced_candidates:
            return max(fenced_candidates, key=lambda item: item[1])[0]

        candidates = decode_candidates(stripped)
        if candidates:
            return max(candidates, key=lambda item: item[1])[0]
        raise json.JSONDecodeError("模型响应中未找到合法 JSON 对象", stripped, 0) from direct_error

    if not isinstance(parsed, dict):
        raise ValueError("模型响应必须是 JSON 对象。")
    return parsed


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


def _resolve_pending_knowledge_version_context(
    project_name: str | None,
    story_id: str,
    creative_profile: dict | None = None,
) -> dict[str, str]:
    profile = dict(creative_profile) if isinstance(creative_profile, dict) else {}
    if not profile and project_name:
        profile = load_creative_profile(project_name, story_id)

    worldline_mode = str(profile.get("worldline_retrieval_mode") or "prefer").strip().lower()
    if worldline_mode not in {"prefer", "strict"}:
        worldline_mode = "prefer"
    worldline_id = str(profile.get("worldline_id") or "").strip()
    if not worldline_id:
        if worldline_mode == "strict":
            raise RuntimeError("当前故事启用了严格世界线隔离，但创作配置未设置世界线 ID。")
        worldline_id = "main"

    version_scope = str(profile.get("version_scope") or "").strip()
    if not version_scope:
        version_scope = "project_main" if worldline_id.lower() == "main" else "au"
    worldline_label = str(profile.get("worldline_label") or "").strip()
    if not worldline_label:
        worldline_label = "本项目主线" if worldline_id.lower() == "main" else worldline_id

    return {
        "story_id": str(story_id or "default").strip() or "default",
        "version_scope": version_scope,
        "worldline_id": worldline_id,
        "worldline_label": worldline_label,
        "worldline_retrieval_mode": worldline_mode,
    }


def build_pending_knowledge_from_setting_extraction(
    update_data: dict,
    story_id: str,
    chapter_no: int,
    project_name: str | None = None,
    creative_profile: dict | None = None,
) -> list[dict]:
    version_context = _resolve_pending_knowledge_version_context(
        project_name,
        story_id,
        creative_profile,
    )
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
                **version_context,
                "injection_policy": "always",
                "source_chapter_no": chapter_no,
            })
    return items


def build_pending_knowledge_from_memory_update(
    update_data: dict,
    story_id: str,
    chapter_no: int,
    project_name: str | None = None,
    creative_profile: dict | None = None,
) -> list[dict]:
    return build_pending_knowledge_from_setting_extraction(
        update_data,
        story_id,
        chapter_no,
        project_name=project_name,
        creative_profile=creative_profile,
    )


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
