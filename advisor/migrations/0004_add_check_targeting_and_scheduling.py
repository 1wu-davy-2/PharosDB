"""AdvisorCheck 增加 target_groups M2M 和 last_scheduled_run_at 字段。"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("advisor", "0003_create_instance_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="advisorcheck",
            name="last_scheduled_run_at",
            field=models.DateTimeField(
                blank=True, default=None, null=True,
                verbose_name="上次定时执行时间",
            ),
        ),
        migrations.AddField(
            model_name="advisorcheck",
            name="target_groups",
            field=models.ManyToManyField(
                blank=True,
                related_name="checks",
                to="advisor.instancegroup",
                verbose_name="目标分组",
                help_text="空 = 全部实例（向后兼容）",
            ),
        ),
    ]
