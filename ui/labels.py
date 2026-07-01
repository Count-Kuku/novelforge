"""Chinese display labels used across the Streamlit UI."""
from __future__ import annotations

STATUS_LABELS = {
    "pass": "通过",
    "revise": "需要修改",
    "blocked": "阻塞",
    "draft": "草稿",
    "approved": "已确认",
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
    "outline_discussion": "全书讨论结论",
    "creative_profile_discussion": "创作配置讨论结论",
    "volume_outline": "分卷大纲",
    "volume_discussion": "分卷讨论结论",
    "arc_outline": "剧情段大纲",
    "arc_discussion": "剧情段讨论结论",
    "arc_chapter_plan": "剧情段章节分配",
    "chapter_outline": "章节细纲",
    "chapter_discussion": "章节讨论结论",
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
    "knowledge_characters": "知识库条目：角色",
    "knowledge_items": "知识库条目：物品与道具",
    "knowledge_abilities": "知识库条目：技能与能力",
    "knowledge_world_rules": "知识库条目：世界观规则",
    "knowledge_locations": "知识库条目：地点",
    "knowledge_organizations": "知识库条目：组织",
    "knowledge_timeline_events": "知识库条目：事件与时间线",
    "knowledge_relationships": "知识库条目：角色关系",
    "knowledge_writing_style": "知识库条目：写作风格",
    "knowledge_dialogue_style": "知识库条目：对白风格",
    "knowledge_narrative_techniques": "知识库条目：写作手法",
    "knowledge_constraints": "知识库条目：硬性约束",
    "entity_character_card": "实体卡：角色",
    "entity_setting_card": "实体卡：设定",
    "entity_alias_group": "实体别名组",
}

SCHEMA_LABELS = {
    "OrganizedReferenceResult": "资料整理结果",
    "OutlineDiscussionResult": "全书讨论结果",
    "CreativeProfileDiscussionResult": "创作配置讨论结果",
    "ChapterDiscussionResult": "章节讨论结果",
    "VolumeDiscussionResult": "分卷讨论结果",
    "ArcDiscussionResult": "剧情段讨论结果",
    "ArcChapterPlanResult": "剧情段章节分配计划",
    "MemoryUpdateResult": "章节设定提炼结果",
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
    "setting_extraction": "设定提炼",
    "completed": "完成",
    "halted": "暂停",
}

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
