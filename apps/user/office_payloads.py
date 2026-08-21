"""Small view-model helpers for office data exposure.

These helpers keep internal operational fields out of generic callers while
letting admin/internal surfaces opt into richer data.
"""

from __future__ import annotations

from typing import Any

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
