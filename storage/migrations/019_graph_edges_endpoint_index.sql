-- 019_graph_edges_endpoint_index.sql
-- 补建 graph_edges 端点索引（017 迁移遗留修复）。
-- 017 为改造时序字段，采用「建 graph_edges_new → 搬运数据 → DROP TABLE graph_edges →
-- RENAME」的方式重建该表；DROP 会连带删除 001 建立的 idx_graph_edges_source /
-- idx_graph_edges_target，但重建后仅补了 idx_ge_valid（覆盖 source+target+有效区间，
-- 不含 relation_type）。导致按「端点 + 关系类型」过滤的查询（如查某实体的师徒/隶属边）
-- 退化为全表扫描。本迁移补回两个端点索引，并保证可重复执行。

CREATE INDEX IF NOT EXISTS idx_graph_edges_source
    ON graph_edges(source_node_id, relation_type, deleted_at);

CREATE INDEX IF NOT EXISTS idx_graph_edges_target
    ON graph_edges(target_node_id, relation_type, deleted_at);
