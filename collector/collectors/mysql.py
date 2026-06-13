"""MySQLCollector — 从 performance_schema 采集慢查询数据。"""

import hashlib
import time
from datetime import datetime

import pymysql

from ..crypto import decrypt
from .base import BaseCollector

# performance_schema 查询 SQL
# 参考 PMM agent/agents/mysql/perfschema/summaries.go
# MariaDB 10.5 兼容: 使用 SCHEMA_NAME (非 CURRENT_SCHEMA), 无 SUM_ROWS_READ/SUM_QUICK/SUM_BYTES_SENT
SUMMARIES_SQL = """
SELECT
    DIGEST                                           AS queryid,
    DIGEST                                           AS mysql_digest,
    DIGEST_TEXT                                      AS fingerprint,
    SCHEMA_NAME                                      AS `schema`,
    COUNT_STAR                                       AS cnt,
    SUM_TIMER_WAIT                                   AS sum_timer_wait,
    MIN_TIMER_WAIT                                   AS min_timer_wait,
    MAX_TIMER_WAIT                                   AS max_timer_wait,
    SUM_ROWS_SENT                                    AS sum_rows_sent,
    SUM_ROWS_EXAMINED                                AS sum_rows_examined,
    SUM_ROWS_AFFECTED                                AS sum_rows_affected,
    SUM_LOCK_TIME                                    AS sum_lock_time,
    SUM_SORT_MERGE_PASSES                            AS sum_merge_passes,
    SUM_NO_INDEX_USED                                AS sum_no_index_used,
    SUM_NO_GOOD_INDEX_USED                           AS sum_no_good_index_used,
    SUM_CREATED_TMP_TABLES                           AS sum_tmp_tables,
    SUM_CREATED_TMP_DISK_TABLES                      AS sum_tmp_disk_tables,
    SUM_SELECT_FULL_JOIN                             AS sum_full_join,
    SUM_SELECT_SCAN                                  AS sum_full_scan,
    SUM_SORT_ROWS                                    AS sum_sort_rows,
    SUM_SORT_SCAN                                    AS sum_sort_scan,
    SUM_SELECT_FULL_RANGE_JOIN                       AS sum_select_full_range_join,
    SUM_SELECT_RANGE                                 AS sum_select_range,
    SUM_SELECT_RANGE_CHECK                           AS sum_select_range_check,
    SUM_SORT_RANGE                                   AS sum_sort_range
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL AND DIGEST_TEXT IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 200
"""

# 单条查询的 example SQL
# 优先查 history_long (默认 1000 行)，普通 history 只有 10 行/线程极易命中空结果
EXAMPLE_SQL = """
SELECT SQL_TEXT
FROM performance_schema.events_statements_history_long
WHERE DIGEST = %s AND SQL_TEXT IS NOT NULL
LIMIT 1
"""

# ── EXPLAIN 相关 ──────────────────────────────────────────────────────────────

TOP_N_EXPLAIN = 5       # 每个采集周期对 top-5 慢查询执行 EXPLAIN
EXPLAIN_TIMEOUT = 3      # EXPLAIN 最大允许秒数

# 排除系统库 — 避免采集器自己的查询被 EXPLAIN
_EXCLUDED_SCHEMAS = frozenset({"performance_schema", "information_schema", "mysql", "sys"})

_CONTAINER_KEYS = frozenset({
    "nested_loop", "ordering_operation", "grouping_operation",
    "duplicates_removal", "windowing",
})


def normalize_plan_summary(plan: dict) -> str:
    """提取 EXPLAIN JSON 的结构性摘要，剔除 cost/timing 数值浮动。

    只保留每个 table 节点的 join_type/access_type、key、Extra 等结构信息，
    以及嵌套子查询树。用于判断两次 EXPLAIN 是否有实质差异。
    """

    def _walk(node):
        if isinstance(node, list):
            return [_walk(item) for item in node]
        if not isinstance(node, dict):
            return node

        if "table" in node:
            tbl = node["table"]
            result = {
                "table_name": tbl.get("table_name"),
                "access_type": tbl.get("access_type"),
                "key":           tbl.get("key"),
                "possible_keys": sorted(tbl.get("possible_keys", []) or []),
                "used_columns":  sorted(tbl.get("used_columns", []) or []),
                "Extra":        tbl.get("Extra", ""),
                "filtered":     tbl.get("filtered"),
            }
            if "materialized_from_subquery" in tbl:
                result["materialized_from_subquery"] = _walk(
                    tbl["materialized_from_subquery"]
                )
            return result

        result: dict = {}
        for key in node:
            if key in _CONTAINER_KEYS or key == "query_block":
                result[key] = _walk(node[key])
        return result

    import json
    return json.dumps(
        _walk(plan.get("query_block", plan)),
        sort_keys=True,
        default=str,
    )


class MySQLCollector(BaseCollector):
    """MySQL Agentless 采集器 — 查询 performance_schema。

    除指标采集外，每个周期对 top-{TOP_N_EXPLAIN} 慢查询自动执行 EXPLAIN，
    写入 ClickHouse execution_plans 表，支持执行计划历史版本对比。
    """

    # 内存中保存上一次快照，用于计算 delta
    # key: (instance_id, queryid), value: dict of metric values
    _snapshots: dict = {}

    # EXPLAIN 去重缓存: key="{instance_name}:{fingerprint}" → plan_hash
    _plan_cache: dict[str, str] = {}

    def connect(self):
        self.conn = pymysql.connect(
            host=self.instance.host,
            port=self.instance.port,
            user=self.instance.username,
            password=decrypt(self.instance.password),
            connect_timeout=10,
            charset="utf8mb4",
        )
        # 确保连接的 max_allowed_packet 足够大
        try:
            cur = self.conn.cursor()
            cur.execute("SET SESSION net_read_timeout = 600")
            cur.execute("SET SESSION net_write_timeout = 600")
            cur.close()
        except Exception:
            pass

    def collect(self) -> list[dict]:
        cur = self.conn.cursor(pymysql.cursors.DictCursor)
        cur.execute(SUMMARIES_SQL)
        rows = cur.fetchall()

        result = []
        now = datetime.utcnow()
        instance_key = self.instance.id

        for row in rows:
            queryid = row["queryid"]
            snapshot_key = (instance_key, queryid)

            # 获取上一次快照
            prev = self._snapshots.get(snapshot_key)

            # 计算 delta
            delta = self._compute_delta(prev, row)

            # 保存当前快照
            self._snapshots[snapshot_key] = {
                "cnt": row["cnt"],
                "sum_timer_wait": row.get("sum_timer_wait") or 0,
                "sum_rows_sent": row.get("sum_rows_sent") or 0,
                "sum_rows_examined": row.get("sum_rows_examined") or 0,
                "sum_rows_affected": row.get("sum_rows_affected") or 0,
                "sum_lock_time": row.get("sum_lock_time") or 0,
                "sum_merge_passes": row.get("sum_merge_passes") or 0,
            }

            # 获取 example query
            example = ""
            try:
                cur.execute(EXAMPLE_SQL, (queryid,))
                ex_row = cur.fetchone()
                if ex_row:
                    example = ex_row.get("SQL_TEXT", "")[:2000]
            except Exception:
                pass

            # 构建 ClickHouse 行
            ch_row = self._build_ch_row(row, delta, example, now)
            result.append(ch_row)

        # ── 对 top-N 慢查询执行 EXPLAIN ──
        # 只对 DML 类型查询执行 EXPLAIN（SHOW/SET/其他不行）
        top_queries = sorted(
            result, key=lambda r: r["m_query_time_sum"], reverse=True
        )[:TOP_N_EXPLAIN * 2]  # 多取一些，防止过滤后不足
        explain_count = 0
        for q in top_queries:
            fingerprint = (q.get("fingerprint") or "").strip().upper()
            if not fingerprint.startswith(("SELECT", "INSERT", "UPDATE", "DELETE", "REPLACE")):
                continue
            schema_name = (q.get("schema") or "").lower()
            if schema_name in _EXCLUDED_SCHEMAS:
                continue
            if self._maybe_collect_explain(q, cur):
                explain_count += 1
                if explain_count >= TOP_N_EXPLAIN:
                    break

        cur.close()
        return result

    def _compute_delta(self, prev, curr):
        """计算两次快照之间的差值。首次采集返回原始值。"""
        def v(key):
            return curr.get(key) or 0

        if prev is None:
            return {
                "cnt": curr["cnt"],
                "sum_timer_wait": v("sum_timer_wait"),
                "min_timer_wait": v("min_timer_wait"),
                "max_timer_wait": v("max_timer_wait"),
                "sum_rows_sent": v("sum_rows_sent"),
                "sum_rows_examined": v("sum_rows_examined"),
                "sum_rows_affected": v("sum_rows_affected"),
                "sum_rows_read": v("sum_rows_read"),
                "sum_lock_time": v("sum_lock_time"),
                "sum_merge_passes": v("sum_merge_passes"),
                "sum_no_index_used": v("sum_no_index_used"),
                "sum_no_good_index_used": v("sum_no_good_index_used"),
                "sum_tmp_tables": v("sum_tmp_tables"),
                "sum_tmp_disk_tables": v("sum_tmp_disk_tables"),
                "sum_full_join": v("sum_full_join"),
                "sum_full_scan": v("sum_full_scan"),
                "sum_sort_rows": v("sum_sort_rows"),
                "sum_sort_scan": v("sum_sort_scan"),
                "sum_select_full_range_join": v("sum_select_full_range_join"),
                "sum_select_range": v("sum_select_range"),
                "sum_select_range_check": v("sum_select_range_check"),
                "sum_sort_range": v("sum_sort_range"),
                "sum_qc_hit": v("sum_qc_hit"),
                "sum_bytes_sent": v("sum_bytes_sent"),
                "sum_tmp_table_sizes": v("sum_tmp_table_sizes"),
            }

        # Delta: 当前值 - 上一次值
        def delta_val(key):
            return (curr.get(key) or 0) - (prev.get(key) or 0)

        return {
            "cnt": delta_val("cnt"),
            "sum_timer_wait": delta_val("sum_timer_wait"),
            "min_timer_wait": curr["min_timer_wait"] or 0,
            "max_timer_wait": curr["max_timer_wait"] or 0,
            "sum_rows_sent": delta_val("sum_rows_sent"),
            "sum_rows_examined": delta_val("sum_rows_examined"),
            "sum_rows_affected": delta_val("sum_rows_affected"),
            "sum_rows_read": delta_val("sum_rows_read"),
            "sum_lock_time": delta_val("sum_lock_time"),
            "sum_merge_passes": delta_val("sum_merge_passes"),
            "sum_no_index_used": delta_val("sum_no_index_used"),
            "sum_no_good_index_used": delta_val("sum_no_good_index_used"),
            "sum_tmp_tables": delta_val("sum_tmp_tables"),
            "sum_tmp_disk_tables": delta_val("sum_tmp_disk_tables"),
            "sum_full_join": delta_val("sum_full_join"),
            "sum_full_scan": delta_val("sum_full_scan"),
            "sum_sort_rows": delta_val("sum_sort_rows"),
            "sum_sort_scan": delta_val("sum_sort_scan"),
            "sum_select_full_range_join": delta_val("sum_select_full_range_join"),
            "sum_select_range": delta_val("sum_select_range"),
            "sum_select_range_check": delta_val("sum_select_range_check"),
            "sum_sort_range": delta_val("sum_sort_range"),
            "sum_qc_hit": delta_val("sum_qc_hit"),
            "sum_bytes_sent": delta_val("sum_bytes_sent"),
            "sum_tmp_table_sizes": delta_val("sum_tmp_table_sizes"),
        }

    def _build_ch_row(self, raw_row, delta, example, now):
        """将 performance_schema 行映射为 ClickHouse metrics 表的行。"""
        # 皮秒转秒
        ps_to_s = 1e12

        instance = self.instance
        cnt = max(delta["cnt"], 1)  # 避免除零

        return {
            # 主维度
            "queryid": raw_row["queryid"],
            "mysql_digest": raw_row.get("mysql_digest") or raw_row.get("queryid") or "",
            "service_name": instance.name,
            "database": "",
            "schema": raw_row.get("schema") or "",
            "username": "",
            "client_host": "",

            # 标准标签
            "replication_set": "",
            "cluster": instance.cluster or "",
            "service_type": "mysql",
            "service_id": f"mysql-{instance.id}",
            "environment": instance.environment or "",
            "az": "",
            "region": "",
            "node_model": "",
            "node_id": "",
            "node_name": "",
            "node_type": "",
            "machine_id": "",
            "container_name": "",
            "container_id": "",

            # 扩展维度
            "top_queryid": "",
            "application_name": "",
            "planid": "",
            "cmd_type": "",

            # 自定义标签
            "labels.key": [],
            "labels.value": [],

            # Agent 元信息
            "agent_id": f"pharos-agentless-{instance.id}",
            "agent_type": "qan-mysql-perfschema-agent",

            # 时间
            "period_start": now,
            "period_length": instance.collect_interval,

            # 查询指纹
            "fingerprint": raw_row.get("fingerprint") or "",
            "example": example,
            "is_truncated": 0,
            "example_type": "RANDOM",
            "example_metrics": "",
            "tables": [],

            # Explain
            "explain_fingerprint": "",
            "placeholders_count": 0,

            # Plan
            "top_query": "",
            "query_plan": "",
            "plan_summary": "",

            # Histogram
            "histogram_items": [],

            # 警告与错误
            "num_queries_with_warnings": 0,
            "warnings.code": [],
            "warnings.count": [],
            "num_queries_with_errors": 0,
            "errors.code": [],
            "errors.count": [],
            "num_queries": float(delta["cnt"]),

            # ============ MySQL Metrics ============
            # 1. Query Time
            "m_query_time_cnt": float(delta["cnt"]),
            "m_query_time_sum": delta["sum_timer_wait"] / ps_to_s,
            "m_query_time_min": (raw_row["min_timer_wait"] or 0) / ps_to_s,
            "m_query_time_max": (raw_row["max_timer_wait"] or 0) / ps_to_s,
            "m_query_time_p99": 0,

            # 2. Lock Time
            "m_lock_time_cnt": float(delta["cnt"]),
            "m_lock_time_sum": delta["sum_lock_time"] / ps_to_s,
            "m_lock_time_min": 0,
            "m_lock_time_max": 0,
            "m_lock_time_p99": 0,

            # 3. Rows Sent
            "m_rows_sent_cnt": float(delta["cnt"]),
            "m_rows_sent_sum": float(delta["sum_rows_sent"]),
            "m_rows_sent_min": 0,
            "m_rows_sent_max": 0,
            "m_rows_sent_p99": 0,

            # 4. Rows Examined
            "m_rows_examined_cnt": float(delta["cnt"]),
            "m_rows_examined_sum": float(delta["sum_rows_examined"]),
            "m_rows_examined_min": 0,
            "m_rows_examined_max": 0,
            "m_rows_examined_p99": 0,

            # 5. Rows Affected
            "m_rows_affected_cnt": float(delta["cnt"]),
            "m_rows_affected_sum": float(delta["sum_rows_affected"]),
            "m_rows_affected_min": 0,
            "m_rows_affected_max": 0,
            "m_rows_affected_p99": 0,

            # 6. Rows Read
            "m_rows_read_cnt": float(delta["cnt"]),
            "m_rows_read_sum": float(delta["sum_rows_read"]),
            "m_rows_read_min": 0,
            "m_rows_read_max": 0,
            "m_rows_read_p99": 0,

            # 7. Merge Passes
            "m_merge_passes_cnt": float(delta["cnt"]),
            "m_merge_passes_sum": float(delta["sum_merge_passes"]),
            "m_merge_passes_min": 0,
            "m_merge_passes_max": 0,
            "m_merge_passes_p99": 0,

            # 8-13. InnoDB metrics (Agentless 无法获取，填 0)
            "m_innodb_io_r_ops_cnt": 0, "m_innodb_io_r_ops_sum": 0,
            "m_innodb_io_r_ops_min": 0, "m_innodb_io_r_ops_max": 0, "m_innodb_io_r_ops_p99": 0,
            "m_innodb_io_r_bytes_cnt": 0, "m_innodb_io_r_bytes_sum": 0,
            "m_innodb_io_r_bytes_min": 0, "m_innodb_io_r_bytes_max": 0, "m_innodb_io_r_bytes_p99": 0,
            "m_innodb_io_r_wait_cnt": 0, "m_innodb_io_r_wait_sum": 0,
            "m_innodb_io_r_wait_min": 0, "m_innodb_io_r_wait_max": 0, "m_innodb_io_r_wait_p99": 0,
            "m_innodb_rec_lock_wait_cnt": 0, "m_innodb_rec_lock_wait_sum": 0,
            "m_innodb_rec_lock_wait_min": 0, "m_innodb_rec_lock_wait_max": 0, "m_innodb_rec_lock_wait_p99": 0,
            "m_innodb_queue_wait_cnt": 0, "m_innodb_queue_wait_sum": 0,
            "m_innodb_queue_wait_min": 0, "m_innodb_queue_wait_max": 0, "m_innodb_queue_wait_p99": 0,
            "m_innodb_pages_distinct_cnt": 0, "m_innodb_pages_distinct_sum": 0,
            "m_innodb_pages_distinct_min": 0, "m_innodb_pages_distinct_max": 0, "m_innodb_pages_distinct_p99": 0,

            # 14. Query Length
            "m_query_length_cnt": 0, "m_query_length_sum": 0,
            "m_query_length_min": 0, "m_query_length_max": 0, "m_query_length_p99": 0,

            # 15. Bytes Sent
            "m_bytes_sent_cnt": float(delta["cnt"]),
            "m_bytes_sent_sum": float(delta["sum_bytes_sent"]),
            "m_bytes_sent_min": 0, "m_bytes_sent_max": 0, "m_bytes_sent_p99": 0,

            # 16-18. Temp Tables
            "m_tmp_tables_cnt": float(delta["cnt"]),
            "m_tmp_tables_sum": float(delta["sum_tmp_tables"]),
            "m_tmp_tables_min": 0, "m_tmp_tables_max": 0, "m_tmp_tables_p99": 0,
            "m_tmp_disk_tables_cnt": float(delta["cnt"]),
            "m_tmp_disk_tables_sum": float(delta["sum_tmp_disk_tables"]),
            "m_tmp_disk_tables_min": 0, "m_tmp_disk_tables_max": 0, "m_tmp_disk_tables_p99": 0,
            "m_tmp_table_sizes_cnt": float(delta["cnt"]),
            "m_tmp_table_sizes_sum": float(delta["sum_tmp_table_sizes"]),
            "m_tmp_table_sizes_min": 0, "m_tmp_table_sizes_max": 0, "m_tmp_table_sizes_p99": 0,

            # ============ Boolean Metrics ============
            "m_qc_hit_cnt": float(delta["cnt"]),
            "m_qc_hit_sum": float(delta["sum_qc_hit"]),
            "m_full_scan_cnt": float(delta["cnt"]),
            "m_full_scan_sum": float(delta["sum_full_scan"]),
            "m_full_join_cnt": float(delta["cnt"]),
            "m_full_join_sum": float(delta["sum_full_join"]),
            "m_tmp_table_cnt": 0, "m_tmp_table_sum": 0,
            "m_tmp_table_on_disk_cnt": 0, "m_tmp_table_on_disk_sum": 0,
            "m_filesort_cnt": 0, "m_filesort_sum": 0,
            "m_filesort_on_disk_cnt": 0, "m_filesort_on_disk_sum": 0,
            "m_select_full_range_join_cnt": float(delta["cnt"]),
            "m_select_full_range_join_sum": float(delta["sum_select_full_range_join"]),
            "m_select_range_cnt": float(delta["cnt"]),
            "m_select_range_sum": float(delta["sum_select_range"]),
            "m_select_range_check_cnt": float(delta["cnt"]),
            "m_select_range_check_sum": float(delta["sum_select_range_check"]),
            "m_sort_range_cnt": float(delta["cnt"]),
            "m_sort_range_sum": float(delta["sum_sort_range"]),
            "m_sort_rows_cnt": float(delta["cnt"]),
            "m_sort_rows_sum": float(delta["sum_sort_rows"]),
            "m_sort_scan_cnt": float(delta["cnt"]),
            "m_sort_scan_sum": float(delta["sum_sort_scan"]),
            "m_no_index_used_cnt": float(delta["cnt"]),
            "m_no_index_used_sum": float(delta["sum_no_index_used"]),
            "m_no_good_index_used_cnt": float(delta["cnt"]),
            "m_no_good_index_used_sum": float(delta["sum_no_good_index_used"]),

            # ============ MongoDB Metrics (全部填 0) ============
            "m_docs_returned_cnt": 0, "m_docs_returned_sum": 0,
            "m_docs_returned_min": 0, "m_docs_returned_max": 0, "m_docs_returned_p99": 0,
            "m_response_length_cnt": 0, "m_response_length_sum": 0,
            "m_response_length_min": 0, "m_response_length_max": 0, "m_response_length_p99": 0,
            "m_docs_scanned_cnt": 0, "m_docs_scanned_sum": 0,
            "m_docs_scanned_min": 0, "m_docs_scanned_max": 0, "m_docs_scanned_p99": 0,
            "m_docs_examined_cnt": 0, "m_docs_examined_sum": 0,
            "m_docs_examined_min": 0, "m_docs_examined_max": 0, "m_docs_examined_p99": 0,
            "m_keys_examined_cnt": 0, "m_keys_examined_sum": 0,
            "m_keys_examined_min": 0, "m_keys_examined_max": 0, "m_keys_examined_p99": 0,
            "m_locks_global_acquire_count_read_shared_cnt": 0, "m_locks_global_acquire_count_read_shared_sum": 0,
            "m_locks_global_acquire_count_write_shared_cnt": 0, "m_locks_global_acquire_count_write_shared_sum": 0,
            "m_locks_database_acquire_count_read_shared_cnt": 0, "m_locks_database_acquire_count_read_shared_sum": 0,
            "m_locks_database_acquire_wait_count_read_shared_cnt": 0, "m_locks_database_acquire_wait_count_read_shared_sum": 0,
            "m_locks_database_time_acquiring_micros_read_shared_cnt": 0, "m_locks_database_time_acquiring_micros_read_shared_sum": 0,
            "m_locks_database_time_acquiring_micros_read_shared_min": 0, "m_locks_database_time_acquiring_micros_read_shared_max": 0, "m_locks_database_time_acquiring_micros_read_shared_p99": 0,
            "m_locks_collection_acquire_count_read_shared_cnt": 0, "m_locks_collection_acquire_count_read_shared_sum": 0,
            "m_storage_bytes_read_cnt": 0, "m_storage_bytes_read_sum": 0,
            "m_storage_bytes_read_min": 0, "m_storage_bytes_read_max": 0, "m_storage_bytes_read_p99": 0,
            "m_storage_time_reading_micros_cnt": 0, "m_storage_time_reading_micros_sum": 0,
            "m_storage_time_reading_micros_min": 0, "m_storage_time_reading_micros_max": 0, "m_storage_time_reading_micros_p99": 0,

            # ============ PostgreSQL Metrics (全部填 0) ============
            "m_shared_blks_hit_cnt": 0, "m_shared_blks_hit_sum": 0,
            "m_shared_blks_read_cnt": 0, "m_shared_blks_read_sum": 0,
            "m_shared_blks_dirtied_cnt": 0, "m_shared_blks_dirtied_sum": 0,
            "m_shared_blks_written_cnt": 0, "m_shared_blks_written_sum": 0,
            "m_local_blks_hit_cnt": 0, "m_local_blks_hit_sum": 0,
            "m_local_blks_read_cnt": 0, "m_local_blks_read_sum": 0,
            "m_local_blks_dirtied_cnt": 0, "m_local_blks_dirtied_sum": 0,
            "m_local_blks_written_cnt": 0, "m_local_blks_written_sum": 0,
            "m_temp_blks_read_cnt": 0, "m_temp_blks_read_sum": 0,
            "m_temp_blks_written_cnt": 0, "m_temp_blks_written_sum": 0,
            "m_shared_blk_read_time_cnt": 0, "m_shared_blk_read_time_sum": 0,
            "m_shared_blk_write_time_cnt": 0, "m_shared_blk_write_time_sum": 0,
            "m_local_blk_read_time_cnt": 0, "m_local_blk_read_time_sum": 0,
            "m_local_blk_write_time_cnt": 0, "m_local_blk_write_time_sum": 0,
            "m_cpu_user_time_cnt": 0, "m_cpu_user_time_sum": 0,
            "m_cpu_sys_time_cnt": 0, "m_cpu_sys_time_sum": 0,
            "m_plans_calls_cnt": 0, "m_plans_calls_sum": 0,
            "m_plan_time_cnt": 0, "m_plan_time_sum": 0,
            "m_plan_time_min": 0, "m_plan_time_max": 0,
            "m_wal_records_cnt": 0, "m_wal_records_sum": 0,
            "m_wal_fpi_cnt": 0, "m_wal_fpi_sum": 0,
            "m_wal_bytes_cnt": 0, "m_wal_bytes_sum": 0,
            "m_wal_buffers_full_cnt": 0, "m_wal_buffers_full_sum": 0,
            "m_parallel_workers_to_launch_cnt": 0, "m_parallel_workers_to_launch_sum": 0,
            "m_parallel_workers_launched_cnt": 0, "m_parallel_workers_launched_sum": 0,
        }

    # ── EXPLAIN 方法 ──────────────────────────────────────────────────────

    def _maybe_collect_explain(self, metrics_row, cursor) -> bool:
        """对一条慢查询执行 EXPLAIN，有变化时写入 ClickHouse execution_plans。

        Returns True if EXPLAIN was successfully executed (regardless of whether
        it was a new plan or unchanged), False if skipped.
        """
        fingerprint = metrics_row.get("fingerprint", "")
        mysql_digest = metrics_row.get("mysql_digest", "")
        schema = metrics_row.get("schema", "")

        if not mysql_digest or not fingerprint:
            return False

        import logging as _logging
        _log = _logging.getLogger(__name__)

        # 1. 获取 SQL 原文
        # events_statements_history 容量很小（默认 10/线程），可能已被淘汰。
        # 优先查 history_long (MySQL 5.7+ / MariaDB 10.5.2+)，其次 history，
        # 都查不到则复用同周期已取到的 example。
        sql_text = ""
        for table in (
            "performance_schema.events_statements_history_long",
            "performance_schema.events_statements_history",
        ):
            try:
                cursor.execute(
                    "SELECT SQL_TEXT FROM {} WHERE DIGEST = %s AND SQL_TEXT IS NOT NULL LIMIT 1".format(table),
                    (mysql_digest,),
                )
                row = cursor.fetchone()
                if row:
                    sql_text = row.get("SQL_TEXT", "")[:8192]
                    break
            except Exception:
                continue
        if not sql_text:
            sql_text = (metrics_row.get("example") or "")[:8192]
        if not sql_text:
            return False

        # 2. 执行 EXPLAIN（带超时保护）
        # 注意：sql_text 是完整的 SQL 语句（含字面值），不能用 pymysql 参数 %s
        # 传参，否则 pymysql 会把它当成字符串值做单引号包裹，导致语法错误。
        # 这里用 Python 字符串拼接，sql_text 来自 MySQL history 表，非用户输入。
        plan_json_raw = None

        # 先尝试 MariaDB SET STATEMENT 语法，再 MySQL hint 语法
        try:
            cursor.execute(
                "SET STATEMENT max_statement_time=%s FOR EXPLAIN FORMAT=JSON "
                + sql_text,
                (EXPLAIN_TIMEOUT,),
            )
            plan_json_raw = cursor.fetchone()
        except Exception as e1:
            try:
                cursor.execute(
                    "EXPLAIN FORMAT=JSON /*+ MAX_EXECUTION_TIME(%s) */ "
                    + sql_text,
                    (EXPLAIN_TIMEOUT * 1000,),
                )
                plan_json_raw = cursor.fetchone()
            except Exception as e2:
                _log.warning(
                    "[explain] EXPLAIN failed instance=%s: "
                    "mariadb=%s mysql=%s sql_preview=%s",
                    self.instance.name, e1, e2, sql_text[:100],
                )
                return False
        if not plan_json_raw:
            return False

        # 3. 解析 + 提取结构摘要
        # DictCursor 返回 {'EXPLAIN': 'json_str'}，按 key 取；同时兼容 tuple 模式
        import json as _json
        try:
            if isinstance(plan_json_raw, dict):
                plan_str = plan_json_raw.get("EXPLAIN", "")
            elif isinstance(plan_json_raw, (list, tuple)):
                plan_str = plan_json_raw[0]
            else:
                plan_str = str(plan_json_raw)
            plan_dict = _json.loads(plan_str) if isinstance(plan_str, str) else plan_str
        except (_json.JSONDecodeError, IndexError, TypeError, KeyError):
            return False

        plan_summary = normalize_plan_summary(plan_dict)
        plan_hash = hashlib.md5(plan_summary.encode()).hexdigest()

        # 4. 去重检查
        if not self._should_save_plan(fingerprint, plan_hash):
            return True  # 计划未变，但 EXPLAIN 本身成功了

        # 5. 写入 ClickHouse execution_plans
        from datetime import datetime as _dt
        plan_id = hashlib.md5(
            f"{fingerprint}{_dt.utcnow().isoformat()}".encode()
        ).hexdigest()

        try:
            from ..clickhouse import get_writer
            get_writer().write_execution_plans([{
                "plan_id": plan_id,
                "fingerprint": fingerprint,
                "service_name": self.instance.name,
                "schema": schema,
                "plan_json": _json.dumps(plan_dict, ensure_ascii=False),
                "plan_summary": plan_summary,
                "plan_hash": plan_hash,
                "query_example": sql_text[:2000],
                "created_at": _dt.utcnow(),
                "instance_id": self.instance.id,
            }])
        except Exception:
            pass

        # 6. 回写 metrics_row，让同批次 metrics 写入时带上 planid
        metrics_row["planid"] = plan_id
        metrics_row["explain_fingerprint"] = plan_hash
        return True

    def _should_save_plan(self, fingerprint, new_plan_hash):
        """检查 EXPLAIN 是否与上一次不同。

        缓存 key 含 instance name：不同实例上相同 fingerprint 的计划可能完全不同。
        """
        cache_key = f"{self.instance.name}:{fingerprint}"
        cached = self._plan_cache.get(cache_key)
        if cached is not None:
            return cached != new_plan_hash

        try:
            from ..clickhouse import get_writer
            writer = get_writer()
            rows, _cols = writer.execute(
                "SELECT plan_hash FROM pharos_db.execution_plans "
                "WHERE fingerprint = %(fp)s AND service_name = %(svc)s "
                "ORDER BY created_at DESC LIMIT 1",
                {"fp": fingerprint, "svc": self.instance.name},
            )
            last_hash = rows[0][0] if rows else None
        except Exception:
            last_hash = None

        self._plan_cache[cache_key] = last_hash
        return last_hash != new_plan_hash
