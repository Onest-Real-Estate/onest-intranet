"""Small view-model helpers for office data exposure.

These helpers keep internal operational fields out of generic callers while
letting admin/internal surfaces opt into richer data.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from django.utils import timezone

from apps.user.models import Office, OfficeContactAssignment


def office_selector_payload(office: Office) -> dict:
    return {
        "id": office.pk,
        "name": office.name,
        "slug": office.slug,
        "stableKey": office.stable_key,
        "region": office.region_name(),
        "isActive": office.is_active,
        "isAssignable": office.is_assignable,
    }


def office_summary_payload(office: Office) -> dict:
    return {
        "id": office.pk,
        "name": office.name,
        "slug": office.slug,
        "stableKey": office.stable_key,
        "kind": office.kind,
        "pathLabel": office.path_label(),
        "isActive": office.is_active,
        "streetAddress": office.street_address,
        "city": office.city,
        "state": office.state,
        "zipCode": office.zip_code,
        "mainPhone": office.main_phone,
        "publicEmail": office.public_email,
        "officeHours": office.office_hours,
        "parkingInstructions": office.parking_instructions,
    }


def office_internal_payload(office: Office) -> dict:
    payload = office_summary_payload(office)
    payload.update(
        {
            "internalEmail": office.internal_email,
            "accessInstructions": office.access_instructions,
            "accessInstructionsInternal": office.access_instructions_internal,
        }
    )
    return payload


def _contact_person(
    assignment: OfficeContactAssignment | None,
) -> dict[str, Any] | None:
    if assignment is None:
        return None
    user = assignment.user
    return {
        "id": user.pk,
        "displayName": user.get_full_name() or user.display_name or user.email,
        "email": user.email,
        "phoneNumber": user.phone_number or "",
        "isPrimary": assignment.is_primary,
        "assignmentType": assignment.assignment_type,
        "assignmentTypeLabel": OfficeContactAssignment.AssignmentType(
            assignment.assignment_type
        ).label,
    }


def _primary_or_first(
    assignments: list[OfficeContactAssignment],
) -> OfficeContactAssignment | None:
    if not assignments:
        return None
    for assignment in assignments:
        if assignment.is_primary:
            return assignment
    return assignments[0]


def office_directions_url(office: Office) -> str:
    """Approved external map destination (Google Maps URL API).

    Built from the public address fields only — no internal data is ever
    embedded in the query string.
    """
    parts = [office.street_address, office.city, office.state, office.zip_code]
    query = ", ".join(part for part in parts if part)
    if not query:
        return ""
    return f"https://www.google.com/maps/search/?api=1&{urlencode({'query': query})}"


def _head_office() -> Office | None:
    return (
        Office.objects.filter(kind=Office.Kind.HEAD_OFFICE, is_active=True)
        .order_by("pk")
        .first()
    )


def corporate_contacts_payload(*, on_date=None) -> list[dict[str, Any]]:
    """Company-level directory carried as head-office contact assignments.

    Ordered by role seniority (the corporate_types order), primary holder
    first within a role — not alphabetically by type code.
    """
    head = _head_office()
    if head is None:
        return []
    assignments = list(
        OfficeContactAssignment.current_queryset(head, on_date=on_date).filter(
            assignment_type__in=OfficeContactAssignment.corporate_types()
        )
    )
    order = {
        value: index
        for index, value in enumerate(OfficeContactAssignment.corporate_types())
    }
    assignments.sort(
        key=lambda item: (
            order.get(item.assignment_type, len(order)),
            not item.is_primary,
            item.user.email,
        )
    )
    people = (_contact_person(assignment) for assignment in assignments)
    return [person for person in people if person is not None]


def office_info_payload(office: Office, *, include_internal: bool = False) -> dict:
    """Agent-facing office brochure for one office.

    Always keyed by the office itself (id + updatedAt). Callers must never mix
    another office's body into a response for a different primary assignment.
    Internal fields are omitted unless ``include_internal`` is True.
    """
    current = list(OfficeContactAssignment.current_queryset(office))
    by_type: dict[str, list[OfficeContactAssignment]] = {}
    for assignment in current:
        by_type.setdefault(assignment.assignment_type, []).append(assignment)

    types = OfficeContactAssignment.AssignmentType
    payload: dict[str, Any] = {
        **office_summary_payload(office),
        "regionName": office.region_name(),
        "directionsUrl": office_directions_url(office),
        "updatedAt": office.updated_at.isoformat(),
        "version": f"{office.pk}:{office.updated_at.isoformat()}",
        "contacts": {
            "branchManager": _contact_person(
                _primary_or_first(by_type.get(types.MANAGER, []))
            ),
            "branchAdmin": _contact_person(
                _primary_or_first(by_type.get(types.ADMIN, []))
            ),
            "brokers": [
                person
                for person in (
                    _contact_person(item)
                    for item in by_type.get(types.BROKER_CONTACT, [])
                )
                if person is not None
            ],
            "transactionCoordinator": _contact_person(
                _primary_or_first(by_type.get(types.TRANSACTION_COORDINATOR, []))
            ),
            "itSupport": _contact_person(
                _primary_or_first(by_type.get(types.IT_SUPPORT, []))
            ),
        },
        "corporateContacts": corporate_contacts_payload(),
        "includeInternal": include_internal,
    }
    if include_internal:
        payload["internalEmail"] = office.internal_email
        if office.access_instructions_internal:
            payload["accessInstructions"] = office.access_instructions
            payload["accessInstructionsInternal"] = True
        else:
            # Public access copy can still appear on the agent page.
            payload["accessInstructions"] = office.access_instructions
            payload["accessInstructionsInternal"] = False
    else:
        # Never embed internal instructions in a non-internal payload.
        if not office.access_instructions_internal:
            payload["accessInstructions"] = office.access_instructions
            payload["accessInstructionsInternal"] = False
        else:
            payload["accessInstructions"] = ""
            payload["accessInstructionsInternal"] = True
        payload["internalEmail"] = ""
    # Stamp generation time so caches cannot silently reuse another office.
    payload["generatedAt"] = timezone.now().isoformat()
    return payload
