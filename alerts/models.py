from django.db import models
from django.utils import timezone


class AlertRule(models.Model):
    RULE_TYPE_CHOICES = [
        ("slow_query_time", "慢查询耗时"),
        ("no_index_ratio",  "无索引比例"),
        ("query_count",     "查询总量"),
        ("custom_sql",      "自定义 SQL"),
    ]
    SEVERITY_CHOICES = [
        ("warning",  "警告"),
        ("critical", "严重"),
    ]

    name        = models.CharField("规则名称", max_length=128)
    rule_type   = models.CharField("规则类型", max_length=32, choices=RULE_TYPE_CHOICES)
    instance    = models.ForeignKey(
        "collector.DatabaseInstance",
        on_delete=models.CASCADE,
        null=True, blank=True,
        verbose_name="绑定实例",
        help_text="留空则对所有活跃实例生效",
    )
    threshold   = models.FloatField("阈值")
    period      = models.PositiveIntegerField("统计周期 (分钟)", default=5)
    severity    = models.CharField("严重级别", max_length=16, choices=SEVERITY_CHOICES, default="warning")
    webhook_url = models.CharField("Webhook URL", max_length=512, blank=True)
    custom_sql  = models.TextField(
        "自定义 SQL", blank=True,
        help_text="返回单个数值与阈值比较。可用占位符: %(service)s %(seconds)s",
    )
    is_enabled  = models.BooleanField("启用", default=True)
    description = models.TextField("描述", blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table     = "alert_rule"
        ordering     = ["-created_at"]
        verbose_name = "告警规则"
        verbose_name_plural = verbose_name

    def __str__(self):
        scope = self.instance.name if self.instance_id else "ALL"
        return f"[{self.get_severity_display()}] {self.name} @ {scope}"


class AlertEvent(models.Model):
    STATUS_CHOICES = [
        ("firing",   "告警中"),
        ("resolved", "已恢复"),
    ]

    rule         = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name="events")
    instance     = models.ForeignKey(
        "collector.DatabaseInstance",
        on_delete=models.SET_NULL, null=True,
        verbose_name="实例",
    )
    metric_value = models.FloatField("触发指标值")
    threshold    = models.FloatField("触发时阈值")
    status       = models.CharField("状态", max_length=16, choices=STATUS_CHOICES, default="firing")
    fired_at     = models.DateTimeField("触发时间", default=timezone.now)
    resolved_at  = models.DateTimeField("恢复时间", null=True, blank=True)
    notified     = models.BooleanField("已通知", default=False)
    notify_error = models.TextField("通知错误", blank=True)

    class Meta:
        db_table     = "alert_event"
        ordering     = ["-fired_at"]
        verbose_name = "告警事件"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=["rule", "instance", "status"]),
            models.Index(fields=["status", "fired_at"]),
        ]

    def __str__(self):
        return f"{self.rule.name} [{self.status}] {self.fired_at:%Y-%m-%d %H:%M}"

    @property
    def duration_seconds(self) -> int:
        end = self.resolved_at or timezone.now()
        return int((end - self.fired_at).total_seconds())
