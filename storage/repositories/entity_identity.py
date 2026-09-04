"""Entity identity + slot supersession helpers for the Entity-Fact-Relation model.

Pure functions with no storage/novelforge imports, so both the repository layer
(``storage/repositories/knowledge.py``) and higher-level backfill code can share
the exact same grouping key. Keeping this single-sourced is what makes entity
grouping and fact supersession consistent across write paths.
"""
from __future__ import annotations

import re
from hashlib import sha256
from typing import Any

# Mirrors domain/knowledge_quality.GLOBAL_WORLDLINE_IDS
GLOBAL_WORLDLINE_IDS = {"", "all", "global", "shared", "common", "canon", "unknown"}

# category -> entity_type (the one place this mapping is authoritative for backfill).
CATEGORY_TO_ENTITY_TYPE: dict[str, str] = {
    "characters": "character",
    "items": "item",
    "abilities": "ability",
    "locations": "location",
    "organizations": "organization",
    "timeline_events": "event",
    "world_rules": "world_rule",
    "relationships": "relationship",
    "writing_style": "writing_style",
    "dialogue_style": "dialogue_style",
    "narrative_techniques": "narrative_technique",
}

# fact_key -> default merge policy. "replace" means a new value invalidates the
# old one (valid_to_chapter is set); "append" means both stay valid.
FACT_MERGE_POLICY: dict[str, str] = {
    "location": "replace",
    "status": "replace",
    "holder": "replace",
    "owners": "replace",
    "owner": "replace",
    "users": "append",
    "current_goal": "replace",
    "abilities": "append",
    "appearance": "append",
    "personality": "append",
}

# fact_keys that never get chapter supersession (event facts are point-in-time).
_NO_SUPERSESSION_FACT_KEYS = {"timeline", "time", "causes", "outcomes", "order_hint"}


def normalize_name(value: Any) -> str:
    """Mirror ``normalize_knowledge_match_name``: lowercase, keep alnum + CJK only."""
    cleaned = str(value or "").lower()
    return "".join(re.findall(r"[a-z0-9\u4e00-\u9fff]+", cleaned))


def isolation_domain(item: dict) -> tuple[str, str, str, str]:
    """(setting_scope, story_id, worldline_id, version_scope) for an item dict.

    Mirrors ``domain/knowledge_quality._knowledge_isolation_domain``.
    """
    story_id = str(item.get("story_id") or "").strip()
    setting_scope = str(item.get("setting_scope") or ("story" if story_id else "project")).strip().lower()
    if setting_scope != "story":
        story_id = ""
    worldline_id = str(item.get("worldline_id") or "").strip().lower()
    if worldline_id in GLOBAL_WORLDLINE_IDS:
        worldline_id = ""
    version_scope = str(item.get("version_scope") or "").strip().lower()
    if version_scope == "unknown":
        version_scope = ""
    return setting_scope, story_id, worldline_id, version_scope


def entity_id_for(entity_type: str, name: str, domain: tuple[str, str, str, str]) -> str:
    """Deterministic entity_id. Stable across runs so re-backfill is idempotent."""
    identity = "|".join((entity_type, normalize_name(name), *domain))
    digest = sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"entity_{digest}"


def entity_type_for_category(category: Any) -> str | None:
    return CATEGORY_TO_ENTITY_TYPE.get(str(category or "").strip())


def merge_policy_for(fact_key: str | None) -> str:
    if not fact_key:
        return "append"
    return FACT_MERGE_POLICY.get(str(fact_key).strip(), "append")


def supersession_enabled(fact_key: str | None) -> bool:
    """Whether a fact_key participates in chapter-scoped supersession."""
    if not fact_key:
        return False
    key = str(fact_key).strip()
    if key in _NO_SUPERSESSION_FACT_KEYS:
        return False
    return merge_policy_for(key) == "replace"
