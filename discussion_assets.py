import hashlib
from datetime import datetime, timezone
from typing import Any

from prompt_options import build_discussion_prompt_option_candidates


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _discussion_payload(discussion_step: dict) -> dict:
    if not isinstance(discussion_step, dict):
        return {}
    if isinstance(discussion_step.get("discussion"), dict):
        return discussion_step["discussion"]
    if any(key in discussion_step for key in {
        "current_understanding",
        "core_goals",
        "key_constraints",
        "recommended_direction",
        "recommended_profile",
        "options",
        "risks",
    }):
        return discussion_step
    data = discussion_step.get("data", {})
    if not isinstance(data, dict):
        return {}
    discussion = data.get("discussion", {})
    return discussion if isinstance(discussion, dict) else {}


def _string_list(values: Any) -> list[str]:
    if not values:
        return []
    if not isinstance(values, list):
        values = [values]
    rows = []
    for value in values:
        text = str(value or "").strip()
        if text:
            rows.append(text)
    return rows


def _short_name(text: str, fallback: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return fallback
    for separator in ["：", ":", "，", ",", "。", ".", "；", ";"]:
        if separator in cleaned:
            head = cleaned.split(separator, 1)[0].strip()
            if head:
                cleaned = head
                break
    return cleaned[:36].rstrip() or fallback


def _stable_id(prefix: str, *parts: str) -> str:
    raw = "|".join(str(part or "") for part in parts)
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _discussion_title(discussion: dict, discussion_kind: str) -> str:
    return str(discussion.get("title") or {
        "outline": "全书讨论",
        "chapter": "章节讨论",
        "volume": "分卷讨论",
        "arc": "剧情段讨论",
        "creative_profile": "创作配置讨论",
    }.get(discussion_kind, "讨论")).strip()


def _source_title(discussion: dict, discussion_kind: str) -> str:
    return f"讨论提炼：{_discussion_title(discussion, discussion_kind)}"


def _setting_candidate(
    *,
    discussion: dict,
    discussion_kind: str,
    story_id: str,
    source_ref: str,
    label: str,
    category: str,
    field_name: str,
    summary: str,
    importance: float,
) -> dict:
    title = _discussion_title(discussion, discussion_kind)
    item_id = _stable_id(
        "discussion_setting",
        discussion_kind,
        story_id,
        source_ref,
        label,
        category,
        field_name,
        summary,
    )
    now = _now()
    return {
        "id": item_id,
        "category": category,
        "name": _short_name(summary, f"{label}：{title}"),
        "summary": summary,
        "details": {
            "原始设定": summary,
            "来源字段": field_name,
            "讨论类型": discussion_kind,
            "讨论标题": title,
            "讨论来源": source_ref,
        },
        "evidence": [{
            "source_title": _source_title(discussion, discussion_kind),
            "quote": summary[:160],
            "note": "由用户讨论结论提炼，用户确认后作为核心设定生效。",
        }],
        "confidence": 0.85,
        "importance": importance,
        "evidence_strength": 0.75,
        "canon_status": "user_override",
        "extraction_mode": "discussion",
        "tags": ["核心设定", "讨论提炼", discussion_kind, label],
        "scope": "project",
        "authority": "project",
        "source_title": _source_title(discussion, discussion_kind),
        "source_origin": "discussion_extraction",
        "status": "confirmed",
        "setting_role": "core",
        "setting_scope": "story",
        "setting_field": field_name,
        "story_id": story_id,
        "injection_policy": "always",
        "version_scope": "project_main",
        "worldline_id": "main",
        "worldline_label": "本项目主线",
        "created_at": now,
        "updated_at": now,
    }


def build_discussion_setting_candidates(
    discussion_step: dict,
    discussion_kind: str,
    *,
    story_id: str,
    source_ref: str = "",
) -> list[dict]:
    discussion = _discussion_payload(discussion_step)
    if not discussion:
        return []

    kind = str(discussion_kind or "discussion").strip() or "discussion"
    candidates: list[dict] = []
    current_understanding = str(discussion.get("current_understanding") or "").strip()
    if current_understanding:
        candidates.append(_setting_candidate(
            discussion=discussion,
            discussion_kind=kind,
            story_id=story_id,
            source_ref=source_ref,
            label="讨论理解",
            category="world_rules",
            field_name="world",
            summary=current_understanding,
            importance=0.72,
        ))

    for label, key in [
        ("核心目标", "core_goals"),
        ("章节目标", "chapter_goal"),
        ("分卷目标", "volume_goal"),
        ("剧情段目标", "arc_goal"),
        ("推荐方向", "recommended_direction"),
    ]:
        raw_values = _string_list(discussion.get(key))
        if isinstance(discussion.get(key), str) and discussion.get(key):
            raw_values = [str(discussion.get(key)).strip()]
        for value in raw_values[:6]:
            candidates.append(_setting_candidate(
                discussion=discussion,
                discussion_kind=kind,
                story_id=story_id,
                source_ref=source_ref,
                label=label,
                category="constraints",
                field_name="active_constraints",
                summary=value,
                importance=0.85,
            ))

    for value in _string_list(discussion.get("key_constraints"))[:8]:
        candidates.append(_setting_candidate(
            discussion=discussion,
            discussion_kind=kind,
            story_id=story_id,
            source_ref=source_ref,
            label="关键约束",
            category="constraints",
            field_name="active_constraints",
            summary=value,
            importance=0.9,
        ))

    deduped: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        key = (
            str(candidate.get("category") or ""),
            str(candidate.get("setting_field") or ""),
            str(candidate.get("summary") or "").casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _capability_for_discussion(kind: str) -> str:
    return {
        "outline": "outline",
        "volume": "outline",
        "arc": "outline",
        "chapter": "chapter_outline",
        "creative_profile": "all",
    }.get(kind, "all")


def build_discussion_rule_candidates(
    discussion_step: dict,
    discussion_kind: str,
    *,
    source_ref: str = "",
) -> list[dict]:
    discussion = _discussion_payload(discussion_step)
    if not discussion:
        return []
    kind = str(discussion_kind or "discussion").strip() or "discussion"
    title = _discussion_title(discussion, kind)
    candidates: list[dict] = []
    constraints = _string_list(discussion.get("key_constraints"))
    recommended = str(discussion.get("recommended_direction") or "").strip()
    goals = []
    for key in ["core_goals", "chapter_goal", "volume_goal", "arc_goal"]:
        value = discussion.get(key)
        goals.extend(_string_list(value))
    goals = list(dict.fromkeys(goals))
    planning_lines = []
    planning_lines.extend(f"必须遵守讨论约束：{item}" for item in constraints[:8])
    planning_lines.extend(f"优先落实讨论目标：{item}" for item in goals[:6])
    if recommended:
        planning_lines.append(f"优先采用讨论推荐方向：{recommended}")
    if planning_lines:
        content = "\n".join(f"- {line}" for line in planning_lines)
        candidates.append({
            "id": _stable_id("discussion_rule", kind, source_ref, "planning", content),
            "title": f"{title}：规划规则",
            "scope": _capability_for_discussion(kind),
            "target": "story",
            "content": content,
            "source_kind": kind,
            "source_ref": source_ref,
        })

    risks = _string_list(discussion.get("risks"))
    if risks:
        content = "\n".join(f"- 审阅时检查讨论风险：{item}" for item in risks[:8])
        candidates.append({
            "id": _stable_id("discussion_rule", kind, source_ref, "review", content),
            "title": f"{title}：审阅规则",
            "scope": "review",
            "target": "story",
            "content": content,
            "source_kind": kind,
            "source_ref": source_ref,
        })
    return candidates


def build_discussion_asset_candidates(
    discussion_step: dict,
    discussion_kind: str,
    *,
    story_id: str,
    source_ref: str = "",
) -> dict[str, list[dict]]:
    return {
        "settings": build_discussion_setting_candidates(
            discussion_step,
            discussion_kind,
            story_id=story_id,
            source_ref=source_ref,
        ),
        "prompt_options": build_discussion_prompt_option_candidates(
            discussion_step,
            discussion_kind,
            source_ref=source_ref,
        ),
        "rules": build_discussion_rule_candidates(
            discussion_step,
            discussion_kind,
            source_ref=source_ref,
        ),
    }
