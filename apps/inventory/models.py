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
