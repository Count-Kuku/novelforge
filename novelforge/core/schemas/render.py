"""Markdown renderers and schema validators."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from novelforge.core.schemas._base import _label_source_type
from novelforge.core.schemas.review import (
    CharacterAnalysisResult,
    ConsistencyAnalysisResult,
    ForeshadowingAnalysisResult,
    MemoryUpdatePayload,
    MemoryUpdateResult,
    OperationResult,
    OrganizedReferenceResult,
    ReviewResult,
    TimelineAnalysisResult,
)
from novelforge.core.schemas.creative import (
    ArcDiscussionResult,
    ChapterDiscussionResult,
    CreativeProfile,
    CreativeProfileDiscussionResult,
    ExtractedKnowledgeItem,
    KnowledgeExtractionResult,
    OutlineDiscussionResult,
    VolumeDiscussionResult,
)
from novelforge.core.schemas.retrieval import (
    ArcChapterPlanResult,
    ChapterEvaluationResult,
    ComprehensiveChapterEvaluationResult,
)

def validate_review_result(data: dict[str, Any]) -> ReviewResult:
    return ReviewResult.model_validate(data)


def validate_setting_extraction_result(data: dict[str, Any], chapter_no: int) -> MemoryUpdateResult:
    payload = MemoryUpdatePayload.model_validate(data)
    return MemoryUpdateResult(chapter_no=chapter_no, **payload.model_dump())


def validate_memory_update_result(data: dict[str, Any], chapter_no: int) -> MemoryUpdateResult:
    return validate_setting_extraction_result(data, chapter_no)


def parse_operation_result(data: str | dict[str, Any]) -> OperationResult:
    if isinstance(data, str):
        return OperationResult.model_validate_json(data)
    return OperationResult.model_validate(data)


def format_schema_validation_error(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error.get("loc", [])) or "root"
        parts.append(f"{location}: {error.get('msg', 'invalid value')}")
    return "; ".join(parts)


def _markdown_section(title: str, items: list[str]) -> str:
    body = "\n".join(f"- {item}" for item in items) if items else "- 无"
    return f"## {title}\n\n{body}"


def render_character_analysis_markdown(result: CharacterAnalysisResult) -> str:
    return "\n\n".join([
        f"# {result.title}",
        _markdown_section("角色出场概览", result.character_overview),
        _markdown_section("角色行为与设定一致性", result.consistency_findings),
        _markdown_section("角色关系推进", result.relationship_progression),
        _markdown_section("发现的问题", result.issues),
        _markdown_section("修改建议", result.recommendations),
    ])


def render_timeline_analysis_markdown(result: TimelineAnalysisResult) -> str:
    return "\n\n".join([
        f"# {result.title}",
        _markdown_section("本章关键事件顺序", result.key_events),
        _markdown_section("与已有时间线的衔接", result.timeline_alignment),
        _markdown_section("可能的时间矛盾", result.contradictions),
        _markdown_section("节奏与推进评估", result.pacing_assessment),
        _markdown_section("修改建议", result.recommendations),
    ])


def render_foreshadowing_analysis_markdown(result: ForeshadowingAnalysisResult) -> str:
    return "\n\n".join([
        f"# {result.title}",
        _markdown_section("本章新增伏笔", result.new_foreshadowing),
        _markdown_section("已有伏笔的呼应或回收", result.callbacks_and_payoffs),
        _markdown_section("伏笔强度评估", result.strength_assessment),
        _markdown_section("发现的问题", result.issues),
        _markdown_section("修改建议", result.recommendations),
    ])


def render_consistency_analysis_markdown(result: ConsistencyAnalysisResult) -> str:
    overall = result.overall_conclusion or "无"
    return "\n\n".join([
        f"# {result.title}",
        f"## 总体结论\n\n{overall}",
        _markdown_section("角色一致性", result.character_consistency),
        _markdown_section("世界设定一致性", result.world_consistency),
        _markdown_section("时间线一致性", result.timeline_consistency),
        _markdown_section("伏笔与铺垫", result.foreshadowing_and_setup),
        _markdown_section("优先修改项", result.priority_fixes),
    ])


def render_organized_reference_markdown(result: OrganizedReferenceResult) -> str:
    lines = [f"# {result.source_title or '资料整理结果'}"]
    if result.source_summary:
        lines.extend(["", "## 资料摘要", "", result.source_summary])
    if result.notes:
        lines.extend(["", "## 备注", ""])
        lines.extend([f"- {item}" for item in result.notes])

    for index, entry in enumerate(result.entries, start=1):
        lines.extend(["", f"## [{index}] {entry.title}", ""])
        lines.append(f"- 资料类型：{_label_source_type(entry.source_type)}")
        if entry.tags:
            lines.append(f"- 标签：{', '.join(entry.tags)}")
        if entry.summary:
            lines.extend(["", "### 摘要", "", entry.summary])
        if entry.content:
            lines.extend(["", "### 详细内容", "", entry.content])
        if entry.extra_fields:
            lines.extend(["", "### 补充字段", ""])
            for key, value in entry.extra_fields.items():
                lines.append(f"- {key}: {value}")

    return "\n".join(lines)


KNOWLEDGE_CATEGORY_LABELS = {
    "characters": "角色知识",
    "items": "物品与道具",
    "abilities": "技能与能力",
    "world_rules": "世界观规则",
    "locations": "地点资料",
    "organizations": "组织资料",
    "timeline_events": "事件与时间线",
    "relationships": "角色关系",
    "writing_style": "写作风格",
    "dialogue_style": "对白风格",
    "narrative_techniques": "写作手法",
}


def label_knowledge_category(value: str) -> str:
    return KNOWLEDGE_CATEGORY_LABELS.get(str(value or ""), str(value or "未知知识"))


def render_knowledge_extraction_markdown(result: KnowledgeExtractionResult) -> str:
    lines = [f"# {result.source_title or '资料知识提取结果'}"]
    if result.source_summary:
        lines.extend(["", "## 资料摘要", "", result.source_summary])

    grouped: dict[str, list[ExtractedKnowledgeItem]] = {}
    for item in result.items:
        grouped.setdefault(item.category, []).append(item)

    if not grouped:
        lines.extend(["", "## 提取结果", "", "- 未提取到可保存知识。"])

    for category, items in grouped.items():
        lines.extend(["", f"## {label_knowledge_category(category)}", ""])
        for index, item in enumerate(items, start=1):
            lines.append(f"### [{index}] {item.name}")
            if item.summary:
                lines.extend(["", item.summary])
            lines.append(
                f"- 可信度：{item.confidence:.2f} / 重要性：{item.importance:.2f} / 证据强度：{item.evidence_strength:.2f}"
            )
            if item.canon_status and item.canon_status != "unknown":
                lines.append(f"- 原作状态：{item.canon_status}")
            if item.extraction_mode and item.extraction_mode != "general":
                lines.append(f"- 提取模式：{item.extraction_mode}")
            if item.source_segment_title or item.source_segment_id:
                segment_label = item.source_segment_title or item.source_segment_id
                if item.source_segment_index is not None:
                    segment_label = f"{item.source_segment_index}. {segment_label}"
                lines.append(f"- 来源片段：{segment_label}")
            elif item.source_segment_titles or item.source_segment_ids:
                segment_labels = item.source_segment_titles or item.source_segment_ids
                lines.append(f"- 来源片段：{', '.join(segment_labels[:5])}")
            if item.merged_from_pending_ids:
                lines.append(f"- 合并来源数：{len(item.merged_from_pending_ids)}")
            if item.tags:
                lines.append(f"- 标签：{', '.join(item.tags)}")
            if item.details:
                lines.append("- 细节：")
                for key, value in item.details.items():
                    lines.append(f"  - {key}：{value}")
            evidence_lines = [evidence for evidence in item.evidence if evidence.quote or evidence.note]
            if evidence_lines:
                lines.append("- 证据：")
                for evidence in evidence_lines[:3]:
                    source = evidence.source_title or result.source_title or "未标明来源"
                    quote = evidence.quote or evidence.note
                    lines.append(f"  - {source}：{quote}")
            lines.append("")

    if result.notes:
        lines.extend(["", "## 备注", ""])
        lines.extend([f"- {item}" for item in result.notes])

    return "\n".join(lines).strip()


def render_discussion_markdown(
    result: OutlineDiscussionResult | ChapterDiscussionResult | VolumeDiscussionResult | ArcDiscussionResult | CreativeProfileDiscussionResult,
) -> str:
    lines = [f"# {result.title}"]

    goal_sections = [
        ("chapter_goal", "章节目标"),
        ("volume_goal", "分卷目标"),
        ("arc_goal", "剧情段目标"),
    ]
    for attr_name, label in goal_sections:
        goal = getattr(result, attr_name, "")
        if goal:
            lines.extend(["", f"## {label}", "", goal])

    if result.current_understanding:
        lines.extend(["", "## 当前理解", "", result.current_understanding])

    if getattr(result, "core_goals", []):
        lines.extend(["", "## 核心目标", ""])
        lines.extend([f"- {item}" for item in result.core_goals])

    if result.key_constraints:
        lines.extend(["", "## 关键约束", ""])
        lines.extend([f"- {item}" for item in result.key_constraints])

    if result.options:
        lines.extend(["", "## 可选方案", ""])
        for index, option in enumerate(result.options, start=1):
            lines.append(f"### [{index}] {option.title}")
            if option.summary:
                lines.extend(["", option.summary, ""])
            if option.strengths:
                lines.append("优点：")
                lines.extend([f"- {item}" for item in option.strengths])
            if option.risks:
                lines.append("风险：")
                lines.extend([f"- {item}" for item in option.risks])
            lines.append("")

    if result.open_questions:
        lines.extend(["", "## 待确认问题", ""])
        lines.extend([f"- {item}" for item in result.open_questions])

    if result.risks:
        lines.extend(["", "## 风险", ""])
        lines.extend([f"- {item}" for item in result.risks])

    if result.recommended_direction:
        lines.extend(["", "## 推荐方向", "", result.recommended_direction])

    recommended_profile = getattr(result, "recommended_profile", None)
    if isinstance(recommended_profile, CreativeProfile):
        lines.extend(["", "## 推荐创作配置", ""])
        lines.extend([
            f"- 任务性质：{recommended_profile.story_mode or '-'}",
            f"- 目标篇幅：{recommended_profile.target_length or '-'}",
            f"- 目标字数：{recommended_profile.target_word_count or '未设置'}",
            f"- 生成层级：{recommended_profile.workflow_depth or '-'}",
            f"- 资料参考强度：{recommended_profile.reference_strength or '-'}",
            f"- 重点参考方向：{', '.join(recommended_profile.reference_focus or []) or '未设置'}",
            f"- 允许改写原设：{'是' if recommended_profile.allow_canon_deviation else '否'}",
            f"- 资料冲突处理：{recommended_profile.conflict_policy or '-'}",
            f"- 当前世界线：{recommended_profile.worldline_label or recommended_profile.worldline_id or '未设置'}",
            f"- 世界线检索模式：{recommended_profile.worldline_retrieval_mode or 'prefer'}",
        ])

    lines.extend(["", f"是否已收敛：`{result.approval_ready}`"])
    return "\n".join(lines)


def render_arc_chapter_plan_markdown(result: ArcChapterPlanResult) -> str:
    lines = [f"# {result.title}"]
    if result.arc_goal:
        lines.extend(["", "## 剧情段目标", "", result.arc_goal])
    if result.planning_assumptions:
        lines.extend(["", "## 规划假设", ""])
        lines.extend([f"- {item}" for item in result.planning_assumptions])
    if result.chapters:
        lines.extend(["", "## 章节分配", ""])
        for item in result.chapters:
            lines.append(f"### 第 {item.chapter_no:03d} 章：{item.title or '未命名'}")
            lines.extend(["", f"- 目标：{item.chapter_goal or '无'}"])
            lines.append(f"- 冲突：{item.conflict or '无'}")
            lines.append(f"- 预计字数：{item.expected_word_count or '未设置'}")
            if item.key_events:
                lines.append("- 关键事件：")
                lines.extend([f"  - {event}" for event in item.key_events])
            if item.foreshadowing_dependencies:
                lines.append("- 伏笔依赖：")
                lines.extend([f"  - {dependency}" for dependency in item.foreshadowing_dependencies])
            lines.append("")
    if result.risks:
        lines.extend(["", "## 风险", ""])
        lines.extend([f"- {item}" for item in result.risks])
    return "\n".join(lines).strip()


def render_chapter_evaluation_markdown(result: ChapterEvaluationResult) -> str:
    score_lines = [
        f"- 总分：{result.overall_score}",
        f"- 角色一致性：{result.character_consistency_score}",
        f"- 剧情推进：{result.plot_progression_score}",
        f"- 信息密度：{result.information_density_score}",
        f"- 情绪冲击：{result.emotional_impact_score}",
        f"- 伏笔处理：{result.foreshadowing_score}",
        f"- 文笔质量：{result.prose_quality_score}",
    ]
    return "\n\n".join([
        f"# {result.title}",
        "## 评分\n\n" + "\n".join(score_lines),
        f"## 总结\n\n{result.summary or '无'}",
        _markdown_section("优点", result.strengths),
        _markdown_section("问题", result.issues),
        _markdown_section("优先修改项", result.revision_priorities),
    ])


def render_comprehensive_chapter_evaluation_markdown(result: ComprehensiveChapterEvaluationResult) -> str:
    score_lines = [
        f"- 总分：{result.overall_score}",
        f"- 角色一致性：{result.character_consistency_score}",
        f"- 剧情推进：{result.plot_progression_score}",
        f"- 信息密度：{result.information_density_score}",
        f"- 情绪效果：{result.emotional_impact_score}",
        f"- 伏笔处理：{result.foreshadowing_score}",
        f"- 文字完成度：{result.prose_quality_score}",
    ]
    diagnosis = result.consistency_diagnosis
    return "\n\n".join([
        f"# {result.title}",
        f"## 总结论\n\n- 状态：`{result.status}`\n- 结论：{result.verdict_summary or '无'}\n- 下一步：{result.next_action or '无'}",
        "## 评分\n\n" + "\n".join(score_lines),
        f"## 总结\n\n{result.summary or '无'}",
        _markdown_section("优点", result.strengths),
        _markdown_section("阻塞问题", result.blocking_issues),
        _markdown_section("主要问题", result.issues),
        "## 一致性诊断\n\n"
        + _markdown_section("角色", diagnosis.characters)
        + "\n\n"
        + _markdown_section("世界观", diagnosis.world)
        + "\n\n"
        + _markdown_section("时间线", diagnosis.timeline)
        + "\n\n"
        + _markdown_section("伏笔", diagnosis.foreshadowing),
        _markdown_section("优先修改项", result.revision_priorities),
    ])
