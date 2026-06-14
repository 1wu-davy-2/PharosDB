import logging
import os
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AdvisorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "advisor"
    verbose_name = "安全巡检"

    def ready(self):
        # 只在工作进程（RUN_MAIN=true）或生产进程（无 runserver）里启动调度器
        if os.environ.get("RUN_MAIN") == "true" or "runserver" not in sys.argv:
            self._boot()

    def _boot(self):
        """从 DB 恢复 Advisor 调度器，跳过表不存在的情况（首次 migrate 前）。"""
        try:
            from django.db import connection
            if "advisor_check" not in connection.introspection.table_names():
                logger.info("[advisor boot] advisor_check 表不存在，跳过调度器恢复")
                return
        except Exception as e:
            logger.error(f"[advisor boot] 检查数据库表失败: {e}")
            return

        from .scheduler import advisor_registry
        advisor_registry.start()
