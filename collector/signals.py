"""Django 信号 — 实例变更时同步更新内存调度器。"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


def connect_signals():
    """在 AppConfig.ready() 中调用，确保信号只注册一次。"""
    pass  # 装饰器已在模块导入时注册，这里只是触发模块加载


@receiver(post_save, sender="collector.DatabaseInstance")
def on_instance_save(sender, instance, **kwargs):
    from .scheduler import registry
    registry.update_instance(
        instance_id=instance.id,
        interval=instance.collect_interval,
        is_active=instance.is_active,
    )


@receiver(post_delete, sender="collector.DatabaseInstance")
def on_instance_delete(sender, instance, **kwargs):
    from .scheduler import registry
    registry.stop_instance(instance.id)
