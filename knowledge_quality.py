import hashlib
import json
import re

from knowledge_workflows import knowledge_category_label, safe_confidence
from memory import (
    load_entity_aliases,
    load_knowledge_base,
    save_entity_aliases,
)


def normalize_knowledge_match_name(value: str) -> str:
    cleaned = str(value or "").lower()
    return "".join(re.findall(r"[a-z0-9\u4e00-\u9fff]+", cleaned))


def merge_text_values(values: list[str], separator: str = "\n\n") -> str:
    merged = []
    seen = set()
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        merged.append(cleaned)
    return separator.join(merged)


def merge_list_values(values: list) -> list:
    merged = []
    seen = set()
    for value in values:
        if isinstance(value, list):
            candidates = value
        else:
            candidates = [value]
        for candidate in candidates:
            marker = json.dumps(candidate, ensure_ascii=False, sort_keys=True) if isinstance(candidate, dict) else str(candidate)
            if not marker.strip() or marker in seen:
                continue
            seen.add(marker)
            merged.append(candidate)
    return merged


def find_duplicate_knowledge_groups(items: list[dict]) -> list[list[int]]:
    groups: dict[str, list[int]] = {}
    for index, item in enumerate(items):
        key = normalize_knowledge_match_name(item.get("name", ""))
        if not key:
            continue
        groups.setdefault(key, []).append(index)
    return [indices for indices in groups.values() if len(indices) > 1]


def normalized_knowledge_key(item: dict) -> tuple[str, str]:
    return (
        str(item.get("category") or "").strip(),
        normalize_knowledge_match_name(item.get("name", "")),
    )


def normalized_summary_tokens(item: dict) -> set[str]:
    text = normalize_knowledge_match_name(" ".join([
        str(item.get("name", "") or ""),
        str(item.get("summary", "") or ""),
    ]))
    if not text:
        return set()
    cjk_chars = set(re.findall(r"[\u4e00-\u9fff]", text))
    ascii_words = set(re.findall(r"[a-z0-9]{2,}", text))
    return cjk_chars | ascii_words


def details_conflicts(left: dict, right: dict) -> list[str]:
    left_details = left.get("details", {}) if isinstance(left.get("details", {}), dict) else {}
    right_details = right.get("details", {}) if isinstance(right.get("details", {}), dict) else {}
    conflicts = []
    for key in sorted(set(left_details.keys()) & set(right_details.keys()), key=str):
        left_value = normalize_knowledge_match_name(left_details.get(key, ""))
        right_value = normalize_knowledge_match_name(right_details.get(key, ""))
        if left_value and right_value and left_value != right_value:
            conflicts.append(str(key))
    return conflicts


def canon_status_conflict(left: dict, right: dict) -> bool:
    left_status = str(left.get("canon_status") or "unknown")
    right_status = str(right.get("canon_status") or "unknown")
    if "unknown" in {left_status, right_status}:
        return False
    return left_status != right_status


FACT_FIELD_GROUPS = {
    "身份/职位": ["身份", "职位", "职业", "头衔", "称号", "role", "identity", "job", "title", "position"],
    "年龄/阶段": ["年龄", "年纪", "阶段", "时期", "age", "stage"],
    "阵营/归属": ["阵营", "归属", "所属", "组织", "派系", "立场", "affiliation", "faction", "side", "organization"],
    "关系状态": ["关系", "亲属", "恋人", "伴侣", "敌对", "relationship", "relation", "status"],
    "能力/限制": ["能力", "技能", "限制", "弱点", "代价", "条件", "ability", "power", "limit", "weakness", "cost"],
    "时间/顺序": ["时间", "日期", "顺序", "前后", "发生", "timeline", "time", "date", "order"],
    "地点/位置": ["地点", "位置", "所在地", "场景", "location", "place"],
    "性格/动机": ["性格", "动机", "目标", "态度", "personality", "motivation", "goal"],
}


def normalize_fact_value(value) -> str:
    if isinstance(value, list):
        text = " ".join(str(item) for item in value if str(item).strip())
    elif isinstance(value, dict):
        text = " ".join(f"{key}:{item}" for key, item in value.items() if str(item).strip())
    else:
        text = str(value or "")
    text = re.sub(r"\s+", "", text.lower())
    return "".join(re.findall(r"[a-z0-9\u4e00-\u9fff]+", text))


def fact_field_label(key: str) -> str | None:
    normalized_key = normalize_knowledge_match_name(key)
    if not normalized_key:
        return None
    for label, keywords in FACT_FIELD_GROUPS.items():
        for keyword in keywords:
            normalized_keyword = normalize_knowledge_match_name(keyword)
            if normalized_keyword and normalized_keyword in normalized_key:
                return label
    return None


def extract_fact_claims(item: dict) -> dict[str, list[dict]]:
    details = item.get("details", {}) if isinstance(item.get("details", {}), dict) else {}
    claims: dict[str, list[dict]] = {}
    for key, value in details.items():
        label = fact_field_label(str(key))
        normalized_value = normalize_fact_value(value)
        if not label or not normalized_value:
            continue
        raw_value = str(value)
        if len(raw_value) > 240:
            raw_value = raw_value[:240] + "..."
        claims.setdefault(label, []).append({
            "field": str(key),
            "value": raw_value,
            "normalized": normalized_value,
        })
    return claims


def fact_conflicts(left: dict, right: dict) -> list[dict]:
    left_claims = extract_fact_claims(left)
    right_claims = extract_fact_claims(right)
    conflicts = []
    for label in sorted(set(left_claims) & set(right_claims)):
        left_values = {claim["normalized"] for claim in left_claims[label]}
        right_values = {claim["normalized"] for claim in right_claims[label]}
        if not left_values or not right_values or left_values == right_values:
            continue
        conflicts.append({
            "fact": label,
            "left": "；".join(f"{claim['field']}={claim['value']}" for claim in left_claims[label][:3]),
            "right": "；".join(f"{claim['field']}={claim['value']}" for claim in right_claims[label][:3]),
        })
    return conflicts


def recommend_fact_conflict_resolution(left: dict, right: dict) -> str:
    left_score = safe_confidence(left.get("evidence_strength", 0.5)) + safe_confidence(left.get("confidence", 0.7))
    right_score = safe_confidence(right.get("evidence_strength", 0.5)) + safe_confidence(right.get("confidence", 0.7))
    left_status = str(left.get("canon_status") or "unknown")
    right_status = str(right.get("canon_status") or "unknown")
    if left_status == "canon" and right_status != "canon":
        return f"建议优先保留《{left.get('source_title') or left.get('name') or '左侧条目'}》中的 canon 事实，把另一条降为 inferred/ambiguous 或作为备注。"
    if right_status == "canon" and left_status != "canon":
        return f"建议优先保留《{right.get('source_title') or right.get('name') or '右侧条目'}》中的 canon 事实，把另一条降为 inferred/ambiguous 或作为备注。"
    if abs(left_score - right_score) >= 0.2:
        winner = left if left_score > right_score else right
        return f"建议优先核对并保留证据更强的一条：{winner.get('source_title') or winner.get('name') or '未命名来源'}。"
    return "建议人工核对原文证据；若属于不同时间点或不同版本，请拆成时间线/版本限定事实，而不是直接覆盖。"


def possible_alias_pair(left: dict, right: dict) -> bool:
    if str(left.get("category") or "") != str(right.get("category") or ""):
        return False
    left_name = normalize_knowledge_match_name(left.get("name", ""))
    right_name = normalize_knowledge_match_name(right.get("name", ""))
    if not left_name or not right_name or left_name == right_name:
        return False
    if len(left_name) >= 2 and len(right_name) >= 2 and (left_name in right_name or right_name in left_name):
        return True
    left_chars = set(re.findall(r"[\u4e00-\u9fff]", left_name))
    right_chars = set(re.findall(r"[\u4e00-\u9fff]", right_name))
    if left_chars and right_chars:
        overlap_ratio = len(left_chars & right_chars) / max(min(len(left_chars), len(right_chars)), 1)
        if overlap_ratio >= 0.5:
            left_tokens = normalized_summary_tokens(left)
            right_tokens = normalized_summary_tokens(right)
            return bool(left_tokens & right_tokens)
    return False


def make_alias_id(category: str, canonical_name: str) -> str:
    key = normalize_knowledge_match_name(f"{category}_{canonical_name}")
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10] if key else hashlib.sha1(canonical_name.encode("utf-8")).hexdigest()[:10]
    return f"alias_{digest}"


def upsert_entity_alias_group(
    project_name: str,
    *,
    category: str,
    canonical_name: str,
    aliases: list[str],
    notes: str = "",
    source_pending_ids: list[str] | None = None,
) -> dict:
    clean_category = str(category or "characters").strip()
    clean_canonical = str(canonical_name or "").strip()
    clean_aliases = []
    seen = set()
    for value in [clean_canonical] + list(aliases or []):
        cleaned = str(value or "").strip()
        key = normalize_knowledge_match_name(cleaned)
        if not cleaned or not key or key in seen:
            continue
        seen.add(key)
        clean_aliases.append(cleaned)
    if not clean_canonical and clean_aliases:
        clean_canonical = clean_aliases[0]
    if not clean_canonical:
        raise ValueError("别名组主名称不能为空。")

    alias_groups = load_entity_aliases(project_name)
    target_key = normalize_knowledge_match_name(clean_canonical)
    alias_keys = {normalize_knowledge_match_name(value) for value in clean_aliases}
    matched_index = None
    for index, group in enumerate(alias_groups):
        if str(group.get("category") or "") != clean_category:
            continue
        group_names = [group.get("canonical_name", "")] + list(group.get("aliases", []) if isinstance(group.get("aliases", []), list) else [])
        group_keys = {normalize_knowledge_match_name(value) for value in group_names if normalize_knowledge_match_name(value)}
        if target_key in group_keys or group_keys & alias_keys:
            matched_index = index
            break

    payload = {
        "id": make_alias_id(clean_category, clean_canonical),
        "category": clean_category,
        "canonical_name": clean_canonical,
        "aliases": clean_aliases,
        "notes": notes.strip(),
        "source_pending_ids": merge_list_values([source_pending_ids or []]),
        "status": "active",
    }
    if matched_index is None:
        alias_groups.append(payload)
    else:
        existing = dict(alias_groups[matched_index])
        existing_aliases = existing.get("aliases", []) if isinstance(existing.get("aliases", []), list) else []
        existing["canonical_name"] = existing.get("canonical_name") or clean_canonical
        existing["aliases"] = merge_list_values([existing_aliases, clean_aliases])
        existing["notes"] = merge_text_values([existing.get("notes", ""), payload["notes"]])
        existing["source_pending_ids"] = merge_list_values([existing.get("source_pending_ids", []), payload["source_pending_ids"]])
        existing["status"] = "active"
        payload = existing
        alias_groups[matched_index] = existing
    save_entity_aliases(project_name, alias_groups)
    return payload


def build_pending_knowledge_quality_issues(project_name: str, pending_items: list[dict]) -> list[dict]:
    issues: list[dict] = []
    by_key: dict[tuple[str, str], list[tuple[int, dict]]] = {}
    for index, item in enumerate(pending_items):
        key = normalized_knowledge_key(item)
        if key[0] and key[1]:
            by_key.setdefault(key, []).append((index, item))

    for (category, _), indexed_items in by_key.items():
        if len(indexed_items) < 2:
            continue
        items = [item for _, item in indexed_items]
        names = [str(item.get("name") or "未命名") for item in items]
        pending_ids = [str(item.get("pending_id") or "") for item in items if item.get("pending_id")]
        pair_conflicts = []
        for left_index in range(len(items)):
            for right_index in range(left_index + 1, len(items)):
                fields = details_conflicts(items[left_index], items[right_index])
                if fields:
                    pair_conflicts.append(f"字段差异：{', '.join(fields[:4])}")
                if canon_status_conflict(items[left_index], items[right_index]):
                    pair_conflicts.append("原作状态不一致")
                fact_diffs = fact_conflicts(items[left_index], items[right_index])
                if fact_diffs:
                    pair_conflicts.append("事实冲突：" + "、".join(diff["fact"] for diff in fact_diffs[:4]))
        issues.append({
            "type": "same_name_conflict" if pair_conflicts else "duplicate",
            "severity": "高" if pair_conflicts else "中",
            "category": category,
            "title": f"{knowledge_category_label(category)} / {names[0]}",
            "description": "；".join(pair_conflicts[:4]) if pair_conflicts else f"同分类同名待确认条目 {len(items)} 条，建议合并或只保留证据更强的一条。",
            "pending_ids": pending_ids,
            "indices": [index for index, _ in indexed_items],
        })

        for left_index, left_item in indexed_items:
            for right_index, right_item in indexed_items:
                if left_index >= right_index:
                    continue
                fact_diffs = fact_conflicts(left_item, right_item)
                if not fact_diffs:
                    continue
                diff_text = "；".join(
                    f"{diff['fact']}：{diff['left']} <> {diff['right']}"
                    for diff in fact_diffs[:3]
                )
                issues.append({
                    "type": "fact_conflict",
                    "severity": "高",
                    "category": category,
                    "title": f"{knowledge_category_label(category)} / {left_item.get('name') or right_item.get('name') or '未命名'}",
                    "description": diff_text,
                    "recommendation": recommend_fact_conflict_resolution(left_item, right_item),
                    "pending_ids": [
                        str(left_item.get("pending_id") or ""),
                        str(right_item.get("pending_id") or ""),
                    ],
                    "indices": [left_index, right_index],
                })

    for left_index in range(len(pending_items)):
        left = pending_items[left_index]
        for right_index in range(left_index + 1, len(pending_items)):
            right = pending_items[right_index]
            if possible_alias_pair(left, right):
                issues.append({
                    "type": "alias_candidate",
                    "severity": "低",
                    "category": left.get("category", ""),
                    "title": f"{left.get('name', '未命名')} / {right.get('name', '未命名')}",
                    "description": "名称或文本高度相近，可能是同一实体的别名、称呼或拆分条目。",
                    "pending_ids": [
                        str(left.get("pending_id") or ""),
                        str(right.get("pending_id") or ""),
                    ],
                    "indices": [left_index, right_index],
                })

    confirmed_by_key: dict[tuple[str, str], list[dict]] = {}
    for category, items in load_knowledge_base(project_name).items():
        for item in items:
            if isinstance(item, dict):
                key = (category, normalize_knowledge_match_name(item.get("name", "")))
                if key[1]:
                    confirmed_by_key.setdefault(key, []).append(item)

    for index, item in enumerate(pending_items):
        key = normalized_knowledge_key(item)
        matches = confirmed_by_key.get(key, [])
        if not matches:
            continue
        conflicts = []
        for confirmed in matches[:3]:
            fields = details_conflicts(item, confirmed)
            if fields:
                conflicts.append(f"与已确认条目字段差异：{', '.join(fields[:4])}")
            if canon_status_conflict(item, confirmed):
                conflicts.append("与已确认条目原作状态不一致")
            fact_diffs = fact_conflicts(item, confirmed)
            if fact_diffs:
                issues.append({
                    "type": "fact_conflict",
                    "severity": "高",
                    "category": item.get("category", ""),
                    "title": f"{knowledge_category_label(item.get('category', ''))} / {item.get('name', '未命名')}",
                    "description": "；".join(
                        f"与正式库事实冲突：{diff['fact']}：{diff['left']} <> {diff['right']}"
                        for diff in fact_diffs[:3]
                    ),
                    "recommendation": recommend_fact_conflict_resolution(item, confirmed),
                    "pending_ids": [str(item.get("pending_id") or "")],
                    "indices": [index],
                    "confirmed_count": len(matches),
                })
        issues.append({
            "type": "confirmed_overlap",
            "severity": "高" if conflicts else "中",
            "category": item.get("category", ""),
            "title": f"{knowledge_category_label(item.get('category', ''))} / {item.get('name', '未命名')}",
            "description": "；".join(conflicts[:4]) if conflicts else f"正式知识库已有 {len(matches)} 条同名知识，确认前建议核对是否重复。",
            "pending_ids": [str(item.get("pending_id") or "")],
            "indices": [index],
            "confirmed_count": len(matches),
        })

    severity_order = {"高": 0, "中": 1, "低": 2}
    type_order = {"fact_conflict": 0, "same_name_conflict": 1, "confirmed_overlap": 2, "duplicate": 3, "alias_candidate": 4}
    return sorted(issues, key=lambda issue: (
        severity_order.get(issue.get("severity", "低"), 9),
        type_order.get(issue.get("type", ""), 9),
        issue.get("title", ""),
    ))


def build_pending_issue_map(issues: list[dict]) -> dict[str, dict]:
    severity_rank = {"高": 3, "中": 2, "低": 1}
    mapped: dict[str, dict] = {}
    for issue in issues:
        severity = str(issue.get("severity") or "低")
        issue_type = str(issue.get("type") or "")
        description = str(issue.get("description") or "")
        for pending_id in issue.get("pending_ids", []):
            pending_id = str(pending_id or "")
            if not pending_id:
                continue
            current = mapped.setdefault(pending_id, {
                "severity": severity,
                "types": set(),
                "descriptions": [],
            })
            if severity_rank.get(severity, 0) > severity_rank.get(current.get("severity", "低"), 0):
                current["severity"] = severity
            if issue_type:
                current["types"].add(issue_type)
            if description and description not in current["descriptions"]:
                current["descriptions"].append(description)
    return mapped
