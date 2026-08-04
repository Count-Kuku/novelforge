"""Shared labels and state helpers for the free-writing UI."""

from __future__ import annotations

from ui.common import scoped_session_key, scoped_widget_key


ACTION_LABELS = {
    "generate": "生成片段",
    "continue": "继续写",
    "rewrite": "重新生成",
    "branch": "生成另一版本",
}

FRAGMENT_STATUS_LABELS = {
    "proposed": "当前版本",
    "accepted": "已保留",
    "superseded": "已被替换",
    "discarded": "未采用",
    "finalized": "已整理到章节",
}

SESSION_STATUS_LABELS = {
    "active": "创作中",
    "completed": "已完成",
    "archived": "已归档",
}


def active_session_key(project_name: str, story_id: str) -> str:
    return scoped_session_key("creative_active_session", project_name, story_id)


def pending_active_session_key(project_name: str, story_id: str) -> str:
    return scoped_session_key(
        "creative_pending_active_session",
        project_name,
        story_id,
    )


def last_result_key(project_name: str, story_id: str, session_id: str) -> str:
    return scoped_session_key(
        "creative_last_result",
        project_name,
        story_id,
        session_id,
    )


def action_mode_key(session_id: str) -> str:
    return scoped_widget_key("creative_action", session_id or "new")


def active_fragment(bundle: dict) -> dict:
    session = bundle.get("session", {}) or {}
    active_id = str(session.get("active_fragment_id") or "")
    for fragment in bundle.get("fragments", []):
        if str(fragment.get("fragment_id") or "") == active_id:
            return fragment
    return {}


def branch_frontier(bundle: dict) -> dict:
    """Return the accepted fragment that can anchor an alternate version."""
    fragment = active_fragment(bundle)
    if not fragment:
        return {}
    status = str(fragment.get("status") or "")
    if status in {"accepted", "finalized"}:
        return fragment
    if status != "proposed":
        return {}
    parent_id = str(fragment.get("parent_fragment_id") or "")
    for item in bundle.get("fragments", []):
        if (
            str(item.get("fragment_id") or "") == parent_id
            and str(item.get("status") or "") in {"accepted", "finalized"}
        ):
            return item
    return {}
