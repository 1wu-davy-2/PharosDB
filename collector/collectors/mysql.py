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
EXAMPLE_SQL = """
SELECT SQL_TEXT
FROM performance_schema.events_statements_history
WHERE DIGEST = %s AND SQL_TEXT IS NOT NULL
LIMIT 1
"""


class MySQLCollector(BaseCollector):
    """MySQL Agentless 采集器 — 查询 performance_schema。"""

    # 内存中保存上一次快照，用于计算 delta
    # key: (instance_id, queryid), value: dict of metric values
    _snapshots: dict = {}

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
