"""Announcement records and the admin-managed category vocabulary.

The domain stores stable machine codes and nothing about how they look. No
hex value, Tailwind class, or badge variant appears here: presentation is
derived in :mod:`apps.announcements.presentation` and notification behaviour
in :mod:`apps.announcements.policy`, so a design change never becomes a data
migration.

Audience follows the office tree exactly as office resources do: the owning
node *is* the audience. Head office owns brokerage-wide news, a region owns
its region, a branch owns itself. A reader sees the announcements owned by any
node on their own office's ancestor chain — see
:mod:`apps.announcements.services`.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.announcements.taxonomy import (
    PRIORITY_CHOICES,
    SYSTEM_CATEGORY_CODES,
)
from apps.user.models import Office
from apps.user.storage import private_storage


class ProtectedCategoryError(Exception):
    """A category that governance does not allow to be destroyed."""


class AnnouncementCategoryQuerySet(models.QuerySet["AnnouncementCategory"]):
    def active(self) -> AnnouncementCategoryQuerySet:
        return self.filter(is_active=True)

    def delete(self):
        """Bulk deletes go through the same guard as single ones.

        ``PROTECT`` on the announcement foreign key already stops a referenced
        category from vanishing. This adds the second half of the governance
        rule — seeded categories are permanent regardless of references — and
        puts it somewhere a bulk admin action cannot route around.
        """
        blocked = sorted(self.filter(is_system=True).values_list("code", flat=True))
        if blocked:
            raise ProtectedCategoryError(
                f"System categories cannot be deleted: {', '.join(blocked)}."
            )
        return super().delete()


class AnnouncementCategory(models.Model):
    """Admin-managed announcement vocabulary with a protected stable key.

    ``code`` is the contract — it appears in feed URLs, audit payloads, and
    presentation maps — so it is immutable once the row exists. ``label`` is
    presentation and is freely editable. Retiring a category means
    ``is_active=False``: it disappears from the compose and filter choices
    while every announcement already carrying it stays readable.
    """

    code = models.SlugField(
        _("code"),
        max_length=40,
        unique=True,
        help_text=_(
            "Stable machine key used in URLs, audits, and presentation maps. "
            "Set once at creation and never changed."
        ),
    )
    label = models.CharField(_("label"), max_length=80)
    description = models.CharField(_("description"), max_length=200, blank=True)
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Inactive categories cannot be assigned to new announcements but "
            "remain readable on existing ones."
        ),
    )
    display_order = models.PositiveSmallIntegerField(_("display order"), default=100)
    is_system = models.BooleanField(
        _("system category"),
        default=False,
        editable=False,
        help_text=_("Seeded by the catalog. Can be relabelled, never deleted."),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = AnnouncementCategoryQuerySet.as_manager()

    class Meta:
        ordering = ["display_order", "label"]
        verbose_name = _("announcement category")
        verbose_name_plural = _("announcement categories")

    def __str__(self):
        return self.label

    def clean(self):
        super().clean()
        if not self.pk:
            return
        stored = (
            type(self).objects.filter(pk=self.pk).values_list("code", flat=True).first()
        )
        if stored is not None and stored != self.code:
            raise ValidationError(
                {
                    "code": _(
                        "The category code is a stable key and cannot be "
                        "changed. Edit the label instead."
                    )
                }
            )

    def delete(self, *args, **kwargs):
        if self.is_system or self.code in SYSTEM_CATEGORY_CODES:
            raise ProtectedCategoryError(
                f"System category {self.code!r} cannot be deleted. "
                "Deactivate it instead."
            )
        return super().delete(*args, **kwargs)


class AnnouncementQuerySet(models.QuerySet["Announcement"]):
    def published(self) -> AnnouncementQuerySet:
        return self.filter(status=Announcement.Status.PUBLISHED)

    def within_window(self, *, now=None) -> AnnouncementQuerySet:
        moment = now or timezone.now()
        return self.filter(
            Q(publish_at__isnull=True) | Q(publish_at__lte=moment),
            Q(expires_at__isnull=True) | Q(expires_at__gt=moment),
        )


class Announcement(models.Model):
    """One piece of brokerage news, classified and audience-scoped.

    ``category`` and ``priority`` are optional on the row so a draft can be
    saved incomplete — the writer's outstanding work is reported as validation
    debt rather than blocking a save. The check constraint makes the same rule
    unavoidable at publish: a published row always carries both.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")
        ARCHIVED = "archived", _("Archived")

    owner_office = models.ForeignKey(
        Office,
        verbose_name=_("owning office"),
        related_name="announcements",
        on_delete=models.PROTECT,
        help_text=_(
            "The audience. Head office publishes brokerage-wide, a region to "
            "its region, a branch to itself."
        ),
    )
    slug = models.SlugField(_("slug"), max_length=80)
    title = models.CharField(_("title"), max_length=180)
    summary = models.CharField(_("summary"), max_length=280, blank=True)
    body = models.TextField(_("body"), blank=True)
    attachment = models.FileField(
        _("attachment"),
        max_length=255,
        blank=True,
        storage=private_storage,
        upload_to="announcements/%Y/%m/",
        help_text=_(
            "Stored in protected storage and only reachable through the "
            "download view, which re-evaluates the audience on every request."
        ),
    )
    attachment_name = models.CharField(
        _("original file name"), max_length=255, blank=True
    )
    category = models.ForeignKey(
        AnnouncementCategory,
        verbose_name=_("category"),
        related_name="announcements",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text=_("Required to publish. PROTECT keeps referenced rows alive."),
    )
    priority = models.CharField(
        _("priority"),
        max_length=16,
        choices=PRIORITY_CHOICES,
        blank=True,
        help_text=_(
            "Required to publish. Affects ordering and notification policy "
            "only — never who can see the announcement."
        ),
    )
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    publish_at = models.DateTimeField(
        _("publishes at"),
        null=True,
        blank=True,
        help_text=_("Empty means visible as soon as it is published."),
    )
    expires_at = models.DateTimeField(
        _("expires at"),
        null=True,
        blank=True,
        help_text=_("Empty means it never leaves the feed."),
    )
    published_at = models.DateTimeField(
        _("published at"), null=True, blank=True, editable=False
    )
    created_by = models.ForeignKey(
        "user.User",
        verbose_name=_("created by"),
        related_name="announcements_created",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = AnnouncementQuerySet.as_manager()

    class Meta:
        # Ordering here is the storage default only; the feed's documented
        # order is applied explicitly in ``services.order_for_feed``.
        ordering = ["-published_at", "-pk"]
        verbose_name = _("announcement")
        verbose_name_plural = _("announcements")
        constraints = [
            models.UniqueConstraint(
                fields=["owner_office", "slug"],
                name="announcement_unique_slug_per_office",
            ),
            # The acceptance criterion "all published announcements have valid
            # stable category and priority codes" as a database fact, not a
            # convention every future writer has to remember.
            models.CheckConstraint(
                condition=~Q(status="published")
                | (Q(category__isnull=False) & ~Q(priority="")),
                name="announcement_published_requires_taxonomy",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__isnull=True)
                | Q(publish_at__isnull=True)
                | Q(expires_at__gt=F("publish_at")),
                name="announcement_window_ordered",
            ),
        ]
        indexes = [
            models.Index(
                fields=["owner_office", "status"],
                name="announcement_scope_status",
            ),
            models.Index(
                fields=["status", "priority", "-published_at"],
                name="announcement_feed_order",
            ),
        ]

    def __str__(self):
        return f"{self.owner_office} / {self.slug}"

    @property
    def scope_level(self) -> str:
        """Company, region, or office, derived from the owning node kind."""
        if self.owner_office.kind == Office.Kind.HEAD_OFFICE:
            return "company"
        if self.owner_office.kind == Office.Kind.REGION:
            return "region"
        return "office"

    def is_visible_at(self, moment) -> bool:
        """Window membership only. Audience is a queryset concern."""
        if self.status != self.Status.PUBLISHED:
            return False
        if self.publish_at is not None and self.publish_at > moment:
            return False
        return self.expires_at is None or self.expires_at > moment

    def clean(self):
        super().clean()
        from apps.announcements.services import validation_debt

        errors: dict[str, object] = {}
        if self.expires_at and self.publish_at and self.expires_at <= self.publish_at:
            errors["expires_at"] = _("Expiry must be after the publish time.")
        # Only blocks *assigning* a retired category; rows that already carry
        # one validate unchanged because they are not re-assigning it.
        if (
            self.category is not None
            and not self.category.is_active
            and self._category_changed()
        ):
            errors["category"] = _("That category is retired. Choose an active one.")
        if self.status == self.Status.PUBLISHED:
            for field, message in validation_debt(self):
                errors.setdefault(field, message)
        if errors:
            raise ValidationError(errors)

    def _category_changed(self) -> bool:
        if not self.pk:
            return True
        previous = (
            type(self)
            .objects.filter(pk=self.pk)
            .values_list("category__code", flat=True)
            .first()
        )
        return previous != (self.category.code if self.category else None)


class AnnouncementAudienceQuerySet(models.QuerySet["AnnouncementAudience"]):
    def for_kind(self, kind: str) -> AnnouncementAudienceQuerySet:
        return self.filter(kind=kind)


class AnnouncementAudience(models.Model):
    """One audience selector attached to one announcement.

    Audience is a set of rows rather than a column so it can be indexed,
    constrained, and joined. Selectors combine as a **union (OR)**: a reader
    who matches any one of them sees the announcement, and matching several
    still yields one feed entry — see ``docs/announcements.md``.

    Each row names exactly one target, enforced by a check constraint per
    kind, so an ill-formed selector cannot be stored and every read path can
    trust the shape it finds. Rows are never a materialized recipient list:
    they are the *rule*, re-evaluated against the reader's current office and
    current effective roles on every read.
    """

    class Kind(models.TextChoices):
        COMPANY = "company", _("Everyone at the brokerage")
        ROLE = "role", _("Everyone holding a role")
        REGION = "region", _("A region and the offices under it")
        OFFICE = "office", _("One office only")
        USER = "user", _("One named person")

    announcement = models.ForeignKey(
        "Announcement",
        verbose_name=_("announcement"),
        related_name="audiences",
        on_delete=models.CASCADE,
    )
    kind = models.CharField(_("kind"), max_length=16, choices=Kind.choices)
    role = models.CharField(
        _("role code"),
        max_length=64,
        blank=True,
        help_text=_("Stable role catalog code. Only for role selectors."),
    )
    office = models.ForeignKey(
        Office,
        verbose_name=_("office"),
        related_name="announcement_audiences",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text=_(
            "The region or office targeted. A region selector reaches every "
            "office beneath it; an office selector reaches that office alone."
        ),
    )
    user = models.ForeignKey(
        "user.User",
        verbose_name=_("person"),
        related_name="announcement_audiences",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    objects = AnnouncementAudienceQuerySet.as_manager()

    class Meta:
        verbose_name = _("announcement audience")
        verbose_name_plural = _("announcement audiences")
        constraints = [
            # Exactly one target per kind. Without this a "role" row could
            # carry an office nobody reads, and the two would disagree about
            # who the audience is.
            models.CheckConstraint(
                condition=(
                    Q(kind="company", role="", office__isnull=True, user__isnull=True)
                    | (
                        Q(kind="role", office__isnull=True, user__isnull=True)
                        & ~Q(role="")
                    )
                    | Q(
                        kind__in=["region", "office"],
                        role="",
                        office__isnull=False,
                        user__isnull=True,
                    )
                    | Q(kind="user", role="", office__isnull=True, user__isnull=False)
                ),
                name="announcement_audience_one_target_per_kind",
            ),
            # Partial uniques rather than one wide constraint: NULL columns do
            # not deduplicate inside a composite unique index.
            models.UniqueConstraint(
                fields=["announcement"],
                condition=Q(kind="company"),
                name="announcement_audience_one_company_row",
            ),
            models.UniqueConstraint(
                fields=["announcement", "role"],
                condition=Q(kind="role"),
                name="announcement_audience_unique_role",
            ),
            models.UniqueConstraint(
                fields=["announcement", "kind", "office"],
                condition=Q(office__isnull=False),
                name="announcement_audience_unique_office",
            ),
            models.UniqueConstraint(
                fields=["announcement", "user"],
                condition=Q(kind="user"),
                name="announcement_audience_unique_user",
            ),
        ]
        indexes = [
            # One index per read shape. The feed asks "which announcements
            # target this office / these roles / this person", so the leading
            # column is the selector target, not the announcement.
            models.Index(fields=["kind", "office"], name="announcement_aud_office"),
            models.Index(fields=["kind", "role"], name="announcement_aud_role"),
            models.Index(fields=["kind", "user"], name="announcement_aud_user"),
        ]

    def __str__(self):
        return f"{self.announcement_ref} → {self.kind}:{self.target_label}"

    @property
    def announcement_ref(self) -> str:
        return str(self.announcement.slug)

    @property
    def target_label(self) -> str:
        if self.kind == self.Kind.COMPANY:
            return "everyone"
        if self.kind == self.Kind.ROLE:
            return self.role
        if self.office is not None:
            return self.office.name
        if self.user is not None:
            return self.user.get_full_name() or self.user.email
        return ""
