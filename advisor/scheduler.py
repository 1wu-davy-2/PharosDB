"""
轻量内存调度器 — 定时巡检规则执行。

每个启用的 AdvisorCheck 由一个 _AdvisorScheduler 独立调度，
根据 check.interval 字段自动计算执行周期，无需 Redis/Celery。

重启时由 AdvisorConfig.ready() 从数据库恢复所有规则调度。
"""

import logging
import threading
import time

from django.utils import timezone as djangotz

logger = logging.getLogger(__name__)

# interval → 秒数
INTERVAL_MAP = {
    "standard": 24 * 3600,    # 24h
    "frequent": 4 * 3600,     # 4h
    "rare": 72 * 3600,        # 72h
}

# 首次运行延迟偏移（避免所有规则同时启动）
_INITIAL_JITTER_MAX = 120  # 最多分散在 2 分钟内


class _AdvisorScheduler:
    """单条巡检规则的定时调度器（Timer 链）。

    基于 interval + last_scheduled_run_at 计算下一轮延迟，
    消除执行耗时导致的漂移。
    """

    def __init__(self, check_id: int, interval_seconds: int):
        self.check_id = check_id
        self.interval = interval_seconds
        self._timer: threading.Timer | None = None
        self._stopped = False
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            self._stopped = False
        self._schedule_next()
        logger.info(f"[AdvisorScheduler] check {self.check_id} 启动调度, 间隔 {self.interval}s")

    def stop(self):
        with self._lock:
            self._stopped = True
            if self._timer:
                self._timer.cancel()
                self._timer = None
        logger.info(f"[AdvisorScheduler] check {self.check_id} 停止调度")

    def update_interval(self, new_interval: int):
        self.stop()
        self.interval = new_interval
        self._stopped = False
        self._schedule_next()
        logger.info(f"[AdvisorScheduler] check {self.check_id} 间隔更新为 {new_interval}s")

    def _schedule_next(self, *, run_start: float | None = None):
        with self._lock:
            if self._stopped:
                return

            if run_start is not None:
                elapsed = time.time() - run_start
                delay = self.interval - elapsed
                if delay < 0:
                    delay = 0.5
            else:
                # 计算距离上次执行过去了多久，决定首次延迟
                delay = self._calc_initial_delay()

            self._timer = threading.Timer(delay, self._run)
            self._timer.daemon = True
            self._timer.start()

    def _calc_initial_delay(self) -> float:
        """根据 last_scheduled_run_at 计算首次执行延迟。"""
        try:
            from .models import AdvisorCheck
            check = AdvisorCheck.objects.get(id=self.check_id)
            if check.last_scheduled_run_at:
                elapsed = (djangotz.now() - check.last_scheduled_run_at).total_seconds()
                if elapsed < 0:
                    elapsed = 0
                remaining = self.interval - elapsed
                return max(0.5, remaining)
            else:
                # 从未执行过 — 分散初始执行（避免所有规则同时启动）
                import random
                jitter = random.randint(5, _INITIAL_JITTER_MAX)
                return min(self.interval, jitter)
        except Exception:
            return self.interval

    def _run(self):
        with self._lock:
            if self._stopped:
                return
        run_start = time.time()
        try:
            from .models import AdvisorCheck
            from .runner import run_scheduled

            check = AdvisorCheck.objects.get(id=self.check_id)
            if not check.enabled:
                logger.debug(f"[AdvisorScheduler] check {self.check_id} 已禁用，跳过")
                return
            run_scheduled(check)
        except AdvisorCheck.DoesNotExist:
            logger.warning(f"[AdvisorScheduler] check {self.check_id} 不存在，停止调度")
            self.stop()
            return
        except Exception as e:
            logger.error(f"[AdvisorScheduler] check {self.check_id} 执行异常: {e}")
        finally:
            self._schedule_next(run_start=run_start)


class AdvisorSchedulerRegistry:
    """全局 Advisor 调度器注册表。"""

    def __init__(self):
        self._schedulers: dict[int, _AdvisorScheduler] = {}
        self._lock = threading.Lock()
        self._running = False

    @property
    def running(self):
        return self._running

    def start(self):
        """启动所有已启用规则的调度（从 DB 加载）。"""
        self._running = True
        self.load_from_db()
        logger.info("[AdvisorScheduler] 全局调度已启动")

    def stop(self):
        """停止所有调度。"""
        self._running = False
        with self._lock:
            for sched in list(self._schedulers.values()):
                sched.stop()
            self._schedulers.clear()
        logger.info("[AdvisorScheduler] 全局调度已停止")

    def start_check(self, check_id: int, interval: str):
        """启动单条规则的调度。"""
        seconds = INTERVAL_MAP.get(interval, INTERVAL_MAP["standard"])
        with self._lock:
            if check_id in self._schedulers:
                self._schedulers[check_id].stop()
            sched = _AdvisorScheduler(check_id, seconds)
            self._schedulers[check_id] = sched
        sched.start()

    def stop_check(self, check_id: int):
        """停止单条规则的调度。"""
        with self._lock:
            sched = self._schedulers.pop(check_id, None)
        if sched:
            sched.stop()

    def update_check(self, check_id: int, interval: str, enabled: bool):
        """根据规则状态更新调度：启用则加入，禁用则移除。"""
        if enabled and self._running:
            self.start_check(check_id, interval)
        else:
            self.stop_check(check_id)

    def load_from_db(self):
        """从数据库恢复所有启用规则的调度。"""
        try:
            from .models import AdvisorCheck
            checks = AdvisorCheck.objects.filter(enabled=True)
            for check in checks:
                self.start_check(check.id, check.interval)
            logger.info(f"[AdvisorScheduler] 从数据库恢复 {checks.count()} 条规则调度")
        except Exception as e:
            logger.error(f"[AdvisorScheduler] 恢复调度失败: {e}")

    def status(self) -> dict:
        """返回调度器当前状态。"""
        with self._lock:
            return {
                "running": self._running,
                "active_checks": len(self._schedulers),
                "checks": [
                    {"check_id": cid, "interval": s.interval, "active": not s._stopped}
                    for cid, s in self._schedulers.items()
                ],
            }


# ═══════════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════════

advisor_registry = AdvisorSchedulerRegistry()
