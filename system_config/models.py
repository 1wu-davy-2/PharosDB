"""全局系统配置 — 简单的 key-value 存储，用于管理采集/告警等各项参数。"""

from django.db import models


class SystemConfig(models.Model):
    """全局配置项，单一来源 (single source of truth) 管理系统运行时参数。

    key 唯一；value 统一存为文本，业务层自行转换类型。
    """

    VALUE_TYPE_CHOICES = [
        ("int", "整数"),
        ("float", "浮点数"),
        ("str", "字符串"),
        ("bool", "布尔值"),
        ("json", "JSON"),
    ]

    key = models.CharField("配置键", max_length=128, unique=True, db_index=True)
    value = models.TextField("配置值")
    value_type = models.CharField(
        "值类型", max_length=16, choices=VALUE_TYPE_CHOICES, default="str",
    )
    description = models.TextField("说明", blank=True, default="")
    category = models.CharField("分类", max_length=64, default="general")
    display_name = models.CharField("显示名称", max_length=128, blank=True, default="")
    editable = models.BooleanField("允许前端修改", default=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "system_config"
        verbose_name = "全局配置"
        verbose_name_plural = verbose_name
        ordering = ["category", "key"]

    def __str__(self):
        return f"{self.key} = {self.value}"

    @classmethod
    def get_value(cls, key, default=None):
        """类方法：按 key 读取值（自动转换类型）。"""
        try:
            cfg = cls.objects.get(key=key)
            return cfg.to_typed()
        except cls.DoesNotExist:
            return default

    def to_typed(self):
        """将存储的字符串值按 value_type 转为对应 Python 类型。"""
        try:
            if self.value_type == "int":
                return int(self.value)
            elif self.value_type == "float":
                return float(self.value)
            elif self.value_type == "bool":
                return self.value.lower() in ("true", "1", "yes")
            elif self.value_type == "json":
                import json as _json
                return _json.loads(self.value)
            return self.value
        except (ValueError, TypeError):
            return self.value
