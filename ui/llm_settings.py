"""LLM profile configuration page."""
from __future__ import annotations

import html
import json
from urllib.parse import urlparse

import streamlit as st

from novelforge.core.llm import PROVIDER_PRESETS, test_llm_capabilities
from novelforge.services.capabilities import build_default_capability_registry
from novelforge.services.model_readiness import get_model_readiness
from novelforge.services.provider_adapters import (
    PROVIDER_PRESET_VERSION,
    discover_provider_models,
)
from novelforge.services.credentials import build_credential_ref, store_system_credential
from novelforge.services.memory import (
    delete_llm_profile,
    get_active_llm_profile,
    load_llm_profiles,
    load_llm_settings,
    set_active_llm_profile,
    upsert_llm_profile,
)
from ui.common import confirmed_button, developer_mode_enabled, scoped_widget_key
from ui.layout import render_stat_strip
from ui.llm_usage import render_usage_dashboard


PROVIDER_TYPE_OPTIONS = {
    "auto": "自动识别",
    "deepseek": "DeepSeek",
    "openrouter": "OpenRouter",
    "openai": "OpenAI",
    "qwen": "通义千问",
    "siliconflow": "硅基流动",
    "ollama": "本地 Ollama",
    "openai_compatible": "其它 OpenAI 兼容接口",
}
COST_TRACKING_MODE_OPTIONS = {
    "auto": "自动选择",
    "provider_reported": "使用供应商返回费用",
    "manual": "按 Token 价格估算",
    "tokens_only": "仅统计 Token",
}
PRICING_CURRENCY_OPTIONS = {"CNY": "人民币（CNY）", "USD": "美元（USD）"}
DISPLAY_CURRENCY_OPTIONS = {"CNY": "人民币为主", "USD": "美元为主"}
EMBEDDING_MODE_OPTIONS = {
    "disabled": "关闭语义向量（关键词检索）",
    "same_provider": "与聊天模型使用同一服务",
    "separate_provider": "使用独立向量服务",
    "local": "使用本地向量服务",
}


def _render_capability_result(result: dict) -> None:
    chat_message = str(result.get("chat_status_message") or "")
    if result.get("chat_status") == "ready":
        st.success(f"对话模型：{chat_message}")
    else:
        st.error(f"对话模型：{chat_message}")
    embedding_message = str(result.get("embedding_status_message") or "")
    if result.get("embedding_status") == "ready":
        st.success(f"资料语义检索：{embedding_message}")
    elif result.get("embedding_status") == "disabled":
        st.info(embedding_message)
    else:
        st.warning(f"资料语义检索：{embedding_message}")


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

    action_col1, action_col2, action_col3 = st.columns(3)
    if action_col1.button(
        "切换生效",
        key=scoped_widget_key("switch_llm_profile", selected_profile_id),
        width="stretch",
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
        width="stretch",
    ):
        if not selected_profile.get("api_key"):
            st.error("当前方案没有填写接口密钥，无法测试。")
        else:
            with st.spinner("正在测试连接..."):
                try:
                    result = test_llm_capabilities(
                        str(selected_profile.get("base_url", "") or ""),
                        str(selected_profile.get("api_key", "") or ""),
                        str(selected_profile.get("model_name", "") or ""),
                        embedding_mode=str(selected_profile.get("embedding_mode") or "disabled"),
                        embedding_model_name=str(selected_profile.get("embedding_model_name") or ""),
                        embedding_base_url=str(selected_profile.get("embedding_base_url") or ""),
                        embedding_api_key=str(selected_profile.get("embedding_api_key") or ""),
                        provider_type=str(selected_profile.get("provider_type") or "auto"),
                    )
                    upsert_llm_profile({**selected_profile, **result})
                    _render_capability_result(result)
                except Exception as exc:
                    st.error(str(exc))
    if action_col3.button(
        "发现模型",
        key=scoped_widget_key("discover_llm_models", selected_profile_id),
        width="stretch",
    ):
        try:
            with st.spinner("正在读取供应商模型列表..."):
                discovered = discover_provider_models(
                    base_url=str(selected_profile.get("base_url") or ""),
                    api_key=str(selected_profile.get("api_key") or ""),
                    provider_type=str(selected_profile.get("provider_type") or "auto"),
                )
            st.session_state[scoped_widget_key("discovered_models", selected_profile_id)] = discovered
        except Exception as exc:
            st.error(f"模型发现失败：{exc}")
    discovered = st.session_state.get(
        scoped_widget_key("discovered_models", selected_profile_id), {}
    )
    if discovered:
        models = list(discovered.get("models") or [])
        st.caption(
            f"预设版本 {discovered.get('preset_version', PROVIDER_PRESET_VERSION)} · "
            f"发现 {len(models)} 个模型"
        )
        st.code("\n".join(models[:100]) or "未返回模型", language=None)
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
                width="stretch",
                help=f"{provider['base_url']} / {provider['model_name']}",
                on_click=lambda p=provider, pid=profile_id: (
                    st.session_state.update({
                        _profile_widget_key("llm_base_url", pid): p["base_url"],
                        _profile_widget_key("llm_model_name", pid): p["model_name"],
                        _profile_widget_key("llm_embedding_mode", pid): p.get("embedding_mode", "disabled"),
                        _profile_widget_key("llm_embedding_model_name", pid): p["embedding_model_name"],
                        _profile_widget_key("llm_embedding_base_url", pid): p.get("embedding_base_url", ""),
                        _profile_widget_key("llm_provider_type", pid): p.get("provider_type", "auto"),
                        _profile_widget_key("llm_cost_tracking_mode", pid): p.get("cost_tracking_mode", "auto"),
                        _profile_widget_key("llm_pricing_currency", pid): p.get("pricing_currency", "USD"),
                        _profile_widget_key("llm_display_currency", pid): p.get("display_currency", "CNY"),
                        _profile_widget_key("llm_usd_to_cny_rate", pid): float(p.get("usd_to_cny_rate", 7.142857) or 7.142857),
                        _profile_widget_key("llm_input_price", pid): float(p.get("input_price_per_million", 0) or 0),
                        _profile_widget_key("llm_cached_input_price", pid): float(p.get("cached_input_price_per_million", 0) or 0),
                        _profile_widget_key("llm_cache_write_price", pid): float(p.get("cache_write_price_per_million", 0) or 0),
                        _profile_widget_key("llm_output_price", pid): float(p.get("output_price_per_million", 0) or 0),
                        _profile_widget_key("llm_embedding_price", pid): float(p.get("embedding_price_per_million", 0) or 0),
                        _profile_widget_key("llm_pricing_updated_at", pid): p.get("pricing_updated_at", ""),
                        _profile_widget_key("llm_pricing_source_url", pid): p.get("pricing_source_url", ""),
                        _profile_widget_key("llm_currency_rate_updated_at", pid): p.get("currency_rate_updated_at", ""),
                        _profile_widget_key("llm_currency_rate_source_url", pid): p.get("currency_rate_source_url", ""),
                    })
                ) or None,
            )


def _clean_llm_profile_form_values(
    profile_id_value: str,
    profile_name: str,
    base_url: str,
    api_key: str,
    model_name: str,
    embedding_mode: str,
    embedding_model_name: str,
    embedding_base_url: str,
    embedding_api_key: str,
    provider_type: str,
    cost_tracking_mode: str,
    pricing_currency: str,
    display_currency: str,
    usd_to_cny_rate: float,
    currency_rate_updated_at: str,
    currency_rate_source_url: str,
    input_price_per_million: float,
    cached_input_price_per_million: float,
    cache_write_price_per_million: float,
    output_price_per_million: float,
    embedding_price_per_million: float,
    pricing_updated_at: str,
    pricing_source_url: str,
    preflight_enabled: bool,
    preflight_warning_tokens: int,
    preflight_confirmation_tokens: int,
    preflight_warning_cost_usd: float,
    preflight_confirmation_cost_usd: float,
    preflight_warning_cost_cny: float,
    preflight_confirmation_cost_cny: float,
    preflight_require_confirmation: bool,
) -> dict:
    return {
        "id": profile_id_value.strip(),
        "name": profile_name.strip(),
        "base_url": base_url.strip(),
        "api_key": api_key.strip(),
        "model_name": model_name.strip(),
        "embedding_mode": embedding_mode.strip().lower() or "disabled",
        "embedding_model_name": embedding_model_name.strip(),
        "embedding_base_url": embedding_base_url.strip(),
        "embedding_api_key": embedding_api_key.strip(),
        "provider_type": provider_type.strip().lower() or "auto",
        "cost_tracking_mode": cost_tracking_mode.strip().lower() or "auto",
        "pricing_currency": pricing_currency.strip().upper() or "USD",
        "display_currency": display_currency.strip().upper() or "CNY",
        "usd_to_cny_rate": max(float(usd_to_cny_rate), 0.000001),
        "currency_rate_updated_at": currency_rate_updated_at.strip(),
        "currency_rate_source_url": currency_rate_source_url.strip(),
        "input_price_per_million": max(float(input_price_per_million), 0.0),
        "cached_input_price_per_million": max(float(cached_input_price_per_million), 0.0),
        "cache_write_price_per_million": max(float(cache_write_price_per_million), 0.0),
        "output_price_per_million": max(float(output_price_per_million), 0.0),
        "embedding_price_per_million": max(float(embedding_price_per_million), 0.0),
        "pricing_updated_at": pricing_updated_at.strip(),
        "pricing_source_url": pricing_source_url.strip(),
        "preflight_enabled": bool(preflight_enabled),
        "preflight_warning_tokens": max(int(preflight_warning_tokens), 0),
        "preflight_confirmation_tokens": max(int(preflight_confirmation_tokens), 0),
        "preflight_warning_cost_usd": max(float(preflight_warning_cost_usd), 0.0),
        "preflight_confirmation_cost_usd": max(
            float(preflight_confirmation_cost_usd), 0.0
        ),
        "preflight_warning_cost_cny": max(float(preflight_warning_cost_cny), 0.0),
        "preflight_confirmation_cost_cny": max(
            float(preflight_confirmation_cost_cny), 0.0
        ),
        "preflight_require_confirmation": bool(preflight_require_confirmation),
    }


def _validate_llm_profile_payload(payload: dict, *, require_api_key: bool, auto_activate: bool) -> bool:
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
    if payload.get("provider_type") not in PROVIDER_TYPE_OPTIONS:
        st.error("供应商类型无效，请重新选择。")
        return False
    embedding_mode = str(payload.get("embedding_mode") or "disabled")
    if embedding_mode not in EMBEDDING_MODE_OPTIONS:
        st.error("语义向量模式无效，请重新选择。")
        return False
    if embedding_mode != "disabled" and not payload.get("embedding_model_name"):
        st.error("启用语义向量时必须填写向量模型名。")
        return False
    embedding_base_url = str(payload.get("embedding_base_url") or "")
    if embedding_mode in {"separate_provider", "local"}:
        if not embedding_base_url:
            st.error("独立或本地向量服务必须填写服务网址。")
            return False
        parsed_embedding_url = urlparse(embedding_base_url)
        if parsed_embedding_url.scheme not in {"http", "https"} or not parsed_embedding_url.netloc:
            st.error("向量服务网址格式无效，需要以 http:// 或 https:// 开头。")
            return False
    if embedding_mode == "separate_provider" and not payload.get("embedding_api_key"):
        st.error("独立向量服务必须填写自己的 API Key。")
        return False
    if payload.get("cost_tracking_mode") not in COST_TRACKING_MODE_OPTIONS:
        st.error("费用统计模式无效，请重新选择。")
        return False
    if payload.get("pricing_currency") not in PRICING_CURRENCY_OPTIONS:
        st.error("价格币种无效，请重新选择。")
        return False
    if payload.get("display_currency") not in DISPLAY_CURRENCY_OPTIONS:
        st.error("主显示币种无效，请重新选择。")
        return False
    pricing_source_url = str(payload.get("pricing_source_url") or "")
    if pricing_source_url:
        parsed_source = urlparse(pricing_source_url)
        if parsed_source.scheme not in {"http", "https"} or not parsed_source.netloc:
            st.error("价格来源网址格式无效，需要以 http:// 或 https:// 开头。")
            return False
    currency_rate_source_url = str(payload.get("currency_rate_source_url") or "")
    if currency_rate_source_url:
        parsed_source = urlparse(currency_rate_source_url)
        if parsed_source.scheme not in {"http", "https"} or not parsed_source.netloc:
            st.error("币种换算来源网址格式无效，需要以 http:// 或 https:// 开头。")
            return False
    return True


def _save_llm_profile(payload: dict, *, auto_activate: bool) -> None:
    saved_profile = upsert_llm_profile(payload)
    if auto_activate:
        set_active_llm_profile(saved_profile.get("id", ""))


def _handle_test_and_save_profile(payload: dict, *, auto_activate: bool) -> None:
    if not _validate_llm_profile_payload(payload, require_api_key=True, auto_activate=auto_activate):
        return
    try:
        with st.spinner("正在分别测试对话模型和资料语义检索..."):
            result = test_llm_capabilities(
                payload["base_url"],
                payload["api_key"],
                payload["model_name"],
                embedding_mode=payload.get("embedding_mode", "disabled"),
                embedding_model_name=payload.get("embedding_model_name", ""),
                embedding_base_url=payload.get("embedding_base_url", ""),
                    embedding_api_key=payload.get("embedding_api_key", ""),
                    provider_type=payload.get("provider_type", "auto"),
            )
        _render_capability_result(result)
        if result.get("chat_status") != "ready":
            st.error("对话模型尚不可用，配置未保存。请检查密钥、服务地址和模型名。")
            return
        _save_llm_profile({**payload, **result}, auto_activate=auto_activate)
        if result.get("embedding_status") == "failed":
            st.warning("对话模型已保存；资料检索暂时明确降级为关键词模式。")
        else:
            st.success("能力测试完成，模型配置方案已保存。")
    except Exception as exc:
        st.error(str(exc))


def _handle_direct_save_profile(payload: dict, *, auto_activate: bool) -> None:
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
            value="",
            placeholder=(
                f"已安全保存 ···{selected_profile.get('api_key_last_four')}，留空保持不变"
                if selected_profile.get("api_key_ref") else "输入 API Key"
            ),
            type="password",
            key=_profile_widget_key("llm_api_key", selected_profile_id),
            help="密钥保存到系统凭据管理器；数据库和配置文件只记录引用、指纹与末四位。",
        )
        model_name = col_mn.text_input(
            "聊天模型名",
            value=selected_profile.get("model_name", ""),
            placeholder="deepseek-v4-flash",
            key=_profile_widget_key("llm_model_name", selected_profile_id),
        )
        selected_embedding_mode = str(selected_profile.get("embedding_mode") or "disabled")
        if selected_embedding_mode not in EMBEDDING_MODE_OPTIONS:
            selected_embedding_mode = "disabled"
        embedding_mode = st.selectbox(
            "资料语义检索",
            options=list(EMBEDDING_MODE_OPTIONS),
            index=list(EMBEDDING_MODE_OPTIONS).index(selected_embedding_mode),
            format_func=lambda value: EMBEDDING_MODE_OPTIONS.get(value, value),
            key=_profile_widget_key("llm_embedding_mode", selected_profile_id),
            help="关闭后仍可使用关键词检索；聊天模型与资料导入不会因此被阻塞。",
        )
        embedding_col_model, embedding_col_url = st.columns(2)
        embedding_model_name = embedding_col_model.text_input(
            "语义向量模型名",
            value=selected_profile.get("embedding_model_name", ""),
            placeholder="text-embedding-3-small",
            key=_profile_widget_key("llm_embedding_model_name", selected_profile_id),
            help="关闭语义向量时会忽略此字段。",
        )
        embedding_base_url = embedding_col_url.text_input(
            "独立/本地向量服务网址",
            value=selected_profile.get("embedding_base_url", ""),
            placeholder="http://localhost:11434/v1",
            key=_profile_widget_key("llm_embedding_base_url", selected_profile_id),
            help="只有独立或本地向量模式会使用此地址。",
        )
        embedding_api_key = st.text_input(
            "独立向量服务密钥",
            value="",
            placeholder=(
                f"已安全保存 ···{selected_profile.get('embedding_api_key_last_four')}，留空保持不变"
                if selected_profile.get("embedding_api_key_ref") else "独立服务需要时填写"
            ),
            type="password",
            key=_profile_widget_key("llm_embedding_api_key", selected_profile_id),
            help="只有使用独立向量服务时需要填写；不会拿聊天密钥去探测其它供应商。",
        )
        provider_col, tracking_col = st.columns(2)
        provider_values = list(PROVIDER_TYPE_OPTIONS)
        selected_provider_type = str(selected_profile.get("provider_type") or "auto")
        if selected_provider_type not in provider_values:
            selected_provider_type = "auto"
        provider_type = provider_col.selectbox(
            "供应商类型",
            options=provider_values,
            index=provider_values.index(selected_provider_type),
            format_func=lambda value: PROVIDER_TYPE_OPTIONS.get(value, value),
            key=_profile_widget_key("llm_provider_type", selected_profile_id),
            help="用于识别供应商特有的 usage 和费用字段；自动识别失败时可以手动指定。",
        )
        tracking_values = list(COST_TRACKING_MODE_OPTIONS)
        selected_tracking_mode = str(selected_profile.get("cost_tracking_mode") or "auto")
        if selected_tracking_mode not in tracking_values:
            selected_tracking_mode = "auto"
        cost_tracking_mode = tracking_col.selectbox(
            "费用统计模式",
            options=tracking_values,
            index=tracking_values.index(selected_tracking_mode),
            format_func=lambda value: COST_TRACKING_MODE_OPTIONS.get(value, value),
            key=_profile_widget_key("llm_cost_tracking_mode", selected_profile_id),
            help="自动模式优先采用 OpenRouter 等供应商直接返回的费用，否则按下方价格估算。",
        )
        with st.expander("Token 费用估算设置", expanded=False):
            currency_cols = st.columns(3)
            pricing_currency_values = list(PRICING_CURRENCY_OPTIONS)
            selected_pricing_currency = str(
                selected_profile.get("pricing_currency") or "USD"
            ).upper()
            if selected_pricing_currency not in pricing_currency_values:
                selected_pricing_currency = "USD"
            pricing_currency = currency_cols[0].selectbox(
                "价格币种",
                options=pricing_currency_values,
                index=pricing_currency_values.index(selected_pricing_currency),
                format_func=lambda value: PRICING_CURRENCY_OPTIONS[value],
                key=_profile_widget_key("llm_pricing_currency", selected_profile_id),
                help="下方每百万 Token 单价使用的币种。DeepSeek 官方中文价格可直接选择人民币。",
            )
            display_currency_values = list(DISPLAY_CURRENCY_OPTIONS)
            selected_display_currency = str(
                selected_profile.get("display_currency") or "CNY"
            ).upper()
            if selected_display_currency not in display_currency_values:
                selected_display_currency = "CNY"
            display_currency = currency_cols[1].selectbox(
                "主显示币种",
                options=display_currency_values,
                index=display_currency_values.index(selected_display_currency),
                format_func=lambda value: DISPLAY_CURRENCY_OPTIONS[value],
                key=_profile_widget_key("llm_display_currency", selected_profile_id),
            )
            usd_to_cny_rate = currency_cols[2].number_input(
                "美元兑人民币换算系数",
                min_value=0.000001,
                value=float(selected_profile.get("usd_to_cny_rate") or 7.142857),
                step=0.01,
                format="%.6f",
                key=_profile_widget_key("llm_usd_to_cny_rate", selected_profile_id),
                help="用于双币种显示和将人民币价格标准化到账本；可按服务商账单口径自行调整。",
            )
            currency_name = PRICING_CURRENCY_OPTIONS[pricing_currency]
            st.caption(
                f"下方价格单位为{currency_name} / 百万 Token。费用按调用发生时的价格与换算快照保存；"
                "缺少必要价格时只显示 Token，不会伪装成零费用。"
            )
            price_cols = st.columns(3)
            input_price_per_million = price_cols[0].number_input(
                f"输入价格 / 百万 Token（{pricing_currency}）",
                min_value=0.0,
                value=float(selected_profile.get("input_price_per_million") or 0.0),
                step=0.01,
                format="%.4f",
                key=_profile_widget_key("llm_input_price", selected_profile_id),
            )
            cached_input_price_per_million = price_cols[1].number_input(
                f"缓存输入价格 / 百万 Token（{pricing_currency}）",
                min_value=0.0,
                value=float(selected_profile.get("cached_input_price_per_million") or 0.0),
                step=0.001,
                format="%.6f",
                key=_profile_widget_key("llm_cached_input_price", selected_profile_id),
            )
            output_price_per_million = price_cols[2].number_input(
                f"输出价格 / 百万 Token（{pricing_currency}）",
                min_value=0.0,
                value=float(selected_profile.get("output_price_per_million") or 0.0),
                step=0.01,
                format="%.4f",
                key=_profile_widget_key("llm_output_price", selected_profile_id),
            )
            secondary_price_cols = st.columns(2)
            cache_write_price_per_million = secondary_price_cols[0].number_input(
                f"缓存写入价格 / 百万 Token（{pricing_currency}）",
                min_value=0.0,
                value=float(selected_profile.get("cache_write_price_per_million") or 0.0),
                step=0.001,
                format="%.6f",
                key=_profile_widget_key("llm_cache_write_price", selected_profile_id),
            )
            embedding_price_per_million = secondary_price_cols[1].number_input(
                f"Embedding 价格 / 百万 Token（{pricing_currency}）",
                min_value=0.0,
                value=float(selected_profile.get("embedding_price_per_million") or 0.0),
                step=0.01,
                format="%.4f",
                key=_profile_widget_key("llm_embedding_price", selected_profile_id),
            )
            price_meta_cols = st.columns(2)
            pricing_updated_at = price_meta_cols[0].text_input(
                "价格核对日期",
                value=str(selected_profile.get("pricing_updated_at") or ""),
                placeholder="2026-08-10",
                key=_profile_widget_key("llm_pricing_updated_at", selected_profile_id),
            )
            pricing_source_url = price_meta_cols[1].text_input(
                "价格来源网址",
                value=str(selected_profile.get("pricing_source_url") or ""),
                placeholder="https://...",
                key=_profile_widget_key("llm_pricing_source_url", selected_profile_id),
            )
            currency_meta_cols = st.columns(2)
            currency_rate_updated_at = currency_meta_cols[0].text_input(
                "换算系数核对日期",
                value=str(selected_profile.get("currency_rate_updated_at") or ""),
                placeholder="2026-08-10",
                key=_profile_widget_key(
                    "llm_currency_rate_updated_at", selected_profile_id
                ),
            )
            currency_rate_source_url = currency_meta_cols[1].text_input(
                "换算系数来源网址",
                value=str(selected_profile.get("currency_rate_source_url") or ""),
                placeholder="https://...",
                key=_profile_widget_key(
                    "llm_currency_rate_source_url", selected_profile_id
                ),
            )
            if provider_type == "deepseek":
                st.info(
                    "DeepSeek 快速填充采用官方中文页的人民币价格。默认换算系数用于对齐该预设的"
                    "官方中英文价目，不是实时外汇汇率；官方价格调整后请一并复核。"
                )
        with st.expander("执行前预算与提醒", expanded=False):
            preflight_enabled = st.checkbox(
                "在支持的操作前显示 Token 与费用预估",
                value=bool(selected_profile.get("preflight_enabled", True)),
                key=_profile_widget_key("llm_preflight_enabled", selected_profile_id),
            )
            st.caption("阈值使用预估区间的上界判断；设为 0 表示关闭对应阈值。")
            token_budget_cols = st.columns(2)
            preflight_warning_tokens = token_budget_cols[0].number_input(
                "Token 提醒阈值",
                min_value=0,
                value=int(selected_profile.get("preflight_warning_tokens") or 0),
                step=10000,
                key=_profile_widget_key("llm_preflight_warning_tokens", selected_profile_id),
            )
            preflight_confirmation_tokens = token_budget_cols[1].number_input(
                "Token 确认阈值",
                min_value=0,
                value=int(selected_profile.get("preflight_confirmation_tokens") or 0),
                step=10000,
                key=_profile_widget_key(
                    "llm_preflight_confirmation_tokens", selected_profile_id
                ),
            )
            preflight_warning_cost_usd = float(
                selected_profile.get("preflight_warning_cost_usd") or 0
            )
            preflight_confirmation_cost_usd = float(
                selected_profile.get("preflight_confirmation_cost_usd") or 0
            )
            preflight_warning_cost_cny = float(
                selected_profile.get("preflight_warning_cost_cny") or 0
            )
            preflight_confirmation_cost_cny = float(
                selected_profile.get("preflight_confirmation_cost_cny") or 0
            )
            cost_budget_cols = st.columns(2)
            budget_currency_name = "人民币" if display_currency == "CNY" else "美元"
            warning_cost_value = cost_budget_cols[0].number_input(
                f"费用提醒阈值（{budget_currency_name}）",
                min_value=0.0,
                value=(
                    preflight_warning_cost_cny
                    if display_currency == "CNY"
                    else preflight_warning_cost_usd
                ),
                step=0.01,
                format="%.4f",
                key=_profile_widget_key(
                    f"llm_preflight_warning_cost_{display_currency.lower()}",
                    selected_profile_id,
                ),
            )
            confirmation_cost_value = cost_budget_cols[1].number_input(
                f"费用确认阈值（{budget_currency_name}）",
                min_value=0.0,
                value=(
                    preflight_confirmation_cost_cny
                    if display_currency == "CNY"
                    else preflight_confirmation_cost_usd
                ),
                step=0.01,
                format="%.4f",
                key=_profile_widget_key(
                    f"llm_preflight_confirmation_cost_{display_currency.lower()}",
                    selected_profile_id,
                ),
            )
            if display_currency == "CNY":
                preflight_warning_cost_cny = warning_cost_value
                preflight_confirmation_cost_cny = confirmation_cost_value
            else:
                preflight_warning_cost_usd = warning_cost_value
                preflight_confirmation_cost_usd = confirmation_cost_value
            preflight_require_confirmation = st.checkbox(
                "超过确认阈值时必须勾选确认",
                value=bool(
                    selected_profile.get("preflight_require_confirmation", False)
                ),
                key=_profile_widget_key(
                    "llm_preflight_require_confirmation", selected_profile_id
                ),
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
            embedding_mode,
            embedding_model_name,
            embedding_base_url,
            embedding_api_key,
            provider_type,
            cost_tracking_mode,
            pricing_currency,
            display_currency,
            usd_to_cny_rate,
            currency_rate_updated_at,
            currency_rate_source_url,
            input_price_per_million,
            cached_input_price_per_million,
            cache_write_price_per_million,
            output_price_per_million,
            embedding_price_per_million,
            pricing_updated_at,
            pricing_source_url,
            preflight_enabled,
            preflight_warning_tokens,
            preflight_confirmation_tokens,
            preflight_warning_cost_usd,
            preflight_confirmation_cost_usd,
            preflight_warning_cost_cny,
            preflight_confirmation_cost_cny,
            preflight_require_confirmation,
        )
        if not payload["api_key"]:
            payload["api_key"] = str(selected_profile.get("api_key") or "")
        if not payload["embedding_api_key"]:
            payload["embedding_api_key"] = str(
                selected_profile.get("embedding_api_key") or ""
            )
        if test_col.form_submit_button("测试并保存", width="stretch"):
            _handle_test_and_save_profile(payload, auto_activate=auto_activate)

        if save_col.form_submit_button("直接保存", width="stretch"):
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
        preview_key = (
            f"***{profile.get('api_key_last_four')}"
            if profile.get("api_key_last_four")
            else _mask_api_key(str(profile.get("api_key", "") or ""))
        )
        card_class = "nf-card active-profile-card" if is_active else "nf-card"
        st.markdown(
            f"""
            <div class="{card_class}">
                    <div class="nf-card-title">{html.escape(label)} { '<span style="color:var(--nf-accent-strong);font-size:0.85rem;">（当前生效）</span>' if is_active else ''}</div>
                <div class="nf-card-copy">
                    <b>标识：</b>{html.escape(profile.get("id", ""))}<br>
                    <b>服务地址：</b>{html.escape(profile.get("base_url", ""))}<br>
                    <b>供应商：</b>{html.escape(PROVIDER_TYPE_OPTIONS.get(profile.get("provider_type", "auto"), profile.get("provider_type", "auto")))}<br>
                    <b>计费方式：</b>{html.escape(COST_TRACKING_MODE_OPTIONS.get(profile.get("cost_tracking_mode", "auto"), profile.get("cost_tracking_mode", "auto")))}<br>
                    <b>价格 / 主显示币种：</b>{html.escape(str(profile.get("pricing_currency") or "USD"))} / {html.escape(str(profile.get("display_currency") or "CNY"))}<br>
                    <b>聊天模型：</b>{html.escape(profile.get("model_name", ""))}<br>
                    <b>向量模型：</b>{html.escape(profile.get("embedding_model_name", ""))}<br>
                    <b>价格核对：</b>{html.escape(str(profile.get("pricing_updated_at") or "未标记"))}<br>
                    <b>密钥：</b>{html.escape(preview_key) if preview_key else "未设置"}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_active_llm_settings(settings: dict) -> None:
    st.markdown("### 当前生效方案")
    masked_key = (
        f"***{settings.get('api_key_last_four')}"
        if settings.get("api_key_last_four")
        else _mask_api_key(settings.get("api_key", ""))
    )
    readiness = get_model_readiness(settings)
    chat_label = {
        "ready": "可用",
        "unverified": "待验证",
        "missing": "未配置",
        "failed": "验证失败",
    }.get(readiness.get("chat_status"), str(readiness.get("chat_status") or "-"))
    retrieval_label = "语义 + 关键词" if readiness.get("retrieval_mode") == "hybrid" else "关键词模式"
    with st.container(border=True):
        st.markdown(f"**{settings.get('profile_name') or '未命名方案'}**")
        st.caption(
            f"{PROVIDER_TYPE_OPTIONS.get(settings.get('provider_type', 'auto'), settings.get('provider_type', 'auto'))} · "
            f"{settings.get('model_name') or '未设置对话模型'} · "
            f"密钥 {'已设置' if masked_key else '未设置'}"
        )
        render_stat_strip(
            [
                ("对话能力", chat_label, settings.get("model_name") or "未设置"),
                ("资料检索", retrieval_label, readiness.get("embedding_status") or "-"),
                ("主显示币种", settings.get("display_currency", "CNY"), "费用预估"),
                ("执行前预估", "开启" if settings.get("preflight_enabled", True) else "关闭", "Token 与费用"),
            ]
        )
        if readiness.get("chat_status") in {"missing", "failed"}:
            st.error(readiness.get("chat_message") or "聊天模型尚不可用。")
        elif readiness.get("chat_status") == "unverified":
            st.info("聊天配置尚未验证。建议点击“测试连接”，系统会分别检查对话和语义检索能力。")
        if readiness.get("retrieval_mode") == "lexical":
            st.caption(readiness.get("embedding_message") or "资料检索当前使用关键词模式。")
    if not developer_mode_enabled():
        return
    with st.expander("查看完整配置与文件路径", expanded=False):
        st.code(json.dumps({
        "方案标识": settings.get("profile_id", ""),
        "方案名称": settings.get("profile_name", ""),
        "模型服务网址": settings.get("base_url", ""),
        "接口密钥": masked_key,
        "聊天模型名": settings.get("model_name", ""),
        "语义向量模式": settings.get("embedding_mode", "disabled"),
        "语义向量模型名": settings.get("embedding_model_name", ""),
        "语义向量服务网址": settings.get("embedding_base_url", ""),
        "供应商类型": settings.get("provider_type", "auto"),
        "费用统计模式": settings.get("cost_tracking_mode", "auto"),
        "价格币种": settings.get("pricing_currency", "USD"),
        "主显示币种": settings.get("display_currency", "CNY"),
        "美元兑人民币换算系数": settings.get("usd_to_cny_rate", 7.142857),
        "输入价格/百万Token": settings.get("input_price_per_million", 0),
        "缓存输入价格/百万Token": settings.get("cached_input_price_per_million", 0),
        "缓存写入价格/百万Token": settings.get("cache_write_price_per_million", 0),
        "输出价格/百万Token": settings.get("output_price_per_million", 0),
        "Embedding价格/百万Token": settings.get("embedding_price_per_million", 0),
        "价格核对日期": settings.get("pricing_updated_at", ""),
        "执行前预估": settings.get("preflight_enabled", True),
        "Token提醒阈值": settings.get("preflight_warning_tokens", 0),
        "Token确认阈值": settings.get("preflight_confirmation_tokens", 0),
        "费用提醒阈值/人民币": settings.get("preflight_warning_cost_cny", 0),
        "费用确认阈值/人民币": settings.get("preflight_confirmation_cost_cny", 0),
        "费用提醒阈值/美元": settings.get("preflight_warning_cost_usd", 0),
        "费用确认阈值/美元": settings.get("preflight_confirmation_cost_usd", 0),
        "超阈值必须确认": settings.get("preflight_require_confirmation", False),
        "环境配置文件": settings.get("env_path", ""),
        "方案保存文件": settings.get("profiles_path", ""),
        }, ensure_ascii=False, indent=2), language="json")


def _render_capability_center() -> None:
    st.markdown("### 能力中心")
    st.caption(f"供应商预设版本：{PROVIDER_PRESET_VERSION}。各工作流只声明自身所需能力。")
    snapshot = build_default_capability_registry().snapshot()
    labels = {
        "chat": "对话生成",
        "embedding": "语义向量",
        "search": "网络搜索",
        "ocr": "本地 OCR",
    }
    for capability in ("chat", "embedding", "search", "ocr"):
        item = snapshot.get(capability, {})
        with st.container(border=True):
            st.markdown(
                f"**{labels[capability]}** · "
                f"{'可用' if item.get('available') else '不可用 / 可降级'}"
            )
            st.caption(str(item.get("message") or "暂无状态说明。"))
    with st.expander("配置网络搜索能力", expanded=not snapshot.get("search", {}).get("available")):
        brave_key = st.text_input(
            "Brave Search API Key",
            type="password",
            value="",
            placeholder="已保存时留空即可",
            key="capability_center_brave_key",
            help="密钥写入系统凭据管理器，数据库只保存引用、指纹和末四位。",
        )
        if st.button("安全保存搜索密钥", key="save_brave_search_credential"):
            if not brave_key.strip():
                st.warning("请输入 Brave Search API Key。")
            else:
                try:
                    store_system_credential(
                        brave_key.strip(),
                        purpose="web-search",
                        owner_id="brave",
                        credential_ref=build_credential_ref("web-search", "brave"),
                    )
                    st.success("搜索密钥已保存到系统凭据管理器。")
                    st.rerun()
                except Exception as exc:
                    st.error(f"搜索密钥保存失败：{exc}")


def render_llm_settings_page():
    profiles, active_profile, settings, _, _ = _load_llm_profile_state()
    view = st.segmented_control(
        "模型设置视图",
        options=["当前方案", "能力中心", "已保存方案", "用量与费用"],
        default="当前方案",
        key="llm_settings_view",
        label_visibility="collapsed",
    )
    if view == "当前方案":
        _render_active_llm_settings(settings)
        selected_profile = _render_llm_profile_management(profiles, active_profile)
        _render_provider_quick_fill(str(selected_profile.get("id") or ""))
        _render_llm_profile_form(selected_profile, active_profile)
    elif view == "能力中心":
        _render_capability_center()
    elif view == "已保存方案":
        _render_saved_llm_profiles(profiles, active_profile)
    else:
        st.markdown("### 全局模型用量")
        render_usage_dashboard(key_prefix="global_llm_usage")
