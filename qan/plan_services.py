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


_JSON_COLUMNS = {"plan_json", "plan_summary"}


def _row_to_dict(columns, row):
    """Raw ClickHouse row → dict, auto-parsing JSON columns."""
    d = {}
    for i, col in enumerate(columns):
        val = row[i]
        if hasattr(val, "isoformat"):
            val = val.isoformat()
        if col in _JSON_COLUMNS and isinstance(val, str):
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass  # keep as string if unparseable
        d[col] = val
    return d


_PLAN_LIST_COLS = [
    "plan_id", "fingerprint", "service_name", "schema",
    "plan_json", "plan_summary", "plan_hash", "query_example",
    "created_at", "instance_id",
]
_COL_CSV = ", ".join(_PLAN_LIST_COLS)


def get_plan_list(fingerprint, service_name=None, limit=50):
    """某 fingerprint 的所有历史计划（含完整 JSON），按时间倒序。

    fingerprint 支持精确匹配和 LIKE 前缀匹配。
    返回结果包含 plan_json / plan_summary，前端可直接渲染树形结构。
    """
    client = _get_client()
    rows = _try_query(client, fingerprint, limit=limit, exact=True)
    if not rows:
        rows = _try_query(client, fingerprint, limit=limit, exact=False)

    if service_name:
        rows = [r for r in rows if r[2] == service_name]

    rows = rows[:limit]
    return [_row_to_dict(_PLAN_LIST_COLS, r) for r in rows]


def _try_query(client, fingerprint, limit=50, exact=True):
    params = {"fp": fingerprint, "limit": limit}

    if exact:
        sql = (
            f"SELECT {_COL_CSV} FROM pharos_db.execution_plans "
            "WHERE fingerprint = %(fp)s "
            "ORDER BY created_at DESC LIMIT %(limit)s"
        )
    else:
        params["fp_like"] = fingerprint + "%"
        sql = (
            f"SELECT {_COL_CSV} FROM pharos_db.execution_plans "
            "WHERE fingerprint LIKE %(fp_like)s "
            "ORDER BY created_at DESC LIMIT %(limit)s"
        )
    try:
        return client.execute(sql, params)
    except Exception:
        return []


def get_plan_detail(plan_id):
    """单个计划的完整 JSON（plan_json / plan_summary 已解析为 dict）。"""
    client = _get_client()
    sql = (
        f"SELECT {_COL_CSV} FROM pharos_db.execution_plans "
        "WHERE plan_id = %(pid)s"
    )
    rows = client.execute(sql, {"pid": plan_id})
    if not rows:
        return None
    return _row_to_dict(_PLAN_LIST_COLS, rows[0])


def compare_plans(plan_id_a, plan_id_b):
    """对比两个执行计划，返回逐节点 diff。"""
    plan_a = get_plan_detail(plan_id_a)
    plan_b = get_plan_detail(plan_id_b)
    if not plan_a or not plan_b:
        return None

    summary_a = plan_a.get("plan_summary", {})
    summary_b = plan_b.get("plan_summary", {})

    # _row_to_dict 已解析 JSON 列；兜底处理 string 情况
    if isinstance(summary_a, str):
        try:
            summary_a = json.loads(summary_a)
        except (json.JSONDecodeError, TypeError):
            return {"plan_a": plan_a, "plan_b": plan_b,
                    "diff": [], "error": "plan_summary 解析失败"}
    if isinstance(summary_b, str):
        try:
            summary_b = json.loads(summary_b)
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
    """判断变化类型：optimized / degraded / modified。

    一方为 None（旧采集器未提取到该字段）时不判为优化/退化，仅标记 modified。
    """
    if field == "access_type":
        if old_val is None or new_val is None:
            return "modified"
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
