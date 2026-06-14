"""安全巡检 (Advisor) 数据模型。

Checks 以 Python 表达式定义，支持两种模式:
  - EXISTS: 查询返回行 → 发现问题
  - THRESHOLD: 查询返回标量值 > threshold → 发现问题
"""

from django.db import models


class AdvisorCheck(models.Model):
    """巡检规则定义。"""

    FAMILY_CHOICES = [
        ("mysql", "MySQL / MariaDB"),
        ("postgresql", "PostgreSQL"),
        ("mongodb", "MongoDB"),
        ("generic", "通用"),
    ]
    SEVERITY_CHOICES = [
        ("critical", "严重"),
        ("error", "错误"),
        ("warning", "警告"),
        ("info", "提示"),
    ]
    MODE_CHOICES = [
        ("exists", "行存在即为问题"),
        ("threshold", "超过阈值即为问题"),
    ]
    INTERVAL_CHOICES = [
        ("standard", "标准 (24h)"),
        ("frequent", "高频 (4h)"),
        ("rare", "低频 (72h)"),
    ]

    # 基本信息
    name = models.CharField("规则名", max_length=128, unique=True, db_index=True)
    display_name = models.CharField("显示名称", max_length=256)
    summary = models.CharField("摘要", max_length=512)
    description = models.TextField("详细说明", blank=True, default="")

    # 分类
    family = models.CharField("数据库类型", max_length=20, choices=FAMILY_CHOICES, default="generic")
    category = models.CharField("巡检分类", max_length=64, default="security")
    severity = models.CharField("严重级别", max_length=20, choices=SEVERITY_CHOICES, default="warning")

    # 执行配置
    interval = models.CharField("执行频率", max_length=20, choices=INTERVAL_CHOICES, default="standard")
    mode = models.CharField("检查模式", max_length=20, choices=MODE_CHOICES, default="exists")
    query = models.TextField("巡检 SQL", help_text="SELECT 语句，placeholder {instance} 会被替换为实例名")
    threshold = models.FloatField("阈值 (仅 threshold 模式)", default=0)
    threshold_column = models.CharField("阈值列名", max_length=64, blank=True, default="value",
                                        help_text="threshold 模式下，取查询结果第一行此列的值与阈值比较")

    # 生命周期
    enabled = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "advisor_check"
        verbose_name = "巡检规则"
        verbose_name_plural = verbose_name
        ordering = ["category", "severity", "name"]

    def __str__(self):
        return self.display_name


class AdvisorFinding(models.Model):
    """巡检发现（每次执行的结果）。"""

    SEVERITY_CHOICES = AdvisorCheck.SEVERITY_CHOICES

    advisor_check = models.ForeignKey(
        AdvisorCheck, on_delete=models.CASCADE, related_name="findings",
        verbose_name="巡检规则",
    )
    instance = models.ForeignKey(
        "collector.DatabaseInstance", on_delete=models.CASCADE, related_name="advisor_findings",
        verbose_name="数据库实例",
    )

    severity = models.CharField("严重级别", max_length=20, choices=SEVERITY_CHOICES)
    summary = models.CharField("摘要", max_length=512)
    detail = models.TextField("详细描述", blank=True, default="")
    labels = models.JSONField("附加标签", default=dict, blank=True)

    found_at = models.DateTimeField("发现时间", auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField("修复时间", null=True, blank=True)

    class Meta:
        db_table = "advisor_finding"
        verbose_name = "巡检发现"
        verbose_name_plural = verbose_name
        ordering = ["-found_at"]
        indexes = [
            models.Index(fields=["advisor_check", "instance", "found_at"]),
            models.Index(fields=["instance", "resolved_at"]),
        ]

    def __str__(self):
        return f"{self.advisor_check.display_name} — {self.instance.name}"
