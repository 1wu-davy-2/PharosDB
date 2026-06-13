"""锁链拓扑 API。

- LockTopologyView:  实时查询 performance_schema，返回 nodes/edges 图结构
- LockHistoryView:   查询 ClickHouse lock_waits，返回历史死锁事件列表
"""

import logging

import pymysql
from rest_framework.response import Response
from rest_framework.views import APIView

from collector.crypto import decrypt
from collector.models import DatabaseInstance

logger = logging.getLogger(__name__)


def _build_topology(rows: list[dict]) -> dict:
    """将锁等待行转换为 nodes + edges 图结构。

    节点类型：
      - blocker: 仅持锁（不等待）
      - waiter:  仅等待锁（不持锁）
      - both:    既持锁又等待锁（链式阻塞中间节点）
      - deadlock: 参与死锁环的节点
    """
    from collector.collectors.lock_snapshot import detect_deadlock_cycles

    blockers = {str(r["blocking_trx_id"]) for r in rows}
    waiters  = {str(r["waiting_trx_id"])  for r in rows}

    edges_raw = [(str(r["blocking_trx_id"]), str(r["waiting_trx_id"])) for r in rows]
    cycles = detect_deadlock_cycles(edges_raw)
    deadlock_nodes: set[str] = {n for cycle in cycles for n in cycle}

    thread_info: dict[str, dict] = {}
    for r in rows:
        bid = str(r["blocking_trx_id"])
        wid = str(r["waiting_trx_id"])
        thread_info.setdefault(bid, {
            "trx_id": bid,
            "thread_id": int(r.get("blocking_thread_id") or 0),
            "query": (r.get("blocking_query") or "")[:512],
        })
        thread_info.setdefault(wid, {
            "trx_id": wid,
            "thread_id": int(r.get("waiting_thread_id") or 0),
            "query": (r.get("waiting_query") or "")[:512],
        })

    nodes = []
    for trx_id, info in thread_info.items():
        is_blocker = trx_id in blockers
        is_waiter  = trx_id in waiters
        if trx_id in deadlock_nodes:
            node_type = "deadlock"
        elif is_blocker and is_waiter:
            node_type = "both"
        elif is_blocker:
            node_type = "blocker"
        else:
            node_type = "waiter"
        nodes.append({**info, "type": node_type})

    edges = []
    seen_edges: set[tuple] = set()
    for r in rows:
        bid = str(r["blocking_trx_id"])
        wid = str(r["waiting_trx_id"])
        key = (bid, wid)
        if key not in seen_edges:
            seen_edges.add(key)
            edges.append({
                "source": bid,
                "target": wid,
                "lock_type":  r.get("lock_type", ""),
                "lock_mode":  r.get("lock_mode", ""),
                "object_schema": r.get("object_schema") or r.get("lock_object_schema", ""),
                "object_table":  r.get("object_name")  or r.get("lock_object_table", ""),
                "index_name":    r.get("index_name", ""),
                "lock_data":     (r.get("lock_data") or "")[:256],
                "wait_secs":     int(r.get("waiting_query_secs") or 0),
            })

    return {
        "nodes": nodes,
        "edges": edges,
        "has_deadlock": bool(cycles),
        "deadlock_cycles": cycles,
    }


class LockTopologyView(APIView):
    """GET /api/locks/topology/?instance_id=<id>

    实时从 performance_schema 拉取锁等待链，返回图结构。
    不经过 ClickHouse，延迟最低。
    """

    def get(self, request):
        instance_id = request.query_params.get("instance_id")
        if not instance_id:
            return Response({"error": "instance_id 参数必填"}, status=400)

        try:
            instance = DatabaseInstance.objects.get(pk=instance_id)
        except DatabaseInstance.DoesNotExist:
            return Response({"error": "实例不存在"}, status=404)

        if instance.db_type != "mysql":
            return Response({"error": "仅支持 MySQL/MariaDB 实例"}, status=400)

        try:
            from collector.collectors.lock_snapshot import LockSnapshotCollector
            collector = LockSnapshotCollector(instance)
            conn = collector._connect()
            try:
                sql = collector._pick_sql()
                with conn.cursor() as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"[LockTopology] 查询失败 instance={instance_id}: {e}")
            return Response({"error": str(e)}, status=500)

        if not rows:
            return Response({
                "nodes": [], "edges": [],
                "has_deadlock": False, "deadlock_cycles": [],
            })

        return Response(_build_topology(rows))


class LockHistorySnapshotView(APIView):
    """GET /api/locks/history-snapshot/?service_name=xxx&ts=1750938940

    查询 ClickHouse 中某次锁快照的全部行，还原锁链拓扑图。
    ts 参数为 Unix 时间戳（与历史列表中的 ts 字段一致）。
    """

    def get(self, request):
        svc = request.query_params.get("service_name")
        ts = request.query_params.get("ts")
        if not svc or not ts:
            return Response({"error": "service_name 和 ts 参数必填"}, status=400)

        sql = """
            SELECT
                service_name,
                collected_at,
                waiting_trx_id,
                waiting_thread_id,
                waiting_query,
                waiting_age_seconds,
                blocking_trx_id,
                blocking_thread_id,
                blocking_query,
                lock_type,
                lock_mode,
                lock_object_schema,
                lock_object_table,
                lock_index,
                lock_data,
                is_deadlock
            FROM pharos_db.lock_waits
            WHERE service_name = %(svc)s
              AND toInt32(toUnixTimestamp(collected_at)) = toInt32(%(ts)s)
            LIMIT 200
        """

        try:
            from collector.clickhouse import ClickHouseWriter
            rows, _cols = ClickHouseWriter().execute(sql, {"svc": svc, "ts": ts})
        except Exception as e:
            logger.error(f"[LockHistorySnapshot] ClickHouse 查询失败: {e}")
            return Response({"error": str(e)}, status=500)

        if not rows:
            return Response({"nodes": [], "edges": [], "has_deadlock": False, "deadlock_cycles": []})

        col_names = [
            "service_name", "collected_at",
            "waiting_trx_id", "waiting_thread_id", "waiting_query",
            "waiting_query_secs",  # CH 列是 waiting_age_seconds，映射为 _build_topology 期望的字段名
            "blocking_trx_id", "blocking_thread_id", "blocking_query",
            "lock_type", "lock_mode",
            "lock_object_schema", "lock_object_table", "lock_index", "lock_data",
            "is_deadlock",
        ]
        rows_dict = [dict(zip(col_names, r)) for r in rows]
        result = _build_topology(rows_dict)
        result["collected_at"] = rows_dict[0].get("collected_at")
        return Response(result)


class LockHistoryView(APIView):
    """GET /api/locks/history/?instance_id=<id>&hours=1&deadlock_only=false

    查询 ClickHouse lock_waits 表，返回过去 N 小时的锁等待摘要。
    """

    def get(self, request):
        instance_id = request.query_params.get("instance_id")
        if not instance_id:
            return Response({"error": "instance_id 参数必填"}, status=400)

        try:
            instance = DatabaseInstance.objects.get(pk=instance_id)
        except DatabaseInstance.DoesNotExist:
            return Response({"error": "实例不存在"}, status=404)

        hours = min(int(request.query_params.get("hours", 1)), 24)
        deadlock_only = request.query_params.get("deadlock_only", "false").lower() == "true"

        sql = """
            SELECT
                toUnixTimestamp(collected_at)    AS ts,
                waiting_trx_id,
                waiting_thread_id,
                waiting_query,
                waiting_age_seconds,
                blocking_trx_id,
                blocking_thread_id,
                blocking_query,
                lock_type,
                lock_mode,
                lock_object_schema,
                lock_object_table,
                lock_index,
                lock_data,
                is_deadlock
            FROM pharos_db.lock_waits
            WHERE service_name = %(svc)s
              AND collected_at >= now() - INTERVAL %(hours)s HOUR
              {deadlock_filter}
            ORDER BY collected_at DESC
            LIMIT 500
        """.format(deadlock_filter="AND is_deadlock = 1" if deadlock_only else "")

        try:
            from collector.clickhouse import ClickHouseWriter
            result, col_types = ClickHouseWriter().execute(sql, {"svc": instance.name, "hours": hours})
        except Exception as e:
            logger.error(f"[LockHistory] ClickHouse 查询失败: {e}")
            return Response({"error": str(e)}, status=500)

        col_names = [c[0] for c in col_types]
        rows = [dict(zip(col_names, row)) for row in result]
        return Response({"rows": rows, "total": len(rows)})
