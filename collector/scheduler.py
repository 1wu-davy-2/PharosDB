"""
轻量内存调度器 — 无需 Redis/Celery。

三个队列：
  1. SchedulerRegistry     — 采集队列（连接正常，is_active=True）
  2. LockSchedulerRegistry — 锁快照队列（仅 MySQL 连接正常实例）
  3. DeadQueueRegistry     — 死亡队列（连接失败，5min 重试，成功后移交采集队列）

重启时由 AppConfig.ready() 从数据库恢复所有实例的调度。
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 采集调度器（单实例）
# ═══════════════════════════════════════════════════════════════

class _InstanceScheduler:
    """单实例的定时采集调度器（Timer 链）。

    基于 _run() 启动时间计算下一轮延迟，消除采集耗时导致的秒级漂移。
    """

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
                delay = self.interval
            self._timer = threading.Timer(delay, self._run)
            self._timer.daemon = True
            self._timer.start()

    def _run(self):
        with self._lock:
            if self._stopped:
                return
        run_start = time.time()
        try:
            from .models import DatabaseInstance
            instance = DatabaseInstance.objects.get(id=self.instance_id)
            if not instance.is_active:
                return
            if instance.connection_status != "connected":
                logger.info(f"[scheduler] 实例 {self.instance_id} 连接断开，转入死亡队列")
                dead_registry.start_instance(self.instance_id)
                self.stop()
                return
            if instance.db_type not in ("mysql", "postgresql"):
                logger.debug(f"[scheduler] 实例 {self.instance_id} ({instance.db_type}) 暂不支持，跳过")
                return
            from .tasks import _do_collect
            _do_collect(instance, triggered_by="scheduled")
        except Exception as e:
            logger.error(f"[scheduler] 实例 {self.instance_id} 采集异常: {e}")
        finally:
            self._schedule_next(run_start=run_start)


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

    def update_instance(self, instance_id: int, interval: int, is_active: bool, connection_status: str = "connected"):
        """根据实例状态决定放入哪个队列。

        - connected + active → 采集队列
        - disconnected       → 死亡队列
        - inactive           → 不调度
        """
        if connection_status == "disconnected":
            self.stop_instance(instance_id)
            dead_registry.start_instance(instance_id)
            return

        if is_active:
            dead_registry.stop_instance(instance_id)
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
            # connected + active → 采集队列
            connected = DatabaseInstance.objects.filter(is_active=True, connection_status="connected")
            for inst in connected:
                self.start_instance(inst.id, inst.collect_interval)
            logger.info(f"[scheduler] 从数据库恢复 {connected.count()} 个实例的采集调度")

            # disconnected → 死亡队列
            disconnected = DatabaseInstance.objects.filter(connection_status="disconnected")
            for inst in disconnected:
                dead_registry.start_instance(inst.id)
            logger.info(f"[scheduler] 死亡队列恢复 {disconnected.count()} 个实例")
        except Exception as e:
            logger.error(f"[scheduler] 恢复调度失败: {e}")

    def status(self) -> list[dict]:
        with self._lock:
            return [
                {"instance_id": iid, "interval": s.interval, "active": not s._stopped}
                for iid, s in self._schedulers.items()
            ]


# ═══════════════════════════════════════════════════════════════
# 锁快照调度器（单实例）
# ═══════════════════════════════════════════════════════════════

class LockScheduler:
    """单实例的锁快照自适应调度器。

    无锁时 30s 轮询；检测到锁时自动切到 5s；锁清除后回到 30s。
    基于 _run() 启动时间计算下一轮延迟，消除采集耗时导致的秒级漂移。
    """

    INTERVAL_IDLE = 30
    INTERVAL_ACTIVE = 5

    def __init__(self, instance_id: int):
        self.instance_id = instance_id
        self._timer: threading.Timer | None = None
        self._stopped = False
        self._lock = threading.Lock()
        self._high_freq = False

    def start(self):
        with self._lock:
            self._stopped = False
        self._schedule_next(self.INTERVAL_IDLE)
        logger.info(f"[LockScheduler] 实例 {self.instance_id} 启动锁快照采集")

    def stop(self):
        with self._lock:
            self._stopped = True
            if self._timer:
                self._timer.cancel()
                self._timer = None
        logger.info(f"[LockScheduler] 实例 {self.instance_id} 停止锁快照采集")

    def _schedule_next(self, interval: int, *, run_start: float | None = None):
        with self._lock:
            if self._stopped:
                return
            if run_start is not None:
                elapsed = time.time() - run_start
                delay = interval - elapsed
                if delay < 0:
                    delay = 0.5
            else:
                delay = interval
            self._timer = threading.Timer(delay, self._run)
            self._timer.daemon = True
            self._timer.start()

    def _run(self):
        with self._lock:
            if self._stopped:
                return
        run_start = time.time()
        try:
            from .models import DatabaseInstance
            instance = DatabaseInstance.objects.get(id=self.instance_id)
            if not instance.is_active or instance.db_type != "mysql":
                self._schedule_next(self.INTERVAL_IDLE)
                return
            if instance.connection_status != "connected":
                self.stop()
                return

            from .collectors.lock_snapshot import LockSnapshotCollector
            result = LockSnapshotCollector(instance).collect()

            if result.has_locks:
                if not self._high_freq:
                    self._high_freq = True
                    logger.info(
                        f"[LockScheduler] 实例 {self.instance_id} 检测到锁，切换 5s 高频模式"
                    )
                self._schedule_next(self.INTERVAL_ACTIVE, run_start=run_start)
            else:
                if self._high_freq:
                    self._high_freq = False
                    logger.info(
                        f"[LockScheduler] 实例 {self.instance_id} 锁已清除，恢复 30s 轮询"
                    )
                self._schedule_next(self.INTERVAL_IDLE, run_start=run_start)
        except Exception as e:
            logger.error(f"[LockScheduler] 实例 {self.instance_id} 异常: {e}")
            self._schedule_next(self.INTERVAL_IDLE)


class LockSchedulerRegistry:
    """全局锁采集调度器注册表。"""

    def __init__(self):
        self._schedulers: dict[int, LockScheduler] = {}
        self._lock = threading.Lock()

    def start_instance(self, instance_id: int):
        with self._lock:
            if instance_id in self._schedulers:
                self._schedulers[instance_id].stop()
            sched = LockScheduler(instance_id)
            self._schedulers[instance_id] = sched
        sched.start()

    def stop_instance(self, instance_id: int):
        with self._lock:
            sched = self._schedulers.pop(instance_id, None)
        if sched:
            sched.stop()

    def load_from_db(self):
        """Django 启动后从数据库恢复所有 active MySQL 连接正常的实例的锁采集调度。"""
        try:
            from .models import DatabaseInstance
            instances = DatabaseInstance.objects.filter(
                is_active=True, db_type="mysql", connection_status="connected",
            )
            for inst in instances:
                self.start_instance(inst.id)
            logger.info(f"[LockScheduler] 从数据库恢复 {instances.count()} 个实例的锁采集调度")
        except Exception as e:
            logger.error(f"[LockScheduler] 恢复锁采集调度失败: {e}")

    def status(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "instance_id": iid,
                    "high_freq": s._high_freq,
                    "active": not s._stopped,
                }
                for iid, s in self._schedulers.items()
            ]


# ═══════════════════════════════════════════════════════════════
# 死亡队列（连接失败的实例，5min 重试）
# ═══════════════════════════════════════════════════════════════

class _DeadQueueScheduler:
    """死亡队列中的单实例重试调度器。

    每 5 分钟尝试一次连接，成功则：
      - 更新 connection_status=connected, db_version
      - 将实例交给采集队列
      - 停止自己
    失败则保持在死亡队列，继续重试。
    """

    RETRY_INTERVAL = 300  # 5 分钟

    def __init__(self, instance_id: int):
        self.instance_id = instance_id
        self._timer: threading.Timer | None = None
        self._stopped = False
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            self._stopped = False
        self._schedule_next()
        logger.info(f"[DeadQueue] 实例 {self.instance_id} 加入死亡队列，每 {self.RETRY_INTERVAL}s 重试")

    def stop(self):
        with self._lock:
            self._stopped = True
            if self._timer:
                self._timer.cancel()
                self._timer = None
        logger.info(f"[DeadQueue] 实例 {self.instance_id} 移出死亡队列")

    def _schedule_next(self, *, run_start: float | None = None):
        with self._lock:
            if self._stopped:
                return
            if run_start is not None:
                elapsed = time.time() - run_start
                delay = self.RETRY_INTERVAL - elapsed
                if delay < 0:
                    delay = 0.5
            else:
                delay = self.RETRY_INTERVAL
            self._timer = threading.Timer(delay, self._run)
            self._timer.daemon = True
            self._timer.start()

    def _run(self):
        with self._lock:
            if self._stopped:
                return
        run_start = time.time()
        try:
            from .models import DatabaseInstance
            from .version_detect import detect_version

            instance = DatabaseInstance.objects.get(id=self.instance_id)

            if not instance.is_active:
                self.stop()
                return

            # 尝试连接
            try:
                version_raw, _ = detect_version(instance)
                # 连接成功
                instance.db_version = version_raw
                instance.connection_status = "connected"
                instance.save(update_fields=["db_version", "connection_status", "updated_at"])
                logger.info(f"[DeadQueue] 实例 {self.instance_id} 连接恢复，版本={version_raw}，移交采集队列")

                # 移交采集队列
                self.stop()
                registry.start_instance(instance.id, instance.collect_interval)
                # 如果是 MySQL，同时启动锁采集
                if instance.db_type == "mysql":
                    lock_registry.start_instance(instance.id)
                return

            except Exception as e:
                logger.debug(f"[DeadQueue] 实例 {self.instance_id} 重试失败: {e}")
                # 仍在死亡队列，继续重试
                pass

        except Exception as e:
            logger.error(f"[DeadQueue] 实例 {self.instance_id} 异常: {e}")

        finally:
            self._schedule_next(run_start=run_start)


class DeadQueueRegistry:
    """全局死亡队列注册表。"""

    def __init__(self):
        self._schedulers: dict[int, _DeadQueueScheduler] = {}
        self._lock = threading.Lock()

    def start_instance(self, instance_id: int):
        with self._lock:
            if instance_id in self._schedulers:
                return  # 已在死亡队列中，不重复添加
            sched = _DeadQueueScheduler(instance_id)
            self._schedulers[instance_id] = sched
        sched.start()

    def stop_instance(self, instance_id: int):
        with self._lock:
            sched = self._schedulers.pop(instance_id, None)
        if sched:
            sched.stop()

    def status(self) -> list[dict]:
        with self._lock:
            return [
                {"instance_id": iid, "retry_in": _DeadQueueScheduler.RETRY_INTERVAL}
                for iid, s in self._schedulers.items()
                if not s._stopped
            ]


# ═══════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════

registry = SchedulerRegistry()
lock_registry = LockSchedulerRegistry()
dead_registry = DeadQueueRegistry()
