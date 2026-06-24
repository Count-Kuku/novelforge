"""Streaming preview helpers for Streamlit generation actions."""
from __future__ import annotations

import logging
import uuid

import streamlit as st


LOGGER = logging.getLogger("novelforge.ui.streaming")


class GenerationCancelled(RuntimeError):
    cancel_generation = True


def render_stream_preview(preview_slot, text: str, preview_language: str | None = None):
    preview_text = text or "等待模型开始输出..."
    if preview_language:
        preview_slot.code(preview_text, language=preview_language)
    else:
        preview_slot.markdown(preview_text)


def safe_stream_emit(stream_callback, text: str):
    if not stream_callback:
        return
    try:
        stream_callback(text)
    except Exception as exc:
        if getattr(exc, "cancel_generation", False):
            raise
        LOGGER.warning("Stream callback failed while emitting marker: %s", exc, exc_info=True)


def make_stream_preview(label: str, preview_language: str | None = None):
    cancel_key = f"stream_cancel:{uuid.uuid4().hex}"
    st.session_state[cancel_key] = False
    status = st.status(label, expanded=True)
    with status:
        control_col, _ = st.columns([1, 3])
        control_col.button(
            "停止生成",
            key=f"{cancel_key}:button",
            on_click=lambda: st.session_state.__setitem__(cancel_key, True),
            use_container_width=True,
        )
        preview_slot = st.empty()
        render_stream_preview(preview_slot, "", preview_language)
    state = {"text": ""}

    def stream_callback(delta: str):
        if st.session_state.get(cancel_key):
            raise GenerationCancelled("用户已停止本次生成。")
        if not delta:
            return
        state["text"] += str(delta)
        cursor = "\n\n▌" if preview_language else "▌"
        render_stream_preview(preview_slot, f"{state['text']}{cursor}", preview_language)

    def complete(message: str = "生成完成。"):
        render_stream_preview(preview_slot, state["text"], preview_language)
        status.update(label=message, state="complete", expanded=False)

    def cancel(message: str = "已停止生成。"):
        render_stream_preview(preview_slot, state["text"], preview_language)
        status.update(label=message, state="complete", expanded=True)

    def fail(message: str):
        render_stream_preview(preview_slot, state["text"], preview_language)
        status.update(label=message, state="error", expanded=True)

    return stream_callback, complete, cancel, fail


def run_with_stream(label: str, func, *args, preview_language: str | None = None, **kwargs):
    stream_callback, complete, cancel, fail = make_stream_preview(label, preview_language=preview_language)
    try:
        result = func(*args, stream_callback=stream_callback, **kwargs)
        complete()
        return result
    except GenerationCancelled:
        cancel()
        st.stop()
    except Exception as exc:
        fail(f"{label}失败：{exc}")
        raise
