"""Implementation slice for the retrieval facade: sources."""

from __future__ import annotations

from novelforge.services import retrieval as _retrieval_api

def ingest_external_source_file(project_name: str, source_name: str, content: str, *, overwrite: bool = True) -> str:
    safe_name = _retrieval_api.re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "_", source_name).strip("_") or "external_source"
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
    target.write_text(content, encoding="utf-8")
    return target.relative_to(source_root).as_posix()


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
