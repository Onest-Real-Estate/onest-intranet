"""Office confirmation and deterministic onboarding-admin resolution.

The selected office remains owned by :class:`apps.user.models.User`; public
office facts and effective-dated contacts remain owned by the office domain.
This module only composes the self-safe confirmation card and the recipient
policy used by the onboarding handoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.user.models import Office, OfficeContactAssignment, User, UserOnboardingCase

OFFICE_CONFIRMATION_FIELD = "confirm_office"
CONFIRMED_OFFICE_FIELD = "confirmed_office_id"
OFFICE_HANDOFF_EVENT = "user.onboarding.office_handoff_requested"


class OfficeAdminResolutionLevel(StrEnum):
    OFFICE = "office"
    REGION = "region"
    COMPANY = "company"
    UNAVAILABLE = "unavailable"


class DefaultOnboardingOwnerPolicy(StrEnum):
    """Product-owned policy for new cases; explicit owners always win."""

    RESOLVED_OFFICE_ADMIN = "resolved_office_admin"


DEFAULT_OWNER_POLICY = DefaultOnboardingOwnerPolicy.RESOLVED_OFFICE_ADMIN


def office_confirmation_is_current(user: User, case: UserOnboardingCase | None) -> bool:
    return bool(
        case
        and case.office_confirmed_at
        and getattr(case, "office_confirmed_for_id", None)
        == getattr(user, "office_id", None)
        and case.office_confirmation_version == user.onboarding_version
    )


@dataclass(frozen=True)
class ResolvedOfficeAdministrator:
    user: User
    assignment: OfficeContactAssignment
    level: OfficeAdminResolutionLevel
    source_office: Office


class OfficeHandoffDeliveryUnavailable(RuntimeError):
    """The durable in-app handoff does not exist yet; the outbox should retry."""


def _fallback_offices(
    office: Office,
) -> tuple[tuple[OfficeAdminResolutionLevel, Office], ...]:
    """Return office → region → company nodes once, in product-policy order."""
    candidates: list[tuple[OfficeAdminResolutionLevel, Office]] = [
        (OfficeAdminResolutionLevel.OFFICE, office)
    ]
    seen = {office.pk}
    region = office.region
    if region is not None and region.pk not in seen:
        candidates.append((OfficeAdminResolutionLevel.REGION, region))
        seen.add(region.pk)

    node = office
    visited: set[int] = set()
    head: Office | None = None
    while node is not None and node.pk not in visited:
        visited.add(node.pk)
        if node.kind == Office.Kind.HEAD_OFFICE:
            head = node
            break
        node = node.parent
    if head is not None and head.pk not in seen:
        candidates.append((OfficeAdminResolutionLevel.COMPANY, head))
    return tuple(candidates)


def resolve_office_administrator(
    office: Office, *, on_date: date | None = None
) -> ResolvedOfficeAdministrator | None:
    """Resolve one current Branch Admin with a bounded, deterministic query.

    Contacts outside the selected office's approved fallback chain are never
    loaded. Inactive users and future/expired assignments are excluded at the
    database boundary. There is no out-of-office source in the current model;
    adding one belongs here as a future availability adapter.
    """
    candidates = _fallback_offices(office)
    by_id = {
        node.pk: (index, level, node) for index, (level, node) in enumerate(candidates)
    }
    today = on_date or timezone.localdate()
    assignments = list(
        OfficeContactAssignment.objects.filter(
            office_id__in=by_id,
            assignment_type=OfficeContactAssignment.AssignmentType.ADMIN,
            user__is_active=True,
        )
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=today))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=today))
        .select_related("user", "office")
    )
    if not assignments:
        return None
    assignments.sort(
        key=lambda item: (
            by_id[item.office_id][0],
            not item.is_primary,
            item.user.email.casefold(),
            item.user_id,
        )
    )
    assignment = assignments[0]
    _, level, source_office = by_id[assignment.office_id]
    return ResolvedOfficeAdministrator(
        user=assignment.user,
        assignment=assignment,
        level=level,
        source_office=source_office,
    )


def office_confirmation_payload(
    office: Office,
    *,
    resolution: ResolvedOfficeAdministrator | None = None,
) -> dict[str, Any]:
    """Public office card plus only the administrator relevant to this office."""
    resolved = (
        resolution if resolution is not None else resolve_office_administrator(office)
    )
    administrator = None
    if resolved is not None:
        administrator = {
            "id": resolved.user.pk,
            "name": resolved.user.get_full_name()
            or resolved.user.display_name
            or resolved.user.email,
            "phone": resolved.user.phone_number or "",
            "email": resolved.user.email,
            "isPrimary": resolved.assignment.is_primary,
            "resolutionLevel": str(resolved.level),
            "resolutionLabel": {
                OfficeAdminResolutionLevel.OFFICE: "Office Branch Admin",
                OfficeAdminResolutionLevel.REGION: "Regional Branch Admin",
                OfficeAdminResolutionLevel.COMPANY: "Company Branch Admin",
            }[resolved.level],
        }
    return {
        "office": {
            "id": office.pk,
            "name": office.name,
            "hierarchy": office.path_label(),
            "region": office.region_name(),
            "streetAddress": office.street_address,
            "city": office.city,
            "state": office.state,
            "zipCode": office.zip_code,
            "mainPhone": office.main_phone,
            "publicEmail": office.public_email,
            "officeHours": office.office_hours,
        },
        "administrator": administrator,
        "support": {
            "available": administrator is None,
            "message": (
                "No current office administrator is available. Finish your profile, "
                "then contact IT Support from the Hub so the onboarding team can route "
                "your case."
                if administrator is None
                else ""
            ),
        },
    }


def handoff_dedupe_key(*, user_id: int, onboarding_version: int, office_id: int) -> str:
    return (
        f"office-handoff:user:{user_id}:version:{onboarding_version}:office:{office_id}"
    )


def record_office_handoff_delivery(
    *, user_id: int, office_id: int, onboarding_version: int, recipient_id: int
) -> None:
    """Reflect durable notification creation onto the current onboarding case.

    The notification row remains the delivery source of truth. This state is
    the small journey checkpoint used by the agent-facing composer. A replay
    for an older office or reset cycle never changes the current case.
    """
    from apps.audit.events import publish
    from apps.audit.service import AuditTarget, log_event, system_actor
    from apps.notifications.models import Notification
    from apps.user.models import UserOnboardingCase

    notification_exists = False
    with transaction.atomic():
        case = (
            UserOnboardingCase.objects.select_for_update(of=("self",))
            .select_related("user", "user__office")
            .filter(user_id=user_id)
            .first()
        )
        if case is None:
            raise OfficeHandoffDeliveryUnavailable("Onboarding case is unavailable.")
        if (
            case.user.onboarding_version != onboarding_version
            or getattr(case.user, "office_id", None) != office_id
            or case.office_handoff_onboarding_version != onboarding_version
            or getattr(case, "office_handoff_office_id", None) != office_id
        ):
            return

        notification_exists = Notification.objects.filter(
            recipient_id=recipient_id,
            dedupe_key=handoff_dedupe_key(
                user_id=user_id,
                onboarding_version=onboarding_version,
                office_id=office_id,
            ),
        ).exists()
        next_state = (
            UserOnboardingCase.OfficeHandoffState.NOTIFIED
            if notification_exists
            else UserOnboardingCase.OfficeHandoffState.NOTIFICATION_FAILED
        )
        previous = UserOnboardingCase.OfficeHandoffState(case.office_handoff_state)
        if previous != next_state:
            now = timezone.now()
            case.office_handoff_state = next_state
            case.office_handoff_updated_at = now
            case.updated_at = now
            case.save(
                update_fields=[
                    "office_handoff_state",
                    "office_handoff_updated_at",
                    "updated_at",
                ]
            )
            log_event(
                "user.onboarding.office_handoff_delivery_recorded",
                actor=system_actor(),
                target=AuditTarget(
                    target_type=UserOnboardingCase._meta.label_lower,
                    target_id=str(user_id),
                    target_label=f"User {user_id}",
                ),
                before={"state": str(previous)},
                after={"state": str(next_state)},
                channel="notifications",
                office_id=case.user.office.stable_key if case.user.office else "",
            )
            publish(
                "user.onboarding.office_handoff_changed",
                subject=f"user:{user_id}",
                payload={
                    "user_id": user_id,
                    "from": str(previous),
                    "to": str(next_state),
                },
            )
    if not notification_exists:
        raise OfficeHandoffDeliveryUnavailable(
            "The scoped onboarding notification was not durably recorded."
        )
