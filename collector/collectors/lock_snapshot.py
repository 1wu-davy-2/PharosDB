"""活跃锁链拓扑采集器。

- 自动检测 MySQL/MariaDB 版本，选择对应采集 SQL
- 死锁检测：有向等待图 + DFS 环检测，不依赖 INNODB STATUS 文本解析
- 返回 LockCollectResult，供调度器决定下次轮询间隔
"""

import logging
from datetime import datetime, timezone

import pymysql

from ..crypto import decrypt
from ..version_detect import parse_mysql_version

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 采集 SQL（两个版本）
# ─────────────────────────────────────────────────────────────

# MySQL 8.0+ / MariaDB 10.5+  — performance_schema.data_lock_waits
_SQL_P8 = """
SELECT
    w.REQUESTING_ENGINE_TRANSACTION_ID   AS waiting_trx_id,
    tw.PROCESSLIST_ID                    AS waiting_thread_id,
    IFNULL(tw.PROCESSLIST_INFO, '')      AS waiting_query,
    IFNULL(tw.PROCESSLIST_TIME, 0)       AS waiting_query_secs,
    w.BLOCKING_ENGINE_TRANSACTION_ID     AS blocking_trx_id,
    tb.PROCESSLIST_ID                    AS blocking_thread_id,
    IFNULL(tb.PROCESSLIST_INFO, '')      AS blocking_query,
    l.LOCK_TYPE                          AS lock_type,
    l.LOCK_MODE                          AS lock_mode,
    IFNULL(l.OBJECT_SCHEMA, '')          AS object_schema,
    IFNULL(l.OBJECT_NAME,   '')          AS object_name,
    IFNULL(l.INDEX_NAME,    '')          AS index_name,
    IFNULL(l.LOCK_DATA,     '')          AS lock_data
FROM performance_schema.data_lock_waits w
JOIN performance_schema.data_locks l
    ON  l.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.threads tw
    ON  tw.THREAD_ID = w.REQUESTING_THREAD_ID
JOIN performance_schema.threads tb
    ON  tb.THREAD_ID = w.BLOCKING_THREAD_ID
"""

# MySQL 5.7 / MariaDB < 10.5  — information_schema.*
_SQL_57 = """
SELECT
    r.trx_id                                         AS waiting_trx_id,
    r.trx_mysql_thread_id                            AS waiting_thread_id,
    IFNULL(r.trx_query, '')                          AS waiting_query,
    TIMESTAMPDIFF(SECOND, r.trx_wait_started, NOW()) AS waiting_query_secs,
    b.trx_id                                         AS blocking_trx_id,
    b.trx_mysql_thread_id                            AS blocking_thread_id,
    IFNULL(b.trx_query, '')                          AS blocking_query,
    lk.lock_type                                     AS lock_type,
    lk.lock_mode                                     AS lock_mode,
    ''                                               AS object_schema,
    lk.lock_table                                    AS object_name,
    IFNULL(lk.lock_index, '')                        AS index_name,
    ''                                               AS lock_data
FROM information_schema.INNODB_LOCK_WAITS w
JOIN information_schema.INNODB_TRX        r  ON r.trx_id  = w.requesting_trx_id
JOIN information_schema.INNODB_TRX        b  ON b.trx_id  = w.blocking_trx_id
JOIN information_schema.INNODB_LOCKS      lk ON lk.lock_id = w.requested_lock_id
"""


# ─────────────────────────────────────────────────────────────
# 死锁环检测（等待图 DFS）
# ─────────────────────────────────────────────────────────────

def detect_deadlock_cycles(edges: list[tuple[str, str]]) -> list[list[str]]:
    """在 blocker→waiter 有向图里找环（死锁）。

    Args:
        edges: [(blocking_trx_id, waiting_trx_id), ...]

    Returns:
        每个死锁环是一个 trx_id 列表（首尾相同）。
    """
    # 等待图：waiter → 它依赖的 blockers（标准 wait-for graph 方向）
    graph: dict[str, list[str]] = {}
    all_nodes: set[str] = set()
    for blocker, waiter in edges:
        graph.setdefault(waiter, []).append(blocker)
        all_nodes.update([blocker, waiter])

    visited: set[str] = set()
    rec_stack: set[str] = set()
    cycles: list[list[str]] = []

    def dfs(node: str, path: list[str]):
        visited.add(node)
        rec_stack.add(node)
        path.append(node)
        for nbr in graph.get(node, []):
            if nbr not in visited:
                dfs(nbr, path)
            elif nbr in rec_stack:
                idx = path.index(nbr)
                cycles.append(path[idx:] + [nbr])
        path.pop()
        rec_stack.discard(node)

    for node in sorted(all_nodes):
        if node not in visited:
            dfs(node, [])

    return cycles


# ─────────────────────────────────────────────────────────────
# 结果对象
# ─────────────────────────────────────────────────────────────

class LockCollectResult:
    def __init__(
        self,
        success: bool,
        lock_count: int = 0,
        has_deadlock: bool = False,
        deadlock_cycles: list | None = None,
        raw_rows: list | None = None,
        error: str = "",
    ):
        self.success = success
        self.lock_count = lock_count
        self.has_deadlock = has_deadlock
        self.deadlock_cycles = deadlock_cycles or []
        self.raw_rows = raw_rows or []
        self.error = error

    @property
    def has_locks(self) -> bool:
        return self.lock_count > 0


# ─────────────────────────────────────────────────────────────
# 采集器
# ─────────────────────────────────────────────────────────────

class LockSnapshotCollector:
    """采集 MySQL 活跃锁等待，写入 ClickHouse lock_waits 表。"""

    def __init__(self, instance):
        self.instance = instance

    def _connect(self):
        return pymysql.connect(
            host=self.instance.host,
            port=self.instance.port,
            user=self.instance.username,
            password=decrypt(self.instance.password),
            connect_timeout=5,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def _pick_sql(self) -> str:
        """根据实例已存储的 db_version 选择对应的采集 SQL。

        版本在实例注册时已写入 db_version 字段，采集时直接读取，
        不再每次连接查询 VERSION()，省去一次额外的连接开销。
        """
        version_str = self.instance.db_version
        if not version_str:
            logger.warning(f"[LockCollector] {self.instance.name} db_version 为空，回退到 57 SQL")
            return _SQL_57

        major, minor, is_mariadb = parse_mysql_version(version_str)

        if is_mariadb:
            # data_lock_waits 在 MariaDB 10.6+ 才引入
            return _SQL_P8 if (major == 10 and minor >= 6) else _SQL_57
        return _SQL_P8 if major >= 8 else _SQL_57

    def collect(self) -> LockCollectResult:
        try:
            conn = self._connect()
        except Exception as e:
            logger.error(f"[LockCollector] {self.instance.name} 连接失败: {e}")
            return LockCollectResult(success=False, error=str(e))

        try:
            return self._do_collect(conn)
        finally:
            conn.close()

    def _do_collect(self, conn) -> LockCollectResult:
        sql = self._pick_sql()
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

        if not rows:
            return LockCollectResult(success=True, lock_count=0)

        # 死锁检测
        edges = [(str(r["blocking_trx_id"]), str(r["waiting_trx_id"])) for r in rows]
        cycles = detect_deadlock_cycles(edges)
        has_deadlock = bool(cycles)

        if has_deadlock:
            logger.warning(
                f"[LockCollector] {self.instance.name} 检测到死锁！环: {cycles}"
            )

        # 写 ClickHouse
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        ch_rows = []
        for r in rows:
            ch_rows.append({
                "service_name":       self.instance.name,
                "collected_at":       now,
                "waiting_trx_id":     str(r.get("waiting_trx_id", "")),
                "waiting_thread_id":  int(r.get("waiting_thread_id") or 0),
                "waiting_query":      (r.get("waiting_query") or "")[:2048],
                "waiting_trx_started": now,
                "waiting_age_seconds": int(r.get("waiting_query_secs") or 0),
                "blocking_trx_id":    str(r.get("blocking_trx_id", "")),
                "blocking_thread_id": int(r.get("blocking_thread_id") or 0),
                "blocking_query":     (r.get("blocking_query") or "")[:2048],
                "lock_type":          r.get("lock_type", ""),
                "lock_mode":          r.get("lock_mode", ""),
                "lock_object_schema": r.get("object_schema", ""),
                "lock_object_table":  r.get("object_name", ""),
                "lock_index":         r.get("index_name", ""),
                "lock_data":          (r.get("lock_data") or "")[:512],
                "is_deadlock":        1 if has_deadlock else 0,
            })

        try:
            from ..clickhouse import ClickHouseWriter
            ClickHouseWriter().write_lock_waits(ch_rows)
        except Exception as e:
            logger.error(f"[LockCollector] ClickHouse 写入失败: {e}")

        return LockCollectResult(
            success=True,
            lock_count=len(rows),
            has_deadlock=has_deadlock,
            deadlock_cycles=cycles,
            raw_rows=rows,
        )
