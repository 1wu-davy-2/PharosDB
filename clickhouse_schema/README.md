# PMM QAN ClickHouse Schema — 字段完整映射

> 来源：Percona PMM v3.8.0  
> 路径：`qan-api2/migrations/sql/` (22 个迁移文件)  
> 建表引擎：`MergeTree()` / 集群模式 `ReplicatedMergeTree()`  
> 分区：`PARTITION BY toYYYYMMDD(period_start)` — 按天分区

---

## 迁移追踪 (Migration Traceability)

| 迁移 | 文件 | 操作 |
|------|------|------|
| **01** | `01_init.up.sql` | 🔨 CREATE TABLE metrics（主维度 + 全部 MySQL 指标 + MongoDB 指标 + Boolean 指标） |
| **02** | `02_postgresql_columns.up.sql` | ➕ ADD PostgreSQL shared/local/temp blocks + blk_read/write_time |
| **03** | `03_add_agent_type.up.sql` | ✏️ MODIFY agent_type Enum：增加 `postgresql-pgstatstatements` |
| **04** | `04_add_tables_column.up.sql` | ➕ ADD `tables` Array(String) |
| **05** | `05_add_more_std_labels.up.sql` | ➕ ADD 6 个标准标签：node_id/nome/type, machine_id, container_id, service_id |
| **06** | `06_change_agent_type.up.sql` | ✏️ MODIFY agent_type：值加 `qan-` 前缀 |
| **07** | `07_pg_stat_monitor_columns.up.sql` | ➕ ADD m_cpu_user_time_*, m_cpu_sys_time_* |
| **08** | `08_add_agent_type_pg_stat_monitor.up.sql` | ✏️ MODIFY agent_type：增加 `qan-postgresql-pgstatmonitor-agent` |
| **09** | `09_pg_stat_monitor_09_columns.up.sql` | ➕ ADD m_plans_calls_*, m_wal_records_*, m_wal_fpi_* |
| **10** | `10_pg_stat_monitor_09_columns_plan.up.sql` | ➕ ADD m_wal_bytes_*, m_plan_time_* (cnt/sum/min/max) |
| **11** | `11_pg_stat_monitor_09_dimensions.up.sql` | ➕ ADD top_queryid, application_name, planid |
| **12** | `12_add_cmd_type_pg_stat_monitor.up.sql` | ➕ ADD cmd_type |
| **13** | `13_pg_stat_monitor_09_topquery.up.sql` | ➕ ADD top_query |
| **14** | `14_pg_stat_monitor_09_queryplan.up.sql` | ➕ ADD query_plan |
| **15** | `15_pg_stat_monitor_09_histogram.up.sql` | ➕ ADD histogram_items Array(String) |
| **16** | `16_explain_columns.up.sql` | ➕ ADD explain_fingerprint, placeholders_count |
| **17** | `17_shared_blk_columns.up.sql` | ✏️ RENAME m_blk_read/write_time → m_shared_blk_read/write_time + ADD local 版 |
| **18** | `18_remove_explain_format_column.up.sql` | ❌ DROP example_format |
| **19** | `19_plan_summary.up.sql` | ➕ ADD plan_summary |
| **20** | `20_extended_profiler.up.sql` | ➕ ADD MongoDB 扩展指标（docs_examined/keys_examined/locks/storage） |
| **21** | `21_mongolog.up.sql` | ✏️ MODIFY agent_type：增加 `qan-mongodb-mongolog-agent` |
| **22** | `22_pg_stat_monitor_23.up.sql` | ➕ ADD m_wal_buffers_full_*, m_parallel_workers_* |

---

## 字段分组速览

| 分组 | 前缀/字段 | 数量 | 来源 DB |
|------|----------|------|---------|
| 主维度 | queryid, service_name, database, schema, username, client_host | 6 | All |
| 标准标签 | replication_set, cluster, service_type, service_id, environment, az, region, node_*, machine_id, container_* | 13 | All |
| 扩展维度 | top_queryid, application_name, planid, cmd_type | 4 | PG |
| 自定义标签 | labels.key, labels.value | 2 (Array) | All |
| Agent 元信息 | agent_id, agent_type | 2 | All |
| 时间 | period_start, period_length | 2 | All |
| 查询指纹 | fingerprint, example, is_truncated, example_type, example_metrics, tables | 6 | All |
| Explain | explain_fingerprint, placeholders_count | 2 | PG |
| 计划 | top_query, query_plan, plan_summary | 3 | PG |
| 直方图 | histogram_items | 1 (Array) | PG |
| 警告/错误 | num_queries_with_warnings, warnings.*, num_queries_with_errors, errors.*, num_queries | 6 | All |
| **MySQL 指标** | m_query_time_*, m_lock_time_*, m_rows_sent_*, m_rows_examined_*, m_rows_affected_*, m_rows_read_*, m_merge_passes_*, m_innodb_*, m_query_length_*, m_bytes_sent_*, m_tmp_* | 99 | MySQL |
| **MySQL Boolean** | m_qc_hit_*, m_full_scan_*, m_full_join_*, m_tmp_table_*, m_filesort_*, m_select_*, m_sort_*, m_no_index_*, m_no_good_index_* | 30 | MySQL |
| **MongoDB 指标** | m_docs_returned_*, m_response_length_*, m_docs_scanned_*, m_docs_examined_*, m_keys_examined_*, m_locks_*, m_storage_* | 54 | MongoDB |
| **PG 块指标** | m_shared_blks_*, m_local_blks_*, m_temp_blks_* | 20 | PostgreSQL |
| **PG I/O Time** | m_shared_blk_read_time_*, m_shared_blk_write_time_*, m_local_blk_read_time_*, m_local_blk_write_time_* | 8 | PostgreSQL |
| **PG CPU** | m_cpu_user_time_*, m_cpu_sys_time_* | 4 | PostgreSQL |
| **PG Plans/WAL** | m_plans_calls_*, m_plan_time_*, m_wal_records_*, m_wal_fpi_*, m_wal_bytes_*, m_wal_buffers_full_*, m_parallel_workers_* | 24 | PostgreSQL |
| **总计** | | ~290 列 | |

---

## 指标命名规范

每个指标字段遵循 PMM 的统一命名模式：

```
m_{metric_name}_{agg}
```

- `_cnt` — 统计到的数据点数量（用于计算平均值 `_sum / _cnt`）
- `_sum` — 该指标在 bucket 内的累加值
- `_min` — bucket 内最小值
- `_max` — bucket 内最大值
- `_p99` — bucket 内 P99 百分位值

### 指标的五元组模式（数值型指标）

| 后缀 | 含义 | 示例 |
|------|------|------|
| `_cnt` | Count of data points | `m_query_time_cnt` |
| `_sum` | Sum of values | `m_query_time_sum` |
| `_min` | Minimum value | `m_query_time_min` |
| `_max` | Maximum value | `m_query_time_max` |
| `_p99` | 99th percentile | `m_query_time_p99` |

### 指标的二值模式（布尔型指标）

| 后缀 | 含义 | 示例 |
|------|------|------|
| `_cnt` | Count of data points | `m_full_scan_cnt` |
| `_sum` | Occurrence count (0 or 1 per query) | `m_full_scan_sum` |

> `_sum / _cnt` = 该事件在 bucket 中的发生比例

---

## 引擎说明

```go
// qan-api2/migrations/migrations.go
const (
    metricsEngineSimple  = "MergeTree"            // 单节点
    metricsEngineCluster = "ReplicatedMergeTree"  // 集群
)
```

- **单节点部署** → `ENGINE = MergeTree()`
- **ClickHouse 集群** → `ENGINE = ReplicatedMergeTree()` + ZooKeeper 路径
- 分区键：`toYYYYMMDD(period_start)` — 每天一个分区
- 排序键：`(queryid, service_name, database, schema, username, client_host, period_start)`

---

## 涉及的数据源 Agent 类型

| Enum 值 | Agent | 数据库 |
|---------|-------|--------|
| 1 | qan-mysql-perfschema-agent | MySQL (Performance Schema) |
| 2 | qan-mysql-slowlog-agent | MySQL (Slow Log) |
| 3 | qan-mongodb-profiler-agent | MongoDB (Profiler) |
| 4 | qan-postgresql-pgstatements-agent | PostgreSQL (pg_stat_statements) |
| 5 | qan-postgresql-pgstatmonitor-agent | PostgreSQL (pg_stat_monitor) |
| 6 | qan-mongodb-mongolog-agent | MongoDB (MongoLog) |
