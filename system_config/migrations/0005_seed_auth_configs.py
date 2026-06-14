"""Seed auth-related system configs (login lockout)."""

from django.db import migrations

DEFAULTS = [
    ("auth_max_login_attempts", "5", "int", "security",
     "最大登录失败次数", "同一用户名+IP 在时间窗口内连续失败超过此次数将被锁定"),
    ("auth_login_lockout_minutes", "15", "int", "security",
     "登录锁定时间 (分钟)", "被锁定后等待多少分钟才能再次尝试登录"),
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
        ("system_config", "0004_seed_notification_configs"),
    ]
    operations = [
        migrations.RunPython(seed_configs, unseed_configs),
    ]
