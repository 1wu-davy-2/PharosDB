-- ============================================================================
-- PMM QAN Metrics Table — 完整建表语句
-- 来源：Percona PMM v3.8.0 — qan-api2/migrations/sql/01_init.up.sql
--       合并迁移 02 ~ 22 的所有 ALTER TABLE ADD COLUMN
-- 引擎：MergeTree，按天分区 (PARTITION BY toYYYYMMDD(period_start))
-- ============================================================================

CREATE TABLE IF NOT EXISTS metrics (
  -- ==========================================================================
  -- 主维度 (Main Dimensions)
  -- ==========================================================================
  `queryid` LowCardinality(String) COMMENT 'hash of query fingerprint',
  `service_name` LowCardinality(String) COMMENT 'Name of service (IP or hostname of DB server by default)',
  `database` LowCardinality(String) COMMENT 'PostgreSQL: database',
  `schema` LowCardinality(String) COMMENT 'MySQL: database; PostgreSQL: schema',
  `username` LowCardinality(String) COMMENT 'client user name',
  `client_host` LowCardinality(String) COMMENT 'client IP or hostname',

  -- ==========================================================================
  -- 标准标签 (Standard Labels)
  -- ==========================================================================
  `replication_set` LowCardinality(String) COMMENT 'Name of replication set',
  `cluster` LowCardinality(String) COMMENT 'Cluster name',
  `service_type` LowCardinality(String) COMMENT 'Type of service',
  `service_id` LowCardinality(String) COMMENT 'Service identifier',           -- m05
  `environment` LowCardinality(String) COMMENT 'Environment name',
  `az` LowCardinality(String) COMMENT 'Availability zone',
  `region` LowCardinality(String) COMMENT 'Region name',
  `node_model` LowCardinality(String) COMMENT 'Node model',
  `node_id` LowCardinality(String) COMMENT 'Node identifier',                 -- m05
  `node_name` LowCardinality(String) COMMENT 'Node name',                     -- m05
  `node_type` LowCardinality(String) COMMENT 'Node type',                     -- m05
  `machine_id` LowCardinality(String) COMMENT 'Machine identifier',           -- m05
  `container_name` LowCardinality(String) COMMENT 'Container name',
  `container_id` LowCardinality(String) COMMENT 'Container identifier',       -- m05

  -- ==========================================================================
  -- 扩展维度 (Extended Dimensions) — m11, m12
  -- ==========================================================================
  `top_queryid` LowCardinality(String) COMMENT 'Top-level queryid',           -- m11
  `application_name` LowCardinality(String) COMMENT 'Application name',       -- m11
  `planid` LowCardinality(String) COMMENT 'Plan identifier',                  -- m11
  `cmd_type` LowCardinality(String) COMMENT 'Command type (SELECT, INSERT...)', -- m12

  -- ==========================================================================
  -- 自定义标签 (Custom Labels)
  -- ==========================================================================
  `labels.key` Array(LowCardinality(String)) COMMENT 'Custom labels names',
  `labels.value` Array(LowCardinality(String)) COMMENT 'Custom labels values',

  -- ==========================================================================
  -- Agent 元信息 (Agent Metadata)
  -- ==========================================================================
  `agent_id` LowCardinality(String) COMMENT 'Identifier of agent that collect and send metrics',
  `agent_type` Enum8(
    'qan-agent-type-invalid' = 0,
    'qan-mysql-perfschema-agent' = 1,
    'qan-mysql-slowlog-agent' = 2,
    'qan-mongodb-profiler-agent' = 3,
    'qan-postgresql-pgstatements-agent' = 4,
    'qan-postgresql-pgstatmonitor-agent' = 5,
    'qan-mongodb-mongolog-agent' = 6
  ) COMMENT 'Agent Type that collects metrics: slowlog, perf schema, etc.',

  -- ==========================================================================
  -- 时间维度 (Time Bucket)
  -- ==========================================================================
  `period_start` DateTime COMMENT 'Time when collection of bucket started',
  `period_length` UInt32 COMMENT 'Duration of collection bucket',

  -- ==========================================================================
  -- 查询指纹与示例 (Query Fingerprint & Example)
  -- ==========================================================================
  `fingerprint` LowCardinality(String) COMMENT 'mysql digest_text; query without data',
  `example` String COMMENT 'One of query example from set found in bucket',
  -- example_format 已在 m18 删除 (DROP COLUMN)
  `is_truncated` UInt8 COMMENT 'Indicates if query examples is too long and was truncated',
  `example_type` Enum8(
    'EXAMPLE_TYPE_INVALID' = 0,
    'RANDOM' = 1,
    'SLOWEST' = 2,
    'FASTEST' = 3,
    'WITH_ERROR' = 4
  ) COMMENT 'Indicates what query example was picked up',
  `example_metrics` String COMMENT 'Metrics of query example in JSON format.',
  `tables` Array(String) COMMENT 'Tables involved in the query',            -- m04

  -- ==========================================================================
  -- Explain 信息 — m16
  -- ==========================================================================
  `explain_fingerprint` String COMMENT 'Explain fingerprint',                -- m16
  `placeholders_count` UInt32 COMMENT 'Number of placeholders in query',     -- m16

  -- ==========================================================================
  -- 计划信息 (Plan Info) — m13, m14, m19
  -- ==========================================================================
  `top_query` LowCardinality(String) COMMENT 'Top query text',               -- m13
  `query_plan` LowCardinality(String) COMMENT 'Query execution plan',        -- m14
  `plan_summary` LowCardinality(String) COMMENT 'Plan summary',              -- m19

  -- ==========================================================================
  -- 直方图 (Histogram) — m15
  -- ==========================================================================
  `histogram_items` Array(String) COMMENT 'Histogram items in JSON format',  -- m15

  -- ==========================================================================
  -- 警告与错误计数 (Warnings & Errors)
  -- ==========================================================================
  `num_queries_with_warnings` Float32 COMMENT 'How many queries was with warnings in bucket',
  `warnings.code` Array(UInt32) COMMENT 'List of warnings',
  `warnings.count` Array(Float32) COMMENT 'Count of each warnings in bucket',
  `num_queries_with_errors` Float32 COMMENT 'How many queries was with error in bucket',
  `errors.code` Array(UInt64) COMMENT 'List of Last_errno',
  `errors.count` Array(UInt64) COMMENT 'Count of each Last_errno in bucket',
  `num_queries` Float32 COMMENT 'Amount queries in this bucket',

  -- ==========================================================================
  -- ====================== 以下是 Metrics 指标字段 ============================
  -- ==========================================================================

  -- --------------------------------------------------------------------------
  -- 1. Query Time（查询耗时）
  -- --------------------------------------------------------------------------
  `m_query_time_cnt` Float32,
  `m_query_time_sum` Float32 COMMENT 'The statement execution time in seconds.',
  `m_query_time_min` Float32 COMMENT 'Smallest value of query_time in bucket',
  `m_query_time_max` Float32 COMMENT 'Biggest value of query_time in bucket',
  `m_query_time_p99` Float32 COMMENT '99 percentile of value of query_time in bucket',

  -- --------------------------------------------------------------------------
  -- 2. Lock Time（锁等待时间）
  -- --------------------------------------------------------------------------
  `m_lock_time_cnt` Float32,
  `m_lock_time_sum` Float32 COMMENT 'The time to acquire locks in seconds.',
  `m_lock_time_min` Float32,
  `m_lock_time_max` Float32,
  `m_lock_time_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 3. Rows Sent（发送行数）
  -- --------------------------------------------------------------------------
  `m_rows_sent_cnt` Float32,
  `m_rows_sent_sum` Float32 COMMENT 'The number of rows sent to the client.',
  `m_rows_sent_min` Float32,
  `m_rows_sent_max` Float32,
  `m_rows_sent_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 4. Rows Examined（扫描行数 - SELECT）
  -- --------------------------------------------------------------------------
  `m_rows_examined_cnt` Float32,
  `m_rows_examined_sum` Float32 COMMENT 'Number of rows scanned - SELECT.',
  `m_rows_examined_min` Float32,
  `m_rows_examined_max` Float32,
  `m_rows_examined_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 5. Rows Affected（影响行数 - INSERT/UPDATE/DELETE）
  -- --------------------------------------------------------------------------
  `m_rows_affected_cnt` Float32,
  `m_rows_affected_sum` Float32 COMMENT 'Number of rows changed - UPDATE, DELETE, INSERT.',
  `m_rows_affected_min` Float32,
  `m_rows_affected_max` Float32,
  `m_rows_affected_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 6. Rows Read（读取行数）
  -- --------------------------------------------------------------------------
  `m_rows_read_cnt` Float32,
  `m_rows_read_sum` Float32 COMMENT 'The number of rows read from tables.',
  `m_rows_read_min` Float32,
  `m_rows_read_max` Float32,
  `m_rows_read_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 7. Merge Passes（归并趟数）
  -- --------------------------------------------------------------------------
  `m_merge_passes_cnt` Float32,
  `m_merge_passes_sum` Float32 COMMENT 'The number of merge passes that the sort algorithm has had to do.',
  `m_merge_passes_min` Float32,
  `m_merge_passes_max` Float32,
  `m_merge_passes_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 8. InnoDB I/O Read Ops
  -- --------------------------------------------------------------------------
  `m_innodb_io_r_ops_cnt` Float32,
  `m_innodb_io_r_ops_sum` Float32 COMMENT 'Counts the number of page read operations scheduled.',
  `m_innodb_io_r_ops_min` Float32,
  `m_innodb_io_r_ops_max` Float32,
  `m_innodb_io_r_ops_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 9. InnoDB I/O Read Bytes
  -- --------------------------------------------------------------------------
  `m_innodb_io_r_bytes_cnt` Float32,
  `m_innodb_io_r_bytes_sum` Float32 COMMENT 'Similar to innodb_IO_r_ops, but the unit is bytes.',
  `m_innodb_io_r_bytes_min` Float32,
  `m_innodb_io_r_bytes_max` Float32,
  `m_innodb_io_r_bytes_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 10. InnoDB I/O Read Wait
  -- --------------------------------------------------------------------------
  `m_innodb_io_r_wait_cnt` Float32,
  `m_innodb_io_r_wait_sum` Float32 COMMENT 'Shows how long (in seconds) it took InnoDB to actually read the data from storage.',
  `m_innodb_io_r_wait_min` Float32,
  `m_innodb_io_r_wait_max` Float32,
  `m_innodb_io_r_wait_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 11. InnoDB Record Lock Wait
  -- --------------------------------------------------------------------------
  `m_innodb_rec_lock_wait_cnt` Float32,
  `m_innodb_rec_lock_wait_sum` Float32 COMMENT 'Shows how long (in seconds) the query waited for row locks.',
  `m_innodb_rec_lock_wait_min` Float32,
  `m_innodb_rec_lock_wait_max` Float32,
  `m_innodb_rec_lock_wait_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 12. InnoDB Queue Wait
  -- --------------------------------------------------------------------------
  `m_innodb_queue_wait_cnt` Float32,
  `m_innodb_queue_wait_sum` Float32 COMMENT 'Shows how long (in seconds) the query spent either waiting to enter the InnoDB queue or inside that queue waiting for execution.',
  `m_innodb_queue_wait_min` Float32,
  `m_innodb_queue_wait_max` Float32,
  `m_innodb_queue_wait_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 13. InnoDB Pages Distinct
  -- --------------------------------------------------------------------------
  `m_innodb_pages_distinct_cnt` Float32,
  `m_innodb_pages_distinct_sum` Float32 COMMENT 'Counts approximately the number of unique pages the query accessed.',
  `m_innodb_pages_distinct_min` Float32,
  `m_innodb_pages_distinct_max` Float32,
  `m_innodb_pages_distinct_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 14. Query Length
  -- --------------------------------------------------------------------------
  `m_query_length_cnt` Float32,
  `m_query_length_sum` Float32 COMMENT 'Shows how long the query is.',
  `m_query_length_min` Float32,
  `m_query_length_max` Float32,
  `m_query_length_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 15. Bytes Sent
  -- --------------------------------------------------------------------------
  `m_bytes_sent_cnt` Float32,
  `m_bytes_sent_sum` Float32 COMMENT 'The number of bytes sent to all clients.',
  `m_bytes_sent_min` Float32,
  `m_bytes_sent_max` Float32,
  `m_bytes_sent_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 16. Temp Tables（内存临时表）
  -- --------------------------------------------------------------------------
  `m_tmp_tables_cnt` Float32,
  `m_tmp_tables_sum` Float32 COMMENT 'Number of temporary tables created on memory for the query.',
  `m_tmp_tables_min` Float32,
  `m_tmp_tables_max` Float32,
  `m_tmp_tables_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 17. Temp Disk Tables（磁盘临时表）
  -- --------------------------------------------------------------------------
  `m_tmp_disk_tables_cnt` Float32,
  `m_tmp_disk_tables_sum` Float32 COMMENT 'Number of temporary tables created on disk for the query.',
  `m_tmp_disk_tables_min` Float32,
  `m_tmp_disk_tables_max` Float32,
  `m_tmp_disk_tables_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 18. Temp Table Sizes
  -- --------------------------------------------------------------------------
  `m_tmp_table_sizes_cnt` Float32,
  `m_tmp_table_sizes_sum` Float32 COMMENT 'Total Size in bytes for all temporary tables used in the query.',
  `m_tmp_table_sizes_min` Float32,
  `m_tmp_table_sizes_max` Float32,
  `m_tmp_table_sizes_p99` Float32,

  -- ==========================================================================
  -- ====================== Boolean Metrics（布尔类指标） ========================
  -- 这些指标的 _sum 表示发生次数，_cnt 表示统计到的 bucket 数
  -- ==========================================================================

  -- --------------------------------------------------------------------------
  -- 19. Query Cache Hit
  -- --------------------------------------------------------------------------
  `m_qc_hit_cnt` Float32,
  `m_qc_hit_sum` Float32 COMMENT 'Query Cache hits.',

  -- --------------------------------------------------------------------------
  -- 20. Full Scan
  -- --------------------------------------------------------------------------
  `m_full_scan_cnt` Float32,
  `m_full_scan_sum` Float32 COMMENT 'The query performed a full table scan.',

  -- --------------------------------------------------------------------------
  -- 21. Full Join
  -- --------------------------------------------------------------------------
  `m_full_join_cnt` Float32,
  `m_full_join_sum` Float32 COMMENT 'The query performed a full join (a join without indexes).',

  -- --------------------------------------------------------------------------
  -- 22. Temp Table（隐式临时表）
  -- --------------------------------------------------------------------------
  `m_tmp_table_cnt` Float32,
  `m_tmp_table_sum` Float32 COMMENT 'The query created an implicit internal temporary table.',

  -- --------------------------------------------------------------------------
  -- 23. Temp Table On Disk
  -- --------------------------------------------------------------------------
  `m_tmp_table_on_disk_cnt` Float32,
  `m_tmp_table_on_disk_sum` Float32 COMMENT 'The querys temporary table was stored on disk.',

  -- --------------------------------------------------------------------------
  -- 24. Filesort
  -- --------------------------------------------------------------------------
  `m_filesort_cnt` Float32,
  `m_filesort_sum` Float32 COMMENT 'The query used a filesort.',

  -- --------------------------------------------------------------------------
  -- 25. Filesort On Disk
  -- --------------------------------------------------------------------------
  `m_filesort_on_disk_cnt` Float32,
  `m_filesort_on_disk_sum` Float32 COMMENT 'The filesort was performed on disk.',

  -- --------------------------------------------------------------------------
  -- 26. Select Full Range Join
  -- --------------------------------------------------------------------------
  `m_select_full_range_join_cnt` Float32,
  `m_select_full_range_join_sum` Float32 COMMENT 'The number of joins that used a range search on a reference table.',

  -- --------------------------------------------------------------------------
  -- 27. Select Range
  -- --------------------------------------------------------------------------
  `m_select_range_cnt` Float32,
  `m_select_range_sum` Float32 COMMENT 'The number of joins that used ranges on the first table.',

  -- --------------------------------------------------------------------------
  -- 28. Select Range Check
  -- --------------------------------------------------------------------------
  `m_select_range_check_cnt` Float32,
  `m_select_range_check_sum` Float32 COMMENT 'The number of joins without keys that check for key usage after each row.',

  -- --------------------------------------------------------------------------
  -- 29. Sort Range
  -- --------------------------------------------------------------------------
  `m_sort_range_cnt` Float32,
  `m_sort_range_sum` Float32 COMMENT 'The number of sorts that were done using ranges.',

  -- --------------------------------------------------------------------------
  -- 30. Sort Rows
  -- --------------------------------------------------------------------------
  `m_sort_rows_cnt` Float32,
  `m_sort_rows_sum` Float32 COMMENT 'The number of sorted rows.',

  -- --------------------------------------------------------------------------
  -- 31. Sort Scan
  -- --------------------------------------------------------------------------
  `m_sort_scan_cnt` Float32,
  `m_sort_scan_sum` Float32 COMMENT 'The number of sorts that were done by scanning the table.',

  -- --------------------------------------------------------------------------
  -- 32. No Index Used
  -- --------------------------------------------------------------------------
  `m_no_index_used_cnt` Float32,
  `m_no_index_used_sum` Float32 COMMENT 'The number of queries without index.',

  -- --------------------------------------------------------------------------
  -- 33. No Good Index Used
  -- --------------------------------------------------------------------------
  `m_no_good_index_used_cnt` Float32,
  `m_no_good_index_used_sum` Float32 COMMENT 'The number of queries without good index.',

  -- ==========================================================================
  -- ====================== MongoDB Metrics（MongoDB 指标） =====================
  -- ==========================================================================

  -- --------------------------------------------------------------------------
  -- 34. Docs Returned
  -- --------------------------------------------------------------------------
  `m_docs_returned_cnt` Float32,
  `m_docs_returned_sum` Float32 COMMENT 'The number of returned documents.',
  `m_docs_returned_min` Float32,
  `m_docs_returned_max` Float32,
  `m_docs_returned_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 35. Response Length
  -- --------------------------------------------------------------------------
  `m_response_length_cnt` Float32,
  `m_response_length_sum` Float32 COMMENT 'The response length of the query result in bytes.',
  `m_response_length_min` Float32,
  `m_response_length_max` Float32,
  `m_response_length_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 36. Docs Scanned
  -- --------------------------------------------------------------------------
  `m_docs_scanned_cnt` Float32,
  `m_docs_scanned_sum` Float32 COMMENT 'The number of scanned documents.',
  `m_docs_scanned_min` Float32,
  `m_docs_scanned_max` Float32,
  `m_docs_scanned_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 37. Docs Examined — m20
  -- --------------------------------------------------------------------------
  `m_docs_examined_cnt` Float32,
  `m_docs_examined_sum` Float32 COMMENT 'Total number of documents scanned during query execution',
  `m_docs_examined_min` Float32,
  `m_docs_examined_max` Float32,
  `m_docs_examined_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 38. Keys Examined — m20
  -- --------------------------------------------------------------------------
  `m_keys_examined_cnt` Float32,
  `m_keys_examined_sum` Float32 COMMENT 'Total number of index keys scanned during query execution',
  `m_keys_examined_min` Float32,
  `m_keys_examined_max` Float32,
  `m_keys_examined_p99` Float32,

  -- --------------------------------------------------------------------------
  -- 39. MongoDB Locks — m20
  -- --------------------------------------------------------------------------
  `m_locks_global_acquire_count_read_shared_cnt` Float32,
  `m_locks_global_acquire_count_read_shared_sum` Float32 COMMENT 'Number of times a global read lock was acquired during query execution',
  `m_locks_global_acquire_count_write_shared_cnt` Float32,
  `m_locks_global_acquire_count_write_shared_sum` Float32 COMMENT 'Number of times a global write lock was acquired during query execution',
  `m_locks_database_acquire_count_read_shared_cnt` Float32,
  `m_locks_database_acquire_count_read_shared_sum` Float32 COMMENT 'Number of times a read lock was acquired at the database level during query execution',
  `m_locks_database_acquire_wait_count_read_shared_cnt` Float32,
  `m_locks_database_acquire_wait_count_read_shared_sum` Float32 COMMENT 'Number of times a read lock at the database level was requested but had to wait before being granted',
  `m_locks_database_time_acquiring_micros_read_shared_cnt` Float32,
  `m_locks_database_time_acquiring_micros_read_shared_sum` Float32 COMMENT 'Indicates the time, spent acquiring a read lock at the database level during an operation',
  `m_locks_database_time_acquiring_micros_read_shared_min` Float32,
  `m_locks_database_time_acquiring_micros_read_shared_max` Float32,
  `m_locks_database_time_acquiring_micros_read_shared_p99` Float32,
  `m_locks_collection_acquire_count_read_shared_cnt` Float32,
  `m_locks_collection_acquire_count_read_shared_sum` Float32 COMMENT 'Number of times a read lock was acquired on a specific collection during operations',

  -- --------------------------------------------------------------------------
  -- 40. MongoDB Storage — m20
  -- --------------------------------------------------------------------------
  `m_storage_bytes_read_cnt` Float32,
  `m_storage_bytes_read_sum` Float32 COMMENT 'Total number of bytes read from storage during a specific operation',
  `m_storage_bytes_read_min` Float32,
  `m_storage_bytes_read_max` Float32,
  `m_storage_bytes_read_p99` Float32,
  `m_storage_time_reading_micros_cnt` Float32,
  `m_storage_time_reading_micros_sum` Float32 COMMENT 'Indicates the time, spent reading data from storage during an operation',
  `m_storage_time_reading_micros_min` Float32,
  `m_storage_time_reading_micros_max` Float32,
  `m_storage_time_reading_micros_p99` Float32,

  -- ==========================================================================
  -- ====================== PostgreSQL Metrics =================================
  -- ==========================================================================

  -- --------------------------------------------------------------------------
  -- 41. Shared Blocks — m02
  -- --------------------------------------------------------------------------
  `m_shared_blks_hit_cnt` Float32,
  `m_shared_blks_hit_sum` Float32 COMMENT 'Total number of shared block cache hits by the statement',
  `m_shared_blks_read_cnt` Float32,
  `m_shared_blks_read_sum` Float32 COMMENT 'Total number of shared blocks read by the statement.',
  `m_shared_blks_dirtied_cnt` Float32,
  `m_shared_blks_dirtied_sum` Float32 COMMENT 'Total number of shared blocks dirtied by the statement.',
  `m_shared_blks_written_cnt` Float32,
  `m_shared_blks_written_sum` Float32 COMMENT 'Total number of shared blocks written by the statement.',

  -- --------------------------------------------------------------------------
  -- 42. Local Blocks — m02
  -- --------------------------------------------------------------------------
  `m_local_blks_hit_cnt` Float32,
  `m_local_blks_hit_sum` Float32 COMMENT 'Total number of local block cache hits by the statement',
  `m_local_blks_read_cnt` Float32,
  `m_local_blks_read_sum` Float32 COMMENT 'Total number of local blocks read by the statement.',
  `m_local_blks_dirtied_cnt` Float32,
  `m_local_blks_dirtied_sum` Float32 COMMENT 'Total number of local blocks dirtied by the statement.',
  `m_local_blks_written_cnt` Float32,
  `m_local_blks_written_sum` Float32 COMMENT 'Total number of local blocks written by the statement.',

  -- --------------------------------------------------------------------------
  -- 43. Temp Blocks — m02
  -- --------------------------------------------------------------------------
  `m_temp_blks_read_cnt` Float32,
  `m_temp_blks_read_sum` Float32 COMMENT 'Total number of temp blocks read by the statement.',
  `m_temp_blks_written_cnt` Float32,
  `m_temp_blks_written_sum` Float32 COMMENT 'Total number of temp blocks written by the statement.',

  -- --------------------------------------------------------------------------
  -- 44. Block I/O Time — m02 + m17 (renamed + local added)
  --     m02 added: m_blk_read_time_*, m_blk_write_time_*
  --     m17 renamed: m_blk_read_time_* → m_shared_blk_read_time_*
  --                  m_blk_write_time_* → m_shared_blk_write_time_*
  --     m17 added:   m_local_blk_read_time_*, m_local_blk_write_time_*
  -- --------------------------------------------------------------------------
  `m_shared_blk_read_time_cnt` Float32,
  `m_shared_blk_read_time_sum` Float32 COMMENT 'Total time the statement spent reading shared blocks, in milliseconds (if track_io_timing is enabled, otherwise zero).',
  `m_shared_blk_write_time_cnt` Float32,
  `m_shared_blk_write_time_sum` Float32 COMMENT 'Total time the statement spent writing shared blocks, in milliseconds (if track_io_timing is enabled, otherwise zero).',
  `m_local_blk_read_time_cnt` Float32,
  `m_local_blk_read_time_sum` Float32 COMMENT 'Total time the statement spent reading local blocks, in milliseconds (if track_io_timing is enabled, otherwise zero).',
  `m_local_blk_write_time_cnt` Float32,
  `m_local_blk_write_time_sum` Float32 COMMENT 'Total time the statement spent writing local blocks, in milliseconds (if track_io_timing is enabled, otherwise zero).',

  -- --------------------------------------------------------------------------
  -- 45. CPU Time — m07
  -- --------------------------------------------------------------------------
  `m_cpu_user_time_cnt` Float32,
  `m_cpu_user_time_sum` Float32 COMMENT 'Total time user spent in query',
  `m_cpu_sys_time_cnt` Float32,
  `m_cpu_sys_time_sum` Float32 COMMENT 'Total time system spent in query',

  -- --------------------------------------------------------------------------
  -- 46. Plans & WAL — m09, m10, m22
  -- --------------------------------------------------------------------------
  `m_plans_calls_cnt` Float32,
  `m_plans_calls_sum` Float32 COMMENT 'Total number of planned calls',
  `m_plan_time_cnt` Float32 COMMENT 'Count of plan time.',
  `m_plan_time_sum` Float32 COMMENT 'Sum of plan time.',
  `m_plan_time_min` Float32 COMMENT 'Min of plan time.',
  `m_plan_time_max` Float32 COMMENT 'Max of plan time.',
  `m_wal_records_cnt` Float32,
  `m_wal_records_sum` Float32 COMMENT 'Total number of WAL (Write-ahead logging) records',
  `m_wal_fpi_cnt` Float32,
  `m_wal_fpi_sum` Float32 COMMENT 'Total number of FPI (full page images) in WAL (Write-ahead logging) records',
  `m_wal_bytes_cnt` Float32,
  `m_wal_bytes_sum` Float32 COMMENT 'Total bytes of WAL (Write-ahead logging) records',
  `m_wal_buffers_full_cnt` Float32,
  `m_wal_buffers_full_sum` Float32 COMMENT 'Total number of times WAL buffers become full',
  `m_parallel_workers_to_launch_cnt` Float32,
  `m_parallel_workers_to_launch_sum` Float32 COMMENT 'Total number of parallel workers to launch',
  `m_parallel_workers_launched_cnt` Float32,
  `m_parallel_workers_launched_sum` Float32 COMMENT 'Total number of parallel workers launched'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(period_start)
ORDER BY (
  queryid,
  service_name,
  database,
  schema,
  username,
  client_host,
  period_start
)
SETTINGS index_granularity = 8192;
