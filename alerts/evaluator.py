"""
告警评估器 — 每 5 分钟由线程调度器调用。
数据源：ClickHouse pharos_db.metrics 表（与 QAN 共用）。
"""

import logging

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── ClickHouse 查询模板 ──────────────────────────────────────────────────────
# 所有查询针对 pharos_db.metrics，按 service_name 过滤，period 用秒表示

_QUERIES = {
    # 周期内平均查询耗时 > threshold 秒的慢查询条数（按 queryid 去重后计算）
    "slow_query_time": """
        SELECT countIf(avg_query_time > %(threshold)s)
        FROM (
            SELECT
                queryid,
                if(SUM(num_queries) > 0,
                   SUM(m_query_time_sum) / SUM(num_queries), 0) AS avg_query_time
            FROM pharos_db.metrics
            WHERE service_name = %(service)s
              AND period_start >= now() - INTERVAL %(seconds)s SECOND
            GROUP BY queryid
        )
    """,

    # 无索引查询占总查询的百分比
    "no_index_ratio": """
        SELECT if(SUM(num_queries) = 0, 0,
            SUM(m_no_index_used_sum) * 100.0 / SUM(num_queries)
        )
        FROM pharos_db.metrics
        WHERE service_name = %(service)s
          AND period_start >= now() - INTERVAL %(seconds)s SECOND
    """,

    # 周期内总查询执行次数
    "query_count": """
        SELECT SUM(num_queries)
        FROM pharos_db.metrics
        WHERE service_name = %(service)s
          AND period_start >= now() - INTERVAL %(seconds)s SECOND
    """,
}


def _get_ch_client():
    from clickhouse_driver import Client
    from django.conf import settings
    return Client(
        host=settings.CLICKHOUSE_HOST,
        port=settings.CLICKHOUSE_PORT,
        user=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
        database=settings.CLICKHOUSE_DATABASE,
        connect_timeout=5,
        send_receive_timeout=30,
    )


def _query_metric(rule, instance) -> float | None:
    """对单个实例执行规则查询，返回指标值，失败或无数据返回 None。"""
    params = {
        "service": instance.name,
        "threshold": rule.threshold,
        "seconds": rule.period * 60,
    }

    if rule.rule_type == "custom_sql":
        if not rule.custom_sql.strip():
            return None
        sql = rule.custom_sql
    else:
        sql = _QUERIES[rule.rule_type]

    try:
        client = _get_ch_client()
        rows = client.execute(sql, params)
        if rows and rows[0][0] is not None:
            return float(rows[0][0])
    except Exception as e:
        logger.error(f"[alert] CH 查询失败 rule={rule.id} instance={instance.name}: {e}")
    return None


def _send_webhook(event) -> None:
    """发送 Alertmanager 兼容格式的 Webhook 通知。"""
    url = event.rule.webhook_url
    if not url:
        return

    payload = {
        "version": "4",
        "status": event.status,
        "alerts": [{
            "status": event.status,
            "labels": {
                "alertname": event.rule.name,
                "rule_type": event.rule.rule_type,
                "severity":  event.rule.severity,
                "instance":  event.instance.name if event.instance else "all",
            },
            "annotations": {
                "metric_value": str(event.metric_value),
                "threshold":    str(event.threshold),
                "description":  event.rule.description,
            },
            "startsAt": event.fired_at.isoformat(),
            "endsAt":   event.resolved_at.isoformat() if event.resolved_at else "0001-01-01T00:00:00Z",
            "generatorURL": f"/alerts/rules/{event.rule_id}/",
        }],
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        event.notified = True
        event.notify_error = ""
        logger.info(f"[alert] Webhook 发送成功 event={event.id} status={event.status}")
    except Exception as e:
        event.notify_error = str(e)
        logger.error(f"[alert] Webhook 失败 event={event.id}: {e}")
    finally:
        event.save(update_fields=["notified", "notify_error"])


def _evaluate_single(rule, instance) -> None:
    """单规则 × 单实例的状态机：firing / resolved。"""
    from .models import AlertEvent

    value = _query_metric(rule, instance)
    if value is None:
        return

    is_firing = value > rule.threshold

    active = (
        AlertEvent.objects
        .filter(rule=rule, instance=instance, status="firing")
        .order_by("-fired_at")
        .first()
    )

    if is_firing and not active:
        event = AlertEvent.objects.create(
            rule=rule,
            instance=instance,
            metric_value=value,
            threshold=rule.threshold,
            status="firing",
        )
        logger.warning(
            f"[alert] FIRING rule={rule.name} instance={instance.name} "
            f"value={value:.3f} threshold={rule.threshold}"
        )
        _send_webhook(event)

    elif not is_firing and active:
        active.status = "resolved"
        active.resolved_at = timezone.now()
        active.save(update_fields=["status", "resolved_at"])
        logger.info(
            f"[alert] RESOLVED rule={rule.name} instance={instance.name} value={value:.3f}"
        )
        _send_webhook(active)


def evaluate_all_rules() -> dict:
    """主入口，被调度器每 5 分钟调用一次。"""
    from .models import AlertRule
    from collector.models import DatabaseInstance

    rules = list(AlertRule.objects.filter(is_enabled=True).select_related("instance"))
    if not rules:
        return {"evaluated": 0}

    all_instances = list(DatabaseInstance.objects.filter(is_active=True))
    count = 0

    for rule in rules:
        targets = [rule.instance] if rule.instance_id else all_instances
        for inst in targets:
            if inst is None:
                continue
            try:
                _evaluate_single(rule, inst)
                count += 1
            except Exception as e:
                logger.error(f"[alert] evaluate_single 异常 rule={rule.id} instance={inst.id}: {e}")

    return {"evaluated": count}
