"""采集任务函数。_do_collect 被调度器和手动触发共享调用。"""

import logging
import time

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
