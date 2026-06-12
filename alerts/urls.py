from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AlertEventViewSet, AlertRuleViewSet

router = DefaultRouter()
router.register("rules",  AlertRuleViewSet,  basename="alert-rule")
router.register("events", AlertEventViewSet, basename="alert-event")

app_name = "alerts"

urlpatterns = [
    path("", include(router.urls)),
]
