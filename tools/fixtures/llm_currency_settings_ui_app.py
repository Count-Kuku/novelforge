"""Streamlit fixture for CNY-first model settings."""
from __future__ import annotations

from novelforge.core.llm import PROVIDER_PRESETS
from novelforge.services.memory.core import _normalize_llm_profile
import ui.llm_settings as settings_ui


profile = _normalize_llm_profile(
    {
        **PROVIDER_PRESETS["DeepSeek"],
        "id": "deepseek-main",
        "name": "DeepSeek 主账号",
        "api_key": "test-key",
    },
    "deepseek-main",
)
active_settings = {
    **profile,
    "profile_id": profile["id"],
    "profile_name": profile["name"],
    "env_path": ".env",
    "profiles_path": "data/llm_profiles.json",
}
settings_ui._load_llm_profile_state = lambda: (
    [profile],
    profile,
    active_settings,
    [profile["id"]],
    {profile["id"]: f"{profile['name']}（当前）"},
)
settings_ui.render_usage_dashboard = lambda **_kwargs: None
settings_ui.render_llm_settings_page()
