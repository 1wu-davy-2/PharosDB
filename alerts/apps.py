import logging
import os
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)

_eval_timer: threading.Timer | None = None
EVAL_INTERVAL = 300  # 5 分钟


def _schedule_evaluation():
    global _eval_timer

    def _run():
        try:
            from .evaluator import evaluate_all_rules
            result = evaluate_all_rules()
            logger.debug(f"[alerts] 规则评估完成: {result}")
        except Exception as e:
            logger.error(f"[alerts] 规则评估异常: {e}")
        finally:
            _schedule_evaluation()

    _eval_timer = threading.Timer(EVAL_INTERVAL, _run)
    _eval_timer.daemon = True
    _eval_timer.start()


class AlertsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "alerts"
    verbose_name = "告警中心"

    def ready(self):
        if os.environ.get("RUN_MAIN") == "true" or "runserver" not in __import__("sys").argv:
            self._boot()

    def _boot(self):
        try:
            from django.db import connection
            if "alert_rule" not in connection.introspection.table_names():
                return
        except Exception:
            return
        _schedule_evaluation()
        logger.info(f"[alerts] 告警评估器已启动，间隔 {EVAL_INTERVAL}s")
