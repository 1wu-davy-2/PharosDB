"""Celery app 初始化 — PharosDB 异步任务框架。"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("pharosdb")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
