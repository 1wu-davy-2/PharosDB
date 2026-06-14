from django.db import models


class DatabaseInstance(models.Model):
    """被监控数据库实例的连接信息。"""

    DB_TYPE_CHOICES = [
        ("mysql", "MySQL"),
        ("postgresql", "PostgreSQL"),
        ("mongodb", "MongoDB"),
    ]
    ENV_CHOICES = [
        ("prod", "Production"),
        ("staging", "Staging"),
        ("dev", "Development"),
    ]
    CONNECTION_STATUS_CHOICES = [
        ("connected", "Connected"),
        ("disconnected", "Disconnected"),
    ]

    name = models.CharField("名称", max_length=128)
    db_type = models.CharField("数据库类型", max_length=20, choices=DB_TYPE_CHOICES, default="mysql")
    host = models.CharField("主机地址", max_length=255)
    port = models.PositiveIntegerField("端口", default=3306)
    username = models.CharField("用户名", max_length=128)
    password = models.TextField("密码 (加密存储)")
    environment = models.CharField("环境", max_length=32, choices=ENV_CHOICES, default="prod")
    cluster = models.CharField("集群", max_length=128, blank=True, default="")
    cluster_role = models.CharField(
        "集群角色", max_length=20,
        choices=[("primary", "Primary"), ("replica", "Replica"),
                 ("shard", "Shard"), ("standalone", "Standalone")],
        default="standalone",
    )
    is_active = models.BooleanField("启用采集", default=True)
    collect_interval = models.PositiveIntegerField("采集间隔 (秒)", default=60)
    db_version = models.CharField("数据库版本", max_length=64, blank=True, default="")
    connection_status = models.CharField(
        "连接状态", max_length=16, choices=CONNECTION_STATUS_CHOICES, default="disconnected",
    )
    last_error = models.TextField("最近错误", blank=True, default="")
    last_collected_at = models.DateTimeField("上次采集时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "collector_database_instance"
        ordering = ["-created_at"]
        verbose_name = "数据库实例"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.name} ({self.db_type}://{self.host}:{self.port})"


class CollectionHistory(models.Model):
    """每次采集的执行记录。"""

    TRIGGER_CHOICES = [
        ("scheduled", "定时"),
        ("manual", "手动"),
    ]
    STATUS_CHOICES = [
        ("success", "成功"),
        ("failed", "失败"),
        ("partial", "部分成功"),
    ]

    instance = models.ForeignKey(
        DatabaseInstance,
        on_delete=models.CASCADE,
        related_name="collection_histories",
        verbose_name="实例",
    )
    triggered_by = models.CharField("触发方式", max_length=16, choices=TRIGGER_CHOICES, default="scheduled")
    status = models.CharField("状态", max_length=16, choices=STATUS_CHOICES, default="success")
    started_at = models.DateTimeField("开始时间")
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    duration_ms = models.IntegerField("耗时 (ms)", null=True, blank=True)
    queries_collected = models.IntegerField("采集查询数", default=0)
    rows_written = models.IntegerField("写入行数", default=0)
    error_message = models.TextField("错误信息", blank=True, default="")

    class Meta:
        db_table = "collector_collection_history"
        ordering = ["-started_at"]
        verbose_name = "采集历史"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.instance.name} {self.started_at:%Y-%m-%d %H:%M:%S} [{self.status}]"
