"""Real-estate transaction records and explicit party assignments.

Storage only for non-status fields. Every status change goes through
:mod:`apps.transactions.lifecycle` — the model refuses unguarded status
writes the same way agent contracts do.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.transactions.money import money_field
from apps.transactions.taxonomy import (
    ASSIGNMENT_ROLE_CHOICES,
    REPRESENTATION_CHOICES,
    SINGLETON_ASSIGNMENT_ROLES,
    STATUS_CHOICES,
    STATUS_CODES,
    TYPE_CHOICES,
    AssignmentRole,
    TransactionStatus,
)
from apps.user.models import Office

_STATUS_LIST: list[str] = sorted(STATUS_CODES)
_SINGLETON_ROLES: list[str] = sorted(SINGLETON_ASSIGNMENT_ROLES)


class TransactionQuerySet(models.QuerySet["Transaction"]):
    def for_reader(self, user, *, access) -> TransactionQuerySet:
        """Rows this reader may see — applied before anything else.

        Company / superuser short-circuit, then office/region tree, then
        personal grants via active assignments or the convenience FKs.
        """
        if getattr(user, "is_anonymous", False):
            return self.none()

        if getattr(user, "is_superuser", False) or access.company_wide:
            return self.all()

        personal = (
            Q(primary_agent=user)
            | Q(coordinator=user)
            | Q(
                assignments__user=user,
                assignments__ended_at__isnull=True,
            )
        )
        reach = Q(pk__in=[])
        if access.office_keys:
            reach |= Q(office__stable_key__in=sorted(access.office_keys))
        if access.region_keys:
            reach |= Q(office__region__stable_key__in=sorted(access.region_keys))
        return self.filter(reach | personal).distinct()

    def update(self, **kwargs):
        if "status" in kwargs:
            raise ValidationError(
                {
                    "status": _(
                        "Transaction status may only change through the "
                        "lifecycle transition service."
                    )
                }
            )
        return super().update(**kwargs)


class Transaction(models.Model):
    """One brokerage real-estate deal (buy, sell, or rent)."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    reference = models.CharField(_("reference"), max_length=16, unique=True, blank=True)

    transaction_type = models.CharField(
        _("transaction type"), max_length=20, choices=TYPE_CHOICES
    )
    representation_type = models.CharField(
        _("representation type"), max_length=20, choices=REPRESENTATION_CHOICES
    )

    office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name=_("owning office"),
        help_text=_("The node that owns this deal. Scope is read from it."),
    )
    primary_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_transactions",
        verbose_name=_("primary agent"),
    )
    coordinator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coordinated_transactions",
        verbose_name=_("assigned coordinator"),
    )

    property_snapshot = models.JSONField(
        _("property snapshot"),
        default=dict,
        blank=True,
        help_text=_("Address and identity fields captured at write time."),
    )
    property_external_ref = models.CharField(
        _("property external reference"),
        max_length=64,
        blank=True,
        db_index=True,
        help_text=_("Opaque CRM/MLS property id for a later join."),
    )
    mls_number = models.CharField(
        _("MLS number"), max_length=64, blank=True, db_index=True
    )

    client_snapshots = models.JSONField(
        _("client snapshots"),
        default=list,
        blank=True,
        help_text=_("Client presentation data; gated by field permission."),
    )
    client_external_refs = models.JSONField(
        _("client external references"),
        default=list,
        blank=True,
        help_text=_("Opaque CRM contact ids for a later join."),
    )

    list_price = money_field(verbose_name=_("list price"))
    contract_price = money_field(verbose_name=_("contract price"))

    acceptance_date = models.DateField(_("acceptance date"), null=True, blank=True)
    closing_date = models.DateField(_("closing date"), null=True, blank=True)

    lender_ref = models.CharField(_("lender reference"), max_length=128, blank=True)
    title_ref = models.CharField(_("title reference"), max_length=128, blank=True)
    referral_ref = models.CharField(_("referral reference"), max_length=128, blank=True)

    status = models.CharField(
        _("status"),
        max_length=32,
        choices=STATUS_CHOICES,
        default=TransactionStatus.DRAFT,
        db_index=True,
    )
    held_from_status = models.CharField(
        _("held from status"),
        max_length=32,
        blank=True,
        help_text=_("Pipeline status restored when leaving On Hold."),
    )

    preparing_at = models.DateTimeField(_("preparing at"), null=True, blank=True)
    under_contract_at = models.DateTimeField(
        _("under contract at"), null=True, blank=True
    )
    pending_at = models.DateTimeField(_("pending at"), null=True, blank=True)
    compliance_review_at = models.DateTimeField(
        _("compliance review at"), null=True, blank=True
    )
    compliance_approved_at = models.DateTimeField(
        _("compliance approved at"),
        null=True,
        blank=True,
        help_text=_(
            "Set when leaving Compliance Review for Ready to Close. "
            "Closing refuses without it."
        ),
    )
    ready_to_close_at = models.DateTimeField(
        _("ready to close at"), null=True, blank=True
    )
    closed_at = models.DateTimeField(_("closed at"), null=True, blank=True)
    archived_at = models.DateTimeField(_("archived at"), null=True, blank=True)
    on_hold_at = models.DateTimeField(_("on hold at"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    withdrawn_at = models.DateTimeField(_("withdrawn at"), null=True, blank=True)
    terminated_at = models.DateTimeField(_("terminated at"), null=True, blank=True)

    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions_archived",
        verbose_name=_("archived by"),
    )
    archive_reason = models.CharField(_("archive reason"), max_length=255, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions_created",
        verbose_name=_("created by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = TransactionQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("transaction")
        verbose_name_plural = _("transactions")
        permissions = (
            (
                "view_transaction_financials",
                _("Can view transaction list and contract prices"),
            ),
            (
                "view_transaction_clients",
                _("Can view transaction client snapshots"),
            ),
        )
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=_STATUS_LIST),
                name="transaction_status_is_known",
            ),
            models.CheckConstraint(
                condition=(
                    (Q(status=TransactionStatus.CLOSED) & Q(closed_at__isnull=False))
                    | (
                        ~Q(status=TransactionStatus.CLOSED)
                        & ~Q(status=TransactionStatus.ARCHIVED)
                        & Q(closed_at__isnull=True)
                    )
                    | (
                        Q(status=TransactionStatus.ARCHIVED)
                        & Q(closed_at__isnull=False)
                        & Q(archived_at__isnull=False)
                    )
                ),
                name="transaction_closed_at_matches_status",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=TransactionStatus.ARCHIVED, archived_at__isnull=False)
                    | (
                        ~Q(status=TransactionStatus.ARCHIVED)
                        & Q(archived_at__isnull=True)
                    )
                ),
                name="transaction_archived_at_matches_status",
            ),
        ]
        indexes = [
            models.Index(fields=["office", "status"], name="txn_office_status_idx"),
            models.Index(
                fields=["status", "closing_date"], name="txn_status_closing_idx"
            ),
            models.Index(
                fields=["primary_agent", "status"], name="txn_primary_status_idx"
            ),
            models.Index(fields=["mls_number"], name="txn_mls_number_idx"),
            models.Index(fields=["coordinator", "status"], name="txn_coord_status_idx"),
        ]

    def __str__(self) -> str:
        return self.reference or f"TXN-{self.pk or '?'}"

    @property
    def office_pk(self) -> int | None:
        return getattr(self, "office_id", None)

    @property
    def primary_agent_pk(self) -> int | None:
        return getattr(self, "primary_agent_id", None)

    @property
    def coordinator_pk(self) -> int | None:
        return getattr(self, "coordinator_id", None)

    @property
    def status_label(self) -> str:
        from apps.transactions.taxonomy import STATUS_LABELS

        return str(STATUS_LABELS.get(self.status, self.status))

    def save(self, *args, **kwargs):
        """Refuse unguarded status mutations outside the lifecycle service."""
        if self.pk:
            from apps.transactions.lifecycle import status_write_allowed

            previous = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
            if (
                previous is not None
                and previous != self.status
                and not status_write_allowed()
            ):
                raise ValidationError(
                    {
                        "status": _(
                            "Transaction status may only change through the "
                            "lifecycle transition service."
                        )
                    }
                )
        super().save(*args, **kwargs)


class TransactionAssignment(models.Model):
    """Explicit, auditable membership of a user on a transaction."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name=_("transaction"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transaction_assignments",
        verbose_name=_("user"),
    )
    role = models.CharField(_("role"), max_length=32, choices=ASSIGNMENT_ROLE_CHOICES)
    assigned_at = models.DateTimeField(_("assigned at"), auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transaction_assignments_made",
        verbose_name=_("assigned by"),
    )
    ended_at = models.DateTimeField(_("ended at"), null=True, blank=True)

    class Meta:
        ordering = ["-assigned_at", "-pk"]
        verbose_name = _("transaction assignment")
        verbose_name_plural = _("transaction assignments")
        constraints = [
            models.UniqueConstraint(
                fields=["transaction", "user", "role"],
                condition=Q(ended_at__isnull=True),
                name="txn_assignment_unique_active",
            ),
            models.UniqueConstraint(
                fields=["transaction", "role"],
                condition=Q(ended_at__isnull=True, role__in=_SINGLETON_ROLES),
                name="txn_assignment_singleton_active",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "ended_at"], name="txn_assign_user_active_idx"
            ),
            models.Index(
                fields=["transaction", "role", "ended_at"],
                name="txn_assign_role_active_idx",
            ),
        ]

    def __str__(self) -> str:
        user_id = getattr(self, "user_id", None)
        transaction_id = getattr(self, "transaction_id", None)
        return f"{self.role}:{user_id}@{transaction_id}"

    @property
    def user_pk(self) -> int | None:
        return getattr(self, "user_id", None)

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    @property
    def role_label(self) -> str:
        from apps.transactions.taxonomy import ASSIGNMENT_ROLE_LABELS

        return str(ASSIGNMENT_ROLE_LABELS.get(self.role, self.role))


# Re-export for callers that expect AssignmentRole on the model module.
__all__ = [
    "AssignmentRole",
    "Transaction",
    "TransactionAssignment",
    "TransactionQuerySet",
]
