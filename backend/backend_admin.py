"""Django Admin views for MediSafe AI records."""

from django.contrib import admin

import backend


@admin.register(backend.SafetyReport)
class SafetyReportAdmin(admin.ModelAdmin):
    list_display = (
        "report_id",
        "medicine",
        "user",
        "report_date",
        "symptom_category",
        "status",
        "created_at",
    )
    list_filter = ("status", "category_source", "report_date", "created_at")
    search_fields = (
        "report_id",
        "medicine__name",
        "user__username",
        "symptoms",
        "description",
        "symptom_category__name",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("medicine", "user", "symptom_category")
    readonly_fields = tuple(field.name for field in backend.SafetyReport._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method == "GET" and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False
