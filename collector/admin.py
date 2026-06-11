from django.contrib import admin

from .models import DatabaseInstance


@admin.register(DatabaseInstance)
class DatabaseInstanceAdmin(admin.ModelAdmin):
    list_display = ["name", "db_type", "host", "port", "environment", "is_active", "last_collected_at"]
    list_filter = ["db_type", "environment", "is_active"]
    search_fields = ["name", "host"]
