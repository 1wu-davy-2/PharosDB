from django.db import migrations

DEFAULTS = [
    ("top_n_explain",    "5",  "int",    "collection",
     "自动 EXPLAIN Top-N", "每个采集周期对耗时降序前 N 条慢查询自动执行 EXPLAIN"),
    ("explain_timeout",  "3",  "int",    "collection",
     "EXPLAIN 超时 (秒)", "单次 EXPLAIN 最大允许的执行时间"),
    ("lock_poll_interval",       "5",   "int", "collection",
     "锁采集高频间隔 (秒)", "检测到锁等待时，锁采集器加速轮询的间隔"),
    ("lock_idle_interval",       "30",  "int", "collection",
     "锁采集空闲间隔 (秒)", "无锁等待时锁采集器的正常轮询间隔"),
    ("alert_eval_interval",      "300", "int", "alerting",
     "告警评估间隔 (秒)", "告警规则检查的调度周期"),
    ("index_usage_retention",    "7",   "int", "retention",
     "索引使用数据保留天数", "ClickHouse 中 index_usage 表的数据 TTL"),
    ("metrics_retention_days",   "30",  "int", "retention",
     "指标数据保留天数", "ClickHouse 中 metrics 表的 PARTITION 保留天数"),
]


def seed_configs(apps, schema_editor):
    SystemConfig = apps.get_model("system_config", "SystemConfig")
    for key, val, vtype, cat, name, desc in DEFAULTS:
        SystemConfig.objects.get_or_create(
            key=key,
            defaults={
                "value": val,
                "value_type": vtype,
                "category": cat,
                "display_name": name,
                "description": desc,
                "editable": True,
            },
        )


def unseed_configs(apps, schema_editor):
    SystemConfig = apps.get_model("system_config", "SystemConfig")
    keys = [d[0] for d in DEFAULTS]
    SystemConfig.objects.filter(key__in=keys).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("system_config", "0001_initial"),
    ]
    operations = [
        migrations.RunPython(seed_configs, unseed_configs),
    ]
