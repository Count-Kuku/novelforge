"""Shared Streamlit widget helpers."""
from __future__ import annotations

import hashlib
import html
import os

import streamlit as st

from novelforge.domain.creative_profile_workflows import CUSTOM_OPTION_LABEL


def developer_mode_enabled() -> bool:
    """Developer-only surfaces are opt-in and never exposed by default."""

    value = str(os.environ.get("NOVELFORGE_DEVELOPER_MODE") or "").strip().lower()
    return value in {"1", "true", "yes", "on", "enabled"}

def create_batch_progress_callback(title: str):
    progress_bar = st.progress(0)
    status_slot = st.empty()

    def update(event: dict):
        if not isinstance(event, dict):
            return
        total = max(int(event.get("total") or 1), 1)
        current = max(0, min(int(event.get("current") or 0), total))
        percent = int((current / total) * 100)
        message = str(event.get("message") or "正在处理").strip()
        progress_bar.progress(percent)
        status_slot.caption(f"{title}：{message}（{current}/{total}）")

    return update

def navigate_to_target(
    page: str,
    *,
    view: str | None = None,
    subview: str | None = None,
    payload: dict | None = None,
):
    """请求一次性导航；旧页面名由导航契约转换到新的 Hub 视图。"""

    # 延迟导入，避免 navigation 读取 UI helper 时形成模块循环。
    from ui.navigation import build_navigation_intent

    intent = build_navigation_intent(
        page,
        view=view,
        subview=subview,
        payload=payload,
        developer_mode=developer_mode_enabled(),
    )
    st.session_state["pending_navigation_intent"] = intent
    st.rerun()


def navigate_to(page: str):
    navigate_to_target(page)


def render_hub_navigation(
    label: str,
    options: list[str] | tuple[str, ...],
    *,
    key: str,
    default: str,
    caption: str = "",
):
    """渲染统一的 Hub 内导航条，避免各页面重复实现状态初始化和视觉容器。"""

    normalized_options = list(options)
    if not normalized_options:
        return None
    if key in st.session_state and st.session_state.get(key) not in normalized_options:
        st.session_state[key] = default if default in normalized_options else normalized_options[0]
    normalized_default = default if default in normalized_options else normalized_options[0]
    with st.container(border=True):
        if caption:
            st.caption(caption)
        return st.segmented_control(
            label,
            options=normalized_options,
            default=normalized_default if key not in st.session_state else None,
            key=key,
            width="stretch",
            label_visibility="collapsed",
        )


def stable_widget_suffix(value: str) -> str:
    return hashlib.md5(str(value).encode("utf-8")).hexdigest()[:10]

def scoped_widget_key(base: str, *parts) -> str:
    scope = ":".join(str(part) for part in parts if part is not None)
    return f"{base}_{stable_widget_suffix(scope)}"

def scoped_session_key(base: str, *parts) -> str:
    scope = ":".join(str(part) for part in parts if part is not None)
    return f"{base}:{stable_widget_suffix(scope)}"

def confirmed_button(
    container,
    label: str,
    confirm_label: str,
    key: str,
    *,
    width: str = "stretch",
    type: str = "secondary",
    help_text: str | None = None,
) -> bool:
    confirm_key = f"{key}_confirm"
    confirmed = container.checkbox(confirm_label, key=confirm_key)

    def consume_confirmation() -> None:
        # Button callbacks run before the next script pass, so the destructive
        # action is authorized exactly once and cannot carry over to a newly
        # selected target after st.rerun().
        st.session_state[confirm_key] = False

    return container.button(
        label,
        key=key,
        disabled=not confirmed,
        width=width,
        type=type,
        help=help_text,
        on_click=consume_confirmation,
    )

def render_quick_action(
    label: str,
    page: str,
    help_text: str,
    *,
    view: str | None = None,
    subview: str | None = None,
):
    with st.container(border=True):
        st.markdown(
            f"""
            <div class="nf-action-card-body">
                <div class="nf-action-title">{html.escape(str(label))}</div>
                <div class="nf-action-copy">{html.escape(str(help_text))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(
            f"打开：{label}",
            key=f"quick_action_{stable_widget_suffix(f'{page}:{view}:{subview}')}",
            width="stretch",
        ):
            navigate_to_target(page, view=view, subview=subview)


def render_next_step_action(
    label: str,
    page: str,
    *,
    view: str | None = None,
    subview: str | None = None,
    help_text: str = "",
    key_suffix: str = "",
):
    """渲染创作流程唯一的推荐下一步，统一通过导航意图切换。"""

    with st.container(border=True):
        st.markdown("**推荐下一步**")
        if help_text:
            st.caption(help_text)
        if st.button(
            label,
            key=f"next_step_{stable_widget_suffix(f'{page}:{view}:{subview}:{key_suffix}')}",
            type="primary",
            width="stretch",
        ):
            navigate_to_target(page, view=view, subview=subview)

def _safe_int_metric_value(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

def select_with_custom(container, label: str, options: list[str], current_value: str, key: str, help_text: str = "") -> str:
    cleaned_value = str(current_value or "").strip()
    selection_options = list(options)
    if CUSTOM_OPTION_LABEL not in selection_options:
        selection_options.append(CUSTOM_OPTION_LABEL)
    default_index = selection_options.index(cleaned_value) if cleaned_value in selection_options else selection_options.index(CUSTOM_OPTION_LABEL)
    selected = container.selectbox(
        label,
        options=selection_options,
        index=default_index,
        key=f"{key}_select",
        help=help_text or None,
    )
    if selected != CUSTOM_OPTION_LABEL:
        return selected
    custom_value = container.text_input(
        f"自定义{label}",
        value=cleaned_value if cleaned_value not in options else "",
        key=f"{key}_custom",
        placeholder=f"输入自己的{label}",
    )
    return custom_value.strip() or cleaned_value or options[0]
