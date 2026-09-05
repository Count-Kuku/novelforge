"""Rule payload normalization shared across the memory facade."""

from __future__ import annotations

RULE_SCOPES = ["all", "outline", "chapter_outline", "write", "review", "setting_extraction"]


def _default_rules() -> dict:
    return {
        "all": [],
        "outline": [],
        "chapter_outline": [],
        "write": [],
        "review": [],
        "setting_extraction": [],
    }


def normalize_rules(rules: dict | None) -> dict:
    normalized = _default_rules()
    if isinstance(rules, dict):
        for scope in RULE_SCOPES:
            value = rules.get(scope, [])
            normalized[scope] = [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []
    return normalized
