"""Story-level creation mode rules shared by API, workflows and UI adapters."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class CreationMode(StrEnum):
    """The two deliberately different authoring surfaces."""

    PLANNED = "planned"
    CONVERSATIONAL = "conversational"


class PlanningContextPolicy(StrEnum):
    """Whether planned artifacts participate in conversational context."""

    MODE_DEFAULT = "mode_default"
    INCLUDE = "include"
    EXCLUDE = "exclude"


DEFAULT_CREATION_MODE = CreationMode.PLANNED.value
DEFAULT_PLANNING_CONTEXT_POLICY = PlanningContextPolicy.MODE_DEFAULT.value


def normalize_creation_mode(value: Any, *, default: str = DEFAULT_CREATION_MODE) -> str:
    """Return a persisted mode or a safe compatibility default."""

    candidate = str(value or "").strip().lower()
    if candidate in {item.value for item in CreationMode}:
        return candidate
    fallback = str(default or DEFAULT_CREATION_MODE).strip().lower()
    return fallback if fallback in {item.value for item in CreationMode} else DEFAULT_CREATION_MODE


def normalize_planning_context_policy(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {item.value for item in PlanningContextPolicy}:
        return candidate
    return DEFAULT_PLANNING_CONTEXT_POLICY


def should_include_planning_context(
    creation_mode: Any,
    planning_context_policy: Any = DEFAULT_PLANNING_CONTEXT_POLICY,
) -> bool:
    """Resolve the effective planning visibility without involving persistence."""

    mode = normalize_creation_mode(creation_mode)
    policy = normalize_planning_context_policy(planning_context_policy)
    if policy == PlanningContextPolicy.INCLUDE.value:
        return True
    if policy == PlanningContextPolicy.EXCLUDE.value:
        return False
    return mode == CreationMode.PLANNED.value


def normalize_story_creation_settings(payload: dict[str, Any] | None) -> dict[str, str]:
    """Normalize the small story-level routing settings carried by API DTOs."""

    source = payload if isinstance(payload, dict) else {}
    return {
        "creation_mode": normalize_creation_mode(source.get("creation_mode")),
        "planning_context_policy": normalize_planning_context_policy(
            source.get("planning_context_policy")
        ),
    }
