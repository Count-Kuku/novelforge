"""LLM profile configuration page."""
from __future__ import annotations

import html
import json
from urllib.parse import urlparse

import streamlit as st

from llm import PROVIDER_PRESETS, test_llm_connection
from memory import (
    delete_llm_profile,
    get_active_llm_profile,
    load_llm_profiles,
    load_llm_settings,
    set_active_llm_profile,
    upsert_llm_profile,
)
from ui.common import confirmed_button, scoped_widget_key


def _load_llm_profile_state() -> tuple[list[dict], dict, dict, list[str], dict[str, str]]:
    profiles_payload = load_llm_profiles()
    profiles = profiles_payload.get("profiles", [])
    active_profile = get_active_llm_profile()
    settings = load_llm_settings()
    profile_options = [profile.get("id", "") for profile in profiles]
    profile_option_labels = {
        profile.get("id", ""): f"{profile.get('name', profile.get('id', ''))} {'（当前）' if profile.get('id') == active_profile.get('id') else ''}"
        for profile in profiles
    }
    return profiles, active_profile, settings, profile_options, profile_option_labels


def _render_llm_profile_selector(
    profiles: list[dict],
    active_profile: dict,
    profile_options: list[str],
    profile_option_labels: dict[str, str],
) -> tuple[str, dict]:
    if not profile_options:
        st.info("还没有模型配置方案，请先在下方新增一套。")
        return "", active_profile
    selected_profile_id = st.selectbox(
        "选择配置方案",
        options=profile_options,
        index=profile_options.index(active_profile.get("id", "")) if active_profile.get("id", "") in profile_options else 0,
        format_func=lambda pid: profile_option_labels.get(pid, pid),
        key="llm_profile_selector",
    )
    selected_profile = next((profile for profile in profiles if profile.get("id") == selected_profile_id), active_profile)
    return selected_profile_id, selected_profile


def _render_llm_profile_actions(selected_profile_id: str, selected_profile: dict) -> None:
    if not selected_profile_id:
        st.caption("暂无可操作的配置方案。")
        return

    action_col1, action_col2 = st.columns(2)
    if action_col1.button(
        "切换生效",
        key=scoped_widget_key("switch_llm_profile", selected_profile_id),
        use_container_width=True,
    ):
        try:
            set_active_llm_profile(selected_profile_id)
            st.success("已切换当前模型配置方案。")
            st.rerun()
        except Exception as exc:
            st.error(f"切换失败：{exc}")
    if action_col2.button(
        "测试连接",
        key=scoped_widget_key("test_llm_connection", selected_profile_id),
        use_container_width=True,
    ):
        if not selected_profile.get("api_key"):
            st.error("当前方案没有填写接口密钥，无法测试。")
        else:
            with st.spinner("正在测试连接..."):
                try:
                    message = test_llm_connection(
                        str(selected_profile.get("base_url", "") or ""),
                        str(selected_profile.get("api_key", "") or ""),
                        str(selected_profile.get("model_name", "") or ""),
                    )
                    st.success(message)
                except Exception as exc:
                    st.error(str(exc))
    with st.expander("删除当前配置方案", expanded=False):
        if confirmed_button(
            st,
            "删除当前方案",
            "我确认不再需要这个配置方案",
            scoped_widget_key("delete_llm_profile", selected_profile_id),
            help_text="删除后无法在界面中恢复，请先确认该方案不再需要。",
        ):
            try:
                delete_llm_profile(selected_profile_id)
                st.success("配置方案已删除。")
                st.rerun()
            except Exception as exc:
                st.error(f"删除失败：{exc}")


def _render_llm_profile_management(profiles: list[dict], active_profile: dict) -> dict:
    st.markdown("### 配置方案管理")
    profile_options = [profile.get("id", "") for profile in profiles]
    profile_option_labels = {
        profile.get("id", ""): f"{profile.get('name', profile.get('id', ''))} {'（当前）' if profile.get('id') == active_profile.get('id') else ''}"
        for profile in profiles
    }
    selected_profile_id, selected_profile = _render_llm_profile_selector(
        profiles, active_profile, profile_options, profile_option_labels
    )
    _render_llm_profile_actions(selected_profile_id, selected_profile)
    return selected_profile


def _profile_widget_key(base: str, profile_id: str) -> str:
    return scoped_widget_key(base, profile_id or "__new__")


def _render_provider_quick_fill(profile_id: str) -> None:
    st.markdown("### 快速填充")
    st.caption("点击下方服务商按钮，自动填写常见服务地址和模型名，然后按需微调。")
    provider_keys = [name for name in PROVIDER_PRESETS if name != "自定义"]
    provider_labels = {
        "阿里云通义千问 (Qwen)": "阿里云 Qwen",
        "硅基流动 (SiliconFlow)": "硅基流动",
    }
    fill_cols = st.columns(len(provider_keys))
    for idx, provider_name in enumerate(provider_keys):
        provider = PROVIDER_PRESETS[provider_name]
        with fill_cols[idx]:
            st.button(
                provider_labels.get(provider_name, provider_name),
                key=_profile_widget_key(f"fill_provider_{idx}", profile_id),
                use_container_width=True,
                help=f"{provider['base_url']} / {provider['model_name']}",
                on_click=lambda p=provider, pid=profile_id: (
                    st.session_state.update({
                        _profile_widget_key("llm_base_url", pid): p["base_url"],
                        _profile_widget_key("llm_model_name", pid): p["model_name"],
                        _profile_widget_key("llm_embedding_model_name", pid): p["embedding_model_name"],
                    })
                ) or None,
            )


def _clean_llm_profile_form_values(
    profile_id_value: str,
    profile_name: str,
    base_url: str,
    api_key: str,
    model_name: str,
    embedding_model_name: str,
) -> dict[str, str]:
    return {
        "id": profile_id_value.strip(),
        "name": profile_name.strip(),
        "base_url": base_url.strip(),
        "api_key": api_key.strip(),
        "model_name": model_name.strip(),
        "embedding_model_name": embedding_model_name.strip(),
    }


def _validate_llm_profile_payload(payload: dict[str, str], *, require_api_key: bool, auto_activate: bool) -> bool:
    if not payload["id"]:
        st.error("方案标识不能为空。")
        return False
    if not payload["name"]:
        st.error("方案名称不能为空。")
        return False
    if not payload["base_url"]:
        st.error("模型服务网址不能为空。")
        return False
    if require_api_key and not payload["api_key"]:
        st.error("接口密钥不能为空。")
        return False
    if auto_activate and not payload["api_key"]:
        st.error("接口密钥为空时不能立即启用这个方案。可以取消“保存后立即启用”，或先填写密钥。")
        return False
    parsed_url = urlparse(payload["base_url"])
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        st.error("模型服务网址格式无效，需要以 http:// 或 https:// 开头，并包含完整域名。")
        return False
    return True


def _save_llm_profile(payload: dict[str, str], *, auto_activate: bool) -> None:
    saved_profile = upsert_llm_profile(payload)
    if auto_activate:
        set_active_llm_profile(saved_profile.get("id", ""))


def _handle_test_and_save_profile(payload: dict[str, str], *, auto_activate: bool) -> None:
    if not _validate_llm_profile_payload(payload, require_api_key=True, auto_activate=auto_activate):
        return
    try:
        with st.spinner("正在测试连接..."):
            test_llm_connection(payload["base_url"], payload["api_key"], payload["model_name"])
        _save_llm_profile(payload, auto_activate=auto_activate)
        st.success("连接成功，模型配置方案已保存。")
        st.rerun()
    except Exception as exc:
        st.error(str(exc))


def _handle_direct_save_profile(payload: dict[str, str], *, auto_activate: bool) -> None:
    if not _validate_llm_profile_payload(payload, require_api_key=False, auto_activate=auto_activate):
        return
    if not payload["api_key"]:
        st.warning("接口密钥为空，后续使用该方案时可能连接失败。")
    try:
        _save_llm_profile(payload, auto_activate=auto_activate)
        st.success("模型配置方案已保存。")
        st.rerun()
    except Exception as exc:
        st.error(f"保存失败：{exc}")


def _render_llm_profile_form(selected_profile: dict, active_profile: dict) -> None:
    selected_profile_id = str(selected_profile.get("id") or "")
    with st.form(_profile_widget_key("llm_profile_form", selected_profile_id)):
        st.markdown("### 编辑或新增配置方案")
        col_a, col_b = st.columns(2)
        profile_id_value = col_a.text_input(
            "方案标识",
            value=selected_profile.get("id", ""),
            key=_profile_widget_key("llm_profile_id", selected_profile_id),
            help="用于内部识别这套配置。建议使用英文、数字、短横线，例如 deepseek-main。",
        )
        profile_name = col_b.text_input(
            "方案名称",
            value=selected_profile.get("name", ""),
            placeholder="例如：DeepSeek 主账号",
            key=_profile_widget_key("llm_profile_name", selected_profile_id),
        )
        base_url = st.text_input(
            "模型服务网址",
            value=selected_profile.get("base_url", ""),
            placeholder="https://api.deepseek.com",
            key=_profile_widget_key("llm_base_url", selected_profile_id),
            help="选择一个服务商快速填充常见的服务地址和模型名。",
        )
        col_ak, col_mn = st.columns(2)
        api_key = col_ak.text_input(
            "接口密钥",
            value=selected_profile.get("api_key", ""),
            type="password",
            key=_profile_widget_key("llm_api_key", selected_profile_id),
        )
        model_name = col_mn.text_input(
            "聊天模型名",
            value=selected_profile.get("model_name", ""),
            placeholder="deepseek-v4-flash",
            key=_profile_widget_key("llm_model_name", selected_profile_id),
        )
        embedding_model_name = st.text_input(
            "语义向量模型名",
            value=selected_profile.get("embedding_model_name", ""),
            placeholder="text-embedding-3-small",
            key=_profile_widget_key("llm_embedding_model_name", selected_profile_id),
        )
        auto_activate = st.checkbox(
            "保存后立即启用这个方案",
            value=selected_profile.get("id") == active_profile.get("id"),
            key=_profile_widget_key("llm_auto_activate", selected_profile_id),
        )

        test_col, save_col = st.columns([1, 1])
        payload = _clean_llm_profile_form_values(
            profile_id_value,
            profile_name,
            base_url,
            api_key,
            model_name,
            embedding_model_name,
        )
        if test_col.form_submit_button("测试并保存", use_container_width=True):
            _handle_test_and_save_profile(payload, auto_activate=auto_activate)

        if save_col.form_submit_button("直接保存", use_container_width=True):
            _handle_direct_save_profile(payload, auto_activate=auto_activate)


def _mask_api_key(raw_key: str) -> str:
    if not raw_key:
        return ""
    return f"***{raw_key[-4:]}"


def _render_saved_llm_profiles(profiles: list[dict], active_profile: dict) -> None:
    st.markdown("### 已保存方案")
    for profile in profiles:
        is_active = profile.get("id") == active_profile.get("id")
        label = profile.get("name", profile.get("id", ""))
        preview_key = _mask_api_key(str(profile.get("api_key", "") or ""))
        card_class = "nf-card active-profile-card" if is_active else "nf-card"
        st.markdown(
            f"""
            <div class="{card_class}">
                    <div class="nf-card-title">{html.escape(label)} { '<span style="color:var(--nf-accent-strong);font-size:0.85rem;">（当前生效）</span>' if is_active else ''}</div>
                <div class="nf-card-copy">
                    <b>标识：</b>{html.escape(profile.get("id", ""))}<br>
                    <b>服务地址：</b>{html.escape(profile.get("base_url", ""))}<br>
                    <b>聊天模型：</b>{html.escape(profile.get("model_name", ""))}<br>
                    <b>向量模型：</b>{html.escape(profile.get("embedding_model_name", ""))}<br>
                    <b>密钥：</b>{html.escape(preview_key) if preview_key else "未设置"}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_active_llm_settings(settings: dict) -> None:
    st.markdown("### 当前生效配置")
    masked_key = _mask_api_key(settings.get("api_key", ""))
    st.code(json.dumps({
        "方案标识": settings.get("profile_id", ""),
        "方案名称": settings.get("profile_name", ""),
        "模型服务网址": settings.get("base_url", ""),
        "接口密钥": masked_key,
        "聊天模型名": settings.get("model_name", ""),
        "语义向量模型名": settings.get("embedding_model_name", ""),
        "环境配置文件": settings.get("env_path", ""),
        "方案保存文件": settings.get("profiles_path", ""),
    }, ensure_ascii=False, indent=2), language="json")


def render_llm_settings_page():
    st.caption("可以保存多套模型服务方案并随时切换。当前启用的方案会同步到项目根目录 `.env`。")

    profiles, active_profile, settings, _, _ = _load_llm_profile_state()
    selected_profile = _render_llm_profile_management(profiles, active_profile)
    _render_provider_quick_fill(str(selected_profile.get("id") or ""))
    _render_llm_profile_form(selected_profile, active_profile)
    _render_saved_llm_profiles(profiles, active_profile)
    _render_active_llm_settings(settings)
