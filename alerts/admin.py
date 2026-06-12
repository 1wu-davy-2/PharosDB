from django.contrib import admin

from .models import AlertEvent, AlertRule


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display  = ["name", "rule_type", "instance", "threshold", "period", "severity", "is_enabled", "updated_at"]
    list_filter   = ["rule_type", "severity", "is_enabled"]
    search_fields = ["name", "description"]


@admin.register(AlertEvent)
class AlertEventAdmin(admin.ModelAdmin):
    list_display  = ["rule", "instance", "metric_value", "threshold", "status", "fired_at", "resolved_at", "notified"]
    list_filter   = ["status", "notified", "rule__severity"]
    search_fields = ["rule__name"]
    readonly_fields = ["fired_at", "resolved_at", "notified", "notify_error"]
