"""索引使用统计采集器。

从 performance_schema.table_io_waits_summary_by_index_usage 采集每个索引的读写计数，
写入 ClickHouse index_usage 表，用于未使用索引 / 冗余索引自动检测。

MySQL 5.6+ / MariaDB 10.5+ 均支持该表。
"""

import logging
from datetime import datetime, timezone

import pymysql

from ..crypto import decrypt

logger = logging.getLogger(__name__)

# 每次采集间隔 (秒) — 独立于 metrics 采集频率
INTERVAL = 900  # 15 min

_SQL = """
    SELECT
        COALESCE(OBJECT_SCHEMA, '') AS object_schema,
        COALESCE(OBJECT_NAME, '')   AS object_name,
        COALESCE(INDEX_NAME, '')    AS index_name,
        COUNT_READ                  AS count_read,
        COUNT_WRITE                 AS count_write,
        COUNT_FETCH                 AS count_fetch,
        SUM_TIMER_READ              AS sum_timer_read,
        SUM_TIMER_WRITE             AS sum_timer_write
    FROM performance_schema.table_io_waits_summary_by_index_usage
    WHERE OBJECT_SCHEMA NOT IN (
        'mysql', 'sys', 'performance_schema', 'information_schema'
    )
    ORDER BY OBJECT_SCHEMA, OBJECT_NAME, INDEX_NAME
"""


class IndexUsageCollector:
    """采集 MySQL/MariaDB 的索引使用统计，写入 ClickHouse。"""

    def __init__(self, instance):
        self.instance = instance
        # 上次快照缓存，用于去重: key="schema.table.index" → (count_read, count_write)
        self._last_snapshot: dict[str, tuple[int, int]] = {}

    def _connect(self):
        return pymysql.connect(
            host=self.instance.host,
            port=self.instance.port,
            user=self.instance.username,
            password=decrypt(self.instance.password),
            connect_timeout=5,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def collect(self) -> int:
        """采集索引使用统计，返回写入行数。仅写入有变化的行。"""
        try:
            conn = self._connect()
        except Exception as e:
            logger.error(f"[IndexUsage] {self.instance.name} 连接失败: {e}")
            return 0

        try:
            with conn.cursor() as cur:
                cur.execute(_SQL)
                rows = cur.fetchall()
        except Exception as e:
            logger.error(f"[IndexUsage] {self.instance.name} 查询失败: {e}")
            return 0
        finally:
            conn.close()

        if not rows:
            return 0

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        changed = []
        new_snapshot = {}

        for r in rows:
            key = f"{r['object_schema']}.{r['object_name']}.{r['index_name']}"
            cr = int(r["count_read"] or 0)
            cw = int(r["count_write"] or 0)
            new_snapshot[key] = (cr, cw)

            last = self._last_snapshot.get(key)
            if last is None or last != (cr, cw):
                changed.append(r)

        self._last_snapshot = new_snapshot

        if not changed:
            return 0

        ch_rows = []
        for r in changed:
            ch_rows.append({
                "service_name": self.instance.name,
                "collected_at": now,
                "object_schema": r["object_schema"],
                "object_name": r["object_name"],
                "index_name": r["index_name"],
                "count_read": int(r["count_read"] or 0),
                "count_write": int(r["count_write"] or 0),
                "count_fetch": int(r["count_fetch"] or 0),
                "sum_timer_read": int(r["sum_timer_read"] or 0),
                "sum_timer_write": int(r["sum_timer_write"] or 0),
            })

        try:
            from ..clickhouse import get_writer
            get_writer().write_index_usage(ch_rows)
            logger.info(f"[IndexUsage] {self.instance.name} 写入 {len(ch_rows)} 条变化")
        except Exception as e:
            logger.error(f"[IndexUsage] {self.instance.name} ClickHouse 写入失败: {e}")

        return len(ch_rows)
