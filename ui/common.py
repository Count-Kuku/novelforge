"""Shared Streamlit widget helpers."""
from __future__ import annotations

import hashlib
import html

import streamlit as st

from creative_profile_workflows import CUSTOM_OPTION_LABEL

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

def navigate_to(page: str):
    st.session_state["pending_nav_page"] = page
    st.rerun()

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
    use_container_width: bool = True,
    type: str = "secondary",
    help_text: str | None = None,
) -> bool:
    confirmed = container.checkbox(confirm_label, key=f"{key}_confirm")
    return container.button(
        label,
        key=key,
        disabled=not confirmed,
        use_container_width=use_container_width,
        type=type,
        help=help_text,
    )

def render_quick_action(label: str, page: str, help_text: str):
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
        if st.button("进入", key=f"quick_action_{stable_widget_suffix(page)}", use_container_width=True):
            navigate_to(page)

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

