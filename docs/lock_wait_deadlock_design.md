# 锁等待 / 死锁可视化 — 设计与实现

## 背景

PMM 对 MySQL 锁等待的支持仅限于基础指标（`m_innodb_rec_lock_wait`），无法展示**哪个事务阻塞了哪个事务**的拓扑关系。PharosDB 以 `performance_schema.data_lock_waits` / `information_schema.INNODB_LOCK_WAITS` 为数据源，实时构建锁链拓扑图，并将历史快照写入 ClickHouse 供回溯分析，填补这一空白。

---

## 整体架构

```
MySQL / MariaDB
  └─ performance_schema.data_lock_waits   (8.0+ / MariaDB 10.6+)
  └─ information_schema.INNODB_LOCK_WAITS (5.7  / MariaDB <10.6)
        │
        ▼  LockSnapshotCollector (每实例独立线程)
        │   ├─ 版本自动检测 → 选择对应 SQL
        │   ├─ DFS 死锁环检测
        │   └─ 写入 ClickHouse lock_waits 表
        │
  ┌─────┴──────┐
  │            │
实时 API      历史 API
/api/locks/  /api/locks/
topology/    history/
  │            │
  └─────┬──────┘
        ▼
  React LockPage
  SVG 锁链拓扑图 + 历史表格
```

---

## 采集层

### MySQL 版本自动检测

连接后执行 `SELECT VERSION()`，解析版本字符串，自动选择对应 SQL，无需用户配置：

| 数据库            | 条件                   | 使用的表                                   |
|-------------------|------------------------|--------------------------------------------|
| MySQL             | major >= 8             | `performance_schema.data_lock_waits`       |
| MySQL             | major < 8              | `information_schema.INNODB_LOCK_WAITS`     |
| MariaDB           | major=10, minor >= 6   | `performance_schema.data_lock_waits`       |
| MariaDB           | 其他                   | `information_schema.INNODB_LOCK_WAITS`     |

```python
# collector/collectors/lock_snapshot.py
def _pick_sql(self, conn) -> str:
    version_str = ...  # SELECT VERSION()
    if is_mariadb:
        return _SQL_P8 if (major == 10 and minor >= 6) else _SQL_57
    return _SQL_P8 if major >= 8 else _SQL_57
```

> MariaDB 10.5 不包含 `data_lock_waits`，该表在 10.6.0 才引入，边界取 minor >= 6。

### 采集 SQL

**P8 版（MySQL 8+ / MariaDB 10.6+）**

```sql
SELECT
    w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx_id,
    tw.PROCESSLIST_ID                  AS waiting_thread_id,
    tw.PROCESSLIST_INFO                AS waiting_query,
    tw.PROCESSLIST_TIME                AS waiting_query_secs,
    w.BLOCKING_ENGINE_TRANSACTION_ID   AS blocking_trx_id,
    tb.PROCESSLIST_ID                  AS blocking_thread_id,
    tb.PROCESSLIST_INFO                AS blocking_query,
    l.LOCK_TYPE, l.LOCK_MODE,
    l.OBJECT_SCHEMA, l.OBJECT_NAME, l.INDEX_NAME, l.LOCK_DATA
FROM performance_schema.data_lock_waits w
JOIN performance_schema.data_locks  l  ON l.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.threads     tw ON tw.THREAD_ID = w.REQUESTING_THREAD_ID
JOIN performance_schema.threads     tb ON tb.THREAD_ID = w.BLOCKING_THREAD_ID
```

**57 版（MySQL 5.7 / MariaDB <10.6）**

```sql
SELECT
    r.trx_id                                         AS waiting_trx_id,
    r.trx_mysql_thread_id                            AS waiting_thread_id,
    r.trx_query                                      AS waiting_query,
    TIMESTAMPDIFF(SECOND, r.trx_wait_started, NOW()) AS waiting_query_secs,
    b.trx_id                                         AS blocking_trx_id,
    b.trx_mysql_thread_id                            AS blocking_thread_id,
    b.trx_query                                      AS blocking_query,
    lk.lock_type, lk.lock_mode, lk.lock_table, lk.lock_index
FROM information_schema.INNODB_LOCK_WAITS  w
JOIN information_schema.INNODB_TRX         r  ON r.trx_id  = w.requesting_trx_id
JOIN information_schema.INNODB_TRX         b  ON b.trx_id  = w.blocking_trx_id
JOIN information_schema.INNODB_LOCKS       lk ON lk.lock_id = w.requested_lock_id
```

### 死锁检测（DFS 环检测）

不依赖 `SHOW ENGINE INNODB STATUS` 文本解析（跨版本格式不稳定），而是直接对等待行构建**有向等待图**，用 DFS + 递归栈检测环：

```python
def detect_deadlock_cycles(edges: list[tuple[str, str]]) -> list[list[str]]:
    # edges: [(blocking_trx_id, waiting_trx_id), ...]
    # 等待图方向：waiter → blocker
    graph = {}
    for blocker, waiter in edges:
        graph.setdefault(waiter, []).append(blocker)

    visited, rec_stack, cycles = set(), set(), []

    def dfs(node, path):
        visited.add(node); rec_stack.add(node); path.append(node)
        for nbr in graph.get(node, []):
            if nbr not in visited:
                dfs(nbr, path)
            elif nbr in rec_stack:          # 找到环
                idx = path.index(nbr)
                cycles.append(path[idx:] + [nbr])
        path.pop(); rec_stack.discard(node)

    for node in sorted(all_nodes):
        if node not in visited:
            dfs(node, [])
    return cycles
```

### 自适应轮询调度器

每个 MySQL 实例独立一个 `LockScheduler` 线程，无锁时 30s 轮询，检测到活跃锁后自动切换 5s 高频模式，锁消失后恢复 30s：

```
无锁状态  ──[发现锁]──▶  高频模式(5s)
   ▲                         │
   └──────[锁清除]────────────┘
```

```python
# collector/scheduler.py  LockScheduler._run()
if result.has_locks:
    self._high_freq = True
    self._schedule_next(INTERVAL_ACTIVE)   # 5s
else:
    self._high_freq = False
    self._schedule_next(INTERVAL_IDLE)     # 30s
```

Django 启动时由 `CollectorConfig.ready()` → `lock_registry.load_from_db()` 自动恢复所有 active MySQL 实例的调度。

---

## 存储层（ClickHouse）

表：`pharos_db.lock_waits`

```sql
CREATE TABLE pharos_db.lock_waits (
    service_name        LowCardinality(String),
    collected_at        DateTime,
    waiting_trx_id      String,
    waiting_thread_id   UInt64,
    waiting_query       String,
    waiting_trx_started DateTime,
    waiting_age_seconds UInt32,
    blocking_trx_id     String,
    blocking_thread_id  UInt64,
    blocking_query      String,
    lock_type           LowCardinality(String),
    lock_mode           LowCardinality(String),
    lock_object_schema  LowCardinality(String),
    lock_object_table   LowCardinality(String),
    lock_index          String,
    lock_data           String,
    is_deadlock         UInt8 DEFAULT 0
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(collected_at)
ORDER BY (service_name, collected_at, waiting_trx_id)
TTL collected_at + INTERVAL 30 DAY;
```

- 按月分区，自动 TTL 30 天
- `is_deadlock` 由采集时 DFS 检测结果写入，查询时无需重新计算

---

## API 层

### `GET /api/locks/topology/?instance_id=<id>`

实时从 MySQL `performance_schema` / `information_schema` 查询，不经过 ClickHouse，延迟最低。返回 nodes + edges 图结构：

```json
{
  "nodes": [
    {"trx_id": "1234", "thread_id": 42, "query": "UPDATE ...", "type": "blocker"},
    {"trx_id": "1235", "thread_id": 43, "query": "UPDATE ...", "type": "waiter"}
  ],
  "edges": [
    {"source": "1234", "target": "1235", "lock_mode": "X", "wait_secs": 12, ...}
  ],
  "has_deadlock": false,
  "deadlock_cycles": []
}
```

节点类型：

| type       | 含义                   | 颜色   |
|------------|------------------------|--------|
| `blocker`  | 仅持锁，不等待         | 红     |
| `waiter`   | 仅等待锁               | 橙     |
| `both`     | 既持锁又等待（链式中间）| 紫     |
| `deadlock` | 参与死锁环             | 黄     |

### `GET /api/locks/history/?instance_id=<id>&hours=1&deadlock_only=false`

查询 ClickHouse `lock_waits` 表，返回过去 N 小时（最多 24h）的锁等待记录，最多 500 条，支持仅返回死锁事件。

---

## 前端

### 技术方案

- **纯 SVG + 自实现 Force Layout**：不引入 d3，使用约 120 tick 的弹簧-排斥物理模拟确定节点位置
- **有向箭头**：每种节点颜色独立 SVG `<marker>`，箭头颜色跟随源节点
- **5s 自动刷新**：实时拓扑页面 checkbox 控制，开启时 `setInterval(fetchTopology, 5000)`
- **点击节点**：右侧 Drawer 展示事务详情（Thread ID、SQL、节点类型）
- **点击历史行**：右侧 Drawer 展示该条锁等待的完整 SQL 和锁对象信息

### 组件结构

```
LockPage
 ├─ FilterBar        实例选择 / Tab 切换 / 自动刷新 / 历史过滤
 ├─ LockGraph        SVG 拓扑图（实时 tab）
 │    └─ useForceLayout  纯 JS 物理仿真 hook
 ├─ HistoryTable     锁等待历史表格（历史 tab）
 └─ DetailDrawer     节点 / 历史行详情侧滑板
```

### Force Layout 算法

```
每帧 120 tick：
  1. 节点间排斥力    F = REPULSION / dist²
  2. 边的弹簧吸引力  F = SPRING_K × (dist - SPRING_LEN)
  3. 向画布中心的重力 F = CENTER_K × (center - pos)
  4. 速度衰减        v *= DAMPING (0.8)
  5. 位置更新 + 边界 clamp
```

位置结果缓存在 `useRef`，仅在 nodes/edges 变化时重新计算。

---

## 文件清单

| 文件 | 说明 |
|------|------|
| `collector/collectors/lock_snapshot.py` | 核心采集器，版本检测、SQL 执行、DFS 死锁检测、写 ClickHouse |
| `collector/scheduler.py` | `LockScheduler` + `LockSchedulerRegistry`，自适应调度 |
| `collector/apps.py` | Django 启动时初始化锁采集调度 |
| `collector/clickhouse.py` | 新增 `write_lock_waits()` + `execute()` 方法 |
| `locks/__init__.py` | Django app |
| `locks/apps.py` | AppConfig |
| `locks/views.py` | `LockTopologyView` + `LockHistoryView` |
| `locks/urls.py` | URL 路由 |
| `clickhouse_schema/02_lock_waits_table.sql` | ClickHouse 建表 DDL |
| `frontend/src/pages/LockPage.jsx` | 前端主页面 |
| `frontend/src/pages/LockPage.css` | 样式（全量 CSS 变量，支持暗色模式）|
| `frontend/src/i18n/locales/zh.json` | 新增 `locks.*` 中文翻译 |
| `frontend/src/i18n/locales/en.json` | 新增 `locks.*` 英文翻译 |
