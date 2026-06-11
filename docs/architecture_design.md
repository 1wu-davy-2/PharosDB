# PharosDB 架构设计

## 1. 系统定位

PharosDB 是一个**数据库可观测性平台**，专注于 SQL 性能分析（QAN - Query Analytics）。通过 Agentless 模式直连目标数据库，采集 `performance_schema` 中的慢查询、锁等待、执行计划等指标，存入 ClickHouse 进行聚合分析。

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        PharosDB Frontend                        │
│                     React + Vite (port 17000)                    │
└──────────────────────────────┬──────────────────────────────────┘
                               │ REST API
┌──────────────────────────────▼──────────────────────────────────┐
│                      PharosDB Backend (Django)                   │
│                                                                  │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ accounts │  │ collector │  │   qan    │  │    config      │  │
│  │ (JWT认证) │  │ (数据采集) │  │ (查询分析)│  │ (Celery/设置) │  │
│  └──────────┘  └─────┬─────┘  └────┬─────┘  └───────────────┘  │
│                      │              │                             │
└──────────────────────┼──────────────┼─────────────────────────────┘
                       │              │
          ┌────────────▼───┐    ┌─────▼──────┐
          │   MariaDB      │    │ ClickHouse │
          │  (Django ORM)  │    │ (指标存储)  │
          │  pharos_db     │    │ pharos_db  │
          └────────────────┘    └────────────┘
                       │
         ┌─────────────┼─────────────────┐
         ▼             ▼                 ▼
    ┌─────────┐  ┌──────────┐    ┌──────────┐
    │  MySQL  │  │PostgreSQL│    │ MongoDB  │
    │ (目标DB) │  │ (目标DB) │    │ (目标DB) │
    └─────────┘  └──────────┘    └──────────┘
```

## 3. 核心模块设计

### 3.1 collector — 数据采集引擎

```
collector/
├── models.py              # DatabaseInstance 模型
├── views.py               # CRUD API + 连接测试
├── serializers.py         # DRF 序列化器
├── urls.py                # 路由
├── admin.py               # Django Admin
├── clickhouse.py          # ClickHouseWriter 单例
├── tasks.py               # Celery 异步任务
├── collectors/
│   ├── __init__.py
│   ├── base.py            # BaseCollector 抽象类
│   └── mysql.py           # MySQLCollector
```

#### DatabaseInstance 模型

| 字段 | 类型 | 说明 |
|------|------|------|
| name | CharField(128) | 显示名称 |
| db_type | CharField(choices) | mysql / postgresql / mongodb |
| host | CharField(255) | 目标主机地址 |
| port | PositiveIntegerField | 端口号 |
| username | CharField(128) | 连接用户名 |
| password | TextField | Fernet 加密存储 |
| environment | CharField(32) | prod / staging / dev |
| cluster | CharField(128) | 所属集群 (可选) |
| is_active | BooleanField | 是否启用采集 |
| collect_interval | PositiveIntegerField | 采集间隔 (秒), 默认 60 |
| last_collected_at | DateTimeField | 上次采集时间 |
| created_at / updated_at | DateTimeField | 时间戳 |

#### 采集器设计

```
BaseCollector (ABC)
├── connect()           # 建立连接
├── collect()           # 抽象方法 — 执行采集
├── transform()         # 转换为 ClickHouse 行格式
└── close()             # 关闭连接

MySQLCollector(BaseCollector)
├── collect_summaries() # performance_schema.events_statements_summary_by_digest
├── collect_history()   # performance_schema.events_statements_history
└── _compute_delta()    # 计算两次快照之间的差值
```

#### ClickHouse 写入

- 使用 `clickhouse-driver` (原生协议, 端口 9000)
- 批量 INSERT 到 `pharos_db.metrics` 表
- 使用参数化查询防止 SQL 注入
- 单例模式复用连接

### 3.2 qan — 查询分析服务

```
qan/
├── services.py          # ClickHouse 查询逻辑
├── views.py             # REST API 视图
├── serializers.py       # 响应序列化器
└── urls.py              # 路由
```

#### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/qan/top-queries/ | Top N 慢查询 |
| GET | /api/qan/query/{queryid}/detail/ | 单条查询详情 |
| GET | /api/qan/query/{queryid}/trend/ | 时间趋势 |
| GET | /api/qan/overview/ | 概览统计 |

### 3.3 config — 配置与调度

- `celery.py` — Celery app 初始化
- `settings.py` — 增加 Celery 配置、INSTALLED_APPS
- Beat Schedule — 每 60s 触发 `collect_all_metrics` 任务

## 4. 数据流

### Agentless 采集流程

```
1. Celery Beat 触发 collect_all_metrics
2. 遍历所有 is_active=True 的 DatabaseInstance
3. 对每个实例:
   a. MySQLCollector.connect() — TCP 直连目标 MySQL
   b. MySQLCollector.collect_summaries()
      SELECT * FROM performance_schema.events_statements_summary_by_digest
      WHERE DIGEST IS NOT NULL AND DIGEST_TEXT IS NOT NULL
   c. 计算 delta (当前快照 - 上一次快照)
   d. transform() — 映射到 ClickHouse metrics 表的 269 列
   e. ClickHouseWriter.write_metrics() — 批量写入
   f. 更新 last_collected_at
```

### 数据映射 (performance_schema → ClickHouse metrics)

| performance_schema 字段 | ClickHouse metrics 字段 | 转换 |
|------------------------|------------------------|------|
| DIGEST | queryid | 直接映射 |
| DIGEST_TEXT | fingerprint | 直接映射 |
| CURRENT_SCHEMA | `schema` | 直接映射 |
| COUNT_STAR | m_query_time_cnt | 直接映射 |
| SUM_TIMER_WAIT | m_query_time_sum | 除以 1e12 (皮秒→秒) |
| MIN_TIMER_WAIT | m_query_time_min | 除以 1e12 |
| MAX_TIMER_WAIT | m_query_time_max | 除以 1e12 |
| SUM_ROWS_SENT | m_rows_sent_sum | 直接映射 |
| SUM_ROWS_EXAMINED | m_rows_examined_sum | 直接映射 |
| SUM_ROWS_AFFECTED | m_rows_affected_sum | 直接映射 |
| SUM_LOCK_TIME | m_lock_time_sum | 除以 1e12 |
| SUM_SORT_MERGE_PASSES | m_merge_passes_sum | 直接映射 |
| SUM_NO_INDEX_USED | m_no_index_used_sum | 直接映射 |
| SUM_NO_GOOD_INDEX_USED | m_no_good_index_used_sum | 直接映射 |
| ... | ... | ... |

## 5. 技术栈

| 组件 | 技术选型 | 版本 |
|------|---------|------|
| Web 框架 | Django + DRF | 5.1.x + 3.15.x |
| 认证 | JWT (SimpleJWT) | 5.4.x |
| 关系数据库 | MariaDB | 10.5.29 |
| 时序数据库 | ClickHouse | 26.5.1 |
| 任务队列 | Celery + Redis | 5.4.x |
| 调度 | django-celery-beat | 2.7.x |
| 前端 | React + Vite | 18.x + 5.x |
| 密码加密 | cryptography (Fernet) | 43.x |
| ClickHouse 驱动 | clickhouse-driver | 0.2.10 |

## 6. 安全设计

- 数据库密码使用 Fernet 对称加密存储，密钥从环境变量 `FERNET_KEY` 读取
- 所有 API 需 JWT 认证 (除 login 外)
- ClickHouse 使用独立的只读用户查询 (建议生产环境)
- CORS 仅允许前端域名

## 7. Agentless vs Agent 能力边界

| 数据源 | Agentless | Agent |
|--------|:---------:|:-----:|
| 慢查询 / 查询指纹 | ✅ performance_schema | ✅ 慢查询日志 |
| 锁等待 | ✅ data_lock_waits | 需文件解析 |
| 执行计划 | ✅ EXPLAIN | 不适用 |
| 等待事件 | ✅ events_waits_* | 同左 |
| InnoDB 指标 | ✅ SHOW GLOBAL STATUS | 同左 |
| OS 层 (CPU/磁盘/内存) | ❌ | ✅ |

**结论**: Agentless 覆盖 SQL 性能分析的全部需求，OS 层指标由 Zabbix/Prometheus 负责。
