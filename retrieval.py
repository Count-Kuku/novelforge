from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from llm import get_embedding
from memory import (
    load_arc_metadata,
    load_arc_outline,
    load_analysis_report,
    load_chapter,
    load_chapter_outline,
    load_chapter_outline_metadata,
    load_memory,
    load_outline,
    load_volume_outline,
    load_volume_metadata,
    load_review,
    load_review_json,
    list_arcs,
    list_volumes,
    load_retrieval_manifest,
    load_retrieval_vectors,
    project_path,
    retrieval_sources_path,
    save_retrieval_manifest,
    save_retrieval_vectors,
)
from schemas import RetrievalChunk, RetrievalDocument, RetrievalHit, RetrievalIndexManifest, RetrievalVectorStore


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\-\u4e00-\u9fff]{2,}")
DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 150
DEFAULT_TOP_K = 6
DEFAULT_EMBEDDING_MODEL = os.getenv("LLM_EMBEDDING_MODEL") or os.getenv("EMBEDDING_MODEL") or "text-embedding-3-small"
AUTHORITY_WEIGHTS = {
    "project": 2.0,
    "official": 1.5,
    "curated": 1.0,
    "community": 0.5,
    "unknown": 0.0,
}
STRUCTURED_SOURCE_TYPES = {
    "memory_character",
    "memory_world",
    "memory_au_rule",
    "memory_relationship",
    "memory_timeline",
    "memory_foreshadowing",
    "memory_active_constraint",
    "chapter_summary",
    "review_summary",
    "review_issue",
    "review_characters_check",
    "review_world_check",
    "review_timeline_check",
    "review_foreshadowing_check",
}


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def _split_long_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks = []
    start = 0
    step = max(chunk_size - overlap, 1)
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(cleaned):
            break
        start += step
    return chunks


def _split_markdown_sections(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_title = ""
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if current_title or current_lines:
                sections.append((current_title, current_lines))
            current_title = stripped.lstrip("#").strip()
            current_lines = []
            continue
        current_lines.append(line)

    if current_title or current_lines:
        sections.append((current_title, current_lines))

    result = []
    for title, section_lines in sections:
        body = "\n".join(section_lines).strip()
        if title or body:
            result.append((title, body))
    return result


def _split_paragraph_blocks(text: str) -> list[str]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n+", text) if block.strip()]
    return blocks


def _chunk_by_paragraphs(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    blocks = _split_paragraph_blocks(text)
    if not blocks:
        return _split_long_text(text, chunk_size=chunk_size, overlap=overlap)

    chunks = []
    current = []
    current_length = 0

    for block in blocks:
        block_length = len(block)
        if current and current_length + block_length + 2 > chunk_size:
            combined = "\n\n".join(current).strip()
            if combined:
                chunks.append(combined)

            if overlap > 0 and current:
                overlap_blocks = []
                overlap_length = 0
                for item in reversed(current):
                    item_length = len(item)
                    if overlap_blocks and overlap_length + item_length > overlap:
                        break
                    overlap_blocks.insert(0, item)
                    overlap_length += item_length
                current = overlap_blocks[:]
                current_length = sum(len(item) for item in current)
            else:
                current = []
                current_length = 0

        current.append(block)
        current_length += block_length + 2

    if current:
        combined = "\n\n".join(current).strip()
        if combined:
            chunks.append(combined)

    return chunks or _split_long_text(text, chunk_size=chunk_size, overlap=overlap)


def _chunk_markdown_sections(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[tuple[str, str]]:
    sections = _split_markdown_sections(text)
    if not sections:
        return [("", chunk) for chunk in _chunk_by_paragraphs(text, chunk_size=chunk_size, overlap=overlap)]

    result: list[tuple[str, str]] = []
    for title, body in sections:
        if not body.strip():
            continue
        paragraph_chunks = _chunk_by_paragraphs(body, chunk_size=chunk_size, overlap=overlap)
        if paragraph_chunks:
            result.extend([(title, chunk) for chunk in paragraph_chunks])
        else:
            result.append((title, body.strip()))
    return result


def _document_id(source_type: str, project_name: str, identifier: str) -> str:
    return f"{project_name}:{source_type}:{identifier}"


def _make_document(
    project_name: str,
    source_type: str,
    identifier: str,
    title: str,
    content: str,
    *,
    scope: str = "project",
    chapter_no: int | None = None,
    path: str = "",
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> RetrievalDocument | None:
    normalized_content = _normalize_whitespace(content)
    if not normalized_content:
        return None
    return RetrievalDocument(
        doc_id=_document_id(source_type, project_name, identifier),
        project_name=project_name,
        source_type=source_type,
        scope=scope,
        title=title,
        content=normalized_content,
        chapter_no=chapter_no,
        path=path,
        tags=tags or [],
        metadata=metadata or {},
    )


def _infer_authority(scope: str, metadata: dict | None) -> str:
    if isinstance(metadata, dict):
        authority = str(metadata.get("authority", "")).strip().lower()
        if authority:
            return authority
    if scope == "project":
        return "project"
    return "unknown"


def _documents_from_memory(project_name: str) -> list[RetrievalDocument]:
    memory = load_memory(project_name)
    documents: list[RetrievalDocument] = []

    for index, item in enumerate(memory.get("characters", []), start=1):
        doc = _make_document(
            project_name,
            "memory_character",
            str(index),
            f"Character {index}",
            str(item),
            tags=["character"],
            metadata={"memory_field": "characters", "authority": "project"},
        )
        if doc:
            documents.append(doc)

    canon_mode = str(memory.get("canon_mode", "")).strip()
    if canon_mode:
        doc = _make_document(
            project_name,
            "memory_world",
            "canon_mode",
            "Canon Mode",
            canon_mode,
            tags=["canon_mode", "world"],
            metadata={"memory_field": "canon_mode", "authority": "project"},
        )
        if doc:
            documents.append(doc)

    for index, item in enumerate(memory.get("au_rules", []), start=1):
        doc = _make_document(
            project_name,
            "memory_au_rule",
            str(index),
            f"AU Rule {index}",
            str(item),
            tags=["au_rule"],
            metadata={"memory_field": "au_rules", "authority": "project"},
        )
        if doc:
            documents.append(doc)

    for index, item in enumerate(memory.get("relationships", []), start=1):
        doc = _make_document(
            project_name,
            "memory_relationship",
            str(index),
            f"Relationship {index}",
            str(item),
            tags=["relationship"],
            metadata={"memory_field": "relationships", "authority": "project"},
        )
        if doc:
            documents.append(doc)

    for field_name, source_type, tag in [
        ("world", "memory_world", "world"),
        ("timeline", "memory_timeline", "timeline"),
        ("foreshadowing", "memory_foreshadowing", "foreshadowing"),
    ]:
        for index, item in enumerate(memory.get(field_name, []), start=1):
            doc = _make_document(
                project_name,
                source_type,
                str(index),
                f"{field_name.title()} {index}",
                str(item),
                tags=[tag],
                metadata={"memory_field": field_name, "authority": "project"},
            )
            if doc:
                documents.append(doc)

    for item in memory.get("chapter_summaries", []):
        if not isinstance(item, dict):
            continue
        chapter_no = item.get("chapter_no")
        summary = item.get("summary", "")
        if not summary:
            continue
        doc = _make_document(
            project_name,
            "chapter_summary",
            str(chapter_no),
            f"Chapter {chapter_no:03d} Summary" if isinstance(chapter_no, int) else "Chapter Summary",
            summary,
            chapter_no=chapter_no if isinstance(chapter_no, int) else None,
            tags=["summary"],
            metadata={"memory_field": "chapter_summaries", "authority": "project"},
        )
        if doc:
            documents.append(doc)

    for index, item in enumerate(memory.get("active_constraints", []), start=1):
        doc = _make_document(
            project_name,
            "memory_active_constraint",
            str(index),
            f"Active Constraint {index}",
            str(item),
            tags=["constraint"],
            metadata={"memory_field": "active_constraints", "authority": "project"},
        )
        if doc:
            documents.append(doc)

    return documents


def _documents_from_project_files(project_name: str) -> list[RetrievalDocument]:
    documents: list[RetrievalDocument] = []
    base_path = project_path(project_name)

    outline = load_outline(project_name)
    doc = _make_document(
        project_name,
        "outline",
        "outline",
        "Project Outline",
        outline,
        path=str(base_path / "outline.md"),
        tags=["outline"],
        metadata={"authority": "project"},
    )
    if doc:
        documents.append(doc)

    for volume in list_volumes(project_name):
        volume_no = int(volume.get("volume_no", 0))
        volume_outline = load_volume_outline(project_name, volume_no)
        volume_meta = load_volume_metadata(project_name, volume_no)
        doc = _make_document(
            project_name,
            "volume_outline",
            f"volume_{volume_no:03d}",
            volume_meta.get("title") or f"Volume {volume_no:03d}",
            volume_outline,
            path=str(base_path / "volumes" / f"volume_{volume_no:03d}.md"),
            tags=["volume_outline", f"volume_{volume_no:03d}"],
            metadata={
                "authority": "project",
                "volume_no": volume_no,
                "status": volume_meta.get("status", "draft"),
                "summary": volume_meta.get("summary", ""),
            },
        )
        if doc:
            documents.append(doc)

    for arc in list_arcs(project_name):
        arc_no = int(arc.get("arc_no", 0))
        arc_outline = load_arc_outline(project_name, arc_no)
        arc_meta = load_arc_metadata(project_name, arc_no)
        doc = _make_document(
            project_name,
            "arc_outline",
            f"arc_{arc_no:03d}",
            arc_meta.get("title") or f"Arc {arc_no:03d}",
            arc_outline,
            path=str(base_path / "arcs" / f"arc_{arc_no:03d}.md"),
            tags=["arc_outline", f"arc_{arc_no:03d}"],
            metadata={
                "authority": "project",
                "arc_no": arc_no,
                "volume_no": arc_meta.get("volume_no"),
                "status": arc_meta.get("status", "draft"),
                "summary": arc_meta.get("summary", ""),
                "estimated_chapter_count": arc_meta.get("estimated_chapter_count"),
                "target_word_count_range": arc_meta.get("target_word_count_range", ""),
            },
        )
        if doc:
            documents.append(doc)

    chapter_outline_dir = base_path / "chapter_outlines"
    if chapter_outline_dir.exists():
        for file in sorted(chapter_outline_dir.glob("chapter_*.md")):
            match = re.search(r"chapter_(\d+)\.md$", file.name)
            chapter_no = int(match.group(1)) if match else None
            chapter_meta = load_chapter_outline_metadata(project_name, chapter_no) if chapter_no is not None else {}
            doc = _make_document(
                project_name,
                "chapter_outline",
                file.stem,
                f"Chapter {chapter_no:03d} Outline" if chapter_no is not None else file.stem,
                load_chapter_outline(project_name, chapter_no) if chapter_no is not None else file.read_text(encoding="utf-8"),
                chapter_no=chapter_no,
                path=str(file),
                tags=["chapter_outline"],
                metadata={
                    "authority": "project",
                    "volume_no": chapter_meta.get("volume_no"),
                    "arc_no": chapter_meta.get("arc_no"),
                },
            )
            if doc:
                documents.append(doc)

    chapters_dir = base_path / "chapters"
    if chapters_dir.exists():
        for file in sorted(chapters_dir.glob("chapter_*.md")):
            match = re.search(r"chapter_(\d+)\.md$", file.name)
            chapter_no = int(match.group(1)) if match else None
            content = load_chapter(project_name, chapter_no) if chapter_no is not None else file.read_text(encoding="utf-8")
            doc = _make_document(
                project_name,
                "chapter_content",
                file.stem,
                f"Chapter {chapter_no:03d} Content" if chapter_no is not None else file.stem,
                content,
                chapter_no=chapter_no,
                path=str(file),
                tags=["chapter"],
                metadata={"authority": "project"},
            )
            if doc:
                documents.append(doc)

    reviews_dir = base_path / "reviews"
    if reviews_dir.exists():
        for file in sorted(reviews_dir.glob("chapter_*.json")):
            match = re.search(r"chapter_(\d+)\.json$", file.name)
            if not match:
                continue
            chapter_no = int(match.group(1))
            review_json = load_review_json(project_name, chapter_no)
            if not review_json:
                continue
            summary_doc = _make_document(
                project_name,
                "review_summary",
                f"summary_{chapter_no:03d}",
                f"Chapter {chapter_no:03d} Review Summary",
                review_json.get("summary", ""),
                chapter_no=chapter_no,
                path=str(file),
                tags=["review", "summary", review_json.get("status", "")],
                metadata={"status": review_json.get("status", ""), "authority": "project"},
            )
            if summary_doc:
                documents.append(summary_doc)

            for index, issue in enumerate(review_json.get("issues", []), start=1):
                doc = _make_document(
                    project_name,
                    "review_issue",
                    f"{chapter_no:03d}_{index:02d}",
                    f"Chapter {chapter_no:03d} Review Issue {index}",
                    issue,
                    chapter_no=chapter_no,
                    path=str(file),
                    tags=["review", "issue"],
                    metadata={"status": review_json.get("status", ""), "authority": "project"},
                )
                if doc:
                    documents.append(doc)

            for field_name, label in [
                ("characters", "review_characters_check"),
                ("world", "review_world_check"),
                ("timeline", "review_timeline_check"),
                ("foreshadowing", "review_foreshadowing_check"),
            ]:
                content = review_json.get("consistency_checks", {}).get(field_name, "")
                doc = _make_document(
                    project_name,
                    label,
                    f"{chapter_no:03d}_{field_name}",
                    f"Chapter {chapter_no:03d} {field_name.title()} Check",
                    content,
                    chapter_no=chapter_no,
                    path=str(file),
                    tags=["review", field_name],
                    metadata={"status": review_json.get("status", ""), "authority": "project"},
                )
                if doc:
                    documents.append(doc)

        for file in sorted(reviews_dir.glob("chapter_*.md")):
            match = re.search(r"chapter_(\d+)\.md$", file.name)
            chapter_no = int(match.group(1)) if match else None
            content = load_review(project_name, chapter_no) if chapter_no is not None else file.read_text(encoding="utf-8")
            doc = _make_document(
                project_name,
                "review_markdown",
                file.stem,
                f"Chapter {chapter_no:03d} Review Markdown" if chapter_no is not None else file.stem,
                content,
                chapter_no=chapter_no,
                path=str(file),
                tags=["review", "markdown"],
                metadata={"authority": "project"},
            )
            if doc:
                documents.append(doc)

    analysis_dir = base_path / "analysis"
    if analysis_dir.exists():
        for file in sorted(analysis_dir.glob("*.md")):
            match = re.search(r"(.+)_chapter_(\d+)\.md$", file.name)
            analysis_type = match.group(1) if match else file.stem
            chapter_no = int(match.group(2)) if match else None
            content = load_analysis_report(project_name, analysis_type, chapter_no) if chapter_no is not None else file.read_text(encoding="utf-8")
            for section_title, section_body in _split_markdown_sections(content):
                identifier = f"{analysis_type}_{chapter_no or 'na'}_{section_title or 'body'}"
                doc = _make_document(
                    project_name,
                    f"analysis_{analysis_type}",
                    identifier,
                    section_title or f"{analysis_type} analysis",
                    section_body,
                    chapter_no=chapter_no,
                    path=str(file),
                    tags=["analysis", analysis_type],
                    metadata={"authority": "project"},
                )
                if doc:
                    documents.append(doc)

    return documents


def _documents_from_external_sources(project_name: str) -> list[RetrievalDocument]:
    source_dir = retrieval_sources_path(project_name)
    documents: list[RetrievalDocument] = []

    for file in sorted(source_dir.rglob("*")):
        if not file.is_file() or file.suffix.lower() not in {".md", ".txt", ".json"}:
            continue

        raw_text = file.read_text(encoding="utf-8")
        scope = "reference"
        title = file.stem
        content = raw_text
        metadata = {"external_file": True}
        tags = ["external"]
        source_type = "external_source"

        if file.suffix.lower() == ".json":
            try:
                parsed = json.loads(raw_text)
                scope = str(parsed.get("scope", scope)) if isinstance(parsed, dict) else scope
                title = str(parsed.get("title", title)) if isinstance(parsed, dict) else title
                body = parsed.get("content", "") if isinstance(parsed, dict) else ""
                content = body if isinstance(body, str) and body.strip() else raw_text
                metadata.update(parsed.get("metadata", {}) if isinstance(parsed, dict) and isinstance(parsed.get("metadata"), dict) else {})
                tags.extend(parsed.get("tags", []) if isinstance(parsed, dict) and isinstance(parsed.get("tags"), list) else [])
                source_type = str(parsed.get("source_type", source_type)) if isinstance(parsed, dict) else source_type
            except Exception:
                content = raw_text

        doc = _make_document(
            project_name,
            source_type,
            file.stem,
            title,
            content,
            scope=scope if scope in {"project", "canon", "reference"} else "reference",
            path=str(file),
            tags=tags,
            metadata={**metadata, "authority": _infer_authority(scope, metadata)},
        )
        if doc:
            documents.append(doc)

    return documents


def gather_retrieval_documents(project_name: str) -> list[RetrievalDocument]:
    documents = []
    documents.extend(_documents_from_memory(project_name))
    documents.extend(_documents_from_project_files(project_name))
    documents.extend(_documents_from_external_sources(project_name))
    return documents


def chunk_document(document: RetrievalDocument) -> list[RetrievalChunk]:
    if document.source_type in STRUCTURED_SOURCE_TYPES:
        parts = [(document.title, document.content.strip())] if document.content.strip() else []
    elif document.source_type.startswith("analysis_"):
        parts = _chunk_markdown_sections(document.content)
    elif document.source_type in {"outline", "chapter_outline", "review_markdown", "external_source", "external_character_sheet", "external_location_sheet", "external_organization_sheet", "external_timeline_note", "external_canon_event", "external_world_rule", "external_artifact_note"}:
        parts = _chunk_markdown_sections(document.content)
    elif document.source_type == "chapter_content":
        parts = [(document.title, chunk) for chunk in _chunk_by_paragraphs(document.content)]
    else:
        parts = [(document.title, chunk) for chunk in _split_long_text(document.content)]

    if not parts:
        return []

    result = []
    for index, (section_title, chunk_text) in enumerate(parts, start=1):
        chunk_title = section_title or document.title
        result.append(RetrievalChunk(
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
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_vector_store(project_name: str, manifest: RetrievalIndexManifest | None = None) -> RetrievalVectorStore:
    manifest = manifest or load_retrieval_index(project_name)
    vectors = {}
    for chunk in manifest.chunks:
        vectors[chunk.chunk_id] = get_embedding(f"{chunk.title}\n{chunk.content}")

    store = RetrievalVectorStore(
        project_name=project_name,
        built_at=datetime.now().isoformat(timespec="seconds"),
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        vectors=vectors,
    )
    save_retrieval_vectors(project_name, store.model_dump_json(indent=2))
    return store


def load_vector_store(project_name: str) -> RetrievalVectorStore | None:
    content = load_retrieval_vectors(project_name)
    if not content.strip():
        return None
    try:
        return RetrievalVectorStore.model_validate_json(content)
    except Exception:
        return None


def build_retrieval_index(project_name: str) -> RetrievalIndexManifest:
    documents = gather_retrieval_documents(project_name)
    chunks: list[RetrievalChunk] = []
    for document in documents:
        chunks.extend(chunk_document(document))

    manifest = RetrievalIndexManifest(
        project_name=project_name,
        built_at=datetime.now().isoformat(timespec="seconds"),
        document_count=len(documents),
        chunk_count=len(chunks),
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        embedding_enabled=False,
        documents=documents,
        chunks=chunks,
    )
    save_retrieval_manifest(project_name, manifest.model_dump_json(indent=2))
    return manifest


def rebuild_retrieval_assets(project_name: str, *, build_vectors: bool = True) -> RetrievalIndexManifest:
    manifest = build_retrieval_index(project_name)
    if not build_vectors:
        return manifest
    try:
        build_vector_store(project_name, manifest)
        manifest.embedding_enabled = True
        save_retrieval_manifest(project_name, manifest.model_dump_json(indent=2))
    except Exception:
        manifest.embedding_enabled = False
        save_retrieval_manifest(project_name, manifest.model_dump_json(indent=2))
    return manifest


def load_retrieval_index(project_name: str) -> RetrievalIndexManifest:
    content = load_retrieval_manifest(project_name)
    if not content.strip():
        return build_retrieval_index(project_name)
    try:
        return RetrievalIndexManifest.model_validate_json(content)
    except Exception:
        return build_retrieval_index(project_name)


def _expand_query_terms(query: str) -> list[str]:
    terms = _tokenize(query)
    unique_terms = []
    seen = set()
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        unique_terms.append(term)
    return unique_terms


def _score_chunk(chunk: RetrievalChunk, query_terms: list[str]) -> tuple[float, list[str]]:
    content_terms = _tokenize(f"{chunk.title} {chunk.content} {' '.join(chunk.tags)}")
    if not content_terms:
        return 0.0, []

    counter = Counter(content_terms)
    matched_terms = []
    score = 0.0
    for term in query_terms:
        count = counter.get(term, 0)
        if count <= 0:
            continue
        matched_terms.append(term)
        score += 2.0 + min(count, 4) * 0.5

    if not matched_terms:
        return 0.0, []

    if chunk.scope == "project":
        score += 1.5
    elif chunk.scope == "canon":
        score += 1.0

    if chunk.source_type.startswith("memory_"):
        score += 0.5
    if chunk.source_type in {"review_issue", "chapter_summary"}:
        score += 0.25

    authority = str(chunk.metadata.get("authority", "")).strip().lower()
    score += AUTHORITY_WEIGHTS.get(authority, 0.0)

    return score, matched_terms


def _semantic_scores(project_name: str, query: str, chunks: list[RetrievalChunk]) -> dict[str, float]:
    store = load_vector_store(project_name)
    if not store or not store.vectors:
        return {}

    query_vector = get_embedding(query)
    scores = {}
    for chunk in chunks:
        vector = store.vectors.get(chunk.chunk_id)
        if not vector:
            continue
        scores[chunk.chunk_id] = _cosine_similarity(query_vector, vector)
    return scores


def _rerank_hits(hits: list[RetrievalHit]) -> list[RetrievalHit]:
    reranked = []
    for hit in hits:
        chunk = hit.chunk
        authority = str(chunk.metadata.get("authority", "unknown") or "unknown").strip().lower()
        rerank_bonus = 0.0

        if hit.semantic_score >= 0.55:
            rerank_bonus += 0.6
        elif hit.semantic_score >= 0.35:
            rerank_bonus += 0.3

        if chunk.scope == "project":
            rerank_bonus += 0.4
        if authority == "official":
            rerank_bonus += 0.3
        elif authority == "curated":
            rerank_bonus += 0.15

        adjusted_score = hit.score + rerank_bonus
        reranked.append(hit.model_copy(update={"score": adjusted_score}))

    reranked.sort(key=lambda item: (-item.score, -item.semantic_score, -item.lexical_score, item.chunk.source_type, item.chunk.chapter_no or 0, item.chunk.chunk_id))
    return reranked


def retrieve_context(
    project_name: str,
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    allowed_scopes: list[str] | None = None,
    allowed_source_types: list[str] | None = None,
    retrieval_mode: str = "hybrid",
) -> list[RetrievalHit]:
    index = load_retrieval_index(project_name)
    query_terms = _expand_query_terms(query)
    if not query_terms and retrieval_mode == "lexical":
        return []

    scope_filter = set(allowed_scopes or ["project", "canon", "reference"])
    source_filter = set(allowed_source_types or [])

    filtered_chunks = []
    for chunk in index.chunks:
        if chunk.scope not in scope_filter:
            continue
        if source_filter and chunk.source_type not in source_filter:
            continue
        filtered_chunks.append(chunk)

    semantic_scores = {}
    semantic_enabled = retrieval_mode in {"semantic", "hybrid"}
    if semantic_enabled:
        try:
            semantic_scores = _semantic_scores(project_name, query, filtered_chunks)
        except Exception:
            semantic_scores = {}

    hits = []
    for chunk in filtered_chunks:
        lexical_score, matched_terms = _score_chunk(chunk, query_terms) if query_terms else (0.0, [])
        semantic_score = semantic_scores.get(chunk.chunk_id, 0.0)

        if retrieval_mode == "lexical":
            final_score = lexical_score
        elif retrieval_mode == "semantic":
            final_score = semantic_score
        else:
            final_score = lexical_score + semantic_score * 4.0

        if final_score <= 0:
            continue
        hits.append(RetrievalHit(
            chunk=chunk,
            score=final_score,
            lexical_score=lexical_score,
            semantic_score=semantic_score,
            retrieval_mode=retrieval_mode if semantic_scores else "lexical",
            matched_terms=matched_terms,
        ))

    hits = _rerank_hits(hits)
    return hits[:top_k]


def format_retrieval_context(hits: list[RetrievalHit]) -> str:
    if not hits:
        return "未检索到额外上下文。"

    lines = ["以下为检索到的相关上下文，请优先参考与当前任务直接相关的内容："]
    for index, hit in enumerate(hits, start=1):
        chunk = hit.chunk
        header = f"[{index}] {chunk.source_type} / mode={hit.retrieval_mode} / score={hit.score:.2f}"
        if chunk.chapter_no is not None:
            header += f" / chapter {chunk.chapter_no:03d}"
        if chunk.scope != "project":
            header += f" / scope={chunk.scope}"
        if chunk.title:
            header += f" / {chunk.title}"
        lines.append(header)
        lines.append(chunk.content)
    return "\n".join(lines)


def ingest_external_source_file(project_name: str, source_name: str, content: str):
    safe_name = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "_", source_name).strip("_") or "external_source"
    try:
        parsed = json.loads(content)
        suffix = ".json" if isinstance(parsed, dict) else ".md"
    except Exception:
        suffix = ".md"
    target = retrieval_sources_path(project_name) / f"{safe_name}{suffix}"
    target.write_text(content, encoding="utf-8")


def build_structured_external_source_payload(
    *,
    source_type: str,
    scope: str,
    title: str,
    summary: str,
    content: str,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    extra_fields: dict | None = None,
) -> dict:
    tags = [str(item).strip() for item in (tags or []) if str(item).strip()]
    metadata = metadata.copy() if isinstance(metadata, dict) else {}
    extra_fields = extra_fields.copy() if isinstance(extra_fields, dict) else {}

    sections = []
    if summary.strip():
        sections.append("# Summary\n\n" + summary.strip())
    if content.strip():
        sections.append("# Details\n\n" + content.strip())
    for key, value in extra_fields.items():
        cleaned = str(value).strip()
        if cleaned:
            section_title = key.replace("_", " ").title()
            sections.append(f"# {section_title}\n\n{cleaned}")

    return {
        "source_type": source_type,
        "scope": scope,
        "title": title.strip(),
        "content": "\n\n".join(section for section in sections if section.strip()),
        "tags": tags,
        "metadata": metadata,
    }
