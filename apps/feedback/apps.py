from django.apps import AppConfig


class FeedbackConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.feedback"
    label = "feedback"
    verbose_name = "Feedback and support"

    def ready(self) -> None:
        # Registers the notification source resolver. Must not import models at
        # module import time.
        from apps.feedback import notifications  # noqa: F401
