"""Issuance snapshots: freeze party, office, and commercial facts.

Profile and office rows keep changing. A signed (or even drafted-for-issue)
contract must not silently rewrite its legal identity when someone later edits
a name or address. Snapshots are plain JSON dicts stored on the contract row;
rebuild only through an explicit amendment/replacement workflow.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from apps.user.models import Office, User


def _dec(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def party_snapshot(user: User) -> dict[str, Any]:
    """Legal party facts for the recipient agent at snapshot time."""
    return {
        "userId": user.pk,
        "email": user.email,
        "displayName": user.preferred_display_name(),
        "legalFirstName": user.first_name,
        "legalLastName": user.last_name,
        "agentIdentifier": user.agent_identifier or "",
        "licenseNumber": user.license_number or "",
        "licenseState": user.license_state or "",
        "agentStatus": user.agent_status,
    }


def office_snapshot(office: Office) -> dict[str, Any]:
    """Owning office identity and mailing address at snapshot time."""
    region = office.region if office.region_id else None
    return {
        "officeId": office.pk,
        "stableKey": office.stable_key,
        "name": office.name,
        "kind": office.kind,
        "streetAddress": office.street_address or "",
        "city": office.city or "",
        "state": office.state or "",
        "zipCode": office.zip_code or "",
        "mainPhone": office.main_phone or "",
        "publicEmail": office.public_email or "",
        "regionStableKey": region.stable_key if region is not None else None,
        "regionName": region.name if region is not None else None,
    }


def terms_snapshot_from_contract(contract) -> dict[str, Any]:
    """Rendered commercial terms copied from the contract's structured fields."""
    return {
        "agentSplitPercent": _dec(contract.agent_split_percent),
        "officeSplitPercent": _dec(contract.office_split_percent),
        "transactionFeeAmount": _dec(contract.transaction_fee_amount),
        "transactionFeePercent": _dec(contract.transaction_fee_percent),
        "annualCapAmount": _dec(contract.annual_cap_amount),
        "specialArrangements": contract.special_arrangements or "",
        "addendaReferences": list(contract.addenda_references or []),
        "mentor": {
            "percent": _dec(contract.mentor_percent),
            "fixedAmount": _dec(contract.mentor_fixed_amount),
            "capAmount": _dec(contract.mentor_cap_amount),
            "basis": contract.mentor_basis or "",
            "payeeId": contract.mentor_payee_id,
            "notes": contract.mentor_notes or "",
        },
        "referral": {
            "percent": _dec(contract.referral_percent),
            "fixedAmount": _dec(contract.referral_fixed_amount),
            "capAmount": _dec(contract.referral_cap_amount),
            "basis": contract.referral_basis or "",
            "payeeId": contract.referral_payee_id,
            "notes": contract.referral_notes or "",
        },
    }
