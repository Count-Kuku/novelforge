"""Credential metadata and explainable automatic-configuration storage."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def _json(value: Any, fallback) -> str:
    return json.dumps(value if isinstance(value, type(fallback)) else fallback, ensure_ascii=False, sort_keys=True)


def upsert_credential_reference_row(conn: sqlite3.Connection, metadata: dict) -> dict:
    credential_ref = str(metadata.get("credential_ref") or "").strip()
    purpose = str(metadata.get("purpose") or "").strip()
    if not credential_ref or not purpose:
        raise ValueError("Credential reference and purpose are required.")
    conn.execute(
        """
        INSERT INTO credential_references (
            credential_ref, purpose, owner_id, backend, fingerprint, last_four,
            metadata_json, created_at, updated_at, deleted_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            strftime('%Y-%m-%dT%H:%M:%SZ','now'),
            strftime('%Y-%m-%dT%H:%M:%SZ','now'), NULL
        )
        ON CONFLICT(credential_ref) DO UPDATE SET
            purpose=excluded.purpose, owner_id=excluded.owner_id,
            backend=excluded.backend, fingerprint=excluded.fingerprint,
            last_four=excluded.last_four, metadata_json=excluded.metadata_json,
            updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'), deleted_at=NULL
        """,
        (
            credential_ref, purpose, str(metadata.get("owner_id") or ""),
            str(metadata.get("backend") or ""), str(metadata.get("fingerprint") or ""),
            str(metadata.get("last_four") or ""), _json(metadata.get("metadata"), {}),
        ),
    )
    return load_credential_reference_row(conn, credential_ref)


def load_credential_reference_row(conn: sqlite3.Connection, credential_ref: str) -> dict:
    row = conn.execute(
        "SELECT * FROM credential_references WHERE credential_ref=? AND deleted_at IS NULL",
        (str(credential_ref or "").strip(),),
    ).fetchone()
    if not row:
        return {}
    result = dict(row)
    try:
        result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
    except (TypeError, ValueError):
        result["metadata"] = {}
    return result


def mark_credential_reference_deleted_row(conn: sqlite3.Connection, credential_ref: str) -> bool:
    cursor = conn.execute(
        """
        UPDATE credential_references
        SET deleted_at=COALESCE(deleted_at,strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
        WHERE credential_ref=? AND deleted_at IS NULL
        """,
        (str(credential_ref or "").strip(),),
    )
    return cursor.rowcount > 0


def load_automatic_configuration_state_row(conn: sqlite3.Connection, config_key: str) -> dict:
    row = conn.execute(
        "SELECT * FROM automatic_configuration_state WHERE config_key=?",
        (str(config_key or "").strip(),),
    ).fetchone()
    if not row:
        return {}
    result = dict(row)
    for column, fallback in (("settings_json", {}), ("locked_fields_json", [])):
        try:
            result[column.removesuffix("_json")] = json.loads(result.pop(column) or _json(fallback, fallback))
        except (TypeError, ValueError):
            result[column.removesuffix("_json")] = fallback
    return result


def save_automatic_configuration_row(
    conn: sqlite3.Connection,
    *,
    state: dict,
    revision: dict | None = None,
) -> dict:
    config_key = str(state.get("config_key") or "").strip()
    operation = str(state.get("operation") or "").strip()
    if not config_key or not operation:
        raise ValueError("Automatic configuration key and operation are required.")
    conn.execute(
        """
        INSERT INTO automatic_configuration_state (
            config_key, project_name, story_id, operation, settings_json,
            locked_fields_json, source_revision_id, created_at, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            strftime('%Y-%m-%dT%H:%M:%SZ','now'),
            strftime('%Y-%m-%dT%H:%M:%SZ','now')
        )
        ON CONFLICT(config_key) DO UPDATE SET
            project_name=excluded.project_name, story_id=excluded.story_id,
            operation=excluded.operation, settings_json=excluded.settings_json,
            locked_fields_json=excluded.locked_fields_json,
            source_revision_id=excluded.source_revision_id,
            updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
        """,
        (
            config_key, str(state.get("project_name") or ""), str(state.get("story_id") or ""),
            operation, _json(state.get("settings"), {}), _json(state.get("locked_fields"), []),
            str(state.get("source_revision_id") or "") or None,
        ),
    )
    if revision:
        conn.execute(
            """
            INSERT OR IGNORE INTO automatic_configuration_revisions (
                revision_id, config_key, project_name, story_id, operation,
                before_json, after_json, diff_json, reasons_json, signals_json,
                locked_fields_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            """,
            (
                str(revision.get("revision_id") or ""), config_key,
                str(state.get("project_name") or ""), str(state.get("story_id") or ""), operation,
                _json(revision.get("before"), {}), _json(revision.get("after"), {}),
                _json(revision.get("diff"), {}), _json(revision.get("reasons"), []),
                _json(revision.get("signals"), {}), _json(state.get("locked_fields"), []),
            ),
        )
    return load_automatic_configuration_state_row(conn, config_key)


def list_automatic_configuration_revision_rows(
    conn: sqlite3.Connection, config_key: str, *, limit: int = 50,
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT * FROM automatic_configuration_revisions
        WHERE config_key=? ORDER BY created_at DESC, rowid DESC LIMIT ?
        """,
        (str(config_key or "").strip(), max(1, min(int(limit), 200))),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        for column, fallback in (
            ("before_json", {}), ("after_json", {}), ("diff_json", {}),
            ("reasons_json", []), ("signals_json", {}), ("locked_fields_json", []),
        ):
            try:
                item[column.removesuffix("_json")] = json.loads(item.pop(column) or _json(fallback, fallback))
            except (TypeError, ValueError):
                item[column.removesuffix("_json")] = fallback
        result.append(item)
    return result
