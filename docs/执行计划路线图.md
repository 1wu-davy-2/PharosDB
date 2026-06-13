# PharosDB 执行计划

## 总览

| 阶段 | 内容 | 前置条件 | 状态 |
|:---:|------|:---:|:---:|
| P0 | DatabaseInstance 模型 + 连接测试 API | 无 | ⬜ |
| P1 | MySQLCollector — 慢查询采集 + ClickHouse 写入 | P0 | ⬜ |
| P2 | Celery + Beat 调度 — 自动定时采集 | P1 | ⬜ |
| P3 | QAN API — Top Queries / 详情 / 趋势 | P1 | ⬜ |
| P4 | 前端 QAN 页面 — 慢查询列表 + 分析 | P3 | ⬜ |
| P5 | PostgreSQL / MongoDB 采集器 | P1 | ⬜ |
| P6 | 执行计划分析 + 优化建议 | P3 | ⬜ |

---

## P0: DatabaseInstance 模型 + 连接测试 API

### 目标
注册被监控数据库实例，测试连通性。

### 交付物
- [x] `collector` Django app
- [x] `DatabaseInstance` 模型 (MariaDB)
- [x] CRUD API: `POST/GET/PUT/DELETE /api/collector/instances/`
- [x] 连接测试: `POST /api/collector/instances/{id}/test-connection/`
- [x] Django Admin 注册
- [x] 数据库 migrate

### 模型字段
```
name             CharField(128)     显示名称
db_type          CharField(20)      mysql / postgresql / mongodb
host             CharField(255)     目标主机
port             IntegerField       端口 (默认 3306)
username         CharField(128)     用户名
password         TextField          Fernet 加密
environment      CharField(32)      prod / staging / dev
cluster          CharField(128)     集群名 (可选)
is_active        BooleanField       是否启用
collect_interval IntegerField       采集间隔秒 (默认 60)
last_collected_at DateTimeField     上次采集时间
```

### API
```
POST   /api/collector/instances/            创建实例
GET    /api/collector/instances/             列表
GET    /api/collector/instances/{id}/        详情
PUT    /api/collector/instances/{id}/        更新
DELETE /api/collector/instances/{id}/        删除
POST   /api/collector/instances/{id}/test/   测试连接
```

---

## P1: MySQLCollector + ClickHouse 写入

### 目标
从目标 MySQL 的 performance_schema 采集慢查询数据，写入 ClickHouse。

### 交付物
- [x] `collector/collectors/base.py` — BaseCollector 抽象类
- [x] `collector/collectors/mysql.py` — MySQLCollector
- [x] `collector/clickhouse.py` — ClickHouseWriter
- [x] 手动触发采集 API: `POST /api/collector/instances/{id}/collect/`

### 采集 SQL
```sql
-- 核心查询: performance_schema.events_statements_summary_by_digest
SELECT
    DIGEST AS queryid,
    DIGEST_TEXT AS fingerprint,
    CURRENT_SCHEMA AS `schema`,
    COUNT_STAR AS cnt,
    SUM_TIMER_WAIT / 1e12 AS query_time_sum,
    MIN_TIMER_WAIT / 1e12 AS query_time_min,
    MAX_TIMER_WAIT / 1e12 AS query_time_max,
    SUM_ROWS_SENT AS rows_sent_sum,
    SUM_ROWS_EXAMINED AS rows_examined_sum,
    SUM_ROWS_AFFECTED AS rows_affected_sum,
    SUM_LOCK_TIME / 1e12 AS lock_time_sum,
    SUM_SORT_MERGE_PASSES AS merge_passes_sum,
    SUM_NO_INDEX_USED AS no_index_used_sum,
    SUM_NO_GOOD_INDEX_USED AS no_good_index_used_sum,
    SUM_CREATED_TMP_TABLES AS tmp_tables_sum,
    SUM_CREATED_TMP_DISK_TABLES AS tmp_disk_tables_sum,
    SUM_SELECT_FULL_JOIN AS full_join_sum,
    SUM_SELECT_SCAN AS full_scan_sum,
    SUM_SORT_ROWS AS sort_rows_sum,
    SUM_SORT_SCAN AS sort_scan_sum
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL AND DIGEST_TEXT IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 100
```

---

## P2: Celery + Beat 调度

### 目标
自动定时采集所有活跃实例。

### 交付物
- [x] `config/celery.py` — Celery app
- [x] `collector/tasks.py` — collect_all_metrics / collect_instance
- [x] Beat schedule: 每 60s
- [x] requirements.txt 更新

### 任务设计
```
collect_all_metrics     — beat 每 60s 触发, 遍历 active 实例
collect_instance(id)    — 单实例采集, 供手动触发复用
```

---

## P3: QAN API

### 目标
从 ClickHouse 查询聚合数据，供前端展示。

### 交付物
- [x] `qan` Django app
- [x] Top Queries API
- [x] Query Detail API
- [x] Query Trend API

### API
```
GET /api/qan/top-queries/?service=xxx&period=1h&sort=m_query_time_sum&limit=20
GET /api/qan/query/{queryid}/?service=xxx&period=1h
GET /api/qan/query/{queryid}/trend/?service=xxx&start=...&end=...
GET /api/qan/overview/?service=xxx&period=1h
```

---

## 执行顺序

```
P0 (模型+API) → P1 (采集+写入) → P2 (调度) ─┐
                                              ├→ P3 (QAN API) → P4 (前端)
                                              └→ P5 (PG/Mongo 采集器)
```

P0 和 P1 是最小可用版本。P2 让系统自动化。P3 提供查询能力。
