# PharosDB

> 像灯塔一样，穿透数据库性能迷雾。

PharosDB 是一个数据库可观测性平台，专注于那些现有工具做不好的事情：把慢查询、锁等待、死锁这些分散的信号拼成一张完整的图，让你在告警响起的时候不只是知道"哪里慢"，还能知道"为什么慢"。

---

## 项目现状

当前已实现的功能：

- **SQL 分析（QAN）** — 基于 `performance_schema` 或 `pg_stat_statements` 的慢查询聚合，支持 SQL 指纹、执行频次、耗时分布、扫描行数，按服务和时间段过滤
- **锁链拓扑** — 实时从 `performance_schema.data_lock_waits`（MySQL 8+ / MariaDB 10.6+）或 `information_schema.INNODB_LOCK_WAITS`（MySQL 5.7 / MariaDB 旧版）拉取活跃锁等待，渲染成有向图，谁阻塞了谁、等了多久、涉及哪张表一目了然；DFS 算法检测死锁环，不解析 `INNODB STATUS` 文本
- **历史死锁记录** — 锁快照写入 ClickHouse，支持按时间段回溯，30 天 TTL 自动清理
- **自适应采集** — 无锁时 30s 轮询，检测到活跃锁自动切 5s 高频，锁消失后恢复；MySQL 版本在连接时自动识别，无需手动配置
- **实例管理** — MySQL / PostgreSQL / MongoDB 实例注册，连接测试，采集历史
- **告警中心** — 基础告警规则管理（开发中）
- **多语言 + 主题** — 中英文切换，亮色 / 暗色主题，全量 CSS 变量

---

## 技术栈

| 层次 | 技术 |
|------|------|
| 前端 | React 18, Vite, react-i18next, CSS Variables |
| 后端 | Python 3.12, Django 5, Django REST Framework, SimpleJWT |
| 分析存储 | ClickHouse（时序指标、锁快照，MergeTree + TTL）|
| 元数据库 | MariaDB / MySQL（Django ORM，实例配置、用户、告警规则）|
| 采集 | pymysql + psycopg2，内置线程调度器，无需 Celery / Redis |

---

## 目录结构

```
PharosDB/
├── accounts/          用户认证（JWT）
├── collector/         实例管理、QAN 采集、调度器
│   └── collectors/    MySQL / PostgreSQL / 锁快照 采集器
├── qan/               QAN 查询 API
├── locks/             锁拓扑 API（实时 + 历史）
├── alerts/            告警规则与事件
├── config/            Django settings / urls
├── clickhouse_schema/ ClickHouse 建表 DDL
├── docs/              设计文档
├── frontend/          React 前端
│   └── src/
│       ├── pages/     各功能页面
│       ├── components/
│       ├── context/   Auth / Theme
│       └── i18n/      zh / en 翻译
└── dev.ps1            本地开发启动脚本
```

---

## 本地开发

### 依赖

- Python 3.12+
- Node.js 20+
- MariaDB / MySQL（元数据库）
- ClickHouse（指标存储）

### 快速启动

```powershell
# 1. 克隆并安装依赖
git clone <repo>
cd PharosDB
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

cd frontend
npm install
cd ..

# 2. 配置环境变量
copy .env.example .env
# 编辑 .env，填写数据库连接信息

# 3. 初始化数据库
python manage.py migrate
python manage.py createsuperuser

# 4. 创建 ClickHouse 表
# 执行 clickhouse_schema/ 下的 .sql 文件

# 5. 启动开发服务
.\dev.ps1
```

启动后：

- 前端：http://localhost:17000
- 后端 API：http://localhost:17080

### 端口约定

| 服务 | 端口 | 说明 |
|------|------|------|
| 前端 Vite | 17000 | `frontend/vite.config.js` |
| 后端 Django | 17080 | `dev.ps1` 启动参数 |

`dev.ps1` 会在启动前自动 kill 占用这两个端口的旧进程。

---

## API 概览

| 路径 | 说明 |
|------|------|
| `POST /api/auth/login/` | 登录，返回 JWT |
| `GET  /api/collector/instances/` | 实例列表 |
| `POST /api/collector/instances/<id>/collect/` | 手动触发采集 |
| `GET  /api/qan/query-stats/` | 慢查询聚合 |
| `GET  /api/locks/topology/?instance_id=<id>` | 实时锁链拓扑 |
| `GET  /api/locks/history/?instance_id=<id>&hours=1` | 历史锁等待 |

---

## 文档

- [锁等待 / 死锁可视化设计](docs/lock_wait_deadlock_design.md)
- [QAN 采集核心循环](docs/QAN_Agent_采集核心循环.md)
- [架构设计](docs/architecture_design.md)

---

## 作者

微光（Lumen）— Full-Stack Developer & O&M Monitoring Enthusiast
