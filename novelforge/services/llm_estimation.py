"""Application service for calibrated execution preflight estimates."""
from __future__ import annotations

import logging

from novelforge.domain.llm_preflight import build_preflight_estimate, build_stage_estimate
from novelforge.services.llm_usage import get_llm_usage_calibration
from novelforge.services.memory import get_active_llm_profile


LOGGER = logging.getLogger("novelforge.llm_estimation")


def load_stage_calibration(
    operation: str,
    *,
    agent_role: str = "",
    endpoint_type: str = "chat",
    profile: dict | None = None,
) -> dict:
    """Load a matching history cohort without letting observability break UI."""

    active_profile = dict(profile or get_active_llm_profile())
    selected_model = (
        active_profile.get("embedding_model_name")
        if endpoint_type == "embedding"
        else active_profile.get("model_name")
    )
    model_name = str(selected_model or "")
    filters = {
        "operation": str(operation or "unattributed"),
        "profile_id": str(active_profile.get("id") or ""),
        "endpoint_type": str(endpoint_type or "chat"),
    }
    if agent_role:
        filters["agent_role"] = str(agent_role)
    if model_name:
        filters["model_name"] = model_name
    try:
        return get_llm_usage_calibration(**filters)
    except Exception as exc:
        LOGGER.warning("Failed to load LLM estimate calibration: %s", exc, exc_info=True)
        return {"sample_count": 0}


def build_calibrated_preflight(
    stage_specs: list[dict],
    *,
    profile: dict | None = None,
    estimate_kind: str = "llm_workflow",
    external_calls: list[dict] | None = None,
    assumptions: list[str] | None = None,
) -> dict:
    """Resolve history cohorts and aggregate stage specifications."""

    active_profile = dict(profile or get_active_llm_profile())
    stages: list[dict] = []
    for raw_spec in stage_specs:
        spec = dict(raw_spec or {})
        operation = str(spec.get("operation") or "unattributed")
        agent_role = str(spec.get("agent_role") or "")
        endpoint_type = str(spec.get("endpoint_type") or "chat")
        calibration = spec.pop("calibration", None)
        if calibration is None:
            calibration = load_stage_calibration(
                operation,
                agent_role=agent_role,
                endpoint_type=endpoint_type,
                profile=active_profile,
            )
        stages.append(build_stage_estimate(calibration=calibration, **spec))
    return build_preflight_estimate(
        stages,
        profile=active_profile,
        estimate_kind=estimate_kind,
        external_calls=external_calls,
        assumptions=assumptions,
    )
