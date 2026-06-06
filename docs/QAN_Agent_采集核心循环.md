# PMM QAN Agent 采集核心循环 — 深度解析

> 源码版本：Percona PMM v3.8.0  
> 分析范围：MySQL PerfSchema Agent / MySQL Slowlog Agent / PostgreSQL pg_stat_monitor Agent

---

## 目录

1. [总体架构](#1-总体架构)
2. [MySQL PerfSchema Agent — 采集循环](#2-mysql-perfschema-agent--采集循环)
3. [MySQL Slowlog Agent — 采集循环](#3-mysql-slowlog-agent--采集循环)
4. [PostgreSQL pg_stat_monitor Agent — 采集循环](#4-postgresql-pgstatmonitor-agent--采集循环)
5. [从 Agent 到 ClickHouse：完整数据链路](#5-从-agent-到-clickhouse完整数据链路)
6. [指标计算：差值算法详解](#6-指标计算差值算法详解)
7. [单位换算速查表](#7-单位换算速查表)
8. [缓存机制：快照存储](#8-缓存机制快照存储)
9. [Agent 生命周期状态机](#9-agent-生命周期状态机)

---

## 1. 总体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PMM Server                                    │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────────────────┐ │
│  │ pmm-agent │───▶│ pmm-managed  │───▶│ ClickHouse (metrics 表)     │ │
│  │ (gRPC)    │    │ (qan-api2)   │    │   → QAN 查询页面展示        │ │
│  └──────────┘    └──────────────┘    └────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
       ▲
       │ gRPC (QANCollectRequest)
       │
┌──────┴──────────────────────────────────────────────────────────────┐
│                     PMM Agent (pmm-agent)                            │
│                                                                      │
│  ┌──────────────────┐  ┌─────────────────┐  ┌──────────────────┐   │
│  │ perfschema       │  │ slowlog         │  │ pgstatmonitor    │   │
│  │ (内置 Agent)     │  │ (内置 Agent)    │  │ (内置 Agent)     │   │
│  │                  │  │                 │  │                  │   │
│  │ MySQL DB ──▶ Ch  │  │ SlowLog file    │  │ PG DB ──▶ Ch    │   │
│  └──────┬───────────┘  └───────┬─────────┘  └──────┬───────────┘   │
│         │                      │                    │               │
│         ▼                      ▼                    ▼               │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Supervisor                                 │   │
│  │  agent.Changes() ──▶ QANRequests ──▶ gRPC ──▶ Server        │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

**三个核心内置 Agent（BuiltinAgent 接口）：**

| Agent | 数据源 | 采集对象 |
|-------|--------|---------|
| `perfschema` | MySQL `performance_schema` | `events_statements_summary_by_digest` |
| `slowlog` | MySQL Slow Query Log 文件 | 慢查询原始日志 |
| `pgstatmonitor` | PostgreSQL `pg_stat_monitor` 扩展 | `pg_stat_monitor` 视图 |

---

## 2. MySQL PerfSchema Agent — 采集循环

### 2.1 源文件

```
agent/agents/mysql/perfschema/
├── perfschema.go     ← 主循环 (Run)、差值计算 (makeBuckets)、bean 构建 (getNewBuckets)
├── models.go         ← reform ORM 模型定义 (MySQL 表映射)
├── summaries.go      ← events_statements_summary_by_digest 查询 + 缓存
└── history.go        ← events_statements_history 查询 + 缓存
```

### 2.2 核心循环流程图

```
  ┌────────────────────────────────────────────────────────────┐
  │          PerfSchema.Run(ctx) 主循环                        │
  └────────────────────────────────────────────────────────────┘
         │
         ▼
  ┌─────────────────┐
  │ 1. 初始化缓存    │  getSummaries(q) → 加载当前快照 → 写入 summaryCache
  │                 │  (避免首轮把存量数据当增量上报)
  └────────┬────────┘
         │
         ▼
  ┌─────────────────────────────────────────┐
  │ 2. 对齐到整分钟边界                       │
  │    wait = 下个 xx:00 秒 - 当前时间         │
  │    time.NewTimer(wait)                   │
  └────────┬────────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────────────┐
  │ 3. Timer 到期 → 触发采集                  │
  │    start = time.Now()                    │
  │    m.getNewBuckets(start, lengthS)       │
  └────────┬────────────────────────────────┘
         │
         ▼
  ┌──────────────────────────────────────────────────────────────┐
  │ 4. getNewBuckets() 内部                                      │
  │                                                               │
  │   ┌─────────────────────────────────────────────────────┐    │
  │   │ a. current = getSummaries(q)                        │    │
  │   │    SELECT * FROM events_statements_summary_by_digest│    │
  │   │    WHERE DIGEST IS NOT NULL                         │    │
  │   │                                                     │    │
  │   │ b. prev = summaryCache.Get()    // 上一次的快照      │    │
  │   │                                                     │    │
  │   │ c. buckets = makeBuckets(current, prev)             │    │
  │   │    → 对每个 DIGEST 做 diff 生成 MetricsBucket        │    │
  │   │                                                     │    │
  │   │ d. summaryCache.Set(current)    // 更新快照          │    │
  │   │                                                     │    │
  │   │ e. 从 historyCache 补充 Example / ExplainFingerprint│    │
  │   │    填充 AgentId、PeriodStartUnixSecs 等              │    │
  │   └─────────────────────────────────────────────────────┘    │
  └────────┬─────────────────────────────────────────────────────┘
         │
         ▼
  ┌──────────────────────────────┐
  │ 5. 发送到 channel             │
  │    m.changes <- Change{       │
  │      MetricsBucket: buckets   │
  │    }                           │
  └────────┬─────────────────────┘
         │
         ▼
  ┌──────────────────────────────┐
  │ 6. 重置 Timer                 │
  │    wait = 下个整分钟边界       │
  │    t.Reset(wait)              │
  │    回到步骤 3                  │
  └──────────────────────────────┘
```

### 2.3 关键常量

```go
const (
    retainHistory    = 5 * time.Minute   // history 缓存保留时间
    refreshHistory   = 5 * time.Second   // history 缓存刷新间隔
    retainSummaries  = 25 * time.Hour    // summary 缓存保留时间（支持每日查询）
    querySummaries   = time.Minute       // ★ 核心：每 60 秒采集一次
)
```

### 2.4 数据源：events_statements_summary_by_digest

这是 MySQL Performance Schema 的核心视图，按 SQL 指纹聚合所有语句的执行统计：

```
┌──────────────────────────────────────┬─────────────────────────────┐
│ MySQL 列名                           │ PMM 指标                     │
├──────────────────────────────────────┼─────────────────────────────┤
│ DIGEST                               │ queryid (MD5 hash)           │
│ DIGEST_TEXT                          │ fingerprint (参数化 SQL)     │
│ SCHEMA_NAME                          │ schema                      │
│ COUNT_STAR                           │ num_queries                 │
│ SUM_TIMER_WAIT                       │ m_query_time_sum            │
│ SUM_LOCK_TIME                        │ m_lock_time_sum             │
│ SUM_ERRORS                           │ num_queries_with_errors     │
│ SUM_WARNINGS                         │ num_queries_with_warnings   │
│ SUM_ROWS_AFFECTED                    │ m_rows_affected_sum         │
│ SUM_ROWS_SENT                        │ m_rows_sent_sum             │
│ SUM_ROWS_EXAMINED                    │ m_rows_examined_sum         │
│ SUM_CREATED_TMP_DISK_TABLES          │ m_tmp_disk_tables_sum       │
│ SUM_CREATED_TMP_TABLES               │ m_tmp_tables_sum            │
│ SUM_SELECT_FULL_JOIN                 │ m_full_join_sum             │
│ SUM_SELECT_FULL_RANGE_JOIN           │ m_select_full_range_join_sum│
│ SUM_SELECT_RANGE                     │ m_select_range_sum          │
│ SUM_SELECT_RANGE_CHECK               │ m_select_range_check_sum    │
│ SUM_SELECT_SCAN                      │ m_full_scan_sum             │
│ SUM_SORT_MERGE_PASSES                │ m_merge_passes_sum          │
│ SUM_SORT_RANGE                       │ m_sort_range_sum            │
│ SUM_SORT_ROWS                        │ m_sort_rows_sum             │
│ SUM_SORT_SCAN                        │ m_sort_scan_sum             │
│ SUM_NO_INDEX_USED                    │ m_no_index_used_sum         │
│ SUM_NO_GOOD_INDEX_USED               │ m_no_good_index_used_sum    │
└──────────────────────────────────────┴─────────────────────────────┘
```

### 2.5 并行线程：history 缓存刷新

PerfSchema Agent 有一个**独立 goroutine** 每 5 秒刷新 `events_statements_history`：

```
runHistoryCacheRefresher(ctx):
  每 refreshHistory (5s) →
    getHistory(q) → SELECT SQL_TEXT, DIGEST, DIGEST_TEXT, CURRENT_SCHEMA
                   FROM events_statements_history_long
                   WHERE DIGEST IS NOT NULL AND SQL_TEXT IS NOT NULL
    → historyCache.Set(current)
```

**作用**：history 表保存了最近执行的 SQL **原文**（带真实值）。Agent 从中提取：
- **Example**：随机一条真实 SQL 作为"查询示例"
- **ExplainFingerprint**：去除注释后的参数化 SQL
- **PlaceholdersCount**：`?` 占位符个数

### 2.6 PerfSchema Digest 去重逻辑

PerfSchema 的 `DIGEST` 是 MD5 hash，但**不同 schema 下相同 fingerprint 会生成不同 DIGEST**。

PMM 使用 `queryIDWithSchema` 构造唯一 ID：

```go
func queryIDWithSchema(schema, queryID string) string {
    if schema == "" { return queryID }
    return fmt.Sprintf("%s-%s", schema, queryID)
}
```

即 summary cache 中的 key = `"mydb-abc123def456"`，确保了跨 schema 的隔离。

---

## 3. MySQL Slowlog Agent — 采集循环

Slowlog Agent 的采集模式与 PerfSchema 完全不同——它**不轮询 DB**，而是**持续解析慢查询日志文件**。

### 3.1 核心流程

```
  ┌────────────────────────────────────────────────────────┐
  │          Slowlog.Run(ctx)                               │
  └────────────────────────────────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────────┐
  │ 1. 连接到 MySQL                       │
  │    - 确认 slow_query_log = ON          │
  │    - 确认 log_output = FILE            │
  │    - 获取 slow_query_log_file 路径     │
  │    - 获取 long_query_time 阈值         │
  └────────┬────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────────┐
  │ 2. 启动文件 Tailer                   │
  │    类似 tail -f slow_query_log_file  │
  │    持续读取新增的慢查询记录           │
  └────────┬────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────────┐
  │ 3. 解析慢查询事件                    │
  │    # Time: 2023-01-01T12:00:00       │
  │    # User@Host: user[user] @ host [] │
  │    # Query_time: 1.234  Lock_time:   │
  │    # Rows_sent: 100  Rows_examined:  │
  │    SET timestamp=...;                │
  │    SELECT * FROM ...;                │
  └────────┬────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────────┐
  │ 4. 生成 Fingerprint                  │
  │    queryparser.MySQLFingerprint()    │
  │    参数化 → digest_text              │
  │    MD5 → queryid                     │
  └────────┬────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────────┐
  │ 5. 按时间窗口聚合                    │
  │    默认 60s 一个 Bucket              │
  │    同一个 digest 的慢查询在窗口内合并 │
  └────────┬────────────────────────────┘
         │
         ▼
  ┌─────────────────────────────────────┐
  │ 6. 发送 MetricsBucket 到 channel     │
  └─────────────────────────────────────┘
```

### 3.2 Slowlog vs PerfSchema 对比

| 特性 | PerfSchema | Slowlog |
|------|-----------|---------|
| 数据来源 | `events_statements_summary_by_digest`（聚合视图） | 慢查询日志文件（原始日志） |
| 采集模式 | 定时轮询（60s） | 实时 Tail 文件 |
| 覆盖范围 | 所有执行过的 SQL | 只覆盖超过 `long_query_time` 的 SQL |
| 指标精度 | 预聚合的 SUM/MIN/MAX/AVG | 逐条累加 |
| 示例 SQL | 从 history 表获取 | 原始日志直接包含 |
| CPU 负载 | 查询开销小（聚合表很小） | 文件 I/O + 解析开销 |
| 适用场景 | 生产环境（推荐） | PerfSchema 不可用时 |

---

## 4. PostgreSQL pg_stat_monitor Agent — 采集循环

### 4.1 源文件

```
agent/agents/postgres/pgstatmonitor/
├── pgstatmonitor.go           ← 主循环 (Run)、bean 构建 (getNewBuckets/makeBuckets)
├── pgstatmonitor_models.go    ← pg_stat_monitor 动态字段映射 (多版本兼容)
├── stat_monitor_cache.go      ← 快照缓存
└── models.go / models_reform.go
```

### 4.2 核心循环流程图

```
  ┌───────────────────────────────────────────────────────────────┐
  │          PGStatMonitorQAN.Run(ctx) 主循环                      │
  └───────────────────────────────────────────────────────────────┘
         │
         ▼
  ┌──────────────────────┐
  │ 1. 获取 PG 配置       │  getSettings()
  │    - pgsm_bucket_time │  → waitTime (默认 60s)
  │    - normalized_query │  → 是否使用规范化查询
  └────────┬─────────────┘
         │
         ▼
  ┌──────────────────────────┐
  │ 2. 初始化缓存              │  monitorCache.getStatMonitorExtended()
  │    加载当前快照写入缓存    │  (避免存量当增量上报)
  └────────┬─────────────────┘
         │
         ▼
  ┌──────────────────────────┐
  │ 3. Timer 到期 (waitTime)  │
  │    → getSettings() 重新读 │
  │    → getWaitTime() 确认   │
  └────────┬─────────────────┘
         │
         ▼
  ┌──────────────────────────────────────────────────────────────┐
  │ 4. getNewBuckets(ctx, lengthS, normalizedQuery)              │
  │                                                               │
  │   ┌─────────────────────────────────────────────────────┐    │
  │   │ a. current, prev = monitorCache.getStatMonitorExtended()│ │
  │   │    (一层调用同时返回当前快照 + 缓存快照)              │    │
  │   │                                                     │    │
  │   │    内部逻辑：                                         │    │
  │   │    - SELECT * FROM pg_stat_monitor                  │    │
  │   │    - 按 (bucket_start_time, queryid) 组织为 map      │    │
  │   │    - fingerprint 处理 (参数化)                       │    │
  │   │    - 查询截断检测                                    │    │
  │   │                                                     │    │
  │   │ b. buckets = m.makeBuckets(current, prev)           │    │
  │   │    → 对每个 (bucket, queryid) 做 diff 生成 Bucket    │    │
  │   │                                                     │    │
  │   │ c. monitorCache.refresh(current)  // 更新快照       │    │
  │   │                                                     │    │
  │   │ d. 填充 AgentId、PeriodLengthSecs                   │    │
  │   └─────────────────────────────────────────────────────┘    │
  └────────┬─────────────────────────────────────────────────────┘
         │
         ▼
  ┌──────────────────────────────┐
  │ 5. 发送到 channel             │
  │    m.changes <- Change{       │
  │      MetricsBucket: buckets   │
  │    }                           │
  └────────┬─────────────────────┘
         │
         ▼
  ┌──────────────────────────────┐
  │ 6. 重置 Timer → 回到步骤 3    │
  └──────────────────────────────┘
```

### 4.3 pg_stat_monitor 的特殊之处

#### 4.3.1 多版本兼容

`pg_stat_monitor` 是 PG 扩展，其列名和列集在不同版本间变化很大。PMM 通过 **运行时检测版本** 动态构建字段映射：

```go
// pgstatmonitor.go: getPGMonitorVersion()
// 通过 SELECT pg_stat_monitor_version() 获取版本
// 然后结合 PG 版本号生成版本枚举值
//
// 示例：
//   PG 16 + PGSM 2.3 → pgStatMonitorVersion23PG16
//   PG 14 + PGSM 1.1 → pgStatMonitorVersion11PG14
```

对应的字段映射矩阵（部分）：

| PGSM 版本 | PG 版本 | TotalTime 列名 | QueryID 列名 | Rows 列名 |
|-----------|---------|---------------|-------------|----------|
| < 2.0 | PG ≤ 12 | `total_time` | `queryid` | `rows` |
| < 2.0 | PG ≥ 13 | `total_exec_time` | `queryid` | `rows_retrieved` |
| ≥ 2.0 | PG ≤ 12 | `total_time` | `pgsm_query_id` | `rows` |
| ≥ 2.0 | PG ≥ 13 | `total_exec_time` | `pgsm_query_id` | `rows` |

#### 4.3.2 pg_stat_monitor 自带 Bucket 机制

不同于 PerfSchema，`pg_stat_monitor` **自带**时间分桶：

```
pg_stat_monitor 表结构（简化）：
  bucket              INT       ← bucket 序号
  bucket_start_time   TIMESTAMP ← bucket 起始时间
  queryid / pgsm_query_id      ← 查询指纹 hash
  query               TEXT      ← 原始查询
  calls               INT       ← bucket 内执行次数
  total_exec_time     FLOAT     ← 总执行时间（毫秒）
  ... 各种指标 ...
```

这意味着 PMM 的快照维度是 **`bucket 起始时间 + queryid`**，而不是单纯的 `queryid`。

#### 4.3.3 内置 Histogram

`pg_stat_monitor` (≥ 0.9) 在 `resp_calls` 列中直接提供了**响应时间直方图**：

- PGSM < 2.0：10 个桶，范围 (0-3ms) 到 (31622-100000ms)
- PGSM ≥ 2.0：22 个桶，范围 (0-1μs) 到 (100000μs-...)

PMM Agent 直接读取 `resp_calls` (PostgreSQL int 数组)，并与上次快照做 diff，生成 `HistogramItem[]`。

#### 4.3.4 CPU 时间的版本差异

```go
// PGSM 2.0+ 已经在 PG 端做了累积，Agent 端不再做 diff
if vPGSM >= pgStatMonitorVersion20PG12 {
    cpuSysTime  = currentPSM.CPUSysTime   // 直接用当前值
    cpuUserTime = currentPSM.CPUUserTime
} else {
    cpuSysTime  = currentPSM.CPUSysTime - prevPSM.CPUSysTime  // 做 diff
    cpuUserTime = currentPSM.CPUUserTime - prevPSM.CPUUserTime
}
```

### 4.4 PerfSchema vs pg_stat_monitor 对比

| 特性 | MySQL PerfSchema | PG pg_stat_monitor |
|------|-----------------|-------------------|
| 数据源 | `events_statements_summary_by_digest` | `pg_stat_monitor` 视图 |
| 聚合方式 | MySQL 内核做聚合（累积表） | PG 扩展做分桶聚合 |
| 时间粒度 | PMM 定时 60s 拉取 | PG 扩展自带 bucket（默认 60s） |
| 快照维度 | `(schema, digest)` | `(bucket_start_time, queryid)` |
| 指标数量 | ~23 个 SUM_* 字段 | ~50+ 个字段（含 plan/wal/histogram） |
| 示例 SQL | 从 history 表额外查询 | 直接从 pg_stat_monitor 获取 |
| Histogram | 不支持 | 内置 `resp_calls` 数组 |
| 版本兼容 | 比较简单（MySQL 5.6+） | 复杂（30+ 版本×PG 版本组合） |

---

## 5. 从 Agent 到 ClickHouse：完整数据链路

### 5.1 数据流全景

```
  ┌─────────┐   Changes() channel    ┌─────────────┐   QANRequests()    ┌──────────┐
  │ Agent   │ ───MetricsBucket─────▶ │ Supervisor  │ ──QANCollectReq──▶ │  Client  │
  │ (内置)  │                        │ (goroutine) │                    │ (gRPC)   │
  └─────────┘                        └─────────────┘                    └────┬─────┘
                                                                           │
                                                                    gRPC stream
                                                                           │
                                                              ┌────────────┴─────┐
                                                              │   PMM Server     │
                                                              │   qan-api2       │
                                                              │                  │
                                                              │ receiver/        │
                                                              │   MetricsBucket  │
                                                              │   .Save()        │
                                                              │      │           │
                                                              │      ▼           │
                                                              │ INSERT INTO      │
                                                              │   metrics (...)  │
                                                              │      │           │
                                                              │      ▼           │
                                                              │ ┌──────────────┐ │
                                                              │ │ ClickHouse   │ │
                                                              │ │ metrics 表   │ │
                                                              │ └──────────────┘ │
                                                              └──────────────────┘
```

### 5.2 关键代码路径

```
1. Agent.Run() 产生 MetricsBucket
   → agent/agents/mysql/perfschema/perfschema.go:260
     m.changes <- agents.Change{MetricsBucket: buckets}

2. Supervisor goroutine 接收 Change
   → agent/agents/supervisor/supervisor.go:680-694
     for change := range agent.Changes() {
         s.qanRequests <- &agentv1.QANCollectRequest{
             MetricsBucket: change.MetricsBucket,
         }
     }

3. Client 通过 gRPC 发送到 Server
   → agent/client/client.go
     QANRequests() → gRPC stream → PMM Server

4. Server 端 qan-api2 接收并写入 ClickHouse
   → qan-api2/services/receiver/  (接收 gRPC)
   → qan-api2/models/data_ingestion.go:48  (insertSQL)
   → ClickHouse metrics 表
```

### 5.3 MetricsBucket 结构

每个 Agent 产生的 `MetricsBucket` 是一个 protobuf 消息：

```protobuf
message MetricsBucket {
  Common common = 1;           // 公共字段 (queryid, fingerprint, num_queries, m_query_time_sum...)
  MySQL mysql = 2;             // MySQL 特有指标
  PostgreSQL postgresql = 3;   // PostgreSQL 特有指标
  MongoDB mongodb = 4;         // MongoDB 特有指标
}

message MetricsBucket_Common {
  string queryid = 1;
  string fingerprint = 2;
  string example = 3;
  uint32 num_queries = 4;
  float m_query_time_sum = 5;
  float m_query_time_cnt = 6;
  // ... 更多公共指标
  string agent_id = ...;
  uint32 period_start_unix_secs = ...;
  uint32 period_length_secs = ...;
}
```

---

## 6. 指标计算：差值算法详解

### 6.1 核心算法 — inc()

```go
// perfschema.go:413
func inc(current, prev uint64) float32 {
    if current <= prev {
        return 0  // 处理 wrap-around / truncate
    }
    return float32(current - prev)
}
```

**三种情况**：

| 情况 | current vs prev | 含义 | 处理 |
|------|----------------|------|------|
| 正常增长 | current > prev | 此周期有新查询执行 | `current - prev` → 增量 |
| 无变化 | current == prev | 此周期无此 digest 的查询 | skip（不产生 bucket） |
| Truncate | current < prev | Performance Schema 表被截断（重启/满） | 当作新查询，prev=0 |

### 6.2 PerfSchema 的 makeBuckets 算法

```go
func makeBuckets(current, prev summaryMap) []*agentv1.MetricsBucket {
    for digest, currentESS := range current {
        prevESS := prev[digest]

        // 情况 1: COUNT_STAR 没变 → 跳过
        if currentESS.CountStar == prevESS.CountStar {
            continue
        }

        // 情况 2: COUNT_STAR 减少了 → truncate 检测，prev 归零
        if currentESS.CountStar < prevESS.CountStar {
            prevESS = &eventsStatementsSummaryByDigest{}
        }

        // 计算增量
        count := inc(currentESS.CountStar, prevESS.CountStar)

        // 对每个指标计算 diff
        for _, p := range []struct{...}{
            {inc(SumTimerWait_diff) / 1e12, &mb.Common.MQueryTimeSum, &mb.Common.MQueryTimeCnt},
            {inc(SumLockTime_diff)  / 1e12, &mb.Mysql.MLockTimeSum,     &mb.Mysql.MLockTimeCnt},
            // ... 20+ 个指标
        } {
            if p.value != 0 {
                *p.sum = p.value
                *p.cnt = count
            }
        }
    }
}
```

### 6.3 pg_stat_monitor 的 makeBuckets 算法

与 PerfSchema 类似但维度是 `(bucket_start_time, queryid)`：

```go
func (m *PGStatMonitorQAN) makeBuckets(current, cache map[time.Time]map[string]*pgStatMonitorExtended) {
    for bucketStartTime, bucket := range current {
        prev := cache[bucketStartTime]  // 同一时间 bucket 的上次快照

        for queryID, currentPSM := range bucket {
            prevPSM := prev[queryID]

            count := float32(currentPSM.Calls - prevPSM.Calls)

            switch {
            case count == 0:    // 无变化 → 跳过
                continue
            case count < 0:     // truncate → 当作新查询
                prevPSM = &pgStatMonitorExtended{}
                count = float32(currentPSM.Calls)
            case prevPSM.Calls == 0:  // 新查询
                // 正常处理
            default:            // 正常增量
                // 正常处理
            }

            // 计算各指标 diff
            // Rows, SharedBlks*, LocalBlks*, TempBlks*, Plans*, Wal*, CPU Time...
        }
    }
}
```

### 6.4 为什么 _cnt = count（增量查询次数）

PMM 的指标模型中，`_cnt` 记录的是 **此 bucket 中该 queryid 的执行次数**，而不是采样点数。这使得上层可以做：

```sql
-- 单次查询平均耗时
m_query_time_sum / m_query_time_cnt  -- = 总耗时 / 执行次数

-- 全表扫描比例
m_full_scan_sum / m_full_scan_cnt    -- = 全表扫描次数 / 执行次数
```

---

## 7. 单位换算速查表

Agent 从数据库读取原始值后，需要转换为 PMM 统一单位（秒）写入 ClickHouse：

| 数据源 | 原始单位 | 目标单位 | 换算 | 代码位置 |
|--------|---------|---------|------|---------|
| MySQL SUM_TIMER_WAIT | **皮秒** (10⁻¹²) | 秒 | ÷ 1,000,000,000,000 | `perfschema.go:473` |
| MySQL SUM_LOCK_TIME | **皮秒** (10⁻¹²) | 秒 | ÷ 1,000,000,000,000 | `perfschema.go:474` |
| PG total_exec_time | **毫秒** (10⁻³) | 秒 | ÷ 1,000 | `pgstatmonitor.go:693` |
| PG blk_read_time | **毫秒** (10⁻³) | 秒 | ÷ 1,000 | `pgstatmonitor.go:694-697` |
| PG cpu_user_time | **微秒** (10⁻⁶) | 秒 | ÷ 1,000,000 | `pgstatmonitor.go:700` |
| PG plan_time | PG 自带毫秒 | 秒 | ÷ 1,000 | `pgstatmonitor.go:629` |
| MySQL rows_* | 条数 | 条数 | 不变 | — |

**重要**：PMM Agent 在做 diff **之前**就做单位换算，所以 ClickHouse 中的 `m_query_time_sum` 始终是**秒**。

---

## 8. 缓存机制：快照存储

### 8.1 PerfSchema 双层缓存

```
┌──────────────────────────────────────────────┐
│               PerfSchema Agent               │
│                                              │
│  ┌────────────────────┐  ┌────────────────┐  │
│  │   summaryCache      │  │  historyCache   │  │
│  │                     │  │                 │  │
│  │ Type: summaryMap    │  │ Type: historyMap│  │
│  │ Key: schema-digest  │  │ Key: schema-    │  │
│  │ Value: *ESSBD       │  │      digest     │  │
│  │                     │  │ Value: *ESH     │  │
│  │ Retain: 25h         │  │ Retain: 5m      │  │
│  │ Limit: digest_size  │  │ Limit: hist_size│  │
│  │ Refresh: 60s        │  │ Refresh: 5s     │  │
│  └────────────────────┘  └────────────────┘  │
└──────────────────────────────────────────────┘
```

- **summaryCache**：保存上一分钟的 `events_statements_summary_by_digest` 快照，用于 diff
- **historyCache**：保存最近 5 分钟的 `events_statements_history_long`，用于提取真实 SQL 示例

### 8.2 pg_stat_monitor 单层缓存

```
┌──────────────────────────────────────────────┐
│           PGStatMonitorQAN Agent             │
│                                              │
│  ┌──────────────────────────────────────┐    │
│  │        statMonitorCache               │    │
│  │                                       │    │
│  │ Type: map[time.Time]                  │    │
│  │         map[string]                   │    │
│  │           *pgStatMonitorExtended      │    │
│  │                                       │    │
│  │ Key: bucket_start_time → queryid      │    │
│  │                                       │    │
│  │ flushOlderThan(): 清理过期 bucket     │    │
│  └──────────────────────────────────────┘    │
└──────────────────────────────────────────────┘
```

- PGSM 自带 bucket 机制，缓存需要按 `bucket_start_time` 维度存储
- 每次采集时 `flushOlderThan()` 清理已完成的 bucket

### 8.3 缓存实现

两种 Agent 都使用 `agent/agents/cache/` 包的通用 LRU 缓存：

```go
// cache.New(typ, retain, sizeLimit, logger)
// - typ:    缓存值类型（用于 reflect 复制）
// - retain: 条目保留时间（过期自动淘汰）
// - sizeLimit: 最大条目数
```

---

## 9. Agent 生命周期状态机

每个内置 Agent 通过 `Changes()` channel 报告状态变化：

```
                 ┌──────────┐
      创建 Agent │ STARTING │
            ───▶│          │─── 初始化成功 ──▶ ┌─────────┐
                 └──────────┘                   │ RUNNING │
                      │                         │         │◀──┐
                      │ 初始化失败               └────┬────┘   │
                      ▼                             │        │ 恢复
                 ┌─────────┐                  采集失败│        │
                 │ WAITING │                        ▼        │
                 │         │◀── 采集失败 ────  ┌─────────┐   │
                 └─────────┘                   │ WAITING │───┘
                      │                        └─────────┘
                      │ ctx.Done()
                      ▼
                 ┌─────────┐        ┌─────────┐
                 │ STOPPING│───────▶│  DONE   │ (channel closed)
                 └─────────┘        └─────────┘
```

**状态转换代码路径**：

```go
// 启动
m.changes <- agents.Change{Status: STARTING}     // perfschema.go:206
m.changes <- agents.Change{Status: RUNNING}       // perfschema.go:211

// 采集成功 → 发送数据
m.changes <- agents.Change{MetricsBucket: buckets} // perfschema.go:260

// 采集失败 → 降级
m.changes <- agents.Change{Status: WAITING}       // perfschema.go:251

// 退出
defer func() {
    m.changes <- agents.Change{Status: DONE}      // perfschema.go:197
    close(m.changes)
}()
```

---

## 附录 A：源码文件索引

```
agent/
├── agents/
│   ├── agents.go                      ← BuiltinAgent 接口定义 + Change 结构体
│   ├── cache/                         ← 通用 LRU 缓存
│   ├── supervisor/
│   │   └── supervisor.go              ← Agent 生命周期管理，Change → QANRequests 转发
│   ├── mysql/
│   │   ├── perfschema/
│   │   │   ├── perfschema.go          ← ★ PerfSchema Run() 主循环 + makeBuckets
│   │   │   ├── models.go              ← ORM 模型 (MySQL 表 → Go struct)
│   │   │   ├── models_reform.go       ← reform 自动生成代码
│   │   │   ├── summaries.go           ← getSummaries() + summaryCache
│   │   │   └── history.go             ← getHistory() + historyCache
│   │   └── slowlog/
│   │       └── slowlog.go             ← Slowlog Run() + 慢查询日志解析
│   └── postgres/
│       └── pgstatmonitor/
│           ├── pgstatmonitor.go       ← ★ PGStatMonitorQAN Run() + makeBuckets
│           ├── pgstatmonitor_models.go← 动态字段映射 (30+ 版本兼容)
│           └── stat_monitor_cache.go  ← statMonitorCache
├── runner/
│   ├── runner.go                      ← Job/Action 并发调度
│   └── jobs/                          ← Backup/Restore Jobs
└── client/
    └── client.go                      ← gRPC 客户端，连接 PMM Server

qan-api2/
├── models/
│   ├── metrics.go                     ← ClickHouse 查询 (SELECT/聚合模板)
│   └── data_ingestion.go             ← ClickHouse INSERT (insertSQL)
├── migrations/
│   ├── migrations.go                  ← 迁移引擎 (MergeTree vs ReplicatedMergeTree)
│   └── sql/01_init.up.sql ... 22_*.sql ← 22 个 DDL 迁移文件
└── services/
    └── receiver/                      ← gRPC 接收器，接收 Agent 上报数据
```

## 附录 B：关键常量和定时器汇总

| 位置 | 常量 | 值 | 含义 |
|------|------|-----|------|
| perfschema.go | `querySummaries` | 60s | PerfSchema 主采集间隔 |
| perfschema.go | `retainSummaries` | 25h | summary 缓存过期时间 |
| perfschema.go | `refreshHistory` | 5s | history 缓存刷新间隔 |
| perfschema.go | `retainHistory` | 5min | history 缓存过期时间 |
| perfschema.go | `summariesCacheSize` | 10000 | summary 最大条目数 |
| perfschema.go | `historyCacheSize` | 10000 | history 最大条目数 |
| pgstatmonitor.go | `defaultWaitTime` | 60s | PGSM 默认采集间隔 |
| slowlog.go | (无固定间隔) | — | 实时 tail 文件 |
| data_ingestion.go | `batchTimeout` | 500ms | ClickHouse 写入批量超时 |
| data_ingestion.go | `requestsCap` | 100 | 写入队列容量 |
| runner.go | `bufferSize` | 256 | Actions/Jobs 通道缓冲 |
| runner.go | `defaultTotalCapacity` | 32 | 全局并发数 |
| runner.go | `defaultTokenCapacity` | 2 | 单实例并发数 |
