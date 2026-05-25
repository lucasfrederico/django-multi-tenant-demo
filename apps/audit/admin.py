from django.contrib import admin

from apps.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "tenant",
        "actor",
        "action",
        "content_type",
        "object_id",
    )
    list_filter = ("tenant", "action", "content_type")
    readonly_fields = (
        "tenant",
        "actor",
        "action",
        "content_type",
        "object_id",
        "changes",
        "created_at",
    )
    search_fields = ("object_id",)
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
