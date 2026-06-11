import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CollectorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "collector"
    verbose_name = "采集器"

    def ready(self):
        from django.db.models.signals import post_migrate
        from django.dispatch import receiver

        from .signals import connect_signals
        connect_signals()

        @receiver(post_migrate, sender=self, weak=False)
        def on_migrate(sender, **kwargs):
            pass  # migrate 完成后不自动启动，由进程启动时 _boot 负责

        self._boot()

    def _boot(self):
        """从 DB 恢复调度器，跳过表不存在的情况（首次 migrate 前）。"""
        try:
            from django.db import connection
            tables = connection.introspection.table_names()
            if "collector_database_instance" not in tables:
                return
        except Exception:
            return

        from .scheduler import registry
        registry.load_from_db()
