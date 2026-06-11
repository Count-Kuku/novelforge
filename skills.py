import json
import re
from llm import call_llm
from pydantic import ValidationError
from prompts import (
    character_analysis_prompt,
    consistency_check_prompt,
    foreshadowing_analysis_prompt,
    format_rules_for_prompt,
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
    load_review_json,
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
    CharacterAnalysisResult,
    ConsistencyAnalysisResult,
    ForeshadowingAnalysisResult,
    ReviewResult,
    TimelineAnalysisResult,
    format_schema_validation_error,
    render_character_analysis_markdown,
    render_consistency_analysis_markdown,
    render_foreshadowing_analysis_markdown,
    render_timeline_analysis_markdown,
    validate_memory_update_result,
    validate_review_result,
)


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

def generate_outline(project_name: str, user_idea: str) -> str:
    memory = load_memory(project_name)
    prompt = outline_prompt(memory, user_idea, _build_rules_text(project_name, "outline"))
    outline = call_llm(prompt)
    if not outline.strip():
        raise RuntimeError("LLM returned empty outline.")
    save_outline(project_name, outline)
    return outline

def generate_chapter_outline(
    project_name: str,
    chapter_no: int,
    user_requirement: str
) -> str:
    memory = load_memory(project_name)
    outline = load_outline(project_name)
    recent_summaries = get_recent_chapter_summaries(project_name)
    prompt = chapter_outline_prompt(
        memory,
        outline,
        recent_summaries,
        chapter_no,
        user_requirement,
        _build_rules_text(project_name, "chapter_outline"),
    )
    outline = call_llm(prompt)
    if not outline.strip():
        raise RuntimeError("LLM returned empty chapter outline.")
    save_chapter_outline(project_name, chapter_no, outline)
    return outline

def write_chapter(
    project_name: str,
    chapter_no: int,
    chapter_outline: str,
    word_count: str = "2000-2500"
) -> str:
    memory = load_memory(project_name)
    prompt = write_chapter_prompt(memory, chapter_outline, word_count, _build_rules_text(project_name, "write"))
    chapter = call_llm(prompt)
    if not chapter.strip():
        raise RuntimeError("LLM returned empty chapter content.")
    save_chapter(project_name, chapter_no, chapter)
    return chapter

def update_memory_from_chapter(
    project_name: str,
    chapter_no: int,
    chapter: str
) -> str:
    memory = load_memory(project_name)
    prompt = update_memory_prompt(memory, chapter, _build_rules_text(project_name, "memory_update"))
    result = call_llm(prompt)

    try:
        updates = validate_memory_update_result(_extract_json_object(result), chapter_no)
    except ValidationError as exc:
        return json.dumps({
            "status": "rejected",
            "reason": format_schema_validation_error(exc),
            "raw_response": result,
        }, ensure_ascii=False, indent=2)
    except Exception as exc:
        return json.dumps({
            "status": "rejected",
            "reason": str(exc),
            "raw_response": result,
        }, ensure_ascii=False, indent=2)

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
    return json.dumps({
        "status": "accepted",
        "applied_updates": update_data,
    }, ensure_ascii=False, indent=2)


def review_chapter(project_name: str, chapter_no: int, chapter: str) -> str:
    memory = load_memory(project_name)
    chapter_outline = load_chapter_outline(project_name, chapter_no)
    prompt = review_chapter_prompt(memory, chapter_outline, chapter, _build_rules_text(project_name, "review"))
    result = call_llm(prompt)

    try:
        review = validate_review_result(_extract_json_object(result))
    except ValidationError as exc:
        fallback_review = ReviewResult(
            status="blocked",
            summary=f"审阅结果解析失败：{format_schema_validation_error(exc)}",
            strengths=[],
            issues=["模型未按要求返回合法 Schema 的审阅结果。"],
            pacing="未知",
            next_action="检查原始审阅结果并重新生成。",
        )
        markdown = _format_review_markdown(fallback_review) + f"\n\n## Raw Response\n\n```text\n{result}\n```"
        save_review_json(project_name, chapter_no, fallback_review.model_dump())
        save_review(project_name, chapter_no, markdown)
        return markdown
    except Exception as exc:
        fallback_review = ReviewResult(
            status="blocked",
            summary=f"审阅结果解析失败：{exc}",
            strengths=[],
            issues=["模型未按要求返回合法 JSON 审阅结果。"],
            pacing="未知",
            next_action="检查原始审阅结果并重新生成。",
        )
        markdown = _format_review_markdown(fallback_review) + f"\n\n## Raw Response\n\n```text\n{result}\n```"
        save_review_json(project_name, chapter_no, fallback_review.model_dump())
        save_review(project_name, chapter_no, markdown)
        return markdown

    markdown = _format_review_markdown(review)
    save_review_json(project_name, chapter_no, review.model_dump())
    save_review(project_name, chapter_no, markdown)
    return markdown


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
) -> str:
    payload = _call_json_llm(prompt, empty_error)
    try:
        result = schema.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"Analysis schema validation failed: {format_schema_validation_error(exc)}") from exc
    return renderer(result)


def analyze_characters(project_name: str, chapter_no: int, chapter: str) -> str:
    memory = load_memory(project_name)
    prompt = character_analysis_prompt(memory, chapter, _build_rules_text(project_name, "review"))
    result = _run_analysis(
        prompt,
        "LLM returned empty character analysis.",
        CharacterAnalysisResult,
        render_character_analysis_markdown,
    )
    save_analysis_report(project_name, "characters", chapter_no, result)
    return result


def analyze_timeline(project_name: str, chapter_no: int, chapter: str) -> str:
    memory = load_memory(project_name)
    prompt = timeline_analysis_prompt(memory, chapter, _build_rules_text(project_name, "review"))
    result = _run_analysis(
        prompt,
        "LLM returned empty timeline analysis.",
        TimelineAnalysisResult,
        render_timeline_analysis_markdown,
    )
    save_analysis_report(project_name, "timeline", chapter_no, result)
    return result


def analyze_foreshadowing(project_name: str, chapter_no: int, chapter: str) -> str:
    memory = load_memory(project_name)
    prompt = foreshadowing_analysis_prompt(memory, chapter, _build_rules_text(project_name, "review"))
    result = _run_analysis(
        prompt,
        "LLM returned empty foreshadowing analysis.",
        ForeshadowingAnalysisResult,
        render_foreshadowing_analysis_markdown,
    )
    save_analysis_report(project_name, "foreshadowing", chapter_no, result)
    return result


def run_consistency_check(project_name: str, chapter_no: int, chapter: str) -> str:
    memory = load_memory(project_name)
    prompt = consistency_check_prompt(memory, chapter, _build_rules_text(project_name, "review"))
    result = _run_analysis(
        prompt,
        "LLM returned empty consistency check.",
        ConsistencyAnalysisResult,
        render_consistency_analysis_markdown,
    )
    save_analysis_report(project_name, "consistency", chapter_no, result)
    return result


def pipeline_plan_write_review_update(
    project_name: str,
    chapter_no: int,
    user_requirement: str,
    word_count: str = "2000-2500"
) -> dict:
    result = {
        "chapter_outline": None,
        "chapter": None,
        "review_markdown": None,
        "review": None,
        "memory_update_result": None,
        "errors": {},
    }

    try:
        outline = generate_chapter_outline(project_name, chapter_no, user_requirement)
        result["chapter_outline"] = outline
    except Exception as exc:
        result["errors"]["chapter_outline"] = str(exc)

    if result["chapter_outline"] and "chapter_outline" not in result["errors"]:
        try:
            chapter = write_chapter(project_name, chapter_no, result["chapter_outline"], word_count)
            result["chapter"] = chapter
        except Exception as exc:
            result["errors"]["write_chapter"] = str(exc)

    if result["chapter"] and "write_chapter" not in result["errors"]:
        try:
            review_md = review_chapter(project_name, chapter_no, result["chapter"])
            result["review_markdown"] = review_md
            review_json = load_review_json(project_name, chapter_no)
            result["review"] = review_json if review_json else None
        except Exception as exc:
            result["errors"]["review_chapter"] = str(exc)

    if result["chapter"] and "write_chapter" not in result["errors"]:
        try:
            memory_update = update_memory_from_chapter(project_name, chapter_no, result["chapter"])
            memory_update_data = json.loads(memory_update) if isinstance(memory_update, str) else memory_update
            result["memory_update_result"] = memory_update_data
        except Exception as exc:
            result["errors"]["memory_update"] = str(exc)

    return result
