"""
AuditLog genérico via GenericForeignKey.

Padrão: post_save / post_delete signals nos models de domínio gravam
uma linha aqui. Útil pra compliance, debug ('quem mudou X e quando'),
e reconstrução de estado.

Trade-offs:
- GenericForeignKey adiciona content_type lookup mas mantém AuditLog
  agnóstico ao domínio. Pra apps com 3-5 entidades audited, vale.
- Para escala alta, talvez quebrar em audit_log_auction, audit_log_bid
  com FK forte (e particionar por tempo). Por enquanto, fica genérico.
- `changes` é JSONField com o diff. Em produção, considerar:
   - mascarar campos PII (não copiar `password`, etc.)
   - truncar valores grandes
   - excluir campos timestamp (auto_now) pra reduzir ruído

Action: CREATED / UPDATED / DELETED. Não capturo "READ" — leituras
geralmente são auditadas por outra camada (access log do nginx, etc.).
"""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.tenants.models import Tenant


class AuditLog(models.Model):
    ACTION_CREATED = "created"
    ACTION_UPDATED = "updated"
    ACTION_DELETED = "deleted"
    ACTION_CHOICES = [
        (ACTION_CREATED, "Created"),
        (ACTION_UPDATED, "Updated"),
        (ACTION_DELETED, "Deleted"),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="audit_logs",
        null=True,
        blank=True,
        help_text="NULL pra ações de superuser global; sempre setado em ações de tenant.",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="audit_actions",
        null=True,
        blank=True,
        help_text="User que disparou. NULL se ação foi de sistema (signal sem request).",
    )
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)

    # GenericFK pro objeto auditado
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.CharField(max_length=64)
    target = GenericForeignKey("content_type", "object_id")

    changes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_log"
        indexes = [
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["content_type", "object_id"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} {self.content_type.model}#{self.object_id} by {self.actor_id}"
