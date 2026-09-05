-- 018_sequence_order.sql
-- 资料时间线排序键（D8/F18）：timeline_events 按「段落顺序 × 段内顺序」原生排序。
-- sequence_order 由构造器计算（source_segment_index × K + order_hint），sync 写入。
-- 注：仅加到 knowledge_items（确认后原生排序）；pending 队列中该值经 content_json 携带，无需独立列。
-- 纯加性改动，不影响现有列与读取逻辑。

ALTER TABLE knowledge_items ADD COLUMN sequence_order INTEGER;

CREATE INDEX IF NOT EXISTS idx_ki_sequence_order ON knowledge_items(sequence_order);
