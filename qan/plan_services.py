"""执行计划查询服务 — 从 ClickHouse execution_plans 表查询。"""

import json
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
        send_receive_timeout=30,
    )


def _row_to_dict(columns, row):
    d = {}
    for i, col in enumerate(columns):
        val = row[i]
        if hasattr(val, "isoformat"):
            val = val.isoformat()
        d[col] = val
    return d


def get_plan_list(fingerprint, service_name=None, limit=50):
    """某 fingerprint 的所有历史计划，按时间倒序。

    fingerprint 支持精确匹配和前缀匹配（自动添加 % 通配符）。
    """
    client = _get_client()
    params = {"limit": limit}

    # 精确匹配优先（fingerprint 有时包含完整文本），
    # 同时支持 LIKE 前缀搜索（给前端调用更宽松）
    fp_cond = "fingerprint = %(fp)s"
    params["fp"] = fingerprint
    # 先用精确匹配，找不到再 LIKE
    rows = _try_query(client, fingerprint, params, exact=True)
    if not rows:
        rows = _try_query(client, fingerprint, params, exact=False)

    if service_name:
        rows = [r for r in rows if r[2] == service_name]

    rows = rows[:limit]

    cols = ["plan_id", "fingerprint", "service_name", "schema",
            "plan_hash", "query_example", "created_at", "instance_id"]
    return [_row_to_dict(cols, r) for r in rows]


def _try_query(client, fingerprint, params, exact=True):
    if exact:
        sql = (
            "SELECT plan_id, fingerprint, service_name, schema, "
            "plan_hash, query_example, created_at, instance_id "
            "FROM pharos_db.execution_plans "
            "WHERE fingerprint = %(fp)s "
            "ORDER BY created_at DESC LIMIT %(limit)s"
        )
    else:
        params = {**params, "fp_like": fingerprint + "%"}
        sql = (
            "SELECT plan_id, fingerprint, service_name, schema, "
            "plan_hash, query_example, created_at, instance_id "
            "FROM pharos_db.execution_plans "
            "WHERE fingerprint LIKE %(fp_like)s "
            "ORDER BY created_at DESC LIMIT %(limit)s"
        )
    try:
        return client.execute(sql, params)
    except Exception:
        return []
    cols = ["plan_id", "fingerprint", "service_name", "schema",
            "plan_hash", "query_example", "created_at", "instance_id"]
    return [_row_to_dict(cols, r) for r in rows]


def get_plan_detail(plan_id):
    """单个计划的完整 JSON。"""
    client = _get_client()
    sql = (
        "SELECT plan_id, fingerprint, service_name, schema, "
        "plan_json, plan_summary, plan_hash, query_example, "
        "created_at, instance_id "
        "FROM pharos_db.execution_plans WHERE plan_id = %(pid)s"
    )
    rows = client.execute(sql, {"pid": plan_id})
    if not rows:
        return None
    cols = ["plan_id", "fingerprint", "service_name", "schema",
            "plan_json", "plan_summary", "plan_hash", "query_example",
            "created_at", "instance_id"]
    return _row_to_dict(cols, rows[0])


def compare_plans(plan_id_a, plan_id_b):
    """对比两个执行计划，返回逐节点 diff。"""
    plan_a = get_plan_detail(plan_id_a)
    plan_b = get_plan_detail(plan_id_b)
    if not plan_a or not plan_b:
        return None

    try:
        summary_a = json.loads(plan_a["plan_summary"])
        summary_b = json.loads(plan_b["plan_summary"])
    except (json.JSONDecodeError, TypeError):
        return {"plan_a": plan_a, "plan_b": plan_b,
                "diff": [], "error": "plan_summary 解析失败"}

    diffs = _compute_diff(summary_a, summary_b)
    return {"plan_a": plan_a, "plan_b": plan_b, "diff": diffs}


# ── diff 引擎 ─────────────────────────────────────────────────────

_ACCESS_RANK = {"system": 0, "const": 1, "eq_ref": 2, "ref": 3,
                "range": 4, "index": 5, "ALL": 6}
_SCALAR_FIELDS = {"access_type", "key", "Extra", "table_name", "filtered"}
_ARRAY_FIELDS = {"possible_keys", "used_columns"}
_BAD_EXTRA = frozenset(["Using filesort", "Using temporary"])


def _compute_diff(node_a, node_b, path="$"):
    diffs = []
    if isinstance(node_a, dict) and isinstance(node_b, dict):
        all_keys = set(node_a.keys()) | set(node_b.keys())
        for key in sorted(all_keys):
            cp = "{}.{}".format(path, key)
            va = node_a.get(key)
            vb = node_b.get(key)
            if key in _SCALAR_FIELDS:
                if va != vb:
                    diffs.append({
                        "path": cp, "field": key,
                        "a": va, "b": vb,
                        "change": _classify(key, va, vb),
                    })
            elif key in _ARRAY_FIELDS:
                sa, sb = set(va or []), set(vb or [])
                if sa != sb:
                    diffs.append({
                        "path": cp, "field": key,
                        "a": va, "b": vb,
                        "change": "modified",
                        "added": sorted(sb - sa),
                        "removed": sorted(sa - sb),
                    })
            elif key == "materialized_from_subquery":
                diffs.extend(_compute_diff(va or {}, vb or {}, cp))
    elif isinstance(node_a, list) and isinstance(node_b, list):
        for i in range(max(len(node_a), len(node_b))):
            ca = node_a[i] if i < len(node_a) else {}
            cb = node_b[i] if i < len(node_b) else {}
            diffs.extend(_compute_diff(ca, cb, "{}[{}]".format(path, i)))
    elif node_a != node_b:
        diffs.append({
            "path": path, "field": "_value",
            "a": node_a, "b": node_b, "change": "modified",
        })
    return diffs


def _classify(field, old_val, new_val):
    """判断变化类型：optimized / degraded / modified。"""
    if field == "access_type":
        or_ = _ACCESS_RANK.get(str(old_val), 99)
        nr = _ACCESS_RANK.get(str(new_val), 99)
        return "optimized" if nr < or_ else ("degraded" if nr > or_ else "modified")
    if field == "key":
        if old_val is None and new_val is not None:
            return "optimized"
        if old_val is not None and new_val is None:
            return "degraded"
        return "modified"
    if field == "Extra":
        ob = bool(_BAD_EXTRA & set(str(old_val or "").split(", ")))
        nb = bool(_BAD_EXTRA & set(str(new_val or "").split(", ")))
        if not ob and nb:
            return "degraded"
        if ob and not nb:
            return "optimized"
        return "modified"
    return "modified"
