"""Office inventory records and transfer history.

Storage only. Lifecycle changes, office transfers, and retirement go through
:mod:`apps.inventory.services` — the model deliberately has no ``save()``
override and no signal that mutates availability state.

Available quantity for pooled stock is never stored as a drifting counter;
callers use :mod:`apps.inventory.availability` to compute availability for a
requested interval.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.inventory.reservation_taxonomy import (
    CAPACITY_CONSUMING_STATES,
    STATUS_CHOICES,
    STATUS_LABELS,
    ReservationStatus,
)
from apps.inventory.taxonomy import (
    CATEGORY_CHOICES,
    CONDITION_CHOICES,
    RESERVABLE_STATES,
    STATE_CHOICES,
    STATE_LABELS,
    TERMINAL_STATES,
    TRACKING_CHOICES,
    ItemAvailabilityState,
    TrackingMode,
)
from apps.user.models import Office
from apps.user.storage import private_storage

_TERMINAL: list[str] = sorted(TERMINAL_STATES)
_CAPACITY: list[str] = sorted(CAPACITY_CONSUMING_STATES)


def inventory_photo_upload_to(instance: InventoryItem, filename: str) -> str:
    suffix = filename.rsplit("/", 1)[-1][:120]
    return f"inventory/{instance.public_id}/{suffix}"


class InventoryQuerySet(models.QuerySet["InventoryItem"]):
    def active_catalog(self) -> InventoryQuerySet:
        """Non-retired rows still visible in catalog surfaces."""
        return self.filter(retired_at__isnull=True).exclude(
            availability_state=ItemAvailabilityState.RETIRED
        )

    def reservable_catalog(self) -> InventoryQuerySet:
        """Rows eligible for new reservations before interval math."""
        return self.active_catalog().filter(
            availability_state__in=sorted(RESERVABLE_STATES)
        )

    def for_manager(self, user, *, access) -> InventoryQuerySet:
        """Scoped inventory for holders of ``web.view_inventory``.

        Company reach sees everything; region and office grants see the office
        tree beneath them. This is the only place manager visibility is decided.
        """
        if getattr(user, "is_anonymous", False):
            return self.none()

        if getattr(user, "is_superuser", False) or access.company_wide:
            return self.all()

        reach = Q(pk__in=[])
        if access.office_keys:
            reach |= Q(owner_office__stable_key__in=sorted(access.office_keys))
        if access.region_keys:
            reach |= Q(owner_office__region__stable_key__in=sorted(access.region_keys))
        return self.filter(reach)

    def for_agent_office(self, office: Office | None) -> InventoryQuerySet:
        """Active reservable items for one assignable office.

        Used by the agent browser. Never accepts a client-supplied office id —
        the caller must resolve the reader's primary office server-side.
        """
        if office is None or not office.is_assignable or not office.is_active:
            return self.none()
        return self.filter(owner_office=office).reservable_catalog()


class InventoryItem(models.Model):
    """One serialized asset or one pooled stock record."""

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    owner_office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        related_name="inventory_items",
        verbose_name=_("owning office"),
        help_text=_(
            "The assignable office that owns this record. Scope is read from it."
        ),
    )
    name = models.CharField(_("name"), max_length=200)
    category = models.CharField(_("category"), max_length=40, choices=CATEGORY_CHOICES)
    tracking_mode = models.CharField(
        _("tracking mode"),
        max_length=20,
        choices=TRACKING_CHOICES,
        default=TrackingMode.SERIALIZED,
    )
    asset_id = models.CharField(
        _("asset id"),
        max_length=64,
        blank=True,
        help_text=_("Brokerage asset tag. Required for serialized items."),
    )
    serial_number = models.CharField(_("serial number"), max_length=128, blank=True)
    total_quantity = models.PositiveIntegerField(
        _("total quantity"),
        default=1,
        help_text=_(
            "Authoritative on-hand count for pooled stock. Serialized items "
            "always have an effective quantity of one."
        ),
    )
    condition = models.CharField(
        _("condition"), max_length=20, choices=CONDITION_CHOICES
    )
    availability_state = models.CharField(
        _("availability state"),
        max_length=32,
        choices=STATE_CHOICES,
        default=ItemAvailabilityState.AVAILABLE,
    )
    storage_location = models.CharField(
        _("storage location"), max_length=200, blank=True
    )
    notes = models.TextField(_("notes"), blank=True)
    internal_notes = models.TextField(
        _("internal notes"),
        blank=True,
        help_text=_("Staff-only. Never serialized without the sensitive grant."),
    )
    photo = models.FileField(
        _("photo"),
        upload_to=inventory_photo_upload_to,
        storage=private_storage,
        max_length=255,
        blank=True,
    )
    photo_is_public = models.BooleanField(
        _("photo approved for public display"),
        default=False,
        help_text=_(
            "When false the photo is internal-only and served through an "
            "authorized download view."
        ),
    )
    requires_approval = models.BooleanField(
        _("requires office approval"),
        default=False,
        help_text=_(
            "When true, new reservations start as requested and wait for "
            "office approval. When false, available reservations auto-confirm."
        ),
    )
    replacement_value = models.DecimalField(
        _("replacement value"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    replacement_currency = models.CharField(
        _("replacement currency"), max_length=3, default="USD", blank=True
    )
    activated_at = models.DateTimeField(_("activated at"), null=True, blank=True)
    retired_at = models.DateTimeField(_("retired at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_items_created",
        verbose_name=_("created by"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_items_updated",
        verbose_name=_("updated by"),
    )

    if TYPE_CHECKING:
        owner_office_id: int
        created_by_id: int | None
        updated_by_id: int | None

    objects = InventoryQuerySet.as_manager()

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = _("inventory item")
        verbose_name_plural = _("inventory items")
        permissions = (
            ("manage_inventory", _("Can manage scoped inventory items")),
            (
                "view_inventory_sensitive",
                _("Can view inventory serial numbers, valuation, and internal notes"),
            ),
            (
                "reserve_on_behalf",
                _("Can create inventory reservations for other users"),
            ),
            (
                "approve_reservations",
                _("Can approve or deny inventory reservations"),
            ),
            (
                "override_reservations",
                _("Can override inventory reservation policy with a reason"),
            ),
        )
        constraints = [
            models.CheckConstraint(
                condition=~Q(name=""),
                name="inventory_item_requires_name",
            ),
            models.CheckConstraint(
                condition=Q(total_quantity__gte=0),
                name="inventory_item_quantity_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(replacement_value__isnull=True)
                    | Q(replacement_value__gte=Decimal("0"))
                ),
                name="inventory_item_replacement_value_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(tracking_mode=TrackingMode.SERIALIZED) | Q(total_quantity=1)
                ),
                name="inventory_item_serialized_quantity_one",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(tracking_mode=TrackingMode.POOLED) | Q(total_quantity__gte=1)
                ),
                name="inventory_item_pooled_quantity_positive",
            ),
            models.CheckConstraint(
                condition=(~Q(tracking_mode=TrackingMode.SERIALIZED) | ~Q(asset_id="")),
                name="inventory_item_serialized_requires_asset_id",
            ),
            models.CheckConstraint(
                condition=(
                    Q(tracking_mode=TrackingMode.SERIALIZED)
                    | (Q(asset_id="") & Q(serial_number=""))
                ),
                name="inventory_item_pooled_no_identifiers",
            ),
            models.CheckConstraint(
                condition=(
                    Q(availability_state__in=_TERMINAL, retired_at__isnull=False)
                    | (
                        ~Q(availability_state__in=_TERMINAL)
                        & Q(retired_at__isnull=True)
                    )
                ),
                name="inventory_item_retired_at_matches_state",
            ),
            models.UniqueConstraint(
                fields=["owner_office", "asset_id"],
                condition=~Q(asset_id=""),
                name="inventory_item_unique_asset_id_per_office",
            ),
            models.UniqueConstraint(
                fields=["owner_office", "serial_number"],
                condition=~Q(serial_number=""),
                name="inventory_item_unique_serial_per_office",
            ),
        ]
        indexes = [
            models.Index(
                fields=["owner_office", "availability_state"],
                name="inv_item_office_state_idx",
            ),
            models.Index(fields=["category"], name="inv_item_category_idx"),
            models.Index(fields=["tracking_mode"], name="inv_item_tracking_idx"),
            models.Index(
                fields=["owner_office", "category", "availability_state"],
                name="inv_item_office_cat_state",
            ),
            models.Index(fields=["name"], name="inv_item_name_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def availability_state_label(self) -> str:
        return str(STATE_LABELS.get(self.availability_state, self.availability_state))

    @property
    def is_retired(self) -> bool:
        return (
            self.availability_state == ItemAvailabilityState.RETIRED
            or self.retired_at is not None
        )

    @property
    def is_reservable(self) -> bool:
        return not self.is_retired and self.availability_state in RESERVABLE_STATES

    @property
    def effective_quantity(self) -> int:
        if self.tracking_mode == TrackingMode.SERIALIZED:
            return 1
        return self.total_quantity

    def clean(self) -> None:
        super().clean()
        errors: dict[str, object] = {}

        if getattr(self, "owner_office_id", None):
            office = self.owner_office
            if not office.is_assignable or not office.is_active:
                errors["owner_office"] = _(
                    "Only active, assignable offices may own reservable inventory."
                )

        if self.tracking_mode == TrackingMode.SERIALIZED:
            if self.total_quantity != 1:
                errors["total_quantity"] = _(
                    "Serialized items have an effective quantity of one."
                )
            if not self.asset_id.strip():
                errors["asset_id"] = _("Serialized items require an asset id.")
            if self.serial_number and not self.serial_number.strip():
                errors["serial_number"] = _("Serial number cannot be blank.")
        elif self.tracking_mode == TrackingMode.POOLED:
            if self.asset_id.strip() or self.serial_number.strip():
                errors["tracking_mode"] = _(
                    "Pooled items cannot carry asset or serial identifiers."
                )
            if self.total_quantity < 1:
                errors["total_quantity"] = _(
                    "Pooled items require a positive total quantity."
                )

        if self.replacement_value is not None and self.replacement_value < 0:
            errors["replacement_value"] = _("Replacement value must be nonnegative.")

        from apps.inventory.taxonomy import SUPPORTED_CURRENCIES

        currency = (self.replacement_currency or "").upper()
        if self.replacement_value is not None and currency not in SUPPORTED_CURRENCIES:
            errors["replacement_currency"] = _(
                "Unsupported currency. Supported: %(supported)s."
            ) % {"supported": ", ".join(sorted(SUPPORTED_CURRENCIES))}

        if self.availability_state == ItemAvailabilityState.RETIRED:
            if self.retired_at is None:
                errors["retired_at"] = _(
                    "Retired items require a retirement timestamp."
                )
        elif self.retired_at is not None:
            errors["retired_at"] = _(
                "Only retired items may carry a retirement timestamp."
            )

        if errors:
            raise ValidationError(errors)


class InventoryTransfer(models.Model):
    """Audited record of an inventory item moving between offices.

    The item row is updated in place so reservation history keyed by
    ``InventoryItem.public_id`` is preserved across transfers.
    """

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        related_name="transfers",
        verbose_name=_("item"),
    )
    from_office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        related_name="inventory_transfers_from",
        verbose_name=_("from office"),
    )
    to_office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        related_name="inventory_transfers_to",
        verbose_name=_("to office"),
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="inventory_transfers_performed",
        verbose_name=_("performed by"),
    )
    reason = models.TextField(_("reason"), blank=True)
    performed_at = models.DateTimeField(_("performed at"), default=timezone.now)

    if TYPE_CHECKING:
        item_id: int
        from_office_id: int
        to_office_id: int
        performed_by_id: int | None

    class Meta:
        ordering = ["-performed_at", "-pk"]
        verbose_name = _("inventory transfer")
        verbose_name_plural = _("inventory transfers")
        indexes = [
            models.Index(fields=["item", "-performed_at"], name="inv_xfer_item_time"),
            models.Index(fields=["from_office"], name="inv_xfer_from_idx"),
            models.Index(fields=["to_office"], name="inv_xfer_to_idx"),
        ]

    def __str__(self) -> str:
        item_id = getattr(self, "item_id", None)
        from_id = getattr(self, "from_office_id", None)
        to_id = getattr(self, "to_office_id", None)
        return f"{item_id}: {from_id} → {to_id}"


class ReservationQuerySet(models.QuerySet["InventoryReservation"]):
    def capacity_consuming(self) -> ReservationQuerySet:
        return self.filter(status__in=_CAPACITY)

    def for_owner(self, user) -> ReservationQuerySet:
        if getattr(user, "is_anonymous", False):
            return self.none()
        return self.filter(owner=user)

    def overlapping(self, *, item_id: int, starts_at, ends_at) -> ReservationQuerySet:
        """Half-open overlap:
        ``starts_at < other.ends_at AND ends_at > other.starts_at``.
        """
        return self.capacity_consuming().filter(
            item_id=item_id,
            starts_at__lt=ends_at,
            ends_at__gt=starts_at,
        )


class InventoryReservation(models.Model):
    """One hold of office inventory for a pickup/return interval.

    Capacity is never stored as a counter. Overlapping quantity is derived from
    rows in :data:`~apps.inventory.reservation_taxonomy.CAPACITY_CONSUMING_STATES`
    via :mod:`apps.inventory.availability`.
    """

    public_id = models.UUIDField(
        _("public id"), default=uuid.uuid4, editable=False, unique=True
    )
    reference = models.CharField(_("reference"), max_length=24, unique=True, blank=True)
    item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        related_name="reservations",
        verbose_name=_("item"),
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inventory_reservations",
        verbose_name=_("owner"),
        help_text=_("The agent the reservation belongs to."),
    )
    #: Owning office snapshotted at create so transfers do not rewrite history.
    office = models.ForeignKey(
        Office,
        on_delete=models.PROTECT,
        related_name="inventory_reservations",
        verbose_name=_("office at reservation"),
    )
    office_name = models.CharField(_("office name snapshot"), max_length=200)
    item_name = models.CharField(_("item name snapshot"), max_length=200)
    starts_at = models.DateTimeField(_("pickup starts at"))
    ends_at = models.DateTimeField(_("return ends at"))
    quantity = models.PositiveIntegerField(_("quantity"), default=1)
    purpose = models.CharField(_("business purpose"), max_length=240, blank=True)
    status = models.CharField(
        _("status"),
        max_length=32,
        choices=STATUS_CHOICES,
        default=ReservationStatus.CONFIRMED,
    )
    instructions_snapshot = models.TextField(
        _("pickup/return instructions snapshot"), blank=True
    )
    storage_location_snapshot = models.CharField(
        _("storage location snapshot"), max_length=200, blank=True
    )
    #: Client idempotency key. Unique so double-submit returns the first row.
    submission_key = models.CharField(
        _("submission key"), max_length=64, unique=True, editable=False
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_reservations_created",
        verbose_name=_("created by"),
    )
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_reservations_cancelled",
        verbose_name=_("cancelled by"),
    )
    cancel_reason = models.CharField(_("cancel reason"), max_length=240, blank=True)
    approved_at = models.DateTimeField(_("approved at"), null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_reservations_approved",
        verbose_name=_("approved by"),
    )
    denied_at = models.DateTimeField(_("denied at"), null=True, blank=True)
    denied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_reservations_denied",
        verbose_name=_("denied by"),
    )
    deny_reason = models.CharField(_("deny reason"), max_length=240, blank=True)
    ready_at = models.DateTimeField(_("ready at"), null=True, blank=True)
    ready_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_reservations_ready",
        verbose_name=_("marked ready by"),
    )
    checked_out_at = models.DateTimeField(_("checked out at"), null=True, blank=True)
    checked_out_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_reservations_checked_out",
        verbose_name=_("checked out by"),
    )
    checkout_quantity = models.PositiveIntegerField(
        _("checkout quantity"), null=True, blank=True
    )
    checkout_notes = models.CharField(_("checkout notes"), max_length=240, blank=True)
    returned_at = models.DateTimeField(_("returned at"), null=True, blank=True)
    returned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_reservations_returned",
        verbose_name=_("return accepted by"),
    )
    return_quantity = models.PositiveIntegerField(
        _("return quantity"), null=True, blank=True
    )
    return_condition_notes = models.CharField(
        _("return condition notes"), max_length=240, blank=True
    )
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_reservations_completed",
        verbose_name=_("completed by"),
    )
    overdue_at = models.DateTimeField(_("overdue at"), null=True, blank=True)
    lost_at = models.DateTimeField(_("lost at"), null=True, blank=True)
    lost_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_reservations_lost",
        verbose_name=_("marked lost by"),
    )
    lost_reason = models.CharField(_("lost reason"), max_length=240, blank=True)
    damaged_at = models.DateTimeField(_("damaged at"), null=True, blank=True)
    damaged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_reservations_damaged",
        verbose_name=_("marked damaged by"),
    )
    damaged_reason = models.CharField(_("damaged reason"), max_length=240, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    if TYPE_CHECKING:
        item_id: int
        owner_id: int
        office_id: int
        created_by_id: int | None
        cancelled_by_id: int | None
        approved_by_id: int | None
        denied_by_id: int | None
        ready_by_id: int | None
        checked_out_by_id: int | None
        returned_by_id: int | None
        completed_by_id: int | None
        lost_by_id: int | None
        damaged_by_id: int | None

    objects = ReservationQuerySet.as_manager()

    class Meta:
        ordering = ["-starts_at", "-pk"]
        verbose_name = _("inventory reservation")
        verbose_name_plural = _("inventory reservations")
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gte=1),
                name="inventory_reservation_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")),
                name="inventory_reservation_ends_after_starts",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=ReservationStatus.CANCELLED, cancelled_at__isnull=False)
                    | (
                        ~Q(status=ReservationStatus.CANCELLED)
                        & Q(cancelled_at__isnull=True)
                    )
                ),
                name="inventory_reservation_cancelled_at_matches",
            ),
        ]
        indexes = [
            models.Index(
                fields=["item", "status", "starts_at", "ends_at"],
                name="inv_rsv_item_status_range",
            ),
            models.Index(
                fields=["owner", "-starts_at"],
                name="inv_rsv_owner_starts",
            ),
            models.Index(
                fields=["office", "status"],
                name="inv_rsv_office_status",
            ),
            models.Index(fields=["status", "ends_at"], name="inv_rsv_status_ends"),
        ]

    def __str__(self) -> str:
        return self.reference or str(self.public_id)

    @property
    def status_label(self) -> str:
        return str(STATUS_LABELS.get(self.status, self.status))

    @property
    def consumes_capacity(self) -> bool:
        return self.status in CAPACITY_CONSUMING_STATES

    def save(self, *args, **kwargs):
        """Refuse unguarded status mutations outside the lifecycle service."""
        if self.pk:
            from apps.inventory.reservation_lifecycle import status_write_allowed

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
                            "Reservation status may only change through the "
                            "lifecycle transition service."
                        )
                    }
                )
        super().save(*args, **kwargs)


class ReservationTransitionEvent(models.Model):
    """Immutable reservation lifecycle history — never deleted to fix mistakes."""

    reservation = models.ForeignKey(
        InventoryReservation,
        on_delete=models.CASCADE,
        related_name="transition_events",
        verbose_name=_("reservation"),
    )
    action = models.CharField(_("action"), max_length=32)
    from_status = models.CharField(_("from status"), max_length=32)
    to_status = models.CharField(_("to status"), max_length=32)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_reservation_transitions",
        verbose_name=_("actor"),
    )
    reason = models.CharField(_("reason"), max_length=240, blank=True)
    notes = models.CharField(_("notes"), max_length=240, blank=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)
    idempotency_key = models.CharField(
        _("idempotency key"), max_length=64, blank=True, db_index=True
    )
    occurred_at = models.DateTimeField(_("occurred at"), auto_now_add=True)

    if TYPE_CHECKING:
        reservation_id: int
        actor_id: int | None

    class Meta:
        ordering = ["occurred_at", "pk"]
        verbose_name = _("reservation transition event")
        verbose_name_plural = _("reservation transition events")
        indexes = [
            models.Index(
                fields=["reservation", "occurred_at"],
                name="inv_rsv_evt_res_occ",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.action}: {self.from_status} → {self.to_status}"
