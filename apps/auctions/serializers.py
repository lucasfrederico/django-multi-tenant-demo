from decimal import Decimal

from rest_framework import serializers

from apps.auctions.models import AuctionItem, Bid


class AuctionItemSerializer(serializers.ModelSerializer):
    # tenant + created_by + current_price são server-side; nunca aceitos do client.
    tenant = serializers.PrimaryKeyRelatedField(read_only=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    current_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    bid_count = serializers.SerializerMethodField()

    class Meta:
        model = AuctionItem
        fields = [
            "id",
            "tenant",
            "created_by",
            "title",
            "description",
            "starting_price",
            "current_price",
            "status",
            "opens_at",
            "closes_at",
            "created_at",
            "updated_at",
            "bid_count",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_bid_count(self, obj):
        # ATENÇÃO: isso dispara query por item se o queryset não anotou.
        # Em produção, anotar com Count('bids') no get_queryset.
        return obj.bids.count()


class BidSerializer(serializers.ModelSerializer):
    tenant = serializers.PrimaryKeyRelatedField(read_only=True)
    bidder = serializers.PrimaryKeyRelatedField(read_only=True)
    auction = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Bid
        fields = ["id", "tenant", "auction", "bidder", "amount", "placed_at"]
        read_only_fields = ["id", "placed_at"]


class BidCreateSerializer(serializers.Serializer):
    """Input pro endpoint POST /auctions/{id}/bid/ — só o amount."""

    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0")
    )
