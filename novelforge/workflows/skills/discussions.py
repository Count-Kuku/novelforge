"""Implementation slice for the skills facade: discussions."""

from __future__ import annotations

from novelforge.workflows import skills as _skills_api


def _call_discussion_llm(
    project_name: str,
    story_id: str,
    operation: str,
    prompt: str,
    empty_error: str,
    *,
    stream_callback=None,
) -> dict:
    return _skills_api._call_json_llm(
        prompt,
        empty_error,
        stream_callback=stream_callback,
        usage_context={
            "project_name": project_name,
            "story_id": story_id,
            "operation": operation,
            "agent_role": "discussion",
        },
    )

def discuss_outline(project_name: str, user_idea: str, story_id: str = "default", stream_callback=None) -> dict:
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    trace_key = _skills_api._story_trace_key("outline_discuss", project_name, story_id)
    retrieval_context = _skills_api._build_discussion_retrieval_context(
        project_name,
        user_idea,
        story_id=story_id,
        trace_key=trace_key,
        retrieval_profile="outline_discussion",
    )
    prompt = _skills_api.discuss_outline_prompt(memory, user_idea, _skills_api._build_rules_text(project_name, "outline", story_id=story_id), retrieval_context=retrieval_context)
    payload = _call_discussion_llm(project_name, story_id, "discussion.outline", prompt, "模型没有返回全书讨论结果。", stream_callback=stream_callback)
    try:
        result = _skills_api.OutlineDiscussionResult.model_validate(payload)
    except _skills_api.ValidationError as exc:
        raise RuntimeError(f"全书讨论结构校验失败：{_skills_api.format_schema_validation_error(exc)}") from exc

    return _skills_api._make_step_result(
        "discuss_outline",
        success=True,
        status="completed",
        data={
            "discussion": result.model_dump(),
            "report_markdown": _skills_api.render_discussion_markdown(result),
        },
        retrieval_hits=_skills_api.get_retrieval_trace(trace_key),
        validation=_skills_api._make_validation_status(
            status="passed",
            schema_name="OutlineDiscussionResult",
            message="全书讨论结果已通过结构校验。",
        ),
    ).model_dump()


def discuss_creative_profile(project_name: str, user_idea: str, story_id: str = "default", stream_callback=None) -> dict:
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    current_profile = _skills_api.load_creative_profile(project_name, story_id)
    trace_key = _skills_api._story_trace_key("creative_profile_discuss", project_name, story_id)
    retrieval_context = _skills_api._build_retrieval_context(
        project_name,
        user_idea,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
        story_id=story_id,
        retrieval_profile="creative_profile_discussion",
    )
    prompt = _skills_api.discuss_creative_profile_prompt(
        memory, current_profile, user_idea,
        _skills_api._build_rules_text(project_name, "all", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_discussion_llm(project_name, story_id, "discussion.creative_profile", prompt, "模型没有返回创作配置讨论结果。", stream_callback=stream_callback)
    try:
        result = _skills_api.CreativeProfileDiscussionResult.model_validate(payload)
    except _skills_api.ValidationError as exc:
        raise RuntimeError(f"创作配置讨论结构校验失败：{_skills_api.format_schema_validation_error(exc)}") from exc

    return _skills_api._make_step_result(
        "discuss_creative_profile",
        success=True,
        status="completed",
        data={
            "discussion": result.model_dump(),
            "report_markdown": _skills_api.render_discussion_markdown(result),
        },
        retrieval_hits=_skills_api.get_retrieval_trace(trace_key),
        validation=_skills_api._make_validation_status(
            status="passed",
            schema_name="CreativeProfileDiscussionResult",
            message="创作配置讨论结果已通过结构校验。",
        ),
    ).model_dump()


def discuss_chapter(project_name: str, chapter_no: int, user_requirement: str, story_id: str = "default", stream_callback=None) -> dict:
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    outline = _skills_api.load_outline(project_name, story_id=story_id)
    chapter_metadata = _skills_api.load_chapter_outline_metadata(project_name, chapter_no, story_id=story_id)
    volume_no = chapter_metadata.get("volume_no")
    arc_no = chapter_metadata.get("arc_no")
    volume_outline = _skills_api.load_volume_outline(project_name, int(volume_no), story_id=story_id) if volume_no else ""
    arc_outline = _skills_api.load_arc_outline(project_name, int(arc_no), story_id=story_id) if arc_no else ""
    volume_discussion_context = _skills_api._format_discussion_context(
        _skills_api.load_volume_discussion_artifact(project_name, int(volume_no), story_id=story_id) if volume_no else {},
        "当前分卷暂无已批准讨论结论。",
    )
    arc_discussion_context = _skills_api._format_discussion_context(
        _skills_api.load_arc_discussion_artifact(project_name, int(arc_no), story_id=story_id) if arc_no else {},
        "当前剧情段暂无已批准讨论结论。",
    )
    chapter_discussion_context = _skills_api._format_discussion_context(
        _skills_api.load_chapter_discussion_artifact(project_name, chapter_no, story_id=story_id),
        "当前章节暂无已批准讨论结论。",
    )
    recent_summaries = _skills_api.get_recent_chapter_summaries(project_name, story_id=story_id)
    trace_key = _skills_api._story_trace_key("chapter_discuss", project_name, story_id, chapter_no)
    retrieval_context = _skills_api._build_discussion_retrieval_context(
        project_name,
        f"第{chapter_no}章 {user_requirement} {outline} {volume_outline} {arc_outline} {volume_discussion_context} {arc_discussion_context} {chapter_discussion_context}",
        story_id=story_id,
        trace_key=trace_key,
        retrieval_profile="chapter_discussion",
    )
    prompt = _skills_api.discuss_chapter_prompt(
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
        _skills_api._build_rules_text(project_name, "chapter_outline", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_discussion_llm(project_name, story_id, "discussion.chapter", prompt, "模型没有返回章节讨论结果。", stream_callback=stream_callback)
    try:
        result = _skills_api.ChapterDiscussionResult.model_validate(payload)
    except _skills_api.ValidationError as exc:
        raise RuntimeError(f"章节讨论结构校验失败：{_skills_api.format_schema_validation_error(exc)}") from exc

    return _skills_api._make_step_result(
        "discuss_chapter",
        success=True,
        status="completed",
        data={
            "discussion": result.model_dump(),
            "report_markdown": _skills_api.render_discussion_markdown(result),
        },
        retrieval_hits=_skills_api.get_retrieval_trace(trace_key),
        validation=_skills_api._make_validation_status(
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
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    trace_key = _skills_api._story_trace_key("outline_discuss_turn", project_name, story_id)
    retrieval_context = _skills_api._build_discussion_retrieval_context(
        project_name,
        f"{user_idea} {latest_user_message} {current_discussion or {}}",
        story_id=story_id,
        trace_key=trace_key,
        retrieval_profile="outline_discussion",
    )
    prompt = _skills_api.discuss_outline_turn_prompt(
        memory,
        user_idea,
        messages,
        current_discussion,
        latest_user_message,
        _skills_api._build_rules_text(project_name, "outline", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_discussion_llm(project_name, story_id, "discussion.outline_turn", prompt, "模型没有返回本轮全书讨论结果。", stream_callback=stream_callback)
    assistant_message = str(payload.get("assistant_message", "") or "").strip()
    discussion_payload = payload.get("discussion", {}) if isinstance(payload, dict) else {}

    try:
        result = _skills_api.OutlineDiscussionResult.model_validate(discussion_payload)
    except _skills_api.ValidationError as exc:
        raise RuntimeError(f"本轮全书讨论结构校验失败：{_skills_api.format_schema_validation_error(exc)}") from exc

    return _skills_api._make_step_result(
        "discuss_outline_turn",
        success=True,
        status="completed",
        data={
            "assistant_message": assistant_message,
            "discussion": result.model_dump(),
            "report_markdown": _skills_api.render_discussion_markdown(result),
        },
        retrieval_hits=_skills_api.get_retrieval_trace(trace_key),
        validation=_skills_api._make_validation_status(
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
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    outline = _skills_api.load_outline(project_name, story_id=story_id)
    chapter_metadata = _skills_api.load_chapter_outline_metadata(project_name, chapter_no, story_id=story_id)
    volume_no = chapter_metadata.get("volume_no")
    arc_no = chapter_metadata.get("arc_no")
    volume_outline = _skills_api.load_volume_outline(project_name, int(volume_no), story_id=story_id) if volume_no else ""
    arc_outline = _skills_api.load_arc_outline(project_name, int(arc_no), story_id=story_id) if arc_no else ""
    volume_discussion_context = _skills_api._format_discussion_context(
        _skills_api.load_volume_discussion_artifact(project_name, int(volume_no), story_id=story_id) if volume_no else {},
        "当前分卷暂无已批准讨论结论。",
    )
    arc_discussion_context = _skills_api._format_discussion_context(
        _skills_api.load_arc_discussion_artifact(project_name, int(arc_no), story_id=story_id) if arc_no else {},
        "当前剧情段暂无已批准讨论结论。",
    )
    chapter_discussion_context = _skills_api._format_discussion_context(
        _skills_api.load_chapter_discussion_artifact(project_name, chapter_no, story_id=story_id),
        "当前章节暂无已批准讨论结论。",
    )
    recent_summaries = _skills_api.get_recent_chapter_summaries(project_name, story_id=story_id)
    trace_key = _skills_api._story_trace_key("chapter_discuss_turn", project_name, story_id, chapter_no)
    retrieval_context = _skills_api._build_discussion_retrieval_context(
        project_name,
        f"第{chapter_no}章 {user_requirement} {latest_user_message} {outline} {volume_outline} {arc_outline} {volume_discussion_context} {arc_discussion_context} {chapter_discussion_context} {current_discussion or {}}",
        story_id=story_id,
        trace_key=trace_key,
        retrieval_profile="chapter_discussion",
    )
    prompt = _skills_api.discuss_chapter_turn_prompt(
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
        _skills_api._build_rules_text(project_name, "chapter_outline", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_discussion_llm(project_name, story_id, "discussion.chapter_turn", prompt, "模型没有返回本轮章节讨论结果。", stream_callback=stream_callback)
    assistant_message = str(payload.get("assistant_message", "") or "").strip()
    discussion_payload = payload.get("discussion", {}) if isinstance(payload, dict) else {}

    try:
        result = _skills_api.ChapterDiscussionResult.model_validate(discussion_payload)
    except _skills_api.ValidationError as exc:
        raise RuntimeError(f"本轮章节讨论结构校验失败：{_skills_api.format_schema_validation_error(exc)}") from exc

    return _skills_api._make_step_result(
        "discuss_chapter_turn",
        success=True,
        status="completed",
        data={
            "assistant_message": assistant_message,
            "discussion": result.model_dump(),
            "report_markdown": _skills_api.render_discussion_markdown(result),
        },
        retrieval_hits=_skills_api.get_retrieval_trace(trace_key),
        validation=_skills_api._make_validation_status(
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
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    current_profile = _skills_api.load_creative_profile(project_name, story_id)
    trace_key = _skills_api._story_trace_key("creative_profile_discuss_turn", project_name, story_id)
    retrieval_context = _skills_api._build_retrieval_context(
        project_name,
        latest_user_message,
        allowed_scopes=["project", "canon", "reference"],
        trace_key=trace_key,
        story_id=story_id,
        retrieval_profile="creative_profile_discussion",
    )
    prompt = _skills_api.discuss_creative_profile_turn_prompt(
        memory,
        current_profile,
        user_idea,
        messages,
        current_discussion,
        latest_user_message,
        _skills_api._build_rules_text(project_name, "all", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_discussion_llm(project_name, story_id, "discussion.creative_profile_turn", prompt, "模型没有返回本轮创作配置讨论结果。", stream_callback=stream_callback)
    assistant_message = str(payload.get("assistant_message", "") or "").strip()
    discussion_payload = payload.get("discussion", {}) if isinstance(payload, dict) else {}

    try:
        result = _skills_api.CreativeProfileDiscussionResult.model_validate(discussion_payload)
    except _skills_api.ValidationError as exc:
        raise RuntimeError(f"本轮创作配置讨论结构校验失败：{_skills_api.format_schema_validation_error(exc)}") from exc

    return _skills_api._make_step_result(
        "discuss_creative_profile_turn",
        success=True,
        status="completed",
        data={
            "assistant_message": assistant_message,
            "discussion": result.model_dump(),
            "report_markdown": _skills_api.render_discussion_markdown(result),
        },
        retrieval_hits=_skills_api.get_retrieval_trace(trace_key),
        validation=_skills_api._make_validation_status(
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
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    story_outline = _skills_api.load_outline(project_name, story_id=story_id)
    trace_key = _skills_api._story_trace_key("volume_discuss", project_name, story_id, volume_no)
    retrieval_context = _skills_api._build_discussion_retrieval_context(
        project_name,
        f"第{volume_no}卷 {volume_title} {volume_summary} {user_requirement} {story_outline}",
        story_id=story_id,
        trace_key=trace_key,
        retrieval_profile="volume_discussion",
    )
    prompt = _skills_api.discuss_volume_prompt(
        memory,
        story_outline,
        volume_no,
        volume_title,
        volume_summary,
        user_requirement,
        _skills_api._build_rules_text(project_name, "outline", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_discussion_llm(project_name, story_id, "discussion.volume", prompt, "模型没有返回分卷讨论结果。", stream_callback=stream_callback)
    try:
        result = _skills_api.VolumeDiscussionResult.model_validate(payload)
    except _skills_api.ValidationError as exc:
        raise RuntimeError(f"分卷讨论结构校验失败：{_skills_api.format_schema_validation_error(exc)}") from exc

    return _skills_api._make_step_result(
        "discuss_volume",
        success=True,
        status="completed",
        data={
            "discussion": result.model_dump(),
            "report_markdown": _skills_api.render_discussion_markdown(result),
        },
        retrieval_hits=_skills_api.get_retrieval_trace(trace_key),
        validation=_skills_api._make_validation_status(
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
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    story_outline = _skills_api.load_outline(project_name, story_id=story_id)
    trace_key = _skills_api._story_trace_key("volume_discuss_turn", project_name, story_id, volume_no)
    retrieval_context = _skills_api._build_discussion_retrieval_context(
        project_name,
        f"第{volume_no}卷 {volume_title} {volume_summary} {user_requirement} {latest_user_message} {story_outline} {current_discussion or {}}",
        story_id=story_id,
        trace_key=trace_key,
        retrieval_profile="volume_discussion",
    )
    prompt = _skills_api.discuss_volume_turn_prompt(
        memory,
        story_outline,
        volume_no,
        volume_title,
        volume_summary,
        user_requirement,
        messages,
        current_discussion,
        latest_user_message,
        _skills_api._build_rules_text(project_name, "outline", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_discussion_llm(project_name, story_id, "discussion.volume_turn", prompt, "模型没有返回本轮分卷讨论结果。", stream_callback=stream_callback)
    assistant_message = str(payload.get("assistant_message", "") or "").strip()
    discussion_payload = payload.get("discussion", {}) if isinstance(payload, dict) else {}

    try:
        result = _skills_api.VolumeDiscussionResult.model_validate(discussion_payload)
    except _skills_api.ValidationError as exc:
        raise RuntimeError(f"本轮分卷讨论结构校验失败：{_skills_api.format_schema_validation_error(exc)}") from exc

    return _skills_api._make_step_result(
        "discuss_volume_turn",
        success=True,
        status="completed",
        data={
            "assistant_message": assistant_message,
            "discussion": result.model_dump(),
            "report_markdown": _skills_api.render_discussion_markdown(result),
        },
        retrieval_hits=_skills_api.get_retrieval_trace(trace_key),
        validation=_skills_api._make_validation_status(
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
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    story_outline = _skills_api.load_outline(project_name, story_id=story_id)
    volume_outline = _skills_api.load_volume_outline(project_name, int(volume_no), story_id=story_id) if volume_no else ""
    trace_key = _skills_api._story_trace_key("arc_discuss", project_name, story_id, arc_no)
    retrieval_context = _skills_api._build_discussion_retrieval_context(
        project_name,
        f"剧情段 {arc_no:03d} 第{volume_no or 0}卷 {arc_title} {arc_summary} {estimated_chapter_count or ''} {target_word_count_range} {user_requirement} {story_outline} {volume_outline}",
        story_id=story_id,
        trace_key=trace_key,
        retrieval_profile="arc_discussion",
    )
    prompt = _skills_api.discuss_arc_prompt(
        memory,
        story_outline,
        volume_outline,
        arc_no,
        arc_title,
        arc_summary,
        estimated_chapter_count,
        target_word_count_range,
        user_requirement,
        _skills_api._build_rules_text(project_name, "outline", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_discussion_llm(project_name, story_id, "discussion.arc", prompt, "模型没有返回剧情段讨论结果。", stream_callback=stream_callback)
    try:
        result = _skills_api.ArcDiscussionResult.model_validate(payload)
    except _skills_api.ValidationError as exc:
        raise RuntimeError(f"剧情段讨论结构校验失败：{_skills_api.format_schema_validation_error(exc)}") from exc

    return _skills_api._make_step_result(
        "discuss_arc",
        success=True,
        status="completed",
        data={
            "discussion": result.model_dump(),
            "report_markdown": _skills_api.render_discussion_markdown(result),
        },
        retrieval_hits=_skills_api.get_retrieval_trace(trace_key),
        validation=_skills_api._make_validation_status(
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
    memory = _skills_api.build_generation_setting_context(project_name, story_id)
    story_outline = _skills_api.load_outline(project_name, story_id=story_id)
    volume_outline = _skills_api.load_volume_outline(project_name, int(volume_no), story_id=story_id) if volume_no else ""
    trace_key = _skills_api._story_trace_key("arc_discuss_turn", project_name, story_id, arc_no)
    retrieval_context = _skills_api._build_discussion_retrieval_context(
        project_name,
        f"剧情段 {arc_no:03d} 第{volume_no or 0}卷 {arc_title} {arc_summary} {estimated_chapter_count or ''} {target_word_count_range} {user_requirement} {latest_user_message} {story_outline} {volume_outline} {current_discussion or {}}",
        story_id=story_id,
        trace_key=trace_key,
        retrieval_profile="arc_discussion",
    )
    prompt = _skills_api.discuss_arc_turn_prompt(
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
        _skills_api._build_rules_text(project_name, "outline", story_id=story_id),
        retrieval_context=retrieval_context,
    )
    payload = _call_discussion_llm(project_name, story_id, "discussion.arc_turn", prompt, "模型没有返回本轮剧情段讨论结果。", stream_callback=stream_callback)
    assistant_message = str(payload.get("assistant_message", "") or "").strip()
    discussion_payload = payload.get("discussion", {}) if isinstance(payload, dict) else {}

    try:
        result = _skills_api.ArcDiscussionResult.model_validate(discussion_payload)
    except _skills_api.ValidationError as exc:
        raise RuntimeError(f"本轮剧情段讨论结构校验失败：{_skills_api.format_schema_validation_error(exc)}") from exc

    return _skills_api._make_step_result(
        "discuss_arc_turn",
        success=True,
        status="completed",
        data={
            "assistant_message": assistant_message,
            "discussion": result.model_dump(),
            "report_markdown": _skills_api.render_discussion_markdown(result),
        },
        retrieval_hits=_skills_api.get_retrieval_trace(trace_key),
        validation=_skills_api._make_validation_status(
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
    _skills_api.save_volume_discussion_artifact(project_name, volume_no, discussion, report_markdown, story_id)
    return {
        "volume_no": volume_no,
        "discussion": discussion,
        "report_markdown": report_markdown,
        "saved_path": f"data/projects/{project_name}/stories/{story_id}/volumes/volume_{volume_no:03d}.discussion.json",
    }


def clear_volume_discussion_approval(project_name: str, volume_no: int, story_id: str = "default") -> bool:
    return _skills_api.delete_volume_discussion_artifact(project_name, volume_no, story_id)


def approve_arc_discussion(project_name: str, arc_no: int, discussion_step: dict, story_id: str = "default") -> dict:
    discussion = discussion_step.get("data", {}).get("discussion", {}) if isinstance(discussion_step, dict) else {}
    report_markdown = discussion_step.get("data", {}).get("report_markdown", "") if isinstance(discussion_step, dict) else ""
    if not isinstance(discussion, dict) or not discussion:
        raise RuntimeError("没有可批准的剧情段讨论结果。")
    if not discussion.get("approval_ready"):
        raise RuntimeError("剧情段讨论结果尚未达到可批准状态。")
    _skills_api.save_arc_discussion_artifact(project_name, arc_no, discussion, report_markdown, story_id)
    return {
        "arc_no": arc_no,
        "discussion": discussion,
        "report_markdown": report_markdown,
        "saved_path": f"data/projects/{project_name}/stories/{story_id}/arcs/arc_{arc_no:03d}.discussion.json",
    }


def clear_arc_discussion_approval(project_name: str, arc_no: int, story_id: str = "default") -> bool:
    return _skills_api.delete_arc_discussion_artifact(project_name, arc_no, story_id)


def approve_outline_discussion(project_name: str, discussion_step: dict, story_id: str = "default") -> dict:
    discussion = discussion_step.get("data", {}).get("discussion", {}) if isinstance(discussion_step, dict) else {}
    report_markdown = discussion_step.get("data", {}).get("report_markdown", "") if isinstance(discussion_step, dict) else ""
    if not isinstance(discussion, dict) or not discussion:
        raise RuntimeError("没有可批准的全书讨论结果。")
    if not discussion.get("approval_ready"):
        raise RuntimeError("全书讨论结果尚未达到可批准状态。")
    _skills_api.save_outline_discussion_artifact(project_name, discussion, report_markdown, story_id)
    return {
        "discussion": discussion,
        "report_markdown": report_markdown,
        "saved_path": f"data/projects/{project_name}/stories/{story_id}/outline.discussion.json",
    }


def clear_outline_discussion_approval(project_name: str, story_id: str = "default") -> bool:
    return _skills_api.delete_outline_discussion_artifact(project_name, story_id)


def save_creative_profile_discussion_result(project_name: str, discussion_step: dict, story_id: str = "default") -> dict:
    discussion = discussion_step.get("data", {}).get("discussion", {}) if isinstance(discussion_step, dict) else {}
    report_markdown = discussion_step.get("data", {}).get("report_markdown", "") if isinstance(discussion_step, dict) else ""
    if not isinstance(discussion, dict) or not discussion:
        raise RuntimeError("没有可保存的创作配置讨论结果。")
    if not discussion.get("approval_ready"):
        raise RuntimeError("创作配置讨论尚未收敛，继续补充后再保存讨论结论。")
    discussion_result = _skills_api.CreativeProfileDiscussionResult.model_validate(discussion)
    discussion_payload = discussion_result.model_dump()
    _skills_api.save_creative_profile_discussion_artifact(project_name, discussion_payload, report_markdown, story_id)
    return {
        "discussion": discussion_payload,
        "report_markdown": report_markdown,
        "saved_path": f"data/projects/{project_name}/stories/{story_id}/creative_profile.discussion.json",
    }


def approve_creative_profile_discussion(project_name: str, discussion_step: dict, story_id: str = "default") -> dict:
    saved_discussion = save_creative_profile_discussion_result(project_name, discussion_step, story_id)
    recommended_profile = _skills_api.CreativeProfileDiscussionResult.model_validate(saved_discussion["discussion"]).recommended_profile.model_dump()
    recommended_profile.pop("notes", None)
    _skills_api.save_creative_profile(project_name, recommended_profile, story_id, mark_configured=True)
    return {
        **saved_discussion,
        "saved_profile": recommended_profile,
    }


def clear_creative_profile_discussion_approval(project_name: str, story_id: str = "default") -> bool:
    return _skills_api.delete_creative_profile_discussion_artifact(project_name, story_id)


def approve_chapter_discussion(project_name: str, chapter_no: int, discussion_step: dict, story_id: str = "default") -> dict:
    discussion = discussion_step.get("data", {}).get("discussion", {}) if isinstance(discussion_step, dict) else {}
    report_markdown = discussion_step.get("data", {}).get("report_markdown", "") if isinstance(discussion_step, dict) else ""
    if not isinstance(discussion, dict) or not discussion:
        raise RuntimeError("没有可批准的章节讨论结果。")
    if not discussion.get("approval_ready"):
        raise RuntimeError("章节讨论结果尚未达到可批准状态。")
    _skills_api.save_chapter_discussion_artifact(project_name, chapter_no, discussion, report_markdown, story_id)
    return {
        "chapter_no": chapter_no,
        "discussion": discussion,
        "report_markdown": report_markdown,
        "saved_path": f"data/projects/{project_name}/stories/{story_id}/chapter_outlines/chapter_{chapter_no:03d}.discussion.json",
    }


def clear_chapter_discussion_approval(project_name: str, chapter_no: int, story_id: str = "default") -> bool:
    return _skills_api.delete_chapter_discussion_artifact(project_name, chapter_no, story_id)


def _format_review_markdown(review: _skills_api.ReviewResult | dict) -> str:
    if isinstance(review, _skills_api.ReviewResult):
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
