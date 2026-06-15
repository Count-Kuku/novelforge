import json
import re
import hashlib

import streamlit as st
from urllib.parse import urlparse

from memory import (
    load_chapter_discussion_artifact,
    create_project,
    delete_llm_profile,
    delete_long_reference_batch,
    delete_arc,
    delete_retrieval_source_file,
    delete_volume,
    get_active_llm_profile,
    load_arc_discussion_artifact,
    list_arcs,
    load_analysis_report,
    load_arc_metadata,
    load_arc_chapter_plan,
    load_arc_outline,
    load_chapter_outline_metadata,
    load_conflict_resolutions,
    delete_arc_chapter_plan,
    load_evaluation_json,
    load_evaluation_report,
    load_global_rules,
    load_creative_profile,
    load_knowledge_base,
    load_knowledge_category,
    load_source_package_report,
    load_long_reference_batch,
    load_pending_knowledge_items,
    list_projects,
    list_long_reference_batches,
    list_retrieval_source_files,
    list_volumes,
    load_chapter,
    load_chapter_outline,
    load_memory,
    load_outline,
    load_outline_discussion_artifact,
    load_llm_settings,
    load_llm_profiles,
    load_project_rules,
    load_review,
    load_review_json,
    load_volume_discussion_artifact,
    load_volume_metadata,
    load_volume_outline,
    save_chapter,
    save_creative_profile,
    save_source_package_report,
    save_long_reference_batch,
    save_chapter_outline,
    save_chapter_outline_metadata,
    save_global_rules,
    save_memory,
    save_knowledge_category,
    append_knowledge_items,
    confirm_pending_knowledge_items,
    discard_pending_knowledge_items,
    queue_pending_knowledge_items,
    save_pending_knowledge_items,
    save_outline,
    save_project_rules,
    create_long_reference_batch,
    set_active_llm_profile,
    save_arc_metadata,
    save_arc_outline,
    save_volume_metadata,
    save_volume_outline,
    upsert_llm_profile,
    list_pipeline_runs,
    load_pipeline_run,
    retrieval_sources_path,
)
from project_manager import (
    delete_analysis_report,
    delete_chapter_analysis_bundle,
    delete_chapter_bundle,
    delete_chapter_content,
    delete_chapter_outline,
    delete_chapter_review,
    delete_evaluation_report,
    delete_outline,
    delete_pipeline_run,
    delete_project,
    get_project_summary,
    list_analysis_reports,
    list_chapter_inventory,
    list_evaluation_reports,
    list_project_runs,
    list_retrieval_sources,
    rename_project,
    save_analysis_resource,
    save_evaluation_resource,
    save_retrieval_source_content,
    save_review_resources,
)
from retrieval import build_structured_external_source_payload, debug_retrieve_context, rebuild_retrieval_assets, ingest_external_source_file, load_retrieval_index, retrieve_context
from skills import (
    approve_chapter_discussion,
    approve_arc_discussion,
    approve_outline_discussion,
    approve_volume_discussion,
    analyze_characters,
    analyze_foreshadowing,
    analyze_timeline,
    clear_chapter_discussion_approval,
    clear_arc_discussion_approval,
    clear_outline_discussion_approval,
    clear_volume_discussion_approval,
    compact_memory,
    detect_potential_conflicts,
    discuss_arc,
    discuss_arc_turn,
    discuss_chapter,
    discuss_chapter_turn,
    discuss_outline,
    discuss_outline_turn,
    discuss_volume,
    discuss_volume_turn,
    extract_reference_knowledge,
    generate_arc_outline,
    generate_arc_chapter_plan,
    generate_chapter_outline,
    generate_outline,
    generate_volume_outline,
    get_retrieval_trace,
    organize_reference_html,
    organize_reference_url,
    organize_reference_text,
    evaluate_chapter,
    review_chapter,
    run_consistency_check,
    pipeline_plan_write_review_update,
    resume_chapter_pipeline,
    run_dynamic_generation_task,
    save_retrieval_conflict_resolution,
    save_rule_text,
    update_memory_from_chapter,
    write_chapter,
)


RULE_SCOPE_OPTIONS = {
    "all": "通用",
    "outline": "全书大纲",
    "chapter_outline": "章节细纲",
    "write": "正文写作",
    "review": "章节审阅",
    "memory_update": "设定更新",
}

STATUS_LABELS = {
    "pass": "通过",
    "revise": "需要修改",
    "blocked": "阻塞",
    "draft": "草稿",
    "approved": "已批准",
    "archived": "已归档",
    "completed": "已完成",
    "failed": "失败",
    "rejected": "已拒绝",
    "skipped": "已跳过",
}

SCOPE_LABELS = {
    "project": "项目资料",
    "canon": "原作资料",
    "reference": "参考资料",
}

AUTHORITY_LABELS = {
    "project": "项目设定",
    "official": "官方资料",
    "curated": "人工整理",
    "community": "社区资料",
    "unknown": "未标明",
}

RETRIEVAL_MODE_LABELS = {
    "hybrid": "混合检索",
    "lexical": "关键词检索",
    "semantic": "语义检索",
}

SOURCE_TYPE_LABELS = {
    "outline": "全书大纲",
    "outline_discussion": "全书讨论工件",
    "volume_outline": "分卷大纲",
    "volume_discussion": "分卷讨论工件",
    "arc_outline": "剧情段大纲",
    "arc_discussion": "剧情段讨论工件",
    "arc_chapter_plan": "剧情段章节分配",
    "chapter_outline": "章节细纲",
    "chapter_discussion": "章节讨论工件",
    "chapter_content": "章节正文",
    "chapter_summary": "章节摘要",
    "review_summary": "审阅摘要",
    "review_issue": "审阅问题",
    "review_markdown": "审阅报告",
    "review_characters_check": "角色审阅",
    "review_world_check": "世界观审阅",
    "review_timeline_check": "时间线审阅",
    "review_foreshadowing_check": "伏笔审阅",
    "analysis_consistency": "一致性分析",
    "analysis_characters": "角色分析",
    "analysis_timeline": "时间线分析",
    "analysis_foreshadowing": "伏笔分析",
    "evaluation_chapter": "章节评估",
    "conflict_resolution": "冲突裁决",
    "memory_character": "角色设定",
    "memory_world": "世界观设定",
    "memory_au_rule": "改写规则",
    "memory_relationship": "角色关系",
    "memory_timeline": "时间线设定",
    "memory_foreshadowing": "伏笔设定",
    "memory_active_constraint": "当前硬性约束",
    "external_source": "通用外部资料",
    "external_character_sheet": "角色资料",
    "external_location_sheet": "地点资料",
    "external_organization_sheet": "组织资料",
    "external_timeline_note": "时间线资料",
    "external_canon_event": "原作事件",
    "external_world_rule": "世界规则",
    "external_artifact_note": "道具资料",
    "knowledge_characters": "结构化知识：角色",
    "knowledge_items": "结构化知识：物品与道具",
    "knowledge_abilities": "结构化知识：技能与能力",
    "knowledge_world_rules": "结构化知识：世界观规则",
    "knowledge_locations": "结构化知识：地点",
    "knowledge_organizations": "结构化知识：组织",
    "knowledge_timeline_events": "结构化知识：事件与时间线",
    "knowledge_relationships": "结构化知识：角色关系",
    "knowledge_writing_style": "结构化知识：写作风格",
    "knowledge_dialogue_style": "结构化知识：对白风格",
    "knowledge_narrative_techniques": "结构化知识：写作手法",
    "knowledge_constraints": "结构化知识：硬性约束",
}

DECISION_LABELS = {
    "merge": "人工折中",
    "use_project": "采纳项目设定",
    "use_external": "采纳外部/原作资料",
    "ignore": "忽略该冲突",
}

SEVERITY_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
}

SCHEMA_LABELS = {
    "OrganizedReferenceResult": "资料整理结果",
    "OutlineDiscussionResult": "全书讨论结果",
    "ChapterDiscussionResult": "章节讨论结果",
    "VolumeDiscussionResult": "分卷讨论结果",
    "ArcDiscussionResult": "剧情段讨论结果",
    "ArcChapterPlanResult": "剧情段章节分配计划",
    "MemoryUpdateResult": "设定更新结果",
    "ReviewResult": "章节审阅结果",
    "CharacterAnalysisResult": "角色分析结果",
    "TimelineAnalysisResult": "时间线分析结果",
    "ForeshadowingAnalysisResult": "伏笔分析结果",
    "ConsistencyAnalysisResult": "一致性检查结果",
    "ChapterEvaluationResult": "章节评估结果",
    "KnowledgeExtractionResult": "资料知识提取结果",
}

KNOWLEDGE_CATEGORY_LABELS = {
    "characters": "角色知识",
    "items": "物品与道具",
    "abilities": "技能与能力",
    "world_rules": "世界观规则",
    "locations": "地点资料",
    "organizations": "组织资料",
    "timeline_events": "事件与时间线",
    "relationships": "角色关系",
    "writing_style": "写作风格",
    "dialogue_style": "对白风格",
    "narrative_techniques": "写作手法",
    "constraints": "硬性约束",
}

STORY_MODE_WORKFLOWS = {
    "主线故事": ["需求确认", "故事结构", "章节计划", "正文生成", "评估修订"],
    "短篇": ["需求确认", "短篇结构", "正文生成", "快速评估"],
    "中篇": ["需求确认", "故事大纲", "章节计划", "正文生成", "评估修订"],
    "长篇": ["需求确认", "全书大纲", "分卷", "剧情段", "章节细纲", "正文", "审阅与设定更新"],
    "番外": ["角色状态", "场景目标", "正文生成", "风格检查"],
    "续写": ["已有剧情状态", "伏笔与约束检查", "下一段/下一章计划", "正文生成", "连续性审阅"],
    "前传": ["目标时间点", "原设边界", "前传结构", "正文生成", "时间线检查"],
    "穿越": ["原角色核心", "新环境规则", "适配规则", "新故事结构", "正文生成"],
    "补完": ["资料缺口", "原设边界", "补完结构", "正文生成", "一致性检查"],
    "片段": ["场景目标", "角色状态", "片段正文", "快速润色"],
}

CUSTOM_OPTION_LABEL = "自定义"

ERROR_TYPE_LABELS = {
    "llm": "模型调用",
    "validation": "结构校验",
    "persistence": "保存数据",
    "retrieval": "检索",
    "input": "输入",
    "unknown": "未知",
}

STEP_LABELS = {
    "start": "开始",
    "resume": "恢复",
    "creative_structure": "动态创作结构",
    "chapter_outline": "章节细纲",
    "write_chapter": "写作正文",
    "review_chapter": "章节审阅",
    "memory_update": "设定更新",
    "completed": "完成",
    "halted": "暂停",
}


NEW_PROJECT_INPUT_KEY = "new_project_name_input"
NEW_PROJECT_DIALOG_FLAG = "show_new_project_dialog"


def label_status(value: str) -> str:
    return STATUS_LABELS.get(str(value or ""), str(value or "-"))


def label_scope(value: str) -> str:
    return SCOPE_LABELS.get(str(value or ""), str(value or "未知范围"))


def label_authority(value: str) -> str:
    return AUTHORITY_LABELS.get(str(value or ""), str(value or "未标明"))


def label_retrieval_mode(value: str) -> str:
    return RETRIEVAL_MODE_LABELS.get(str(value or ""), str(value or "未知模式"))


def label_source_type(value: str) -> str:
    return SOURCE_TYPE_LABELS.get(str(value or ""), str(value or "未知资料"))


def label_yes_no(value: bool) -> str:
    return "是" if value else "否"


def label_schema(value: str) -> str:
    return SCHEMA_LABELS.get(str(value or ""), str(value or "-"))


def label_error_type(value: str) -> str:
    return ERROR_TYPE_LABELS.get(str(value or ""), str(value or "未知"))


def label_step_name(value: str) -> str:
    return STEP_LABELS.get(str(value or ""), str(value or "-"))


def label_knowledge_category(value: str) -> str:
    return KNOWLEDGE_CATEGORY_LABELS.get(str(value or ""), str(value or "未知知识"))


def label_batch_segment_status(value: str) -> str:
    labels = {
        "pending": "待处理",
        "imported": "已导入",
        "queued": "已加入待确认",
        "extracted": "已提取",
        "failed": "失败",
        "skipped": "已跳过",
        "": "待处理",
    }
    return labels.get(str(value or ""), str(value or "未知"))


def recommended_workflow_for_profile(profile: dict) -> list[str]:
    story_mode = str(profile.get("story_mode", "") or "")
    target_length = str(profile.get("target_length", "") or "")
    if story_mode == "主线故事":
        if "长篇" in target_length or "长" in target_length:
            return STORY_MODE_WORKFLOWS["长篇"]
        if "中篇" in target_length or "中" in target_length:
            return STORY_MODE_WORKFLOWS["中篇"]
        if "短篇" in target_length or "短" in target_length:
            return STORY_MODE_WORKFLOWS["短篇"]
        if "片段" in target_length or "场景" in target_length:
            return STORY_MODE_WORKFLOWS["片段"]
        return STORY_MODE_WORKFLOWS["主线故事"]
    if story_mode in STORY_MODE_WORKFLOWS:
        return STORY_MODE_WORKFLOWS[story_mode]

    combined = f"{story_mode} {target_length}"
    keyword_map = [
        (("续写",), "续写"),
        (("前传",), "前传"),
        (("穿越", "转生", "异世界", "平行世界", "AU"), "穿越"),
        (("番外",), "番外"),
        (("补完", "补全", "补设定"), "补完"),
        (("片段", "场景"), "片段"),
        (("短篇", "短"), "短篇"),
        (("中篇", "中"), "中篇"),
        (("长篇", "长"), "长篇"),
    ]
    for keywords, workflow_key in keyword_map:
        if any(keyword in combined for keyword in keywords):
            return STORY_MODE_WORKFLOWS[workflow_key]
    return STORY_MODE_WORKFLOWS["主线故事"]


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


def _discussion_messages_key(kind: str, suffix: str = "") -> str:
    return f"discussion_messages:{kind}:{suffix}" if suffix else f"discussion_messages:{kind}"


def _discussion_result_key(kind: str, suffix: str = "") -> str:
    return f"discussion_result:{kind}:{suffix}" if suffix else f"discussion_result:{kind}"


def _discussion_input_key(kind: str, suffix: str = "") -> str:
    return f"discussion_input:{kind}:{suffix}" if suffix else f"discussion_input:{kind}"


def _discussion_input_clear_flag_key(kind: str, suffix: str = "") -> str:
    return f"discussion_input_clear:{kind}:{suffix}" if suffix else f"discussion_input_clear:{kind}"


def _consume_discussion_input_clear(kind: str, suffix: str = ""):
    flag_key = _discussion_input_clear_flag_key(kind, suffix)
    if st.session_state.pop(flag_key, False):
        st.session_state[_discussion_input_key(kind, suffix)] = ""


def _append_discussion_message(key: str, role: str, content: str):
    content = str(content or "").strip()
    if not content:
        return
    messages = list(st.session_state.get(key, []))
    messages.append({"role": role, "content": content})
    st.session_state[key] = messages


def _render_discussion_chat(messages: list[dict]):
    if not messages:
        st.caption("当前还没有讨论消息。")
        return
    for item in messages:
        role = "user" if item.get("role") == "user" else "assistant"
        with st.chat_message(role):
            st.markdown(str(item.get("content", "") or ""))


def _render_discussion_summary(discussion_result: dict, empty_message: str):
    discussion = discussion_result.get("data", {}).get("discussion", {}) if discussion_result else {}
    report_markdown = discussion_result.get("data", {}).get("report_markdown", "") if discussion_result else ""
    if not discussion:
        st.caption(empty_message)
        return
    st.markdown(report_markdown)
    render_step_validation(discussion_result)
    render_step_json_expander("讨论结构化数据", discussion)


def _render_approved_discussion_artifact(artifact: dict, empty_message: str):
    discussion = artifact.get("discussion", {}) if isinstance(artifact, dict) else {}
    report_markdown = artifact.get("report_markdown", "") if isinstance(artifact, dict) else ""
    if not discussion:
        st.caption(empty_message)
        return
    st.markdown(report_markdown or "已存在批准后的讨论工件，但缺少可读预览。")
    render_step_json_expander("已批准讨论数据", discussion)


def _resource_browser_selection_key(project_name: str) -> str:
    return f"resource_browser_selection:{project_name}"


def _set_resource_browser_selection(project_name: str, resource: dict):
    st.session_state[_resource_browser_selection_key(project_name)] = resource


def _get_resource_browser_selection(project_name: str) -> dict:
    return dict(st.session_state.get(_resource_browser_selection_key(project_name), {}))


def render_step_status_message(step_result: dict, success_message: str, failure_prefix: str):
    if not step_result:
        return

    status = step_result.get("status")
    if status == "completed":
        st.success(success_message)
    elif status == "skipped":
        warnings = step_result.get("warnings") or []
        st.info(warnings[0] if warnings else "步骤已跳过。")
    else:
        st.error(f"{failure_prefix}{step_result.get('error', '未知错误')}")


def render_step_validation(step_result: dict):
    validation = step_result.get("validation", {})
    if validation.get("status") == "passed":
        st.caption(f"结构校验通过：{label_schema(validation.get('schema_name', '-'))}")
    elif validation.get("status") == "failed":
        schema_name = label_schema(validation.get("schema_name", "-"))
        errors = validation.get("errors") or []
        message = errors[0] if errors else validation.get("message", "结构校验失败。")
        st.caption(f"结构校验失败：{schema_name} / {message}")


def render_step_json_expander(title: str, payload: dict):
    if not payload:
        return
    with st.expander(title, expanded=False):
        st.code(json.dumps(payload, ensure_ascii=False, indent=2), language="json")


def render_step_retrieval(step_result: dict, title: str, fallback_hits: list[dict] | None = None):
    hits = step_result.get("retrieval_hits", []) if step_result else []
    render_retrieval_hits_block(hits or (fallback_hits or []), title)


def _render_rule_editor(title: str, storage_key: str, rules: dict) -> dict:
    st.subheader(title)
    updated = {}
    for scope, label in RULE_SCOPE_OPTIONS.items():
        updated[scope] = [line.strip() for line in st.text_area(
            f"{label}规则（每行一条）",
            value="\n".join(rules.get(scope, [])),
            height=120,
            key=f"{storage_key}_{scope}"
        ).split("\n") if line.strip()]
    return updated


def render_rules_page(project_name: str):
    st.subheader("交互规则中心")
    st.caption("将长期要求存成全局规则或项目规则，系统会在对应能力里自动注入这些约束。")

    with st.expander("快速记录新要求", expanded=True):
        rule_text = st.text_area("输入你的要求", height=140, key="rule_capture_text")
        col1, col2 = st.columns(2)
        scope_label = col1.selectbox("适用能力", options=list(RULE_SCOPE_OPTIONS.values()), key="rule_capture_scope")
        target_label = col2.selectbox("保存位置", options=["项目规则", "全局规则"], key="rule_capture_target")

        if st.button("保存要求为规则"):
            scope = next(key for key, value in RULE_SCOPE_OPTIONS.items() if value == scope_label)
            target = "project" if target_label == "项目规则" else "global"
            try:
                result = save_rule_text(project_name, scope, target, rule_text)
                if result.get("status") == "saved":
                    st.success(f"已保存到{target_label} / {scope_label}")
                    st.rerun()
                else:
                    st.warning("未提取到有效规则。")
            except Exception as exc:
                st.error(f"保存失败：{exc}")

    global_rules = load_global_rules()
    project_rules = load_project_rules(project_name)

    tab1, tab2 = st.tabs(["项目规则", "全局规则"])

    with tab1:
        updated_project_rules = _render_rule_editor(f"项目规则：{project_name}", "project_rules", project_rules)
        if st.button("保存项目规则"):
            save_project_rules(project_name, updated_project_rules)
            st.success("项目规则已保存")

    with tab2:
        updated_global_rules = _render_rule_editor("全局规则", "global_rules", global_rules)
        if st.button("保存全局规则"):
            save_global_rules(updated_global_rules)
            st.success("全局规则已保存")


def render_llm_settings_page():
    st.subheader("模型配置")
    st.caption("支持保存多套模型服务档案，并在网页端一键切换。当前激活的档案会同步写入项目根目录 `.env`。")

    profiles_payload = load_llm_profiles()
    profiles = profiles_payload.get("profiles", [])
    active_profile = get_active_llm_profile()
    settings = load_llm_settings()
    profile_options = [profile.get("id", "") for profile in profiles]

    selected_profile_id = st.selectbox(
        "已保存档案",
        options=profile_options,
        index=profile_options.index(active_profile.get("id", "")) if active_profile.get("id", "") in profile_options else 0,
        format_func=lambda profile_id: next((profile.get("name", profile_id) for profile in profiles if profile.get("id") == profile_id), profile_id),
        key="llm_profile_selector",
    )

    selected_profile = next((profile for profile in profiles if profile.get("id") == selected_profile_id), active_profile)

    switch_col, delete_col = st.columns(2)
    if switch_col.button("切换为当前档案", use_container_width=True):
        try:
            set_active_llm_profile(selected_profile_id)
            st.success("已切换当前模型档案，并同步更新 .env")
            st.rerun()
        except Exception as exc:
            st.error(f"切换失败：{exc}")

    if delete_col.button("删除当前档案", use_container_width=True):
        try:
            delete_llm_profile(selected_profile_id)
            st.success("档案已删除，当前激活配置已同步更新。")
            st.rerun()
        except Exception as exc:
            st.error(f"删除失败：{exc}")

    with st.form("llm_profile_form"):
        st.markdown("### 编辑或新增档案")
        profile_id_value = st.text_input("档案标识", value=selected_profile.get("id", ""), help="用于内部识别这套模型配置。建议使用英文、数字、短横线，例如 deepseek-main。")
        profile_name = st.text_input("档案名称", value=selected_profile.get("name", ""), placeholder="例如：DeepSeek 主账号")
        base_url = st.text_input("模型服务网址", value=selected_profile.get("base_url", ""), placeholder="https://api.deepseek.com")
        api_key = st.text_input("接口密钥", value=selected_profile.get("api_key", ""), type="password")
        model_name = st.text_input("聊天模型名", value=selected_profile.get("model_name", ""), placeholder="deepseek-v4-flash")
        embedding_model_name = st.text_input(
            "语义向量模型名",
            value=selected_profile.get("embedding_model_name", ""),
            placeholder="text-embedding-3-small",
        )
        auto_activate = st.checkbox("保存后立即切换为当前档案", value=selected_profile.get("id") == active_profile.get("id"))
        submitted = st.form_submit_button("保存档案")

    if submitted:
        cleaned_profile_id = profile_id_value.strip()
        cleaned_profile_name = profile_name.strip()
        cleaned_base_url = base_url.strip()
        cleaned_api_key = api_key.strip()
        cleaned_model_name = model_name.strip()
        cleaned_embedding_model_name = embedding_model_name.strip()

        if not cleaned_profile_id:
            st.error("档案标识不能为空。")
            return
        if not cleaned_profile_name:
            st.error("档案名称不能为空。")
            return
        if cleaned_base_url:
            parsed_url = urlparse(cleaned_base_url)
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                st.error("模型服务网址格式无效，需要以 http:// 或 https:// 开头，并包含完整域名。")
                return

        try:
            saved_profile = upsert_llm_profile({
                "id": cleaned_profile_id,
                "name": cleaned_profile_name,
                "base_url": cleaned_base_url,
                "api_key": cleaned_api_key,
                "model_name": cleaned_model_name,
                "embedding_model_name": cleaned_embedding_model_name,
            })
            if auto_activate:
                set_active_llm_profile(saved_profile.get("id", ""))
            st.success("模型档案已保存")
            st.rerun()
        except Exception as exc:
            st.error(f"保存模型档案失败：{exc}")

    st.markdown("### 已保存档案概览")
    for profile in profiles:
        label = profile.get("name", profile.get("id", ""))
        if profile.get("id") == active_profile.get("id"):
            label = f"{label}（当前）"
        with st.expander(label, expanded=False):
            preview_key = ""
            if profile.get("api_key"):
                preview_key = f"***{str(profile.get('api_key'))[-4:]}"
            st.code(json.dumps({
                "档案标识": profile.get("id", ""),
                "档案名称": profile.get("name", ""),
                "模型服务网址": profile.get("base_url", ""),
                "接口密钥": preview_key,
                "聊天模型名": profile.get("model_name", ""),
                "语义向量模型名": profile.get("embedding_model_name", ""),
            }, ensure_ascii=False, indent=2), language="json")

    masked_key = ""
    current_api_key = settings.get("api_key", "")
    if current_api_key:
        visible_tail = current_api_key[-4:] if len(current_api_key) >= 4 else current_api_key
        masked_key = f"***{visible_tail}"

    st.markdown("### 当前生效配置")
    st.code(json.dumps({
        "档案标识": settings.get("profile_id", ""),
        "档案名称": settings.get("profile_name", ""),
        "模型服务网址": settings.get("base_url", ""),
        "接口密钥": masked_key,
        "聊天模型名": settings.get("model_name", ""),
        "语义向量模型名": settings.get("embedding_model_name", ""),
        "环境配置文件": settings.get("env_path", ""),
        "档案保存文件": settings.get("profiles_path", ""),
    }, ensure_ascii=False, indent=2), language="json")


@st.dialog("新建项目")
def render_new_project_dialog(existing_projects: list[str]):
    candidate_name = st.text_input("项目名", key=NEW_PROJECT_INPUT_KEY).strip()
    col1, col2 = st.columns(2)

    if col1.button("确认创建", use_container_width=True):
        if not candidate_name:
            st.error("项目名不能为空。")
            return
        if candidate_name in existing_projects:
            st.error("该项目已存在，请使用项目切换。")
            return

        created_project = create_project(candidate_name)
        st.session_state["project_name"] = created_project
        st.session_state[NEW_PROJECT_DIALOG_FLAG] = False
        st.rerun()

    if col2.button("取消", use_container_width=True):
        st.session_state[NEW_PROJECT_DIALOG_FLAG] = False
        st.rerun()


def init_project_state() -> str | None:
    projects = list_projects()

    project_name = st.session_state.get("project_name")
    if project_name:
        if project_name not in projects:
            create_project(project_name)
        return project_name

    if projects:
        st.session_state["project_name"] = projects[0]
        return projects[0]

    return None


def render_sidebar(project_name: str | None, projects: list[str]):
    if projects:
        st.sidebar.caption("已有项目")
        selected_project = st.sidebar.selectbox(
            "快速切换",
            options=projects,
            index=projects.index(project_name) if project_name in projects else 0,
            key="project_switcher"
        )
        if selected_project != project_name:
            st.session_state["project_name"] = selected_project
            st.rerun()

    if st.sidebar.button("新建项目", use_container_width=True):
        st.session_state[NEW_PROJECT_INPUT_KEY] = ""
        st.session_state[NEW_PROJECT_DIALOG_FLAG] = True

    if st.session_state.get(NEW_PROJECT_DIALOG_FLAG):
        render_new_project_dialog(projects)


def render_memory_page(project_name: str, memory: dict):
    st.subheader("核心设定")
    st.caption("这里维护的是生成时始终优先注入的核心状态。长文本资料、原作证据、历史正文与分析报告通过“资料录入”和“检索中心”按需管理与召回。")

    changed = False
    new_memory = dict(memory)

    new_title = st.text_input("书名", value=memory.get("title", ""))
    if new_title != memory.get("title"):
        new_memory["title"] = new_title
        changed = True

    new_genre = st.text_input("类型", value=memory.get("genre", ""))
    if new_genre != memory.get("genre"):
        new_memory["genre"] = new_genre
        changed = True

    new_canon_mode = st.text_input(
        "原作对齐方式（如：严格贴合 / 轻度 AU / 完全 AU）",
        value=memory.get("canon_mode", "")
    )
    if new_canon_mode != memory.get("canon_mode", ""):
        new_memory["canon_mode"] = new_canon_mode
        changed = True

    new_au_rules = st.text_area(
        "AU 规则（每行一条）",
        value="\n".join(memory.get("au_rules", [])),
        height=100
    )
    au_rule_items = [line.strip() for line in new_au_rules.split("\n") if line.strip()]
    if au_rule_items != memory.get("au_rules", []):
        new_memory["au_rules"] = au_rule_items
        changed = True

    new_world = st.text_area(
        "世界观（每行一条）",
        value="\n".join(memory.get("world", [])),
        height=120
    )
    world_items = [line.strip() for line in new_world.split("\n") if line.strip()]
    if world_items != memory.get("world", []):
        new_memory["world"] = world_items
        changed = True

    new_characters = st.text_area(
        "角色（每行一条）",
        value="\n".join(memory.get("characters", [])),
        height=150
    )
    character_items = [line.strip() for line in new_characters.split("\n") if line.strip()]
    if character_items != memory.get("characters", []):
        new_memory["characters"] = character_items
        changed = True

    new_relationships = st.text_area(
        "角色关系（每行一条）",
        value="\n".join(memory.get("relationships", [])),
        height=120
    )
    relationship_items = [line.strip() for line in new_relationships.split("\n") if line.strip()]
    if relationship_items != memory.get("relationships", []):
        new_memory["relationships"] = relationship_items
        changed = True

    new_timeline = st.text_area(
        "时间线（每行一条）",
        value="\n".join(memory.get("timeline", [])),
        height=120
    )
    timeline_items = [line.strip() for line in new_timeline.split("\n") if line.strip()]
    if timeline_items != memory.get("timeline", []):
        new_memory["timeline"] = timeline_items
        changed = True

    new_foreshadowing = st.text_area(
        "伏笔（每行一条）",
        value="\n".join(memory.get("foreshadowing", [])),
        height=120
    )
    foreshadowing_items = [line.strip() for line in new_foreshadowing.split("\n") if line.strip()]
    if foreshadowing_items != memory.get("foreshadowing", []):
        new_memory["foreshadowing"] = foreshadowing_items
        changed = True

    new_constraints = st.text_area(
        "当前硬性约束（每行一条）",
        value="\n".join(memory.get("active_constraints", [])),
        height=100
    )
    constraint_items = [line.strip() for line in new_constraints.split("\n") if line.strip()]
    if constraint_items != memory.get("active_constraints", []):
        new_memory["active_constraints"] = constraint_items
        changed = True

    col1, col2 = st.columns(2)
    if col1.button("保存设定"):
        save_memory(project_name, new_memory)
        st.success("已保存")
        st.rerun()

    if col2.button("精简核心设定"):
        with st.spinner("正在压缩旧设定..."):
            result = compact_memory(project_name)
        if result.get("status") == "accepted":
            st.success("核心设定已精简")
            st.rerun()
        else:
            st.error(f"精简失败：{result.get('reason', 'unknown')}")

    with st.expander("原始结构化数据（高级编辑）", expanded=False):
        raw_json = st.text_area(
            "memory.json",
            value=json.dumps(new_memory, ensure_ascii=False, indent=2),
            height=400
        )
        if st.button("从结构化数据保存"):
            try:
                parsed = json.loads(raw_json)
                save_memory(project_name, parsed)
                st.success("已保存")
                st.rerun()
            except json.JSONDecodeError as exc:
                st.error(f"结构化数据格式错误：{exc}")


def render_outline_page(project_name: str):
    st.subheader("全书大纲")

    existing_outline = load_outline(project_name)
    step_result = st.session_state.get("outline_step", {})
    user_idea = st.text_area("你的小说想法", height=200)

    messages_key = _discussion_messages_key("outline")
    result_key = _discussion_result_key("outline")
    input_key = _discussion_input_key("outline")
    clear_input_flag_key = _discussion_input_clear_flag_key("outline")
    _consume_discussion_input_clear("outline")
    discussion_step = st.session_state.get(result_key, {})
    approved_artifact = load_outline_discussion_artifact(project_name)

    col_action_1, col_action_2 = st.columns(2)
    if col_action_1.button("开始讨论大纲方向"):
        try:
            result = discuss_outline(project_name, user_idea)
            st.session_state[result_key] = result
            st.session_state[messages_key] = []
            assistant_message = result.get("data", {}).get("discussion", {}).get("current_understanding", "") or "我先整理了当前理解、可选方向和待确认问题，我们可以继续往下细化。"
            _append_discussion_message(messages_key, "assistant", assistant_message)
            st.rerun()
        except Exception as exc:
            st.error(f"讨论失败：{exc}")

    if col_action_2.button("重置讨论"):
        st.session_state[result_key] = {}
        st.session_state[messages_key] = []
        st.session_state[clear_input_flag_key] = True
        st.rerun()

    summary_col, chat_col = st.columns([1, 1])
    with summary_col:
        st.markdown("### 当前讨论结论")
        _render_discussion_summary(discussion_step, "开始讨论后，这里会持续显示当前收敛出的结论。")
        approve_col, clear_col = st.columns(2)
        if approve_col.button("批准当前讨论", key="approve_outline_discussion"):
            try:
                result = approve_outline_discussion(project_name, discussion_step)
                st.success(f"已保存全书讨论工件：{result.get('saved_path', '')}")
                st.rerun()
            except Exception as exc:
                st.error(f"批准失败：{exc}")
        if clear_col.button("清除已批准版本", key="clear_outline_discussion"):
            if clear_outline_discussion_approval(project_name):
                st.success("已清除全书已批准讨论工件。")
                st.rerun()
            else:
                st.warning("当前没有可清除的已批准讨论工件。")
        st.markdown("### 已批准讨论版本")
        _render_approved_discussion_artifact(approved_artifact, "当前全书还没有已批准讨论工件。")

    with chat_col:
        st.markdown("### 讨论对话")
        messages = st.session_state.get(messages_key, [])
        _render_discussion_chat(messages)
        follow_up = st.text_area("继续讨论", key=input_key, height=120, placeholder="例如：我更想突出成长线，但不要太早进入主线冲突。")
        if st.button("发送讨论消息", key="send_outline_discussion"):
            if not follow_up.strip():
                st.warning("讨论消息不能为空。")
            elif not user_idea.strip():
                st.warning("请先填写你的小说想法。")
            else:
                try:
                    _append_discussion_message(messages_key, "user", follow_up)
                    messages = st.session_state.get(messages_key, [])
                    result = discuss_outline_turn(
                        project_name,
                        user_idea,
                        messages,
                        discussion_step.get("data", {}).get("discussion", {}),
                        follow_up,
                    )
                    st.session_state[result_key] = result
                    assistant_message = result.get("data", {}).get("assistant_message", "") or "我已经根据你的补充更新了当前讨论结论。"
                    _append_discussion_message(messages_key, "assistant", assistant_message)
                    st.session_state[clear_input_flag_key] = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"继续讨论失败：{exc}")

    if st.button("生成全书大纲"):
        result = generate_outline(project_name, user_idea)
        st.session_state["outline_step"] = result
        st.session_state["outline"] = result.get("data", {}).get("outline", "")

    outline_text = st.text_area(
        "大纲内容",
        value=st.session_state.get("outline", existing_outline),
        height=500
    )

    if st.button("保存大纲"):
        save_outline(project_name, outline_text)
        st.success("大纲已保存")

    render_step_validation(step_result)
    render_step_retrieval(step_result, "本次大纲生成使用的检索上下文", get_retrieval_trace(f"outline:{project_name}"))


def render_chapter_outline_page(project_name: str):
    st.subheader("章节细纲")

    chapter_no = st.number_input("章节编号", min_value=1, value=1)
    existing_outline = load_chapter_outline(project_name, chapter_no)
    outline_metadata = load_chapter_outline_metadata(project_name, chapter_no)
    volumes = list_volumes(project_name)
    volume_options = [0] + [int(item.get("volume_no", 0)) for item in volumes]
    default_volume = int(outline_metadata.get("volume_no") or 0)
    volume_no = st.selectbox(
        "所属分卷",
        options=volume_options,
        index=volume_options.index(default_volume) if default_volume in volume_options else 0,
        format_func=lambda value: "未指定分卷" if value == 0 else f"第 {value} 卷",
        key=f"chapter_outline_volume_{chapter_no}",
    )
    if volume_no:
        volume_meta = load_volume_metadata(project_name, volume_no)
        volume_discussion_artifact = load_volume_discussion_artifact(project_name, volume_no)
        st.caption(f"当前分卷：第 {volume_no} 卷 / {volume_meta.get('title', '') or '未命名分卷'}")
    else:
        volume_meta = {}
        volume_discussion_artifact = {}
    arcs = list_arcs(project_name, volume_no=volume_no or None)
    arc_options = [0] + [int(item.get("arc_no", 0)) for item in arcs]
    default_arc = int(outline_metadata.get("arc_no") or 0)
    arc_no = st.selectbox(
        "所属剧情段",
        options=arc_options,
        index=arc_options.index(default_arc) if default_arc in arc_options else 0,
        format_func=lambda value: "未指定剧情段" if value == 0 else f"剧情段 {value:03d}",
        key=f"chapter_outline_arc_{chapter_no}",
    )
    if arc_no:
        arc_meta = load_arc_metadata(project_name, arc_no)
        arc_discussion_artifact = load_arc_discussion_artifact(project_name, arc_no)
        st.caption(f"当前剧情段：剧情段 {arc_no:03d} / {arc_meta.get('title', '') or '未命名剧情段'}")
    else:
        arc_meta = {}
        arc_discussion_artifact = {}

    hierarchy_parts = ["全书大纲"]
    if volume_no:
        hierarchy_parts.append(f"第 {volume_no} 卷")
    if arc_no:
        hierarchy_parts.append(f"剧情段 {arc_no:03d}")
    hierarchy_parts.append(f"第 {chapter_no} 章")
    st.info(" -> ".join(hierarchy_parts))

    if volume_meta.get("summary"):
        with st.expander("当前分卷摘要", expanded=False):
            st.markdown(volume_meta.get("summary", ""))
    if arc_meta.get("summary"):
        with st.expander("当前剧情段摘要", expanded=False):
            st.markdown(arc_meta.get("summary", ""))
    approval_required = st.checkbox(
        "要求已批准的章节/卷/剧情段讨论后再生成章节细纲",
        value=False,
        key=f"chapter_outline_require_approval_{chapter_no}",
    )
    with st.expander("当前使用的已批准规划工件", expanded=False):
        st.markdown("### 章节已批准讨论")
        _render_approved_discussion_artifact(load_chapter_discussion_artifact(project_name, chapter_no), "当前章节没有已批准讨论工件。")
        st.markdown("### 分卷已批准讨论")
        _render_approved_discussion_artifact(volume_discussion_artifact, "当前分卷没有已批准讨论工件。")
        st.markdown("### 剧情段已批准讨论")
        _render_approved_discussion_artifact(arc_discussion_artifact, "当前剧情段没有已批准讨论工件。")
    step_result = st.session_state.get(f"chapter_outline_step_{chapter_no}", {})
    requirement = st.text_area("本章要求", height=200)

    suffix = str(chapter_no)
    messages_key = _discussion_messages_key("chapter", suffix)
    result_key = _discussion_result_key("chapter", suffix)
    input_key = _discussion_input_key("chapter", suffix)
    clear_input_flag_key = _discussion_input_clear_flag_key("chapter", suffix)
    _consume_discussion_input_clear("chapter", suffix)
    discussion_step = st.session_state.get(result_key, {})
    chapter_discussion_artifact = load_chapter_discussion_artifact(project_name, chapter_no)

    col_action_1, col_action_2 = st.columns(2)
    if col_action_1.button("开始讨论本章方向"):
        try:
            save_chapter_outline_metadata(project_name, chapter_no, {"volume_no": volume_no or None, "arc_no": arc_no or None})
            result = discuss_chapter(project_name, chapter_no, requirement)
            st.session_state[result_key] = result
            st.session_state[messages_key] = []
            assistant_message = result.get("data", {}).get("discussion", {}).get("current_understanding", "") or "我先整理了本章目标、可选方向和待确认问题，我们可以继续细化。"
            _append_discussion_message(messages_key, "assistant", assistant_message)
            st.rerun()
        except Exception as exc:
            st.error(f"讨论失败：{exc}")

    if col_action_2.button("重置本章讨论"):
        st.session_state[result_key] = {}
        st.session_state[messages_key] = []
        st.session_state[clear_input_flag_key] = True
        st.rerun()

    summary_col, chat_col = st.columns([1, 1])
    with summary_col:
        st.markdown("### 当前讨论结论")
        _render_discussion_summary(discussion_step, "开始讨论后，这里会持续显示本章方向的当前结论。")
        approve_col, clear_col = st.columns(2)
        if approve_col.button("批准当前章节讨论", key=f"approve_chapter_discussion_{chapter_no}"):
            try:
                result = approve_chapter_discussion(project_name, chapter_no, discussion_step)
                st.success(f"已保存章节讨论工件：{result.get('saved_path', '')}")
                st.rerun()
            except Exception as exc:
                st.error(f"批准失败：{exc}")
        if clear_col.button("清除已批准章节讨论", key=f"clear_chapter_discussion_{chapter_no}"):
            if clear_chapter_discussion_approval(project_name, chapter_no):
                st.success("已清除章节已批准讨论工件。")
                st.rerun()
            else:
                st.warning("当前没有可清除的已批准章节讨论工件。")
        st.markdown("### 已批准章节讨论")
        _render_approved_discussion_artifact(chapter_discussion_artifact, "当前章节还没有已批准讨论工件。")

    with chat_col:
        st.markdown("### 讨论对话")
        messages = st.session_state.get(messages_key, [])
        _render_discussion_chat(messages)
        follow_up = st.text_area(
            "继续讨论本章",
            key=input_key,
            height=120,
            placeholder="例如：我希望这章更偏日常拉扯，不要太快进入正面冲突。"
        )
        if st.button("发送本章讨论消息", key=f"send_chapter_discussion_{chapter_no}"):
            if not follow_up.strip():
                st.warning("讨论消息不能为空。")
            elif not requirement.strip():
                st.warning("请先填写本章要求。")
            else:
                try:
                    save_chapter_outline_metadata(project_name, chapter_no, {"volume_no": volume_no or None, "arc_no": arc_no or None})
                    _append_discussion_message(messages_key, "user", follow_up)
                    messages = st.session_state.get(messages_key, [])
                    result = discuss_chapter_turn(
                        project_name,
                        chapter_no,
                        requirement,
                        messages,
                        discussion_step.get("data", {}).get("discussion", {}),
                        follow_up,
                    )
                    st.session_state[result_key] = result
                    assistant_message = result.get("data", {}).get("assistant_message", "") or "我已经根据你的补充更新了本章讨论结论。"
                    _append_discussion_message(messages_key, "assistant", assistant_message)
                    st.session_state[clear_input_flag_key] = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"继续讨论失败：{exc}")

    if st.button("生成章节细纲"):
        if approval_required:
            if volume_no and not (volume_discussion_artifact.get("discussion", {}) or {}).get("approval_ready"):
                st.error("当前分卷还没有已批准讨论工件，已阻止章节细纲生成。")
            elif arc_no and not (arc_discussion_artifact.get("discussion", {}) or {}).get("approval_ready"):
                st.error("当前剧情段还没有已批准讨论工件，已阻止章节细纲生成。")
            elif not (chapter_discussion_artifact.get("discussion", {}) or {}).get("approval_ready"):
                st.error("当前章节还没有已批准讨论工件，已阻止章节细纲生成。")
            else:
                result = generate_chapter_outline(project_name, chapter_no, requirement, volume_no=volume_no or None, arc_no=arc_no or None)
                st.session_state[f"chapter_outline_step_{chapter_no}"] = result
                st.session_state[f"chapter_outline_{chapter_no}"] = result.get("data", {}).get("chapter_outline", "")
        else:
            result = generate_chapter_outline(project_name, chapter_no, requirement, volume_no=volume_no or None, arc_no=arc_no or None)
            st.session_state[f"chapter_outline_step_{chapter_no}"] = result
            st.session_state[f"chapter_outline_{chapter_no}"] = result.get("data", {}).get("chapter_outline", "")

    outline_text = st.text_area(
        "章节细纲内容",
        value=st.session_state.get(f"chapter_outline_{chapter_no}", existing_outline),
        height=500
    )

    if st.button("保存章节细纲"):
        save_chapter_outline(project_name, chapter_no, outline_text)
        save_chapter_outline_metadata(project_name, chapter_no, {"volume_no": volume_no or None, "arc_no": arc_no or None})
        st.success(f"第 {chapter_no} 章细纲已保存")

    render_step_validation(step_result)
    render_step_retrieval(
        step_result,
        "本次细纲生成使用的检索上下文",
        get_retrieval_trace(f"chapter_outline:{project_name}:{chapter_no}")
    )


def render_chapter_page(project_name: str):
    st.subheader("章节正文")

    chapter_no = st.number_input("章节编号", min_value=1, value=1)
    existing_outline = load_chapter_outline(project_name, chapter_no)
    existing_chapter = load_chapter(project_name, chapter_no)
    chapter_step = st.session_state.get(f"chapter_step_{chapter_no}", {})

    chapter_outline = st.text_area(
        "章节细纲",
        value=existing_outline,
        height=250
    )

    tone = st.selectbox(
        "文风/基调",
        options=["", "克制", "热血", "轻快", "压抑", "爽文推进"],
        format_func=lambda value: value or "未特别指定",
        key=f"write_tone_{chapter_no}",
    )
    pacing = st.selectbox(
        "节奏",
        options=["", "慢铺", "均衡", "快推"],
        format_func=lambda value: value or "未特别指定",
        key=f"write_pacing_{chapter_no}",
    )
    dialogue_density = st.selectbox(
        "对话密度",
        options=["", "低", "中", "高"],
        format_func=lambda value: value or "未特别指定",
        key=f"write_dialogue_density_{chapter_no}",
    )
    focus = st.multiselect(
        "描写重点",
        options=["动作", "心理", "环境", "关系拉扯", "战斗", "信息揭示"],
        key=f"write_focus_{chapter_no}",
    )
    ending_strength = st.selectbox(
        "结尾力度",
        options=["", "轻钩子", "强钩子", "悬念断点"],
        format_func=lambda value: value or "未特别指定",
        key=f"write_ending_strength_{chapter_no}",
    )
    extra_requirements = st.text_area(
        "写作补充要求",
        height=120,
        key=f"write_extra_requirements_{chapter_no}",
        placeholder="例如：减少说明性段落，多写试探性对话，结尾用短句收束。",
    )

    writing_guidance = {
        "tone": tone,
        "pacing": pacing,
        "dialogue_density": dialogue_density,
        "focus": focus,
        "ending_strength": ending_strength,
        "extra_requirements": extra_requirements,
    }

    word_count = st.text_input(
        "目标字数（如 2000-2500）",
        value="2000-2500"
    )

    if st.button("写正文"):
        result = write_chapter(project_name, chapter_no, chapter_outline, writing_guidance, word_count)
        st.session_state[f"chapter_step_{chapter_no}"] = result
        st.session_state[f"chapter_{chapter_no}"] = result.get("data", {}).get("chapter", "")

    with st.expander("当前写作指导", expanded=False):
        render_step_json_expander("写作指导参数", writing_guidance)

    chapter_text = st.text_area(
        "章节正文",
        value=st.session_state.get(f"chapter_{chapter_no}", existing_chapter),
        height=600
    )

    if st.button("保存正文"):
        save_chapter(project_name, chapter_no, chapter_text)
        st.success(f"第 {chapter_no} 章正文已保存")

    if st.button("根据正文更新核心设定"):
        result = update_memory_from_chapter(project_name, chapter_no, chapter_text)
        st.session_state[f"memory_update_step_{chapter_no}"] = result
        render_step_status_message(result, "核心设定更新成功", "核心设定更新失败：")
        render_step_validation(result)
        render_step_json_expander("设定更新结构化数据", result)

    render_step_validation(chapter_step)
    render_step_retrieval(
        chapter_step,
        "本次正文生成使用的检索上下文",
        get_retrieval_trace(f"write:{project_name}:{chapter_no}")
    )
    render_step_retrieval(
        st.session_state.get(f"memory_update_step_{chapter_no}", {}),
        "本次设定更新使用的检索上下文",
        get_retrieval_trace(f"memory_update:{project_name}:{chapter_no}")
    )


def render_review_page(project_name: str):
    st.subheader("章节审阅")

    chapter_no = st.number_input("章节编号", min_value=1, value=1, key="review_chapter_no")
    existing_chapter = load_chapter(project_name, chapter_no)
    review_text_key = f"review_result_text_{chapter_no}"
    chapter_text_key = f"review_chapter_text_{chapter_no}"

    existing_review = load_review(project_name, chapter_no)
    existing_review_json = load_review_json(project_name, chapter_no) or {}
    review_step = st.session_state.get(f"review_step_{chapter_no}", {})

    chapter_text = st.text_area(
        "待审阅正文",
        value=existing_chapter,
        height=450,
        key=chapter_text_key
    )

    if st.button("生成审阅意见"):
        try:
            review_result = review_chapter(project_name, chapter_no, chapter_text)
            review_markdown = review_result.get("data", {}).get("review_markdown", "")
            st.session_state[f"review_{chapter_no}"] = review_markdown
            st.session_state[review_text_key] = review_markdown
            st.session_state[f"review_step_{chapter_no}"] = review_result
            st.rerun()
        except Exception as exc:
            st.error(f"生成审阅失败：{exc}")

    review_text = st.text_area(
        "审阅结果",
        value=st.session_state.get(f"review_{chapter_no}", existing_review),
        height=450,
        key=review_text_key
    )

    if review_text:
        st.markdown(review_text)

    latest_review_json = load_review_json(project_name, chapter_no) or existing_review_json

    if latest_review_json:
        st.caption("结构化审阅状态")
        cols = st.columns(3)
        cols[0].metric("状态", label_status(latest_review_json.get("status", "-")))
        cols[1].metric("问题数", len(latest_review_json.get("issues", [])))
        cols[2].metric("优点数", len(latest_review_json.get("strengths", [])))

    render_step_validation(review_step)
    render_step_retrieval(
        review_step,
        "本次审阅使用的检索上下文",
        get_retrieval_trace(f"review:{project_name}:{chapter_no}")
    )


def render_project_overview_page(project_name: str):
    st.subheader("项目总览")
    summary = get_project_summary(project_name)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("正文章节", summary.get("chapter_count", 0))
    col2.metric("细纲章节", summary.get("chapter_outline_count", 0))
    col3.metric("审阅数量", summary.get("review_count", 0))
    col4.metric("分析报告", summary.get("analysis_count", 0))
    col5.metric("评估报告", summary.get("evaluation_count", 0))

    col6, col7, col8, col9, col12, col13, col14 = st.columns(7)
    col6.metric("分卷数量", summary.get("volume_count", 0))
    col7.metric("剧情段数量", summary.get("arc_count", 0))
    col8.metric("流水线记录", summary.get("run_count", 0))
    col9.metric("外部资料", summary.get("retrieval_source_count", 0))
    col12.metric("结构化知识", summary.get("knowledge_item_count", 0))
    col13.metric("待确认知识", summary.get("pending_knowledge_count", 0))
    col14.metric("资料批次", summary.get("long_reference_batch_count", 0))

    col10, col11 = st.columns(2)
    col10.metric("已批准分卷讨论", summary.get("approved_volume_count", 0))
    col11.metric("已批准剧情段讨论", summary.get("approved_arc_count", 0))

    st.caption(f"章节摘要={summary.get('chapter_summary_count', 0)} / 资源文件数={summary.get('resource_file_count', 0)}")

    st.caption(
        f"书名={summary.get('title', project_name)} / 类型={summary.get('genre', '-') or '-'} / 原作对齐={summary.get('canon_mode', '-') or '-'} / 更新时间={summary.get('updated_at', '-') or '-'}"
    )

    with st.expander("项目设置", expanded=False):
        new_name = st.text_input("重命名项目", value=project_name, key=f"rename_project_input_{project_name}")
        if st.button("保存新项目名"):
            try:
                renamed = rename_project(project_name, new_name)
                st.session_state["project_name"] = renamed
                st.success(f"项目已重命名为 `{renamed}`。")
                st.rerun()
            except Exception as exc:
                st.error(f"项目重命名失败：{exc}")

    with st.expander("危险操作", expanded=False):
        st.warning("删除项目会移除该项目下的全部设定、章节、审阅、分析、检索资料和运行记录。")
        confirm_value = st.text_input("输入项目名以确认删除", key=f"delete_project_confirm_{project_name}")
        if st.button("删除当前项目", type="primary"):
            if confirm_value.strip() != project_name:
                st.error("项目名确认不匹配，已取消删除。")
            else:
                deleted = delete_project(project_name)
                if deleted:
                    st.session_state.pop("project_name", None)
                    st.success(f"项目 `{project_name}` 已删除。")
                    st.rerun()
                else:
                    st.error("项目删除失败，目标项目可能不存在。")


def render_creative_profile_page(project_name: str):
    st.subheader("创作配置")
    st.caption("配置本项目的任务性质、目标篇幅、生成层级和资料参考强度。预设只是快捷入口，每一项都可以自定义。")

    render_creative_task_wizard(project_name)
    st.divider()

    profile = load_creative_profile(project_name)
    story_modes = ["主线故事", "番外", "续写", "前传", "穿越", "平行世界", "原作补完", "单场景片段", "设定补写"]
    target_lengths = ["片段", "短篇", "中篇", "长篇"]
    workflow_depths = ["只生成正文", "短篇结构+正文", "章节计划+正文", "分卷/剧情段/章节", "完整长篇流程"]
    reference_strengths = ["轻参考", "中参考", "强参考", "严格原作", "主要参考文风"]
    focus_options = ["角色", "世界观", "剧情事件", "道具能力", "时间线", "写作风格", "对白风格", "写作手法", "硬性约束"]
    conflict_policies = ["优先项目设定", "优先原作资料", "人工确认", "保留多版本"]

    with st.form("creative_profile_form"):
        col_a, col_b = st.columns(2)
        story_mode = select_with_custom(
            col_a,
            "任务性质",
            story_modes,
            profile.get("story_mode", "主线故事"),
            "creative_story_mode",
            "例如：半 AU 续写、原角色现代都市篇、只补某角色死亡前一晚。",
        )
        target_length = select_with_custom(
            col_b,
            "目标篇幅",
            target_lengths,
            profile.get("target_length", "长篇"),
            "creative_target_length",
            "例如：1.5 万字中短篇、五个小节、三幕式短篇。",
        )
        target_word_count = col_a.text_input("目标字数（可选）", value=profile.get("target_word_count", ""), placeholder="例如：8000、2万、20万")
        workflow_depth = select_with_custom(
            col_b,
            "生成层级",
            workflow_depths,
            profile.get("workflow_depth", "完整长篇流程"),
            "creative_workflow_depth",
            "例如：先三幕式结构，再分 5 个小节写正文。",
        )
        reference_strength = select_with_custom(
            col_a,
            "资料参考强度",
            reference_strengths,
            profile.get("reference_strength", "中参考"),
            "creative_reference_strength",
            "例如：强参考角色语气，弱参考世界观；只借人物关系。",
        )
        conflict_policy = select_with_custom(
            col_b,
            "资料冲突处理",
            conflict_policies,
            profile.get("conflict_policy", "优先项目设定"),
            "creative_conflict_policy",
            "例如：原作性格优先，但世界观以本项目为准。",
        )
        existing_focus = profile.get("reference_focus", []) if isinstance(profile.get("reference_focus", []), list) else []
        preset_focus = [item for item in existing_focus if item in focus_options]
        custom_focus = [item for item in existing_focus if item not in focus_options]
        reference_focus = st.multiselect(
            "重点参考方向",
            options=focus_options,
            default=preset_focus or ["角色", "世界观", "剧情事件"],
        )
        custom_reference_focus = st.text_input(
            "自定义参考方向（用逗号分隔，可选）",
            value="，".join(custom_focus),
            placeholder="例如：人物关系、能力代价、心理活动、转场方式、口癖",
        )
        allow_canon_deviation = st.checkbox("允许根据需求改写原设", value=bool(profile.get("allow_canon_deviation", True)))
        notes = st.text_area(
            "自由说明",
            value=profile.get("notes", ""),
            height=140,
            placeholder="这里可以写任何复杂规则。例如：这次是半 AU 续写，只保留角色关系和说话风格，不保留原作结局；世界观改成现代都市，但能力体系保留原作限制。",
        )
        submitted = st.form_submit_button("保存创作配置")

    if submitted:
        custom_focus_items = [
            item.strip()
            for item in custom_reference_focus.replace("，", ",").split(",")
            if item.strip()
        ]
        merged_reference_focus = []
        seen_focus = set()
        for item in reference_focus + custom_focus_items:
            if item in seen_focus:
                continue
            seen_focus.add(item)
            merged_reference_focus.append(item)
        saved = save_creative_profile(project_name, {
            "story_mode": story_mode,
            "target_length": target_length,
            "target_word_count": target_word_count,
            "workflow_depth": workflow_depth,
            "reference_strength": reference_strength,
            "reference_focus": merged_reference_focus,
            "allow_canon_deviation": allow_canon_deviation,
            "conflict_policy": conflict_policy,
            "notes": notes,
        })
        st.success("创作配置已保存。")
        profile = saved

    st.markdown("### 推荐生成路径")
    workflow = recommended_workflow_for_profile(profile)
    st.markdown(" -> ".join(workflow))

    st.markdown("### 参考策略说明")
    strength = profile.get("reference_strength", "中参考")
    strategy_text = {
        "轻参考": "只保留角色核心气质和少量关键设定，适合穿越、平行世界、新环境故事。",
        "中参考": "保留主要人物关系、能力规则和世界观基调，同时允许新剧情展开。",
        "强参考": "强调角色性格、时间线、能力规则和世界观一致性，适合续写和补完。",
        "严格原作": "冲突时优先原作资料，生成前应做一致性检查。",
        "主要参考文风": "弱化剧情设定绑定，重点参考句式、节奏、对白和叙事手法。",
    }.get(strength, "按当前配置综合参考资料。")
    st.info(strategy_text)
    render_step_json_expander("创作配置结构化数据", profile)


def render_dynamic_generation_page(project_name: str):
    st.subheader("动态生成")
    st.caption("根据创作配置自动选择生成层级。适合短篇、番外、续写、前传、穿越、新环境故事或临时片段。")

    profile = load_creative_profile(project_name)
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("任务性质", profile.get("story_mode", "主线故事"))
    col_b.metric("目标篇幅", profile.get("target_length", "长篇"))
    col_c.metric("参考强度", profile.get("reference_strength", "中参考"))
    st.caption(f"推荐路径：{' -> '.join(recommended_workflow_for_profile(profile))}")

    chapter_no = st.number_input("保存到章节编号", min_value=1, value=1, key="dynamic_generation_chapter_no")
    workflow_depth_options = ["按创作配置", "只生成正文", "短篇结构+正文", "章节计划+正文", "分卷/剧情段/章节", "完整长篇流程"]
    workflow_depth = select_with_custom(
        st,
        "本次生成层级",
        workflow_depth_options,
        "按创作配置",
        "dynamic_generation_workflow_depth",
        "可临时写自己的执行方式，例如：先三幕结构，再写 5 个小节正文。",
    )
    default_word_count = profile.get("target_word_count", "") or "2000-2500"
    word_count = st.text_input("本次目标字数", value=default_word_count, key="dynamic_generation_word_count")
    requirement = st.text_area("本次创作需求", height=220, key="dynamic_generation_requirement")

    if st.button("按配置执行动态生成"):
        if not requirement.strip():
            st.error("请先填写本次创作需求。")
        else:
            try:
                with st.spinner("正在按创作配置生成..."):
                    result = run_dynamic_generation_task(
                        project_name,
                        int(chapter_no),
                        requirement,
                        word_count,
                        workflow_depth,
                    )
                st.session_state["dynamic_generation_result"] = result
                st.rerun()
            except Exception as exc:
                st.error(f"动态生成失败：{exc}")

    result = st.session_state.get("dynamic_generation_result", {})
    if not result:
        return

    if result.get("success"):
        st.success("动态生成完成。")
    else:
        st.error(f"动态生成未完成：{result.get('status', '未知状态')}")

    for warning in result.get("warnings", []):
        st.warning(warning)

    steps = result.get("steps", {}) or {}
    if steps:
        st.markdown("### 执行步骤")
        for step_name, step_result in steps.items():
            status_text = label_status(step_result.get("status", "-"))
            st.caption(f"{label_step_name(step_name)}：{status_text}")
            render_step_validation(step_result)
            render_step_retrieval(step_result, f"{label_step_name(step_name)}使用的检索上下文")

    creative_structure = result.get("creative_structure", "")
    if creative_structure:
        with st.expander("创作结构 / 章节计划", expanded=True):
            st.markdown(creative_structure)

    chapter = result.get("chapter", "")
    if chapter:
        with st.expander("生成正文", expanded=True):
            st.markdown(chapter)

    render_step_json_expander("动态生成结构化数据", result)


def build_profile_from_task_wizard(
    task_type: str,
    target_length: str,
    output_goal: str,
    reference_strength: str,
    target_word_count: str,
    focus_items: list[str],
    allow_canon_deviation: bool,
    conflict_policy: str,
    notes: str,
) -> dict:
    workflow_depth = "按创作配置"
    if output_goal == "只要正文":
        workflow_depth = "只生成正文"
    elif output_goal == "短篇结构和正文":
        workflow_depth = "短篇结构+正文"
    elif output_goal == "章节计划和正文":
        workflow_depth = "章节计划+正文"
    elif output_goal == "分卷/剧情段/章节计划":
        workflow_depth = "分卷/剧情段/章节"
    elif output_goal == "完整长篇流程":
        workflow_depth = "完整长篇流程"
    elif target_length in {"片段", "短篇"}:
        workflow_depth = "短篇结构+正文"
    elif target_length == "中篇":
        workflow_depth = "章节计划+正文"
    else:
        workflow_depth = "完整长篇流程"

    return {
        "story_mode": task_type,
        "target_length": target_length,
        "target_word_count": target_word_count,
        "workflow_depth": workflow_depth,
        "reference_strength": reference_strength,
        "reference_focus": focus_items,
        "allow_canon_deviation": allow_canon_deviation,
        "conflict_policy": conflict_policy,
        "notes": notes,
    }


def render_creative_task_wizard(project_name: str):
    st.markdown("### 创作任务向导")
    st.caption("用中文目标快速生成一份创作配置。保存后，“动态生成”和各类生成提示会按这份配置调整。")

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
    notes = st.text_area(
        "补充说明",
        height=120,
        key="task_wizard_notes",
        placeholder="例如：穿越到新环境，只保留角色性格和说话方式；能力体系保留原作限制，但剧情完全重写。",
    )

    preview_profile = build_profile_from_task_wizard(
        task_type,
        target_length,
        output_goal,
        reference_strength,
        target_word_count,
        focus_items,
        allow_canon_deviation,
        conflict_policy,
        notes,
    )
    st.caption(f"推荐路径：{' -> '.join(recommended_workflow_for_profile(preview_profile))}")
    render_step_json_expander("向导生成的配置预览", preview_profile)

    if st.button("保存向导配置"):
        saved = save_creative_profile(project_name, preview_profile)
        st.success("已根据向导保存创作配置。")
        st.session_state["task_wizard_last_profile"] = saved
        st.rerun()


def render_pending_knowledge_queue(project_name: str):
    pending_items = load_pending_knowledge_items(project_name)
    pending_count = len(pending_items)
    with st.expander(f"待确认结构化知识（{pending_count}）", expanded=bool(pending_count)):
        st.caption("提取结果先进入这里。确认后才写入结构化知识并重建检索索引；不合适的条目可以丢弃。")
        if not pending_items:
            st.caption("当前没有待确认的知识条目。")
            return

        option_indices = list(range(pending_count))
        selected_indices = st.multiselect(
            "选择要处理的条目",
            options=option_indices,
            default=option_indices[: min(10, pending_count)],
            format_func=lambda index: (
                f"{index + 1}. {label_knowledge_category(pending_items[index].get('category', ''))}"
                f" / {pending_items[index].get('name', '未命名')}"
                f" / {label_scope(pending_items[index].get('scope', 'reference'))}"
            ),
            key="pending_knowledge_selected_indices",
        )

        for index, item in enumerate(pending_items[:30], start=1):
            st.markdown(f"#### {index}. {label_knowledge_category(item.get('category', ''))} / {item.get('name', '未命名')}")
            st.caption(
                f"范围={label_scope(item.get('scope', 'reference'))} / 可信度={label_authority(item.get('authority', 'curated'))} / 来源={item.get('source_title', '-') or '-'}"
            )
            if item.get("summary"):
                st.write(item.get("summary"))
            if item.get("tags"):
                st.caption(f"标签：{', '.join(item.get('tags', []))}")
        if len(pending_items) > 30:
            st.caption(f"仅预览前 30 条，共 {pending_count} 条。")

        selected_ids = [
            str(pending_items[index].get("pending_id", ""))
            for index in selected_indices
            if 0 <= index < pending_count and pending_items[index].get("pending_id")
        ]
        col_a, col_b = st.columns(2)
        if col_a.button("确认所选并写入结构化知识"):
            if not selected_ids:
                st.error("请先选择条目。")
            else:
                saved_count = confirm_pending_knowledge_items(project_name, selected_ids)
                if saved_count:
                    rebuild_retrieval_assets(project_name, build_vectors=True)
                st.success(f"已确认 {saved_count} 条结构化知识。")
                st.rerun()
        if col_b.button("丢弃所选待确认条目"):
            if not selected_ids:
                st.error("请先选择条目。")
            else:
                removed_count = discard_pending_knowledge_items(project_name, selected_ids)
                st.success(f"已丢弃 {removed_count} 条待确认知识。")
                st.rerun()

        with st.expander("高级编辑：待确认队列原始数据", expanded=False):
            pending_json = st.text_area(
                "pending.json",
                value=json.dumps(pending_items, ensure_ascii=False, indent=2),
                height=360,
                key="pending_knowledge_raw_json",
            )
            if st.button("保存待确认队列修改"):
                try:
                    parsed = json.loads(pending_json)
                    if not isinstance(parsed, list):
                        st.error("待确认队列必须是列表结构。")
                    else:
                        save_pending_knowledge_items(project_name, parsed)
                        st.success("待确认队列已保存。")
                        st.rerun()
                except json.JSONDecodeError as exc:
                    st.error(f"结构化数据格式错误：{exc}")


def normalize_knowledge_match_name(value: str) -> str:
    cleaned = str(value or "").lower()
    cleaned = re.sub(r"[\s　·・,，。.!！?？:：;；'\"“”‘’《》〈〉（）()\[\]【】_\-—]+", "", cleaned)
    return cleaned.strip()


def find_duplicate_knowledge_groups(items: list[dict]) -> list[list[int]]:
    groups: dict[str, list[int]] = {}
    for index, item in enumerate(items):
        key = normalize_knowledge_match_name(item.get("name", ""))
        if not key:
            continue
        groups.setdefault(key, []).append(index)
    return [indices for indices in groups.values() if len(indices) > 1]


def merge_text_values(values: list[str], separator: str = "\n\n") -> str:
    merged = []
    seen = set()
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        merged.append(cleaned)
    return separator.join(merged)


def merge_list_values(values: list) -> list:
    merged = []
    seen = set()
    for value in values:
        if isinstance(value, list):
            candidates = value
        else:
            candidates = [value]
        for candidate in candidates:
            marker = json.dumps(candidate, ensure_ascii=False, sort_keys=True) if isinstance(candidate, dict) else str(candidate)
            if not marker.strip() or marker in seen:
                continue
            seen.add(marker)
            merged.append(candidate)
    return merged


def merge_details_values(items: list[dict]) -> dict:
    merged: dict[str, str] = {}
    for item in items:
        details = item.get("details", {})
        if not isinstance(details, dict):
            continue
        for key, value in details.items():
            cleaned_key = str(key).strip()
            cleaned_value = str(value or "").strip()
            if not cleaned_key or not cleaned_value:
                continue
            if cleaned_key in merged:
                merged[cleaned_key] = merge_text_values([merged[cleaned_key], cleaned_value])
            else:
                merged[cleaned_key] = cleaned_value
    return merged


def pick_authority(values: list[str]) -> str:
    priority = {"official": 5, "project": 4, "curated": 3, "community": 2, "unknown": 1}
    cleaned = [str(value or "unknown") for value in values]
    return max(cleaned or ["unknown"], key=lambda value: priority.get(value, 0))


def safe_confidence(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.7
    return max(0.0, min(1.0, number))


def build_merged_knowledge_item(category: str, selected_items: list[dict]) -> dict:
    first = selected_items[0] if selected_items else {}
    merged_name = first.get("name", "")
    summaries = [item.get("summary", "") for item in selected_items]
    source_titles = [item.get("source_title", "") for item in selected_items]
    source_origins = [item.get("source_origin", "") for item in selected_items]
    return {
        "id": first.get("id", ""),
        "category": category,
        "name": merged_name,
        "summary": merge_text_values(summaries),
        "details": merge_details_values(selected_items),
        "evidence": merge_list_values([item.get("evidence", []) for item in selected_items]),
        "confidence": max([safe_confidence(item.get("confidence", 0.7)) for item in selected_items] or [0.7]),
        "tags": merge_list_values([item.get("tags", []) for item in selected_items]),
        "scope": first.get("scope", "reference"),
        "authority": pick_authority([item.get("authority", "unknown") for item in selected_items]),
        "source_title": merge_text_values(source_titles, separator="；"),
        "source_origin": merge_text_values(source_origins, separator="；"),
        "status": "confirmed",
        "merged_from": [item.get("id", "") for item in selected_items if item.get("id")],
    }


def render_knowledge_organizer(project_name: str, knowledge_category_options: list[str]):
    with st.expander("结构化知识整理", expanded=False):
        st.caption("用于处理长篇资料导入后的重复条目。可以按分类查看、合并同名知识，或删除明显错误的条目。")
        category = st.selectbox(
            "知识分类",
            options=knowledge_category_options,
            format_func=label_knowledge_category,
            key="knowledge_organizer_category",
        )
        items = load_knowledge_category(project_name, category)
        if not items:
            st.caption("当前分类还没有结构化知识。")
            return

        duplicate_groups = find_duplicate_knowledge_groups(items)
        st.caption(f"当前分类共有 {len(items)} 条；检测到 {len(duplicate_groups)} 组同名/近似重复。")
        if duplicate_groups:
            for group_index, group in enumerate(duplicate_groups[:8], start=1):
                names = " / ".join(items[index].get("name", "未命名") for index in group)
                st.caption(f"重复组 {group_index}：{names}")
            if len(duplicate_groups) > 8:
                st.caption(f"仅显示前 8 组，共 {len(duplicate_groups)} 组。")

        default_indices = duplicate_groups[0] if duplicate_groups else []
        selected_indices = st.multiselect(
            "选择要合并或删除的条目",
            options=list(range(len(items))),
            default=default_indices,
            format_func=lambda index: f"{index + 1}. {items[index].get('name', '未命名')} / {items[index].get('summary', '')[:50]}",
            key=f"knowledge_organizer_selected_{category}",
        )
        selected_items = [items[index] for index in selected_indices if 0 <= index < len(items)]

        if selected_items:
            for index, item in zip(selected_indices[:10], selected_items[:10]):
                st.markdown(f"#### {index + 1}. {item.get('name', '未命名')}")
                st.caption(
                    f"范围={label_scope(item.get('scope', 'reference'))} / 可信度={label_authority(item.get('authority', 'unknown'))} / 来源={item.get('source_title', '-') or '-'}"
                )
                if item.get("summary"):
                    st.write(item.get("summary"))

        if len(selected_items) >= 2:
            merged_item = build_merged_knowledge_item(category, selected_items)
            raw_merged_json = st.text_area(
                "合并后结构化数据，可在保存前修改",
                value=json.dumps(merged_item, ensure_ascii=False, indent=2),
                height=340,
                key=f"knowledge_organizer_merged_json_{category}",
            )
            if st.button("保存合并结果并移除原条目", key=f"knowledge_organizer_save_merge_{category}"):
                try:
                    parsed = json.loads(raw_merged_json)
                    if not isinstance(parsed, dict):
                        st.error("合并结果必须是对象结构。")
                    else:
                        parsed["category"] = category
                        selected_set = set(selected_indices)
                        remaining = [item for index, item in enumerate(items) if index not in selected_set]
                        remaining.append(parsed)
                        save_knowledge_category(project_name, category, remaining)
                        rebuild_retrieval_assets(project_name, build_vectors=True)
                        st.success(f"已合并 {len(selected_items)} 条结构化知识，并重建检索索引。")
                        st.rerun()
                except json.JSONDecodeError as exc:
                    st.error(f"结构化数据格式错误：{exc}")


def format_knowledge_item_for_report(item: dict) -> list[str]:
    lines = [f"### {item.get('name', '未命名')}"]
    if item.get("summary"):
        lines.extend(["", str(item.get("summary", "")).strip()])
    meta_parts = []
    if item.get("scope"):
        meta_parts.append(f"范围：{label_scope(item.get('scope'))}")
    if item.get("authority"):
        meta_parts.append(f"可信度：{label_authority(item.get('authority'))}")
    if item.get("source_title"):
        meta_parts.append(f"来源：{item.get('source_title')}")
    if meta_parts:
        lines.extend(["", "- " + " / ".join(meta_parts)])
    details = item.get("details", {}) if isinstance(item.get("details"), dict) else {}
    for key, value in list(details.items())[:8]:
        if str(value).strip():
            lines.append(f"- {key}：{value}")
    tags = item.get("tags", []) if isinstance(item.get("tags"), list) else []
    if tags:
        lines.append(f"- 标签：{', '.join(str(tag) for tag in tags[:12])}")
    return lines


def build_source_package_report(project_name: str, max_items_per_category: int = 30) -> str:
    knowledge_base = load_knowledge_base(project_name)
    total_items = sum(len(items) for items in knowledge_base.values())
    lines = [
        f"# {project_name} 资料包报告",
        "",
        "## 总览",
        "",
        f"- 已确认结构化知识：{total_items} 条",
    ]
    for category, items in knowledge_base.items():
        lines.append(f"- {label_knowledge_category(category)}：{len(items)} 条")

    missing_categories = [label_knowledge_category(category) for category, items in knowledge_base.items() if not items]
    if missing_categories:
        lines.extend(["", "## 资料缺口", ""])
        lines.append("以下分类当前没有已确认知识，后续可以补充资料或重新提取：")
        lines.extend([f"- {item}" for item in missing_categories])

    for category, items in knowledge_base.items():
        if not items:
            continue
        lines.extend(["", f"## {label_knowledge_category(category)}", ""])
        shown_items = items[:max_items_per_category]
        for item in shown_items:
            lines.extend(format_knowledge_item_for_report(item))
            lines.append("")
        if len(items) > max_items_per_category:
            lines.append(f"> 当前分类仅列出前 {max_items_per_category} 条，共 {len(items)} 条。")

    constraints = knowledge_base.get("constraints", [])
    style_items = knowledge_base.get("writing_style", []) + knowledge_base.get("dialogue_style", []) + knowledge_base.get("narrative_techniques", [])
    if constraints or style_items:
        lines.extend(["", "## 同人写作注意事项", ""])
        for item in constraints[:20]:
            lines.append(f"- 硬性约束：{item.get('name', '未命名')}。{item.get('summary', '')}")
        for item in style_items[:20]:
            lines.append(f"- 风格参考：{item.get('name', '未命名')}。{item.get('summary', '')}")

    lines.extend([
        "",
        "## 后续整理建议",
        "",
        "- 如果角色、能力或地点存在重复条目，先在“结构化知识整理”中合并。",
        "- 如果关键分类为空，回到“长篇资料批次管理”继续提取对应分类。",
        "- 如果资料来自不同版本或存在冲突，优先在“检索中心”做冲突裁决。",
    ])
    return "\n".join(lines).strip() + "\n"


def render_source_package_report_page(project_name: str):
    with st.expander("资料包报告", expanded=False):
        st.caption("基于已确认结构化知识生成项目资料总览，可保存为分析报告并进入检索索引。")
        knowledge_base = load_knowledge_base(project_name)
        total_items = sum(len(items) for items in knowledge_base.values())
        st.caption(f"当前已确认结构化知识：{total_items} 条")
        max_items = st.slider("每类最多写入条目数", min_value=5, max_value=100, value=30, step=5, key="source_package_max_items")
        if st.button("生成资料包报告"):
            report = build_source_package_report(project_name, max_items_per_category=max_items)
            st.session_state["source_package_report_preview"] = report

        existing_report = load_source_package_report(project_name)
        report_text = st.text_area(
            "资料包报告",
            value=st.session_state.get("source_package_report_preview", existing_report),
            height=520,
            key="source_package_report_text",
        )
        col_save, col_refresh = st.columns(2)
        if col_save.button("保存资料包报告"):
            if not report_text.strip():
                st.error("报告内容不能为空。")
            else:
                save_source_package_report(project_name, report_text)
                rebuild_retrieval_assets(project_name, build_vectors=True)
                st.success("资料包报告已保存，并重建检索索引。")
                st.rerun()
        if col_refresh.button("用当前知识重新生成并覆盖预览"):
            st.session_state["source_package_report_preview"] = build_source_package_report(
                project_name,
                max_items_per_category=max_items,
            )
            st.rerun()

        if selected_items:
            if st.button("删除所选结构化知识", key=f"knowledge_organizer_delete_{category}"):
                selected_set = set(selected_indices)
                remaining = [item for index, item in enumerate(items) if index not in selected_set]
                save_knowledge_category(project_name, category, remaining)
                rebuild_retrieval_assets(project_name, build_vectors=True)
                st.success(f"已删除 {len(selected_items)} 条结构化知识，并重建检索索引。")
                st.rerun()

        with st.expander("高级编辑：当前分类原始数据", expanded=False):
            raw_category_json = st.text_area(
                f"{category}.json",
                value=json.dumps(items, ensure_ascii=False, indent=2),
                height=360,
                key=f"knowledge_organizer_raw_json_{category}",
            )
            if st.button("保存当前分类原始数据", key=f"knowledge_organizer_save_raw_{category}"):
                try:
                    parsed = json.loads(raw_category_json)
                    if not isinstance(parsed, list):
                        st.error("分类数据必须是列表结构。")
                    else:
                        normalized = [item for item in parsed if isinstance(item, dict)]
                        for item in normalized:
                            item["category"] = category
                        save_knowledge_category(project_name, category, normalized)
                        rebuild_retrieval_assets(project_name, build_vectors=True)
                        st.success("当前分类结构化知识已保存，并重建检索索引。")
                        st.rerun()
                except json.JSONDecodeError as exc:
                    st.error(f"结构化数据格式错误：{exc}")


CHAPTER_TITLE_PATTERN = re.compile(
    r"^\s*(?:第\s*[0-9零一二三四五六七八九十百千万两〇]+\s*[章节卷回部篇]|Chapter\s+\d+|CHAPTER\s+\d+|番外|楔子|序章|终章).*$"
)


def decode_uploaded_text(uploaded_file) -> str:
    if uploaded_file is None:
        return ""
    data = uploaded_file.getvalue()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def normalize_text_for_fingerprint(text: str) -> str:
    return re.sub(r"\s+", "\n", str(text or "").strip())


def calculate_text_fingerprint(text: str) -> str:
    normalized = normalize_text_for_fingerprint(text)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def find_matching_long_reference_batches(
    project_name: str,
    *,
    fingerprint: str,
    source_file_name: str,
    char_count: int,
    segment_count: int,
) -> list[dict]:
    matches = []
    for batch in list_long_reference_batches(project_name):
        score = 0
        reasons = []
        if fingerprint and batch.get("content_fingerprint") == fingerprint:
            score += 100
            reasons.append("内容指纹完全一致")
        if source_file_name and batch.get("source_file_name") == source_file_name:
            score += 20
            reasons.append("文件名一致")
        batch_char_count = int(batch.get("content_char_count") or 0)
        if char_count and batch_char_count and abs(batch_char_count - char_count) <= max(20, int(char_count * 0.01)):
            score += 20
            reasons.append("总字数接近")
        batch_segment_count = int(batch.get("summary", {}).get("segment_count") or 0)
        if segment_count and batch_segment_count == segment_count:
            score += 10
            reasons.append("切分片段数一致")
        if score >= 40:
            item = dict(batch)
            item["match_score"] = score
            item["match_reasons"] = reasons
            matches.append(item)
    return sorted(matches, key=lambda item: item.get("match_score", 0), reverse=True)


def split_long_reference_text(source_title: str, raw_text: str, max_chars: int = 6000) -> list[dict]:
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    lines = text.splitlines()
    chapter_starts = [
        index for index, line in enumerate(lines)
        if CHAPTER_TITLE_PATTERN.match(line.strip())
    ]

    segments: list[dict] = []
    if chapter_starts:
        if chapter_starts[0] > 0:
            preface = "\n".join(lines[:chapter_starts[0]]).strip()
            if preface:
                segments.append({
                    "title": f"{source_title} 序言/简介",
                    "content": preface,
                    "split_method": "章节标题",
                    "chapter_index": 0,
                    "char_count": len(preface),
                })
        for item_index, start in enumerate(chapter_starts):
            end = chapter_starts[item_index + 1] if item_index + 1 < len(chapter_starts) else len(lines)
            title = lines[start].strip() or f"{source_title} 第 {item_index + 1} 段"
            content = "\n".join(lines[start:end]).strip()
            if content:
                segments.append({
                    "title": title,
                    "content": content,
                    "split_method": "章节标题",
                    "chapter_index": item_index + 1,
                    "char_count": len(content),
                })

    if not segments:
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n+", text) if item.strip()]
        current: list[str] = []
        current_length = 0
        for paragraph in paragraphs or [text]:
            paragraph_length = len(paragraph)
            if current and current_length + paragraph_length + 2 > max_chars:
                content = "\n\n".join(current).strip()
                segments.append({
                    "title": f"{source_title} 片段 {len(segments) + 1:03d}",
                    "content": content,
                    "split_method": "字数切分",
                    "chapter_index": len(segments) + 1,
                    "char_count": len(content),
                })
                current = []
                current_length = 0
            if paragraph_length > max_chars:
                for start in range(0, paragraph_length, max_chars):
                    piece = paragraph[start:start + max_chars].strip()
                    if piece:
                        segments.append({
                            "title": f"{source_title} 片段 {len(segments) + 1:03d}",
                            "content": piece,
                            "split_method": "字数切分",
                            "chapter_index": len(segments) + 1,
                            "char_count": len(piece),
                        })
                continue
            current.append(paragraph)
            current_length += paragraph_length + 2
        if current:
            content = "\n\n".join(current).strip()
            segments.append({
                "title": f"{source_title} 片段 {len(segments) + 1:03d}",
                "content": content,
                "split_method": "字数切分",
                "chapter_index": len(segments) + 1,
                "char_count": len(content),
            })

    normalized = []
    for index, segment in enumerate(segments, start=1):
        item = dict(segment)
        item["index"] = index
        item["title"] = item.get("title") or f"{source_title} 片段 {index:03d}"
        item["char_count"] = len(item.get("content", ""))
        normalized.append(item)
    return normalized


def build_long_reference_source_name(base_title: str, segment: dict, fallback_order: int) -> str:
    short_title = re.sub(r"\s+", "_", str(segment.get("title", "segment")))[:40]
    return f"{base_title}_{int(segment.get('index', fallback_order)):04d}_{short_title}"


def import_long_reference_segments(
    project_name: str,
    batch: dict,
    segment_indices: list[int],
) -> tuple[dict, int]:
    imported = 0
    segments = batch.get("segments", [])
    base_title = str(batch.get("title") or "长篇资料")
    total_selected = len(segment_indices)
    for order, index in enumerate(segment_indices, start=1):
        if index < 0 or index >= len(segments):
            continue
        segment = segments[index]
        payload = build_structured_external_source_payload(
            source_type=batch.get("source_type", "external_source"),
            scope=batch.get("scope", "reference"),
            title=segment.get("title", f"{base_title} 片段 {order:03d}"),
            summary=f"长篇资料片段 {segment.get('index')} / 共 {len(segments)} 段 / 字符数 {segment.get('char_count')}",
            content=segment.get("content", ""),
            tags=["长篇资料", "自动切分"],
            metadata={
                "authority": batch.get("authority", "curated"),
                "source_origin": batch.get("source_origin", ""),
                "long_reference": True,
                "batch_id": batch.get("batch_id", ""),
                "part_index": segment.get("index"),
                "part_count": len(segments),
                "split_method": segment.get("split_method"),
                "selected_order": order,
                "selected_count": total_selected,
            },
        )
        source_name = build_long_reference_source_name(base_title, segment, order)
        ingest_external_source_file(project_name, source_name, json.dumps(payload, ensure_ascii=False, indent=2))
        segment["import_status"] = "imported"
        segment["imported_source_name"] = source_name
        segment["import_error"] = ""
        imported += 1
    if imported:
        batch = save_long_reference_batch(project_name, batch)
        rebuild_retrieval_assets(project_name, build_vectors=True)
    return batch, imported


def extract_long_reference_segments_to_queue(
    project_name: str,
    batch: dict,
    segment_indices: list[int],
    enabled_categories: list[str],
) -> tuple[dict, int, int, list[str]]:
    queued_total = 0
    processed = 0
    failed_titles = []
    segments = batch.get("segments", [])
    for index in segment_indices:
        if index < 0 or index >= len(segments):
            continue
        segment = segments[index]
        try:
            result = extract_reference_knowledge(
                project_name,
                segment.get("title", batch.get("title", "长篇资料")),
                segment.get("content", ""),
                enabled_categories,
            )
            payload = result.get("data", {}).get("knowledge_extraction", {})
            items = payload.get("items", []) if isinstance(payload, dict) else []
            queued_count = queue_pending_knowledge_items(
                project_name,
                items,
                scope=batch.get("scope", "reference"),
                authority=batch.get("authority", "curated"),
                source_title=payload.get("source_title", "") or segment.get("title", ""),
                source_origin=batch.get("source_origin", ""),
            )
            segment["extract_status"] = "queued"
            segment["queued_knowledge_count"] = int(segment.get("queued_knowledge_count") or 0) + queued_count
            segment["extract_error"] = ""
            queued_total += queued_count
            processed += 1
        except Exception as exc:
            segment["extract_status"] = "failed"
            segment["extract_error"] = str(exc)
            failed_titles.append(f"{segment.get('title', '未命名片段')}：{exc}")
    batch = save_long_reference_batch(project_name, batch)
    return batch, processed, queued_total, failed_titles


def render_long_reference_batch_manager(project_name: str, knowledge_category_options: list[str]):
    with st.expander("长篇资料批次管理", expanded=False):
        batches = list_long_reference_batches(project_name)
        if not batches:
            st.caption("当前还没有长篇资料批次。请先在“长篇资料导入器”里上传或粘贴整本资料并创建批次。")
            return

        selected_batch_id = st.selectbox(
            "选择资料批次",
            options=[batch.get("batch_id", "") for batch in batches],
            format_func=lambda batch_id: next(
                (
                    f"{batch.get('title', '未命名批次')} / {batch.get('summary', {}).get('segment_count', 0)} 段 / 更新时间 {batch.get('updated_at', '-')}"
                    for batch in batches if batch.get("batch_id") == batch_id
                ),
                batch_id,
            ),
            key="long_reference_batch_select",
        )
        batch = load_long_reference_batch(project_name, selected_batch_id)
        if not batch:
            st.warning("批次记录读取失败。")
            return

        summary = batch.get("summary", {})
        cols = st.columns(5)
        cols[0].metric("总片段", summary.get("segment_count", 0))
        cols[1].metric("已导入", summary.get("imported_count", 0))
        cols[2].metric("待导入", summary.get("import_pending_count", 0))
        cols[3].metric("已提取", summary.get("extract_queued_count", 0))
        cols[4].metric("失败", summary.get("extract_failed_count", 0))
        st.caption(
            f"范围={label_scope(batch.get('scope', 'reference'))} / 可信度={label_authority(batch.get('authority', 'curated'))} / 来源={batch.get('source_origin', '-') or '-'}"
        )
        if batch.get("source_file_name") or batch.get("content_fingerprint"):
            st.caption(
                f"文件={batch.get('source_file_name', '-') or '-'} / 资料指纹={str(batch.get('content_fingerprint', ''))[:12] or '-'} / 字符数={batch.get('content_char_count', 0)}"
            )

        segments = batch.get("segments", [])
        filter_mode = st.selectbox(
            "片段过滤",
            options=["全部", "未导入", "未提取", "提取失败", "已提取"],
            key="long_reference_batch_filter",
        )
        filtered_indices = []
        for index, segment in enumerate(segments):
            if filter_mode == "未导入" and segment.get("import_status") == "imported":
                continue
            if filter_mode == "未提取" and segment.get("extract_status", "pending") not in {"pending", ""}:
                continue
            if filter_mode == "提取失败" and segment.get("extract_status") != "failed":
                continue
            if filter_mode == "已提取" and segment.get("extract_status") not in {"queued", "extracted"}:
                continue
            filtered_indices.append(index)

        selected_indices = st.multiselect(
            "选择要继续处理的片段",
            options=filtered_indices,
            default=filtered_indices[: min(20, len(filtered_indices))],
            format_func=lambda index: (
                f"{segments[index].get('index')}. {segments[index].get('title')}"
                f" / 导入={label_batch_segment_status(segments[index].get('import_status', 'pending'))}"
                f" / 提取={label_batch_segment_status(segments[index].get('extract_status', 'pending'))}"
            ),
            key=f"long_reference_batch_selected_segments_{selected_batch_id}",
        )

        for index in filtered_indices[:12]:
            segment = segments[index]
            st.markdown(f"#### {segment.get('index')}. {segment.get('title')}")
            st.caption(
                f"字符数={segment.get('char_count')} / 导入={label_batch_segment_status(segment.get('import_status', 'pending'))} / 提取={label_batch_segment_status(segment.get('extract_status', 'pending'))} / 待确认知识={segment.get('queued_knowledge_count', 0)}"
            )
            if segment.get("extract_error"):
                st.warning(segment.get("extract_error"))
        if len(filtered_indices) > 12:
            st.caption(f"仅预览前 12 个匹配片段，共 {len(filtered_indices)} 个。")

        col_import, col_extract, col_retry = st.columns(3)
        if col_import.button("导入所选未导入片段", key=f"batch_import_{selected_batch_id}"):
            target_indices = [index for index in selected_indices if segments[index].get("import_status") != "imported"]
            if not target_indices:
                st.error("没有可导入的未导入片段。")
            else:
                _, imported = import_long_reference_segments(project_name, batch, target_indices)
                st.success(f"已导入 {imported} 个片段，并重建检索索引。")
                st.rerun()

        extract_limit = st.number_input("本次最多提取片段数", min_value=1, max_value=50, value=5, key=f"batch_extract_limit_{selected_batch_id}")
        enabled_categories = st.multiselect(
            "提取分类",
            options=knowledge_category_options,
            default=["characters", "items", "abilities", "world_rules", "timeline_events", "relationships"],
            format_func=label_knowledge_category,
            key=f"batch_extract_categories_{selected_batch_id}",
        )
        if col_extract.button("提取所选未提取片段", key=f"batch_extract_{selected_batch_id}"):
            target_indices = [
                index for index in selected_indices
                if segments[index].get("extract_status", "pending") in {"pending", ""}
            ][: int(extract_limit)]
            if not target_indices:
                st.error("没有可提取的未提取片段。")
            elif not enabled_categories:
                st.error("请至少选择一个提取分类。")
            else:
                _, processed, queued_total, failures = extract_long_reference_segments_to_queue(
                    project_name,
                    batch,
                    target_indices,
                    enabled_categories,
                )
                st.success(f"已处理 {processed} 个片段，加入 {queued_total} 条待确认知识。")
                for failure in failures[:5]:
                    st.warning(f"提取失败：{failure}")
                if not failures:
                    st.rerun()

        if col_retry.button("重试失败片段", key=f"batch_retry_{selected_batch_id}"):
            target_indices = [
                index for index in selected_indices
                if segments[index].get("extract_status") == "failed"
            ][: int(extract_limit)]
            if not target_indices:
                st.error("没有选中的失败片段。")
            elif not enabled_categories:
                st.error("请至少选择一个提取分类。")
            else:
                _, processed, queued_total, failures = extract_long_reference_segments_to_queue(
                    project_name,
                    batch,
                    target_indices,
                    enabled_categories,
                )
                st.success(f"已重试 {processed} 个片段，加入 {queued_total} 条待确认知识。")
                for failure in failures[:5]:
                    st.warning(f"重试失败：{failure}")
                if not failures:
                    st.rerun()

        with st.expander("高级操作", expanded=False):
            if st.button("删除当前批次记录", key=f"batch_delete_{selected_batch_id}"):
                delete_long_reference_batch(project_name, selected_batch_id)
                st.success("已删除批次记录。已导入的资料文件和结构化知识不会被删除。")
                st.rerun()
            raw_batch_json = st.text_area(
                "批次原始数据",
                value=json.dumps(batch, ensure_ascii=False, indent=2),
                height=360,
                key=f"batch_raw_json_{selected_batch_id}",
            )
            if st.button("保存批次原始数据", key=f"batch_save_raw_{selected_batch_id}"):
                try:
                    parsed = json.loads(raw_batch_json)
                    if not isinstance(parsed, dict):
                        st.error("批次数据必须是对象结构。")
                    else:
                        save_long_reference_batch(project_name, parsed)
                        st.success("批次数据已保存。")
                        st.rerun()
                except json.JSONDecodeError as exc:
                    st.error(f"结构化数据格式错误：{exc}")


def render_long_reference_importer(project_name: str, source_type_options: dict, knowledge_category_options: list[str]):
    with st.expander("长篇资料导入器", expanded=False):
        st.caption("适合导入长篇网文、原作正文或大段参考资料。建议先切分并导入索引，再分批提取结构化知识。")

        col_a, col_b = st.columns(2)
        long_title = col_a.text_input("长篇资料标题", key="long_reference_title", placeholder="例如：某某原作正文")
        long_scope = col_b.selectbox("资料范围", options=["canon", "reference"], format_func=label_scope, key="long_reference_scope")
        long_authority = col_a.selectbox(
            "资料可信度",
            options=["official", "curated", "community", "unknown"],
            index=0,
            format_func=label_authority,
            key="long_reference_authority",
        )
        long_source_type = col_b.selectbox(
            "资料模板",
            options=list(source_type_options.keys()),
            index=0,
            format_func=lambda key: source_type_options.get(key, label_source_type(key)),
            key="long_reference_source_type",
        )
        long_origin = st.text_input("来源说明/链接（可选）", key="long_reference_origin")
        uploaded_file = st.file_uploader("上传 txt/md 文件（可选）", type=["txt", "md"], key="long_reference_file")
        uploaded_text = decode_uploaded_text(uploaded_file)
        pasted_text = st.text_area(
            "或直接粘贴长篇资料",
            value=uploaded_text,
            height=260,
            key="long_reference_text",
        )
        max_chars = st.slider("无章节标题时的切分字数", min_value=2000, max_value=12000, value=6000, step=1000, key="long_reference_max_chars")

        if st.button("预览长篇切分"):
            title = long_title.strip() or (uploaded_file.name.rsplit(".", 1)[0] if uploaded_file else "长篇资料")
            segments = split_long_reference_text(title, pasted_text, max_chars=max_chars)
            st.session_state["long_reference_segments"] = segments
            st.session_state.pop("long_reference_batch_id", None)
            if segments:
                st.success(f"已切分为 {len(segments)} 个资料片段。")
            else:
                st.error("没有可切分的资料内容。")

        segments = st.session_state.get("long_reference_segments", [])
        if not segments:
            return

        total_chars = sum(int(item.get("char_count", 0)) for item in segments)
        source_file_name = uploaded_file.name if uploaded_file else ""
        content_fingerprint = calculate_text_fingerprint(pasted_text)
        matching_batches = find_matching_long_reference_batches(
            project_name,
            fingerprint=content_fingerprint,
            source_file_name=source_file_name,
            char_count=len(normalize_text_for_fingerprint(pasted_text)),
            segment_count=len(segments),
        )
        st.caption(f"当前预览：{len(segments)} 个片段 / 共 {total_chars} 字符。")
        if content_fingerprint:
            st.caption(f"资料指纹：`{content_fingerprint[:12]}`")
        if matching_batches:
            best_match = matching_batches[0]
            st.warning(
                f"检测到可能已存在的资料批次：{best_match.get('title', '未命名批次')}。"
                f"匹配原因：{'、'.join(best_match.get('match_reasons', [])) or '相似'}。"
            )
            match_options = [batch.get("batch_id", "") for batch in matching_batches]
            selected_match_id = st.selectbox(
                "选择已有批次继续处理",
                options=match_options,
                format_func=lambda batch_id: next(
                    (
                        f"{batch.get('title', '未命名批次')} / 匹配分={batch.get('match_score', 0)} / {batch.get('summary', {}).get('segment_count', 0)} 段"
                        for batch in matching_batches if batch.get("batch_id") == batch_id
                    ),
                    batch_id,
                ),
                key="long_reference_matching_batch",
            )
            if st.button("使用已有批次继续处理"):
                st.session_state["long_reference_batch_id"] = selected_match_id
                st.success("已绑定到已有批次。请在“长篇资料批次管理”里继续导入、提取或重试。")
                st.rerun()
        for segment in segments[:10]:
            st.markdown(f"#### {segment.get('index')}. {segment.get('title')}")
            st.caption(f"切分方式={segment.get('split_method')} / 字符数={segment.get('char_count')}")
            st.write(segment.get("content", "")[:320] + ("..." if len(segment.get("content", "")) > 320 else ""))
        if len(segments) > 10:
            st.caption(f"仅预览前 10 个片段，共 {len(segments)} 个。")

        segment_options = list(range(len(segments)))
        selected_indices = st.multiselect(
            "选择要处理的片段",
            options=segment_options,
            default=segment_options,
            format_func=lambda index: f"{segments[index].get('index')}. {segments[index].get('title')}（{segments[index].get('char_count')} 字符）",
            key="long_reference_selected_segments",
        )

        def get_or_create_preview_batch() -> dict:
            batch_id = st.session_state.get("long_reference_batch_id")
            if batch_id:
                existing = load_long_reference_batch(project_name, batch_id)
                if existing:
                    return existing
            batch = create_long_reference_batch(
                project_name,
                title=long_title.strip() or "长篇资料",
                scope=long_scope,
                authority=long_authority,
                source_type=long_source_type,
                source_origin=long_origin.strip(),
                source_file_name=source_file_name,
                content_fingerprint=content_fingerprint,
                content_char_count=len(normalize_text_for_fingerprint(pasted_text)),
                segments=segments,
            )
            st.session_state["long_reference_batch_id"] = batch.get("batch_id")
            return batch

        if st.button("创建资料处理批次"):
            batch = get_or_create_preview_batch()
            st.success(f"已创建批次：{batch.get('title')} / {batch.get('summary', {}).get('segment_count', 0)} 个片段。")
            st.rerun()

        col_import, col_extract = st.columns(2)
        if col_import.button("批量导入所选片段到资料索引"):
            if not selected_indices:
                st.error("请先选择片段。")
            else:
                batch = get_or_create_preview_batch()
                _, imported = import_long_reference_segments(project_name, batch, selected_indices)
                st.success(f"已导入 {imported} 个长篇资料片段，并重建检索索引。")
                st.rerun()

        batch_limit = st.number_input("本次最多提取片段数", min_value=1, max_value=20, value=3, key="long_reference_extract_limit")
        enabled_categories = st.multiselect(
            "批量提取分类",
            options=knowledge_category_options,
            default=["characters", "items", "abilities", "world_rules", "timeline_events", "relationships"],
            format_func=label_knowledge_category,
            key="long_reference_extract_categories",
        )
        if col_extract.button("批量提取所选片段到待确认队列"):
            if not selected_indices:
                st.error("请先选择片段。")
            elif not enabled_categories:
                st.error("请至少选择一个提取分类。")
            else:
                with st.spinner("正在分批提取结构化知识..."):
                    batch = get_or_create_preview_batch()
                    _, processed, queued_total, failed_titles = extract_long_reference_segments_to_queue(
                        project_name,
                        batch,
                        selected_indices[: int(batch_limit)],
                        enabled_categories,
                    )
                st.success(f"已处理 {processed} 个片段，加入 {queued_total} 条待确认知识。")
                for failure in failed_titles[:5]:
                    st.warning(f"提取失败：{failure}")
                if len(failed_titles) > 5:
                    st.warning(f"另有 {len(failed_titles) - 5} 个片段提取失败。")
                if not failed_titles:
                    st.rerun()


def _build_resource_browser_items(project_name: str) -> list[dict]:
    items: list[dict] = []

    outline = load_outline(project_name)
    outline_discussion = load_outline_discussion_artifact(project_name)
    items.append({
        "id": "outline:root",
        "group": "outline",
        "label": "outline.md",
        "path_label": "全书大纲 / outline.md",
        "content": outline,
        "chapter_no": None,
        "analysis_type": "",
        "relative_path": "outline.md",
        "editable": True,
        "deletable": bool(outline.strip()),
    })
    if outline_discussion.get("discussion"):
        items.append({
            "id": "outline-discussion:root",
            "group": "outline_discussion",
            "label": "outline.discussion.json [已批准]",
            "path_label": "全书讨论工件 / outline.discussion.json / 已批准=是",
            "content": outline_discussion.get("report_markdown", ""),
            "discussion_payload": outline_discussion.get("discussion", {}),
            "chapter_no": None,
            "analysis_type": "",
            "relative_path": "outline.discussion.json",
            "editable": False,
            "deletable": True,
        })

    for volume in list_volumes(project_name):
        volume_no = int(volume.get("volume_no", 0))
        volume_discussion = load_volume_discussion_artifact(project_name, volume_no)
        items.append({
            "id": f"volume:{volume_no}",
            "group": "volume_outline",
            "label": f"volume_{volume_no:03d}.md{' [已批准讨论]' if volume.get('has_approved_discussion') else ''}",
            "path_label": f"volumes / volume_{volume_no:03d}.md / 已批准讨论={label_yes_no(bool(volume.get('has_approved_discussion')))}",
            "content": volume.get("outline", ""),
            "volume_no": volume_no,
            "volume_metadata": volume,
            "chapter_no": None,
            "analysis_type": "",
            "relative_path": f"volumes/volume_{volume_no:03d}.md",
            "editable": True,
            "deletable": True,
        })
        if volume_discussion.get("discussion"):
            items.append({
                "id": f"volume-discussion:{volume_no}",
                "group": "volume_discussion",
                "label": f"volume_{volume_no:03d}.discussion.json [已批准]",
                "path_label": f"volumes / volume_{volume_no:03d}.discussion.json / 已批准=是",
                "content": volume_discussion.get("report_markdown", ""),
                "volume_no": volume_no,
                "discussion_payload": volume_discussion.get("discussion", {}),
                "chapter_no": None,
                "analysis_type": "",
                "relative_path": f"volumes/volume_{volume_no:03d}.discussion.json",
                "editable": False,
                "deletable": True,
            })

    for arc in list_arcs(project_name):
        arc_no = int(arc.get("arc_no", 0))
        volume_no = arc.get("volume_no")
        parent_label = f" / 第{int(volume_no)}卷" if volume_no else ""
        arc_discussion = load_arc_discussion_artifact(project_name, arc_no)
        items.append({
            "id": f"arc:{arc_no}",
            "group": "arc_outline",
            "label": f"arc_{arc_no:03d}.md{' [已批准讨论]' if arc.get('has_approved_discussion') else ''}",
            "path_label": f"arcs / arc_{arc_no:03d}.md{parent_label} / 已批准讨论={label_yes_no(bool(arc.get('has_approved_discussion')))}",
            "content": arc.get("outline", ""),
            "arc_no": arc_no,
            "arc_metadata": arc,
            "chapter_no": None,
            "analysis_type": "",
            "relative_path": f"arcs/arc_{arc_no:03d}.md",
            "editable": True,
            "deletable": True,
        })
        if arc_discussion.get("discussion"):
            items.append({
                "id": f"arc-discussion:{arc_no}",
                "group": "arc_discussion",
                "label": f"arc_{arc_no:03d}.discussion.json [已批准]",
                "path_label": f"arcs / arc_{arc_no:03d}.discussion.json{parent_label} / 已批准=是",
                "content": arc_discussion.get("report_markdown", ""),
                "arc_no": arc_no,
                "arc_metadata": arc,
                "discussion_payload": arc_discussion.get("discussion", {}),
                "chapter_no": None,
                "analysis_type": "",
                "relative_path": f"arcs/arc_{arc_no:03d}.discussion.json",
                "editable": False,
                "deletable": True,
            })
        arc_chapter_plan = load_arc_chapter_plan(project_name, arc_no)
        if arc_chapter_plan.get("plan"):
            items.append({
                "id": f"arc-chapter-plan:{arc_no}",
                "group": "arc_chapter_plan",
                "label": f"arc_{arc_no:03d}.chapter_plan.json",
                "path_label": f"arcs / arc_{arc_no:03d}.chapter_plan.json{parent_label}",
                "content": arc_chapter_plan.get("report_markdown", ""),
                "arc_no": arc_no,
                "arc_metadata": arc,
                "chapter_plan_payload": arc_chapter_plan.get("plan", {}),
                "chapter_no": None,
                "analysis_type": "",
                "relative_path": f"arcs/arc_{arc_no:03d}.chapter_plan.json",
                "editable": False,
                "deletable": True,
            })
    

    chapter_inventory = list_chapter_inventory(project_name)
    for item in chapter_inventory:
        chapter_no = int(item.get("chapter_no", 0))
        if item.get("has_outline"):
            chapter_meta = item.get("metadata", {}) or {}
            chapter_discussion = load_chapter_discussion_artifact(project_name, chapter_no)
            volume_suffix = f" / 第{int(chapter_meta.get('volume_no'))}卷" if chapter_meta.get("volume_no") else ""
            arc_suffix = f" / 剧情段 {int(chapter_meta.get('arc_no')):03d}" if chapter_meta.get("arc_no") else ""
            items.append({
                "id": f"chapter-outline:{chapter_no}",
                "group": "chapter_outline",
                "label": f"chapter_{chapter_no:03d}.md",
                "path_label": f"chapter_outlines / chapter_{chapter_no:03d}.md{volume_suffix}{arc_suffix}",
                "content": item.get("outline_preview", ""),
                "chapter_no": chapter_no,
                "chapter_metadata": chapter_meta,
                "analysis_type": "",
                "relative_path": f"chapter_outlines/chapter_{chapter_no:03d}.md",
                "editable": True,
                "deletable": True,
            })
            if chapter_discussion.get("discussion"):
                items.append({
                    "id": f"chapter-discussion:{chapter_no}",
                    "group": "chapter_discussion",
                    "label": f"chapter_{chapter_no:03d}.discussion.json [已批准]",
                    "path_label": f"chapter_outlines / chapter_{chapter_no:03d}.discussion.json{volume_suffix}{arc_suffix} / 已批准=是",
                    "content": chapter_discussion.get("report_markdown", ""),
                    "chapter_no": chapter_no,
                    "chapter_metadata": chapter_meta,
                    "discussion_payload": chapter_discussion.get("discussion", {}),
                    "analysis_type": "",
                    "relative_path": f"chapter_outlines/chapter_{chapter_no:03d}.discussion.json",
                    "editable": False,
                    "deletable": True,
                })
        if item.get("has_content"):
            items.append({
                "id": f"chapter-content:{chapter_no}",
                "group": "chapter_content",
                "label": f"chapter_{chapter_no:03d}.md",
                "path_label": f"chapters / chapter_{chapter_no:03d}.md",
                "content": item.get("content_preview", ""),
                "chapter_no": chapter_no,
                "analysis_type": "",
                "relative_path": f"chapters/chapter_{chapter_no:03d}.md",
                "editable": True,
                "deletable": True,
            })
        if item.get("has_review_markdown") or item.get("has_review_json"):
            items.append({
                "id": f"review:{chapter_no}",
                "group": "review",
                "label": f"chapter_{chapter_no:03d}",
                "path_label": f"reviews / chapter_{chapter_no:03d}",
                "content": item.get("review_preview", ""),
                "review_payload": item.get("review_payload", {}),
                "chapter_no": chapter_no,
                "analysis_type": "",
                "relative_path": f"reviews/chapter_{chapter_no:03d}",
                "editable": True,
                "deletable": True,
            })

    for report in list_analysis_reports(project_name):
        chapter_no = report.get("chapter_no")
        report_path = report.get("path", "")
        content = ""
        if report_path:
            try:
                with open(report_path, "r", encoding="utf-8") as handle:
                    content = handle.read()
            except Exception:
                content = ""
        items.append({
            "id": f"analysis:{report.get('analysis_type', 'unknown')}:{chapter_no}",
            "group": "analysis",
            "label": report.get("file_name", "analysis.md"),
            "path_label": f"analysis / {report.get('file_name', 'analysis.md')}",
            "content": content,
            "chapter_no": chapter_no,
            "analysis_type": report.get("analysis_type", "unknown"),
            "relative_path": report.get("file_name", ""),
            "editable": True,
            "deletable": True,
        })

    for report in list_evaluation_reports(project_name):
        chapter_no = int(report.get("chapter_no") or 0)
        content = load_evaluation_report(project_name, chapter_no)
        items.append({
            "id": f"evaluation:{chapter_no}",
            "group": "evaluation",
            "label": report.get("file_name", "evaluation.md"),
            "path_label": f"evaluation / {report.get('file_name', 'evaluation.md')}",
            "content": content,
            "evaluation_payload": load_evaluation_json(project_name, chapter_no) or {},
            "chapter_no": chapter_no,
            "analysis_type": "",
            "relative_path": report.get("file_name", ""),
            "editable": True,
            "deletable": True,
        })

    for run in list_project_runs(project_name):
        run_content = load_pipeline_run(project_name, run.get("run_id", ""))
        items.append({
            "id": f"run:{run.get('run_id', '')}",
            "group": "run",
            "label": f"{run.get('run_id', '')}.json",
            "path_label": f"runs / {run.get('run_id', '')}.json",
            "content": run_content,
            "chapter_no": run.get("chapter_no"),
            "analysis_type": "",
            "run_id": run.get("run_id", ""),
            "relative_path": f"runs/{run.get('run_id', '')}.json",
            "editable": False,
            "deletable": True,
        })

    for source in list_retrieval_sources(project_name):
        items.append({
            "id": f"source:{source.get('relative_path', '')}",
            "group": "source",
            "label": source.get("relative_path", ""),
            "path_label": f"retrieval/sources / {source.get('relative_path', '')}",
            "content": source.get("preview", ""),
            "chapter_no": None,
            "analysis_type": "",
            "relative_path": source.get("relative_path", ""),
            "suffix": source.get("suffix", ""),
            "editable": True,
            "deletable": True,
        })

    return items


def _save_browser_resource(project_name: str, resource: dict, edited_content: str, edited_json_text: str = ""):
    group = resource.get("group")
    if group == "outline":
        save_outline(project_name, edited_content)
        return
    if group == "volume_outline":
        volume_no = int(resource.get("volume_no", 0))
        save_volume_outline(project_name, volume_no, edited_content)
        metadata = dict(resource.get("volume_metadata", {}) or {})
        save_volume_metadata(project_name, volume_no, metadata)
        return
    if group == "arc_outline":
        arc_no = int(resource.get("arc_no", 0))
        save_arc_outline(project_name, arc_no, edited_content)
        metadata = dict(resource.get("arc_metadata", {}) or {})
        save_arc_metadata(project_name, arc_no, metadata)
        return
    if group == "chapter_outline":
        save_chapter_outline(project_name, int(resource.get("chapter_no", 0)), edited_content)
        return
    if group == "chapter_content":
        save_chapter(project_name, int(resource.get("chapter_no", 0)), edited_content)
        return
    if group == "review":
        parsed = json.loads(edited_json_text) if edited_json_text.strip() else {}
        save_review_resources(project_name, int(resource.get("chapter_no", 0)), edited_content, parsed)
        return
    if group == "analysis":
        save_analysis_resource(project_name, str(resource.get("analysis_type", "unknown")), int(resource.get("chapter_no") or 0), edited_content)
        return
    if group == "evaluation":
        parsed = json.loads(edited_json_text) if edited_json_text.strip() else {}
        save_evaluation_resource(project_name, int(resource.get("chapter_no", 0)), edited_content, parsed)
        return
    if group == "source":
        save_retrieval_source_content(project_name, str(resource.get("relative_path", "")), edited_content)
        rebuild_retrieval_assets(project_name, build_vectors=True)
        return
    raise ValueError(f"不支持保存这种资源类型：{group}")


def _delete_browser_resource(project_name: str, resource: dict):
    group = resource.get("group")
    if group == "outline":
        return delete_outline(project_name)
    if group == "outline_discussion":
        return clear_outline_discussion_approval(project_name)
    if group == "volume_outline":
        return delete_volume(project_name, int(resource.get("volume_no", 0)))
    if group == "volume_discussion":
        return clear_volume_discussion_approval(project_name, int(resource.get("volume_no", 0)))
    if group == "arc_outline":
        return delete_arc(project_name, int(resource.get("arc_no", 0)))
    if group == "arc_discussion":
        return clear_arc_discussion_approval(project_name, int(resource.get("arc_no", 0)))
    if group == "arc_chapter_plan":
        return delete_arc_chapter_plan(project_name, int(resource.get("arc_no", 0)))
    if group == "chapter_outline":
        return delete_chapter_outline(project_name, int(resource.get("chapter_no", 0)))
    if group == "chapter_discussion":
        return clear_chapter_discussion_approval(project_name, int(resource.get("chapter_no", 0)))
    if group == "chapter_content":
        return delete_chapter_content(project_name, int(resource.get("chapter_no", 0)))
    if group == "review":
        return delete_chapter_review(project_name, int(resource.get("chapter_no", 0)))
    if group == "analysis":
        return delete_analysis_report(project_name, str(resource.get("analysis_type", "unknown")), int(resource.get("chapter_no") or 0))
    if group == "evaluation":
        return delete_evaluation_report(project_name, int(resource.get("chapter_no", 0)))
    if group == "run":
        return delete_pipeline_run(project_name, str(resource.get("run_id", "")))
    if group == "source":
        deleted = delete_retrieval_source_file(project_name, str(resource.get("relative_path", "")))
        if deleted:
            rebuild_retrieval_assets(project_name, build_vectors=True)
        return deleted
    raise ValueError(f"不支持删除这种资源类型：{group}")


def _render_resource_browser_detail(project_name: str, resource: dict):
    if not resource:
        st.caption("请先从左侧选择一个资源。")
        return

    st.markdown(f"### {resource.get('label', '')}")
    st.caption(resource.get("path_label", ""))

    group = resource.get("group")
    if group == "run":
        st.code(resource.get("content", ""), language="json")
        if st.button("删除该运行记录", key=f"browser_delete_{resource.get('id')}"):
            if _delete_browser_resource(project_name, resource):
                st.success("运行记录已删除。")
                st.session_state[_resource_browser_selection_key(project_name)] = {}
                st.rerun()
        return

    if group in {"outline_discussion", "volume_discussion", "arc_discussion", "chapter_discussion", "arc_chapter_plan"}:
        if resource.get("content"):
            st.markdown(resource.get("content", ""))
        render_step_json_expander("结构化数据", resource.get("discussion_payload", {}) or resource.get("chapter_plan_payload", {}))
        if st.button("删除该工件", key=f"browser_delete_{resource.get('id')}"):
            if _delete_browser_resource(project_name, resource):
                st.success("工件已删除。")
                st.session_state[_resource_browser_selection_key(project_name)] = {}
                st.rerun()
        return

    edited_content = st.text_area(
        "内容",
        value=resource.get("content", ""),
        height=520,
        key=f"browser_editor_{resource.get('id')}"
    )

    edited_json_text = ""
    if group == "volume_outline":
        metadata = dict(resource.get("volume_metadata", {}) or {})
        volume_title = st.text_input("分卷标题", value=metadata.get("title", ""), key=f"browser_volume_title_{resource.get('id')}")
        volume_summary = st.text_area("分卷摘要", value=metadata.get("summary", ""), height=120, key=f"browser_volume_summary_{resource.get('id')}")
        volume_status = st.selectbox("分卷状态", options=["draft", "approved", "archived"], index=["draft", "approved", "archived"].index(metadata.get("status", "draft")) if metadata.get("status", "draft") in ["draft", "approved", "archived"] else 0, format_func=label_status, key=f"browser_volume_status_{resource.get('id')}")
        resource["volume_metadata"] = {
            "volume_no": int(resource.get("volume_no", 0)),
            "title": volume_title,
            "summary": volume_summary,
            "status": volume_status,
        }
    if group == "arc_outline":
        metadata = dict(resource.get("arc_metadata", {}) or {})
        arc_title = st.text_input("剧情段标题", value=metadata.get("title", ""), key=f"browser_arc_title_{resource.get('id')}")
        arc_summary = st.text_area("剧情段摘要", value=metadata.get("summary", ""), height=120, key=f"browser_arc_summary_{resource.get('id')}")
        volume_options = [0] + [int(item.get("volume_no", 0)) for item in list_volumes(project_name)]
        current_volume = int(metadata.get("volume_no") or 0)
        arc_volume_no = st.selectbox("所属分卷", options=volume_options, index=volume_options.index(current_volume) if current_volume in volume_options else 0, format_func=lambda value: "未指定分卷" if value == 0 else f"第 {value} 卷", key=f"browser_arc_volume_{resource.get('id')}")
        arc_status = st.selectbox("剧情段状态", options=["draft", "approved", "archived"], index=["draft", "approved", "archived"].index(metadata.get("status", "draft")) if metadata.get("status", "draft") in ["draft", "approved", "archived"] else 0, format_func=label_status, key=f"browser_arc_status_{resource.get('id')}")
        estimated_chapter_count = st.number_input("预计章节数", min_value=0, value=int(metadata.get("estimated_chapter_count") or 0), key=f"browser_arc_estimated_chapters_{resource.get('id')}")
        target_word_count_range = st.text_input("目标总字数范围", value=metadata.get("target_word_count_range", ""), key=f"browser_arc_word_range_{resource.get('id')}")
        resource["arc_metadata"] = {
            "arc_no": int(resource.get("arc_no", 0)),
            "volume_no": arc_volume_no or None,
            "title": arc_title,
            "summary": arc_summary,
            "status": arc_status,
            "estimated_chapter_count": estimated_chapter_count or None,
            "target_word_count_range": target_word_count_range,
        }
    if group == "review":
        edited_json_text = st.text_area(
            "审阅结构化数据",
            value=json.dumps(resource.get("review_payload", {}), ensure_ascii=False, indent=2),
            height=220,
            key=f"browser_json_{resource.get('id')}"
        )
    if group == "evaluation":
        edited_json_text = st.text_area(
            "评估结构化数据",
            value=json.dumps(resource.get("evaluation_payload", {}), ensure_ascii=False, indent=2),
            height=220,
            key=f"browser_json_{resource.get('id')}"
        )

    save_col, delete_col = st.columns(2)
    if resource.get("editable") and save_col.button("保存当前资源", key=f"browser_save_{resource.get('id')}"):
        try:
            _save_browser_resource(project_name, resource, edited_content, edited_json_text)
            st.success("资源已保存。")
            st.rerun()
        except json.JSONDecodeError as exc:
            st.error(f"结构化数据格式错误：{exc}")
        except Exception as exc:
            st.error(f"保存资源失败：{exc}")

    if resource.get("deletable") and delete_col.button("删除当前资源", key=f"browser_delete_{resource.get('id')}"):
        try:
            if _delete_browser_resource(project_name, resource):
                st.success("资源已删除。")
                st.session_state[_resource_browser_selection_key(project_name)] = {}
                st.rerun()
            else:
                st.warning("目标资源不存在。")
        except Exception as exc:
            st.error(f"删除资源失败：{exc}")


def render_resource_management_page(project_name: str):
    st.subheader("项目资源管理")
    browser_items = _build_resource_browser_items(project_name)
    selected = _get_resource_browser_selection(project_name)

    left_col, right_col = st.columns([1, 2])

    with left_col:
        st.markdown("### 资源浏览器")
        search_value = st.text_input("搜索资源", key=f"resource_browser_search_{project_name}")
        search_lower = search_value.strip().lower()
        volume_filter_options = [0] + [int(item.get("volume_no", 0)) for item in list_volumes(project_name)]
        browser_volume_filter = st.selectbox(
            "按分卷过滤",
            options=volume_filter_options,
            format_func=lambda value: "全部分卷" if value == 0 else f"第 {value} 卷",
            key=f"resource_browser_volume_filter_{project_name}",
        )
        arc_filter_candidates = list_arcs(project_name, volume_no=browser_volume_filter or None)
        arc_filter_options = [0] + [int(item.get("arc_no", 0)) for item in arc_filter_candidates]
        browser_arc_filter = st.selectbox(
            "按剧情段过滤",
            options=arc_filter_options,
            format_func=lambda value: "全部剧情段" if value == 0 else f"剧情段 {value:03d}",
            key=f"resource_browser_arc_filter_{project_name}",
        )

        chapter_inventory = list_chapter_inventory(project_name)
        runs = list_project_runs(project_name)
        sources = list_retrieval_sources(project_name)

        if chapter_inventory:
            chapter_numbers = [item.get("chapter_no") for item in chapter_inventory]
            bulk_chapter_selection = st.multiselect(
                "批量章节清理",
                options=chapter_numbers,
                format_func=lambda value: f"第 {int(value)} 章",
                key=f"resource_bulk_chapters_{project_name}"
            )
            if bulk_chapter_selection and st.button("清理所选章节", key=f"bulk_delete_chapters_{project_name}"):
                results = []
                for chapter_no in bulk_chapter_selection:
                    results.append({
                        "chapter_no": int(chapter_no),
                        "result": delete_chapter_bundle(project_name, int(chapter_no)),
                    })
                st.success(f"已批量清理章节资源：{json.dumps(results, ensure_ascii=False)}")
                st.rerun()

        if runs:
            bulk_runs = st.multiselect(
                "批量删除运行记录",
                options=[run.get("run_id") for run in runs],
                key=f"resource_bulk_runs_{project_name}"
            )
            if bulk_runs and st.button("删除所选运行记录", key=f"bulk_delete_runs_{project_name}"):
                deleted_count = 0
                for run_id in bulk_runs:
                    if delete_pipeline_run(project_name, str(run_id)):
                        deleted_count += 1
                st.success(f"已删除 {deleted_count} 条运行记录。")
                st.rerun()

        if sources:
            bulk_sources = st.multiselect(
                "批量删除外部资料",
                options=[source.get("relative_path") for source in sources],
                key=f"resource_bulk_sources_{project_name}"
            )
            if bulk_sources and st.button("删除所选外部资料", key=f"bulk_delete_sources_{project_name}"):
                deleted_count = 0
                for relative_path in bulk_sources:
                    try:
                        if delete_retrieval_source_file(project_name, str(relative_path)):
                            deleted_count += 1
                    except Exception:
                        continue
                if deleted_count:
                    rebuild_retrieval_assets(project_name, build_vectors=True)
                st.success(f"已删除 {deleted_count} 份外部资料。")
                st.rerun()

        groups = [
            ("outline", "全书大纲"),
            ("outline_discussion", "全书讨论工件"),
            ("volume_outline", "分卷大纲"),
            ("volume_discussion", "分卷讨论工件"),
            ("arc_outline", "剧情段大纲"),
            ("arc_discussion", "剧情段讨论工件"),
            ("arc_chapter_plan", "剧情段章节分配"),
            ("chapter_outline", "章节细纲"),
            ("chapter_discussion", "章节讨论工件"),
            ("chapter_content", "章节正文"),
            ("review", "审阅结果"),
            ("analysis", "分析报告"),
            ("evaluation", "评估报告"),
            ("run", "流水线记录"),
            ("source", "外部资料"),
        ]

        for group_key, group_label in groups:
            group_items = [item for item in browser_items if item.get("group") == group_key]
            if browser_volume_filter:
                filtered_items = []
                for item in group_items:
                    item_volume_no = item.get("volume_no")
                    if item_volume_no is None:
                        item_volume_no = (item.get("volume_metadata") or {}).get("volume_no")
                    if item_volume_no is None:
                        item_volume_no = (item.get("arc_metadata") or {}).get("volume_no")
                    if item_volume_no is None:
                        item_volume_no = (item.get("chapter_metadata") or {}).get("volume_no")
                    if item.get("group") in {"outline", "run", "analysis", "evaluation", "source", "review", "chapter_content"}:
                        filtered_items.append(item)
                    elif item_volume_no == browser_volume_filter:
                        filtered_items.append(item)
                group_items = filtered_items
            if browser_arc_filter:
                filtered_items = []
                for item in group_items:
                    item_arc_no = item.get("arc_no")
                    if item_arc_no is None:
                        item_arc_no = (item.get("arc_metadata") or {}).get("arc_no")
                    if item_arc_no is None:
                        item_arc_no = (item.get("chapter_metadata") or {}).get("arc_no")
                    if item.get("group") in {"outline", "outline_discussion", "volume_outline", "volume_discussion", "run", "analysis", "evaluation", "source", "review", "chapter_content"}:
                        filtered_items.append(item)
                    elif item_arc_no == browser_arc_filter:
                        filtered_items.append(item)
                group_items = filtered_items
            if search_lower:
                group_items = [
                    item for item in group_items
                    if search_lower in str(item.get("label", "")).lower()
                    or search_lower in str(item.get("path_label", "")).lower()
                ]
            if not group_items:
                continue
            st.markdown(f"**{group_label}**")
            for item in group_items:
                selected_flag = selected.get("id") == item.get("id")
                button_label = f"> {item.get('label')}" if selected_flag else item.get("label")
                if st.button(button_label, key=f"resource_select_{item.get('id')}", use_container_width=True):
                    _set_resource_browser_selection(project_name, item)
                    st.rerun()

    with right_col:
        st.markdown("### 资源详情")
        if selected and not any(item.get("id") == selected.get("id") for item in browser_items):
            selected = {}
            st.session_state[_resource_browser_selection_key(project_name)] = {}
        if not selected and browser_items:
            selected = browser_items[0]
            _set_resource_browser_selection(project_name, selected)
        _render_resource_browser_detail(project_name, selected)


def render_project_files_page(project_name: str):
    st.subheader("项目文件预览")

    outline = load_outline(project_name)
    if outline:
        with st.expander("outline.md", expanded=True):
            st.markdown(outline)
    outline_discussion = load_outline_discussion_artifact(project_name)
    if outline_discussion.get("discussion"):
        with st.expander("outline.discussion.json", expanded=False):
            st.markdown(outline_discussion.get("report_markdown", "") or "（无可用 Markdown 预览）")
            render_step_json_expander("全书讨论结构化数据", outline_discussion.get("discussion", {}))

    volumes = list_volumes(project_name)
    for volume in volumes:
        volume_no = int(volume.get("volume_no", 0))
        title = volume.get("title", "") or f"volume_{volume_no:03d}.md"
        with st.expander(f"volumes/volume_{volume_no:03d}.md / {title}", expanded=False):
            if volume.get("summary"):
                st.caption(volume.get("summary"))
            st.markdown(volume.get("outline", "") or "")
        volume_discussion = load_volume_discussion_artifact(project_name, volume_no)
        if volume_discussion.get("discussion"):
            with st.expander(f"volumes/volume_{volume_no:03d}.discussion.json / {title}", expanded=False):
                st.markdown(volume_discussion.get("report_markdown", "") or "（无可用 Markdown 预览）")
                render_step_json_expander("分卷讨论结构化数据", volume_discussion.get("discussion", {}))

    arcs = list_arcs(project_name)
    for arc in arcs:
        arc_no = int(arc.get("arc_no", 0))
        title = arc.get("title", "") or f"arc_{arc_no:03d}.md"
        with st.expander(f"arcs/arc_{arc_no:03d}.md / {title}", expanded=False):
            if arc.get("summary"):
                st.caption(arc.get("summary"))
            if arc.get("volume_no"):
                st.caption(f"所属分卷：第 {int(arc.get('volume_no'))} 卷")
            st.markdown(arc.get("outline", "") or "")
        arc_discussion = load_arc_discussion_artifact(project_name, arc_no)
        if arc_discussion.get("discussion"):
            with st.expander(f"arcs/arc_{arc_no:03d}.discussion.json / {title}", expanded=False):
                st.markdown(arc_discussion.get("report_markdown", "") or "（无可用 Markdown 预览）")
                render_step_json_expander("剧情段讨论结构化数据", arc_discussion.get("discussion", {}))


    chapter_no = st.number_input("预览章节编号", min_value=1, value=1, key="preview_chapter_no")
    chapter_outline = load_chapter_outline(project_name, chapter_no)
    chapter = load_chapter(project_name, chapter_no)
    review = load_review(project_name, chapter_no)
    review_json = load_review_json(project_name, chapter_no)

    if chapter_outline:
        with st.expander(f"chapter_outlines/chapter_{chapter_no:03d}.md", expanded=True):
            st.markdown(chapter_outline)
    chapter_discussion = load_chapter_discussion_artifact(project_name, chapter_no)
    if chapter_discussion.get("discussion"):
        with st.expander(f"chapter_outlines/chapter_{chapter_no:03d}.discussion.json", expanded=False):
            st.markdown(chapter_discussion.get("report_markdown", "") or "（无可用 Markdown 预览）")
            render_step_json_expander("章节讨论结构化数据", chapter_discussion.get("discussion", {}))

    if chapter:
        with st.expander(f"chapters/chapter_{chapter_no:03d}.md", expanded=True):
            st.markdown(chapter)

    if review:
        with st.expander(f"reviews/chapter_{chapter_no:03d}.md", expanded=True):
            st.markdown(review)
    if review_json:
        with st.expander(f"reviews/chapter_{chapter_no:03d}.json", expanded=False):
            st.code(json.dumps(review_json, ensure_ascii=False, indent=2), language="json")

    evaluation_report = load_evaluation_report(project_name, chapter_no)
    evaluation_json = load_evaluation_json(project_name, chapter_no)
    if evaluation_report:
        with st.expander(f"evaluation/chapter_{chapter_no:03d}.md", expanded=False):
            st.markdown(evaluation_report)
    if evaluation_json:
        with st.expander(f"evaluation/chapter_{chapter_no:03d}.json", expanded=False):
            st.code(json.dumps(evaluation_json, ensure_ascii=False, indent=2), language="json")


def render_volume_outline_page(project_name: str):
    st.subheader("分卷大纲")

    volume_no = st.number_input("分卷编号", min_value=1, value=1, key="volume_outline_no")
    metadata = load_volume_metadata(project_name, volume_no)
    existing_outline = load_volume_outline(project_name, volume_no)
    step_result = st.session_state.get(f"volume_outline_step_{volume_no}", {})

    title = st.text_input("分卷标题", value=metadata.get("title", ""), key=f"volume_title_{volume_no}")
    summary = st.text_area("分卷摘要", value=metadata.get("summary", ""), height=120, key=f"volume_summary_{volume_no}")
    status = st.selectbox(
        "分卷状态",
        options=["draft", "approved", "archived"],
        index=["draft", "approved", "archived"].index(metadata.get("status", "draft")) if metadata.get("status", "draft") in ["draft", "approved", "archived"] else 0,
        format_func=label_status,
        key=f"volume_status_{volume_no}",
    )

    requirement = st.text_area("本卷要求", height=180, key=f"volume_requirement_{volume_no}")
    suffix = str(volume_no)
    messages_key = _discussion_messages_key("volume", suffix)
    result_key = _discussion_result_key("volume", suffix)
    input_key = _discussion_input_key("volume", suffix)
    clear_input_flag_key = _discussion_input_clear_flag_key("volume", suffix)
    _consume_discussion_input_clear("volume", suffix)
    discussion_step = st.session_state.get(result_key, {})
    approved_artifact = load_volume_discussion_artifact(project_name, volume_no)

    col_action_1, col_action_2 = st.columns(2)
    if col_action_1.button("开始讨论分卷方向", key=f"start_volume_discussion_{volume_no}"):
        try:
            result = discuss_volume(project_name, volume_no, title, summary, requirement)
            st.session_state[result_key] = result
            st.session_state[messages_key] = []
            assistant_message = result.get("data", {}).get("discussion", {}).get("current_understanding", "") or "我先整理了本卷的定位、可选结构和待确认问题，我们可以继续细化。"
            _append_discussion_message(messages_key, "assistant", assistant_message)
            st.rerun()
        except Exception as exc:
            st.error(f"讨论失败：{exc}")

    if col_action_2.button("重置分卷讨论", key=f"reset_volume_discussion_{volume_no}"):
        st.session_state[result_key] = {}
        st.session_state[messages_key] = []
        st.session_state[clear_input_flag_key] = True
        st.rerun()

    summary_col, chat_col = st.columns([1, 1])
    with summary_col:
        st.markdown("### 当前讨论结论")
        _render_discussion_summary(discussion_step, "开始讨论后，这里会持续显示当前分卷方向的结论。")
        approve_col, clear_col = st.columns(2)
        if approve_col.button("批准当前讨论", key=f"approve_volume_discussion_{volume_no}"):
            try:
                result = approve_volume_discussion(project_name, volume_no, discussion_step)
                st.success(f"已保存分卷讨论工件：{result.get('saved_path', '')}")
                st.rerun()
            except Exception as exc:
                st.error(f"批准失败：{exc}")
        if clear_col.button("清除已批准版本", key=f"clear_volume_discussion_{volume_no}"):
            if clear_volume_discussion_approval(project_name, volume_no):
                st.success("已清除分卷已批准讨论工件。")
                st.rerun()
            else:
                st.warning("当前没有可清除的已批准讨论工件。")
        st.markdown("### 已批准讨论版本")
        _render_approved_discussion_artifact(approved_artifact, "当前分卷还没有已批准讨论工件。")

    with chat_col:
        st.markdown("### 讨论对话")
        messages = st.session_state.get(messages_key, [])
        _render_discussion_chat(messages)
        follow_up = st.text_area("继续讨论分卷", key=input_key, height=120, placeholder="例如：这一卷我想更偏升级与站稳脚跟，不要太早引爆终局矛盾。")
        if st.button("发送分卷讨论消息", key=f"send_volume_discussion_{volume_no}"):
            if not follow_up.strip():
                st.warning("讨论消息不能为空。")
            else:
                try:
                    _append_discussion_message(messages_key, "user", follow_up)
                    messages = st.session_state.get(messages_key, [])
                    result = discuss_volume_turn(
                        project_name,
                        volume_no,
                        title,
                        summary,
                        requirement,
                        messages,
                        discussion_step.get("data", {}).get("discussion", {}),
                        follow_up,
                    )
                    st.session_state[result_key] = result
                    assistant_message = result.get("data", {}).get("assistant_message", "") or "我已经根据你的补充更新了本卷讨论结论。"
                    _append_discussion_message(messages_key, "assistant", assistant_message)
                    st.session_state[clear_input_flag_key] = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"继续讨论失败：{exc}")

    if st.button("生成分卷大纲", key=f"generate_volume_outline_{volume_no}"):
        try:
            result = generate_volume_outline(project_name, volume_no, title, summary, requirement, status=status)
            st.session_state[f"volume_outline_step_{volume_no}"] = result
            st.session_state[f"volume_outline_{volume_no}"] = result.get("data", {}).get("volume_outline", "")
            st.rerun()
        except Exception as exc:
            st.error(f"生成分卷大纲失败：{exc}")

    outline_text = st.text_area("分卷大纲内容", value=st.session_state.get(f"volume_outline_{volume_no}", existing_outline), height=500, key=f"volume_outline_editor_{volume_no}")

    col1, col2 = st.columns(2)
    if col1.button("保存分卷大纲", key=f"save_volume_{volume_no}"):
        save_volume_outline(project_name, volume_no, outline_text)
        save_volume_metadata(project_name, volume_no, {"title": title, "summary": summary, "status": status})
        st.success(f"第 {volume_no} 卷大纲已保存")
        st.rerun()
    if col2.button("删除分卷", key=f"delete_volume_{volume_no}"):
        if delete_volume(project_name, volume_no):
            st.success(f"第 {volume_no} 卷已删除")
            st.rerun()
        else:
            st.warning("目标分卷不存在。")

    volumes = list_volumes(project_name)
    if volumes:
        st.markdown("### 现有分卷")
        for item in volumes:
            approval_label = "已有批准讨论" if item.get("has_approved_discussion") else "暂无批准讨论"
            st.caption(f"第 {int(item.get('volume_no', 0))} 卷 / {item.get('title', '') or '未命名'} / 状态={label_status(item.get('status', 'draft'))} / {approval_label}")

    render_step_validation(step_result)
    render_step_retrieval(step_result, "本次分卷大纲生成使用的检索上下文", get_retrieval_trace(f"volume_outline:{project_name}:{volume_no}"))


def render_arc_outline_page(project_name: str):
    st.subheader("剧情段大纲")

    arc_no = st.number_input("剧情段编号", min_value=1, value=1, key="arc_outline_no")
    metadata = load_arc_metadata(project_name, arc_no)
    existing_outline = load_arc_outline(project_name, arc_no)
    step_result = st.session_state.get(f"arc_outline_step_{arc_no}", {})

    volume_options = [0] + [int(item.get("volume_no", 0)) for item in list_volumes(project_name)]
    current_volume = int(metadata.get("volume_no") or 0)
    volume_no = st.selectbox(
        "所属分卷",
        options=volume_options,
        index=volume_options.index(current_volume) if current_volume in volume_options else 0,
        format_func=lambda value: "未指定分卷" if value == 0 else f"第 {value} 卷",
        key=f"arc_volume_{arc_no}",
    )
    title = st.text_input("剧情段标题", value=metadata.get("title", ""), key=f"arc_title_{arc_no}")
    summary = st.text_area("剧情段摘要", value=metadata.get("summary", ""), height=120, key=f"arc_summary_{arc_no}")
    status = st.selectbox(
        "剧情段状态",
        options=["draft", "approved", "archived"],
        index=["draft", "approved", "archived"].index(metadata.get("status", "draft")) if metadata.get("status", "draft") in ["draft", "approved", "archived"] else 0,
        format_func=label_status,
        key=f"arc_status_{arc_no}",
    )
    estimated_chapter_count = st.number_input("预计章节数", min_value=0, value=int(metadata.get("estimated_chapter_count") or 0), key=f"arc_estimated_chapters_{arc_no}")
    target_word_count_range = st.text_input("目标总字数范围", value=metadata.get("target_word_count_range", ""), key=f"arc_word_range_{arc_no}")
    requirement = st.text_area("本剧情段要求", height=180, key=f"arc_requirement_{arc_no}")

    suffix = str(arc_no)
    messages_key = _discussion_messages_key("arc", suffix)
    result_key = _discussion_result_key("arc", suffix)
    input_key = _discussion_input_key("arc", suffix)
    clear_input_flag_key = _discussion_input_clear_flag_key("arc", suffix)
    _consume_discussion_input_clear("arc", suffix)
    discussion_step = st.session_state.get(result_key, {})
    approved_artifact = load_arc_discussion_artifact(project_name, arc_no)

    col_action_1, col_action_2 = st.columns(2)
    if col_action_1.button("开始讨论剧情段方向", key=f"start_arc_discussion_{arc_no}"):
        try:
            result = discuss_arc(
                project_name,
                arc_no,
                volume_no or None,
                title,
                summary,
                estimated_chapter_count or None,
                target_word_count_range,
                requirement,
            )
            st.session_state[result_key] = result
            st.session_state[messages_key] = []
            assistant_message = result.get("data", {}).get("discussion", {}).get("current_understanding", "") or "我先整理了这个剧情段的目标、可选推进结构和待确认问题，我们可以继续细化。"
            _append_discussion_message(messages_key, "assistant", assistant_message)
            st.rerun()
        except Exception as exc:
            st.error(f"讨论失败：{exc}")

    if col_action_2.button("重置剧情段讨论", key=f"reset_arc_discussion_{arc_no}"):
        st.session_state[result_key] = {}
        st.session_state[messages_key] = []
        st.session_state[clear_input_flag_key] = True
        st.rerun()

    summary_col, chat_col = st.columns([1, 1])
    with summary_col:
        st.markdown("### 当前讨论结论")
        _render_discussion_summary(discussion_step, "开始讨论后，这里会持续显示当前剧情段方向的结论。")
        approve_col, clear_col = st.columns(2)
        if approve_col.button("批准当前讨论", key=f"approve_arc_discussion_{arc_no}"):
            try:
                result = approve_arc_discussion(project_name, arc_no, discussion_step)
                st.success(f"已保存剧情段讨论工件：{result.get('saved_path', '')}")
                st.rerun()
            except Exception as exc:
                st.error(f"批准失败：{exc}")
        if clear_col.button("清除已批准版本", key=f"clear_arc_discussion_{arc_no}"):
            if clear_arc_discussion_approval(project_name, arc_no):
                st.success("已清除剧情段已批准讨论工件。")
                st.rerun()
            else:
                st.warning("当前没有可清除的已批准讨论工件。")
        st.markdown("### 已批准讨论版本")
        _render_approved_discussion_artifact(approved_artifact, "当前剧情段还没有已批准讨论工件。")

    with chat_col:
        st.markdown("### 讨论对话")
        messages = st.session_state.get(messages_key, [])
        _render_discussion_chat(messages)
        follow_up = st.text_area("继续讨论剧情段", key=input_key, height=120, placeholder="例如：这一段我想让冲突递进更快，但高潮不要提早透支。")
        if st.button("发送剧情段讨论消息", key=f"send_arc_discussion_{arc_no}"):
            if not follow_up.strip():
                st.warning("讨论消息不能为空。")
            else:
                try:
                    _append_discussion_message(messages_key, "user", follow_up)
                    messages = st.session_state.get(messages_key, [])
                    result = discuss_arc_turn(
                        project_name,
                        arc_no,
                        volume_no or None,
                        title,
                        summary,
                        estimated_chapter_count or None,
                        target_word_count_range,
                        requirement,
                        messages,
                        discussion_step.get("data", {}).get("discussion", {}),
                        follow_up,
                    )
                    st.session_state[result_key] = result
                    assistant_message = result.get("data", {}).get("assistant_message", "") or "我已经根据你的补充更新了剧情段讨论结论。"
                    _append_discussion_message(messages_key, "assistant", assistant_message)
                    st.session_state[clear_input_flag_key] = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"继续讨论失败：{exc}")

    if st.button("生成剧情段大纲", key=f"generate_arc_outline_{arc_no}"):
        try:
            result = generate_arc_outline(
                project_name,
                arc_no,
                volume_no or None,
                title,
                summary,
                estimated_chapter_count or None,
                target_word_count_range,
                requirement,
                status=status,
            )
            st.session_state[f"arc_outline_step_{arc_no}"] = result
            st.session_state[f"arc_outline_{arc_no}"] = result.get("data", {}).get("arc_outline", "")
            st.rerun()
        except Exception as exc:
            st.error(f"生成剧情段大纲失败：{exc}")

    outline_text = st.text_area("剧情段大纲内容", value=st.session_state.get(f"arc_outline_{arc_no}", existing_outline), height=500, key=f"arc_outline_editor_{arc_no}")

    col1, col2 = st.columns(2)
    if col1.button("保存剧情段大纲", key=f"save_arc_{arc_no}"):
        save_arc_outline(project_name, arc_no, outline_text)
        save_arc_metadata(project_name, arc_no, {
            "volume_no": volume_no or None,
            "title": title,
            "summary": summary,
            "status": status,
            "estimated_chapter_count": estimated_chapter_count or None,
            "target_word_count_range": target_word_count_range,
        })
        st.success(f"剧情段 {arc_no:03d} 已保存")
        st.rerun()
    if col2.button("删除剧情段", key=f"delete_arc_{arc_no}"):
        if delete_arc(project_name, arc_no):
            st.success(f"剧情段 {arc_no:03d} 已删除")
            st.rerun()
        else:
            st.warning("目标剧情段不存在。")

    arcs = list_arcs(project_name)
    if arcs:
        st.markdown("### 现有剧情段")
        for item in arcs:
            volume_label = f" / 第 {int(item.get('volume_no'))} 卷" if item.get("volume_no") else ""
            status_label = label_status(item.get("status", "draft"))
            approval_label = "已有批准讨论" if item.get("has_approved_discussion") else "暂无批准讨论"
            st.caption(f"剧情段 {int(item.get('arc_no', 0)):03d}{volume_label} / {item.get('title', '') or '未命名'} / 状态={status_label} / {approval_label}")

    chapter_inventory = list_chapter_inventory(project_name)
    linked_chapters = [
        item for item in chapter_inventory
        if ((item.get("metadata") or {}).get("arc_no") == arc_no)
    ]
    st.markdown("### 当前剧情段下的章节")
    if not linked_chapters:
        st.caption("当前剧情段下还没有归属章节。")
    else:
        for item in linked_chapters:
            chapter_no = int(item.get("chapter_no", 0))
            status_parts = []
            if item.get("has_outline"):
                status_parts.append("细纲")
            if item.get("has_content"):
                status_parts.append("正文")
            if item.get("has_review_markdown") or item.get("has_review_json"):
                status_parts.append("审阅")
            status_text = " / ".join(status_parts) if status_parts else "尚无内容"
            st.caption(f"第 {chapter_no} 章 / {status_text}")

    st.markdown("### 剧情段章节分配计划")
    saved_plan = load_arc_chapter_plan(project_name, arc_no)
    plan_col1, plan_col2 = st.columns(2)
    start_chapter_no = plan_col1.number_input(
        "起始章节编号",
        min_value=1,
        value=min([int(item.get("chapter_no", 1)) for item in linked_chapters], default=1),
        key=f"arc_plan_start_{arc_no}",
    )
    default_plan_count = int(metadata.get("estimated_chapter_count") or 5)
    plan_chapter_count = plan_col2.number_input(
        "计划章节数",
        min_value=1,
        value=max(default_plan_count, 1),
        key=f"arc_plan_count_{arc_no}",
    )
    plan_requirement = st.text_area("章节分配补充要求", height=120, key=f"arc_plan_requirement_{arc_no}")
    plan_step = st.session_state.get(f"arc_chapter_plan_step_{arc_no}", {})
    if st.button("生成剧情段章节分配计划", key=f"generate_arc_chapter_plan_{arc_no}"):
        try:
            result = generate_arc_chapter_plan(
                project_name,
                arc_no,
                int(start_chapter_no),
                int(plan_chapter_count),
                plan_requirement,
            )
            st.session_state[f"arc_chapter_plan_step_{arc_no}"] = result
            st.success("章节分配计划已生成并保存。")
            st.rerun()
        except Exception as exc:
            st.error(f"生成章节分配计划失败：{exc}")
    latest_plan = st.session_state.get(f"arc_chapter_plan_step_{arc_no}", {}).get("data", {}).get("report_markdown", "") or saved_plan.get("report_markdown", "")
    if latest_plan:
        with st.expander("当前剧情段章节分配计划", expanded=False):
            st.markdown(latest_plan)
            render_step_json_expander("章节分配结构化数据", saved_plan.get("plan", {}))
    render_step_validation(plan_step)
    render_step_retrieval(plan_step, "本次章节分配使用的检索上下文", get_retrieval_trace(f"arc_chapter_plan:{project_name}:{arc_no}"))

    render_step_validation(step_result)
    render_step_retrieval(step_result, "本次剧情段大纲生成使用的检索上下文", get_retrieval_trace(f"arc_outline:{project_name}:{arc_no}"))


def render_pipeline_page(project_name: str):
    st.subheader("一键流水线：细纲→写作→审阅→更新记忆")
    chapter_no = st.number_input("章节编号", min_value=1, value=1, key="pipeline_chapter_no")
    requirement = st.text_area("本章要求", height=200, key="pipeline_requirement")
    word_count = st.text_input(
        "目标字数（如 2500-3500）",
        value="2500-3500",
        key="pipeline_word_count"
    )

    if st.button("执行流水线"):
        with st.status("执行中..."):
            result = pipeline_plan_write_review_update(
                project_name, chapter_no, requirement, word_count
            )
        pipeline = result.get("pipeline", {})
        if result.get("success"):
            st.success("流水线完成")
        else:
            st.warning("流水线已完成，但存在失败或拒绝的步骤")
        if result.get("halted"):
            st.caption(f"流水线已暂停：{result.get('halt_reason', '-')}")

        steps_result = result.get("steps", {}) or pipeline.get("steps", {})

        st.subheader("执行状态")
        steps = [
            ("章节细纲", "chapter_outline"),
            ("写作正文", "write_chapter"),
            ("审阅", "review_chapter"),
            ("更新核心设定", "memory_update"),
        ]
        for label, key in steps:
            step_result = steps_result.get(key, {})
            step_status = step_result.get("status")
            if step_status == "completed":
                st.success(f"{label}：完成")
            elif step_status == "skipped":
                st.info(f"{label}：已跳过（前置步骤未完成）")
            else:
                st.error(f"{label}：{step_result.get('error', '未知错误')}")
            render_step_validation(step_result)

        st.subheader("结果预览")
        with st.expander("章节细纲", expanded=True):
            st.markdown(result.get("chapter_outline", "") or steps_result.get("chapter_outline", {}).get("data", {}).get("chapter_outline", "") or "（未生成）")
        with st.expander("章节正文", expanded=True):
            st.markdown(result.get("chapter", "") or steps_result.get("write_chapter", {}).get("data", {}).get("chapter", "") or "（未生成）")
        with st.expander("审阅报告", expanded=True):
            st.markdown(result.get("review_markdown", "") or steps_result.get("review_chapter", {}).get("data", {}).get("review_markdown", "") or "（未生成）")
        review = result.get("review") or steps_result.get("review_chapter", {}).get("data", {}).get("review") or {}
        if review:
            st.caption("结构化审阅状态")
            cols = st.columns(3)
            cols[0].metric("状态", label_status(review.get("status", "-")))
            cols[1].metric("问题数", len(review.get("issues", [])))
            cols[2].metric("优点数", len(review.get("strengths", [])))
            with st.expander("审阅结构化数据", expanded=False):
                st.code(json.dumps(review, ensure_ascii=False, indent=2), language="json")
        render_step_json_expander("核心设定更新结果", result.get("memory_update") or steps_result.get("memory_update", {}))
        render_step_json_expander("流水线状态对象", result)

        transitions = result.get("transition_log", [])
        if transitions:
            with st.expander("状态迁移记录", expanded=False):
                for index, item in enumerate(transitions, start=1):
                    st.markdown(
                        f"{index}. {label_step_name(item.get('from_step', '-'))} -> {label_step_name(item.get('to_step', '-'))} / {item.get('timestamp', '-')}"
                    )
                    if item.get("reason"):
                        st.caption(item.get("reason"))

        workflow_errors = result.get("errors", [])
        if workflow_errors:
            with st.expander("工作流错误记录", expanded=False):
                for index, item in enumerate(workflow_errors, start=1):
                    st.markdown(
                        f"{index}. 步骤={label_step_name(item.get('step_name', '-'))} / 类型={label_error_type(item.get('error_type', 'unknown'))} / 可恢复={label_yes_no(bool(item.get('recoverable', True)))}"
                    )
                    st.caption(item.get("message", ""))

        if result.get("resumable"):
            st.info(f"该运行具备恢复潜力，可从“{label_step_name(result.get('last_successful_step', '-'))}”之后继续。")

        render_step_retrieval(steps_result.get("chapter_outline", {}), "流水线：细纲步骤使用的检索上下文")
        render_step_retrieval(steps_result.get("write_chapter", {}), "流水线：写作步骤使用的检索上下文")
        render_step_retrieval(steps_result.get("review_chapter", {}), "流水线：审阅步骤使用的检索上下文")
        render_step_retrieval(steps_result.get("memory_update", {}), "流水线：核心设定更新步骤使用的检索上下文")

    st.subheader("最近运行记录")
    run_ids = list_pipeline_runs(project_name, chapter_no)
    if not run_ids:
        st.caption("当前章节还没有运行记录。")
        return

    selected_run = st.selectbox("选择运行记录", options=run_ids, key=f"pipeline_run_select_{chapter_no}")
    if selected_run:
        run_content = load_pipeline_run(project_name, selected_run)
        if run_content.strip():
            run_data = json.loads(run_content)
            st.caption(
                f"运行编号={run_data.get('run_id', '-')} / 开始时间={run_data.get('started_at', '-')} / 结束时间={run_data.get('finished_at', '-')} / 可恢复={label_yes_no(bool(run_data.get('resumable', False)))}"
            )
            if run_data.get("halted"):
                st.warning(f"暂停原因：{run_data.get('halt_reason', '-')}")
            if run_data.get("resumable"):
                if st.button("从该运行恢复流水线", key=f"resume_pipeline_{selected_run}"):
                    try:
                        with st.spinner("正在恢复流水线..."):
                            resumed = resume_chapter_pipeline(project_name, selected_run)
                        st.success(f"已生成恢复运行：{resumed.get('run_id', '')}")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"恢复流水线失败：{exc}")
            transitions = run_data.get("transition_log", [])
            if transitions:
                with st.expander("该运行的状态迁移记录", expanded=False):
                    for index, item in enumerate(transitions, start=1):
                        st.markdown(
                            f"{index}. {label_step_name(item.get('from_step', '-'))} -> {label_step_name(item.get('to_step', '-'))} / {item.get('timestamp', '-')}"
                        )
                        if item.get("reason"):
                            st.caption(item.get("reason"))
            workflow_errors = run_data.get("errors", [])
            if workflow_errors:
                with st.expander("该运行的错误记录", expanded=False):
                    for index, item in enumerate(workflow_errors, start=1):
                        st.markdown(
                            f"{index}. 步骤={label_step_name(item.get('step_name', '-'))} / 类型={label_error_type(item.get('error_type', 'unknown'))} / 可恢复={label_yes_no(bool(item.get('recoverable', True)))}"
                        )
                        st.caption(item.get("message", ""))
            render_step_json_expander("运行记录状态对象", run_data)


def render_analysis_page(project_name: str):
    st.subheader("一致性分析")

    chapter_no = st.number_input("章节编号", min_value=1, value=1, key="analysis_chapter_no")
    existing_chapter = load_chapter(project_name, chapter_no)
    chapter_text_key = f"analysis_chapter_text_{chapter_no}"
    chapter_text = st.text_area(
        "待分析正文",
        value=existing_chapter,
        height=400,
        key=chapter_text_key
    )

    analysis_options = {
        "consistency": ("总一致性检查", run_consistency_check),
        "characters": ("角色分析", analyze_characters),
        "timeline": ("时间线分析", analyze_timeline),
        "foreshadowing": ("伏笔分析", analyze_foreshadowing),
    }

    selected_type = st.selectbox(
        "分析类型",
        options=list(analysis_options.keys()),
        format_func=lambda key: analysis_options[key][0],
        key="analysis_type"
    )

    report_text_key = f"analysis_result_text_{selected_type}_{chapter_no}"
    existing_report = load_analysis_report(project_name, selected_type, chapter_no)
    step_state_key = f"analysis_step_{selected_type}_{chapter_no}"

    if st.button("执行分析"):
        try:
            label, handler = analysis_options[selected_type]
            with st.spinner(f"正在生成{label}..."):
                result = handler(project_name, chapter_no, chapter_text)
            report = result.get("data", {}).get("report_markdown", "")
            st.session_state[f"analysis_{selected_type}_{chapter_no}"] = report
            st.session_state[report_text_key] = report
            st.session_state[step_state_key] = result
            st.rerun()
        except Exception as exc:
            st.error(f"执行分析失败：{exc}")

    report_text = st.text_area(
        "分析结果",
        value=st.session_state.get(f"analysis_{selected_type}_{chapter_no}", existing_report),
        height=450,
        key=report_text_key
    )

    if report_text:
        st.markdown(report_text)

    analysis_step = st.session_state.get(step_state_key, {})
    analysis_data = analysis_step.get("data", {}).get("analysis") or {}
    render_step_json_expander("结构化分析结果", analysis_data)
    render_step_validation(analysis_step)
    render_step_retrieval(
        analysis_step,
        "本次分析使用的检索上下文",
        get_retrieval_trace(f"analysis:{selected_type}:{project_name}:{chapter_no}")
    )


def render_evaluation_page(project_name: str):
    st.subheader("章节评估")

    chapter_no = st.number_input("章节编号", min_value=1, value=1, key="evaluation_chapter_no")
    existing_chapter = load_chapter(project_name, chapter_no)
    chapter_text = st.text_area(
        "待评估正文",
        value=existing_chapter,
        height=420,
        key=f"evaluation_chapter_text_{chapter_no}",
    )
    step_key = f"evaluation_step_{chapter_no}"
    report_key = f"evaluation_report_{chapter_no}"
    existing_report = load_evaluation_report(project_name, chapter_no)
    existing_json = load_evaluation_json(project_name, chapter_no) or {}

    if st.button("执行章节评估"):
        try:
            with st.spinner("正在生成章节质量评估..."):
                result = evaluate_chapter(project_name, chapter_no, chapter_text)
            report = result.get("data", {}).get("report_markdown", "")
            st.session_state[step_key] = result
            st.session_state[report_key] = report
            st.rerun()
        except Exception as exc:
            st.error(f"章节评估失败：{exc}")

    report_text = st.text_area(
        "评估报告",
        value=st.session_state.get(report_key, existing_report),
        height=460,
        key=f"evaluation_report_text_{chapter_no}",
    )
    if report_text:
        st.markdown(report_text)

    evaluation_step = st.session_state.get(step_key, {})
    evaluation_payload = evaluation_step.get("data", {}).get("evaluation") or existing_json
    if evaluation_payload:
        cols = st.columns(4)
        cols[0].metric("总分", evaluation_payload.get("overall_score", 0))
        cols[1].metric("剧情推进", evaluation_payload.get("plot_progression_score", 0))
        cols[2].metric("角色一致性", evaluation_payload.get("character_consistency_score", 0))
        cols[3].metric("文笔质量", evaluation_payload.get("prose_quality_score", 0))
        render_step_json_expander("评估结构化数据", evaluation_payload)
    render_step_validation(evaluation_step)
    render_step_retrieval(
        evaluation_step,
        "本次评估使用的检索上下文",
        get_retrieval_trace(f"evaluation:chapter:{project_name}:{chapter_no}")
    )


def render_retrieval_hits_block(hits: list[dict], title: str):
    if not hits:
        return

    with st.expander(title, expanded=False):
        grouped = {"project": {}, "canon": {}, "reference": {}}
        for hit in hits:
            chunk = hit.get("chunk", {})
            scope = chunk.get("scope", "project") or "project"
            source_type = chunk.get("source_type", "unknown") or "unknown"
            grouped.setdefault(scope, {}).setdefault(source_type, []).append(hit)

        hit_index = 1
        for scope in ["project", "canon", "reference"]:
            source_groups = grouped.get(scope, {})
            if not source_groups:
                continue
            st.markdown(f"## {label_scope(scope)}")
            for source_type, source_hits in source_groups.items():
                st.markdown(f"### {label_source_type(source_type)}")
                for hit in source_hits:
                    chunk = hit.get("chunk", {})
                    st.markdown(
                        f"#### [{hit_index}] 检索方式={label_retrieval_mode(hit.get('retrieval_mode', 'lexical'))} / 相关度={hit.get('score', 0):.2f}"
                    )
                    if chunk.get("title"):
                        st.caption(chunk.get("title"))
                    matched_terms = hit.get("matched_terms", [])
                    authority = label_authority(chunk.get("metadata", {}).get("authority", "unknown"))
                    if matched_terms:
                        st.caption(f"命中词：{', '.join(matched_terms)}")
                    st.caption(
                        f"可信度={authority} / 关键词分={hit.get('lexical_score', 0):.2f} / 语义分={hit.get('semantic_score', 0):.2f} / 来源={chunk.get('path', '-') }"
                    )
                    st.write(chunk.get("content", ""))
                    hit_index += 1

        potential_conflicts = detect_potential_conflicts(hits)
        if potential_conflicts:
            st.markdown("## 潜在冲突")
            for index, conflict in enumerate(potential_conflicts, start=1):
                shared_terms = ", ".join(conflict.get("shared_terms", [])) or "(无)"
                project_chunk = conflict.get("project_hit", {}).get("chunk", {})
                external_chunk = conflict.get("external_hit", {}).get("chunk", {})
                project_authority = label_authority(conflict.get("project_authority", project_chunk.get("metadata", {}).get("authority", "project")))
                external_authority = label_authority(conflict.get("external_authority", external_chunk.get("metadata", {}).get("authority", "unknown")))
                severity = SEVERITY_LABELS.get(conflict.get("severity", "low"), conflict.get("severity", "low"))
                rationale = conflict.get("rationale", "")
                st.markdown(f"### [{index}] 严重程度={severity} / 共同命中词={shared_terms}")
                st.caption(
                    f"项目资料：{label_source_type(project_chunk.get('source_type', 'unknown'))} / {project_chunk.get('title', '未命名')} / 可信度={project_authority}"
                )
                st.caption(
                    f"外部资料：{label_scope(external_chunk.get('scope', 'reference'))} / {label_source_type(external_chunk.get('source_type', 'unknown'))} / {external_chunk.get('title', '未命名')} / 可信度={external_authority}"
                )
                if rationale:
                    st.caption(f"判断理由：{rationale}")


def render_retrieval_page(project_name: str, mode: str = "center"):
    if mode == "ingestion":
        st.subheader("资料录入")
        st.caption("导入原作资料、参考资料和样本文本，并把资料整理为检索条目或结构化知识。")
    else:
        st.subheader("检索中心")
        st.caption("管理检索索引、测试资料召回，并处理项目资料与原作/参考资料之间的潜在冲突。")

    source_type_options = {
        "external_source": "通用资料",
        "external_character_sheet": "角色资料",
        "external_location_sheet": "地点资料",
        "external_organization_sheet": "组织资料",
        "external_timeline_note": "时间线资料",
        "external_canon_event": "原作事件",
        "external_world_rule": "世界规则",
        "external_artifact_note": "道具资料",
    }
    knowledge_category_options = list(KNOWLEDGE_CATEGORY_LABELS.keys())

    def _import_organized_reference_entries(organized_result: dict, scope: str, authority: str, origin: str):
        entries = organized_result.get("entries", [])
        imported = 0
        for index, entry in enumerate(entries, start=1):
            payload = build_structured_external_source_payload(
                source_type=entry.get("source_type", "external_source"),
                scope=scope,
                title=entry.get("title", f"entry_{index}"),
                summary=entry.get("summary", ""),
                content=entry.get("content", ""),
                tags=entry.get("tags", []),
                metadata={
                    "authority": authority,
                    "source_origin": origin,
                    "organized_from_reference": True,
                },
                extra_fields=entry.get("extra_fields", {}),
            )
            entry_name = f"{organized_result.get('source_title', 'reference')}_{index:02d}"
            ingest_external_source_file(project_name, entry_name, json.dumps(payload, ensure_ascii=False, indent=2))
            imported += 1
        if imported:
            rebuild_retrieval_assets(project_name, build_vectors=True)
        return imported

    manifest = None
    if mode == "center":
        try:
            manifest = load_retrieval_index(project_name)
            st.caption(
                f"当前索引：{manifest.document_count} 份文档 / {manifest.chunk_count} 个片段 / 构建时间 {manifest.built_at} / 语义向量={'已启用' if manifest.embedding_enabled else '未启用'} / 模型={manifest.embedding_model or '-'}"
            )
        except Exception as exc:
            st.warning(f"索引读取失败：{exc}")

        col1, col2 = st.columns(2)
        if col1.button("重建检索索引"):
            with st.spinner("正在重建索引..."):
                manifest = rebuild_retrieval_assets(project_name, build_vectors=True)
            st.success(
                f"索引已重建：{manifest.document_count} 份文档 / {manifest.chunk_count} 个片段 / 语义向量={'已启用' if manifest.embedding_enabled else '未启用'}"
            )
            st.rerun()

        source_dir = retrieval_sources_path(project_name)
        col2.caption(f"外部资料目录：`{source_dir}`")

        with st.expander("管理已导入资料", expanded=False):
            existing_source_files = list_retrieval_source_files(project_name)
            if not existing_source_files:
                st.caption("当前没有已导入的外部资料文件。")
            else:
                selected_source_file = st.selectbox(
                    "选择要删除的资料文件",
                    options=existing_source_files,
                    key="retrieval_source_delete_target"
                )
                st.caption("删除后会自动重建检索索引。")
                if st.button("删除所选资料"):
                    try:
                        deleted = delete_retrieval_source_file(project_name, selected_source_file)
                        if deleted:
                            rebuild_retrieval_assets(project_name, build_vectors=True)
                            st.success(f"已删除资料：{selected_source_file}")
                            st.rerun()
                        else:
                            st.warning("目标资料不存在，可能已被删除。")
                    except Exception as exc:
                        st.error(f"删除资料失败：{exc}")

    if mode == "ingestion":
        source_dir = retrieval_sources_path(project_name)
        st.caption(f"外部资料保存目录：`{source_dir}`")
        render_pending_knowledge_queue(project_name)
        render_long_reference_batch_manager(project_name, knowledge_category_options)
        render_knowledge_organizer(project_name, knowledge_category_options)
        render_source_package_report_page(project_name)
        render_long_reference_importer(project_name, source_type_options, knowledge_category_options)

    if mode == "ingestion":
        with st.expander("添加外部资料", expanded=False):
            source_name = st.text_input("资料名称", key="retrieval_source_name")
            source_scope = st.selectbox("资料范围", options=["reference", "canon"], format_func=label_scope, key="retrieval_source_scope")
            source_authority = st.selectbox(
                "资料可信度",
                options=["official", "curated", "community", "unknown"],
                index=1,
                format_func=label_authority,
                key="retrieval_source_authority"
            )
            source_origin = st.text_input("来源标识/链接（可选）", key="retrieval_source_origin")
            source_type = st.selectbox(
                "资料模板",
                options=list(source_type_options.keys()),
                format_func=lambda key: source_type_options.get(key, label_source_type(key)),
                key="retrieval_source_type"
            )
            source_title = st.text_input("显示标题（可选）", key="retrieval_source_title")
            source_summary = st.text_area("资料摘要（可选）", height=100, key="retrieval_source_summary")
            source_tags = st.text_input("标签（逗号分隔，可选）", key="retrieval_source_tags")
            source_content = st.text_area("资料正文", height=220, key="retrieval_source_content")

            col_a, col_b = st.columns(2)
            extra_field_1_label = col_a.text_input("扩展字段1名称（可选）", key="retrieval_extra_label_1")
            extra_field_1_value = col_a.text_area("扩展字段1内容", height=90, key="retrieval_extra_value_1")
            extra_field_2_label = col_b.text_input("扩展字段2名称（可选）", key="retrieval_extra_label_2")
            extra_field_2_value = col_b.text_area("扩展字段2内容", height=90, key="retrieval_extra_value_2")

            if st.button("保存外部资料"):
                if not source_name.strip() or not source_content.strip():
                    st.error("资料名称和资料正文不能为空。")
                else:
                    tags = [item.strip() for item in source_tags.split(",") if item.strip()]
                    extra_fields = {}
                    if extra_field_1_label.strip() and extra_field_1_value.strip():
                        extra_fields[extra_field_1_label.strip()] = extra_field_1_value.strip()
                    if extra_field_2_label.strip() and extra_field_2_value.strip():
                        extra_fields[extra_field_2_label.strip()] = extra_field_2_value.strip()

                    payload = build_structured_external_source_payload(
                        source_type=source_type,
                        scope=source_scope,
                        title=source_title.strip() or source_name.strip(),
                        summary=source_summary,
                        content=source_content,
                        tags=tags,
                        metadata={
                            "added_from_ui": True,
                            "template": source_type,
                            "authority": source_authority,
                            "source_origin": source_origin.strip(),
                        },
                        extra_fields=extra_fields,
                    )
                    ingest_external_source_file(project_name, source_name, json.dumps(payload, ensure_ascii=False, indent=2))
                    rebuild_retrieval_assets(project_name, build_vectors=True)
                    st.success("外部资料已保存并重建索引。")
                    st.rerun()

    if mode == "ingestion":
        with st.expander("整理粘贴资料并导入", expanded=False):
            paste_title = st.text_input("资料标题", key="organized_reference_title")
            paste_scope = st.selectbox("资料范围", options=["canon", "reference"], format_func=label_scope, key="organized_reference_scope")
            paste_authority = st.selectbox(
                "资料可信度",
                options=["official", "curated", "community", "unknown"],
                index=1,
                format_func=label_authority,
                key="organized_reference_authority"
            )
            paste_origin = st.text_input("来源说明（可选）", key="organized_reference_origin")
            paste_text = st.text_area("粘贴原始资料", height=240, key="organized_reference_text")

            if st.button("整理粘贴资料"):
                if not paste_text.strip():
                    st.error("请先粘贴原始资料。")
                else:
                    try:
                        result = organize_reference_text(project_name, paste_title, paste_text)
                        st.session_state["organized_reference_result"] = result
                    except Exception as exc:
                        st.error(f"整理失败：{exc}")

            organized_result = st.session_state.get("organized_reference_result", {})
            organized_payload = organized_result.get("data", {}).get("organized_reference", {})
            if organized_payload:
                st.markdown(organized_result.get("data", {}).get("report_markdown", ""))
                render_step_validation(organized_result)
                render_step_json_expander("整理结果结构化数据", organized_payload)
                if st.button("将整理结果导入资料索引"):
                    imported = _import_organized_reference_entries(organized_payload, paste_scope, paste_authority, paste_origin)
                    st.success(f"已导入 {imported} 条资料并重建索引。")
                    st.rerun()

    if mode == "ingestion":
        with st.expander("从网页链接抓取并整理资料", expanded=False):
            url_value = st.text_input("页面链接", key="reference_url_input")
            parsed_url = urlparse(url_value.strip()) if url_value.strip() else None
            default_url_title = parsed_url.netloc if parsed_url and parsed_url.netloc else ""
            url_title = st.text_input("页面标题（可选）", value=default_url_title, key="reference_url_title")
            url_scope = st.selectbox("网页资料范围", options=["canon", "reference"], format_func=label_scope, key="reference_url_scope")
            url_authority = st.selectbox(
                "网页资料可信度",
                options=["official", "curated", "community", "unknown"],
                index=0,
                format_func=label_authority,
                key="reference_url_authority"
            )

            if st.button("抓取并整理网页资料"):
                if not url_value.strip():
                    st.error("页面链接不能为空。")
                else:
                    try:
                        result = organize_reference_url(project_name, url_title or default_url_title or url_value.strip(), url_value.strip())
                        st.session_state["organized_reference_url_result"] = result
                    except Exception as exc:
                        st.error(f"抓取或整理失败：{exc}")

            organized_url_result = st.session_state.get("organized_reference_url_result", {})
            organized_url_payload = organized_url_result.get("data", {}).get("organized_reference", {})
            if organized_url_payload:
                st.markdown(organized_url_result.get("data", {}).get("report_markdown", ""))
                render_step_validation(organized_url_result)
                render_step_json_expander("网页整理结构化数据", organized_url_payload)
                artifacts = organized_url_result.get("artifacts", {})
                if artifacts.get("source_url"):
                    st.caption(f"来源链接：{artifacts.get('source_url')}")
                if st.button("将网页整理结果导入资料索引"):
                    imported = _import_organized_reference_entries(
                        organized_url_payload,
                        url_scope,
                        url_authority,
                        artifacts.get("source_url", url_value.strip()),
                    )
                    st.success(f"已导入 {imported} 条网页资料并重建索引。")
                    st.rerun()

    if mode == "ingestion":
        with st.expander("提取结构化知识并保存", expanded=False):
            st.caption("适合把原作资料、参考资料或样本文风拆成角色、物品能力、世界观、时间线、文风等知识。提取结果会先预览，确认后才写入结构化知识。")
            knowledge_title = st.text_input("资料标题", key="knowledge_extract_title")
            knowledge_scope = st.selectbox("知识范围", options=["canon", "reference", "project"], index=0, format_func=label_scope, key="knowledge_extract_scope")
            knowledge_authority = st.selectbox(
                "知识可信度",
                options=["official", "curated", "community", "project", "unknown"],
                index=1,
                format_func=label_authority,
                key="knowledge_extract_authority",
            )
            knowledge_origin = st.text_input("来源说明（可选）", key="knowledge_extract_origin")
            enabled_categories = st.multiselect(
                "提取分类",
                options=knowledge_category_options,
                default=["characters", "items", "abilities", "world_rules", "timeline_events", "writing_style", "dialogue_style", "constraints"],
                format_func=label_knowledge_category,
                key="knowledge_extract_categories",
            )
            knowledge_text = st.text_area("原始资料", height=260, key="knowledge_extract_text")

            if st.button("提取结构化知识"):
                if not knowledge_text.strip():
                    st.error("请先粘贴原始资料。")
                elif not enabled_categories:
                    st.error("请至少选择一个提取分类。")
                else:
                    try:
                        result = extract_reference_knowledge(project_name, knowledge_title, knowledge_text, enabled_categories)
                        st.session_state["knowledge_extraction_result"] = result
                    except Exception as exc:
                        st.error(f"知识提取失败：{exc}")

            extraction_result = st.session_state.get("knowledge_extraction_result", {})
            extraction_payload = extraction_result.get("data", {}).get("knowledge_extraction", {})
            extraction_items = extraction_payload.get("items", []) if isinstance(extraction_payload, dict) else []
            if extraction_payload:
                st.markdown(extraction_result.get("data", {}).get("report_markdown", ""))
                render_step_validation(extraction_result)
                render_step_json_expander("知识提取结构化数据", extraction_payload)
            if extraction_items:
                item_options = list(range(len(extraction_items)))
                selected_item_indices = st.multiselect(
                    "选择要保存的知识条目",
                    options=item_options,
                    default=item_options,
                    format_func=lambda index: f"{index + 1}. {label_knowledge_category(extraction_items[index].get('category', ''))} / {extraction_items[index].get('name', '未命名')}",
                    key="knowledge_extract_selected_items",
                )
                col_queue, col_direct = st.columns(2)
                if col_queue.button("加入待确认队列"):
                    selected_items = [extraction_items[index] for index in selected_item_indices]
                    queued_count = queue_pending_knowledge_items(
                        project_name,
                        selected_items,
                        scope=knowledge_scope,
                        authority=knowledge_authority,
                        source_title=extraction_payload.get("source_title", "") or knowledge_title,
                        source_origin=knowledge_origin,
                    )
                    st.success(f"已加入 {queued_count} 条待确认知识。")
                    st.rerun()
                if col_direct.button("直接保存所选知识"):
                    selected_items = [extraction_items[index] for index in selected_item_indices]
                    saved_count = append_knowledge_items(
                        project_name,
                        selected_items,
                        scope=knowledge_scope,
                        authority=knowledge_authority,
                        source_title=extraction_payload.get("source_title", "") or knowledge_title,
                        source_origin=knowledge_origin,
                    )
                    rebuild_retrieval_assets(project_name, build_vectors=True)
                    st.success(f"已保存 {saved_count} 条结构化知识，并重建检索索引。")
                    st.rerun()

        knowledge_base = load_knowledge_base(project_name)
        knowledge_count = sum(len(items) for items in knowledge_base.values())
        with st.expander("结构化知识预览", expanded=False):
            if not knowledge_count:
                st.caption("当前还没有保存结构化知识。")
            else:
                for category, items in knowledge_base.items():
                    if not items:
                        continue
                    st.markdown(f"### {label_knowledge_category(category)}（{len(items)}）")
                    for item in items[:8]:
                        st.caption(f"{item.get('name', '未命名')} / {item.get('summary', '')[:80]}")
                    if len(items) > 8:
                        st.caption(f"仅显示前 8 条，共 {len(items)} 条。")
        return

    if manifest and manifest.documents:
        with st.expander("索引来源预览", expanded=False):
            for doc in manifest.documents[:30]:
                st.markdown(f"- `{label_source_type(doc.source_type)}` / `{label_scope(doc.scope)}` / `{doc.title or doc.doc_id}`")
            if len(manifest.documents) > 30:
                st.caption(f"仅显示前 30 项，共 {len(manifest.documents)} 项。")

    with st.expander("检索预览", expanded=True):
        query = st.text_area("检索查询", height=120, key="retrieval_query")
        top_k = st.slider("返回条数", min_value=1, max_value=12, value=6, key="retrieval_top_k")
        retrieval_mode = st.selectbox(
            "检索模式",
            options=["hybrid", "lexical", "semantic"],
            index=0,
            format_func=label_retrieval_mode,
            key="retrieval_mode"
        )
        scope_options = st.multiselect(
            "范围过滤",
            options=["project", "canon", "reference"],
            default=["project", "canon", "reference"],
            format_func=label_scope,
            key="retrieval_scope_filter"
        )
        source_type_candidates = sorted({chunk.source_type for chunk in manifest.chunks}) if manifest else []
        source_type_filter = st.multiselect(
            "来源类型过滤（可选）",
            options=source_type_candidates,
            default=[],
            format_func=label_source_type,
            key="retrieval_source_type_filter",
        )
        include_debug = st.checkbox("生成检索调试信息", value=False, key="retrieval_include_debug")
        if st.button("执行检索"):
            try:
                hits = retrieve_context(
                    project_name,
                    query,
                    top_k=top_k,
                    allowed_scopes=scope_options,
                    allowed_source_types=source_type_filter or None,
                    retrieval_mode=retrieval_mode,
                )
                st.session_state["retrieval_hits"] = [hit.model_dump() for hit in hits]
                st.session_state["retrieval_debug"] = debug_retrieve_context(
                    project_name,
                    query,
                    top_k=top_k,
                    allowed_scopes=scope_options,
                    allowed_source_types=source_type_filter or None,
                    retrieval_mode=retrieval_mode,
                ) if include_debug else {}
            except Exception as exc:
                st.error(f"检索失败：{exc}")

        current_hits = st.session_state.get("retrieval_hits", [])
        for hit in current_hits:
            chunk = hit.get("chunk", {})
            st.markdown(
                f"### {label_source_type(chunk.get('source_type', 'unknown'))} / {label_scope(chunk.get('scope', 'project'))} / 检索方式={label_retrieval_mode(hit.get('retrieval_mode', 'lexical'))} / 相关度={hit.get('score', 0):.2f}"
            )
            if chunk.get("title"):
                st.caption(chunk.get("title"))
            st.write(chunk.get("content", ""))
            matched_terms = hit.get("matched_terms", [])
            if matched_terms:
                st.caption(f"命中词：{', '.join(matched_terms)}")
            st.caption(
                f"关键词分={hit.get('lexical_score', 0):.2f} / 语义分={hit.get('semantic_score', 0):.2f} / 来源={chunk.get('path', '-') }"
            )

        debug_payload = st.session_state.get("retrieval_debug", {})
        if debug_payload:
            with st.expander("检索调试信息", expanded=False):
                st.caption(
                    f"检索词={', '.join(debug_payload.get('query_terms', [])) or '-'} / 候选片段={debug_payload.get('candidate_chunk_count', 0)} / 语义向量={'已启用' if debug_payload.get('semantic_enabled', False) else '未启用'}"
                )
                st.markdown("### 重排前")
                for index, hit in enumerate(debug_payload.get("initial_hits", []), start=1):
                    chunk = hit.get("chunk", {})
                    st.caption(f"{index}. {label_source_type(chunk.get('source_type', 'unknown'))} / {chunk.get('title', '')} / 相关度={hit.get('score', 0):.2f}")
                st.markdown("### 重排后")
                for index, hit in enumerate(debug_payload.get("reranked_hits", []), start=1):
                    chunk = hit.get("chunk", {})
                    st.caption(f"{index}. {label_source_type(chunk.get('source_type', 'unknown'))} / {chunk.get('title', '')} / 相关度={hit.get('score', 0):.2f}")
                render_step_json_expander("完整调试结构化数据", debug_payload)

        conflicts = detect_potential_conflicts(current_hits)
        if conflicts:
            st.markdown("### 检索冲突裁决")
            for index, conflict in enumerate(conflicts, start=1):
                project_chunk = conflict.get("project_hit", {}).get("chunk", {})
                external_chunk = conflict.get("external_hit", {}).get("chunk", {})
                severity = SEVERITY_LABELS.get(conflict.get("severity", "low"), conflict.get("severity", "low"))
                with st.expander(f"冲突 {index} / 严重程度={severity}", expanded=False):
                    st.caption(f"共同命中词：{', '.join(conflict.get('shared_terms', [])) or '-'}")
                    st.markdown(f"**项目证据**：{label_source_type(project_chunk.get('source_type', 'unknown'))} / {project_chunk.get('title', '未命名')}")
                    st.write(project_chunk.get("content", ""))
                    st.markdown(f"**外部证据**：{label_source_type(external_chunk.get('source_type', 'unknown'))} / {external_chunk.get('title', '未命名')}")
                    st.write(external_chunk.get("content", ""))
                    decision = st.selectbox(
                        "裁决",
                        options=["merge", "use_project", "use_external", "ignore"],
                        format_func=lambda value: DECISION_LABELS.get(value, value),
                        key=f"conflict_decision_{index}",
                    )
                    note = st.text_area("裁决说明", height=80, key=f"conflict_note_{index}")
                    if st.button("保存该冲突裁决", key=f"save_conflict_resolution_{index}"):
                        try:
                            saved = save_retrieval_conflict_resolution(project_name, conflict, decision, note)
                            st.success(f"已保存裁决：{saved.get('conflict_id', '')}")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"保存裁决失败：{exc}")

        resolutions = load_conflict_resolutions(project_name)
        if resolutions:
            with st.expander("已保存冲突裁决", expanded=False):
                st.code(json.dumps(resolutions, ensure_ascii=False, indent=2), language="json")


st.set_page_config(page_title="NovelForge", layout="wide")
st.title("NovelForge：同人小说创作工作台")

project_name = init_project_state()
projects = list_projects()
render_sidebar(project_name, projects)

if project_name:
    memory = load_memory(project_name)
    st.caption(f"当前项目：`{project_name}`")
else:
    memory = None
    st.info("当前还没有项目。可先进入“模型配置”填写服务地址与密钥，或点击侧边栏“新建项目”开始创建。")

page = st.sidebar.radio(
    "项目管理",
    ["项目总览", "创作配置", "动态生成", "项目资源", "核心设定", "资料录入", "检索中心", "交互规则", "模型配置", "生成大纲", "分卷大纲", "剧情段大纲", "生成细纲", "写章节", "章节审阅", "一致性分析", "章节评估", "一键流水线", "文件预览"]
)

if not project_name and page != "模型配置":
    st.stop()
elif page == "模型配置":
    render_llm_settings_page()
elif page == "项目总览":
    render_project_overview_page(project_name)
elif page == "创作配置":
    render_creative_profile_page(project_name)
elif page == "动态生成":
    render_dynamic_generation_page(project_name)
elif page == "项目资源":
    render_resource_management_page(project_name)
elif page == "核心设定":
    render_memory_page(project_name, memory)
elif page == "资料录入":
    render_retrieval_page(project_name, mode="ingestion")
elif page == "检索中心":
    render_retrieval_page(project_name, mode="center")
elif page == "交互规则":
    render_rules_page(project_name)
elif page == "生成大纲":
    render_outline_page(project_name)
elif page == "分卷大纲":
    render_volume_outline_page(project_name)
elif page == "剧情段大纲":
    render_arc_outline_page(project_name)
elif page == "生成细纲":
    render_chapter_outline_page(project_name)
elif page == "写章节":
    render_chapter_page(project_name)
elif page == "章节审阅":
    render_review_page(project_name)
elif page == "一致性分析":
    render_analysis_page(project_name)
elif page == "章节评估":
    render_evaluation_page(project_name)
elif page == "一键流水线":
    render_pipeline_page(project_name)
elif page == "文件预览":
    render_project_files_page(project_name)
