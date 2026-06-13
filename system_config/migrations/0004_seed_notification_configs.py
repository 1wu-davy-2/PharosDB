from django.db import migrations

NOTIFICATIONS = [
    # ── 邮箱 (SMTP) ──
    ("smtp_host",     "",         "str",  "notification",
     "SMTP 服务器", "SMTP 邮件服务器地址，例如 smtp.example.com", False),
    ("smtp_port",     "587",      "int",  "notification",
     "SMTP 端口", "SMTP 端口号，587(TLS) 或 465(SSL)", False),
    ("smtp_username", "",         "str",  "notification",
     "SMTP 用户名", "SMTP 登录用户名", False),
    ("smtp_password", "",         "str",  "notification",
     "SMTP 密码", "SMTP 登录密码", True),
    ("smtp_use_tls",  "true",     "bool", "notification",
     "启用 TLS", "是否使用 STARTTLS 加密", False),
    ("sender_email",  "",         "str",  "notification",
     "发件人邮箱", "告警邮件发送者邮箱地址", False),
    ("sender_name",   "PharosDB Alert", "str", "notification",
     "发件人名称", "告警邮件发送者显示名称", False),

    # ── Webhook ──
    ("webhook_url",      "",      "str",  "notification",
     "Webhook URL", "回调地址，支持钉钉/飞书/企微/自定义", False),
    ("webhook_secret",   "",      "str",  "notification",
     "Webhook 签名密钥", "HMAC 签名的 secret，留空不签名", True),
    ("webhook_enabled",  "false", "bool", "notification",
     "启用 Webhook", "是否向 webhook_url 发送告警通知", False),
]


def seed_notification_configs(apps, schema_editor):
    SystemConfig = apps.get_model("system_config", "SystemConfig")
    for key, val, vtype, cat, name, desc, secret in NOTIFICATIONS:
        SystemConfig.objects.get_or_create(
            key=key,
            defaults={
                "value": val,
                "value_type": vtype,
                "category": cat,
                "display_name": name,
                "description": desc,
                "editable": True,
                "is_secret": secret,
            },
        )


def unseed_notification_configs(apps, schema_editor):
    SystemConfig = apps.get_model("system_config", "SystemConfig")
    keys = [d[0] for d in NOTIFICATIONS]
    SystemConfig.objects.filter(key__in=keys).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("system_config", "0003_systemconfig_is_secret"),
    ]
    operations = [
        migrations.RunPython(seed_notification_configs, unseed_notification_configs),
    ]
