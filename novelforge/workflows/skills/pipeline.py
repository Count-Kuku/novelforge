"""Implementation slice for the skills facade: pipeline."""

from __future__ import annotations

from novelforge.workflows import skills as _skills_api

def _build_pipeline_run_id(
    chapter_no: int,
    story_id: str,
    *,
    started_at: str,
    resumed: bool = False,
) -> str:
    raw_story_id = str(story_id or "default").strip() or "default"
    safe_story_id = _skills_api.re.sub(r"[^0-9A-Za-z_-]+", "_", raw_story_id).strip("_")[:48] or "story"
    story_digest = _skills_api.hashlib.sha256(raw_story_id.encode("utf-8")).hexdigest()[:12]
    timestamp = _skills_api.re.sub(r"[^0-9]", "", started_at)
    resume_marker = "_resume" if resumed else ""
    return (
        f"chapter_{chapter_no:03d}_{safe_story_id}_{story_digest}{resume_marker}_"
        f"{timestamp}_{_skills_api.uuid4().hex}"
    )


def pipeline_plan_write_review_update(
    project_name: str,
    chapter_no: int,
    user_requirement: str,
    word_count: str = "2000-2500",
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    started_at = _skills_api.datetime.now().isoformat(timespec="microseconds")
    run_id = _build_pipeline_run_id(chapter_no, story_id, started_at=started_at)
    state = _skills_api.ChapterPipelineState(
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
        _skills_api._safe_stream_emit(stream_callback, f"\n\n## {title}\n\n")

    try:
        emit_step_heading("章节细纲")
        outline = _skills_api.generate_chapter_outline(project_name, chapter_no, user_requirement, story_id=story_id, stream_callback=stream_callback)
        outline_step = _skills_api.WorkflowStepResult.model_validate(outline)
    except Exception as exc:
        outline_step = _skills_api._make_step_result(
            "chapter_outline",
            success=False,
            status="failed",
            error=str(exc),
            retrieval_hits=_skills_api.get_retrieval_trace(_skills_api._story_trace_key("chapter_outline", project_name, story_id, chapter_no)),
        )
        _skills_api._record_pipeline_error(state, step_name="chapter_outline", message=str(exc), error_type="llm")

    _skills_api._record_pipeline_step(state, outline_step)
    state.chapter_outline = outline_step.data.get("chapter_outline", "")
    if outline_step.success:
        state.last_successful_step = "chapter_outline"

    if outline_step.success:
        state.next_step = "write_chapter"
        _skills_api._transition_pipeline_state(state, "write_chapter", "chapter outline completed")
        try:
            emit_step_heading("正文")
            chapter = _skills_api.write_chapter(project_name, chapter_no, state.chapter_outline, None, word_count, story_id=story_id, stream_callback=stream_callback)
            chapter_step = _skills_api.WorkflowStepResult.model_validate(chapter)
        except Exception as exc:
            chapter_step = _skills_api._make_step_result(
                "write_chapter",
                success=False,
                status="failed",
                error=str(exc),
                retrieval_hits=_skills_api.get_retrieval_trace(_skills_api._story_trace_key("write", project_name, story_id, chapter_no)),
            )
            _skills_api._record_pipeline_error(state, step_name="write_chapter", message=str(exc), error_type="llm")
    else:
        chapter_step = _skills_api._make_step_result(
            "write_chapter",
            success=False,
            status="skipped",
            warnings=["Skipped because chapter outline step did not complete successfully."],
            retrieval_hits=_skills_api.get_retrieval_trace(_skills_api._story_trace_key("write", project_name, story_id, chapter_no)),
        )
        _skills_api._halt_pipeline(state, "chapter_outline_failed")

    _skills_api._record_pipeline_step(state, chapter_step)
    state.chapter = chapter_step.data.get("chapter", "")
    if chapter_step.success:
        state.last_successful_step = "write_chapter"

    if chapter_step.success:
        state.next_step = "review_chapter"
        _skills_api._transition_pipeline_state(state, "review_chapter", "chapter writing completed")
        try:
            emit_step_heading("审阅")
            review_step_data = _skills_api.review_chapter(project_name, chapter_no, state.chapter, story_id=story_id, stream_callback=stream_callback)
            review_step = _skills_api.WorkflowStepResult.model_validate(review_step_data)
        except Exception as exc:
            review_step = _skills_api._make_step_result(
                "review_chapter",
                success=False,
                status="failed",
                error=str(exc),
                retrieval_hits=_skills_api.get_retrieval_trace(_skills_api._story_trace_key("review", project_name, story_id, chapter_no)),
            )
            _skills_api._record_pipeline_error(state, step_name="review_chapter", message=str(exc), error_type="llm")
    else:
        review_step = _skills_api._make_step_result(
            "review_chapter",
            success=False,
            status="skipped",
            warnings=["Skipped because chapter writing step did not complete successfully."],
            retrieval_hits=_skills_api.get_retrieval_trace(_skills_api._story_trace_key("review", project_name, story_id, chapter_no)),
        )
        if not state.halted:
            _skills_api._halt_pipeline(state, "write_chapter_failed")

    _skills_api._record_pipeline_step(state, review_step)
    state.review = review_step.data.get("review", {})
    state.review_markdown = review_step.data.get("review_markdown", "")
    if review_step.success:
        state.last_successful_step = "review_chapter"

    if chapter_step.success and review_step.success:
        state.next_step = "setting_extraction"
        _skills_api._transition_pipeline_state(state, "setting_extraction", "review step completed")
        try:
            emit_step_heading("设定提炼")
            memory_step_data = _skills_api.extract_setting_candidates_from_chapter(project_name, chapter_no, state.chapter, story_id=story_id, stream_callback=stream_callback)
            memory_step = _skills_api.WorkflowStepResult.model_validate(memory_step_data)
        except Exception as exc:
            memory_step = _skills_api._make_step_result(
                "setting_extraction",
                success=False,
                status="failed",
                error=str(exc),
                retrieval_hits=_skills_api.get_retrieval_trace(_skills_api._story_trace_key("setting_extraction", project_name, story_id, chapter_no)),
            )
            _skills_api._record_pipeline_error(state, step_name="setting_extraction", message=str(exc), error_type="llm")
    else:
        skip_reason = "review_chapter_failed" if chapter_step.success else "write_chapter_failed"
        skip_warning = (
            "Skipped because chapter review step did not complete successfully."
            if chapter_step.success
            else "Skipped because chapter writing step did not complete successfully."
        )
        memory_step = _skills_api._make_step_result(
            "setting_extraction",
            success=False,
            status="skipped",
            warnings=[skip_warning],
            retrieval_hits=_skills_api.get_retrieval_trace(_skills_api._story_trace_key("setting_extraction", project_name, story_id, chapter_no)),
        )
        if not state.halted:
            _skills_api._halt_pipeline(state, skip_reason)

    _skills_api._record_pipeline_step(state, memory_step)
    state.setting_extraction = memory_step.data
    if memory_step.success:
        state.last_successful_step = "setting_extraction"
    elif not state.halted:
        _skills_api._halt_pipeline(state, "setting_extraction_failed")

    if not state.halted:
        state.next_step = ""
        _skills_api._transition_pipeline_state(state, "completed", "pipeline finished")
    state.finished_at = _skills_api.datetime.now().isoformat(timespec="seconds")
    state.success = all(step.success for step in state.steps.values() if step.status != "skipped")
    state.resumable = bool(state.halted and state.last_successful_step)

    pipeline_result = _skills_api.WorkflowPipelineResult(
        success=state.success,
        steps=state.steps,
        warnings=state.warnings,
    )
    result = state.model_dump()
    result["story_id"] = story_id
    result["pipeline"] = pipeline_result.model_dump()
    _skills_api.save_pipeline_run(project_name, state.run_id, _skills_api.json.dumps(result, ensure_ascii=False, indent=2), story_id=story_id)
    return result


def resume_chapter_pipeline(project_name: str, run_id: str, story_id: str = "default", stream_callback=None) -> dict:
    raw = _skills_api.load_pipeline_run(project_name, run_id, story_id=story_id)
    if not raw.strip():
        raise RuntimeError("没有找到该流水线运行记录。")
    previous = _skills_api.json.loads(raw)
    if not previous.get("resumable"):
        raise RuntimeError("选中的流水线运行记录没有标记为可恢复。")
    previous_story_id = str(previous.get("story_id") or "").strip()
    if previous_story_id and previous_story_id != story_id:
        raise RuntimeError("选中的流水线运行记录属于其他故事，无法在当前故事下恢复。")

    chapter_no = int(previous.get("chapter_no", 0))
    if chapter_no <= 0:
        raise RuntimeError("上一条运行记录缺少有效章节编号。")

    started_at = _skills_api.datetime.now().isoformat(timespec="microseconds")
    resumed_run_id = _build_pipeline_run_id(
        chapter_no,
        story_id,
        started_at=started_at,
        resumed=True,
    )
    state = _skills_api.ChapterPipelineState(
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
    _skills_api._transition_pipeline_state(state, "resume", f"resuming from {run_id}")

    def emit_step_heading(title: str) -> None:
        _skills_api._safe_stream_emit(stream_callback, f"\n\n## {title}\n\n")

    last_successful_step = str(previous.get("last_successful_step", "") or "")
    if last_successful_step == "chapter_outline":
        state.next_step = "write_chapter"
        _skills_api._transition_pipeline_state(state, "write_chapter", "resuming after chapter outline")
        try:
            emit_step_heading("正文")
            chapter_step = _skills_api.WorkflowStepResult.model_validate(
                _skills_api.write_chapter(project_name, chapter_no, state.chapter_outline, None, state.word_count, story_id=story_id, stream_callback=stream_callback)
            )
        except Exception as exc:
            chapter_step = _skills_api._make_step_result(
                "write_chapter", success=False, status="failed", error=str(exc),
                retrieval_hits=_skills_api.get_retrieval_trace(_skills_api._story_trace_key("write", project_name, story_id, chapter_no)),
            )
            _skills_api._record_pipeline_error(state, step_name="write_chapter", message=str(exc), error_type="llm")
        _skills_api._record_pipeline_step(state, chapter_step)
        state.chapter = chapter_step.data.get("chapter", "")
        if not chapter_step.success:
            _skills_api._halt_pipeline(state, "write_chapter_failed")
        else:
            state.last_successful_step = "write_chapter"
            last_successful_step = "write_chapter"

    if last_successful_step == "write_chapter":
        state.next_step = "review_chapter"
        _skills_api._transition_pipeline_state(state, "review_chapter", "resuming after chapter writing")
        try:
            emit_step_heading("审阅")
            review_step = _skills_api.WorkflowStepResult.model_validate(_skills_api.review_chapter(project_name, chapter_no, state.chapter, story_id=story_id, stream_callback=stream_callback))
        except Exception as exc:
            review_step = _skills_api._make_step_result(
                "review_chapter", success=False, status="failed", error=str(exc),
                retrieval_hits=_skills_api.get_retrieval_trace(_skills_api._story_trace_key("review", project_name, story_id, chapter_no)),
            )
            _skills_api._record_pipeline_error(state, step_name="review_chapter", message=str(exc), error_type="llm")
        _skills_api._record_pipeline_step(state, review_step)
        state.review = review_step.data.get("review", {})
        state.review_markdown = review_step.data.get("review_markdown", "")
        if review_step.success:
            state.last_successful_step = "review_chapter"
            last_successful_step = "review_chapter"

    if last_successful_step == "review_chapter":
        state.next_step = "setting_extraction"
        _skills_api._transition_pipeline_state(state, "setting_extraction", "resuming after review")
        try:
            emit_step_heading("设定提炼")
            memory_step = _skills_api.WorkflowStepResult.model_validate(_skills_api.extract_setting_candidates_from_chapter(project_name, chapter_no, state.chapter, story_id=story_id, stream_callback=stream_callback))
        except Exception as exc:
            memory_step = _skills_api._make_step_result(
                "setting_extraction", success=False, status="failed", error=str(exc),
                retrieval_hits=_skills_api.get_retrieval_trace(_skills_api._story_trace_key("setting_extraction", project_name, story_id, chapter_no)),
            )
            _skills_api._record_pipeline_error(state, step_name="setting_extraction", message=str(exc), error_type="llm")
        _skills_api._record_pipeline_step(state, memory_step)
        state.setting_extraction = memory_step.data
        if memory_step.success:
            state.last_successful_step = "setting_extraction"

    if state.last_successful_step == "setting_extraction":
        state.next_step = ""
        _skills_api._transition_pipeline_state(state, "completed", "resume finished")
    elif not state.halted:
        _skills_api._halt_pipeline(state, "resume_incomplete")

    state.finished_at = _skills_api.datetime.now().isoformat(timespec="seconds")
    state.success = state.last_successful_step == "setting_extraction" and not state.halted
    state.resumable = bool(state.halted and state.last_successful_step)
    pipeline_result = _skills_api.WorkflowPipelineResult(
        success=state.success,
        steps=state.steps,
        warnings=state.warnings,
    )
    result = state.model_dump()
    result["story_id"] = story_id
    result["pipeline"] = pipeline_result.model_dump()
    _skills_api.save_pipeline_run(project_name, state.run_id, _skills_api.json.dumps(result, ensure_ascii=False, indent=2), story_id=story_id)
    return result
