from django.apps import AppConfig


class ItSupportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.it_support"
    verbose_name = "IT support"

    def ready(self) -> None:
        # Registers the notification source resolver as a side effect of
        # import, the same way every other module in this project does.
        from apps.it_support import notifications  # noqa: F401
