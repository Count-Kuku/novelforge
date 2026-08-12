"""SQLite operations for the paged, unified knowledge center."""

from __future__ import annotations

import base64
import json
import re
import sqlite3
from typing import Any


def _json_object(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value or "{}"))
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _source_body(metadata_json: Any, indexed_text: Any = "") -> str:
    metadata = _json_object(metadata_json)
    for key in ("content", "text", "raw_text", "source_text"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return str(indexed_text or metadata_json or "{}")


def _cursor_offset(cursor: str) -> int:
    if not str(cursor or "").strip():
        return 0
    try:
        raw = base64.urlsafe_b64decode(str(cursor).encode("ascii")).decode("ascii")
        return max(int(raw), 0)
    except Exception as exc:
        raise ValueError("知识中心分页游标无效。") from exc


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(max(offset, 0)).encode("ascii")).decode("ascii")


def _fts_query(query: str) -> str:
    clean = " ".join(
        re.sub(r"[\x00-\x1f\x7f]+", " ", str(query or "")).replace('"', " ").split()
    )
    return " OR ".join(f'"{term}"' for term in list(dict.fromkeys(clean.split()))[:32])


def search_knowledge_center_rows(
    conn: sqlite3.Connection,
    *,
    query: str = "",
    record_types: list[str] | None = None,
    categories: list[str] | None = None,
    story_id: str | None = None,
    worldline_id: str | None = None,
    include_archived: bool = False,
    archived_only: bool = False,
    cursor: str = "",
    page_size: int = 40,
) -> dict:
    offset = _cursor_offset(cursor)
    bounded_size = max(1, min(int(page_size or 40), 100))
    raw_terms = list(dict.fromkeys(str(query or "").split()))[:32]
    long_terms = [term for term in raw_terms if len(term) >= 3]
    short_terms = [term for term in raw_terms if len(term) < 3]
    match = _fts_query(" ".join(long_terms))
    clauses: list[str] = []
    params: list[Any] = []
    if match:
        clauses.append("knowledge_center_fts MATCH ?")
        params.append(match)
    if short_terms:
        short_predicates: list[str] = []
        for term in short_terms:
            short_predicates.append("(title LIKE ? OR body LIKE ? OR source_terms LIKE ? OR worldline_terms LIKE ?)")
            pattern = f"%{term}%"
            params.extend((pattern, pattern, pattern, pattern))
        clauses.append("(" + " OR ".join(short_predicates) + ")")
    for column, values in (("record_type", record_types), ("category", categories)):
        if values:
            clauses.append(f"{column} IN ({','.join('?' for _ in values)})")
            params.extend(values)
    if story_id is not None:
        clauses.append("story_id IN ('', ?)")
        params.append(str(story_id))
    if worldline_id is not None:
        clauses.append("worldline_id IN ('', 'global', 'main', ?)")
        params.append(str(worldline_id))
    if archived_only:
        clauses.append("record_status = 'archived'")
    elif not include_archived:
        clauses.append("record_status <> 'archived'")
    where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rank_sql = "bm25(knowledge_center_fts, 0, 0, 0.8, 2.2, 1.0, 0.5, 0.4)" if match else "0.0"
    snippet_sql = (
        "snippet(knowledge_center_fts, 4, '<mark>', '</mark>', '…', 26)"
        if match else "substr(body, 1, 220)"
    )
    rows = conn.execute(
        f"""
        SELECT rowid, record_type, record_id, category, title, record_status,
               story_id, worldline_id, updated_at, {rank_sql} AS rank,
               {snippet_sql} AS snippet
        FROM knowledge_center_fts {where_sql}
        ORDER BY rank ASC, updated_at DESC, record_type, record_id
        LIMIT ? OFFSET ?
        """,
        (*params, bounded_size + 1, offset),
    ).fetchall()
    has_more = len(rows) > bounded_size
    return {
        "items": [dict(row) for row in rows[:bounded_size]],
        "page_size": bounded_size,
        "cursor": cursor,
        "next_cursor": _encode_cursor(offset + bounded_size) if has_more else "",
        "has_more": has_more,
    }


def load_knowledge_center_record_row(
    conn: sqlite3.Connection,
    record_type: str,
    record_id: str,
) -> dict:
    clean_type = str(record_type or "").strip()
    clean_id = str(record_id or "").strip()
    if clean_type in {"knowledge", "pending"}:
        pending = clean_type == "pending"
        table = "pending_knowledge_items" if pending else "knowledge_items"
        id_column = "pending_id" if pending else "knowledge_id"
        row = conn.execute(f"SELECT * FROM {table} WHERE {id_column} = ?", (clean_id,)).fetchone()
        if not row:
            return {}
        result = dict(row)
        result["payload"] = _json_object(result.pop("content_json", "{}"))
        result["structured"] = _json_object(result.pop("structured_json", "{}"))
        if pending:
            result["quality"] = _json_object(result.pop("quality_json", "{}"))
        result["archived"] = bool(result.get("deleted_at"))
        return result
    if clean_type != "source":
        return {}
    row = conn.execute(
        """
        SELECT segment.*, source.title AS source_title, source.source_type,
               source.story_id, source.authority, source.canon_status,
               source.active_revision_id, source.deleted_at AS source_deleted_at,
               revision.content_hash AS revision_content_hash,
               revision.filename AS revision_filename,
               revision.metadata_json AS revision_metadata_json,
               (
                   SELECT GROUP_CONCAT(chunk.text, char(10))
                   FROM retrieval_documents AS document
                   JOIN retrieval_chunks AS chunk ON chunk.document_id = document.document_id
                   WHERE (
                       document.source_id = source.source_id
                       OR (
                           COALESCE(json_extract(source.metadata_json, '$.relative_path'), '') <> ''
                           AND instr(
                               replace(COALESCE(json_extract(document.metadata_json, '$.path'), ''), '\\', '/'),
                               json_extract(source.metadata_json, '$.relative_path')
                           ) > 0
                       )
                   )
                     AND document.deleted_at IS NULL AND chunk.deleted_at IS NULL
               ) AS indexed_text
        FROM source_segments AS segment
        JOIN source_documents AS source ON source.source_id = segment.source_id
        LEFT JOIN source_revisions AS revision ON revision.revision_id = segment.source_revision_id
        WHERE segment.segment_id = ?
        """,
        (clean_id,),
    ).fetchone()
    if not row:
        return {}
    result = dict(row)
    result["payload"] = _json_object(result.pop("metadata_json", "{}"))
    result["revision_metadata"] = _json_object(result.pop("revision_metadata_json", "{}"))
    try:
        result["heading_path"] = json.loads(result.pop("heading_path_json", "[]") or "[]")
    except Exception:
        result["heading_path"] = []
    result["archived"] = bool(result.get("deleted_at") or result.get("source_deleted_at"))
    return result


def load_knowledge_graph_rows(
    conn: sqlite3.Connection,
    *,
    story_id: str | None = None,
    worldline_id: str | None = None,
) -> dict:
    """Load the active relationship projection used by creator-facing views.

    The graph is a projection of confirmed knowledge.  Callers must edit the
    owning knowledge item instead of mutating these rows directly.
    """

    clauses = ["edge.deleted_at IS NULL", "source.deleted_at IS NULL", "target.deleted_at IS NULL"]
    params: list[str] = []
    if story_id is not None:
        clauses.append("COALESCE(edge.story_id, '') IN ('', ?)")
        params.append(str(story_id))
    if worldline_id is not None:
        clauses.append(
            "COALESCE(source.worldline_id, target.worldline_id, '') IN ('', 'global', 'main', ?)"
        )
        params.append(str(worldline_id))
    rows = conn.execute(
        f"""
        SELECT edge.edge_id, edge.story_id, edge.relation_type, edge.direction,
               edge.confidence, edge.metadata_json, edge.updated_at,
               source.node_id AS source_node_id,
               source.display_name AS source_name,
               source.node_type AS source_type,
               target.node_id AS target_node_id,
               target.display_name AS target_name,
               target.node_type AS target_type
        FROM graph_edges AS edge
        JOIN graph_nodes AS source ON source.node_id = edge.source_node_id
        JOIN graph_nodes AS target ON target.node_id = edge.target_node_id
        WHERE {' AND '.join(clauses)}
        ORDER BY edge.updated_at DESC, edge.edge_id
        """,
        tuple(params),
    ).fetchall()
    edges: list[dict] = []
    nodes: dict[str, dict] = {}
    for row in rows:
        edge = dict(row)
        metadata = _json_object(edge.pop("metadata_json", "{}"))
        owner_id = str(metadata.get("knowledge_id") or "")
        item = metadata.get("item") if isinstance(metadata.get("item"), dict) else {}
        edge["knowledge_id"] = owner_id
        edge["knowledge_item"] = item
        edges.append(edge)
        for side in ("source", "target"):
            node_id = str(edge.get(f"{side}_node_id") or "")
            if node_id:
                nodes[node_id] = {
                    "node_id": node_id,
                    "name": str(edge.get(f"{side}_name") or ""),
                    "node_type": str(edge.get(f"{side}_type") or "entity"),
                }
    return {"nodes": list(nodes.values()), "edges": edges}


def _payload_for_job(conn: sqlite3.Connection, record_type: str, record_id: str) -> dict:
    if record_type in {"knowledge", "pending"}:
        pending = record_type == "pending"
        table = "pending_knowledge_items" if pending else "knowledge_items"
        id_column = "pending_id" if pending else "knowledge_id"
        row = conn.execute(
            f"""
            SELECT item.*, COALESCE(source.title, '') AS source_title
            FROM {table} AS item
            LEFT JOIN source_documents AS source ON source.source_id = item.source_id
            WHERE item.{id_column} = ?
            """,
            (record_id,),
        ).fetchone()
        if not row:
            return {}
        item = dict(row)
        worldline_name = item.get("worldline_name") if not pending else ""
        return {
            "record_type": record_type, "record_id": record_id,
            "category": item.get("category") or "",
            "title": item.get("name") or item.get("title") or record_id,
            "body": item.get("content_json") or "{}", "source_terms": item.get("source_title") or "",
            "worldline_terms": f"{worldline_name or ''} {item.get('worldline_id') or ''}",
            "story_id": item.get("story_id") or "", "worldline_id": item.get("worldline_id") or "",
            "record_status": "archived" if item.get("deleted_at") else item.get("status") or ("pending" if pending else "confirmed"),
            "updated_at": item.get("updated_at") or item.get("created_at") or "",
        }
    row = conn.execute(
        """
        SELECT segment.*, source.title AS source_title, source.source_type,
               source.story_id, source.deleted_at AS source_deleted_at
               ,(
                   SELECT GROUP_CONCAT(chunk.text, char(10))
                   FROM retrieval_documents AS document
                   JOIN retrieval_chunks AS chunk ON chunk.document_id = document.document_id
                   WHERE (
                       document.source_id = source.source_id
                       OR (
                           COALESCE(json_extract(source.metadata_json, '$.relative_path'), '') <> ''
                           AND instr(
                               replace(COALESCE(json_extract(document.metadata_json, '$.path'), ''), '\\', '/'),
                               json_extract(source.metadata_json, '$.relative_path')
                           ) > 0
                       )
                   )
                     AND document.deleted_at IS NULL AND chunk.deleted_at IS NULL
               ) AS indexed_text
        FROM source_segments AS segment
        JOIN source_documents AS source ON source.source_id = segment.source_id
        WHERE segment.segment_id = ?
        """,
        (record_id,),
    ).fetchone()
    if not row:
        return {}
    item = dict(row)
    return {
        "record_type": "source", "record_id": record_id, "category": "source",
        "title": item.get("title") or item.get("source_title") or record_id,
        "body": _source_body(item.get("metadata_json"), item.get("indexed_text")),
        "source_terms": f"{item.get('source_title') or ''} {item.get('source_type') or ''}",
        "worldline_terms": "", "story_id": item.get("story_id") or "", "worldline_id": "",
        "record_status": "archived" if item.get("deleted_at") or item.get("source_deleted_at") else "source",
        "updated_at": item.get("updated_at") or item.get("created_at") or "",
    }


def process_knowledge_index_jobs(conn: sqlite3.Connection, limit: int = 200) -> dict:
    conn.execute(
        """
        UPDATE knowledge_index_jobs
        SET status='queued', error_text='后台索引在上次进程退出时中断，已重新排队',
            updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'), finished_at=NULL
        WHERE status='running' AND updated_at <= strftime('%Y-%m-%dT%H:%M:%SZ','now','-5 minutes')
        """
    )
    jobs = conn.execute(
        """
        SELECT * FROM knowledge_index_jobs WHERE status = 'queued'
        ORDER BY updated_at, job_id LIMIT ?
        """,
        (max(1, min(int(limit or 200), 2000)),),
    ).fetchall()
    processed = failed = 0
    columns = (
        "record_type", "record_id", "category", "title", "body", "source_terms",
        "worldline_terms", "story_id", "worldline_id", "record_status", "updated_at",
    )
    for raw_job in jobs:
        job = dict(raw_job)
        job_id = str(job.get("job_id") or "")
        try:
            conn.execute(
                "UPDATE knowledge_index_jobs SET status='running', attempts=attempts+1, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE job_id=?",
                (job_id,),
            )
            conn.execute(
                "DELETE FROM knowledge_center_fts WHERE record_type=? AND record_id=?",
                (job.get("record_type"), job.get("record_id")),
            )
            payload = _payload_for_job(conn, str(job.get("record_type") or ""), str(job.get("record_id") or ""))
            if payload:
                conn.execute(
                    f"INSERT INTO knowledge_center_fts ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                    tuple(payload[key] for key in columns),
                )
            conn.execute(
                "UPDATE knowledge_index_jobs SET status='completed', error_text='', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'), finished_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE job_id=?",
                (job_id,),
            )
            processed += 1
        except Exception as exc:
            conn.execute(
                "UPDATE knowledge_index_jobs SET status='failed', error_text=?, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'), finished_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE job_id=?",
                (str(exc), job_id),
            )
            failed += 1
    if processed:
        conn.execute(
            "UPDATE knowledge_index_state SET last_fts_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'), updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE state_id=1"
        )
    remaining = int(conn.execute(
        "SELECT COUNT(*) FROM knowledge_index_jobs WHERE status IN ('queued','running')"
    ).fetchone()[0])
    failed_total = int(conn.execute(
        "SELECT COUNT(*) FROM knowledge_index_jobs WHERE status = 'failed'"
    ).fetchone()[0])
    return {
        "processed": processed, "failed": failed,
        "failed_total": failed_total, "remaining": remaining,
    }


def load_knowledge_index_state_row(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT * FROM knowledge_index_state WHERE state_id=1").fetchone()
    state = dict(row) if row else {}
    state["job_counts"] = {
        str(item[0]): int(item[1])
        for item in conn.execute("SELECT status, COUNT(*) FROM knowledge_index_jobs GROUP BY status")
    }
    return state


def mark_knowledge_retrieval_state(
    conn: sqlite3.Connection,
    status: str,
    *,
    indexed_revision: int | None = None,
    error_text: str = "",
) -> dict:
    clean = str(status or "").strip()
    if clean not in {"queued", "running", "completed", "failed"}:
        raise ValueError("知识检索索引状态无效。")
    revision_value = int(indexed_revision) if indexed_revision is not None else None
    conn.execute(
        f"""
        UPDATE knowledge_index_state SET retrieval_status=?,
            indexed_revision=COALESCE(?, indexed_revision), last_error=?,
            last_retrieval_at=CASE WHEN ? IN ('completed','failed') THEN strftime('%Y-%m-%dT%H:%M:%SZ','now') ELSE last_retrieval_at END,
            updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE state_id=1
        """,
        (clean, revision_value, error_text, clean),
    )
    return load_knowledge_index_state_row(conn)


def retry_knowledge_index_jobs(conn: sqlite3.Connection) -> int:
    cursor = conn.execute(
        "UPDATE knowledge_index_jobs SET status='queued', error_text='', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'), finished_at=NULL WHERE status='failed'"
    )
    conn.execute(
        "UPDATE knowledge_index_state SET retrieval_status='queued', last_error='', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE state_id=1"
    )
    return int(cursor.rowcount or 0)
