"""Interactive writing: fragment acceptance, extraction and compilation."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime, timezone
from uuid import uuid4

from novelforge.workflows.context_assembly import (
    assemble_generation_context,
    ensure_context_budget,
    render_context_for_prompt,
)
from novelforge.core.llm import call_llm
from novelforge.core.llm_usage import llm_usage_scope
from novelforge.core.token_estimation import estimate_chat_input_tokens, estimate_text_tokens
from novelforge.domain.llm_preflight import parse_requested_output_range
from novelforge.services.llm_estimation import build_calibrated_preflight
from novelforge.services.automatic_configuration import (
    configure_operation_automatically,
    estimate_project_source_chars,
)
from novelforge.services.capabilities import require_operation_capabilities
from novelforge.services.memory import (
    accept_creative_fragment,
    begin_creative_turn,
    claim_turn_creative_attachments,
    release_turn_creative_attachments,
    complete_creative_turn,
    consume_context_directives,
    create_creative_session,
    get_story_creation_mode,
    fail_creative_turn,
    finalize_creative_session,
    load_creative_profile,
    load_creative_session_bundle,
    load_entity_master_rows,
    load_story_branch,
    load_pending_knowledge_items,
    load_chapter,
    queue_pending_knowledge_items,
    save_chapter,
    save_generation_context_snapshot,
    select_creative_fragment_variant,
    update_creative_fragment,
    update_creative_session,
)
from novelforge.core.prompts import (
    compile_creative_fragments_prompt,
    creative_fragment_prompt,
    creative_session_summary_prompt,
)
from novelforge.core.schemas import ChapterWritingGuidance
from novelforge.services.memory import retrieval_sources_path
from novelforge.workflows.cancellation import raise_if_cancelled


LOGGER = logging.getLogger("novelforge.interactive_writing")
RECENT_FRAGMENT_CONTEXT_CHARS = 9_000
SUMMARY_REFRESH_THRESHOLD_CHARS = 12_000
SUMMARY_BATCH_MIN_FRAGMENTS = 3


_ENTITY_TYPE_BY_CATEGORY = {
    "characters": "character",
    "items": "item",
    "abilities": "ability",
    "locations": "location",
    "organizations": "organization",
}

_RELATIONSHIP_ENDPOINT_KEYS = {
    "source": (
        "source", "from", "subject", "character_a", "person_a", "角色A", "人物A",
    ),
    "target": (
        "target", "to", "object", "character_b", "person_b", "角色B", "人物B",
    ),
}
_NEW_ENTITY_CANDIDATE_ID = "__new_entity__"


def _relationship_endpoint_name(item: dict, endpoint: str) -> str:
    details = item.get("details") if isinstance(item.get("details"), dict) else {}
    typed_data = item.get("typed_data") if isinstance(item.get("typed_data"), dict) else {}
    for key in _RELATIONSHIP_ENDPOINT_KEYS.get(endpoint, ()):
        value = item.get(key) or typed_data.get(key) or details.get(key)
        if str(value or "").strip():
            return str(value).strip()
    return ""


def _relationship_candidate_options(
    candidates_by_name: dict[tuple[str, str], list[dict]],
    name: str,
) -> list[dict]:
    from storage.repositories.entity_identity import normalize_name

    normalized = normalize_name(name)
    if not normalized:
        return []
    options: list[dict] = []
    seen: set[str] = set()
    for (entity_type, candidate_name), rows in candidates_by_name.items():
        if candidate_name != normalized:
            continue
        for row in rows:
            entity_id = str(row.get("entity_id") or "").strip()
            if not entity_id or entity_id in seen:
                continue
            seen.add(entity_id)
            options.append({**row, "entity_type": str(row.get("entity_type") or entity_type)})
    return options


def _new_relationship_entity_option(item: dict, name: str) -> dict:
    return {
        "entity_id": _NEW_ENTITY_CANDIDATE_ID,
        "canonical_name": name,
        "entity_type": "character",
        "worldline_id": str(item.get("worldline_id") or "").strip(),
        "worldline_label": str(item.get("worldline_label") or "").strip(),
        "source_title": str(item.get("source_title") or "").strip(),
        "version_scope": str(item.get("version_scope") or "project_main").strip() or "project_main",
        "aliases": [],
        "facts": [],
        "is_new": True,
        "label": "新实体（在当前世界线创建）",
    }


def _set_relationship_endpoint_mapping(item: dict, endpoint: str, selected: dict, *, new_entity: bool = False) -> None:
    if new_entity or str(selected.get("entity_id") or "") == _NEW_ENTITY_CANDIDATE_ID:
        item[f"{endpoint}_origin_entity_id"] = ""
        item[f"{endpoint}_origin_canonical_name"] = str(selected.get("canonical_name") or "").strip()
        item[f"{endpoint}_origin_entity_type"] = str(selected.get("entity_type") or "character").strip() or "character"
        item[f"{endpoint}_origin_worldline_id"] = str(selected.get("worldline_id") or "").strip()
        item[f"{endpoint}_origin_worldline_label"] = str(selected.get("worldline_label") or "").strip()
        item[f"{endpoint}_origin_source_title"] = str(selected.get("source_title") or "").strip()
        item[f"{endpoint}_origin_version_scope"] = str(selected.get("version_scope") or "project_main").strip() or "project_main"
        item[f"{endpoint}_origin_knowledge_id"] = ""
        item[f"{endpoint}_resolution_status"] = "new"
        return
    item[f"{endpoint}_origin_entity_id"] = str(selected.get("entity_id") or "").strip()
    item[f"{endpoint}_origin_canonical_name"] = str(selected.get("canonical_name") or "").strip()
    item[f"{endpoint}_origin_entity_type"] = str(selected.get("entity_type") or "character").strip() or "character"
    item[f"{endpoint}_origin_worldline_id"] = str(selected.get("worldline_id") or "").strip()
    item[f"{endpoint}_origin_worldline_label"] = str(selected.get("worldline_label") or "").strip()
    item[f"{endpoint}_origin_source_title"] = str(selected.get("source_title") or "").strip()
    item[f"{endpoint}_origin_version_scope"] = str(selected.get("version_scope") or "project_main").strip() or "project_main"
    facts = selected.get("facts") if isinstance(selected.get("facts"), list) else []
    knowledge_ids = [str(fact.get("knowledge_id") or "").strip() for fact in facts if isinstance(fact, dict)]
    item[f"{endpoint}_origin_knowledge_id"] = next((value for value in knowledge_ids if value), "")
    item[f"{endpoint}_resolution_status"] = "resolved"


def _relationship_endpoint_is_resolved(item: dict, endpoint: str) -> bool:
    status = str(item.get(f"{endpoint}_resolution_status") or "").strip()
    canonical = str(item.get(f"{endpoint}_origin_canonical_name") or "").strip()
    return bool(canonical and (status == "new" or str(item.get(f"{endpoint}_origin_entity_id") or "").strip()))


def _attach_relationship_source_mapping(
    item: dict,
    candidates_by_name: dict[tuple[str, str], list[dict]],
    requested_mappings: dict[str, dict] | None = None,
) -> dict:
    """Resolve both relation endpoints against the frozen entity candidate set.

    Relation endpoints have separate origins. A scalar ``target_origin_entity_id``
    cannot represent a relationship, so the pending row records which endpoint
    needs a choice and keeps both endpoint option lists for the next choice.
    """
    normalized = dict(item)
    requested_mappings = requested_mappings or {}
    options_by_endpoint: dict[str, list[dict]] = {}

    for endpoint in ("source", "target"):
        name = _relationship_endpoint_name(normalized, endpoint)
        if not name:
            options_by_endpoint[endpoint] = []
            continue
        if endpoint not in options_by_endpoint:
            options = _relationship_candidate_options(candidates_by_name, name)
            options_by_endpoint[endpoint] = options or [_new_relationship_entity_option(normalized, name)]
        options = options_by_endpoint[endpoint]
        if _relationship_endpoint_is_resolved(normalized, endpoint):
            continue
        requested = requested_mappings.get(endpoint) if isinstance(requested_mappings.get(endpoint), dict) else {}
        requested_id = str(requested.get("entity_id") or "").strip()
        if requested_id:
            selected = next(
                (row for row in options if str(row.get("entity_id") or "") == requested_id),
                None,
            )
            if selected is not None:
                _set_relationship_endpoint_mapping(normalized, endpoint, selected)
                continue
        real_options = [row for row in options if str(row.get("entity_id") or "") != _NEW_ENTITY_CANDIDATE_ID]
        if len(real_options) == 1:
            _set_relationship_endpoint_mapping(normalized, endpoint, real_options[0])

    normalized["entity_resolution_options_by_endpoint"] = options_by_endpoint
    unresolved = next(
        (endpoint for endpoint in ("source", "target") if not _relationship_endpoint_is_resolved(normalized, endpoint)),
        None,
    )
    if unresolved:
        unresolved_name = _relationship_endpoint_name(normalized, unresolved)
        options = options_by_endpoint.get(unresolved) or (
            [_new_relationship_entity_option(normalized, unresolved_name)] if unresolved_name else []
        )
        missing_name = not bool(unresolved_name)
        normalized.update({
            "entity_resolution_status": "pending_confirmation",
            "entity_resolution_endpoint": unresolved,
            "entity_resolution_reason": (
                "关系端点名称缺失，无法提炼关系。"
                if missing_name
                else "同名关系端点来源不唯一，请选择来源实体。"
                if len([row for row in options if not row.get("is_new")]) > 1
                else "关系端点来源未知，请选择现有来源或新实体。"
            ),
            "entity_resolution_candidates": [str(row.get("entity_id") or "") for row in options],
            "entity_resolution_options": options,
        })
        return normalized
    normalized.update({
        "entity_resolution_status": "resolved",
        "entity_resolution_endpoint": "",
        "entity_resolution_reason": "",
        "entity_resolution_candidates": [],
        "entity_resolution_options": [],
    })
    return normalized


def _source_entity_candidates(
    project_name: str,
    story_id: str,
    branch_id: str | None,
    snapshot_items: list[dict] | None = None,
) -> dict[tuple[str, str], list[dict]]:
    """Return the entity identities visible to this extraction frontier.

    Extraction is asynchronous, so the candidate set must be tied to the
    session branch/checkpoint rather than the mutable profile or a global
    name-only lookup. Checkpoint payloads are preferred because they retain
    inherited source identities; entity masters are a compatibility fallback
    for older checkpoints that predate the entity projection.
    """
    rows: list[dict] = []
    if snapshot_items is None:
        from novelforge.services import memory
        snapshot_items = memory.list_visible_story_knowledge(project_name, story_id, branch_id)
    if snapshot_items is not None:
        from storage.repositories.knowledge import filter_superseded_visible_items
        snapshot_items = filter_superseded_visible_items(snapshot_items)
        physical_origins: dict[str, str] = {}
        for raw in snapshot_items:
            if not isinstance(raw, dict):
                continue
            frozen = {**(raw.get("payload") if isinstance(raw.get("payload"), dict) else {}), **raw}
            content = frozen.get("content_json")
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except (TypeError, ValueError):
                    content = {}
            frozen = {**(content if isinstance(content, dict) else {}), **frozen}
            primary = frozen.get("entity") if isinstance(frozen.get("entity"), dict) else {}
            physical = str(frozen.get("entity_id") or primary.get("entity_id") or "")
            origin = str(frozen.get("origin_entity_id") or frozen.get("target_origin_entity_id") or "")
            if physical and origin and frozen.get("category") != "relationships":
                physical_origins[physical] = origin
            for edge in frozen.get("entity_relations") or frozen.get("edges") or []:
                if not isinstance(edge, dict):
                    continue
                for endpoint in ("source", "target"):
                    physical = str(edge.get(f"{endpoint}_node_id") or "")
                    origin = str(frozen.get(f"{endpoint}_origin_entity_id") or "")
                    if physical and origin:
                        physical_origins[physical] = origin
        for raw in snapshot_items:
            if not isinstance(raw, dict):
                continue
            payload = {**(raw.get("payload") if isinstance(raw.get("payload"), dict) else {}), **raw}
            if not isinstance(payload, dict):
                continue
            content = payload.get("content_json")
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except (TypeError, ValueError):
                    content = {}
            payload = {**(content if isinstance(content, dict) else {}), **payload}
            entity = payload.get("entity") if isinstance(payload.get("entity"), dict) else {}
            related_entities = payload.get("related_entities")
            entity_rows: list[dict] = [entity]
            if isinstance(related_entities, list):
                entity_rows.extend(row for row in related_entities if isinstance(row, dict))
            for entity_index, entity_row in enumerate(entity_rows):
                primary_entity = entity_index == 0
                physical_id = str(entity_row.get("entity_id") or "").strip()
                if not primary_entity and physical_id == str(entity.get("entity_id") or ""):
                    continue
                origin_id = str(physical_origins.get(physical_id) or entity_row.get("origin_entity_id") or "").strip()
                if primary_entity and payload.get("category") != "relationships":
                    origin_id = str(payload.get("origin_entity_id") or payload.get("target_origin_entity_id") or origin_id or "").strip()
                elif not primary_entity:
                    relations = payload.get("entity_relations") or payload.get("edges") or []
                    for relation in relations if isinstance(relations, list) else []:
                        if not isinstance(relation, dict):
                            continue
                        for endpoint in ("source", "target"):
                            if physical_id and physical_id == str(relation.get(f"{endpoint}_node_id") or ""):
                                origin_id = str(payload.get(f"{endpoint}_origin_entity_id") or origin_id or "").strip()
                entity_id = str(
                    origin_id
                    or physical_id
                    or payload.get("entity_id")
                    or ""
                ).strip()
                canonical = str(
                    entity_row.get("canonical_name")
                    or entity_row.get("display_name")
                    or payload.get("canonical_name")
                    or payload.get("entity_canonical_name")
                    or payload.get("name")
                    or ""
                ).strip()
                if not entity_id or not canonical:
                    continue
                aliases = entity_row.get("aliases")
                if not isinstance(aliases, list):
                    aliases = entity_row.get("entity_aliases")
                if not isinstance(aliases, list):
                    aliases = payload.get("entity_aliases") if primary_entity else []
                rows.append({
                    "entity_id": entity_id,
                    "canonical_name": canonical,
                    "entity_type": str(
                        entity_row.get("entity_type")
                        or payload.get("entity_type")
                        or ""
                    ),
                    "worldline_id": str(
                        entity_row.get("worldline_id")
                        or payload.get("worldline_id")
                        or ""
                    ),
                    "worldline_label": str(
                        entity_row.get("worldline_label")
                        or entity_row.get("worldline_name")
                        or payload.get("worldline_label")
                        or payload.get("worldline_name")
                        or ""
                    ),
                    "source_title": str(
                        entity_row.get("source_title")
                        or payload.get("source_title")
                        or payload.get("source_name")
                        or ""
                    ),
                    "aliases": list(aliases or []),
                    "version_scope": str(
                        entity_row.get("version_scope")
                        or payload.get("version_scope")
                        or "project_main"
                    ),
                    "knowledge_id": str(payload.get("knowledge_id") or payload.get("id") or ""),
                    "fact_key": str(payload.get("fact_key") or payload.get("setting_field") or "") if primary_entity else "",
                })
    result: dict[tuple[str, str], list[dict]] = {}
    seen: set[tuple[str, str]] = set()
    from storage.repositories.entity_identity import normalize_name

    for row in rows:
        if not isinstance(row, dict):
            continue
        entity_id = str(row.get("entity_id") or "").strip()
        entity_type = str(row.get("entity_type") or "").strip()
        canonical = str(row.get("canonical_name") or row.get("name") or "").strip()
        if not entity_id or not entity_type or not canonical:
            continue
        aliases = row.get("aliases")
        if not isinstance(aliases, list):
            aliases = []
        for name in [canonical, *aliases]:
            normalized = normalize_name(name)
            if not normalized:
                continue
            key = (entity_type, normalized)
            unique = (key, entity_id)
            if unique not in seen:
                seen.add(unique)
                result.setdefault(key, []).append({
                "entity_id": entity_id,
                "canonical_name": canonical,
                "entity_type": entity_type,
                "worldline_id": str(row.get("worldline_id") or ""),
                "worldline_label": str(row.get("worldline_label") or ""),
                "source_title": str(row.get("source_title") or ""),
                "version_scope": str(row.get("version_scope") or "project_main"),
                "aliases": list(aliases),
                "facts": [],
                })
            target = next(item for item in result[key] if item["entity_id"] == entity_id)
            target["facts"].append({"knowledge_id": row.get("knowledge_id"), "fact_key": row.get("fact_key")})
    return result


def _attach_source_entity_mapping(
    project_name: str,
    story_id: str,
    branch_id: str | None,
    item: dict,
    candidates_by_name: dict[tuple[str, str], list[dict]],
) -> dict:
    """Attach a verified origin entity or mark an ambiguous item pending.

    A creative fact remains a new story/branch fact. ``target_origin_entity_id``
    records which inherited/source identity it derives from; it is never used
    as the new physical entity ID. When two source worlds share a name, the
    item must remain pending until the user selects a target explicitly.
    """
    from storage.repositories.entity_identity import normalize_name

    normalized = dict(item)
    category = str(normalized.get("category") or "").strip()
    details = normalized.get("details") if isinstance(normalized.get("details"), dict) else {}
    typed_data = normalized.get("typed_data") if isinstance(normalized.get("typed_data"), dict) else {}
    requested = str(
        normalized.get("target_origin_entity_id")
        or normalized.get("origin_entity_id")
        or details.get("target_origin_entity_id")
        or typed_data.get("target_origin_entity_id")
        or ""
    ).strip()
    requested_relationship_mappings = {
        endpoint: {
            "entity_id": normalized.get(f"{endpoint}_origin_entity_id")
            or details.get(f"{endpoint}_origin_entity_id")
            or typed_data.get(f"{endpoint}_origin_entity_id")
            or "",
        }
        for endpoint in ("source", "target")
    }
    # These aliases are model output, not a selection from the frozen
    # candidate set. Strip them before persistence so the repository cannot
    # use a forged nested identity or a bare entity_id as a fallback. The
    # ordinary source/target names remain intact, as do explicit
    # *_origin_entity_id requests which are validated below.
    for key in ("source_entity_id", "target_entity_id"):
        normalized.pop(key, None)
    for key in ("source_origin", "target_origin"):
        if isinstance(normalized.get(key), dict):
            normalized.pop(key, None)
    for container_key in ("details", "typed_data"):
        container = normalized.get(container_key)
        if not isinstance(container, dict):
            continue
        cleaned = dict(container)
        for key in ("source_entity_id", "target_entity_id", "source_origin", "target_origin"):
            if key.endswith("_origin") and not isinstance(cleaned.get(key), dict):
                continue
            cleaned.pop(key, None)
        normalized[container_key] = cleaned
    # These fields are server-owned resolution state. A model may request an
    # origin ID, but it may not carry a resolved status/options/canonical tuple
    # into the branch without matching the frozen candidate set below.
    for key in (
        "entity_resolution_status", "entity_resolution_endpoint", "entity_resolution_reason",
        "entity_resolution_candidates", "entity_resolution_options", "entity_resolution_options_by_endpoint",
        "origin_entity_id", "origin_knowledge_id", "origin_worldline_id",
        "target_origin_entity_id", "source_origin_entity_id",
        "source_entity_id", "target_entity_id",
        "source_origin_canonical_name", "target_origin_canonical_name",
        "source_origin_entity_type", "target_origin_entity_type",
        "source_origin_worldline_id", "target_origin_worldline_id",
        "source_origin_worldline_label", "target_origin_worldline_label",
        "source_origin_source_title", "target_origin_source_title",
        "source_origin_version_scope", "target_origin_version_scope",
        "source_origin_knowledge_id", "target_origin_knowledge_id",
        "source_resolution_status", "target_resolution_status",
    ):
        normalized.pop(key, None)
    # Reference fields are graph targets too. Keep their text, but derive
    # graph identities only from this extraction's frozen candidate set.
    from storage.repositories.knowledge import _REFERENCE_FIELD_SPECS
    normalized.pop("reference_origin_entities", None)
    for container_key in ("details", "typed_data"):
        if isinstance(normalized.get(container_key), dict):
            normalized[container_key] = dict(normalized[container_key])
            normalized[container_key].pop("reference_origin_entities", None)
    verified_references: dict[str, list[dict | None]] = {}
    reference_typed = normalized.get("typed_data") if isinstance(normalized.get("typed_data"), dict) else {}
    reference_details = normalized.get("details") if isinstance(normalized.get("details"), dict) else {}
    for field, (_, target_type) in _REFERENCE_FIELD_SPECS.items():
        values = normalized.get(field) or reference_typed.get(field) or reference_details.get(field)
        if not values:
            continue
        values = values if isinstance(values, list) else [values]
        names = [str(value.get("name") or value.get("canonical_name") or "").strip() if isinstance(value, dict) else str(value or "").strip() for value in values]
        normalized[field] = names
        mappings: list[dict | None] = []
        for name in names:
            options = candidates_by_name.get((target_type, normalize_name(name)), [])
            selected = options[0] if len(options) == 1 else None
            mappings.append({**selected, "origin_entity_id": selected["entity_id"]} if selected else None)
        verified_references[field] = mappings
    if verified_references:
        normalized["reference_origin_entities"] = verified_references
    if category == "relationships":
        return _attach_relationship_source_mapping(
            normalized,
            candidates_by_name,
            requested_mappings=requested_relationship_mappings,
        )
    entity_type = _ENTITY_TYPE_BY_CATEGORY.get(category)
    name = str(normalized.get("name") or "").strip()
    if not entity_type or not name:
        return normalized
    candidates = list(candidates_by_name.get((entity_type, normalize_name(name)), []))
    if requested:
        selected = [row for row in candidates if row["entity_id"] == requested]
        if not candidates:
            candidates = [{
                **_new_relationship_entity_option(normalized, name),
                "entity_type": entity_type,
            }]
            selected = [row for row in candidates if row["entity_id"] == requested]
        if requested == _NEW_ENTITY_CANDIDATE_ID:
            # The sentinel is valid only when it was generated by this
            # server-side candidate set (or loaded from a saved pending row).
            # A model cannot bypass a real ambiguity by self-reporting it.
            selected = [
                row for row in candidates
                if str(row.get("entity_id") or "") == _NEW_ENTITY_CANDIDATE_ID
            ]
        if selected:
            if str(selected[0].get("entity_id") or "") == _NEW_ENTITY_CANDIDATE_ID:
                normalized.update({
                    "entity_resolution_status": "new",
                    "entity_resolution_reason": "用户选择在当前世界线创建新实体",
                    "entity_resolution_candidates": [],
                    "entity_resolution_options": [],
                    "target_origin_entity_id": "",
                    "origin_entity_id": "",
                    "origin_knowledge_id": "",
                })
                return normalized
            candidates = selected
        else:
            normalized.update({
                "entity_resolution_status": "pending_confirmation",
                "entity_resolution_reason": "提炼声明的来源实体不在当前世界线可见集",
                "entity_resolution_candidates": [row["entity_id"] for row in candidates],
                "entity_resolution_options": candidates,
                "target_origin_entity_id": "",
                "origin_entity_id": "",
                "origin_knowledge_id": "",
            })
            return normalized
    unique_ids = {row["entity_id"] for row in candidates}
    if len(unique_ids) > 1:
        normalized.update({
            "entity_resolution_status": "pending_confirmation",
            "entity_resolution_reason": "同名实体来源不唯一，需明确 target_origin_entity_id",
            "entity_resolution_candidates": sorted(unique_ids),
            "entity_resolution_options": candidates,
            "target_origin_entity_id": "",
            "origin_entity_id": "",
            "origin_knowledge_id": "",
        })
        return normalized
    if len(unique_ids) == 1:
        selected = candidates[0]
        normalized.update({
            "entity_resolution_status": "resolved",
            "target_origin_entity_id": selected["entity_id"],
            "origin_entity_id": selected["entity_id"],
            "origin_worldline_id": selected.get("worldline_id") or "",
            "worldline_id": selected.get("worldline_id") or "",
            "version_scope": selected.get("version_scope") or "project_main",
            "name": selected["canonical_name"],
            "aliases": list(selected.get("aliases") or []),
        })
        fact_key = str(normalized.get("setting_field") or normalized.get("fact_key") or "")
        matching = {str(fact.get("knowledge_id") or "") for fact in selected.get("facts", []) if fact_key and fact.get("fact_key") == fact_key} - {""}
        if len(matching) == 1:
            normalized["origin_knowledge_id"] = next(iter(matching))
    else:
        normalized.setdefault("entity_resolution_status", "new")
    return normalized


def resolve_fragment_entity_candidate(project_name: str, story_id: str, branch_id: str | None, pending_id: str, target_entity_id: str) -> dict:
    """Select a frozen source identity without rerunning extraction."""
    from novelforge.services import memory
    from storage.repositories.branches import load_branch_for_story
    from storage.repositories.entity_identity import normalize_name

    selected_branch = branch_id or memory.default_branch_id(story_id)
    with memory.open_project_db(memory.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        branch = load_branch_for_story(conn, story_id, selected_branch)
        if branch.get("status") != "active":
            raise ValueError("已归档世界线不能修改待确认资料。")
        candidate = next((item for item in memory.load_pending_knowledge_rows(conn) if str(item.get("pending_id") or "") == pending_id), None)
        if not candidate or candidate.get("story_id") != story_id or candidate.get("branch_id") != selected_branch:
            raise ValueError("待确认资料不属于当前故事世界线。")
        options = [item for item in candidate.get("entity_resolution_options", []) if isinstance(item, dict)]
        if target_entity_id not in {str(item.get("entity_id") or "") for item in options}:
            raise ValueError("所选来源不在该次提炼保存的候选范围内。")
        if str(candidate.get("category") or "").strip() == "relationships":
            endpoint = str(candidate.get("entity_resolution_endpoint") or "").strip()
            if endpoint not in {"source", "target"}:
                raise ValueError("关系资料缺少待确认的端点。")
            selected = next(item for item in options if str(item.get("entity_id") or "") == target_entity_id)
            saved = dict(candidate)
            _set_relationship_endpoint_mapping(
                saved,
                endpoint,
                selected,
                new_entity=target_entity_id == _NEW_ENTITY_CANDIDATE_ID,
            )
            options_by_endpoint = saved.get("entity_resolution_options_by_endpoint")
            if not isinstance(options_by_endpoint, dict):
                options_by_endpoint = {endpoint: options}
            unresolved = next(
                (
                    other
                    for other in ("source", "target")
                    if not _relationship_endpoint_is_resolved(saved, other)
                ),
                None,
            )
            if unresolved:
                next_options = options_by_endpoint.get(unresolved)
                unresolved_name = _relationship_endpoint_name(saved, unresolved)
                if not isinstance(next_options, list) or not next_options:
                    next_options = (
                        [_new_relationship_entity_option(saved, unresolved_name)]
                        if unresolved_name else []
                    )
                saved.update({
                    "entity_resolution_status": "pending_confirmation",
                    "entity_resolution_endpoint": unresolved,
                    "entity_resolution_reason": (
                        "关系端点名称缺失，无法提炼关系。"
                        if not unresolved_name
                        else
                        "同名关系端点来源不唯一，请选择来源实体。"
                        if len([row for row in next_options if not row.get("is_new")]) > 1
                        else "关系端点来源未知，请选择现有来源或新实体。"
                    ),
                    "entity_resolution_candidates": [str(row.get("entity_id") or "") for row in next_options],
                    "entity_resolution_options": next_options,
                })
            else:
                saved.update({
                    "entity_resolution_status": "resolved",
                    "entity_resolution_endpoint": "",
                    "entity_resolution_reason": "用户已完成关系两端来源选择",
                    "entity_resolution_candidates": [],
                    "entity_resolution_options": [],
                })
            memory.upsert_pending_knowledge_items(conn, [saved])
            conn.commit()
            return saved
        key = (_ENTITY_TYPE_BY_CATEGORY.get(candidate.get("category")), normalize_name(candidate.get("name")))
        saved = _attach_source_entity_mapping(project_name, story_id, selected_branch, {**candidate, "target_origin_entity_id": target_entity_id}, {key: options})
        # The pending row already holds server-verified reference targets from
        # the full frozen set; resolving this one entity must not erase them.
        if isinstance(candidate.get("reference_origin_entities"), dict):
            saved["reference_origin_entities"] = candidate["reference_origin_entities"]
        saved["entity_resolution_reason"] = "用户已明确选择资料来源"
        memory.upsert_pending_knowledge_items(conn, [saved])
        conn.commit()
    return saved



from novelforge.workflows import interactive_writing as _iw

def accept_writing_fragment(
    project_name: str,
    story_id: str,
    session_id: str,
    fragment_id: str,
    *,
    extract_if_enabled: bool = True,
    branch_id: str | None = None,
) -> dict:
    bundle = _iw._bundle_or_raise(project_name, story_id, session_id)
    from novelforge.services.memory import resolve_creative_session_branch
    branch_id = resolve_creative_session_branch(project_name, story_id, session_id, branch_id)
    fragment = accept_creative_fragment(
        project_name,
        session_id,
        fragment_id,
        story_id=story_id,
    )
    extraction: dict = {}
    warnings: list[str] = []
    if (
        extract_if_enabled
        and bundle.get("session", {}).get("auto_extract_mode") == "on_accept"
    ):
        try:
            extraction = extract_fragment_knowledge(
                project_name,
                story_id,
                session_id,
                fragment_id,
                branch_id=branch_id or str(bundle.get("session", {}).get("branch_id") or "") or None,
            )
        except Exception as exc:
            warnings.append(f"片段已接受，但自动设定提炼失败：{exc}")
    summary_warning = maybe_refresh_session_summary(
        project_name,
        story_id,
        session_id,
        branch_id=branch_id,
    )
    if summary_warning:
        warnings.append(summary_warning)
    return {
        "fragment": fragment,
        "extraction": extraction,
        "warnings": warnings,
    }


def select_writing_fragment_variant(
    project_name: str,
    story_id: str,
    session_id: str,
    fragment_id: str,
    branch_id: str | None = None,
) -> dict:
    from novelforge.services.memory import resolve_creative_session_branch
    resolve_creative_session_branch(project_name, story_id, session_id, branch_id)
    return select_creative_fragment_variant(
        project_name,
        session_id,
        fragment_id,
        story_id=story_id,
    )


def maybe_refresh_session_summary(
    project_name: str,
    story_id: str,
    session_id: str,
    *,
    force: bool = False,
    branch_id: str | None = None,
) -> str:
    bundle = _iw._bundle_or_raise(project_name, story_id, session_id)
    session = bundle.get("session", {}) or {}
    accepted, pending, pending_text, total_text = _iw._summary_refresh_material(bundle)
    if not accepted:
        return ""
    if not force and (
        len(total_text) < SUMMARY_REFRESH_THRESHOLD_CHARS
        or len(pending) < SUMMARY_BATCH_MIN_FRAGMENTS
    ):
        return ""
    if not pending_text.strip():
        return ""
    try:
        with llm_usage_scope(
            project_name=project_name,
            story_id=story_id,
            task_id=session_id,
            operation="creative.summary",
            agent_role="summarizer",
        ):
            summary = call_llm(
                creative_session_summary_prompt(
                    str(session.get("rolling_summary") or ""),
                    pending_text,
                ),
                temperature=0.2,
            )
        update_creative_session(
            project_name,
            session_id,
            {
                "rolling_summary": str(summary or "").strip(),
                "summary_fragment_id": str(accepted[-1].get("fragment_id") or ""),
            },
            story_id=story_id,
        )
        return ""
    except Exception as exc:
        LOGGER.warning(
            "Failed to refresh creative-session summary: session=%s error=%s",
            session_id,
            exc,
        )
        return f"片段已保存，但会话滚动摘要更新失败：{exc}"


def extract_fragment_knowledge(
    project_name: str,
    story_id: str,
    session_id: str,
    fragment_id: str,
    *,
    stream_callback=None,
    branch_id: str | None = None,
) -> dict:
    bundle = _iw._bundle_or_raise(project_name, story_id, session_id)
    session = bundle.get("session", {}) or {}
    from novelforge.services import memory
    owner_branch = str(session.get("branch_id") or memory.default_branch_id(story_id))
    if branch_id and str(branch_id) != owner_branch:
        raise ValueError("片段提炼的世界线与会话归属不一致。")
    branch_id = owner_branch
    if str(session.get("status") or "") == "archived":
        raise ValueError("已归档的创作会话不能提炼知识。")
    fragments = _iw._fragment_map(bundle)
    fragment = fragments.get(str(fragment_id or ""))
    if fragment is None:
        raise ValueError("创作片段不存在。")
    if str(fragment.get("status") or "") not in {"accepted", "finalized"}:
        raise ValueError("只有已接受片段可以提炼知识。")
    profile = memory.load_effective_story_branch_configuration(project_name, story_id, branch_id).get("profile") or {}
    snapshot_items = None
    # Pin source identities and narrative configuration before the model call.
    # A late F1 extraction must not use F2's newly added entities or settings.
    with memory.open_project_db(memory.project_path(project_name).resolve()) as conn:
        checkpoint = conn.execute(
            "SELECT snapshot_manifest_json FROM branch_checkpoints WHERE branch_id=? AND frontier_fragment_id=? ORDER BY revision DESC LIMIT 1",
            (branch_id, fragment_id),
        ).fetchone()
        if checkpoint:
            manifest = json.loads(checkpoint[0])
            snapshot_items = list(manifest.get("knowledge") or [])
            profile = (manifest.get("configuration") or {}).get("profile") or profile
    entity_candidates = _source_entity_candidates(project_name, story_id, branch_id, snapshot_items)
    worldline_id = str(profile.get("worldline_id") or session.get("worldline_id") or "main")
    worldline_label = str(profile.get("worldline_label") or worldline_id)
    update_creative_fragment(
        project_name,
        fragment_id,
        {"extraction_status": "running"},
        story_id=story_id,
    )
    try:
        from novelforge.workflows.skills import extract_reference_knowledge

        extraction_step = extract_reference_knowledge(
            project_name,
            f"自由创作：{session.get('title') or session_id}",
            str(fragment.get("content") or ""),
            enabled_categories=[],
            extraction_mode="general",
            story_id=story_id,
            custom_instructions=(
                "这是用户已经接受的原创正文片段。只提取后续创作需要长期复用的稳定事实、"
                "角色状态变化、关系变化、世界规则、地点、物品、能力、时间线和明确风格；"
                "不要把临时动作、普通场景描写和未证实猜测保存为长期知识。"
                "canon_status 使用 user_override。"
            ),
            stream_callback=stream_callback,
        )
        extraction = (
            extraction_step.get("data", {}).get("knowledge_extraction", {})
            if isinstance(extraction_step, dict)
            else {}
        )
        items = extraction.get("items", []) if isinstance(extraction, dict) else []
        source_title = f"自由创作：{session.get('title') or session_id}"
        candidates: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            category = str(normalized.get("category") or "")
            name = str(normalized.get("name") or "").strip()
            summary = str(normalized.get("summary") or "").strip()
            if not category or not name or not summary:
                continue
            digest = hashlib.sha256(
                f"{fragment_id}|{category}|{name}|{summary}".encode("utf-8")
            ).hexdigest()[:20]
            normalized.update({
                "pending_id": f"fragment_knowledge_{digest}",
                "story_id": story_id,
                "branch_id": branch_id or "",
                "setting_scope": "story",
                "injection_policy": "retrieval",
                "scope": "project",
                "authority": "project",
                "source_title": source_title,
                "source_origin": "interactive_fragment",
                "source_segment_id": fragment_id,
                "source_segment_ids": [fragment_id],
                "source_segment_title": source_title,
                "source_segment_titles": [source_title],
                "canon_status": "user_override",
                "extraction_mode": "creative_fragment",
                "worldline_id": worldline_id,
                "worldline_label": worldline_label,
                "version_scope": "project_main",
                "status": "pending",
                "tags": list(dict.fromkeys([
                    *[
                        str(tag)
                        for tag in normalized.get("tags", [])
                        if str(tag).strip()
                    ],
                    "自由创作",
                    "片段提炼",
                ])),
            })
            normalized = _attach_source_entity_mapping(project_name, story_id, branch_id, normalized, entity_candidates)
            evidence = normalized.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                normalized["evidence"] = [{
                    "source_title": source_title,
                    "quote": str(fragment.get("content") or "")[:160],
                    "note": "来自用户已接受的自由创作片段。",
                }]
            candidates.append(normalized)
        queued_count = queue_pending_knowledge_items(
            project_name,
            candidates,
            scope="project",
            authority="project",
            source_title=source_title,
            source_origin="interactive_fragment",
            branch_id=branch_id or "",
        )
        # refactor 2 P4（D10）：接受片段提炼的候选自动确认，不再堆积待人工审核。
        # 入队函数返回 int 不返回 ids —— pending_ids 从 candidates 的 pending_id 键提取。
        auto_confirm: dict = {}
        pending_ids_for_confirm = [
            str(item.get("pending_id") or "") for item in candidates
            if str(item.get("pending_id") or "") and item.get("entity_resolution_status") != "pending_confirmation"
        ]
        if pending_ids_for_confirm:
            try:
                from novelforge.workflows.source_workflows import auto_confirm_pending_items_without_risk

                auto_confirm = auto_confirm_pending_items_without_risk(
                    project_name,
                    pending_ids_for_confirm,
                    source_type="interactive_fragment",
                    source_title=source_title,
                    note="接受创作片段后自动提炼并确认",
                )
            except Exception as exc:
                LOGGER.warning("自动确认创作片段提炼候选失败：fragment=%s error=%s", fragment_id, exc)
        ambiguous = {str(item["pending_id"]): str(item.get("entity_resolution_reason") or "同名来源需要确认") for item in candidates if item.get("entity_resolution_status") == "pending_confirmation"}
        if ambiguous:
            auto_confirm["blocked_ids"] = list(dict.fromkeys([*(auto_confirm.get("blocked_ids") or []), *ambiguous]))
            auto_confirm["blocked_reasons"] = {**(auto_confirm.get("blocked_reasons") or {}), **ambiguous}
        update_creative_fragment(
            project_name,
            fragment_id,
            {"extraction_status": "completed"},
            story_id=story_id,
        )
        # 接受时已经捕获了该 frontier 的 pending 基线。提炼成功只允许从
        # 那份固定 payload 生成 ready 检查点，不能按当前 head 重建历史。
        if branch_id:
            from novelforge.services.memory.branches import create_story_checkpoint

            create_story_checkpoint(
                project_name,
                story_id,
                branch_id,
                frontier_fragment_id=fragment_id,
                extraction_status="ready",
                reason="片段提炼完成，确认接受时捕获的基线",
            )
        return {
            "success": True,
            "status": "completed",
            "session_id": session_id,
            "fragment_id": fragment_id,
            "candidates": candidates,
            "candidate_ids": [
                str(item.get("pending_id") or "")
                for item in candidates
                if str(item.get("pending_id") or "")
            ],
            "queued_count": queued_count,
            "auto_confirm": auto_confirm,
            "extraction_step": extraction_step,
        }
    except Exception:
        try:
            update_creative_fragment(
                project_name,
                fragment_id,
                {"extraction_status": "failed"},
                story_id=story_id,
            )
        except Exception as status_exc:
            LOGGER.warning(
                "Failed to record fragment extraction failure: fragment=%s error=%s",
                fragment_id,
                status_exc,
            )
        raise


def pending_knowledge_for_fragment(
    project_name: str,
    fragment_id: str,
) -> list[dict]:
    return [
        item
        for item in load_pending_knowledge_items(project_name)
        if str(item.get("source_segment_id") or "") == str(fragment_id or "")
        or str(fragment_id or "") in {
            str(value)
            for value in item.get("source_segment_ids", [])
            if str(value)
        }
    ]


def compile_session_text(
    bundle: dict,
) -> str:
    fragments = [
        fragment
        for fragment in _iw.active_fragment_chain(bundle)
        if str(fragment.get("status") or "") == "accepted"
    ]
    if not fragments:
        return ""
    return "\n\n".join(
        str(fragment.get("content") or "").strip()
        for fragment in fragments
        if str(fragment.get("content") or "").strip()
    )


def save_writing_session_as_chapter(
    project_name: str,
    story_id: str,
    session_id: str,
    chapter_no: int,
    *,
    append_to_existing: bool = False,
    smooth_transitions: bool = False,
    target_word_count: str = "",
    stream_callback=None,
    branch_id: str | None = None,
) -> dict:
    bundle = _iw._bundle_or_raise(project_name, story_id, session_id)
    from novelforge.services.memory import resolve_creative_session_branch
    branch_id = resolve_creative_session_branch(project_name, story_id, session_id, branch_id)
    if str(bundle.get("session", {}).get("status") or "") == "archived":
        raise ValueError("已归档的创作会话不能汇编为章节。")
    normalized_chapter_no = int(chapter_no)
    if normalized_chapter_no < 1:
        raise ValueError("章节编号必须大于等于 1。")
    compiled = compile_session_text(bundle)
    if not compiled.strip():
        raise ValueError("当前会话还没有已接受片段。")
    existing = load_chapter(project_name, normalized_chapter_no, story_id=story_id, branch_id=branch_id)
    if existing.strip() and not append_to_existing:
        raise FileExistsError("目标章节已有正文；请选择其它章节编号或明确使用追加模式。")
    source_text = (
        f"{existing.rstrip()}\n\n{compiled}"
        if existing.strip() and append_to_existing
        else compiled
    )
    final_text = source_text
    if smooth_transitions:
        with llm_usage_scope(
            project_name=project_name,
            story_id=story_id,
            task_id=session_id,
            operation="creative.compile",
            agent_role="editor",
        ):
            final_text = call_llm(
                compile_creative_fragments_prompt(source_text, target_word_count),
                stream_callback=stream_callback,
            )
        if not str(final_text or "").strip():
            raise RuntimeError("模型没有返回整理后的章节正文。")
    save_chapter(
        project_name,
        normalized_chapter_no,
        str(final_text).strip(),
        story_id=story_id,
        branch_id=branch_id,
    )
    accepted_ids = {
        str(fragment.get("fragment_id") or "")
        for fragment in _iw.active_fragment_chain(bundle)
        if str(fragment.get("status") or "") == "accepted"
    }
    finalize_creative_session(
        project_name,
        session_id,
        sorted(accepted_ids),
        normalized_chapter_no,
        story_id=story_id,
    )
    return {
        "success": True,
        "status": "completed",
        "session_id": session_id,
        "chapter_no": normalized_chapter_no,
        "append_to_existing": bool(append_to_existing),
        "smooth_transitions": bool(smooth_transitions),
        "fragment_count": len(accepted_ids),
        "chapter": str(final_text).strip(),
    }
