"""Fragment history, version selection, and current-fragment actions."""

from __future__ import annotations

import streamlit as st

from novelforge.workflows.interactive_writing import (
    accept_writing_fragment,
    active_fragment_chain,
    extract_fragment_knowledge,
    select_writing_fragment_variant,
)
from ui.common import scoped_widget_key
from ui.streaming import run_with_stream

from .shared import (
    FRAGMENT_STATUS_LABELS,
    action_mode_key,
    active_fragment,
    branch_frontier,
)


def render_fragment_history(
    project_name: str,
    story_id: str,
    bundle: dict,
) -> None:
    turns = {
        str(turn.get("turn_id") or ""): turn
        for turn in bundle.get("turns", [])
        if str(turn.get("turn_id") or "")
    }
    chain = active_fragment_chain(bundle)
    if not chain:
        st.caption("这条创作记录还没有生成内容，可以直接从下方开始。")
        return

    for fragment in chain:
        turn = turns.get(str(fragment.get("turn_id") or ""), {})
        with st.chat_message("user"):
            st.markdown(str(turn.get("user_message") or "继续创作"))
        with st.chat_message("assistant"):
            st.markdown(str(fragment.get("content") or ""))
            status = FRAGMENT_STATUS_LABELS.get(
                str(fragment.get("status") or ""),
                str(fragment.get("status") or ""),
            )
            st.caption(
                f"{status} · {fragment.get('word_count') or len(str(fragment.get('content') or ''))} 字符"
            )

    _render_alternate_versions(project_name, story_id, bundle, chain)


def _render_alternate_versions(
    project_name: str,
    story_id: str,
    bundle: dict,
    active_chain: list[dict],
) -> None:
    active_ids = {
        str(item.get("fragment_id") or "")
        for item in active_chain
    }
    alternatives = [
        fragment
        for fragment in bundle.get("fragments", [])
        if str(fragment.get("fragment_id") or "") not in active_ids
    ]
    if not alternatives:
        return

    with st.expander(f"其他版本（{len(alternatives)}）", expanded=False):
        current = active_fragment(bundle)
        archived = str(bundle.get("session", {}).get("status") or "") == "archived"
        for fragment in alternatives:
            status = FRAGMENT_STATUS_LABELS.get(
                str(fragment.get("status") or ""),
                str(fragment.get("status") or ""),
            )
            st.caption(status)
            st.markdown(str(fragment.get("content") or ""))
            can_select = (
                not archived
                and str(fragment.get("status") or "") == "proposed"
                and str(current.get("status") or "") == "proposed"
                and str(fragment.get("parent_fragment_id") or "")
                == str(current.get("parent_fragment_id") or "")
            )
            if st.button(
                "切换到这个版本",
                disabled=not can_select,
                key=scoped_widget_key(
                    "creative_select_variant",
                    project_name,
                    story_id,
                    fragment.get("fragment_id"),
                ),
            ):
                select_writing_fragment_variant(
                    project_name,
                    story_id,
                    str(bundle.get("session", {}).get("session_id") or ""),
                    str(fragment.get("fragment_id") or ""),
                )
                st.rerun()


def render_fragment_actions(
    project_name: str,
    story_id: str,
    bundle: dict,
) -> None:
    fragment = active_fragment(bundle)
    if not fragment:
        return
    session = dict(bundle.get("session", {}) or {})
    session_id = str(session.get("session_id") or "")
    fragment_id = str(fragment.get("fragment_id") or "")
    status = str(fragment.get("status") or "")
    archived = str(session.get("status") or "") == "archived"
    if archived:
        return

    frontier = branch_frontier(bundle)
    can_extract = status in {"accepted", "finalized"}
    if status == "proposed":
        keep_col, rewrite_col, more_col = st.columns([2, 2, 1])
        if keep_col.button(
            "保留这段",
            key=scoped_widget_key(
                "creative_accept_fragment",
                project_name,
                story_id,
                fragment_id,
            ),
            width="stretch",
            type="primary",
        ):
            with st.spinner("正在保留片段并整理可能的新设定..."):
                result = accept_writing_fragment(
                    project_name,
                    story_id,
                    session_id,
                    fragment_id,
                )
            for warning in result.get("warnings", []):
                st.warning(warning)
            st.rerun()
        if rewrite_col.button(
            "重写这段",
            key=scoped_widget_key(
                "creative_rewrite_fragment",
                project_name,
                story_id,
                fragment_id,
            ),
            width="stretch",
        ):
            st.session_state[action_mode_key(session_id)] = "rewrite"
            st.rerun()
        _render_more_actions(
            more_col,
            project_name,
            story_id,
            session_id,
            fragment_id,
            frontier,
            can_extract,
        )
        return

    if status in {"accepted", "finalized"}:
        info_col, more_col = st.columns([4, 1], vertical_alignment="center")
        info_col.caption(
            "当前内容已保留，可以直接在下方继续创作。"
            if status == "accepted"
            else "当前内容已经整理到章节，仍可从这里继续创作。"
        )
        _render_more_actions(
            more_col,
            project_name,
            story_id,
            session_id,
            fragment_id,
            frontier,
            can_extract,
        )


def _render_more_actions(
    host,
    project_name: str,
    story_id: str,
    session_id: str,
    fragment_id: str,
    frontier: dict,
    can_extract: bool,
) -> None:
    with host.popover("更多", width="stretch"):
        if frontier and st.button(
            "从这里写另一个版本",
            key=scoped_widget_key(
                "creative_branch_fragment",
                project_name,
                story_id,
                fragment_id,
            ),
            width="stretch",
        ):
            st.session_state[action_mode_key(session_id)] = "branch"
            st.rerun()
        if can_extract and st.button(
            "重新检查这段中的新设定",
            key=scoped_widget_key(
                "creative_extract_fragment",
                project_name,
                story_id,
                fragment_id,
            ),
            width="stretch",
        ):
            try:
                result = run_with_stream(
                    "正在整理片段中的新设定...",
                    extract_fragment_knowledge,
                    project_name,
                    story_id,
                    session_id,
                    fragment_id,
                    preview_language="json",
                )
                st.success(f"发现 {len(result.get('candidate_ids', []))} 条可审核的新设定。")
                st.rerun()
            except Exception as exc:
                st.error(f"新设定整理失败：{exc}")
