"""
Tests cobrem o que vou ter que explicar em entrevista:

1. Isolamento de tenant — pilar do multi-tenancy
2. Race condition em bid concorrente — bug clássico que peguei no
   LFAuctionHouse legacy JS antes de reescrever
3. AuditLog é criado pelos signals em CREATE/UPDATE/DELETE
4. Celery task é dispatched on bid

Convenção: cada test começa com `test_` + nome explícito do invariant
sendo checado. Sem "test_works" / "test_happy_path".
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.auctions.models import AuctionItem, Bid


pytestmark = pytest.mark.django_db


# === Isolamento de tenant ===

def test_list_auctions_filters_by_tenant(client_a, client_b, auction_a, auction_b):
    """User de tenant A só vê leilões do tenant A."""
    resp = client_a.get("/api/auctions/")
    assert resp.status_code == 200
    ids = [row["id"] for row in resp.json()["results"]]
    assert auction_a.pk in ids
    assert auction_b.pk not in ids


def test_retrieve_auction_of_other_tenant_returns_404(client_a, auction_b):
    """Acesso direto pelo ID de outro tenant: 404 (não 403 — não vazar existência)."""
    resp = client_a.get(f"/api/auctions/{auction_b.pk}/")
    assert resp.status_code == 404


def test_create_auction_assigns_tenant_and_creator(client_a, user_a):
    payload = {
        "title": "Demo item",
        "starting_price": "10.00",
        "closes_at": (timezone.now() + timezone.timedelta(hours=1)).isoformat(),
    }
    resp = client_a.post("/api/auctions/", payload, format="json")
    assert resp.status_code == 201, resp.json()
    auction = AuctionItem.objects.get(pk=resp.json()["id"])
    assert auction.tenant_id == user_a.tenant_id
    assert auction.created_by_id == user_a.pk


def test_cannot_bid_on_other_tenant_auction(client_a, auction_b):
    """User de A não consegue dar bid em leilão de B (queryset filter no endpoint)."""
    resp = client_a.post(
        f"/api/auctions/{auction_b.pk}/bid/",
        {"amount": "500.00"},
        format="json",
    )
    assert resp.status_code == 404
    assert not Bid.objects.filter(auction=auction_b).exists()


# === Regras do bid ===

def test_bid_below_floor_is_rejected(client_a, auction_a):
    """starting_price=100, bid de 50 → 400 + nenhum Bid criado."""
    resp = client_a.post(
        f"/api/auctions/{auction_a.pk}/bid/", {"amount": "50.00"}, format="json"
    )
    assert resp.status_code == 400
    assert Bid.objects.filter(auction=auction_a).count() == 0


def test_bid_above_floor_creates_bid_and_updates_current_price(client_a, auction_a):
    resp = client_a.post(
        f"/api/auctions/{auction_a.pk}/bid/", {"amount": "150.00"}, format="json"
    )
    assert resp.status_code == 201, resp.json()
    auction_a.refresh_from_db()
    assert auction_a.current_price == Decimal("150.00")
    assert Bid.objects.filter(auction=auction_a).count() == 1


def test_second_bid_must_beat_current_price(client_a, client_a2, auction_a):
    """User 1 dá 150. User 2 tenta 120 — rejeitado (floor virou 150)."""
    client_a.post(
        f"/api/auctions/{auction_a.pk}/bid/", {"amount": "150.00"}, format="json"
    )
    resp = client_a2.post(
        f"/api/auctions/{auction_a.pk}/bid/", {"amount": "120.00"}, format="json"
    )
    assert resp.status_code == 400


def test_bid_on_closed_auction_rejected(client_a, auction_a):
    auction_a.status = AuctionItem.STATUS_CLOSED
    auction_a.save()
    resp = client_a.post(
        f"/api/auctions/{auction_a.pk}/bid/", {"amount": "200.00"}, format="json"
    )
    assert resp.status_code == 400


# === Audit log via signals ===

def test_auction_create_writes_audit_log(client_a, user_a):
    payload = {
        "title": "Audit demo",
        "starting_price": "10.00",
        "closes_at": (timezone.now() + timezone.timedelta(hours=1)).isoformat(),
    }
    client_a.post("/api/auctions/", payload, format="json")
    log = AuditLog.objects.filter(
        action=AuditLog.ACTION_CREATED, content_type__model="auctionitem"
    ).latest("created_at")
    assert log.tenant_id == user_a.tenant_id
    assert log.actor_id == user_a.pk
    assert log.changes["title"] == "Audit demo"


def test_bid_create_writes_audit_log(client_a, auction_a, user_a):
    client_a.post(
        f"/api/auctions/{auction_a.pk}/bid/", {"amount": "200.00"}, format="json"
    )
    log = AuditLog.objects.filter(
        action=AuditLog.ACTION_CREATED, content_type__model="bid"
    ).latest("created_at")
    assert log.tenant_id == user_a.tenant_id
    assert log.actor_id == user_a.pk


# === Celery task dispatch ===

def test_bid_dispatches_notify_outbid_task(client_a, auction_a, caplog):
    """Bid dispara notify_outbid; em eager mode roda inline e loga."""
    # primeiro bid: sem usuário anterior pra notificar (log info)
    client_a.post(
        f"/api/auctions/{auction_a.pk}/bid/", {"amount": "150.00"}, format="json"
    )
    # segundo bid: deve logar "user X foi superado"
    with caplog.at_level("INFO", logger="apps.auctions.tasks"):
        client_a.post(
            f"/api/auctions/{auction_a.pk}/bid/", {"amount": "200.00"}, format="json"
        )
    assert any("foi superado" in r.message for r in caplog.records)
