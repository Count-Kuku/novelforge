from __future__ import annotations

import sqlite3


def sync_stories_index(conn: sqlite3.Connection, index: dict) -> list[dict]:
    stories = index.get("stories", []) if isinstance(index, dict) else []
    active_story_id = str(index.get("active_story_id") or "default") if isinstance(index, dict) else "default"
    seen_story_ids: set[str] = set()
    for story in stories:
        if not isinstance(story, dict):
            continue
        story_id = str(story.get("story_id") or "").strip()
        if not story_id:
            continue
        seen_story_ids.add(story_id)
        conn.execute(
            """
            INSERT INTO stories (
                story_id, name, description, status, is_active, created_at, updated_at, deleted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(story_id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                status = excluded.status,
                is_active = excluded.is_active,
                updated_at = excluded.updated_at,
                deleted_at = NULL
            """,
            (
                story_id,
                str(story.get("name") or story_id),
                str(story.get("description") or ""),
                str(story.get("status") or "active"),
                1 if story_id == active_story_id else 0,
                str(story.get("created_at") or ""),
                str(story.get("updated_at") or ""),
            ),
        )
    conn.execute("UPDATE stories SET is_active = 0 WHERE story_id <> ?", (active_story_id,))
    if seen_story_ids:
        placeholders = ",".join("?" for _ in seen_story_ids)
        conn.execute(
            f"""
            UPDATE stories
            SET deleted_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), is_active = 0
            WHERE deleted_at IS NULL AND story_id NOT IN ({placeholders})
            """,
            tuple(seen_story_ids),
        )
    return list_story_rows(conn, include_deleted=False)


def set_active_story_row(conn: sqlite3.Connection, story_id: str) -> None:
    clean_story_id = str(story_id or "").strip()
    if not clean_story_id:
        raise ValueError("Story ID cannot be empty.")
    conn.execute("UPDATE stories SET is_active = 0")
    updated = conn.execute(
        """
        UPDATE stories
        SET is_active = 1, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE story_id = ? AND deleted_at IS NULL
        """,
        (clean_story_id,),
    ).rowcount
    if updated < 1:
        raise ValueError("Story does not exist.")


def list_story_rows(conn: sqlite3.Connection, *, include_deleted: bool = False) -> list[dict]:
    if include_deleted:
        rows = conn.execute(
            """
            SELECT story_id, name, description, status, is_active, created_at, updated_at, deleted_at
            FROM stories
            ORDER BY is_active DESC, lower(name), story_id
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT story_id, name, description, status, is_active, created_at, updated_at, deleted_at
            FROM stories
            WHERE deleted_at IS NULL
            ORDER BY is_active DESC, lower(name), story_id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def purge_story_scoped_rows(conn: sqlite3.Connection, story_id: str) -> None:
    """Remove every database record owned by one story.

    Story rows themselves are soft-deleted by ``sync_stories_index``.  The
    dependent records therefore do not receive foreign-key cascade handling;
    without this cleanup, reusing the same story ID can revive the deleted
    story's profile, rules, prompt options, JSON assets, and run history.
    """

    clean_story_id = str(story_id or "").strip()
    if not clean_story_id:
        raise ValueError("Story ID cannot be empty.")

    # Evidence can be linked indirectly through knowledge or source rows and
    # has no story_id of its own, so remove it before deleting those parents.
    conn.execute(
        """
        DELETE FROM knowledge_evidence
        WHERE knowledge_id IN (SELECT knowledge_id FROM knowledge_items WHERE story_id = ?)
           OR pending_id IN (SELECT pending_id FROM pending_knowledge_items WHERE story_id = ?)
           OR source_id IN (SELECT source_id FROM source_documents WHERE story_id = ?)
           OR segment_id IN (
               SELECT segment.segment_id
               FROM source_segments AS segment
               JOIN source_documents AS source ON source.source_id = segment.source_id
               WHERE source.story_id = ?
           )
           OR chunk_id IN (
               SELECT chunk.chunk_id
               FROM retrieval_chunks AS chunk
               JOIN retrieval_documents AS document ON document.document_id = chunk.document_id
               WHERE document.story_id = ?
           )
        """,
        (
            clean_story_id,
            clean_story_id,
            clean_story_id,
            clean_story_id,
            clean_story_id,
        ),
    )

    # Older feedback rows may predate explicit story ownership and only point
    # at a story-owned retrieval chunk.  Delete them before chunk removal turns
    # that association into NULL via ON DELETE SET NULL.
    conn.execute(
        """
        DELETE FROM retrieval_feedback
        WHERE story_id = ?
           OR chunk_id IN (
               SELECT chunk.chunk_id
               FROM retrieval_chunks AS chunk
               JOIN retrieval_documents AS document ON document.document_id = chunk.document_id
               WHERE document.story_id = ?
           )
        """,
        (clean_story_id, clean_story_id),
    )

    # Delete leaf/history tables first. Foreign keys then cascade through
    # workflow steps, retrieval chunks/vectors, source segments, and payloads.
    for table in (
        "retrieval_eval_runs",
        "retrieval_feedback",
        "retrieval_conflict_resolutions",
        "workflow_runs",
        "graph_edges",
        "graph_nodes",
        "retrieval_documents",
        "retrieval_eval_cases",
        "knowledge_items",
        "pending_knowledge_items",
        "entity_alias_groups",
        "source_documents",
        "rules",
        "prompt_options",
        "asset_files",
    ):
        conn.execute(f"DELETE FROM {table} WHERE story_id = ?", (clean_story_id,))

    conn.execute("DELETE FROM story_profiles WHERE story_id = ?", (clean_story_id,))
