# 告警中心 — 设计与实现

## 背景

PMM 的告警依赖 Prometheus AlertManager，与 PharosDB 所用的 ClickHouse 数据源完全割裂。PharosDB 直接以
`pharos_db.metrics` 表（QAN 采集写入）为数据源，在不引入任何外部告警系统的前提下，实现规则配置、状态评估、
事件管理和 Webhook 通知的完整闭环。

---

## 整体架构

```
ClickHouse pharos_db.metrics
        │
        ▼  evaluator.py — 每 5 分钟由线程调度器调用
        │   ├─ 遍历所有 is_enabled=True 的 AlertRule
        │   ├─ 按规则类型执行 ClickHouse 聚合查询
        │   ├─ 与 threshold 比较 → firing / resolved 状态机
        │   └─ 写入 AlertEvent，触发 Webhook 通知
        │
  MariaDB
  ├─ alert_rule    (AlertRule 模型)
  └─ alert_event   (AlertEvent 模型)
        │
   DRF API (alerts app)
   /api/alerts/rules/     — CRUD + toggle + test
   /api/alerts/events/    — 只读列表 + summary
        │
   React AlertsPage
   ├─ 汇总卡片 (firing total / warning / critical / active rules)
   ├─ 规则管理 tab (列表、新建、编辑、删除、启停、单次测试)
   └─ 事件记录 tab (firing / resolved / 全部 筛选)
```

---

## 数据模型

### AlertRule — `alert_rule`

| 字段 | 类型 | 说明 |
|---|---|---|
| name | CharField(128) | 规则名称，全局唯一展示标识 |
| rule_type | CharField | slow_query_time / no_index_ratio / query_count / custom_sql |
| instance | FK → DatabaseInstance (nullable) | 留空 = 对所有活跃实例生效 |
| threshold | FloatField | 触发阈值，单位由 rule_type 决定 |
| period | PositiveIntegerField | 统计窗口，分钟，默认 5 |
| severity | CharField | warning / critical |
| webhook_url | CharField(512) | 空则不通知 |
| custom_sql | TextField | rule_type=custom_sql 时有效 |
| is_enabled | BooleanField | 禁用时评估器跳过 |

### AlertEvent — `alert_event`

| 字段 | 类型 | 说明 |
|---|---|---|
| rule | FK → AlertRule | 触发来源规则 |
| instance | FK → DatabaseInstance (nullable) | 具体触发实例 |
| metric_value | FloatField | 触发时的实际指标值 |
| threshold | FloatField | 触发时的规则阈值快照 |
| status | CharField | firing / resolved |
| fired_at | DateTimeField | 触发时间 |
| resolved_at | DateTimeField (nullable) | 恢复时间 |
| notified | BooleanField | Webhook 是否已发送成功 |
| notify_error | TextField | 通知失败时的错误描述 |

`duration_seconds` 是 property，计算 `(resolved_at or now) - fired_at`。

索引：`(rule, instance, status)` 用于快速查找活跃事件；`(status, fired_at)` 用于 summary 聚合。

---

## 评估器设计

### 规则类型与 ClickHouse 查询

所有查询针对 `pharos_db.metrics`，绑定参数：
- `%(service)s`  — 实例的 `name` 字段（与采集时写入的 `service_name` 一致）
- `%(seconds)s`  — `period * 60`
- `%(threshold)s` — 规则阈值（仅 slow_query_time 子查询用到）

**slow_query_time**（单位：秒）

```sql
SELECT countIf(avg_query_time > %(threshold)s)
FROM (
    SELECT
        queryid,
        if(SUM(num_queries) > 0,
           SUM(m_query_time_sum) / SUM(num_queries), 0) AS avg_query_time
    FROM pharos_db.metrics
    WHERE service_name = %(service)s
      AND period_start >= now() - INTERVAL %(seconds)s SECOND
    GROUP BY queryid
)
```

先按 queryid 聚合出每类查询的平均耗时，再统计超过阈值的查询数量。
指标值 > 0 即触发，语义：「周期内存在平均耗时超标的查询类型」。

**no_index_ratio**（单位：%）

```sql
SELECT if(SUM(num_queries) = 0, 0,
    SUM(m_no_index_used_sum) * 100.0 / SUM(num_queries)
)
FROM pharos_db.metrics
WHERE service_name = %(service)s
  AND period_start >= now() - INTERVAL %(seconds)s SECOND
```

**query_count**（单位：次）

```sql
SELECT SUM(num_queries)
FROM pharos_db.metrics
WHERE service_name = %(service)s
  AND period_start >= now() - INTERVAL %(seconds)s SECOND
```

**custom_sql**

用户自由编写 ClickHouse SQL，返回单行单列数值，与阈值比较。可用同名占位符。
示例：统计某个 schema 的 DML 次数：
```sql
SELECT SUM(num_queries)
FROM pharos_db.metrics
WHERE service_name = %(service)s
  AND period_start >= now() - INTERVAL %(seconds)s SECOND
  AND m_rows_affected_sum > 0
```

### 状态机

`_evaluate_single(rule, instance)` 的逻辑：

```
query_metric → value

value > threshold  AND  无 firing 事件  →  创建 AlertEvent(firing)  →  发 Webhook
value <= threshold AND  有 firing 事件  →  更新 resolved_at          →  发 Webhook(resolved)
其余情况（value is None / 状态未变）     →  不操作
```

每个 `(rule, instance)` 组合独立维护状态。不做防抖（连续 N 次才触发），
保持实现简单；如需防抖可在 rule 上增加 `eval_count` 字段后续迭代。

---

## 调度器

`alerts/apps.py` 中使用与 collector 相同的 `threading.Timer` 链式调度模式：

```
AlertsConfig.ready()
    └─ 仅在 RUN_MAIN=true 时执行（避免 Django StatReloader 双进程双启动）
        └─ _schedule_evaluation()
            └─ Timer(300s, _run)
                └─ evaluate_all_rules()
                └─ _schedule_evaluation()  # 自我续期
```

间隔固定 300 秒（5 分钟），与告警规则 `period` 最小粒度一致。
评估本身是同步阻塞，单次执行时间通常在 ClickHouse 往返延迟级别（< 1s），不影响续期精度。

---

## Webhook 通知

发送格式兼容 Alertmanager v4，可直接对接支持 Alertmanager webhook 的告警平台（飞书、钉钉 Incoming Webhook、
PagerDuty 等均有适配插件）。

```json
{
  "version": "4",
  "status": "firing",
  "alerts": [{
    "status": "firing",
    "labels": {
      "alertname": "规则名",
      "rule_type": "slow_query_time",
      "severity": "critical",
      "instance": "mariadb-prod-01"
    },
    "annotations": {
      "metric_value": "3",
      "threshold": "1",
      "description": "规则描述"
    },
    "startsAt": "2026-06-12T10:00:00+08:00",
    "endsAt": "0001-01-01T00:00:00Z"
  }]
}
```

恢复时 `status` 改为 `resolved`，`endsAt` 填入 `resolved_at`。
`notified` / `notify_error` 字段写回 AlertEvent，便于排查通知失败原因。

---

## API 端点

前缀 `/api/alerts/`，均需 JWT 认证。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | rules/ | 规则列表（含 firing_count） |
| POST | rules/ | 新建规则 |
| PUT | rules/{id}/ | 全量更新规则 |
| DELETE | rules/{id}/ | 删除规则（级联删除事件） |
| POST | rules/{id}/toggle/ | 启用/禁用切换 |
| POST | rules/{id}/test/ | 立即查询指标，不写事件，返回当前值 |
| GET | events/ | 事件列表，?status=firing|resolved |
| GET | events/summary/ | 当前 firing 数量 {warning, critical, total} |

`firing_count` 通过 `AlertRuleSerializer` 的 `SerializerMethodField` 实时 COUNT 计算，
在规则列表中展示该规则当前有多少个活跃事件。

---

## 前端结构

`AlertsPage.jsx` 单文件，包含三个子组件：

- **AlertsPage**（主体）：汇总卡片行 + Tab 切换 + 条件渲染 `RulesTable` / `EventsTable` + `RuleModal`
- **RulesTable**：规则表格，操作列含测试/启停/编辑/删除四个按钮
- **EventsTable**：事件表格，含指标值/阈值/状态/触发时间/持续时长
- **RuleModal**：新建/编辑表单，rule_type=custom_sql 时额外展示 SQL textarea

`handleTest()` 调用 `POST /rules/{id}/test/` 后以浏览器 `alert()` 展示逐实例的指标值和是否触发，
用于规则配置调试，不产生任何 AlertEvent 记录。

事件状态过滤（告警中 / 已恢复 / 全部）通过 `?status=` 查询参数由后端过滤，不做前端本地过滤。

---

## 已知限制与后续方向

1. **无防抖**：指标轻微抖动会产生多条 firing/resolved 事件对，可后续在 AlertRule 增加 `consecutive_count` 字段实现连续 N 次超标才触发。
2. **通知仅 Webhook**：暂不支持邮件/短信，如需可在 `_send_webhook` 同级新增渠道函数。
3. **评估精度受采集频率制约**：如采集间隔为 10 分钟，则 `period=1` 的规则可能无数据；建议 `period >= collect_interval / 60`。
4. **固定 5 分钟评估周期**：如有高频告警需求可将 `EVAL_INTERVAL` 下调，但需权衡 ClickHouse 查询压力。
