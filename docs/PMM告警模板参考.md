# PMM 内置告警模板完整参考

> 来源：PMM `managed/data/alerting-templates/*.yml`，共 42 个模板
> 用途：PharosDB 告警中心设计的蓝图参考

---

## 模板格式

```yaml
templates:
  - name: pmm_<name>        # 必须 pmm_ 前缀
    version: 1               # 必须为 1
    summary: <描述>
    expr: |                  # MetricsQL/PromQL 表达式
      <expression>
    params:                  # 可选参数
      - name: <param>
        summary: <说明>
        unit: "%"
        type: float
        range: [0, 100]
        value: <默认值>
    for: 5m                  # 持续时长
    severity: warning        # warning / critical / error
    annotations:
      summary: <告警标题>
      description: <告警详情>
```

- `[[ .param_name ]]` = Go 模板占位符（编译时替换）
- `{{ $labels.field }}` = Prometheus 标签值（运行时替换）
- `{{ $value }}` = 告警表达式的当前值

---

## 一、MySQL（5 个）

### 1. mysql_down — MySQL 宕机
```
Severity: critical    For: 1m
Expr:   mysql_up == 0 AND agent_type="mysqld_exporter" AND disabled="0"
```

### 2. mysql_too_many_connections — 连接数过高
```
Severity: warning     For: 5m
Param:   threshold=80 (%)
Expr:   max_over_time(Threads_connected[5m]) / max_connections * 100 > threshold
```

### 3. mysql_restarted — 实例重启
```
Severity: warning     For: 1m
Param:   threshold=300 (s)
Expr:   mysql_global_status_uptime < threshold
```

### 4. mysql_replication_io_running — 主从 IO 线程中断
```
Severity: critical    For: 1m
Expr:   replica_io_running == 0 OR slave_io_running == 0 (兼容 5.7/8.0)
```

### 5. mysql_replication_sql_running — 主从 SQL 线程中断
```
Severity: critical    For: 1m
Expr:   replica_sql_running == 0 OR slave_sql_running == 0 (兼容 5.7/8.0)
```

---

## 二、PostgreSQL（11 个）

### 6. postgresql_down — PostgreSQL 宕机
```
Severity: critical    For: 1m
Expr:   pg_up == 0 AND agent_type="postgres_exporter" AND disabled="0"
```

### 7. postgresql_too_many_connections — 连接数过高
```
Severity: warning     For: 5m
Param:   threshold=80 (%)
Expr:   pg_stat_activity_count / pg_settings_max_connections * 100 > threshold
```

### 8. postgresql_restarted — 实例重启
```
Severity: warning     For: 1m
Param:   threshold=300 (s)
Expr:   pg_postmaster_uptime_seconds < threshold
```

### 9. postgresql_high_statement_timeouts — 语句超时过高
```
Severity: critical    For: 1m
Expr:   rate(postgresql_errors_total{type="statement_timeout"}[1m]) > 3
```

### 10. postgresql_high_transaction_rollbacks — 事务回滚率过高
```
Severity: warning     For: 1s
Expr:   rollback_rate = rate(rollback[3m]) / (rate(rollback[3m]) + rate(commit[3m])) > 0.10
```

### 11. postgresql_high_index_bloat — 索引膨胀
```
Severity: warning     For: 1h
Expr:   pg_bloat_btree_bloat_pct > 60 AND real_size > 100MB
Note:   建议 REINDEX INDEX CONCURRENTLY <idxname>
```

### 12. postgresql_high_table_bloat — 表膨胀
```
Severity: warning     For: 1h
Expr:   pg_bloat_table_bloat_pct > 70 AND real_size > 200MB
Note:   建议 VACUUM <relname>
```

### 13. postgresql_high_number_dead_tuples — 死元组过多
```
Severity: warning     For: 2m
Expr:   n_dead_tup > 10000 AND dead_ratio >= 0.10
```

### 14. postgresql_not_autoanalyzed — 长时间未自动分析
```
Severity: warning     For: 1h
Expr:   last_autoanalyze > 0 AND (now - last_autoanalyze) > 10 days
```

### 15. postgresql_not_autovacuumed — 长时间未自动 Vacuum
```
Severity: warning     For: 1h
Expr:   last_autovacuum > 0 AND (now - last_autovacuum) > 10 days
```

### 16. postgresql_unused_replication_slots — 未使用的复制槽
```
Severity: warning     For: 1m
Expr:   pg_replication_slots_active == 0
```

---

## 三、MongoDB（19 个）

### 17. mongodb_down — MongoDB 宕机
```
Severity: critical    For: 1m
Expr:   mongodb_up == 0 AND agent_type="mongodb_exporter" AND disabled="0"
```

### 18. mongodb_restarted — 实例重启
```
Severity: warning     For: 1m
Param:   threshold=300 (s)
Expr:   mongodb_instance_uptime_seconds < threshold
```

### 19. mongodb_cve_2025_14847_zlib — CVE-2025-14847 漏洞
```
Severity: critical    For: 5m
Expr:   匹配弱势版本 (3.6~8.2 特定范围) + zlib 压缩活跃 (24h 内增长)
```

### 20. mongodb_dbpath_disk_space — 数据盘空间不足
```
Severity: critical    For: 5m
Param:   threshold=85 (%)
Expr:   fsUsedSize / fsTotalSize * 100 > threshold
```

### 21. mongodb_host_ssl_cert_expiry — SSL 证书即将过期
```
Severity: warning     For: 5m
Param:   threshold=30 (days)
Expr:   (expiry_date - current_date) < threshold
```

### 22. mongodb_oplog_window — Oplog 窗口不足
```
Severity: warning     For: 5m
Param:   threshold=24 (hours)
Expr:   (head_timestamp - tail_timestamp) / 3600 < threshold
```

### 23. mongodb_replication_lag — 复制延迟过高
```
Severity: warning     For: 1m
Param:   threshold=600 (s)
Expr:   max(replication_lag[1m]) > threshold (仅 SECONDARY)
```

### 24. mongodb_replset_no_primary — 副本集无主节点
```
Severity: critical    For: 1m
Expr:   avg(isWritablePrimary) == 0
```

### 25. mongodb_replset_primary_changed — 主节点切换
```
Severity: warning     For: 1m
Expr:   changes(my_state[10m]) > 0
```

### 26. mongodb_unusual_state — 成员异常状态
```
Severity: critical    For: 1m
Expr:   rs_members_state NOT IN (1=PRIMARY,2=SECONDARY,7=ARBITER,8=OTHER)
```

### 27. mongodb_read_tickets — 读票据不足
```
Severity: warning     For: 1m
Param:   threshold=50
Expr:   wiredtiger_concurrent_transactions_available_tickets{txn_rw="read"} < threshold
```

### 28. mongodb_write_tickets — 写票据不足
```
Severity: warning     For: 1m
Param:   threshold=50
Expr:   wiredtiger_concurrent_transactions_available_tickets{txn_rw="write"} < threshold
```

### 29. mongodb_too_many_chunk_migrations — 分片迁移过多
```
Severity: critical    For: 1m
Param:   threshold=40
Expr:   max(moveChunk.start 10min) > threshold
```

### PBM 子组（6 个）

### 30. mongodb_pbm_agent_down — PBM Agent 宕机
```
Severity: critical    For: 1m
Expr:   avg(pbm_agent_status{role=~"P|S|H",self="1"}) > 0 (反逻辑: 存在即告警消失)
```

### 31. mongodb_pbm_backup_failed — PBM 备份失败
```
Severity: warning     For: 1m
Expr:   count(pbm_backup_size_bytes{status="error"}) > 0
```

### 32. mongodb_pbm_backup_duration — 备份耗时过长
```
Severity: warning     For: 5m
Param:   threshold=3600 (s)
Expr:   max(pbm_backup_duration_seconds{status="done"}) > threshold
```

### 33. mongodb_pbm_backup_size — 备份体积过大
```
Severity: warning     For: 5m
Param:   threshold=1 (GiB)
Expr:   max(pbm_backup_size_bytes{status="done"}) / 1GiB > threshold
```

### 34. mongodb_pbm_backup_stale — 备份过期
```
Severity: critical    For: 1m
Param:   threshold=86400 (s, 24h)
Expr:   now - max(pbm_backup_last_transition_ts{status="done"}) > threshold
```

---

## 四、Node/OS（3 个）

### 35. node_high_cpu_load — CPU 负载过高
```
Severity: warning     For: 5m
Param:   threshold=80 (%)
Expr:   (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))) * 100 > threshold
```

### 36. node_low_free_memory — 内存不足
```
Severity: warning     For: 5m
Param:   threshold=20 (%)
Expr:   MemAvailable / MemTotal * 100 < threshold
```

### 37. node_swap_filled_up — Swap 使用过高
```
Severity: warning     For: 5m
Param:   threshold=80 (%)
Expr:   (1 - SwapFree / SwapTotal) * 100 > threshold
```

---

## 五、ProxySQL（1 个）

### 38. proxysql_server_status — ProxySQL 节点离线
```
Severity: warning     For: 5m
Param:   status=4 (3=OFFLINE_SOFT, 4=OFFLINE_HARD)
Expr:   proxysql_runtime_servers_status >= status
```

---

## 六、Redis/Valkey（2 个）

### 39. redis_down — Redis 宕机
```
Severity: critical    For: 1m
Expr:   redis_up == 0 AND agent_type="valkey_exporter" AND disabled="0"
```

### 40. valkey_down — Valkey 宕机
```
Severity: critical    For: 1m
Expr:   redis_up == 0 AND agent_type="valkey_exporter" AND disabled="0"
```

---

## 七、PMM Agent（1 个）

### 41. pmm_agent_down — PMM Agent 失联
```
Severity: critical    For: 1m
Expr:   pmm_managed_inventory_agents{agent_type="pmm-agent"} == 0
```

---

## 八、PMM Managed Backup（1 个）

### 42. backup_error — 托管备份失败
```
Severity: error       For: 1m
Expr:   pmm_managed_backups_artifacts{status="error"} == 1
```

---

## 统计

| 维度 | 数据 |
|------|------|
| 模板总数 | 42 |
| critical | 14 |
| warning | 27 |
| error | 1 |
| 含可配置参数 | 19 |
| 无参数（硬编码） | 23 |
| 表达式使用 PromQL/MetricsQL | 全部 |

### 按数据库分类

| 类别 | 数量 |
|------|------|
| MongoDB（含 PBM） | 19 |
| PostgreSQL | 11 |
| MySQL | 5 |
| Node/OS | 3 |
| Redis/Valkey | 2 |
| ProxySQL | 1 |
| PMM Agent | 1 |
| PMM Backup | 1 |

---

## 对 PharosDB 告警中心的启示

PMM 的模板体系揭示了告警模板的核心结构：

1. **表达式引擎**：PromQL / MetricsQL，PharosDB 也可以选择 ClickHouse SQL 或 PromQL
2. **参数化**：`[[ .param ]]` 双括号占位符，用户创建规则时填入实际值
3. **两级模板**：编译时参数替换 + 运行时标签替换
4. **for 持续时间**：避免瞬时抖动误报
5. **severity 分级**：warning / critical / error
6. **annotations**：summary（短标题）+ description（长描述，可含修复建议）

PharosDB 可直接复用这 42 个模板的**表达式逻辑**和**阈值默认值**，只需将 PromQL 表达式翻译为 ClickHouse SQL / PharosDB 内部规约即可。
