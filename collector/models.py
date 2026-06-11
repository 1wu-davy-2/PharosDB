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

    name = models.CharField("名称", max_length=128)
    db_type = models.CharField("数据库类型", max_length=20, choices=DB_TYPE_CHOICES, default="mysql")
    host = models.CharField("主机地址", max_length=255)
    port = models.PositiveIntegerField("端口", default=3306)
    username = models.CharField("用户名", max_length=128)
    password = models.TextField("密码 (加密存储)")
    environment = models.CharField("环境", max_length=32, choices=ENV_CHOICES, default="prod")
    cluster = models.CharField("集群", max_length=128, blank=True, default="")
    is_active = models.BooleanField("启用采集", default=True)
    collect_interval = models.PositiveIntegerField("采集间隔 (秒)", default=60)
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
