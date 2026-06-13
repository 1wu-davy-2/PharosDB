"""QAN 查询服务 — 从 ClickHouse 查询聚合数据。"""

from clickhouse_driver import Client
from django.conf import settings


def _get_client():
    return Client(
        host=settings.CLICKHOUSE_HOST,
        port=settings.CLICKHOUSE_PORT,
        user=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
        database=settings.CLICKHOUSE_DATABASE,
    )


def get_top_queries(service_name: str, period: str = "1h", sort_by: str = "m_query_time_sum",
                    limit: int = 20, search: str = "", schema: str = "", order: str = "DESC"):
    """获取 Top N 慢查询。

    Args:
        service_name: 服务名称
        period: 时间范围 (如 1h, 6h, 24h, 7d)
        sort_by: 排序字段
        limit: 返回条数
        search: SQL 模糊搜索关键词
        schema: schema 过滤
    """
    client = _get_client()

    # 时间范围解析
    interval_map = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800}
    seconds = interval_map.get(period, 3600)

    # 安全的排序字段白名单
    allowed_sort = {
        "m_query_time_sum", "m_lock_time_sum", "m_rows_sent_sum",
        "m_rows_examined_sum", "m_no_index_used_sum", "num_queries",
    }
    if sort_by not in allowed_sort:
        sort_by = "m_query_time_sum"

    # 安全的排序字段映射
    sort_map = {
        "m_query_time_sum": "total_query_time",
        "m_lock_time_sum": "total_lock_time",
        "m_rows_sent_sum": "total_rows_sent",
        "m_rows_examined_sum": "total_rows_examined",
        "m_no_index_used_sum": "no_index_used_count",
        "num_queries": "num_queries",
    }
    order_col = sort_map.get(sort_by, "total_query_time")
    order_dir = "ASC" if order.upper() == "ASC" else "DESC"

    # 构建过滤条件
    params = {"service": service_name, "seconds": seconds, "limit": limit}
    outer_where = ""
    if search:
        outer_where += " WHERE fingerprint LIKE %(search)s"
        params["search"] = f"%{search}%"
    if schema:
        outer_where += (" WHERE" if "WHERE" not in outer_where else " AND") + " `schema` = %(schema)s"
        params["schema"] = schema

    sql = f"""
        SELECT
            queryid,
            fingerprint,
            `schema`,
            num_queries,
            total_query_time,
            if(num_queries > 0, total_query_time / num_queries, 0) AS avg_query_time,
            max_query_time,
            total_rows_sent,
            total_rows_examined,
            total_lock_time,
            no_index_used_count,
            full_scan_count,
            tmp_tables_count,
            example
        FROM (
            SELECT
                queryid,
                any(fingerprint)                  AS fingerprint,
                any(`schema`)                     AS `schema`,
                SUM(num_queries)                  AS num_queries,
                SUM(m_query_time_sum)             AS total_query_time,
                MAX(m_query_time_max)             AS max_query_time,
                SUM(m_rows_sent_sum)              AS total_rows_sent,
                SUM(m_rows_examined_sum)          AS total_rows_examined,
                SUM(m_lock_time_sum)              AS total_lock_time,
                SUM(m_no_index_used_sum)          AS no_index_used_count,
                SUM(m_full_scan_sum)              AS full_scan_count,
                SUM(m_tmp_tables_sum)             AS tmp_tables_count,
                any(example)                      AS example
            FROM pharos_db.metrics
            WHERE service_name = %(service)s
              AND period_start >= now() - INTERVAL %(seconds)s SECOND
            GROUP BY queryid
        )
        {outer_where}
        ORDER BY {order_col} {order_dir}
        LIMIT %(limit)s
    """

    rows = client.execute(sql, params)

    columns = [
        "queryid", "fingerprint", "schema", "num_queries",
        "total_query_time", "avg_query_time", "max_query_time",
        "total_rows_sent", "total_rows_examined", "total_lock_time",
        "no_index_used_count", "full_scan_count", "tmp_tables_count", "example",
    ]

    return [dict(zip(columns, row)) for row in rows]


def get_query_detail(queryid: str, service_name: str, period: str = "1h"):
    """获取单条查询的详细指标。"""
    client = _get_client()

    interval_map = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800}
    seconds = interval_map.get(period, 3600)

    sql = """
        SELECT
            queryid,
            fingerprint,
            `schema`,
            num_queries,
            total_query_time,
            if(num_queries > 0, total_query_time / num_queries, 0) AS avg_query_time,
            max_query_time,
            min_query_time,
            total_lock_time,
            total_rows_sent,
            total_rows_examined,
            total_rows_affected,
            total_rows_read,
            total_merge_passes,
            total_bytes_sent,
            total_tmp_tables,
            total_tmp_disk_tables,
            full_scan_count,
            full_join_count,
            no_index_used_count,
            no_good_index_used_count,
            total_sort_rows,
            total_sort_scan,
            filesort_count,
            example
        FROM (
            SELECT
                queryid,
                any(fingerprint)                  AS fingerprint,
                any(`schema`)                     AS `schema`,
                SUM(num_queries)                  AS num_queries,
                SUM(m_query_time_sum)             AS total_query_time,
                MAX(m_query_time_max)             AS max_query_time,
                MIN(m_query_time_min)             AS min_query_time,
                SUM(m_lock_time_sum)              AS total_lock_time,
                SUM(m_rows_sent_sum)              AS total_rows_sent,
                SUM(m_rows_examined_sum)          AS total_rows_examined,
                SUM(m_rows_affected_sum)          AS total_rows_affected,
                SUM(m_rows_read_sum)              AS total_rows_read,
                SUM(m_merge_passes_sum)           AS total_merge_passes,
                SUM(m_bytes_sent_sum)             AS total_bytes_sent,
                SUM(m_tmp_tables_sum)             AS total_tmp_tables,
                SUM(m_tmp_disk_tables_sum)        AS total_tmp_disk_tables,
                SUM(m_full_scan_sum)              AS full_scan_count,
                SUM(m_full_join_sum)              AS full_join_count,
                SUM(m_no_index_used_sum)          AS no_index_used_count,
                SUM(m_no_good_index_used_sum)     AS no_good_index_used_count,
                SUM(m_sort_rows_sum)              AS total_sort_rows,
                SUM(m_sort_scan_sum)              AS total_sort_scan,
                SUM(m_filesort_sum)               AS filesort_count,
                any(example)                      AS example
            FROM pharos_db.metrics
            WHERE queryid = %(queryid)s
              AND service_name = %(service)s
              AND period_start >= now() - INTERVAL %(seconds)s SECOND
            GROUP BY queryid
        )
    """

    rows = client.execute(sql, {
        "queryid": queryid,
        "service": service_name,
        "seconds": seconds,
    })

    if not rows:
        return None

    columns = [
        "queryid", "fingerprint", "schema", "num_queries",
        "total_query_time", "avg_query_time", "max_query_time", "min_query_time",
        "total_lock_time", "total_rows_sent", "total_rows_examined",
        "total_rows_affected", "total_rows_read", "total_merge_passes",
        "total_bytes_sent", "total_tmp_tables", "total_tmp_disk_tables",
        "full_scan_count", "full_join_count", "no_index_used_count",
        "no_good_index_used_count", "total_sort_rows", "total_sort_scan",
        "filesort_count", "example",
    ]

    return dict(zip(columns, rows[0]))


def get_query_trend(queryid: str, service_name: str, hours: int = 24):
    """获取查询的时间趋势 (按小时聚合)。"""
    client = _get_client()

    sql = """
        SELECT
            hour,
            num_queries,
            total_query_time,
            if(num_queries > 0, total_query_time / num_queries, 0) AS avg_query_time,
            max_query_time,
            total_rows_sent,
            total_rows_examined
        FROM (
            SELECT
                toStartOfHour(period_start)       AS hour,
                SUM(num_queries)                  AS num_queries,
                SUM(m_query_time_sum)             AS total_query_time,
                MAX(m_query_time_max)             AS max_query_time,
                SUM(m_rows_sent_sum)              AS total_rows_sent,
                SUM(m_rows_examined_sum)          AS total_rows_examined
            FROM pharos_db.metrics
            WHERE queryid = %(queryid)s
              AND service_name = %(service)s
              AND period_start >= now() - INTERVAL %(hours)s HOUR
            GROUP BY hour
        )
        ORDER BY hour
    """

    rows = client.execute(sql, {
        "queryid": queryid,
        "service": service_name,
        "hours": hours,
    })

    columns = [
        "hour", "num_queries", "total_query_time", "avg_query_time",
        "max_query_time", "total_rows_sent", "total_rows_examined",
    ]

    return [dict(zip(columns, row)) for row in rows]


def get_overview(service_name: str, period: str = "1h"):
    """获取概览统计。"""
    client = _get_client()

    interval_map = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800}
    seconds = interval_map.get(period, 3600)

    sql = """
        SELECT
            unique_queries,
            total_queries,
            total_query_time,
            if(total_queries > 0, total_query_time / total_queries, 0) AS avg_query_time,
            total_rows_sent,
            total_rows_examined,
            total_lock_time,
            no_index_queries,
            full_scan_queries
        FROM (
            SELECT
                COUNT(DISTINCT queryid)           AS unique_queries,
                SUM(num_queries)                  AS total_queries,
                SUM(m_query_time_sum)             AS total_query_time,
                SUM(m_rows_sent_sum)              AS total_rows_sent,
                SUM(m_rows_examined_sum)          AS total_rows_examined,
                SUM(m_lock_time_sum)              AS total_lock_time,
                SUM(m_no_index_used_sum)          AS no_index_queries,
                SUM(m_full_scan_sum)              AS full_scan_queries
            FROM pharos_db.metrics
            WHERE service_name = %(service)s
              AND period_start >= now() - INTERVAL %(seconds)s SECOND
        )
    """

    rows = client.execute(sql, {
        "service": service_name,
        "seconds": seconds,
    })

    if not rows:
        return {}

    columns = [
        "unique_queries", "total_queries", "total_query_time", "avg_query_time",
        "total_rows_sent", "total_rows_examined", "total_lock_time",
        "no_index_queries", "full_scan_queries",
    ]

    return dict(zip(columns, rows[0]))


def get_service_list():
    """获取所有服务名称列表。"""
    client = _get_client()
    rows = client.execute(
        "SELECT DISTINCT service_name FROM pharos_db.metrics ORDER BY service_name"
    )
    return [row[0] for row in rows]


def _extract_all_tables(plan_summary: str) -> list[dict]:
    """从 plan_summary JSON 中提取所有 access_type=ALL 的 table 节点。"""
    import json as _json
    results = []

    def _walk(node):
        if isinstance(node, list):
            for item in node:
                _walk(item)
        elif isinstance(node, dict):
            if "table_name" in node and node.get("access_type") == "ALL":
                results.append(node)
            for v in node.values():
                _walk(v)

    try:
        _walk(_json.loads(plan_summary))
    except Exception:
        pass
    return results


def index_analysis(service_name: str):
    """索引分析 — 未使用索引 + 缺失索引推荐。"""
    client = _get_client()

    # 1. 未使用索引：最近一次快照中 count_read=0 的索引
    unused = []
    try:
        rows, _cols = client.execute(
            """
            SELECT
                object_schema,
                object_name,
                index_name,
                count_read,
                count_write,
                count_fetch,
                sum_timer_read,
                sum_timer_write
            FROM pharos_db.index_usage
            WHERE service_name = %(svc)s
              AND collected_at = (
                  SELECT max(collected_at)
                  FROM pharos_db.index_usage
                  WHERE service_name = %(svc)s
              )
              AND index_name != ''
              AND count_read = 0
            ORDER BY count_write DESC
            LIMIT 50
            """,
            {"svc": service_name},
            with_column_types=True,
        )
        cols = [c[0] for c in _cols]
        unused = [dict(zip(cols, r)) for r in rows]
    except Exception:
        pass

    # 2. 缺失索引：EXPLAIN 中 access_type=ALL 的查询
    #    用 LIKE 匹配，因为 access_type 嵌套在 table → container 路径下，
    #    JSONExtractString(root, 'access_type') 无法提取嵌套字段。
    missing = []
    try:
        rows, _cols = client.execute(
            """
            SELECT
                fingerprint,
                schema,
                query_example,
                plan_hash,
                plan_summary,
                created_at
            FROM pharos_db.execution_plans
            WHERE service_name = %(svc)s
              AND plan_summary LIKE %(pat)s
            ORDER BY created_at DESC
            LIMIT 20
            """,
            {"svc": service_name, "pat": '%"access_type":"ALL"%'},
            with_column_types=True,
        )
        cols = [c[0] for c in _cols]
        for r in rows:
            d = dict(zip(cols, r))
            plan_summary = d.pop("plan_summary", "{}")
            # 提取 plan_summary 中所有 ALL 扫描的 table 节点
            tables = _extract_all_tables(plan_summary)
            if tables:
                t = tables[0]
                d["tbl"] = t.get("table_name", "")
                d["access_type"] = "ALL"
                d["possible_keys"] = ", ".join(t.get("possible_keys", []) or [])
                d["idx_key"] = t.get("key") or "(none)"
            else:
                d["tbl"] = ""
                d["access_type"] = "ALL"
                d["possible_keys"] = ""
                d["idx_key"] = "(none)"
            missing.append(d)
    except Exception:
        pass

    return {
        "unused_indexes": unused,
        "missing_indexes": missing,
        "summary": {
            "unused_count": len(unused),
            "missing_count": len(missing),
        },
    }
