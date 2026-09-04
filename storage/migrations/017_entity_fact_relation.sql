-- 017_entity_fact_relation.sql
-- 存储结构重构 P0：以实体为中心的 Entity-Fact-Relation 三层。
-- 纯加性改动，不修改任何现有列与读取逻辑。
-- 详见 docs/storage-refactor-plan.md。

-- ============ L1 实体主档 ============
CREATE TABLE IF NOT EXISTS entities (
    entity_id       TEXT PRIMARY KEY,
    entity_type     TEXT NOT NULL,          -- character|organization|location|item|ability|event|world_rule|...
    canonical_name  TEXT NOT NULL,          -- 归并后的规范名
    display_name    TEXT NOT NULL DEFAULT '',
    story_id        TEXT,
    worldline_id    TEXT,
    setting_scope   TEXT NOT NULL DEFAULT 'project',
    version_scope   TEXT NOT NULL DEFAULT 'project_main',  -- canon(原作) vs project_main(二创)
    alias_group_id  TEXT,
    summary         TEXT NOT NULL DEFAULT '',
    meta_json       TEXT NOT NULL DEFAULT '{}',
    importance      INTEGER NOT NULL DEFAULT 0,
    world_t         REAL,                   -- event 专用：世界内时间可排序键
    world_time_label TEXT,                  -- event 专用：人类可读时间标签
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    deleted_at TEXT,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE SET NULL,
    FOREIGN KEY (alias_group_id) REFERENCES entity_alias_groups(alias_group_id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_identity
    ON entities(entity_type, canonical_name, story_id, worldline_id, setting_scope, version_scope);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type, story_id);
CREATE INDEX IF NOT EXISTS idx_entities_world_t ON entities(entity_type, world_t);

-- ============ L2 事实（knowledge_items 加列） ============
ALTER TABLE knowledge_items ADD COLUMN entity_id TEXT;
ALTER TABLE knowledge_items ADD COLUMN fact_key TEXT;
ALTER TABLE knowledge_items ADD COLUMN chapter_no INTEGER;
ALTER TABLE knowledge_items ADD COLUMN valid_from_chapter INTEGER;
ALTER TABLE knowledge_items ADD COLUMN valid_to_chapter INTEGER;
ALTER TABLE knowledge_items ADD COLUMN superseded_by TEXT;
ALTER TABLE knowledge_items ADD COLUMN merge_policy TEXT NOT NULL DEFAULT 'append';

CREATE INDEX IF NOT EXISTS idx_ki_entity_slot
    ON knowledge_items(entity_id, fact_key, valid_from_chapter);
CREATE INDEX IF NOT EXISTS idx_ki_entity_valid
    ON knowledge_items(entity_id, valid_from_chapter, valid_to_chapter);
CREATE INDEX IF NOT EXISTS idx_ki_chapter ON knowledge_items(chapter_no);

-- ============ L3 关系（graph_edges 加时序列） ============
ALTER TABLE graph_edges ADD COLUMN valid_from_chapter INTEGER;
ALTER TABLE graph_edges ADD COLUMN valid_to_chapter INTEGER;
ALTER TABLE graph_edges ADD COLUMN merge_policy TEXT NOT NULL DEFAULT 'replace';
ALTER TABLE graph_edges ADD COLUMN chapter_no INTEGER;

CREATE INDEX IF NOT EXISTS idx_ge_valid
    ON graph_edges(source_node_id, target_node_id, valid_from_chapter, valid_to_chapter);

-- ============ L3 关系（graph_edges 端点改指向 entities） ============
-- 决策：废弃 graph_nodes 作为节点表，graph_edges 端点统一指向 entities.entity_id。
-- SQLite 无法直接改外键，故重建表。零数据环境下数据迁移为空。
CREATE TABLE graph_edges_new (
    edge_id TEXT PRIMARY KEY,
    story_id TEXT,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'directed',
    confidence REAL,
    evidence_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    valid_from_chapter INTEGER,
    valid_to_chapter INTEGER,
    merge_policy TEXT NOT NULL DEFAULT 'replace',
    chapter_no INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    deleted_at TEXT,
    FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE SET NULL,
    FOREIGN KEY (source_node_id) REFERENCES entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (target_node_id) REFERENCES entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (evidence_id) REFERENCES knowledge_evidence(evidence_id) ON DELETE SET NULL
);

INSERT INTO graph_edges_new (
    edge_id, story_id, source_node_id, target_node_id, relation_type, direction,
    confidence, evidence_id, metadata_json, valid_from_chapter, valid_to_chapter,
    merge_policy, chapter_no, created_at, updated_at, deleted_at
)
SELECT edge_id, story_id, source_node_id, target_node_id, relation_type, direction,
       confidence, evidence_id, metadata_json, valid_from_chapter, valid_to_chapter,
       merge_policy, chapter_no, created_at, updated_at, deleted_at
FROM graph_edges;

DROP TABLE graph_edges;
ALTER TABLE graph_edges_new RENAME TO graph_edges;

CREATE INDEX IF NOT EXISTS idx_ge_valid
    ON graph_edges(source_node_id, target_node_id, valid_from_chapter, valid_to_chapter);
