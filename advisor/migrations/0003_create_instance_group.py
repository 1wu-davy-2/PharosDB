"""创建 InstanceGroup 模型。"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("collector", "0005_add_cluster_role"),
        ("advisor", "0002_seed_security_checks"),
    ]

    operations = [
        migrations.CreateModel(
            name="InstanceGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(db_index=True, max_length=128, unique=True, verbose_name="组名")),
                ("description", models.TextField(blank=True, default="", verbose_name="描述")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("instances", models.ManyToManyField(
                    blank=True, related_name="instance_groups",
                    to="collector.databaseinstance", verbose_name="实例",
                )),
            ],
            options={
                "verbose_name": "实例分组",
                "verbose_name_plural": "实例分组",
                "db_table": "advisor_instance_group",
                "ordering": ["name"],
            },
        ),
    ]
