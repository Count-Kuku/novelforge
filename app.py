import json
import hashlib
import html

import streamlit as st
from urllib.parse import urlparse

from llm import PROVIDER_PRESETS, test_llm_connection

from memory import (
    load_chapter_discussion_artifact,
    create_project,
    create_story,
    delete_llm_profile,
    delete_long_reference_batch,
    delete_arc,
    delete_retrieval_source_file,
    delete_volume,
    get_active_llm_profile,
    get_active_story_id,
    rename_story,
    list_stories,
    load_arc_discussion_artifact,
    list_arcs,
    load_arc_metadata,
    load_arc_chapter_plan,
    load_arc_outline,
    load_chapter_outline_metadata,
    load_conflict_resolutions,
    load_retrieval_eval_cases,
    load_retrieval_eval_runs,
    load_retrieval_feedback,
    load_evaluation_json,
    load_evaluation_report,
    load_global_rules,
    load_creative_profile,
    load_knowledge_base,
    load_knowledge_category,
    load_auto_review_runs,
    load_auto_review_policy,
    load_character_entities,
    load_entity_aliases,
    load_extraction_plan_templates,
    load_setting_entities,
    load_source_package_report,
    load_long_reference_batch,
    load_pending_knowledge_items,
    list_projects,
    list_long_reference_batches,
    list_retrieval_source_files,
    list_volumes,
    load_chapter,
    load_chapter_outline,
    creative_profile_path,
    load_memory,
    load_outline,
    load_outline_discussion_artifact,
    load_llm_settings,
    load_llm_profiles,
    load_project_rules,
    load_rule_conflict_resolutions,
    load_story_memory,
    load_story_rules,
    load_volume_discussion_artifact,
    load_volume_metadata,
    load_volume_outline,
    migrate_project_to_stories,
    save_chapter,
    save_creative_profile,
    save_source_package_report,
    save_long_reference_batch,
    save_chapter_outline,
    save_chapter_outline_metadata,
    save_global_rules,
    save_memory,
    save_story_memory,
    save_character_entities,
    save_auto_review_policy,
    save_entity_aliases,
    save_extraction_plan_templates,
    save_setting_entities,
    confirm_pending_knowledge_items,
    copy_story_settings,
    merge_story_to_project_memory,
    merge_project_to_story_memory,
    merge_story_rules_to_project,
    merge_project_rules_to_story,
    merge_project_rules_to_global,
    merge_story_rules_to_global,
    merge_global_rules_to_project,
    merge_global_rules_to_story,
    discard_pending_knowledge_items,
    rollback_auto_review_run,
    restore_auto_review_snapshots_to_pending,
    return_confirmed_knowledge_item_to_pending,
    queue_pending_knowledge_items,
    save_pending_knowledge_items,
    upsert_retrieval_eval_case,
    delete_retrieval_eval_case,
    append_retrieval_feedback,
    save_outline,
    save_project_rules,
    save_story_rules,
    add_rule_conflict_resolution,
    delete_rule_conflict_resolution,
    create_long_reference_batch,
    set_active_llm_profile,
    set_active_story,
    save_arc_metadata,
    save_arc_outline,
    save_volume_metadata,
    save_volume_outline,
    upsert_llm_profile,
    retrieval_sources_path,
)
from project_manager import (
    delete_chapter_bundle,
    delete_pipeline_run,
    delete_project,
    get_project_summary,
    list_chapter_inventory,
    list_project_runs,
    list_retrieval_sources,
    rename_project,
)
from settings_workflows import CORE_SETTING_KNOWLEDGE_FIELDS, build_core_setting_knowledge_items
from creative_profile_workflows import (
    CUSTOM_OPTION_LABEL,
    build_creative_profile_from_form_values,
    build_profile_from_task_wizard,
    normalize_creative_form_state,
    recommended_workflow_for_profile,
)
from retrieval_eval import (
    build_retrieval_usage_report_from_payload,
    parse_multiline_or_comma_values,
    retrieval_profile_label,
    run_retrieval_eval_cases,
)
from resource_browser import (
    _build_resource_browser_items,
    _delete_browser_resource,
    _save_browser_resource,
)
from retrieval import RETRIEVAL_TASK_PROFILES, debug_retrieve_context, inspect_retrieval_health, rebuild_retrieval_assets, load_retrieval_index, retrieve_context
from extraction_presets import (
    KNOWLEDGE_CONSOLIDATION_MODE_LABELS,
    KNOWLEDGE_EXTRACTION_EXPERT_PRESETS,
    KNOWLEDGE_EXTRACTION_MODE_HELP,
    KNOWLEDGE_EXTRACTION_MODE_LABELS,
    KNOWLEDGE_EXTRACTION_PLAN_PRESETS,
    default_extraction_categories,
)
from source_workflows import (
    auto_confirm_pending_items_without_risk,
    build_extraction_coverage_report,
    build_ingestion_health_report,
    build_ingestion_source_ledger,
    build_source_package_report,
    calculate_text_fingerprint,
    consolidate_batch_pending_items,
    decode_uploaded_text,
    delete_extraction_plan_template,
    extract_long_reference_segments_to_queue,
    find_matching_long_reference_batches,
    get_batch_pending_knowledge_items,
    get_segment_related_knowledge_items,
    import_organized_reference_entries,
    import_long_reference_segments,
    extract_pasted_reference_to_pending,
    normalize_text_for_fingerprint,
    read_retrieval_source_payload,
    run_long_reference_extraction_plan,
    run_long_reference_quick_process,
    save_manual_retrieval_source_card,
    split_long_reference_text,
    summarize_long_reference_resume_state,
    upsert_extraction_plan_template,
)
from knowledge_entities import (
    SETTING_ENTITY_CATEGORY_GROUPS,
    build_character_entity_cards,
    build_merged_knowledge_item,
    build_setting_entity_cards,
)
from knowledge_quality import (
    build_pending_issue_map,
    build_pending_knowledge_quality_issues,
    find_duplicate_knowledge_groups,
    merge_list_values,
    upsert_entity_alias_group,
)
from knowledge_workflows import (
    build_pending_auto_review_preview,
    build_pending_clear_plan,
    build_pending_triage_summary,
    execute_pending_clear_plan,
    delete_confirmed_knowledge_items,
    filter_pending_knowledge_indices_by_values,
    merge_confirmed_knowledge_items,
    pending_quality_label,
    parse_comma_tags,
    replace_knowledge_category_items,
    save_confirmed_knowledge_item,
    safe_confidence,
    summarize_item_evidence,
    update_pending_knowledge_item,
)
from skills import (
    approve_chapter_discussion,
    approve_arc_discussion,
    approve_creative_profile_discussion,
    approve_outline_discussion,
    approve_volume_discussion,
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
    discuss_creative_profile,
    discuss_creative_profile_turn,
    discuss_outline,
    discuss_outline_turn,
    discuss_volume,
    discuss_volume_turn,
    evaluate_chapter_comprehensive,
    generate_arc_outline,
    generate_arc_chapter_plan,
    generate_chapter_outline,
    generate_outline,
    generate_volume_outline,
    get_retrieval_trace,
    organize_reference_text,
    review_chapter,
    pipeline_plan_write_review_update,
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

LONG_REFERENCE_PRESET_INFO = {
    "fanfic_foundation": {
        "label": "同人创作地基（推荐）",
        "button": "使用同人创作地基",
        "summary": "第一次导入整本原作时优先选。它会尽量整理后续写作反复要用的角色、关系、时间线、世界观、能力道具和硬约束。",
        "effect": "适合：搭完整资料库 / 范围=原作资料 / 可信度=官方资料 / 提取=平衡总管+深度提取 / 会自动整理散知识",
    },
    "canon_foundation": {
        "label": "严格原作校验",
        "button": "使用严格原作校验",
        "summary": "只想补一层“不能错、不能改”的原作硬事实时选。它更保守，尽量少推测，适合防止后续写作违背原作。",
        "effect": "适合：补硬事实和防错 / 范围=原作资料 / 可信度=官方资料 / 提取=原作审计+严格原作 / 不自动整理散知识",
    },
    "style_reference": {
        "label": "文风参考",
        "button": "使用文风参考",
        "summary": "导入样本文本或只想学原作表达方式时选。它关注叙事节奏、对白、氛围和描写习惯，不适合拿来补全世界观资料。",
        "effect": "适合：学文风 / 范围=参考资料 / 可信度=人工整理 / 提取=文风专家+文风专用 / 不自动整理散知识",
    },
}

WEB_REFERENCE_INGESTION_ENABLED = False

VERSION_SCOPE_LABELS = {
    "canon": "原作/官方",
    "project_main": "本项目主线",
    "au": "AU/分支",
    "mixed": "混合/待拆分",
    "unknown": "未标明",
}

DEFAULT_WORLDLINE_ID = "main"
DEFAULT_WORLDLINE_LABEL = "本项目主线"

SOURCE_TYPE_LABELS = {
    "outline": "全书大纲",
    "outline_discussion": "全书讨论工件",
    "creative_profile_discussion": "创作配置讨论工件",
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
    "entity_character_card": "实体卡：角色",
    "entity_setting_card": "实体卡：设定",
    "entity_alias_group": "实体别名组",
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

PAGE_GROUPS = {
    "工作台": ["项目总览", "模型配置", "生成规则", "资源浏览器"],
    "资料": ["资料导入", "核心设定", "检索中心"],
    "规划": ["创作配置", "生成大纲", "分卷大纲", "剧情段大纲", "生成细纲"],
    "写作": ["快速生成", "正文生成", "章节评价"],
}

PAGE_DESCRIPTIONS = {
    "项目总览": "查看项目进度、资源规模和基础管理。",
    "快速生成": "实验性快速生成。只凭一段提示词就能生成，也可展开复杂配置，适合测试或临时片段。",
    "资源浏览器": "集中浏览、编辑和清理项目文件。",
    "创作配置": "定义任务类型、篇幅、流程深度和参考强度。",
    "核心设定": "管理故事级和项目级的核心设定（角色、世界观、时间线等）。",
    "生成大纲": "规划全书方向并生成全局大纲。",
    "分卷大纲": "维护中层分卷结构。",
    "剧情段大纲": "维护剧情段和章节分配计划。",
    "生成细纲": "生成具体章节细纲。",
    "正文生成": "根据细纲或需求生成正文内容，可串联审阅和设定更新。适应章节制和自由写作两种模式。",
    "章节评价": "综合判断章节是否可继续、质量分数和一致性诊断。",
    "资料导入": "导入原作、参考资料和长篇文本。",
    "检索中心": "调试索引、召回证据和冲突裁决。",
    "生成规则": "管理全局、项目和故事级的生成约束，控制模型怎么写。",
    "模型配置": "配置模型端点、密钥和档案切换。",
}

DEFAULT_PAGE = "项目总览"

LEGACY_PAGE_ALIASES = {
    "设定": "核心设定",
    "资料录入": "资料导入",
    "项目资源": "资源浏览器",
}

SCHEMA_LABELS = {
    "OrganizedReferenceResult": "资料整理结果",
    "OutlineDiscussionResult": "全书讨论结果",
    "CreativeProfileDiscussionResult": "创作配置讨论结果",
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


def apply_app_style():
    st.markdown(
        """
        <style>
        :root {
            --nf-bg: #f7f8fb;
            --nf-panel: #ffffff;
            --nf-border: #d8dee8;
            --nf-text: #17202a;
            --nf-muted: #667085;
            --nf-accent: #0f766e;
            --nf-accent-strong: #0b5f59;
            --nf-danger: #b42318;
            --nf-shadow: 0 16px 42px rgba(15, 35, 55, 0.08);
        }

        .stApp {
            background:
                linear-gradient(180deg, rgba(255,255,255,0.86), rgba(247,248,251,0.98)),
                var(--nf-bg);
            color: var(--nf-text);
        }

        [data-testid="stSidebar"] {
            background: #123733;
            border-right: 1px solid rgba(255,255,255,0.08);
        }

        [data-testid="stSidebar"] * {
            color: #eef7f6;
        }

        [data-testid="stSidebar"] .stCaption,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
            color: rgba(238,247,246,0.74);
        }

        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea {
            background: #ffffff !important;
            border-color: rgba(255,255,255,0.18) !important;
            color: var(--nf-text) !important;
        }

        [data-testid="stSidebar"] [data-baseweb="select"] *,
        [data-testid="stSidebar"] [data-baseweb="select"] div,
        [data-testid="stSidebar"] [data-baseweb="select"] span,
        [data-testid="stSidebar"] [data-baseweb="select"] [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] [data-baseweb="select"] [data-testid="stMarkdownContainer"] *,
        [data-testid="stSidebar"] [data-baseweb="select"] [role="button"],
        [data-testid="stSidebar"] [data-baseweb="select"] [role="button"] *,
        [data-testid="stSidebar"] [data-baseweb="select"] svg,
        [data-testid="stSidebar"] [data-baseweb="select"] svg path,
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea,
        [data-testid="stSidebar"] input::placeholder,
        [data-testid="stSidebar"] textarea::placeholder {
            color: var(--nf-text) !important;
            fill: var(--nf-text) !important;
        }

        [data-testid="stSidebar"] .stButton > button {
            background: #ffffff !important;
            border-color: rgba(255,255,255,0.22) !important;
            color: var(--nf-text) !important;
            font-weight: 650 !important;
        }

        [data-testid="stSidebar"] button,
        [data-testid="stSidebar"] [data-testid="stPopover"] button {
            background: #ffffff !important;
            border-color: rgba(255,255,255,0.22) !important;
            color: var(--nf-text) !important;
            font-weight: 650 !important;
            opacity: 1 !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        [data-testid="stSidebar"] .stButton > button *,
        [data-testid="stSidebar"] .stButton > button p,
        [data-testid="stSidebar"] .stButton > button span,
        [data-testid="stSidebar"] button *,
        [data-testid="stSidebar"] button p,
        [data-testid="stSidebar"] button span,
        [data-testid="stSidebar"] button svg,
        [data-testid="stSidebar"] button svg path {
            color: var(--nf-text) !important;
            fill: var(--nf-text) !important;
            opacity: 1 !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        [data-testid="stSidebar"] .stButton > button:hover {
            background: #e6fffb !important;
            border-color: var(--nf-accent) !important;
            color: var(--nf-accent-strong) !important;
        }

        [data-testid="stSidebar"] button:hover,
        [data-testid="stSidebar"] button:hover * {
            color: var(--nf-accent-strong) !important;
            fill: var(--nf-accent-strong) !important;
            -webkit-text-fill-color: var(--nf-accent-strong) !important;
        }

        [data-testid="stSidebar"] .stButton > button:disabled,
        [data-testid="stSidebar"] .stButton > button[disabled],
        [data-testid="stSidebar"] .stButton > button:disabled *,
        [data-testid="stSidebar"] .stButton > button[disabled] *,
        [data-testid="stSidebar"] button:disabled,
        [data-testid="stSidebar"] button[disabled],
        [data-testid="stSidebar"] button:disabled *,
        [data-testid="stSidebar"] button[disabled] * {
            background: #ffffff !important;
            border-color: rgba(255,255,255,0.22) !important;
            color: var(--nf-text) !important;
            opacity: 1 !important;
            -webkit-text-fill-color: var(--nf-text) !important;
        }

        .block-container {
            max-width: 1320px;
            padding-top: 1.4rem;
            padding-bottom: 4rem;
        }

        h1, h2, h3 {
            letter-spacing: 0;
        }

        div[data-testid="stMetric"] {
            background: var(--nf-panel);
            border: 1px solid var(--nf-border);
            border-radius: 8px;
            padding: 0.85rem 1rem;
            box-shadow: 0 10px 28px rgba(15, 35, 55, 0.05);
        }

        div[data-testid="stMetric"] label {
            color: var(--nf-muted);
        }

        .nf-hero {
            background: linear-gradient(135deg, #ffffff 0%, #e8f5f3 100%);
            border: 1px solid var(--nf-border);
            border-radius: 8px;
            padding: 1.25rem 1.35rem;
            box-shadow: var(--nf-shadow);
            margin-bottom: 1rem;
        }

        .nf-kicker {
            color: var(--nf-accent);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }

        .nf-title {
            color: var(--nf-text);
            font-size: 1.7rem;
            line-height: 1.25;
            font-weight: 750;
            margin: 0;
        }

        .nf-subtitle {
            color: var(--nf-muted);
            margin-top: 0.35rem;
            margin-bottom: 0;
        }

        .nf-card-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 0.8rem;
            margin: 1rem 0;
        }

        .nf-card {
            background: var(--nf-panel);
            border: 1px solid var(--nf-border);
            border-radius: 8px;
            padding: 1rem;
            box-shadow: 0 10px 26px rgba(15, 35, 55, 0.05);
        }

        .nf-card-title {
            font-weight: 700;
            color: var(--nf-text);
            margin-bottom: 0.35rem;
        }

        .nf-card-copy {
            color: var(--nf-muted);
            font-size: 0.92rem;
            line-height: 1.55;
        }

        .active-profile-card {
            border-left: 4px solid var(--nf-accent) !important;
        }

        .nf-sidebar-title {
            font-size: 1.05rem;
            font-weight: 750;
            margin: 0.2rem 0 0.2rem;
        }

        .nf-sidebar-meta {
            color: rgba(247,240,231,0.68);
            font-size: 0.82rem;
            line-height: 1.45;
            margin-bottom: 0.8rem;
        }

        .stButton > button {
            border-radius: 8px;
            border: 1px solid var(--nf-border);
            background: var(--nf-panel);
        }

        .stButton > button[kind="primary"],
        .stButton > button[data-kind="primary"] {
            background: var(--nf-accent) !important;
            color: #ffffff !important;
            border-color: var(--nf-accent-strong) !important;
            font-weight: 650 !important;
        }

        .stButton > button[kind="primary"]:hover,
        .stButton > button[data-kind="primary"]:hover {
            background: var(--nf-accent-strong) !important;
            color: #ffffff !important;
            border-color: #084c47 !important;
        }

        .stButton > button:hover {
            border-color: var(--nf-accent);
            color: var(--nf-accent);
        }

        div[data-testid="stExpander"] {
            border: 1px solid var(--nf-border);
            border-radius: 8px;
            background: rgba(255,255,255,0.72);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_app_header(project_name: str | None, page: str, memory: dict | None):
    title = html.escape(str((memory or {}).get("title") or project_name or "未选择项目"))
    genre = html.escape(str((memory or {}).get("genre") or "未设置类型"))
    canon_mode = html.escape(str((memory or {}).get("canon_mode") or "未设置原作对齐"))
    page_label = html.escape(str(page))
    project_label = html.escape(str(project_name or "-"))
    description = html.escape(PAGE_DESCRIPTIONS.get(page, ""))
    st.markdown(
        f"""
        <div class="nf-hero">
            <div class="nf-kicker">NovelForge / {page_label}</div>
            <h1 class="nf-title">{title}</h1>
            <p class="nf-subtitle">{description}</p>
            <p class="nf-subtitle">项目：<b>{project_label}</b> / 类型：{genre} / 原作对齐：{canon_mode}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


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
    st.markdown(f"**{label}**")
    st.caption(help_text)
    if st.button("进入", key=f"quick_action_{stable_widget_suffix(page)}", use_container_width=True):
        navigate_to(page)


RESOURCE_BROWSER_GROUPS = [
    ("outline", "全书大纲"),
    ("outline_discussion", "全书讨论工件"),
    ("creative_profile_discussion", "创作配置讨论工件"),
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
    ("knowledge_item", "结构化知识"),
    ("pending_knowledge", "待确认知识"),
    ("long_reference_batch", "资料批次"),
]
RESOURCE_BROWSER_GROUP_LABELS = dict(RESOURCE_BROWSER_GROUPS)


def _normalize_resource_browser_groups(groups: list[str] | tuple[str, ...] | None) -> list[str]:
    allowed_groups = set(RESOURCE_BROWSER_GROUP_LABELS)
    normalized = []
    for group in groups or []:
        group_key = str(group)
        if group_key in allowed_groups and group_key not in normalized:
            normalized.append(group_key)
    return normalized


def _resource_browser_focus_key(project_name: str) -> str:
    return f"resource_browser_focus:{project_name}"


def navigate_to_resource_browser(
    project_name: str,
    groups: list[str] | tuple[str, ...] | None = None,
    *,
    search_value: str = "",
    select_first: bool = True,
):
    st.session_state[_resource_browser_focus_key(project_name)] = {
        "groups": _normalize_resource_browser_groups(groups),
        "search_value": str(search_value or ""),
        "select_first": bool(select_first),
    }
    navigate_to("资源浏览器")


def _consume_resource_browser_focus(project_name: str, browser_items: list[dict]) -> tuple[dict, str]:
    focus = st.session_state.pop(_resource_browser_focus_key(project_name), None)
    if not isinstance(focus, dict):
        return {}, ""

    focus_groups = _normalize_resource_browser_groups(focus.get("groups") or [])
    focus_search = str(focus.get("search_value") or "").strip()

    st.session_state[f"resource_browser_search_{project_name}"] = focus_search
    st.session_state[f"resource_browser_volume_filter_{project_name}"] = 0
    st.session_state[f"resource_browser_arc_filter_{project_name}"] = 0
    if focus_groups:
        st.session_state[f"resource_browser_group_filter_{project_name}"] = focus_groups

    candidates = list(browser_items)
    if focus_groups:
        candidates = [item for item in candidates if item.get("group") in focus_groups]
    if focus_search:
        search_lower = focus_search.lower()
        candidates = [
            item for item in candidates
            if search_lower in str(item.get("label", "")).lower()
            or search_lower in str(item.get("path_label", "")).lower()
        ]

    if candidates and bool(focus.get("select_first", True)):
        selected = candidates[0]
        _set_resource_browser_selection(project_name, selected)
        return selected, ""

    focus_labels = "、".join(RESOURCE_BROWSER_GROUP_LABELS.get(group, group) for group in focus_groups)
    return {}, f"当前没有可定位的{focus_labels or '资源'}。"


def _safe_int_metric_value(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def render_resource_metric_link(
    container,
    project_name: str,
    story_id: str,
    label: str,
    value,
    groups: list[str] | tuple[str, ...],
):
    metric_value = _safe_int_metric_value(value)
    normalized_groups = _normalize_resource_browser_groups(groups)
    container.metric(label, metric_value)
    button_key = scoped_widget_key("overview_resource_metric", project_name, story_id, label, ",".join(normalized_groups))
    if metric_value > 0 and normalized_groups:
        if container.button("查看资源", key=button_key, use_container_width=True):
            navigate_to_resource_browser(project_name, normalized_groups)
    else:
        disabled_label = "暂无资源" if normalized_groups else "未纳入资源"
        container.button(disabled_label, key=button_key, disabled=True, use_container_width=True)


def is_story_creative_profile_configured(project_name: str | None, story_id: str = "default") -> bool:
    if not project_name:
        return False
    try:
        if not creative_profile_path(project_name, story_id).exists():
            return False
        profile = load_creative_profile(project_name, story_id=story_id)
        return bool(profile.get("is_configured"))
    except Exception:
        return False


def planning_pages_for_story(project_name: str | None, story_id: str = "default") -> list[str]:
    if not is_story_creative_profile_configured(project_name, story_id):
        return ["创作配置"]

    try:
        profile = load_creative_profile(project_name, story_id=story_id) if project_name else {}
    except Exception:
        profile = {}

    workflow_depth = str(profile.get("workflow_depth", "") or "")
    target_length = str(profile.get("target_length", "") or "")
    story_mode = str(profile.get("story_mode", "") or "")
    combined = f"{workflow_depth} {target_length} {story_mode}"

    if "完整长篇流程" in workflow_depth or "分卷/剧情段/章节" in workflow_depth or "长篇" in combined:
        return ["创作配置", "生成大纲", "分卷大纲", "剧情段大纲", "生成细纲"]
    if "章节计划+正文" in workflow_depth or "中篇" in combined:
        return ["创作配置", "生成大纲", "生成细纲"]
    if "短篇结构+正文" in workflow_depth or "短篇" in combined or "片段" in combined or "单场景" in combined:
        return ["创作配置", "生成细纲"]
    if "只生成正文" in workflow_depth:
        return ["创作配置"]
    return ["创作配置", "生成大纲", "生成细纲"]


def page_groups_for_story(project_name: str | None, story_id: str = "default") -> dict[str, list[str]]:
    groups = {group: list(pages) for group, pages in PAGE_GROUPS.items()}
    groups["规划"] = planning_pages_for_story(project_name, story_id)
    return groups


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


CREATIVE_PROFILE_FORM_KEYS = {
    "story_mode": "creative_story_mode",
    "target_length": "creative_target_length",
    "target_word_count": "creative_form_target_word_count",
    "workflow_depth": "creative_workflow_depth",
    "reference_strength": "creative_reference_strength",
    "conflict_policy": "creative_conflict_policy",
    "custom_reference_focus": "creative_form_custom_reference_focus",
    "allow_canon_deviation": "creative_form_allow_canon_deviation",
    "notes": "creative_form_notes",
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


def _set_creative_profile_form_state(project_name: str, story_id: str, profile: dict):
    normalized = normalize_creative_form_state(profile)
    st.session_state[_creative_profile_state_key(project_name, story_id)] = normalized
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
    st.session_state[form_keys["notes"]] = normalized["notes"]


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


def _format_discussion_artifact_as_guidance(artifact: dict) -> str:
    discussion = artifact.get("discussion", {}) if isinstance(artifact, dict) else {}
    if not discussion:
        return ""

    lines = ["来自已批准章节讨论："]
    field_specs = [
        ("current_understanding", "当前理解"),
        ("recommended_direction", "推荐方向"),
    ]
    for field, label in field_specs:
        value = str(discussion.get(field, "") or "").strip()
        if value:
            lines.append(f"- {label}：{value}")

    list_field_specs = [
        ("key_constraints", "关键约束"),
        ("risks", "风险提醒"),
        ("open_questions", "待确认问题"),
    ]
    for field, label in list_field_specs:
        values = discussion.get(field, [])
        if isinstance(values, list):
            cleaned_values = [str(item).strip() for item in values if str(item).strip()]
        else:
            cleaned_values = [str(values).strip()] if str(values or "").strip() else []
        if cleaned_values:
            lines.append(f"- {label}：{'；'.join(cleaned_values)}")

    if len(lines) == 1:
        return ""
    return "\n".join(lines)


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


def render_retrieval_usage_report(hits: list[dict], title: str = "资料使用报告"):
    report = build_retrieval_usage_report_from_payload(
        hits,
        label_source_type_func=label_source_type,
        label_scope_func=label_scope,
        label_authority_func=label_authority,
    )
    with st.expander(title, expanded=bool(hits)):
        metric_cols = st.columns(4)
        metric_cols[0].metric("召回片段", report.get("hit_count", 0))
        metric_cols[1].metric("来源类型", len(report.get("source_type_counts", {})))
        metric_cols[2].metric("硬约束/设定", len(report.get("constraints", [])))
        metric_cols[3].metric("冲突裁决", len(report.get("conflicts", [])))
        if report.get("scope_counts"):
            st.caption("范围分布：" + " / ".join(f"{label_scope(key)}={value}" for key, value in report.get("scope_counts", {}).items()))
        if report.get("source_type_counts"):
            st.caption("来源分布：" + " / ".join(f"{label_source_type(key)}={value}" for key, value in report.get("source_type_counts", {}).items()))
        if report.get("risk_notes"):
            for note in report.get("risk_notes", []):
                st.info(note)
        priority_sources = report.get("priority_sources", [])
        if priority_sources:
            st.markdown("#### 优先参考资料")
            st.dataframe(priority_sources, use_container_width=True, hide_index=True)
        constraints = report.get("constraints", [])
        if constraints:
            st.markdown("#### 需要优先遵守的约束/设定")
            for item in constraints:
                st.markdown(f"**{item.get('来源', '')}**")
                st.caption(item.get("内容", ""))
        conflicts = report.get("conflicts", [])
        if conflicts:
            st.markdown("#### 已保存冲突裁决")
            for item in conflicts:
                st.markdown(f"**{item.get('来源', '')}**")
                st.caption(item.get("内容", ""))


def render_step_retrieval(step_result: dict, title: str, fallback_hits: list[dict] | None = None):
    hits = step_result.get("retrieval_hits", []) if step_result else []
    active_hits = hits or (fallback_hits or [])
    if not active_hits:
        return
    render_retrieval_usage_report(active_hits, "本次生成资料使用报告")
    render_retrieval_hits_block(active_hits, title)


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


def _render_rules_copy_tools(project_name: str, story_id: str, current_story_name: str):
    st.markdown("#### 规则复制与导入")
    st.caption("用于在项目规则和故事规则之间同步长期生成约束。项目规则会被所有故事继承，故事规则只覆盖当前故事。")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("从项目导入规则", use_container_width=True):
            merge_project_rules_to_story(project_name, story_id)
            st.success(f"已将项目规则复制到 {current_story_name}")
            st.rerun()

    with col_b:
        other_stories = [s for s in list_stories(project_name) if s.get("story_id") != story_id]
        if other_stories:
            selected_story = st.selectbox(
                "从其他故事导入",
                options=[s.get("story_id") for s in other_stories],
                format_func=lambda sid: next((s.get("name", sid) for s in other_stories if s.get("story_id") == sid), sid),
                key=f"rules_import_story_{story_id}",
                label_visibility="collapsed",
            )
            if st.button("导入故事规则", use_container_width=True, key=f"import_rules_{story_id}"):
                save_story_rules(project_name, story_id, load_story_rules(project_name, selected_story))
                imported_name = next((s.get("name", selected_story) for s in other_stories if s.get("story_id") == selected_story), selected_story)
                st.success(f"已从 {imported_name} 导入规则")
                st.rerun()
        else:
            st.caption("没有其他故事可导入。")

    with col_c:
        if st.button("设为项目默认规则", use_container_width=True):
            merge_story_rules_to_project(project_name, story_id)
            st.success(f"已将 {current_story_name} 的规则合并为项目默认规则")
            st.rerun()

    with st.expander("全局规则同步", expanded=False):
        st.caption("全局规则会影响所有项目。建议只放跨项目稳定偏好，例如输出语言、审阅标准、文风禁忌；具体角色、世界观和剧情要求更适合留在项目或故事规则。")
        global_col_a, global_col_b = st.columns(2)
        with global_col_a:
            if st.button("全局规则合并到项目", use_container_width=True):
                merge_global_rules_to_project(project_name)
                st.success("已将全局规则合并到项目规则")
                st.rerun()
            if st.button("项目规则合并到全局", use_container_width=True):
                merge_project_rules_to_global(project_name)
                st.success("已将项目规则合并到全局规则")
                st.rerun()
        with global_col_b:
            if st.button("全局规则合并到当前故事", use_container_width=True):
                merge_global_rules_to_story(project_name, story_id)
                st.success(f"已将全局规则合并到 {current_story_name}")
                st.rerun()
            if st.button("当前故事规则合并到全局", use_container_width=True):
                merge_story_rules_to_global(project_name, story_id)
                st.success(f"已将 {current_story_name} 的规则合并到全局规则")
                st.rerun()


def _render_rule_conflict_resolution_tools(project_name: str, story_id: str, current_story_name: str):
    st.markdown("#### 冲突解决机制")
    st.caption("默认优先级：人工裁决 > 故事规则 > 项目规则 > 全局规则；同层级内，当前能力的专用规则优先于通用规则。")

    with st.expander("人工冲突裁决", expanded=False):
        layer_options = {
            "当前故事": "story",
            "当前项目": "project",
            "全局": "global",
        }
        col_scope, col_layer = st.columns(2)
        scope_label = col_scope.selectbox(
            "适用能力",
            options=list(RULE_SCOPE_OPTIONS.values()),
            key=f"rule_conflict_scope_{story_id}",
        )
        layer_label = col_layer.selectbox(
            "裁决保存位置",
            options=list(layer_options.keys()),
            key=f"rule_conflict_layer_{story_id}",
        )
        title = st.text_input(
            "裁决标题",
            key=f"rule_conflict_title_{story_id}",
            placeholder="例如：节奏规则冲突、视角规则冲突",
        )
        decision = st.text_area(
            "裁决内容",
            height=100,
            key=f"rule_conflict_decision_{story_id}",
            placeholder="例如：当“快节奏推进”和“日常慢热”冲突时，当前故事优先日常慢热，但章节结尾保留推进钩子。",
        )
        if st.button("保存人工裁决", key=f"save_rule_conflict_{story_id}", use_container_width=True):
            if not decision.strip():
                st.warning("请先填写裁决内容。")
            else:
                scope = next(key for key, value in RULE_SCOPE_OPTIONS.items() if value == scope_label)
                layer = layer_options[layer_label]
                add_rule_conflict_resolution(project_name, layer, scope, title, decision, story_id=story_id)
                st.success("已保存人工冲突裁决")
                st.rerun()

        st.markdown("##### 已保存裁决")
        layer_display = [
            ("故事", "story", current_story_name),
            ("项目", "project", project_name),
            ("全局", "global", "所有项目"),
        ]
        has_items = False
        for layer_label_text, layer, owner in layer_display:
            items = load_rule_conflict_resolutions(project_name, layer, story_id=story_id)
            if not items:
                continue
            has_items = True
            st.markdown(f"**{layer_label_text}裁决 · {owner}**")
            for item in items:
                scope_name = RULE_SCOPE_OPTIONS.get(item.get("scope", "all"), item.get("scope", "all"))
                row_cols = st.columns([4, 1])
                with row_cols[0]:
                    st.caption(f"{scope_name} / {item.get('title', '')}")
                    st.write(item.get("decision", ""))
                with row_cols[1]:
                    if st.button("删除", key=f"delete_rule_conflict_{layer}_{item.get('id')}", use_container_width=True):
                        delete_rule_conflict_resolution(project_name, layer, item.get("id", ""), story_id=story_id)
                        st.success("已删除裁决")
                        st.rerun()
        if not has_items:
            st.caption("暂无人工裁决。")


def render_rules_page(project_name: str):
    story_id = st.session_state.get("active_story_id", "default")
    stories = list_stories(project_name)
    current_story_name = "默认"
    for s in stories:
        if s.get("story_id") == story_id:
            current_story_name = s.get("name", story_id)
            break

    st.subheader("生成规则")
    st.caption("将长期要求存成规则，系统会在对应能力里自动注入这些约束，控制模型怎么写。规则生效优先级：故事 > 项目 > 全局。")

    with st.expander("快速记录新要求", expanded=True):
        rule_text = st.text_area("输入你的要求", height=140, key="rule_capture_text")
        col1, col2, col3 = st.columns(3)
        scope_label = col1.selectbox("适用能力", options=list(RULE_SCOPE_OPTIONS.values()), key="rule_capture_scope")
        target_label = col2.selectbox("保存位置", options=["故事规则", "项目规则", "全局规则"], key="rule_capture_target")

        if st.button("保存要求为规则"):
            scope = next(key for key, value in RULE_SCOPE_OPTIONS.items() if value == scope_label)
            target = "story" if target_label == "故事规则" else ("project" if target_label == "项目规则" else "global")
            try:
                result = save_rule_text(project_name, scope, target, rule_text, story_id=story_id)
                if result.get("status") == "saved":
                    st.success(f"已保存到{target_label} / {scope_label}")
                    st.rerun()
                else:
                    st.warning("未提取到有效规则。")
            except Exception as exc:
                st.error(f"保存失败：{exc}")

    _render_rules_copy_tools(project_name, story_id, current_story_name)
    _render_rule_conflict_resolution_tools(project_name, story_id, current_story_name)
    st.divider()

    global_rules = load_global_rules()
    project_rules = load_project_rules(project_name)
    story_rules = load_story_rules(project_name, story_id)

    tab1, tab2, tab3 = st.tabs(["故事规则", "项目规则", "全局规则"])

    with tab1:
        updated_story_rules = _render_rule_editor(f"故事规则：{current_story_name}", f"story_rules_{story_id}", story_rules)
        if st.button("保存故事规则"):
            save_story_rules(project_name, story_id, updated_story_rules)
            st.success(f"已保存 {current_story_name} 的故事规则")

    with tab2:
        updated_project_rules = _render_rule_editor(f"项目规则：{project_name}", "project_rules", project_rules)
        if st.button("保存项目规则"):
            save_project_rules(project_name, updated_project_rules)
            st.success("项目规则已保存")

    with tab3:
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
    profile_option_labels = {
        profile.get("id", ""): f"{profile.get('name', profile.get('id', ''))} {'（当前）' if profile.get('id') == active_profile.get('id') else ''}"
        for profile in profiles
    }

    st.markdown("### 档案管理")
    col_sel, col_act = st.columns([2, 1])
    with col_sel:
        selected_profile_id = st.selectbox(
            "选择档案",
            options=profile_options,
            index=profile_options.index(active_profile.get("id", "")) if active_profile.get("id", "") in profile_options else 0,
            format_func=lambda pid: profile_option_labels.get(pid, pid),
            key="llm_profile_selector",
        )
    selected_profile = next((profile for profile in profiles if profile.get("id") == selected_profile_id), active_profile)

    with col_act:
        st.caption("")
        action_col1, action_col2, action_col3 = st.columns(3)
        if action_col1.button("切换生效", key="switch_llm_profile", use_container_width=True):
            try:
                set_active_llm_profile(selected_profile_id)
                st.success("已切换当前模型档案。")
                st.rerun()
            except Exception as exc:
                st.error(f"切换失败：{exc}")
        if action_col2.button("测试连接", key="test_llm_connection", use_container_width=True):
            if not selected_profile.get("api_key"):
                st.error("当前档案没有填写接口密钥，无法测试。")
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
        if confirmed_button(
            action_col3,
            "删除档案",
            "确认删除该模型档案",
            "delete_llm_profile",
            help_text="删除前请确认该档案不再需要。",
        ):
            try:
                delete_llm_profile(selected_profile_id)
                st.success("档案已删除。")
                st.rerun()
            except Exception as exc:
                st.error(f"删除失败：{exc}")

    st.markdown("### 快速填充")
    st.caption("点击下方服务商按钮，自动填写常见服务地址和模型名，然后按需微调。")
    provider_keys = list(PROVIDER_PRESETS.keys())
    fill_cols = st.columns(len(provider_keys))
    for idx, provider_name in enumerate(provider_keys):
        provider = PROVIDER_PRESETS[provider_name]
        with fill_cols[idx]:
            if provider_name != "自定义":
                st.button(
                    provider_name,
                    key=f"fill_provider_{idx}",
                    use_container_width=True,
                    help=f"{provider['base_url']} / {provider['model_name']}",
                    on_click=lambda p=provider: (
                        st.session_state.update({
                            "llm_base_url": p["base_url"],
                            "llm_model_name": p["model_name"],
                            "llm_embedding_model_name": p["embedding_model_name"],
                        })
                    ) or None,
                )
            else:
                st.caption(provider_name)

    with st.form("llm_profile_form"):
        st.markdown("### 编辑或新增档案")
        provider_keys = list(PROVIDER_PRESETS.keys())
        col_a, col_b = st.columns(2)
        profile_id_value = col_a.text_input(
            "档案标识",
            value=selected_profile.get("id", ""),
            key="llm_profile_id",
            help="用于内部识别这套配置。建议使用英文、数字、短横线，例如 deepseek-main。",
        )
        profile_name = col_b.text_input("档案名称", value=selected_profile.get("name", ""), placeholder="例如：DeepSeek 主账号", key="llm_profile_name")
        base_url = st.text_input(
            "模型服务网址",
            value=selected_profile.get("base_url", ""),
            placeholder="https://api.deepseek.com",
            key="llm_base_url",
            help="选择一个服务商快速填充常见的服务地址和模型名。",
        )
        col_ak, col_mn = st.columns(2)
        api_key = col_ak.text_input("接口密钥", value=selected_profile.get("api_key", ""), type="password", key="llm_api_key")
        model_name = col_mn.text_input("聊天模型名", value=selected_profile.get("model_name", ""), placeholder="deepseek-v4-flash", key="llm_model_name")
        embedding_model_name = st.text_input(
            "语义向量模型名",
            value=selected_profile.get("embedding_model_name", ""),
            placeholder="text-embedding-3-small",
            key="llm_embedding_model_name",
        )
        auto_activate = st.checkbox("保存后立即切换为当前档案", value=selected_profile.get("id") == active_profile.get("id"), key="llm_auto_activate")

        test_col, save_col = st.columns([1, 1])
        if test_col.form_submit_button("测试并保存", use_container_width=True):
            cleaned_profile_id = profile_id_value.strip()
            cleaned_profile_name = profile_name.strip()
            cleaned_base_url = base_url.strip()
            cleaned_api_key = api_key.strip()
            cleaned_model_name = model_name.strip()
            cleaned_embedding_model_name = embedding_model_name.strip()

            if not cleaned_profile_id:
                st.error("档案标识不能为空。")
            elif not cleaned_profile_name:
                st.error("档案名称不能为空。")
            elif not cleaned_base_url:
                st.error("模型服务网址不能为空。")
            elif not cleaned_api_key:
                st.error("接口密钥不能为空。")
            else:
                parsed_url = urlparse(cleaned_base_url)
                if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                    st.error("模型服务网址格式无效，需要以 http:// 或 https:// 开头，并包含完整域名。")
                else:
                    try:
                        with st.spinner("正在测试连接..."):
                            test_llm_connection(cleaned_base_url, cleaned_api_key, cleaned_model_name)
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
                        st.success("连接成功，模型档案已保存。")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

        if save_col.form_submit_button("直接保存", use_container_width=True):
            cleaned_profile_id = profile_id_value.strip()
            cleaned_profile_name = profile_name.strip()
            cleaned_base_url = base_url.strip()
            cleaned_api_key = api_key.strip()
            cleaned_model_name = model_name.strip()
            cleaned_embedding_model_name = embedding_model_name.strip()

            if not cleaned_profile_id:
                st.error("档案标识不能为空。")
            elif not cleaned_profile_name:
                st.error("档案名称不能为空。")
            elif not cleaned_base_url:
                st.error("模型服务网址不能为空。")
            elif auto_activate and not cleaned_api_key:
                st.error("接口密钥为空时不能立即切换为当前档案。可以取消“保存后立即切换”，或先填写密钥。")
            else:
                parsed_url = urlparse(cleaned_base_url)
                if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                    st.error("模型服务网址格式无效。")
                else:
                    if not cleaned_api_key:
                        st.warning("接口密钥为空，后续使用该档案时可能连接失败。")
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
                        st.success("模型档案已保存。")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"保存失败：{exc}")

    st.markdown("### 已保存档案")
    for profile in profiles:
        is_active = profile.get("id") == active_profile.get("id")
        label = profile.get("name", profile.get("id", ""))
        preview_key = ""
        raw_key = str(profile.get("api_key", "") or "")
        if raw_key:
            preview_key = f"***{raw_key[-4:]}"
        card_class = "nf-card active-profile-card" if is_active else "nf-card"
        st.markdown(
            f"""
            <div class="{card_class}">
            <div class="nf-card-title">{html.escape(label)} { '<span style="color:#0f766e;font-size:0.85rem;">（当前生效）</span>' if is_active else ''}</div>
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

    st.markdown("### 当前生效配置")
    masked_key = ""
    current_api_key = settings.get("api_key", "")
    if current_api_key:
        visible_tail = current_api_key[-4:] if len(current_api_key) >= 4 else current_api_key
        masked_key = f"***{visible_tail}"
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
        migrate_project_to_stories(project_name)
        if "active_story_id" not in st.session_state:
            st.session_state["active_story_id"] = get_active_story_id(project_name)
        return project_name

    if projects:
        st.session_state["project_name"] = projects[0]
        return projects[0]

    return None


def render_sidebar(project_name: str | None, projects: list[str]) -> str:
    st.sidebar.markdown(
        """
        <div class="nf-sidebar-title">NovelForge</div>
        <div class="nf-sidebar-meta">长篇创作工作台</div>
        """,
        unsafe_allow_html=True,
    )

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
            st.session_state["active_story_id"] = get_active_story_id(selected_project)
            st.rerun()
    else:
        st.sidebar.info("还没有项目。可以先配置模型，也可以直接新建项目。")

    if st.sidebar.button("新建项目", use_container_width=True):
        st.session_state[NEW_PROJECT_INPUT_KEY] = ""
        st.session_state[NEW_PROJECT_DIALOG_FLAG] = True

    if st.session_state.get(NEW_PROJECT_DIALOG_FLAG):
        render_new_project_dialog(projects)

    if project_name:
        stories = list_stories(project_name)
        if len(stories) > 1:
            st.sidebar.divider()
            st.sidebar.caption("当前故事")
            active_id = st.session_state.get("active_story_id", "default")
            story_options = [s["story_id"] for s in stories]
            story_labels = {s["story_id"]: f'{s.get("name", s["story_id"])}' for s in stories}
            selected_story = st.sidebar.selectbox(
                "切换故事",
                options=story_options,
                index=story_options.index(active_id) if active_id in story_options else 0,
                format_func=lambda sid: story_labels.get(sid, sid),
                key="story_switcher",
            )
            if selected_story != active_id:
                set_active_story(project_name, selected_story)
                st.session_state["active_story_id"] = selected_story
                st.rerun()
        else:
            only_story_id = stories[0]["story_id"] if stories else "default"
            st.session_state["active_story_id"] = only_story_id

        with st.sidebar.popover("新故事", use_container_width=True):
            new_story_name = st.text_input("故事名称", key="new_story_name_input")
            new_story_desc = st.text_area("故事描述", key="new_story_desc_input", height=80, placeholder="例如：原作线续写、平行世界、角色穿越...")
            copy_from = st.checkbox("从当前故事复制创作配置和核心设定", value=True, key="sidebar_copy_from")
            if st.button("创建故事"):
                if new_story_name.strip():
                    meta = create_story(project_name, new_story_name.strip(), new_story_desc.strip())
                    if copy_from:
                        copy_story_settings(project_name, st.session_state.get("active_story_id", "default"), meta["story_id"])
                    set_active_story(project_name, meta["story_id"])
                    st.session_state["active_story_id"] = meta["story_id"]
                    st.success(f"已创建故事：{new_story_name.strip()}")
                    st.rerun()
                else:
                    st.error("故事名称不能为空。")

    st.sidebar.divider()

    current_story_id = st.session_state.get("active_story_id", "default")
    visible_page_groups = page_groups_for_story(project_name, current_story_id)
    available_pages = [page for pages in visible_page_groups.values() for page in pages]
    pending_nav_page = st.session_state.pop("pending_nav_page", "")
    pending_nav_page = LEGACY_PAGE_ALIASES.get(pending_nav_page, pending_nav_page)
    if pending_nav_page in available_pages:
        st.session_state["active_page"] = pending_nav_page
        st.session_state["nav_revision"] = int(st.session_state.get("nav_revision", 0)) + 1

    active_page = LEGACY_PAGE_ALIASES.get(st.session_state.get("active_page", DEFAULT_PAGE), st.session_state.get("active_page", DEFAULT_PAGE))
    if active_page not in available_pages:
        if active_page in PAGE_GROUPS.get("规划", []) and "创作配置" in available_pages:
            active_page = "创作配置"
        else:
            active_page = DEFAULT_PAGE

    active_group = next(
        (group for group, pages in visible_page_groups.items() if active_page in pages),
        "工作台",
    )
    group_names = list(visible_page_groups.keys())
    nav_revision = int(st.session_state.get("nav_revision", 0))
    selected_group = st.sidebar.radio(
        "工作区",
        options=group_names,
        index=group_names.index(active_group),
        key=f"active_page_group_{nav_revision}",
    )
    group_pages = visible_page_groups[selected_group]
    if active_page not in group_pages:
        active_page = group_pages[0]

    if selected_group == "规划" and project_name and not is_story_creative_profile_configured(project_name, current_story_id):
        st.sidebar.warning("规划页已锁定：先完成当前故事的「创作配置」。保存后会按篇幅和生成层级展开后续入口。")

    selected_page = st.sidebar.radio(
        "页面",
        options=group_pages,
        index=group_pages.index(active_page),
        key=f"active_page_in_group_{selected_group}_{nav_revision}",
        format_func=lambda page: page,
    )
    st.session_state["active_page"] = selected_page

    description = PAGE_DESCRIPTIONS.get(selected_page, "")
    if description:
        st.sidebar.caption(description)

    if project_name:
        try:
            summary = get_project_summary(project_name, story_id=st.session_state.get("active_story_id", "default"))
            st.sidebar.divider()
            st.sidebar.caption(
                f"正文 {summary.get('chapter_count', 0)} / 细纲 {summary.get('chapter_outline_count', 0)} / 资料 {summary.get('retrieval_source_count', 0)}"
            )
            updated_at = summary.get("updated_at") or "-"
            st.sidebar.caption(f"最近更新：{updated_at}")
        except Exception:
            st.sidebar.caption("项目摘要暂不可用。")

    return selected_page


def render_memory_page(project_name: str, memory: dict, embedded: bool = False):
    current_story_id = st.session_state.get("active_story_id", "default")
    if not embedded:
        stories = list_stories(project_name)
        current_story_name = "默认"
        for s in stories:
            if s.get("story_id") == current_story_id:
                current_story_name = s.get("name", current_story_id)
                break
        st.subheader(f"核心设定 · {current_story_name}")
        st.caption("生成时始终优先注入的核心状态。故事级别的设定只影响当前故事，项目级别的资料库（知识库、原材料、规则）为所有故事共享。")

    changed = False
    new_memory = dict(memory)

    new_title = st.text_input("书名", value=memory.get("title", ""), key=f"memory_title_{current_story_id}")
    if new_title != memory.get("title"):
        new_memory["title"] = new_title
        changed = True

    new_genre = st.text_input("类型", value=memory.get("genre", ""), key=f"memory_genre_{current_story_id}")
    if new_genre != memory.get("genre"):
        new_memory["genre"] = new_genre
        changed = True

    new_canon_mode = st.text_input(
        "原作对齐方式（如：严格贴合 / 轻度架空 / 完全架空）",
        value=memory.get("canon_mode", ""),
        key=f"memory_canon_{current_story_id}"
    )
    if new_canon_mode != memory.get("canon_mode", ""):
        new_memory["canon_mode"] = new_canon_mode
        changed = True

    new_au_rules = st.text_area(
        "架空规则（每行一条）",
        value="\n".join(memory.get("au_rules", [])),
        height=100,
        key=f"memory_au_{current_story_id}"
    )
    au_rule_items = [line.strip() for line in new_au_rules.split("\n") if line.strip()]
    if au_rule_items != memory.get("au_rules", []):
        new_memory["au_rules"] = au_rule_items
        changed = True

    new_world = st.text_area(
        "世界观（每行一条）",
        value="\n".join(memory.get("world", [])),
        height=120,
        key=f"memory_world_{current_story_id}"
    )
    world_items = [line.strip() for line in new_world.split("\n") if line.strip()]
    if world_items != memory.get("world", []):
        new_memory["world"] = world_items
        changed = True

    new_characters = st.text_area(
        "角色（每行一条）",
        value="\n".join(memory.get("characters", [])),
        height=150,
        key=f"memory_characters_{current_story_id}"
    )
    character_items = [line.strip() for line in new_characters.split("\n") if line.strip()]
    if character_items != memory.get("characters", []):
        new_memory["characters"] = character_items
        changed = True

    new_relationships = st.text_area(
        "角色关系（每行一条）",
        value="\n".join(memory.get("relationships", [])),
        height=120,
        key=f"memory_relationships_{current_story_id}"
    )
    relationship_items = [line.strip() for line in new_relationships.split("\n") if line.strip()]
    if relationship_items != memory.get("relationships", []):
        new_memory["relationships"] = relationship_items
        changed = True

    new_timeline = st.text_area(
        "时间线（每行一条）",
        value="\n".join(memory.get("timeline", [])),
        height=120,
        key=f"memory_timeline_{current_story_id}"
    )
    timeline_items = [line.strip() for line in new_timeline.split("\n") if line.strip()]
    if timeline_items != memory.get("timeline", []):
        new_memory["timeline"] = timeline_items
        changed = True

    new_foreshadowing = st.text_area(
        "伏笔（每行一条）",
        value="\n".join(memory.get("foreshadowing", [])),
        height=120,
        key=f"memory_foreshadowing_{current_story_id}"
    )
    foreshadowing_items = [line.strip() for line in new_foreshadowing.split("\n") if line.strip()]
    if foreshadowing_items != memory.get("foreshadowing", []):
        new_memory["foreshadowing"] = foreshadowing_items
        changed = True

    new_constraints = st.text_area(
        "当前硬性约束（每行一条）",
        value="\n".join(memory.get("active_constraints", [])),
        height=100,
        key=f"memory_constraints_{current_story_id}"
    )
    constraint_items = [line.strip() for line in new_constraints.split("\n") if line.strip()]
    if constraint_items != memory.get("active_constraints", []):
        new_memory["active_constraints"] = constraint_items
        changed = True

    expanded_setting_fields = [
        ("locations", "地点资料（每行一条）"),
        ("organizations", "组织资料（每行一条）"),
        ("power_systems", "能力体系（每行一条）"),
        ("relationship_graph", "关系图补充（每行一条）"),
    ]
    for field_name, label in expanded_setting_fields:
        value = "\n".join(str(item) for item in memory.get(field_name, []))
        new_value = st.text_area(
            label,
            value=value,
            height=90,
            key=f"memory_{field_name}_{current_story_id}",
        )
        items = [line.strip() for line in new_value.split("\n") if line.strip()]
        if items != memory.get(field_name, []):
            new_memory[field_name] = items
            changed = True

    col1, col2 = st.columns(2)
    if col1.button("保存设定", disabled=not changed):
        save_story_memory(project_name, current_story_id, new_memory)
        st.success("已保存")
        st.rerun()
    if not changed:
        col1.caption("当前表单没有未保存改动。")

    if col2.button("精简核心设定"):
        with st.spinner("正在压缩旧设定..."):
            result = compact_memory(project_name, story_id=current_story_id)
        if result.get("status") == "accepted":
            st.success("核心设定已精简")
            st.rerun()
        else:
            st.error(f"精简失败：{result.get('reason', 'unknown')}")

    render_core_setting_to_knowledge_tool(
        project_name,
        new_memory,
        f"故事核心设定：{current_story_id}",
        f"story_{current_story_id}",
    )

    with st.expander("原始结构化数据（高级编辑）", expanded=False):
        raw_json = st.text_area(
            "memory.json",
            value=json.dumps(new_memory, ensure_ascii=False, indent=2),
            height=400
        )
        if st.button("从结构化数据保存"):
            try:
                parsed = json.loads(raw_json)
                save_story_memory(project_name, current_story_id, parsed)
                st.success("已保存")
                st.rerun()
            except json.JSONDecodeError as exc:
                st.error(f"结构化数据格式错误：{exc}")


def render_core_setting_to_knowledge_tool(project_name: str, memory: dict, source_title: str, key_prefix: str):
    with st.expander("核心设定转入知识库", expanded=False):
        st.caption("适合把稳定、长期复用的设定转成结构化知识。结果会先进入待确认队列，不会直接写入正式知识库。")
        available_fields = [
            field for field in CORE_SETTING_KNOWLEDGE_FIELDS
            if memory.get(field) and (not isinstance(memory.get(field), list) or len(memory.get(field)) > 0)
        ]
        if not available_fields:
            st.caption("当前没有可转入知识库的核心设定。")
            return
        selected_fields = st.multiselect(
            "选择要转入的设定字段",
            options=available_fields,
            default=[field for field in available_fields if field in {"world", "characters", "relationships", "timeline", "active_constraints"}],
            format_func=lambda field: CORE_SETTING_KNOWLEDGE_FIELDS[field][1],
            key=f"{key_prefix}_setting_knowledge_fields",
        )
        preview_items = build_core_setting_knowledge_items(memory, source_title, selected_fields)
        st.caption(f"将生成 {len(preview_items)} 条待确认知识。")
        if preview_items:
            render_step_json_expander("设定入库预览", {"items": preview_items[:20]})
        if st.button("加入待确认知识队列", key=f"{key_prefix}_queue_setting_knowledge", use_container_width=True):
            if not preview_items:
                st.error("没有可加入队列的设定条目。")
            else:
                queued_count = queue_pending_knowledge_items(
                    project_name,
                    preview_items,
                    scope="project",
                    authority="project",
                    source_title=source_title,
                    source_origin="core_settings",
                )
                st.success(f"已加入 {queued_count} 条待确认知识。请到“资料导入 / 待确认知识”审核确认。")
                st.rerun()


def render_outline_page(project_name: str):
    story_id = st.session_state.get("active_story_id", "default")
    st.subheader("全书大纲")

    existing_outline = load_outline(project_name, story_id=story_id)
    step_result = st.session_state.get("outline_step", {})
    user_idea = st.text_area("你的小说想法", height=200)

    messages_key = _discussion_messages_key("outline")
    result_key = _discussion_result_key("outline")
    input_key = _discussion_input_key("outline")
    clear_input_flag_key = _discussion_input_clear_flag_key("outline")
    _consume_discussion_input_clear("outline")
    discussion_step = st.session_state.get(result_key, {})
    approved_artifact = load_outline_discussion_artifact(project_name, story_id=story_id)

    col_action_1, col_action_2 = st.columns(2)
    if col_action_1.button("开始讨论大纲方向"):
        try:
            result = discuss_outline(project_name, user_idea, story_id=story_id)
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
        render_step_retrieval(discussion_step, "本次大纲讨论参考的检索上下文")
        approve_col, clear_col = st.columns(2)
        if approve_col.button("批准当前讨论", key="approve_outline_discussion"):
            try:
                result = approve_outline_discussion(project_name, discussion_step, story_id=story_id)
                st.success(f"已保存全书讨论工件：{result.get('saved_path', '')}")
                st.rerun()
            except Exception as exc:
                st.error(f"批准失败：{exc}")
        if clear_col.button("清除已批准版本", key="clear_outline_discussion"):
            if clear_outline_discussion_approval(project_name, story_id=story_id):
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
                        story_id=story_id,
                    )
                    st.session_state[result_key] = result
                    assistant_message = result.get("data", {}).get("assistant_message", "") or "我已经根据你的补充更新了当前讨论结论。"
                    _append_discussion_message(messages_key, "assistant", assistant_message)
                    st.session_state[clear_input_flag_key] = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"继续讨论失败：{exc}")

    if st.button("生成全书大纲"):
        result = generate_outline(project_name, user_idea, story_id=story_id)
        st.session_state["outline_step"] = result
        st.session_state["outline"] = result.get("data", {}).get("outline", "")

    outline_text = st.text_area(
        "大纲内容",
        value=st.session_state.get("outline", existing_outline),
        height=500
    )

    if st.button("保存大纲"):
        save_outline(project_name, outline_text, story_id=story_id)
        st.success("大纲已保存")

    render_step_validation(step_result)
    render_step_retrieval(step_result, "本次大纲生成使用的检索上下文", get_retrieval_trace(f"outline:{project_name}"))


def render_chapter_outline_page(project_name: str):
    story_id = st.session_state.get("active_story_id", "default")
    st.subheader("章节细纲")

    chapter_no = st.number_input("章节编号", min_value=1, value=1, key=scoped_widget_key("chapter_outline_no", project_name, story_id))
    chapter_no = int(chapter_no)
    chapter_scope = (project_name, story_id, chapter_no)
    chapter_outline_step_key = scoped_session_key("chapter_outline_step", *chapter_scope)
    chapter_outline_text_key = scoped_session_key("chapter_outline", *chapter_scope)
    chapter_outline_editor_key = scoped_widget_key("chapter_outline_editor", *chapter_scope)
    existing_outline = load_chapter_outline(project_name, chapter_no, story_id=story_id)
    outline_metadata = load_chapter_outline_metadata(project_name, chapter_no, story_id=story_id)
    volumes = list_volumes(project_name, story_id=story_id)
    volume_options = [0] + [int(item.get("volume_no", 0)) for item in volumes]
    default_volume = int(outline_metadata.get("volume_no") or 0)
    volume_no = st.selectbox(
        "所属分卷",
        options=volume_options,
        index=volume_options.index(default_volume) if default_volume in volume_options else 0,
        format_func=lambda value: "未指定分卷" if value == 0 else f"第 {value} 卷",
        key=scoped_widget_key("chapter_outline_volume", *chapter_scope),
    )
    if volume_no:
        volume_meta = load_volume_metadata(project_name, volume_no, story_id=story_id)
        volume_discussion_artifact = load_volume_discussion_artifact(project_name, volume_no, story_id=story_id)
        st.caption(f"当前分卷：第 {volume_no} 卷 / {volume_meta.get('title', '') or '未命名分卷'}")
    else:
        volume_meta = {}
        volume_discussion_artifact = {}
    arcs = list_arcs(project_name, volume_no=volume_no or None, story_id=story_id)
    arc_options = [0] + [int(item.get("arc_no", 0)) for item in arcs]
    default_arc = int(outline_metadata.get("arc_no") or 0)
    arc_no = st.selectbox(
        "所属剧情段",
        options=arc_options,
        index=arc_options.index(default_arc) if default_arc in arc_options else 0,
        format_func=lambda value: "未指定剧情段" if value == 0 else f"剧情段 {value:03d}",
        key=scoped_widget_key("chapter_outline_arc", *chapter_scope),
    )
    if arc_no:
        arc_meta = load_arc_metadata(project_name, arc_no, story_id=story_id)
        arc_discussion_artifact = load_arc_discussion_artifact(project_name, arc_no, story_id=story_id)
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
    st.info(" / ".join(hierarchy_parts))

    if volume_meta.get("summary"):
        with st.expander("当前分卷摘要", expanded=False):
            st.markdown(volume_meta.get("summary", ""))
    if arc_meta.get("summary"):
        with st.expander("当前剧情段摘要", expanded=False):
            st.markdown(arc_meta.get("summary", ""))
    approval_required = st.checkbox(
        "要求已批准的章节/卷/剧情段讨论后再生成章节细纲",
        value=False,
        key=scoped_widget_key("chapter_outline_require_approval", *chapter_scope),
    )
    with st.expander("当前使用的已批准规划工件", expanded=False):
        st.markdown("### 章节已批准讨论")
        _render_approved_discussion_artifact(load_chapter_discussion_artifact(project_name, chapter_no, story_id=story_id), "当前章节没有已批准讨论工件。")
        st.markdown("### 分卷已批准讨论")
        _render_approved_discussion_artifact(volume_discussion_artifact, "当前分卷没有已批准讨论工件。")
        st.markdown("### 剧情段已批准讨论")
        _render_approved_discussion_artifact(arc_discussion_artifact, "当前剧情段没有已批准讨论工件。")
    step_result = st.session_state.get(chapter_outline_step_key, {})
    requirement = st.text_area("本章要求", height=200, key=scoped_widget_key("chapter_outline_requirement", *chapter_scope))

    suffix = f"{project_name}:{story_id}:{chapter_no}"
    messages_key = _discussion_messages_key("chapter", suffix)
    result_key = _discussion_result_key("chapter", suffix)
    input_key = _discussion_input_key("chapter", suffix)
    clear_input_flag_key = _discussion_input_clear_flag_key("chapter", suffix)
    _consume_discussion_input_clear("chapter", suffix)
    discussion_step = st.session_state.get(result_key, {})
    chapter_discussion_artifact = load_chapter_discussion_artifact(project_name, chapter_no, story_id=story_id)

    col_action_1, col_action_2 = st.columns(2)
    if col_action_1.button("开始讨论本章方向", key=scoped_widget_key("start_chapter_discussion", *chapter_scope)):
        try:
            save_chapter_outline_metadata(project_name, chapter_no, {"volume_no": volume_no or None, "arc_no": arc_no or None}, story_id=story_id)
            result = discuss_chapter(project_name, chapter_no, requirement, story_id=story_id)
            st.session_state[result_key] = result
            st.session_state[messages_key] = []
            assistant_message = result.get("data", {}).get("discussion", {}).get("current_understanding", "") or "我先整理了本章目标、可选方向和待确认问题，我们可以继续细化。"
            _append_discussion_message(messages_key, "assistant", assistant_message)
            st.rerun()
        except Exception as exc:
            st.error(f"讨论失败：{exc}")

    if col_action_2.button("重置本章讨论", key=scoped_widget_key("reset_chapter_discussion", *chapter_scope)):
        st.session_state[result_key] = {}
        st.session_state[messages_key] = []
        st.session_state[clear_input_flag_key] = True
        st.rerun()

    summary_col, chat_col = st.columns([1, 1])
    with summary_col:
        st.markdown("### 当前讨论结论")
        _render_discussion_summary(discussion_step, "开始讨论后，这里会持续显示本章方向的当前结论。")
        render_step_retrieval(discussion_step, "本次章节讨论参考的检索上下文")
        approve_col, clear_col = st.columns(2)
        if approve_col.button("批准当前章节讨论", key=scoped_widget_key("approve_chapter_discussion", *chapter_scope)):
            try:
                result = approve_chapter_discussion(project_name, chapter_no, discussion_step, story_id=story_id)
                st.success(f"已保存章节讨论工件：{result.get('saved_path', '')}")
                st.rerun()
            except Exception as exc:
                st.error(f"批准失败：{exc}")
        if clear_col.button("清除已批准章节讨论", key=scoped_widget_key("clear_chapter_discussion", *chapter_scope)):
            if clear_chapter_discussion_approval(project_name, chapter_no, story_id=story_id):
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
        if st.button("发送本章讨论消息", key=scoped_widget_key("send_chapter_discussion", *chapter_scope)):
            if not follow_up.strip():
                st.warning("讨论消息不能为空。")
            elif not requirement.strip():
                st.warning("请先填写本章要求。")
            else:
                try:
                    save_chapter_outline_metadata(project_name, chapter_no, {"volume_no": volume_no or None, "arc_no": arc_no or None}, story_id=story_id)
                    _append_discussion_message(messages_key, "user", follow_up)
                    messages = st.session_state.get(messages_key, [])
                    result = discuss_chapter_turn(
                        project_name,
                        chapter_no,
                        requirement,
                        messages,
                        discussion_step.get("data", {}).get("discussion", {}),
                        follow_up,
                        story_id=story_id,
                    )
                    st.session_state[result_key] = result
                    assistant_message = result.get("data", {}).get("assistant_message", "") or "我已经根据你的补充更新了本章讨论结论。"
                    _append_discussion_message(messages_key, "assistant", assistant_message)
                    st.session_state[clear_input_flag_key] = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"继续讨论失败：{exc}")

    if st.button("生成章节细纲", key=scoped_widget_key("generate_chapter_outline", *chapter_scope)):
        if approval_required:
            if volume_no and not (volume_discussion_artifact.get("discussion", {}) or {}).get("approval_ready"):
                st.error("当前分卷还没有已批准讨论工件，已阻止章节细纲生成。")
            elif arc_no and not (arc_discussion_artifact.get("discussion", {}) or {}).get("approval_ready"):
                st.error("当前剧情段还没有已批准讨论工件，已阻止章节细纲生成。")
            elif not (chapter_discussion_artifact.get("discussion", {}) or {}).get("approval_ready"):
                st.error("当前章节还没有已批准讨论工件，已阻止章节细纲生成。")
            else:
                result = generate_chapter_outline(project_name, chapter_no, requirement, volume_no=volume_no or None, arc_no=arc_no or None, story_id=story_id)
                step_result = result
                outline_value = result.get("data", {}).get("chapter_outline", "")
                st.session_state[chapter_outline_step_key] = result
                st.session_state[chapter_outline_text_key] = outline_value
                st.session_state[chapter_outline_editor_key] = outline_value
        else:
            result = generate_chapter_outline(project_name, chapter_no, requirement, volume_no=volume_no or None, arc_no=arc_no or None, story_id=story_id)
            step_result = result
            outline_value = result.get("data", {}).get("chapter_outline", "")
            st.session_state[chapter_outline_step_key] = result
            st.session_state[chapter_outline_text_key] = outline_value
            st.session_state[chapter_outline_editor_key] = outline_value

    outline_text = st.text_area(
        "章节细纲内容",
        value=st.session_state.get(chapter_outline_text_key, existing_outline),
        height=500,
        key=chapter_outline_editor_key,
    )

    if st.button("保存章节细纲", key=scoped_widget_key("save_chapter_outline", *chapter_scope)):
        save_chapter_outline(project_name, chapter_no, outline_text, story_id=story_id)
        save_chapter_outline_metadata(project_name, chapter_no, {"volume_no": volume_no or None, "arc_no": arc_no or None}, story_id=story_id)
        st.success(f"第 {chapter_no} 章细纲已保存")

    render_step_validation(step_result)
    render_step_retrieval(
        step_result,
        "本次细纲生成使用的检索上下文",
        get_retrieval_trace(f"chapter_outline:{project_name}:{chapter_no}")
    )


def render_chapter_page(project_name: str):
    story_id = st.session_state.get("active_story_id", "default")
    profile = load_creative_profile(project_name, story_id=story_id) or {}
    workflow_depth = profile.get("workflow_depth", "")
    is_chapter_mode = workflow_depth in {"完整长篇流程", "分卷/剧情段/章节", "章节计划+正文"}
    mode_hint = "章节模式" if is_chapter_mode else "自由模式"

    st.subheader("正文生成")
    st.caption(f"根据细纲或需求生成正文，可串联审阅和设定更新。当前：{mode_hint}")

    chapter_no = st.number_input(
        "编号" if not is_chapter_mode else "章节编号",
        min_value=1 if is_chapter_mode else 0,
        value=1,
        help="章节模式下按编号读写已有细纲和正文；自由模式下填 1 即可",
    )
    if not is_chapter_mode and chapter_no < 1:
        chapter_no = 1
    chapter_no = int(chapter_no)
    chapter_scope = (project_name, story_id, chapter_no)
    chapter_step_key = scoped_session_key("chapter_step", *chapter_scope)
    chapter_outline_gen_key = scoped_session_key("chapter_outline_gen", *chapter_scope)
    chapter_text_key = scoped_session_key("chapter_text", *chapter_scope)
    pipeline_result_key = scoped_session_key("pipeline_result", *chapter_scope)
    review_markdown_key = scoped_session_key("review_markdown", *chapter_scope)
    review_inline_step_key = scoped_session_key("review_step_inline", *chapter_scope)
    memory_update_step_key = scoped_session_key("memory_update_step", *chapter_scope)
    chapter_outline_editor_key = scoped_widget_key("chapter_write_outline_editor", *chapter_scope)
    chapter_text_editor_key = scoped_widget_key("chapter_text_editor", *chapter_scope)

    existing_outline = load_chapter_outline(project_name, chapter_no, story_id=story_id)
    existing_chapter = load_chapter(project_name, chapter_no, story_id=story_id)
    approved_discussion_artifact = load_chapter_discussion_artifact(project_name, chapter_no, story_id=story_id) if is_chapter_mode else {}
    discussion_guidance_default = _format_discussion_artifact_as_guidance(approved_discussion_artifact) if is_chapter_mode else ""
    chapter_step = st.session_state.get(chapter_step_key, {})

    word_count = st.text_input(
        "目标字数（如 2000-2500）",
        value="2000-2500",
        key=scoped_widget_key("content_word_count", *chapter_scope),
    )

    has_existing_outline = bool(existing_outline or st.session_state.get(chapter_outline_gen_key))

    if not has_existing_outline:
        st.info("没有已有细纲，可直接编写、从需求生成细纲、或从需求完整执行。")
        with st.expander("从需求自动执行", expanded=True):
            gen_requirement = st.text_area("创作需求", height=100, key=scoped_widget_key("auto_full_req", *chapter_scope),
                placeholder="例如：主角在废弃车站发现线索，与搭档产生分歧。")
            col_gen_outline, col_full_pipeline = st.columns(2)
            with col_gen_outline:
                if st.button("仅生成细纲", use_container_width=True, key=scoped_widget_key("gen_outline_btn", *chapter_scope)):
                    if not gen_requirement.strip():
                        st.warning("请先填写创作需求。")
                    else:
                        try:
                            with st.spinner("正在生成细纲..."):
                                outline_result = generate_chapter_outline(project_name, chapter_no, gen_requirement, story_id=story_id)
                            outline_text = outline_result.get("data", {}).get("chapter_outline", "")
                            if outline_text:
                                st.session_state[chapter_outline_gen_key] = outline_text
                                st.session_state[chapter_outline_editor_key] = outline_text
                                st.success("细纲已生成，将在上方细纲文本框中显示。")
                                st.rerun()
                            else:
                                st.error("细纲生成失败，请手工编写。")
                        except Exception as exc:
                            st.error(f"细纲生成失败：{exc}")
            with col_full_pipeline:
                if st.button("细纲→写作→审阅→更新设定", use_container_width=True, type="primary", key=scoped_widget_key("full_pipeline_btn", *chapter_scope)):
                    if not gen_requirement.strip():
                        st.warning("请先填写创作需求。")
                    else:
                        try:
                            with st.status("正在完整执行..."):
                                pipeline_result = pipeline_plan_write_review_update(
                                    project_name, chapter_no, gen_requirement, word_count, story_id=story_id
                                )
                            st.session_state[pipeline_result_key] = pipeline_result
                            chapter = pipeline_result.get("chapter", "") or pipeline_result.get("steps", {}).get("write_chapter", {}).get("data", {}).get("chapter", "")
                            if chapter:
                                st.session_state[chapter_text_key] = chapter
                                st.session_state[chapter_text_editor_key] = chapter
                            st.rerun()
                        except Exception as exc:
                            st.error(f"完整流水线执行失败：{exc}")

    chapter_outline_value = st.session_state.get(chapter_outline_gen_key, existing_outline)
    chapter_outline = st.text_area(
        "内容细纲" if not is_chapter_mode else "章节细纲",
        value=chapter_outline_value,
        height=250,
        key=chapter_outline_editor_key,
    )

    if is_chapter_mode:
        st.markdown("### 本章讨论与写作提示")
        st.caption("这里适合写临时想法、需要特别执行的写法、和已批准章节讨论的收束结论；生成正文时会并入写作补充要求。")
        discussion_guidance_key = scoped_widget_key("write_discussion_guidance", *chapter_scope)
        if discussion_guidance_default and discussion_guidance_key not in st.session_state:
            st.session_state[discussion_guidance_key] = discussion_guidance_default
        action_col, preview_col = st.columns([1, 1])
        if action_col.button("用已批准章节讨论填入", key=scoped_widget_key("fill_discussion_guidance", *chapter_scope)):
            if discussion_guidance_default:
                st.session_state[discussion_guidance_key] = discussion_guidance_default
                st.success("已填入已批准章节讨论。")
            else:
                st.warning("当前章节还没有已批准讨论工件。")
        with preview_col.expander("查看已批准章节讨论", expanded=False):
            _render_approved_discussion_artifact(approved_discussion_artifact, "当前章节还没有已批准讨论工件。")
        discussion_guidance = st.text_area(
            "讨论/指导提示",
            height=160,
            key=discussion_guidance_key,
            placeholder="例如：这一章重点写两人关系试探；冲突先压住，不急着摊牌；结尾让主角意识到线索来自旧案。",
        )
    else:
        discussion_guidance = ""
        st.markdown("### 写作提示（可选）")
        discussion_guidance = st.text_area(
            "补充提示",
            height=80,
            key=scoped_widget_key("write_notes", *chapter_scope),
            placeholder="例如：整体语气轻松，结尾留悬念。",
        )

    st.markdown("### 当前写作设置")
    tone = st.selectbox(
        "文风/基调",
        options=["", "克制", "热血", "轻快", "压抑", "爽文推进"],
        format_func=lambda value: value or "未特别指定",
        key=scoped_widget_key("write_tone", *chapter_scope),
    )
    pacing = st.selectbox(
        "节奏",
        options=["", "慢铺", "均衡", "快推"],
        format_func=lambda value: value or "未特别指定",
        key=scoped_widget_key("write_pacing", *chapter_scope),
    )
    dialogue_density = st.selectbox(
        "对话密度",
        options=["", "低", "中", "高"],
        format_func=lambda value: value or "未特别指定",
        key=scoped_widget_key("write_dialogue_density", *chapter_scope),
    )
    focus = st.multiselect(
        "描写重点",
        options=["动作", "心理", "环境", "关系拉扯", "战斗", "信息揭示"],
        key=scoped_widget_key("write_focus", *chapter_scope),
    )
    ending_strength = st.selectbox(
        "结尾力度",
        options=["", "轻钩子", "强钩子", "悬念断点"],
        format_func=lambda value: value or "未特别指定",
        key=scoped_widget_key("write_ending_strength", *chapter_scope),
    )
    extra_requirements = st.text_area(
        "写作补充要求",
        height=120,
        key=scoped_widget_key("write_extra_requirements", *chapter_scope),
        placeholder="例如：减少说明性段落，多写试探性对话，结尾用短句收束。",
    )
    combined_extra_requirements_parts = []
    if discussion_guidance.strip():
        combined_extra_requirements_parts.append(f"写作提示：\n{discussion_guidance.strip()}")
    if extra_requirements.strip():
        combined_extra_requirements_parts.append(f"补充要求：\n{extra_requirements.strip()}")
    combined_extra_requirements = "\n\n".join(combined_extra_requirements_parts)

    writing_guidance = {
        "tone": tone,
        "pacing": pacing,
        "dialogue_density": dialogue_density,
        "focus": focus,
        "ending_strength": ending_strength,
        "extra_requirements": combined_extra_requirements,
    }

    has_outline = bool(chapter_outline.strip())

    col_write, col_pipeline = st.columns([1, 1])
    with col_write:
        write_clicked = st.button("写正文", type="primary" if has_outline else "secondary", use_container_width=True, key=scoped_widget_key("write_chapter_btn", *chapter_scope))
    with col_pipeline:
        pipeline_clicked = st.button(
            "细纲→写作→审阅→更新设定" if has_outline else "需要先填写或生成细纲",
            disabled=not has_outline,
            use_container_width=True,
            key=scoped_widget_key("inline_pipeline_btn", *chapter_scope),
        )

    if write_clicked:
        result = write_chapter(project_name, chapter_no, chapter_outline, writing_guidance, word_count, story_id=story_id)
        chapter = result.get("data", {}).get("chapter", "")
        st.session_state[chapter_step_key] = result
        st.session_state[chapter_text_key] = chapter
        st.session_state[chapter_text_editor_key] = chapter
        st.rerun()

    if pipeline_clicked and has_outline:
        try:
            with st.status("正在执行流水线..."):
                steps_result = {}
                write_result = write_chapter(project_name, chapter_no, chapter_outline, writing_guidance, word_count, story_id=story_id)
                steps_result["write_chapter"] = write_result
                chapter = write_result.get("data", {}).get("chapter", "")
                if not chapter:
                    raise RuntimeError(write_result.get("error", "正文生成失败"))

                review_result = review_chapter(project_name, chapter_no, chapter, story_id=story_id)
                steps_result["review_chapter"] = review_result
                review_markdown = review_result.get("data", {}).get("review_markdown", "")

                review_success = bool(review_result.get("success")) and review_result.get("status") not in {"failed", "rejected", "blocked"}
                if review_success:
                    memory_result = update_memory_from_chapter(project_name, chapter_no, chapter, story_id=story_id)
                else:
                    memory_result = {
                        "step_name": "memory_update",
                        "success": False,
                        "status": "skipped",
                        "warnings": ["章节审阅未通过或未完成，已跳过核心设定更新。"],
                    }
                steps_result["memory_update"] = memory_result

            st.session_state[chapter_text_key] = chapter
            st.session_state[chapter_text_editor_key] = chapter
            st.session_state[pipeline_result_key] = {
                "steps": steps_result,
                "review_markdown": review_markdown,
            }
            if review_markdown:
                st.session_state[review_markdown_key] = review_markdown
            st.rerun()
        except Exception as exc:
            st.error(f"流水线执行失败：{exc}")

    with st.expander("当前写作指导", expanded=False):
        if discussion_guidance.strip():
            st.markdown("#### 写作提示")
            st.markdown(discussion_guidance)
        render_step_json_expander("写作指导参数", writing_guidance)

    chapter_text = st.text_area(
        "正文" if not is_chapter_mode else "章节正文",
        value=st.session_state.get(chapter_text_key, existing_chapter),
        height=600,
        key=chapter_text_editor_key,
    )

    save_col, review_col, memory_col = st.columns(3)
    with save_col:
        if st.button("保存正文", use_container_width=True):
            save_chapter(project_name, chapter_no, chapter_text, story_id=story_id)
            st.success("正文已保存")

    with review_col:
        has_chapter = bool(chapter_text.strip())
        do_review = st.button(
            "审阅正文" if has_chapter else "需要先生成正文",
            disabled=not has_chapter,
            key=scoped_widget_key("review_inline", *chapter_scope),
            use_container_width=True,
        )
        if do_review and has_chapter:
            try:
                result = review_chapter(project_name, chapter_no, chapter_text, story_id=story_id)
                st.session_state[review_inline_step_key] = result
                st.session_state[review_markdown_key] = result.get("data", {}).get("review_markdown", "")
                st.rerun()
            except Exception as exc:
                st.error(f"审阅失败：{exc}")

    with memory_col:
        do_memory = st.button(
            "更新核心设定" if has_chapter else "需要先生成正文",
            disabled=not has_chapter,
            key=scoped_widget_key("memory_inline", *chapter_scope),
            use_container_width=True,
        )
        if do_memory and has_chapter:
            result = update_memory_from_chapter(project_name, chapter_no, chapter_text, story_id=story_id)
            st.session_state[memory_update_step_key] = result
            render_step_status_message(result, "核心设定更新成功", "核心设定更新失败：")
            render_step_validation(result)
            render_step_json_expander("设定更新结构化数据", result)

    review_markdown = st.session_state.get(review_markdown_key, "")
    if review_markdown:
        with st.expander("审阅结果", expanded=True):
            st.markdown(review_markdown)

    pipeline_result = st.session_state.get(pipeline_result_key, {})
    if pipeline_result:
        expanded_by_default = bool(pipeline_result.get("steps", {}).get("write_chapter", {}).get("success"))
        with st.expander("流水线执行详情", expanded=not expanded_by_default):
            pipeline_steps = pipeline_result.get("steps", {})
            for step_label, step_key in [("细纲", "chapter_outline"), ("写作", "write_chapter"), ("审阅", "review_chapter"), ("设定更新", "memory_update")]:
                step_result = pipeline_steps.get(step_key, {})
                if step_result:
                    status = step_result.get("status", "-")
                    st.caption(f"{step_label}：{label_status(status)}")
                    render_step_validation(step_result)
            pipeline_markdown = pipeline_result.get("review_markdown", "") or pipeline_steps.get("review_chapter", {}).get("data", {}).get("review_markdown", "")
            if pipeline_markdown:
                st.markdown("#### 审阅结果")
                st.markdown(pipeline_markdown)

    render_step_validation(chapter_step)
    render_step_retrieval(
        chapter_step,
        "本次正文生成使用的检索上下文",
        get_retrieval_trace(f"write:{project_name}:{chapter_no}")
    )
    render_step_retrieval(
        st.session_state.get(review_inline_step_key, {}),
        "本次审阅使用的检索上下文",
        get_retrieval_trace(f"review:{project_name}:{chapter_no}")
    )
    render_step_retrieval(
        st.session_state.get(memory_update_step_key, {}),
        "本次设定更新使用的检索上下文",
        get_retrieval_trace(f"memory_update:{project_name}:{chapter_no}")
    )


def render_project_overview_page(project_name: str):
    story_id = st.session_state.get("active_story_id", "default")
    summary = get_project_summary(project_name, story_id=story_id)
    overview_title = html.escape(str(summary.get("title", project_name) or project_name))
    overview_genre = html.escape(str(summary.get("genre", "-") or "-"))
    overview_canon_mode = html.escape(str(summary.get("canon_mode", "-") or "-"))
    overview_updated_at = html.escape(str(summary.get("updated_at", "-") or "-"))

    st.markdown(
        f"""
        <div class="nf-card">
            <div class="nf-card-title">当前创作状态</div>
            <div class="nf-card-copy">
                书名：{overview_title} /
                类型：{overview_genre} /
                原作对齐：{overview_canon_mode} /
                更新时间：{overview_updated_at}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 常用入口")
    action_col1, action_col2, action_col3, action_col4 = st.columns(4)
    with action_col1:
        render_quick_action("快速生成", "快速生成", "实验性快速生成入口，适合测试或临时片段。")
    with action_col2:
        render_quick_action("正文生成", "正文生成", "根据细纲或需求写作，可串联审阅和设定更新。")
    with action_col3:
        render_quick_action("整理资料", "资料导入", "导入原作、参考和长文本资料。")
    with action_col4:
        render_quick_action("查看资源", "资源浏览器", "集中管理章节、报告和来源文件。")

    st.markdown("### 项目指标")
    col1, col2, col3, col4, col5 = st.columns(5)
    render_resource_metric_link(col1, project_name, story_id, "正文章节", summary.get("chapter_count", 0), ["chapter_content"])
    render_resource_metric_link(col2, project_name, story_id, "细纲章节", summary.get("chapter_outline_count", 0), ["chapter_outline"])
    render_resource_metric_link(col3, project_name, story_id, "审阅数量", summary.get("review_count", 0), ["review"])
    render_resource_metric_link(col4, project_name, story_id, "分析报告", summary.get("analysis_count", 0), ["analysis"])
    render_resource_metric_link(col5, project_name, story_id, "评估报告", summary.get("evaluation_count", 0), ["evaluation"])

    col6, col7, col8, col9, col12, col13, col14 = st.columns(7)
    render_resource_metric_link(col6, project_name, story_id, "分卷数量", summary.get("volume_count", 0), ["volume_outline"])
    render_resource_metric_link(col7, project_name, story_id, "剧情段数量", summary.get("arc_count", 0), ["arc_outline"])
    render_resource_metric_link(col8, project_name, story_id, "流水线记录", summary.get("run_count", 0), ["run"])
    render_resource_metric_link(col9, project_name, story_id, "外部资料", summary.get("retrieval_source_count", 0), ["source"])
    render_resource_metric_link(col12, project_name, story_id, "结构化知识", summary.get("knowledge_item_count", 0), ["knowledge_item"])
    render_resource_metric_link(col13, project_name, story_id, "待确认知识", summary.get("pending_knowledge_count", 0), ["pending_knowledge"])
    render_resource_metric_link(col14, project_name, story_id, "资料批次", summary.get("long_reference_batch_count", 0), ["long_reference_batch"])

    col10, col11 = st.columns(2)
    render_resource_metric_link(col10, project_name, story_id, "已批准分卷讨论", summary.get("approved_volume_count", 0), ["volume_discussion"])
    render_resource_metric_link(col11, project_name, story_id, "已批准剧情段讨论", summary.get("approved_arc_count", 0), ["arc_discussion"])

    st.caption(f"章节摘要={summary.get('chapter_summary_count', 0)} / 资源文件数={summary.get('resource_file_count', 0)}")

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


def render_settings_page(project_name: str):
    story_id = st.session_state.get("active_story_id", "default")
    stories = list_stories(project_name)
    current_story_name = "默认"
    for s in stories:
        if s.get("story_id") == story_id:
            current_story_name = s.get("name", story_id)
            break

    st.subheader(f"核心设定 · {current_story_name}")
    st.caption("故事级设定仅影响当前故事；项目级设定为所有故事共享。创意方向和生成流程请到「创作配置」页面配置。")

    story_tab, project_tab = st.tabs(["故事设定", "项目设定"])

    with story_tab:
        _render_story_settings_tab(project_name, story_id, current_story_name)

    with project_tab:
        _render_project_settings_tab(project_name)


def _render_story_settings_tab(project_name: str, story_id: str, story_name: str):
    st.markdown("#### 设定复制与导入")

    merge_key = f"merge_preview_{story_id}"
    pending_merge = st.session_state.get(merge_key)

    if pending_merge:
        st.markdown("##### 合并预览")
        for opt in pending_merge:
            if opt.conflict:
                st.markdown(f"**{opt.label}**")
                st.caption(f"来源：`{opt.source_value}`　目标：`{opt.target_value}`")
                choice = st.radio(
                    "保留",
                    options=["source", "target", "merged"] if opt.field_type == "list" else ["source", "target"],
                    format_func=lambda c: {"source": "来源值", "target": "目标值", "merged": "合并去重"}.get(c, c),
                    horizontal=True,
                    key=f"merge_{opt.path}",
                )
                opt.resolution_choice = choice
                opt.resolution = {"source": opt.source_value, "target": opt.target_value, "merged": (
                    list(dict.fromkeys(str(v) for v in (opt.source_value or []) + (opt.target_value or [])))
                    if opt.field_type == "list" else opt.source_value
                )}.get(choice, opt.source_value)
            else:
                opt.resolution = opt.source_value if opt.source_value is not None else opt.target_value
                opt.resolution_choice = "source"

        confirm_col, cancel_col = st.columns(2)
        if confirm_col.button("确认合并", use_container_width=True):
            action = pending_merge[0].path.split(".")[0] if pending_merge else ""
            field_resolutions = {}
            for opt in pending_merge:
                parts = opt.path.split(".", 1)
                if len(parts) != 2:
                    continue
                field_resolutions[f"memory.{parts[1]}"] = opt.resolution
            if action == "project_to_story":
                merge_project_to_story_memory(project_name, story_id, field_resolutions=field_resolutions)
                st.success("已从项目导入设定到当前故事")
            elif action == "story_to_project":
                merge_story_to_project_memory(project_name, story_id, field_resolutions=field_resolutions)
                st.success("已合并当前故事设定到项目基础设定")
            elif action == "story_to_story":
                copy_story_settings(project_name, pending_merge[0].path.split(".")[1] if len(pending_merge[0].path.split(".")) > 1 else "", story_id)
                st.success("已从其他故事导入设定")
            st.session_state.pop(merge_key)
            st.rerun()
        if cancel_col.button("取消", use_container_width=True):
            st.session_state.pop(merge_key)
            st.rerun()
    else:
        col_a, col_b, col_c = st.columns(3)
        if col_a.button("从项目导入设定", use_container_width=True):
            from merge import build_merge_plan
            base = load_memory(project_name)
            story = load_story_memory(project_name, story_id)
            plan = build_merge_plan(base, story, source_label="项目", target_label="故事")
            for opt in plan:
                opt.path = f"project_to_story.{opt.path}"
            st.session_state[merge_key] = plan
            st.rerun()

        other_stories = [s for s in list_stories(project_name) if s.get("story_id") != story_id]
        if other_stories:
            sel_story = col_b.selectbox("从其他故事导入", options=[s.get("story_id") for s in other_stories],
                                         format_func=lambda sid: next((s.get("name", sid) for s in other_stories if s["story_id"] == sid), sid),
                                         key="settings_import_story", label_visibility="collapsed")
            if col_b.button("导入", use_container_width=True, key="import_other_story"):
                copy_story_settings(project_name, sel_story, story_id)
                st.success("已从其他故事导入设定到当前故事")
                st.rerun()

        if col_c.button("设为项目默认", use_container_width=True):
            from merge import build_merge_plan
            base = load_memory(project_name)
            story = load_story_memory(project_name, story_id)
            plan = build_merge_plan(story, base, source_label="故事", target_label="项目")
            for opt in plan:
                opt.path = f"story_to_project.{opt.path}"
            st.session_state[merge_key] = plan
            st.rerun()

    st.divider()
    st.markdown(f"#### {story_name} 的核心设定")
    memory = load_story_memory(project_name, story_id)
    render_memory_page(project_name, memory, embedded=True)


def _render_project_settings_tab(project_name: str):
    base_memory = load_memory(project_name)
    st.markdown("#### 项目基础设定（所有故事共享）")
    changed = False
    new_memory = dict(base_memory)

    new_title = st.text_input("书名", value=base_memory.get("title", ""), key="project_title")
    if new_title != base_memory.get("title"):
        new_memory["title"] = new_title
        changed = True
    new_genre = st.text_input("类型", value=base_memory.get("genre", ""), key="project_genre")
    if new_genre != base_memory.get("genre"):
        new_memory["genre"] = new_genre
        changed = True

    for field in [
        "canon_mode",
        "au_rules",
        "world",
        "characters",
        "relationships",
        "timeline",
        "foreshadowing",
        "active_constraints",
        "locations",
        "organizations",
        "power_systems",
        "relationship_graph",
    ]:
        label_map = {
            "canon_mode": "原作对齐方式",
            "au_rules": "架空规则",
            "world": "世界观", "characters": "角色", "relationships": "角色关系",
            "timeline": "时间线", "foreshadowing": "伏笔", "active_constraints": "硬性约束",
            "locations": "地点资料", "organizations": "组织资料", "power_systems": "能力体系",
            "relationship_graph": "关系图补充",
        }
        raw_value = base_memory.get(field, "")
        value = raw_value if isinstance(raw_value, str) else "\n".join(str(item) for item in raw_value)
        new_value = st.text_area(label_map.get(field, field), value=value, height=100, key=f"project_{field}")
        if isinstance(raw_value, str):
            if new_value != raw_value:
                new_memory[field] = new_value
                changed = True
        else:
            new_items = [line.strip() for line in new_value.split("\n") if line.strip()]
            if new_items != base_memory.get(field, []):
                new_memory[field] = new_items
                changed = True

    if st.button("保存项目设定", disabled=not changed):
        save_memory(project_name, new_memory)
        st.success("已保存")
        st.rerun()
    if not changed:
        st.caption("当前表单没有未保存改动。")

    render_core_setting_to_knowledge_tool(
        project_name,
        new_memory,
        "项目基础设定",
        "project_base",
    )

    st.divider()
    st.markdown("#### 项目知识库")
    knowledge = load_knowledge_base(project_name)
    total_items = sum(len(items) for items in knowledge.values())
    st.caption(f"共 {len(knowledge)} 个分类，{total_items} 条知识条目。详细信息请到「资料导入」页面管理。")
    for cat, items in knowledge.items():
        if items:
            with st.expander(f"{label_knowledge_category(cat)}（{len(items)} 条）", expanded=False):
                for item in items:
                    st.markdown(f"- **{item.get('name', '-')}**：{str(item.get('content', ''))[:200]}")
    if st.button("前往资料导入", use_container_width=True, key="goto_ingestion"):
        navigate_to("资料导入")


def _render_story_management_tab(project_name: str):
    stories = list_stories(project_name)
    st.markdown(f"#### 故事列表（共 {len(stories)} 个）")

    for s in stories:
        story_id = str(s.get("story_id") or "")
        cols = st.columns([3, 1, 1, 1, 1, 1])
        cols[0].write(f"**{s.get('name', s['story_id'])}**  ({s['story_id']})")
        cols[1].write(s.get("status", "active"))
        cols[2].write(s.get("created_at", "")[:10])

        is_active = story_id == st.session_state.get("active_story_id", "default")
        if cols[3].button("切换", key=f"switch_{story_id}", disabled=is_active, use_container_width=True):
            set_active_story(project_name, story_id)
            st.session_state["active_story_id"] = story_id
            st.rerun()

        with cols[4].popover("编辑", use_container_width=True):
            st.caption(f"故事 ID：`{story_id}`")
            new_story_name = st.text_input(
                "故事名称",
                value=str(s.get("name") or story_id),
                key=f"rename_story_name_{story_id}",
            )
            new_story_description = st.text_area(
                "故事描述",
                value=str(s.get("description") or ""),
                height=80,
                key=f"rename_story_desc_{story_id}",
            )
            if st.button("保存故事信息", key=f"save_story_meta_{story_id}", use_container_width=True):
                try:
                    rename_story(project_name, story_id, new_story_name, new_story_description)
                    st.success("故事信息已更新。")
                    st.rerun()
                except Exception as exc:
                    st.error(f"保存失败：{exc}")

        if cols[5].button("复制", key=f"copy_{story_id}", use_container_width=True):
            try:
                new_story_name = f"{s.get('name') or story_id} 副本"
                meta = create_story(project_name, new_story_name, str(s.get("description") or ""))
                copy_story_settings(project_name, story_id, meta["story_id"])
                st.success(f"已复制设定到新故事：{meta.get('name') or meta['story_id']}")
                st.rerun()
            except Exception as exc:
                st.error(f"复制失败：{exc}")

    st.divider()
    st.markdown("#### 创建新故事")
    with st.popover("新故事", use_container_width=True):
        new_story_name = st.text_input("故事名称", key="settings_new_story_name")
        new_story_desc = st.text_area("故事描述", height=80, key="settings_new_story_desc",
                                       placeholder="例如：原作线续写、平行世界、角色穿越...")
        copy_from = st.checkbox("从当前故事复制创作配置和核心设定", value=True)
        if st.button("创建故事"):
            if new_story_name.strip():
                meta = create_story(project_name, new_story_name.strip(), new_story_desc.strip())
                if copy_from:
                    copy_story_settings(project_name, st.session_state.get("active_story_id", "default"), meta["story_id"])
                set_active_story(project_name, meta["story_id"])
                st.session_state["active_story_id"] = meta["story_id"]
                st.success(f"已创建故事：{new_story_name.strip()}")
                st.rerun()
            else:
                st.error("故事名称不能为空。")

    st.divider()
    st.markdown("#### 模型配置")
    render_llm_settings_page()


def render_creative_profile_page(project_name: str, embedded: bool = False):
    story_id = st.session_state.get("active_story_id", "default")
    stories = list_stories(project_name)
    current_story_name = "默认"
    for s in stories:
        if s.get("story_id") == story_id:
            current_story_name = s.get("name", story_id)
            break
    if not embedded:
        st.subheader(f"创作配置 · {current_story_name}")
        st.info(
            f"当前正在配置 **{current_story_name}** 的创作参数。"
            "创作配置是故事级别的——同一项目不同故事可以设置各自的篇幅、参考强度和生成层级。"
            "项目级别的资料（知识库、原材料、规则）为所有故事共享。",
            icon="📖",
        )

    profile = load_creative_profile(project_name, story_id=story_id)
    _init_creative_profile_form_state(project_name, story_id, profile)
    form_state = _get_creative_profile_form_state(project_name, story_id)
    profile_keys = _creative_profile_form_keys(project_name, story_id)
    story_modes = ["主线故事", "番外", "续写", "前传", "穿越", "平行世界", "原作补完", "单场景片段", "设定补写"]
    target_lengths = ["片段", "短篇", "中篇", "长篇"]
    workflow_depths = ["只生成正文", "短篇结构+正文", "章节计划+正文", "分卷/剧情段/章节", "完整长篇流程"]
    reference_strengths = ["轻参考", "中参考", "强参考", "严格原作", "主要参考文风"]
    focus_options = ["角色", "世界观", "剧情事件", "道具能力", "时间线", "写作风格", "对白风格", "写作手法", "硬性约束"]
    conflict_policies = ["优先项目设定", "优先原作资料", "人工确认", "保留多版本"]

    creative_discussion_suffix = f"{project_name}:{story_id}"
    discussion_messages_key = _discussion_messages_key("creative_profile", creative_discussion_suffix)
    discussion_result_key = _discussion_result_key("creative_profile", creative_discussion_suffix)
    discussion_input_key = _discussion_input_key("creative_profile", creative_discussion_suffix)
    clear_input_flag_key = _discussion_input_clear_flag_key("creative_profile", creative_discussion_suffix)
    _consume_discussion_input_clear("creative_profile", creative_discussion_suffix)
    discussion_step = st.session_state.get(discussion_result_key, {})
    with st.expander("讨论辅助", expanded=not form_state.get("story_mode") or form_state["story_mode"] == "主线故事"):
        st.caption("用自然语言描述目标，讨论结果会自动填入下方表单。")
        col_seed, col_action = st.columns([3, 1])
        with col_seed:
            user_idea = st.text_area(
                "这次想写什么",
                height=100,
                key=scoped_widget_key("creative_profile_discussion_seed", project_name, story_id),
                placeholder="例如：想写一个偏伤感的现代都市架空续写，只保留原作人物关系和说话风格，不保留原作结局。",
                label_visibility="collapsed",
            )
        with col_action:
            st.write("")
            st.write("")
            if st.button("开始讨论", key=scoped_widget_key("start_creative_profile_discussion", project_name, story_id), use_container_width=True):
                if not user_idea.strip():
                    st.warning("请先描述这次想写什么。")
                else:
                    try:
                        result = discuss_creative_profile(project_name, user_idea, story_id=story_id)
                        st.session_state[discussion_result_key] = result
                        st.session_state[discussion_messages_key] = []
                        assistant_message = result.get("data", {}).get("discussion", {}).get("current_understanding", "") or "我先整理了当前理解、推荐配置方向和待确认问题，我们可以继续细化。"
                        _append_discussion_message(discussion_messages_key, "assistant", assistant_message)
                        recommended = result.get("data", {}).get("discussion", {}).get("recommended_profile", {})
                        if recommended:
                            _set_creative_profile_form_state(project_name, story_id, recommended)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"讨论失败：{exc}")
            if st.button("重置", key=scoped_widget_key("reset_creative_profile_discussion", project_name, story_id), use_container_width=True):
                st.session_state[discussion_result_key] = {}
                st.session_state[discussion_messages_key] = []
                st.session_state[clear_input_flag_key] = True
                st.rerun()

        if discussion_step or st.session_state.get(discussion_messages_key, []):
            summary_col, chat_col = st.columns([1, 1])
            with summary_col:
                st.markdown("##### 当前结论")
                _render_discussion_summary(discussion_step, "")
                render_step_retrieval(discussion_step, "讨论参考的上传资料")
                discussion_payload = discussion_step.get("data", {}).get("discussion", {}) if discussion_step else {}
                recommended_profile = discussion_payload.get("recommended_profile", {}) if isinstance(discussion_payload, dict) else {}
                action_col1, action_col2 = st.columns(2)
                if action_col1.button("应用推荐到表单", use_container_width=True, key=scoped_widget_key("apply_profile_rec", project_name, story_id)):
                    if not recommended_profile:
                        st.warning("当前还没有可应用的推荐配置。")
                    else:
                        _set_creative_profile_form_state(project_name, story_id, recommended_profile)
                        st.success("已将推荐配置回填到表单。")
                        st.rerun()
                if action_col2.button("批准并保存", use_container_width=True, key=scoped_widget_key("approve_profile_rec", project_name, story_id)):
                    try:
                        result = approve_creative_profile_discussion(project_name, discussion_step, story_id=story_id)
                        _set_creative_profile_form_state(project_name, story_id, result.get("saved_profile", {}))
                        st.success("已保存创作配置。")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"批准失败：{exc}")
            with chat_col:
                st.markdown("##### 对话")
                messages = st.session_state.get(discussion_messages_key, [])
                _render_discussion_chat(messages)
                follow_up = st.text_area(
                    "继续讨论",
                    key=discussion_input_key,
                    height=80,
                    placeholder="例如：我希望重点保留人物关系，但剧情走向可以明显偏离原作。",
                    label_visibility="collapsed",
                )
                if st.button("发送", key=scoped_widget_key("send_creative_profile_discussion", project_name, story_id), use_container_width=True):
                    if not follow_up.strip():
                        st.warning("讨论消息不能为空。")
                    elif not user_idea.strip():
                        st.warning("请先填写这次想写什么。")
                    else:
                        try:
                            _append_discussion_message(discussion_messages_key, "user", follow_up)
                            messages = st.session_state.get(discussion_messages_key, [])
                            result = discuss_creative_profile_turn(
                                project_name, user_idea, messages,
                                discussion_step.get("data", {}).get("discussion", {}),
                                follow_up, story_id=story_id,
                            )
                            st.session_state[discussion_result_key] = result
                            assistant_message = result.get("data", {}).get("assistant_message", "") or "已更新创作配置建议。"
                            _append_discussion_message(discussion_messages_key, "assistant", assistant_message)
                            recommended = result.get("data", {}).get("discussion", {}).get("recommended_profile", {})
                            if recommended:
                                _set_creative_profile_form_state(project_name, story_id, recommended)
                            st.session_state[clear_input_flag_key] = True
                            st.rerun()
                        except Exception as exc:
                            st.error(f"继续讨论失败：{exc}")

    with st.form(scoped_widget_key("creative_profile_form", project_name, story_id)):
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
        col_worldline_a, col_worldline_b, col_worldline_c = st.columns([1, 1, 1])
        worldline_id = col_worldline_a.text_input(
            "当前世界线 ID",
            value=form_state.get("worldline_id", DEFAULT_WORLDLINE_ID),
            placeholder="例如：main、au_modern、branch_01",
            key=profile_keys["worldline_id"],
            help="用于 RAG 检索过滤和加权。建议使用稳定英文/拼音/数字 ID。",
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
        notes = st.text_area(
            "自由说明",
            value=form_state.get("notes", ""),
            height=140,
            placeholder="这里可以写任何复杂规则。例如：这次是半架空续写，只保留角色关系和说话风格，不保留原作结局；世界观改成现代都市，但能力体系保留原作限制。",
            key=profile_keys["notes"],
        )
        form_actions = st.columns([1, 1, 3])
        submitted = form_actions[0].form_submit_button("保存创作配置", use_container_width=True)

    if submitted:
        saved = save_creative_profile(project_name, build_creative_profile_from_form_values(
            story_mode,
            target_length,
            target_word_count,
            workflow_depth,
            reference_strength,
            conflict_policy,
            reference_focus,
            custom_reference_focus,
            allow_canon_deviation,
            worldline_id,
            worldline_label,
            worldline_retrieval_mode,
            notes,
        ), story_id=story_id, mark_configured=True)
        _set_creative_profile_form_state(project_name, story_id, saved)
        st.success("创作配置已保存。")
        profile = saved
    else:
        preview_profile = build_creative_profile_from_form_values(
            story_mode,
            target_length,
            target_word_count,
            workflow_depth,
            reference_strength,
            conflict_policy,
            reference_focus,
            custom_reference_focus,
            allow_canon_deviation,
            worldline_id,
            worldline_label,
            worldline_retrieval_mode,
            notes,
        )
        profile = preview_profile

    st.markdown("### 推荐生成路径")
    workflow = recommended_workflow_for_profile(profile)
    st.markdown(" / ".join(workflow))

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
    story_id = st.session_state.get("active_story_id", "default")
    st.subheader("快速生成")
    st.caption("实验性快速生成入口。只靠一段提示词就能生成，也可以展开高级配置进行精细控制。不需要预先配置创作配置。")

    profile = load_creative_profile(project_name, story_id=story_id) or {}
    if profile.get("is_configured"):
        st.caption(f"当前故事配置：{profile.get('story_mode', '主线故事')} / {profile.get('target_length', '长篇')} / 参考 {profile.get('reference_strength', '中参考')}")

    requirement = st.text_area(
        "创作提示词",
        height=200,
        key="quick_gen_requirement",
        placeholder="例如：写一个 500 字的开场，主角在雨中遇到神秘人，气氛要压抑。",
    )

    col_run, col_save = st.columns([3, 1])
    with col_save:
        chapter_no = st.number_input("保存到章节", min_value=0, value=0, key="quick_gen_chapter_no",
                                     help="0 表示不保存，仅预览。")

    with st.expander("高级配置", expanded=False):
        default_word_count = profile.get("target_word_count", "") or "2000-2500"
        word_count = st.text_input("目标字数", value=default_word_count, key="quick_gen_word_count")
        workflow_depth_options = ["只生成正文", "短篇结构+正文", "章节计划+正文"]
        workflow_depth = st.selectbox(
            "生成层级",
            options=workflow_depth_options,
            index=0,
            key="quick_gen_workflow_depth",
        )
        st.caption("短篇结构会先生成创作结构再写正文；章节计划会先生成细纲再写正文。只生成正文则直接输出。")

        st.markdown("#### 写作参数")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            tone = st.selectbox(
                "文风/基调",
                options=["", "克制", "热血", "轻快", "压抑", "爽文推进"],
                format_func=lambda v: v or "未指定",
                key="quick_gen_tone",
            )
        with col_b:
            pacing = st.selectbox(
                "节奏",
                options=["", "慢铺", "均衡", "快推"],
                format_func=lambda v: v or "未指定",
                key="quick_gen_pacing",
            )
        with col_c:
            dialogue_density = st.selectbox(
                "对话密度",
                options=["", "低", "中", "高"],
                format_func=lambda v: v or "未指定",
                key="quick_gen_dialogue",
            )
        focus = st.multiselect(
            "描写重点",
            options=["动作", "心理", "环境", "关系拉扯", "战斗", "信息揭示"],
            key="quick_gen_focus",
        )
        col_d, col_e = st.columns(2)
        with col_d:
            ending_strength = st.selectbox(
                "结尾力度",
                options=["", "轻钩子", "强钩子", "悬念断点"],
                format_func=lambda v: v or "未指定",
                key="quick_gen_ending",
            )
        with col_e:
            extra_requirements = st.text_area(
                "补充要求",
                height=80,
                key="quick_gen_extra",
                placeholder="例如：减少说明性段落，多用短句。",
            )

    if col_run.button("生成", use_container_width=True, type="primary"):
        if not requirement.strip():
            st.error("请先填写创作提示词。")
        else:
            try:
                effective_chapter_no = int(chapter_no) or 1
                writing_guidance = {
                    "tone": tone,
                    "pacing": pacing,
                    "dialogue_density": dialogue_density,
                    "focus": focus,
                    "ending_strength": ending_strength,
                    "extra_requirements": extra_requirements,
                }
                with st.spinner("正在生成..."):
                    result = run_dynamic_generation_task(
                        project_name,
                        effective_chapter_no,
                        requirement,
                        word_count,
                        workflow_depth,
                        story_id=story_id,
                        writing_guidance=writing_guidance,
                    )
                st.session_state["dynamic_generation_result"] = result
                st.rerun()
            except Exception as exc:
                st.error(f"生成失败：{exc}")

    result = st.session_state.get("dynamic_generation_result", {})
    if not result:
        return

    if result.get("success"):
        st.success("生成完成。")
    else:
        st.error(f"生成未完成：{result.get('status', '未知状态')}")

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

    render_step_json_expander("生成结构化数据", result)


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
    st.caption(f"推荐路径：{' / '.join(recommended_workflow_for_profile(preview_profile))}")
    render_step_json_expander("向导生成的配置预览", preview_profile)

    if st.button("保存向导配置"):
        saved = save_creative_profile(project_name, preview_profile, story_id=story_id, mark_configured=True)
        _set_creative_profile_form_state(project_name, story_id, saved)
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

        quality_issues = build_pending_knowledge_quality_issues(project_name, pending_items)
        issue_map = build_pending_issue_map(quality_issues)
        policy = load_auto_review_policy(project_name)

        render_pending_triage_dashboard(project_name, pending_items, issue_map, policy)
        render_pending_knowledge_quality_panel(project_name, pending_items)
        filtered_indices = filter_pending_knowledge_indices(pending_items, issue_map)

        st.caption(f"当前筛选结果：{len(filtered_indices)} / {pending_count} 条")
        if filtered_indices:
            metric_cols = st.columns(4)
            metric_cols[0].metric("高风险", sum(1 for index in filtered_indices if issue_map.get(str(pending_items[index].get("pending_id", "")), {}).get("severity") == "高"))
            metric_cols[1].metric("低证据", sum(1 for index in filtered_indices if safe_confidence(pending_items[index].get("evidence_strength", 0.5)) < 0.45))
            metric_cols[2].metric("低置信", sum(1 for index in filtered_indices if safe_confidence(pending_items[index].get("confidence", 0.7)) < 0.55))
            metric_cols[3].metric("正式库重叠", sum(1 for index in filtered_indices if "confirmed_overlap" in issue_map.get(str(pending_items[index].get("pending_id", "")), {}).get("types", set())))

        selected_indices = st.multiselect(
            "选择要处理的条目",
            options=filtered_indices,
            default=filtered_indices[: min(10, len(filtered_indices))],
            format_func=lambda index: (
                f"{index + 1}. {label_knowledge_category(pending_items[index].get('category', ''))}"
                f" / {pending_items[index].get('name', '未命名')}"
                f" / {pending_quality_label(issue_map.get(str(pending_items[index].get('pending_id', '')), {}))}"
                f" / {label_scope(pending_items[index].get('scope', 'reference'))}"
            ),
            key="pending_knowledge_selected_indices",
        )

        preview_limit = st.slider(
            "预览条目数",
            min_value=5,
            max_value=80,
            value=min(30, max(5, len(filtered_indices))),
            step=5,
            key="pending_knowledge_preview_limit",
        )
        for index in filtered_indices[: int(preview_limit)]:
            item = pending_items[index]
            pending_id = str(item.get("pending_id", ""))
            issue_info = issue_map.get(pending_id, {})
            st.markdown(f"#### {index + 1}. {label_knowledge_category(item.get('category', ''))} / {item.get('name', '未命名')}")
            st.caption(
                f"{pending_quality_label(issue_info)} / 范围={label_scope(item.get('scope', 'reference'))} / "
                f"可信度={safe_confidence(item.get('confidence', 0.7)):.2f} / 证据={safe_confidence(item.get('evidence_strength', 0.5)):.2f} / "
                f"权威={label_authority(item.get('authority', 'curated'))} / 来源={item.get('source_title', '-') or '-'}"
            )
            if item.get("source_segment_title") or item.get("source_segment_index") is not None:
                st.caption(f"片段：{item.get('source_segment_index', '-')}. {item.get('source_segment_title', '-')}")
            if item.get("summary"):
                st.write(item.get("summary"))
            evidence_lines = summarize_item_evidence(item)
            if evidence_lines:
                st.caption("证据：" + "；".join(evidence_lines[:2]))
            evidence_contexts = item.get("evidence_contexts", []) if isinstance(item.get("evidence_contexts", []), list) else []
            if evidence_contexts:
                context = evidence_contexts[0]
                st.caption(
                    f"证据定位：段落 {context.get('paragraph_index', '-') or '-'} / 字符位置 {context.get('char_index', '-') if context.get('char_index') is not None else '-'}"
                )
                if context.get("context"):
                    st.caption("上下文：" + str(context.get("context"))[:260])
            if issue_info.get("descriptions"):
                st.warning(" / ".join(issue_info.get("descriptions", [])[:2]))
            if item.get("tags"):
                st.caption(f"标签：{', '.join(str(tag) for tag in item.get('tags', []))}")
        if len(filtered_indices) > int(preview_limit):
            st.caption(f"仅预览前 {int(preview_limit)} 条筛选结果，共 {len(filtered_indices)} 条。")

        render_pending_knowledge_item_editor(project_name, pending_items, filtered_indices)

        selected_ids = [
            str(pending_items[index].get("pending_id", ""))
            for index in selected_indices
            if 0 <= index < pending_count and pending_items[index].get("pending_id")
        ]
        with st.expander("自动审核预检与批量处理", expanded=False):
            st.caption("这里不会重新调用模型，只按当前自动审核策略和质检结果判断哪些条目可以自动保存，哪些仍保留给人工审核。")
            auto_scope = st.radio(
                "预检范围",
                options=["当前筛选结果", "已选择条目"],
                horizontal=True,
                key="pending_auto_review_scope",
            )
            auto_candidate_indices = filtered_indices if auto_scope == "当前筛选结果" else selected_indices
            auto_candidate_items = [
                pending_items[index]
                for index in auto_candidate_indices
                if 0 <= index < pending_count
            ]
            auto_preview = build_pending_auto_review_preview(
                auto_candidate_items,
                issue_map,
                policy,
            )
            preview_cols = st.columns(4)
            preview_cols[0].metric("候选条目", auto_preview.get("candidate_count", 0))
            preview_cols[1].metric("可自动确认", len(auto_preview.get("confirmed_ids", [])))
            preview_cols[2].metric("A 级", auto_preview.get("grade_counts", {}).get("A", 0))
            preview_cols[3].metric("保留待确认", len(auto_preview.get("blocked_ids", [])))
            reason_counts = auto_preview.get("blocked_reason_counts", {})
            if reason_counts:
                st.caption("主要保留原因：" + " / ".join(f"{reason}={count}" for reason, count in list(reason_counts.items())[:8]))
            preview_rows = auto_preview.get("rows", [])[:80]
            if preview_rows:
                st.dataframe(preview_rows, use_container_width=True, hide_index=True)
                if len(auto_preview.get("rows", [])) > len(preview_rows):
                    st.caption(f"仅展示前 {len(preview_rows)} 条预检结果。")
            auto_candidate_ids = [
                str(item.get("pending_id") or "")
                for item in auto_candidate_items
                if item.get("pending_id")
            ]
            if st.button("按当前策略自动确认低风险条目", key="pending_run_auto_review", use_container_width=True):
                if not auto_candidate_ids:
                    st.error("当前范围内没有可审核条目。")
                else:
                    auto_summary = auto_confirm_pending_items_without_risk(
                        project_name,
                        auto_candidate_ids,
                        source_type="pending_queue_manual_auto_review",
                        source_title=f"待确认队列 / {auto_scope}",
                        note="用户在待确认队列手动触发自动审核",
                    )
                    st.success(
                        f"自动审核完成：确认 {len(auto_summary.get('confirmed_ids', []))} 条，"
                        f"保留 {len(auto_summary.get('blocked_ids', []))} 条。"
                    )
                    if auto_summary.get("run_id"):
                        st.caption(f"处理记录 ID：{auto_summary.get('run_id')}")
                    st.rerun()
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
        if confirmed_button(
            col_b,
            "丢弃所选待确认条目",
            "确认丢弃所选条目",
            "discard_selected_pending_knowledge",
        ):
            if not selected_ids:
                st.error("请先选择条目。")
            else:
                removed_count = discard_pending_knowledge_items(project_name, selected_ids)
                st.success(f"已丢弃 {removed_count} 条待确认知识。")
                st.rerun()

        with st.expander("高级：待确认队列原始数据", expanded=False):
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


def render_auto_review_policy_panel(project_name: str):
    policy = load_auto_review_policy(project_name)
    with st.expander("自动审核策略", expanded=False):
        st.caption("控制低风险知识是否自动保存。策略越严格，保留待确认越多；策略越宽松，人工审核负担越低。")
        col_conf, col_evidence = st.columns(2)
        min_confidence = col_conf.slider(
            "自动确认最低置信度",
            min_value=0.0,
            max_value=1.0,
            value=float(policy.get("min_confidence", 0.45)),
            step=0.05,
            key="auto_review_policy_min_confidence",
        )
        min_evidence_strength = col_evidence.slider(
            "自动确认最低证据强度",
            min_value=0.0,
            max_value=1.0,
            value=float(policy.get("min_evidence_strength", 0.35)),
            step=0.05,
            key="auto_review_policy_min_evidence",
        )
        col_grade_a, col_grade_e = st.columns(2)
        grade_a_confidence = col_grade_a.slider(
            "A 级置信度阈值",
            min_value=0.0,
            max_value=1.0,
            value=float(policy.get("grade_a_confidence", 0.75)),
            step=0.05,
            key="auto_review_policy_grade_a_confidence",
        )
        grade_a_evidence_strength = col_grade_e.slider(
            "A 级证据阈值",
            min_value=0.0,
            max_value=1.0,
            value=float(policy.get("grade_a_evidence_strength", 0.65)),
            step=0.05,
            key="auto_review_policy_grade_a_evidence",
        )
        allow_grade_b_auto_confirm = st.checkbox(
            "允许 B 级条目自动确认",
            value=bool(policy.get("allow_grade_b_auto_confirm", True)),
            key="auto_review_policy_allow_grade_b",
            help="关闭后，只有 A 级条目会自动保存，B 级会保留用于抽查。",
        )
        require_evidence = st.checkbox(
            "自动确认必须有证据",
            value=bool(policy.get("require_evidence", True)),
            key="auto_review_policy_require_evidence",
        )
        manual_review_categories = st.multiselect(
            "必须人工审核的分类",
            options=list(KNOWLEDGE_CATEGORY_LABELS.keys()),
            default=[
                category
                for category in policy.get("manual_review_categories", ["constraints"])
                if category in KNOWLEDGE_CATEGORY_LABELS
            ],
            format_func=label_knowledge_category,
            key="auto_review_policy_manual_categories",
            help="这些分类永远不会自动确认，适合硬性约束、世界规则等高影响资料。",
        )
        if st.button("保存自动审核策略", key="save_auto_review_policy", use_container_width=True):
            saved = save_auto_review_policy(project_name, {
                "min_confidence": min_confidence,
                "min_evidence_strength": min_evidence_strength,
                "grade_a_confidence": grade_a_confidence,
                "grade_a_evidence_strength": grade_a_evidence_strength,
                "allow_grade_b_auto_confirm": allow_grade_b_auto_confirm,
                "require_evidence": require_evidence,
                "manual_review_categories": manual_review_categories,
            })
            st.success("自动审核策略已保存。")
            st.json(saved)


def render_auto_review_runs_panel(project_name: str):
    runs = list(reversed(load_auto_review_runs(project_name)))
    with st.expander(f"处理记录与人工复核箱（{len(runs)}）", expanded=bool(runs)):
        st.caption("这里保存自动确认和批量处理方案的记录。发现误处理时，可以按批次回退。")
        if not runs:
            st.caption("当前还没有批量处理记录。")
            return

        active_runs = [run for run in runs if str(run.get("status") or "active") != "rolled_back"]
        metric_cols = st.columns(4)
        metric_cols[0].metric("记录数", len(runs))
        metric_cols[1].metric("可回退", len(active_runs))
        metric_cols[2].metric("入库", sum(len(run.get("confirmed_ids", []) or []) for run in runs))
        metric_cols[3].metric("归档/复核", sum(len(run.get("archived_ids", []) or []) + len(run.get("manual_review_ids", []) or []) for run in runs))

        selected_run_id = st.selectbox(
            "选择处理记录",
            options=[str(run.get("run_id") or "") for run in runs],
            format_func=lambda run_id: next(
                (
                    f"{run.get('created_at', '-')[:19]} / {run.get('source_title') or run.get('source_type') or '自动审核'}"
                    f" / 入库 {len(run.get('confirmed_ids', []) or [])}"
                    f" / 归档 {len(run.get('archived_ids', []) or [])}"
                    f" / 复核 {len(run.get('manual_review_ids', []) or [])}"
                    f" / {'已回退' if run.get('status') == 'rolled_back' else '可回退'}"
                    for run in runs if str(run.get("run_id") or "") == run_id
                ),
                run_id,
            ),
            key="auto_review_run_select",
        )
        selected_run = next((run for run in runs if str(run.get("run_id") or "") == selected_run_id), {})
        if not selected_run:
            return

        st.caption(
            f"处理记录 ID={selected_run.get('run_id', '')} / 来源={selected_run.get('source_type', '-') or '-'} / "
            f"批次={selected_run.get('batch_id', '-') or '-'} / 状态={selected_run.get('status', 'active')}"
        )
        if selected_run.get("note"):
            st.info(str(selected_run.get("note")))

        batch_summary = selected_run.get("batch_summary", {}) if isinstance(selected_run.get("batch_summary", {}), dict) else {}
        if batch_summary:
            batch_cols = st.columns(4)
            batch_cols[0].metric("本批次", batch_summary.get("total", 0))
            batch_cols[1].metric("入库", batch_summary.get("confirmed", len(selected_run.get("confirmed_ids", []) or [])))
            batch_cols[2].metric("归档", batch_summary.get("archived", len(selected_run.get("archived_ids", []) or [])))
            batch_cols[3].metric("复核箱", batch_summary.get("manual_review", len(selected_run.get("manual_review_ids", []) or [])))

        reason_counts: dict[str, int] = {}
        for reason in (selected_run.get("blocked_reasons", {}) or {}).values():
            reason_counts[str(reason or "未说明")] = reason_counts.get(str(reason or "未说明"), 0) + 1
        if reason_counts:
            st.caption("保留原因：" + " / ".join(f"{reason}={count}" for reason, count in reason_counts.items()))

        rows = []
        for decision in selected_run.get("decisions", [])[:80] if isinstance(selected_run.get("decisions", []), list) else []:
            if not isinstance(decision, dict):
                continue
            action = str(decision.get("action") or "")
            decision_value = str(decision.get("decision") or "")
            decision_label = {
                "confirm": "自动入库",
                "archive": "归档丢弃",
                "manual_review": "人工复核箱",
            }.get(action) or ("自动确认" if decision_value == "confirm" else "保留待确认")
            rows.append({
                "决策": decision_label,
                "等级": decision.get("grade", ""),
                "分类": label_knowledge_category(decision.get("category", "")),
                "名称": decision.get("name", ""),
                "原因": decision.get("reason", ""),
            })
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
            if len(selected_run.get("decisions", []) or []) > len(rows):
                st.caption(f"仅展示前 {len(rows)} 条决策。")

        manual_snapshots = selected_run.get("manual_review_snapshots", []) if isinstance(selected_run.get("manual_review_snapshots", []), list) else []
        if manual_snapshots:
            with st.expander(f"人工复核箱预览（{len(manual_snapshots)}）", expanded=True):
                restored_ids = {
                    str(item or "")
                    for item in selected_run.get("restored_pending_ids", [])
                    if str(item or "").strip()
                }
                st.dataframe(
                    [
                        {
                            "分类": label_knowledge_category(item.get("category", "")),
                            "名称": item.get("name", ""),
                            "摘要": str(item.get("summary", ""))[:120],
                            "来源": item.get("source_title", "") or item.get("source_segment_title", ""),
                            "状态": "已恢复" if str(item.get("pending_id") or "") in restored_ids else "待恢复",
                        }
                        for item in manual_snapshots[:120]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
                if len(manual_snapshots) > 120:
                    st.caption("仅展示前 120 条，完整快照保存在原始数据里。")
                restorable_snapshots = [
                    item for item in manual_snapshots
                    if isinstance(item, dict)
                    and str(item.get("pending_id") or "").strip()
                    and str(item.get("pending_id") or "") not in restored_ids
                ]
                selected_restore_ids = st.multiselect(
                    "选择要恢复到待确认队列的复核条目",
                    options=[str(item.get("pending_id") or "") for item in restorable_snapshots],
                    format_func=lambda pending_id: next(
                        (
                            f"{label_knowledge_category(item.get('category', ''))} / {item.get('name', pending_id)}"
                            for item in restorable_snapshots
                            if str(item.get("pending_id") or "") == pending_id
                        ),
                        pending_id,
                    ),
                    key=f"restore_manual_review_ids_{selected_run_id}",
                )
                restore_cols = st.columns(2)
                if restore_cols[0].button(
                    "恢复所选到待确认",
                    key=f"restore_manual_review_selected_{selected_run_id}",
                    disabled=not selected_restore_ids,
                    use_container_width=True,
                ):
                    result = restore_auto_review_snapshots_to_pending(project_name, selected_run_id, selected_restore_ids)
                    if result.get("success"):
                        st.success(result.get("message", "已恢复。"))
                        st.rerun()
                    else:
                        st.error(result.get("message", "恢复失败。"))
                if restore_cols[1].button(
                    f"恢复全部未恢复（{len(restorable_snapshots)}）",
                    key=f"restore_manual_review_all_{selected_run_id}",
                    disabled=not restorable_snapshots,
                    use_container_width=True,
                ):
                    result = restore_auto_review_snapshots_to_pending(
                        project_name,
                        selected_run_id,
                        [str(item.get("pending_id") or "") for item in restorable_snapshots],
                    )
                    if result.get("success"):
                        st.success(result.get("message", "已恢复。"))
                        st.rerun()
                    else:
                        st.error(result.get("message", "恢复失败。"))

        with st.expander("高级：处理记录原始数据", expanded=False):
            st.json(selected_run)

        if selected_run.get("status") == "rolled_back":
            result = selected_run.get("rollback_result", {})
            st.warning(f"该记录已回退：删除 {result.get('removed_count', 0)} 条正式知识，恢复 {result.get('restored_count', 0)} 条待确认知识。")
            return

        confirm_text = st.text_input(
            "输入处理记录 ID 以确认回退",
            key=f"rollback_auto_review_confirm_{selected_run_id}",
            placeholder=selected_run_id,
        )
        if st.button("回退这次处理", key=f"rollback_auto_review_{selected_run_id}", use_container_width=True):
            if confirm_text.strip() != selected_run_id:
                st.error("请先输入完整处理记录 ID，避免误回退。")
            else:
                result = rollback_auto_review_run(project_name, selected_run_id)
                if result.get("success"):
                    st.success(result.get("message", "已回退。"))
                    st.rerun()
                else:
                    st.error(result.get("message", "回退失败。"))


def render_pending_knowledge_item_editor(project_name: str, pending_items: list[dict], filtered_indices: list[int]):
    with st.expander("表单编辑：单条待确认知识", expanded=False):
        if not filtered_indices:
            st.caption("当前筛选结果为空，没有可编辑条目。")
            return

        selected_index = st.selectbox(
            "选择要编辑的条目",
            options=filtered_indices,
            format_func=lambda index: (
                f"{index + 1}. {label_knowledge_category(pending_items[index].get('category', ''))}"
                f" / {pending_items[index].get('name', '未命名')}"
                f" / {pending_items[index].get('source_title', '-') or '-'}"
            ),
            key="pending_item_editor_select",
        )
        item = dict(pending_items[selected_index])
        pending_id = str(item.get("pending_id") or "")
        if not pending_id:
            st.warning("该条目缺少内部 ID，无法通过表单保存。")
            return

        details_value = json.dumps(item.get("details", {}) if isinstance(item.get("details", {}), dict) else {}, ensure_ascii=False, indent=2)
        evidence_value = json.dumps(item.get("evidence", []) if isinstance(item.get("evidence", []), list) else [], ensure_ascii=False, indent=2)
        evidence_contexts_value = json.dumps(item.get("evidence_contexts", []) if isinstance(item.get("evidence_contexts", []), list) else [], ensure_ascii=False, indent=2)
        tags_value = ", ".join(str(tag) for tag in item.get("tags", []) if str(tag).strip()) if isinstance(item.get("tags"), list) else ""

        with st.form(key=f"pending_item_editor_form_{pending_id}"):
            col_a, col_b = st.columns(2)
            category = col_a.selectbox(
                "分类",
                options=list(KNOWLEDGE_CATEGORY_LABELS.keys()),
                index=list(KNOWLEDGE_CATEGORY_LABELS.keys()).index(item.get("category")) if item.get("category") in KNOWLEDGE_CATEGORY_LABELS else 0,
                format_func=label_knowledge_category,
            )
            name = col_b.text_input("名称", value=str(item.get("name") or ""))
            summary = st.text_area("摘要", value=str(item.get("summary") or ""), height=110)

            col_scope, col_authority, col_canon = st.columns(3)
            scope_options = ["project", "canon", "reference"]
            scope = col_scope.selectbox(
                "范围",
                options=scope_options,
                index=scope_options.index(item.get("scope")) if item.get("scope") in scope_options else 2,
                format_func=label_scope,
            )
            authority_options = ["project", "official", "curated", "community", "unknown"]
            authority = col_authority.selectbox(
                "可信度/权威",
                options=authority_options,
                index=authority_options.index(item.get("authority")) if item.get("authority") in authority_options else 2,
                format_func=label_authority,
            )
            canon_options = ["canon", "inferred", "ambiguous", "fanon", "user_override", "unknown"]
            canon_status = col_canon.selectbox(
                "原作状态",
                options=canon_options,
                index=canon_options.index(item.get("canon_status")) if item.get("canon_status") in canon_options else 5,
            )

            col_version, col_worldline = st.columns(2)
            version_scope = col_version.selectbox(
                "版本 / 世界线范围",
                options=list(VERSION_SCOPE_LABELS.keys()),
                index=list(VERSION_SCOPE_LABELS.keys()).index(item.get("version_scope")) if item.get("version_scope") in VERSION_SCOPE_LABELS else 4,
                format_func=lambda value: VERSION_SCOPE_LABELS.get(value, value),
            )
            worldline_value = str(item.get("worldline_id") or DEFAULT_WORLDLINE_ID)
            worldline_label_value = str(item.get("worldline_label") or DEFAULT_WORLDLINE_LABEL)
            worldline_id = col_worldline.text_input("世界线 ID", value=worldline_value)
            worldline_label = st.text_input("世界线名称", value=worldline_label_value)

            col_conf, col_imp, col_ev = st.columns(3)
            confidence = col_conf.slider("置信度", 0.0, 1.0, safe_confidence(item.get("confidence", 0.7)), 0.05)
            importance = col_imp.slider("重要性", 0.0, 1.0, safe_confidence(item.get("importance", 0.5)), 0.05)
            evidence_strength = col_ev.slider("证据强度", 0.0, 1.0, safe_confidence(item.get("evidence_strength", 0.5)), 0.05)

            col_source, col_origin = st.columns(2)
            source_title = col_source.text_input("来源标题", value=str(item.get("source_title") or ""))
            source_origin = col_origin.text_input("来源说明/链接", value=str(item.get("source_origin") or ""))
            tags = st.text_input("标签（逗号分隔）", value=tags_value)

            col_seg_a, col_seg_b = st.columns(2)
            source_segment_title = col_seg_a.text_input("来源片段标题", value=str(item.get("source_segment_title") or ""))
            source_segment_id = col_seg_b.text_input("来源片段 ID（可选）", value=str(item.get("source_segment_id") or ""))

            details_json = st.text_area("详情 JSON（高级）", value=details_value, height=180)
            evidence_json = st.text_area("证据 JSON（高级）", value=evidence_value, height=180)
            evidence_contexts_json = st.text_area("证据上下文 JSON（高级）", value=evidence_contexts_value, height=120)

            col_save, col_confirm = st.columns(2)
            save_clicked = col_save.form_submit_button("保存修改到待确认队列", use_container_width=True)
            confirm_clicked = col_confirm.form_submit_button("保存修改并确认入库", use_container_width=True)

        if not (save_clicked or confirm_clicked):
            return

        if not name.strip():
            st.error("名称不能为空。")
            return
        try:
            parsed_details = json.loads(details_json or "{}")
            if not isinstance(parsed_details, dict):
                st.error("详情必须是 JSON 对象。")
                return
            parsed_evidence = json.loads(evidence_json or "[]")
            if not isinstance(parsed_evidence, list):
                st.error("证据必须是 JSON 列表。")
                return
            parsed_evidence_contexts = json.loads(evidence_contexts_json or "[]")
            if not isinstance(parsed_evidence_contexts, list):
                st.error("证据上下文必须是 JSON 列表。")
                return
        except json.JSONDecodeError as exc:
            st.error(f"JSON 格式错误：{exc}")
            return

        updated_item = {
            **item,
            "category": category,
            "name": name.strip(),
            "summary": summary.strip(),
            "details": parsed_details,
            "evidence": parsed_evidence,
            "evidence_contexts": parsed_evidence_contexts,
            "confidence": confidence,
            "importance": importance,
            "evidence_strength": evidence_strength,
            "canon_status": canon_status,
            "version_scope": version_scope,
            "worldline_id": worldline_id.strip() or DEFAULT_WORLDLINE_ID,
            "worldline_label": worldline_label.strip() or DEFAULT_WORLDLINE_LABEL,
            "scope": scope,
            "authority": authority,
            "source_title": source_title.strip(),
            "source_origin": source_origin.strip(),
            "source_segment_title": source_segment_title.strip(),
            "source_segment_id": source_segment_id.strip(),
            "tags": parse_comma_tags(tags),
            "edited_in_ui": True,
        }
        if not update_pending_knowledge_item(project_name, pending_id, updated_item):
            st.error("保存失败：待确认条目不存在，可能已被其他操作处理。")
            return
        if confirm_clicked:
            saved_count = confirm_pending_knowledge_items(project_name, [pending_id])
            if saved_count:
                rebuild_retrieval_assets(project_name, build_vectors=True)
            st.success(f"已保存修改并确认 {saved_count} 条结构化知识。")
        else:
            st.success("已保存修改到待确认队列。")
        st.rerun()


def render_confirmed_knowledge_item_editor(
    project_name: str,
    category: str,
    items: list[dict],
    candidate_indices: list[int],
):
    with st.expander("表单编辑：正式知识库单条知识", expanded=False):
        if not candidate_indices:
            st.caption("当前分类没有可编辑条目。")
            return

        selected_index = st.selectbox(
            "选择要编辑的正式知识",
            options=candidate_indices,
            format_func=lambda index: (
                f"{index + 1}. {label_knowledge_category(items[index].get('category', category))}"
                f" / {items[index].get('name', '未命名')}"
                f" / {items[index].get('source_title', '-') or '-'}"
            ),
            key=f"confirmed_item_editor_select_{category}",
        )
        item = dict(items[selected_index])
        details_value = json.dumps(item.get("details", {}) if isinstance(item.get("details", {}), dict) else {}, ensure_ascii=False, indent=2)
        evidence_value = json.dumps(item.get("evidence", []) if isinstance(item.get("evidence", []), list) else [], ensure_ascii=False, indent=2)
        evidence_contexts_value = json.dumps(item.get("evidence_contexts", []) if isinstance(item.get("evidence_contexts", []), list) else [], ensure_ascii=False, indent=2)
        tags_value = ", ".join(str(tag) for tag in item.get("tags", []) if str(tag).strip()) if isinstance(item.get("tags"), list) else ""

        with st.form(key=f"confirmed_item_editor_form_{category}_{selected_index}"):
            col_a, col_b = st.columns(2)
            target_category = col_a.selectbox(
                "分类",
                options=list(KNOWLEDGE_CATEGORY_LABELS.keys()),
                index=list(KNOWLEDGE_CATEGORY_LABELS.keys()).index(item.get("category")) if item.get("category") in KNOWLEDGE_CATEGORY_LABELS else list(KNOWLEDGE_CATEGORY_LABELS.keys()).index(category),
                format_func=label_knowledge_category,
            )
            name = col_b.text_input("名称", value=str(item.get("name") or ""))
            summary = st.text_area("摘要", value=str(item.get("summary") or ""), height=110)

            col_scope, col_authority, col_canon = st.columns(3)
            scope_options = ["project", "canon", "reference"]
            scope = col_scope.selectbox(
                "范围",
                options=scope_options,
                index=scope_options.index(item.get("scope")) if item.get("scope") in scope_options else 2,
                format_func=label_scope,
            )
            authority_options = ["project", "official", "curated", "community", "unknown"]
            authority = col_authority.selectbox(
                "可信度/权威",
                options=authority_options,
                index=authority_options.index(item.get("authority")) if item.get("authority") in authority_options else 2,
                format_func=label_authority,
            )
            canon_options = ["canon", "inferred", "ambiguous", "fanon", "user_override", "unknown"]
            canon_status = col_canon.selectbox(
                "原作状态",
                options=canon_options,
                index=canon_options.index(item.get("canon_status")) if item.get("canon_status") in canon_options else 5,
            )

            col_version, col_worldline = st.columns(2)
            version_scope = col_version.selectbox(
                "版本 / 世界线范围",
                options=list(VERSION_SCOPE_LABELS.keys()),
                index=list(VERSION_SCOPE_LABELS.keys()).index(item.get("version_scope")) if item.get("version_scope") in VERSION_SCOPE_LABELS else 4,
                format_func=lambda value: VERSION_SCOPE_LABELS.get(value, value),
            )
            worldline_id = col_worldline.text_input("世界线 ID", value=str(item.get("worldline_id") or DEFAULT_WORLDLINE_ID))
            worldline_label = st.text_input("世界线名称", value=str(item.get("worldline_label") or DEFAULT_WORLDLINE_LABEL))

            col_conf, col_imp, col_ev = st.columns(3)
            confidence = col_conf.slider("置信度", 0.0, 1.0, safe_confidence(item.get("confidence", 0.7)), 0.05)
            importance = col_imp.slider("重要性", 0.0, 1.0, safe_confidence(item.get("importance", 0.5)), 0.05)
            evidence_strength = col_ev.slider("证据强度", 0.0, 1.0, safe_confidence(item.get("evidence_strength", 0.5)), 0.05)

            col_source, col_origin = st.columns(2)
            source_title = col_source.text_input("来源标题", value=str(item.get("source_title") or ""))
            source_origin = col_origin.text_input("来源说明/链接", value=str(item.get("source_origin") or ""))
            tags = st.text_input("标签（逗号分隔）", value=tags_value)

            col_seg_a, col_seg_b = st.columns(2)
            source_segment_title = col_seg_a.text_input("来源片段标题", value=str(item.get("source_segment_title") or ""))
            source_segment_id = col_seg_b.text_input("来源片段 ID（可选）", value=str(item.get("source_segment_id") or ""))

            details_json = st.text_area("详情 JSON（高级）", value=details_value, height=180)
            evidence_json = st.text_area("证据 JSON（高级）", value=evidence_value, height=180)
            evidence_contexts_json = st.text_area("证据上下文 JSON（高级）", value=evidence_contexts_value, height=120)

            col_save, col_delete = st.columns(2)
            save_clicked = col_save.form_submit_button("保存正式知识并重建索引", use_container_width=True)
            delete_confirmed = col_delete.checkbox(
                "确认删除该条正式知识",
                key=scoped_widget_key("delete_confirmed_knowledge_confirm", project_name, category, selected_index),
            )
            delete_clicked = col_delete.form_submit_button(
                "删除该条正式知识",
                use_container_width=True,
                disabled=not delete_confirmed,
            )

        can_return_to_pending = bool(item.get("auto_review_run_id") or item.get("source_pending_id"))
        return_clicked = False
        return_reason = ""
        if can_return_to_pending:
            st.caption(
                f"自动审核记录：{item.get('auto_review_run_id', '-') or '-'} / "
                f"原待确认条目：{item.get('source_pending_id', '-') or '-'}"
            )
            with st.expander("退回待确认", expanded=False):
                st.caption("只退回这一条正式知识，不影响同一次自动审核的其他条目。退回后可在待确认队列重新编辑、确认或丢弃。")
                return_reason = st.text_input(
                    "退回原因（可选）",
                    key=f"return_confirmed_reason_{category}_{selected_index}",
                    placeholder="例如：自动审核误判、证据需要复核、世界线不对",
                )
                return_clicked = st.button(
                    "将该条正式知识退回待确认",
                    key=f"return_confirmed_to_pending_{category}_{selected_index}",
                    use_container_width=True,
                )

        if return_clicked:
            knowledge_id = str(item.get("id") or "")
            result = return_confirmed_knowledge_item_to_pending(
                project_name,
                category,
                knowledge_id,
                reason=return_reason,
            )
            if result.get("success"):
                rebuild_retrieval_assets(project_name, build_vectors=True)
                st.success(result.get("message", "已退回待确认。"))
                st.rerun()
            st.error(result.get("message", "退回失败。"))
            return

        if not (save_clicked or delete_clicked):
            return

        if delete_clicked:
            if save_confirmed_knowledge_item(project_name, category, selected_index, item, delete_only=True):
                rebuild_retrieval_assets(project_name, build_vectors=True)
                st.success("已删除该条正式知识，并重建检索索引。")
                st.rerun()
            st.error("删除失败：条目不存在或分类无效。")
            return

        if not name.strip():
            st.error("名称不能为空。")
            return
        try:
            parsed_details = json.loads(details_json or "{}")
            if not isinstance(parsed_details, dict):
                st.error("详情必须是 JSON 对象。")
                return
            parsed_evidence = json.loads(evidence_json or "[]")
            if not isinstance(parsed_evidence, list):
                st.error("证据必须是 JSON 列表。")
                return
            parsed_evidence_contexts = json.loads(evidence_contexts_json or "[]")
            if not isinstance(parsed_evidence_contexts, list):
                st.error("证据上下文必须是 JSON 列表。")
                return
        except json.JSONDecodeError as exc:
            st.error(f"JSON 格式错误：{exc}")
            return

        updated_item = {
            **item,
            "category": target_category,
            "name": name.strip(),
            "summary": summary.strip(),
            "details": parsed_details,
            "evidence": parsed_evidence,
            "evidence_contexts": parsed_evidence_contexts,
            "confidence": confidence,
            "importance": importance,
            "evidence_strength": evidence_strength,
            "canon_status": canon_status,
            "version_scope": version_scope,
            "worldline_id": worldline_id.strip() or DEFAULT_WORLDLINE_ID,
            "worldline_label": worldline_label.strip() or DEFAULT_WORLDLINE_LABEL,
            "scope": scope,
            "authority": authority,
            "source_title": source_title.strip(),
            "source_origin": source_origin.strip(),
            "source_segment_title": source_segment_title.strip(),
            "source_segment_id": source_segment_id.strip(),
            "tags": parse_comma_tags(tags),
            "edited_in_ui": True,
            "status": item.get("status") or "confirmed",
        }
        if save_confirmed_knowledge_item(project_name, category, selected_index, updated_item):
            rebuild_retrieval_assets(project_name, build_vectors=True)
            move_note = "，并移动分类" if target_category != category else ""
            st.success(f"已保存正式知识{move_note}，并重建检索索引。")
            st.rerun()
        st.error("保存失败：条目不存在或分类无效。")


def render_pending_triage_dashboard(project_name: str, pending_items: list[dict], issue_map: dict[str, dict], policy: dict):
    auto_preview = build_pending_auto_review_preview(pending_items, issue_map, policy)
    summary = build_pending_triage_summary(pending_items, issue_map, auto_preview)
    with st.expander("待确认处理台", expanded=len(pending_items) >= 50):
        st.caption("大批量待确认不要逐条读。推荐顺序：自动确认低风险 / 处理冲突和重复 / 再看低证据条目。")
        metric_cols = st.columns(5)
        metric_cols[0].metric("待处理", summary["total"])
        metric_cols[1].metric("可自动确认", summary["auto_confirm_count"])
        metric_cols[2].metric("需人工看", summary["manual_count"])
        metric_cols[3].metric("事实/同名冲突", summary["risk_counts"]["fact_conflict"] + summary["risk_counts"]["same_name_conflict"])
        metric_cols[4].metric("低证据/无证据", summary["risk_counts"]["low_evidence"] + summary["risk_counts"]["no_evidence"])

        if summary["auto_confirm_count"]:
            st.success(
                f"建议先自动确认 {summary['auto_confirm_count']} 条低风险内容。"
                "自动审核会留下记录，后续发现误入库可以在自动审核记录里回退。"
            )
        else:
            st.info("当前策略下没有可自动确认的低风险条目。可以调宽自动审核策略，或先处理冲突/低证据条目。")

        action_cols = st.columns(4)
        if action_cols[0].button(
            f"自动确认低风险（{summary['auto_confirm_count']}）",
            key="pending_triage_auto_confirm_all",
            use_container_width=True,
            disabled=summary["auto_confirm_count"] == 0,
            type="primary" if summary["auto_confirm_count"] else "secondary",
        ):
            candidate_ids = [
                str(item.get("pending_id") or "")
                for item in pending_items
                if item.get("pending_id")
            ]
            auto_summary = auto_confirm_pending_items_without_risk(
                project_name,
                candidate_ids,
                source_type="pending_queue_triage_auto_review",
                source_title="待确认处理台 / 全量低风险",
                note="用户在待确认处理台触发全量低风险自动确认",
            )
            st.success(
                f"自动审核完成：确认 {len(auto_summary.get('confirmed_ids', []))} 条，"
                f"保留 {len(auto_summary.get('blocked_ids', []))} 条。"
            )
            st.rerun()

        if action_cols[1].button("只看冲突/已存在", key="pending_triage_show_conflicts", use_container_width=True):
            st.session_state["pending_filter_risks"] = ["fact_conflict", "same_name_conflict", "confirmed_overlap"]
            st.session_state["pending_sort_mode"] = "risk_first"
            st.rerun()
        if action_cols[2].button("只看低证据", key="pending_triage_show_low_evidence", use_container_width=True):
            st.session_state["pending_filter_risks"] = ["low_evidence", "low_confidence", "no_evidence"]
            st.session_state["pending_sort_mode"] = "low_evidence"
            st.rerun()
        if action_cols[3].button("只看重复/别名", key="pending_triage_show_duplicates", use_container_width=True):
            st.session_state["pending_filter_risks"] = ["duplicate", "alias_candidate"]
            st.session_state["pending_sort_mode"] = "risk_first"
            st.rerun()

        if st.button("清空待确认筛选", key="pending_triage_clear_filters", use_container_width=True):
            for key in [
                "pending_filter_categories",
                "pending_filter_risks",
                "pending_filter_sources",
                "pending_filter_worldlines",
            ]:
                st.session_state[key] = []
            st.session_state["pending_filter_keyword"] = ""
            st.session_state["pending_sort_mode"] = "risk_first"
            st.rerun()

        st.markdown("#### 批量处理方案（可回退）")
        archive_low_quality = st.checkbox(
            "低证据、低置信、无证据条目直接归档丢弃",
            value=True,
            key="pending_clear_archive_low_quality",
            help="归档不会写入正式知识，但会保存在本次处理批次记录里；整批回退时会恢复到待确认队列。",
        )
        clear_plan = build_pending_clear_plan(
            pending_items,
            issue_map,
            policy,
            archive_low_quality=archive_low_quality,
        )
        plan_counts = clear_plan.get("counts", {})
        plan_cols = st.columns(4)
        plan_cols[0].metric("本次覆盖", clear_plan.get("total", 0))
        plan_cols[1].metric("自动入库", plan_counts.get("confirm", 0))
        plan_cols[2].metric("归档丢弃", plan_counts.get("archive", 0))
        plan_cols[3].metric("人工复核箱", plan_counts.get("manual_review", 0))
        st.caption("执行后，本次覆盖的条目会离开普通待确认队列；入库、归档和复核箱都会写进一条可回退的处理记录。")
        preview_rows = [
            {
                "动作": {
                    "confirm": "自动入库",
                    "archive": "归档丢弃",
                    "manual_review": "人工复核箱",
                }.get(decision.get("action", ""), decision.get("action", "")),
                "分类": decision.get("category_label", ""),
                "名称": decision.get("name", ""),
                "原因": decision.get("reason", ""),
                "置信度": f"{decision.get('confidence', 0):.2f}",
                "证据": f"{decision.get('evidence_strength', 0):.2f}",
            }
            for decision in clear_plan.get("decisions", [])[:120]
        ]
        with st.expander("查看处理方案样例", expanded=False):
            if preview_rows:
                st.dataframe(preview_rows, use_container_width=True, hide_index=True)
                if len(clear_plan.get("decisions", [])) > len(preview_rows):
                    st.caption(f"仅展示前 {len(preview_rows)} 条，完整决策会写入批次记录。")
            else:
                st.caption("当前没有可执行的待确认条目。")

        if confirmed_button(
            st,
            "执行批量处理方案",
            "确认执行本次批量处理方案",
            "pending_clear_execute_plan",
            type="primary",
        ):
            result = execute_pending_clear_plan(
                project_name,
                clear_plan,
                note="用户在待确认处理台执行批量处理方案",
            )
            if result.get("success"):
                st.success(f"{result.get('message')} 批次记录：{result.get('run_id')}")
                st.rerun()
            else:
                st.error(result.get("message", "执行失败。"))

        with st.expander("分布明细", expanded=False):
            dist_cols = st.columns(3)
            top_categories = sorted(summary["category_counts"].items(), key=lambda item: item[1], reverse=True)[:12]
            top_sources = sorted(summary["source_counts"].items(), key=lambda item: item[1], reverse=True)[:12]
            top_worldlines = sorted(summary["worldline_counts"].items(), key=lambda item: item[1], reverse=True)[:12]
            dist_cols[0].dataframe(
                [{"分类": label_knowledge_category(category), "数量": count} for category, count in top_categories],
                use_container_width=True,
                hide_index=True,
            )
            dist_cols[1].dataframe(
                [{"来源": source, "数量": count} for source, count in top_sources],
                use_container_width=True,
                hide_index=True,
            )
            dist_cols[2].dataframe(
                [{"世界线": worldline, "数量": count} for worldline, count in top_worldlines],
                use_container_width=True,
                hide_index=True,
            )


def filter_pending_knowledge_indices(pending_items: list[dict], issue_map: dict[str, dict]) -> list[int]:
    categories = sorted({
        str(item.get("category") or "")
        for item in pending_items
        if str(item.get("category") or "").strip()
    })
    source_titles = sorted({
        str(item.get("source_title") or "")
        for item in pending_items
        if str(item.get("source_title") or "").strip()
    })
    worldlines = sorted({
        str(item.get("worldline_label") or item.get("worldline_id") or "")
        for item in pending_items
        if str(item.get("worldline_label") or item.get("worldline_id") or "").strip()
    })
    col_a, col_b, col_c = st.columns(3)
    selected_categories = col_a.multiselect(
        "筛选分类",
        options=categories,
        default=[],
        format_func=label_knowledge_category,
        key="pending_filter_categories",
    )
    risk_filter = col_b.multiselect(
        "筛选质检线索",
        options=["fact_conflict", "same_name_conflict", "confirmed_overlap", "duplicate", "alias_candidate", "low_evidence", "low_confidence", "no_evidence"],
        default=[],
        format_func=lambda value: {
            "fact_conflict": "事实冲突",
            "same_name_conflict": "同名冲突",
            "confirmed_overlap": "正式库已有",
            "duplicate": "同名重复",
            "alias_candidate": "疑似别名",
            "low_evidence": "低证据强度",
            "low_confidence": "低置信度",
            "no_evidence": "无证据摘录",
        }.get(value, value),
        key="pending_filter_risks",
    )
    sort_mode = col_c.selectbox(
        "排序",
        options=["risk_first", "low_evidence", "low_confidence", "high_importance", "newest", "category"],
        format_func=lambda value: {
            "risk_first": "高风险优先",
            "low_evidence": "低证据优先",
            "low_confidence": "低置信优先",
            "high_importance": "高重要性优先",
            "newest": "新加入优先",
            "category": "按分类/名称",
        }.get(value, value),
        key="pending_sort_mode",
    )

    keyword = st.text_input("搜索待确认知识", key="pending_filter_keyword", placeholder="名称、摘要、来源、标签、片段标题")
    selected_source_titles = st.multiselect(
        "筛选来源",
        options=source_titles,
        default=[],
        key="pending_filter_sources",
    )
    selected_worldlines = st.multiselect(
        "筛选世界线",
        options=worldlines,
        default=[],
        key="pending_filter_worldlines",
    )

    return filter_pending_knowledge_indices_by_values(
        pending_items,
        issue_map,
        selected_categories=selected_categories,
        selected_source_titles=selected_source_titles,
        selected_worldlines=selected_worldlines,
        risk_filter=risk_filter,
        keyword=keyword,
        sort_mode=sort_mode,
    )


def render_pending_knowledge_quality_panel(project_name: str, pending_items: list[dict]):
    issues = build_pending_knowledge_quality_issues(project_name, pending_items)
    with st.expander(f"提取质检：重复 / 冲突 / 别名线索（{len(issues)}）", expanded=bool(issues)):
        st.caption("用于在确认入库前发现同名重复、字段冲突、疑似别名和已存在正式知识。这里只给出线索，正式入库仍由你确认。")
        if not issues:
            st.caption("当前没有发现明显的重复、冲突或别名线索。")
            return
        issue_rows = []
        type_labels = {
            "duplicate": "同名重复",
            "same_name_conflict": "同名冲突",
            "fact_conflict": "事实冲突",
            "alias_candidate": "疑似别名",
            "confirmed_overlap": "正式库已有",
        }
        for index, issue in enumerate(issues, start=1):
            issue_rows.append({
                "序号": index,
                "级别": issue.get("severity", ""),
                "类型": type_labels.get(issue.get("type", ""), issue.get("type", "")),
                "对象": issue.get("title", ""),
                "说明": issue.get("description", ""),
                "关联待确认": len([item for item in issue.get("pending_ids", []) if item]),
            })
        st.dataframe(issue_rows, use_container_width=True, hide_index=True)

        selected_issue_index = st.selectbox(
            "查看质检线索",
            options=list(range(len(issues))),
            format_func=lambda index: f"{index + 1}. {type_labels.get(issues[index].get('type', ''), issues[index].get('type', ''))} / {issues[index].get('title', '')}",
            key="pending_quality_issue_select",
        )
        issue = issues[selected_issue_index]
        if issue.get("recommendation"):
            st.info(str(issue.get("recommendation")))
        selected_items = [
            pending_items[index]
            for index in issue.get("indices", [])
            if 0 <= index < len(pending_items)
        ]
        for item in selected_items:
            st.markdown(f"**{label_knowledge_category(item.get('category', ''))} / {item.get('name', '未命名')}**")
            st.caption(
                f"内部 ID={item.get('pending_id', '-')} / 可信度={safe_confidence(item.get('confidence', 0.7)):.2f} / "
                f"证据强度={safe_confidence(item.get('evidence_strength', 0.5)):.2f} / 来源={item.get('source_title', '-') or '-'}"
            )
            if item.get("summary"):
                st.write(str(item.get("summary"))[:500])
            details = item.get("details", {})
            if isinstance(details, dict) and details:
                st.caption("详情：" + "；".join(f"{key}={value}" for key, value in list(details.items())[:8]))

        can_merge = issue.get("type") in {"duplicate", "same_name_conflict", "fact_conflict"} and len(selected_items) >= 2
        can_save_alias = issue.get("type") == "alias_candidate" and len(selected_items) >= 2
        if can_save_alias:
            alias_names = [str(item.get("name") or "").strip() for item in selected_items if str(item.get("name") or "").strip()]
            default_canonical = alias_names[0] if alias_names else ""
            alias_col_a, alias_col_b = st.columns(2)
            canonical_name = alias_col_a.text_input(
                "别名组主名称",
                value=default_canonical,
                key="pending_quality_alias_canonical",
            )
            alias_notes = alias_col_b.text_input(
                "别名备注",
                value="由待确认质检的疑似别名线索保存。",
                key="pending_quality_alias_notes",
            )
            if st.button("保存为实体别名组", key="pending_quality_save_alias_group", use_container_width=True):
                try:
                    alias_group = upsert_entity_alias_group(
                        project_name,
                        category=str(selected_items[0].get("category") or "characters"),
                        canonical_name=canonical_name,
                        aliases=alias_names,
                        notes=alias_notes,
                        source_pending_ids=[
                            str(item.get("pending_id") or "") for item in selected_items if item.get("pending_id")
                        ],
                    )
                    st.success(f"已保存别名组：{alias_group.get('canonical_name')} / {', '.join(alias_group.get('aliases', []))}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"保存别名组失败：{exc}")

        if can_merge and st.button("将这组同名条目合并为新的待确认条目", key="pending_quality_merge_issue", use_container_width=True):
            category = str(selected_items[0].get("category") or "")
            merged_item = build_merged_knowledge_item(category, selected_items)
            merged_item["status"] = "pending"
            merged_item["tags"] = merge_list_values([merged_item.get("tags", []), ["质检合并"]])
            merged_item["merged_from_pending_ids"] = [
                str(item.get("pending_id") or "") for item in selected_items if item.get("pending_id")
            ]
            target_ids = [str(item.get("pending_id") or "") for item in selected_items if item.get("pending_id")]
            discard_pending_knowledge_items(project_name, target_ids)
            queued_count = queue_pending_knowledge_items(
                project_name,
                [merged_item],
                scope=merged_item.get("scope", selected_items[0].get("scope", "reference")),
                authority=merged_item.get("authority", selected_items[0].get("authority", "curated")),
                source_title=merged_item.get("source_title", ""),
                source_origin=merged_item.get("source_origin", ""),
            )
            st.success(f"已合并 {len(target_ids)} 条，生成 {queued_count} 条新的待确认知识。")
            st.rerun()


def render_character_entity_card_panel(project_name: str):
    existing_cards = load_character_entities(project_name)
    st.markdown("#### 角色实体卡")
    st.caption("从已确认的角色、关系、能力、对白风格、时间线和约束知识中聚合角色资料卡。角色卡保存后会进入检索索引。")
    col_limit, col_action = st.columns([1, 1])
    max_characters = col_limit.number_input(
        "最多生成角色数",
        min_value=5,
        max_value=200,
        value=80,
        step=5,
        key="character_entity_max_count",
    )
    if col_action.button("生成角色实体卡预览", key="generate_character_entities", use_container_width=True):
        cards = build_character_entity_cards(project_name, max_characters=int(max_characters))
        st.session_state["character_entity_preview"] = cards
        st.success(f"已生成 {len(cards)} 张角色实体卡预览。")

    preview_cards = st.session_state.get("character_entity_preview", existing_cards)
    st.caption(f"已保存 {len(existing_cards)} 张；当前预览 {len(preview_cards)} 张。")
    if preview_cards:
        for card in preview_cards[:5]:
            with st.expander(f"{card.get('name', '未命名角色')} · 角色卡预览", expanded=False):
                if card.get("summary"):
                    st.write(card.get("summary"))
                if card.get("relationships"):
                    st.markdown("**关系**")
                    st.write("\n".join(f"- {item}" for item in card.get("relationships", [])[:5]))
                if card.get("dialogue_style"):
                    st.markdown("**对白/风格**")
                    st.write("\n".join(f"- {item}" for item in card.get("dialogue_style", [])[:5]))
                if card.get("constraints"):
                    st.markdown("**约束**")
                    st.write("\n".join(f"- {item}" for item in card.get("constraints", [])[:5]))

    raw_cards_json = st.text_area(
        "角色实体卡 JSON",
        value=json.dumps(preview_cards, ensure_ascii=False, indent=2),
        height=320,
        key="character_entity_cards_json",
    )
    col_save, col_clear = st.columns(2)
    if col_save.button("保存角色实体卡并重建索引", key="save_character_entities", use_container_width=True):
        try:
            parsed = json.loads(raw_cards_json)
            if not isinstance(parsed, list):
                st.error("角色实体卡必须是列表结构。")
            else:
                save_character_entities(project_name, parsed)
                rebuild_retrieval_assets(project_name, build_vectors=True)
                st.session_state["character_entity_preview"] = parsed
                st.success(f"已保存 {len(parsed)} 张角色实体卡。")
                st.rerun()
        except json.JSONDecodeError as exc:
            st.error(f"角色实体卡 JSON 格式错误：{exc}")
    if col_clear.button("清空预览", key="clear_character_entity_preview", use_container_width=True):
        st.session_state.pop("character_entity_preview", None)
        st.rerun()


def render_setting_entity_card_panel(project_name: str):
    existing_cards = load_setting_entities(project_name)
    st.markdown("#### 设定实体卡")
    st.caption("从已确认的世界规则、地点、组织、能力、物品和硬性约束中聚合设定资料卡。保存后会进入检索索引。")
    col_limit, col_action = st.columns([1, 1])
    max_cards = col_limit.number_input(
        "最多生成设定卡数",
        min_value=5,
        max_value=300,
        value=120,
        step=5,
        key="setting_entity_max_count",
    )
    if col_action.button("生成设定实体卡预览", key="generate_setting_entities", use_container_width=True):
        cards = build_setting_entity_cards(project_name, max_cards=int(max_cards))
        st.session_state["setting_entity_preview"] = cards
        st.success(f"已生成 {len(cards)} 张设定实体卡预览。")

    preview_cards = st.session_state.get("setting_entity_preview", existing_cards)
    st.caption(f"已保存 {len(existing_cards)} 张；当前预览 {len(preview_cards)} 张。")
    if preview_cards:
        rows = [
            {
                "类型": SETTING_ENTITY_CATEGORY_GROUPS.get(card.get("setting_type", ""), card.get("setting_type", "")),
                "名称": card.get("name", ""),
                "重要性": safe_confidence(card.get("importance", 0.5)),
                "世界线": card.get("worldline_label", ""),
            }
            for card in preview_cards[:12]
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        for card in preview_cards[:5]:
            with st.expander(f"{SETTING_ENTITY_CATEGORY_GROUPS.get(card.get('setting_type', ''), card.get('setting_type', '设定'))} / {card.get('name', '未命名设定')}", expanded=False):
                if card.get("summary"):
                    st.write(str(card.get("summary"))[:900])
                for label, field in [("规则/资料", "rules"), ("时间线", "timeline"), ("关联实体", "related_entities")]:
                    values = card.get(field, [])
                    if isinstance(values, list) and values:
                        st.markdown(f"**{label}**")
                        st.write("\n".join(f"- {item}" for item in values[:8]))
                if card.get("profile"):
                    st.caption("profile")
                    st.json(card.get("profile"))

    raw_cards_json = st.text_area(
        "设定实体卡 JSON",
        value=json.dumps(preview_cards, ensure_ascii=False, indent=2),
        height=320,
        key="setting_entity_cards_json",
    )
    col_save, col_clear = st.columns(2)
    if col_save.button("保存设定实体卡并重建索引", key="save_setting_entities", use_container_width=True):
        try:
            parsed = json.loads(raw_cards_json)
            if not isinstance(parsed, list):
                st.error("设定实体卡必须是列表结构。")
            else:
                save_setting_entities(project_name, parsed)
                rebuild_retrieval_assets(project_name, build_vectors=True)
                st.session_state["setting_entity_preview"] = parsed
                st.success(f"已保存 {len(parsed)} 张设定实体卡。")
                st.rerun()
        except json.JSONDecodeError as exc:
            st.error(f"设定实体卡 JSON 格式错误：{exc}")
    if col_clear.button("清空设定卡预览", key="clear_setting_entity_preview", use_container_width=True):
        st.session_state.pop("setting_entity_preview", None)
        st.rerun()


def render_entity_alias_panel(project_name: str):
    alias_groups = load_entity_aliases(project_name)
    st.markdown("#### 实体别名库")
    st.caption("沉淀同一实体的不同称呼，后续可辅助提取质检、检索和实体卡整理。")
    cols = st.columns(3)
    cols[0].metric("别名组", len(alias_groups))
    cols[1].metric("别名总数", sum(len(item.get("aliases", [])) for item in alias_groups if isinstance(item.get("aliases", []), list)))
    cols[2].metric("角色别名组", sum(1 for item in alias_groups if item.get("category") == "characters"))

    with st.expander("新增 / 编辑别名组", expanded=False):
        edit_options = ["__new__"] + [str(item.get("id") or index) for index, item in enumerate(alias_groups)]
        selected_alias_id = st.selectbox(
            "选择别名组",
            options=edit_options,
            format_func=lambda value: "新增别名组" if value == "__new__" else next(
                (
                    f"{label_knowledge_category(item.get('category', ''))} / {item.get('canonical_name', '')}"
                    for index, item in enumerate(alias_groups)
                    if str(item.get("id") or index) == value
                ),
                value,
            ),
            key="entity_alias_edit_select",
        )
        selected_group = {}
        if selected_alias_id != "__new__":
            selected_group = next(
                (item for index, item in enumerate(alias_groups) if str(item.get("id") or index) == selected_alias_id),
                {},
            )
        col_a, col_b = st.columns(2)
        category = col_a.selectbox(
            "实体分类",
            options=list(KNOWLEDGE_CATEGORY_LABELS.keys()),
            index=list(KNOWLEDGE_CATEGORY_LABELS.keys()).index(selected_group.get("category")) if selected_group.get("category") in KNOWLEDGE_CATEGORY_LABELS else 0,
            format_func=label_knowledge_category,
            key="entity_alias_category",
        )
        canonical_name = col_b.text_input("主名称", value=str(selected_group.get("canonical_name") or ""), key="entity_alias_canonical")
        aliases_text = st.text_area(
            "别名（每行一个）",
            value="\n".join(str(item) for item in selected_group.get("aliases", []) if str(item).strip()) if isinstance(selected_group.get("aliases", []), list) else "",
            height=120,
            key="entity_alias_aliases",
        )
        notes = st.text_area("备注", value=str(selected_group.get("notes") or ""), height=80, key="entity_alias_notes")
        col_save, col_delete = st.columns(2)
        if col_save.button("保存别名组", key="save_entity_alias_group", use_container_width=True):
            try:
                alias_group = upsert_entity_alias_group(
                    project_name,
                    category=category,
                    canonical_name=canonical_name,
                    aliases=[line.strip() for line in aliases_text.splitlines() if line.strip()],
                    notes=notes,
                    source_pending_ids=selected_group.get("source_pending_ids", []) if isinstance(selected_group.get("source_pending_ids", []), list) else [],
                )
                st.success(f"已保存别名组：{alias_group.get('canonical_name')}")
                st.rerun()
            except Exception as exc:
                st.error(f"保存失败：{exc}")
        if selected_alias_id != "__new__" and col_delete.button("删除别名组", key="delete_entity_alias_group", use_container_width=True):
            kept = [
                item for index, item in enumerate(alias_groups)
                if str(item.get("id") or index) != selected_alias_id
            ]
            save_entity_aliases(project_name, kept)
            st.success("已删除别名组。")
            st.rerun()

    if alias_groups:
        rows = []
        for item in alias_groups:
            aliases = item.get("aliases", []) if isinstance(item.get("aliases", []), list) else []
            rows.append({
                "分类": label_knowledge_category(item.get("category", "")),
                "主名称": item.get("canonical_name", ""),
                "别名": "、".join(str(value) for value in aliases[:8]),
                "备注": item.get("notes", ""),
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.caption("当前还没有实体别名组。")


def render_knowledge_organizer(project_name: str, knowledge_category_options: list[str]):
    with st.expander("结构化知识整理", expanded=False):
        st.caption("用于处理长篇资料导入后的重复条目。可以按分类查看、合并同名知识，或删除明显错误的条目。")
        render_character_entity_card_panel(project_name)
        st.divider()
        render_setting_entity_card_panel(project_name)
        st.divider()
        render_entity_alias_panel(project_name)
        st.divider()
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

        keyword = st.text_input("搜索正式知识", key=f"knowledge_organizer_keyword_{category}", placeholder="名称、摘要、来源、标签")
        worldline_options = sorted({
            str(item.get("worldline_label") or item.get("worldline_id") or "")
            for item in items
            if isinstance(item, dict) and str(item.get("worldline_label") or item.get("worldline_id") or "").strip()
        })
        selected_worldlines = st.multiselect(
            "筛选正式知识世界线",
            options=worldline_options,
            default=[],
            key=f"knowledge_organizer_worldlines_{category}",
        )
        candidate_indices = []
        keyword_value = keyword.strip().lower()
        for index, item in enumerate(items):
            item_worldline = str(item.get("worldline_label") or item.get("worldline_id") or "")
            if selected_worldlines and item_worldline not in selected_worldlines:
                continue
            if keyword_value:
                search_text = " ".join([
                    str(item.get("name", "")),
                    str(item.get("summary", "")),
                    str(item.get("source_title", "")),
                    str(item.get("source_origin", "")),
                    " ".join(str(tag) for tag in item.get("tags", []) if str(tag).strip()) if isinstance(item.get("tags"), list) else "",
                ]).lower()
                if keyword_value not in search_text:
                    continue
            candidate_indices.append(index)
        st.caption(f"当前筛选结果：{len(candidate_indices)} / {len(items)} 条")
        render_confirmed_knowledge_item_editor(project_name, category, items, candidate_indices)

        default_indices = duplicate_groups[0] if duplicate_groups else []
        default_indices = [index for index in default_indices if index in candidate_indices]
        selected_indices = st.multiselect(
            "选择要合并或删除的条目",
            options=candidate_indices,
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
                        if merge_confirmed_knowledge_items(project_name, category, selected_indices, parsed):
                            rebuild_retrieval_assets(project_name, build_vectors=True)
                            st.success(f"已合并 {len(selected_items)} 条结构化知识，并重建检索索引。")
                            st.rerun()
                        st.error("合并失败：条目不存在或分类无效。")
                except json.JSONDecodeError as exc:
                    st.error(f"结构化数据格式错误：{exc}")

        if selected_items:
            if confirmed_button(
                st,
                "删除所选结构化知识",
                "确认删除所选结构化知识",
                scoped_widget_key("knowledge_organizer_delete", project_name, category),
            ):
                removed_count = delete_confirmed_knowledge_items(project_name, category, selected_indices)
                if removed_count:
                    rebuild_retrieval_assets(project_name, build_vectors=True)
                    st.success(f"已删除 {removed_count} 条结构化知识，并重建检索索引。")
                    st.rerun()
                st.error("删除失败：条目不存在或分类无效。")

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
                        saved_count = replace_knowledge_category_items(project_name, category, parsed)
                        rebuild_retrieval_assets(project_name, build_vectors=True)
                        st.success(f"当前分类结构化知识已保存 {saved_count} 条，并重建检索索引。")
                        st.rerun()
                except json.JSONDecodeError as exc:
                    st.error(f"结构化数据格式错误：{exc}")


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


def render_knowledge_diff_item(item: dict, prefix: str):
    st.markdown(f"**{item.get('category_label') or label_knowledge_category(item.get('category', ''))} / {item.get('name', '未命名')}**")
    st.caption(
        f"原作状态={item.get('canon_status', 'unknown')} / 置信度={safe_confidence(item.get('confidence', 0.7)):.2f} / "
        f"证据强度={safe_confidence(item.get('evidence_strength', 0.5)):.2f} / 来源={item.get('source_title') or item.get('source_segment_title') or '-'}"
    )
    if item.get("summary"):
        st.write(str(item.get("summary"))[:500])
    details = item.get("details", {})
    if isinstance(details, dict) and details:
        st.caption(f"{prefix} details")
        st.json(details)


def render_extraction_diff_detail(project_name: str, diff: dict, key_prefix: str):
    if not isinstance(diff, dict) or not diff:
        return
    with st.expander("查看重提取差异详情", expanded=False):
        cols = st.columns(4)
        cols[0].metric("新增", diff.get("added_count", 0))
        cols[1].metric("匹配", diff.get("matched_count", 0))
        cols[2].metric("可能遗漏", diff.get("missing_count", 0))
        cols[3].metric("变化", diff.get("changed_count", 0))
        old_ids = [str(item) for item in diff.get("existing_pending_ids", []) if str(item).strip()]
        new_ids = [str(item) for item in diff.get("new_pending_ids", []) if str(item).strip()]
        if old_ids or new_ids:
            action_cols = st.columns(2)
            if action_cols[0].button("采用新版：删除旧待确认条目", key=f"{key_prefix}_accept_new", use_container_width=True):
                removed = discard_pending_knowledge_items(project_name, old_ids)
                st.success(f"已删除旧待确认条目 {removed} 条，保留本次重提取结果。")
                st.rerun()
            if action_cols[1].button("保留旧版：删除本次新增条目", key=f"{key_prefix}_keep_old", use_container_width=True):
                removed = discard_pending_knowledge_items(project_name, new_ids)
                st.success(f"已删除本次重提取新增/变化条目 {removed} 条，保留旧待确认结果。")
                st.rerun()

        tabs = st.tabs(["新增", "变化", "可能遗漏"])
        with tabs[0]:
            items = diff.get("added_items", [])
            if not items:
                st.caption("没有新增条目。")
            for index, item in enumerate(items[:10], start=1):
                render_knowledge_diff_item(item, f"{key_prefix}_added_{index}")
        with tabs[1]:
            items = diff.get("changed_items", [])
            if not items:
                st.caption("没有变化条目。")
            for index, pair in enumerate(items[:10], start=1):
                st.markdown(f"**{pair.get('label', '未命名条目')}**")
                if pair.get("changed_fields"):
                    st.caption("变化字段：" + "、".join(str(field) for field in pair.get("changed_fields", [])))
                old_col, new_col = st.columns(2)
                with old_col:
                    st.caption("旧提取")
                    render_knowledge_diff_item(pair.get("old", {}), f"{key_prefix}_old_{index}")
                with new_col:
                    st.caption("新提取")
                    render_knowledge_diff_item(pair.get("new", {}), f"{key_prefix}_new_{index}")
        with tabs[2]:
            items = diff.get("missing_items", [])
            if not items:
                st.caption("没有可能遗漏条目。")
            for index, item in enumerate(items[:10], start=1):
                render_knowledge_diff_item(item, f"{key_prefix}_missing_{index}")


def apply_long_reference_fanfic_preset(preset: str):
    if preset not in LONG_REFERENCE_PRESET_INFO:
        return
    if preset == "canon_foundation":
        st.session_state["long_reference_scope"] = "canon"
        st.session_state["long_reference_authority"] = "official"
        st.session_state["long_reference_source_type"] = "external_source"
        st.session_state["long_reference_quick_import_index"] = True
        st.session_state["long_reference_quick_auto_confirm"] = True
        st.session_state["long_reference_quick_consolidate"] = False
        st.session_state["long_reference_shared_expert_preset"] = "canon_auditor"
        st.session_state["long_reference_shared_category_strategy_canon_auditor"] = "preset"
        st.session_state["long_reference_shared_mode_canon_auditor"] = "strict_canon"
    elif preset == "fanfic_foundation":
        st.session_state["long_reference_scope"] = "canon"
        st.session_state["long_reference_authority"] = "official"
        st.session_state["long_reference_source_type"] = "external_source"
        st.session_state["long_reference_quick_import_index"] = True
        st.session_state["long_reference_quick_auto_confirm"] = True
        st.session_state["long_reference_quick_consolidate"] = True
        st.session_state["long_reference_shared_expert_preset"] = "balanced"
        st.session_state["long_reference_shared_category_strategy_balanced"] = "preset"
        st.session_state["long_reference_shared_mode_balanced"] = "deep"
    elif preset == "style_reference":
        st.session_state["long_reference_scope"] = "reference"
        st.session_state["long_reference_authority"] = "curated"
        st.session_state["long_reference_source_type"] = "external_source"
        st.session_state["long_reference_quick_import_index"] = True
        st.session_state["long_reference_quick_auto_confirm"] = True
        st.session_state["long_reference_quick_consolidate"] = False
        st.session_state["long_reference_shared_expert_preset"] = "style_expert"
        st.session_state["long_reference_shared_category_strategy_style_expert"] = "preset"
        st.session_state["long_reference_shared_mode_style_expert"] = "style"
    st.session_state["long_reference_active_preset"] = preset
    st.session_state["long_reference_preset_notice"] = f"已应用：{LONG_REFERENCE_PRESET_INFO[preset]['label']}"


def render_extraction_coverage_report(project_name: str, batch: dict | None = None, key_prefix: str = "coverage"):
    report = build_extraction_coverage_report(project_name, batch)
    with st.expander(f"提取覆盖率报告：{report['title']}", expanded=False):
        cols = st.columns(5)
        cols[0].metric("待确认知识", report["pending_count"])
        cols[1].metric("缺失分类", len(report["missing_categories"]))
        cols[2].metric("低证据", report["low_evidence"])
        cols[3].metric("低置信", report["low_confidence"])
        cols[4].metric("无证据", report["no_evidence"])
        if report["total_segments"]:
            st.caption(
                f"批次片段：已提取 {report['extracted_segments']} / {report['total_segments']}，失败 {report['failed_segments']}，"
                f"已有待确认知识覆盖片段 {report['covered_source_segments']}"
            )

        category_rows = [
            {"分类": label_knowledge_category(category), "待确认条目": count}
            for category, count in report["category_counts"].items()
        ]
        st.dataframe(category_rows, use_container_width=True, hide_index=True)
        if report["missing_categories"]:
            st.warning("缺失分类：" + "、".join(label_knowledge_category(category) for category in report["missing_categories"]))
        if report["weak_categories"]:
            st.caption("薄弱分类：" + "、".join(label_knowledge_category(category) for category in report["weak_categories"]))
        col_a, col_b = st.columns(2)
        col_a.json(report["canon_counts"])
        col_b.json(report["mode_counts"])


def render_ingestion_health_panel(project_name: str):
    report = build_ingestion_health_report(project_name)
    with st.expander("资料健康度总览", expanded=True):
        cols = st.columns(6)
        cols[0].metric("健康分", report["score"])
        cols[1].metric("已确认知识", report["confirmed_count"])
        cols[2].metric("待确认", report["pending_count"])
        cols[3].metric("导入未提取", report["imported_not_extracted"])
        cols[4].metric("提取失败", report["failed_segments"])
        cols[5].metric("高风险线索", report["high_risk_issue_count"])
        entity_cols = st.columns(4)
        entity_cols[0].metric("角色实体卡", report["character_entity_count"])
        entity_cols[1].metric("设定实体卡", report["setting_entity_count"])
        entity_cols[2].metric("别名组", report["alias_group_count"])
        entity_cols[3].metric("计划模板", report["extraction_plan_template_count"])
        if report["total_segments"]:
            st.caption(f"长篇片段提取进度：{report['extracted_segments']} / {report['total_segments']}")
        warning_parts = []
        if report["missing_confirmed"]:
            warning_parts.append("正式库缺失分类：" + "、".join(label_knowledge_category(category) for category in report["missing_confirmed"]))
        if report["weak_confirmed"]:
            warning_parts.append("正式库薄弱分类：" + "、".join(label_knowledge_category(category) for category in report["weak_confirmed"]))
        if report["low_evidence"] or report["low_confidence"] or report["no_evidence"]:
            warning_parts.append(f"待确认质量风险：低证据 {report['low_evidence']} / 低置信 {report['low_confidence']} / 无证据 {report['no_evidence']}")
        for text in warning_parts[:4]:
            st.warning(text)
        col_a, col_b = st.columns(2)
        col_a.dataframe(
            [{"分类": label_knowledge_category(category), "正式库": report["confirmed_counts"].get(category, 0), "待确认": report["pending_counts"].get(category, 0)} for category in KNOWLEDGE_CATEGORY_LABELS],
            use_container_width=True,
            hide_index=True,
        )
        col_b.caption("世界线分布")
        col_b.json({
            "待确认": report["worldline_counts"],
            "正式库": report["confirmed_worldline_counts"],
        })


def render_source_record_detail(project_name: str, record: dict):
    if record.get("kind") == "long_batch":
        batch = load_long_reference_batch(project_name, record.get("batch_id", ""))
        if not batch:
            st.warning("批次记录读取失败。")
            return
        st.caption(
            f"范围={label_scope(batch.get('scope', 'reference'))} / 可信度={label_authority(batch.get('authority', 'curated'))} / "
            f"类型={label_source_type(batch.get('source_type', 'external_source'))}"
        )
        segments = batch.get("segments", [])
        segment_options = list(range(len(segments)))
        selected_index = st.selectbox(
            "查看片段原文与关联知识",
            options=segment_options,
            format_func=lambda index: (
                f"{segments[index].get('index')}. {segments[index].get('title')} / "
                f"导入={label_batch_segment_status(segments[index].get('import_status', 'pending'))} / "
                f"提取={label_batch_segment_status(segments[index].get('extract_status', 'pending'))}"
            ),
            key=f"source_ledger_segment_{record.get('id')}",
        ) if segment_options else None
        if selected_index is None:
            return
        segment = segments[selected_index]
        st.text_area(
            "片段原文",
            value=segment.get("content", ""),
            height=260,
            key=f"source_ledger_segment_content_{record.get('id')}_{segment.get('segment_id')}",
            disabled=True,
        )
        related = get_segment_related_knowledge_items(project_name, segment)
        cols = st.columns(2)
        cols[0].metric("关联待确认", len(related["pending"]))
        cols[1].metric("关联已确认", len(related["confirmed"]))
        for label, items in [("待确认知识", related["pending"][:12]), ("已确认知识", related["confirmed"][:12])]:
            if not items:
                continue
            with st.expander(label, expanded=False):
                for item in items:
                    st.markdown(f"**{label_knowledge_category(item.get('category', ''))} / {item.get('name', '未命名')}**")
                    if item.get("summary"):
                        st.caption(str(item.get("summary"))[:260])
        return

    if record.get("kind") == "retrieval_source":
        payload = read_retrieval_source_payload(project_name, record.get("relative_path", ""))
        metadata = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
        st.caption(
            f"文件={record.get('relative_path', '-')} / 范围={label_scope(record.get('scope', 'reference'))} / "
            f"可信度={label_authority(record.get('authority', 'unknown'))} / 类型={label_source_type(record.get('source_type', 'external_source'))}"
        )
        if record.get("source_origin"):
            st.caption(f"来源：{record.get('source_origin')}")
        if payload.get("summary"):
            st.markdown("##### 摘要")
            st.write(payload.get("summary"))
        content = str(payload.get("content") or payload.get("body") or "")
        if metadata:
            with st.expander("元数据", expanded=False):
                st.json(metadata)
        if content:
            st.text_area(
                "资料正文",
                value=content,
                height=260,
                key=f"source_ledger_content_{record.get('id')}",
                disabled=True,
            )
        return

    st.caption("这个来源只在待确认或已确认知识中出现，当前没有对应的原文批次或检索资料文件。")


def render_source_ledger_page(project_name: str):
    with st.expander("资料来源台账", expanded=True):
        records = build_ingestion_source_ledger(project_name)
        if not records:
            st.caption("当前还没有可追踪的资料来源。")
            return

        kind_filter = st.multiselect(
            "来源类型",
            options=["long_batch", "retrieval_source", "knowledge_only"],
            default=["long_batch", "retrieval_source", "knowledge_only"],
            format_func=lambda value: {
                "long_batch": "长篇批次",
                "retrieval_source": "检索资料",
                "knowledge_only": "知识来源",
            }.get(value, value),
            key="source_ledger_kind_filter",
        )
        keyword = st.text_input("按标题或来源搜索", key="source_ledger_keyword")
        filtered_records = []
        for record in records:
            if kind_filter and record.get("kind") not in kind_filter:
                continue
            search_text = " ".join([
                str(record.get("title", "")),
                str(record.get("source_origin", "")),
                str(record.get("relative_path", "")),
                str(record.get("file_name", "")),
            ]).lower()
            if keyword.strip() and keyword.strip().lower() not in search_text:
                continue
            filtered_records.append(record)

        metric_cols = st.columns(4)
        metric_cols[0].metric("来源记录", len(filtered_records))
        metric_cols[1].metric("片段/资料", sum(int(item.get("segment_count") or 0) for item in filtered_records))
        metric_cols[2].metric("待确认", sum(int(item.get("pending_count") or 0) for item in filtered_records))
        metric_cols[3].metric("已确认", sum(int(item.get("confirmed_count") or 0) for item in filtered_records))

        table_rows = []
        for record in filtered_records:
            table_rows.append({
                "类型": record.get("kind_label", ""),
                "标题": record.get("title", ""),
                "范围": label_scope(record.get("scope", "")) if record.get("scope") else "-",
                "可信度": label_authority(record.get("authority", "")) if record.get("authority") else "-",
                "资料类型": label_source_type(record.get("source_type", "")),
                "片段": record.get("segment_count", 0),
                "已导入": record.get("imported_count", 0),
                "已提取": record.get("extracted_count", 0),
                "失败": record.get("failed_count", 0),
                "待确认": record.get("pending_count", 0),
                "已确认": record.get("confirmed_count", 0),
            })
        st.dataframe(table_rows, use_container_width=True, hide_index=True)

        selected_record_id = st.selectbox(
            "查看来源详情",
            options=[record.get("id", "") for record in filtered_records],
            format_func=lambda record_id: next(
                (f"{record.get('kind_label')} / {record.get('title')}" for record in filtered_records if record.get("id") == record_id),
                record_id,
            ),
            key="source_ledger_selected_record",
        )
        selected_record = next((record for record in filtered_records if record.get("id") == selected_record_id), {})
        if selected_record:
            render_source_record_detail(project_name, selected_record)


def render_long_reference_batch_manager(project_name: str, knowledge_category_options: list[str]):
    with st.expander("长篇资料批次管理", expanded=False):
        batches = list_long_reference_batches(project_name)
        if not batches:
            st.caption("当前还没有长篇资料批次。请先在“长篇文本导入”里上传或粘贴整本资料并创建批次。")
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
        resume_state = summarize_long_reference_resume_state(segments)
        unfinished_indices = resume_state["unfinished_indices"]
        imported_not_extracted_indices = resume_state["imported_not_extracted_indices"]
        failed_indices = resume_state["failed_indices"]
        pending_import_indices = resume_state["pending_import_indices"]
        if unfinished_indices:
            st.warning(
                f"检测到这个批次还没处理完：未导入 {len(pending_import_indices)} 段，"
                f"已导入但未提取 {len(imported_not_extracted_indices)} 段，"
                f"提取失败 {len(failed_indices)} 段。"
            )
            st.info(
                "怎么继续：下面已经默认切到“未完成（推荐续跑）”。保持默认选择，点击“继续处理所选片段”。"
                "系统会跳过已导入片段的重复导入，只继续未完成的提取；失败片段会按当前设置重试。"
            )
        else:
            st.success("这个批次的片段都已经完成提取。下一步可以去“待确认知识”审核，或按需重跑已提取片段。")

        render_extraction_coverage_report(project_name, batch, key_prefix=f"batch_{selected_batch_id}")

        filter_key = f"long_reference_batch_filter_{selected_batch_id}"
        if filter_key not in st.session_state:
            st.session_state[filter_key] = "未完成（推荐续跑）" if unfinished_indices else "全部"
        filter_mode = st.selectbox(
            "查看哪些片段",
            options=["未完成（推荐续跑）", "已导入未提取", "未导入", "提取失败", "已提取", "全部"],
            key=filter_key,
        )
        filtered_indices = []
        for index, segment in enumerate(segments):
            if filter_mode == "未完成（推荐续跑）" and index not in unfinished_indices:
                continue
            if filter_mode == "已导入未提取" and index not in imported_not_extracted_indices:
                continue
            if filter_mode == "未导入" and index not in pending_import_indices:
                continue
            if filter_mode == "提取失败" and index not in failed_indices:
                continue
            if filter_mode == "已提取" and segment.get("extract_status") not in {"queued", "extracted"}:
                continue
            filtered_indices.append(index)

        selected_segments_key = f"long_reference_batch_selected_segments_{selected_batch_id}_{stable_widget_suffix(filter_mode)}"
        selected_indices = st.multiselect(
            "选择要继续处理的片段",
            options=filtered_indices,
            default=filtered_indices[: min(20, len(filtered_indices))],
            format_func=lambda index: (
                f"{segments[index].get('index')}. {segments[index].get('title')}"
                f" / 导入={label_batch_segment_status(segments[index].get('import_status', 'pending'))}"
                f" / 提取={label_batch_segment_status(segments[index].get('extract_status', 'pending'))}"
            ),
            key=selected_segments_key,
        )

        for index in filtered_indices[:12]:
            segment = segments[index]
            st.markdown(f"#### {segment.get('index')}. {segment.get('title')}")
            st.caption(
                f"字符数={segment.get('char_count')} / 导入={label_batch_segment_status(segment.get('import_status', 'pending'))} / 提取={label_batch_segment_status(segment.get('extract_status', 'pending'))} / 待确认知识={segment.get('queued_knowledge_count', 0)}"
            )
            if segment.get("extract_error"):
                st.warning(segment.get("extract_error"))
            extract_diff = segment.get("last_extract_diff", {})
            if isinstance(extract_diff, dict) and extract_diff:
                st.caption(
                    f"上次提取对比：新增 {extract_diff.get('added_count', 0)} / 匹配 {extract_diff.get('matched_count', 0)} / "
                    f"可能遗漏 {extract_diff.get('missing_count', 0)} / 变化 {extract_diff.get('changed_count', 0)}"
                )
                render_extraction_diff_detail(project_name, extract_diff, key_prefix=f"segment_diff_{selected_batch_id}_{index}")
        if len(filtered_indices) > 12:
            st.caption(f"仅预览前 12 个匹配片段，共 {len(filtered_indices)} 个。")

        st.markdown("#### 推荐操作")
        st.caption("想继续推进这个批次时，优先用自动处理：未导入片段会进入资料索引，片段会被提取成候选知识，低风险条目会自动入库，风险条目保留待确认。")
        quick_continue_limit = st.number_input(
            "本次最多自动处理片段数",
            min_value=1,
            value=min(5, max(1, len(selected_indices))),
            key=f"batch_quick_limit_{selected_batch_id}",
        )
        quick_continue_high_ok = True
        if quick_continue_limit > 50:
            st.warning(f"处理 {quick_continue_limit} 段将产生约 {quick_continue_limit} 次 LLM 调用，预计耗时会较长。")
            quick_continue_high_ok = st.checkbox(
                "我确认要大量处理",
                key=f"batch_quick_high_confirm_{selected_batch_id}",
            )
        selected_count = len(selected_indices)
        planned_quick_count = min(int(quick_continue_limit), selected_count)
        st.info(
            f"本次继续处理将按当前选择顺序处理 {planned_quick_count} 个片段；"
            f"已选择 {selected_count} 个，当前过滤结果共 {len(filtered_indices)} 个片段。"
        )
        selected_needs_import = any(index in pending_import_indices for index in selected_indices)
        with st.expander("批次自动处理策略（可选）", expanded=False):
            quick_continue_auto_confirm = st.checkbox(
                "自动审核并保存低风险知识",
                value=True,
                key=f"batch_quick_auto_confirm_{selected_batch_id}",
            )
            quick_continue_import = st.checkbox(
                "同时导入资料索引",
                value=selected_needs_import,
                key=f"batch_quick_import_{selected_batch_id}",
                help="断点续跑时，已导入片段会自动跳过，不会重复写入资料索引。",
            )
            quick_continue_preset_key = st.selectbox(
                "专家提取预设",
                options=list(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.keys()),
                index=list(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.keys()).index("balanced"),
                format_func=lambda value: KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[value]["label"],
                key=f"batch_quick_preset_{selected_batch_id}",
            )
            quick_continue_preset = KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[quick_continue_preset_key]
            quick_continue_categories = st.multiselect(
                "提取分类",
                options=knowledge_category_options,
                default=default_extraction_categories("preset", quick_continue_preset, knowledge_category_options),
                format_func=label_knowledge_category,
                key=f"batch_quick_categories_{selected_batch_id}_{quick_continue_preset_key}",
            )
            quick_continue_mode = st.selectbox(
                "提取模式",
                options=list(KNOWLEDGE_EXTRACTION_MODE_LABELS.keys()),
                index=list(KNOWLEDGE_EXTRACTION_MODE_LABELS.keys()).index(quick_continue_preset["mode"]) if quick_continue_preset["mode"] in KNOWLEDGE_EXTRACTION_MODE_LABELS else 0,
                format_func=lambda value: KNOWLEDGE_EXTRACTION_MODE_LABELS.get(value, value),
                key=f"batch_quick_mode_{selected_batch_id}_{quick_continue_preset_key}",
            )
            st.info(KNOWLEDGE_EXTRACTION_MODE_HELP.get(quick_continue_mode, "当前模式暂无说明。"))
            quick_continue_custom_instructions = st.text_area(
                "补充提取要求（高级，可选）",
                height=90,
                key=f"batch_quick_custom_instructions_{selected_batch_id}_{quick_continue_preset_key}",
                placeholder="例如：只保留稳定设定；角色心理推断必须标为 inferred。",
            )
        if "quick_continue_categories" not in locals():
            quick_continue_preset = KNOWLEDGE_EXTRACTION_EXPERT_PRESETS["balanced"]
            quick_continue_categories = default_extraction_categories("preset", quick_continue_preset, knowledge_category_options)
            quick_continue_mode = quick_continue_preset["mode"]
            quick_continue_auto_confirm = True
            quick_continue_import = True
            quick_continue_custom_instructions = ""
        if st.button("继续处理所选片段", key=f"batch_quick_process_{selected_batch_id}", use_container_width=True, type="primary" if unfinished_indices else "secondary"):
            if not selected_indices:
                st.error("请先选择片段。")
            elif not quick_continue_categories:
                st.error("请至少选择一个提取分类。")
            elif not quick_continue_high_ok:
                st.error("处理数量超过 50 段，请先勾选确认框。")
            else:
                with st.spinner("正在继续处理批次..."):
                    progress_callback = create_batch_progress_callback("批次自动处理")
                    batch, quick_summary = run_long_reference_quick_process(
                        project_name,
                        batch,
                        selected_indices[: int(quick_continue_limit)],
                        enabled_categories=quick_continue_categories,
                        extraction_mode=quick_continue_mode,
                        extract_limit=int(quick_continue_limit),
                        import_to_index=quick_continue_import,
                        consolidate_after_extract=False,
                        auto_confirm_safe_items=quick_continue_auto_confirm,
                        custom_instructions=quick_continue_custom_instructions,
                        progress_callback=progress_callback,
                    )
                st.session_state[f"batch_quick_result_{selected_batch_id}"] = quick_summary
                st.success(
                    f"已处理：导入 {quick_summary.get('imported_count', 0)} 段，"
                    f"提取 {quick_summary.get('processed_count', 0)} 段，"
                    f"自动保存 {quick_summary.get('auto_confirmed_count', 0)} 条，"
                    f"保留待确认 {quick_summary.get('blocked_count', 0)} 条。"
                )
                st.rerun()
        batch_quick_result = st.session_state.get(f"batch_quick_result_{selected_batch_id}", {})
        if batch_quick_result:
            with st.expander("上次批次自动处理结果", expanded=bool(batch_quick_result.get("blocked_count"))):
                st.json({
                    "导入片段": batch_quick_result.get("imported_count", 0),
                    "提取片段": batch_quick_result.get("processed_count", 0),
                    "新增候选": batch_quick_result.get("new_pending_count", 0),
                    "自动保存": batch_quick_result.get("auto_confirmed_count", 0),
                    "自动审核记录": batch_quick_result.get("auto_confirm", {}).get("run_id", ""),
                    "保留待确认": batch_quick_result.get("blocked_count", 0),
                    "保留原因": batch_quick_result.get("auto_confirm", {}).get("blocked_reasons", {}),
                    "失败": batch_quick_result.get("failed_titles", []),
                })

        st.markdown("#### 高级：手动处理")
        col_import, col_extract, col_retry, col_reextract = st.columns(4)
        if col_import.button("导入所选未导入片段", key=f"batch_import_{selected_batch_id}"):
            target_indices = [index for index in selected_indices if segments[index].get("import_status") != "imported"]
            if not target_indices:
                st.error("没有可导入的未导入片段。")
            else:
                _, imported = import_long_reference_segments(project_name, batch, target_indices)
                st.success(f"已导入 {imported} 个片段，并重建检索索引。")
                st.rerun()

        extract_limit = st.number_input("本次最多提取片段数", min_value=1, value=5, key=f"batch_extract_limit_{selected_batch_id}")
        batch_extract_high_ok = True
        if extract_limit > 50:
            st.warning(f"提取 {extract_limit} 段将产生约 {extract_limit} 次 LLM 调用，预计耗时会较长。")
            batch_extract_high_ok = st.checkbox(
                "我确认要大量处理",
                key=f"batch_extract_high_confirm_{selected_batch_id}",
            )
        expert_preset = st.selectbox(
            "专家提取预设",
            options=list(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.keys()),
            format_func=lambda value: KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[value]["label"],
            key=f"batch_extract_expert_{selected_batch_id}",
            help="预设会自动推荐提取分类和提取模式。第一次处理长篇资料建议使用“平衡总管”。",
        )
        preset = KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[expert_preset]
        category_default_strategy = st.radio(
            "提取分类初始策略",
            options=["preset", "all", "none"],
            format_func=lambda value: {"preset": "按专家预设", "all": "全选分类", "none": "不预选分类"}.get(value, value),
            horizontal=True,
            key=f"batch_extract_category_strategy_{selected_batch_id}_{expert_preset}",
            help="只影响当前控件的默认勾选。分类越多，覆盖越广；分类越少，输出越聚焦。",
        )
        enabled_categories = st.multiselect(
            "提取分类",
            options=knowledge_category_options,
            default=default_extraction_categories(category_default_strategy, preset, knowledge_category_options),
            format_func=label_knowledge_category,
            key=f"batch_extract_categories_{selected_batch_id}_{expert_preset}_{category_default_strategy}",
            help="决定允许模型输出哪些类型的知识。没有选中的分类不会被主动提取。",
        )
        extraction_mode = st.selectbox(
            "提取模式",
            options=list(KNOWLEDGE_EXTRACTION_MODE_LABELS.keys()),
            index=list(KNOWLEDGE_EXTRACTION_MODE_LABELS.keys()).index(preset["mode"]) if preset["mode"] in KNOWLEDGE_EXTRACTION_MODE_LABELS else 0,
            format_func=lambda value: KNOWLEDGE_EXTRACTION_MODE_LABELS.get(value, value),
            key=f"batch_extract_mode_{selected_batch_id}_{expert_preset}",
            help="模式决定模型看资料时的优先级。通用更稳，深度更适合正式搭同人资料地基。",
        )
        st.info(KNOWLEDGE_EXTRACTION_MODE_HELP.get(extraction_mode, "当前模式暂无说明。"))
        if col_extract.button("提取所选未提取片段", key=f"batch_extract_{selected_batch_id}"):
            if not batch_extract_high_ok:
                st.error("处理数量超过 50 段，请先勾选确认框。")
            else:
                target_indices = [
                    index for index in selected_indices
                    if segments[index].get("extract_status", "pending") in {"pending", ""}
                ][: int(extract_limit)]
                if not target_indices:
                    st.error("没有可提取的未提取片段。")
                elif not enabled_categories:
                    st.error("请至少选择一个提取分类。")
                else:
                    with st.spinner("正在提取所选片段..."):
                        progress_callback = create_batch_progress_callback("批量提取")
                        _, processed, queued_total, failures = extract_long_reference_segments_to_queue(
                            project_name,
                            batch,
                            target_indices,
                            enabled_categories,
                            extraction_mode=extraction_mode,
                            progress_callback=progress_callback,
                        )
                    st.session_state[f"batch_manual_extract_result_{selected_batch_id}"] = {
                        "action": "提取所选未提取片段",
                        "processed": processed,
                        "queued_total": queued_total,
                        "failures": failures,
                    }
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
                with st.spinner("正在重试失败片段..."):
                    progress_callback = create_batch_progress_callback("重试提取")
                    _, processed, queued_total, failures = extract_long_reference_segments_to_queue(
                        project_name,
                        batch,
                        target_indices,
                        enabled_categories,
                        extraction_mode=extraction_mode,
                        progress_callback=progress_callback,
                    )
                st.session_state[f"batch_manual_extract_result_{selected_batch_id}"] = {
                    "action": "重试失败片段",
                    "processed": processed,
                    "queued_total": queued_total,
                    "failures": failures,
                }
                st.rerun()

        if col_reextract.button("重新提取已提取片段", key=f"batch_reextract_{selected_batch_id}"):
            target_indices = [
                index for index in selected_indices
                if segments[index].get("extract_status") in {"queued", "extracted"}
            ][: int(extract_limit)]
            if not target_indices:
                st.error("没有选中的已提取片段。")
            elif not enabled_categories:
                st.error("请至少选择一个提取分类。")
            else:
                with st.spinner("正在重新提取片段..."):
                    progress_callback = create_batch_progress_callback("重新提取")
                    _, processed, queued_total, failures = extract_long_reference_segments_to_queue(
                        project_name,
                        batch,
                        target_indices,
                        enabled_categories,
                        extraction_mode=extraction_mode,
                        progress_callback=progress_callback,
                    )
                st.session_state[f"batch_manual_extract_result_{selected_batch_id}"] = {
                    "action": "重新提取已提取片段",
                    "processed": processed,
                    "queued_total": queued_total,
                    "failures": failures,
                }
                st.rerun()

        manual_extract_result = st.session_state.get(f"batch_manual_extract_result_{selected_batch_id}", {})
        if manual_extract_result:
            with st.expander("上次手动提取结果", expanded=bool(manual_extract_result.get("failures"))):
                st.json({
                    "操作": manual_extract_result.get("action", ""),
                    "处理片段": manual_extract_result.get("processed", 0),
                    "新增候选": manual_extract_result.get("queued_total", 0),
                    "失败": manual_extract_result.get("failures", []),
                })

        st.markdown("#### 多专家提取计划")
        plan_col_a, plan_col_b, plan_col_c = st.columns(3)
        plan_key = plan_col_a.selectbox(
            "计划预设",
            options=list(KNOWLEDGE_EXTRACTION_PLAN_PRESETS.keys()),
            format_func=lambda value: KNOWLEDGE_EXTRACTION_PLAN_PRESETS[value]["label"],
            key=f"batch_extract_plan_{selected_batch_id}",
        )
        plan_preset = KNOWLEDGE_EXTRACTION_PLAN_PRESETS[plan_key]
        project_plan_templates = load_extraction_plan_templates(project_name)
        template_options = ["__none__"] + [str(item.get("id") or "") for item in project_plan_templates if item.get("id")]
        selected_template_id = st.selectbox(
            "项目提取计划模板",
            options=template_options,
            format_func=lambda value: "不使用项目模板" if value == "__none__" else next(
                (f"{item.get('name', value)} / {' / '.join(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.get(step, {}).get('label', step) for step in item.get('steps', []))}" for item in project_plan_templates if item.get("id") == value),
                value,
            ),
            key=f"batch_extract_plan_template_{selected_batch_id}",
        )
        selected_template = next((item for item in project_plan_templates if item.get("id") == selected_template_id), {})
        plan_limit = plan_col_b.number_input(
            "计划最多处理片段数",
            min_value=1,
            value=min(3, max(1, len(selected_indices) or 1)),
            key=f"batch_extract_plan_limit_{selected_batch_id}",
        )
        batch_plan_high_ok = True
        if plan_limit > 50:
            st.warning(f"计划处理 {plan_limit} 段将产生约 {plan_limit} 次 LLM 调用，预计耗时会较长。")
            batch_plan_high_ok = st.checkbox(
                "我确认要大量处理",
                key=f"batch_plan_high_confirm_{selected_batch_id}",
            )
        plan_reextract = plan_col_c.checkbox(
            "允许重跑已提取片段",
            value=False,
            key=f"batch_extract_plan_reextract_{selected_batch_id}",
        )
        plan_steps = st.multiselect(
            "专家步骤顺序",
            options=list(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.keys()),
            default=[
                step for step in (selected_template.get("steps") if selected_template else plan_preset["steps"])
                if step in KNOWLEDGE_EXTRACTION_EXPERT_PRESETS
            ],
            format_func=lambda value: KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[value]["label"],
            key=f"batch_extract_plan_steps_{selected_batch_id}_{plan_key}_{selected_template_id}",
        )
        with st.expander("保存当前专家步骤为项目模板", expanded=False):
            template_name = st.text_input("模板名称", value=plan_preset.get("label", "自定义提取计划"), key=f"batch_extract_plan_template_name_{selected_batch_id}")
            template_notes = st.text_area("模板备注", value="", height=80, key=f"batch_extract_plan_template_notes_{selected_batch_id}")
            if st.button("保存提取计划模板", key=f"batch_save_extract_plan_template_{selected_batch_id}", use_container_width=True):
                try:
                    saved_template = upsert_extraction_plan_template(project_name, template_name, plan_steps, template_notes)
                    st.success(f"已保存项目提取计划模板：{saved_template.get('name')}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"保存模板失败：{exc}")
            if project_plan_templates:
                st.markdown("##### 已保存模板")
                st.dataframe(
                    [
                        {
                            "名称": item.get("name", ""),
                            "步骤": " / ".join(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.get(step, {}).get("label", step) for step in item.get("steps", [])),
                            "备注": item.get("notes", ""),
                        }
                        for item in project_plan_templates
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
                delete_template_id = st.selectbox(
                    "删除模板",
                    options=["__none__"] + [str(item.get("id") or "") for item in project_plan_templates if item.get("id")],
                    format_func=lambda value: "不删除" if value == "__none__" else next((item.get("name", value) for item in project_plan_templates if item.get("id") == value), value),
                    key=f"batch_delete_extract_plan_template_select_{selected_batch_id}",
                )
                if delete_template_id != "__none__" and confirmed_button(
                    st,
                    "删除所选提取计划模板",
                    "确认删除所选模板",
                    scoped_widget_key("batch_delete_extract_plan_template", project_name, selected_batch_id),
                ):
                    if delete_extraction_plan_template(project_name, delete_template_id):
                        st.success("已删除提取计划模板。")
                        st.rerun()
                    else:
                        st.error("删除失败：模板不存在。")
                templates_json = st.text_area(
                    "模板库 JSON",
                    value=json.dumps(project_plan_templates, ensure_ascii=False, indent=2),
                    height=180,
                    key=f"batch_extract_plan_templates_json_{selected_batch_id}",
                )
                if st.button("保存模板库 JSON", key=f"batch_save_extract_plan_templates_json_{selected_batch_id}", use_container_width=True):
                    try:
                        parsed = json.loads(templates_json)
                        if not isinstance(parsed, list):
                            st.error("模板库必须是列表结构。")
                        else:
                            save_extraction_plan_templates(project_name, parsed)
                            st.success("已保存提取计划模板库。")
                            st.rerun()
                    except json.JSONDecodeError as exc:
                        st.error(f"模板库 JSON 格式错误：{exc}")
        if plan_steps:
            st.caption("计划顺序：" + " / ".join(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[step]["label"] for step in plan_steps))
        auto_consolidate = st.checkbox(
            "计划完成后自动整理当前批次待确认知识",
            value=False,
            key=f"batch_extract_plan_auto_consolidate_{selected_batch_id}",
        )
        auto_consolidation_mode = "balanced"
        auto_consolidation_limit = 80
        auto_consolidation_categories = [category for category in ["characters", "relationships", "timeline_events", "world_rules", "abilities", "items"] if category in knowledge_category_options]
        if auto_consolidate:
            auto_col_a, auto_col_b = st.columns(2)
            auto_consolidation_mode = auto_col_a.selectbox(
                "自动整理模式",
                options=list(KNOWLEDGE_CONSOLIDATION_MODE_LABELS.keys()),
                format_func=lambda value: KNOWLEDGE_CONSOLIDATION_MODE_LABELS.get(value, value),
                key=f"batch_extract_plan_auto_consolidation_mode_{selected_batch_id}",
            )
            auto_consolidation_limit = auto_col_b.number_input(
                "自动整理最多条目数",
                min_value=5,
                max_value=200,
                value=80,
                step=5,
                key=f"batch_extract_plan_auto_consolidation_limit_{selected_batch_id}",
            )
            auto_consolidation_categories = st.multiselect(
                "自动整理分类",
                options=knowledge_category_options,
                default=auto_consolidation_categories,
                format_func=label_knowledge_category,
                key=f"batch_extract_plan_auto_consolidation_categories_{selected_batch_id}",
            )
        if st.button("执行多专家提取计划", key=f"batch_run_extract_plan_{selected_batch_id}", use_container_width=True):
            if not selected_indices:
                st.error("请先选择要处理的片段。")
            elif not plan_steps:
                st.error("请至少选择一个专家步骤。")
            elif not batch_plan_high_ok:
                st.error("处理数量超过 50 段，请先勾选确认框。")
            else:
                with st.spinner("正在按专家计划提取资料..."):
                    progress_callback = create_batch_progress_callback("多专家提取计划")
                    updated_batch, plan_summary = run_long_reference_extraction_plan(
                        project_name,
                        batch,
                        selected_indices,
                        plan_steps,
                        max_segments=int(plan_limit),
                        reextract_completed=plan_reextract,
                        progress_callback=progress_callback,
                    )
                    auto_result = {}
                    if auto_consolidate and plan_summary.get("queued_total", 0):
                        auto_result = consolidate_batch_pending_items(
                            project_name,
                            updated_batch,
                            categories=auto_consolidation_categories,
                            consolidation_mode=auto_consolidation_mode,
                            limit=int(auto_consolidation_limit),
                        )
                        plan_summary["auto_consolidation"] = {
                            "enabled": True,
                            "success": auto_result.get("success", False),
                            "message": auto_result.get("message", ""),
                            "source_count": auto_result.get("source_count", 0),
                            "queued_count": auto_result.get("queued_count", 0),
                            "mode": auto_consolidation_mode,
                            "categories": auto_consolidation_categories,
                        }
                        if auto_result.get("result"):
                            st.session_state[f"batch_consolidation_result_{selected_batch_id}"] = auto_result.get("result")
                    elif auto_consolidate:
                        plan_summary["auto_consolidation"] = {
                            "enabled": True,
                            "success": False,
                            "message": "本次计划没有新增待确认知识，已跳过自动整理。",
                            "source_count": 0,
                            "queued_count": 0,
                            "mode": auto_consolidation_mode,
                            "categories": auto_consolidation_categories,
                        }
                    if auto_consolidate:
                        history = updated_batch.get("extraction_plan_runs", [])
                        if isinstance(history, list) and history:
                            history[-1] = plan_summary
                            updated_batch["extraction_plan_runs"] = history
                        updated_batch["last_extraction_plan"] = plan_summary
                        save_long_reference_batch(project_name, updated_batch)
                st.session_state[f"batch_extract_plan_result_{selected_batch_id}"] = plan_summary
                if not plan_summary.get("segment_indices"):
                    st.warning("没有可执行的目标片段。若要重跑已提取片段，请勾选“允许重跑已提取片段”。")
                else:
                    st.success(
                        f"计划完成：执行 {len(plan_summary.get('processed_steps', []))} 个专家步骤，"
                        f"累计处理 {plan_summary.get('processed_segments', 0)} 次片段，加入 {plan_summary.get('queued_total', 0)} 条待确认知识。"
                    )
                    if plan_summary.get("auto_consolidation", {}).get("enabled"):
                        auto_info = plan_summary.get("auto_consolidation", {})
                        if auto_info.get("success"):
                            st.success(auto_info.get("message", "自动整理已完成。"))
                        else:
                            st.warning(auto_info.get("message", "自动整理没有生成结果。"))
                    for failure in plan_summary.get("failures", [])[:5]:
                        st.warning(f"计划步骤失败：{failure}")
                    st.rerun()

        plan_result = st.session_state.get(f"batch_extract_plan_result_{selected_batch_id}") or batch.get("last_extraction_plan", {})
        if isinstance(plan_result, dict) and plan_result:
            with st.expander("上次多专家提取计划结果", expanded=False):
                step_rows = []
                for step in plan_result.get("processed_steps", []):
                    step_rows.append({
                        "专家": step.get("label", step.get("step", "")),
                        "模式": KNOWLEDGE_EXTRACTION_MODE_LABELS.get(step.get("mode", ""), step.get("mode", "")),
                        "分类": "、".join(label_knowledge_category(category) for category in step.get("categories", [])),
                        "处理片段": step.get("processed", 0),
                        "入队知识": step.get("queued", 0),
                        "失败": len(step.get("failures", [])),
                    })
                if step_rows:
                    st.dataframe(step_rows, use_container_width=True, hide_index=True)
                st.caption(
                    f"目标片段数={len(plan_result.get('segment_indices', []))} / "
                    f"累计处理={plan_result.get('processed_segments', 0)} / "
                    f"入队知识={plan_result.get('queued_total', 0)} / "
                    f"失败={plan_result.get('failure_count', 0)}"
                )
                auto_info = plan_result.get("auto_consolidation", {})
                if isinstance(auto_info, dict) and auto_info.get("enabled"):
                    st.caption(
                        f"自动整理：{KNOWLEDGE_CONSOLIDATION_MODE_LABELS.get(auto_info.get('mode', ''), auto_info.get('mode', ''))} / "
                        f"来源条目={auto_info.get('source_count', 0)} / 生成={auto_info.get('queued_count', 0)} / "
                        f"结果={'成功' if auto_info.get('success') else '未完成'}"
                    )
                    if auto_info.get("message"):
                        st.info(auto_info.get("message"))

        st.markdown("#### 批次级整理")
        batch_pending_items = get_batch_pending_knowledge_items(project_name, batch)
        st.caption(f"当前批次关联待确认知识 {len(batch_pending_items)} 条。整理会合并同一实体/关系/事件，并用整理后的条目替换这些散条目。")
        col_mode, col_limit = st.columns(2)
        consolidation_mode = col_mode.selectbox(
            "整理模式",
            options=list(KNOWLEDGE_CONSOLIDATION_MODE_LABELS.keys()),
            format_func=lambda value: KNOWLEDGE_CONSOLIDATION_MODE_LABELS.get(value, value),
            key=f"batch_consolidation_mode_{selected_batch_id}",
        )
        consolidation_limit = col_limit.number_input(
            "本次最多整理条目数",
            min_value=5,
            max_value=200,
            value=60,
            step=5,
            key=f"batch_consolidation_limit_{selected_batch_id}",
        )
        consolidation_categories = st.multiselect(
            "整理分类",
            options=knowledge_category_options,
            default=["characters", "relationships", "timeline_events", "world_rules", "abilities", "items"],
            format_func=label_knowledge_category,
            key=f"batch_consolidation_categories_{selected_batch_id}",
        )
        if st.button("整理当前批次待确认知识", key=f"batch_consolidate_pending_{selected_batch_id}", use_container_width=True):
            try:
                consolidation_summary = consolidate_batch_pending_items(
                    project_name,
                    batch,
                    categories=consolidation_categories,
                    consolidation_mode=consolidation_mode,
                    limit=int(consolidation_limit),
                )
                if consolidation_summary.get("result"):
                    st.session_state[f"batch_consolidation_result_{selected_batch_id}"] = consolidation_summary.get("result")
                if consolidation_summary.get("success"):
                    st.success(consolidation_summary.get("message", "批次整理已完成。"))
                    st.rerun()
                else:
                    st.error(consolidation_summary.get("message", "批次整理没有生成结果。"))
            except Exception as exc:
                st.error(f"批次整理失败：{exc}")

        consolidation_result = st.session_state.get(f"batch_consolidation_result_{selected_batch_id}", {})
        if consolidation_result:
            with st.expander("上次批次整理结果", expanded=False):
                st.markdown(consolidation_result.get("data", {}).get("report_markdown", ""))
                render_step_validation(consolidation_result)
                render_step_json_expander(
                    "批次整理结构化数据",
                    consolidation_result.get("data", {}).get("knowledge_extraction", {}),
                )

        with st.expander("高级操作", expanded=False):
            if confirmed_button(
                st,
                "删除当前批次记录",
                "确认删除当前批次记录",
                scoped_widget_key("batch_delete", project_name, selected_batch_id),
            ):
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


def render_long_reference_importer(project_name: str, source_type_options: dict, knowledge_category_options: list[str], expanded: bool = False):
    with st.expander("长篇文本导入", expanded=expanded):
        st.info("推荐顺序：选择处理方案 / 上传或粘贴文本 / 检查切分结果 / 自动处理。处理完成后，风险条目会留在“待确认知识”里。")
        with st.expander("1. 选择处理方案", expanded=True):
            st.caption("先选资料用途。第一次整理整本原作，通常直接选“同人创作地基”。系统会自动设置资料范围、可信度、自动处理方式和提取模式，之后仍可手动调整。")
            active_preset = st.session_state.get("long_reference_active_preset", "")
            if active_preset in LONG_REFERENCE_PRESET_INFO:
                active_info = LONG_REFERENCE_PRESET_INFO[active_preset]
                st.success(st.session_state.get("long_reference_preset_notice", f"当前方案：{active_info['label']}"))
                st.caption(active_info["effect"])
            else:
                st.info("当前还没有套用处理方案。第一次整理整本原作，建议选“同人创作地基（推荐）”。")
            preset_cols = st.columns(3)
            for column, preset_key in zip(preset_cols, LONG_REFERENCE_PRESET_INFO):
                preset_info = LONG_REFERENCE_PRESET_INFO[preset_key]
                with column:
                    is_active = active_preset == preset_key
                    st.markdown(f"**{preset_info['label']}{'（当前）' if is_active else ''}**")
                    st.caption(preset_info["summary"])
                    st.caption(preset_info["effect"])
                    if st.button(
                        "已应用" if is_active else preset_info["button"],
                        key=f"long_reference_preset_{preset_key}",
                        use_container_width=True,
                        type="primary" if is_active else "secondary",
                    ):
                        apply_long_reference_fanfic_preset(preset_key)
                        st.rerun()
        with st.expander("流程说明", expanded=False):
            st.markdown(
                """
1. **预览切分**：只把文本临时拆成章节/片段，方便检查切分是否合理，还不会写入资料库。
2. **保存为处理批次**：把这次切分结果保存下来。之后可以在“长篇批次”里继续导入、提取、重试或重新提取。
3. **导入资料索引**：把片段作为原文资料加入检索库。后续写作、规划、审阅可以召回原文证据，但不会生成结构化角色/设定卡。
4. **提取结构化知识**：让模型从片段中提取角色、关系、时间线、设定、文风等候选知识，结果先进入“待确认知识”，需要审核后才会成为正式知识库。
                """.strip()
            )

        st.markdown("#### 2. 上传或粘贴资料")
        long_title = st.text_input("资料标题", key="long_reference_title", placeholder="例如：某某原作正文")
        with st.expander("资料属性与切分规则（可选）", expanded=False):
            col_a, col_b = st.columns(2)
            long_scope = col_a.selectbox("资料范围", options=["canon", "reference"], format_func=label_scope, key="long_reference_scope")
            long_authority = col_b.selectbox(
                "资料可信度",
                options=["official", "curated", "community", "unknown"],
                index=0,
                format_func=label_authority,
                key="long_reference_authority",
            )
            long_source_type = col_a.selectbox(
                "资料模板",
                options=list(source_type_options.keys()),
                index=0,
                format_func=lambda key: source_type_options.get(key, label_source_type(key)),
                key="long_reference_source_type",
            )
            long_origin = col_b.text_input("来源说明/链接（可选）", key="long_reference_origin")
            max_chars = st.slider("没有章节标题时，每段最多字数", min_value=2000, max_value=12000, value=6000, step=1000, key="long_reference_max_chars")
        uploaded_file = st.file_uploader("上传 txt/md 文件", type=["txt", "md"], key="long_reference_file")
        uploaded_text = decode_uploaded_text(uploaded_file)
        if uploaded_file is not None:
            upload_signature = hashlib.sha1(uploaded_file.getvalue()).hexdigest()
            if st.session_state.get("long_reference_uploaded_signature") != upload_signature:
                st.session_state["long_reference_uploaded_signature"] = upload_signature
                st.session_state["long_reference_text"] = uploaded_text
                st.session_state.pop("long_reference_segments", None)
                st.session_state.pop("long_reference_batch_id", None)
            st.caption(f"已读取文件：{uploaded_file.name} / {len(uploaded_file.getvalue())} 字节 / 解码后 {len(uploaded_text)} 字符")
            if not uploaded_text.strip():
                st.warning("文件已上传，但没有解码出文本内容。请确认文件不是二进制格式，或尝试另存为 UTF-8/UTF-16 txt。")
        pasted_text = st.text_area(
            "或直接粘贴资料正文",
            value=st.session_state.get("long_reference_text", uploaded_text),
            height=260,
            key="long_reference_text",
        )

        # 自动切分：有文本且尚未切分时自动执行，省去手动点"预览切分"的步骤
        if pasted_text.strip() and "long_reference_segments" not in st.session_state:
            title = long_title.strip() or (uploaded_file.name.rsplit(".", 1)[0] if uploaded_file else "长篇资料")
            segments = split_long_reference_text(title, pasted_text, max_chars=max_chars)
            st.session_state["long_reference_segments"] = segments
            st.session_state.pop("long_reference_batch_id", None)
            if segments:
                st.caption(f"已自动切分为 {len(segments)} 个资料片段。如需调整切分参数，修改后点击“重新生成切分预览”。")

        if st.button("重新生成切分预览", help="修改资料或切分参数后，重新生成片段预览。已有片段将被替换。"):
            title = long_title.strip() or (uploaded_file.name.rsplit(".", 1)[0] if uploaded_file else "长篇资料")
            if not pasted_text.strip():
                st.error("没有可处理的文本内容。请上传 txt/md 文件，或把文本粘贴到输入框中。")
                return
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
        st.markdown("#### 3. 检查切分结果")
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
            "选择本次要处理的片段",
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
            fallback_title = uploaded_file.name.rsplit(".", 1)[0] if uploaded_file else "长篇资料"
            batch = create_long_reference_batch(
                project_name,
                title=long_title.strip() or fallback_title,
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

        st.markdown("#### 4. 自动处理")
        st.caption("会自动保存批次、导入资料索引、提取结构化知识，并保存低风险条目；有冲突或证据不足的条目会留在“待确认知识”。")
        quick_extract_limit = st.number_input(
            "本次最多处理片段数",
            min_value=1,
            value=min(5, max(1, len(selected_indices))),
            key="long_reference_quick_limit",
            help="不设上限，超过 50 段需要额外确认。",
        )
        quick_quick_high_ok = True
        if quick_extract_limit > 50:
            st.warning(f"处理 {quick_extract_limit} 段将产生约 {quick_extract_limit} 次 LLM 调用，预计耗时会较长。")
            quick_quick_high_ok = st.checkbox(
                "我确认要大量处理",
                key="long_reference_quick_high_confirm",
            )
        selected_count = len(selected_indices)
        planned_quick_count = min(int(quick_extract_limit), selected_count)
        st.info(
            f"本次自动处理将按当前选择顺序处理 {planned_quick_count} 个片段；"
            f"已选择 {selected_count} 个，当前资料共 {len(segments)} 个片段。"
        )
        with st.expander("自动处理选项", expanded=False):
            quick_import_to_index = st.checkbox(
                "同时导入资料索引",
                value=True,
                key="long_reference_quick_import_index",
                help="开启后，原文片段会进入检索库，后续写作可以召回原文证据。",
            )
            quick_auto_confirm = st.checkbox(
                "自动审核并保存低风险知识",
                value=True,
                key="long_reference_quick_auto_confirm",
                help="只自动确认没有冲突、证据存在、置信度尚可的条目；风险条目会留在待确认队列。",
            )
            quick_consolidate = st.checkbox(
                "提取后自动整理散知识",
                value=False,
                key="long_reference_quick_consolidate",
                help="会尝试把同一批次里的散知识合并成更稳定的角色/关系/设定条目。正式大批量处理时再开启更稳。",
            )

        with st.expander("提取参数设置", expanded=False):
            shared_expert_preset = st.selectbox(
                "专家提取预设",
                options=list(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.keys()),
                index=list(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.keys()).index("balanced"),
                format_func=lambda value: KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[value]["label"],
                key="long_reference_shared_expert_preset",
                help="预设会自动推荐提取分类和提取模式。第一次处理长篇资料建议使用“平衡总管”。",
            )
            shared_preset = KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[shared_expert_preset]
            shared_category_strategy = st.radio(
                "提取分类初始策略",
                options=["preset", "all", "none"],
                format_func=lambda value: {"preset": "按专家预设", "all": "全选分类", "none": "不预选分类"}.get(value, value),
                horizontal=True,
                key=f"long_reference_shared_category_strategy_{shared_expert_preset}",
                help="只影响当前控件的默认勾选。分类越多，覆盖越广；分类越少，输出越聚焦。",
            )
            shared_categories = st.multiselect(
                "提取分类",
                options=knowledge_category_options,
                default=default_extraction_categories(shared_category_strategy, shared_preset, knowledge_category_options),
                format_func=label_knowledge_category,
                key=f"long_reference_shared_categories_{shared_expert_preset}_{shared_category_strategy}",
                help="决定允许模型输出哪些类型的知识。没有选中的分类不会被主动提取。",
            )
            shared_extraction_mode = st.selectbox(
                "提取模式",
                options=list(KNOWLEDGE_EXTRACTION_MODE_LABELS.keys()),
                index=list(KNOWLEDGE_EXTRACTION_MODE_LABELS.keys()).index(shared_preset["mode"]) if shared_preset["mode"] in KNOWLEDGE_EXTRACTION_MODE_LABELS else 0,
                format_func=lambda value: KNOWLEDGE_EXTRACTION_MODE_LABELS.get(value, value),
                key=f"long_reference_shared_mode_{shared_expert_preset}",
                help="模式决定模型看资料时的优先级。通用更稳，深度更适合正式搭同人资料地基。",
            )
            st.info(KNOWLEDGE_EXTRACTION_MODE_HELP.get(shared_extraction_mode, "当前模式暂无说明。"))
            shared_custom_instructions = st.text_area(
                "补充提取要求（高级，可选）",
                height=90,
                key=f"long_reference_shared_custom_instructions_{shared_expert_preset}",
                placeholder="例如：优先提取主角相关关系；忽略普通战斗过程；保留所有称呼和口癖。",
            )

        if st.button("开始处理所选片段", use_container_width=True, type="primary"):
            if not selected_indices:
                st.error("请先选择片段。")
            elif not shared_categories:
                st.error("请至少选择一个提取分类。")
            elif not quick_quick_high_ok:
                st.error("处理数量超过 50 段，请先勾选确认框。")
            else:
                with st.spinner("正在保存批次、导入索引、提取并自动审核低风险知识..."):
                    progress_callback = create_batch_progress_callback("自动处理")
                    batch = get_or_create_preview_batch()
                    updated_batch, quick_summary = run_long_reference_quick_process(
                        project_name,
                        batch,
                        selected_indices[: int(quick_extract_limit)],
                        enabled_categories=shared_categories,
                        extraction_mode=shared_extraction_mode,
                        extract_limit=int(quick_extract_limit),
                        import_to_index=quick_import_to_index,
                        consolidate_after_extract=quick_consolidate,
                        auto_confirm_safe_items=quick_auto_confirm,
                        custom_instructions=shared_custom_instructions,
                        progress_callback=progress_callback,
                    )
                st.session_state["long_reference_quick_result"] = quick_summary
                st.success(
                    f"自动处理完成：导入 {quick_summary.get('imported_count', 0)} 段，"
                    f"提取 {quick_summary.get('processed_count', 0)} 段，"
                    f"新增待确认 {quick_summary.get('new_pending_count', 0)} 条，"
                    f"自动保存 {quick_summary.get('auto_confirmed_count', 0)} 条，"
                    f"保留待确认 {quick_summary.get('blocked_count', 0)} 条。"
                )
                for failure in quick_summary.get("failed_titles", [])[:5]:
                    st.warning(f"处理失败：{failure}")
                st.rerun()

        quick_result = st.session_state.get("long_reference_quick_result", {})
        if quick_result:
            with st.expander("上次自动处理结果", expanded=bool(quick_result.get("blocked_count"))):
                st.caption(
                    f"模式={KNOWLEDGE_EXTRACTION_MODE_LABELS.get(quick_result.get('extraction_mode', ''), quick_result.get('extraction_mode', ''))} / "
                    f"分类={'、'.join(label_knowledge_category(category) for category in quick_result.get('categories', []))}"
                )
                st.json({
                    "导入片段": quick_result.get("imported_count", 0),
                    "提取片段": quick_result.get("processed_count", 0),
                    "新增候选": quick_result.get("new_pending_count", 0),
                    "自动保存": quick_result.get("auto_confirmed_count", 0),
                    "自动审核记录": quick_result.get("auto_confirm", {}).get("run_id", ""),
                    "保留待确认": quick_result.get("blocked_count", 0),
                    "失败": quick_result.get("failed_titles", []),
                    "保留原因": quick_result.get("auto_confirm", {}).get("blocked_reasons", {}),
                })

        with st.expander("高级：分步处理", expanded=False):
            st.caption("适合调试或手动控制。保存批次、导入索引、提取知识可以分别执行。")
            if st.button("保存为处理批次", help="保存当前切分结果，方便之后继续处理、重试失败片段或重新提取。"):
                batch = get_or_create_preview_batch()
                st.success(f"已保存批次：{batch.get('title')} / {batch.get('summary', {}).get('segment_count', 0)} 个片段。")
                st.rerun()

            if st.button(
                "导入资料索引",
                help="把所选片段作为可检索原文资料入库。适合让后续写作引用原文，但不会自动生成角色/设定知识。",
            ):
                if not selected_indices:
                    st.error("请先选择片段。")
                else:
                    batch = get_or_create_preview_batch()
                    _, imported = import_long_reference_segments(project_name, batch, selected_indices)
                    st.success(f"已导入 {imported} 个长篇资料片段，并重建检索索引。")
                    st.rerun()

            st.markdown("##### 手动提取结构化知识")
            batch_limit = st.number_input("本次最多提取片段数", min_value=1, value=3, key="long_reference_extract_limit")
            manual_extract_high_ok = True
            if batch_limit > 50:
                st.warning(f"提取 {batch_limit} 段将产生约 {batch_limit} 次 LLM 调用，预计耗时会较长。")
                manual_extract_high_ok = st.checkbox(
                    "我确认要大量处理",
                    key="long_reference_manual_extract_high_confirm",
                )
            manual_consolidate = st.checkbox(
                "提取后自动整理散知识",
                value=False,
                key="long_reference_manual_consolidate",
                help="提取完成后自动合并重复/同名的候选知识条目。提取片段数较多时建议开启。",
            )
            if st.button("提取结构化知识", use_container_width=True):
                if not selected_indices:
                    st.error("请先选择片段。")
                elif not shared_categories:
                    st.error("请至少选择一个提取分类。")
                elif not manual_extract_high_ok:
                    st.error("处理数量超过 50 段，请先勾选确认框。")
                else:
                    with st.spinner("正在分批提取结构化知识..."):
                        progress_callback = create_batch_progress_callback("手动提取结构化知识")
                        batch = get_or_create_preview_batch()
                        _, processed, queued_total, failed_titles = extract_long_reference_segments_to_queue(
                            project_name,
                            batch,
                            selected_indices[: int(batch_limit)],
                            shared_categories,
                            extraction_mode=shared_extraction_mode,
                            custom_instructions=shared_custom_instructions,
                            progress_callback=progress_callback,
                        )
                    st.session_state["long_reference_manual_extract_result"] = {
                        "processed": processed,
                        "queued_total": queued_total,
                        "failed_titles": failed_titles,
                    }
                    if manual_consolidate and queued_total:
                        consolidation_summary = consolidate_batch_pending_items(
                            project_name,
                            batch,
                            categories=shared_categories,
                            consolidation_mode="balanced",
                            limit=max(20, min(120, queued_total)),
                        )
                        st.success(
                            f"追加整理：合并 {consolidation_summary.get('source_count', 0)} 条为 "
                            f"{consolidation_summary.get('queued_count', 0)} 条稳定知识。"
                        )
                        st.session_state["long_reference_manual_extract_result"]["consolidation"] = consolidation_summary
                    st.rerun()

            manual_result = st.session_state.get("long_reference_manual_extract_result", {})
            if manual_result:
                with st.expander("上次手动提取结果", expanded=bool(manual_result.get("failed_titles"))):
                    st.json({
                        "处理片段": manual_result.get("processed", 0),
                        "新增候选": manual_result.get("queued_total", 0),
                        "失败": manual_result.get("failed_titles", []),
                        "整理": manual_result.get("consolidation", {}),
                    })


def _render_resource_browser_detail(project_name: str, resource: dict):
    story_id = st.session_state.get("active_story_id", "default")
    if not resource:
        st.caption("请先从左侧选择一个资源。")
        return

    st.markdown(f"### {resource.get('label', '')}")
    st.caption(resource.get("path_label", ""))

    group = resource.get("group")
    if group == "run":
        st.code(resource.get("content", ""), language="json")
        delete_key = scoped_widget_key("browser_delete", project_name, story_id, resource.get("id"))
        if confirmed_button(
            st,
            "删除该运行记录",
            "确认删除该运行记录",
            delete_key,
        ):
            if _delete_browser_resource(project_name, resource, story_id=story_id):
                st.success("运行记录已删除。")
                st.session_state[_resource_browser_selection_key(project_name)] = {}
                st.rerun()
        return

    if group in {"outline_discussion", "creative_profile_discussion", "volume_discussion", "arc_discussion", "chapter_discussion", "arc_chapter_plan"}:
        if resource.get("content"):
            st.markdown(resource.get("content", ""))
        render_step_json_expander("结构化数据", resource.get("discussion_payload", {}) or resource.get("chapter_plan_payload", {}))
        delete_key = scoped_widget_key("browser_delete", project_name, story_id, resource.get("id"))
        if confirmed_button(
            st,
            "删除该工件",
            "确认删除该讨论/计划工件",
            delete_key,
        ):
            if _delete_browser_resource(project_name, resource, story_id=story_id):
                st.success("工件已删除。")
                st.session_state[_resource_browser_selection_key(project_name)] = {}
                st.rerun()
        return

    if group in {"knowledge_item", "pending_knowledge", "long_reference_batch"}:
        st.caption("该资源在浏览器中只读；编辑和批量处理请回到「资料导入」。")
        st.code(resource.get("content", ""), language="json")
        if st.button(
            "前往资料导入",
            key=scoped_widget_key("browser_goto_ingestion", project_name, story_id, resource.get("id")),
            use_container_width=True,
        ):
            navigate_to("资料导入")
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
        volume_options = [0] + [int(item.get("volume_no", 0)) for item in list_volumes(project_name, story_id=story_id)]
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
            _save_browser_resource(project_name, resource, edited_content, edited_json_text, story_id=story_id)
            st.success("资源已保存。")
            st.rerun()
        except json.JSONDecodeError as exc:
            st.error(f"结构化数据格式错误：{exc}")
        except Exception as exc:
            st.error(f"保存资源失败：{exc}")

    delete_key = scoped_widget_key("browser_delete", project_name, story_id, resource.get("id"))
    if resource.get("deletable") and confirmed_button(
        delete_col,
        "删除当前资源",
        "确认删除当前资源",
        delete_key,
    ):
        try:
            if _delete_browser_resource(project_name, resource, story_id=story_id):
                st.success("资源已删除。")
                st.session_state[_resource_browser_selection_key(project_name)] = {}
                st.rerun()
            else:
                st.warning("目标资源不存在。")
        except Exception as exc:
            st.error(f"删除资源失败：{exc}")


def render_resource_management_page(project_name: str):
    st.subheader("资源浏览器")
    story_id = st.session_state.get("active_story_id", "default")
    browser_items = _build_resource_browser_items(project_name, story_id=story_id)
    selected = _get_resource_browser_selection(project_name)
    focused_selected, focus_warning = _consume_resource_browser_focus(project_name, browser_items)
    if focused_selected:
        selected = focused_selected
    if focus_warning:
        st.info(focus_warning)

    left_col, right_col = st.columns([1, 2])

    with left_col:
        st.markdown("### 资源浏览器")
        search_value = st.text_input("搜索资源", key=f"resource_browser_search_{project_name}")
        search_lower = search_value.strip().lower()
        group_filter_key = f"resource_browser_group_filter_{project_name}"
        group_filter_options = [group_key for group_key, _ in RESOURCE_BROWSER_GROUPS]
        existing_group_filter = st.session_state.get(group_filter_key)
        if not isinstance(existing_group_filter, list) or any(group not in group_filter_options for group in existing_group_filter):
            st.session_state[group_filter_key] = group_filter_options
        browser_group_filter = st.multiselect(
            "资源类型",
            options=group_filter_options,
            format_func=lambda value: RESOURCE_BROWSER_GROUP_LABELS.get(value, value),
            key=group_filter_key,
        )
        active_group_filter = set(browser_group_filter)
        volume_filter_options = [0] + [int(item.get("volume_no", 0)) for item in list_volumes(project_name, story_id=story_id)]
        browser_volume_filter = st.selectbox(
            "按分卷过滤",
            options=volume_filter_options,
            format_func=lambda value: "全部分卷" if value == 0 else f"第 {value} 卷",
            key=f"resource_browser_volume_filter_{project_name}",
        )
        arc_filter_candidates = list_arcs(project_name, volume_no=browser_volume_filter or None, story_id=story_id)
        arc_filter_options = [0] + [int(item.get("arc_no", 0)) for item in arc_filter_candidates]
        browser_arc_filter = st.selectbox(
            "按剧情段过滤",
            options=arc_filter_options,
            format_func=lambda value: "全部剧情段" if value == 0 else f"剧情段 {value:03d}",
            key=f"resource_browser_arc_filter_{project_name}",
        )

        with st.expander("批量清理（可选）", expanded=False):
            st.caption("用于一次删除多项资源。普通浏览和编辑不需要打开这里。")
            chapter_inventory = list_chapter_inventory(project_name, story_id=story_id)
            runs = list_project_runs(project_name, story_id=story_id)
            sources = list_retrieval_sources(project_name)

            if chapter_inventory:
                chapter_numbers = [item.get("chapter_no") for item in chapter_inventory]
                bulk_chapter_selection = st.multiselect(
                    "批量章节清理",
                    options=chapter_numbers,
                    format_func=lambda value: f"第 {int(value)} 章",
                    key=f"resource_bulk_chapters_{project_name}"
                )
                if bulk_chapter_selection and confirmed_button(
                    st,
                    "清理所选章节",
                    "确认清理所选章节的细纲、正文、审阅、分析、评价和运行记录",
                    scoped_widget_key("bulk_delete_chapters", project_name, story_id),
                ):
                    results = []
                    for chapter_no in bulk_chapter_selection:
                        results.append({
                            "chapter_no": int(chapter_no),
                            "result": delete_chapter_bundle(project_name, int(chapter_no), story_id=story_id),
                        })
                    st.success(f"已批量清理章节资源：{json.dumps(results, ensure_ascii=False)}")
                    st.rerun()

            if runs:
                bulk_runs = st.multiselect(
                    "批量删除运行记录",
                    options=[run.get("run_id") for run in runs],
                    key=f"resource_bulk_runs_{project_name}"
                )
                if bulk_runs and confirmed_button(
                    st,
                    "删除所选运行记录",
                    "确认删除所选运行记录",
                    scoped_widget_key("bulk_delete_runs", project_name, story_id),
                ):
                    deleted_count = 0
                    for run_id in bulk_runs:
                        if delete_pipeline_run(project_name, str(run_id), story_id=story_id):
                            deleted_count += 1
                    st.success(f"已删除 {deleted_count} 条运行记录。")
                    st.rerun()

            if sources:
                bulk_sources = st.multiselect(
                    "批量删除外部资料",
                    options=[source.get("relative_path") for source in sources],
                    key=f"resource_bulk_sources_{project_name}"
                )
                if bulk_sources and confirmed_button(
                    st,
                    "删除所选外部资料",
                    "确认删除所选外部资料并重建索引",
                    scoped_widget_key("bulk_delete_sources", project_name),
                ):
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

        global_filter_passthrough_groups = {
            "outline",
            "outline_discussion",
            "creative_profile_discussion",
            "run",
            "analysis",
            "evaluation",
            "source",
            "review",
            "chapter_content",
            "knowledge_item",
            "pending_knowledge",
            "long_reference_batch",
        }
        visible_resource_count = 0
        visible_items = []

        for group_key, group_label in RESOURCE_BROWSER_GROUPS:
            if group_key not in active_group_filter:
                continue
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
                    if item.get("group") in global_filter_passthrough_groups:
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
                    if item.get("group") in global_filter_passthrough_groups or item.get("group") in {"volume_outline", "volume_discussion"}:
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
            visible_resource_count += len(group_items)
            visible_items.extend(group_items)
            st.markdown(f"**{group_label}**")
            for item in group_items:
                selected_flag = selected.get("id") == item.get("id")
                button_label = f"> {item.get('label')}" if selected_flag else item.get("label")
                if st.button(button_label, key=f"resource_select_{item.get('id')}", use_container_width=True):
                    _set_resource_browser_selection(project_name, item)
                    st.rerun()
        if not visible_resource_count:
            st.caption("当前筛选下没有可显示的资源。")

    with right_col:
        st.markdown("### 资源详情")
        if selected and not any(item.get("id") == selected.get("id") for item in browser_items):
            selected = {}
            st.session_state[_resource_browser_selection_key(project_name)] = {}
        visible_ids = {item.get("id") for item in visible_items}
        if selected and visible_ids and selected.get("id") not in visible_ids:
            selected = {}
            st.session_state[_resource_browser_selection_key(project_name)] = {}
        if not selected and visible_items:
            selected = visible_items[0]
            _set_resource_browser_selection(project_name, selected)
        _render_resource_browser_detail(project_name, selected)


def render_volume_outline_page(project_name: str):
    story_id = st.session_state.get("active_story_id", "default")
    st.subheader("分卷大纲")

    volume_no = st.number_input("分卷编号", min_value=1, value=1, key=scoped_widget_key("volume_outline_no", project_name, story_id))
    volume_no = int(volume_no)
    volume_scope = (project_name, story_id, volume_no)
    volume_outline_step_key = scoped_session_key("volume_outline_step", *volume_scope)
    volume_outline_text_key = scoped_session_key("volume_outline", *volume_scope)
    volume_outline_editor_key = scoped_widget_key("volume_outline_editor", *volume_scope)
    metadata = load_volume_metadata(project_name, volume_no, story_id=story_id)
    existing_outline = load_volume_outline(project_name, volume_no, story_id=story_id)
    step_result = st.session_state.get(volume_outline_step_key, {})

    title = st.text_input("分卷标题", value=metadata.get("title", ""), key=scoped_widget_key("volume_title", *volume_scope))
    summary = st.text_area("分卷摘要", value=metadata.get("summary", ""), height=120, key=scoped_widget_key("volume_summary", *volume_scope))
    status = st.selectbox(
        "分卷状态",
        options=["draft", "approved", "archived"],
        index=["draft", "approved", "archived"].index(metadata.get("status", "draft")) if metadata.get("status", "draft") in ["draft", "approved", "archived"] else 0,
        format_func=label_status,
        key=scoped_widget_key("volume_status", *volume_scope),
    )

    requirement = st.text_area("本卷要求", height=180, key=scoped_widget_key("volume_requirement", *volume_scope))
    suffix = f"{project_name}:{story_id}:{volume_no}"
    messages_key = _discussion_messages_key("volume", suffix)
    result_key = _discussion_result_key("volume", suffix)
    input_key = _discussion_input_key("volume", suffix)
    clear_input_flag_key = _discussion_input_clear_flag_key("volume", suffix)
    _consume_discussion_input_clear("volume", suffix)
    discussion_step = st.session_state.get(result_key, {})
    approved_artifact = load_volume_discussion_artifact(project_name, volume_no, story_id=story_id)

    col_action_1, col_action_2 = st.columns(2)
    if col_action_1.button("开始讨论分卷方向", key=scoped_widget_key("start_volume_discussion", *volume_scope)):
        try:
            result = discuss_volume(project_name, volume_no, title, summary, requirement, story_id=story_id)
            st.session_state[result_key] = result
            st.session_state[messages_key] = []
            assistant_message = result.get("data", {}).get("discussion", {}).get("current_understanding", "") or "我先整理了本卷的定位、可选结构和待确认问题，我们可以继续细化。"
            _append_discussion_message(messages_key, "assistant", assistant_message)
            st.rerun()
        except Exception as exc:
            st.error(f"讨论失败：{exc}")

    if col_action_2.button("重置分卷讨论", key=scoped_widget_key("reset_volume_discussion", *volume_scope)):
        st.session_state[result_key] = {}
        st.session_state[messages_key] = []
        st.session_state[clear_input_flag_key] = True
        st.rerun()

    summary_col, chat_col = st.columns([1, 1])
    with summary_col:
        st.markdown("### 当前讨论结论")
        _render_discussion_summary(discussion_step, "开始讨论后，这里会持续显示当前分卷方向的结论。")
        render_step_retrieval(discussion_step, "本次分卷讨论参考的检索上下文")
        approve_col, clear_col = st.columns(2)
        if approve_col.button("批准当前讨论", key=scoped_widget_key("approve_volume_discussion", *volume_scope)):
            try:
                result = approve_volume_discussion(project_name, volume_no, discussion_step, story_id=story_id)
                st.success(f"已保存分卷讨论工件：{result.get('saved_path', '')}")
                st.rerun()
            except Exception as exc:
                st.error(f"批准失败：{exc}")
        if clear_col.button("清除已批准版本", key=scoped_widget_key("clear_volume_discussion", *volume_scope)):
            if clear_volume_discussion_approval(project_name, volume_no, story_id=story_id):
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
        if st.button("发送分卷讨论消息", key=scoped_widget_key("send_volume_discussion", *volume_scope)):
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
                        story_id=story_id,
                    )
                    st.session_state[result_key] = result
                    assistant_message = result.get("data", {}).get("assistant_message", "") or "我已经根据你的补充更新了本卷讨论结论。"
                    _append_discussion_message(messages_key, "assistant", assistant_message)
                    st.session_state[clear_input_flag_key] = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"继续讨论失败：{exc}")

    if st.button("生成分卷大纲", key=scoped_widget_key("generate_volume_outline", *volume_scope)):
        try:
            result = generate_volume_outline(project_name, volume_no, title, summary, requirement, status=status, story_id=story_id)
            outline_value = result.get("data", {}).get("volume_outline", "")
            st.session_state[volume_outline_step_key] = result
            st.session_state[volume_outline_text_key] = outline_value
            st.session_state[volume_outline_editor_key] = outline_value
            st.rerun()
        except Exception as exc:
            st.error(f"生成分卷大纲失败：{exc}")

    outline_text = st.text_area(
        "分卷大纲内容",
        value=st.session_state.get(volume_outline_text_key, existing_outline),
        height=500,
        key=volume_outline_editor_key,
    )

    col1, col2 = st.columns(2)
    if col1.button("保存分卷大纲", key=scoped_widget_key("save_volume", *volume_scope)):
        save_volume_outline(project_name, volume_no, outline_text, story_id=story_id)
        save_volume_metadata(project_name, volume_no, {"title": title, "summary": summary, "status": status}, story_id=story_id)
        st.success(f"第 {volume_no} 卷大纲已保存")
        st.rerun()
    if confirmed_button(
        col2,
        "删除分卷",
        f"确认删除第 {volume_no} 卷",
        scoped_widget_key("delete_volume", project_name, story_id, volume_no),
    ):
        if delete_volume(project_name, volume_no, story_id=story_id):
            st.success(f"第 {volume_no} 卷已删除")
            st.rerun()
        else:
            st.warning("目标分卷不存在。")

    volumes = list_volumes(project_name, story_id=story_id)
    if volumes:
        st.markdown("### 现有分卷")
        for item in volumes:
            approval_label = "已有批准讨论" if item.get("has_approved_discussion") else "暂无批准讨论"
            st.caption(f"第 {int(item.get('volume_no', 0))} 卷 / {item.get('title', '') or '未命名'} / 状态={label_status(item.get('status', 'draft'))} / {approval_label}")

    render_step_validation(step_result)
    render_step_retrieval(step_result, "本次分卷大纲生成使用的检索上下文", get_retrieval_trace(f"volume_outline:{project_name}:{volume_no}"))


def render_arc_outline_page(project_name: str):
    story_id = st.session_state.get("active_story_id", "default")
    st.subheader("剧情段大纲")

    arc_no = st.number_input("剧情段编号", min_value=1, value=1, key=scoped_widget_key("arc_outline_no", project_name, story_id))
    arc_no = int(arc_no)
    arc_scope = (project_name, story_id, arc_no)
    arc_outline_step_key = scoped_session_key("arc_outline_step", *arc_scope)
    arc_outline_text_key = scoped_session_key("arc_outline", *arc_scope)
    arc_outline_editor_key = scoped_widget_key("arc_outline_editor", *arc_scope)
    arc_chapter_plan_step_key = scoped_session_key("arc_chapter_plan_step", *arc_scope)
    metadata = load_arc_metadata(project_name, arc_no, story_id=story_id)
    existing_outline = load_arc_outline(project_name, arc_no, story_id=story_id)
    step_result = st.session_state.get(arc_outline_step_key, {})

    volume_options = [0] + [int(item.get("volume_no", 0)) for item in list_volumes(project_name, story_id=story_id)]
    current_volume = int(metadata.get("volume_no") or 0)
    volume_no = st.selectbox(
        "所属分卷",
        options=volume_options,
        index=volume_options.index(current_volume) if current_volume in volume_options else 0,
        format_func=lambda value: "未指定分卷" if value == 0 else f"第 {value} 卷",
        key=scoped_widget_key("arc_volume", *arc_scope),
    )
    title = st.text_input("剧情段标题", value=metadata.get("title", ""), key=scoped_widget_key("arc_title", *arc_scope))
    summary = st.text_area("剧情段摘要", value=metadata.get("summary", ""), height=120, key=scoped_widget_key("arc_summary", *arc_scope))
    status = st.selectbox(
        "剧情段状态",
        options=["draft", "approved", "archived"],
        index=["draft", "approved", "archived"].index(metadata.get("status", "draft")) if metadata.get("status", "draft") in ["draft", "approved", "archived"] else 0,
        format_func=label_status,
        key=scoped_widget_key("arc_status", *arc_scope),
    )
    estimated_chapter_count = st.number_input("预计章节数", min_value=0, value=int(metadata.get("estimated_chapter_count") or 0), key=scoped_widget_key("arc_estimated_chapters", *arc_scope))
    target_word_count_range = st.text_input("目标总字数范围", value=metadata.get("target_word_count_range", ""), key=scoped_widget_key("arc_word_range", *arc_scope))
    requirement = st.text_area("本剧情段要求", height=180, key=scoped_widget_key("arc_requirement", *arc_scope))

    suffix = f"{project_name}:{story_id}:{arc_no}"
    messages_key = _discussion_messages_key("arc", suffix)
    result_key = _discussion_result_key("arc", suffix)
    input_key = _discussion_input_key("arc", suffix)
    clear_input_flag_key = _discussion_input_clear_flag_key("arc", suffix)
    _consume_discussion_input_clear("arc", suffix)
    discussion_step = st.session_state.get(result_key, {})
    approved_artifact = load_arc_discussion_artifact(project_name, arc_no, story_id=story_id)

    col_action_1, col_action_2 = st.columns(2)
    if col_action_1.button("开始讨论剧情段方向", key=scoped_widget_key("start_arc_discussion", *arc_scope)):
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
                story_id=story_id,
            )
            st.session_state[result_key] = result
            st.session_state[messages_key] = []
            assistant_message = result.get("data", {}).get("discussion", {}).get("current_understanding", "") or "我先整理了这个剧情段的目标、可选推进结构和待确认问题，我们可以继续细化。"
            _append_discussion_message(messages_key, "assistant", assistant_message)
            st.rerun()
        except Exception as exc:
            st.error(f"讨论失败：{exc}")

    if col_action_2.button("重置剧情段讨论", key=scoped_widget_key("reset_arc_discussion", *arc_scope)):
        st.session_state[result_key] = {}
        st.session_state[messages_key] = []
        st.session_state[clear_input_flag_key] = True
        st.rerun()

    summary_col, chat_col = st.columns([1, 1])
    with summary_col:
        st.markdown("### 当前讨论结论")
        _render_discussion_summary(discussion_step, "开始讨论后，这里会持续显示当前剧情段方向的结论。")
        render_step_retrieval(discussion_step, "本次剧情段讨论参考的检索上下文")
        approve_col, clear_col = st.columns(2)
        if approve_col.button("批准当前讨论", key=scoped_widget_key("approve_arc_discussion", *arc_scope)):
            try:
                result = approve_arc_discussion(project_name, arc_no, discussion_step, story_id=story_id)
                st.success(f"已保存剧情段讨论工件：{result.get('saved_path', '')}")
                st.rerun()
            except Exception as exc:
                st.error(f"批准失败：{exc}")
        if clear_col.button("清除已批准版本", key=scoped_widget_key("clear_arc_discussion", *arc_scope)):
            if clear_arc_discussion_approval(project_name, arc_no, story_id=story_id):
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
        if st.button("发送剧情段讨论消息", key=scoped_widget_key("send_arc_discussion", *arc_scope)):
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
                        story_id=story_id,
                    )
                    st.session_state[result_key] = result
                    assistant_message = result.get("data", {}).get("assistant_message", "") or "我已经根据你的补充更新了剧情段讨论结论。"
                    _append_discussion_message(messages_key, "assistant", assistant_message)
                    st.session_state[clear_input_flag_key] = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"继续讨论失败：{exc}")

    if st.button("生成剧情段大纲", key=scoped_widget_key("generate_arc_outline", *arc_scope)):
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
                story_id=story_id,
            )
            outline_value = result.get("data", {}).get("arc_outline", "")
            st.session_state[arc_outline_step_key] = result
            st.session_state[arc_outline_text_key] = outline_value
            st.session_state[arc_outline_editor_key] = outline_value
            st.rerun()
        except Exception as exc:
            st.error(f"生成剧情段大纲失败：{exc}")

    outline_text = st.text_area(
        "剧情段大纲内容",
        value=st.session_state.get(arc_outline_text_key, existing_outline),
        height=500,
        key=arc_outline_editor_key,
    )

    col1, col2 = st.columns(2)
    if col1.button("保存剧情段大纲", key=scoped_widget_key("save_arc", *arc_scope)):
        save_arc_outline(project_name, arc_no, outline_text, story_id=story_id)
        save_arc_metadata(project_name, arc_no, {
            "volume_no": volume_no or None,
            "title": title,
            "summary": summary,
            "status": status,
            "estimated_chapter_count": estimated_chapter_count or None,
            "target_word_count_range": target_word_count_range,
        }, story_id=story_id)
        st.success(f"剧情段 {arc_no:03d} 已保存")
        st.rerun()
    if confirmed_button(
        col2,
        "删除剧情段",
        f"确认删除剧情段 {arc_no:03d}",
        scoped_widget_key("delete_arc", *arc_scope),
    ):
        if delete_arc(project_name, arc_no, story_id=story_id):
            st.success(f"剧情段 {arc_no:03d} 已删除")
            st.rerun()
        else:
            st.warning("目标剧情段不存在。")

    arcs = list_arcs(project_name, story_id=story_id)
    if arcs:
        st.markdown("### 现有剧情段")
        for item in arcs:
            volume_label = f" / 第 {int(item.get('volume_no'))} 卷" if item.get("volume_no") else ""
            status_label = label_status(item.get("status", "draft"))
            approval_label = "已有批准讨论" if item.get("has_approved_discussion") else "暂无批准讨论"
            st.caption(f"剧情段 {int(item.get('arc_no', 0)):03d}{volume_label} / {item.get('title', '') or '未命名'} / 状态={status_label} / {approval_label}")

    chapter_inventory = list_chapter_inventory(project_name, story_id=story_id)
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
    saved_plan = load_arc_chapter_plan(project_name, arc_no, story_id=story_id)
    plan_col1, plan_col2 = st.columns(2)
    start_chapter_no = plan_col1.number_input(
        "起始章节编号",
        min_value=1,
        value=min([int(item.get("chapter_no", 1)) for item in linked_chapters], default=1),
        key=scoped_widget_key("arc_plan_start", *arc_scope),
    )
    default_plan_count = int(metadata.get("estimated_chapter_count") or 5)
    plan_chapter_count = plan_col2.number_input(
        "计划章节数",
        min_value=1,
        value=max(default_plan_count, 1),
        key=scoped_widget_key("arc_plan_count", *arc_scope),
    )
    plan_requirement = st.text_area("章节分配补充要求", height=120, key=scoped_widget_key("arc_plan_requirement", *arc_scope))
    plan_step = st.session_state.get(arc_chapter_plan_step_key, {})
    if st.button("生成剧情段章节分配计划", key=scoped_widget_key("generate_arc_chapter_plan", *arc_scope)):
        try:
            result = generate_arc_chapter_plan(
                project_name,
                arc_no,
                int(start_chapter_no),
                int(plan_chapter_count),
                plan_requirement,
                story_id=story_id,
            )
            st.session_state[arc_chapter_plan_step_key] = result
            st.success("章节分配计划已生成并保存。")
            st.rerun()
        except Exception as exc:
            st.error(f"生成章节分配计划失败：{exc}")
    latest_plan = st.session_state.get(arc_chapter_plan_step_key, {}).get("data", {}).get("report_markdown", "") or saved_plan.get("report_markdown", "")
    if latest_plan:
        with st.expander("当前剧情段章节分配计划", expanded=False):
            st.markdown(latest_plan)
            render_step_json_expander("章节分配结构化数据", saved_plan.get("plan", {}))
    render_step_validation(plan_step)
    render_step_retrieval(plan_step, "本次章节分配使用的检索上下文", get_retrieval_trace(f"arc_chapter_plan:{project_name}:{arc_no}"))

    render_step_validation(step_result)
    render_step_retrieval(step_result, "本次剧情段大纲生成使用的检索上下文", get_retrieval_trace(f"arc_outline:{project_name}:{arc_no}"))


def run_comprehensive_chapter_evaluation(project_name: str, chapter_no: int, chapter_text: str, story_id: str = "default") -> dict:
    return evaluate_chapter_comprehensive(project_name, chapter_no, chapter_text, story_id=story_id)


def render_evaluation_page(project_name: str):
    story_id = st.session_state.get("active_story_id", "default")
    st.subheader("章节评价")
    st.caption("综合评价会一次性给出：通过/需改/阻塞结论、质量评分、一致性诊断和优先修改项。旧的审阅/专项分析能力仍保留给流水线和历史兼容。")

    chapter_no = st.number_input("章节编号", min_value=1, value=1, key=scoped_widget_key("evaluation_chapter_no", project_name, story_id))
    chapter_no = int(chapter_no)
    evaluation_scope = (project_name, story_id, chapter_no)
    existing_chapter = load_chapter(project_name, chapter_no, story_id=story_id)
    chapter_text = st.text_area(
        "待评估正文",
        value=existing_chapter,
        height=420,
        key=scoped_widget_key("evaluation_chapter_text", *evaluation_scope),
    )
    step_key = scoped_session_key("evaluation_step", *evaluation_scope)
    report_key = scoped_session_key("evaluation_report", *evaluation_scope)
    existing_report = load_evaluation_report(project_name, chapter_no, story_id=story_id)
    existing_json = load_evaluation_json(project_name, chapter_no, story_id=story_id) or {}

    if st.button("生成综合章节评价", key=scoped_widget_key("generate_evaluation", *evaluation_scope)):
        try:
            with st.spinner("正在生成章节综合评价..."):
                result = run_comprehensive_chapter_evaluation(project_name, chapter_no, chapter_text, story_id=story_id)
            report = result.get("data", {}).get("report_markdown", "")
            st.session_state[step_key] = result
            st.session_state[report_key] = report
            st.rerun()
        except Exception as exc:
            st.error(f"章节评价失败：{exc}")

    report_text = st.text_area(
        "评价报告",
        value=st.session_state.get(report_key, existing_report),
        height=460,
        key=scoped_widget_key("evaluation_report_text", *evaluation_scope),
    )
    if report_text:
        st.markdown(report_text)

    evaluation_step = st.session_state.get(step_key, {})
    evaluation_payload = evaluation_step.get("data", {}).get("evaluation") or existing_json
    if evaluation_payload:
        cols = st.columns(5)
        cols[0].metric("状态", label_status(evaluation_payload.get("status", "-")))
        cols[1].metric("总分", evaluation_payload.get("overall_score", 0))
        cols[2].metric("剧情推进", evaluation_payload.get("plot_progression_score", 0))
        cols[3].metric("角色一致性", evaluation_payload.get("character_consistency_score", 0))
        cols[4].metric("文字完成度", evaluation_payload.get("prose_quality_score", 0))
        render_step_json_expander("评价结构化数据", evaluation_payload)
    render_step_validation(evaluation_step)
    render_step_retrieval(
        evaluation_step,
        "本次评价使用的检索上下文",
        get_retrieval_trace(f"evaluation:comprehensive:{project_name}:{chapter_no}") or get_retrieval_trace(f"evaluation:chapter:{project_name}:{chapter_no}")
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
                    expanded_terms = hit.get("expanded_terms", [])
                    if expanded_terms:
                        st.caption(f"查询扩展：{', '.join(expanded_terms[:12])}")
                    match_reasons = hit.get("match_reasons", [])
                    if match_reasons:
                        st.caption("召回原因：" + "；".join(match_reasons[:5]))
                    score_breakdown = hit.get("score_breakdown", {})
                    if score_breakdown:
                        breakdown_text = " / ".join(f"{key}={value:.2f}" for key, value in score_breakdown.items())
                        st.caption(f"分数拆解：{breakdown_text}")
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


def render_retrieval_eval_workbench(project_name: str, manifest):
    cases = load_retrieval_eval_cases(project_name)
    runs = list(reversed(load_retrieval_eval_runs(project_name)))
    feedback_items = load_retrieval_feedback(project_name)
    source_type_candidates = sorted({chunk.source_type for chunk in manifest.chunks}) if manifest else []
    with st.expander("RAG 评测与反馈", expanded=False):
        st.caption("用固定测试问题评估召回是否命中预期资料；检索反馈会影响后续排序，适合持续调教项目资料库。")
        metric_cols = st.columns(4)
        active_cases = [case for case in cases if str(case.get("status") or "active") == "active"]
        metric_cols[0].metric("评测用例", len(cases))
        metric_cols[1].metric("启用用例", len(active_cases))
        metric_cols[2].metric("评测运行", len(runs))
        metric_cols[3].metric("反馈记录", len(feedback_items))

        with st.expander("新增 / 更新评测用例", expanded=False):
            edit_options = ["__new__"] + [str(case.get("case_id") or "") for case in cases]
            edit_case_id = st.selectbox(
                "编辑目标",
                options=edit_options,
                format_func=lambda value: "新建用例" if value == "__new__" else next((case.get("name", value) for case in cases if case.get("case_id") == value), value),
                key="rag_eval_edit_case_id",
            )
            current_case = next((case for case in cases if case.get("case_id") == edit_case_id), {}) if edit_case_id != "__new__" else {}
            case_name = st.text_input("用例名称", value=current_case.get("name", ""), key=f"rag_eval_case_name_{edit_case_id}")
            case_query = st.text_area("测试查询", value=current_case.get("query", ""), height=90, key=f"rag_eval_case_query_{edit_case_id}")
            expected_terms_text = st.text_area(
                "期望命中词（逗号或换行分隔）",
                value="\n".join(current_case.get("expected_terms", [])),
                height=80,
                key=f"rag_eval_expected_terms_{edit_case_id}",
            )
            expected_chunk_ids_text = st.text_area(
                "期望片段 ID（可选，逗号或换行分隔）",
                value="\n".join(current_case.get("expected_chunk_ids", [])),
                height=70,
                key=f"rag_eval_expected_chunks_{edit_case_id}",
            )
            eval_col_a, eval_col_b, eval_col_c = st.columns(3)
            expected_source_types = eval_col_a.multiselect(
                "期望来源类型（可选）",
                options=source_type_candidates,
                default=[item for item in current_case.get("expected_source_types", []) if item in source_type_candidates],
                format_func=label_source_type,
                key=f"rag_eval_expected_source_types_{edit_case_id}",
            )
            profile_options = [""] + list(RETRIEVAL_TASK_PROFILES.keys())
            eval_profile = eval_col_b.selectbox(
                "任务策略",
                options=profile_options,
                index=profile_options.index(current_case.get("retrieval_profile", "")) if current_case.get("retrieval_profile", "") in profile_options else 0,
                format_func=retrieval_profile_label,
                key=f"rag_eval_profile_{edit_case_id}",
            )
            eval_mode = eval_col_c.selectbox(
                "检索模式",
                options=["hybrid", "lexical", "semantic"],
                index=["hybrid", "lexical", "semantic"].index(current_case.get("retrieval_mode", "hybrid")) if current_case.get("retrieval_mode", "hybrid") in {"hybrid", "lexical", "semantic"} else 0,
                format_func=label_retrieval_mode,
                key=f"rag_eval_mode_{edit_case_id}",
            )
            scope_values = st.multiselect(
                "范围过滤",
                options=["project", "canon", "reference"],
                default=current_case.get("allowed_scopes", []) or ["project", "canon", "reference"],
                format_func=label_scope,
                key=f"rag_eval_scopes_{edit_case_id}",
            )
            source_type_values = st.multiselect(
                "来源类型过滤（可选）",
                options=source_type_candidates,
                default=[item for item in current_case.get("allowed_source_types", []) if item in source_type_candidates],
                format_func=label_source_type,
                key=f"rag_eval_allowed_source_types_{edit_case_id}",
            )
            config_col_a, config_col_b, config_col_c = st.columns(3)
            eval_top_k = config_col_a.number_input("返回条数", min_value=1, max_value=20, value=int(current_case.get("top_k", 6) or 6), key=f"rag_eval_top_k_{edit_case_id}")
            eval_min_matches = config_col_b.number_input("最少命中预期数", min_value=1, max_value=20, value=int(current_case.get("min_expected_matches", 1) or 1), key=f"rag_eval_min_matches_{edit_case_id}")
            eval_status = config_col_c.selectbox(
                "状态",
                options=["active", "disabled"],
                index=0 if current_case.get("status", "active") != "disabled" else 1,
                format_func=lambda value: "启用" if value == "active" else "停用",
                key=f"rag_eval_status_{edit_case_id}",
            )
            eval_notes = st.text_area("备注", value=current_case.get("notes", ""), height=70, key=f"rag_eval_notes_{edit_case_id}")
            if st.button("保存评测用例", key=f"save_rag_eval_case_{edit_case_id}", use_container_width=True):
                try:
                    saved = upsert_retrieval_eval_case(project_name, {
                        "case_id": "" if edit_case_id == "__new__" else edit_case_id,
                        "name": case_name,
                        "query": case_query,
                        "expected_terms": parse_multiline_or_comma_values(expected_terms_text),
                        "expected_chunk_ids": parse_multiline_or_comma_values(expected_chunk_ids_text),
                        "expected_source_types": expected_source_types,
                        "allowed_scopes": scope_values,
                        "allowed_source_types": source_type_values,
                        "retrieval_profile": eval_profile,
                        "retrieval_mode": eval_mode,
                        "top_k": int(eval_top_k),
                        "min_expected_matches": int(eval_min_matches),
                        "status": eval_status,
                        "notes": eval_notes,
                    })
                    st.success(f"已保存评测用例：{saved.get('name')}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"保存失败：{exc}")

        if cases:
            rows = [
                {
                    "名称": case.get("name", ""),
                    "查询": case.get("query", "")[:80],
                    "期望词": "、".join(case.get("expected_terms", [])[:5]),
                    "期望来源": "、".join(label_source_type(item) for item in case.get("expected_source_types", [])[:5]),
                    "策略": retrieval_profile_label(case.get("retrieval_profile", "")),
                    "状态": "启用" if case.get("status", "active") == "active" else "停用",
                }
                for case in cases
            ]
            st.dataframe(rows, use_container_width=True, hide_index=True)
            action_col_a, action_col_b, action_col_c = st.columns(3)
            selected_case_id = action_col_a.selectbox(
                "选择运行/删除用例",
                options=[str(case.get("case_id") or "") for case in cases],
                format_func=lambda value: next((case.get("name", value) for case in cases if case.get("case_id") == value), value),
                key="rag_eval_selected_case",
            )
            if action_col_b.button("运行所选用例", key="run_selected_rag_eval", use_container_width=True):
                selected_case = next((case for case in cases if case.get("case_id") == selected_case_id), None)
                if selected_case:
                    run = run_retrieval_eval_cases(project_name, [selected_case], note="手动运行单个评测用例")
                    st.session_state["rag_eval_last_run"] = run
                    st.success(f"评测完成：通过 {run.get('passed_count', 0)} / {run.get('case_count', 0)}")
            if confirmed_button(
                action_col_c,
                "删除所选用例",
                "确认删除所选用例",
                scoped_widget_key("delete_selected_rag_eval", project_name),
            ):
                if delete_retrieval_eval_case(project_name, selected_case_id):
                    st.success("已删除评测用例。")
                    st.rerun()
            if st.button("运行全部启用评测用例", key="run_all_rag_eval", use_container_width=True):
                run = run_retrieval_eval_cases(project_name, cases, note="手动运行全部启用评测用例")
                st.session_state["rag_eval_last_run"] = run
                st.success(f"评测完成：通过 {run.get('passed_count', 0)} / {run.get('case_count', 0)}，通过率 {run.get('pass_rate', 0):.0%}")

        last_run = st.session_state.get("rag_eval_last_run") or (runs[0] if runs else {})
        if last_run:
            with st.expander("最近一次评测结果", expanded=True):
                st.caption(
                    f"处理记录 ID={last_run.get('run_id', '')} / 通过 {last_run.get('passed_count', 0)} / "
                    f"总数 {last_run.get('case_count', 0)} / 通过率 {last_run.get('pass_rate', 0):.0%}"
                )
                result_rows = []
                for result in last_run.get("results", []):
                    top_hit = result.get("top_hit", {}).get("chunk", {}) if isinstance(result.get("top_hit", {}), dict) else {}
                    result_rows.append({
                        "结果": "通过" if result.get("passed") else "未通过",
                        "用例": result.get("name", ""),
                        "命中": f"{result.get('matched_count', 0)} / {result.get('expectation_count', 0)}",
                        "Top1": f"{label_source_type(top_hit.get('source_type', ''))} / {top_hit.get('title', '')}" if top_hit else "-",
                        "错误": result.get("error", ""),
                    })
                if result_rows:
                    st.dataframe(result_rows, use_container_width=True, hide_index=True)
                render_step_json_expander("评测运行原始数据", last_run)

        if feedback_items:
            with st.expander("最近检索反馈", expanded=False):
                st.dataframe(
                    [
                        {
                            "时间": item.get("created_at", "")[:19],
                            "反馈": item.get("rating", ""),
                            "查询": item.get("query", "")[:50],
                            "来源": label_source_type(item.get("source_type", "")),
                            "标题": item.get("title", ""),
                            "备注": item.get("note", ""),
                        }
                        for item in reversed(feedback_items[-50:])
                    ],
                    use_container_width=True,
                    hide_index=True,
                )


def render_retrieval_feedback_controls(project_name: str, current_hits: list[dict], query: str):
    if not current_hits:
        return
    with st.expander("记录本次检索反馈", expanded=False):
        st.caption("反馈会保存到项目 RAG 资产中；后续检索会对有用/优先片段加权，对无用/错误片段降权。")
        hit_options = [
            str(hit.get("chunk", {}).get("chunk_id") or "")
            for hit in current_hits
            if hit.get("chunk", {}).get("chunk_id")
        ]
        selected_chunk_id = st.selectbox(
            "选择片段",
            options=hit_options,
            format_func=lambda value: next(
                (
                    f"{label_source_type(hit.get('chunk', {}).get('source_type', ''))} / "
                    f"{hit.get('chunk', {}).get('title', '') or value} / score={hit.get('score', 0):.2f}"
                    for hit in current_hits
                    if hit.get("chunk", {}).get("chunk_id") == value
                ),
                value,
            ),
            key="retrieval_feedback_chunk",
        )
        rating = st.radio(
            "反馈类型",
            options=["helpful", "priority", "irrelevant", "wrong"],
            horizontal=True,
            format_func=lambda value: {
                "helpful": "有用",
                "priority": "应优先",
                "irrelevant": "无关",
                "wrong": "错误",
            }.get(value, value),
            key="retrieval_feedback_rating",
        )
        note = st.text_area("反馈备注（可选）", height=70, key="retrieval_feedback_note")
        if st.button("保存检索反馈", key="save_retrieval_feedback", use_container_width=True):
            selected_hit = next((hit for hit in current_hits if hit.get("chunk", {}).get("chunk_id") == selected_chunk_id), {})
            chunk = selected_hit.get("chunk", {})
            try:
                saved = append_retrieval_feedback(project_name, {
                    "query": query,
                    "rating": rating,
                    "note": note,
                    "chunk_id": chunk.get("chunk_id", ""),
                    "document_id": chunk.get("document_id", ""),
                    "source_type": chunk.get("source_type", ""),
                    "scope": chunk.get("scope", ""),
                    "title": chunk.get("title", ""),
                    "path": chunk.get("path", ""),
                })
                st.success(f"已保存反馈：{saved.get('rating')} / {saved.get('title') or saved.get('chunk_id')}")
                st.rerun()
            except Exception as exc:
                st.error(f"保存反馈失败：{exc}")


def render_retrieval_page(project_name: str, mode: str = "center"):
    if mode == "ingestion":
        st.subheader("资料导入")
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

    if mode == "ingestion":
        source_dir = retrieval_sources_path(project_name)
        pending_count = len(load_pending_knowledge_items(project_name))
        batch_count = len(list_long_reference_batches(project_name))
        source_count = len(list_retrieval_source_files(project_name))
        knowledge_base = load_knowledge_base(project_name)
        knowledge_count = sum(len(items) for items in knowledge_base.values())

        st.caption(f"外部资料保存目录：`{source_dir}`")
        metric_cols = st.columns(4)
        metric_cols[0].metric("待确认知识", pending_count)
        metric_cols[1].metric("长篇批次", batch_count)
        metric_cols[2].metric("已导入资料", source_count)
        metric_cols[3].metric("已确认知识", knowledge_count)

        st.markdown("### 导入向导")
        st.caption("先选资料来源，再处理当前步骤。大段文本建议走“长篇文本”，少量资料可以直接粘贴或手动建卡。")
        source_choice = st.radio(
            "资料来源",
            options=["长篇文本", "粘贴资料", "手动资料卡"],
            horizontal=True,
            key="ingestion_source_choice",
        )

        if source_choice == "长篇文本":
            render_long_reference_importer(project_name, source_type_options, knowledge_category_options, expanded=True)

        elif source_choice == "粘贴资料":
            target_choice = st.radio(
                "处理方式",
                options=["整理为检索资料", "提取为结构化知识"],
                horizontal=True,
                key="paste_ingestion_target",
            )
            if target_choice == "整理为检索资料":
                st.markdown("#### 粘贴资料 / 整理为检索资料")
                paste_title = st.text_input("资料标题", key="organized_reference_title")
                col_scope, col_auth = st.columns(2)
                paste_scope = col_scope.selectbox("资料范围", options=["canon", "reference"], format_func=label_scope, key="organized_reference_scope")
                paste_authority = col_auth.selectbox(
                    "资料可信度",
                    options=["official", "curated", "community", "unknown"],
                    index=1,
                    format_func=label_authority,
                    key="organized_reference_authority",
                )
                paste_origin = st.text_input("来源说明（可选）", key="organized_reference_origin")
                paste_text = st.text_area("资料正文", height=240, key="organized_reference_text")
                if st.button("整理并预览", use_container_width=True):
                    if not paste_text.strip():
                        st.error("请先粘贴资料正文。")
                    else:
                        try:
                            st.session_state["organized_reference_result"] = organize_reference_text(project_name, paste_title, paste_text)
                        except Exception as exc:
                            st.error(f"整理失败：{exc}")

                organized_result = st.session_state.get("organized_reference_result", {})
                organized_payload = organized_result.get("data", {}).get("organized_reference", {})
                if organized_payload:
                    st.markdown("#### 整理预览")
                    st.markdown(organized_result.get("data", {}).get("report_markdown", ""))
                    render_step_validation(organized_result)
                    render_step_json_expander("整理结果结构化数据", organized_payload)
                    if st.button("保存到检索资料库", use_container_width=True, type="primary"):
                        imported = import_organized_reference_entries(
                            project_name,
                            organized_payload,
                            scope=paste_scope,
                            authority=paste_authority,
                            origin=paste_origin,
                        )
                        st.success(f"已导入 {imported} 条资料并重建索引。")
                        st.rerun()

            else:
                st.markdown("#### 粘贴资料 / 提取为结构化知识")
                st.caption("提取结果默认先进入待确认队列；也可以自动保存低风险条目。")
                knowledge_title = st.text_input("资料标题", key="knowledge_extract_title")
                col_scope, col_auth = st.columns(2)
                knowledge_scope = col_scope.selectbox("知识范围", options=["canon", "reference", "project"], index=0, format_func=label_scope, key="knowledge_extract_scope")
                knowledge_authority = col_auth.selectbox(
                    "知识可信度",
                    options=["official", "curated", "community", "project", "unknown"],
                    index=1,
                    format_func=label_authority,
                    key="knowledge_extract_authority",
                )
                knowledge_origin = st.text_input("来源说明（可选）", key="knowledge_extract_origin")
                with st.expander("提取设置", expanded=False):
                    expert_preset = st.selectbox(
                        "专家提取预设",
                        options=list(KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.keys()),
                        format_func=lambda value: KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[value]["label"],
                        key="knowledge_extract_expert_preset",
                    )
                    preset = KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[expert_preset]
                    enabled_categories = st.multiselect(
                        "提取分类",
                        options=knowledge_category_options,
                        default=default_extraction_categories("preset", preset, knowledge_category_options),
                        format_func=label_knowledge_category,
                        key=f"knowledge_extract_categories_{expert_preset}",
                    )
                    extraction_mode = st.selectbox(
                        "提取模式",
                        options=list(KNOWLEDGE_EXTRACTION_MODE_LABELS.keys()),
                        index=list(KNOWLEDGE_EXTRACTION_MODE_LABELS.keys()).index(preset["mode"]) if preset["mode"] in KNOWLEDGE_EXTRACTION_MODE_LABELS else 0,
                        format_func=lambda value: KNOWLEDGE_EXTRACTION_MODE_LABELS.get(value, value),
                        key=f"knowledge_extract_mode_{expert_preset}",
                    )
                    st.info(KNOWLEDGE_EXTRACTION_MODE_HELP.get(extraction_mode, "当前模式暂无说明。"))
                    custom_instructions = st.text_area(
                        "补充提取要求（可选）",
                        height=90,
                        key=f"knowledge_extract_custom_instructions_{expert_preset}",
                        placeholder="例如：只保留长期复用的事实；不确定内容标为 ambiguous。",
                    )
                knowledge_text = st.text_area("资料正文", height=260, key="knowledge_extract_text")

                action_cols = st.columns(2)
                run_extract = action_cols[0].button("提取并预览", use_container_width=True)
                run_auto = action_cols[1].button("自动提取并保存低风险", use_container_width=True, type="primary")
                if run_extract or run_auto:
                    if not knowledge_text.strip():
                        st.error("请先粘贴资料正文。")
                    elif not enabled_categories:
                        st.error("请至少选择一个提取分类。")
                    else:
                        try:
                            extraction_summary = extract_pasted_reference_to_pending(
                                project_name,
                                title=knowledge_title,
                                text=knowledge_text,
                                enabled_categories=enabled_categories,
                                extraction_mode=extraction_mode,
                                custom_instructions=custom_instructions,
                                scope=knowledge_scope,
                                authority=knowledge_authority,
                                origin=knowledge_origin,
                                auto_confirm_safe_items=run_auto,
                            )
                            result = extraction_summary.get("result", {})
                            st.session_state["knowledge_extraction_result"] = result
                            if run_auto:
                                auto_summary = extraction_summary.get("auto_confirm", {})
                                st.success(
                                    f"已提取 {extraction_summary.get('item_count', 0)} 条，加入待确认 {extraction_summary.get('queued_count', 0)} 条，"
                                    f"自动保存 {len(auto_summary.get('confirmed_ids', []))} 条，"
                                    f"保留待确认 {len(auto_summary.get('blocked_ids', []))} 条。"
                                )
                                st.rerun()
                            else:
                                st.success(
                                    f"已提取 {extraction_summary.get('item_count', 0)} 条，"
                                    f"并加入待确认队列 {extraction_summary.get('queued_count', 0)} 条。"
                                )
                                st.rerun()
                        except Exception as exc:
                            st.error(f"知识提取失败：{exc}")

                extraction_result = st.session_state.get("knowledge_extraction_result", {})
                extraction_payload = extraction_result.get("data", {}).get("knowledge_extraction", {})
                if extraction_payload:
                    st.markdown("#### 最近一次提取预览")
                    st.markdown(extraction_result.get("data", {}).get("report_markdown", ""))
                    render_step_validation(extraction_result)
                    render_step_json_expander("知识提取结构化数据", extraction_payload)

        else:
            st.markdown("#### 手动资料卡")
            st.caption("适合少量已经整理好的设定卡、角色卡、事件卡。保存后直接进入检索资料库。")
            source_name = st.text_input("资料名称", key="retrieval_source_name")
            col_scope, col_auth = st.columns(2)
            source_scope = col_scope.selectbox("资料范围", options=["reference", "canon"], format_func=label_scope, key="retrieval_source_scope")
            source_authority = col_auth.selectbox(
                "资料可信度",
                options=["official", "curated", "community", "unknown"],
                index=1,
                format_func=label_authority,
                key="retrieval_source_authority",
            )
            source_origin = st.text_input("来源说明/链接（可选）", key="retrieval_source_origin")
            source_type = st.selectbox(
                "资料模板",
                options=list(source_type_options.keys()),
                format_func=lambda key: source_type_options.get(key, label_source_type(key)),
                key="retrieval_source_type",
            )
            source_title = st.text_input("显示标题（可选）", key="retrieval_source_title")
            source_summary = st.text_area("资料摘要（可选）", height=100, key="retrieval_source_summary")
            source_tags = st.text_input("标签（逗号分隔，可选）", key="retrieval_source_tags")
            source_content = st.text_area("资料正文", height=220, key="retrieval_source_content")
            if st.button("保存资料卡", use_container_width=True, type="primary"):
                if not source_name.strip() or not source_content.strip():
                    st.error("资料名称和资料正文不能为空。")
                else:
                    save_manual_retrieval_source_card(
                        project_name,
                        source_name=source_name,
                        source_type=source_type,
                        scope=source_scope,
                        title=source_title,
                        summary=source_summary,
                        content=source_content,
                        tags=[item.strip() for item in source_tags.split(",") if item.strip()],
                        authority=source_authority,
                        origin=source_origin,
                    )
                    st.success("资料卡已保存并重建索引。")
                    st.rerun()

        st.divider()
        st.markdown("### 待处理与整理")
        ledger_tab, queue_tab, record_tab, batch_tab, knowledge_tab, package_tab = st.tabs(["来源台账", "待确认知识", "处理记录", "长篇批次", "知识整理", "资料包"])
        with ledger_tab:
            render_ingestion_health_panel(project_name)
            render_source_ledger_page(project_name)
        with queue_tab:
            render_auto_review_policy_panel(project_name)
            render_pending_knowledge_queue(project_name)
        with record_tab:
            render_auto_review_runs_panel(project_name)
        with batch_tab:
            render_long_reference_batch_manager(project_name, knowledge_category_options)
        with knowledge_tab:
            render_knowledge_organizer(project_name, knowledge_category_options)
        with package_tab:
            render_source_package_report_page(project_name)
        return

    manifest = None
    if mode == "center":
        try:
            manifest = load_retrieval_index(project_name)
            st.caption(
                f"当前索引：{manifest.document_count} 份文档 / {manifest.chunk_count} 个片段 / 构建时间 {manifest.built_at} / 语义向量={'已启用' if manifest.embedding_enabled else '未启用'} / 模型={manifest.embedding_model or '-'}"
            )
        except Exception as exc:
            st.warning(f"索引读取失败：{exc}")

        col1, col2, col3 = st.columns(3)
        if col1.button("重建关键词索引"):
            with st.spinner("正在重建关键词索引..."):
                manifest = rebuild_retrieval_assets(project_name, build_vectors=False)
            st.success(
                f"关键词索引已重建：{manifest.document_count} 份文档 / {manifest.chunk_count} 个片段"
            )
            st.rerun()
        if col2.button("重建完整索引"):
            with st.spinner("正在重建索引和语义向量..."):
                manifest = rebuild_retrieval_assets(project_name, build_vectors=True)
            st.success(
                f"索引已重建：{manifest.document_count} 份文档 / {manifest.chunk_count} 个片段 / 语义向量={'已启用' if manifest.embedding_enabled else '未启用'}"
            )
            st.rerun()

        source_dir = retrieval_sources_path(project_name)
        col3.caption(f"外部资料目录：`{source_dir}`")

        with st.expander("RAG 健康检查", expanded=True):
            try:
                health = inspect_retrieval_health(project_name)
                status_label = {
                    "healthy": "健康",
                    "warning": "需要注意",
                    "error": "异常",
                }.get(health.get("status", ""), health.get("status", "未知"))
                st.caption(
                    f"状态：{status_label} / 索引构建时间：{health.get('built_at') or '-'} / "
                    f"向量构建时间：{health.get('vector_built_at') or '-'} / "
                    f"当前向量模型：{health.get('active_embedding_model') or '-'}"
                )
                metric_cols = st.columns(6)
                metric_cols[0].metric("索引文档", health.get("document_count", 0))
                metric_cols[1].metric("索引片段", health.get("chunk_count", 0))
                metric_cols[2].metric("当前片段", health.get("current_chunk_count", 0))
                metric_cols[3].metric("向量数", health.get("vector_count", 0))
                metric_cols[4].metric("缺失向量", health.get("missing_vector_count", 0))
                metric_cols[5].metric("陈旧片段", health.get("stale_chunk_count", 0))

                if health.get("embedding_enabled"):
                    st.success(f"语义向量已启用：{health.get('vector_model') or health.get('embedding_model') or '-'} / 维度 {health.get('vector_dimension') or '-'}")
                else:
                    st.warning("语义向量未启用。混合检索会自动退回关键词检索；如需语义召回，请配置可用的 Embedding 模型后重建完整索引。")

                for issue in health.get("issues", []):
                    severity = issue.get("severity")
                    message = issue.get("message", "")
                    if severity == "high":
                        st.error(message)
                    elif severity == "medium":
                        st.warning(message)
                    else:
                        st.info(message)

                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("#### 来源分布")
                    source_counts = health.get("source_type_counts", {})
                    if source_counts:
                        st.dataframe(
                            [{"来源类型": label_source_type(key), "片段数": value} for key, value in source_counts.items()],
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.caption("暂无来源片段。")
                with col_b:
                    st.markdown("#### 范围分布")
                    scope_counts = health.get("scope_counts", {})
                    if scope_counts:
                        st.dataframe(
                            [{"范围": label_scope(key), "片段数": value} for key, value in scope_counts.items()],
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.caption("暂无范围统计。")
            except Exception as exc:
                st.error(f"RAG 健康检查失败：{exc}")

        render_retrieval_eval_workbench(project_name, manifest)

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
                if confirmed_button(
                    st,
                    "删除所选资料",
                    "确认删除所选资料并重建索引",
                    scoped_widget_key("delete_selected_retrieval_source", project_name),
                ):
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
        retrieval_profile_options = [""] + list(RETRIEVAL_TASK_PROFILES.keys())
        retrieval_profile = st.selectbox(
            "任务策略",
            options=retrieval_profile_options,
            index=0,
            format_func=retrieval_profile_label,
            key="retrieval_task_profile",
            help="选择后会使用对应任务的来源偏好和默认召回数量；手动来源过滤会优先于任务策略。",
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
        worldline_options = sorted({
            str(chunk.metadata.get("worldline_id") or "").strip()
            for chunk in manifest.chunks
            if isinstance(chunk.metadata, dict) and str(chunk.metadata.get("worldline_id") or "").strip()
        }) if manifest else []
        worldline_filter = st.selectbox(
            "世界线偏好（可选）",
            options=[""] + worldline_options,
            format_func=lambda value: "不限定" if not value else value,
            key="retrieval_worldline_filter",
            help="选择后会优先召回同世界线资料；通用资料仍会保留。",
        )
        worldline_mode = st.selectbox(
            "世界线模式",
            options=["prefer", "strict"],
            format_func=lambda value: {"prefer": "偏好匹配", "strict": "严格过滤"}.get(value, value),
            key="retrieval_worldline_mode",
            help="偏好匹配会给同世界线资料加权、给其他世界线轻微降权；严格过滤会排除明确属于其他世界线的资料。",
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
                    retrieval_profile=retrieval_profile or None,
                    worldline_id=worldline_filter or None,
                    worldline_mode=worldline_mode,
                )
                st.session_state["retrieval_hits"] = [hit.model_dump() for hit in hits]
                st.session_state["retrieval_last_query"] = query
                st.session_state["retrieval_debug"] = debug_retrieve_context(
                    project_name,
                    query,
                    top_k=top_k,
                    allowed_scopes=scope_options,
                    allowed_source_types=source_type_filter or None,
                    retrieval_mode=retrieval_mode,
                    retrieval_profile=retrieval_profile or None,
                    worldline_id=worldline_filter or None,
                    worldline_mode=worldline_mode,
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
            expanded_terms = hit.get("expanded_terms", [])
            if expanded_terms:
                st.caption(f"查询扩展：{', '.join(expanded_terms[:12])}")
            match_reasons = hit.get("match_reasons", [])
            if match_reasons:
                st.caption("召回原因：" + "；".join(match_reasons[:5]))
            score_breakdown = hit.get("score_breakdown", {})
            if score_breakdown:
                breakdown_text = " / ".join(f"{key}={value:.2f}" for key, value in score_breakdown.items())
                st.caption(f"分数拆解：{breakdown_text}")
            st.caption(
                f"关键词分={hit.get('lexical_score', 0):.2f} / 语义分={hit.get('semantic_score', 0):.2f} / 来源={chunk.get('path', '-') }"
            )

        render_retrieval_feedback_controls(project_name, current_hits, st.session_state.get("retrieval_last_query", query))

        debug_payload = st.session_state.get("retrieval_debug", {})
        if debug_payload:
            with st.expander("检索调试信息", expanded=False):
                st.caption(
                    f"策略={debug_payload.get('retrieval_profile') or '通用'} / 世界线={debug_payload.get('worldline_id') or '不限定'} / 模式={debug_payload.get('worldline_mode') or 'prefer'} / 检索词={', '.join(debug_payload.get('query_terms', [])) or '-'} / 候选片段={debug_payload.get('candidate_chunk_count', 0)} / 语义向量={'已启用' if debug_payload.get('semantic_enabled', False) else '未启用'}"
                )
                expanded_terms = debug_payload.get("expanded_terms", [])
                if expanded_terms:
                    st.caption(f"查询扩展：{', '.join(expanded_terms[:20])}")
                alias_groups = debug_payload.get("matched_alias_groups", [])
                if alias_groups:
                    with st.expander("命中的别名组", expanded=False):
                        st.dataframe(
                            [
                                {
                                    "主名称": group.get("canonical_name", ""),
                                    "命中名称": "、".join(group.get("matched_names", [])),
                                    "别名": "、".join(group.get("aliases", [])),
                                    "分类": label_knowledge_category(group.get("category", "")),
                                }
                                for group in alias_groups
                            ],
                            use_container_width=True,
                            hide_index=True,
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
apply_app_style()

project_name = init_project_state()
projects = list_projects()
page = render_sidebar(project_name, projects)

if project_name:
    story_id = st.session_state.get("active_story_id", "default")
    memory = load_story_memory(project_name, story_id)
else:
    story_id = "default"
    memory = None
    st.info("当前还没有项目。可先进入“模型配置”填写服务地址与密钥，或点击侧边栏“新建项目”开始创建。")

render_app_header(project_name, page, memory)

if not project_name and page != "模型配置":
    st.stop()
elif page == "模型配置":
    render_llm_settings_page()
elif page == "项目总览":
    render_project_overview_page(project_name)
elif page == "创作配置":
    render_creative_profile_page(project_name)
elif page == "核心设定":
    render_settings_page(project_name)
elif page == "快速生成":
    render_dynamic_generation_page(project_name)
elif page == "资源浏览器":
    render_resource_management_page(project_name)
elif page == "资料导入":
    render_retrieval_page(project_name, mode="ingestion")
elif page == "检索中心":
    render_retrieval_page(project_name, mode="center")
elif page == "生成规则":
    render_rules_page(project_name)
elif page == "生成大纲":
    render_outline_page(project_name)
elif page == "分卷大纲":
    render_volume_outline_page(project_name)
elif page == "剧情段大纲":
    render_arc_outline_page(project_name)
elif page == "生成细纲":
    render_chapter_outline_page(project_name)
elif page == "正文生成":
    render_chapter_page(project_name)
elif page == "章节评价":
    render_evaluation_page(project_name)

