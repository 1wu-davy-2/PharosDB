from django.contrib import admin

from .models import CollectionHistory, DatabaseInstance


@admin.register(DatabaseInstance)
class DatabaseInstanceAdmin(admin.ModelAdmin):
    list_display = ["name", "db_type", "host", "port", "environment", "is_active", "last_collected_at"]
    list_filter = ["db_type", "environment", "is_active"]
    search_fields = ["name", "host"]


@admin.register(CollectionHistory)
class CollectionHistoryAdmin(admin.ModelAdmin):
    list_display = ["instance", "triggered_by", "status", "started_at", "duration_ms", "queries_collected", "rows_written"]
    list_filter = ["triggered_by", "status", "instance"]
    search_fields = ["instance__name"]
    readonly_fields = ["instance", "triggered_by", "status", "started_at", "finished_at",
                       "duration_ms", "queries_collected", "rows_written", "error_message"]
