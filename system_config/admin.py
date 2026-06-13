from django.contrib import admin

from .models import SystemConfig


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ["key", "value", "value_type", "category", "editable", "updated_at"]
    list_filter = ["category", "value_type", "editable"]
    search_fields = ["key", "display_name", "description"]
    readonly_fields = ["updated_at", "created_at"]
