from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"
    verbose_name = "Notifications"

    def ready(self):
        # Source resolvers and the domain-event consumer are wired at startup
        # so a producer never has to remember to import them.
        from apps.notifications.consumers import register_notification_consumer
        from apps.notifications.resolvers import register_default_resolvers

        register_default_resolvers()
        register_notification_consumer()
