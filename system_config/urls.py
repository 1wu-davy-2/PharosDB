"""系统配置 URL 路由。"""
from django.urls import path

from . import views

app_name = "system_config"

urlpatterns = [
    path("config/", views.ConfigView.as_view(), name="config"),
]
