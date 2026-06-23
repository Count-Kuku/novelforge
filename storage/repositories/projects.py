from __future__ import annotations

import sqlite3


def upsert_project_meta(
    conn: sqlite3.Connection,
    *,
    project_name: str,
    title: str | None = None,
    genre: str = "",
    description: str = "",
) -> dict:
    clean_name = str(project_name or "").strip()
    if not clean_name:
        raise ValueError("Project name cannot be empty.")
    clean_title = str(title or clean_name).strip() or clean_name
    conn.execute(
        """
        INSERT INTO project_meta (project_id, name, title, genre, description, created_at, updated_at)
        VALUES (
            lower(hex(randomblob(16))),
            ?,
            ?,
            ?,
            ?,
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        )
        ON CONFLICT(name) DO UPDATE SET
            title = excluded.title,
            genre = excluded.genre,
            description = excluded.description,
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        """,
        (clean_name, clean_title, str(genre or ""), str(description or "")),
    )
    row = conn.execute(
        "SELECT project_id, name, title, genre, description, created_at, updated_at FROM project_meta WHERE name = ?",
        (clean_name,),
    ).fetchone()
    return dict(row)


def get_project_meta(conn: sqlite3.Connection, project_name: str) -> dict | None:
    row = conn.execute(
        "SELECT project_id, name, title, genre, description, created_at, updated_at FROM project_meta WHERE name = ?",
        (str(project_name or "").strip(),),
    ).fetchone()
    return dict(row) if row else None
