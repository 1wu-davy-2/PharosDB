"""安全巡检 (Advisor) 数据模型。

Checks 以 Python 表达式定义，支持两种模式:
  - EXISTS: 查询返回行 → 发现问题
  - THRESHOLD: 查询返回标量值 > threshold → 发现问题
"""

from django.db import models


class InstanceGroup(models.Model):
    """实例分组 — 将数据库实例组织到命名组中以供巡检规则定向。"""

    name = models.CharField("组名", max_length=128, unique=True, db_index=True)
    description = models.TextField("描述", blank=True, default="")
    instances = models.ManyToManyField(
        "collector.DatabaseInstance",
        related_name="instance_groups",
        verbose_name="实例",
        blank=True,
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "advisor_instance_group"
        verbose_name = "实例分组"
        verbose_name_plural = verbose_name
        ordering = ["name"]

    def __str__(self):
        return self.name


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

    # 定向分组 (空 = 全部实例, 向后兼容)
    target_groups = models.ManyToManyField(
        InstanceGroup,
        related_name="checks",
        verbose_name="目标分组",
        blank=True,
        help_text="空 = 全部实例（向后兼容）",
    )
    last_scheduled_run_at = models.DateTimeField(
        "上次定时执行时间",
        null=True, blank=True, default=None,
    )

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


class ScheduledRunLog(models.Model):
    """调度执行日志 — 记录每次定时巡检执行。"""

    STATUS_CHOICES = [
        ("success", "成功"),
        ("failed", "失败"),
        ("partial", "部分成功"),
    ]

    advisor_check = models.ForeignKey(
        AdvisorCheck, on_delete=models.CASCADE, related_name="run_logs",
        verbose_name="巡检规则",
    )
    instance_group = models.ForeignKey(
        InstanceGroup, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="run_logs", verbose_name="目标分组",
    )
    instances_checked = models.IntegerField("检查实例数", default=0)
    findings_created = models.IntegerField("新发现数", default=0)
    started_at = models.DateTimeField("开始时间", auto_now_add=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    duration_ms = models.IntegerField("耗时 (ms)", null=True, blank=True)
    status = models.CharField(
        "状态", max_length=16,
        choices=STATUS_CHOICES, default="success",
    )

    class Meta:
        db_table = "advisor_scheduled_run_log"
        verbose_name = "调度执行日志"
        verbose_name_plural = verbose_name
        ordering = ["-started_at"]

    def __str__(self):
        group_name = self.instance_group.name if self.instance_group else "全部"
        return f"{self.advisor_check.display_name} → {group_name} ({self.status})"
