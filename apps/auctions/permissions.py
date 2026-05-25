"""
Defesa em profundidade.

`get_queryset()` no ViewSet já filtra por tenant. Mas se algum dia
alguém esquecer disso (ou usar uma view direta sem queryset filter),
essa permission garante que um user com tenant=X não consegue acessar
obj.tenant=Y. Belt + suspenders.
"""

from rest_framework.permissions import BasePermission


class IsSameTenant(BasePermission):
    """Bloqueia acesso a objetos de outro tenant."""

    message = "Você não tem acesso a recursos de outro tenant."

    def has_object_permission(self, request, view, obj):
        user_tenant_id = getattr(request.user, "tenant_id", None)
        return user_tenant_id is not None and obj.tenant_id == user_tenant_id
