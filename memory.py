import json
from pathlib import Path

BASE_DIR = Path("data/projects")
DEFAULT_MEMORY = {
    "title": "",
    "genre": "",
    "world": [],
    "characters": [],
    "timeline": [],
    "foreshadowing": [],
    "chapter_summaries": []
}


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
