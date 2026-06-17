import hashlib
from datetime import datetime, timezone

from memory import (
    KNOWLEDGE_CATEGORIES,
    append_auto_review_run,
    confirm_pending_knowledge_items_with_records,
    load_auto_review_policy,
    load_pending_knowledge_items,
    save_pending_knowledge_items,
)


def knowledge_category_label(value: str) -> str:
    return KNOWLEDGE_CATEGORIES.get(str(value or ""), str(value or "未知知识"))


def safe_confidence(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.7
    return max(0.0, min(1.0, number))


def pending_quality_label(issue_info: dict) -> str:
    if not issue_info:
        return "质检=正常"
    type_labels = {
        "duplicate": "重复",
        "same_name_conflict": "冲突",
        "fact_conflict": "事实冲突",
        "alias_candidate": "别名",
        "confirmed_overlap": "已存在",
    }
    labels = [
        type_labels.get(issue_type, issue_type)
        for issue_type in sorted(issue_info.get("types", []))
    ]
    return f"质检={issue_info.get('severity', '低')}:{'/'.join(labels) if labels else '线索'}"


def summarize_item_evidence(item: dict) -> list[str]:
    evidence = item.get("evidence", [])
    if not isinstance(evidence, list):
        return []
    lines = []
    for evidence_item in evidence:
        if isinstance(evidence_item, dict):
            quote = str(evidence_item.get("quote") or evidence_item.get("text") or evidence_item.get("note") or "").strip()
            source_title = str(evidence_item.get("source_title") or "").strip()
            text = f"{source_title}: {quote}" if source_title and quote else quote
        else:
            text = str(evidence_item or "").strip()
        if text:
            lines.append(text[:180])
    return lines


def pending_item_risk_types(item: dict, issue_map: dict[str, dict]) -> set[str]:
    issue_info = issue_map.get(str(item.get("pending_id") or ""), {})
    risks = set(issue_info.get("types", set()))
    if safe_confidence(item.get("evidence_strength", 0.5)) < 0.45:
        risks.add("low_evidence")
    if safe_confidence(item.get("confidence", 0.7)) < 0.55:
        risks.add("low_confidence")
    if not summarize_item_evidence(item):
        risks.add("no_evidence")
    return risks


def evaluate_pending_auto_review_decision(item: dict, issue_map: dict, policy: dict | None = None) -> dict:
    active_policy = dict(policy or {})
    pending_id = str(item.get("pending_id") or "")
    category = str(item.get("category") or "")
    manual_categories = set(active_policy.get("manual_review_categories", []) if isinstance(active_policy.get("manual_review_categories", []), list) else [])
    if category in manual_categories:
        return {
            "pending_id": pending_id,
            "decision": "blocked",
            "grade": "C",
            "reason": f"{knowledge_category_label(category)} 需人工审核",
        }
    issue = issue_map.get(pending_id, {}) if isinstance(issue_map, dict) else {}
    if issue:
        return {
            "pending_id": pending_id,
            "decision": "blocked",
            "grade": "D" if issue.get("severity") == "高" else "C",
            "reason": pending_quality_label(issue),
        }
    try:
        confidence = float(item.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0
    try:
        evidence_strength = float(item.get("evidence_strength") or 0)
    except (TypeError, ValueError):
        evidence_strength = 0
    evidence = item.get("evidence", [])
    min_confidence = float(active_policy.get("min_confidence", 0.45))
    min_evidence_strength = float(active_policy.get("min_evidence_strength", 0.35))
    grade_a_confidence = float(active_policy.get("grade_a_confidence", 0.75))
    grade_a_evidence_strength = float(active_policy.get("grade_a_evidence_strength", 0.65))
    require_evidence = bool(active_policy.get("require_evidence", True))
    allow_grade_b = bool(active_policy.get("allow_grade_b_auto_confirm", True))
    if require_evidence and not evidence:
        return {
            "pending_id": pending_id,
            "decision": "blocked",
            "grade": "C",
            "reason": "缺少证据",
        }
    if confidence and confidence < min_confidence:
        return {
            "pending_id": pending_id,
            "decision": "blocked",
            "grade": "C",
            "reason": f"置信度偏低：{confidence:.2f}",
        }
    if evidence_strength and evidence_strength < min_evidence_strength:
        return {
            "pending_id": pending_id,
            "decision": "blocked",
            "grade": "C",
            "reason": f"证据强度偏低：{evidence_strength:.2f}",
        }
    grade = "A" if (confidence >= grade_a_confidence and evidence_strength >= grade_a_evidence_strength) else "B"
    if grade == "B" and not allow_grade_b:
        return {
            "pending_id": pending_id,
            "decision": "blocked",
            "grade": "B",
            "reason": "B 级条目按当前策略保留抽查",
        }
    return {
        "pending_id": pending_id,
        "decision": "confirm",
        "grade": grade,
        "reason": f"无质检风险，置信度 {confidence:.2f}，证据强度 {evidence_strength:.2f}",
    }


def pending_item_has_auto_confirm_risk(item: dict, issue_map: dict, policy: dict | None = None) -> bool:
    return evaluate_pending_auto_review_decision(item, issue_map, policy).get("decision") != "confirm"


def build_pending_auto_review_preview(items: list[dict], issue_map: dict, policy: dict | None = None) -> dict:
    rows = []
    confirmed_ids = []
    blocked_ids = []
    grade_counts: dict[str, int] = {}
    blocked_reason_counts: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        pending_id = str(item.get("pending_id") or "")
        if not pending_id:
            continue
        decision = evaluate_pending_auto_review_decision(item, issue_map, policy)
        grade = str(decision.get("grade") or "")
        reason = str(decision.get("reason") or "")
        grade_counts[grade] = grade_counts.get(grade, 0) + 1
        if decision.get("decision") == "confirm":
            confirmed_ids.append(pending_id)
            decision_label = "自动确认"
        else:
            blocked_ids.append(pending_id)
            blocked_reason_counts[reason] = blocked_reason_counts.get(reason, 0) + 1
            decision_label = "保留待确认"
        rows.append({
            "决策": decision_label,
            "等级": grade,
            "分类": knowledge_category_label(item.get("category", "")),
            "名称": item.get("name", ""),
            "置信度": f"{safe_confidence(item.get('confidence', 0)):.2f}",
            "证据": f"{safe_confidence(item.get('evidence_strength', 0)):.2f}",
            "原因": reason,
            "来源": item.get("source_title", "") or item.get("source_segment_title", ""),
        })
    rows.sort(key=lambda row: (0 if row.get("决策") == "保留待确认" else 1, row.get("等级", ""), row.get("分类", ""), row.get("名称", "")))
    return {
        "candidate_count": len(confirmed_ids) + len(blocked_ids),
        "confirmed_ids": confirmed_ids,
        "blocked_ids": blocked_ids,
        "grade_counts": grade_counts,
        "blocked_reason_counts": blocked_reason_counts,
        "rows": rows,
    }


def build_pending_triage_summary(pending_items: list[dict], issue_map: dict[str, dict], auto_preview: dict) -> dict:
    risk_counts = {
        "fact_conflict": 0,
        "same_name_conflict": 0,
        "confirmed_overlap": 0,
        "duplicate": 0,
        "alias_candidate": 0,
        "low_evidence": 0,
        "low_confidence": 0,
        "no_evidence": 0,
    }
    category_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    worldline_counts: dict[str, int] = {}
    for item in pending_items:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "unknown")
        source = str(item.get("source_title") or item.get("source_origin") or "未标明来源")
        worldline = str(item.get("worldline_label") or item.get("worldline_id") or "未标明")
        category_counts[category] = category_counts.get(category, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1
        worldline_counts[worldline] = worldline_counts.get(worldline, 0) + 1
        for risk in pending_item_risk_types(item, issue_map):
            if risk in risk_counts:
                risk_counts[risk] += 1

    return {
        "total": len(pending_items),
        "auto_confirm_count": len(auto_preview.get("confirmed_ids", [])),
        "manual_count": len(auto_preview.get("blocked_ids", [])),
        "grade_counts": auto_preview.get("grade_counts", {}),
        "blocked_reason_counts": auto_preview.get("blocked_reason_counts", {}),
        "risk_counts": risk_counts,
        "category_counts": category_counts,
        "source_counts": source_counts,
        "worldline_counts": worldline_counts,
    }


def build_pending_clear_plan(
    pending_items: list[dict],
    issue_map: dict[str, dict],
    policy: dict,
    *,
    archive_low_quality: bool = True,
) -> dict:
    decisions = []
    counts = {
        "confirm": 0,
        "manual_review": 0,
        "archive": 0,
    }
    manual_categories = set(policy.get("manual_review_categories", []) if isinstance(policy.get("manual_review_categories", []), list) else [])
    for item in pending_items:
        if not isinstance(item, dict):
            continue
        pending_id = str(item.get("pending_id") or "")
        if not pending_id:
            continue
        auto_decision = evaluate_pending_auto_review_decision(item, issue_map, policy)
        risks = pending_item_risk_types(item, issue_map)
        category = str(item.get("category") or "")
        action = "manual_review"
        reason = auto_decision.get("reason") or "需要人工复核"

        if auto_decision.get("decision") == "confirm":
            action = "confirm"
            reason = auto_decision.get("reason") or "低风险自动入库"
        elif category in manual_categories:
            action = "manual_review"
            reason = f"{knowledge_category_label(category)} 按策略进入人工复核箱"
        elif risks & {"fact_conflict", "same_name_conflict", "confirmed_overlap"}:
            action = "manual_review"
            reason = "存在事实冲突、同名冲突或正式库已有条目"
        elif risks & {"duplicate", "alias_candidate"}:
            action = "manual_review"
            reason = "疑似重复或别名，适合人工合并"
        elif archive_low_quality and risks & {"low_evidence", "low_confidence", "no_evidence"}:
            action = "archive"
            reason = "低证据、低置信或无证据，归档丢弃并保留快照"

        counts[action] += 1
        decisions.append({
            "pending_id": pending_id,
            "action": action,
            "reason": reason,
            "grade": auto_decision.get("grade", ""),
            "category": category,
            "category_label": knowledge_category_label(category),
            "name": item.get("name", "未命名"),
            "source_title": item.get("source_title", "") or item.get("source_segment_title", ""),
            "confidence": safe_confidence(item.get("confidence", 0.0)),
            "evidence_strength": safe_confidence(item.get("evidence_strength", 0.0)),
            "risks": sorted(risks),
        })
    return {
        "total": len(decisions),
        "counts": counts,
        "decisions": decisions,
        "archive_low_quality": archive_low_quality,
    }


def execute_pending_clear_plan(project_name: str, plan: dict, *, note: str = "") -> dict:
    decisions = [item for item in plan.get("decisions", []) if isinstance(item, dict)]
    if not decisions:
        return {"success": False, "message": "处理方案为空。"}

    pending = load_pending_knowledge_items(project_name)
    pending_by_id = {
        str(item.get("pending_id") or ""): item
        for item in pending
        if isinstance(item, dict) and item.get("pending_id")
    }
    candidate_ids = [
        str(decision.get("pending_id") or "")
        for decision in decisions
        if str(decision.get("pending_id") or "") in pending_by_id
    ]
    if not candidate_ids:
        return {"success": False, "message": "方案中的条目已经不在待确认队列里。"}

    action_by_id = {
        str(decision.get("pending_id") or ""): str(decision.get("action") or "manual_review")
        for decision in decisions
    }
    confirm_ids = [pending_id for pending_id in candidate_ids if action_by_id.get(pending_id) == "confirm"]
    archive_ids = [pending_id for pending_id in candidate_ids if action_by_id.get(pending_id) == "archive"]
    manual_ids = [pending_id for pending_id in candidate_ids if action_by_id.get(pending_id) == "manual_review"]

    run_at = datetime.now(timezone.utc).isoformat()
    id_digest = hashlib.sha1("|".join(sorted(candidate_ids)).encode("utf-8")).hexdigest()[:10]
    run_id = f"pending_batch_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{id_digest}"

    confirm_result = confirm_pending_knowledge_items_with_records(
        project_name,
        confirm_ids,
        confirmation_metadata={
            "auto_review_run_id": run_id,
            "auto_reviewed_at": run_at,
            "pending_batch_action": "confirm",
        },
    ) if confirm_ids else {"saved_count": 0, "confirmed_records": [], "pending_snapshots": []}

    pending_after_confirm = load_pending_knowledge_items(project_name)
    remove_ids = set(archive_ids + manual_ids)
    if remove_ids:
        remaining = [
            item for item in pending_after_confirm
            if str(item.get("pending_id") or "") not in remove_ids
        ]
        save_pending_knowledge_items(project_name, remaining)

    archive_snapshots = []
    manual_snapshots = []
    for pending_id in archive_ids:
        snapshot = dict(pending_by_id.get(pending_id, {}))
        if snapshot:
            snapshot["pending_batch_action"] = "archive"
            snapshot["processed_batch_id"] = run_id
            archive_snapshots.append(snapshot)
    for pending_id in manual_ids:
        snapshot = dict(pending_by_id.get(pending_id, {}))
        if snapshot:
            snapshot["pending_batch_action"] = "manual_review"
            snapshot["processed_batch_id"] = run_id
            manual_snapshots.append(snapshot)

    pending_snapshots = []
    seen_snapshot_ids = set()
    for snapshot in list(confirm_result.get("pending_snapshots", [])) + archive_snapshots + manual_snapshots:
        pending_id = str(snapshot.get("pending_id") or "")
        if pending_id and pending_id in seen_snapshot_ids:
            continue
        if pending_id:
            seen_snapshot_ids.add(pending_id)
        pending_snapshots.append(dict(snapshot))

    decision_rows = [
        decision for decision in decisions
        if str(decision.get("pending_id") or "") in set(candidate_ids)
    ]
    run = append_auto_review_run(project_name, {
        "run_id": run_id,
        "source_type": "pending_batch_process",
        "source_title": "待确认清空模式",
        "note": note or "执行待确认清空方案",
        "candidate_ids": candidate_ids,
        "confirmed_ids": confirm_ids,
        "blocked_ids": manual_ids,
        "archived_ids": archive_ids,
        "manual_review_ids": manual_ids,
        "decisions": decision_rows,
        "confirmed_records": confirm_result.get("confirmed_records", []),
        "pending_snapshots": pending_snapshots,
        "archived_snapshots": archive_snapshots,
        "manual_review_snapshots": manual_snapshots,
        "saved_count": int(confirm_result.get("saved_count", 0)),
        "policy": load_auto_review_policy(project_name),
        "batch_summary": {
            "total": len(candidate_ids),
            "confirmed": len(confirm_ids),
            "archived": len(archive_ids),
            "manual_review": len(manual_ids),
        },
    })
    if int(confirm_result.get("saved_count", 0)):
        from retrieval import rebuild_retrieval_assets

        rebuild_retrieval_assets(project_name, build_vectors=True)
    return {
        "success": True,
        "message": (
            f"处理完成：入库 {int(confirm_result.get('saved_count', 0))} 条，"
            f"归档 {len(archive_ids)} 条，进入复核箱 {len(manual_ids)} 条。"
        ),
        "run_id": run.get("run_id", run_id),
        "confirmed_count": int(confirm_result.get("saved_count", 0)),
        "archived_count": len(archive_ids),
        "manual_review_count": len(manual_ids),
    }
