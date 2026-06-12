"""ClickHouseWriter — 批量写入 metrics 表的单例封装。"""

import logging
from datetime import datetime

from clickhouse_driver import Client
from django.conf import settings

logger = logging.getLogger(__name__)

# metrics 表的列名列表 (按建表顺序)
METRICS_COLUMNS = [
    "queryid", "mysql_digest", "service_name", "database", "schema", "username", "client_host",
    "replication_set", "cluster", "service_type", "service_id",
    "environment", "az", "region", "node_model", "node_id", "node_name",
    "node_type", "machine_id", "container_name", "container_id",
    "top_queryid", "application_name", "planid", "cmd_type",
    "labels.key", "labels.value",
    "agent_id", "agent_type",
    "period_start", "period_length",
    "fingerprint", "example", "is_truncated", "example_type", "example_metrics", "tables",
    "explain_fingerprint", "placeholders_count",
    "top_query", "query_plan", "plan_summary",
    "histogram_items",
    "num_queries_with_warnings", "warnings.code", "warnings.count",
    "num_queries_with_errors", "errors.code", "errors.count",
    "num_queries",
    # MySQL metrics
    "m_query_time_cnt", "m_query_time_sum", "m_query_time_min", "m_query_time_max", "m_query_time_p99",
    "m_lock_time_cnt", "m_lock_time_sum", "m_lock_time_min", "m_lock_time_max", "m_lock_time_p99",
    "m_rows_sent_cnt", "m_rows_sent_sum", "m_rows_sent_min", "m_rows_sent_max", "m_rows_sent_p99",
    "m_rows_examined_cnt", "m_rows_examined_sum", "m_rows_examined_min", "m_rows_examined_max", "m_rows_examined_p99",
    "m_rows_affected_cnt", "m_rows_affected_sum", "m_rows_affected_min", "m_rows_affected_max", "m_rows_affected_p99",
    "m_rows_read_cnt", "m_rows_read_sum", "m_rows_read_min", "m_rows_read_max", "m_rows_read_p99",
    "m_merge_passes_cnt", "m_merge_passes_sum", "m_merge_passes_min", "m_merge_passes_max", "m_merge_passes_p99",
    "m_innodb_io_r_ops_cnt", "m_innodb_io_r_ops_sum", "m_innodb_io_r_ops_min", "m_innodb_io_r_ops_max", "m_innodb_io_r_ops_p99",
    "m_innodb_io_r_bytes_cnt", "m_innodb_io_r_bytes_sum", "m_innodb_io_r_bytes_min", "m_innodb_io_r_bytes_max", "m_innodb_io_r_bytes_p99",
    "m_innodb_io_r_wait_cnt", "m_innodb_io_r_wait_sum", "m_innodb_io_r_wait_min", "m_innodb_io_r_wait_max", "m_innodb_io_r_wait_p99",
    "m_innodb_rec_lock_wait_cnt", "m_innodb_rec_lock_wait_sum", "m_innodb_rec_lock_wait_min", "m_innodb_rec_lock_wait_max", "m_innodb_rec_lock_wait_p99",
    "m_innodb_queue_wait_cnt", "m_innodb_queue_wait_sum", "m_innodb_queue_wait_min", "m_innodb_queue_wait_max", "m_innodb_queue_wait_p99",
    "m_innodb_pages_distinct_cnt", "m_innodb_pages_distinct_sum", "m_innodb_pages_distinct_min", "m_innodb_pages_distinct_max", "m_innodb_pages_distinct_p99",
    "m_query_length_cnt", "m_query_length_sum", "m_query_length_min", "m_query_length_max", "m_query_length_p99",
    "m_bytes_sent_cnt", "m_bytes_sent_sum", "m_bytes_sent_min", "m_bytes_sent_max", "m_bytes_sent_p99",
    "m_tmp_tables_cnt", "m_tmp_tables_sum", "m_tmp_tables_min", "m_tmp_tables_max", "m_tmp_tables_p99",
    "m_tmp_disk_tables_cnt", "m_tmp_disk_tables_sum", "m_tmp_disk_tables_min", "m_tmp_disk_tables_max", "m_tmp_disk_tables_p99",
    "m_tmp_table_sizes_cnt", "m_tmp_table_sizes_sum", "m_tmp_table_sizes_min", "m_tmp_table_sizes_max", "m_tmp_table_sizes_p99",
    # Boolean metrics
    "m_qc_hit_cnt", "m_qc_hit_sum",
    "m_full_scan_cnt", "m_full_scan_sum",
    "m_full_join_cnt", "m_full_join_sum",
    "m_tmp_table_cnt", "m_tmp_table_sum",
    "m_tmp_table_on_disk_cnt", "m_tmp_table_on_disk_sum",
    "m_filesort_cnt", "m_filesort_sum",
    "m_filesort_on_disk_cnt", "m_filesort_on_disk_sum",
    "m_select_full_range_join_cnt", "m_select_full_range_join_sum",
    "m_select_range_cnt", "m_select_range_sum",
    "m_select_range_check_cnt", "m_select_range_check_sum",
    "m_sort_range_cnt", "m_sort_range_sum",
    "m_sort_rows_cnt", "m_sort_rows_sum",
    "m_sort_scan_cnt", "m_sort_scan_sum",
    "m_no_index_used_cnt", "m_no_index_used_sum",
    "m_no_good_index_used_cnt", "m_no_good_index_used_sum",
    # MongoDB metrics
    "m_docs_returned_cnt", "m_docs_returned_sum", "m_docs_returned_min", "m_docs_returned_max", "m_docs_returned_p99",
    "m_response_length_cnt", "m_response_length_sum", "m_response_length_min", "m_response_length_max", "m_response_length_p99",
    "m_docs_scanned_cnt", "m_docs_scanned_sum", "m_docs_scanned_min", "m_docs_scanned_max", "m_docs_scanned_p99",
    "m_docs_examined_cnt", "m_docs_examined_sum", "m_docs_examined_min", "m_docs_examined_max", "m_docs_examined_p99",
    "m_keys_examined_cnt", "m_keys_examined_sum", "m_keys_examined_min", "m_keys_examined_max", "m_keys_examined_p99",
    "m_locks_global_acquire_count_read_shared_cnt", "m_locks_global_acquire_count_read_shared_sum",
    "m_locks_global_acquire_count_write_shared_cnt", "m_locks_global_acquire_count_write_shared_sum",
    "m_locks_database_acquire_count_read_shared_cnt", "m_locks_database_acquire_count_read_shared_sum",
    "m_locks_database_acquire_wait_count_read_shared_cnt", "m_locks_database_acquire_wait_count_read_shared_sum",
    "m_locks_database_time_acquiring_micros_read_shared_cnt", "m_locks_database_time_acquiring_micros_read_shared_sum",
    "m_locks_database_time_acquiring_micros_read_shared_min", "m_locks_database_time_acquiring_micros_read_shared_max", "m_locks_database_time_acquiring_micros_read_shared_p99",
    "m_locks_collection_acquire_count_read_shared_cnt", "m_locks_collection_acquire_count_read_shared_sum",
    "m_storage_bytes_read_cnt", "m_storage_bytes_read_sum", "m_storage_bytes_read_min", "m_storage_bytes_read_max", "m_storage_bytes_read_p99",
    "m_storage_time_reading_micros_cnt", "m_storage_time_reading_micros_sum", "m_storage_time_reading_micros_min", "m_storage_time_reading_micros_max", "m_storage_time_reading_micros_p99",
    # PostgreSQL metrics
    "m_shared_blks_hit_cnt", "m_shared_blks_hit_sum",
    "m_shared_blks_read_cnt", "m_shared_blks_read_sum",
    "m_shared_blks_dirtied_cnt", "m_shared_blks_dirtied_sum",
    "m_shared_blks_written_cnt", "m_shared_blks_written_sum",
    "m_local_blks_hit_cnt", "m_local_blks_hit_sum",
    "m_local_blks_read_cnt", "m_local_blks_read_sum",
    "m_local_blks_dirtied_cnt", "m_local_blks_dirtied_sum",
    "m_local_blks_written_cnt", "m_local_blks_written_sum",
    "m_temp_blks_read_cnt", "m_temp_blks_read_sum",
    "m_temp_blks_written_cnt", "m_temp_blks_written_sum",
    "m_shared_blk_read_time_cnt", "m_shared_blk_read_time_sum",
    "m_shared_blk_write_time_cnt", "m_shared_blk_write_time_sum",
    "m_local_blk_read_time_cnt", "m_local_blk_read_time_sum",
    "m_local_blk_write_time_cnt", "m_local_blk_write_time_sum",
    "m_cpu_user_time_cnt", "m_cpu_user_time_sum",
    "m_cpu_sys_time_cnt", "m_cpu_sys_time_sum",
    "m_plans_calls_cnt", "m_plans_calls_sum",
    "m_plan_time_cnt", "m_plan_time_sum", "m_plan_time_min", "m_plan_time_max",
    "m_wal_records_cnt", "m_wal_records_sum",
    "m_wal_fpi_cnt", "m_wal_fpi_sum",
    "m_wal_bytes_cnt", "m_wal_bytes_sum",
    "m_wal_buffers_full_cnt", "m_wal_buffers_full_sum",
    "m_parallel_workers_to_launch_cnt", "m_parallel_workers_to_launch_sum",
    "m_parallel_workers_launched_cnt", "m_parallel_workers_launched_sum",
]


EXECUTION_PLANS_COLUMNS = [
    "plan_id", "fingerprint", "service_name", "schema",
    "plan_json", "plan_summary", "plan_hash", "query_example",
    "created_at", "instance_id",
]


LOCK_WAITS_COLUMNS = [
    "service_name", "collected_at",
    "waiting_trx_id", "waiting_thread_id", "waiting_query",
    "waiting_trx_started", "waiting_age_seconds",
    "blocking_trx_id", "blocking_thread_id", "blocking_query",
    "lock_type", "lock_mode",
    "lock_object_schema", "lock_object_table", "lock_index", "lock_data",
    "is_deadlock",
]


class ClickHouseWriter:
    """ClickHouse 批量写入单例。"""

    _instance = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_client(self):
        if self._client is None:
            self._client = self._new_client()
        return self._client

    def _new_client(self):
        return Client(
            host=settings.CLICKHOUSE_HOST,
            port=settings.CLICKHOUSE_PORT,
            user=settings.CLICKHOUSE_USER,
            password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DATABASE,
            connect_timeout=5,
            send_receive_timeout=30,
        )

    def _reset_client(self):
        """断开并重置客户端连接（处理连接池异常）。"""
        try:
            if self._client:
                self._client.disconnect()
        except Exception:
            pass
        self._client = None

    def execute(self, sql: str, params=None, with_column_types=True):
        """通用查询接口，返回 (rows, column_types) 元组。"""
        client = self._get_client()
        if hasattr(self, "_last_error"):
            self._reset_client()
            del self._last_error
        return client.execute(sql, params or {}, with_column_types=with_column_types)

    def write_lock_waits(self, rows: list[dict]) -> int:
        """批量写入 lock_waits 表。"""
        if not rows:
            return 0
        client = self._get_client()
        columns = LOCK_WAITS_COLUMNS
        data = [[row.get(col) for col in columns] for row in rows]
        cols_str = ", ".join(f"`{c}`" for c in columns)
        sql = f"INSERT INTO pharos_db.lock_waits ({cols_str}) VALUES"
        try:
            client.execute(sql, data)
            logger.info(f"写入 {len(data)} 行到 ClickHouse lock_waits 表")
            return len(data)
        except Exception as e:
            logger.error(f"ClickHouse lock_waits 写入失败: {e}")
            raise

    def write_metrics(self, rows: list[dict]):
        """批量写入 metrics 表。"""
        if not rows:
            return 0

        client = self._get_client()

        # 按列名顺序提取数据
        columns = list(METRICS_COLUMNS)
        data = []
        for row in rows:
            data.append([row.get(col, "") for col in columns])

        cols_str = ", ".join(f"`{c}`" for c in columns)
        sql = f"INSERT INTO pharos_db.metrics ({cols_str}) VALUES"

        try:
            client.execute(sql, data)
            logger.info(f"写入 {len(data)} 行到 ClickHouse metrics 表")
            return len(data)
        except Exception as e:
            logger.error(f"ClickHouse 写入失败: {e}")
            raise

    def write_execution_plans(self, rows: list[dict]) -> int:
        """批量写入 execution_plans 表。"""
        if not rows:
            return 0
        client = self._get_client()
        columns = EXECUTION_PLANS_COLUMNS
        data = [[row.get(col) for col in columns] for row in rows]
        cols_str = ", ".join(f"`{c}`" for c in columns)
        sql = f"INSERT INTO pharos_db.execution_plans ({cols_str}) VALUES"
        try:
            client.execute(sql, data)
            logger.info(f"写入 {len(data)} 行到 ClickHouse execution_plans 表")
            return len(data)
        except Exception as e:
            logger.error(f"ClickHouse execution_plans 写入失败: {e}")
            raise


def get_writer() -> ClickHouseWriter:
    return ClickHouseWriter()
