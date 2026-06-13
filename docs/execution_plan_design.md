# 执行计划采集与对比 — 实现文档

## 1. 实现状态：已完成

P1-P3 已全部实现，P4（变更告警）待开发。

---

## 2. 架构总览

```
采集周期 (每 60s)
  └─ MySQLCollector.collect()
       ├─ 1. 查询 metrics → 计算 delta
       ├─ 2. 写入 ClickHouse metrics
       └─ 3. 对 top-5 慢查询:
            ├─ 从 events_statements_history_long 获取 SQL
            ├─ 执行 EXPLAIN FORMAT=JSON
            ├─ normalize_plan_summary() 提取结构摘要
            ├─ 去重检查 (内存缓存 + ClickHouse 回查)
            ├─ 写入 ClickHouse execution_plans
            └─ 回写 planid / explain_fingerprint 到 metrics 行
```

---

## 3. 数据存储

### 3.1 ClickHouse `execution_plans` 表

```sql
-- clickhouse_schema/03_execution_plans_table.sql
CREATE TABLE pharos_db.execution_plans (
    plan_id        String,       -- MD5(fingerprint + timestamp)
    fingerprint    String,
    service_name   String,
    schema         String,
    plan_json      String,       -- EXPLAIN FORMAT=JSON 原文
    plan_summary   String,       -- normalize_plan_summary() 输出
    plan_hash      String,       -- MD5(plan_summary)，去重用
    query_example  String,       -- 实际 EXPLAIN 的 SQL
    created_at     DateTime,
    instance_id    Int32
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (fingerprint, created_at)
SETTINGS index_granularity = 8192;
```

### 3.2 metrics 表关联字段

metrics 行在写入时附带：
- `planid` — 指向 execution_plans.plan_id
- `explain_fingerprint` — plan_hash，与 plan_summary 的 MD5 一致
- `plan_summary` — 预留，当前为空字符串

---

## 4. 采集实现

### 4.1 文件位置

- `collector/collectors/mysql.py:518-664` — `MySQLCollector._maybe_collect_explain()`
- `collector/collectors/mysql.py:68-109` — `normalize_plan_summary()`

### 4.2 采集参数

| 参数 | 值 | 位置 |
|------|-----|------|
| TOP_N_EXPLAIN | 5 | mysql.py:59 |
| EXPLAIN_TIMEOUT | 3s | mysql.py:60 |

### 4.3 normalize_plan_summary 逻辑

递归遍历 EXPLAIN JSON 树，对每个 `table` 节点仅提取结构字段：
- `table_name`, `access_type`, `key`, `possible_keys`, `used_columns`, `Extra`, `filtered`
- 递归处理 `materialized_from_subquery`
- 容器节点: `nested_loop`, `ordering_operation`, `grouping_operation`, `duplicates_removal`, `windowing`
- **丢弃**: 所有 cost_info、prefix_cost、timing 等浮动数值

### 4.4 去重策略

两级缓存：
1. **内存缓存** `_plan_cache: dict[str, str]` — key=`"{instance_name}:{fingerprint}"`，value=plan_hash
2. **ClickHouse 回查** — 仅缓存 miss 时查询最近一条的 plan_hash

95%+ 命中缓存，避免每周期 100 次无效 ClickHouse SELECT。

### 4.5 MariaDB 兼容

MariaDB 使用 `SET STATEMENT max_statement_time=N FOR EXPLAIN FORMAT=JSON`。
MySQL 使用 `EXPLAIN FORMAT=JSON /*+ MAX_EXECUTION_TIME(N) */` hint 作为 fallback。

---

## 5. API 端点

文件: `qan/views.py`, `qan/plan_services.py`, `qan/urls.py`

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/qan/plans/?fingerprint=X&service=Y` | 某 fingerprint 的所有历史计划列表 |
| GET | `/api/qan/plans/<plan_id>/` | 单个计划的完整 JSON (含 plan_json) |
| GET | `/api/qan/plans/compare/?a=<id>&b=<id>` | 对比两个计划，返回 `{plan_a, plan_b, diff[]}` |
| POST | `/api/qan/explain/` | 手动触发 EXPLAIN，body: `{service, sql}` |

### 5.1 Compare API 返回格式

```json
{
  "plan_a": { ... full plan detail ... },
  "plan_b": { ... full plan detail ... },
  "diff": [
    {
      "path": "$.nested_loop[0].access_type",
      "field": "access_type",
      "a": "ref",
      "b": "ALL",
      "change": "degraded"
    }
  ]
}
```

### 5.2 Diff 引擎 (`qan/plan_services.py:133-193`)

递归比较两个 `plan_summary` JSON 树：
- Dict key 遍历：两边并集，对共享 key 调用 `_classify()` 判断变化类型
- Array 比较：按索引位置逐项对比
- `_classify()` 规则：
  - `access_type`: 按 rank 排序 (system < const < eq_ref < ref < range < index < ALL)
  - `key`: NULL→index = optimized, index→NULL = degraded
  - `Extra`: Using filesort/Using temporary 的出现/消失
  - 其他字段: 直接相等比较

**注意**: diff 比较的是 `plan_summary`（结构摘要），不是 `plan_json`（完整 JSON）。两个 plan_json 不同但 plan_summary 相同 → diff 为空，表示执行计划结构未变，仅参数值不同。

---

## 6. 前端实现

### 6.1 文件位置

- `frontend/src/pages/QANPage.jsx` — Plan 标签页全部逻辑
- `frontend/src/components/PlanDiffTable.jsx` — diff 表格组件
- `frontend/src/pages/QANPage.css` — 样式

### 6.2 UI 模式

#### 浏览模式（默认）
- 时间轴列表: 所有历史版本，每项显示采集时间 + access_type + key
- 点击选中 → 从缓存/API 加载完整树 → `PlanNode` 组件渲染
- 自动选中最新版本

#### 对比模式
- 两个下拉选择器 (A / B)，从版本列表填充
- "对比"按钮调用 compare API
- diff 表格: 路径 | 字段 | 旧值(A) | 新值(B) | 变化标签 (绿色=优化, 红色=退化, 灰色=修改)
- 两棵树并排显示，差异节点带颜色高亮

#### 手动 EXPLAIN
- 可折叠面板，textarea 预填 detail.example
- POST /api/qan/explain/ 实时执行
- 结果显示后自动刷新版本列表

### 6.3 关键组件

**PlanNode** — 递归 JSON 树组件，支持：
- 对象/数组/标量 三种节点类型
- 默认展开 2 层
- `highlightPaths: Set<string>` + `diffMap: Map<string, type>` 用于对比高亮
- JSON path 计算: `$.nested_loop[0].table.access_type`

**PlanDiffTable** — diff 结果表格，5 列紧凑布局，颜色标签标注优化/退化/修改。

---

## 7. PostgreSQL 状态

PostgreSQL collector (`collector/collectors/postgresql.py`) **未实现**自动 EXPLAIN 采集。
- 采集 `pg_stat_statements` 的 `plans`/`plan_time` 计数指标
- 手动 EXPLAIN 通过 `POST /api/qan/explain/` 支持
- 不写入 execution_plans 表
- 无 normalize_plan_summary() 等价函数（PG EXPLAIN JSON 结构不同）

---

## 8. 待实现

| 项目 | 优先级 | 说明 |
|------|--------|------|
| PostgreSQL 自动采集 | P2 | 实现 `_maybe_collect_explain()`，适配 PG EXPLAIN JSON |
| 计划变更告警 | P2 | 新增告警规则类型 `plan_change`，监控 plan_hash 变化 |
| Redis 缓存 | P3 | 多进程部署时共享去重缓存 |
