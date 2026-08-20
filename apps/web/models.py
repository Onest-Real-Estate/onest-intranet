from django.db import models
from django.utils.translation import gettext_lazy as _


class OperationsPermission(models.Model):
    """Permission anchor for administrative modules without domain models yet."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_users", _("Can view scoped users")),
            ("view_new_agents", _("Can view scoped new agents")),
            (
                "manage_new_agent_onboarding",
                _("Can manage scoped new-agent onboarding"),
            ),
            ("add_users", _("Can add users")),
            ("assign_user_roles", _("Can assign user roles")),
            ("view_agent_contracts", _("Can view scoped agent contracts")),
            ("view_transactions", _("Can view scoped transactions")),
            ("view_inventory", _("Can view scoped inventory")),
            ("view_reservations", _("Can view scoped reservations")),
            ("manage_announcements", _("Can manage announcements")),
            ("manage_training", _("Can manage training")),
            ("manage_documents", _("Can manage documents")),
            ("view_compliance", _("Can view scoped compliance items")),
            ("view_feedback", _("Can view scoped feedback")),
            ("view_platform_tasks", _("Can view sanitized platform task status")),
            ("manage_offices", _("Can manage scoped offices")),
            ("view_it_support", _("Can view scoped IT support requests")),
        )


class DashboardMetricPermission(models.Model):
    """Permission anchor for dashboard metrics whose domain models are pending.

    ``OperationsPermission`` gates administrative *destinations*. These gate
    dashboard *figures*, which are a different grant: every agent may read
    their own pipeline, while only managers may read a team aggregate. Keeping
    them apart means revoking one never silently widens the other.
    """

    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("view_own_transactions", _("Can view own transaction metrics")),
            ("view_own_tasks", _("Can view own task metrics")),
            ("view_own_commission", _("Can view own commission metrics")),
            ("view_own_leads", _("Can view own lead metrics")),
            ("view_office_tasks", _("Can view scoped team task metrics")),
        )
