"""跨节点关联服务 — 完全 Agentless 的分布式 SQL 关联和锁聚合。

基于集群拓扑 (Step 1) 收窄 JOIN 范围，多维置信度评分 (Step 2)。
所有查询均在 ClickHouse 内完成。
"""

import logging

from clickhouse_driver import Client
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_client():
    return Client(
        host=settings.CLICKHOUSE_HOST,
        port=settings.CLICKHOUSE_PORT,
        user=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
        database=settings.CLICKHOUSE_DATABASE,
        connect_timeout=5,
        send_receive_timeout=60,
    )


def _get_cluster_instances(cluster_name):
    """获取同集群所有实例名称列表。

    Returns list[str] — 可能为空。
    """
    from collector.models import DatabaseInstance

    qs = DatabaseInstance.objects.filter(cluster=cluster_name, is_active=True)
    return [inst.name for inst in qs]


# ═══════════════════════════════════════════════════════════════════
# Step 2: 跨节点 SQL 关联
# ═══════════════════════════════════════════════════════════════════


def get_cross_node_correlations(cluster, start, end, min_confidence=60, limit=200):
    """增强时间窗口关联 — 多维置信度评分。

    Args:
        cluster:        集群名称（限定 JOIN 范围）
        start / end:    ISO 时间范围
        min_confidence: 最小置信度 (0-100)
        limit:          最大返回条数

    Returns:
        { "correlations": [...], "count": N, "cluster": str }
    """
    instance_names = _get_cluster_instances(cluster)
    if len(instance_names) < 2:
        return {"correlations": [], "count": 0, "cluster": cluster,
                "hint": f"集群 '{cluster}' 活跃节点不足 2 个，无法做跨节点关联"}

    client = _get_client()

    params = {
        "instances": instance_names,
        "start": start,
        "end": end,
        "limit": limit,
        "min_conf": min_confidence,
    }

    # ── 多维置信度 JOIN ──
    # ClickHouse 内完成评分，只返回 confidence >= min_confidence 的行
    # 注意: 为兼容无 where_values 列的历史数据，加数据来源判断
    sql = """
    SELECT
        a.service_name         AS node_a,
        b.service_name         AS node_b,
        a.fingerprint,
        a.client_host          AS client_host_a,
        b.client_host          AS client_host_b,
        a.username             AS username_a,
        b.username             AS username_b,
        a.m_query_time_sum     AS query_time_a,
        b.m_query_time_sum     AS query_time_b,
        a.num_queries          AS cnt_a,
        b.num_queries          AS cnt_b,
        a.example              AS example_a,
        b.example              AS example_b,
        abs(toUnixTimestamp(a.period_start) - toUnixTimestamp(b.period_start)) AS diff_seconds,
        multiIf(
            abs(toUnixTimestamp(a.period_start) - toUnixTimestamp(b.period_start)) < 0.2,
            25, 0
        ) AS score_time,
        multiIf(
            a.client_host != '' AND a.client_host = b.client_host,
            40, 0
        ) AS score_host,
        multiIf(
            length(a.where_values) > 0 AND length(b.where_values) > 0
            AND hasAny(a.where_values, b.where_values),
            30, 0
        ) AS score_values,
        multiIf(
            a.username != '' AND b.username != ''
            AND a.username = b.username,
            5, 0
        ) AS score_user,
        (score_time + score_host + score_values + score_user) AS confidence
    FROM pharos_db.metrics AS a
    JOIN pharos_db.metrics AS b
      ON a.fingerprint = b.fingerprint
     AND a.service_name != b.service_name
     AND a.service_name IN %(instances)s
     AND b.service_name IN %(instances)s
     AND a.period_start BETWEEN %(start)s AND %(end)s
     AND b.period_start BETWEEN %(start)s AND %(end)s
     AND abs(toUnixTimestamp(a.period_start) - toUnixTimestamp(b.period_start)) < 5
    HAVING confidence >= %(min_conf)s
    ORDER BY confidence DESC, diff_seconds
    LIMIT %(limit)s
    """

    try:
        rows = client.execute(sql, params)
    except Exception as e:
        logger.error(f"跨节点关联查询失败: {e}")
        return {"correlations": [], "count": 0, "cluster": cluster,
                "error": str(e)}

    columns = [
        "node_a", "node_b", "fingerprint",
        "client_host_a", "client_host_b",
        "username_a", "username_b",
        "query_time_a", "query_time_b",
        "cnt_a", "cnt_b",
        "example_a", "example_b",
        "diff_seconds", "score_time", "score_host", "score_values", "score_user",
        "confidence",
    ]

    correlations = []
    for row in rows:
        d = dict(zip(columns, row))
        # 后处理：补充集群角色
        d["role_a"] = _get_instance_role(d["node_a"])
        d["role_b"] = _get_instance_role(d["node_b"])
        correlations.append(_serialize_correlation(d))

    return {"correlations": correlations, "count": len(correlations), "cluster": cluster}


def _get_instance_role(name):
    try:
        from collector.models import DatabaseInstance
        return DatabaseInstance.objects.filter(name=name).values_list("cluster_role", flat=True).first() or "standalone"
    except Exception:
        return "standalone"


def _serialize_correlation(d):
    return {
        "node_a": d["node_a"],
        "role_a": d["role_a"],
        "node_b": d["node_b"],
        "role_b": d["role_b"],
        "fingerprint": d.get("fingerprint", ""),
        "client_host_a": d.get("client_host_a", ""),
        "client_host_b": d.get("client_host_b", ""),
        "query_time_a": round(d.get("query_time_a", 0), 6),
        "query_time_b": round(d.get("query_time_b", 0), 6),
        "cnt_a": int(d.get("cnt_a", 0)),
        "cnt_b": int(d.get("cnt_b", 0)),
        "diff_seconds": round(d.get("diff_seconds", 0), 4),
        "confidence": int(d.get("confidence", 0)),
        "score_breakdown": {
            "time": int(d.get("score_time", 0)),
            "host": int(d.get("score_host", 0)),
            "values": int(d.get("score_values", 0)),
            "user": int(d.get("score_user", 0)),
        },
        "example_a": (d.get("example_a", "") or "")[:300],
        "example_b": (d.get("example_b", "") or "")[:300],
    }


# ═══════════════════════════════════════════════════════════════════
# Step 3: 跨节点锁聚合
# ═══════════════════════════════════════════════════════════════════


def get_cross_node_locks(cluster, start, end, limit=200):
    """跨节点锁关联 — (schema, table, row_data) 三元组确定性匹配。

    同一行数据在两个不同节点上同时存在锁等待 → 分布式锁竞争。
    确定性 100%，不是概率。
    """
    instance_names = _get_cluster_instances(cluster)
    if len(instance_names) < 2:
        return {"locks": [], "count": 0, "cluster": cluster,
                "hint": f"集群 '{cluster}' 活跃节点不足 2 个"}

    client = _get_client()

    sql = """
    SELECT
        a.service_name            AS blocker_node,
        b.service_name            AS waiter_node,
        a.lock_object_schema      AS `schema`,
        a.lock_object_table       AS `table`,
        a.lock_data               AS row_id,
        a.blocking_trx_id         AS blocker_trx,
        a.blocking_query          AS blocker_query,
        b.waiting_trx_id          AS waiter_trx,
        b.waiting_query           AS waiter_query,
        b.waiting_age_seconds     AS wait_age_secs,
        a.collected_at            AS blocker_time,
        b.collected_at            AS waiter_time,
        b.is_deadlock             AS is_deadlock
    FROM pharos_db.lock_waits a
    JOIN pharos_db.lock_waits b
      ON a.lock_object_schema  = b.lock_object_schema
     AND a.lock_object_table   = b.lock_object_table
     AND a.lock_data           = b.lock_data
     AND a.service_name        != b.service_name
     AND a.service_name        IN %(instances)s
     AND b.service_name        IN %(instances)s
     AND abs(toUnixTimestamp(a.collected_at) - toUnixTimestamp(b.collected_at)) < 30
    WHERE a.collected_at BETWEEN %(start)s AND %(end)s
    ORDER BY a.collected_at DESC
    LIMIT %(limit)s
    """

    try:
        rows = client.execute(sql, {
            "instances": instance_names,
            "start": start,
            "end": end,
            "limit": limit,
        })
    except Exception as e:
        logger.error(f"跨节点锁查询失败: {e}")
        return {"locks": [], "count": 0, "cluster": cluster, "error": str(e)}

    columns = [
        "blocker_node", "waiter_node", "schema", "table", "row_id",
        "blocker_trx", "blocker_query",
        "waiter_trx", "waiter_query", "wait_age_secs",
        "blocker_time", "waiter_time", "is_deadlock",
    ]

    locks = []
    for row in rows:
        d = dict(zip(columns, row))
        d["blocker_time"] = d["blocker_time"].isoformat() if hasattr(d["blocker_time"], "isoformat") else str(d["blocker_time"])
        d["waiter_time"] = d["waiter_time"].isoformat() if hasattr(d["waiter_time"], "isoformat") else str(d["waiter_time"])
        d["is_deadlock"] = bool(d.get("is_deadlock", 0))
        d["role_a"] = _get_instance_role(d["blocker_node"])
        d["role_b"] = _get_instance_role(d["waiter_node"])
        locks.append(d)

    return {"locks": locks, "count": len(locks), "cluster": cluster}
