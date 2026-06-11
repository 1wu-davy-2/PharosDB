"""
轻量内存调度器 — 无需 Redis/Celery。
每个实例按各自的 collect_interval 用 threading.Timer 链循环调度。
重启时由 AppConfig.ready() 从数据库恢复所有 active 实例的调度。
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)


class _InstanceScheduler:
    """单实例的定时采集调度器（Timer 链）。"""

    def __init__(self, instance_id: int, interval: int):
        self.instance_id = instance_id
        self.interval = interval
        self._timer: threading.Timer | None = None
        self._stopped = False
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            self._stopped = False
        self._schedule_next()
        logger.info(f"[scheduler] 实例 {self.instance_id} 启动定时采集，间隔 {self.interval}s")

    def stop(self):
        with self._lock:
            self._stopped = True
            if self._timer:
                self._timer.cancel()
                self._timer = None
        logger.info(f"[scheduler] 实例 {self.instance_id} 停止定时采集")

    def update_interval(self, new_interval: int):
        self.stop()
        self.interval = new_interval
        self._stopped = False
        self._schedule_next()
        logger.info(f"[scheduler] 实例 {self.instance_id} 采集间隔更新为 {new_interval}s")

    def _schedule_next(self):
        with self._lock:
            if self._stopped:
                return
            self._timer = threading.Timer(self.interval, self._run)
            self._timer.daemon = True
            self._timer.start()

    def _run(self):
        with self._lock:
            if self._stopped:
                return
        try:
            from .models import DatabaseInstance
            instance = DatabaseInstance.objects.get(id=self.instance_id)
            if not instance.is_active:
                return
            if instance.db_type != "mysql":
                # 暂不支持的类型静默跳过，不写失败历史
                logger.debug(f"[scheduler] 实例 {self.instance_id} ({instance.db_type}) 暂不支持，跳过")
                return
            from .tasks import _do_collect
            _do_collect(instance, triggered_by="scheduled")
        except Exception as e:
            logger.error(f"[scheduler] 实例 {self.instance_id} 采集异常: {e}")
        finally:
            self._schedule_next()


class SchedulerRegistry:
    """全局调度器注册表，维护所有实例的 _InstanceScheduler。"""

    def __init__(self):
        self._schedulers: dict[int, _InstanceScheduler] = {}
        self._lock = threading.Lock()

    def start_instance(self, instance_id: int, interval: int):
        with self._lock:
            if instance_id in self._schedulers:
                self._schedulers[instance_id].stop()
            sched = _InstanceScheduler(instance_id, interval)
            self._schedulers[instance_id] = sched
        sched.start()

    def stop_instance(self, instance_id: int):
        with self._lock:
            sched = self._schedulers.pop(instance_id, None)
        if sched:
            sched.stop()

    def update_instance(self, instance_id: int, interval: int, is_active: bool):
        if is_active:
            with self._lock:
                existing = self._schedulers.get(instance_id)
            if existing:
                if existing.interval != interval:
                    existing.update_interval(interval)
            else:
                self.start_instance(instance_id, interval)
        else:
            self.stop_instance(instance_id)

    def load_from_db(self):
        """Django 启动后从数据库恢复所有 active 实例的调度。"""
        try:
            from .models import DatabaseInstance
            instances = DatabaseInstance.objects.filter(is_active=True)
            for inst in instances:
                self.start_instance(inst.id, inst.collect_interval)
            logger.info(f"[scheduler] 从数据库恢复 {instances.count()} 个实例的调度")
        except Exception as e:
            logger.error(f"[scheduler] 恢复调度失败: {e}")

    def status(self) -> list[dict]:
        with self._lock:
            return [
                {"instance_id": iid, "interval": s.interval, "active": not s._stopped}
                for iid, s in self._schedulers.items()
            ]


# 全局单例
registry = SchedulerRegistry()
