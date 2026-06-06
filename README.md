
# PharosDB — 全栈数据库可观测性平台

> 像灯塔一样，穿透数据库性能迷雾。

**PharosDB** 是一款使用 Go / Python / Vue 3 混合架构的原生开源监控工具。它无缝集成 **Zabbix** 与 **Prometheus**，构建了一个拥有**"基础设施 + 网络 + 数据库"完整上下文**的监控中枢。当数据库告警亮起时，PharosDB 能像灯塔一样，不仅告诉你"哪里慢"，更通过全栈视角指引你"为什么慢"。

## ✨ 核心特性与优势

* 🔗 **全方位上下文联动：** 打通 Zabbix (宿主机/网络态) 与 Prometheus (应用/中间件态) 的数据壁垒，在同一个 Dashboard 中溯源异常。
* 🕸️ **直观的锁等待拓扑图：** 告别晦涩的 `sys.innodb_lock_waits` 表格。基于 Vue 3 渲染的锁链拓扑图，秒级定位"谁阻塞了谁，阻塞了多久，涉及哪行数据"。
* 🧠 **深度 SQL 分析：** 自动进行 SQL 指纹聚合（DIGEST_TEXT 标准化）、执行计划版本对比以及等待事件分类，让慢查询无所遁形。
* ⚡ **极简而强大的混合架构：** 拒绝臃肿，按层优化。复用成熟的 Go Exporter 生态进行数据采集，利用 ClickHouse 处理海量时序与分析数据，通过 Python/Django DRF 提供极速迭代的业务逻辑支撑。

## 🏗️ 架构设计图景

PharosDB 遵循务实的 Client/Server 混合语言架构：

1. **Agent 采集层 (Go)：** 直接复用并改造开源社区成熟的 Go Exporters (如 `mysqld_exporter`, `postgres_exporter`)，轻量、高效，数据直接推送至核心 API。
2. **分析逻辑层 (Python / Django DRF)：** 专注复杂业务建模，处理 SQL 分组统计、诊断规则匹配与数据清洗，兼顾开发效率与系统稳定性。
3. **高并发存储层 (ClickHouse)：** 天然对齐 APM 与 QAN (Query Analytics) 需求，轻松应对海量高频的监控指标与日志存储。
4. **可视化表现层 (Vue 3)：** 提供现代化的交互体验，专注于复杂拓扑关系与动态图表的渲染。

---

## 👨‍💻 作者与致谢

* **Author:** 微光 (Lumen) - *Full-Stack Developer & O&M Monitoring Enthusiast*
* **Special Thanks:**
  * 感谢 Zabbix 与 Prometheus 社区提供的强大开源生态底座。
  * 感谢 **Google Gemini 模型** 在项目构思、架构选型探讨以及品牌命名 (PharosDB) 中提供的 AI 辅助与灵感启发。
