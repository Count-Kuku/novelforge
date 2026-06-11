import json
import re
from llm import call_llm
from prompts import (
    format_rules_for_prompt,
    outline_prompt,
    chapter_outline_prompt,
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
    save_memory,
    save_outline,
    save_project_rules,
    save_review,
    save_review_json,
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


def _coerce_list(value) -> list:
    if isinstance(value, list):
        return value
    return []


def _coerce_string(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value).strip()


def _build_rules_text(project_name: str, scope: str) -> str:
    global_rules = load_global_rules()
    project_rules = load_project_rules(project_name)
    return format_rules_for_prompt(global_rules, project_rules, scope)


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


def _normalize_memory_updates(updates: dict, chapter_no: int) -> dict:
    if not isinstance(updates, dict):
        raise ValueError("Memory update payload must be a JSON object.")

    for key in ["new_characters", "world_updates", "timeline_updates", "foreshadowing_updates"]:
        if not isinstance(updates.get(key, []), list):
            raise ValueError(f"Memory update field '{key}' must be a list.")

    if not isinstance(updates.get("chapter_summary", ""), str):
        raise ValueError("Memory update field 'chapter_summary' must be a string.")

    return {
        "new_characters": _coerce_list(updates.get("new_characters")),
        "world_updates": _coerce_list(updates.get("world_updates")),
        "timeline_updates": _coerce_list(updates.get("timeline_updates")),
        "foreshadowing_updates": _coerce_list(updates.get("foreshadowing_updates")),
        "chapter_summary": _coerce_string(updates.get("chapter_summary")),
        "chapter_no": chapter_no,
    }


def _normalize_review(review: dict) -> dict:
    if not isinstance(review, dict):
        raise ValueError("Review payload must be a JSON object.")

    status = _coerce_string(review.get("status")).lower()
    if status not in {"pass", "revise", "blocked"}:
        raise ValueError("Review status must be one of: pass, revise, blocked.")

    consistency_checks = review.get("consistency_checks")
    if not isinstance(consistency_checks, dict):
        raise ValueError("Review field 'consistency_checks' must be an object.")

    strengths = review.get("strengths", [])
    issues = review.get("issues", [])
    if not isinstance(strengths, list) or not all(isinstance(item, str) for item in strengths):
        raise ValueError("Review field 'strengths' must be a list of strings.")
    if not isinstance(issues, list) or not all(isinstance(item, str) for item in issues):
        raise ValueError("Review field 'issues' must be a list of strings.")

    return {
        "status": status,
        "summary": _coerce_string(review.get("summary")),
        "strengths": [_coerce_string(item) for item in strengths if _coerce_string(item)],
        "issues": [_coerce_string(item) for item in issues if _coerce_string(item)],
        "consistency_checks": {
            "characters": _coerce_string(consistency_checks.get("characters")),
            "world": _coerce_string(consistency_checks.get("world")),
            "timeline": _coerce_string(consistency_checks.get("timeline")),
            "foreshadowing": _coerce_string(consistency_checks.get("foreshadowing")),
        },
        "pacing": _coerce_string(review.get("pacing")),
        "next_action": _coerce_string(review.get("next_action")),
    }


def _format_review_markdown(review: dict) -> str:
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
    word_count: str = "2500-3500"
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
        updates = _normalize_memory_updates(_extract_json_object(result), chapter_no)
    except Exception as exc:
        return json.dumps({
            "status": "rejected",
            "reason": str(exc),
            "raw_response": result,
        }, ensure_ascii=False, indent=2)

    memory["world"].extend(updates["world_updates"])
    memory["characters"].extend(updates["new_characters"])
    memory["timeline"].extend(updates["timeline_updates"])
    memory["foreshadowing"].extend(updates["foreshadowing_updates"])
    memory["world"] = _dedupe_list_items(memory["world"])
    memory["characters"] = _dedupe_list_items(memory["characters"])
    memory["timeline"] = _dedupe_list_items(memory["timeline"])
    memory["foreshadowing"] = _dedupe_list_items(memory["foreshadowing"])

    memory["chapter_summaries"] = [
        item for item in memory["chapter_summaries"]
        if not isinstance(item, dict) or item.get("chapter_no") != chapter_no
    ]
    memory["chapter_summaries"].append({
        "chapter_no": updates["chapter_no"],
        "summary": updates["chapter_summary"]
    })

    save_memory(project_name, memory)
    return json.dumps({
        "status": "accepted",
        "applied_updates": updates,
    }, ensure_ascii=False, indent=2)


def review_chapter(project_name: str, chapter_no: int, chapter: str) -> str:
    memory = load_memory(project_name)
    chapter_outline = load_chapter_outline(project_name, chapter_no)
    prompt = review_chapter_prompt(memory, chapter_outline, chapter, _build_rules_text(project_name, "review"))
    result = call_llm(prompt)

    try:
        review = _normalize_review(_extract_json_object(result))
    except Exception as exc:
        fallback_review = {
            "status": "blocked",
            "summary": f"审阅结果解析失败：{exc}",
            "strengths": [],
            "issues": ["模型未按要求返回合法 JSON 审阅结果。"],
            "consistency_checks": {
                "characters": "未知",
                "world": "未知",
                "timeline": "未知",
                "foreshadowing": "未知",
            },
            "pacing": "未知",
            "next_action": "检查原始审阅结果并重新生成。",
        }
        markdown = _format_review_markdown(fallback_review) + f"\n\n## Raw Response\n\n```text\n{result}\n```"
        save_review_json(project_name, chapter_no, fallback_review)
        save_review(project_name, chapter_no, markdown)
        return markdown

    markdown = _format_review_markdown(review)
    save_review_json(project_name, chapter_no, review)
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


def pipeline_plan_write_review_update(
    project_name: str,
    chapter_no: int,
    user_requirement: str,
    word_count: str = "2500-3500"
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
