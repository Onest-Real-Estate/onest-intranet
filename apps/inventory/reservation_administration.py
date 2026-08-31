"""Scoped inventory reservation administration queries."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.utils.translation import gettext_lazy as _

from apps.inventory.models import InventoryReservation
from apps.inventory.reservation_taxonomy import (
    STATUS_CODES,
    STATUS_LABELS,
    ReservationPermission,
)
from apps.user.models import User
from apps.user.services.hierarchy import descendant_queryset
from apps.user.services.role_assignments import (
    get_effective_access,
    has_effective_permission,
)
from apps.web.contracts import list_response

PAGE_SIZE = 25


@dataclass(frozen=True)
class ReservationScope:
    office_ids: frozenset[int]


@dataclass(frozen=True)
class AdminReservationFilters:
    q: str = ""
    status: str = ""

    def as_payload(self) -> dict[str, str]:
        return {"q": self.q, "status": self.status}


def _has_permission(actor: User, codename: str) -> bool:
    if getattr(actor, "is_superuser", False):
        return True
    return has_effective_permission(actor, codename)


def reservation_scope(actor: User) -> ReservationScope:
    access = get_effective_access(actor)
    assignable = Q(is_active=True, is_assignable=True)
    from apps.user.models import Office

    ids: set[int] = set()
    if getattr(actor, "is_superuser", False) or access.company_wide:
        ids.update(Office.objects.filter(assignable).values_list("pk", flat=True))
        return ReservationScope(office_ids=frozenset(ids))

    if access.region_keys:
        regions = Office.objects.filter(
            kind=Office.Kind.REGION, stable_key__in=access.region_keys
        )
        for region in regions:
            ids.update(
                descendant_queryset(region)
                .filter(assignable)
                .values_list("pk", flat=True)
            )
    if access.office_keys:
        seats = Office.objects.filter(stable_key__in=access.office_keys)
        for seat in seats:
            if seat.is_assignable and seat.is_active:
                ids.add(seat.pk)
            if seat.kind != Office.Kind.BRANCH:
                ids.update(
                    descendant_queryset(seat)
                    .filter(assignable)
                    .values_list("pk", flat=True)
                )
    return ReservationScope(office_ids=frozenset(ids))


def can_view_reservations(actor: User) -> bool:
    return _has_permission(actor, ReservationPermission.VIEW)


def can_approve_reservations(actor: User) -> bool:
    return _has_permission(actor, ReservationPermission.APPROVE)


def can_override_reservations(actor: User) -> bool:
    return _has_permission(actor, ReservationPermission.OVERRIDE)


def ensure_view_authority(actor: User) -> ReservationScope:
    if not can_view_reservations(actor):
        raise PermissionDenied(_("You do not have permission to view reservations."))
    return reservation_scope(actor)


def managed_reservation_queryset(actor: User) -> QuerySet[InventoryReservation]:
    scope = ensure_view_authority(actor)
    qs = (
        InventoryReservation.objects.filter(office_id__in=scope.office_ids)
        .select_related("item", "owner", "office")
        .prefetch_related("transition_events__actor")
        .order_by("-starts_at", "-pk")
    )
    return qs


def load_reservation(actor: User, public_id) -> InventoryReservation | None:
    return managed_reservation_queryset(actor).filter(public_id=public_id).first()


def parse_filters(params) -> AdminReservationFilters:
    status = (params.get("status") or "").strip()
    if status not in STATUS_CODES:
        status = ""
    return AdminReservationFilters(
        q=(params.get("q") or "").strip()[:120],
        status=status,
    )


def apply_filters(
    queryset: QuerySet[InventoryReservation], filters: AdminReservationFilters
) -> QuerySet[InventoryReservation]:
    qs = queryset
    if filters.status:
        qs = qs.filter(status=filters.status)
    if filters.q:
        term = filters.q
        qs = qs.filter(
            Q(reference__icontains=term)
            | Q(item_name__icontains=term)
            | Q(purpose__icontains=term)
            | Q(owner__email__icontains=term)
            | Q(owner__first_name__icontains=term)
            | Q(owner__last_name__icontains=term)
        )
    return qs


def build_admin_list(
    actor: User,
    *,
    params,
    page: int = 1,
) -> dict:
    from apps.inventory.reservation_lifecycle import sync_overdue_reservations
    from apps.inventory.reservation_payloads import reservation_row

    sync_overdue_reservations()
    filters = parse_filters(params)
    qs = apply_filters(managed_reservation_queryset(actor), filters)
    total = qs.count()
    start = max(page - 1, 0) * PAGE_SIZE
    rows = [reservation_row(row, admin=True) for row in qs[start : start + PAGE_SIZE]]
    return {
        "reservations": list_response(
            rows,
            page=page,
            page_size=PAGE_SIZE,
            total_items=total,
            filters=filters.as_payload(),
        ),
        "filterOptions": {
            "statuses": [
                {"value": code, "label": str(label)}
                for code, label in sorted(STATUS_LABELS.items(), key=lambda row: row[1])
            ],
        },
        "can": {
            "approve": can_approve_reservations(actor),
            "override": can_override_reservations(actor),
        },
    }
