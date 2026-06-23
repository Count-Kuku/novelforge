WITH ranked_project_assets AS (
    SELECT
        asset_id,
        ROW_NUMBER() OVER (
            PARTITION BY asset_type, logical_key
            ORDER BY updated_at DESC, created_at DESC, asset_id DESC
        ) AS rank
    FROM asset_files
    WHERE story_id IS NULL AND deleted_at IS NULL
)
UPDATE asset_files
SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
WHERE asset_id IN (
    SELECT asset_id FROM ranked_project_assets WHERE rank > 1
);

WITH ranked_story_assets AS (
    SELECT
        asset_id,
        ROW_NUMBER() OVER (
            PARTITION BY story_id, asset_type, logical_key
            ORDER BY updated_at DESC, created_at DESC, asset_id DESC
        ) AS rank
    FROM asset_files
    WHERE story_id IS NOT NULL AND deleted_at IS NULL
)
UPDATE asset_files
SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
WHERE asset_id IN (
    SELECT asset_id FROM ranked_story_assets WHERE rank > 1
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_asset_files_project_active_unique
ON asset_files(asset_type, logical_key)
WHERE story_id IS NULL AND deleted_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_asset_files_story_active_unique
ON asset_files(story_id, asset_type, logical_key)
WHERE story_id IS NOT NULL AND deleted_at IS NULL;
