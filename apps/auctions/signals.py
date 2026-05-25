"""
post_save / post_delete em AuctionItem e Bid → grava linha no AuditLog.

Como passar 'actor' (user que fez a ação) ao signal:
  - Signals nativos não recebem request. Hack idiomático Django:
    ViewSet seta `instance._audit_actor = request.user` antes do save,
    e o signal lê esse atributo se existir.
  - Para captures fora do request (Django shell, scripts, Celery tasks),
    actor fica NULL — representando 'sistema'.

Diff de changes:
  - Em CREATE, grava todos os fields (snapshot).
  - Em UPDATE, captura kwargs['update_fields'] se passado; senão
    snapshot completo (mais cara de storage, mas simplifica).
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.audit.middleware import get_current_user
from apps.audit.models import AuditLog
from apps.auctions.models import AuctionItem, Bid


def _snapshot(instance, fields=None):
    """Retorna dict serializável dos fields do instance."""
    if fields is None:
        fields = [f.name for f in instance._meta.concrete_fields]
    snap = {}
    for f in fields:
        val = getattr(instance, f, None)
        # serialize valores não-JSON
        if val is None:
            snap[f] = None
        elif hasattr(val, "isoformat"):
            snap[f] = val.isoformat()
        elif hasattr(val, "_meta"):  # FK → pk
            snap[f] = val.pk
        else:
            snap[f] = str(val) if not isinstance(val, (int, float, bool, str)) else val
    return snap


def _log(action, instance, *, fields=None):
    # actor: prioridade instance._audit_actor (caller passou explícito),
    # fallback thread-local (request.user via middleware), fallback NULL
    actor = getattr(instance, "_audit_actor", None) or get_current_user()
    AuditLog.objects.create(
        tenant=getattr(instance, "tenant", None),
        actor=actor,
        action=action,
        target=instance,
        changes=_snapshot(instance, fields),
    )


@receiver(post_save, sender=AuctionItem)
def auction_audit(sender, instance, created, update_fields=None, **kwargs):
    if created:
        _log(AuditLog.ACTION_CREATED, instance)
    else:
        _log(AuditLog.ACTION_UPDATED, instance, fields=list(update_fields or []))


@receiver(post_delete, sender=AuctionItem)
def auction_deleted(sender, instance, **kwargs):
    _log(AuditLog.ACTION_DELETED, instance)


@receiver(post_save, sender=Bid)
def bid_audit(sender, instance, created, **kwargs):
    if created:
        _log(AuditLog.ACTION_CREATED, instance)
    # Bids não são editáveis na regra do produto — sem branch UPDATE


@receiver(post_delete, sender=Bid)
def bid_deleted(sender, instance, **kwargs):
    _log(AuditLog.ACTION_DELETED, instance)
