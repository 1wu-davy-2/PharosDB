import logging
import os

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CollectorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "collector"
    verbose_name = "采集器"

    def ready(self):
        from .signals import connect_signals
        connect_signals()

        # Django dev server 的 StatReloader 会启动两个进程：
        # 外层 watcher 进程设置 RUN_MAIN=true 再 spawn 实际工作进程。
        # 只在工作进程（RUN_MAIN=true）或生产进程（无该变量）里启动调度器。
        if os.environ.get("RUN_MAIN") == "true" or not self._is_dev_server():
            self._boot()

    def _is_dev_server(self):
        import sys
        return "runserver" in sys.argv

    def _boot(self):
        """从 DB 恢复调度器，跳过表不存在的情况（首次 migrate 前）。"""
        try:
            from django.db import connection
            if "collector_database_instance" not in connection.introspection.table_names():
                return
        except Exception:
            return

        from .scheduler import lock_registry, registry
        registry.load_from_db()
        lock_registry.load_from_db()
