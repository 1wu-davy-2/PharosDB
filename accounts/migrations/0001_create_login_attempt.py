"""Create LoginAttempt model for brute-force login protection."""

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="LoginAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(db_index=True, max_length=150, verbose_name="用户名")),
                ("ip_address", models.CharField(default="0.0.0.0", max_length=64, verbose_name="客户端 IP")),
                ("success", models.BooleanField(default=False, verbose_name="是否成功")),
                ("attempted_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="尝试时间")),
            ],
            options={
                "verbose_name": "登录尝试记录",
                "verbose_name_plural": "登录尝试记录",
                "db_table": "accounts_login_attempt",
                "ordering": ["-attempted_at"],
            },
        ),
    ]
