"""Implementation slice for the retrieval facade: sources."""

from __future__ import annotations

from novelforge.services import retrieval as _retrieval_api

def ingest_external_source_file(
    project_name: str,
    source_name: str,
    content: str,
    *,
    overwrite: bool = True,
    return_record: bool = False,
) -> str | dict:
    safe_name = _retrieval_api.re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "_", source_name).strip("_") or "external_source"
    parsed = {}
    try:
        parsed = _retrieval_api.json.loads(content)
        suffix = ".json" if isinstance(parsed, dict) else ".md"
    except Exception:
        suffix = ".md"
    source_root = _retrieval_api.retrieval_sources_path(project_name)
    target = source_root / f"{safe_name}{suffix}"
    if not overwrite:
        counter = 2
        while target.exists():
            target = source_root / f"{safe_name}_{counter:02d}{suffix}"
            counter += 1
    previous_content = target.read_bytes() if target.exists() and target.is_file() else None
    target.write_text(content, encoding="utf-8")
    relative_path = target.relative_to(source_root).as_posix()
    parsed_payload = parsed if isinstance(parsed, dict) else {}
    metadata = parsed_payload.get("metadata") if isinstance(parsed_payload.get("metadata"), dict) else {}
    authority_name = str(metadata.get("authority") or "unknown").strip().lower()
    authority_score = {
        "project": 1.0,
        "official": 0.9,
        "curated": 0.75,
        "community": 0.45,
        "unknown": 0.0,
    }.get(authority_name, 0.0)
    try:
        source_record = _retrieval_api.sync_retrieval_source_file_record(
            project_name,
            relative_path=relative_path,
            title=str(parsed_payload.get("title") or target.name),
            content_hash=_retrieval_api.sha256(content.encode("utf-8")).hexdigest(),
            source_type=str(parsed_payload.get("source_type") or "external_source"),
            authority=authority_score,
            metadata={
                **metadata,
                "relative_path": relative_path,
                "scope": str(parsed_payload.get("scope") or "reference"),
                "char_count": len(str(parsed_payload.get("content") or content)),
                "content": str(parsed_payload.get("content") or content),
            },
        )
    except Exception:
        # Keep the file system and DB source ledger aligned if the authority
        # write fails after a local overwrite.
        if previous_content is None:
            target.unlink(missing_ok=True)
        else:
            target.write_bytes(previous_content)
        raise
    result = {"relative_path": relative_path, **dict(source_record or {})}
    return result if return_record else relative_path


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
