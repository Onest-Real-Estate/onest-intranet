from django.apps import AppConfig


class UserConfig(AppConfig):
    name = "apps.user"

    def ready(self):
        # Register allauth signal handlers (default group on signup).
        from . import signals  # noqa: F401
        from .services.onboarding_stream import register_stream_consumer

        register_stream_consumer()
