CREATE TABLE IF NOT EXISTS asset_payloads (
    asset_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (asset_id) REFERENCES asset_files(asset_id) ON DELETE CASCADE
);
