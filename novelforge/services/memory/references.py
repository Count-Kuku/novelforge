"""Implementation slice for the memory facade: references."""

from __future__ import annotations

from novelforge.services import memory as _memory_api

def long_reference_batches_path(project_name: str) -> _memory_api.Path:
    path = _memory_api.project_path(project_name) / "long_reference_batches"
    path.mkdir(exist_ok=True)
    return path


def long_reference_batch_path(project_name: str, batch_id: str) -> _memory_api.Path:
    safe_id = _memory_api.re.sub(r"[^A-Za-z0-9_\-]+", "_", str(batch_id or "")).strip("_")
    if not safe_id:
        raise ValueError("Batch id cannot be empty.")
    return long_reference_batches_path(project_name) / f"{safe_id}.json"


def _now_iso() -> str:
    return _memory_api.datetime.now(_memory_api.timezone.utc).isoformat()


def summarize_long_reference_batch(batch: dict) -> dict:
    segments = batch.get("segments", []) if isinstance(batch.get("segments", []), list) else []
    imported_count = len([item for item in segments if item.get("import_status") == "imported"])
    extracted_count = len([item for item in segments if item.get("extract_status") in {"queued", "extracted"}])
    failed_count = len([item for item in segments if item.get("extract_status") == "failed"])
    skipped_count = len([item for item in segments if item.get("extract_status") == "skipped"])
    total_count = len(segments)
    return {
        "segment_count": total_count,
        "imported_count": imported_count,
        "extract_queued_count": extracted_count,
        "extract_failed_count": failed_count,
        "extract_skipped_count": skipped_count,
        "import_pending_count": max(total_count - imported_count, 0),
        "extract_pending_count": len([
            item for item in segments
            if item.get("extract_status", "pending") in {"pending", ""}
        ]),
    }


def normalize_long_reference_batch(batch: dict | None) -> dict:
    raw = batch if isinstance(batch, dict) else {}
    batch_id = str(raw.get("batch_id") or f"batch_{_memory_api.uuid4().hex}")
    now = _now_iso()
    segments = []
    for index, item in enumerate(raw.get("segments", []) if isinstance(raw.get("segments", []), list) else [], start=1):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", ""))
        title = str(item.get("title") or f"片段 {index:03d}")
        segments.append({
            **item,
            "segment_id": str(item.get("segment_id") or f"seg_{index:04d}_{_memory_api.uuid4().hex[:8]}"),
            "index": int(item.get("index") or index),
            "title": title,
            "content": content,
            "char_count": int(item.get("char_count") or len(content)),
            "split_method": str(item.get("split_method") or "未知"),
            "import_status": str(item.get("import_status") or "pending"),
            "extract_status": str(item.get("extract_status") or "pending"),
            "queued_knowledge_count": int(item.get("queued_knowledge_count") or 0),
            "imported_source_name": str(item.get("imported_source_name") or ""),
            "extract_error": str(item.get("extract_error") or ""),
        })
    normalized = {
        **raw,
        "batch_id": batch_id,
        "title": str(raw.get("title") or "长篇资料批次"),
        "scope": str(raw.get("scope") or "reference"),
        "authority": str(raw.get("authority") or "curated"),
        "source_type": str(raw.get("source_type") or "external_source"),
        "source_origin": str(raw.get("source_origin") or ""),
        "source_file_name": str(raw.get("source_file_name") or ""),
        "content_fingerprint": str(raw.get("content_fingerprint") or ""),
        "content_char_count": int(raw.get("content_char_count") or sum(len(item.get("content", "")) for item in segments)),
        "created_at": str(raw.get("created_at") or now),
        "updated_at": str(raw.get("updated_at") or now),
        "segments": segments,
    }
    normalized["summary"] = summarize_long_reference_batch(normalized)
    return normalized


def create_long_reference_batch(
    project_name: str,
    *,
    title: str,
    scope: str,
    authority: str,
    source_type: str,
    source_origin: str = "",
    source_file_name: str = "",
    content_fingerprint: str = "",
    content_char_count: int = 0,
    segments: list[dict],
) -> dict:
    batch = normalize_long_reference_batch({
        "batch_id": f"batch_{_memory_api.uuid4().hex}",
        "title": title,
        "scope": scope,
        "authority": authority,
        "source_type": source_type,
        "source_origin": source_origin,
        "source_file_name": source_file_name,
        "content_fingerprint": content_fingerprint,
        "content_char_count": content_char_count,
        "segments": segments,
    })
    save_long_reference_batch(project_name, batch)
    return batch


def save_long_reference_batch(project_name: str, batch: dict) -> dict:
    normalized = normalize_long_reference_batch({
        **(batch or {}),
        "updated_at": _now_iso(),
    })
    path = long_reference_batch_path(project_name, normalized["batch_id"])
    _memory_api._write_json_mirror(path, normalized)
    _memory_api._sync_source_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_long_reference_batch(conn, normalized),
    )
    return normalized


def load_long_reference_batch(project_name: str, batch_id: str) -> dict:
    db_item = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.load_long_reference_batch_row(conn, batch_id),
        "long reference batch",
    )
    if db_item is not None:
        if not db_item:
            return {}
        return normalize_long_reference_batch(db_item)
    path = long_reference_batch_path(project_name, batch_id)
    if not path.exists():
        return {}
    try:
        raw = _memory_api.json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return normalize_long_reference_batch(raw)


def _list_long_reference_batches_from_files(project_name: str) -> list[dict]:
    path = long_reference_batches_path(project_name)
    batches = []
    for file in sorted(path.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            raw = _memory_api.json.loads(file.read_text(encoding="utf-8"))
        except Exception:
            continue
        batch = normalize_long_reference_batch(raw)
        batch["file_name"] = file.name
        batches.append(batch)
    return batches


def list_long_reference_batches(project_name: str) -> list[dict]:
    db_items = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        _memory_api.load_long_reference_batch_rows,
        "long reference batches",
    )
    if db_items is not None:
        batches = []
        for item in db_items:
            batch = normalize_long_reference_batch(item)
            safe_id = _memory_api.re.sub(r"[^A-Za-z0-9_\-]+", "_", str(batch.get("batch_id") or "")).strip("_")
            batch["file_name"] = f"{safe_id}.json"
            batches.append(batch)
        return batches
    batches = _list_long_reference_batches_from_files(project_name)
    if db_items == [] and batches:
        for batch in batches:
            _memory_api._sync_source_to_db_best_effort(
                project_name,
                lambda conn, payload=batch: _memory_api.sync_long_reference_batch(conn, payload),
            )
    return batches


def delete_long_reference_batch(project_name: str, batch_id: str) -> bool:
    path = long_reference_batch_path(project_name, batch_id)
    clean_batch_id = str(batch_id or "").strip()
    file_existed = path.exists()
    db_exists = bool(load_long_reference_batch(project_name, clean_batch_id))
    if not file_existed and not db_exists:
        return False
    if file_existed:
        path.unlink()
    _memory_api._sync_source_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.mark_long_reference_batch_deleted(conn, batch_id=clean_batch_id),
    )
    return True


def retrieval_path(project_name: str) -> _memory_api.Path:
    path = _memory_api.project_path(project_name) / "retrieval"
    path.mkdir(exist_ok=True)
    return path


def retrieval_sources_path(project_name: str) -> _memory_api.Path:
    path = retrieval_path(project_name) / "sources"
    path.mkdir(parents=True, exist_ok=True)
    return path


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
    _memory_api._write_json_mirror(file, resolutions)
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_conflict_resolution(conn, normalized),
    )
    _memory_api.sync_project_retrieval_assets(project_name)
    return normalized


def _normalize_string_list_field(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
    return []


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
    return {
        "case_id": case_id,
        "story_id": str(payload.get("story_id") or "").strip(),
        "name": str(payload.get("name") or payload.get("query") or "未命名评测用例").strip(),
        "query": str(payload.get("query") or "").strip(),
        "expected_terms": _normalize_string_list_field(payload.get("expected_terms", [])),
        "expected_chunk_ids": _normalize_string_list_field(payload.get("expected_chunk_ids", [])),
        "expected_source_types": _normalize_string_list_field(payload.get("expected_source_types", [])),
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
    _memory_api._write_json_mirror(retrieval_eval_cases_path(project_name), normalized)
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
    _memory_api._write_json_mirror(retrieval_eval_runs_path(project_name), runs[-200:])
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
    }
    items = load_retrieval_feedback(project_name)
    items.append(normalized)
    _memory_api._write_json_mirror(retrieval_feedback_path(project_name), items[-1000:])
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
    _memory_api._write_text_mirror(file, content)
    try:
        manifest_payload = _memory_api.json.loads(content)
    except Exception:
        manifest_payload = None
    if not isinstance(manifest_payload, dict):
        _memory_api._discard_pending_mirror_deletion(file)
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
    _memory_api._write_text_mirror(file, content)
    try:
        vector_payload = _memory_api.json.loads(content)
    except Exception:
        vector_payload = None
    if not isinstance(vector_payload, dict):
        _memory_api._discard_pending_mirror_deletion(file)
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


def sync_project_database_from_files(project_name: str) -> dict:
    """Create project.db from legacy files when no authoritative DB exists."""
    normalized_name = _memory_api.normalize_project_name(project_name)
    database_path = _memory_api.project_path(normalized_name) / "project.db"
    result = {
        "ok": False,
        "project_name": normalized_name,
        "db_path": str(database_path),
        "synced": {},
        "warnings": [],
        "error": "",
    }
    if database_path.exists():
        result["error"] = (
            "Refusing to import legacy files over an existing authoritative project.db. "
            "Move or back up the database first if a full legacy restore is intended."
        )
        return result
    try:
        _memory_api.initialize_project_db(_memory_api.ensure_project_path(normalized_name), normalized_name)
        with _memory_api.open_project_db(_memory_api.project_path(normalized_name).resolve()) as conn:
            project_root = _memory_api.project_path(normalized_name).resolve()

            memory_file = project_root / "memory.json"
            legacy_memory = {}
            if memory_file.exists():
                try:
                    raw_memory = _memory_api.json.loads(memory_file.read_text(encoding="utf-8"))
                    if isinstance(raw_memory, dict):
                        legacy_memory = raw_memory
                except Exception as exc:
                    result["warnings"].append(f"project memory metadata skipped: {exc}")
            _memory_api.upsert_project_meta(
                conn,
                project_name=normalized_name,
                title=str(legacy_memory.get("title") or normalized_name),
                genre=str(legacy_memory.get("genre") or ""),
            )
            result["synced"]["project_metadata"] = 1

            def sync_payload_asset(
                file: _memory_api.Path,
                *,
                asset_type: str,
                logical_key: str,
                payload,
                story_id: str | None = None,
                title: str = "",
                metadata: dict | None = None,
            ) -> None:
                if not file.exists():
                    return
                resolved_file = file.resolve()
                try:
                    relative_path = str(resolved_file.relative_to(project_root)).replace("\\", "/")
                except ValueError:
                    return
                content_hash = _memory_api.hashlib.sha256(resolved_file.read_bytes()).hexdigest()
                asset_id_source = f"{story_id or 'project'}:{asset_type}:{logical_key}"
                asset_id = "asset_" + _memory_api.hashlib.sha256(asset_id_source.encode("utf-8")).hexdigest()[:24]
                _memory_api.register_asset_file(
                    conn,
                    asset_id=asset_id,
                    story_id=story_id,
                    asset_type=asset_type,
                    logical_key=logical_key,
                    title=title,
                    relative_path=relative_path,
                    content_hash=content_hash,
                    mime_type="application/json",
                    metadata=metadata,
                )
                _memory_api.upsert_asset_payload(
                    conn,
                    asset_type=asset_type,
                    logical_key=logical_key,
                    story_id=story_id,
                    payload=payload,
                )

            stories_index = _memory_api._load_stories_index_file(normalized_name)
            if not stories_index.get("stories"):
                default_story = _memory_api.StoryMeta(
                    story_id="default",
                    name="默认故事",
                    description="",
                    status="active",
                    created_at=_memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds"),
                    updated_at=_memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds"),
                )
                stories_index = _memory_api.StoriesIndex(stories=[default_story], active_story_id="default").model_dump()
            _memory_api.sync_stories_index(conn, stories_index)
            result["synced"]["stories"] = len(stories_index.get("stories", []))

            profile_count = 0
            story_rule_count = 0
            story_prompt_option_count = 0
            asset_payload_count = 0
            for story in stories_index.get("stories", []):
                story_id = str(story.get("story_id") or "default")
                profile_file = _memory_api.creative_profile_path(normalized_name, story_id)
                if profile_file.exists():
                    try:
                        profile_raw = _memory_api.json.loads(profile_file.read_text(encoding="utf-8"))
                    except Exception:
                        profile_raw = {}
                    profile = _memory_api.CreativeProfile.model_validate(profile_raw).model_dump()
                    _memory_api.sync_story_profile(conn, story_id, profile)
                    profile_count += 1

                story_rules_file = _memory_api._story_rules_overrides_path(normalized_name, story_id)
                if story_rules_file.exists():
                    try:
                        story_rules_raw = _memory_api.json.loads(story_rules_file.read_text(encoding="utf-8"))
                    except Exception:
                        story_rules_raw = {}
                    story_rules = _memory_api.normalize_rules(story_rules_raw)
                    _memory_api.sync_rules_payload(conn, "story", story_rules, story_id)
                    story_rule_count += sum(len(items) for items in story_rules.values())

                story_prompt_options = _memory_api._load_prompt_options_file(
                    _memory_api._story_prompt_options_path(normalized_name, story_id),
                    "story",
                )
                _memory_api.sync_prompt_options_payload(conn, "story", story_prompt_options, story_id)
                story_prompt_option_count += len(story_prompt_options)

                creative_discussion_file = _memory_api._creative_profile_discussion_path(normalized_name, story_id)
                if creative_discussion_file.exists():
                    try:
                        payload = _memory_api.json.loads(creative_discussion_file.read_text(encoding="utf-8"))
                    except Exception:
                        payload = None
                    if isinstance(payload, dict):
                        sync_payload_asset(
                            creative_discussion_file,
                            asset_type="creative_profile_discussion",
                            logical_key="creative_profile",
                            story_id=story_id,
                            title="Creative Profile Discussion",
                            payload=payload,
                        )
                        asset_payload_count += 1

                story_memory_file = _memory_api._story_memory_overrides_path(normalized_name, story_id)
                if story_memory_file.exists():
                    try:
                        payload = _memory_api.json.loads(story_memory_file.read_text(encoding="utf-8"))
                    except Exception:
                        payload = None
                    if isinstance(payload, dict):
                        sync_payload_asset(
                            story_memory_file,
                            asset_type="story_memory_overrides",
                            logical_key="memory_overrides",
                            story_id=story_id,
                            title="Story Memory Overrides",
                            payload=payload,
                        )
                        asset_payload_count += 1

                summaries_file = _memory_api._story_chapter_summaries_path(normalized_name, story_id)
                if summaries_file.exists():
                    try:
                        payload = _memory_api.json.loads(summaries_file.read_text(encoding="utf-8"))
                    except Exception:
                        payload = None
                    if isinstance(payload, list):
                        sync_payload_asset(
                            summaries_file,
                            asset_type="chapter_summaries",
                            logical_key="chapter_summaries",
                            story_id=story_id,
                            title="Chapter Summaries",
                            payload=[item for item in payload if isinstance(item, dict)],
                        )
                        asset_payload_count += 1

                outline_discussion_file = _memory_api._outline_discussion_path(normalized_name, story_id)
                if outline_discussion_file.exists():
                    try:
                        payload = _memory_api.json.loads(outline_discussion_file.read_text(encoding="utf-8"))
                    except Exception:
                        payload = None
                    if isinstance(payload, dict):
                        sync_payload_asset(
                            outline_discussion_file,
                            asset_type="outline_discussion",
                            logical_key="main",
                            story_id=story_id,
                            title="Story Outline Discussion",
                            payload=payload,
                        )
                        asset_payload_count += 1

                for file in _memory_api.volumes_path(normalized_name, story_id).glob("volume_*.meta.json"):
                    try:
                        volume_no = int(file.name.replace("volume_", "").replace(".meta.json", ""))
                        payload = _memory_api.VolumeOutlineMetadata.model_validate(_memory_api.json.loads(file.read_text(encoding="utf-8"))).model_dump()
                    except Exception:
                        continue
                    sync_payload_asset(
                        file,
                        asset_type="volume_metadata",
                        logical_key=f"volume_{volume_no:03d}",
                        story_id=story_id,
                        title=f"Volume {volume_no:03d} Metadata",
                        payload=payload,
                        metadata={"volume_no": volume_no},
                    )
                    asset_payload_count += 1

                for file in _memory_api.volumes_path(normalized_name, story_id).glob("volume_*.discussion.json"):
                    try:
                        volume_no = int(file.name.replace("volume_", "").replace(".discussion.json", ""))
                        payload = _memory_api.json.loads(file.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    if isinstance(payload, dict):
                        sync_payload_asset(
                            file,
                            asset_type="volume_discussion",
                            logical_key=f"volume_{volume_no:03d}",
                            story_id=story_id,
                            title=f"Volume {volume_no:03d} Discussion",
                            payload=payload,
                            metadata={"volume_no": volume_no},
                        )
                        asset_payload_count += 1

                for file in _memory_api.arcs_path(normalized_name, story_id).glob("arc_*.meta.json"):
                    try:
                        arc_no = int(file.name.replace("arc_", "").replace(".meta.json", ""))
                        payload = _memory_api.ArcOutlineMetadata.model_validate(_memory_api.json.loads(file.read_text(encoding="utf-8"))).model_dump()
                    except Exception:
                        continue
                    sync_payload_asset(
                        file,
                        asset_type="arc_metadata",
                        logical_key=f"arc_{arc_no:03d}",
                        story_id=story_id,
                        title=f"Arc {arc_no:03d} Metadata",
                        payload=payload,
                        metadata={"arc_no": arc_no},
                    )
                    asset_payload_count += 1

                for file in _memory_api.arcs_path(normalized_name, story_id).glob("arc_*.discussion.json"):
                    try:
                        arc_no = int(file.name.replace("arc_", "").replace(".discussion.json", ""))
                        payload = _memory_api.json.loads(file.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    if isinstance(payload, dict):
                        sync_payload_asset(
                            file,
                            asset_type="arc_discussion",
                            logical_key=f"arc_{arc_no:03d}",
                            story_id=story_id,
                            title=f"Arc {arc_no:03d} Discussion",
                            payload=payload,
                            metadata={"arc_no": arc_no},
                        )
                        asset_payload_count += 1

                for file in _memory_api.arcs_path(normalized_name, story_id).glob("arc_*.chapter_plan.json"):
                    try:
                        arc_no = int(file.name.replace("arc_", "").replace(".chapter_plan.json", ""))
                        payload = _memory_api.json.loads(file.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    if isinstance(payload, dict):
                        sync_payload_asset(
                            file,
                            asset_type="arc_chapter_plan",
                            logical_key=f"arc_{arc_no:03d}",
                            story_id=story_id,
                            title=f"Arc {arc_no:03d} Chapter Plan",
                            payload=payload,
                            metadata={"arc_no": arc_no},
                        )
                        asset_payload_count += 1

                chapter_outline_dir = _memory_api._story_path_from_project_path(normalized_name, story_id, "chapter_outlines")
                for file in chapter_outline_dir.glob("chapter_*.meta.json"):
                    try:
                        chapter_no = int(file.name.replace("chapter_", "").replace(".meta.json", ""))
                        payload = _memory_api.ChapterOutlineMetadata.model_validate(_memory_api.json.loads(file.read_text(encoding="utf-8"))).model_dump()
                    except Exception:
                        continue
                    sync_payload_asset(
                        file,
                        asset_type="chapter_outline_metadata",
                        logical_key=f"chapter_{chapter_no:03d}",
                        story_id=story_id,
                        title=f"Chapter {chapter_no:03d} Outline Metadata",
                        payload=payload,
                        metadata={"chapter_no": chapter_no},
                    )
                    asset_payload_count += 1

                for file in chapter_outline_dir.glob("chapter_*.discussion.json"):
                    try:
                        chapter_no = int(file.name.replace("chapter_", "").replace(".discussion.json", ""))
                        payload = _memory_api.json.loads(file.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    if isinstance(payload, dict):
                        sync_payload_asset(
                            file,
                            asset_type="chapter_discussion",
                            logical_key=f"chapter_{chapter_no:03d}",
                            story_id=story_id,
                            title=f"Chapter {chapter_no:03d} Discussion",
                            payload=payload,
                            metadata={"chapter_no": chapter_no},
                        )
                        asset_payload_count += 1

                for file in _memory_api._story_path_from_project_path(normalized_name, story_id, "reviews").glob("chapter_*.json"):
                    try:
                        chapter_no = int(file.name.replace("chapter_", "").replace(".json", ""))
                        payload = _memory_api.json.loads(file.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    if isinstance(payload, dict):
                        sync_payload_asset(
                            file,
                            asset_type="review_json",
                            logical_key=f"chapter_{chapter_no:03d}",
                            story_id=story_id,
                            title=f"Chapter {chapter_no:03d} Review JSON",
                            payload=payload,
                            metadata={"chapter_no": chapter_no},
                        )
                        asset_payload_count += 1

                for file in _memory_api.evaluation_path(normalized_name, story_id).glob("chapter_*.json"):
                    try:
                        chapter_no = int(file.name.replace("chapter_", "").replace(".json", ""))
                        payload = _memory_api.json.loads(file.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    if isinstance(payload, dict):
                        sync_payload_asset(
                            file,
                            asset_type="evaluation_json",
                            logical_key=f"chapter_{chapter_no:03d}",
                            story_id=story_id,
                            title=f"Chapter {chapter_no:03d} Evaluation JSON",
                            payload=payload,
                            metadata={"chapter_no": chapter_no},
                        )
                        asset_payload_count += 1
            result["synced"]["story_profiles"] = profile_count
            result["synced"]["story_rules"] = story_rule_count
            result["synced"]["story_prompt_options"] = story_prompt_option_count
            result["synced"]["asset_payloads"] = asset_payload_count

            project_rules_file = _memory_api.project_path(normalized_name) / "rules.json"
            if project_rules_file.exists():
                try:
                    project_rules_raw = _memory_api.json.loads(project_rules_file.read_text(encoding="utf-8"))
                except Exception:
                    project_rules_raw = {}
                project_rules = _memory_api.normalize_rules(project_rules_raw)
            else:
                project_rules = _memory_api.normalize_rules(None)
            _memory_api.sync_rules_payload(conn, "project", project_rules)
            result["synced"]["project_rules"] = sum(len(items) for items in project_rules.values())

            project_prompt_options = _memory_api._load_prompt_options_file(
                _memory_api._project_prompt_options_path(normalized_name),
                "project",
            )
            _memory_api.sync_prompt_options_payload(conn, "project", project_prompt_options)
            result["synced"]["project_prompt_options"] = len(project_prompt_options)

            project_payload_count = 0
            for file, asset_type, logical_key, title in [
                (_memory_api.character_entities_path(normalized_name), "character_entities", "characters", "Character Entities"),
                (_memory_api.setting_entities_path(normalized_name), "setting_entities", "settings", "Setting Entities"),
                (_memory_api.extraction_plan_templates_path(normalized_name), "extraction_plan_templates", "templates", "Extraction Plan Templates"),
            ]:
                if not file.exists():
                    continue
                try:
                    payload = _memory_api.json.loads(file.read_text(encoding="utf-8"))
                except Exception:
                    payload = None
                if isinstance(payload, list):
                    sync_payload_asset(
                        file,
                        asset_type=asset_type,
                        logical_key=logical_key,
                        title=title,
                        payload=[item for item in payload if isinstance(item, dict)],
                    )
                    project_payload_count += 1

            project_rule_conflicts_file = _memory_api._project_rule_conflict_resolutions_path(normalized_name)
            if project_rule_conflicts_file.exists():
                try:
                    payload = _memory_api.json.loads(project_rule_conflicts_file.read_text(encoding="utf-8"))
                except Exception:
                    payload = None
                if isinstance(payload, list):
                    normalized_conflicts = _memory_api.normalize_rule_conflict_resolutions(payload)
                    sync_payload_asset(
                        project_rule_conflicts_file,
                        asset_type="rule_conflict_resolutions",
                        logical_key="project:project",
                        title="Project Rule Conflict Resolutions",
                        payload=normalized_conflicts,
                    )
                    project_payload_count += 1

            for story in stories_index.get("stories", []):
                story_id = str(story.get("story_id") or "default")
                story_rule_conflicts_file = _memory_api._story_rule_conflict_resolutions_path(normalized_name, story_id)
                if not story_rule_conflicts_file.exists():
                    continue
                try:
                    payload = _memory_api.json.loads(story_rule_conflicts_file.read_text(encoding="utf-8"))
                except Exception:
                    payload = None
                if isinstance(payload, list):
                    normalized_conflicts = _memory_api.normalize_rule_conflict_resolutions(payload)
                    sync_payload_asset(
                        story_rule_conflicts_file,
                        asset_type="rule_conflict_resolutions",
                        logical_key=f"story:{story_id}",
                        story_id=story_id,
                        title="Story Rule Conflict Resolutions",
                        payload=normalized_conflicts,
                    )
                    project_payload_count += 1
            result["synced"]["project_asset_payloads"] = project_payload_count

            legacy_setting_items: dict[str, list[dict]] = {}
            if legacy_memory:
                try:
                    from novelforge.domain.setting_knowledge import build_setting_items_from_memory

                    for item in build_setting_items_from_memory(
                        legacy_memory,
                        setting_scope="project",
                        source_title="项目核心设定",
                    ):
                        category = str(item.get("category") or "")
                        if category in _memory_api.KNOWLEDGE_CATEGORIES:
                            legacy_setting_items.setdefault(category, []).append(item)
                except Exception as exc:
                    result["warnings"].append(f"legacy core settings skipped: {exc}")

            knowledge_total = 0
            for category in _memory_api.KNOWLEDGE_CATEGORIES:
                items = _memory_api._load_json_list(_memory_api.knowledge_category_path(normalized_name, category))
                existing_ids = {
                    str(item.get("id") or "")
                    for item in items
                    if isinstance(item, dict) and str(item.get("id") or "")
                }
                for legacy_item in legacy_setting_items.get(category, []):
                    legacy_id = str(legacy_item.get("id") or "")
                    if legacy_id and legacy_id not in existing_ids:
                        items.append(legacy_item)
                        existing_ids.add(legacy_id)
                _memory_api.sync_knowledge_category(conn, category, items)
                knowledge_total += len(items)
            result["synced"]["knowledge_items"] = knowledge_total

            pending_items = _memory_api._load_json_list(_memory_api.pending_knowledge_path(normalized_name))
            _memory_api.sync_pending_knowledge(conn, pending_items)
            result["synced"]["pending_knowledge_items"] = len(pending_items)

            alias_items = _memory_api._load_json_list(_memory_api.entity_aliases_path(normalized_name))
            _memory_api.sync_entity_alias_groups(conn, alias_items)
            result["synced"]["entity_alias_groups"] = len(alias_items)

            policy_path = _memory_api.auto_review_policy_path(normalized_name)
            if policy_path.exists():
                try:
                    policy_raw = _memory_api.json.loads(policy_path.read_text(encoding="utf-8"))
                except Exception:
                    policy_raw = {}
                policy = _memory_api.normalize_auto_review_policy(policy_raw)
            else:
                policy = dict(_memory_api.DEFAULT_AUTO_REVIEW_POLICY)
            _memory_api.sync_auto_review_policy(conn, policy)
            runs = _memory_api._load_json_list(_memory_api.auto_review_runs_path(normalized_name))
            _memory_api.sync_auto_review_runs(conn, runs)
            result["synced"]["auto_review_runs"] = len(runs)

            eval_cases = _memory_api._load_json_list(retrieval_eval_cases_path(normalized_name))
            _memory_api.sync_retrieval_eval_cases(conn, eval_cases)
            result["synced"]["retrieval_eval_cases"] = len(eval_cases)

            eval_runs = _memory_api._load_json_list(retrieval_eval_runs_path(normalized_name))
            for run in eval_runs:
                try:
                    _memory_api.sync_retrieval_eval_run(conn, run)
                except Exception as exc:
                    result["warnings"].append(f"retrieval_eval_run skipped: {exc}")
            result["synced"]["retrieval_eval_runs"] = len(eval_runs)

            feedback_items = _memory_api._load_json_list(retrieval_feedback_path(normalized_name))
            for feedback in feedback_items:
                try:
                    _memory_api.append_retrieval_feedback_row(conn, feedback)
                except Exception as exc:
                    result["warnings"].append(f"retrieval_feedback skipped: {exc}")
            result["synced"]["retrieval_feedback"] = len(feedback_items)

            conflict_items = []
            conflict_file = conflict_resolutions_path(normalized_name)
            if conflict_file.exists():
                try:
                    raw_conflicts = _memory_api.json.loads(conflict_file.read_text(encoding="utf-8"))
                except Exception:
                    raw_conflicts = []
                if isinstance(raw_conflicts, list):
                    for item in raw_conflicts:
                        try:
                            conflict_items.append(_memory_api.ConflictResolution.model_validate(item).model_dump())
                        except Exception:
                            continue
            for resolution in conflict_items:
                try:
                    _memory_api.sync_conflict_resolution(conn, resolution)
                except Exception as exc:
                    result["warnings"].append(f"conflict_resolution skipped: {exc}")
            result["synced"]["conflict_resolutions"] = len(conflict_items)

            batches = _list_long_reference_batches_from_files(normalized_name)
            for batch in batches:
                _memory_api.sync_long_reference_batch(conn, batch)
            result["synced"]["long_reference_batches"] = len(batches)

            source_root = retrieval_sources_path(normalized_name).resolve()
            source_files = [
                file.relative_to(source_root).as_posix()
                for file in source_root.rglob("*")
                if file.is_file()
            ]
            source_files = sorted(source_files, key=str.lower)
            for relative_path in source_files:
                target = (source_root / relative_path).resolve()
                if source_root not in target.parents and target != source_root:
                    continue
                content_hash = _memory_api.hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
                _memory_api.sync_retrieval_source_file(
                    conn,
                    relative_path=relative_path,
                    title=target.name,
                    content_hash=content_hash,
                    source_type="reference",
                    metadata={"relative_path": relative_path},
                )
            result["synced"]["retrieval_source_files"] = len(source_files)

            manifest_file = retrieval_path(normalized_name) / "manifest.json"
            manifest_content = manifest_file.read_text(encoding="utf-8") if manifest_file.exists() else ""
            if manifest_content.strip():
                try:
                    manifest_payload = _memory_api.json.loads(manifest_content)
                    if isinstance(manifest_payload, dict):
                        _memory_api.sync_retrieval_manifest_payload(conn, manifest_payload)
                        result["synced"]["retrieval_manifest"] = 1
                except Exception as exc:
                    result["warnings"].append(f"retrieval_manifest skipped: {exc}")
            else:
                result["synced"]["retrieval_manifest"] = 0

            vector_file = retrieval_path(normalized_name) / "vectors.json"
            vector_content = vector_file.read_text(encoding="utf-8") if vector_file.exists() else ""
            if vector_content.strip():
                try:
                    vector_payload = _memory_api.json.loads(vector_content)
                    if isinstance(vector_payload, dict):
                        _memory_api.sync_retrieval_vector_store_payload(conn, vector_payload)
                        result["synced"]["retrieval_vectors"] = len(vector_payload.get("vectors", {}) if isinstance(vector_payload.get("vectors", {}), dict) else {})
                except Exception as exc:
                    result["warnings"].append(f"retrieval_vectors skipped: {exc}")
            else:
                result["synced"]["retrieval_vectors"] = 0

            workflow_count = 0
            # Reuse the file snapshot already synchronized above. Calling the
            # DB-first list_stories() while this import transaction is open
            # would open a second writer and deadlock on a fresh legacy DB.
            for story in stories_index.get("stories", []):
                story_id = str(story.get("story_id") or "default")
                for run_id in _memory_api._list_pipeline_runs_from_files(normalized_name, story_id=story_id):
                    run_file = _memory_api.runs_path(normalized_name, story_id) / f"{run_id}.json"
                    raw = run_file.read_text(encoding="utf-8") if run_file.exists() else ""
                    if not raw.strip():
                        continue
                    try:
                        payload = _memory_api.json.loads(raw)
                        if not isinstance(payload, dict):
                            continue
                        asset_id_source = f"{story_id or 'project'}:workflow_run_snapshot:{run_id}"
                        artifact_asset_id = "asset_" + _memory_api.hashlib.sha256(asset_id_source.encode("utf-8")).hexdigest()[:24]
                        _memory_api.sync_workflow_run_snapshot(
                            conn,
                            run_id=str(run_id),
                            payload=payload,
                            story_id=story_id,
                            artifact_asset_id=artifact_asset_id,
                        )
                        workflow_count += 1
                    except Exception as exc:
                        result["warnings"].append(f"workflow_run {run_id} skipped: {exc}")
            result["synced"]["workflow_runs"] = workflow_count

            conn.commit()
        _memory_api._DB_UNAVAILABLE_PROJECTS.discard(normalized_name)
        result["ok"] = True
    except Exception as exc:
        _memory_api._DB_UNAVAILABLE_PROJECTS.add(normalized_name)
        result["error"] = str(exc)
    return result

def sync_global_database_from_files() -> dict:
    """Create global.db from legacy JSON/.env when no authoritative DB exists."""
    global _GLOBAL_DB_UNAVAILABLE
    database_path = _memory_api.Path("data") / "global.db"
    result = {
        "ok": False,
        "db_path": str(database_path),
        "synced": {},
        "warnings": [],
        "error": "",
    }
    if database_path.exists():
        result["error"] = (
            "Refusing to import legacy files over an existing authoritative global.db. "
            "Move or back up the database first if a full legacy restore is intended."
        )
        return result
    try:
        _memory_api.initialize_global_db(_memory_api.Path("data"))
        with _memory_api.open_global_db(_memory_api.Path("data")) as conn:
            if _memory_api.LLM_PROFILES_PATH.exists():
                try:
                    raw_llm_profiles = _memory_api.json.loads(_memory_api.LLM_PROFILES_PATH.read_text(encoding="utf-8"))
                except Exception:
                    raw_llm_profiles = _memory_api._default_llm_profile_payload()
            else:
                raw_llm_profiles = {
                    "active_profile_id": "default",
                    "profiles": [_memory_api._load_env_llm_profile()],
                }
            llm_profiles = _memory_api._normalize_llm_profiles_payload(raw_llm_profiles)
            _memory_api.sync_global_setting(conn, "llm_profiles", llm_profiles)
            result["synced"]["llm_profiles"] = len(llm_profiles.get("profiles", []))

            if _memory_api.GLOBAL_RULES_PATH.exists():
                try:
                    raw_rules = _memory_api.json.loads(_memory_api.GLOBAL_RULES_PATH.read_text(encoding="utf-8"))
                except Exception:
                    raw_rules = {}
            else:
                raw_rules = {}
            global_rules = _memory_api.normalize_rules(raw_rules)
            _memory_api.sync_rules_payload(conn, "global", global_rules)
            result["synced"]["global_rules"] = sum(len(items) for items in global_rules.values())

            prompt_options = _memory_api._load_prompt_options_file(_memory_api.GLOBAL_PROMPT_OPTIONS_PATH, "global")
            _memory_api.sync_prompt_options_payload(conn, "global", prompt_options)
            result["synced"]["global_prompt_options"] = len(prompt_options)

            if _memory_api.GLOBAL_RULE_CONFLICT_RESOLUTIONS_PATH.exists():
                try:
                    raw_conflicts = _memory_api.json.loads(_memory_api.GLOBAL_RULE_CONFLICT_RESOLUTIONS_PATH.read_text(encoding="utf-8"))
                except Exception:
                    raw_conflicts = []
            else:
                raw_conflicts = []
            global_conflicts = _memory_api.normalize_rule_conflict_resolutions(raw_conflicts if isinstance(raw_conflicts, list) else None)
            _memory_api.sync_global_setting(conn, "rule_conflict_resolutions", global_conflicts)
            result["synced"]["global_rule_conflict_resolutions"] = len(global_conflicts)

            conn.commit()
        _memory_api._GLOBAL_DB_UNAVAILABLE = False
        result["ok"] = True
    except Exception as exc:
        _memory_api._GLOBAL_DB_UNAVAILABLE = True
        result["error"] = str(exc)
    return result
