-- =============================================================
-- PharosDB lock_waits table
-- 锁等待 / 死锁事件快照，来自 performance_schema.data_lock_waits
-- 轮询周期：有锁时 5s，无锁时 30s（自适应）
-- =============================================================
CREATE TABLE IF NOT EXISTS pharos_db.lock_waits
(
    service_name           LowCardinality(String),
    collected_at           DateTime,

    -- 等待方（被阻塞的事务）
    waiting_trx_id         String,
    waiting_thread_id      UInt64,
    waiting_query          String,
    waiting_trx_started    DateTime,
    waiting_age_seconds    UInt32,

    -- 阻塞方（持锁的事务）
    blocking_trx_id        String,
    blocking_thread_id     UInt64,
    blocking_query         String,

    -- 锁对象
    lock_type              LowCardinality(String),
    lock_mode              LowCardinality(String),
    lock_object_schema     LowCardinality(String),
    lock_object_table      LowCardinality(String),
    lock_index             String,
    lock_data              String,

    -- 死锁标记（DFS 环检测结果）
    is_deadlock            UInt8 DEFAULT 0
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(collected_at)
ORDER BY (service_name, collected_at, waiting_trx_id)
TTL collected_at + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;
