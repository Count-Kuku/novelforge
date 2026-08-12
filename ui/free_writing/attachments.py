"""Attachment tray for free writing."""

from __future__ import annotations

import streamlit as st

from novelforge.services.document_parsing import (
    DocumentParsingError,
    get_local_ocr_readiness,
    ocr_pdf_bytes,
    parse_document_bytes,
)
from novelforge.services.memory import list_creative_attachments
from novelforge.workflows.creative_attachments import (
    ATTACHMENT_SCOPE_LABELS,
    attach_existing_creative_source,
    import_creative_documents,
    import_creative_pasted_text,
    import_creative_url,
    list_existing_creative_sources,
    schedule_creative_attachment_knowledge,
)
from ui.llm_preflight import render_preflight_estimate
from ui.common import scoped_widget_key


def _attachment_caption(attachment: dict) -> str:
    status = str(attachment.get("status") or "indexed")
    status_label = {
        "parsed": "已解析",
        "indexed": "原文可检索",
        "processing": "知识提取中",
        "ready": "整理完成",
        "failed": "处理失败",
    }.get(status, status)
    scope_label = ATTACHMENT_SCOPE_LABELS.get(
        str(attachment.get("scope") or "session"),
        str(attachment.get("scope") or ""),
    )
    return f"{scope_label} · {status_label}"


def _render_attachment_status(project_name: str, attachment: dict) -> None:
    caption = _attachment_caption(attachment)
    task_status = str(attachment.get("task_status") or "")
    message = str(
        attachment.get("task_message")
        or attachment.get("metadata", {}).get("background_message")
        or ""
    )
    progress = attachment.get("task_progress") or {}
    metadata = attachment.get("metadata") or {}
    if progress.get("total"):
        caption += f" · {int(progress.get('finished') or 0)}/{int(progress.get('total') or 0)}"
    st.markdown(f"- **{attachment.get('title') or attachment.get('filename') or '未命名资料'}** · {caption}")
    if message:
        st.caption(message)
    parser = metadata.get("parser_metadata") if isinstance(metadata, dict) else {}
    documents = parser.get("documents", []) if isinstance(parser, dict) else []
    first_document = documents[0] if documents and isinstance(documents[0], dict) else {}
    ocr_metadata = first_document.get("metadata") if isinstance(first_document.get("metadata"), dict) else {}
    page_confidences = ocr_metadata.get("ocr_page_confidences", [])
    if isinstance(page_confidences, list) and page_confidences:
        with st.expander("OCR 逐页置信度", expanded=False):
            st.dataframe(
                [
                    {
                        "页码": item.get("page"),
                        "置信度": item.get("confidence"),
                        "识别字符": item.get("char_count"),
                    }
                    for item in page_confidences
                    if isinstance(item, dict)
                ],
                hide_index=True,
                width="stretch",
            )
    if task_status == "completed_with_errors" or str(attachment.get("status")) == "failed":
        st.warning("部分知识处理失败；原文仍可检索，可前往资料中心重试后台任务。")
    if metadata.get("background_status") == "awaiting_confirmation":
        estimate = metadata.get("background_estimate") or {}
        approved = render_preflight_estimate(
            estimate,
            expanded=False,
            confirmation_key=scoped_widget_key(
                "creative_attachment_budget_confirm",
                project_name,
                attachment.get("attachment_id"),
            ),
        )
        if st.button(
            "确认并开始后台整理",
            disabled=not approved,
            key=scoped_widget_key(
                "creative_attachment_confirm_background",
                project_name,
                attachment.get("attachment_id"),
            ),
            width="stretch",
        ):
            schedule_creative_attachment_knowledge(
                project_name,
                str(attachment.get("attachment_id") or ""),
                confirm_over_budget=True,
            )
            st.rerun()


def _render_existing_attachments(
    project_name: str,
    story_id: str,
    session_id: str,
) -> None:
    attachments = list_creative_attachments(
        project_name,
        story_id=story_id,
        session_id=session_id,
    )
    if not attachments:
        st.caption("还没有可用资料。导入后原文会立即参与当前创作的关键词检索。")
        return
    for attachment in attachments[:12]:
        title = str(
            attachment.get("title")
            or attachment.get("filename")
            or "未命名资料"
        )
        _render_attachment_status(project_name, attachment)
    if len(attachments) > 12:
        st.caption(f"另有 {len(attachments) - 12} 份资料，可在资料中心查看。")


def render_attachment_tray(
    project_name: str,
    story_id: str,
    session_id: str,
) -> None:
    with st.expander("资料与附件", expanded=False):
        _render_existing_attachments(project_name, story_id, session_id)
        st.divider()
        scope_options = ["turn", "session", "story", "project"] if session_id else ["story", "project"]
        scope = st.segmented_control(
            "这些资料在哪里生效？",
            options=scope_options,
            default="session" if session_id else "story",
            format_func=lambda value: ATTACHMENT_SCOPE_LABELS[value],
            key=scoped_widget_key(
                "creative_attachment_scope",
                project_name,
                story_id,
                session_id or "new",
            ),
            width="stretch",
        ) or ("session" if session_id else "story")
        tab_file, tab_text, tab_url, tab_existing = st.tabs(["上传文件", "粘贴长文", "网页地址", "已有资料"])
        with tab_file:
            ocr_readiness = get_local_ocr_readiness()
            use_ocr = st.checkbox(
                "对 PDF 显式执行本地 OCR",
                value=False,
                disabled=not bool(ocr_readiness.get("available")),
                key=scoped_widget_key(
                    "creative_attachment_use_ocr",
                    project_name,
                    story_id,
                    session_id or "new",
                ),
                help="默认关闭。开启后只在本机逐页识别，并保存页级置信度供抽查。",
            )
            st.caption(str(ocr_readiness.get("message") or ""))
            uploaded_files = st.file_uploader(
                "选择资料文件",
                type=["txt", "md", "markdown", "docx", "epub", "pdf"],
                accept_multiple_files=True,
                key=scoped_widget_key(
                    "creative_attachment_files",
                    project_name,
                    story_id,
                    session_id or "new",
                ),
            )
            if st.button(
                "导入并开始检索",
                disabled=not bool(uploaded_files),
                key=scoped_widget_key(
                    "creative_attachment_import_files",
                    project_name,
                    story_id,
                    session_id or "new",
                ),
                width="stretch",
                type="primary",
            ):
                documents = []
                errors: list[str] = []
                scanned_pdfs: list[str] = []
                for item in list(uploaded_files or []):
                    try:
                        if use_ocr and str(item.name).lower().endswith(".pdf"):
                            document = ocr_pdf_bytes(item.name, item.getvalue())
                        else:
                            document = parse_document_bytes(item.name, item.getvalue())
                        documents.append(document)
                        if (
                            str(document.media_type) == "application/pdf"
                            and int(document.metadata.get("empty_page_count") or 0) > 0
                        ):
                            scanned_pdfs.append(item.name)
                    except DocumentParsingError as exc:
                        errors.append(str(exc))
                for error in errors:
                    st.error(error)
                if documents:
                    try:
                        imported = import_creative_documents(
                            project_name,
                            story_id,
                            session_id,
                            documents,
                            scope=scope,
                        )
                    except Exception as exc:
                        st.error(f"资料导入失败：{exc}")
                    else:
                        st.success(f"已导入 {len(imported)} 份资料，原文现在即可检索。")
                        if scanned_pdfs:
                            st.info(
                                "检测到可能含扫描页的 PDF。当前环境未配置 OCR 执行器，"
                                "不会静默上传或识别；原文文本层仍已可检索。"
                            )
                        st.rerun()
        with tab_text:
            pasted_title = st.text_input(
                "资料标题",
                placeholder="例如：原作设定摘录",
                key=scoped_widget_key(
                    "creative_attachment_text_title",
                    project_name,
                    story_id,
                    session_id or "new",
                ),
            )
            pasted_text = st.text_area(
                "粘贴资料正文",
                height=180,
                key=scoped_widget_key(
                    "creative_attachment_text",
                    project_name,
                    story_id,
                    session_id or "new",
                ),
            )
            if st.button(
                "保存并开始检索",
                disabled=not bool(str(pasted_text or "").strip()),
                key=scoped_widget_key(
                    "creative_attachment_import_text",
                    project_name,
                    story_id,
                    session_id or "new",
                ),
                width="stretch",
                type="primary",
            ):
                try:
                    import_creative_pasted_text(
                        project_name,
                        story_id,
                        session_id,
                        pasted_text,
                        title=pasted_title,
                        scope=scope,
                    )
                except Exception as exc:
                    st.error(f"资料导入失败：{exc}")
                else:
                    st.success("资料已保存，原文现在即可检索。")
                    st.rerun()
        with tab_url:
            url = st.text_input(
                "公开网页地址",
                placeholder="https://example.com/article",
                key=scoped_widget_key(
                    "creative_attachment_url",
                    project_name,
                    story_id,
                    session_id or "new",
                ),
                help="只抓取公开静态文本页面；不登录、不执行 JavaScript，也不绕过付费墙。",
            )
            if st.button(
                "抓取并开始检索",
                disabled=not bool(str(url or "").strip()),
                key=scoped_widget_key(
                    "creative_attachment_import_url",
                    project_name,
                    story_id,
                    session_id or "new",
                ),
                width="stretch",
                type="primary",
            ):
                try:
                    import_creative_url(
                        project_name,
                        story_id,
                        session_id,
                        url,
                        scope=scope,
                    )
                except Exception as exc:
                    st.error(f"网页资料导入失败：{exc}")
                else:
                    st.success("网页正文已保存，现在即可检索。")
                    st.rerun()
        with tab_existing:
            sources = list_existing_creative_sources(project_name)
            if not sources:
                st.caption("资料中心里还没有可选择的检索资料。")
            else:
                selected_path = st.selectbox(
                    "选择已有资料",
                    options=[str(item.get("relative_path") or "") for item in sources],
                    format_func=lambda value: next(
                        (
                            str(item.get("title") or value)
                            for item in sources
                            if str(item.get("relative_path") or "") == value
                        ),
                        value,
                    ),
                    key=scoped_widget_key(
                        "creative_attachment_existing",
                        project_name,
                        story_id,
                        session_id or "new",
                    ),
                )
                if st.button(
                    "添加到当前创作",
                    key=scoped_widget_key(
                        "creative_attachment_attach_existing",
                        project_name,
                        story_id,
                        session_id or "new",
                    ),
                    width="stretch",
                    type="primary",
                ):
                    try:
                        attach_existing_creative_source(
                            project_name,
                            story_id,
                            session_id,
                            selected_path,
                            scope=scope,
                        )
                    except Exception as exc:
                        st.error(f"已有资料添加失败：{exc}")
                    else:
                        st.success("已有资料已加入当前创作。")
                        st.rerun()
