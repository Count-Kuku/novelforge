from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest

from novelforge.services.memory import create_long_reference_batch, create_project, set_active_project_name
from tools.verify_utils import isolated_workspace
from ui.common import scoped_widget_key
from ui.navigation import ADVANCED_PAGE_GROUPS, PAGE_DESCRIPTIONS, PAGE_LABELS, PRIMARY_PAGE_GROUPS


def _verify_live_ui_reload_registry() -> str:
    """确保长运行的 Streamlit 进程不会继续使用旧页面函数。"""

    import app as app_module
    import ui.long_reference_importer as cached_importer
    import ui.retrieval_ingestion_page as cached_ingestion_page

    stale_importer = lambda *args, **kwargs: None
    stale_ingestion_page = lambda *args, **kwargs: None
    cached_importer.render_long_reference_importer = stale_importer
    cached_ingestion_page.render_retrieval_ingestion_page = stale_ingestion_page
    live_modules = app_module._reload_live_ui_modules()
    if live_modules["long_reference_importer"].render_long_reference_importer is stale_importer:
        raise AssertionError("长篇导入模块没有在脚本重跑时刷新")
    if live_modules["retrieval_ingestion"].render_retrieval_ingestion_page is stale_ingestion_page:
        raise AssertionError("资料中心模块没有在脚本重跑时刷新")
    return "资料中心及长篇导入模块支持运行中自动刷新"


def _verify_stale_navigation_cache() -> str:
    """复现 Streamlit 长运行进程中的旧导航模块缓存。"""

    import ui.app_shell as cached_app_shell  # noqa: F401
    import ui.navigation as cached_navigation

    with isolated_workspace("novelforge_stale_navigation_"):
        try:
            for name in ["PAGE_GROUP_LABELS", "PAGE_LABELS", "PAGE_ICONS"]:
                if hasattr(cached_navigation, name):
                    delattr(cached_navigation, name)
            importlib.reload(cached_app_shell)
            if not hasattr(cached_navigation, "PAGE_GROUP_LABELS"):
                raise AssertionError("app_shell 无法自行恢复旧导航缓存")

            for name in ["PAGE_GROUP_LABELS", "PAGE_LABELS", "PAGE_ICONS"]:
                if hasattr(cached_navigation, name):
                    delattr(cached_navigation, name)
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
            errors = [str(item.value) for item in app.exception]
            if errors:
                raise AssertionError(f"旧导航缓存恢复失败：{errors}")
            if not hasattr(cached_navigation, "PAGE_GROUP_LABELS"):
                raise AssertionError("导航模块未在 app_shell 之前重载")
        finally:
            importlib.reload(cached_navigation)
    return "运行中的旧导航模块会在应用壳层之前自动重载"


def _source_checks() -> list[str]:
    checks: list[str] = []
    all_pages = [page for pages in ADVANCED_PAGE_GROUPS.values() for page in pages]
    missing_labels = [page for page in all_pages if not PAGE_LABELS.get(page)]
    missing_descriptions = [page for page in all_pages if not PAGE_DESCRIPTIONS.get(page)]
    if missing_labels:
        raise AssertionError(f"导航页缺少用户可读名称：{missing_labels}")
    if missing_descriptions:
        raise AssertionError(f"导航页缺少说明：{missing_descriptions}")
    checks.append("全部导航页具有可读名称与说明")

    primary_pages = {page for pages in PRIMARY_PAGE_GROUPS.values() for page in pages}
    hidden_pages = {"项目资源", "检索中心", "章节审阅", "生成规则", "提示词选项"}
    if primary_pages & hidden_pages:
        raise AssertionError(f"普通侧栏仍显示重复或高级页面：{sorted(primary_pages & hidden_pages)}")
    checks.append("普通侧栏只保留核心创作链路")

    ingestion_source = (ROOT / "ui" / "retrieval_ingestion_page.py").read_text(encoding="utf-8")
    for label in ["概览", "导入", "处理", "管理"]:
        if label not in ingestion_source:
            raise AssertionError(f"资料中心缺少工作区：{label}")
    checks.append("资料中心聚焦导入、处理和来源管理，知识审核统一进入知识库")
    importer_source = (ROOT / "ui" / "long_reference_importer.py").read_text(encoding="utf-8")
    if 'st.expander("长篇文本导入"' in importer_source:
        raise AssertionError("长篇导入仍被包在折叠栏中")
    if 'options=["上传或粘贴", "网络资料", "手动条目"]' not in ingestion_source:
        raise AssertionError("文件上传与文本粘贴仍是两个入口")
    checks.append("文件上传与文本粘贴共用统一导入流程")

    preflight_source = (ROOT / "ui" / "llm_preflight.py").read_text(encoding="utf-8")
    summary_pos = preflight_source.index('render_action_summary(')
    detail_pos = preflight_source.index('with st.expander("查看 Token 与费用明细"')
    if summary_pos >= detail_pos:
        raise AssertionError("Token 与费用摘要没有显示在详细信息之前")
    checks.append("Token 与费用摘要始终显示在操作附近")

    legacy_width_files = []
    for path in list((ROOT / "ui").rglob("*.py")) + [ROOT / "app.py"]:
        if "use_container_width" in path.read_text(encoding="utf-8"):
            legacy_width_files.append(str(path.relative_to(ROOT)))
    if legacy_width_files:
        raise AssertionError(f"仍使用过期宽度参数：{legacy_width_files}")
    checks.append("全部界面组件使用统一的新宽度 API")
    return checks


def _render_all_pages() -> tuple[list[str], dict[str, list[str]]]:
    rendered: list[str] = []
    failures: dict[str, list[str]] = {}
    with isolated_workspace("novelforge_ui_restructure_"):
        project_name = create_project("UI 重构验收")
        set_active_project_name(project_name)
        batch = create_long_reference_batch(
            project_name,
            title="批次界面验收",
            scope="canon",
            authority="official",
            source_type="external_source",
            segments=[
                {
                    "segment_id": "ui-segment-1",
                    "index": 1,
                    "title": "第一章",
                    "content": "用于验证长篇批次管理界面。",
                    "char_count": 16,
                    "import_status": "pending",
                    "extract_status": "pending",
                    "queued_knowledge_count": 0,
                }
            ],
        )
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        for page in [page for pages in ADVANCED_PAGE_GROUPS.values() for page in pages]:
            app.session_state["project_name"] = project_name
            app.session_state["active_story_id"] = "default"
            app.session_state["pending_nav_page"] = page
            app.run(timeout=30)
            errors = [str(item.value) for item in app.exception]
            if errors:
                failures[page] = errors
            else:
                rendered.append(page)

        alternate_views = [
            ("创作配置", scoped_widget_key("creative_profile_view", project_name, "default"), "手动配置", "创作方向 / 手动配置"),
            ("生成大纲", scoped_widget_key("outline_page_view", project_name, "default"), "2 · 讨论方向", "全书大纲 / 讨论方向"),
            ("生成大纲", scoped_widget_key("outline_page_view", project_name, "default"), "3 · 生成编辑", "全书大纲 / 生成编辑"),
            ("正文生成", scoped_widget_key("chapter_page_view", project_name, "default", 1), "2 · 写作正文", "章节写作 / 正文"),
            ("正文生成", scoped_widget_key("chapter_page_view", project_name, "default", 1), "3 · 保存与审阅", "章节写作 / 审阅"),
            ("章节审阅", scoped_widget_key("evaluation_view", project_name, "default", 1), "审阅报告", "章节审阅 / 审阅报告"),
            ("生成规则", f"rules_page_view_{project_name}_default", "快速新增", "生成规则 / 快速新增"),
            ("生成规则", f"rules_page_view_{project_name}_default", "同步与冲突", "生成规则 / 同步与冲突"),
            ("检索中心", scoped_widget_key("retrieval_center_view", project_name, "default"), "质量评测", "资料检索 / 质量评测"),
            ("检索中心", scoped_widget_key("retrieval_center_view", project_name, "default"), "索引维护", "资料检索 / 索引维护"),
            ("模型配置", "llm_settings_view", "已保存方案", "模型与费用 / 已保存方案"),
            ("模型配置", "llm_settings_view", "用量与费用", "模型与费用 / 用量"),
        ]
        for page, view_key, view_value, label in alternate_views:
            app.session_state["pending_nav_page"] = page
            app.session_state[view_key] = view_value
            app.run(timeout=30)
            errors = [str(item.value) for item in app.exception]
            if errors:
                failures[label] = errors
            else:
                rendered.append(label)

        app.session_state["pending_nav_page"] = "资料导入"
        workspace_key = scoped_widget_key("ingestion_workspace_section", project_name, "default")
        task_view_key = scoped_widget_key("ingestion_task_view", project_name, "default")
        app.session_state[workspace_key] = "长篇批次"
        if task_view_key in app.session_state:
            del app.session_state[task_view_key]
        app.session_state[scoped_widget_key("long_reference_batch_select", project_name)] = batch["batch_id"]
        app.run(timeout=30)
        batch_errors = [str(item.value) for item in app.exception]
        if batch_errors:
            failures["长篇批次工作区"] = batch_errors
        elif app.session_state[workspace_key] != "处理" or app.session_state[task_view_key] != "长篇批次":
            failures["长篇批次工作区"] = ["旧工作区状态没有迁移到处理 / 长篇批次"]
        else:
            rendered.append("长篇批次工作区")

        library_view_key = scoped_widget_key("knowledge_library_view", project_name, "default")
        library_all_view_key = scoped_widget_key("knowledge_library_all_view", project_name, "default")
        app.session_state[workspace_key] = "知识库"
        app.run(timeout=30)
        management_errors = [str(item.value) for item in app.exception]
        if management_errors:
            failures["知识库工作区"] = management_errors
        elif (
            "active_page" not in app.session_state
            or app.session_state["active_page"] != "知识库"
            or library_view_key not in app.session_state
            or app.session_state[library_view_key] != "全部知识"
            or library_all_view_key not in app.session_state
            or app.session_state[library_all_view_key] != "知识条目"
        ):
            failures["知识库工作区"] = ["旧知识库状态没有迁移到知识库 / 全部知识 / 知识条目"]
        else:
            rendered.append("知识库工作区")

        ingestion_views = [
            ("处理", scoped_widget_key("ingestion_task_view", project_name, "default"), "后台任务", "资料中心 / 后台任务"),
            ("管理", scoped_widget_key("ingestion_management_view", project_name, "default"), "原文资料", "资料中心 / 原文资料"),
            ("管理", scoped_widget_key("ingestion_management_view", project_name, "default"), "健康检查", "资料中心 / 健康检查"),
            ("管理", scoped_widget_key("ingestion_management_view", project_name, "default"), "资料包", "资料中心 / 资料包"),
        ]
        for workspace, view_key, view_value, label in ingestion_views:
            app.session_state[workspace_key] = workspace
            app.session_state[view_key] = view_value
            app.run(timeout=30)
            errors = [str(item.value) for item in app.exception]
            if errors:
                failures[label] = errors
            else:
                rendered.append(label)

        knowledge_views = [
            ("全部知识", scoped_widget_key("knowledge_library_all_view", project_name, "default"), "知识条目", "知识库 / 知识条目"),
            ("全部知识", scoped_widget_key("knowledge_library_all_view", project_name, "default"), "统一搜索", "知识库 / 统一搜索"),
            ("全部知识", scoped_widget_key("knowledge_library_all_view", project_name, "default"), "创作实体", "知识库 / 创作实体"),
            ("待审核知识", scoped_widget_key("knowledge_library_review_view", project_name, "default"), "审核队列", "知识库 / 审核队列"),
            ("待审核知识", scoped_widget_key("knowledge_library_review_view", project_name, "default"), "审核策略", "知识库 / 审核策略"),
            ("待审核知识", scoped_widget_key("knowledge_library_review_view", project_name, "default"), "处理记录", "知识库 / 处理记录"),
            ("优先设定", "", "", "知识库 / 优先设定"),
        ]
        for library_view, subview_key, subview_value, label in knowledge_views:
            app.session_state["pending_nav_page"] = "知识库"
            app.session_state[library_view_key] = library_view
            if subview_key:
                app.session_state[subview_key] = subview_value
            app.run(timeout=30)
            errors = [str(item.value) for item in app.exception]
            if errors:
                failures[label] = errors
            else:
                rendered.append(label)

        app.session_state["pending_nav_page"] = "资料导入"
        app.session_state[scoped_widget_key("ingestion_workspace_section", project_name, "default")] = "导入"
        source_choice_key = scoped_widget_key("ingestion_source_choice", project_name, "default")
        app.session_state[source_choice_key] = "直接粘贴"
        app.session_state[scoped_widget_key("long_reference_text", project_name, "default")] = (
            "这是一段用于验证统一资料导入流程的短文本。"
        )
        app.run(timeout=30)
        unified_errors = [str(item.value) for item in app.exception]
        segments_key = scoped_widget_key("long_reference_segments", project_name, "default")
        try:
            segments = app.session_state[segments_key]
        except KeyError:
            segments = []
        if unified_errors:
            failures["上传或粘贴工作区"] = unified_errors
        elif app.session_state[source_choice_key] != "上传或粘贴":
            failures["上传或粘贴工作区"] = ["旧的直接粘贴入口没有迁移到统一入口"]
        elif len(segments) != 1:
            failures["上传或粘贴工作区"] = [f"短文本没有自动按单片段处理：{len(segments)}"]
        else:
            rendered.append("上传或粘贴工作区")

        selection_mode_key = scoped_widget_key("long_reference_selection_mode", project_name, "default")
        selected_segments_key = scoped_widget_key("long_reference_selected_segments", project_name, "default")
        app.session_state[selection_mode_key] = "手动选择"
        app.session_state[selected_segments_key] = [999]
        app.session_state[scoped_widget_key("long_reference_text", project_name, "default")] = (
            "替换后的短文本应清除上一份资料留下的无效片段选择。"
        )
        app.run(timeout=30)
        reset_errors = [str(item.value) for item in app.exception]
        if reset_errors:
            failures["资料切分选择重置"] = reset_errors
        elif app.session_state[selection_mode_key] != "全部片段":
            failures["资料切分选择重置"] = ["更换原文后没有重置旧的片段选择"]
        else:
            rendered.append("资料切分选择重置")
    return rendered, failures


def main() -> int:
    checks = _source_checks()
    checks.append(_verify_stale_navigation_cache())
    checks.append(_verify_live_ui_reload_registry())
    rendered, failures = _render_all_pages()
    result = {
        "ok": not failures,
        "checks": checks,
        "rendered_pages": rendered,
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
