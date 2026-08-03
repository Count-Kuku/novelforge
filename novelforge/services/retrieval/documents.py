"""Implementation slice for the retrieval facade: documents."""

from __future__ import annotations

from novelforge.services import retrieval as _retrieval_api

def _documents_from_memory(project_name: str) -> list[_retrieval_api.RetrievalDocument]:
    memory = _retrieval_api.load_memory(project_name)
    documents: list[_retrieval_api.RetrievalDocument] = []

    for index, item in enumerate(memory.get("characters", []), start=1):
        doc = _retrieval_api._make_document(
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
        doc = _retrieval_api._make_document(
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
        doc = _retrieval_api._make_document(
            project_name,
            "memory_au_rule",
            str(index),
            f"架空规则 {index}",
            str(item),
            tags=["au_rule"],
            metadata={"memory_field": "au_rules", "authority": "project"},
        )
        if doc:
            documents.append(doc)

    for index, item in enumerate(memory.get("relationships", []), start=1):
        doc = _retrieval_api._make_document(
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
            doc = _retrieval_api._make_document(
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
        doc = _retrieval_api._make_document(
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
        doc = _retrieval_api._make_document(
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

    for field_name, source_type, tag in [
        ("locations", "memory_location", "location"),
        ("organizations", "memory_organization", "organization"),
        ("power_systems", "memory_power_system", "power_system"),
    ]:
        for index, item in enumerate(memory.get(field_name, []), start=1):
            doc = _retrieval_api._make_document(
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

    for index, item in enumerate(memory.get("relationship_graph", []), start=1):
        if isinstance(item, dict):
            content = f"{item.get('source', '')} -> {item.get('target', '')}: {item.get('relation', '')}"
        else:
            content = str(item)
        doc = _retrieval_api._make_document(
            project_name,
            "memory_relationship_graph",
            str(index),
            f"Relationship Graph {index}",
            content,
            tags=["relationship_graph"],
            metadata={"memory_field": "relationship_graph", "authority": "project"},
        )
        if doc:
            documents.append(doc)

    return documents

def _knowledge_item_retrieval_metadata(category: str, item: dict) -> dict:
    return {
        "knowledge_id": str(item.get("id") or ""),
        "knowledge_category": category,
        "authority": str(item.get("authority") or "project"),
        "source_title": str(item.get("source_title") or ""),
        "source_origin": str(item.get("source_origin") or ""),
        "confidence": item.get("confidence", 0.7),
        "status": str(item.get("status") or "confirmed"),
        "canon_status": str(item.get("canon_status") or "unknown"),
        "setting_scope": str(item.get("setting_scope") or ""),
        "setting_role": str(item.get("setting_role") or ""),
        "setting_field": str(item.get("setting_field") or ""),
        "story_id": str(item.get("story_id") or ""),
        "injection_policy": str(item.get("injection_policy") or ""),
        "version_scope": str(item.get("version_scope") or ""),
        "worldline_id": str(item.get("worldline_id") or ""),
        "worldline_label": str(item.get("worldline_label") or ""),
    }


def _knowledge_metadata_by_doc_id(project_name: str) -> dict[str, dict]:
    knowledge_base = _retrieval_api.load_knowledge_base(project_name)
    metadata_by_doc_id: dict[str, dict] = {}
    for category, items in knowledge_base.items():
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            doc_id = _retrieval_api._document_id(f"knowledge_{category}", project_name, str(item.get("id") or index))
            metadata_by_doc_id[doc_id] = _knowledge_item_retrieval_metadata(category, item)
    return metadata_by_doc_id


def _documents_from_knowledge(project_name: str) -> list[_retrieval_api.RetrievalDocument]:
    knowledge_base = _retrieval_api.load_knowledge_base(project_name)
    documents: list[_retrieval_api.RetrievalDocument] = []

    for category, items in knowledge_base.items():
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip() or f"{category}_{index:04d}"
            summary = str(item.get("summary", "")).strip()
            details = item.get("details", {}) if isinstance(item.get("details"), dict) else {}
            evidence = item.get("evidence", []) if isinstance(item.get("evidence"), list) else []
            detail_lines = [f"{key}: {value}" for key, value in details.items() if str(value).strip()]
            evidence_lines = []
            for evidence_item in evidence[:5]:
                if not isinstance(evidence_item, dict):
                    continue
                quote = str(evidence_item.get("quote", "") or evidence_item.get("note", "")).strip()
                if quote:
                    evidence_lines.append(f"evidence: {quote}")
            content = "\n".join([
                f"name: {name}",
                f"summary: {summary}",
                *detail_lines,
                *evidence_lines,
            ])
            doc = _retrieval_api._make_document(
                project_name,
                f"knowledge_{category}",
                str(item.get("id") or index),
                name,
                content,
                scope=str(item.get("scope") or "project"),
                path=str(_retrieval_api.project_path(project_name) / "knowledge" / f"{category}.json"),
                tags=[str(tag) for tag in item.get("tags", []) if str(tag).strip()] if isinstance(item.get("tags"), list) else [],
                metadata=_knowledge_item_retrieval_metadata(category, item),
            )
            if doc:
                documents.append(doc)

    return documents


def _documents_from_character_entities(project_name: str) -> list[_retrieval_api.RetrievalDocument]:
    documents: list[_retrieval_api.RetrievalDocument] = []
    for index, card in enumerate(_retrieval_api.load_character_entities(project_name), start=1):
        if not isinstance(card, dict):
            continue
        name = str(card.get("name", "")).strip() or f"角色实体卡 {index}"
        profile = card.get("profile", {}) if isinstance(card.get("profile"), dict) else {}
        profile_lines = [f"{key}: {value}" for key, value in profile.items() if str(value).strip()]
        list_fields = [
            ("relationships", "relationship"),
            ("abilities_and_items", "ability_or_item"),
            ("dialogue_style", "dialogue_style"),
            ("constraints", "constraint"),
            ("timeline", "timeline"),
        ]
        content_lines = [
            f"name: {name}",
            "aliases: " + " / ".join(str(value) for value in card.get("aliases", []) if str(value).strip()) if isinstance(card.get("aliases", []), list) else "",
            f"summary: {str(card.get('summary', '')).strip()}",
            *profile_lines,
        ]
        for field_name, label in list_fields:
            values = card.get(field_name, [])
            if not isinstance(values, list):
                continue
            for value in values:
                text = str(value or "").strip()
                if text:
                    content_lines.append(f"{label}: {text}")
        evidence = card.get("evidence", []) if isinstance(card.get("evidence"), list) else []
        for evidence_item in evidence[:5]:
            if not isinstance(evidence_item, dict):
                continue
            quote = str(evidence_item.get("quote", "") or evidence_item.get("note", "")).strip()
            if quote:
                content_lines.append(f"evidence: {quote}")
        doc = _retrieval_api._make_document(
            project_name,
            "entity_character_card",
            str(card.get("id") or index),
            name,
            "\n".join(content_lines),
            scope=str(card.get("scope") or "project"),
            path=str(_retrieval_api.project_path(project_name) / "knowledge" / "entities" / "characters.json"),
            tags=[str(tag) for tag in card.get("tags", []) if str(tag).strip()] if isinstance(card.get("tags"), list) else ["character_entity"],
            metadata={
                "entity_type": "character",
                "authority": str(card.get("authority") or "project"),
                "confidence": card.get("confidence", 0.7),
                "importance": card.get("importance", 0.5),
                "canon_status": str(card.get("canon_status") or "unknown"),
                "setting_scope": str(card.get("setting_scope") or ""),
                "story_id": str(card.get("story_id") or ""),
                "version_scope": str(card.get("version_scope") or ""),
                "worldline_id": str(card.get("worldline_id") or ""),
                "worldline_label": str(card.get("worldline_label") or ""),
                "source_knowledge_ids": card.get("source_knowledge_ids", []),
            },
        )
        if doc:
            documents.append(doc)
    return documents


def _documents_from_entity_aliases(project_name: str) -> list[_retrieval_api.RetrievalDocument]:
    documents: list[_retrieval_api.RetrievalDocument] = []
    for index, group in enumerate(_retrieval_api.load_entity_aliases(project_name), start=1):
        if not isinstance(group, dict):
            continue
        canonical_name = str(group.get("canonical_name") or "").strip()
        aliases = [str(value).strip() for value in group.get("aliases", []) if str(value).strip()] if isinstance(group.get("aliases", []), list) else []
        if not canonical_name and not aliases:
            continue
        title = canonical_name or aliases[0]
        content_lines = [
            f"canonical_name: {title}",
            f"category: {group.get('category', '')}",
            "aliases: " + " / ".join(aliases),
        ]
        if group.get("notes"):
            content_lines.append(f"notes: {group.get('notes')}")
        doc = _retrieval_api._make_document(
            project_name,
            "entity_alias_group",
            str(group.get("id") or index),
            title,
            "\n".join(content_lines),
            scope="project",
            path=str(_retrieval_api.project_path(project_name) / "knowledge" / "entities" / "aliases.json"),
            tags=["entity_alias", str(group.get("category") or "")],
            metadata={
                "entity_type": "alias_group",
                "knowledge_category": str(group.get("category") or ""),
                "aliases": aliases,
                "source_pending_ids": group.get("source_pending_ids", []),
                "authority": "project",
            },
        )
        if doc:
            documents.append(doc)
    return documents


def _documents_from_setting_entities(project_name: str) -> list[_retrieval_api.RetrievalDocument]:
    documents: list[_retrieval_api.RetrievalDocument] = []
    for index, card in enumerate(_retrieval_api.load_setting_entities(project_name), start=1):
        if not isinstance(card, dict):
            continue
        name = str(card.get("name") or "").strip()
        if not name:
            continue
        content_lines = [
            f"name: {name}",
            f"setting_type: {card.get('setting_type', '')}",
            f"summary: {card.get('summary', '')}",
        ]
        for field in ["rules", "locations", "organizations", "abilities", "constraints", "timeline", "related_entities"]:
            values = card.get(field, [])
            if isinstance(values, list) and values:
                content_lines.append(f"{field}: " + "；".join(str(item) for item in values[:12]))
            elif isinstance(values, dict) and values:
                content_lines.append(f"{field}: " + _retrieval_api.json.dumps(values, ensure_ascii=False))
        doc = _retrieval_api._make_document(
            project_name,
            "entity_setting_card",
            str(card.get("id") or index),
            name,
            "\n".join(content_lines),
            scope=str(card.get("scope") or "project"),
            path=str(_retrieval_api.project_path(project_name) / "knowledge" / "entities" / "settings.json"),
            tags=[str(tag) for tag in card.get("tags", []) if str(tag).strip()] if isinstance(card.get("tags"), list) else ["setting_entity"],
            metadata={
                "entity_type": "setting",
                "setting_type": str(card.get("setting_type") or ""),
                "authority": str(card.get("authority") or "project"),
                "confidence": card.get("confidence", 0.7),
                "importance": card.get("importance", 0.5),
                "canon_status": str(card.get("canon_status") or "unknown"),
                "setting_scope": str(card.get("setting_scope") or ""),
                "story_id": str(card.get("story_id") or ""),
                "worldline_id": str(card.get("worldline_id") or ""),
                "worldline_label": str(card.get("worldline_label") or ""),
                "version_scope": str(card.get("version_scope") or ""),
                "source_knowledge_ids": card.get("source_knowledge_ids", []),
            },
        )
        if doc:
            documents.append(doc)
    return documents


def _documents_from_project_files(project_name: str, story_id: str = "default") -> list[_retrieval_api.RetrievalDocument]:
    documents: list[_retrieval_api.RetrievalDocument] = []
    base_path = _retrieval_api.story_path(project_name, story_id)

    outline = _retrieval_api.load_outline(project_name, story_id=story_id)
    creative_profile_discussion_artifact = _retrieval_api.load_creative_profile_discussion_artifact(project_name, story_id=story_id)
    outline_discussion_artifact = _retrieval_api.load_outline_discussion_artifact(project_name, story_id=story_id)
    doc = _retrieval_api._make_document(
        project_name,
        "outline",
        f"{story_id}/outline",
        f"[{story_id}] Project Outline",
        outline,
        path=str(base_path / "outline.md"),
        tags=["outline", f"story:{story_id}"],
        metadata={"authority": "project", "story_id": story_id},
    )
    if doc:
        documents.append(doc)

    for item in _retrieval_api.load_story_chapter_summaries(project_name, story_id):
        if not isinstance(item, dict):
            continue
        chapter_no = item.get("chapter_no")
        summary = str(item.get("summary", "") or "").strip()
        if not summary:
            continue
        doc = _retrieval_api._make_document(
            project_name,
            "chapter_summary",
            f"{story_id}/chapter_summary_{chapter_no}",
            f"[{story_id}] Chapter {chapter_no:03d} Summary" if isinstance(chapter_no, int) else f"[{story_id}] Chapter Summary",
            summary,
            chapter_no=chapter_no if isinstance(chapter_no, int) else None,
            path=str(base_path / "chapter_summaries.json"),
            tags=["summary", f"story:{story_id}"],
            metadata={"memory_field": "chapter_summaries", "authority": "project", "story_id": story_id},
        )
        if doc:
            documents.append(doc)

    creative_profile_discussion = creative_profile_discussion_artifact.get("report_markdown", "")
    doc = _retrieval_api._make_document(
        project_name,
        "creative_profile_discussion",
        f"{story_id}/creative_profile_discussion",
        f"[{story_id}] Approved Creative Profile Discussion",
        creative_profile_discussion,
        path=str(base_path / "creative_profile.discussion.json"),
        tags=["creative_profile_discussion", "approved_discussion", "creative_profile", f"story:{story_id}"],
        metadata={
            "authority": "project",
            "story_id": story_id,
            "approval_ready": bool((creative_profile_discussion_artifact.get("discussion") or {}).get("approval_ready")),
            "recommended_profile": (creative_profile_discussion_artifact.get("discussion") or {}).get("recommended_profile", {}),
        },
    )
    if doc:
        documents.append(doc)

    outline_discussion = outline_discussion_artifact.get("report_markdown", "")
    doc = _retrieval_api._make_document(
        project_name,
        "outline_discussion",
        f"{story_id}/outline_discussion",
        f"[{story_id}] Approved Outline Discussion",
        outline_discussion,
        path=str(base_path / "outline.discussion.json"),
        tags=["outline_discussion", "approved_discussion"],
        metadata={
            "authority": "project",
            "story_id": story_id,
            "approval_ready": bool((outline_discussion_artifact.get("discussion") or {}).get("approval_ready")),
        },
    )
    if doc:
        documents.append(doc)

    for volume in _retrieval_api.list_volumes(project_name, story_id=story_id):
        volume_no = int(volume.get("volume_no", 0))
        volume_outline = _retrieval_api.load_volume_outline(project_name, volume_no, story_id=story_id)
        volume_meta = _retrieval_api.load_volume_metadata(project_name, volume_no, story_id=story_id)
        volume_discussion_artifact = _retrieval_api.load_volume_discussion_artifact(project_name, volume_no, story_id=story_id)
        doc = _retrieval_api._make_document(
            project_name,
            "volume_outline",
            f"{story_id}/volume_{volume_no:03d}",
            volume_meta.get("title") or f"Volume {volume_no:03d}",
            volume_outline,
            path=str(base_path / "volumes" / f"volume_{volume_no:03d}.md"),
            tags=["volume_outline", f"volume_{volume_no:03d}"],
            metadata={
                "authority": "project",
                "story_id": story_id,
                "volume_no": volume_no,
                "status": volume_meta.get("status", "draft"),
                "summary": volume_meta.get("summary", ""),
            },
        )
        if doc:
            documents.append(doc)

        volume_discussion = volume_discussion_artifact.get("report_markdown", "")
        doc = _retrieval_api._make_document(
            project_name,
            "volume_discussion",
            f"{story_id}/volume_{volume_no:03d}",
            f"{volume_meta.get('title') or f'Volume {volume_no:03d}'} Approved Discussion",
            volume_discussion,
            path=str(base_path / "volumes" / f"volume_{volume_no:03d}.discussion.json"),
            tags=["volume_discussion", f"volume_{volume_no:03d}", "approved_discussion"],
            metadata={
                "authority": "project",
                "story_id": story_id,
                "volume_no": volume_no,
                "approval_ready": bool((volume_discussion_artifact.get("discussion") or {}).get("approval_ready")),
            },
        )
        if doc:
            documents.append(doc)

    for arc in _retrieval_api.list_arcs(project_name, story_id=story_id):
        arc_no = int(arc.get("arc_no", 0))
        arc_outline = _retrieval_api.load_arc_outline(project_name, arc_no, story_id=story_id)
        arc_meta = _retrieval_api.load_arc_metadata(project_name, arc_no, story_id=story_id)
        arc_discussion_artifact = _retrieval_api.load_arc_discussion_artifact(project_name, arc_no, story_id=story_id)
        doc = _retrieval_api._make_document(
            project_name,
            "arc_outline",
            f"{story_id}/arc_{arc_no:03d}",
            arc_meta.get("title") or f"Arc {arc_no:03d}",
            arc_outline,
            path=str(base_path / "arcs" / f"arc_{arc_no:03d}.md"),
            tags=["arc_outline", f"arc_{arc_no:03d}"],
            metadata={
                "authority": "project",
                "story_id": story_id,
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

        arc_discussion = arc_discussion_artifact.get("report_markdown", "")
        doc = _retrieval_api._make_document(
            project_name,
            "arc_discussion",
            f"{story_id}/arc_{arc_no:03d}",
            f"{arc_meta.get('title') or f'Arc {arc_no:03d}'} Approved Discussion",
            arc_discussion,
            path=str(base_path / "arcs" / f"arc_{arc_no:03d}.discussion.json"),
            tags=["arc_discussion", f"arc_{arc_no:03d}", "approved_discussion"],
            metadata={
                "authority": "project",
                "story_id": story_id,
                "arc_no": arc_no,
                "volume_no": arc_meta.get("volume_no"),
                "approval_ready": bool((arc_discussion_artifact.get("discussion") or {}).get("approval_ready")),
            },
        )
        if doc:
            documents.append(doc)

        arc_chapter_plan = _retrieval_api.load_arc_chapter_plan(project_name, arc_no, story_id=story_id)
        plan_markdown = arc_chapter_plan.get("report_markdown", "")
        doc = _retrieval_api._make_document(
            project_name,
            "arc_chapter_plan",
            f"{story_id}/arc_{arc_no:03d}",
            f"{arc_meta.get('title') or f'Arc {arc_no:03d}'} Chapter Plan",
            plan_markdown,
            path=str(base_path / "arcs" / f"arc_{arc_no:03d}.chapter_plan.json"),
            tags=["arc_chapter_plan", f"arc_{arc_no:03d}"],
            metadata={
                "authority": "project",
                "story_id": story_id,
                "arc_no": arc_no,
                "volume_no": arc_meta.get("volume_no"),
            },
        )
        if doc:
            documents.append(doc)

    chapter_outline_dir = base_path / "chapter_outlines"
    chapter_discussion_numbers: set[int] = set()
    for record in _retrieval_api.list_asset_payload_records(project_name, asset_type="chapter_discussion", story_id=story_id):
        chapter_no = _retrieval_api._chapter_no_from_asset_record(record)
        if isinstance(chapter_no, int):
            chapter_discussion_numbers.add(chapter_no)
    if chapter_outline_dir.exists():
        for file in chapter_outline_dir.glob("chapter_*.discussion.json"):
            match = _retrieval_api.re.search(r"chapter_(\d+)\.discussion\.json$", file.name)
            if match:
                chapter_discussion_numbers.add(int(match.group(1)))
    if chapter_outline_dir.exists():
        for file in sorted(chapter_outline_dir.glob("chapter_*.md")):
            match = _retrieval_api.re.search(r"chapter_(\d+)\.md$", file.name)
            chapter_no = int(match.group(1)) if match else None
            chapter_meta = _retrieval_api.load_chapter_outline_metadata(project_name, chapter_no, story_id=story_id) if chapter_no is not None else {}
            doc = _retrieval_api._make_document(
                project_name,
                "chapter_outline",
                f"{story_id}/{file.stem}",
                f"Chapter {chapter_no:03d} Outline" if chapter_no is not None else file.stem,
                _retrieval_api.load_chapter_outline(project_name, chapter_no, story_id=story_id) if chapter_no is not None else file.read_text(encoding="utf-8"),
                chapter_no=chapter_no,
                path=str(file),
                tags=["chapter_outline"],
                metadata={
                    "authority": "project",
                    "story_id": story_id,
                    "volume_no": chapter_meta.get("volume_no"),
                    "arc_no": chapter_meta.get("arc_no"),
                },
            )
            if doc:
                documents.append(doc)

        for chapter_no in sorted(chapter_discussion_numbers):
            chapter_meta = _retrieval_api.load_chapter_outline_metadata(project_name, chapter_no, story_id=story_id)
            chapter_discussion_artifact = _retrieval_api.load_chapter_discussion_artifact(project_name, chapter_no, story_id=story_id)
            chapter_discussion = chapter_discussion_artifact.get("report_markdown", "")
            doc = _retrieval_api._make_document(
                project_name,
                "chapter_discussion",
                f"{story_id}/chapter_{chapter_no:03d}",
                f"Chapter {chapter_no:03d} Approved Discussion",
                chapter_discussion,
                chapter_no=chapter_no,
                path=str(base_path / "chapter_outlines" / f"chapter_{chapter_no:03d}.discussion.json"),
                tags=["chapter_discussion", f"chapter_{chapter_no:03d}", "approved_discussion"],
                metadata={
                    "authority": "project",
                    "story_id": story_id,
                    "chapter_no": chapter_no,
                    "volume_no": chapter_meta.get("volume_no"),
                    "arc_no": chapter_meta.get("arc_no"),
                    "approval_ready": bool((chapter_discussion_artifact.get("discussion") or {}).get("approval_ready")),
                },
            )
            if doc:
                documents.append(doc)

    chapters_dir = base_path / "chapters"
    if chapters_dir.exists():
        for file in sorted(chapters_dir.glob("chapter_*.md")):
            match = _retrieval_api.re.search(r"chapter_(\d+)\.md$", file.name)
            chapter_no = int(match.group(1)) if match else None
            content = _retrieval_api.load_chapter(project_name, chapter_no, story_id=story_id) if chapter_no is not None else file.read_text(encoding="utf-8")
            doc = _retrieval_api._make_document(
                project_name,
                "chapter_content",
                f"{story_id}/{file.stem}",
                f"Chapter {chapter_no:03d} Content" if chapter_no is not None else file.stem,
                content,
                chapter_no=chapter_no,
                path=str(file),
                tags=["chapter"],
                metadata={"authority": "project", "story_id": story_id},
            )
            if doc:
                documents.append(doc)

    reviews_dir = base_path / "reviews"
    review_payloads: dict[int, dict] = {}
    review_paths: dict[int, str] = {}
    for record in _retrieval_api.list_asset_payload_records(project_name, asset_type="review_json", story_id=story_id):
        chapter_no = _retrieval_api._chapter_no_from_asset_record(record)
        payload = record.get("payload")
        if isinstance(chapter_no, int) and isinstance(payload, dict):
            review_payloads[chapter_no] = payload
            review_paths[chapter_no] = str(base_path / str(record.get("relative_path") or f"reviews/chapter_{chapter_no:03d}.json"))
    if reviews_dir.exists():
        for file in sorted(reviews_dir.glob("chapter_*.json")):
            match = _retrieval_api.re.search(r"chapter_(\d+)\.json$", file.name)
            if not match:
                continue
            chapter_no = int(match.group(1))
            review_json = _retrieval_api.load_review_json(project_name, chapter_no, story_id=story_id)
            if isinstance(review_json, dict):
                review_payloads[chapter_no] = review_json
                review_paths[chapter_no] = str(file)
    for chapter_no in sorted(review_payloads):
        review_json = review_payloads[chapter_no]
        review_path = review_paths.get(chapter_no, str(base_path / "reviews" / f"chapter_{chapter_no:03d}.json"))
        payload_doc = _retrieval_api._make_document(
            project_name,
            "review_payload",
            f"{story_id}/payload_{chapter_no:03d}",
            f"Chapter {chapter_no:03d} Review Payload",
            _retrieval_api.json.dumps(review_json, ensure_ascii=False, indent=2),
            chapter_no=chapter_no,
            path=review_path,
            tags=["review", "payload", str(review_json.get("status", ""))],
            metadata={"status": review_json.get("status", ""), "authority": "project", "story_id": story_id},
        )
        if payload_doc:
            documents.append(payload_doc)
        summary_doc = _retrieval_api._make_document(
            project_name,
            "review_summary",
            f"{story_id}/summary_{chapter_no:03d}",
            f"Chapter {chapter_no:03d} Review Summary",
            str(review_json.get("summary", "")),
            chapter_no=chapter_no,
            path=review_path,
            tags=["review", "summary", str(review_json.get("status", ""))],
            metadata={"status": review_json.get("status", ""), "authority": "project", "story_id": story_id},
        )
        if summary_doc:
            documents.append(summary_doc)

        issues = review_json.get("issues", [])
        if not isinstance(issues, list):
            issues = []
        for index, issue in enumerate(issues, start=1):
            issue_content = _retrieval_api.json.dumps(issue, ensure_ascii=False) if isinstance(issue, dict) else str(issue)
            doc = _retrieval_api._make_document(
                project_name,
                "review_issue",
                f"{story_id}/{chapter_no:03d}_{index:02d}",
                f"Chapter {chapter_no:03d} Review Issue {index}",
                issue_content,
                chapter_no=chapter_no,
                path=review_path,
                tags=["review", "issue"],
                metadata={"status": review_json.get("status", ""), "authority": "project", "story_id": story_id},
            )
            if doc:
                documents.append(doc)

        consistency_checks = review_json.get("consistency_checks", {})
        if not isinstance(consistency_checks, dict):
            consistency_checks = {}
        for field_name, label in [
            ("characters", "review_characters_check"),
            ("world", "review_world_check"),
            ("timeline", "review_timeline_check"),
            ("foreshadowing", "review_foreshadowing_check"),
        ]:
            content = consistency_checks.get(field_name, "")
            doc = _retrieval_api._make_document(
                project_name,
                label,
                f"{story_id}/{chapter_no:03d}_{field_name}",
                f"Chapter {chapter_no:03d} {field_name.title()} Check",
                str(content),
                chapter_no=chapter_no,
                path=review_path,
                tags=["review", field_name],
                metadata={"status": review_json.get("status", ""), "authority": "project", "story_id": story_id},
            )
            if doc:
                documents.append(doc)

    if reviews_dir.exists():
        for file in sorted(reviews_dir.glob("chapter_*.md")):
            match = _retrieval_api.re.search(r"chapter_(\d+)\.md$", file.name)
            chapter_no = int(match.group(1)) if match else None
            content = _retrieval_api.load_review(project_name, chapter_no, story_id=story_id) if chapter_no is not None else file.read_text(encoding="utf-8")
            doc = _retrieval_api._make_document(
                project_name,
                "review_markdown",
                f"{story_id}/{file.stem}",
                f"Chapter {chapter_no:03d} Review Markdown" if chapter_no is not None else file.stem,
                content,
                chapter_no=chapter_no,
                path=str(file),
                tags=["review", "markdown"],
                metadata={"authority": "project", "story_id": story_id},
            )
            if doc:
                documents.append(doc)

    analysis_dir = base_path / "analysis"
    if analysis_dir.exists():
        for file in sorted(analysis_dir.glob("*.md")):
            match = _retrieval_api.re.search(r"(.+)_chapter_(\d+)\.md$", file.name)
            analysis_type = match.group(1) if match else file.stem
            chapter_no = int(match.group(2)) if match else None
            content = _retrieval_api.load_analysis_report(project_name, analysis_type, chapter_no, story_id=story_id) if chapter_no is not None else file.read_text(encoding="utf-8")
            for section_title, section_body in _retrieval_api._split_markdown_sections(content):
                identifier = f"{analysis_type}_{chapter_no or 'na'}_{section_title or 'body'}"
                doc = _retrieval_api._make_document(
                    project_name,
                    f"analysis_{analysis_type}",
                    f"{story_id}/{identifier}",
                    section_title or f"{analysis_type} analysis",
                    section_body,
                    chapter_no=chapter_no,
                    path=str(file),
                    tags=["analysis", analysis_type],
                    metadata={"authority": "project", "story_id": story_id},
                )
                if doc:
                    documents.append(doc)

    evaluation_dir = base_path / "evaluation"
    evaluation_payloads: dict[int, dict] = {}
    evaluation_paths: dict[int, str] = {}
    for record in _retrieval_api.list_asset_payload_records(project_name, asset_type="evaluation_json", story_id=story_id):
        chapter_no = _retrieval_api._chapter_no_from_asset_record(record)
        payload = record.get("payload")
        if isinstance(chapter_no, int) and isinstance(payload, dict):
            evaluation_payloads[chapter_no] = payload
            evaluation_paths[chapter_no] = str(base_path / str(record.get("relative_path") or f"evaluation/chapter_{chapter_no:03d}.json"))
    if evaluation_dir.exists():
        for file in sorted(evaluation_dir.glob("chapter_*.json")):
            match = _retrieval_api.re.search(r"chapter_(\d+)\.json$", file.name)
            if not match:
                continue
            chapter_no = int(match.group(1))
            evaluation_json = _retrieval_api.load_evaluation_json(project_name, chapter_no, story_id=story_id)
            if isinstance(evaluation_json, dict):
                evaluation_payloads[chapter_no] = evaluation_json
                evaluation_paths[chapter_no] = str(file)
    for chapter_no in sorted(evaluation_payloads):
        evaluation_json = evaluation_payloads[chapter_no]
        evaluation_path = evaluation_paths.get(chapter_no, str(base_path / "evaluation" / f"chapter_{chapter_no:03d}.json"))
        doc = _retrieval_api._make_document(
            project_name,
            "evaluation_payload",
            f"{story_id}/payload_{chapter_no:03d}",
            f"Chapter {chapter_no:03d} Evaluation Payload",
            _retrieval_api.json.dumps(evaluation_json, ensure_ascii=False, indent=2),
            chapter_no=chapter_no,
            path=evaluation_path,
            tags=["evaluation", "payload"],
            metadata={"authority": "project", "story_id": story_id, "evaluation": evaluation_json},
        )
        if doc:
            documents.append(doc)
    if evaluation_dir.exists():
        for file in sorted(evaluation_dir.glob("chapter_*.md")):
            match = _retrieval_api.re.search(r"chapter_(\d+)\.md$", file.name)
            chapter_no = int(match.group(1)) if match else None
            content = _retrieval_api.load_evaluation_report(project_name, chapter_no, story_id=story_id) if chapter_no is not None else file.read_text(encoding="utf-8")
            doc = _retrieval_api._make_document(
                project_name,
                "evaluation_chapter",
                f"{story_id}/{file.stem}",
                f"Chapter {chapter_no:03d} Evaluation" if chapter_no is not None else file.stem,
                content,
                chapter_no=chapter_no,
                path=str(file),
                tags=["evaluation"],
                metadata={
                    "authority": "project",
                    "story_id": story_id,
                    "evaluation": _retrieval_api.load_evaluation_json(project_name, chapter_no, story_id=story_id) if chapter_no is not None else {},
                },
            )
            if doc:
                documents.append(doc)

    return documents


def _documents_from_external_sources(project_name: str) -> list[_retrieval_api.RetrievalDocument]:
    source_dir = _retrieval_api.retrieval_sources_path(project_name)
    documents: list[_retrieval_api.RetrievalDocument] = []

    source_files = []
    seen_source_paths: set[str] = set()
    for relative_path in _retrieval_api.list_retrieval_source_files(project_name):
        clean_relative_path = str(relative_path or "").replace("\\", "/").strip()
        if not clean_relative_path or clean_relative_path in seen_source_paths:
            continue
        seen_source_paths.add(clean_relative_path)
        source_files.append((clean_relative_path, source_dir / clean_relative_path))
    for file in sorted(source_dir.rglob("*")):
        if not file.is_file():
            continue
        relative_path = file.relative_to(source_dir).as_posix()
        if relative_path in seen_source_paths:
            continue
        seen_source_paths.add(relative_path)
        source_files.append((relative_path, file))

    for relative_path, file in source_files:
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
                parsed = _retrieval_api.json.loads(raw_text)
                scope = str(parsed.get("scope", scope)) if isinstance(parsed, dict) else scope
                title = str(parsed.get("title", title)) if isinstance(parsed, dict) else title
                body = parsed.get("content", "") if isinstance(parsed, dict) else ""
                content = body if isinstance(body, str) and body.strip() else raw_text
                metadata.update(parsed.get("metadata", {}) if isinstance(parsed, dict) and isinstance(parsed.get("metadata"), dict) else {})
                tags.extend(parsed.get("tags", []) if isinstance(parsed, dict) and isinstance(parsed.get("tags"), list) else [])
                source_type = str(parsed.get("source_type", source_type)) if isinstance(parsed, dict) else source_type
            except Exception as exc:
                _retrieval_api.logging.getLogger("novelforge").warning(
                    "Failed to parse external retrieval source as JSON: project=%s file=%s error=%s",
                    project_name, file, exc,
                )
                content = raw_text

        doc = _retrieval_api._make_document(
            project_name,
            source_type,
            relative_path,
            title,
            content,
            scope=scope if scope in {"project", "canon", "reference"} else "reference",
            path=str(file),
            tags=tags,
            metadata={**metadata, "authority": _retrieval_api._infer_authority(scope, metadata)},
        )
        if doc:
            documents.append(doc)

    return documents


def gather_retrieval_documents(project_name: str) -> list[_retrieval_api.RetrievalDocument]:
    documents = []
    documents.extend(_documents_from_memory(project_name))
    documents.extend(_documents_from_knowledge(project_name))
    documents.extend(_documents_from_character_entities(project_name))
    documents.extend(_documents_from_entity_aliases(project_name))
    documents.extend(_documents_from_setting_entities(project_name))
    documents.extend(_documents_from_external_sources(project_name))

    # Conflict resolutions may be project-wide or story-owned.  Preserve the
    # ownership in both the document ID and metadata so story filtering can
    # keep identically named resolutions isolated.
    conflict_resolutions = _retrieval_api.load_conflict_resolutions(project_name)
    for item in conflict_resolutions:
        conflict_id = str(item.get("conflict_id", "")).strip()
        resolution_story_id = str(item.get("story_id") or "").strip()
        resolution_identifier = (
            f"story:{resolution_story_id}:{conflict_id}"
            if resolution_story_id
            else f"project:{conflict_id}"
        )
        content = "\n".join([
            f"decision: {item.get('decision', '')}",
            f"note: {item.get('note', '')}",
            f"shared_terms: {', '.join(item.get('shared_terms', []))}",
            f"project_source: {item.get('project_source', '')}",
            f"external_source: {item.get('external_source', '')}",
        ])
        doc = _retrieval_api._make_document(
            project_name,
            "conflict_resolution",
            resolution_identifier,
            f"Conflict Resolution {conflict_id}",
            content,
            path=str(_retrieval_api.project_path(project_name) / "retrieval" / "conflict_resolutions.json"),
            tags=["conflict_resolution"],
            metadata={
                "authority": "project",
                "decision": item.get("decision", ""),
                "story_id": resolution_story_id,
            },
        )
        if doc:
            documents.append(doc)

    for story in _retrieval_api.list_stories(project_name):
        story_id = story.get("story_id", "default")
        # Replacing the authoritative manifest with a partial snapshot would
        # soft-delete every document belonging to the failed story.  Let the
        # caller fail before save_retrieval_manifest instead.
        documents.extend(_documents_from_project_files(project_name, story_id))
    return documents
