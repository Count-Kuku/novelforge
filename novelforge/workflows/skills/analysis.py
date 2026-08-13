"""Implementation slice for the skills facade: analysis."""

from __future__ import annotations

from novelforge.workflows import skills as _skills_api

def update_memory_from_chapter(
    project_name: str,
    chapter_no: int,
    chapter: str,
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    return _skills_api.extract_setting_candidates_from_chapter(project_name, chapter_no, chapter, story_id=story_id, stream_callback=stream_callback)


def review_chapter(project_name: str, chapter_no: int, chapter: str, story_id: str = "default", stream_callback=None) -> dict:
    chapter_outline = _skills_api.load_chapter_outline(project_name, chapter_no, story_id=story_id)
    trace_key = _skills_api._story_trace_key("review", project_name, story_id, chapter_no)
    context_assembly = _skills_api.assemble_generation_context(
        project_name,
        story_id=story_id,
        capability="review",
        query=f"第{chapter_no}章审阅 {chapter_outline} {chapter}",
        chapter_no=chapter_no,
        allowed_scopes=["project", "canon", "reference"],
        retrieval_profile="review",
    )
    _skills_api.ensure_context_budget(context_assembly)
    _skills_api._LAST_RETRIEVAL_TRACES[trace_key] = list(context_assembly.retrieval_hits)
    prompt = _skills_api.review_chapter_prompt(
        {},
        chapter_outline,
        chapter,
        _skills_api.render_context_for_prompt(context_assembly),
    )
    with _skills_api.llm_usage_scope(
        project_name=project_name,
        story_id=story_id,
        operation="review.chapter",
        agent_role="reviewer",
    ):
        result = _skills_api.call_llm(prompt, stream_callback=stream_callback)
    if not result.strip():
        raise RuntimeError("审阅失败：模型返回了空响应。")
    retrieval_hits = _skills_api.get_retrieval_trace(trace_key)

    try:
        review = _skills_api.validate_review_result(_skills_api._extract_json_object(result))
    except _skills_api.ValidationError as exc:
        reason = _skills_api.format_schema_validation_error(exc)
        fallback_review = _skills_api.ReviewResult(
            status="blocked",
            summary=f"审阅结果解析失败：{reason}",
            strengths=[],
            issues=["模型未按要求返回合法结构的审阅结果。"],
            pacing="未知",
            next_action="检查原始审阅结果并重新生成。",
        )
        sources_md = _skills_api._format_supporting_sources_markdown(retrieval_hits)
        conflict_md = _skills_api._format_potential_conflicts_markdown(retrieval_hits)
        markdown = _skills_api._format_review_markdown(fallback_review)
        if sources_md:
            markdown += f"\n\n{sources_md}"
        if conflict_md:
            markdown += f"\n\n{conflict_md}"
        markdown += f"\n\n## 模型原始返回\n\n```text\n{result}\n```"
        _skills_api.save_review_json(project_name, chapter_no, fallback_review.model_dump(), story_id=story_id)
        _skills_api.save_review(project_name, chapter_no, markdown, story_id=story_id)
        return _skills_api._make_step_result(
            "review_chapter",
            success=False,
            status="rejected",
            data={
                "review": fallback_review.model_dump(),
                "review_markdown": markdown,
                "context_assembly": context_assembly.model_dump(),
            },
            error=reason,
            warnings=[*context_assembly.warnings, "已生成并保存审阅报告的兜底版本。"],
            retrieval_hits=retrieval_hits,
            validation=_skills_api._make_validation_status(
                status="failed",
                schema_name="ReviewResult",
                message="审阅结果结构校验失败。",
                errors=[reason],
            ),
            artifacts={"review_saved": True, "raw_response": result},
        ).model_dump()
    except Exception as exc:
        fallback_review = _skills_api.ReviewResult(
            status="blocked",
            summary=f"审阅结果解析失败：{exc}",
            strengths=[],
            issues=["模型未按要求返回合法结构化审阅结果。"],
            pacing="未知",
            next_action="检查原始审阅结果并重新生成。",
        )
        sources_md = _skills_api._format_supporting_sources_markdown(retrieval_hits)
        conflict_md = _skills_api._format_potential_conflicts_markdown(retrieval_hits)
        markdown = _skills_api._format_review_markdown(fallback_review)
        if sources_md:
            markdown += f"\n\n{sources_md}"
        if conflict_md:
            markdown += f"\n\n{conflict_md}"
        markdown += f"\n\n## 模型原始返回\n\n```text\n{result}\n```"
        _skills_api.save_review_json(project_name, chapter_no, fallback_review.model_dump(), story_id=story_id)
        _skills_api.save_review(project_name, chapter_no, markdown, story_id=story_id)
        return _skills_api._make_step_result(
            "review_chapter",
            success=False,
            status="rejected",
            data={
                "review": fallback_review.model_dump(),
                "review_markdown": markdown,
                "context_assembly": context_assembly.model_dump(),
            },
            error=str(exc),
            warnings=[*context_assembly.warnings, "已生成并保存审阅报告的兜底版本。"],
            retrieval_hits=retrieval_hits,
            validation=_skills_api._make_validation_status(
                status="failed",
                schema_name="ReviewResult",
                message="审阅结果提取失败。",
                errors=[str(exc)],
            ),
            artifacts={"review_saved": True, "raw_response": result},
        ).model_dump()

    sources_md = _skills_api._format_supporting_sources_markdown(retrieval_hits)
    conflict_md = _skills_api._format_potential_conflicts_markdown(retrieval_hits)
    markdown = _skills_api._format_review_markdown(review)
    if sources_md:
        markdown += f"\n\n{sources_md}"
    if conflict_md:
        markdown += f"\n\n{conflict_md}"
    _skills_api.save_review_json(project_name, chapter_no, review.model_dump(), story_id=story_id)
    _skills_api.save_review(project_name, chapter_no, markdown, story_id=story_id)
    return _skills_api._make_step_result(
        "review_chapter",
        success=True,
        status="completed",
        data={
            "review": review.model_dump(),
            "review_markdown": markdown,
            "context_assembly": context_assembly.model_dump(),
        },
        warnings=context_assembly.warnings,
        retrieval_hits=retrieval_hits,
        validation=_skills_api._make_validation_status(
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
    usage_context: dict | None = None,
) -> tuple[object, str]:
    payload = _skills_api._call_json_llm(
        prompt,
        empty_error,
        stream_callback=stream_callback,
        usage_context=usage_context,
    )
    try:
        result = schema.model_validate(payload)
    except _skills_api.ValidationError as exc:
        raise RuntimeError(f"分析结果结构校验失败：{_skills_api.format_schema_validation_error(exc)}") from exc
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
    retrieval_hits = _skills_api.get_retrieval_trace(trace_key)
    sources_md = _skills_api._format_supporting_sources_markdown(retrieval_hits)
    conflict_md = _skills_api._format_potential_conflicts_markdown(retrieval_hits)
    report_markdown = markdown
    if sources_md:
        report_markdown = f"{report_markdown}\n\n{sources_md}"
    if conflict_md:
        report_markdown = f"{report_markdown}\n\n{conflict_md}"

    _skills_api.save_analysis_report(project_name, analysis_type, chapter_no, report_markdown, story_id=story_id)
    return _skills_api._make_step_result(
        step_name,
        success=True,
        status="completed",
        data={
            "analysis": result_model.model_dump(),
            "report_markdown": report_markdown,
            "analysis_type": analysis_type,
        },
        retrieval_hits=retrieval_hits,
        validation=_skills_api._make_validation_status(
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
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    trace_key = _skills_api._story_trace_key("analysis:characters", project_name, story_id, chapter_no)
    retrieval_context = _skills_api._build_retrieval_context(
        project_name,
        f"第{chapter_no}章角色分析 {chapter}",
        allowed_source_types=["chapter_summary", "chapter_content", "memory_character", "memory_relationship", "memory_active_constraint", "review_issue", "analysis_characters", "external_source"] + _skills_api.KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
            story_id=story_id)
    prompt = _skills_api.merge_retrieval_context(
        _skills_api.character_analysis_prompt(memory, chapter, _skills_api._build_rules_text(project_name, "review", story_id=story_id)),
        retrieval_context,
    )
    result_model, markdown = _run_analysis(
        prompt,
        "模型没有返回角色分析结果。",
        _skills_api.CharacterAnalysisResult,
        _skills_api.render_character_analysis_markdown,
        stream_callback=stream_callback,
        usage_context={"project_name": project_name, "story_id": story_id, "operation": "analysis.characters", "agent_role": "analyst"},
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
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    trace_key = _skills_api._story_trace_key("analysis:timeline", project_name, story_id, chapter_no)
    retrieval_context = _skills_api._build_retrieval_context(
        project_name,
        f"第{chapter_no}章时间线分析 {chapter}",
        allowed_source_types=["chapter_summary", "chapter_content", "memory_timeline", "memory_active_constraint", "review_timeline_check", "analysis_timeline", "external_source"] + _skills_api.KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
            story_id=story_id)
    prompt = _skills_api.merge_retrieval_context(
        _skills_api.timeline_analysis_prompt(memory, chapter, _skills_api._build_rules_text(project_name, "review", story_id=story_id)),
        retrieval_context,
    )
    result_model, markdown = _run_analysis(
        prompt,
        "模型没有返回时间线分析结果。",
        _skills_api.TimelineAnalysisResult,
        _skills_api.render_timeline_analysis_markdown,
        stream_callback=stream_callback,
        usage_context={"project_name": project_name, "story_id": story_id, "operation": "analysis.timeline", "agent_role": "analyst"},
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
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    trace_key = _skills_api._story_trace_key("analysis:foreshadowing", project_name, story_id, chapter_no)
    retrieval_context = _skills_api._build_retrieval_context(
        project_name,
        f"第{chapter_no}章伏笔分析 {chapter}",
        allowed_source_types=["chapter_summary", "chapter_content", "memory_foreshadowing", "memory_active_constraint", "review_foreshadowing_check", "analysis_foreshadowing", "external_source"] + _skills_api.KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
            story_id=story_id)
    prompt = _skills_api.merge_retrieval_context(
        _skills_api.foreshadowing_analysis_prompt(memory, chapter, _skills_api._build_rules_text(project_name, "review", story_id=story_id)),
        retrieval_context,
    )
    result_model, markdown = _run_analysis(
        prompt,
        "模型没有返回伏笔分析结果。",
        _skills_api.ForeshadowingAnalysisResult,
        _skills_api.render_foreshadowing_analysis_markdown,
        stream_callback=stream_callback,
        usage_context={"project_name": project_name, "story_id": story_id, "operation": "analysis.foreshadowing", "agent_role": "analyst"},
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
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    trace_key = _skills_api._story_trace_key("analysis:consistency", project_name, story_id, chapter_no)
    retrieval_context = _skills_api._build_retrieval_context(
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
    prompt = _skills_api.merge_retrieval_context(
        _skills_api.consistency_check_prompt(memory, chapter, _skills_api._build_rules_text(project_name, "review", story_id=story_id)),
        retrieval_context,
    )
    result_model, markdown = _run_analysis(
        prompt,
        "模型没有返回一致性检查结果。",
        _skills_api.ConsistencyAnalysisResult,
        _skills_api.render_consistency_analysis_markdown,
        stream_callback=stream_callback,
        usage_context={"project_name": project_name, "story_id": story_id, "operation": "analysis.consistency", "agent_role": "analyst"},
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
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    chapter_outline = _skills_api.load_chapter_outline(project_name, chapter_no, story_id=story_id)
    trace_key = _skills_api._story_trace_key("evaluation:chapter", project_name, story_id, chapter_no)
    retrieval_context = _skills_api._build_retrieval_context(
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
        ] + _skills_api.KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
        story_id=story_id,
        retrieval_profile="review",
    )
    prompt = _skills_api.merge_retrieval_context(
        _skills_api.evaluate_chapter_prompt(memory, chapter_outline, chapter, _skills_api._build_rules_text(project_name, "review", story_id=story_id)),
        retrieval_context,
    )
    payload = _skills_api._call_json_llm(
        prompt,
        "模型没有返回章节评估结果。",
        stream_callback=stream_callback,
        usage_context={"project_name": project_name, "story_id": story_id, "operation": "evaluation.chapter", "agent_role": "reviewer"},
    )
    try:
        result = _skills_api.ChapterEvaluationResult.model_validate(payload)
    except _skills_api.ValidationError as exc:
        raise RuntimeError(f"章节评估结构校验失败：{_skills_api.format_schema_validation_error(exc)}") from exc

    retrieval_hits = _skills_api.get_retrieval_trace(trace_key)
    report_markdown = _skills_api.render_chapter_evaluation_markdown(result)
    sources_md = _skills_api._format_supporting_sources_markdown(retrieval_hits)
    conflict_md = _skills_api._format_potential_conflicts_markdown(retrieval_hits)
    if sources_md:
        report_markdown += f"\n\n{sources_md}"
    if conflict_md:
        report_markdown += f"\n\n{conflict_md}"
    _skills_api.save_evaluation_json(project_name, chapter_no, result.model_dump(), story_id=story_id)
    _skills_api.save_evaluation_report(project_name, chapter_no, report_markdown, story_id=story_id)
    return _skills_api._make_step_result(
        "evaluate_chapter",
        success=True,
        status="completed",
        data={
            "evaluation": result.model_dump(),
            "report_markdown": report_markdown,
        },
        retrieval_hits=retrieval_hits,
        validation=_skills_api._make_validation_status(
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
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    chapter_outline = _skills_api.load_chapter_outline(project_name, chapter_no, story_id=story_id)
    trace_key = _skills_api._story_trace_key("evaluation:comprehensive", project_name, story_id, chapter_no)
    retrieval_context = _skills_api._build_retrieval_context(
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
        ] + _skills_api.KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
        story_id=story_id,
        retrieval_profile="review",
    )
    prompt = _skills_api.merge_retrieval_context(
        _skills_api.comprehensive_chapter_evaluation_prompt(
            memory,
            chapter_outline,
            chapter,
            _skills_api._build_rules_text(project_name, "review", story_id=story_id),
        ),
        retrieval_context,
    )
    payload = _skills_api._call_json_llm(
        prompt,
        "模型没有返回章节综合评价结果。",
        stream_callback=stream_callback,
        usage_context={"project_name": project_name, "story_id": story_id, "operation": "evaluation.comprehensive", "agent_role": "reviewer"},
    )
    try:
        result = _skills_api.ComprehensiveChapterEvaluationResult.model_validate(payload)
    except _skills_api.ValidationError as exc:
        raise RuntimeError(f"章节综合评价结构校验失败：{_skills_api.format_schema_validation_error(exc)}") from exc

    retrieval_hits = _skills_api.get_retrieval_trace(trace_key)
    report_markdown = _skills_api.render_comprehensive_chapter_evaluation_markdown(result)
    sources_md = _skills_api._format_supporting_sources_markdown(retrieval_hits)
    conflict_md = _skills_api._format_potential_conflicts_markdown(retrieval_hits)
    if sources_md:
        report_markdown += f"\n\n{sources_md}"
    if conflict_md:
        report_markdown += f"\n\n{conflict_md}"
    _skills_api.save_evaluation_json(project_name, chapter_no, result.model_dump(), story_id=story_id)
    _skills_api.save_evaluation_report(project_name, chapter_no, report_markdown, story_id=story_id)
    return _skills_api._make_step_result(
        "evaluate_chapter_comprehensive",
        success=True,
        status="completed",
        data={
            "evaluation": result.model_dump(),
            "report_markdown": report_markdown,
        },
        retrieval_hits=retrieval_hits,
        validation=_skills_api._make_validation_status(
            status="passed",
            schema_name="ComprehensiveChapterEvaluationResult",
            message="章节综合评价已通过结构校验并保存。",
        ),
        artifacts={
            "report_saved": True,
            "saved_path": f"data/projects/{project_name}/stories/{story_id}/evaluation/chapter_{chapter_no:03d}.md",
        },
    ).model_dump()


def review_chapter_by_mode(
    project_name: str,
    chapter_no: int,
    chapter: str,
    *,
    mode: str = "quick",
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    """Run either review depth through one stable chapter-review contract.

    The existing ``reviews`` and ``evaluation`` assets remain the compatibility
    stores for quick and comprehensive results.  Callers no longer need to know
    which legacy workflow or payload field belongs to each depth.
    """

    normalized_mode = str(mode or "quick").strip().lower()
    aliases = {
        "quick": "quick",
        "fast": "quick",
        "快速": "quick",
        "快速审阅": "quick",
        "comprehensive": "comprehensive",
        "full": "comprehensive",
        "综合": "comprehensive",
        "综合审阅": "comprehensive",
    }
    normalized_mode = aliases.get(normalized_mode, normalized_mode)
    if normalized_mode == "quick":
        result = review_chapter(
            project_name,
            chapter_no,
            chapter,
            story_id=story_id,
            stream_callback=stream_callback,
        )
        payload_field = "review"
        report_field = "review_markdown"
        storage_kind = "reviews"
    elif normalized_mode == "comprehensive":
        result = evaluate_chapter_comprehensive(
            project_name,
            chapter_no,
            chapter,
            story_id=story_id,
            stream_callback=stream_callback,
        )
        payload_field = "evaluation"
        report_field = "report_markdown"
        storage_kind = "evaluation"
    else:
        raise ValueError(f"未知章节审阅模式：{mode}")

    unified = dict(result or {})
    data = dict(unified.get("data") or {})
    data["review_mode"] = normalized_mode
    data["review_payload"] = data.get(payload_field) or {}
    data["review_report"] = str(data.get(report_field) or "")
    data["compatibility_storage"] = storage_kind
    unified["data"] = data
    artifacts = dict(unified.get("artifacts") or {})
    artifacts.update({"review_mode": normalized_mode, "compatibility_storage": storage_kind})
    unified["artifacts"] = artifacts
    return unified
