"""
Seed de dev: cria 2 tenants, alguns users, 1 leilão ativo e 2 bids.

Rodar:
  python manage.py shell < scripts/seed_dev.py

Idempotente (get_or_create). Roda quantas vezes quiser sem duplicar.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.auctions.models import AuctionItem, Bid
from apps.tenants.models import Tenant, User


def run():
    acme, _ = Tenant.objects.get_or_create(slug="acme", defaults={"name": "Acme Co."})
    globex, _ = Tenant.objects.get_or_create(
        slug="globex", defaults={"name": "Globex Corp."}
    )

    alice, created = User.objects.get_or_create(
        email="alice@acme.test", defaults={"tenant": acme, "full_name": "Alice"}
    )
    if created:
        alice.set_password("alice123")
        alice.save()

    bob, created = User.objects.get_or_create(
        email="bob@acme.test", defaults={"tenant": acme, "full_name": "Bob"}
    )
    if created:
        bob.set_password("bob123")
        bob.save()

    carl, created = User.objects.get_or_create(
        email="carl@globex.test", defaults={"tenant": globex, "full_name": "Carl"}
    )
    if created:
        carl.set_password("carl123")
        carl.save()

    auction, created = AuctionItem.objects.get_or_create(
        tenant=acme,
        title="Vintage typewriter",
        defaults={
            "created_by": alice,
            "description": "1953 Olivetti Lettera 22 in working condition.",
            "starting_price": Decimal("250.00"),
            "status": AuctionItem.STATUS_ACTIVE,
            "opens_at": timezone.now() - timedelta(hours=2),
            "closes_at": timezone.now() + timedelta(days=2),
        },
    )

    if created:
        Bid.objects.create(
            tenant=acme, auction=auction, bidder=bob, amount=Decimal("260.00")
        )
        Bid.objects.create(
            tenant=acme, auction=auction, bidder=alice, amount=Decimal("280.00")
        )
        auction.current_price = Decimal("280.00")
        auction.save(update_fields=["current_price", "updated_at"])

    print("== Seed OK ==")
    print(f"  Tenants: {Tenant.objects.count()}")
    print(f"  Users:   {User.objects.count()}")
    print(f"  Auctions: {AuctionItem.objects.count()}")
    print(f"  Bids:     {Bid.objects.count()}")
    print()
    print("Credenciais de teste:")
    print("  alice@acme.test  / alice123 (tenant acme)")
    print("  bob@acme.test    / bob123   (tenant acme)")
    print("  carl@globex.test / carl123  (tenant globex)")


run()
