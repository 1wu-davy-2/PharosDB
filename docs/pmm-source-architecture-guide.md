# PMM (Percona Monitoring and Management) 源码架构指南

> **生成时间**: 2026-06-08
> **源码路径**: `pmm-source/`
> **上游仓库**: [github.com/percona/pmm](https://github.com/percona/pmm)

---

## 1. 项目概述

**PMM (Percona Monitoring and Management)** 是 Percona 公司开源的"最佳品类"数据库监控解决方案。它提供**单一管理面板**，用于监控 MySQL、MongoDB、PostgreSQL、Valkey、Redis 等数据库的性能。

### 核心能力
- **自定义仪表盘 & 实时告警** — 监控数据库性能
- **从节点到查询的逐层下钻** — 快速定位性能瓶颈
- **内置 Advisors 检查** — 自动识别安全威胁、性能退化、数据丢失和损坏风险
- **Query Analytics (QAN)** — 查询指纹聚合、执行计划分析、等待事件分类

### 与 PharosDB 的关系

PharosDB 的设计灵感直接来自 PMM 的架构：
| PMM 组件 | PharosDB 对应 |
|----------|-------------|
| pmm-agent (Go) | Agent 采集层 (Go Exporters) |
| pmm-managed + qan-api2 (Go) | 分析逻辑层 (Python/Django DRF) |
| ClickHouse | ClickHouse ✅ 直接复用 |
| VictoriaMetrics + Grafana | Zabbix + Prometheus + Vue 3 前端 |

---

## 2. 架构全景图

### 2.1 Client-Server 架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                          PMM Server (服务器端)                         │
│                                                                       │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  ┌────────────┐  │
│  │  PostgreSQL  │  │  ClickHouse  │  │VictoriaMetrics│  │   Grafana   │  │
│  │ (清单/配置)   │  │ (QAN 数据)    │  │ (时序指标)    │  │ (可视化)     │  │
│  └──────┬──────┘  └──────▲───────┘  └──────▲───────┘  └──────▲──────┘  │
│         │                │                  │                  │        │
│  ┌──────┴────────────────┴──────────────────┴──────────────────┴─────┐│
│  │                       pmm-managed (核心后端)                        ││
│  │  -  Inventory (Node/Service/Agent CRUD)                           ││
│  │  -  gRPC + REST API (端口 7771/7772)                              ││
│  │  -  Supervisor 进程管理                                            ││
│  │  -  Backup 编排 & HA 协调                                          ││
│  └───────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────┘
         ▲                              ▲
         │ gRPC bidirectional stream    │ HTTP/JSON
         │                              │
┌────────┴──────────────────────────────┴──────────────────────────────┐
│                        PMM Client (客户端)                             │
│  ┌──────────────┐  ┌──────────────────────────────────────────────┐  │
│  │  pmm-admin   │  │              pmm-agent                        │  │
│  │  (CLI 工具)   │  │  ┌──────────┐ ┌──────────┐ ┌───────────┐   │  │
│  │               │  │  │node_exporter│ │mysqld_   │ │postgres_  │   │  │
│  │  - add/remove │  │  │(机器指标)  │ │exporter  │ │exporter   │   │  │
│  │    service    │  │  └──────────┘ └──────────┘ └───────────┘   │  │
│  │  - inventory  │  │  ┌──────────────────────────────────────┐   │  │
│  │  - status     │  │  │  Built-in QAN Agents (进程内采集)     │   │  │
│  │  - annotate   │  │  │  perfschema / slowlog / pg_stat_*    │   │  │
│  └──────────────┘  │  └──────────────────────────────────────┘   │  │
│                     └──────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 两条核心数据管线

**Metrics 管线** (时序指标):
```
Exporters (node/mysqld/mongodb/postgres/...)
  → VMAgent (scrape exporters)
    → VictoriaMetrics (时序存储)
      → Grafana (可视化)
      → VMAlert → Alertmanager (告警)
```

**Query Analytics (QAN) 管线** (查询分析):
```
QAN Agents (perfschema/slowlog/pg_stat_statements/MongoDB profiler)
  → pmm-managed (gRPC 接收)
    → qan-api2 (gRPC 收集器, 端口 9911)
      → ClickHouse `metrics` 表
        → PMM UI / Grafana QAN Panel (可视化)
```

### 2.3 Agent 通信协议

pmm-agent 与 pmm-managed 之间通过**双向 gRPC 流**持久连接：

```
pmm-agent ←→ pmm-managed (bidirectional gRPC stream)
  Server → Agent: SetStateRequest, StartAction, StartJob, Ping
  Agent → Server: StateChanged, QanCollect, ActionResult, JobResult, Pong
```

---

## 3. 仓库目录地图

### 3.1 核心组件

| 目录 | 组件 | 语言 | 职责 | 组件指南 |
|------|------|------|------|----------|
| `managed/` | **pmm-managed** | Go | 服务器核心后端：清单管理、API、VictoriaMetrics/Grafana 配置、备份编排、告警、HA | `managed/AGENTS.md` |
| `agent/` | **pmm-agent** | Go | 客户端代理：管理 Exporters 子进程、内置 QAN/RTA 采集器、执行 Actions 和 Jobs | `agent/AGENTS.md` |
| `admin/` | **pmm-admin** | Go | CLI 工具：添加/移除监控服务、管理清单、查看状态、创建注释 | `admin/AGENTS.md` |
| `api/` | **APIs** | Protobuf | API 定义（单一事实来源）：生成 gRPC、REST、Swagger 客户端 | `api/AGENTS.md` |
| `qan-api2/` | **qan-api2** | Go | 查询分析 API：ClickHouse 数据摄入和分析查询 | `qan-api2/AGENTS.md` |
| `vmproxy/` | **vmproxy** | Go | VictoriaMetrics 反向代理：实现基于标签的访问控制 (LBAC) | `vmproxy/AGENTS.md` |
| `ui/` | **PMM UI** | TypeScript/React | PMM Web 前端：React + Vite + MUI + TanStack Query | `ui/AGENTS.md` |
| `dashboards/dashboards/` | **Grafana 仪表盘** | JSON | Grafana 仪表盘定义（MySQL/MongoDB/PostgreSQL/OS 等） | `dashboards/dashboards/AGENTS.md` |
| `dashboards/pmm-app/` | **QAN App** | TypeScript/React | Grafana 应用插件：打包仪表盘 + QAN 面板 | `dashboards/pmm-app/AGENTS.md` |
| `api-tests/` | **API 集成测试** | Go | 针对实时 PMM Server 的端到端 API 测试 | `api-tests/AGENTS.md` |
| `build/` | **构建 & 打包** | — | Docker、RPM/DEB、Packer、Ansible | `build/AGENTS.md` |

### 3.2 辅助目录

| 目录 | 用途 |
|------|------|
| `docs/` | API 文档和流程文档（技术栈、最佳实践、Git 工作流） |
| `documentation/` | 面向用户的文档（MkDocs） |
| `version/` | 版本信息和功能开关 |
| `dev/` | 开发工具（如 mongo-rs-backups） |
| `.devcontainer/` | 开发容器配置 |
| `utils/` | 跨组件共享工具（logger、errors、tls、字符串处理等） |

### 3.3 外部仓库

PMM 依赖这些 Percona 维护的外部仓库：

| 仓库 | 用途 |
|------|------|
| [percona/grafana](https://github.com/percona/grafana) | Percona 定制的 Grafana 分支 |
| [percona/node_exporter](https://github.com/percona/node_exporter) | 机器级指标采集 |
| [percona/mysqld_exporter](https://github.com/percona/mysqld_exporter) | MySQL 指标采集 |
| [percona/mongodb_exporter](https://github.com/percona/mongodb_exporter) | MongoDB 指标采集 |
| [percona/postgres_exporter](https://github.com/percona/postgres_exporter) | PostgreSQL 指标采集 |
| [percona/proxysql_exporter](https://github.com/percona/proxysql_exporter) | ProxySQL 指标采集 |
| [percona/rds_exporter](https://github.com/percona/rds_exporter) | AWS RDS 指标采集 |
| [percona/azure_metrics_exporter](https://github.com/percona/azure_metrics_exporter) | Azure 数据库指标采集 |
| [percona/pmm-qa](https://github.com/percona/pmm-qa) | E2E UI 测试和 QA 自动化 |

---

## 4. 核心领域模型

PMM 的核心清单模型是 **Node → Service → Agent** 三层结构：

```
┌──────────┐    1:N    ┌───────────┐    1:N    ┌──────────┐
│   Node   │──────────→│  Service  │──────────→│   Agent  │
│ (主机)    │           │ (数据库服务) │           │ (监控代理) │
└──────────┘           └───────────┘           └──────────┘
     │                                               │
     │             1:N                               │
     └───────────────────────────────────────────────┘
                  (Agent 直接关联 Node)

PMM Agent (父) ──1:N──→ Child Agent (子)
  (如 pmm-agent)         (如 mysqld_exporter)
```

### 实体说明

| 实体 | 存储表 | 说明 |
|------|--------|------|
| **Node** | `nodes` | 物理/虚拟主机：generic、container、remote、remote_rds、remote_azure_database |
| **Service** | `services` | 数据库/应用：MySQL、MongoDB、PostgreSQL、ProxySQL、HAProxy、External、Valkey |
| **Agent** | `agents` | 监控代理：pmm-agent、各类 exporter、QAN agents、VMAgent 等 |

### 关系
- 一个 Node 有多个 Service
- 一个 Service 属于一个 Node
- 一个 Agent 运行在一个 Node 上 (`runs_on_node_id`)，可选择监控一个 Service (`service_id`)
- 子 Agent 属于父 PMM Agent (`pmm_agent_id`)

---

## 5. 组件详解

### 5.1 pmm-managed — 服务器核心

**代码量最大、最复杂的组件**，是 PMM Server 的大脑。

**核心职责**:
- 管理所有服务器端组件（VictoriaMetrics、Grafana、QAN、VMAlert、Alertmanager）
- 维护 Node/Service/Agent 清单（存储在 PostgreSQL）
- 编排备份任务
- 运行 Advisor 检查（Starlark 脚本引擎）
- 处理 HA 共识（Raft 协议）
- 暴露 gRPC/REST API

**服务架构模式**（依赖注入）:
```go
type Service struct {
    db       *reform.DB
    l        *logrus.Entry
    // 其他依赖作为接口注入
}

func New(db *reform.DB, logger *logrus.Entry, ...) *Service {
    return &Service{db: db, l: logger, ...}
}
```

**端口规划**:
| 端口 | 协议 | 用途 |
|------|------|------|
| 7771 | gRPC | 主要 API 协议 |
| 7772 | HTTP/JSON | gRPC-Gateway REST API |
| 7773 | HTTP | Debug 端点（/debug/metrics, /debug/pprof, /debug/vars） |

**关键子服务**:
| 服务包 | 职责 |
|--------|------|
| `services/agents` | Agent 注册、双向 gRPC 处理器、状态跟踪 |
| `services/inventory` | Node/Service/Agent CRUD + 校验 |
| `services/management` | 高层操作（add/remove MySQL、PostgreSQL 等） |
| `services/server` | 设置、版本、更新、日志 |
| `services/backup` | 备份编排、兼容性检查 |
| `services/checks` | Advisor 检查（Starlark） |
| `services/alerting` | 告警模板管理 |
| `services/victoriametrics` | VictoriaMetrics scrape 配置生成 |
| `services/vmalert` | VMAlert 规则生成 |
| `services/grafana` | Grafana API 客户端（用户、仪表盘、注释） |
| `services/supervisord` | Supervisord 进程管理 |
| `services/ha` | Raft 共识、Gossip 协议、Leader 选举 |

**ORM 选择**：使用 **reform**（非 gorm），模型定义在 `managed/models/*_model.go`，通过 `//go:generate go tool reform` 生成代码。

### 5.2 pmm-agent — 客户端代理

运行在每个被监控主机上的**轻量级守护进程**。

**核心设计：Supervisor 模式**
```
pmm-managed 下发 SetStateRequest（期望状态）
       ↓
Supervisor 计算差异（toStart / toRestart / toStop）
       ↓
调和实际状态以匹配期望状态
```

**两种 Agent 类型**:

1. **Process Agents（外部进程）** — 作为子进程运行的 Exporters：
   - `node_exporter` — 机器级指标
   - `mysqld_exporter` — MySQL 指标
   - `mongodb_exporter` — MongoDB 指标
   - `postgres_exporter` — PostgreSQL 指标
   - `proxysql_exporter` — ProxySQL 指标
   - `rds_exporter` — AWS RDS 指标
   - `azure_exporter` — Azure 数据库指标
   - `valkey_exporter` — Valkey/Redis 指标
   - VMAgent — Prometheus scrape 代理
   - 每个进程有状态机：`STARTING → RUNNING`（或 `FAILING` + 退避重试）

2. **Built-in Agents（进程内）** — Go 代码实现，直接运行在 pmm-agent 进程内：
   - MySQL QAN: perfschema、slowlog
   - PostgreSQL QAN: pg_stat_statements、pg_stat_monitor
   - MongoDB QAN: profiler、mongolog
   - RTA (Real-Time Analytics) agents

**关键包**:
| 包 | 职责 |
|----|------|
| `commands` | CLI 命令：run（主事件循环）、setup（注册到服务器） |
| `config` | 配置管理：YAML + CLI 标志 + 环境变量 |
| `client` | gRPC 客户端：持久连接管理、消息路由 |
| `agents/supervisor` | 中央生命周期管理 |
| `agents/process` | 外部进程包装器（状态机 + 退避） |
| `runner/actions` | 短期操作：EXPLAIN、PT summary |
| `runner/jobs` | 长期作业：备份/恢复 |

### 5.3 pmm-admin — CLI 管理工具

用户通过命令行管理监控服务的入口。

**命令结构**:
```
pmm-admin
├── config                  # 配置 pmm-agent 连接
├── list                    # 列出被监控的服务
├── status                  # 显示 PMM 状态
├── summary                 # 生成诊断摘要
├── annotate                # 添加图表注释
├── inventory               # 低级清单操作
│   ├── list nodes/services/agents
│   ├── add node/service/agent
│   └── remove node/service/agent
└── management              # 高级管理操作（推荐）
    ├── add mysql/postgresql/mongodb/...
    └── remove / register / unregister
```

**Management vs Inventory**:
- **Management 命令**：一键完成 Node + Service + Agent 创建（用户常用）
- **Inventory 命令**：逐个操作实体（高级场景）

### 5.4 API 层 — 协议定义

`api/` 目录是**所有 API 的单一事实来源**，包含 Protocol Buffer (`.proto`) 定义。

**代码生成管线**:
```
.proto 文件（事实来源）
  → protoc-gen-go           → *.pb.go（Go 结构体）
  → protoc-gen-go-grpc      → *_grpc.pb.go（gRPC 接口）
  → protoc-gen-grpc-gateway → *.pb.gw.go（HTTP/JSON 网关）
  → protoc-gen-validate     → *.pb.validate.go（消息校验）
  → protoc-gen-openapiv2    → *.swagger.json（OpenAPI 文档）
  → swagger generate client → json/client/（Go HTTP 客户端）
```

**主要 API 服务**:
| 服务 | Proto 位置 | 用途 |
|------|-----------|------|
| `ServerService` | `server/v1/` | 版本、就绪检查、设置、更新 |
| `NodesService` | `inventory/v1/` | Node CRUD |
| `ServicesService` | `inventory/v1/` | Service CRUD |
| `AgentsService` | `inventory/v1/` | Agent CRUD |
| `ManagementService` | `management/v1/` | 高层 add/remove 操作 |
| `BackupService` | `backup/v1/` | 备份管理 |
| `QANService` | `qan/v1/` | 查询分析报告 |
| `AdvisorService` | `advisors/v1/` | Advisor 检查 |
| `AlertingService` | `alerting/v1/` | 告警管理 |
| `AgentService` | `agent/v1/` | Agent ↔ Server 双向流 |

### 5.5 qan-api2 — 查询分析引擎

专门负责**查询性能数据的存储和分析**。

**数据流**:
```
pmm-agent QAN 采集器
  → pmm-managed（gRPC 转发）
    → qan-api2 CollectorService.Collect（gRPC 端口 9911）
      → MetricsBucket（批量写入器：500ms 或 100 条缓冲）
        → ClickHouse `metrics` 表

PMM UI / API 客户端
  → qan-api2 QANService（gRPC/REST 端口 9911/9922）
    → Reporter / Metrics 模型（动态 SQL 查询）
      → ClickHouse
```

**核心数据模型**: `metrics` 表（ClickHouse）
- **维度列**: service_name, database, schema, username, client_host, node_id, service_id 等
- **查询标识**: queryid (指纹 hash), fingerprint (标准化 SQL), query (示例 SQL)
- **性能指标**: num_queries, m_query_time_sum/min/max/p99, m_lock_time_*, m_rows_sent_*, m_rows_examined_* 等
- **时间**: period_start (DateTime), period_length (秒)

**技术栈**:
- ClickHouse 驱动: `github.com/ClickHouse/clickhouse-go/v2`
- 查询层: `github.com/jmoiron/sqlx`（无 ORM，直接写 SQL）
- 动态 SQL: `text/template` 构建报表查询
- 迁移: `golang-migrate/migrate/v4`
- 支持 ReplicatedMergeTree（集群模式）

### 5.6 PMM UI — Web 前端

React/TypeScript 应用，运行在 Grafana iframe 内。

**Monorepo 结构**（Yarn Workspaces + Turborepo）:
| 包 | 路径 | 用途 |
|----|------|------|
| **pmm** | `ui/apps/pmm/` | 主 PMM UI 应用（Vite + React） |
| **pmm-compat** | `ui/apps/pmm-compat/` | Grafana 插件（Webpack） |
| **@pmm/shared** | `ui/packages/shared/` | 共享代码：跨框架消息、类型、工具 |

**关键路由**:
| 路由 | 页面 |
|------|------|
| `/updates` | PMM Server 更新 |
| `/help` | 帮助中心 |
| `/rta` | 实时分析 |
| `/graph/*` | Grafana iframe（仪表盘） |

**技术选型**:
- React 18 + TypeScript + Vite
- MUI (Material UI) + @percona/percona-ui 组件库
- TanStack Query（服务端状态管理，缓存 + 去重 + 后台刷新）
- React Context（UI/认证状态）
- Vitest + Testing Library（测试）

### 5.7 vmproxy — VictoriaMetrics 代理

轻量级、无状态的 HTTP 反向代理，实现**基于标签的访问控制 (LBAC)**。

```
Client (Grafana / API)
  → HTTP 请求 + X-Proxy-Filter Header
    → vmproxy（解析 Header，注入 extra_filters[]）
      → VictoriaMetrics（应用标签过滤）
        → 响应返回给客户端
```

过滤机制示例：Header `X-Proxy-Filter: WyJlbnY9UUEiLCAicmVnaW9uPUVVIl0=` → Base64 解码 → `["env=QA", "region=EU"]` → 注入到 VictoriaMetrics 查询参数。

---

## 6. 技术栈速览

| 技术 | 用途 |
|------|------|
| **Go** | 所有后端组件（managed、agent、admin、qan-api2、vmproxy） |
| **TypeScript / React** | PMM UI 前端 |
| **Protobuf v3 / gRPC** | API 定义和组件间通信 |
| **grpc-gateway** | 从 gRPC 定义自动生成 HTTP/JSON REST API |
| **PostgreSQL** | pmm-managed 主数据存储（清单、设置、备份记录） |
| **ClickHouse** | 查询分析数据存储（qan-api2） |
| **VictoriaMetrics** | 时序指标存储 |
| **VMAlert** | 告警规则评估 |
| **Grafana** | 仪表盘和可视化 |
| **reform** | Go ORM（仅 pmm-managed 使用，非 gorm） |
| **sqlx** | ClickHouse SQL 查询（qan-api2） |
| **logrus** | 结构化日志 |
| **testify** | 测试断言（仅 assert/require） |
| **mockery** | Go 接口 Mock 生成 |
| **Kong** | pmm-admin CLI 框架 |
| **Kingpin** | 其他 CLI 组件标志解析 |
| **Docker Compose** | 本地开发环境 |
| **Buf** | Protobuf 编译、lint、破坏性变更检测 |

---

## 7. 开发工作流

### 7.1 核心 Make 目标

```bash
make env-up          # 启动开发容器（PMM Server）
make env-up-rebuild  # 从零重建开发容器
make gen             # 生成所有代码（protobuf、reform、mockery、格式化）
make check           # 运行所有 linter
make format          # 格式化代码（gofumpt、goimports、gci）
make release         # 构建所有二进制文件
make test-common     # 运行公共单元测试
make api-test        # 运行 API 集成测试
make prepare-pr      # 完整 PR 前管线
```

### 7.2 代码生成命令

```bash
# 从仓库根目录 — 生成所有内容
make gen

# 仅在 api/ 目录 — 只生成 API 代码
cd api && make gen

# Lint proto 文件
make check   # 运行 buf lint
```

### 7.3 关键文件参考

| 文件 | 用途 |
|------|------|
| `AGENTS.md` | AI Agent 开发总指南（单一权威入口） |
| `Makefile` / `Makefile.include` | 构建和开发目标 |
| `docker-compose.dev.yml` | 开发环境定义 |
| `go.mod` | Go 模块定义 |
| `.golangci.yml` | Linter 配置 |
| `docs/process/tech_stack.md` | 技术栈选型说明 |
| `docs/process/best_practices.md` | 编码最佳实践 |
| `docs/process/GIT_AND_GITHUB.md` | Git 工作流 |

---

## 8. 全局开发约定

### 代码风格
- 使用 `gofumpt -s` 格式化，运行 `make format`
- 遵循 [Effective Go](https://golang.org/doc/effective_go.html)
- Import 分组：stdlib → 外部（percona → 第三方）→ 内部
- 使用 `any` 而不是 `interface{}`
- 不使用命名返回值
- 注释放在独立行，不内联

### 错误处理
- API 错误使用 `status.Error()` + 正确的 gRPC 状态码
- 错误包装：`fmt.Errorf("context: %w", err)`
- 尽早返回错误，避免深层嵌套
- 使用标准库 `errors` 包

### 日志
- 使用 `logrus` + 结构化字段
- 传递 `*logrus.Entry`（非 `*logrus.Logger`）
- 输出到无缓冲 stderr

### 测试
- 使用 `testify/assert` 和 `testify/require`（不使用 suites）
- Mock 生成：`mockery`（配置在 `.mockery.yaml`）
- 单元测试：`*_test.go` 放在实现旁边
- 集成测试：`/api-tests/` 目录
- E2E 测试：[pmm-qa](https://github.com/percona/pmm-qa)

### 永不编辑的文件
- `*.pb.go`、`*.pb.gw.go`、`*_reform.go`、`*.pb.validate.go`
- Swagger 规范文件
- `json/client/` 目录下的文件

---

## 9. 对 PharosDB 改造的启示

### 9.1 可直接借鉴的设计

1. **Agent Supervisor 模式** — pmm-agent 的期望状态调和模式可以复用到 PharosDB Agent 的设计中
2. **QAN 管线** — ClickHouse 的 `metrics` 表设计（指纹聚合 + 多维度分组 + 统计指标）是 SQL 分析的黄金标准
3. **Node → Service → Agent 三层模型** — 这个清单模型可以适配 PharosDB，Agent 类型可以扩展
4. **双向 gRPC 流** — Server 主动推送配置变更给 Agent，避免轮询
5. **API 生成管线** — Protobuf → gRPC + REST + Swagger 的单事实来源模式

### 9.2 PharosDB 可改进的方向

| PMM 的设计 | PharosDB 可做的改进 |
|------------|-------------------|
| Grafana 仪表盘（JSON 定义） | 用 Vue 3 组件替代，实现更灵活的交互 |
| Go 后端组件多、分散 | Python/Django 统一业务层，更快的迭代速度 |
| 无锁等待拓扑图 | PharosDB 已有此特性，是差异化优势 |
| PMM UI 运行在 Grafana iframe 内 | PharosDB 可以是独立 SPA，体验更好 |
| PMM 仅支持数据库层 | PharosDB 集成 Zabbix，可看基础设施+网络层 |

### 9.3 改造优先级建议

1. **先理解 QAN 管线** — 这是数据库监控的核心价值（`qan-api2/` + `agent/agents/mysql|postgres|mongodb/`）
2. **再看 Agent 通信协议** — 理解 Agent 如何上报数据（`api/agent/v1/agent.proto`）
3. **然后看 Inventory 管理** — 理解 Node/Service/Agent 生命周期（`managed/services/inventory/` + `management/`）
4. **最后看前端** — 理解 Grafana 插件和 QAN 面板如何消费数据（`dashboards/pmm-app/`）

---

## 10. 官方资源链接

| 资源 | 链接 |
|------|------|
| **PMM 官方文档** | [https://docs.percona.com/percona-monitoring-and-management/3/index.html](https://docs.percona.com/percona-monitoring-and-management/3/index.html) |
| **PMM GitHub 仓库** | [https://github.com/percona/pmm](https://github.com/percona/pmm) |
| **PMM 安装指南** | [https://docs.percona.com/percona-monitoring-and-management/3/install-pmm/index.html](https://docs.percona.com/percona-monitoring-and-management/3/install-pmm/index.html) |
| **Percona 官方页面** | [https://www.percona.com/software/database-tools/percona-monitoring-and-management](https://www.percona.com/software/database-tools/percona-monitoring-and-management) |
| **社区论坛** | [https://forums.percona.com/c/percona-monitoring-and-management-pmm](https://forums.percona.com/c/percona-monitoring-and-management-pmm) |
| **JIRA 问题跟踪** | [https://perconadev.atlassian.net](https://perconadev.atlassian.net) |
| **技术栈文档** | `pmm-source/docs/process/tech_stack.md` |
| **最佳实践文档** | `pmm-source/docs/process/best_practices.md` |
| **Git 工作流文档** | `pmm-source/docs/process/GIT_AND_GITHUB.md` |
| **gRPC 官方文档** | [https://grpc.io/](https://grpc.io/) |
| **Protobuf v3 文档** | [https://developers.google.com/protocol-buffers/](https://developers.google.com/protocol-buffers/) |
| **grpc-gateway** | [https://github.com/grpc-ecosystem/grpc-gateway](https://github.com/grpc-ecosystem/grpc-gateway) |
| **ClickHouse 官方** | [https://clickhouse.com/](https://clickhouse.com/) |
| **VictoriaMetrics** | [https://victoriametrics.com/](https://victoriametrics.com/) |
| **Grafana 官方** | [https://grafana.com/](https://grafana.com/) |

---

> **下一步建议**: 从 `qan-api2/` 开始深入阅读源码，这是 PMM 最核心的查询分析引擎，也是 PharosDB 改造最需要理解的部分。配合阅读 `agent/agents/mysql/`、`agent/agents/postgres/`、`agent/agents/mongodb/` 了解 QAN 数据是如何采集的。
