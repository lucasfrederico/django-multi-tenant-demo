"""
AuctionItem + Bid.

Domain inspirado no LFAuctionHouse (LoverCraft) que reescrevi em Java —
mesmo problema de invariants em escala, traduzido pro Django.

Decisões:
- Cada model carrega FK pro Tenant (não só via User). Isso permite
  filter direto sem JOIN extra e deixa o queryset filter no ViewSet
  trivial: `qs.filter(tenant=request.user.tenant)`.
- `current_price` é denormalizado (em vez de calcular max(Bid.amount)
  a cada read) — trade-off: precisa atualizar em transação na hora do bid.
  Vou tratar isso no ViewSet do Bid com `select_for_update` na Phase 1.
- Status `draft/active/closed` controla aceitação de bids (regra fica
  no service/ViewSet, não no model — mais testável).
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.tenants.models import Tenant


class AuctionItem(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_ACTIVE = "active"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_CLOSED, "Closed"),
    ]

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="auctions"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="auctions_created",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    starting_price = models.DecimalField(max_digits=12, decimal_places=2)
    current_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Denormalizado pra evitar max(Bid.amount) em todo read.",
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT
    )
    opens_at = models.DateTimeField(default=timezone.now)
    closes_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "auction_item"
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "closes_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.tenant.slug})"


class Bid(models.Model):
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="bids"
    )
    auction = models.ForeignKey(
        AuctionItem, on_delete=models.CASCADE, related_name="bids"
    )
    bidder = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bids"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    placed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bid"
        indexes = [
            models.Index(fields=["auction", "-amount"]),
            models.Index(fields=["tenant", "-placed_at"]),
        ]
        ordering = ["-placed_at"]

    def __str__(self):
        return f"Bid {self.amount} on auction#{self.auction_id}"
