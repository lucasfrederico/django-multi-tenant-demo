from django.contrib import admin

from apps.tenants.models import Tenant, User


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "created_at")
    search_fields = ("slug", "name")


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "tenant", "is_staff", "is_active", "date_joined")
    list_filter = ("tenant", "is_staff", "is_active")
    search_fields = ("email", "full_name")
    readonly_fields = ("date_joined",)
