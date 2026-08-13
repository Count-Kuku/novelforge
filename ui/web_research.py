"""Initial web-discovery and source-import panel."""

from __future__ import annotations

import streamlit as st

from novelforge.core.schemas import FetchedWebPage, WebSearchResult
from novelforge.services.web_research import (
    WebFetchError,
    WebSearchConfigurationError,
    WebSearchRequestError,
    available_web_search_providers,
    fetch_web_page,
    import_fetched_web_pages,
    get_imported_web_pages_retrieval_statuses,
    load_imported_web_page,
    search_web,
    set_imported_web_pages_retrieval_status,
)
from ui.common import scoped_session_key, scoped_widget_key
from ui.labels import label_authority, label_scope
from ui.web_research_tasks import render_web_research_task_manager


def _search_result_key(project_name: str, story_id: str) -> str:
    return scoped_session_key("web_research_search_result", project_name, story_id)


def _last_import_key(project_name: str, story_id: str) -> str:
    return scoped_session_key("web_research_last_import", project_name, story_id)


def _render_search_results(
    project_name: str,
    story_id: str,
    result: WebSearchResult,
) -> list[dict]:
    selected: list[dict] = []
    st.markdown(f"#### 搜索结果（{len(result.results)}）")
    if not result.results:
        st.info("当前查询没有返回可用网页。")
        return selected
    for hit in result.results:
        with st.container(border=True):
            select_col, content_col = st.columns([1, 11])
            is_selected = select_col.checkbox(
                "选择",
                value=hit.rank <= 3,
                label_visibility="collapsed",
                key=scoped_widget_key(
                    "web_research_hit_selected",
                    project_name,
                    story_id,
                    hit.result_id,
                ),
            )
            content_col.markdown(f"**{hit.rank}. {hit.title or hit.url}**")
            content_col.caption(hit.url)
            if hit.description:
                content_col.write(hit.description)
            if hit.extra_snippets:
                with content_col.expander("更多搜索摘要", expanded=False):
                    for snippet in hit.extra_snippets:
                        st.write(snippet)
            if is_selected:
                selected.append(hit.model_dump())
    return selected


def _fetch_selected_pages(selected: list[dict]) -> tuple[list[FetchedWebPage], list[str]]:
    pages: list[FetchedWebPage] = []
    errors: list[str] = []
    progress = st.progress(0.0, text="准备抓取网页...")
    total = len(selected)
    for index, hit in enumerate(selected, start=1):
        title = str(hit.get("title") or hit.get("url") or "网页")
        progress.progress((index - 1) / max(total, 1), text=f"正在抓取：{title}")
        try:
            pages.append(fetch_web_page(str(hit.get("url") or "")))
        except WebFetchError as exc:
            errors.append(f"{title}：{exc}")
        except Exception as exc:
            errors.append(f"{title}：抓取失败：{exc}")
        progress.progress(index / max(total, 1), text=f"已处理 {index}/{total} 个网页")
    progress.empty()
    return pages, errors


def _render_manual_web_research_import(project_name: str, story_id: str) -> None:
    """Render the first usable web-search-to-retrieval vertical slice."""

    state_scope = (project_name, story_id)
    st.markdown("#### 网络检索")
    st.caption(
        "搜索公开网页，检查结果后抓取正文并导入当前项目。"
        "系统优先使用当前模型的原生搜索，否则自动切换到免密通用搜索；"
        "不会登录网站或绕过付费墙。"
    )

    provider_options = available_web_search_providers()
    provider = "auto"
    st.caption(f"搜索服务：{provider_options[provider]}")
    query = st.text_input(
        "研究主题或检索词",
        placeholder="例如：原神 坎瑞亚 官方设定 时间线",
        key=scoped_widget_key("web_research_query", *state_scope),
    )
    option_cols = st.columns(3)
    result_count = option_cols[0].slider(
        "结果数量",
        min_value=3,
        max_value=20,
        value=8,
        key=scoped_widget_key("web_research_result_count", *state_scope),
    )
    language = option_cols[1].selectbox(
        "结果语言",
        options=["zh-hans", "en"],
        format_func=lambda value: "简体中文" if value == "zh-hans" else "英文",
        key=scoped_widget_key("web_research_language", *state_scope),
    )
    freshness = option_cols[2].selectbox(
        "时间范围",
        options=["", "pw", "pm", "py"],
        format_func=lambda value: {
            "": "不限",
            "pw": "最近一周",
            "pm": "最近一月",
            "py": "最近一年",
        }[value],
        key=scoped_widget_key("web_research_freshness", *state_scope),
    )
    if st.button(
        "搜索网页",
        width="stretch",
        type="primary",
        key=scoped_widget_key("web_research_search", *state_scope),
    ):
        if not query.strip():
            st.error("请先填写研究主题或检索词。")
        else:
            try:
                with st.spinner("正在检索公开网页..."):
                    search_result = search_web(
                        query,
                        provider=provider,
                        count=result_count,
                        language=language,
                        freshness=freshness,
                    )
                st.session_state[_search_result_key(*state_scope)] = search_result.model_dump()
            except (WebSearchConfigurationError, WebSearchRequestError, ValueError) as exc:
                st.error(f"网络检索失败：{exc}")
            except Exception as exc:
                st.error(f"网络检索失败：{exc}")

    raw_result = st.session_state.get(_search_result_key(*state_scope), {})
    if not raw_result:
        return
    result = WebSearchResult.model_validate(raw_result)
    selected = _render_search_results(project_name, story_id, result)

    import_cols = st.columns(2)
    scope = import_cols[0].selectbox(
        "资料范围",
        options=["reference", "canon"],
        format_func=label_scope,
        key=scoped_widget_key("web_research_scope", *state_scope),
    )
    authority = import_cols[1].selectbox(
        "默认可信度",
        options=["unknown", "community", "curated", "official"],
        format_func=label_authority,
        key=scoped_widget_key("web_research_authority", *state_scope),
    )
    st.info("默认可信度只用于批量初始标记；后续多 Agent 版本会按来源逐页评估。")
    if st.button(
        f"抓取并导入选中网页（{len(selected)}）",
        width="stretch",
        disabled=not selected,
        key=scoped_widget_key("web_research_import_selected", *state_scope),
    ):
        pages, errors = _fetch_selected_pages(selected)
        imported: list[dict] = []
        if pages:
            try:
                with st.spinner("正在保存网页并重建检索索引..."):
                    imported = import_fetched_web_pages(
                        project_name,
                        pages,
                        query=result.query,
                        provider=result.provider,
                        scope=scope,
                        authority=authority,
                        extra_metadata={
                            "retrieval_status": "quarantine",
                            "untrusted_web_content": True,
                            "story_id": str(story_id or ""),
                            "manual_web_import": True,
                        },
                    )
            except Exception as exc:
                st.error(f"网页保存或索引重建失败：{exc}")
        st.session_state[_last_import_key(*state_scope)] = {
            "imported": imported,
            "errors": errors,
            "retrieval_status": "quarantine",
        }
        if imported:
            st.success(f"已保存 {len(imported)} 个网页到隔离区。请检查正文后再启用检索。")
        for error in errors:
            st.warning(error)

    last_import = st.session_state.get(_last_import_key(*state_scope), {})
    imported_rows = last_import.get("imported", []) if isinstance(last_import, dict) else []
    if imported_rows:
        with st.expander("最近导入的网络资料与正文预览", expanded=True):
            st.dataframe(imported_rows, width="stretch", hide_index=True)
            preview_options = {
                str(item.get("relative_path") or ""): str(item.get("title") or item.get("url") or "网页")
                for item in imported_rows
                if str(item.get("relative_path") or "")
            }
            if preview_options:
                preview_path = st.selectbox(
                    "预览网页",
                    options=list(preview_options),
                    format_func=lambda value: preview_options[value],
                    key=scoped_widget_key("manual_web_preview", *state_scope),
                )
                try:
                    preview_page = load_imported_web_page(project_name, preview_path)
                    st.caption(preview_page.final_url)
                    st.text_area(
                        "抓取正文（只读预览）",
                        value=preview_page.text[:6000],
                        height=260,
                        disabled=True,
                        key=scoped_widget_key("manual_web_preview_text", *state_scope, preview_path),
                    )
                except Exception as exc:
                    st.warning(f"无法读取网页预览：{exc}")
        paths = list(preview_options)
        statuses = get_imported_web_pages_retrieval_statuses(project_name, paths)
        all_active = bool(paths) and len(statuses) == len(paths) and all(value == "active" for value in statuses.values())
        if all_active:
            st.success("最近导入的网页已启用，并以不可信外部证据边界参与检索。")
            if st.button(
                "重新隔离最近导入的网页",
                width="stretch",
                key=scoped_widget_key("manual_web_quarantine", *state_scope),
            ):
                set_imported_web_pages_retrieval_status(
                    project_name,
                    paths,
                    status="quarantine",
                    build_vectors=True,
                )
                st.rerun()
        else:
            st.warning("最近导入的网页仍在隔离区，不会进入写作检索。")
            if st.button(
                "确认正文后，启用最近导入的网页",
                width="stretch",
                type="primary",
                key=scoped_widget_key("manual_web_activate", *state_scope),
            ):
                set_imported_web_pages_retrieval_status(
                    project_name,
                    paths,
                    status="active",
                    build_vectors=True,
                )
                refreshed = get_imported_web_pages_retrieval_statuses(project_name, paths)
                if len(refreshed) != len(paths) or any(value != "active" for value in refreshed.values()):
                    st.error("部分来源缺失，未能全部启用。")
                else:
                    st.rerun()


def render_web_research_import(project_name: str, story_id: str) -> None:
    """Render durable agent research and the smaller manual import path."""

    st.markdown("#### 网络资料研究")
    agent_tab, manual_tab = st.tabs(["自动研究 Agent", "手动搜索导入"])
    with agent_tab:
        render_web_research_task_manager(project_name, story_id)
    with manual_tab:
        _render_manual_web_research_import(project_name, story_id)
