import hashlib
import json

from memory import (
    delete_arc,
    delete_arc_chapter_plan,
    delete_retrieval_source_file,
    delete_volume,
    list_arcs,
    list_long_reference_batches,
    list_volumes,
    load_arc_chapter_plan,
    load_arc_discussion_artifact,
    load_chapter_discussion_artifact,
    load_creative_profile_discussion_artifact,
    load_evaluation_json,
    load_evaluation_report,
    load_knowledge_base,
    load_outline,
    load_outline_discussion_artifact,
    load_pending_knowledge_items,
    load_pipeline_run,
    load_volume_discussion_artifact,
    save_arc_metadata,
    save_arc_outline,
    save_chapter,
    save_chapter_outline,
    save_outline,
    save_volume_metadata,
    save_volume_outline,
)
from project_manager import (
    delete_analysis_report,
    delete_chapter_content as delete_chapter_content_resource,
    delete_chapter_outline,
    delete_chapter_review,
    delete_evaluation_report,
    delete_outline,
    delete_pipeline_run,
    list_analysis_reports,
    list_chapter_inventory,
    list_evaluation_reports,
    list_project_runs,
    list_retrieval_sources,
    save_analysis_resource,
    save_evaluation_resource,
    save_retrieval_source_content,
    save_review_resources,
)
from retrieval import rebuild_retrieval_assets
from schemas import label_knowledge_category
from skills import (
    clear_arc_discussion_approval,
    clear_chapter_discussion_approval,
    clear_creative_profile_discussion_approval,
    clear_outline_discussion_approval,
    clear_volume_discussion_approval,
)


def stable_widget_suffix(value: str) -> str:
    return hashlib.md5(str(value).encode("utf-8")).hexdigest()[:10]


def label_yes_no(value: bool) -> str:
    return "是" if value else "否"


def _resource_browser_json_text(payload) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except TypeError:
        return str(payload)


def _resource_browser_item_name(item: dict, fallback: str) -> str:
    for field in ["name", "title", "subject", "key", "id", "pending_id"]:
        value = str(item.get(field) or "").strip()
        if value:
            return value[:80]
    content = str(item.get("content") or item.get("summary") or "").strip()
    if content:
        return content[:80]
    return fallback


def _long_reference_batch_browser_payload(batch: dict) -> dict:
    segments = []
    for segment in batch.get("segments", []):
        if not isinstance(segment, dict):
            continue
        segments.append({
            key: value for key, value in segment.items()
            if key != "content"
        })
    return {
        "batch_id": batch.get("batch_id", ""),
        "title": batch.get("title", ""),
        "scope": batch.get("scope", ""),
        "authority": batch.get("authority", ""),
        "source_type": batch.get("source_type", ""),
        "source_origin": batch.get("source_origin", ""),
        "source_file_name": batch.get("source_file_name", ""),
        "content_char_count": batch.get("content_char_count", 0),
        "created_at": batch.get("created_at", ""),
        "updated_at": batch.get("updated_at", ""),
        "summary": batch.get("summary", {}),
        "segments": segments,
    }


def _build_resource_browser_items(project_name: str, story_id: str = "default") -> list[dict]:
    items: list[dict] = []

    outline = load_outline(project_name, story_id=story_id)
    outline_discussion = load_outline_discussion_artifact(project_name, story_id=story_id)
    creative_profile_discussion = load_creative_profile_discussion_artifact(project_name, story_id=story_id)
    items.append({
        "id": "outline:root",
        "group": "outline",
        "label": "outline.md",
        "path_label": "全书大纲 / outline.md",
        "content": outline,
        "chapter_no": None,
        "analysis_type": "",
        "relative_path": "outline.md",
        "editable": True,
        "deletable": bool(outline.strip()),
    })
    if outline_discussion.get("discussion"):
        items.append({
            "id": "outline-discussion:root",
            "group": "outline_discussion",
            "label": "outline.discussion.json [已批准]",
            "path_label": "全书讨论工件 / outline.discussion.json / 已批准=是",
            "content": outline_discussion.get("report_markdown", ""),
            "discussion_payload": outline_discussion.get("discussion", {}),
            "chapter_no": None,
            "analysis_type": "",
            "relative_path": "outline.discussion.json",
            "editable": False,
            "deletable": True,
        })
    if creative_profile_discussion.get("discussion"):
        items.append({
            "id": "creative-profile-discussion:root",
            "group": "creative_profile_discussion",
            "label": "creative_profile.discussion.json [已批准]",
            "path_label": "创作配置讨论工件 / creative_profile.discussion.json / 已批准=是",
            "content": creative_profile_discussion.get("report_markdown", ""),
            "discussion_payload": creative_profile_discussion.get("discussion", {}),
            "chapter_no": None,
            "analysis_type": "",
            "relative_path": "creative_profile.discussion.json",
            "editable": False,
            "deletable": True,
        })

    for volume in list_volumes(project_name, story_id=story_id):
        volume_no = int(volume.get("volume_no", 0))
        volume_discussion = load_volume_discussion_artifact(project_name, volume_no, story_id=story_id)
        items.append({
            "id": f"volume:{volume_no}",
            "group": "volume_outline",
            "label": f"volume_{volume_no:03d}.md{' [已批准讨论]' if volume.get('has_approved_discussion') else ''}",
            "path_label": f"volumes / volume_{volume_no:03d}.md / 已批准讨论={label_yes_no(bool(volume.get('has_approved_discussion')))}",
            "content": volume.get("outline", ""),
            "volume_no": volume_no,
            "volume_metadata": volume,
            "chapter_no": None,
            "analysis_type": "",
            "relative_path": f"volumes/volume_{volume_no:03d}.md",
            "editable": True,
            "deletable": True,
        })
        if volume_discussion.get("discussion"):
            items.append({
                "id": f"volume-discussion:{volume_no}",
                "group": "volume_discussion",
                "label": f"volume_{volume_no:03d}.discussion.json [已批准]",
                "path_label": f"volumes / volume_{volume_no:03d}.discussion.json / 已批准=是",
                "content": volume_discussion.get("report_markdown", ""),
                "volume_no": volume_no,
                "discussion_payload": volume_discussion.get("discussion", {}),
                "chapter_no": None,
                "analysis_type": "",
                "relative_path": f"volumes/volume_{volume_no:03d}.discussion.json",
                "editable": False,
                "deletable": True,
            })

    for arc in list_arcs(project_name, story_id=story_id):
        arc_no = int(arc.get("arc_no", 0))
        volume_no = arc.get("volume_no")
        parent_label = f" / 第{int(volume_no)}卷" if volume_no else ""
        arc_discussion = load_arc_discussion_artifact(project_name, arc_no, story_id=story_id)
        items.append({
            "id": f"arc:{arc_no}",
            "group": "arc_outline",
            "label": f"arc_{arc_no:03d}.md{' [已批准讨论]' if arc.get('has_approved_discussion') else ''}",
            "path_label": f"arcs / arc_{arc_no:03d}.md{parent_label} / 已批准讨论={label_yes_no(bool(arc.get('has_approved_discussion')))}",
            "content": arc.get("outline", ""),
            "arc_no": arc_no,
            "arc_metadata": arc,
            "chapter_no": None,
            "analysis_type": "",
            "relative_path": f"arcs/arc_{arc_no:03d}.md",
            "editable": True,
            "deletable": True,
        })
        if arc_discussion.get("discussion"):
            items.append({
                "id": f"arc-discussion:{arc_no}",
                "group": "arc_discussion",
                "label": f"arc_{arc_no:03d}.discussion.json [已批准]",
                "path_label": f"arcs / arc_{arc_no:03d}.discussion.json{parent_label} / 已批准=是",
                "content": arc_discussion.get("report_markdown", ""),
                "arc_no": arc_no,
                "arc_metadata": arc,
                "discussion_payload": arc_discussion.get("discussion", {}),
                "chapter_no": None,
                "analysis_type": "",
                "relative_path": f"arcs/arc_{arc_no:03d}.discussion.json",
                "editable": False,
                "deletable": True,
            })
        arc_chapter_plan = load_arc_chapter_plan(project_name, arc_no, story_id=story_id)
        if arc_chapter_plan.get("plan"):
            items.append({
                "id": f"arc-chapter-plan:{arc_no}",
                "group": "arc_chapter_plan",
                "label": f"arc_{arc_no:03d}.chapter_plan.json",
                "path_label": f"arcs / arc_{arc_no:03d}.chapter_plan.json{parent_label}",
                "content": arc_chapter_plan.get("report_markdown", ""),
                "arc_no": arc_no,
                "arc_metadata": arc,
                "chapter_plan_payload": arc_chapter_plan.get("plan", {}),
                "chapter_no": None,
                "analysis_type": "",
                "relative_path": f"arcs/arc_{arc_no:03d}.chapter_plan.json",
                "editable": False,
                "deletable": True,
            })

    chapter_inventory = list_chapter_inventory(project_name, story_id=story_id)
    for item in chapter_inventory:
        chapter_no = int(item.get("chapter_no", 0))
        if item.get("has_outline"):
            chapter_meta = item.get("metadata", {}) or {}
            chapter_discussion = load_chapter_discussion_artifact(project_name, chapter_no, story_id=story_id)
            volume_suffix = f" / 第{int(chapter_meta.get('volume_no'))}卷" if chapter_meta.get("volume_no") else ""
            arc_suffix = f" / 剧情段 {int(chapter_meta.get('arc_no')):03d}" if chapter_meta.get("arc_no") else ""
            items.append({
                "id": f"chapter-outline:{chapter_no}",
                "group": "chapter_outline",
                "label": f"chapter_{chapter_no:03d}.md",
                "path_label": f"chapter_outlines / chapter_{chapter_no:03d}.md{volume_suffix}{arc_suffix}",
                "content": item.get("outline_preview", ""),
                "chapter_no": chapter_no,
                "chapter_metadata": chapter_meta,
                "analysis_type": "",
                "relative_path": f"chapter_outlines/chapter_{chapter_no:03d}.md",
                "editable": True,
                "deletable": True,
            })
            if chapter_discussion.get("discussion"):
                items.append({
                    "id": f"chapter-discussion:{chapter_no}",
                    "group": "chapter_discussion",
                    "label": f"chapter_{chapter_no:03d}.discussion.json [已批准]",
                    "path_label": f"chapter_outlines / chapter_{chapter_no:03d}.discussion.json{volume_suffix}{arc_suffix} / 已批准=是",
                    "content": chapter_discussion.get("report_markdown", ""),
                    "chapter_no": chapter_no,
                    "chapter_metadata": chapter_meta,
                    "discussion_payload": chapter_discussion.get("discussion", {}),
                    "analysis_type": "",
                    "relative_path": f"chapter_outlines/chapter_{chapter_no:03d}.discussion.json",
                    "editable": False,
                    "deletable": True,
                })
        if item.get("has_content"):
            items.append({
                "id": f"chapter-content:{chapter_no}",
                "group": "chapter_content",
                "label": f"chapter_{chapter_no:03d}.md",
                "path_label": f"chapters / chapter_{chapter_no:03d}.md",
                "content": item.get("content_preview", ""),
                "chapter_no": chapter_no,
                "analysis_type": "",
                "relative_path": f"chapters/chapter_{chapter_no:03d}.md",
                "editable": True,
                "deletable": True,
            })
        if item.get("has_review_markdown") or item.get("has_review_json"):
            items.append({
                "id": f"review:{chapter_no}",
                "group": "review",
                "label": f"chapter_{chapter_no:03d}",
                "path_label": f"reviews / chapter_{chapter_no:03d}",
                "content": item.get("review_preview", ""),
                "review_payload": item.get("review_payload", {}),
                "chapter_no": chapter_no,
                "analysis_type": "",
                "relative_path": f"reviews/chapter_{chapter_no:03d}",
                "editable": True,
                "deletable": True,
            })

    for report in list_analysis_reports(project_name, story_id=story_id):
        chapter_no = report.get("chapter_no")
        report_path = report.get("path", "")
        content = ""
        if report_path:
            try:
                with open(report_path, "r", encoding="utf-8") as handle:
                    content = handle.read()
            except Exception:
                content = ""
        items.append({
            "id": f"analysis:{report.get('analysis_type', 'unknown')}:{chapter_no}",
            "group": "analysis",
            "label": report.get("file_name", "analysis.md"),
            "path_label": f"analysis / {report.get('file_name', 'analysis.md')}",
            "content": content,
            "chapter_no": chapter_no,
            "analysis_type": report.get("analysis_type", "unknown"),
            "relative_path": report.get("file_name", ""),
            "editable": True,
            "deletable": True,
        })

    for report in list_evaluation_reports(project_name, story_id=story_id):
        chapter_no = int(report.get("chapter_no") or 0)
        content = load_evaluation_report(project_name, chapter_no, story_id=story_id)
        items.append({
            "id": f"evaluation:{chapter_no}",
            "group": "evaluation",
            "label": report.get("file_name", "evaluation.md"),
            "path_label": f"evaluation / {report.get('file_name', 'evaluation.md')}",
            "content": content,
            "evaluation_payload": load_evaluation_json(project_name, chapter_no, story_id=story_id) or {},
            "chapter_no": chapter_no,
            "analysis_type": "",
            "relative_path": report.get("file_name", ""),
            "editable": True,
            "deletable": True,
        })

    for run in list_project_runs(project_name, story_id=story_id):
        run_content = load_pipeline_run(project_name, run.get("run_id", ""), story_id=story_id)
        items.append({
            "id": f"run:{run.get('run_id', '')}",
            "group": "run",
            "label": f"{run.get('run_id', '')}.json",
            "path_label": f"runs / {run.get('run_id', '')}.json",
            "content": run_content,
            "chapter_no": run.get("chapter_no"),
            "analysis_type": "",
            "run_id": run.get("run_id", ""),
            "relative_path": f"runs/{run.get('run_id', '')}.json",
            "editable": False,
            "deletable": True,
        })

    for source in list_retrieval_sources(project_name):
        items.append({
            "id": f"source:{source.get('relative_path', '')}",
            "group": "source",
            "label": source.get("relative_path", ""),
            "path_label": f"retrieval/sources / {source.get('relative_path', '')}",
            "content": source.get("preview", ""),
            "chapter_no": None,
            "analysis_type": "",
            "relative_path": source.get("relative_path", ""),
            "suffix": source.get("suffix", ""),
            "editable": True,
            "deletable": True,
        })

    knowledge_base = load_knowledge_base(project_name)
    for category, knowledge_items in knowledge_base.items():
        for index, knowledge_item in enumerate(knowledge_items, start=1):
            if not isinstance(knowledge_item, dict):
                continue
            item_name = _resource_browser_item_name(knowledge_item, f"知识条目 {index}")
            item_identity = str(knowledge_item.get("id") or knowledge_item.get("knowledge_id") or item_name)
            items.append({
                "id": f"knowledge:{category}:{stable_widget_suffix(f'{category}:{index}:{item_identity}')}",
                "group": "knowledge_item",
                "label": f"{label_knowledge_category(category)} / {item_name}",
                "path_label": f"knowledge / {category} / {item_identity}",
                "content": _resource_browser_json_text(knowledge_item),
                "knowledge_payload": knowledge_item,
                "knowledge_category": category,
                "chapter_no": None,
                "analysis_type": "",
                "relative_path": f"knowledge/{category}.json",
                "editable": False,
                "deletable": False,
            })

    for index, pending_item in enumerate(load_pending_knowledge_items(project_name), start=1):
        if not isinstance(pending_item, dict):
            continue
        category = str(pending_item.get("category") or "unknown")
        pending_id = str(pending_item.get("pending_id") or pending_item.get("id") or f"pending:{index}")
        item_name = _resource_browser_item_name(pending_item, f"待确认条目 {index}")
        items.append({
            "id": f"pending-knowledge:{stable_widget_suffix(f'{index}:{pending_id}')}",
            "group": "pending_knowledge",
            "label": f"{label_knowledge_category(category)} / {item_name}",
            "path_label": f"pending_knowledge / {category} / {pending_id}",
            "content": _resource_browser_json_text(pending_item),
            "pending_payload": pending_item,
            "knowledge_category": category,
            "chapter_no": None,
            "analysis_type": "",
            "relative_path": "pending_knowledge.json",
            "editable": False,
            "deletable": False,
        })

    for batch in list_long_reference_batches(project_name):
        if not isinstance(batch, dict):
            continue
        batch_id = str(batch.get("batch_id") or "")
        batch_identity = batch_id or str(batch.get("file_name") or batch.get("title") or "long_reference_batch")
        batch_title = str(batch.get("title") or batch.get("source_file_name") or batch_id or "资料批次")
        summary = batch.get("summary", {}) if isinstance(batch.get("summary", {}), dict) else {}
        segment_count = int(summary.get("segment_count") or len(batch.get("segments", []) or []))
        extracted_count = int(summary.get("extract_queued_count") or 0)
        items.append({
            "id": f"long-reference-batch:{stable_widget_suffix(batch_identity)}",
            "group": "long_reference_batch",
            "label": f"{batch_title}（{segment_count} 段 / 已提取 {extracted_count}）",
            "path_label": f"long_reference_batches / {batch.get('file_name') or batch_id}",
            "content": _resource_browser_json_text(_long_reference_batch_browser_payload(batch)),
            "batch_payload": batch,
            "chapter_no": None,
            "analysis_type": "",
            "relative_path": f"long_reference_batches/{batch.get('file_name') or batch_id}",
            "editable": False,
            "deletable": False,
        })

    return items


def _save_browser_resource(project_name: str, resource: dict, edited_content: str, edited_json_text: str = "", story_id: str = "default"):
    group = resource.get("group")
    if group == "outline":
        save_outline(project_name, edited_content, story_id=story_id)
        return
    if group == "volume_outline":
        volume_no = int(resource.get("volume_no", 0))
        save_volume_outline(project_name, volume_no, edited_content, story_id=story_id)
        metadata = dict(resource.get("volume_metadata", {}) or {})
        save_volume_metadata(project_name, volume_no, metadata, story_id=story_id)
        return
    if group == "arc_outline":
        arc_no = int(resource.get("arc_no", 0))
        save_arc_outline(project_name, arc_no, edited_content, story_id=story_id)
        metadata = dict(resource.get("arc_metadata", {}) or {})
        save_arc_metadata(project_name, arc_no, metadata, story_id=story_id)
        return
    if group == "chapter_outline":
        save_chapter_outline(project_name, int(resource.get("chapter_no", 0)), edited_content, story_id=story_id)
        return
    if group == "chapter_content":
        save_chapter(project_name, int(resource.get("chapter_no", 0)), edited_content, story_id=story_id)
        return
    if group == "review":
        parsed = json.loads(edited_json_text) if edited_json_text.strip() else {}
        save_review_resources(project_name, int(resource.get("chapter_no", 0)), edited_content, parsed, story_id=story_id)
        return
    if group == "analysis":
        save_analysis_resource(project_name, str(resource.get("analysis_type", "unknown")), int(resource.get("chapter_no") or 0), edited_content, story_id=story_id)
        return
    if group == "evaluation":
        parsed = json.loads(edited_json_text) if edited_json_text.strip() else {}
        save_evaluation_resource(project_name, int(resource.get("chapter_no", 0)), edited_content, parsed, story_id=story_id)
        return
    if group == "source":
        save_retrieval_source_content(project_name, str(resource.get("relative_path", "")), edited_content)
        rebuild_retrieval_assets(project_name, build_vectors=True)
        return
    raise ValueError(f"不支持保存这种资源类型：{group}")


def _delete_browser_resource(project_name: str, resource: dict, story_id: str = "default"):
    group = resource.get("group")
    if group == "outline":
        return delete_outline(project_name, story_id=story_id)
    if group == "outline_discussion":
        return clear_outline_discussion_approval(project_name, story_id=story_id)
    if group == "creative_profile_discussion":
        return clear_creative_profile_discussion_approval(project_name, story_id=story_id)
    if group == "volume_outline":
        return delete_volume(project_name, int(resource.get("volume_no", 0)), story_id=story_id)
    if group == "volume_discussion":
        return clear_volume_discussion_approval(project_name, int(resource.get("volume_no", 0)), story_id=story_id)
    if group == "arc_outline":
        return delete_arc(project_name, int(resource.get("arc_no", 0)), story_id=story_id)
    if group == "arc_discussion":
        return clear_arc_discussion_approval(project_name, int(resource.get("arc_no", 0)), story_id=story_id)
    if group == "arc_chapter_plan":
        return delete_arc_chapter_plan(project_name, int(resource.get("arc_no", 0)), story_id=story_id)
    if group == "chapter_outline":
        return delete_chapter_outline(project_name, int(resource.get("chapter_no", 0)), story_id=story_id)
    if group == "chapter_discussion":
        return clear_chapter_discussion_approval(project_name, int(resource.get("chapter_no", 0)), story_id=story_id)
    if group == "chapter_content":
        return delete_chapter_content_resource(project_name, int(resource.get("chapter_no", 0)), story_id=story_id)
    if group == "review":
        return delete_chapter_review(project_name, int(resource.get("chapter_no", 0)), story_id=story_id)
    if group == "analysis":
        return delete_analysis_report(project_name, str(resource.get("analysis_type", "unknown")), int(resource.get("chapter_no") or 0), story_id=story_id)
    if group == "evaluation":
        return delete_evaluation_report(project_name, int(resource.get("chapter_no", 0)), story_id=story_id)
    if group == "run":
        return delete_pipeline_run(project_name, str(resource.get("run_id", "")), story_id=story_id)
    if group == "source":
        deleted = delete_retrieval_source_file(project_name, str(resource.get("relative_path", "")))
        if deleted:
            rebuild_retrieval_assets(project_name, build_vectors=True)
        return deleted
    raise ValueError(f"不支持删除这种资源类型：{group}")
