"""Creative profile page."""
from __future__ import annotations

import html

import streamlit as st

from creative_profile_workflows import (
    CUSTOM_OPTION_LABEL,
    build_creative_profile_from_form_values,
    build_profile_from_task_wizard,
    normalize_creative_form_state,
    recommended_workflow_for_profile,
)
from memory import list_stories, load_creative_profile, save_creative_profile
from skills import (
    discuss_creative_profile,
    discuss_creative_profile_turn,
)
from ui.common import navigate_to, scoped_widget_key, select_with_custom, stable_widget_suffix
from ui.discussion import (
    _append_discussion_message,
    _consume_discussion_input_clear,
    _discussion_initial_user_message,
    _discussion_input_clear_flag_key,
    _discussion_input_key,
    _discussion_messages_key,
    _discussion_result_key,
    _render_discussion_chat,
    _render_discussion_decision_hint,
    _render_discussion_empty_hint,
    _render_discussion_summary,
    _render_discussion_workspace,
    _run_discussion_chat_stream,
)
from ui.layout import render_section_heading
from ui.step_views import render_step_json_expander, render_step_retrieval


DEFAULT_WORLDLINE_ID = "main"
DEFAULT_WORLDLINE_LABEL = "本项目主线"


CREATIVE_PROFILE_FORM_KEYS = {
    "story_mode": "creative_story_mode",
    "target_length": "creative_target_length",
    "target_word_count": "creative_form_target_word_count",
    "workflow_depth": "creative_workflow_depth",
    "reference_strength": "creative_reference_strength",
    "conflict_policy": "creative_conflict_policy",
    "custom_reference_focus": "creative_form_custom_reference_focus",
    "allow_canon_deviation": "creative_form_allow_canon_deviation",
    "reference_focus": "creative_form_reference_focus",
    "worldline_id": "creative_form_worldline_id",
    "worldline_label": "creative_form_worldline_label",
    "worldline_retrieval_mode": "creative_form_worldline_retrieval_mode",
}


def _creative_profile_state_key(project_name: str, story_id: str) -> str:
    return f"creative_profile_form_state:{stable_widget_suffix(f'{project_name}:{story_id}')}"


def _creative_profile_form_keys(project_name: str, story_id: str) -> dict[str, str]:
    suffix = stable_widget_suffix(f"{project_name}:{story_id}")
    return {name: f"{base_key}_{suffix}" for name, base_key in CREATIVE_PROFILE_FORM_KEYS.items()}


def _init_creative_profile_form_state(project_name: str, story_id: str, profile: dict):
    state_key = _creative_profile_state_key(project_name, story_id)
    if state_key in st.session_state:
        return
    st.session_state[state_key] = normalize_creative_form_state(profile)


def _get_creative_profile_form_state(project_name: str, story_id: str) -> dict:
    return dict(st.session_state.get(_creative_profile_state_key(project_name, story_id), {}))


def _set_creative_profile_form_state(project_name: str, story_id: str, profile: dict, *, sync_widgets: bool = True):
    normalized = normalize_creative_form_state(profile)
    st.session_state[_creative_profile_state_key(project_name, story_id)] = normalized
    if not sync_widgets:
        return
    form_keys = _creative_profile_form_keys(project_name, story_id)
    st.session_state[f"{form_keys['story_mode']}_select"] = normalized["story_mode"] if normalized["story_mode"] in {"主线故事", "番外", "续写", "前传", "穿越", "平行世界", "原作补完", "单场景片段", "设定补写", CUSTOM_OPTION_LABEL} else CUSTOM_OPTION_LABEL
    st.session_state[f"{form_keys['story_mode']}_custom"] = normalized["story_mode"] if normalized["story_mode"] not in {"主线故事", "番外", "续写", "前传", "穿越", "平行世界", "原作补完", "单场景片段", "设定补写"} else ""
    st.session_state[f"{form_keys['target_length']}_select"] = normalized["target_length"] if normalized["target_length"] in {"片段", "短篇", "中篇", "长篇", CUSTOM_OPTION_LABEL} else CUSTOM_OPTION_LABEL
    st.session_state[f"{form_keys['target_length']}_custom"] = normalized["target_length"] if normalized["target_length"] not in {"片段", "短篇", "中篇", "长篇"} else ""
    st.session_state[f"{form_keys['workflow_depth']}_select"] = normalized["workflow_depth"] if normalized["workflow_depth"] in {"只生成正文", "短篇结构+正文", "章节计划+正文", "分卷/剧情段/章节", "完整长篇流程", CUSTOM_OPTION_LABEL} else CUSTOM_OPTION_LABEL
    st.session_state[f"{form_keys['workflow_depth']}_custom"] = normalized["workflow_depth"] if normalized["workflow_depth"] not in {"只生成正文", "短篇结构+正文", "章节计划+正文", "分卷/剧情段/章节", "完整长篇流程"} else ""
    st.session_state[f"{form_keys['reference_strength']}_select"] = normalized["reference_strength"] if normalized["reference_strength"] in {"轻参考", "中参考", "强参考", "严格原作", "主要参考文风", CUSTOM_OPTION_LABEL} else CUSTOM_OPTION_LABEL
    st.session_state[f"{form_keys['reference_strength']}_custom"] = normalized["reference_strength"] if normalized["reference_strength"] not in {"轻参考", "中参考", "强参考", "严格原作", "主要参考文风"} else ""
    st.session_state[f"{form_keys['conflict_policy']}_select"] = normalized["conflict_policy"] if normalized["conflict_policy"] in {"优先项目设定", "优先原作资料", "人工确认", "保留多版本", CUSTOM_OPTION_LABEL} else CUSTOM_OPTION_LABEL
    st.session_state[f"{form_keys['conflict_policy']}_custom"] = normalized["conflict_policy"] if normalized["conflict_policy"] not in {"优先项目设定", "优先原作资料", "人工确认", "保留多版本"} else ""
    st.session_state[form_keys["target_word_count"]] = normalized["target_word_count"]
    st.session_state[form_keys["reference_focus"]] = normalized["reference_focus"]
    st.session_state[form_keys["custom_reference_focus"]] = normalized["custom_reference_focus"]
    st.session_state[form_keys["allow_canon_deviation"]] = normalized["allow_canon_deviation"]
    st.session_state[form_keys["worldline_id"]] = normalized["worldline_id"]
    st.session_state[form_keys["worldline_label"]] = normalized["worldline_label"]
    st.session_state[form_keys["worldline_retrieval_mode"]] = normalized["worldline_retrieval_mode"]

def _current_creative_story(project_name: str) -> tuple[str, str]:
    story_id = st.session_state.get("active_story_id", "default")
    stories = list_stories(project_name)
    current_story_name = "默认"
    for s in stories:
        if s.get("story_id") == story_id:
            current_story_name = s.get("name", story_id)
            break
    return story_id, current_story_name

def _render_creative_profile_header(current_story_name: str, embedded: bool):
    if not embedded:
        render_section_heading(
            f"当前故事：{current_story_name}",
            "同一项目下的不同故事可以拥有各自的篇幅、参考强度和生成层级。",
        )
        st.info(
            f"当前正在配置 **{current_story_name}** 的创作参数。"
            "创作配置是故事级别的——同一项目不同故事可以设置各自的篇幅、参考强度和生成层级。"
            "项目级别的资料（知识库、原材料、规则）为所有故事共享。",
        )

def _render_creative_profile_discussion(project_name: str, story_id: str, form_state: dict):
    creative_discussion_suffix = f"{project_name}:{story_id}"
    discussion_messages_key = _discussion_messages_key("creative_profile", creative_discussion_suffix)
    discussion_result_key = _discussion_result_key("creative_profile", creative_discussion_suffix)
    discussion_input_key = _discussion_input_key("creative_profile", creative_discussion_suffix)
    clear_input_flag_key = _discussion_input_clear_flag_key("creative_profile", creative_discussion_suffix)
    legacy_seed_key = scoped_widget_key("creative_profile_discussion_seed", project_name, story_id)
    _consume_discussion_input_clear("creative_profile", creative_discussion_suffix)
    if discussion_input_key not in st.session_state and st.session_state.get(legacy_seed_key):
        st.session_state[discussion_input_key] = st.session_state.get(legacy_seed_key, "")
    discussion_step = st.session_state.get(discussion_result_key, {})
    messages = st.session_state.get(discussion_messages_key, [])
    st.caption("把想写什么、写多长、参考资料强度和生成流程放在同一个对话里；系统会整理成配置草稿。")
    _render_creative_profile_discussion_workspace(
        project_name,
        story_id,
        discussion_step,
        discussion_result_key,
        discussion_messages_key,
        discussion_input_key,
        clear_input_flag_key,
        messages,
    )


def _render_creative_profile_discussion_workspace(
    project_name: str,
    story_id: str,
    discussion_step: dict,
    discussion_result_key: str,
    discussion_messages_key: str,
    discussion_input_key: str,
    clear_input_flag_key: str,
    messages: list[dict],
):
    def render_input_panel(_stream_container) -> None:
        st.markdown("##### 讨论创作配置")
        _render_discussion_decision_hint(
            ["故事类型", "目标篇幅", "生成流程", "参考强度"],
            "创作配置、项目资源和后续检索",
            note="建议可直接保存为正式配置；需要细调可在下方高级配置修改。",
        )
        current_messages = st.session_state.get(discussion_messages_key, [])
        if current_messages:
            _render_discussion_chat(current_messages, height=260)
        else:
            _render_discussion_empty_hint("先说想写什么，我会整理成配置建议。")
        live_turn_container = st.empty()
        user_input = st.text_area(
            "讨论输入",
            key=discussion_input_key,
            height=96,
            placeholder="例如：我想写一个同一时间线下女主视角的故事，篇幅和当前上传的篇幅差不多。",
            label_visibility="collapsed",
        )
        has_started = bool(st.session_state.get(discussion_result_key) or current_messages)
        send_label = "发送" if has_started else "开始讨论"
        action_col, reset_col = st.columns([3, 1])
        if action_col.button(send_label, key=scoped_widget_key("send_creative_profile_discussion", project_name, story_id), use_container_width=True):
            submitted = str(user_input or "").strip()
            if not submitted:
                st.warning("讨论消息不能为空。")
            else:
                try:
                    existing_messages = list(st.session_state.get(discussion_messages_key, []))
                    _append_discussion_message(discussion_messages_key, "user", submitted)
                    updated_messages = st.session_state.get(discussion_messages_key, [])
                    if has_started:
                        seed_idea = _discussion_initial_user_message(existing_messages, submitted)
                        result = _run_discussion_chat_stream(
                            live_turn_container,
                            submitted,
                            "继续讨论创作配置",
                            discuss_creative_profile_turn,
                            project_name,
                            seed_idea,
                            updated_messages,
                            st.session_state.get(discussion_result_key, {}).get("data", {}).get("discussion", {}),
                            submitted,
                            story_id=story_id,
                        )
                        assistant_message = result.get("data", {}).get("assistant_message", "") or "已更新创作配置建议。"
                    else:
                        result = _run_discussion_chat_stream(
                            live_turn_container,
                            submitted,
                            "讨论创作配置",
                            discuss_creative_profile,
                            project_name,
                            submitted,
                            story_id=story_id,
                        )
                        assistant_message = result.get("data", {}).get("discussion", {}).get("current_understanding", "") or "我先整理了当前理解、推荐配置方向和待确认问题，我们可以继续细化。"
                    st.session_state[discussion_result_key] = result
                    _append_discussion_message(discussion_messages_key, "assistant", assistant_message)
                    st.session_state[clear_input_flag_key] = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"讨论失败：{exc}")
        if reset_col.button("重置", key=scoped_widget_key("reset_creative_profile_discussion", project_name, story_id), use_container_width=True):
            st.session_state[discussion_result_key] = {}
            st.session_state[discussion_messages_key] = []
            st.session_state[clear_input_flag_key] = True
            st.rerun()

    def render_output_panel() -> None:
        st.markdown("##### 配置草稿")
        current_step = st.session_state.get(discussion_result_key, discussion_step)
        if not current_step:
            st.caption("开始讨论后，这里显示配置建议；确认后可直接保存为正式创作配置。")
            return
        discussion_payload = current_step.get("data", {}).get("discussion", {}) if current_step else {}
        recommended_profile = discussion_payload.get("recommended_profile", {}) if isinstance(discussion_payload, dict) else {}
        st.markdown("##### 建议详情")
        _render_discussion_summary(current_step, "")
        st.caption("使用建议会直接保存为正式创作配置；需要细调时，可到下方高级配置修改后再保存。")
        if st.button("保存", use_container_width=True, type="primary", key=scoped_widget_key("apply_profile_rec", project_name, story_id)):
            if not recommended_profile:
                st.warning("当前还没有可保存的推荐配置。")
            else:
                profile_to_save = dict(recommended_profile)
                profile_to_save.pop("notes", None)
                saved_profile = save_creative_profile(project_name, profile_to_save, story_id=story_id, mark_configured=True)
                _set_creative_profile_form_state(project_name, story_id, saved_profile)
                st.success("已保存为正式创作配置。")
                st.rerun()
        render_step_retrieval(current_step, "讨论参考的上传资料")
    _render_discussion_workspace(
        f"creative-profile-{project_name}-{story_id}",
        render_input_panel,
        render_output_panel,
    )


def _creative_profile_from_form_values(form_values: dict) -> dict:
    return build_creative_profile_from_form_values(
        form_values["story_mode"],
        form_values["target_length"],
        form_values["target_word_count"],
        form_values["workflow_depth"],
        form_values["reference_strength"],
        form_values["conflict_policy"],
        form_values["reference_focus"],
        form_values["custom_reference_focus"],
        form_values["allow_canon_deviation"],
        form_values["worldline_id"],
        form_values["worldline_label"],
        form_values["worldline_retrieval_mode"],
    )


def _render_creative_worldline_fields(form_state: dict, profile_keys: dict[str, str]) -> dict:
    col_worldline_a, col_worldline_b, col_worldline_c = st.columns([1, 1, 1])
    worldline_id = col_worldline_a.text_input(
        "当前世界线 ID",
        value=form_state.get("worldline_id", DEFAULT_WORLDLINE_ID),
        placeholder="例如：main、au_modern、branch_01",
        key=profile_keys["worldline_id"],
        help="用于 资料检索过滤和加权。建议使用稳定英文/拼音/数字 ID。",
    )
    worldline_label = col_worldline_b.text_input(
        "当前世界线名称",
        value=form_state.get("worldline_label", DEFAULT_WORLDLINE_LABEL),
        placeholder="例如：本项目主线、现代 AU、二周目分支",
        key=profile_keys["worldline_label"],
    )
    worldline_retrieval_mode = col_worldline_c.selectbox(
        "世界线检索模式",
        options=["prefer", "strict"],
        index=0 if form_state.get("worldline_retrieval_mode", "prefer") != "strict" else 1,
        format_func=lambda value: {"prefer": "偏好匹配", "strict": "严格过滤"}.get(value, value),
        key=profile_keys["worldline_retrieval_mode"],
        help="偏好匹配会保留其他世界线但降权；严格过滤会排除明确属于其他世界线的资料。",
    )
    return {
        "worldline_id": worldline_id,
        "worldline_label": worldline_label,
        "worldline_retrieval_mode": worldline_retrieval_mode,
    }


def _render_creative_reference_fields(form_state: dict, profile_keys: dict[str, str], focus_options: list[str]) -> dict:
    reference_focus = st.multiselect(
        "重点参考方向",
        options=focus_options,
        default=form_state.get("reference_focus", ["角色", "世界观", "剧情事件"]),
        key=profile_keys["reference_focus"],
    )
    custom_reference_focus = st.text_input(
        "自定义参考方向（用逗号分隔，可选）",
        value=form_state.get("custom_reference_focus", ""),
        placeholder="例如：人物关系、能力代价、心理活动、转场方式、口癖",
        key=profile_keys["custom_reference_focus"],
    )
    allow_canon_deviation = st.checkbox(
        "允许根据需求改写原设",
        value=bool(form_state.get("allow_canon_deviation", True)),
        key=profile_keys["allow_canon_deviation"],
    )
    return {
        "reference_focus": reference_focus,
        "custom_reference_focus": custom_reference_focus,
        "allow_canon_deviation": allow_canon_deviation,
    }


def _render_creative_profile_form_fields(project_name: str, story_id: str, form_state: dict) -> tuple[bool, dict]:
    profile_keys = _creative_profile_form_keys(project_name, story_id)
    story_modes = ["主线故事", "番外", "续写", "前传", "穿越", "平行世界", "原作补完", "单场景片段", "设定补写"]
    target_lengths = ["片段", "短篇", "中篇", "长篇"]
    workflow_depths = ["只生成正文", "短篇结构+正文", "章节计划+正文", "分卷/剧情段/章节", "完整长篇流程"]
    reference_strengths = ["轻参考", "中参考", "强参考", "严格原作", "主要参考文风"]
    focus_options = ["角色", "世界观", "剧情事件", "道具能力", "时间线", "写作风格", "对白风格", "写作手法", "硬性约束"]
    conflict_policies = ["优先项目设定", "优先原作资料", "人工确认", "保留多版本"]

    profile_form_host = st.expander(
        "高级：手动调整创作配置",
        expanded=False,
    )
    with profile_form_host.form(scoped_widget_key("creative_profile_form", project_name, story_id)):
        col_a, col_b = st.columns(2)
        story_mode = select_with_custom(
            col_a,
            "任务性质",
            story_modes,
            form_state.get("story_mode", "主线故事"),
            profile_keys["story_mode"],
            "例如：半架空续写、原角色现代都市篇、只补某角色死亡前一晚。",
        )
        target_length = select_with_custom(
            col_b,
            "目标篇幅",
            target_lengths,
            form_state.get("target_length", "长篇"),
            profile_keys["target_length"],
            "例如：1.5 万字中短篇、五个小节、三幕式短篇。",
        )
        target_word_count = col_a.text_input(
            "目标字数（可选）",
            value=form_state.get("target_word_count", ""),
            placeholder="例如：8000、2万、20万",
            key=profile_keys["target_word_count"],
        )
        workflow_depth = select_with_custom(
            col_b,
            "生成层级",
            workflow_depths,
            form_state.get("workflow_depth", "完整长篇流程"),
            profile_keys["workflow_depth"],
            "例如：先三幕式结构，再分 5 个小节写正文。",
        )
        reference_strength = select_with_custom(
            col_a,
            "资料参考强度",
            reference_strengths,
            form_state.get("reference_strength", "中参考"),
            profile_keys["reference_strength"],
            "例如：强参考角色语气，弱参考世界观；只借人物关系。",
        )
        conflict_policy = select_with_custom(
            col_b,
            "资料冲突处理",
            conflict_policies,
            form_state.get("conflict_policy", "优先项目设定"),
            profile_keys["conflict_policy"],
            "例如：原作性格优先，但世界观以本项目为准。",
        )
        worldline_values = _render_creative_worldline_fields(form_state, profile_keys)
        reference_values = _render_creative_reference_fields(form_state, profile_keys, focus_options)
        form_actions = st.columns([1, 1, 3])
        submitted = form_actions[0].form_submit_button("保存创作配置", use_container_width=True)
    return submitted, {
        "story_mode": story_mode,
        "target_length": target_length,
        "target_word_count": target_word_count,
        "workflow_depth": workflow_depth,
        "reference_strength": reference_strength,
        "conflict_policy": conflict_policy,
        **reference_values,
        **worldline_values,
    }


def _render_creative_profile_form(project_name: str, story_id: str, form_state: dict) -> dict:
    submitted, form_values = _render_creative_profile_form_fields(project_name, story_id, form_state)
    profile = _creative_profile_from_form_values(form_values)
    if not submitted:
        return profile

    saved = save_creative_profile(project_name, profile, story_id=story_id, mark_configured=True)
    _set_creative_profile_form_state(project_name, story_id, saved, sync_widgets=False)
    st.success("创作配置已保存。")
    return saved

def _render_creative_profile_recommendation(project_name: str, story_id: str, profile: dict):
    render_section_heading("推荐生成路径", "系统会根据当前配置建议从哪个创作流程开始。")
    workflow = recommended_workflow_for_profile(profile)
    workflow_text = html.escape(" / ".join(str(item) for item in workflow))
    st.markdown(
        f"""
        <div class="nf-card">
            <div class="nf-card-copy">{workflow_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_section_heading("参考策略说明")
    strength = profile.get("reference_strength", "中参考")
    strategy_text = {
        "轻参考": "只保留角色核心气质和少量关键设定，适合穿越、平行世界、新环境故事。",
        "中参考": "保留主要人物关系、能力规则和世界观基调，同时允许新剧情展开。",
        "强参考": "强调角色性格、时间线、能力规则和世界观一致性，适合续写和补完。",
        "严格原作": "冲突时优先原作资料，生成前应做一致性检查。",
        "主要参考文风": "弱化剧情设定绑定，重点参考句式、节奏、对白和叙事手法。",
    }.get(strength, "按当前配置综合参考资料。")
    st.info(strategy_text)
    if profile.get("is_configured"):
        if st.button("开始生成正文", type="primary", use_container_width=True, key=scoped_widget_key("start_generation_after_profile", project_name, story_id)):
            navigate_to("正文生成")
            st.rerun()
    with st.expander("高级：创作配置详细数据", expanded=False):
        st.json({key: value for key, value in profile.items() if key != "notes"})

def render_creative_profile_page(project_name: str, embedded: bool = False, *, render_discussion_asset_candidates):
    story_id, current_story_name = _current_creative_story(project_name)
    _render_creative_profile_header(current_story_name, embedded)

    profile = load_creative_profile(project_name, story_id=story_id)
    _init_creative_profile_form_state(project_name, story_id, profile)
    form_state = _get_creative_profile_form_state(project_name, story_id)
    render_section_heading("讨论创作配置", "把想写的内容说清楚，系统会整理成可采用的配置建议。")
    _render_creative_profile_discussion(
        project_name,
        story_id,
        form_state,
    )
    render_section_heading("手动配置", "这些字段会决定后续规划、正文生成和检索资料的默认策略。")
    profile = _render_creative_profile_form(project_name, story_id, form_state)
    _render_creative_profile_recommendation(project_name, story_id, profile)

def render_creative_task_wizard(project_name: str, story_id: str = "default"):
    st.markdown("### 创作任务向导")
    st.caption("用中文目标快速生成一份创作配置。保存后，“快速生成”和各类生成提示会按这份配置调整。")

    task_options = ["主线故事", "番外", "续写", "前传", "穿越", "平行世界", "原作补完", "单场景片段", "设定补写"]
    length_options = ["片段", "短篇", "中篇", "长篇"]
    output_options = ["只要正文", "短篇结构和正文", "章节计划和正文", "分卷/剧情段/章节计划", "完整长篇流程"]
    strength_options = ["轻参考", "中参考", "强参考", "严格原作", "主要参考文风"]
    focus_options = ["角色", "世界观", "剧情事件", "道具能力", "时间线", "写作风格", "对白风格", "写作手法", "硬性约束"]
    conflict_options = ["优先项目设定", "优先原作资料", "人工确认", "保留多版本"]

    col_a, col_b = st.columns(2)
    task_type = col_a.selectbox("这次想写什么", task_options, key="task_wizard_type")
    target_length = col_b.selectbox("大概篇幅", length_options, key="task_wizard_length")
    output_goal = col_a.selectbox("希望系统产出什么", output_options, key="task_wizard_output")
    reference_strength = col_b.selectbox("参考原作/资料的强度", strength_options, index=1, key="task_wizard_reference_strength")
    target_word_count = col_a.text_input("目标字数（可选）", placeholder="例如：8000、2万、20万", key="task_wizard_word_count")
    conflict_policy = col_b.selectbox("资料冲突时怎么处理", conflict_options, key="task_wizard_conflict_policy")
    focus_items = st.multiselect(
        "重点参考方向",
        options=focus_options,
        default=["角色", "世界观", "剧情事件"],
        key="task_wizard_focus",
    )
    allow_canon_deviation = st.checkbox("允许按需求改写原设", value=True, key="task_wizard_allow_deviation")

    preview_profile = build_profile_from_task_wizard(
        task_type,
        target_length,
        output_goal,
        reference_strength,
        target_word_count,
        focus_items,
        allow_canon_deviation,
        conflict_policy,
    )
    st.caption(f"推荐路径：{' / '.join(recommended_workflow_for_profile(preview_profile))}")
    render_step_json_expander("向导生成的配置预览", preview_profile)

    if st.button("保存向导配置", key=scoped_widget_key("save_creative_task_wizard", project_name, story_id)):
        saved = save_creative_profile(project_name, preview_profile, story_id=story_id, mark_configured=True)
        _set_creative_profile_form_state(project_name, story_id, saved)
        st.success("已根据向导保存创作配置。")
        st.session_state["task_wizard_last_profile"] = saved
        st.rerun()
