import re
from typing import Any


def normalize_asset_text(value: Any) -> str:
    text = str(value or "").strip().casefold()
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def _ngrams(text: str, size: int = 2) -> set[str]:
    cleaned = normalize_asset_text(text)
    if not cleaned:
        return set()
    if len(cleaned) <= size:
        return {cleaned}
    return {cleaned[index:index + size] for index in range(0, len(cleaned) - size + 1)}


def text_similarity(left: Any, right: Any) -> float:
    left_key = normalize_asset_text(left)
    right_key = normalize_asset_text(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    shorter, longer = sorted([left_key, right_key], key=len)
    if len(shorter) >= 16 and shorter in longer:
        return 0.92
    left_ngrams = _ngrams(left_key)
    right_ngrams = _ngrams(right_key)
    if not left_ngrams or not right_ngrams:
        return 0.0
    return len(left_ngrams & right_ngrams) / len(left_ngrams | right_ngrams)


def _issue(level: str, reason: str, item: dict, score: float = 0.0, layer: str = "") -> dict:
    return {
        "level": level,
        "reason": reason,
        "item": item,
        "score": round(float(score), 3),
        "layer": layer,
    }


def _top_issues(issues: list[dict], limit: int = 4) -> list[dict]:
    rank = {"duplicate": 0, "warning": 1, "related": 2}
    issues.sort(key=lambda item: (rank.get(item.get("level", "related"), 9), -float(item.get("score") or 0)))
    deduped: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for issue in issues:
        existing = issue.get("item") if isinstance(issue.get("item"), dict) else {}
        key = (str(issue.get("layer") or ""), str(existing.get("id") or existing.get("name") or existing.get("content") or existing.get("summary") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
        if len(deduped) >= limit:
            break
    return deduped


def analyze_setting_candidate(candidate: dict, existing_settings: list[dict]) -> list[dict]:
    summary = str(candidate.get("summary") or "")
    name = str(candidate.get("name") or "")
    category = str(candidate.get("category") or "")
    field_name = str(candidate.get("setting_field") or "")
    issues: list[dict] = []
    for existing in existing_settings:
        if not isinstance(existing, dict):
            continue
        same_field = category == str(existing.get("category") or "") and field_name == str(existing.get("setting_field") or "")
        summary_score = text_similarity(summary, existing.get("summary", ""))
        name_score = text_similarity(name, existing.get("name", ""))
        if str(candidate.get("id") or "") and str(candidate.get("id") or "") == str(existing.get("id") or ""):
            issues.append(_issue("duplicate", "ID 已存在，确认会更新这个设定。", existing, 1.0))
        elif summary_score >= 0.96:
            issues.append(_issue("duplicate", "设定内容几乎相同。", existing, summary_score))
        elif name_score >= 0.96:
            issues.append(_issue("warning", "名称相同或极其相近，需要确认是覆盖还是并列。", existing, name_score))
        elif same_field and summary_score >= 0.5:
            issues.append(_issue("related", "同类型设定里已有相近内容。", existing, summary_score))
    return _top_issues(issues)


def analyze_prompt_option_candidate(candidate: dict, existing_options: list[dict]) -> list[dict]:
    content = str(candidate.get("content") or "")
    name = str(candidate.get("name") or "")
    capability = str(candidate.get("capability") or "")
    issues: list[dict] = []
    for existing in existing_options:
        if not isinstance(existing, dict):
            continue
        content_score = text_similarity(content, existing.get("content", ""))
        name_score = text_similarity(name, existing.get("name", ""))
        same_capability = capability == str(existing.get("capability") or "")
        layer = str(existing.get("scope") or "")
        if str(candidate.get("id") or "") and str(candidate.get("id") or "") == str(existing.get("id") or ""):
            issues.append(_issue("duplicate", "ID 已存在，保存会在同层或当前故事层覆盖同 ID 选项。", existing, 1.0, layer))
        elif content_score >= 0.96:
            issues.append(_issue("duplicate", "Prompt 内容几乎相同。", existing, content_score, layer))
        elif name_score >= 0.96:
            issues.append(_issue("warning", "名称相同或极其相近。", existing, name_score, layer))
        elif same_capability and content_score >= 0.5:
            issues.append(_issue("related", "同能力下已有相近 Prompt。", existing, content_score, layer))
    return _top_issues(issues)


def analyze_rule_candidate(candidate: dict, rule_layers: list[tuple[str, dict]]) -> list[dict]:
    content = str(candidate.get("content") or "")
    scope = str(candidate.get("scope") or "all")
    candidate_lines = [line.strip().lstrip("-* ").strip() for line in content.splitlines() if line.strip()]
    issues: list[dict] = []
    for layer, rules in rule_layers:
        if not isinstance(rules, dict):
            continue
        for rule_scope in ["all", scope]:
            for existing_text in rules.get(rule_scope, []) or []:
                existing = {"id": f"{layer}:{rule_scope}:{existing_text}", "name": existing_text, "summary": existing_text, "scope": rule_scope}
                best_score = max([text_similarity(line, existing_text) for line in candidate_lines] or [0.0])
                if best_score >= 0.96:
                    issues.append(_issue("duplicate", "已有几乎相同的规则。", existing, best_score, layer))
                elif best_score >= 0.55:
                    issues.append(_issue("related", "已有相近规则，确认前可检查是否重复或冲突。", existing, best_score, layer))
    return _top_issues(issues)
