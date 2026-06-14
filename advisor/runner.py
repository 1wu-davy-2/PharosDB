"""巡检执行引擎 — 纯 Python，无 Starlark 依赖。

直接复用 collector 的连接逻辑，对每个启用的实例执行巡检 SQL，
结果写入 AdvisorFinding 表。
"""

import logging
from datetime import datetime, timezone

from django.utils import timezone as djangotz

from .models import AdvisorCheck, AdvisorFinding

logger = logging.getLogger(__name__)


def run_check(check, instance):
    """对单个实例执行一条巡检规则。

    Args:
        check: AdvisorCheck 实例
        instance: DatabaseInstance 实例

    Returns:
        AdvisorFinding or None
    """
    from collector.crypto import decrypt

    password = decrypt(instance.password)

    if instance.db_type in ("mysql",):
        return _run_mysql(check, instance, password)
    elif instance.db_type == "postgresql":
        return _run_postgresql(check, instance, password)

    return None


def _connect_mysql(instance, password):
    import pymysql
    return pymysql.connect(
        host=instance.host, port=instance.port,
        user=instance.username, password=password,
        connect_timeout=10, charset="utf8mb4",
    )


def _run_mysql(check, instance, password):
    import pymysql

    conn = None
    cur = None
    try:
        conn = _connect_mysql(instance, password)
        cur = conn.cursor(pymysql.cursors.DictCursor)
        cur.execute(check.query)
        rows = cur.fetchall()

        finding = _evaluate(check, rows, instance)
        return finding
    except Exception as e:
        logger.warning(f"[advisor] {check.name} on {instance.name} failed: {e}")
        return None
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


def _run_postgresql(check, instance, password):
    import psycopg2
    import psycopg2.extras

    conn = None
    cur = None
    try:
        conn = psycopg2.connect(
            host=instance.host, port=instance.port,
            user=instance.username, password=password,
            connect_timeout=10,
        )
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(check.query)
        rows = cur.fetchall()

        finding = _evaluate(check, rows, instance)
        return finding
    except Exception as e:
        logger.warning(f"[advisor] {check.name} on {instance.name} failed: {e}")
        return None
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


def _evaluate(check, rows, instance):
    """根据 check.mode 评估查询结果。

    exists 模式: 有行 → 记录发现
    threshold 模式: 第一行指定列的值 > threshold → 记录发现
    """
    if check.mode == "exists":
        if rows:
            return _create_finding(check, instance, rows)
        return None

    if check.mode == "threshold" and rows:
        col = check.threshold_column or "value"
        val = rows[0].get(col, 0)
        try:
            val = float(val)
        except (TypeError, ValueError):
            val = 0
        if val > check.threshold:
            detail = f"当前值 {val} > 阈值 {check.threshold}"
            return _create_finding(check, instance, rows, detail)
        return None

    return None


def _create_finding(check, instance, rows, extra_detail=""):
    """创建 AdvisorFinding 记录。"""
    # 格式化查询结果为可读文本
    sample = ""
    try:
        import json as _json
        sample = _json.dumps(rows[:3], ensure_ascii=False, default=str)[:2000]
    except Exception:
        sample = str(rows)[:2000]

    detail = check.description or ""
    if extra_detail:
        detail = extra_detail + "\n" + detail

    # 自动解决之前的相同发现（同一 check+instance）
    AdvisorFinding.objects.filter(
        advisor_check=check, instance=instance, resolved_at__isnull=True,
    ).update(resolved_at=djangotz.now())

    return AdvisorFinding.objects.create(
        advisor_check=check,
        instance=instance,
        severity=check.severity,
        summary=check.summary,
        detail=f"{detail}\n\n查询结果:\n{sample}" if sample else detail,
        labels={
            "instance_name": instance.name,
            "instance_type": instance.db_type,
            "check_name": check.name,
        },
    )


# ═══════════════════════════════════════════════════════════════════
# 批量巡检调度
# ═══════════════════════════════════════════════════════════════════

def run_all_checks():
    """对全部启用实例运行全部启用规则（服务启动时 + 定时调用）。"""
    from collector.models import DatabaseInstance

    checks = AdvisorCheck.objects.filter(enabled=True)
    instances = DatabaseInstance.objects.filter(is_active=True, connection_status="connected")

    total_findings = 0
    for check in checks:
        # 过滤数据库类型
        if check.family == "mysql":
            targets = instances.filter(db_type="mysql")
        elif check.family == "postgresql":
            targets = instances.filter(db_type="postgresql")
        elif check.family == "mongodb":
            targets = instances.filter(db_type="mongodb")
        else:
            targets = instances.all()

        for inst in targets:
            finding = run_check(check, inst)
            if finding:
                total_findings += 1

    logger.info(f"[advisor] 巡检完成: {checks.count()} 条规则, {total_findings} 项发现")
    return total_findings


def run_check_on_instance(check_name, instance_id):
    """手动触发：对指定实例运行指定规则。"""
    from collector.models import DatabaseInstance

    try:
        check = AdvisorCheck.objects.get(name=check_name, enabled=True)
        inst = DatabaseInstance.objects.get(pk=instance_id, is_active=True)
    except (AdvisorCheck.DoesNotExist, DatabaseInstance.DoesNotExist):
        return None

    return run_check(check, inst)
