"""Focused acceptance checks for the ingestion/knowledge upgrade."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.domain.knowledge_types import normalize_typed_knowledge_item
from novelforge.domain.knowledge_workflows import evaluate_pending_auto_review_decision
from novelforge.services.document_parsing import parse_document_bytes
from novelforge.services.retrieval import (
    RetrievalDocument,
    build_structured_external_source_payload,
    chunk_document,
)
from novelforge.services.retrieval.search import (
    _build_feedback_stats,
    _feedback_bonus_for_chunk,
    _reciprocal_rank_fusion,
)
from novelforge.workflows.source_workflows import (
    extract_long_reference_segments_to_queue,
    split_long_reference_text,
)
from storage.repositories.knowledge import sync_knowledge_category, sync_pending_knowledge
from storage.repositories.retrieval import search_retrieval_chunks_fts, sync_retrieval_manifest_payload
from storage.repositories.sources import sync_long_reference_batch
from storage.repositories.stories import sync_stories_index
from storage.schema import CURRENT_SCHEMA_VERSION, MIGRATIONS_DIR, _execute_migration_script, ensure_schema


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def _docx_bytes() -> bytes:
    target = BytesIO()
    with ZipFile(target, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>第一章</w:t></w:r></w:p>
<w:p><w:r><w:t>角色在城门发现了线索。</w:t></w:r></w:p>
</w:body></w:document>""",
        )
        archive.writestr(
            "word/styles.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>
</w:styles>""",
        )
    return target.getvalue()


def _epub_bytes() -> bytes:
    target = BytesIO()
    with ZipFile(target, "w") as archive:
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>""",
        )
        archive.writestr(
            "OEBPS/content.opf",
            """<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf"><metadata><title>测试书</title></metadata><manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c1"/></spine></package>""",
        )
        archive.writestr("OEBPS/c1.xhtml", "<html><body><h1>序章</h1><p>雨夜中的事件。</p></body></html>")
    return target.getvalue()


def verify_parsing_and_chunking() -> None:
    markdown = parse_document_bytes("notes.md", "# 规则\n\n魔法需要代价。".encode("utf-8"))
    fenced_markdown = parse_document_bytes(
        "fenced.md",
        "# 规则\n\n```markdown\n# 这不是标题\n```\n\n正文。".encode("utf-8"),
    )
    utf16_text = parse_document_bytes("utf16.txt", "中文编码正文".encode("utf-16"))
    docx = parse_document_bytes("novel.docx", _docx_bytes())
    epub = parse_document_bytes("novel.epub", _epub_bytes())
    check(markdown.sections[0].title == "规则", "Markdown 标题层级被保留")
    check(len(fenced_markdown.sections) == 1, "代码围栏内的井号不会被误判为 Markdown 标题")
    check("中文编码正文" in utf16_text.text, "UTF-16 文本不会被 GB18030 误解码")
    check(docx.sections and docx.sections[0].title == "第一章", "DOCX 标题样式被解析")
    check(epub.sections and "雨夜" in epub.sections[0].text, "EPUB 书脊正文被解析")
    compact_metadata = epub.to_dict()
    check(
        "text" not in compact_metadata["sections"][0] and compact_metadata["sections"][0]["char_count"] > 0,
        "解析器元数据不会重复保存整份正文",
    )

    raw = "# 第一章\n\n" + "甲。乙！丙？" * 300 + "\n\n***\n\n# 第二章\n\n结束。"
    segments = split_long_reference_text("测试", raw, max_chars=500)
    check(len(segments) > 2, "长章节会按句子边界继续拆分")
    check(all(item["char_count"] <= 500 for item in segments), "所有导入片段遵守硬字符上限")
    check(all(item.get("content_hash") for item in segments), "片段带稳定内容哈希")
    check(all("start_offset" in item and "end_offset" in item for item in segments), "片段带原文位置锚点")

    document = RetrievalDocument(
        doc_id="p:external_source:long-parent",
        project_name="p",
        source_type="external_source",
        scope="reference",
        title="重复标题",
        content="# 同名\n\n" + "甲" * 7000 + "关键尾部\n\n# 同名\n\n第二个同名章节。",
    )
    retrieval_chunks = chunk_document(document)
    check(all(len(chunk.content) <= 900 for chunk in retrieval_chunks), "检索子片段不会因超长单段突破上限")
    tail_hit = next(chunk for chunk in retrieval_chunks if "关键尾部" in chunk.content)
    check("关键尾部" in tail_hit.metadata.get("parent_content", ""), "长父段落窗口始终覆盖命中的子片段")
    parent_ids = {
        chunk.metadata.get("parent_chunk_id")
        for chunk in retrieval_chunks
        if chunk.title == "同名"
    }
    check(len(parent_ids) == 2, "重复章节标题不会共享错误的父上下文")


def verify_zero_chunk_regression() -> None:
    payload = build_structured_external_source_payload(
        source_type="external_source",
        scope="reference",
        title="测试资料",
        summary="摘要内容",
        content="详细内容与规则。",
    )
    document = RetrievalDocument(
        doc_id="p:external_source:test",
        project_name="p",
        source_type="external_source",
        scope="reference",
        title="测试资料",
        content=payload["content"],
    )
    chunks = chunk_document(document)
    check(len(chunks) == 2, "结构化外部资料不会再生成零片段")
    check(all(chunk.metadata.get("parent_chunk_id") for chunk in chunks), "检索子片段带父上下文标识")


def verify_story_scope() -> None:
    batch = {
        "batch_id": "scope",
        "title": "资料",
        "segments": [{"segment_id": "seg", "index": 1, "title": "片段", "content": "原文证据"}],
    }
    captured: dict = {}

    def fake_extract(*args, **kwargs):
        captured.update(kwargs)
        return {"data": {"knowledge_extraction": {"source_title": "资料", "items": []}}}

    with (
        patch("novelforge.workflows.source_workflows.extract_reference_knowledge", side_effect=fake_extract),
        patch("novelforge.workflows.source_workflows.get_segment_related_knowledge_items", return_value={"pending": [], "confirmed": []}),
        patch("novelforge.workflows.source_workflows.queue_pending_knowledge_items", return_value=0),
        patch("novelforge.workflows.source_workflows.save_long_reference_batch", side_effect=lambda _project, value, **_kwargs: value),
    ):
        extract_long_reference_segments_to_queue(
            "p", batch, [0], ["characters"], story_id="story_alpha"
        )
    check(captured.get("story_id") == "story_alpha", "后台资料提取沿用任务故事作用域")


def verify_database_and_retrieval() -> None:
    legacy = sqlite3.connect(":memory:")
    legacy.row_factory = sqlite3.Row
    legacy.execute("PRAGMA foreign_keys = ON")
    legacy.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT '')")
    for version in range(1, 11):
        migration = next(MIGRATIONS_DIR.glob(f"{version:03d}_*.sql"))
        _execute_migration_script(legacy, migration.read_text(encoding="utf-8"))
        legacy.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
    legacy.execute(
        "INSERT INTO retrieval_documents (document_id, document_type, scope, title) VALUES ('legacy-doc', 'external_source', 'reference', '旧资料')"
    )
    legacy.execute(
        "INSERT INTO retrieval_chunks (chunk_id, document_id, chunk_index, text) VALUES ('legacy-chunk', 'legacy-doc', 1, '迁移前的城门资料')"
    )
    migration_11 = next(MIGRATIONS_DIR.glob("011_*.sql"))
    _execute_migration_script(legacy, migration_11.read_text(encoding="utf-8"))
    check(search_retrieval_chunks_fts(legacy, "城门资料", 5)[0]["chunk_id"] == "legacy-chunk", "v10 升级时会立即回填既有全文索引")
    legacy.close()

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    check(ensure_schema(conn) == CURRENT_SCHEMA_VERSION >= 11, "数据库迁移包含资料知识升级 v11")
    sync_stories_index(conn, {"stories": [{"story_id": "default", "name": "默认"}], "active_story_id": "default"})
    batch = sync_long_reference_batch(conn, {
        "batch_id": "upgrade",
        "story_id": "default",
        "title": "升级资料",
        "content_fingerprint": "hash-a",
        "content_char_count": 20,
        "segments": [{
            "segment_id": "seg-upgrade", "index": 1, "title": "第一节",
            "content": "角色阿青在城门发现原文证据。", "start_offset": 0, "end_offset": 15,
            "heading_path": ["第一节"], "content_kind": "scene",
        }],
    })
    check(bool(batch.get("source_revision_id")), "导入批次创建稳定来源修订")
    first_revision = batch["source_revision_id"]
    same_revision = sync_long_reference_batch(conn, {
        **batch,
        "segments": [{**batch["segments"][0], "import_status": "imported"}],
    })
    check(
        same_revision["source_revision_id"] == first_revision
        and conn.execute("SELECT COUNT(*) FROM source_revisions WHERE source_id = ?", (batch["source_id"],)).fetchone()[0] == 1,
        "任务状态变化不会改写或复制来源修订",
    )
    changed_revision = sync_long_reference_batch(conn, {
        **batch,
        "source_content_hash": "exact-hash-b",
        "segments": [{**batch["segments"][0], "content": "角色阿青  在城门发现原文证据。"}],
    })
    check(changed_revision["source_revision_id"] != first_revision, "精确原文变化会创建新的来源修订")

    typed = normalize_typed_knowledge_item({
        "pending_id": "pending-upgrade", "id": "knowledge-upgrade", "story_id": "default",
        "category": "characters", "name": "阿青", "details": {"身份": "主角"},
        "source_id": batch["source_id"], "source_revision_id": batch["source_revision_id"],
        "source_segment_id": "seg-upgrade", "evidence": [{"quote": "原文证据", "start_offset": 8}],
    })
    sync_pending_knowledge(conn, [typed])
    sync_knowledge_category(conn, "characters", [typed])
    sync_knowledge_category(conn, "characters", [{**typed, "summary": "更新后的摘要"}])
    knowledge = dict(conn.execute(
        "SELECT source_id, segment_id, schema_version, structured_json FROM knowledge_items"
    ).fetchone())
    check(knowledge["source_id"] == batch["source_id"] and knowledge["segment_id"] == "seg-upgrade", "知识条目使用真实来源与片段外键")
    check(knowledge["schema_version"] == 2 and knowledge["structured_json"] != "{}", "分类知识按类型化结构落库")
    check(conn.execute("SELECT COUNT(*) FROM knowledge_revisions").fetchone()[0] == 2, "知识变更生成不可变修订历史")
    evidence = dict(conn.execute(
        "SELECT source_revision_id, start_offset, validation_status FROM knowledge_evidence WHERE knowledge_id = 'knowledge-upgrade'"
    ).fetchone())
    check(evidence["source_revision_id"] == batch["source_revision_id"] and evidence["validation_status"] == "anchored", "证据保存来源修订与精确文本锚点")

    manifest = {
        "documents": [{
            "doc_id": "doc-upgrade", "project_name": "p", "source_type": "external_source",
            "scope": "reference", "title": "城门资料", "content": "角色阿青在城门发现原文证据。",
            "metadata": {"story_id": "default", "source_id": batch["source_id"], "source_revision_id": batch["source_revision_id"]},
        }],
        "chunks": [{
            "chunk_id": "doc-upgrade#chunk001", "document_id": "doc-upgrade", "project_name": "p",
            "source_type": "external_source", "scope": "reference", "title": "城门资料",
            "content": "角色阿青在城门发现原文证据。", "tags": ["角色"],
            "metadata": {"chunk_index": 1, "parent_chunk_id": "doc-upgrade#parent", "chunk_level": "child", "source_revision_id": batch["source_revision_id"]},
        }],
    }
    sync_retrieval_manifest_payload(conn, manifest)
    check(search_retrieval_chunks_fts(conn, "城门发现", 5)[0]["chunk_id"] == "doc-upgrade#chunk001", "FTS5/BM25 可召回中文资料片段")

    fused, breakdown = _reciprocal_rank_fusion([
        ("lexical", ["a", "b"], 1.0), ("semantic", ["b", "a"], 1.0)
    ])
    check(fused["a"] == fused["b"] and "rrf_lexical" in breakdown["a"], "RRF 独立融合词法与语义名次")

    feedback_chunk = RetrievalDocument(
        doc_id="feedback-doc", project_name="p", source_type="external_source",
        scope="reference", title="反馈", content="新内容",
    )
    feedback_hit_chunk = chunk_document(feedback_chunk)[0]
    old_hash = "old-content-hash"
    with patch(
        "novelforge.services.retrieval.search._retrieval_api.load_retrieval_feedback",
        return_value=[{"chunk_id": feedback_hit_chunk.chunk_id, "content_hash": old_hash, "rating": "wrong"}],
    ):
        feedback_stats = _build_feedback_stats("p")
    check(_feedback_bonus_for_chunk(feedback_hit_chunk, feedback_stats) == 0, "内容更新后不会继承旧片段反馈")

    typed_decision = evaluate_pending_auto_review_decision(
        {
            "pending_id": "typed-missing", "category": "world_rules", "name": "缺字段规则",
            "confidence": 0.9, "evidence_strength": 0.9, "evidence": ["证据"],
        },
        {},
        {"allow_grade_b_auto_confirm": True, "require_evidence": True},
    )
    check(typed_decision["decision"] == "blocked", "缺少类型必填字段的知识不会被自动确认")
    conn.close()


def main() -> None:
    verify_parsing_and_chunking()
    verify_zero_chunk_regression()
    verify_story_scope()
    verify_database_and_retrieval()
    print("All ingestion/knowledge upgrade checks passed.")


if __name__ == "__main__":
    main()
