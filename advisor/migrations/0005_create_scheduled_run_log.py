"""创建 ScheduledRunLog 模型 — 定时巡检执行日志。"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("advisor", "0004_add_check_targeting_and_scheduling"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScheduledRunLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("instances_checked", models.IntegerField(default=0, verbose_name="检查实例数")),
                ("findings_created", models.IntegerField(default=0, verbose_name="新发现数")),
                ("started_at", models.DateTimeField(auto_now_add=True, verbose_name="开始时间")),
                ("finished_at", models.DateTimeField(blank=True, null=True, verbose_name="结束时间")),
                ("duration_ms", models.IntegerField(blank=True, null=True, verbose_name="耗时 (ms)")),
                ("status", models.CharField(
                    choices=[("success", "成功"), ("failed", "失败"), ("partial", "部分成功")],
                    default="success", max_length=16, verbose_name="状态",
                )),
                ("advisor_check", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="run_logs", to="advisor.advisorcheck",
                    verbose_name="巡检规则",
                )),
                ("instance_group", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="run_logs", to="advisor.instancegroup",
                    verbose_name="目标分组",
                )),
            ],
            options={
                "verbose_name": "调度执行日志",
                "verbose_name_plural": "调度执行日志",
                "db_table": "advisor_scheduled_run_log",
                "ordering": ["-started_at"],
            },
        ),
    ]
