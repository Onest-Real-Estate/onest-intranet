from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import NoReverseMatch
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.web.quick_access.catalog import (
    DEFAULT_ICON,
    ICON_KEYS,
    internal_destination_by_key,
)
from apps.web.quick_access.destinations import validate_destination


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
            (
                "publish_announcements",
                _("Can publish, schedule, and archive announcements"),
            ),
            ("pin_announcements", _("Can pin announcements")),
            ("manage_training", _("Can manage training")),
            ("manage_documents", _("Can manage documents")),
            ("view_compliance", _("Can view scoped compliance items")),
            ("view_feedback", _("Can view scoped feedback")),
            ("view_platform_tasks", _("Can view sanitized platform task status")),
            ("manage_offices", _("Can manage scoped offices")),
            ("view_it_support", _("Can view scoped IT support requests")),
            (
                "manage_quick_access",
                _("Can manage scoped Quick Access links"),
            ),
            (
                "manage_company_quick_access",
                _("Can manage company-wide Quick Access links"),
            ),
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


class QuickAccessLink(models.Model):
    """One launcher on the dashboard's Quick Access panel.

    The panel used to be a tuple in ``dashboard/providers.py``: changing it
    meant a deploy. This model moves that configuration into the database
    without giving it up to free text — the destination, the mark, and every
    integration attribute are drawn from reviewed allowlists in
    ``apps.web.quick_access.catalog``.

    Audience is modelled explicitly rather than as an opaque list. A link is
    company-wide, or it names offices and regions in
    :class:`QuickAccessLinkOfficeAudience` rows; it is open to every role, or
    it names roles in :class:`QuickAccessLinkRoleAudience` rows. Resolution
    order and the reasons a link stays hidden are documented in
    ``docs/quick-access.md`` and implemented once, in
    ``apps.web.quick_access.resolution``.

    Records are archived, never deleted: audit rows, onboarding tool-setup
    state, and historical dashboards all reference a link by its stable key.
    """

    class DestinationType(models.TextChoices):
        EXTERNAL_URL = "external_url", _("External URL")
        INTERNAL_ROUTE = "internal_route", _("Internal route")

    class OwnerScope(models.TextChoices):
        #: Editable only with ``web.manage_company_quick_access``.
        COMPANY = "company", _("Company")
        #: Editable by any administrator whose scope covers its audience.
        SCOPED = "scoped", _("Office or region")

    class SsoCapability(models.TextChoices):
        NONE = "none", _("No single sign-on")
        MICROSOFT_ENTRA = "microsoft_entra", _("Microsoft Entra ID")
        SAML = "saml", _("SAML")
        OIDC = "oidc", _("OpenID Connect")

    class IntegrationHealth(models.TextChoices):
        UNKNOWN = "unknown", _("Not monitored")
        HEALTHY = "healthy", _("Healthy")
        DEGRADED = "degraded", _("Degraded")
        OFFLINE = "offline", _("Offline")

    class SetupBehavior(models.TextChoices):
        NONE = "none", _("No setup step")
        SELF_SERVICE = "self_service", _("Agent signs in directly")
        REQUEST_ACCESS = "request_access", _("Access must be requested")
        PROVISIONED = "provisioned", _("Provisioned during onboarding")

    stable_key = models.SlugField(
        _("stable key"),
        max_length=64,
        unique=True,
        help_text=_(
            "Permanent identity used by audit records and integrations. "
            "Cannot be changed once the link exists."
        ),
    )
    name = models.CharField(_("name"), max_length=120)
    description = models.CharField(_("description"), max_length=255, blank=True)
    destination_type = models.CharField(
        _("destination type"),
        max_length=32,
        choices=DestinationType.choices,
        default=DestinationType.EXTERNAL_URL,
    )
    destination_value = models.CharField(
        _("destination"),
        max_length=500,
        help_text=_(
            "An https:// URL, or the key of an allowlisted internal destination."
        ),
    )
    icon = models.CharField(
        _("icon"),
        max_length=32,
        default=DEFAULT_ICON,
        help_text=_("Key of an approved mark shipped by the frontend."),
    )
    is_active = models.BooleanField(_("active"), default=True)
    is_archived = models.BooleanField(_("archived"), default=False)
    sort_order = models.PositiveIntegerField(
        _("sort order"),
        default=0,
        help_text=_(
            "Lower sorts first. Positions may repeat; ties break by name so "
            "routine reordering never has to renumber the whole panel."
        ),
    )
    publish_start_at = models.DateTimeField(_("publish from"), null=True, blank=True)
    publish_end_at = models.DateTimeField(_("publish until"), null=True, blank=True)
    sso_capability = models.CharField(
        _("single sign-on"),
        max_length=32,
        choices=SsoCapability.choices,
        default=SsoCapability.NONE,
    )
    integration_health = models.CharField(
        _("integration health"),
        max_length=32,
        choices=IntegrationHealth.choices,
        default=IntegrationHealth.UNKNOWN,
    )
    setup_behavior = models.CharField(
        _("setup behaviour"),
        max_length=32,
        choices=SetupBehavior.choices,
        default=SetupBehavior.SELF_SERVICE,
    )
    company_wide = models.BooleanField(
        _("visible company-wide"),
        default=False,
        help_text=_("Ignore office audience rows and show this to every office."),
    )
    owner_scope = models.CharField(
        _("owner scope"),
        max_length=16,
        choices=OwnerScope.choices,
        default=OwnerScope.SCOPED,
    )
    owner_office = models.ForeignKey(
        "user.Office",
        verbose_name=_("owning office"),
        related_name="owned_quick_access_links",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_("created at"), default=timezone.now)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    archived_at = models.DateTimeField(_("archived at"), null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        related_name="created_quick_access_links",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("updated by"),
        related_name="updated_quick_access_links",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    if TYPE_CHECKING:
        # Reverse accessors and implicit FK columns Django creates at runtime.
        # Declared for the type checker only; they have no runtime effect.
        owner_office_id: int | None
        role_audiences: models.Manager["QuickAccessLinkRoleAudience"]
        office_audiences: models.Manager["QuickAccessLinkOfficeAudience"]

    class Meta:
        ordering = ["sort_order", "name", "pk"]
        verbose_name = _("quick access link")
        verbose_name_plural = _("quick access links")
        indexes = [
            models.Index(
                fields=["is_archived", "is_active", "sort_order"],
                name="web_qal_live_order",
            ),
            models.Index(
                fields=["publish_start_at", "publish_end_at"],
                name="web_qal_window",
            ),
            models.Index(fields=["owner_scope"], name="web_qal_owner_scope"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(publish_end_at__isnull=True)
                | Q(publish_start_at__isnull=True)
                | Q(publish_end_at__gt=models.F("publish_start_at")),
                name="web_qal_publish_window_ordered",
            ),
            models.CheckConstraint(
                condition=~Q(owner_scope="scoped") | Q(company_wide=False),
                name="web_qal_company_wide_is_company_owned",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.stable_key})"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, object] = {}
        if self.pk:
            original = (
                type(self).objects.filter(pk=self.pk).values("stable_key").first()
            )
            if original and original["stable_key"] != self.stable_key:
                errors["stable_key"] = _(
                    "Stable identity cannot be changed once created."
                )
        if self.icon not in ICON_KEYS:
            errors["icon"] = _("Choose one of the approved icons.")
        try:
            self.destination_value = validate_destination(
                self.destination_type, self.destination_value
            )
        except ValidationError as exc:
            errors["destination_value"] = exc
        if (
            self.publish_start_at
            and self.publish_end_at
            and self.publish_end_at <= self.publish_start_at
        ):
            errors["publish_end_at"] = _("The publish window must end after it starts.")
        if self.company_wide and self.owner_scope != self.OwnerScope.COMPANY:
            errors["company_wide"] = _(
                "A company-wide link is a company-owned definition."
            )
        if errors:
            raise ValidationError(errors)

    def href(self) -> str:
        """Return a currently approved destination, or ``""``.

        The form and ``clean()`` validate every write, but the browser boundary
        validates again so a legacy row or direct database edit cannot surface
        an unsafe URL. Internal keys resolve through ``reverse()`` at render
        time. A key that left the allowlist, or a route that no longer reverses,
        returns empty rather than taking down the whole panel.
        """
        try:
            value = validate_destination(self.destination_type, self.destination_value)
        except ValidationError:
            return ""
        if self.destination_type == self.DestinationType.INTERNAL_ROUTE:
            destination = internal_destination_by_key().get(value)
            try:
                return destination.href() if destination else ""
            except NoReverseMatch:
                return ""
        return value

    @property
    def is_external(self) -> bool:
        return self.destination_type == self.DestinationType.EXTERNAL_URL


class QuickAccessLinkRoleAudience(models.Model):
    """One role that may see a link.

    No rows means "every role". Rows store the stable role code from
    ``apps.user.roles``, never a Django group name or a display label.
    """

    link = models.ForeignKey(
        QuickAccessLink,
        verbose_name=_("link"),
        related_name="role_audiences",
        on_delete=models.CASCADE,
    )
    role_code = models.CharField(_("role"), max_length=64)

    if TYPE_CHECKING:
        link_id: int

    class Meta:
        ordering = ["role_code"]
        verbose_name = _("quick access role audience")
        verbose_name_plural = _("quick access role audiences")
        constraints = [
            models.UniqueConstraint(
                fields=["link", "role_code"], name="web_qal_role_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.link_id}:{self.role_code}"


class QuickAccessLinkOfficeAudience(models.Model):
    """One office-tree node that may see a link.

    ``include_descendants`` is what makes a region or company audience
    expressible without duplicating a row per branch: a row on a region with
    descendants included covers every office beneath it, and one on a single
    branch without it covers exactly that branch.
    """

    link = models.ForeignKey(
        QuickAccessLink,
        verbose_name=_("link"),
        related_name="office_audiences",
        on_delete=models.CASCADE,
    )
    office = models.ForeignKey(
        "user.Office",
        verbose_name=_("office"),
        related_name="quick_access_audiences",
        on_delete=models.CASCADE,
    )
    include_descendants = models.BooleanField(_("include descendants"), default=True)

    if TYPE_CHECKING:
        link_id: int
        office_id: int

    class Meta:
        ordering = ["office__sort_order", "office__name"]
        verbose_name = _("quick access office audience")
        verbose_name_plural = _("quick access office audiences")
        constraints = [
            models.UniqueConstraint(
                fields=["link", "office"], name="web_qal_office_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.link_id}:{self.office_id}"


class QuickAccessLinkClick(models.Model):
    """One reader opening one launcher, recorded for panel analytics.

    Deliberately *not* an :class:`~apps.audit.models.AuditEvent`. A click is
    high-volume telemetry about which tools an office actually uses, not a
    security-relevant lifecycle change, and mixing the two would bury the audit
    trail under traffic.

    **The row carries no destination.** It names the link by stable key and
    records nothing about the URL — no path, no query string, no fragment — so
    an external tool's session token or tenant identifier can never reach this
    table by way of a click. The key is enough to answer every question the
    panel asks; the URL is only ever a liability here.

    ``link`` is nulled rather than cascaded when a link is finally removed:
    counts for a retired tool stay answerable through ``link_stable_key``.
    """

    link = models.ForeignKey(
        QuickAccessLink,
        verbose_name=_("link"),
        related_name="clicks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: Snapshot, so a removed link still counts. Not unique, not a foreign key.
    link_stable_key = models.SlugField(_("link key"), max_length=64)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        related_name="quick_access_clicks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: The office the reader sat in at the time, so a later transfer does not
    #: rewrite history. Denormalized on purpose.
    office = models.ForeignKey(
        "user.Office",
        verbose_name=_("office"),
        related_name="quick_access_clicks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    destination_type = models.CharField(
        _("destination type"),
        max_length=32,
        choices=QuickAccessLink.DestinationType.choices,
    )
    occurred_at = models.DateTimeField(_("occurred at"), default=timezone.now)

    if TYPE_CHECKING:
        link_id: int | None
        user_id: int | None
        office_id: int | None

    class Meta:
        ordering = ["-occurred_at", "-pk"]
        verbose_name = _("quick access click")
        verbose_name_plural = _("quick access clicks")
        indexes = [
            models.Index(
                fields=["link_stable_key", "occurred_at"], name="web_qac_key_time"
            ),
            models.Index(fields=["occurred_at"], name="web_qac_time"),
        ]

    def __str__(self) -> str:
        return f"{self.link_stable_key}@{self.occurred_at.isoformat()}"
