import json
import re
from llm import call_llm
from prompts import (
    outline_prompt,
    chapter_outline_prompt,
    write_chapter_prompt,
    update_memory_prompt
)
from memory import load_memory, save_memory, save_chapter


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

def generate_outline(project_name: str, user_idea: str) -> str:
    memory = load_memory(project_name)
    prompt = outline_prompt(memory, user_idea)
    return call_llm(prompt)

def generate_chapter_outline(
    project_name: str,
    chapter_no: int,
    user_requirement: str
) -> str:
    memory = load_memory(project_name)
    prompt = chapter_outline_prompt(memory, chapter_no, user_requirement)
    return call_llm(prompt)

def write_chapter(
    project_name: str,
    chapter_no: int,
    chapter_outline: str
) -> str:
    memory = load_memory(project_name)
    prompt = write_chapter_prompt(memory, chapter_outline)
    chapter = call_llm(prompt)

    save_chapter(project_name, chapter_no, chapter)
    return chapter

def update_memory_from_chapter(
    project_name: str,
    chapter_no: int,
    chapter: str
) -> str:
    memory = load_memory(project_name)
    prompt = update_memory_prompt(memory, chapter)
    result = call_llm(prompt)

    try:
        updates = _extract_json_object(result)
    except Exception:
        return result

    memory["world"].extend(updates.get("world_updates", []))
    memory["characters"].extend(updates.get("new_characters", []))
    memory["timeline"].extend(updates.get("timeline_updates", []))
    memory["foreshadowing"].extend(updates.get("foreshadowing_updates", []))
    memory["world"] = _dedupe_list_items(memory["world"])
    memory["characters"] = _dedupe_list_items(memory["characters"])
    memory["timeline"] = _dedupe_list_items(memory["timeline"])
    memory["foreshadowing"] = _dedupe_list_items(memory["foreshadowing"])

    chapter_summary = {
        "chapter_no": chapter_no,
        "summary": updates.get("chapter_summary", "")
    }

    memory["chapter_summaries"] = [
        item for item in memory["chapter_summaries"]
        if not isinstance(item, dict) or item.get("chapter_no") != chapter_no
    ]
    memory["chapter_summaries"].append({
        "chapter_no": chapter_summary["chapter_no"],
        "summary": chapter_summary["summary"]
    })

    save_memory(project_name, memory)
    return json.dumps(updates, ensure_ascii=False, indent=2)
