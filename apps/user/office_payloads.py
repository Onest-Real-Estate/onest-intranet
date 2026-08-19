"""Small view-model helpers for office data exposure.

These helpers keep internal operational fields out of generic callers while
letting admin/internal surfaces opt into richer data.
"""

from __future__ import annotations

from apps.user.models import Office


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
