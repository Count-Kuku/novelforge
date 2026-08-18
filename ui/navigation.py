"""用户导航契约与旧页面迁移映射。

这里不依赖 Streamlit，所有函数都可以在离线测试中直接调用。页面 renderer
仍然保留旧名称，直到所有旧状态和调用方完成迁移。
"""
from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any


TOP_LEVEL_PAGES = ["工作台", "创作", "资料库", "设置"]
DEFAULT_PAGE = "工作台"
LOGGER = logging.getLogger("novelforge.ui.navigation")

# 旧页面分组只用于兼容测试、开发工具和规划页状态迁移，不再直接渲染到普通侧栏。
LEGACY_PAGE_GROUPS = {
    "工作台": ["项目总览", "项目资源"],
    "资料": ["资料导入", "知识库", "检索中心"],
    "规划": ["创作配置", "生成大纲", "分卷大纲", "剧情段大纲", "生成细纲"],
    "写作": ["自由创作", "正文生成", "章节审阅"],
    "配置": ["模型配置", "生成规则", "提示词选项"],
}

PAGE_LABELS = {
    "工作台": "工作台",
    "创作": "创作",
    "资料库": "资料库",
    "设置": "设置",
    "项目总览": "项目首页",
    "项目资源": "内容管理",
    "资料导入": "资料中心",
    "知识库": "知识库",
    "检索中心": "资料检索",
    "创作配置": "创作方向",
    "生成大纲": "全书大纲",
    "分卷大纲": "分卷规划",
    "剧情段大纲": "剧情段规划",
    "生成细纲": "章节细纲",
    "自由创作": "自由模式",
    "正文生成": "章节写作",
    "章节审阅": "章节审阅",
    "模型配置": "模型与费用",
    "生成规则": "生成规则",
    "提示词选项": "写作偏好",
}

PAGE_ICONS = {
    "工作台": "⌂",
    "创作": "✎",
    "资料库": "◆",
    "设置": "⚙",
    "项目总览": "⌂",
    "项目资源": "▦",
    "资料导入": "↥",
    "知识库": "◆",
    "检索中心": "⌕",
    "创作配置": "✦",
    "生成大纲": "≡",
    "分卷大纲": "▤",
    "剧情段大纲": "⌁",
    "生成细纲": "☷",
    "自由创作": "✎",
    "正文生成": "▰",
    "章节审阅": "✓",
    "模型配置": "⚙",
    "生成规则": "⚑",
    "提示词选项": "◐",
}

PAGE_DESCRIPTIONS = {
    "工作台": "查看项目状态，从推荐下一步继续创作，或按指标查找已有内容。",
    "创作": "从创作方向、小说规划到章节写作，也可以直接进入自由模式。",
    "资料库": "统一导入、搜索、编辑资料与知识，并处理待审核知识。",
    "设置": "管理模型、费用、生成规则和写作偏好；开发者模式提供诊断工具。",
    "项目总览": "查看项目状态，并从推荐操作继续创作。",
    "自由创作": "输入要求生成片段；继续交流即可续写，并能把稳定设定整理进知识库。",
    "项目资源": "集中查找和管理大纲、正文、报告与创作记录。",
    "创作配置": "用对话或表单确定作品类型、篇幅、参考原作的程度和推荐流程。",
    "知识库": "统一管理全部正式知识、优先设定和待审核知识；优先设定属于知识库。",
    "生成大纲": "确定全书主线、主题和整体结构。",
    "分卷大纲": "把全书规划拆分为各卷的目标和内容。",
    "剧情段大纲": "规划一段连续剧情，并安排它覆盖的章节。",
    "生成细纲": "规划单章的场景、冲突、推进与收尾。",
    "正文生成": "根据需求或细纲写正文，并在保存后选择快速或综合审阅。",
    "章节审阅": "统一生成和查看快速门禁或综合章节体检报告。",
    "资料导入": "导入、处理、审核并维护可复用资料与知识。",
    "检索中心": "查找匹配资料，评估检索质量并维护索引。",
    "生成规则": "管理任何生成都不能违背的长期边界、禁忌和一致性要求。",
    "提示词选项": "管理可随时开关的文风、节奏与描写偏好。",
    "模型配置": "设置模型服务、费用、预算提醒和常用方案。",
}

LEGACY_PAGE_ALIASES = {
    "设定": "知识库",
    "核心设定": "知识库",
    "优先设定": "知识库",
    "待审核设定": "待审核知识",
    "资料录入": "资料导入",
    "资源浏览器": "项目资源",
    "快速生成": "自由创作",
    "章节评价": "章节审阅",
}

# 页面名到 Hub 的稳定映射。view/subview 使用用户可见文本，便于旧状态迁移时
# 直接诊断；真正的 scoped widget key 由 app_shell 在当前项目/故事作用域中生成。
LEGACY_NAVIGATION_TARGETS: dict[str, dict[str, Any]] = {
    "项目总览": {"page": "工作台", "view": "概览"},
    "项目资源": {"page": "工作台", "view": "内容"},
    "资料导入": {"page": "资料库", "view": "导入与来源", "subview": "导入"},
    "知识库": {"page": "资料库", "view": "查找与编辑"},
    "待审核知识": {"page": "资料库", "view": "待审核", "subview": "审核队列"},
    "检索中心": {"page": "设置", "view": "开发工具", "subview": "资料检索"},
    "创作配置": {"page": "创作", "view": "创作方向"},
    "生成大纲": {"page": "创作", "view": "小说规划", "subview": "全书"},
    "分卷大纲": {"page": "创作", "view": "小说规划", "subview": "分卷"},
    "剧情段大纲": {"page": "创作", "view": "小说规划", "subview": "剧情段"},
    "生成细纲": {"page": "创作", "view": "小说规划", "subview": "章节细纲"},
    "自由创作": {"page": "创作", "view": "自由模式"},
    "正文生成": {"page": "创作", "view": "章节写作", "subview": "章节需求"},
    "章节审阅": {"page": "创作", "view": "章节写作", "subview": "保存与审阅"},
    "模型配置": {"page": "设置", "view": "模型与费用"},
    "生成规则": {"page": "设置", "view": "高级创作", "subview": "生成规则"},
    "提示词选项": {"page": "设置", "view": "高级创作", "subview": "写作偏好"},
}


def page_groups_for_story(
    *,
    project_name: str | None,
    planning_pages: list[str] | None = None,
    developer_mode: bool = False,
) -> dict[str, list[str]]:
    """返回普通侧栏的四个入口，保留旧参数以兼容开发脚本。"""

    if not project_name:
        return {"设置": ["设置"]}
    return {page: [page] for page in TOP_LEVEL_PAGES}


def canonical_legacy_page(page: str) -> str:
    raw_page = str(page or "").strip()
    return LEGACY_PAGE_ALIASES.get(raw_page, raw_page)


def build_navigation_intent(
    page: str,
    *,
    view: str | None = None,
    subview: str | None = None,
    payload: dict[str, Any] | None = None,
    developer_mode: bool = False,
) -> dict[str, Any]:
    """把新旧页面调用统一转换为一次性导航意图。"""

    canonical_page = canonical_legacy_page(page)
    if canonical_page in TOP_LEVEL_PAGES:
        target = {"page": canonical_page}
    else:
        if canonical_page not in LEGACY_NAVIGATION_TARGETS:
            LOGGER.warning("Unknown navigation target %r; falling back to project overview", page)
        target = deepcopy(LEGACY_NAVIGATION_TARGETS.get(canonical_page, LEGACY_NAVIGATION_TARGETS["项目总览"]))

    # 普通用户打开旧检索中心时回到资料库，避免通过历史状态暴露开发工具。
    if canonical_page == "检索中心" and not developer_mode:
        target = {"page": "资料库", "view": "查找与编辑"}

    if view is not None:
        target["view"] = str(view)
    if subview is not None:
        target["subview"] = str(subview)
    clean_payload = dict(payload or {})
    if clean_payload:
        target["payload"] = clean_payload
    target["version"] = 1
    return target


def is_valid_top_level_page(page: str) -> bool:
    return str(page or "") in TOP_LEVEL_PAGES
