"""Implementation slice for the memory facade: retrieval sources, eval, feedback, manifest."""

from __future__ import annotations

import logging

from novelforge.services import memory as _memory_api
from storage.repositories.ingestion_batch_mutations import (
    delete_long_reference_batch_row,
    persist_long_reference_batch_row,
)
from storage.repositories.retrieval import search_retrieval_chunks_fts
from storage.repositories.sources import list_source_revision_rows

def retrieval_path(project_name: str) -> _memory_api.Path:
    path = _memory_api.project_path(project_name) / "retrieval"
    path.mkdir(exist_ok=True)
    return path


def retrieval_sources_path(project_name: str) -> _memory_api.Path:
    path = retrieval_path(project_name) / "sources"
    path.mkdir(parents=True, exist_ok=True)
    return path


def search_project_retrieval_fts(project_name: str, query: str, limit: int = 20) -> list[dict]:
    result = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: search_retrieval_chunks_fts(conn, query, limit),
        "retrieval FTS",
    )
    return result if isinstance(result, list) else []


def load_source_revisions(project_name: str, source_id: str = "") -> list[dict]:
    result = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: list_source_revision_rows(conn, source_id),
        "source revisions",
    )
    return result if isinstance(result, list) else []


def conflict_resolutions_path(project_name: str) -> _memory_api.Path:
    return retrieval_path(project_name) / "conflict_resolutions.json"


def retrieval_eval_cases_path(project_name: str) -> _memory_api.Path:
    return retrieval_path(project_name) / "eval_cases.json"


def retrieval_eval_runs_path(project_name: str) -> _memory_api.Path:
    return retrieval_path(project_name) / "eval_runs.json"


def retrieval_feedback_path(project_name: str) -> _memory_api.Path:
    return retrieval_path(project_name) / "feedback.json"


def load_conflict_resolutions(project_name: str) -> list[dict]:
    db_items = _memory_api._load_runtime_from_db_best_effort(project_name, _memory_api.load_conflict_resolution_rows, "conflict resolutions")
    if db_items is not None:
        results = []
        for item in db_items:
            try:
                results.append(_memory_api.ConflictResolution.model_validate(item).model_dump())
            except Exception:
                continue
        return results
    file = conflict_resolutions_path(project_name)
    if not file.exists():
        return []
    try:
        raw = _memory_api.json.loads(file.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    results = []
    for item in raw:
        try:
            results.append(_memory_api.ConflictResolution.model_validate(item).model_dump())
        except Exception:
            continue
    return results


def save_conflict_resolution(project_name: str, resolution: dict) -> dict:
    from datetime import datetime

    normalized = _memory_api.ConflictResolution.model_validate({
        **resolution,
        "updated_at": str(resolution.get("updated_at") or _memory_api.datetime.now().isoformat(timespec="seconds")),
    }).model_dump()
    resolutions = load_conflict_resolutions(project_name)
    resolutions = [
        item
        for item in resolutions
        if not (
            item.get("conflict_id") == normalized["conflict_id"]
            and str(item.get("story_id") or "") == str(normalized.get("story_id") or "")
        )
    ]
    resolutions.append(normalized)
    file = conflict_resolutions_path(project_name)
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_conflict_resolution(conn, normalized),
    )
    _memory_api.sync_project_retrieval_assets(project_name)
    return normalized


def _normalize_string_list_field(value, *, case_insensitive: bool = False) -> list[str]:
    if isinstance(value, list):
        values = [str(item).strip() for item in value if str(item).strip()]
    elif isinstance(value, str):
        values = [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
    else:
        values = []
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        key = item.casefold() if case_insensitive else item
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def normalize_retrieval_eval_case(case: dict) -> dict:
    payload = dict(case or {})
    now = _memory_api.datetime.now(_memory_api.timezone.utc).isoformat()
    case_id = str(payload.get("case_id") or "").strip() or f"rag_eval_{_memory_api.uuid4().hex}"
    top_k = payload.get("top_k", 6)
    try:
        top_k = max(1, min(20, int(top_k)))
    except (TypeError, ValueError):
        top_k = 6
    min_expected_matches = payload.get("min_expected_matches", 1)
    try:
        min_expected_matches = max(1, int(min_expected_matches))
    except (TypeError, ValueError):
        min_expected_matches = 1
    retrieval_mode = str(payload.get("retrieval_mode") or "hybrid").strip()
    if retrieval_mode not in {"hybrid", "lexical", "semantic"}:
        retrieval_mode = "hybrid"
    worldline_mode = str(payload.get("worldline_mode") or "prefer").strip()
    if worldline_mode not in {"prefer", "strict"}:
        worldline_mode = "prefer"
    expected_terms = _normalize_string_list_field(payload.get("expected_terms", []), case_insensitive=True)
    expected_chunk_ids = _normalize_string_list_field(payload.get("expected_chunk_ids", []))
    expected_source_types = _normalize_string_list_field(payload.get("expected_source_types", []))
    expectation_count = len(expected_terms) + len(expected_chunk_ids) + len(expected_source_types)
    if expectation_count:
        min_expected_matches = min(min_expected_matches, expectation_count)
    return {
        "case_id": case_id,
        "story_id": str(payload.get("story_id") or "").strip(),
        "name": str(payload.get("name") or payload.get("query") or "未命名评测用例").strip(),
        "query": str(payload.get("query") or "").strip(),
        "expected_terms": expected_terms,
        "expected_chunk_ids": expected_chunk_ids,
        "expected_source_types": expected_source_types,
        "allowed_scopes": _normalize_string_list_field(payload.get("allowed_scopes", [])),
        "allowed_source_types": _normalize_string_list_field(payload.get("allowed_source_types", [])),
        "retrieval_profile": str(payload.get("retrieval_profile") or "").strip(),
        "retrieval_mode": retrieval_mode,
        "worldline_id": str(payload.get("worldline_id") or "").strip(),
        "worldline_mode": worldline_mode,
        "top_k": top_k,
        "min_expected_matches": min_expected_matches,
        "notes": str(payload.get("notes") or "").strip(),
        "status": str(payload.get("status") or "active").strip() or "active",
        "created_at": str(payload.get("created_at") or now),
        "updated_at": now,
    }


def load_retrieval_eval_cases(project_name: str) -> list[dict]:
    db_items = _memory_api._load_runtime_from_db_best_effort(project_name, _memory_api.load_retrieval_eval_case_rows, "retrieval eval cases")
    if db_items is not None:
        return db_items
    json_items = _memory_api._load_json_list(retrieval_eval_cases_path(project_name))
    if db_items == [] and json_items:
        _memory_api._sync_runtime_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_retrieval_eval_cases(conn, json_items),
        )
    return json_items


def save_retrieval_eval_cases(project_name: str, cases: list[dict]):
    normalized = [
        normalize_retrieval_eval_case(item)
        for item in (cases or [])
        if isinstance(item, dict)
    ]
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_retrieval_eval_cases(conn, normalized),
    )


def upsert_retrieval_eval_case(project_name: str, case: dict) -> dict:
    normalized = normalize_retrieval_eval_case(case)
    if not normalized["query"]:
        raise ValueError("评测查询不能为空。")
    if not (normalized["expected_terms"] or normalized["expected_chunk_ids"] or normalized["expected_source_types"]):
        raise ValueError("至少需要一个期望命中词、片段 ID 或来源类型。")
    cases = load_retrieval_eval_cases(project_name)
    updated = []
    replaced = False
    for item in cases:
        if str(item.get("case_id") or "") == normalized["case_id"]:
            normalized["created_at"] = item.get("created_at") or normalized["created_at"]
            updated.append(normalized)
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(normalized)
    save_retrieval_eval_cases(project_name, updated)
    return normalized


def delete_retrieval_eval_case(project_name: str, case_id: str) -> bool:
    target_id = str(case_id or "").strip()
    cases = load_retrieval_eval_cases(project_name)
    remaining = [item for item in cases if str(item.get("case_id") or "") != target_id]
    if len(remaining) == len(cases):
        return False
    save_retrieval_eval_cases(project_name, remaining)
    return True


def load_retrieval_eval_runs(project_name: str) -> list[dict]:
    db_items = _memory_api._load_runtime_from_db_best_effort(project_name, _memory_api.load_retrieval_eval_run_rows, "retrieval eval runs")
    if db_items is not None:
        return db_items
    json_items = _memory_api._load_json_list(retrieval_eval_runs_path(project_name))
    if db_items == [] and json_items:
        for item in json_items:
            _memory_api._sync_runtime_to_db_best_effort(
                project_name,
                lambda conn, payload=item: _memory_api.sync_retrieval_eval_run(conn, payload),
            )
    return json_items


def append_retrieval_eval_run(project_name: str, run: dict) -> dict:
    normalized = dict(run or {})
    normalized["run_id"] = str(normalized.get("run_id") or f"rag_eval_run_{_memory_api.uuid4().hex}")
    normalized["created_at"] = str(normalized.get("created_at") or _memory_api.datetime.now(_memory_api.timezone.utc).isoformat())
    runs = load_retrieval_eval_runs(project_name)
    runs.append(normalized)
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_retrieval_eval_run(conn, normalized),
    )
    return normalized


def load_retrieval_feedback(project_name: str) -> list[dict]:
    db_items = _memory_api._load_runtime_from_db_best_effort(project_name, _memory_api.load_retrieval_feedback_rows, "retrieval feedback")
    if db_items is not None:
        return db_items
    json_items = _memory_api._load_json_list(retrieval_feedback_path(project_name))
    if db_items == [] and json_items:
        for item in json_items:
            _memory_api._sync_runtime_to_db_best_effort(
                project_name,
                lambda conn, payload=item: _memory_api.append_retrieval_feedback_row(conn, payload),
            )
    return json_items


def append_retrieval_feedback(project_name: str, feedback: dict) -> dict:
    allowed_ratings = {"helpful", "priority", "irrelevant", "wrong"}
    payload = dict(feedback or {})
    rating = str(payload.get("rating") or "").strip()
    if rating not in allowed_ratings:
        raise ValueError("未知的检索反馈类型。")
    chunk_id = str(payload.get("chunk_id") or "").strip()
    if not chunk_id:
        raise ValueError("缺少检索片段 ID。")
    normalized = {
        "feedback_id": str(payload.get("feedback_id") or f"rag_feedback_{_memory_api.uuid4().hex}"),
        "created_at": str(payload.get("created_at") or _memory_api.datetime.now(_memory_api.timezone.utc).isoformat()),
        "query": str(payload.get("query") or "").strip(),
        "rating": rating,
        "note": str(payload.get("note") or "").strip(),
        "chunk_id": chunk_id,
        "document_id": str(payload.get("document_id") or "").strip(),
        "source_type": str(payload.get("source_type") or "").strip(),
        "scope": str(payload.get("scope") or "").strip(),
        "title": str(payload.get("title") or "").strip(),
        "path": str(payload.get("path") or "").strip(),
        "story_id": str(payload.get("story_id") or "").strip(),
        "content_hash": str(payload.get("content_hash") or "").strip(),
        "source_revision_id": str(payload.get("source_revision_id") or "").strip(),
    }
    items = load_retrieval_feedback(project_name)
    items.append(normalized)
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.append_retrieval_feedback_row(conn, normalized),
    )
    return normalized


def list_retrieval_source_files(project_name: str) -> list[str]:
    db_paths = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        _memory_api.list_retrieval_source_file_rows,
        "retrieval source files",
    )
    if db_paths is not None:
        return db_paths
    path = retrieval_sources_path(project_name)
    files = [file.relative_to(path).as_posix() for file in path.rglob("*") if file.is_file()]
    files = sorted(files, key=str.lower)
    if db_paths == [] and files:
        source_root = retrieval_sources_path(project_name).resolve()
        for relative_path in files:
            target = (source_root / relative_path).resolve()
            content_hash = _memory_api.hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
            _memory_api.sync_retrieval_source_file_record(
                project_name,
                relative_path=relative_path,
                title=target.name,
                content_hash=content_hash,
                metadata={"relative_path": relative_path},
            )
    return files


def delete_retrieval_source_file(project_name: str, relative_path: str) -> bool:
    base_path = retrieval_sources_path(project_name).resolve()
    normalized_relative_path = str(relative_path).replace("\\", "/").strip()
    target = (base_path / normalized_relative_path).resolve()
    if base_path not in target.parents and target != base_path:
        raise ValueError("Invalid retrieval source path.")
    file_existed = target.exists() and target.is_file()
    source_registered = normalized_relative_path in list_retrieval_source_files(project_name)
    if not file_existed and not source_registered:
        return False
    if file_existed:
        target.unlink()
    _memory_api.mark_asset_deleted_record(
        project_name,
        asset_type="retrieval_source",
        logical_key=normalized_relative_path,
    )
    _memory_api._sync_source_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.mark_retrieval_source_file_deleted(
            conn,
            relative_path=normalized_relative_path,
        ),
    )
    return True


def save_retrieval_manifest(project_name: str, content: str):
    file = retrieval_path(project_name) / "manifest.json"
    try:
        manifest_payload = _memory_api.json.loads(content)
    except Exception:
        manifest_payload = None
    if not isinstance(manifest_payload, dict):
        _memory_api._raise_if_db_only(f"Retrieval manifest for {project_name} must be valid JSON object in DB-only mode.")
        return
    _memory_api._sync_retrieval_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_retrieval_manifest_payload(conn, manifest_payload),
    )
    _memory_api.register_asset_file_record(
        project_name,
        file,
        asset_type="retrieval_manifest",
        logical_key="manifest",
        title="Retrieval Manifest",
        mime_type="application/json",
        source_kind="retrieval_index",
    )


def load_retrieval_manifest(project_name: str) -> str:
    db_payload = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.load_retrieval_manifest_payload(conn, project_name),
        "retrieval manifest",
    )
    if db_payload is not None:
        if not db_payload:
            return ""
        return _memory_api.json.dumps(db_payload, ensure_ascii=False, indent=2)
    file = retrieval_path(project_name) / "manifest.json"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_retrieval_vectors(project_name: str, content: str):
    file = retrieval_path(project_name) / "vectors.json"
    try:
        vector_payload = _memory_api.json.loads(content)
    except Exception:
        vector_payload = None
    if not isinstance(vector_payload, dict):
        _memory_api._raise_if_db_only(f"Retrieval vectors for {project_name} must be valid JSON object in DB-only mode.")
        return
    _memory_api._sync_retrieval_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_retrieval_vector_store_payload(conn, vector_payload),
    )
    _memory_api.register_asset_file_record(
        project_name,
        file,
        asset_type="retrieval_vectors",
        logical_key="vectors",
        title="Retrieval Vectors",
        mime_type="application/json",
        source_kind="retrieval_index",
    )


def load_retrieval_vectors(project_name: str) -> str:
    db_payload = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.load_retrieval_vector_store_payload(conn, project_name),
        "retrieval vectors",
    )
    if db_payload is not None:
        if not db_payload:
            return ""
        return _memory_api.json.dumps(db_payload, ensure_ascii=False, indent=2)
    file = retrieval_path(project_name) / "vectors.json"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def chapter_count(project_name: str, story_id: str = "default") -> int:
    chapters_dir = _memory_api._story_path_from_project_path(project_name, story_id, "chapters")
    if not chapters_dir.exists():
        return 0
    return len([f for f in chapters_dir.iterdir() if f.suffix == ".md"])
