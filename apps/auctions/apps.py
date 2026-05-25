from django.apps import AppConfig


class AuctionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.auctions"
    label = "auctions"

    def ready(self):
        # registra receivers (post_save / post_delete → AuditLog)
        from apps.auctions import signals  # noqa: F401
