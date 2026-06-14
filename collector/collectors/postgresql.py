"""PostgreSQLCollector — 从 pg_stat_statements 采集慢查询数据。"""

import hashlib
from datetime import datetime

import psycopg2
import psycopg2.extras

from ..crypto import decrypt
from .base import BaseCollector

# pg_stat_statements 支持情况:
# - PG 13+: plans, plan_time 字段可用
# - PG 12-: 无 plans/plan_time, 用 0 填充
# - 需要 CREATE EXTENSION pg_stat_statements

SUMMARIES_SQL = """
SELECT
    queryid::text                          AS queryid,
    query                                  AS fingerprint,
    dbname                                 AS schema_name,
    calls                                  AS cnt,
    total_exec_time                        AS total_exec_time_ms,
    min_exec_time                          AS min_exec_time_ms,
    max_exec_time                          AS max_exec_time_ms,
    mean_exec_time                         AS mean_exec_time_ms,
    rows                                   AS rows_sent,
    shared_blks_hit                        AS shared_blks_hit,
    shared_blks_read                       AS shared_blks_read,
    shared_blks_dirtied                    AS shared_blks_dirtied,
    shared_blks_written                    AS shared_blks_written,
    local_blks_hit                         AS local_blks_hit,
    local_blks_read                        AS local_blks_read,
    local_blks_dirtied                     AS local_blks_dirtied,
    local_blks_written                     AS local_blks_written,
    temp_blks_read                         AS temp_blks_read,
    temp_blks_written                      AS temp_blks_written,
    blk_read_time                          AS blk_read_time_ms,
    blk_write_time                         AS blk_write_time_ms
FROM pg_stat_statements
JOIN pg_database ON pg_database.oid = pg_stat_statements.dbid
WHERE query IS NOT NULL
  AND queryid IS NOT NULL
ORDER BY total_exec_time DESC
LIMIT 200
"""

# PG 13+ 额外字段
SUMMARIES_SQL_PG13_EXTRA = """
SELECT
    queryid::text                          AS queryid,
    query                                  AS fingerprint,
    dbname                                 AS schema_name,
    calls                                  AS cnt,
    total_exec_time                        AS total_exec_time_ms,
    min_exec_time                          AS min_exec_time_ms,
    max_exec_time                          AS max_exec_time_ms,
    mean_exec_time                         AS mean_exec_time_ms,
    rows                                   AS rows_sent,
    shared_blks_hit, shared_blks_read,
    shared_blks_dirtied, shared_blks_written,
    local_blks_hit, local_blks_read,
    local_blks_dirtied, local_blks_written,
    temp_blks_read, temp_blks_written,
    blk_read_time                          AS blk_read_time_ms,
    blk_write_time                         AS blk_write_time_ms,
    plans                                  AS plans,
    total_plan_time                        AS total_plan_time_ms,
    min_plan_time                          AS min_plan_time_ms,
    max_plan_time                          AS max_plan_time_ms,
    wal_records, wal_fpi, wal_bytes
FROM pg_stat_statements
JOIN pg_database ON pg_database.oid = pg_stat_statements.dbid
WHERE query IS NOT NULL
  AND queryid IS NOT NULL
ORDER BY total_exec_time DESC
LIMIT 200
"""


class PostgreSQLCollector(BaseCollector):
    """PostgreSQL Agentless 采集器 — 查询 pg_stat_statements。"""

    _snapshots: dict = {}

    def connect(self):
        self.conn = psycopg2.connect(
            host=self.instance.host,
            port=self.instance.port,
            user=self.instance.username,
            password=decrypt(self.instance.password),
            connect_timeout=10,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        self.conn.autocommit = True
        self._pg_version = self._get_pg_version()
        self._detect_role()
        self._detect_app_hosts()

    def _get_pg_version(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute("SHOW server_version_num")
            row = cur.fetchone()
            return int(row["server_version_num"]) // 10000

    def _detect_role(self):
        """自动检测 PG 集群角色（primary / replica / standalone）。

        检查 pg_is_in_recovery() + pg_stat_wal_receiver。
        """
        role = "standalone"
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT pg_is_in_recovery()")
                row = cur.fetchone()
                is_replica = row["pg_is_in_recovery"] if row else False

                if is_replica:
                    # 进一步区分 replica vs standalone（shard 无法自动检测，需人工标记）
                    cur.execute(
                        "SELECT COUNT(*) FROM pg_stat_wal_receiver WHERE status = 'streaming'"
                    )
                    wal_row = cur.fetchone()
                    has_wal = wal_row and wal_row["count"] > 0
                    role = "replica" if has_wal else "replica"
                else:
                    # 检查是否有 streaming replicas 连接（说明这是 primary）
                    cur.execute("SELECT COUNT(*) FROM pg_stat_replication")
                    repl_row = cur.fetchone()
                    has_replicas = repl_row and repl_row["count"] > 0
                    role = "primary" if has_replicas else "primary"

            if self.instance.cluster_role != role:
                from collector.models import DatabaseInstance
                DatabaseInstance.objects.filter(pk=self.instance.id).update(cluster_role=role)
                self.instance.cluster_role = role
        except Exception:
            pass

    def _detect_app_hosts(self):
        """从 pg_stat_activity 获取当前连接的应用端 IP 列表。"""
        self._app_hosts = []
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT client_addr, COUNT(*) AS cnt "
                    "FROM pg_stat_activity "
                    "WHERE client_addr IS NOT NULL "
                    "  AND usename NOT IN ('postgres', 'replication') "
                    "  AND state != 'idle' "
                    "GROUP BY client_addr ORDER BY cnt DESC LIMIT 10"
                )
                rows = cur.fetchall()
                # RealDictCursor returns dicts, but rows could be tuples
                for row in rows:
                    ip = row.get("client_addr") if isinstance(row, dict) else str(row[0])
                    if ip:
                        self._app_hosts.append(ip)
        except Exception:
            self._app_hosts = []

    def collect(self) -> list[dict]:
        sql = SUMMARIES_SQL_PG13_EXTRA if self._pg_version >= 13 else SUMMARIES_SQL

        with self.conn.cursor() as cur:
            try:
                cur.execute(sql)
            except psycopg2.Error as e:
                if "pg_stat_statements" in str(e):
                    raise RuntimeError(
                        "pg_stat_statements 扩展未安装，请执行: CREATE EXTENSION pg_stat_statements"
                    ) from e
                raise

            rows = cur.fetchall()

        result = []
        now = datetime.utcnow()

        for row in rows:
            row = dict(row)
            queryid = row["queryid"]
            snapshot_key = (self.instance.id, queryid)

            prev = self._snapshots.get(snapshot_key)
            delta = self._compute_delta(prev, row)

            self._snapshots[snapshot_key] = {
                "cnt": row["cnt"],
                "total_exec_time_ms": row.get("total_exec_time_ms") or 0,
                "rows_sent": row.get("rows_sent") or 0,
                "shared_blks_hit": row.get("shared_blks_hit") or 0,
                "shared_blks_read": row.get("shared_blks_read") or 0,
                "shared_blks_dirtied": row.get("shared_blks_dirtied") or 0,
                "shared_blks_written": row.get("shared_blks_written") or 0,
                "temp_blks_read": row.get("temp_blks_read") or 0,
                "temp_blks_written": row.get("temp_blks_written") or 0,
                "blk_read_time_ms": row.get("blk_read_time_ms") or 0,
                "blk_write_time_ms": row.get("blk_write_time_ms") or 0,
            }

            result.append(self._build_ch_row(row, delta, now))

        return result

    def _compute_delta(self, prev, curr):
        def v(key):
            return curr.get(key) or 0

        if prev is None:
            return {k: v(k) for k in [
                "cnt", "total_exec_time_ms", "rows_sent",
                "shared_blks_hit", "shared_blks_read",
                "shared_blks_dirtied", "shared_blks_written",
                "local_blks_hit", "local_blks_read",
                "local_blks_dirtied", "local_blks_written",
                "temp_blks_read", "temp_blks_written",
                "blk_read_time_ms", "blk_write_time_ms",
                "plans", "total_plan_time_ms",
                "wal_records", "wal_fpi", "wal_bytes",
            ]}

        def d(key):
            return (curr.get(key) or 0) - (prev.get(key) or 0)

        return {
            "cnt": d("cnt"),
            "total_exec_time_ms": d("total_exec_time_ms"),
            "rows_sent": d("rows_sent"),
            "shared_blks_hit": d("shared_blks_hit"),
            "shared_blks_read": d("shared_blks_read"),
            "shared_blks_dirtied": d("shared_blks_dirtied"),
            "shared_blks_written": d("shared_blks_written"),
            "local_blks_hit": d("local_blks_hit"),
            "local_blks_read": d("local_blks_read"),
            "local_blks_dirtied": d("local_blks_dirtied"),
            "local_blks_written": d("local_blks_written"),
            "temp_blks_read": d("temp_blks_read"),
            "temp_blks_written": d("temp_blks_written"),
            "blk_read_time_ms": d("blk_read_time_ms"),
            "blk_write_time_ms": d("blk_write_time_ms"),
            "plans": d("plans"),
            "total_plan_time_ms": d("total_plan_time_ms"),
            "wal_records": d("wal_records"),
            "wal_fpi": d("wal_fpi"),
            "wal_bytes": d("wal_bytes"),
        }

    def _build_ch_row(self, raw, delta, now):
        ms_to_s = 1e3
        cnt = max(delta["cnt"], 1)
        instance = self.instance

        # queryid 是数字字符串，用 fingerprint hash 补充
        fp = raw.get("fingerprint") or ""
        fp_hash = hashlib.md5(fp.encode()).hexdigest()[:16]

        return {
            "queryid": raw["queryid"] or fp_hash,
            "service_name": instance.name,
            "database": raw.get("schema_name") or "",
            "schema": raw.get("schema_name") or "",
            "username": "",
            "client_host": self._app_hosts[0] if self._app_hosts else "",
            "replication_set": "",
            "cluster": instance.cluster or "",
            "service_type": "postgresql",
            "service_id": f"postgresql-{instance.id}",
            "environment": instance.environment or "",
            "az": "", "region": "", "node_model": "",
            "node_id": "", "node_name": "", "node_type": "", "machine_id": "",
            "container_name": "", "container_id": "",
            "top_queryid": "", "application_name": "", "planid": "", "cmd_type": "",
            "labels.key": [], "labels.value": [],
            "agent_id": f"pharos-agentless-{instance.id}",
            "agent_type": "qan-postgresql-pgstatements-agent",
            "period_start": now,
            "period_length": instance.collect_interval,
            "fingerprint": fp,
            "example": fp,
            "where_values": [],
            "is_truncated": 0,
            "example_type": "RANDOM",
            "example_metrics": "",
            "tables": [],
            "explain_fingerprint": "", "placeholders_count": 0,
            "top_query": "", "query_plan": "", "plan_summary": "",
            "histogram_items": [],
            "num_queries_with_warnings": 0,
            "warnings.code": [], "warnings.count": [],
            "num_queries_with_errors": 0,
            "errors.code": [], "errors.count": [],
            "num_queries": float(delta["cnt"]),

            # Query time (ms → s)
            "m_query_time_cnt": float(delta["cnt"]),
            "m_query_time_sum": (delta["total_exec_time_ms"] or 0) / ms_to_s,
            "m_query_time_min": (raw.get("min_exec_time_ms") or 0) / ms_to_s,
            "m_query_time_max": (raw.get("max_exec_time_ms") or 0) / ms_to_s,
            "m_query_time_p99": 0,

            # Lock time (PG 无直接对应)
            "m_lock_time_cnt": 0, "m_lock_time_sum": 0,
            "m_lock_time_min": 0, "m_lock_time_max": 0, "m_lock_time_p99": 0,

            # Rows sent
            "m_rows_sent_cnt": float(delta["cnt"]),
            "m_rows_sent_sum": float(delta["rows_sent"]),
            "m_rows_sent_min": 0, "m_rows_sent_max": 0, "m_rows_sent_p99": 0,

            # Rows examined (PG 无直接对应)
            "m_rows_examined_cnt": 0, "m_rows_examined_sum": 0,
            "m_rows_examined_min": 0, "m_rows_examined_max": 0, "m_rows_examined_p99": 0,

            # Rows affected (PG 的 rows 含 affected+returned，近似)
            "m_rows_affected_cnt": float(delta["cnt"]),
            "m_rows_affected_sum": float(delta["rows_sent"]),
            "m_rows_affected_min": 0, "m_rows_affected_max": 0, "m_rows_affected_p99": 0,

            # Rows read
            "m_rows_read_cnt": 0, "m_rows_read_sum": 0,
            "m_rows_read_min": 0, "m_rows_read_max": 0, "m_rows_read_p99": 0,

            # Merge passes
            "m_merge_passes_cnt": 0, "m_merge_passes_sum": 0,
            "m_merge_passes_min": 0, "m_merge_passes_max": 0, "m_merge_passes_p99": 0,

            # InnoDB (PG 无)
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

            # Query length / bytes sent / temp tables
            "m_query_length_cnt": 0, "m_query_length_sum": 0,
            "m_query_length_min": 0, "m_query_length_max": 0, "m_query_length_p99": 0,
            "m_bytes_sent_cnt": 0, "m_bytes_sent_sum": 0,
            "m_bytes_sent_min": 0, "m_bytes_sent_max": 0, "m_bytes_sent_p99": 0,
            "m_tmp_tables_cnt": 0, "m_tmp_tables_sum": 0,
            "m_tmp_tables_min": 0, "m_tmp_tables_max": 0, "m_tmp_tables_p99": 0,
            "m_tmp_disk_tables_cnt": 0, "m_tmp_disk_tables_sum": 0,
            "m_tmp_disk_tables_min": 0, "m_tmp_disk_tables_max": 0, "m_tmp_disk_tables_p99": 0,
            "m_tmp_table_sizes_cnt": 0, "m_tmp_table_sizes_sum": 0,
            "m_tmp_table_sizes_min": 0, "m_tmp_table_sizes_max": 0, "m_tmp_table_sizes_p99": 0,

            # Boolean metrics
            "m_qc_hit_cnt": 0, "m_qc_hit_sum": 0,
            "m_full_scan_cnt": 0, "m_full_scan_sum": 0,
            "m_full_join_cnt": 0, "m_full_join_sum": 0,
            "m_tmp_table_cnt": 0, "m_tmp_table_sum": 0,
            "m_tmp_table_on_disk_cnt": 0, "m_tmp_table_on_disk_sum": 0,
            "m_filesort_cnt": 0, "m_filesort_sum": 0,
            "m_filesort_on_disk_cnt": 0, "m_filesort_on_disk_sum": 0,
            "m_select_full_range_join_cnt": 0, "m_select_full_range_join_sum": 0,
            "m_select_range_cnt": 0, "m_select_range_sum": 0,
            "m_select_range_check_cnt": 0, "m_select_range_check_sum": 0,
            "m_sort_range_cnt": 0, "m_sort_range_sum": 0,
            "m_sort_rows_cnt": 0, "m_sort_rows_sum": 0,
            "m_sort_scan_cnt": 0, "m_sort_scan_sum": 0,
            "m_no_index_used_cnt": 0, "m_no_index_used_sum": 0,
            "m_no_good_index_used_cnt": 0, "m_no_good_index_used_sum": 0,

            # MongoDB (无)
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

            # PostgreSQL 核心指标
            "m_shared_blks_hit_cnt": float(delta["cnt"]),
            "m_shared_blks_hit_sum": float(delta["shared_blks_hit"]),
            "m_shared_blks_read_cnt": float(delta["cnt"]),
            "m_shared_blks_read_sum": float(delta["shared_blks_read"]),
            "m_shared_blks_dirtied_cnt": float(delta["cnt"]),
            "m_shared_blks_dirtied_sum": float(delta["shared_blks_dirtied"]),
            "m_shared_blks_written_cnt": float(delta["cnt"]),
            "m_shared_blks_written_sum": float(delta["shared_blks_written"]),
            "m_local_blks_hit_cnt": float(delta["cnt"]),
            "m_local_blks_hit_sum": float(delta["local_blks_hit"]),
            "m_local_blks_read_cnt": float(delta["cnt"]),
            "m_local_blks_read_sum": float(delta["local_blks_read"]),
            "m_local_blks_dirtied_cnt": float(delta["cnt"]),
            "m_local_blks_dirtied_sum": float(delta["local_blks_dirtied"]),
            "m_local_blks_written_cnt": float(delta["cnt"]),
            "m_local_blks_written_sum": float(delta["local_blks_written"]),
            "m_temp_blks_read_cnt": float(delta["cnt"]),
            "m_temp_blks_read_sum": float(delta["temp_blks_read"]),
            "m_temp_blks_written_cnt": float(delta["cnt"]),
            "m_temp_blks_written_sum": float(delta["temp_blks_written"]),
            "m_shared_blk_read_time_cnt": float(delta["cnt"]),
            "m_shared_blk_read_time_sum": (delta["blk_read_time_ms"] or 0) / ms_to_s,
            "m_shared_blk_write_time_cnt": float(delta["cnt"]),
            "m_shared_blk_write_time_sum": (delta["blk_write_time_ms"] or 0) / ms_to_s,
            "m_local_blk_read_time_cnt": 0, "m_local_blk_read_time_sum": 0,
            "m_local_blk_write_time_cnt": 0, "m_local_blk_write_time_sum": 0,
            "m_cpu_user_time_cnt": 0, "m_cpu_user_time_sum": 0,
            "m_cpu_sys_time_cnt": 0, "m_cpu_sys_time_sum": 0,
            "m_plans_calls_cnt": float(delta["cnt"]),
            "m_plans_calls_sum": float(delta.get("plans") or 0),
            "m_plan_time_cnt": float(delta["cnt"]),
            "m_plan_time_sum": (delta.get("total_plan_time_ms") or 0) / ms_to_s,
            "m_plan_time_min": (raw.get("min_plan_time_ms") or 0) / ms_to_s,
            "m_plan_time_max": (raw.get("max_plan_time_ms") or 0) / ms_to_s,
            "m_wal_records_cnt": float(delta["cnt"]),
            "m_wal_records_sum": float(delta.get("wal_records") or 0),
            "m_wal_fpi_cnt": float(delta["cnt"]),
            "m_wal_fpi_sum": float(delta.get("wal_fpi") or 0),
            "m_wal_bytes_cnt": float(delta["cnt"]),
            "m_wal_bytes_sum": float(delta.get("wal_bytes") or 0),
            "m_wal_buffers_full_cnt": 0, "m_wal_buffers_full_sum": 0,
            "m_parallel_workers_to_launch_cnt": 0, "m_parallel_workers_to_launch_sum": 0,
            "m_parallel_workers_launched_cnt": 0, "m_parallel_workers_launched_sum": 0,
        }
