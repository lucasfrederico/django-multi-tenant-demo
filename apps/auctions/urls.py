from rest_framework.routers import DefaultRouter

from apps.auctions.views import AuctionItemViewSet

router = DefaultRouter()
router.register(r"auctions", AuctionItemViewSet, basename="auction")

urlpatterns = router.urls
