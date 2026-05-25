"""
ViewSet de AuctionItem + endpoint custom de Bid.

Multi-tenancy core:
- `get_queryset()` filtra por tenant do user logado. Sempre.
- `perform_create()` injeta tenant + created_by — client não envia.
- IsSameTenant permission é belt+suspenders pro caso de alguém quebrar
  o filter.

Bid race condition:
- `transaction.atomic` + `select_for_update` no AuctionItem garante que
  duas chamadas concorrentes ao mesmo auction são serializadas. Sem isso,
  cenário clássico de TOCTOU: dois users dão $100 ao mesmo tempo, ambos
  leem current_price=50, ambos escrevem current_price=100, último bid
  passa e o primeiro fica "perdido". Foi exatamente esse o problema do
  LFAuctionHouse legacy JS que reescrevi em Java.
"""

from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.auctions.models import AuctionItem, Bid
from apps.auctions.permissions import IsSameTenant
from apps.auctions.serializers import (
    AuctionItemSerializer,
    BidCreateSerializer,
    BidSerializer,
)


class AuctionItemViewSet(viewsets.ModelViewSet):
    serializer_class = AuctionItemSerializer
    permission_classes = [IsAuthenticated, IsSameTenant]

    def get_queryset(self):
        tenant_id = getattr(self.request.user, "tenant_id", None)
        if tenant_id is None:
            return AuctionItem.objects.none()
        return AuctionItem.objects.filter(tenant_id=tenant_id)

    def perform_create(self, serializer):
        serializer.save(
            tenant=self.request.user.tenant,
            created_by=self.request.user,
        )

    @action(detail=True, methods=["post"], url_path="bid")
    def place_bid(self, request, pk=None):
        """POST /api/auctions/{id}/bid/ {"amount": 123.45}"""
        input_ser = BidCreateSerializer(data=request.data)
        input_ser.is_valid(raise_exception=True)
        amount = input_ser.validated_data["amount"]

        # transação serializa concorrência por linha do AuctionItem
        with transaction.atomic():
            auction = (
                AuctionItem.objects
                .select_for_update()
                .filter(pk=pk, tenant_id=request.user.tenant_id)
                .first()
            )
            if auction is None:
                return Response(
                    {"detail": "leilão não encontrado neste tenant."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if auction.status != AuctionItem.STATUS_ACTIVE:
                return Response(
                    {"detail": f"leilão não está active (status={auction.status})."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            now = timezone.now()
            if now < auction.opens_at:
                return Response(
                    {"detail": "leilão ainda não abriu."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if now >= auction.closes_at:
                return Response(
                    {"detail": "leilão fechado."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            floor = auction.current_price or auction.starting_price
            if Decimal(amount) <= floor:
                return Response(
                    {
                        "detail": f"bid precisa ser maior que {floor}.",
                        "current_floor": str(floor),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            bid = Bid.objects.create(
                tenant=auction.tenant,
                auction=auction,
                bidder=request.user,
                amount=amount,
            )
            auction.current_price = amount
            auction.save(update_fields=["current_price", "updated_at"])

        return Response(BidSerializer(bid).data, status=status.HTTP_201_CREATED)
