"""Celery 任务 — 数据采集。"""

import logging
import time

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


def _do_collect(instance, triggered_by: str) -> dict:
    """执行单实例采集并写入 CollectionHistory，返回结果 dict。"""
    from .clickhouse import ClickHouseWriter
    from .collectors.mysql import MySQLCollector
    from .models import CollectionHistory

    started_at = timezone.now()
    t0 = time.monotonic()

    history = CollectionHistory(
        instance=instance,
        triggered_by=triggered_by,
        status="failed",
        started_at=started_at,
    )

    try:
        if instance.db_type == "mysql":
            collector = MySQLCollector(instance)
            rows = collector.run()
        else:
            raise NotImplementedError(f"暂不支持 {instance.db_type} 采集器")

        count = 0
        if rows:
            writer = ClickHouseWriter()
            count = writer.write_metrics(rows)

        instance.last_collected_at = timezone.now()
        instance.save(update_fields=["last_collected_at"])

        history.status = "success"
        history.queries_collected = len(rows)
        history.rows_written = count

        result = {
            "instance": instance.name,
            "queries_collected": len(rows),
            "rows_written": count,
        }
    except Exception as e:
        history.status = "failed"
        history.error_message = str(e)
        logger.error(f"[{instance.name}] 采集失败: {e}")
        result = {"error": str(e)}
    finally:
        history.finished_at = timezone.now()
        history.duration_ms = int((time.monotonic() - t0) * 1000)
        history.save()

    return result


@shared_task(name="collector.collect_all_metrics")
def collect_all_metrics():
    """遍历所有活跃实例，执行采集。由 Celery Beat 定时触发。"""
    from .models import DatabaseInstance

    instances = DatabaseInstance.objects.filter(is_active=True)
    total_rows = 0

    for instance in instances:
        result = _do_collect(instance, triggered_by="scheduled")
        if "rows_written" in result:
            total_rows += result["rows_written"]
            logger.info(
                f"[{instance.name}] 采集完成: {result['queries_collected']} 查询, "
                f"{result['rows_written']} 行写入"
            )

    return {"instances": instances.count(), "rows_written": total_rows}


@shared_task(name="collector.collect_instance")
def collect_instance(instance_id: int):
    """单实例采集 — 供 beat 调度复用。"""
    from .models import DatabaseInstance

    try:
        instance = DatabaseInstance.objects.get(id=instance_id)
    except DatabaseInstance.DoesNotExist:
        logger.error(f"实例 {instance_id} 不存在")
        return {"error": f"实例 {instance_id} 不存在"}

    return _do_collect(instance, triggered_by="scheduled")
