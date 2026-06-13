from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.urls", namespace="accounts")),
    path("api/collector/", include("collector.urls", namespace="collector")),
    path("api/qan/", include("qan.urls", namespace="qan")),
    path("api/locks/", include("locks.urls", namespace="locks")),
    path("api/alerts/", include("alerts.urls", namespace="alerts")),
    path("api/", include("system_config.urls", namespace="system_config")),
]
