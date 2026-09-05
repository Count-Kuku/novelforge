-- 020_drop_graph_nodes.sql
-- 删除废弃的 graph_nodes 表。
-- schema 17 已把关系图节点统一收编进 entities 表，graph_edges 端点改为指向
-- entities.entity_id；graph_nodes 自此停写不停表，仅作为兼容空表保留。
-- 现项目无历史数据、无需向后兼容，正式删除该表。其索引 idx_graph_nodes_lookup
-- 随表自动删除；graph_edges 自 017 重建后已无指向 graph_nodes 的外键，删除安全。

DROP TABLE IF EXISTS graph_nodes;
