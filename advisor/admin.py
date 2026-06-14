from django.contrib import admin

from .models import AdvisorCheck, AdvisorFinding


@admin.register(AdvisorCheck)
class AdvisorCheckAdmin(admin.ModelAdmin):
    list_display = ["display_name", "name", "family", "category", "severity", "mode", "interval", "enabled"]
    list_filter = ["family", "category", "severity", "mode", "enabled"]
    search_fields = ["name", "display_name", "summary"]


@admin.register(AdvisorFinding)
class AdvisorFindingAdmin(admin.ModelAdmin):
    list_display = ["summary", "advisor_check", "instance", "severity", "found_at", "resolved_at"]
    list_filter = ["severity", "found_at"]
    search_fields = ["summary", "detail"]
