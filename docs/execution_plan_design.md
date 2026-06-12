# 执行计划采集与历史版本对比 — 方案评估

## 1. PMM 现状

PMM 的执行计划展示方式：

- **数据源**：`performance_schema.events_statements_history` / `events_statements_history_long`（保留最近执行的
  SQL 原文，含真实参数值）
- **触发方式**：纯 UI 手动触发 — 用户在 Query Analytics 页面点击某条查询，PMM 后端实时连接目标数据库执行
  `EXPLAIN FORMAT=JSON`，返回结果渲染为表格
- **存储**：不存储。每次打开都是实时查询，关闭页面即丢弃
- **对比能力**：无。不存历史版本，无法对比两个时间点的执行计划差异

PMM 的 history 表刷新 goroutine 每 5 秒采集一次 `events_statements_history_long`，但仅用于提取 example SQL
和 fingerprint，不触发 EXPLAIN。

## 2. PMM 方式的局限性

| 局限 | 影响 |
|---|---|
| 每次打开详情页都需要连 DB 执行 EXPLAIN | 对生产库有额外负载，长时间未关闭的页面不会重新查询 |
| 无持久化存储 | 无法回溯「上周这个查询走的什么索引」 |
| 无变更检测 | 索引新增/删除后执行计划变了，用户无感知 |
| 无版本对比 | 无法在 UI 上并排对比两次 EXPLAIN 的差异 |
| 依赖 history 表留存 | `events_statements_history_long` 默认只保留最近 10000 条，SQL 可能已被淘汰 |

## 3. PharosDB 增强方案

### 3.1 设计目标

1. **主动采集**：采集 metrics 的同时，对 top-N 慢查询自动执行 EXPLAIN
2. **持久存储**：将 EXPLAIN JSON 存入 ClickHouse（新增 `execution_plans` 表）或 MariaDB（`plan_snapshot` 表）
3. **变更检测**：同一 fingerprint 的 EXPLAIN 发生变化时记录事件
4. **版本对比**：前端并排展示两个版本的执行计划，高亮差异（访问类型变化、索引变化、rows 估算变化）

### 3.2 数据源分析

执行 EXPLAIN 需要的原始 SQL 从两个途径获取：

**途径 A：`events_statements_history`（MySQL 5.6+）**

```sql
-- 获取某个 digest 的一条真实 SQL
SELECT SQL_TEXT
FROM performance_schema.events_statements_history
WHERE DIGEST = %s AND SQL_TEXT IS NOT NULL
LIMIT 1
```

- 优点：SQL 已在内存中，取回几乎无开销
- 缺点：只保留最近执行的 N 条（默认 10 条/线程），可能已被淘汰
- 适用：高频查询，几乎总能命中

**途径 B：采集器已有 example 字段**

当前 `MySQLCollector.collect()` 已经在 metrics 写入时查询 history 表获取 example SQL，并存入
ClickHouse `metrics.example` 字段。可直接复用该字段作为 EXPLAIN 输入。

- 优点：无需额外 DB 连接，直接从 ClickHouse 读取
- 缺点：example 取自上一采集周期的随机一条，可能不是最优代表性 SQL

**建议**：优先使用途径 A（实时从 history 表获取），fallback 到途径 B（metrics.example）。

### 3.3 存储方案

#### 方案 1：ClickHouse 新表 `execution_plans`（推荐）

```sql
CREATE TABLE pharos_db.execution_plans (
    plan_id        String,          -- MD5(fingerprint + timestamp)
    fingerprint    String,          -- SQL 指纹
    service_name   String,          -- 实例名称
    schema         String,
    plan_json      String,          -- EXPLAIN FORMAT=JSON 原文
    plan_summary   String,          -- 结构摘要 JSON (normalize_plan_summary 输出)
    plan_hash      String,          -- MD5(plan_summary)，用于去重比对
    query_example  String,          -- 执行 EXPLAIN 用的实际 SQL
    created_at     DateTime,
    instance_id    Int32
) ENGINE = MergeTree()
ORDER BY (fingerprint, created_at)
PARTITION BY toYYYYMM(created_at);

-- metrics 表需新增的列（已有则跳过）
-- ALTER TABLE pharos_db.metrics ADD COLUMN mysql_digest String DEFAULT '';
```

> **注意**：表结构不再包含 `cost`、`rows_estimated`、`access_type`、`used_indexes` 等提取列。
> 这些信息保存在 `plan_summary` JSON 中，ClickHouse 可通过
> `JSONExtractString(plan_summary, '$.nested_loop[0].access_type')` 按需提取，
> 无需冗余列也避免了 EXPLAIN 版本差异导致的列映射维护成本。

**优点**：
- 与现有 metrics 表同库，查询方便（JOIN 无跨库开销）
- MergeTree 压缩比高，JSON 存储成本低
- 按 fingerprint 排序天然支持「某查询的所有历史计划」

**缺点**：
- 新增表需要 migrate + collector 适配

#### 方案 2：MariaDB 本地表 `plan_snapshot`

```python
class PlanSnapshot(models.Model):
    fingerprint = models.CharField(max_length=64)
    instance = models.ForeignKey(DatabaseInstance, ...)
    plan_json = models.TextField()
    plan_summary = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
```

- 优点：Django ORM 直接管理，迁移简单
- 缺点：大量 JSON 存在 MariaDB 性能不如 ClickHouse；跨库查询不便

**建议**：方案 1（ClickHouse），与 metrics 数据就近存储。

### 3.4 采集策略

#### 时机

在 `MySQLCollector.collect()` 的 delta 计算完成后，对 top-N（可配置，默认 5）慢查询执行 EXPLAIN：

```
collect():
  1. 获取 summaries → 计算 delta → 写 metrics
  2. 按 m_query_time_sum DESC 取 top-5
  3. 对每个 top query:
     a. 从 events_statements_history 获取 SQL_TEXT
     b. 执行 EXPLAIN FORMAT=JSON <SQL_TEXT>
     c. 检查与上一次 EXPLAIN 是否相同
     d. 不同则写入 execution_plans
     e. 更新 metrics.explain_fingerprint（设为 plan_id）
```

#### 去重策略

避免每次采集都写入相同的 EXPLAIN。关键：**不能每次采集都查 ClickHouse** —
20 实例 × top-5 = 每 60s 100 次 SELECT，纯浪费。

方案：**进程内存缓存**（`_plan_cache` dict），key=`"{instance_name}:{fingerprint}"`（
区分实例：同一 fingerprint 在不同 DB 上可能有完全不同的执行计划），value=plan_hash。

```python
def _should_save_plan(self, fingerprint, new_plan_hash):
    cache_key = f"{self.instance.name}:{fingerprint}"
    cached = self._plan_cache.get(cache_key)
    if cached is not None:
        return cached != new_plan_hash   # 命中缓存，直接对比，0 次 CH 查询

    # 缓存未命中（首次遇到此 fingerprint 或进程重启）才查 ClickHouse
    rows = self._ch_client.execute(
        "SELECT plan_hash FROM pharos_db.execution_plans "
        "WHERE fingerprint = %s AND service_name = %s "
        "ORDER BY created_at DESC LIMIT 1",
        (fingerprint, self.instance.name),
    )
    last_hash = rows[0][0] if rows else None
    self._plan_cache[cache_key] = last_hash
    return last_hash != new_plan_hash
```

**缓存命中率估算**：执行计划很少频繁变化 — 一条慢查询在一天内通常只有 1-2 次计划变更。
95%+ 的检查命中缓存，实际 CH 查询量可忽略。

> 如果部署多 worker 进程（gunicorn / uwsgi），每个 worker 有独立内存缓存，重启后全部 miss。
> 更健壮的方案是引入一个轻量 Redis 实例（`SETEX plan:cache:{instance}:{fingerprint} <plan_hash> 86400`），
> 多进程共享且 TTL 自动过期。可根据实际部署规模评估是否需要。

#### normalize_plan_summary 逻辑

`EXPLAIN FORMAT=JSON` 的输出包含很多运行时信息（`cost_info` 中的 `eval_cost`、
`prefix_cost` 可能因统计信息更新而浮动）。对比时应剔除纯数值浮动，只比较**结构变化**。

MySQL EXPLAIN JSON 的真实结构是一个递归树，`query_block` 下可以包含：
- `nested_loop`：JOIN 时每个表一个子节点
- `ordering_operation`：filesort
- `grouping_operation`：GROUP BY
- `duplicates_removal`：DISTINCT
- 子查询 / UNION / derived table 各有递归 query_block

正确的 normalize 必须递归遍历整棵树，只提取每个 `table` 节点的结构信息：

```python
_TABLE_KEYS = ("access_type", "key", "key_length", "used_key_parts", "ref",
               "rows_examined_per_scan", "filtered", "Extra",
               "using_index", "used_columns", "possible_keys",
               "attached_condition", "index_condition")

_CONTAINER_KEYS = ("nested_loop", "ordering_operation", "grouping_operation",
                    "duplicates_removal", "windowing")

def normalize_plan_summary(plan: dict) -> str:
    """提取 EXPLAIN JSON 的结构性摘要，剔除 cost / timing 等数值浮动。

    MySQL 8.0 EXPLAIN FORMAT=JSON 的递归结构：
      query_block → ordering_operation → nested_loop → [table, table, ...]
      或  query_block → table
      或  query_block → nested_loop → table → materialized_from_subquery → query_block ...

    只保留每个 table 节点的访问方式、索引、过滤条件；丢弃所有 cost_info、
    prefix_cost、data_read_per_join 等浮动数值。
    """

    def walk(node):
        if isinstance(node, list):
            return [walk(item) for item in node]

        if not isinstance(node, dict):
            return node

        # 叶子节点：table（表访问）
        if "table" in node:
            tbl = node["table"]
            return {
                "table_name": tbl.get("table_name"),
                "access_type": tbl.get("access_type"),
                "key": tbl.get("key"),
                "possible_keys": sorted(tbl.get("possible_keys", []) or []),
                "used_columns": sorted(tbl.get("used_columns", []) or []),
                "Extra": tbl.get("Extra", ""),
                "filtered": tbl.get("filtered"),
                # materialized_from_subquery 在 tbl 里，不在外层 node
                "materialized_from_subquery": walk(tbl.get("materialized_from_subquery"))
                    if "materialized_from_subquery" in tbl else None,
            }

        # 容器节点：query_block / nested_loop / ordering_operation 等
        result = {"_type": node.get("select_id") and "query_block"}
        for key in node:
            if key in _CONTAINER_KEYS or key == "query_block":
                result[key] = walk(node[key])
        return result

    return json.dumps(walk(plan.get("query_block", plan)), sort_keys=True)
```

关键修正：
- 真实遍历 `nested_loop`（不是不存在的 `missing_subparts`）
- 覆盖 `ordering_operation`、`grouping_operation`、`duplicates_removal`
- 处理 `materialized_from_subquery`（子查询物化场景）
- `sort_keys=True` 保证 JSON 输出稳定可比较
- 对顶层 `query_block` 缺失的情况做了 fallback

### 3.5 版本对比

#### ClickHouse 查询

```sql
-- 某 fingerprint 的所有历史计划，按时间倒序
-- cost / rows_estimated / access_type / used_indexes 已移至 plan_summary JSON 内部，
-- 应用层从 plan_summary 按需提取（避免 EXPLAIN 版本差异导致列映射维护成本）
SELECT plan_id, plan_summary, plan_hash, query_example, created_at
FROM pharos_db.execution_plans
WHERE fingerprint = %(fingerprint)s AND service_name = %(service_name)s
ORDER BY created_at DESC
```

#### 对比算法

1. 从 `execution_plans` 取最近两条（或用户选择的两条）
2. 逐节点对比 JSON：
   - `table` / `access_type` / `key` / `key_len` / `rows` / `Extra`
3. 标记变更类型：
   - **绿色**：优化（rows↓, access_type 提升）
   - **红色**：退化（rows↑, Using filesort 出现, 索引丢失）
   - **灰色**：无变化

#### 前端展示

```
┌──────────────────────────────────────────────────┐
│  执行计划历史                                     │
│  ┌──────────┬──────────┬──────────┬──────────┐   │
│  │ 06-12    │ 06-10    │ 06-08    │ 06-05    │   │
│  │ type:ALL │ type:ref│ type:ref │ type:ref │   │
│  │ key:NULL │ key:idx │ key:idx  │ key:idx  │   │
│  │ rows:50M │ rows:10 │ rows:12  │ rows:9   │   │
│  └──────────┴──────────┴──────────┴──────────┘   │
│  时间线 ●─────────●──────────●────────────────    │
│        6/5 索引创建   6/10 表膨胀    6/12 索引失效 │
│                                                   │
│  对比: [06-10 ▼] vs [06-12 ▼]                     │
│  ┌──────────────┬──────────────┬─────────────┐    │
│  │ 节点          │ 06-10 (旧)   │ 06-12 (新)   │    │
│  ├──────────────┼──────────────┼─────────────┤    │
│  │ access_type  │ ref          │ ALL ⚠       │    │
│  │ key          │ idx_created  │ NULL ⚠      │    │
│  │ rows         │ ~12          │ ~50,000,000 ⚠│   │
│  │ Extra        │              │ Using where  │    │
│  └──────────────┴──────────────┴─────────────┘    │
└──────────────────────────────────────────────────┘
```

### 3.6 API 设计

| 方法 | 端点 | 说明 |
|---|---|---|
| GET | `/api/qan/query/<fingerprint>/plans/` | 获取某查询的所有历史执行计划 |
| GET | `/api/qan/plans/<plan_id>/` | 获取单个计划的完整 JSON |
| POST | `/api/qan/query/<fingerprint>/explain/` | 手动触发一次 EXPLAIN（实时） |
| GET | `/api/qan/query/<fingerprint>/plans/compare/?a=<plan_id>&b=<plan_id>` | 对比两个计划 |

### 3.7 采集器改造点

```python
# collector/collectors/mysql.py 新增

import hashlib
import json
from datetime import datetime

TOP_N_EXPLAIN = 5   # 每个采集周期对 top-5 慢查询执行 EXPLAIN
EXPLAIN_TIMEOUT = 3  # EXPLAIN 最大允许秒数（传给 MAX_EXECUTION_TIME 时 ×1000 为 ms）

class MySQLCollector(BaseCollector):

    # 内存缓存: {fingerprint: plan_hash}，避免同一采集周期内重复查 CH
    _plan_cache: dict[str, str] = {}

    def collect(self) -> list[dict]:
        # ... 现有 delta 计算 + 写 metrics ...

        # 对 top-N 执行 EXPLAIN
        top_queries = sorted(
            result, key=lambda r: r["m_query_time_sum"], reverse=True
        )[:TOP_N_EXPLAIN]

        for q in top_queries:
            self._maybe_collect_explain(q, cur)

        return result

    def _maybe_collect_explain(self, metrics_row, cursor):
        fingerprint = metrics_row["fingerprint"]
        mysql_digest = metrics_row.get("mysql_digest") or metrics_row.get("queryid")

        if not mysql_digest:
            return

        # ── 1. 获取 SQL 原文 ──────────────────────────────────────
        # 问题: metrics_row["queryid"] 目前等于 MySQL 原生 DIGEST (SHA-256),
        #       但未来如果改为自算 MD5，两值将不同。
        # 解决: SUMMARIES_SQL 中新增 mysql_digest 列，始终保存 MySQL 原生 DIGEST,
        #       EXPLAIN 时用 mysql_digest 查 events_statements_history。
        cursor.execute(
            "SELECT SQL_TEXT "
            "FROM performance_schema.events_statements_history "
            "WHERE DIGEST = %s AND SQL_TEXT IS NOT NULL "
            "LIMIT 1",
            (mysql_digest,),
        )
        row = cursor.fetchone()
        if not row:
            return
        sql_text = row["SQL_TEXT"]

        # ── 2. 执行 EXPLAIN（带超时保护） ────────────────────────
        # EXPLAIN FORMAT=JSON 在复杂视图 / 多层子查询时可能卡数秒，
        # 不加超时会阻塞整个采集周期。失败静默跳过。
        #
        # 使用 MAX_EXECUTION_TIME hint（MySQL 5.7.8+ / MariaDB 10.1.2+），
        # 而非 socket.settimeout（私有 API，pymysql 版本升级可能结构变化导致静默失效）。
        try:
            cursor.execute(
                f"EXPLAIN FORMAT=JSON /*+ MAX_EXECUTION_TIME({EXPLAIN_TIMEOUT * 1000}) */ {sql_text}"
            )
            plan_json_raw = cursor.fetchone()
        except Exception:
            return

        if not plan_json_raw:
            return
        plan_dict = json.loads(plan_json_raw[0]) if isinstance(plan_json_raw[0], str) else plan_json_raw[0]

        # ── 3. 提取摘要 + 去重检查 ──────────────────────────────
        plan_hash = hashlib.md5(
            normalize_plan_summary(plan_dict).encode()
        ).hexdigest()

        if not self._should_save_plan(fingerprint, plan_hash):
            return

        # ── 4. 写入 ClickHouse execution_plans 表 ───────────────
        plan_id = hashlib.md5(
            f"{fingerprint}{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()

        self._ch_writer.write("execution_plans", [{
            "plan_id": plan_id,
            "fingerprint": fingerprint,
            "service_name": self.instance.name,
            "schema": metrics_row.get("schema", ""),
            "plan_json": json.dumps(plan_dict),
            "plan_summary": normalize_plan_summary(plan_dict),
            "plan_hash": plan_hash,
            "created_at": datetime.utcnow(),
            "instance_id": self.instance.id,
        }])

        # ── 5. 回写 metrics.explain_fingerprint / planid ────────
        # 直接修改 metrics_rows，写入时生效（与 metrics 同批次写入 CH）
        metrics_row["planid"] = plan_id
        metrics_row["explain_fingerprint"] = plan_hash

    def _should_save_plan(self, fingerprint, plan_hash):
        """检查 EXPLAIN 是否与上一次不同。

        优化: 内存缓存优先命中（同一采集周期同一 fingerprint 不会重复查）。
        次优: 进程内存命中 → 直接对比。
        末位: ClickHouse 查询 → 存入内存缓存。

        在监控 20 实例、每 60s 对 top-5 各执行一次 EXPLAIN 时:
        - 缓存命中: ~95% (执行计划很少频繁变化)
        - ClickHouse 查询: 仅 ~5 次/周期，可忽略
        """
        cache_key = f"{self.instance.name}:{fingerprint}"
        cached = self._plan_cache.get(cache_key)
        if cached is not None:
            return cached != plan_hash

        try:
            rows = self._ch_client.execute(
                "SELECT plan_hash FROM pharos_db.execution_plans "
                "WHERE fingerprint = %s AND service_name = %s "
                "ORDER BY created_at DESC LIMIT 1",
                (fingerprint, self.instance.name),
            )
            last_hash = rows[0][0] if rows else None
            self._plan_cache[cache_key] = last_hash
            return last_hash != plan_hash
        except Exception:
            # CH 不可用时仍写入，不丢数据
            return True
```

### 3.8 MySQL 版本兼容

| MySQL 版本 | EXPLAIN FORMAT=JSON | events_statements_history |
|---|---|---|
| 5.6 | ✅ (5.6.5+) | ✅ |
| 5.7 | ✅ | ✅ |
| 8.0 | ✅ (增加 EXPLAIN ANALYZE) | ✅ |
| MariaDB 10.3+ | ✅ | 部分版本无 `events_statements_history_long` |

对于 MariaDB 10.5（PharosDB 的测试实例），`events_statements_history` 存在且可用，
`EXPLAIN FORMAT=JSON` 也支持。

## 4. 实施优先级

| 阶段 | 内容 | 工作量 |
|---|---|---|
| P1 | ClickHouse `execution_plans` 表创建 + collector 集成 | 3h |
| P2 | API: 历史计划列表 + 详情 + 手动 EXPLAIN | 2h |
| P3 | 前端: 计划时间线 + 并排对比视图 | 4h |
| P4 | 计划变更告警（新增告警规则类型 `plan_change`） | 2h |

## 5. 总结

| 维度 | PMM | PharosDB (当前) | PharosDB (方案) |
|---|---|---|---|
| EXPLAIN 触发 | 手动 UI | 无 | 自动 top-N + 手动 |
| 计划存储 | 不存 | 无 | ClickHouse execution_plans |
| 历史版本 | 无 | 无 | 完整时间线 |
| 版本对比 | 无 | 无 | 逐节点 diff + 高亮 |
| 变更感知 | 无 | 无 | 计划变更事件 + 告警 |
| 对生产库负载 | 每次打开页面 | 无 | 仅在采集周期对 top-5 执行 |
