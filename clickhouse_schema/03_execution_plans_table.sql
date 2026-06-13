-- =============================================================
-- PharosDB execution_plans table
-- EXPLAIN FORMAT=JSON 历史版本存储，支持版本对比与基线追踪
-- 由 MySQLCollector._maybe_collect_explain() 每次采集周期自动写入
-- =============================================================
CREATE TABLE IF NOT EXISTS pharos_db.execution_plans
(
    plan_id        String,
    fingerprint    String,
    service_name   String,
    schema         String,
    plan_json      String,
    plan_summary   String,
    plan_hash      String,
    query_example  String,
    created_at     DateTime,
    instance_id    Int32
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (fingerprint, created_at)
SETTINGS index_granularity = 8192;
