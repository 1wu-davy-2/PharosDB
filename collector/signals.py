"""Django 信号 — 实例变更时同步更新内存调度器。

根据 connection_status 自动将实例分配到正确的队列：
  - connected + active   → 采集队列
  - disconnected         → 死亡队列
  - inactive             → 停止调度
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


def connect_signals():
    """在 AppConfig.ready() 中调用，确保信号只注册一次。"""
    pass  # 装饰器已在模块导入时注册，这里只是触发模块加载


@receiver(post_save, sender="collector.DatabaseInstance")
def on_instance_save(sender, instance, **kwargs):
    from .scheduler import index_registry, lock_registry, registry

    registry.update_instance(
        instance_id=instance.id,
        interval=instance.collect_interval,
        is_active=instance.is_active,
        connection_status=instance.connection_status,
    )

    if instance.db_type == "mysql" and instance.is_active and instance.connection_status == "connected":
        lock_registry.start_instance(instance.id)
        index_registry.start_instance(instance.id)
    else:
        lock_registry.stop_instance(instance.id)
        index_registry.stop_instance(instance.id)


@receiver(post_delete, sender="collector.DatabaseInstance")
def on_instance_delete(sender, instance, **kwargs):
    from .scheduler import dead_registry, index_registry, lock_registry, registry
    registry.stop_instance(instance.id)
    lock_registry.stop_instance(instance.id)
    index_registry.stop_instance(instance.id)
    dead_registry.stop_instance(instance.id)
