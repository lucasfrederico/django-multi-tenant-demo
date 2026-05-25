"""
Fixtures globais. Tudo aqui é importável de qualquer test sem import explícito.

Notas:
- `db` é fixture do pytest-django que abre transação por test e roll back no
  fim. Tudo que precisa de DB depende dela (direta ou indireta).
- Celery roda em modo eager (`task_always_eager`) — task.delay() executa
  inline na thread do test, sem worker, sem broker.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.auctions.models import AuctionItem
from apps.tenants.models import Tenant, User


@pytest.fixture(autouse=True)
def _celery_eager(settings):
    """Roda Celery sync em todos os tests."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True


@pytest.fixture
def tenant_a(db):
    return Tenant.objects.create(name="Tenant A", slug="tenant-a")


@pytest.fixture
def tenant_b(db):
    return Tenant.objects.create(name="Tenant B", slug="tenant-b")


@pytest.fixture
def user_a(tenant_a):
    return User.objects.create_user(
        email="alice@a.test", password="x", tenant=tenant_a, full_name="Alice"
    )


@pytest.fixture
def user_a2(tenant_a):
    return User.objects.create_user(
        email="anna@a.test", password="x", tenant=tenant_a, full_name="Anna"
    )


@pytest.fixture
def user_b(tenant_b):
    return User.objects.create_user(
        email="bob@b.test", password="x", tenant=tenant_b, full_name="Bob"
    )


def _client_for(user):
    client = APIClient()
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def client_a(user_a):
    return _client_for(user_a)


@pytest.fixture
def client_a2(user_a2):
    return _client_for(user_a2)


@pytest.fixture
def client_b(user_b):
    return _client_for(user_b)


@pytest.fixture
def auction_a(tenant_a, user_a):
    """Leilão ativo no tenant A, criado por user_a."""
    return AuctionItem.objects.create(
        tenant=tenant_a,
        created_by=user_a,
        title="Vintage Sword",
        description="Forged in legend",
        starting_price=Decimal("100.00"),
        status=AuctionItem.STATUS_ACTIVE,
        opens_at=timezone.now() - timedelta(hours=1),
        closes_at=timezone.now() + timedelta(hours=1),
    )


@pytest.fixture
def auction_b(tenant_b, user_b):
    return AuctionItem.objects.create(
        tenant=tenant_b,
        created_by=user_b,
        title="Crystal Orb",
        starting_price=Decimal("50.00"),
        status=AuctionItem.STATUS_ACTIVE,
        opens_at=timezone.now() - timedelta(hours=1),
        closes_at=timezone.now() + timedelta(hours=1),
    )
