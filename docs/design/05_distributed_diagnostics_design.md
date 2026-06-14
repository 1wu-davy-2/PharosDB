# 分布式跨节点诊断 — 实现方案（完全 Agentless）

## 问题定义

> 分布式数据库跨节点诊断难：分布式锁、跨节点慢查询无全局视图，各节点日志孤立，无法拼接完整事务链路。

### PharosDB 核心约束

- **完全 Agentless**：无 agent 进程运行在应用侧，无法注入 trace context
- **不改应用代码**：SQL comment 方案（方案 A）本质是 APM 的活，数据库监控不应要求应用配合
- ClickHouse 已有单节点数据：`metrics` / `lock_waits` / `execution_plans`
- `DatabaseInstance.cluster` 字段存在但未使用

### 去掉方案 A 之后，能用的武器

| 方案 | 本质 | 状态 |
|------|------|------|
| **D — 集群拓扑** | 让系统知道哪些节点属于同一个集群，各节点的角色（primary/replica/shard） | ← 地基，必须先做 |
| **B — 增强时间窗口关联** | 多维置信度评分，关联同一集群内节点间的 SQL | ← 核心能力，D 之后做 |
| **C — eBPF/proxy** | 网络层抓包解析协议 | 运维复杂度不适合当前团队，暂不做 |

---

## 架构

```
┌─────────────────────────────────────────────────────┐
│                    集群层 (D)                         │
│  cluster_id = "galera-prod-01"                       │
│    ├── mariadb-prod-01  (primary,  role=writer)      │
│    ├── mariadb-prod-02  (replica,  role=reader)      │
│    └── mariadb-prod-03  (replica,  role=reader)      │
│                                                      │
│  D 提供约束 → 跨节点关联只在同 cluster_id 内执行      │
│  没有 D：全量 JOIN，又慢又乱                          │
│  有 D：收窄到同集群节点，查询有意义、结果可解释        │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│                  关联层 (B)                           │
│                                                      │
│  维度                  来源                权重       │
│  ──────────────────────────────────────────────      │
│  client_host 相同     metrics.client_host    ★★★     │
│  时间差 < 200ms       metrics.period_start   ★★      │
│  WHERE 值匹配         原始 SQL 文本提取      ★★★     │
│  DB user 相同         metrics.username       ★       │
│                                                      │
│  → 置信度评分 (0-100)，只展示 score ≥ 60             │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│                分布式锁层 (Step 3)                    │
│                                                      │
│  lock_object_schema + lock_object_table + lock_data  │
│  跨 service_name JOIN → 同一行数据在不同节点上的      │
│  锁持有/等待关系                                     │
└─────────────────────────────────────────────────────┘
```

---

## Step 1：集群拓扑增强（地基）

**不做完这一步，后续所有跨节点分析都没有语义。**

### 1.1 DatabaseInstance 新增字段

```python
# collector/models.py
cluster_role = models.CharField(
    "集群角色", max_length=20,
    choices=[("primary","Primary"), ("replica","Replica"),
             ("shard","Shard"), ("standalone","Standalone")],
    default="standalone",
)
```

### 1.2 自动角色检测

```
MySQL / MariaDB:
  SHOW REPLICA STATUS  → 有结果 = replica
  wsrep_incoming_addresses → Galera 集群成员检测
  SELECT @@read_only    → ON = replica

PostgreSQL:
  SELECT pg_is_in_recovery()  → true = replica / standby
  pg_stat_wal_receiver        → 有记录 = 正在接收 WAL
```

### 1.3 采集时写入 client_host

```
MySQL:    performance_schema.threads.PROCESSLIST_HOST
PG:       pg_stat_activity.client_addr
写入:     ClickHouse metrics.client_host 列（已有但未采集）
```

**这是 Step 2 关联的核心维度，不存 client_host 后续无法做同源关联。**

### 1.4 前端变更

- InstancesPage：Cluster 列支持分组折叠，显示角色标签（Primary/Replica）
- Dashboard：集群卡片，首行展示 `cluster_id` → 下方节点列表及角色标识

### 改动清单

| 模块 | 改动 |
|------|------|
| `collector/models.py` | 加 `cluster_role` + migration |
| `collector/collectors/mysql.py` | `collect()` 加 `client_host` 采集 + 角色自动检测 |
| `collector/collectors/postgresql.py` | 同上 |
| `clickhouse_schema/` | `metrics` 表确认 `client_host` 列存在 |

---

## Step 2：增强时间窗口关联（核心能力）

### 2.1 为什么单纯 fingerprint + 时间窗口不够

同一条 SQL `UPDATE orders SET status=? WHERE order_id=?` 被成百上千个不同请求并发执行，时间窗口 + 指纹根本无法区分 "是同一业务事务" 还是 "另一个请求的同类 SQL"。

### 2.2 多维置信度评分模型

```
confidence = Σ(weight × match)

维度                  weight   匹配规则
────────────────────────────────────────────
client_host 相同       40       a.client_host = b.client_host AND != ""
时间差 < 200ms         25       abs(diff_ms) < 200
WHERE 值匹配           30       同一业务主键出现在两个节点
DB user 相同            5       a.username = b.username AND != "" AND not system
────────────────────────────────────────────
满分                  100
展示阈值               60
```

### 2.3 WHERE 值提取

这是**最被低估的增强点**。`events_statements_history_long.SQL_TEXT` 存的是带实际参数的原始 SQL：

```
-- fingerprint: SELECT * FROM orders WHERE order_id = ?
-- raw SQL:      SELECT * FROM orders WHERE order_id = 12345
-- raw SQL:      SELECT * FROM orders WHERE order_id = 67890
```

从原始 SQL 中提取 `order_id = 12345` 的 **实际值** 存入 ClickHouse 新列 `where_values`（JSON array），关联时：

```sql
-- 简化示意：两个节点都在操作 order_id=12345 → 高置信度
WHERE arrayIntersect(
    JSONExtract(a.where_values, 'Array(String)'),
    JSONExtract(b.where_values, 'Array(String)')
) != []
```

### 2.4 ClickHouse 关联查询

```sql
SELECT
    a.service_name    AS node_a,
    b.service_name    AS node_b,
    a.fingerprint,
    a.client_host,
    a.total_query_time,
    b.total_query_time,
    abs(toUnixTimestamp(a.period_start) - toUnixTimestamp(b.period_start)) AS diff_ms,

    -- 置信度计算
    (CASE WHEN a.client_host != '' AND a.client_host = b.client_host THEN 40 ELSE 0 END
   + CASE WHEN abs(toUnixTimestamp(a.period_start) - toUnixTimestamp(b.period_start)) < 0.2 THEN 25 ELSE 0 END
   + CASE WHEN arrayIntersect(a.where_values_arr, b.where_values_arr) != [] THEN 30 ELSE 0 END
   + CASE WHEN a.username != '' AND a.username = b.username THEN 5 ELSE 0 END
    ) AS confidence

FROM metrics a
JOIN metrics b
  ON a.fingerprint = b.fingerprint
 AND a.service_name != b.service_name
 AND a.service_name IN (SELECT name FROM collector_database_instance WHERE cluster = %(cluster)s)
 AND b.service_name IN (SELECT name FROM collector_database_instance WHERE cluster = %(cluster)s)
 AND a.period_start BETWEEN %(start)s AND %(end)s
 AND b.period_start BETWEEN %(start)s AND %(end)s
 AND abs(toUnixTimestamp(a.period_start) - toUnixTimestamp(b.period_start)) < 5

HAVING confidence >= 60
ORDER BY confidence DESC, diff_ms
LIMIT 200
```

**D 的价值在这里体现**：`IN (同 cluster 节点名)` 把 JOIN 范围收窄，跨集群的相同 SQL 不会被误关联。

### 2.5 API

```
GET /api/qan/cross-node/correlation/
  ?cluster=galera-prod-01
  &start=2026-06-14T00:00:00
  &end=2026-06-14T01:00:00
  &min_confidence=60

Response:
{
  "correlations": [
    {
      "node_a": "mariadb-prod-01",   "role_a": "primary",
      "node_b": "mariadb-prod-02",   "role_b": "replica",
      "fingerprint": "UPDATE orders SET ...",
      "client_host": "10.0.1.50",
      "diff_ms": 85,
      "confidence": 95,
      "matched_where_values": ["order_id=12345"],
      "query_example": "..."
    },
    ...
  ],
  "count": 47
}
```

### 改动清单

| 模块 | 改动 |
|------|------|
| ClickHouse `metrics` | `ALTER TABLE ADD COLUMN where_values Array(String) DEFAULT []` |
| `MySQLCollector` | `collect()` 从 raw SQL 提取 WHERE 值（正则），写入 `client_host` + `where_values` |
| `qan/services.py` | 新增 `get_cross_node_correlations(cluster, start, end, min_confidence)` |
| `qan/views.py` | 新增 `CrossNodeCorrelationView` |
| `qan/urls.py` | 新增路由 |
| 前端 | QAN 页面新 tab 「跨节点关联」— 按置信度色带展示 |

---

## Step 3：跨节点锁聚合（确定性最高）

**这是三个 Step 里最有确定性价值的部分**——锁数据本身就带有 `lock_object_schema` / `lock_object_table` / `lock_data`，三要素完全确定 "同一行数据"。

### 3.1 原理

```
节点 A lock_waits (2026-06-14 10:00:01):
  trx_789 持有 monitor.test_lock, row_data='id=5'

节点 B lock_waits (2026-06-14 10:00:03):
  trx_456 等待 monitor.test_lock, row_data='id=5'

→ 跨节点匹配: 同一个表的同一行 (monitor.test_lock, id=5)
→ 置信度 100% — 这是确定性关联，不是概率
```

### 3.2 ClickHouse 查询

```sql
SELECT
    a.service_name            AS blocker_node,
    b.service_name            AS waiter_node,
    a.lock_object_table       AS `table`,
    a.lock_data               AS row_id,
    a.blocking_trx_id         AS blocker_trx,
    b.waiting_trx_id          AS waiter_trx,
    a.collected_at            AS blocker_time,
    b.collected_at            AS waiter_time
FROM pharos_db.lock_waits a
JOIN pharos_db.lock_waits b
  ON a.lock_object_schema = b.lock_object_schema
 AND a.lock_object_table  = b.lock_object_table
 AND a.lock_data          = b.lock_data
 AND a.service_name != b.service_name
 AND abs(toUnixTimestamp(a.collected_at) - toUnixTimestamp(b.collected_at)) < 30
WHERE a.collected_at BETWEEN %(start)s AND %(end)s
ORDER BY a.collected_at DESC
LIMIT 200
```

### 3.3 前端展示

在现有 LockPage 基础上新增 **"全局视图" tab**：
- 单节点内锁链 = 实线
- 跨节点锁链 = 虚线，标注节点名
- 节点颜色不同，死锁环高亮

### 改动清单

| 模块 | 改动 |
|------|------|
| `qan/services.py` | 新增 `get_cross_node_locks(cluster, start, end)` |
| `qan/views.py` | 新增 `CrossNodeLockView` |
| 前端 LockPage | 新增 "全局视图" tab |

---

## 实施路线

```
Step 1 — 集群拓扑 (2 天)           ← 地基，必须先做
  ├── DatabaseInstance.cluster_role
  ├── 自动角色检测 (P2: 可选)
  ├── client_host 采集进 ClickHouse
  └── InstancesPage 集群分组卡片

Step 2 — 增强关联 (3 天)           ← 核心
  ├── ClickHouse metrics 新增 where_values 列
  ├── MySQLCollector 提取 WHERE 值 + client_host
  ├── qan/services.py 多维置信度评分
  ├── CrossNodeCorrelationView API
  └── 前端 QAN「跨节点关联」tab（置信度色带）

Step 3 — 跨节点锁聚合 (2 天)       ← 确定性最高
  ├── qan/services.py 跨节点锁匹配
  ├── CrossNodeLockView API
  └── LockPage「全局视图」tab
```

**总估：7 天**

---

## Checklist

### Step 1
- [ ] `DatabaseInstance` 新增 `cluster_role` 字段 + migration
- [ ] `MySQLCollector` 采集 `performance_schema.threads.PROCESSLIST_HOST` → `client_host`
- [ ] `PGCollector` 采集 `pg_stat_activity.client_addr` → `client_host`
- [ ] 自动角色检测（`SHOW REPLICA STATUS` / `pg_is_in_recovery()`）
- [ ] InstancesPage 集群分组 + 角色标签

### Step 2
- [ ] ClickHouse `metrics` 表新增 `where_values Array(String)` 列
- [ ] `MySQLCollector` 从 raw SQL 提取 WHERE 等号值
- [ ] `qan/services.py` 新增 `get_cross_node_correlations()`
- [ ] API `GET /api/qan/cross-node/correlation/`
- [ ] 前端 QAN 「跨节点关联」tab（置信度色带 + 差异度列）

### Step 3
- [ ] `qan/services.py` 新增 `get_cross_node_locks()`
- [ ] API `GET /api/qan/cross-node/locks/`
- [ ] LockPage 新增「全局视图」tab（虚线跨节点边 + 节点色区分）
