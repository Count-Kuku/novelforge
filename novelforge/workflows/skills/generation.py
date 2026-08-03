"""Implementation slice for the skills facade: generation."""

from __future__ import annotations

from novelforge.workflows import skills as _skills_api

def generate_outline(project_name: str, user_idea: str, story_id: str = "default", stream_callback=None) -> dict:
    approved_discussion_context = _skills_api._format_discussion_context(
        _skills_api.load_outline_discussion_artifact(project_name, story_id=story_id),
        "当前全书暂无已批准讨论结论。",
    )
    trace_key = _skills_api._story_trace_key("outline", project_name, story_id)
    context_query = f"{user_idea} {approved_discussion_context}"
    context_assembly = _skills_api.assemble_generation_context(
        project_name,
        story_id=story_id,
        capability="outline",
        query=context_query,
        allowed_scopes=["project", "canon", "reference"],
        retrieval_profile="outline_generation",
    )
    _skills_api.ensure_context_budget(context_assembly)
    _skills_api._LAST_RETRIEVAL_TRACES[trace_key] = list(context_assembly.retrieval_hits)
    prompt = _skills_api.outline_prompt(
        {},
        f"{user_idea}\n\n已批准讨论结论：\n{approved_discussion_context}".strip(),
        _skills_api.render_context_for_prompt(context_assembly),
    )
    outline = _skills_api.call_llm(prompt, stream_callback=stream_callback)
    if not outline.strip():
        raise RuntimeError("模型没有返回全书大纲。")
    _skills_api.save_outline(project_name, outline, story_id=story_id)
    return _skills_api._make_step_result(
        "outline",
        success=True,
        status="completed",
        data={"outline": outline, "context_assembly": context_assembly.model_dump()},
        warnings=context_assembly.warnings,
        retrieval_hits=_skills_api.get_retrieval_trace(trace_key),
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
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    story_outline = _skills_api.load_outline(project_name, story_id=story_id)
    approved_discussion_context = _skills_api._format_discussion_context(
        _skills_api.load_volume_discussion_artifact(project_name, volume_no, story_id=story_id),
        "当前分卷暂无已批准讨论结论。",
    )
    trace_key = _skills_api._story_trace_key("volume_outline", project_name, story_id, volume_no)
    retrieval_context = _skills_api._build_retrieval_context(
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
        ] + _skills_api.KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
        story_id=story_id,
        retrieval_profile="outline_generation",
    )
    prompt = _skills_api.merge_retrieval_context(
        _skills_api.volume_outline_prompt(
            memory,
            story_outline,
            volume_no,
            volume_title,
            volume_summary,
            approved_discussion_context,
            user_requirement,
            _skills_api._build_rules_text(project_name, "outline", story_id=story_id),
        ),
        retrieval_context,
    )
    outline = _skills_api.call_llm(prompt, stream_callback=stream_callback)
    if not outline.strip():
        raise RuntimeError("模型没有返回分卷大纲。")
    _skills_api.save_volume_outline(project_name, volume_no, outline, story_id=story_id)
    _skills_api.save_volume_metadata(project_name, volume_no, {"title": volume_title, "summary": volume_summary, "status": status}, story_id=story_id)
    return _skills_api._make_step_result(
        "volume_outline",
        success=True,
        status="completed",
        data={"volume_outline": outline, "volume_metadata": {"volume_no": volume_no, "title": volume_title, "summary": volume_summary, "status": status}},
        retrieval_hits=_skills_api.get_retrieval_trace(trace_key),
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
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    story_outline = _skills_api.load_outline(project_name, story_id=story_id)
    volume_outline = _skills_api.load_volume_outline(project_name, int(volume_no), story_id=story_id) if volume_no else ""
    approved_discussion_context = _skills_api._format_discussion_context(
        _skills_api.load_arc_discussion_artifact(project_name, arc_no, story_id=story_id),
        "当前剧情段暂无已批准讨论结论。",
    )
    trace_key = _skills_api._story_trace_key("arc_outline", project_name, story_id, arc_no)
    retrieval_context = _skills_api._build_retrieval_context(
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
        ] + _skills_api.KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
        story_id=story_id,
        retrieval_profile="outline_generation",
    )
    prompt = _skills_api.merge_retrieval_context(
        _skills_api.arc_outline_prompt(
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
            _skills_api._build_rules_text(project_name, "outline", story_id=story_id),
        ),
        retrieval_context,
    )
    outline = _skills_api.call_llm(prompt, stream_callback=stream_callback)
    if not outline.strip():
        raise RuntimeError("模型没有返回剧情段大纲。")
    _skills_api.save_arc_outline(project_name, arc_no, outline, story_id=story_id)
    _skills_api.save_arc_metadata(
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
    return _skills_api._make_step_result(
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
        retrieval_hits=_skills_api.get_retrieval_trace(trace_key),
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
    arc_meta = _skills_api.load_arc_metadata(project_name, arc_no, story_id=story_id)
    volume_no = arc_meta.get("volume_no")
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    story_outline = _skills_api.load_outline(project_name, story_id=story_id)
    volume_outline = _skills_api.load_volume_outline(project_name, int(volume_no), story_id=story_id) if volume_no else ""
    arc_outline = _skills_api.load_arc_outline(project_name, arc_no, story_id=story_id)
    trace_key = _skills_api._story_trace_key("arc_chapter_plan", project_name, story_id, arc_no)
    retrieval_context = _skills_api._build_retrieval_context(
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
        ] + _skills_api.KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
        retrieval_profile="chapter_planning",
    )
    prompt = _skills_api.merge_retrieval_context(
        _skills_api.arc_chapter_plan_prompt(
            memory,
            story_outline,
            volume_outline,
            arc_outline,
            arc_no,
            start_chapter_no,
            chapter_count,
            arc_meta.get("target_word_count_range", ""),
            user_requirement,
            _skills_api._build_rules_text(project_name, "chapter_outline", story_id=story_id),
        ),
        retrieval_context,
    )
    payload = _skills_api._call_json_llm(prompt, "模型没有返回剧情段章节分配计划。", stream_callback=stream_callback)
    try:
        result = _skills_api.ArcChapterPlanResult.model_validate(payload)
    except _skills_api.ValidationError as exc:
        raise RuntimeError(f"剧情段章节分配计划结构校验失败：{_skills_api.format_schema_validation_error(exc)}") from exc

    report_markdown = _skills_api.render_arc_chapter_plan_markdown(result)
    _skills_api.save_arc_chapter_plan(project_name, arc_no, result.model_dump(), report_markdown, story_id=story_id)
    return _skills_api._make_step_result(
        "arc_chapter_plan",
        success=True,
        status="completed",
        data={
            "arc_chapter_plan": result.model_dump(),
            "report_markdown": report_markdown,
        },
        retrieval_hits=_skills_api.get_retrieval_trace(trace_key),
        validation=_skills_api._make_validation_status(
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
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    profile = _skills_api.load_creative_profile(project_name, story_id)
    trace_key = _skills_api._story_trace_key("creative_structure", project_name, story_id, chapter_no)
    retrieval_context = _skills_api._build_retrieval_context(
        project_name,
        f"{profile} {user_requirement}",
        allowed_scopes=["project", "canon", "reference"],
        top_k=8,
        trace_key=trace_key,
        story_id=story_id,
        retrieval_profile="chapter_planning",
    )
    prompt = _skills_api.merge_retrieval_context(
        _skills_api.creative_structure_prompt(
            memory,
            profile,
            user_requirement,
            _skills_api._build_rules_text(project_name, "chapter_outline", story_id=story_id),
        ),
        retrieval_context,
    )
    structure = _skills_api.call_llm(prompt, stream_callback=stream_callback)
    if not structure.strip():
        raise RuntimeError("模型没有返回创作结构。")

    artifacts = {}
    if save_as_chapter_outline:
        _skills_api.save_chapter_outline(project_name, chapter_no, structure, story_id=story_id)
        artifacts["saved_path"] = f"data/projects/{project_name}/stories/{story_id}/chapter_outlines/chapter_{chapter_no:03d}.md"

    return _skills_api._make_step_result(
        "creative_structure",
        success=True,
        status="completed",
        data={
            "creative_structure": structure,
            "creative_profile": profile,
            "chapter_no": chapter_no,
        },
        retrieval_hits=_skills_api.get_retrieval_trace(trace_key),
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
    outline = _skills_api.load_outline(project_name, story_id=story_id)
    existing_metadata = _skills_api.load_chapter_outline_metadata(project_name, chapter_no, story_id=story_id)
    effective_volume_no = volume_no if volume_no is not None else existing_metadata.get("volume_no")
    effective_arc_no = arc_no if arc_no is not None else existing_metadata.get("arc_no")
    volume_outline = _skills_api.load_volume_outline(project_name, int(effective_volume_no), story_id=story_id) if effective_volume_no else ""
    arc_outline = _skills_api.load_arc_outline(project_name, int(effective_arc_no), story_id=story_id) if effective_arc_no else ""
    volume_discussion_context = _skills_api._format_discussion_context(
        _skills_api.load_volume_discussion_artifact(project_name, int(effective_volume_no), story_id=story_id) if effective_volume_no else {},
        "当前分卷暂无已批准讨论结论。",
    )
    arc_discussion_context = _skills_api._format_discussion_context(
        _skills_api.load_arc_discussion_artifact(project_name, int(effective_arc_no), story_id=story_id) if effective_arc_no else {},
        "当前剧情段暂无已批准讨论结论。",
    )
    chapter_discussion_context = _skills_api._format_discussion_context(
        _skills_api.load_chapter_discussion_artifact(project_name, chapter_no, story_id=story_id),
        "当前章节暂无已批准讨论结论。",
    )
    trace_key = _skills_api._story_trace_key("chapter_outline", project_name, story_id, chapter_no)
    recent_summaries = _skills_api.get_recent_chapter_summaries(project_name, story_id=story_id)
    context_query = (
        f"第{chapter_no}章 {user_requirement} {outline} {volume_outline} {arc_outline} "
        f"{volume_discussion_context} {arc_discussion_context} {chapter_discussion_context}"
    )
    context_assembly = _skills_api.assemble_generation_context(
        project_name,
        story_id=story_id,
        capability="chapter_outline",
        query=context_query,
        chapter_no=chapter_no,
        allowed_scopes=["project", "canon", "reference"],
        retrieval_profile="chapter_planning",
    )
    _skills_api.ensure_context_budget(context_assembly)
    _skills_api._LAST_RETRIEVAL_TRACES[trace_key] = list(context_assembly.retrieval_hits)
    prompt = _skills_api.chapter_outline_prompt(
        {},
        outline,
        volume_outline,
        arc_outline,
        volume_discussion_context,
        arc_discussion_context,
        chapter_discussion_context,
        recent_summaries,
        chapter_no,
        user_requirement,
        _skills_api.render_context_for_prompt(context_assembly),
    )
    outline = _skills_api.call_llm(prompt, stream_callback=stream_callback)
    if not outline.strip():
        raise RuntimeError("模型没有返回章节细纲。")
    artifacts = {"saved": False}
    if save_output:
        _skills_api.save_chapter_outline(project_name, chapter_no, outline, story_id=story_id)
        _skills_api.save_chapter_outline_metadata(project_name, chapter_no, {"volume_no": effective_volume_no, "arc_no": effective_arc_no}, story_id=story_id)
        artifacts = {
            "saved": True,
            "saved_path": f"data/projects/{project_name}/stories/{story_id}/chapter_outlines/chapter_{chapter_no:03d}.md",
            "metadata_path": f"data/projects/{project_name}/stories/{story_id}/chapter_outlines/chapter_{chapter_no:03d}.meta.json",
        }
    return _skills_api._make_step_result(
        "chapter_outline",
        success=True,
        status="completed",
        data={
            "chapter_outline": outline,
            "chapter_outline_metadata": {
                "chapter_no": chapter_no,
                "volume_no": effective_volume_no,
                "arc_no": effective_arc_no,
            },
            "context_assembly": context_assembly.model_dump(),
        },
        warnings=context_assembly.warnings,
        retrieval_hits=_skills_api.get_retrieval_trace(trace_key),
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
    raw_guidance = writing_guidance if isinstance(writing_guidance, dict) else {}
    selected_prompt_option_ids = raw_guidance.get("prompt_option_ids") if "prompt_option_ids" in raw_guidance else None
    normalized_guidance = _skills_api.ChapterWritingGuidance.model_validate(raw_guidance).model_dump()
    trace_key = _skills_api._story_trace_key("write", project_name, story_id, chapter_no)
    context_assembly = _skills_api.assemble_generation_context(
        project_name,
        story_id=story_id,
        capability="write",
        query=_skills_api.build_chapter_context_query(chapter_no, chapter_outline, normalized_guidance),
        chapter_no=chapter_no,
        generation_guidance=normalized_guidance,
        prompt_option_ids=selected_prompt_option_ids,
        manual_knowledge_ids=normalized_guidance.get("manual_knowledge_ids"),
        allowed_scopes=["project", "canon", "reference"],
        retrieval_profile="drafting",
    )
    _skills_api.ensure_context_budget(context_assembly)
    _skills_api._LAST_RETRIEVAL_TRACES[trace_key] = list(context_assembly.retrieval_hits)
    prompt = _skills_api.write_chapter_prompt(
        {},
        chapter_outline,
        normalized_guidance,
        word_count,
        assembled_context=_skills_api.render_context_for_prompt(context_assembly),
    )
    chapter = _skills_api.call_llm(prompt, stream_callback=stream_callback)
    if not chapter.strip():
        raise RuntimeError("模型没有返回章节正文。")
    artifacts = {"saved": False}
    warnings = list(context_assembly.warnings)
    if save_output:
        _skills_api.save_chapter(project_name, chapter_no, chapter, story_id=story_id)
        artifacts = {
            "saved": True,
            "saved_path": f"data/projects/{project_name}/stories/{story_id}/chapters/chapter_{chapter_no:03d}.md",
        }
        try:
            snapshot_key = _skills_api.save_generation_context_snapshot(
                project_name,
                story_id,
                context_assembly.model_dump(),
            )
            artifacts["context_snapshot_id"] = snapshot_key
        except Exception as exc:
            _skills_api.logging.getLogger("novelforge").warning(
                "Failed to save generation context snapshot: project=%s story=%s chapter=%s error=%s",
                project_name,
                story_id,
                chapter_no,
                exc,
            )
            warnings.append(f"正文已保存，但上下文快照保存失败：{exc}")

        directive_ids = [
            str(block.metadata.get("directive_id") or "")
            for block in context_assembly.blocks
            if block.source_type == "context_directive" and str(block.metadata.get("directive_id") or "")
        ]
        try:
            consumed = _skills_api.consume_context_directives(project_name, story_id, directive_ids)
            if consumed:
                artifacts["consumed_directive_ids"] = [
                    str(item.get("directive_id") or "")
                    for item in consumed
                ]
        except Exception as exc:
            _skills_api.logging.getLogger("novelforge").warning(
                "Failed to consume context directives: project=%s story=%s chapter=%s error=%s",
                project_name,
                story_id,
                chapter_no,
                exc,
            )
            warnings.append(f"正文已保存，但导演注剩余次数更新失败：{exc}")
    return _skills_api._make_step_result(
        "write_chapter",
        success=True,
        status="completed",
        data={
            "chapter": chapter,
            "writing_guidance": normalized_guidance,
            "context_assembly": context_assembly.model_dump(),
        },
        warnings=warnings,
        retrieval_hits=_skills_api.get_retrieval_trace(trace_key),
        artifacts=artifacts,
    ).model_dump()


def build_dynamic_direct_outline(profile: dict, user_requirement: str) -> str:
    return "\n\n".join([
        "# 直接正文生成任务",
        f"创作配置：{_skills_api.json.dumps(profile or {}, ensure_ascii=False)}",
        f"用户需求：{user_requirement}",
        "请根据创作配置和检索上下文直接写正文，不需要输出大纲。",
    ])


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
    profile = _skills_api.load_creative_profile(project_name, story_id)
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
        _skills_api._safe_stream_emit(stream_callback, f"\n\n## {title}\n\n")

    if effective_depth == "只生成正文":
        direct_outline = build_dynamic_direct_outline(profile, user_requirement)
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

    is_custom_depth = effective_depth not in _skills_api.KNOWN_WORKFLOW_DEPTHS

    if effective_depth in {"短篇结构+正文", "分卷/剧情段/章节"} or is_custom_depth or (
        using_profile_depth and _skills_api._is_lightweight_story_profile(profile)
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
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    trace_key = _skills_api._story_trace_key("setting_extraction", project_name, story_id, chapter_no)
    retrieval_context = _skills_api._build_retrieval_context(
        project_name,
        f"第{chapter_no}章设定提炼 {chapter}",
        allowed_source_types=["memory_character", "memory_world", "memory_au_rule", "memory_relationship", "memory_timeline", "memory_foreshadowing", "memory_active_constraint", "chapter_summary", "external_source"] + _skills_api.KNOWLEDGE_SOURCE_TYPES,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
        story_id=story_id,
        retrieval_profile="review",
    )
    prompt = _skills_api.merge_retrieval_context(
        _skills_api.setting_extraction_prompt(memory, chapter, _skills_api._build_rules_text(project_name, "setting_extraction", story_id=story_id)),
        retrieval_context,
    )
    result = _skills_api.call_llm(prompt, stream_callback=stream_callback)
    if not result.strip():
        raise RuntimeError("设定提炼失败：模型返回了空响应。")
    retrieval_hits = _skills_api.get_retrieval_trace(trace_key)

    try:
        updates = _skills_api.validate_setting_extraction_result(_skills_api._extract_json_object(result), chapter_no)
    except _skills_api.ValidationError as exc:
        reason = _skills_api.format_schema_validation_error(exc)
        return _skills_api._make_step_result(
            "setting_extraction",
            success=False,
            status="rejected",
            error=reason,
            retrieval_hits=retrieval_hits,
            validation=_skills_api._make_validation_status(
                status="failed",
                schema_name="MemoryUpdateResult",
                message="设定提炼结构校验失败。",
                errors=[reason],
            ),
            artifacts={"raw_response": result},
        ).model_dump()
    except Exception as exc:
        return _skills_api._make_step_result(
            "setting_extraction",
            success=False,
            status="rejected",
            error=str(exc),
            retrieval_hits=retrieval_hits,
            validation=_skills_api._make_validation_status(
                status="failed",
                schema_name="MemoryUpdateResult",
                message="设定提炼结果提取失败。",
                errors=[str(exc)],
            ),
            artifacts={"raw_response": result},
        ).model_dump()

    update_data = updates.model_dump()
    pending_items = _skills_api.build_pending_knowledge_from_setting_extraction(
        update_data,
        story_id,
        chapter_no,
        project_name=project_name,
    )
    queued_count = _skills_api.queue_pending_knowledge_items(
        project_name,
        pending_items,
        scope="project",
        authority="project",
        source_title=f"第 {chapter_no} 章正文",
        source_origin="chapter_update",
    )
    chapter_summary_saved = False
    chapter_summary_error = ""
    try:
        summaries = [
            item for item in _skills_api.load_story_chapter_summaries(project_name, story_id)
            if not isinstance(item, dict) or item.get("chapter_no") != chapter_no
        ]
        summaries.append({
            "chapter_no": update_data["chapter_no"],
            "summary": update_data["chapter_summary"]
        })
        _skills_api.save_story_chapter_summaries(project_name, story_id, summaries)
        chapter_summary_saved = True
    except Exception as exc:
        chapter_summary_error = f"章节摘要保存失败：{exc}"
        _skills_api.logging.getLogger("novelforge").warning(
            "Failed to save story chapter summaries: project=%s story=%s chapter=%s error=%s",
            project_name, story_id, chapter_no, exc,
        )
    return _skills_api._make_step_result(
        "setting_extraction",
        success=chapter_summary_saved,
        status="completed" if chapter_summary_saved else "failed",
        data={
            "applied_updates": update_data,
            "pending_knowledge_items": pending_items,
            "queued_knowledge_count": queued_count,
            "chapter_summary_saved": chapter_summary_saved,
        },
        error=chapter_summary_error,
        warnings=(
            []
            if chapter_summary_saved
            else ["候选设定已加入待确认知识队列，但章节摘要未保存；可重试设定提炼步骤。"]
        ),
        retrieval_hits=retrieval_hits,
        validation=_skills_api._make_validation_status(
            status="passed",
            schema_name="MemoryUpdateResult",
            message=(
                "章节设定提炼已通过结构校验，候选设定已加入待确认知识队列。"
                if chapter_summary_saved
                else "章节设定提炼已通过结构校验，但章节摘要保存失败。"
            ),
        ),
        artifacts={
            "memory_saved": False,
            "pending_knowledge_count": len(pending_items),
            "queued_knowledge_count": queued_count,
            "chapter_summary_saved": chapter_summary_saved,
        },
    ).model_dump()
