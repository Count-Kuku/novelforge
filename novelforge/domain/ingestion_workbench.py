"""Pure status aggregation for the source-ingestion workbench."""
from __future__ import annotations


def summarize_long_reference_resume_state(segments: list[dict]) -> dict:
    pending_import_indices = []
    pending_extract_indices = []
    imported_not_extracted_indices = []
    failed_indices = []
    completed_indices = []
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        import_status = str(segment.get("import_status") or "pending")
        extract_status = str(segment.get("extract_status") or "pending")
        if import_status != "imported":
            pending_import_indices.append(index)
        if extract_status in {"pending", ""}:
            pending_extract_indices.append(index)
            if import_status == "imported":
                imported_not_extracted_indices.append(index)
        if extract_status == "failed":
            failed_indices.append(index)
        if extract_status in {"queued", "extracted"}:
            completed_indices.append(index)
    unfinished_indices = sorted(set(pending_import_indices + pending_extract_indices + failed_indices))
    return {
        "pending_import_indices": pending_import_indices,
        "pending_extract_indices": pending_extract_indices,
        "imported_not_extracted_indices": imported_not_extracted_indices,
        "failed_indices": failed_indices,
        "completed_indices": completed_indices,
        "unfinished_indices": unfinished_indices,
    }


def _batch_action(
    *,
    action_id: str,
    priority: int,
    tone: str,
    title: str,
    detail: str,
    button_label: str,
    target_section: str,
    batch_id: str = "",
    task_id: str = "",
) -> dict:
    return {
        "action_id": action_id,
        "priority": priority,
        "tone": tone,
        "title": title,
        "detail": detail,
        "button_label": button_label,
        "target_section": target_section,
        "batch_id": batch_id,
        "task_id": task_id,
    }


def build_ingestion_workbench_summary(
    batches: list[dict],
    *,
    source_count: int,
    health: dict,
    tasks: list[dict] | None = None,
) -> dict:
    """Turn ingestion internals into user-facing status rows and actions."""
    batch_rows = []
    actions = []
    task_rows = []
    active_task_count = 0
    failed_task_count = 0
    active_task_batch_ids = set()
    unfinished_batch_count = 0
    completed_batch_count = 0
    empty_batch_count = 0

    task_status_labels = {
        "queued": "等待开始",
        "running": "处理中",
        "paused": "已暂停",
        "failed": "执行中断",
        "completed_with_errors": "部分失败",
        "completed": "已完成",
        "cancelled": "已取消",
    }
    for task in tasks or []:
        task_id = str(task.get("task_id") or task.get("run_id") or "")
        batch_id = str(task.get("batch_id") or "")
        status = str(task.get("status") or "queued")
        progress = dict(task.get("progress") or {})
        if status not in {"completed", "cancelled"}:
            active_task_count += 1
            if batch_id:
                active_task_batch_ids.add(batch_id)
        if status in {"failed", "completed_with_errors"}:
            failed_task_count += 1
            actions.append(_batch_action(
                action_id=f"recover_task:{task_id}",
                priority=110 if status == "failed" else 105,
                tone="error",
                title=f"处理任务失败项：{task.get('title') or '资料任务'}",
                detail=(
                    f"已完成 {progress.get('completed', 0)} / {progress.get('total', 0)} 个片段，"
                    f"失败 {progress.get('failed', 0)} 个；可以只重试失败项。"
                ),
                button_label="查看并重试",
                target_section="资料任务",
                batch_id=batch_id,
                task_id=task_id,
            ))
        elif status in {"queued", "running", "paused"}:
            actions.append(_batch_action(
                action_id=f"continue_task:{task_id}",
                priority=92 if status == "running" else 88,
                tone="warning",
                title=f"继续任务：{task.get('title') or '资料任务'}",
                detail=(
                    f"已完成 {progress.get('completed', 0)} / {progress.get('total', 0)} 个片段，"
                    f"剩余 {progress.get('remaining', 0)} 个。"
                ),
                button_label="打开资料任务",
                target_section="资料任务",
                batch_id=batch_id,
                task_id=task_id,
            ))
        task_rows.append({
            "task_id": task_id,
            "batch_id": batch_id,
            "title": str(task.get("title") or "资料任务"),
            "status": status,
            "status_label": task_status_labels.get(status, status),
            "total_count": int(progress.get("total") or 0),
            "completed_count": int(progress.get("completed") or 0),
            "remaining_count": int(progress.get("remaining") or 0),
            "failed_count": int(progress.get("failed") or 0),
            "updated_at": str(task.get("updated_at") or ""),
        })

    for batch in batches:
        batch_id = str(batch.get("batch_id") or "")
        title = str(batch.get("title") or "未命名资料批次")
        segments = [item for item in batch.get("segments", []) if isinstance(item, dict)]
        resume_state = summarize_long_reference_resume_state(segments)
        failed_count = len(resume_state["failed_indices"])
        pending_import_count = len(resume_state["pending_import_indices"])
        pending_extract_count = len(resume_state["pending_extract_indices"])
        imported_not_extracted_count = len(resume_state["imported_not_extracted_indices"])
        unfinished_count = len(resume_state["unfinished_indices"])

        if not segments:
            status = "attention"
            status_label = "没有片段"
            empty_batch_count += 1
            actions.append(_batch_action(
                action_id=f"inspect_empty_batch:{batch_id}",
                priority=90,
                tone="error",
                title=f"检查《{title}》的空批次",
                detail="这个批次没有可处理片段，请检查原文解析结果，或删除后重新导入。",
                button_label="检查资料批次",
                target_section="长篇批次",
                batch_id=batch_id,
            ))
        elif failed_count:
            status = "attention"
            status_label = "存在失败"
            if batch_id not in active_task_batch_ids:
                actions.append(_batch_action(
                    action_id=f"retry_batch:{batch_id}",
                    priority=100,
                    tone="error",
                    title=f"重试《{title}》的失败片段",
                    detail=f"有 {failed_count} 个片段提取失败；已成功的片段会保留，不需要重做。",
                    button_label="前往批次重试",
                    target_section="长篇批次",
                    batch_id=batch_id,
                ))
        elif unfinished_count:
            status = "processing"
            status_label = "等待继续"
            if imported_not_extracted_count:
                detail = f"有 {imported_not_extracted_count} 个已导入片段尚未整理为知识。"
            elif pending_import_count:
                detail = f"有 {pending_import_count} 个片段尚未保存为可匹配原文。"
            else:
                detail = f"还有 {pending_extract_count} 个片段等待整理。"
            if batch_id not in active_task_batch_ids:
                actions.append(_batch_action(
                    action_id=f"continue_batch:{batch_id}",
                    priority=75,
                    tone="warning",
                    title=f"继续处理《{title}》",
                    detail=detail,
                    button_label="继续处理批次",
                    target_section="长篇批次",
                    batch_id=batch_id,
                ))
        else:
            status = "ready"
            status_label = "处理完成"

        if unfinished_count or not segments:
            unfinished_batch_count += 1
        else:
            completed_batch_count += 1
        batch_rows.append({
            "batch_id": batch_id,
            "title": title,
            "status": status,
            "status_label": status_label,
            "segment_count": len(segments),
            "failed_count": failed_count,
            "pending_import_count": pending_import_count,
            "pending_extract_count": pending_extract_count,
            "completed_count": len(resume_state["completed_indices"]),
            "updated_at": str(batch.get("updated_at") or ""),
        })

    pending_count = int(health.get("pending_count") or 0)
    high_risk_count = int(health.get("high_risk_issue_count") or 0)
    if high_risk_count:
        actions.append(_batch_action(
            action_id="review_high_risk_pending",
            priority=95,
            tone="error",
            title="处理高风险待审核知识",
            detail=f"当前有 {high_risk_count} 条高风险线索，需要比较原文证据和已有知识后再决定。",
            button_label="进入待审核知识",
            target_section="待审核知识",
        ))
    elif pending_count:
        actions.append(_batch_action(
            action_id="review_pending",
            priority=80,
            tone="warning",
            title="审核新整理出的知识",
            detail=f"有 {pending_count} 条待审核知识；确认后才会成为后续写作使用的正式知识。",
            button_label="进入待审核知识",
            target_section="待审核知识",
        ))

    confirmed_count = int(health.get("confirmed_count") or 0)
    if not batches and not source_count and not confirmed_count:
        actions.append(_batch_action(
            action_id="start_ingestion",
            priority=70,
            tone="info",
            title="导入第一份资料",
            detail="整本原作用“长篇文本”，少量设定或百科内容可以直接粘贴。",
            button_label="查看导入向导",
            target_section="导入向导",
        ))
    elif health.get("missing_confirmed") and not pending_count:
        missing_count = len(health.get("missing_confirmed", []))
        actions.append(_batch_action(
            action_id="fill_knowledge_gaps",
            priority=45,
            tone="info",
            title="补充资料缺口",
            detail=f"正式知识库仍有 {missing_count} 个空白分类，可以继续导入资料或对已有批次执行专项提取。",
            button_label="查看导入向导",
            target_section="导入向导",
        ))

    actions.sort(key=lambda item: (-int(item.get("priority") or 0), str(item.get("action_id") or "")))
    failed_segment_count = int(health.get("failed_segments") or 0)
    risk_count = failed_segment_count + high_risk_count + empty_batch_count + failed_task_count
    if risk_count:
        overall_status = "attention"
    elif pending_count or unfinished_batch_count or active_task_count:
        overall_status = "processing"
    elif source_count or confirmed_count:
        overall_status = "ready"
    else:
        overall_status = "empty"

    return {
        "overall_status": overall_status,
        "health_score": int(health.get("score") or 0),
        "needs_processing_count": (
            active_task_count
            + len([
                row for row in batch_rows
                if row.get("status") != "ready" and row.get("batch_id") not in active_task_batch_ids
            ])
            + (1 if pending_count else 0)
        ),
        "active_task_count": active_task_count,
        "failed_task_count": failed_task_count,
        "unfinished_batch_count": unfinished_batch_count,
        "completed_batch_count": completed_batch_count,
        "ready_source_count": int(source_count),
        "confirmed_knowledge_count": confirmed_count,
        "pending_review_count": pending_count,
        "risk_count": risk_count,
        "failed_segment_count": failed_segment_count,
        "high_risk_count": high_risk_count,
        "empty_batch_count": empty_batch_count,
        "batch_rows": batch_rows,
        "task_rows": task_rows,
        "actions": actions,
        "health": health,
    }
