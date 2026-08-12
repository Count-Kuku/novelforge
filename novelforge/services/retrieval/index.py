"""Implementation slice for the retrieval facade: index."""

from __future__ import annotations

from novelforge.services import retrieval as _retrieval_api

def chunk_document(document: _retrieval_api.RetrievalDocument) -> list[_retrieval_api.RetrievalChunk]:
    parts: list[tuple[str, str, str, int]]
    if document.source_type in _retrieval_api.STRUCTURED_SOURCE_TYPES or document.source_type.startswith("knowledge_") or document.source_type.startswith("entity_"):
        parent = document.content.strip()
        parts = [
            (document.title, chunk, parent, 1)
            for chunk in _retrieval_api._chunk_by_paragraphs(parent)
        ] if parent else []
    elif document.source_type.startswith("analysis_"):
        parts = []
        for section_index, (title, body) in enumerate(_retrieval_api._split_markdown_sections(document.content), start=1):
            parts.extend(
                (title, chunk, body.strip(), section_index)
                for chunk in _retrieval_api._chunk_by_paragraphs(body)
                if chunk.strip()
            )
    elif document.source_type in {"outline", "chapter_outline", "arc_chapter_plan", "evaluation_chapter", "review_markdown", "external_source", "external_character_sheet", "external_location_sheet", "external_organization_sheet", "external_timeline_note", "external_canon_event", "external_world_rule", "external_artifact_note"}:
        parts = []
        for section_index, (title, body) in enumerate(_retrieval_api._split_markdown_sections(document.content), start=1):
            parts.extend(
                (title, chunk, body.strip(), section_index)
                for chunk in _retrieval_api._chunk_by_paragraphs(body)
                if chunk.strip()
            )
    elif document.source_type == "chapter_content":
        parts = [(document.title, chunk, document.content.strip(), 1) for chunk in _retrieval_api._chunk_by_paragraphs(document.content)]
    else:
        parts = [(document.title, chunk, document.content.strip(), 1) for chunk in _retrieval_api._split_long_text(document.content)]

    if not parts:
        return []

    result = []
    parent_search_cursors: dict[tuple[int, str], int] = {}
    for index, (section_title, chunk_text, full_parent_content, section_index) in enumerate(parts, start=1):
        chunk_title = section_title or document.title
        parent_content = full_parent_content or document.content.strip()
        parent_seed = f"{section_index}\n{chunk_title}\n{parent_content}".encode("utf-8")
        parent_id = f"{document.doc_id}#parent-{_retrieval_api.sha256(parent_seed).hexdigest()[:12]}"
        parent_key = (section_index, parent_id)
        search_from = max(
            parent_search_cursors.get(parent_key, 0) - _retrieval_api.DEFAULT_CHUNK_OVERLAP,
            0,
        )
        content_start = parent_content.find(chunk_text, search_from) if parent_content else -1
        if content_start < 0 and parent_content:
            content_start = parent_content.find(chunk_text)
        if content_start >= 0:
            parent_search_cursors[parent_key] = content_start + len(chunk_text)
        parent_window_start = 0
        parent_window = parent_content
        if len(parent_window) > 6000:
            anchor = max(content_start, 0)
            parent_window_start = min(max(anchor - 2000, 0), len(parent_content) - 6000)
            parent_window = parent_content[parent_window_start:parent_window_start + 6000]
        parent_anchor_offset = parent_window.find(chunk_text) if parent_window else -1
        result.append(_retrieval_api.RetrievalChunk(
            chunk_id=f"{document.doc_id}#chunk{index:03d}",
            document_id=document.doc_id,
            project_name=document.project_name,
            source_type=document.source_type,
            scope=document.scope,
            title=chunk_title,
            content=chunk_text,
            chapter_no=document.chapter_no,
            path=document.path,
            tags=document.tags,
            metadata={
                **document.metadata,
                "chunk_index": index,
                "chunk_total": len(parts),
                "section_title": section_title,
                "chunk_level": "child",
                "parent_chunk_id": parent_id,
                "parent_title": chunk_title,
                "parent_content": parent_window,
                "parent_window_start": parent_window_start,
                "parent_anchor_offset": parent_anchor_offset if parent_anchor_offset >= 0 else None,
                "content_hash": _retrieval_api.sha256(f"{chunk_title}\n{chunk_text}".encode("utf-8")).hexdigest(),
                "start_offset": content_start if content_start >= 0 else None,
                "end_offset": content_start + len(chunk_text) if content_start >= 0 else None,
            },
        ))
    for index, chunk in enumerate(result):
        chunk.metadata["previous_chunk_id"] = result[index - 1].chunk_id if index > 0 else ""
        chunk.metadata["next_chunk_id"] = result[index + 1].chunk_id if index + 1 < len(result) else ""
    return result


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = _retrieval_api.math.sqrt(sum(x * x for x in a))
    norm_b = _retrieval_api.math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _is_reusable_vector(vector: object, *, expected_dimension: int | None = None) -> bool:
    if not isinstance(vector, list) or not vector:
        return False
    if expected_dimension is not None and len(vector) != expected_dimension:
        return False
    try:
        numeric_values = []
        for value in vector:
            if isinstance(value, bool):
                return False
            numeric_value = float(value)
            if not _retrieval_api.math.isfinite(numeric_value):
                return False
            numeric_values.append(numeric_value)
        return any(value != 0.0 for value in numeric_values)
    except (TypeError, ValueError):
        return False


def _generate_chunk_vector(chunk: _retrieval_api.RetrievalChunk) -> list[float]:
    vector = _retrieval_api.get_embedding(f"{chunk.title}\n{chunk.content}")
    if not _is_reusable_vector(vector):
        raise RuntimeError(f"向量模型为片段 {chunk.chunk_id} 返回了空向量、零向量或异常数值。")
    return [float(value) for value in vector]


def _vector_health_summary(
    manifest: _retrieval_api.RetrievalIndexManifest,
    store: _retrieval_api.RetrievalVectorStore | None,
) -> dict:
    chunks_by_id = {chunk.chunk_id: chunk for chunk in manifest.chunks}
    manifest_chunk_ids = set(chunks_by_id)
    vector_ids = set(store.vectors) if store else set()
    raw_missing_vector_count = len(manifest_chunk_ids - vector_ids)
    invalid_vector_ids: set[str] = set()
    stale_content_vector_ids: set[str] = set()
    dimension_by_id: dict[str, int] = {}

    if store:
        for chunk_id in manifest_chunk_ids & vector_ids:
            vector = store.vectors.get(chunk_id)
            if not _is_reusable_vector(vector):
                invalid_vector_ids.add(chunk_id)
                continue
            dimension_by_id[chunk_id] = len(vector)
            if store.content_hashes.get(chunk_id) != _retrieval_api._retrieval_chunk_content_hash(chunks_by_id[chunk_id]):
                stale_content_vector_ids.add(chunk_id)

    dimension_counts = _retrieval_api.Counter(dimension_by_id.values())
    canonical_dimension = 0
    if dimension_counts:
        canonical_dimension = min(
            dimension_counts,
            key=lambda dimension: (-dimension_counts[dimension], dimension),
        )
    inconsistent_dimension_ids = {
        chunk_id
        for chunk_id, dimension in dimension_by_id.items()
        if canonical_dimension and dimension != canonical_dimension
    }
    unusable_vector_ids = invalid_vector_ids | stale_content_vector_ids | inconsistent_dimension_ids
    usable_vector_ids = (manifest_chunk_ids & vector_ids) - unusable_vector_ids
    return {
        "vector_ids": vector_ids,
        "vector_dimension": canonical_dimension,
        "vector_dimension_counts": dict(sorted(dimension_counts.items())),
        "raw_missing_vector_count": raw_missing_vector_count,
        "missing_vector_count": len(manifest_chunk_ids - usable_vector_ids),
        "invalid_vector_count": len(invalid_vector_ids),
        "stale_content_vector_count": len(stale_content_vector_ids),
        "inconsistent_vector_dimension_count": len(inconsistent_dimension_ids),
        "usable_vector_count": len(usable_vector_ids),
    }


def build_vector_store(project_name: str, manifest: _retrieval_api.RetrievalIndexManifest | None = None) -> _retrieval_api.RetrievalVectorStore:
    manifest = manifest or load_retrieval_index(project_name)
    embedding_model = _retrieval_api._active_embedding_model_name()
    previous_store = load_vector_store(project_name)
    can_reuse = bool(previous_store and previous_store.embedding_model == embedding_model)
    vectors = {}
    content_hashes = {}
    generated_vectors: dict[str, list[float]] = {}
    reused_vector_count = 0
    generated_vector_count = 0
    for chunk in manifest.chunks:
        content_hash = _retrieval_api._retrieval_chunk_content_hash(chunk)
        previous_vector = previous_store.vectors.get(chunk.chunk_id) if can_reuse and previous_store else None
        previous_hash = previous_store.content_hashes.get(chunk.chunk_id) if can_reuse and previous_store else None
        if previous_hash == content_hash and _is_reusable_vector(previous_vector):
            vectors[chunk.chunk_id] = previous_vector
            reused_vector_count += 1
        else:
            generated_vector = _generate_chunk_vector(chunk)
            vectors[chunk.chunk_id] = generated_vector
            generated_vectors[chunk.chunk_id] = generated_vector
            generated_vector_count += 1
        content_hashes[chunk.chunk_id] = content_hash

    forced_full_build = len({len(vector) for vector in vectors.values()}) > 1
    if forced_full_build:
        # A provider can change an embedding model's dimension without changing
        # its configured model name.  Reusing the old dimension would silently
        # remove those chunks from semantic search, so rebuild a uniform store.
        fresh_vectors: dict[str, list[float]] = {}
        fresh_dimension = 0
        for chunk in manifest.chunks:
            vector = generated_vectors.get(chunk.chunk_id) or _generate_chunk_vector(chunk)
            if not fresh_dimension:
                fresh_dimension = len(vector)
            elif len(vector) != fresh_dimension:
                raise RuntimeError(
                    "同一次向量构建返回了不一致的维度："
                    f"期望 {fresh_dimension}，片段 {chunk.chunk_id} 返回 {len(vector)}。"
                )
            fresh_vectors[chunk.chunk_id] = vector
        vectors = fresh_vectors
        reused_vector_count = 0
        generated_vector_count = len(fresh_vectors)

    previous_vector_ids = set(previous_store.vectors) if previous_store else set()
    removed_vector_count = len(previous_vector_ids - set(vectors))

    store = _retrieval_api.RetrievalVectorStore(
        project_name=project_name,
        built_at=_retrieval_api.datetime.now().isoformat(timespec="seconds"),
        embedding_model=embedding_model,
        vectors=vectors,
        content_hashes=content_hashes,
        build_mode="incremental" if can_reuse and not forced_full_build else "full",
        reused_vector_count=reused_vector_count,
        generated_vector_count=generated_vector_count,
        removed_vector_count=removed_vector_count,
    )
    _retrieval_api.save_retrieval_vectors(project_name, store.model_dump_json(indent=2))
    return store


def load_vector_store(project_name: str) -> _retrieval_api.RetrievalVectorStore | None:
    content = _retrieval_api.load_retrieval_vectors(project_name)
    if not content.strip():
        return None
    try:
        return _retrieval_api.RetrievalVectorStore.model_validate_json(content)
    except Exception:
        return None


def inspect_retrieval_health(project_name: str) -> dict:
    issues: list[dict] = []
    try:
        manifest = load_retrieval_index(project_name)
        manifest_error = ""
    except Exception as exc:
        manifest = build_retrieval_index(project_name)
        manifest_error = str(exc)
        issues.append({
            "severity": "high",
            "message": f"索引读取失败，已尝试重建关键词索引：{exc}",
        })

    try:
        current_documents = _retrieval_api.gather_retrieval_documents(project_name)
        current_chunks: list[_retrieval_api.RetrievalChunk] = []
        for document in current_documents:
            current_chunks.extend(chunk_document(document))
        gather_error = ""
    except Exception as exc:
        current_documents = []
        current_chunks = []
        gather_error = str(exc)
        issues.append({
            "severity": "high",
            "message": f"当前资料收集失败：{exc}",
        })

    manifest_chunk_ids = {chunk.chunk_id for chunk in manifest.chunks}
    current_chunk_ids = {chunk.chunk_id for chunk in current_chunks}
    stale_chunk_count = len(manifest_chunk_ids - current_chunk_ids)
    missing_index_chunk_count = len(current_chunk_ids - manifest_chunk_ids)
    if stale_chunk_count or missing_index_chunk_count:
        issues.append({
            "severity": "medium",
            "message": f"索引与当前资料不一致：陈旧片段 {stale_chunk_count} 个，未入索引片段 {missing_index_chunk_count} 个。建议重建索引。",
        })

    store = load_vector_store(project_name)
    active_embedding_model = _retrieval_api._active_embedding_model_name()
    active_embedding_mode = _retrieval_api._active_embedding_mode()
    vector_health = _vector_health_summary(manifest, store)
    vector_ids = vector_health["vector_ids"]
    missing_vector_count = vector_health["missing_vector_count"]
    stale_vector_count = len(vector_ids - manifest_chunk_ids)
    vector_dimension = vector_health["vector_dimension"]

    if manifest.chunk_count and not manifest.embedding_enabled:
        issues.append({
            "severity": "low" if active_embedding_mode == "disabled" else "medium",
            "message": (
                "语义向量已由用户关闭，当前明确使用关键词检索。"
                if active_embedding_mode == "disabled"
                else f"当前索引没有启用语义向量，混合检索会退回关键词检索。当前配置的向量模型：{active_embedding_model or '-'}。"
            ),
        })
    elif manifest.embedding_enabled and missing_vector_count:
        issues.append({
            "severity": "medium",
            "message": f"语义向量不完整或不可用：共 {missing_vector_count} 个片段。建议重建向量索引。",
        })
    if vector_health["invalid_vector_count"]:
        issues.append({
            "severity": "medium",
            "message": f"发现 {vector_health['invalid_vector_count']} 个空向量、零向量或异常数值向量。",
        })
    if vector_health["inconsistent_vector_dimension_count"]:
        dimensions = " / ".join(
            f"{dimension} 维={count}"
            for dimension, count in vector_health["vector_dimension_counts"].items()
        )
        issues.append({
            "severity": "medium",
            "message": (
                f"发现 {vector_health['inconsistent_vector_dimension_count']} 个维度不一致的向量"
                f"（{dimensions}）。这些向量不会参与语义检索。"
            ),
        })
    if vector_health["stale_content_vector_count"]:
        issues.append({
            "severity": "medium",
            "message": f"发现 {vector_health['stale_content_vector_count']} 个内容哈希已过期的向量。建议重建向量索引。",
        })
    if stale_vector_count:
        issues.append({
            "severity": "low",
            "message": f"向量文件包含 {stale_vector_count} 个不再存在于索引中的旧向量。建议重建向量索引。",
        })
    if manifest.embedding_model and active_embedding_model and manifest.embedding_model != active_embedding_model:
        issues.append({
            "severity": "low",
            "message": f"当前配置的向量模型 `{active_embedding_model}` 与索引记录 `{manifest.embedding_model}` 不一致。切换模型后建议重建完整索引。",
        })
    if store and store.embedding_model and active_embedding_model and store.embedding_model != active_embedding_model:
        issues.append({
            "severity": "low",
            "message": f"当前配置的向量模型 `{active_embedding_model}` 与向量文件记录 `{store.embedding_model}` 不一致。建议重建完整索引。",
        })

    source_type_counts = _retrieval_api.Counter(chunk.source_type for chunk in manifest.chunks)
    scope_counts = _retrieval_api.Counter(chunk.scope for chunk in manifest.chunks)
    if manifest.chunk_count == 0:
        issues.append({
            "severity": "medium",
            "message": "当前检索索引没有任何片段。请先导入资料、确认知识或保存大纲/章节后重建索引。",
        })

    status = "healthy"
    if any(issue["severity"] == "high" for issue in issues):
        status = "error"
    elif any(issue["severity"] == "medium" for issue in issues):
        status = "warning"

    return {
        "status": status,
        "manifest_error": manifest_error,
        "gather_error": gather_error,
        "document_count": manifest.document_count,
        "chunk_count": manifest.chunk_count,
        "current_document_count": len(current_documents),
        "current_chunk_count": len(current_chunks),
        "embedding_enabled": manifest.embedding_enabled,
        "embedding_mode": active_embedding_mode,
        "embedding_model": manifest.embedding_model,
        "active_embedding_model": active_embedding_model,
        "vector_store_present": bool(store),
        "vector_count": len(vector_ids),
        "usable_vector_count": vector_health["usable_vector_count"],
        "vector_dimension": vector_dimension,
        "vector_dimension_counts": vector_health["vector_dimension_counts"],
        "invalid_vector_count": vector_health["invalid_vector_count"],
        "inconsistent_vector_dimension_count": vector_health["inconsistent_vector_dimension_count"],
        "stale_content_vector_count": vector_health["stale_content_vector_count"],
        "raw_missing_vector_count": vector_health["raw_missing_vector_count"],
        "missing_vector_count": missing_vector_count,
        "stale_vector_count": stale_vector_count,
        "stale_chunk_count": stale_chunk_count,
        "missing_index_chunk_count": missing_index_chunk_count,
        "built_at": manifest.built_at,
        "vector_built_at": store.built_at if store else "",
        "vector_model": store.embedding_model if store else "",
        "vector_build_mode": store.build_mode if store else "",
        "reused_vector_count": store.reused_vector_count if store else 0,
        "generated_vector_count": store.generated_vector_count if store else 0,
        "removed_vector_count": store.removed_vector_count if store else 0,
        "source_type_counts": dict(source_type_counts.most_common()),
        "scope_counts": dict(scope_counts.most_common()),
        "issues": issues,
    }


def build_retrieval_index(project_name: str) -> _retrieval_api.RetrievalIndexManifest:
    documents = _retrieval_api.gather_retrieval_documents(project_name)
    chunks: list[_retrieval_api.RetrievalChunk] = []
    for document in documents:
        chunks.extend(chunk_document(document))

    manifest = _retrieval_api.RetrievalIndexManifest(
        project_name=project_name,
        built_at=_retrieval_api.datetime.now().isoformat(timespec="seconds"),
        document_count=len(documents),
        chunk_count=len(chunks),
        embedding_model=_retrieval_api._active_embedding_model_name(),
        embedding_enabled=False,
        documents=documents,
        chunks=chunks,
    )
    _retrieval_api.save_retrieval_manifest(project_name, manifest.model_dump_json(indent=2))
    return manifest


def rebuild_retrieval_assets(project_name: str, *, build_vectors: bool = True) -> _retrieval_api.RetrievalIndexManifest:
    manifest = build_retrieval_index(project_name)
    if not build_vectors or not _retrieval_api._active_embedding_model_name():
        return manifest
    try:
        build_vector_store(project_name, manifest)
        manifest.embedding_enabled = True
        _retrieval_api.save_retrieval_manifest(project_name, manifest.model_dump_json(indent=2))
    except Exception as exc:
        _retrieval_api.logging.getLogger("novelforge.retrieval").warning(
            "Vector index build failed for %s; lexical index remains available: %s",
            project_name,
            exc,
        )
        manifest.embedding_enabled = False
        _retrieval_api.save_retrieval_manifest(project_name, manifest.model_dump_json(indent=2))
    return manifest


def _refresh_manifest_knowledge_metadata(project_name: str, manifest: _retrieval_api.RetrievalIndexManifest) -> _retrieval_api.RetrievalIndexManifest:
    metadata_by_doc_id = _retrieval_api._knowledge_metadata_by_doc_id(project_name)
    if not metadata_by_doc_id:
        return manifest
    changed = False
    for document in manifest.documents:
        if not document.source_type.startswith("knowledge_"):
            continue
        metadata = metadata_by_doc_id.get(document.doc_id)
        if not metadata:
            continue
        merged = {**document.metadata, **metadata}
        if merged != document.metadata:
            document.metadata = merged
            changed = True
    for chunk in manifest.chunks:
        if not chunk.source_type.startswith("knowledge_"):
            continue
        metadata = metadata_by_doc_id.get(chunk.document_id)
        if not metadata:
            continue
        merged = {**chunk.metadata, **metadata}
        if merged != chunk.metadata:
            chunk.metadata = merged
            changed = True
    if changed:
        _retrieval_api.save_retrieval_manifest(project_name, manifest.model_dump_json(indent=2))
    return manifest


def _is_story_scoped_source_type(source_type: str) -> bool:
    normalized = str(source_type or "")
    return normalized in _retrieval_api.STORY_SCOPED_SOURCE_TYPES or normalized.startswith("analysis_")


def _manifest_needs_story_scope_rebuild(manifest: _retrieval_api.RetrievalIndexManifest) -> bool:
    seen_doc_ids: set[str] = set()
    for document in manifest.documents:
        if document.doc_id in seen_doc_ids:
            return True
        seen_doc_ids.add(document.doc_id)
        if _is_story_scoped_source_type(document.source_type) and not str(document.metadata.get("story_id") or "").strip():
            return True
    for chunk in manifest.chunks:
        if _is_story_scoped_source_type(chunk.source_type) and not str(chunk.metadata.get("story_id") or "").strip():
            return True
    return False


def load_retrieval_index(project_name: str) -> _retrieval_api.RetrievalIndexManifest:
    content = _retrieval_api.load_retrieval_manifest(project_name)
    if not content.strip():
        return build_retrieval_index(project_name)
    try:
        manifest = _retrieval_api.RetrievalIndexManifest.model_validate_json(content)
        retrieval_stale = False
        try:
            from novelforge.services.memory import load_knowledge_center_index_state

            state = load_knowledge_center_index_state(project_name)
            retrieval_stale = (
                str(state.get("retrieval_status") or "") in {"queued", "running"}
                or int(state.get("requested_revision") or 0)
                > int(state.get("indexed_revision") or 0)
            )
        except Exception:
            pass
        if retrieval_stale or _manifest_needs_story_scope_rebuild(manifest):
            return build_retrieval_index(project_name)
        return _refresh_manifest_knowledge_metadata(project_name, manifest)
    except Exception:
        return build_retrieval_index(project_name)
