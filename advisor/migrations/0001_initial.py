import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("collector", "0005_add_cluster_role"),
    ]

    operations = [
        migrations.CreateModel(
            name="AdvisorCheck",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(db_index=True, max_length=128, unique=True, verbose_name="规则名")),
                ("display_name", models.CharField(max_length=256, verbose_name="显示名称")),
                ("summary", models.CharField(max_length=512, verbose_name="摘要")),
                ("description", models.TextField(blank=True, default="", verbose_name="详细说明")),
                ("family", models.CharField(choices=[("mysql", "MySQL / MariaDB"), ("postgresql", "PostgreSQL"), ("mongodb", "MongoDB"), ("generic", "通用")], default="generic", max_length=20, verbose_name="数据库类型")),
                ("category", models.CharField(default="security", max_length=64, verbose_name="巡检分类")),
                ("severity", models.CharField(choices=[("critical", "严重"), ("error", "错误"), ("warning", "警告"), ("info", "提示")], default="warning", max_length=20, verbose_name="严重级别")),
                ("interval", models.CharField(choices=[("standard", "标准 (24h)"), ("frequent", "高频 (4h)"), ("rare", "低频 (72h)")], default="standard", max_length=20, verbose_name="执行频率")),
                ("mode", models.CharField(choices=[("exists", "行存在即为问题"), ("threshold", "超过阈值即为问题")], default="exists", max_length=20, verbose_name="检查模式")),
                ("query", models.TextField(help_text="SELECT 语句", verbose_name="巡检 SQL")),
                ("threshold", models.FloatField(default=0, verbose_name="阈值 (仅 threshold 模式)")),
                ("threshold_column", models.CharField(blank=True, default="value", max_length=64, verbose_name="阈值列名")),
                ("enabled", models.BooleanField(default=True, verbose_name="启用")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
            ],
            options={
                "verbose_name": "巡检规则",
                "verbose_name_plural": "巡检规则",
                "db_table": "advisor_check",
                "ordering": ["category", "severity", "name"],
            },
        ),
        migrations.CreateModel(
            name="AdvisorFinding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("severity", models.CharField(choices=[("critical", "严重"), ("error", "错误"), ("warning", "警告"), ("info", "提示")], max_length=20, verbose_name="严重级别")),
                ("summary", models.CharField(max_length=512, verbose_name="摘要")),
                ("detail", models.TextField(blank=True, default="", verbose_name="详细描述")),
                ("labels", models.JSONField(blank=True, default=dict, verbose_name="附加标签")),
                ("found_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="发现时间")),
                ("resolved_at", models.DateTimeField(blank=True, null=True, verbose_name="修复时间")),
                ("advisor_check", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="findings", to="advisor.advisorcheck", verbose_name="巡检规则")),
                ("instance", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="advisor_findings", to="collector.databaseinstance", verbose_name="数据库实例")),
            ],
            options={
                "verbose_name": "巡检发现",
                "verbose_name_plural": "巡检发现",
                "db_table": "advisor_finding",
                "ordering": ["-found_at"],
            },
        ),
        migrations.AddIndex(
            model_name="advisorfinding",
            index=models.Index(fields=["advisor_check", "instance", "found_at"], name="advisor_find_check_ins_idx"),
        ),
        migrations.AddIndex(
            model_name="advisorfinding",
            index=models.Index(fields=["instance", "resolved_at"], name="advisor_find_inst_res_idx"),
        ),
    ]
