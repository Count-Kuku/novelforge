import json
from pathlib import Path

BASE_DIR = Path("data/projects")
GLOBAL_RULES_PATH = Path("data/global_rules.json")
RULE_SCOPES = ["all", "outline", "chapter_outline", "write", "review", "memory_update"]
DEFAULT_MEMORY = {
    "title": "",
    "genre": "",
    "world": [],
    "characters": [],
    "timeline": [],
    "foreshadowing": [],
    "chapter_summaries": []
}


def _default_rules() -> dict:
    return {
        "all": [],
        "outline": [],
        "chapter_outline": [],
        "write": [],
        "review": [],
        "memory_update": [],
    }


def normalize_rules(rules: dict | None) -> dict:
    normalized = _default_rules()
    if isinstance(rules, dict):
        for scope in RULE_SCOPES:
            value = rules.get(scope, [])
            normalized[scope] = [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []
    return normalized


def project_path(project_name: str) -> Path:
    path = BASE_DIR / project_name.strip()
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_projects() -> list[str]:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(
        [path.name for path in BASE_DIR.iterdir() if path.is_dir()],
        key=str.lower
    )


def normalize_memory(project_name: str, memory: dict | None) -> dict:
    normalized = DEFAULT_MEMORY.copy()
    if isinstance(memory, dict):
        normalized.update(memory)

    normalized["title"] = normalized.get("title") or project_name

    for key in ["world", "characters", "timeline", "foreshadowing", "chapter_summaries"]:
        value = normalized.get(key)
        normalized[key] = value if isinstance(value, list) else []

    genre = normalized.get("genre", "")
    normalized["genre"] = genre if isinstance(genre, str) else str(genre)
    return normalized


def load_memory(project_name: str) -> dict:
    path = project_path(project_name) / "memory.json"

    if not path.exists():
        memory = normalize_memory(project_name, None)
        save_memory(project_name, memory)
        return memory

    memory = json.loads(path.read_text(encoding="utf-8"))
    normalized = normalize_memory(project_name, memory)

    if normalized != memory:
        save_memory(project_name, normalized)

    return normalized


def save_memory(project_name: str, memory: dict):
    path = project_path(project_name) / "memory.json"
    normalized = normalize_memory(project_name, memory)
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def load_global_rules() -> dict:
    GLOBAL_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not GLOBAL_RULES_PATH.exists():
        rules = normalize_rules(None)
        save_global_rules(rules)
        return rules

    rules = json.loads(GLOBAL_RULES_PATH.read_text(encoding="utf-8"))
    normalized = normalize_rules(rules)
    if normalized != rules:
        save_global_rules(normalized)
    return normalized


def save_global_rules(rules: dict):
    GLOBAL_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_rules(rules)
    GLOBAL_RULES_PATH.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def load_project_rules(project_name: str) -> dict:
    path = project_path(project_name) / "rules.json"
    if not path.exists():
        rules = normalize_rules(None)
        save_project_rules(project_name, rules)
        return rules

    rules = json.loads(path.read_text(encoding="utf-8"))
    normalized = normalize_rules(rules)
    if normalized != rules:
        save_project_rules(project_name, normalized)
    return normalized


def save_project_rules(project_name: str, rules: dict):
    path = project_path(project_name) / "rules.json"
    normalized = normalize_rules(rules)
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def save_outline(project_name: str, outline: str):
    path = project_path(project_name) / "outline.md"
    path.write_text(outline, encoding="utf-8")


def load_outline(project_name: str) -> str:
    path = project_path(project_name) / "outline.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def save_chapter_outline(project_name: str, chapter_no: int, outline: str):
    path = project_path(project_name) / "chapter_outlines"
    path.mkdir(exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.md"
    file.write_text(outline, encoding="utf-8")


def load_chapter_outline(project_name: str, chapter_no: int) -> str:
    file = project_path(project_name) / "chapter_outlines" / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_chapter(project_name: str, chapter_no: int, content: str):
    path = project_path(project_name) / "chapters"
    path.mkdir(exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")


def load_chapter(project_name: str, chapter_no: int) -> str:
    file = project_path(project_name) / "chapters" / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_review(project_name: str, chapter_no: int, content: str):
    path = project_path(project_name) / "reviews"
    path.mkdir(exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")


def load_review(project_name: str, chapter_no: int) -> str:
    file = project_path(project_name) / "reviews" / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


DEFAULT_SUMMARY_LIMIT = 5

def get_recent_chapter_summaries(project_name: str, limit: int = DEFAULT_SUMMARY_LIMIT) -> list[dict]:
    memory = load_memory(project_name)
    summaries = [
        item for item in memory.get("chapter_summaries", [])
        if isinstance(item, dict) and item.get("summary")
    ]
    summaries.sort(key=lambda item: item.get("chapter_no", 0))
    return summaries[-limit:]


def save_review_json(project_name: str, chapter_no: int, data: dict):
    path = project_path(project_name) / "reviews"
    path.mkdir(exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.json"
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_review_json(project_name: str, chapter_no: int) -> dict | None:
    file = project_path(project_name) / "reviews" / f"chapter_{chapter_no:03d}.json"
    if not file.exists():
        return None
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_analysis_report(project_name: str, analysis_type: str, chapter_no: int, content: str):
    path = project_path(project_name) / "analysis"
    path.mkdir(exist_ok=True)
    file = path / f"{analysis_type}_chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")


def load_analysis_report(project_name: str, analysis_type: str, chapter_no: int) -> str:
    file = project_path(project_name) / "analysis" / f"{analysis_type}_chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def retrieval_path(project_name: str) -> Path:
    path = project_path(project_name) / "retrieval"
    path.mkdir(exist_ok=True)
    return path


def retrieval_sources_path(project_name: str) -> Path:
    path = retrieval_path(project_name) / "sources"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_retrieval_manifest(project_name: str, content: str):
    file = retrieval_path(project_name) / "manifest.json"
    file.write_text(content, encoding="utf-8")


def load_retrieval_manifest(project_name: str) -> str:
    file = retrieval_path(project_name) / "manifest.json"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_retrieval_vectors(project_name: str, content: str):
    file = retrieval_path(project_name) / "vectors.json"
    file.write_text(content, encoding="utf-8")


def load_retrieval_vectors(project_name: str) -> str:
    file = retrieval_path(project_name) / "vectors.json"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def chapter_count(project_name: str) -> int:
    chapters_dir = project_path(project_name) / "chapters"
    if not chapters_dir.exists():
        return 0
    return len([f for f in chapters_dir.iterdir() if f.suffix == ".md"])
