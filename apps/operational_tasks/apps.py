from django.apps import AppConfig


class OperationalTasksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.operational_tasks"
    label = "operational_tasks"
    verbose_name = "Operational tasks"

    def ready(self) -> None:
        # Registration side effects only: the action-item collector and the
        # notification resolver both have to exist before the first request,
        # and neither may import models at module import time.
        from apps.operational_tasks import notifications  # noqa: F401
