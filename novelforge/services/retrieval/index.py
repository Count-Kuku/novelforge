"""Implementation slice for the retrieval facade: index."""

from __future__ import annotations

from novelforge.services import retrieval as _retrieval_api

def chunk_document(document: _retrieval_api.RetrievalDocument) -> list[_retrieval_api.RetrievalChunk]:
    if document.source_type in _retrieval_api.STRUCTURED_SOURCE_TYPES or document.source_type.startswith("knowledge_") or document.source_type.startswith("entity_"):
        parts = [(document.title, document.content.strip())] if document.content.strip() else []
    elif document.source_type.startswith("analysis_"):
        parts = _retrieval_api._chunk_markdown_sections(document.content)
    elif document.source_type in {"outline", "chapter_outline", "arc_chapter_plan", "evaluation_chapter", "review_markdown", "external_source", "external_character_sheet", "external_location_sheet", "external_organization_sheet", "external_timeline_note", "external_canon_event", "external_world_rule", "external_artifact_note"}:
        parts = _retrieval_api._chunk_markdown_sections(document.content)
    elif document.source_type == "chapter_content":
        parts = [(document.title, chunk) for chunk in _retrieval_api._chunk_by_paragraphs(document.content)]
    else:
        parts = [(document.title, chunk) for chunk in _retrieval_api._split_long_text(document.content)]

    if not parts:
        return []

    result = []
    for index, (section_title, chunk_text) in enumerate(parts, start=1):
        chunk_title = section_title or document.title
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
            },
        ))
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


def build_vector_store(project_name: str, manifest: _retrieval_api.RetrievalIndexManifest | None = None) -> _retrieval_api.RetrievalVectorStore:
    manifest = manifest or load_retrieval_index(project_name)
    vectors = {}
    content_hashes = {}
    for chunk in manifest.chunks:
        vectors[chunk.chunk_id] = _retrieval_api.get_embedding(f"{chunk.title}\n{chunk.content}")
        content_hashes[chunk.chunk_id] = _retrieval_api._retrieval_chunk_content_hash(chunk)

    store = _retrieval_api.RetrievalVectorStore(
        project_name=project_name,
        built_at=_retrieval_api.datetime.now().isoformat(timespec="seconds"),
        embedding_model=_retrieval_api._active_embedding_model_name(),
        vectors=vectors,
        content_hashes=content_hashes,
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
    vector_ids = set(store.vectors.keys()) if store else set()
    missing_vector_count = len(manifest_chunk_ids - vector_ids)
    stale_vector_count = len(vector_ids - manifest_chunk_ids)
    vector_dimension = 0
    if store and store.vectors:
        first_vector = next(iter(store.vectors.values()), [])
        vector_dimension = len(first_vector) if isinstance(first_vector, list) else 0

    if manifest.chunk_count and not manifest.embedding_enabled:
        issues.append({
            "severity": "medium",
            "message": f"当前索引没有启用语义向量，混合检索会退回关键词检索。当前配置的向量模型：{active_embedding_model or '-'}。",
        })
    elif manifest.embedding_enabled and missing_vector_count:
        issues.append({
            "severity": "medium",
            "message": f"语义向量不完整：缺少 {missing_vector_count} 个片段向量。建议重建向量索引。",
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
        "embedding_model": manifest.embedding_model,
        "active_embedding_model": active_embedding_model,
        "vector_store_present": bool(store),
        "vector_count": len(vector_ids),
        "vector_dimension": vector_dimension,
        "missing_vector_count": missing_vector_count,
        "stale_vector_count": stale_vector_count,
        "stale_chunk_count": stale_chunk_count,
        "missing_index_chunk_count": missing_index_chunk_count,
        "built_at": manifest.built_at,
        "vector_built_at": store.built_at if store else "",
        "vector_model": store.embedding_model if store else "",
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
    if not build_vectors:
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
        if _manifest_needs_story_scope_rebuild(manifest):
            return build_retrieval_index(project_name)
        return _refresh_manifest_knowledge_metadata(project_name, manifest)
    except Exception:
        return build_retrieval_index(project_name)
