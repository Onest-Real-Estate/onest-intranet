"""Server-owned create/prepare field schema for the guided transaction form.

The frontend mirrors required markers from this payload. Validation still runs
exclusively on the server via :data:`REQUIRED_FIELDS` and the helpers here.
"""

from __future__ import annotations

from typing import Any

from apps.transactions.taxonomy import (
    REPRESENTATION_CODES,
    REPRESENTATION_LABELS,
    REQUIRED_FIELDS,
    TYPE_CODES,
    TYPE_LABELS,
    RepresentationType,
    TransactionStatus,
    TransactionType,
)

#: Fields collected on the guided create form, in display order within sections.
CREATE_SECTIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "classification",
        "label": "Transaction type",
        "fields": ("transactionType", "representationType"),
    },
    {
        "id": "property",
        "label": "Property",
        "fields": (
            "propertyLine1",
            "propertyLine2",
            "propertyCity",
            "propertyState",
            "propertyPostalCode",
            "mlsNumber",
        ),
    },
    {
        "id": "parties",
        "label": "Clients / parties",
        "fields": ("clientName", "clientEmail", "clientPhone", "clientRole"),
    },
    {
        "id": "assignments",
        "label": "Agents and office",
        "fields": (
            "officeKey",
            "primaryAgentId",
            "coAgentId",
            "coordinatorId",
        ),
    },
    {
        "id": "commercial",
        "label": "Prices and dates",
        "fields": (
            "listPrice",
            "contractPrice",
            "acceptanceDate",
            "closingDate",
        ),
    },
    {
        "id": "vendors",
        "label": "Vendors and referral",
        "fields": ("lenderRef", "titleRef", "referralRef"),
    },
)

#: camelCase form keys → model / nested attribute names used by validators.
FORM_FIELD_TO_MODEL: dict[str, str] = {
    "transactionType": "transaction_type",
    "representationType": "representation_type",
    "officeKey": "office",
    "primaryAgentId": "primary_agent",
    "coAgentId": "co_agent",
    "coordinatorId": "coordinator",
    "propertyLine1": "property_snapshot",
    "propertyLine2": "property_snapshot",
    "propertyCity": "property_snapshot",
    "propertyState": "property_snapshot",
    "propertyPostalCode": "property_snapshot",
    "mlsNumber": "mls_number",
    "clientName": "client_snapshots",
    "clientEmail": "client_snapshots",
    "clientPhone": "client_snapshots",
    "clientRole": "client_snapshots",
    "listPrice": "list_price",
    "contractPrice": "contract_price",
    "acceptanceDate": "acceptance_date",
    "closingDate": "closing_date",
    "lenderRef": "lender_ref",
    "titleRef": "title_ref",
    "referralRef": "referral_ref",
}

#: Representation codes allowed for each transaction type.
TYPE_REPRESENTATION_ALLOWLIST: dict[str, frozenset[str]] = {
    TransactionType.BUY: frozenset(
        {
            RepresentationType.BUYER,
            RepresentationType.DUAL,
        }
    ),
    TransactionType.SELL: frozenset(
        {
            RepresentationType.SELLER,
            RepresentationType.DUAL,
        }
    ),
    TransactionType.RENT: frozenset(
        {
            RepresentationType.LANDLORD,
            RepresentationType.TENANT,
            RepresentationType.DUAL,
        }
    ),
}


def allowed_representations_for(transaction_type: str) -> list[dict[str, str]]:
    allowed = TYPE_REPRESENTATION_ALLOWLIST.get(transaction_type, REPRESENTATION_CODES)
    return [
        {"value": code, "label": str(REPRESENTATION_LABELS[code])}
        for code in sorted(allowed)
        if code in REPRESENTATION_LABELS
    ]


def _draft_required(transaction_type: str, representation_type: str) -> set[str]:
    required = {
        FORM_FIELD_TO_MODEL[k]
        for k, v in FORM_FIELD_TO_MODEL.items()
        if v in REQUIRED_FIELDS[TransactionStatus.DRAFT]
    }
    # Always require the classification pair on the form.
    required.update({"transaction_type", "representation_type", "office"})
    _ = (transaction_type, representation_type)  # reserved for jurisdiction rules
    return required


def _preparing_required(
    transaction_type: str,
    representation_type: str,
    *,
    jurisdiction: str,
) -> set[str]:
    required = set(REQUIRED_FIELDS[TransactionStatus.PREPARING])
    # Street address is expected before preparing so the workspace has a
    # usable property label; MLS stays optional for private sales.
    required.add("property_snapshot")
    if representation_type == RepresentationType.DUAL:
        # Dual representation still needs at least one named client party.
        required.add("client_snapshots")
    if jurisdiction.upper() in {"VA", "MD", "DC"} and transaction_type in {
        TransactionType.BUY,
        TransactionType.SELL,
    }:
        # Hub markets collect MLS when present; still optional if blank at
        # prepare — no hard require, but schema marks it recommended.
        pass
    return required


def build_create_schema(
    *,
    transaction_type: str = "",
    representation_type: str = "",
    jurisdiction: str = "",
    stage: str = "draft",
    lock_office: bool = False,
    lock_primary_agent: bool = False,
) -> dict[str, Any]:
    """CamelCase schema prop for the create page.

    ``stage`` is ``draft`` (save) or ``preparing`` (final prepare validation).
    """
    txn_type = transaction_type if transaction_type in TYPE_CODES else ""
    rep = representation_type if representation_type in REPRESENTATION_CODES else ""
    if stage == "preparing":
        model_required = _preparing_required(txn_type, rep, jurisdiction=jurisdiction)
    else:
        model_required = _draft_required(txn_type, rep)

    form_required: list[str] = []
    for form_key, model_key in FORM_FIELD_TO_MODEL.items():
        if model_key in model_required:
            if form_key.startswith("property") and model_key == "property_snapshot":
                if form_key == "propertyLine1":
                    form_required.append(form_key)
                continue
            if form_key.startswith("client") and model_key == "client_snapshots":
                if form_key == "clientName":
                    form_required.append(form_key)
                continue
            form_required.append(form_key)

    locked: list[str] = []
    if lock_office:
        locked.append("officeKey")
    if lock_primary_agent:
        locked.append("primaryAgentId")

    return {
        "stage": stage,
        "sections": list(CREATE_SECTIONS),
        "requiredFields": sorted(set(form_required)),
        "lockedFields": locked,
        "transactionTypes": [
            {"value": code, "label": str(TYPE_LABELS[code])}
            for code in sorted(TYPE_CODES)
        ],
        "representationTypes": allowed_representations_for(txn_type)
        if txn_type
        else [
            {"value": code, "label": str(REPRESENTATION_LABELS[code])}
            for code in sorted(REPRESENTATION_CODES)
        ],
        "jurisdiction": jurisdiction or "",
    }


def assert_type_representation_pair(
    transaction_type: str, representation_type: str
) -> None:
    from django.core.exceptions import ValidationError

    allowed = TYPE_REPRESENTATION_ALLOWLIST.get(transaction_type)
    if allowed is None:
        raise ValidationError({"transactionType": ["Unknown transaction type."]})
    if representation_type not in allowed:
        raise ValidationError(
            {
                "representationType": [
                    "This representation is not valid for the selected "
                    "transaction type."
                ]
            }
        )


__all__ = [
    "CREATE_SECTIONS",
    "FORM_FIELD_TO_MODEL",
    "TYPE_REPRESENTATION_ALLOWLIST",
    "allowed_representations_for",
    "assert_type_representation_pair",
    "build_create_schema",
]
