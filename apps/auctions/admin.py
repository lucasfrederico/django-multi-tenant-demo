from django.contrib import admin

from apps.auctions.models import AuctionItem, Bid


class BidInline(admin.TabularInline):
    model = Bid
    extra = 0
    readonly_fields = ("bidder", "amount", "placed_at", "tenant")
    can_delete = False


@admin.register(AuctionItem)
class AuctionItemAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "tenant",
        "status",
        "starting_price",
        "current_price",
        "closes_at",
        "created_by",
    )
    list_filter = ("tenant", "status")
    search_fields = ("title", "description")
    readonly_fields = ("created_at", "updated_at", "current_price")
    inlines = [BidInline]


@admin.register(Bid)
class BidAdmin(admin.ModelAdmin):
    list_display = ("auction", "bidder", "amount", "placed_at", "tenant")
    list_filter = ("tenant",)
    readonly_fields = ("placed_at",)
