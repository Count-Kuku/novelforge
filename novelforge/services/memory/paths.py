"""Path constants and Windows-safe path character rules for storage keys."""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path("data/projects")
PROJECT_REGISTRY_PATH = BASE_DIR / "index.json"
DELETED_PROJECTS_DIR = Path("data/deleted_projects")
PROJECT_DATA_MARKERS = (
    "stories",
    "memory.json",
    "creative_profile.json",
    "rules.json",
    "prompt_options.json",
    "retrieval",
)
GLOBAL_RULES_PATH = Path("data/global_rules.json")
GLOBAL_PROMPT_OPTIONS_PATH = Path("data/prompt_options.json")
GLOBAL_RULE_CONFLICT_RESOLUTIONS_PATH = Path("data/global_rule_conflict_resolutions.json")
ENV_PATH = Path(".env")
LLM_PROFILES_PATH = Path("data/llm_profiles.json")
WINDOWS_RESERVED_PATH_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
WINDOWS_INVALID_PATH_CHARS = set('<>:"/\\|?*')
