from __future__ import annotations

import json
import sqlite3
from hashlib import sha256
from typing import Any


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _json_loads_list(value: Any) -> list:
    if isinstance(value, list):
        return list(value)
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return list(parsed) if isinstance(parsed, list) else []


def _story_id_or_none(conn: sqlite3.Connection, story_id: Any) -> str | None:
    clean_story_id = str(story_id or "").strip()
    if not clean_story_id:
        return None
    row = conn.execute(
        "SELECT story_id FROM stories WHERE story_id = ? AND deleted_at IS NULL",
        (clean_story_id,),
    ).fetchone()
    return clean_story_id if row else None


def sync_global_setting(conn: sqlite3.Connection, key: str, payload) -> None:
    clean_key = str(key or "").strip()
    if not clean_key:
        raise ValueError("Global setting key cannot be empty.")
    conn.execute(
        """
        INSERT INTO global_settings (setting_key, payload_json, created_at, updated_at)
        VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ON CONFLICT(setting_key) DO UPDATE SET
            payload_json = excluded.payload_json,
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        """,
        (clean_key, _json_dumps(payload)),
    )


def load_global_setting(conn: sqlite3.Connection, key: str):
    clean_key = str(key or "").strip()
    row = conn.execute(
        """
        SELECT payload_json
        FROM global_settings
        WHERE setting_key = ?
        """,
        (clean_key,),
    ).fetchone()
    if not row:
        return None
    value = row["payload_json"] if isinstance(row, sqlite3.Row) else row[0]
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def sync_story_profile(conn: sqlite3.Connection, story_id: str, profile: dict) -> dict:
    clean_story_id = _story_id_or_none(conn, story_id)
    if not clean_story_id:
        return dict(profile or {})
    payload = dict(profile or {})
    conn.execute(
        """
        INSERT INTO story_profiles (
            story_id, profile_json, worldline_id, worldline_name, retrieval_mode,
            created_at, updated_at
        )
        VALUES (
            ?, ?, ?, ?, ?,
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        )
        ON CONFLICT(story_id) DO UPDATE SET
            profile_json = excluded.profile_json,
            worldline_id = excluded.worldline_id,
            worldline_name = excluded.worldline_name,
            retrieval_mode = excluded.retrieval_mode,
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        """,
        (
            clean_story_id,
            _json_dumps(payload),
            str(payload.get("worldline_id") or "").strip() or None,
            str(payload.get("worldline_name") or payload.get("worldline_label") or "").strip() or None,
            str(payload.get("retrieval_mode") or "").strip() or None,
        ),
    )
    return payload


def load_story_profile_row(conn: sqlite3.Connection, story_id: str) -> dict:
    clean_story_id = str(story_id or "").strip()
    row = conn.execute(
        """
        SELECT profile_json
        FROM story_profiles
        WHERE story_id = ?
        """,
        (clean_story_id,),
    ).fetchone()
    if not row:
        return {}
    return _json_loads_dict(row["profile_json"] if isinstance(row, sqlite3.Row) else row[0])


def _rule_id(scope: str, story_id: str | None, capability: str, content: str) -> str:
    seed = f"{scope}:{story_id or ''}:{capability}:{content}"
    return "rule_" + sha256(seed.encode("utf-8")).hexdigest()[:24]


def sync_rules_payload(conn: sqlite3.Connection, scope: str, rules: dict, story_id: str | None = None) -> dict:
    clean_scope = str(scope or "").strip()
    if clean_scope not in {"global", "project", "story"}:
        raise ValueError("Rules scope must be global, project, or story.")
    clean_story_id = _story_id_or_none(conn, story_id) if clean_scope == "story" else None
    normalized = dict(rules or {})
    active_ids: list[str] = []
    for capability, raw_items in normalized.items():
        items = raw_items if isinstance(raw_items, list) else []
        for index, raw_content in enumerate(items, start=1):
            content = str(raw_content or "").strip()
            if not content:
                continue
            rule_id = _rule_id(clean_scope, clean_story_id, str(capability), content)
            active_ids.append(rule_id)
            conn.execute(
                """
                INSERT INTO rules (
                    rule_id, scope, story_id, capability, content, enabled, priority,
                    source, metadata_json, created_at, updated_at, deleted_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, 1, ?, 'manual', ?,
                    strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                    strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                    NULL
                )
                ON CONFLICT(rule_id) DO UPDATE SET
                    scope = excluded.scope,
                    story_id = excluded.story_id,
                    capability = excluded.capability,
                    content = excluded.content,
                    priority = excluded.priority,
                    metadata_json = excluded.metadata_json,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                    deleted_at = NULL
                """,
                (
                    rule_id,
                    clean_scope,
                    clean_story_id,
                    str(capability),
                    content,
                    50 + index,
                    _json_dumps({"index": index}),
                ),
            )
    params: list[Any] = [clean_scope]
    story_clause = "story_id IS NULL"
    if clean_scope == "story":
        story_clause = "story_id = ?"
        params.append(clean_story_id)
    if active_ids:
        placeholders = ",".join("?" for _ in active_ids)
        conn.execute(
            f"""
            UPDATE rules
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE scope = ? AND {story_clause}
              AND rule_id NOT IN ({placeholders}) AND deleted_at IS NULL
            """,
            (*params, *active_ids),
        )
    else:
        conn.execute(
            f"""
            UPDATE rules
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE scope = ? AND {story_clause} AND deleted_at IS NULL
            """,
            tuple(params),
        )
    return normalized


def load_rules_payload(conn: sqlite3.Connection, scope: str, story_id: str | None = None) -> dict:
    clean_scope = str(scope or "").strip()
    clean_story_id = str(story_id or "").strip()
    if clean_scope == "story":
        rows = conn.execute(
            """
            SELECT capability, content
            FROM rules
            WHERE scope = 'story' AND story_id = ? AND deleted_at IS NULL AND enabled = 1
            ORDER BY capability, priority, created_at, rule_id
            """,
            (clean_story_id,),
        ).fetchall()
    elif clean_scope == "global":
        rows = conn.execute(
            """
            SELECT capability, content
            FROM rules
            WHERE scope = 'global' AND story_id IS NULL AND deleted_at IS NULL AND enabled = 1
            ORDER BY capability, priority, created_at, rule_id
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT capability, content
            FROM rules
            WHERE scope = 'project' AND story_id IS NULL AND deleted_at IS NULL AND enabled = 1
            ORDER BY capability, priority, created_at, rule_id
            """
        ).fetchall()
    payload: dict[str, list[str]] = {}
    for row in rows:
        capability = row["capability"] if isinstance(row, sqlite3.Row) else row[0]
        content = row["content"] if isinstance(row, sqlite3.Row) else row[1]
        payload.setdefault(str(capability), []).append(str(content))
    return payload


def sync_prompt_options_payload(
    conn: sqlite3.Connection,
    scope: str,
    options: list[dict],
    story_id: str | None = None,
) -> list[dict]:
    clean_scope = str(scope or "").strip()
    if clean_scope not in {"global", "project", "story"}:
        raise ValueError("Prompt option scope must be global, project, or story.")
    clean_story_id = _story_id_or_none(conn, story_id) if clean_scope == "story" else None
    normalized = [dict(item) for item in options if isinstance(item, dict)]
    active_ids: list[str] = []
    for item in normalized:
        option_id = str(item.get("id") or item.get("option_id") or "").strip()
        if not option_id:
            seed = _json_dumps(item)
            option_id = "prompt_" + sha256(seed.encode("utf-8")).hexdigest()[:24]
        active_ids.append(option_id)
        tags = item.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        conn.execute(
            """
            INSERT INTO prompt_options (
                option_id, scope, story_id, capability, category, slot, name, content,
                enabled, built_in, priority, source, source_kind, source_ref, tags_json,
                created_at, updated_at, deleted_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                NULL
            )
            ON CONFLICT(option_id) DO UPDATE SET
                scope = excluded.scope,
                story_id = excluded.story_id,
                capability = excluded.capability,
                category = excluded.category,
                slot = excluded.slot,
                name = excluded.name,
                content = excluded.content,
                enabled = excluded.enabled,
                built_in = excluded.built_in,
                priority = excluded.priority,
                source = excluded.source,
                source_kind = excluded.source_kind,
                source_ref = excluded.source_ref,
                tags_json = excluded.tags_json,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                deleted_at = NULL
            """,
            (
                option_id,
                clean_scope,
                clean_story_id,
                str(item.get("capability") or "all"),
                str(item.get("category") or "custom"),
                str(item.get("slot") or "custom"),
                str(item.get("name") or option_id),
                str(item.get("content") or ""),
                1 if item.get("enabled", True) else 0,
                1 if item.get("built_in", False) else 0,
                int(item.get("priority") or 50),
                str(item.get("source") or "manual"),
                str(item.get("source_kind") or "").strip() or None,
                str(item.get("source_ref") or "").strip() or None,
                _json_dumps(tags),
            ),
        )
    params: list[Any] = [clean_scope]
    story_clause = "story_id IS NULL"
    if clean_scope == "story":
        story_clause = "story_id = ?"
        params.append(clean_story_id)
    if active_ids:
        placeholders = ",".join("?" for _ in active_ids)
        conn.execute(
            f"""
            UPDATE prompt_options
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE scope = ? AND {story_clause}
              AND option_id NOT IN ({placeholders}) AND deleted_at IS NULL
            """,
            (*params, *active_ids),
        )
    else:
        conn.execute(
            f"""
            UPDATE prompt_options
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE scope = ? AND {story_clause} AND deleted_at IS NULL
            """,
            tuple(params),
        )
    return normalized


def load_prompt_options_payload(conn: sqlite3.Connection, scope: str, story_id: str | None = None) -> list[dict]:
    clean_scope = str(scope or "").strip()
    clean_story_id = str(story_id or "").strip()
    if clean_scope == "story":
        rows = conn.execute(
            """
            SELECT option_id, capability, category, slot, name, content, enabled,
                   built_in, priority, source, source_kind, source_ref, tags_json
            FROM prompt_options
            WHERE scope = 'story' AND story_id = ? AND deleted_at IS NULL
            ORDER BY priority, lower(name), option_id
            """,
            (clean_story_id,),
        ).fetchall()
    elif clean_scope == "global":
        rows = conn.execute(
            """
            SELECT option_id, capability, category, slot, name, content, enabled,
                   built_in, priority, source, source_kind, source_ref, tags_json
            FROM prompt_options
            WHERE scope = 'global' AND story_id IS NULL AND deleted_at IS NULL
            ORDER BY priority, lower(name), option_id
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT option_id, capability, category, slot, name, content, enabled,
                   built_in, priority, source, source_kind, source_ref, tags_json
            FROM prompt_options
            WHERE scope = 'project' AND story_id IS NULL AND deleted_at IS NULL
            ORDER BY priority, lower(name), option_id
            """
        ).fetchall()
    items: list[dict] = []
    for row in rows:
        item = {
            "id": row["option_id"] if isinstance(row, sqlite3.Row) else row[0],
            "scope": clean_scope,
            "capability": row["capability"] if isinstance(row, sqlite3.Row) else row[1],
            "category": row["category"] if isinstance(row, sqlite3.Row) else row[2],
            "slot": row["slot"] if isinstance(row, sqlite3.Row) else row[3],
            "name": row["name"] if isinstance(row, sqlite3.Row) else row[4],
            "content": row["content"] if isinstance(row, sqlite3.Row) else row[5],
            "enabled": bool(row["enabled"] if isinstance(row, sqlite3.Row) else row[6]),
            "built_in": bool(row["built_in"] if isinstance(row, sqlite3.Row) else row[7]),
            "priority": row["priority"] if isinstance(row, sqlite3.Row) else row[8],
            "source": row["source"] if isinstance(row, sqlite3.Row) else row[9],
            "tags": _json_loads_list(row["tags_json"] if isinstance(row, sqlite3.Row) else row[12]),
        }
        source_kind = row["source_kind"] if isinstance(row, sqlite3.Row) else row[10]
        source_ref = row["source_ref"] if isinstance(row, sqlite3.Row) else row[11]
        if source_kind:
            item["source_kind"] = source_kind
        if source_ref:
            item["source_ref"] = source_ref
        items.append(item)
    return items
