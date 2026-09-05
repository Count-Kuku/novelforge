"""Implementation slice for the memory facade: one-time legacy JSON bootstrap sync."""

from __future__ import annotations

import logging

from novelforge.services import memory as _memory_api
from storage.repositories.ingestion_batch_mutations import (
    delete_long_reference_batch_row,
    persist_long_reference_batch_row,
)
from storage.repositories.retrieval import search_retrieval_chunks_fts
from storage.repositories.sources import list_source_revision_rows

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
                    creation_mode="planned",
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
                profile_file = _memory_api._story_path_from_project_path(
                    normalized_name, story_id, "creative_profile.json"
                )
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

                creative_discussion_file = _memory_api._story_path_from_project_path(
                    normalized_name, story_id, "creative_profile.discussion.json"
                )
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
                        source_title="项目优先设定",
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

            eval_cases = _memory_api._load_json_list(_memory_api.retrieval_eval_cases_path(normalized_name))
            _memory_api.sync_retrieval_eval_cases(conn, eval_cases)
            result["synced"]["retrieval_eval_cases"] = len(eval_cases)

            eval_runs = _memory_api._load_json_list(_memory_api.retrieval_eval_runs_path(normalized_name))
            for run in eval_runs:
                try:
                    _memory_api.sync_retrieval_eval_run(conn, run)
                except Exception as exc:
                    result["warnings"].append(f"retrieval_eval_run skipped: {exc}")
            result["synced"]["retrieval_eval_runs"] = len(eval_runs)

            feedback_items = _memory_api._load_json_list(_memory_api.retrieval_feedback_path(normalized_name))
            for feedback in feedback_items:
                try:
                    _memory_api.append_retrieval_feedback_row(conn, feedback)
                except Exception as exc:
                    result["warnings"].append(f"retrieval_feedback skipped: {exc}")
            result["synced"]["retrieval_feedback"] = len(feedback_items)

            conflict_items = []
            conflict_file = _memory_api.conflict_resolutions_path(normalized_name)
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

            batches = _memory_api._list_long_reference_batches_from_files(normalized_name)
            for batch in batches:
                _memory_api.sync_long_reference_batch(conn, batch)
            result["synced"]["long_reference_batches"] = len(batches)

            source_root = _memory_api.retrieval_sources_path(normalized_name).resolve()
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

            manifest_file = _memory_api.retrieval_path(normalized_name) / "manifest.json"
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

            vector_file = _memory_api.retrieval_path(normalized_name) / "vectors.json"
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
