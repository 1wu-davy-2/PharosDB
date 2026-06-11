"""Celery 任务 — 数据采集。"""

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="collector.collect_all_metrics")
def collect_all_metrics():
    """遍历所有活跃实例，执行采集。由 Celery Beat 定时触发。"""
    from .clickhouse import ClickHouseWriter
    from .collectors.mysql import MySQLCollector
    from .models import DatabaseInstance

    instances = DatabaseInstance.objects.filter(is_active=True)
    total_rows = 0

    for instance in instances:
        try:
            if instance.db_type == "mysql":
                collector = MySQLCollector(instance)
                rows = collector.run()

                if rows:
                    writer = ClickHouseWriter()
                    count = writer.write_metrics(rows)
                    total_rows += count

                instance.last_collected_at = timezone.now()
                instance.save(update_fields=["last_collected_at"])
                logger.info(f"[{instance.name}] 采集完成: {len(rows)} 查询, {count} 行写入")
            else:
                logger.warning(f"[{instance.name}] 暂不支持 {instance.db_type} 采集器")
        except Exception as e:
            logger.error(f"[{instance.name}] 采集失败: {e}")

    return {"instances": instances.count(), "rows_written": total_rows}


@shared_task(name="collector.collect_instance")
def collect_instance(instance_id: int):
    """单实例采集 — 供手动触发和 beat 调度复用。"""
    from .clickhouse import ClickHouseWriter
    from .collectors.mysql import MySQLCollector
    from .models import DatabaseInstance

    try:
        instance = DatabaseInstance.objects.get(id=instance_id)
    except DatabaseInstance.DoesNotExist:
        logger.error(f"实例 {instance_id} 不存在")
        return {"error": f"实例 {instance_id} 不存在"}

    if instance.db_type != "mysql":
        return {"error": f"暂不支持 {instance.db_type} 采集器"}

    try:
        collector = MySQLCollector(instance)
        rows = collector.run()

        if rows:
            writer = ClickHouseWriter()
            count = writer.write_metrics(rows)
        else:
            count = 0

        instance.last_collected_at = timezone.now()
        instance.save(update_fields=["last_collected_at"])

        return {
            "instance": instance.name,
            "queries_collected": len(rows),
            "rows_written": count,
        }
    except Exception as e:
        logger.error(f"[{instance.name}] 采集失败: {e}")
        return {"error": str(e)}
