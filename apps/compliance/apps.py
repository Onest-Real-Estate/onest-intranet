from django.apps import AppConfig


class ComplianceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.compliance"
    verbose_name = "Compliance"

    def ready(self) -> None:
        from apps.compliance import notifications  # noqa: F401
