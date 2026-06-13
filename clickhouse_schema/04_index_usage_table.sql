-- =============================================================
-- PharosDB index_usage table
-- 来自 performance_schema.table_io_waits_summary_by_index_usage
-- 用于未使用索引 / 冗余索引自动检测
-- =============================================================
CREATE TABLE IF NOT EXISTS pharos_db.index_usage
(
    service_name    LowCardinality(String),
    collected_at    DateTime,
    object_schema   LowCardinality(String),
    object_name     String,
    index_name      String,
    count_read      UInt64,
    count_write     UInt64,
    count_fetch     UInt64,
    sum_timer_read  UInt64,
    sum_timer_write UInt64
)
ENGINE = ReplacingMergeTree(collected_at)
ORDER BY (service_name, object_schema, object_name, index_name)
PARTITION BY toYYYYMM(collected_at)
SETTINGS index_granularity = 8192;
