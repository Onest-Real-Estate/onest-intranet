"""Guided create / draft / prepare workflow for transactions.

Creator rules
-------------
- ``web.manage_transactions``: office and people must sit inside effective scope.
- ``web.create_own_transactions``: primary agent is forced to the actor; office
  is forced to the actor's home office; crafted expansions are refused.

Idempotency
-----------
``submission_key`` on :class:`~apps.transactions.models.Transaction` makes
prepare safe under double-submit. A repeated key returns the same row without
a second create audit or prepare transition event.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.dateparse import parse_date

from apps.transactions.create_schema import (
    assert_type_representation_pair,
    build_create_schema,
)
from apps.transactions.lifecycle import transition
from apps.transactions.models import Transaction
from apps.transactions.permissions import (
    CREATE_OWN_TRANSACTIONS,
    MANAGE_TRANSACTIONS,
)
from apps.transactions.services import (
    ActorContext,
    _normalize_client_snapshots,
    _normalize_property_snapshot,
    create_draft,
    scoped_transaction_queryset,
    upsert_assignment,
)
from apps.transactions.taxonomy import (
    AssignmentRole,
    TransactionStatus,
)
from apps.user.models import Office, User
from apps.user.roles import REALTOR, TRANSACTION_COORDINATOR
from apps.user.services.role_assignments import (
    get_effective_access,
    has_effective_permission,
)

_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class CreatorMode:
    """Resolved create posture for the signed-in actor."""

    manage: bool
    create_own: bool

    @property
    def allowed(self) -> bool:
        return self.manage or self.create_own

    @property
    def lock_office(self) -> bool:
        return self.create_own and not self.manage

    @property
    def lock_primary_agent(self) -> bool:
        return self.create_own and not self.manage


def resolve_creator_mode(user: User) -> CreatorMode:
    if getattr(user, "is_superuser", False):
        return CreatorMode(manage=True, create_own=True)
    return CreatorMode(
        manage=has_effective_permission(user, MANAGE_TRANSACTIONS),
        create_own=has_effective_permission(user, CREATE_OWN_TRANSACTIONS),
    )


def require_creator(user: User) -> CreatorMode:
    mode = resolve_creator_mode(user)
    if not mode.allowed:
        raise PermissionDenied("You do not have permission to create a transaction.")
    return mode


def actor_context(user: User) -> ActorContext:
    access = get_effective_access(user)
    return ActorContext(user=user, permissions=frozenset(access.permissions))


def _office_in_actor_scope(user: User, office: Office, *, access=None) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    if access is None:
        access = get_effective_access(user)
    if access.company_wide:
        return True
    if office.stable_key in access.office_keys:
        return True
    region = office.region
    return bool(region is not None and region.stable_key in access.region_keys)


def scoped_offices_for_creator(user: User) -> list[Office]:
    mode = require_creator(user)
    access = get_effective_access(user)
    if mode.lock_office:
        home = getattr(user, "office", None)
        return [home] if home is not None else []
    if getattr(user, "is_superuser", False) or access.company_wide:
        return list(Office.objects.order_by("name", "pk"))
    filters = Q(pk__in=[])
    if access.office_keys:
        filters |= Q(stable_key__in=sorted(access.office_keys))
    if access.region_keys:
        filters |= Q(region__stable_key__in=sorted(access.region_keys))
    return list(Office.objects.filter(filters).distinct().order_by("name", "pk"))


def scoped_people_queryset(user: User, *, role: str = "agent"):
    """People an actor may assign, scoped before serialization."""
    mode = require_creator(user)
    access = get_effective_access(user)
    qs = User.objects.filter(is_active=True, profile_completed=True)
    if mode.lock_office:
        home = getattr(user, "office", None)
        if home is None:
            return qs.none()
        qs = qs.filter(office=home)
    elif not (getattr(user, "is_superuser", False) or access.company_wide):
        office_filter = Q(pk__in=[])
        if access.office_keys:
            office_filter |= Q(office__stable_key__in=sorted(access.office_keys))
        if access.region_keys:
            office_filter |= Q(
                office__region__stable_key__in=sorted(access.region_keys)
            )
        qs = qs.filter(office_filter)

    if role == "coordinator":
        qs = qs.filter(
            role_assignments__role=TRANSACTION_COORDINATOR,
            role_assignments__status="active",
        )
    else:
        qs = qs.filter(
            role_assignments__role=REALTOR,
            role_assignments__status="active",
        )
    return qs.distinct().order_by("first_name", "last_name", "email", "pk")


def search_transaction_people(
    user: User, *, q: str, role: str = "agent", limit: int = 20
) -> list[dict[str, Any]]:
    qs = scoped_people_queryset(user, role=role)
    needle = (q or "").strip()
    if needle:
        qs = qs.filter(
            Q(email__icontains=needle)
            | Q(first_name__icontains=needle)
            | Q(last_name__icontains=needle)
            | Q(preferred_name__icontains=needle)
        )
    results: list[dict[str, Any]] = []
    for person in qs[: max(1, min(limit, 50))]:
        results.append(
            {
                "id": person.pk,
                "name": person.preferred_display_name()
                if hasattr(person, "preferred_display_name")
                else str(person),
                "email": person.email or "",
                "officeId": person.office_id,
                "officeName": person.office.name if person.office_id else "",
                "officeState": getattr(person.office, "state", "")
                if person.office_id
                else "",
                "officeKey": person.office.stable_key if person.office_id else "",
                "licenseState": getattr(person, "license_state", "") or "",
                "agentIdentifier": getattr(person, "agent_identifier", "") or "",
            }
        )
    return results


def _parse_money(raw: Any, field: str) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        return Decimal(str(raw).replace(",", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError({field: ["Enter a valid amount."]}) from exc


def _parse_date(raw: Any, field: str) -> date | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    parsed = parse_date(str(raw).strip())
    if parsed is None:
        raise ValidationError({field: ["Enter a valid date (YYYY-MM-DD)."]})
    return parsed


def _resolve_office(user: User, mode: CreatorMode, office_key: str | None) -> Office:
    if mode.lock_office:
        home = getattr(user, "office", None)
        if home is None:
            raise ValidationError(
                {"officeKey": ["Your profile needs a home office before creating."]}
            )
        if office_key and office_key != home.stable_key:
            raise ValidationError(
                {"officeKey": ["Agents create deals in their home office only."]}
            )
        return home
    key = (office_key or "").strip()
    if not key:
        raise ValidationError({"officeKey": ["An owning office is required."]})
    office = Office.objects.filter(stable_key=key).first()
    if office is None or not _office_in_actor_scope(user, office):
        raise ValidationError({"officeKey": ["Choose an office in your scope."]})
    return office


def _resolve_person(
    user: User,
    *,
    person_id: str | None,
    field: str,
    role: str,
    required: bool = False,
) -> User | None:
    raw = (person_id or "").strip()
    if not raw:
        if required:
            raise ValidationError({field: ["This person is required."]})
        return None
    try:
        pk = int(raw)
    except ValueError as exc:
        raise ValidationError({field: ["Unknown person."]}) from exc
    person = scoped_people_queryset(user, role=role).filter(pk=pk).first()
    if person is None:
        # Do not disclose whether the id exists outside scope.
        raise ValidationError({field: ["Choose a person in your scope."]})
    return person


def _property_from_form(data: dict[str, Any]) -> dict:
    return _normalize_property_snapshot(
        {
            "line1": data.get("propertyLine1") or data.get("property_line1") or "",
            "line2": data.get("propertyLine2") or data.get("property_line2") or "",
            "city": data.get("propertyCity") or data.get("property_city") or "",
            "state": data.get("propertyState") or data.get("property_state") or "",
            "postal_code": data.get("propertyPostalCode")
            or data.get("property_postal_code")
            or "",
        }
    )


def _clients_from_form(data: dict[str, Any]) -> list:
    name = (data.get("clientName") or data.get("client_name") or "").strip()
    if not name and isinstance(data.get("clientSnapshots"), list):
        return _normalize_client_snapshots(data.get("clientSnapshots"))
    if not name:
        return []
    return _normalize_client_snapshots(
        [
            {
                "name": name,
                "email": data.get("clientEmail") or data.get("client_email") or "",
                "phone": data.get("clientPhone") or data.get("client_phone") or "",
                "role": data.get("clientRole") or data.get("client_role") or "",
            }
        ]
    )


def _normalize_address_key(snapshot: dict) -> str:
    line1 = str(snapshot.get("line1") or snapshot.get("address_line1") or "").strip()
    city = str(snapshot.get("city") or "").strip()
    state = str(snapshot.get("state") or "").strip()
    return _WS.sub(" ", f"{line1} {city} {state}").casefold()


class DuplicateWarning(ValidationError):
    """In-scope likely duplicates; caller must confirm to proceed."""

    def __init__(self, matches: list[dict[str, str]]):
        self.matches = matches
        super().__init__(
            {
                "form": [
                    "A similar transaction already exists in your scope. "
                    "Confirm to create anyway."
                ],
                "confirmedDuplicate": [
                    "Confirm that this is not a duplicate before preparing."
                ],
            }
        )


def find_duplicate_matches(
    user: User,
    *,
    mls_number: str,
    property_snapshot: dict,
    client_snapshots: list,
    exclude_pk: int | None = None,
) -> list[dict[str, str]]:
    """Return privacy-safe matches visible to ``user`` only.

    Out-of-scope candidates are never acknowledged.
    """
    scoped = scoped_transaction_queryset(user).exclude(
        status__in={
            TransactionStatus.CANCELLED,
            TransactionStatus.WITHDRAWN,
            TransactionStatus.TERMINATED,
            TransactionStatus.ARCHIVED,
        }
    )
    if exclude_pk is not None:
        scoped = scoped.exclude(pk=exclude_pk)

    filters = Q(pk__in=[])
    mls = (mls_number or "").strip()
    if mls:
        filters |= Q(mls_number__iexact=mls)

    address_key = _normalize_address_key(property_snapshot or {})
    client_emails = {
        str(c.get("email", "")).strip().casefold()
        for c in (client_snapshots or [])
        if c.get("email")
    }
    client_names = {
        str(c.get("name", "")).strip().casefold()
        for c in (client_snapshots or [])
        if c.get("name")
    }

    matches: list[dict[str, str]] = []
    seen: set[int] = set()
    # MLS hits via SQL; address/client via bounded scan of scoped rows.
    for tx in scoped.filter(filters).order_by("-pk")[:20]:
        seen.add(tx.pk)
        matches.append({"publicId": str(tx.public_id), "reference": tx.reference})

    if address_key or client_emails or client_names:
        for tx in scoped.order_by("-pk")[:200]:
            if tx.pk in seen:
                continue
            hit = False
            if address_key and _normalize_address_key(tx.property_snapshot or {}) == (
                address_key
            ):
                hit = True
            if not hit and client_emails:
                for client in tx.client_snapshots or []:
                    email = str(client.get("email", "")).strip().casefold()
                    if email and email in client_emails:
                        hit = True
                        break
            if not hit and client_names:
                for client in tx.client_snapshots or []:
                    name = str(client.get("name", "")).strip().casefold()
                    if name and name in client_names:
                        hit = True
                        break
            if hit:
                seen.add(tx.pk)
                matches.append(
                    {"publicId": str(tx.public_id), "reference": tx.reference}
                )
            if len(matches) >= 10:
                break
    return matches


def _apply_fields(
    *,
    user: User,
    mode: CreatorMode,
    actor: ActorContext,
    tx: Transaction | None,
    data: dict[str, Any],
    require_preparing_fields: bool,
) -> tuple[Office, str, str, User | None, User | None, User | None, dict]:
    transaction_type = (
        data.get("transactionType") or data.get("transaction_type") or ""
    ).strip()
    representation_type = (
        data.get("representationType") or data.get("representation_type") or ""
    ).strip()
    assert_type_representation_pair(transaction_type, representation_type)

    office = _resolve_office(
        user, mode, data.get("officeKey") or data.get("office_key")
    )

    if mode.lock_primary_agent:
        primary = user
        crafted = (
            data.get("primaryAgentId") or data.get("primary_agent_id") or ""
        ).strip()
        if crafted and crafted != str(user.pk):
            raise ValidationError(
                {"primaryAgentId": ["You are the primary agent on deals you create."]}
            )
    else:
        primary = _resolve_person(
            user,
            person_id=data.get("primaryAgentId") or data.get("primary_agent_id"),
            field="primaryAgentId",
            role="agent",
            required=require_preparing_fields,
        )

    co_agent = _resolve_person(
        user,
        person_id=data.get("coAgentId") or data.get("co_agent_id"),
        field="coAgentId",
        role="agent",
        required=False,
    )
    coordinator = _resolve_person(
        user,
        person_id=data.get("coordinatorId") or data.get("coordinator_id"),
        field="coordinatorId",
        role="coordinator",
        required=False,
    )

    property_snapshot = _property_from_form(data)
    client_snapshots = _clients_from_form(data)
    mls_number = (data.get("mlsNumber") or data.get("mls_number") or "")[:64]
    list_price = _parse_money(
        data.get("listPrice") or data.get("list_price"), "listPrice"
    )
    contract_price = _parse_money(
        data.get("contractPrice") or data.get("contract_price"), "contractPrice"
    )
    acceptance_date = _parse_date(
        data.get("acceptanceDate") or data.get("acceptance_date"), "acceptanceDate"
    )
    closing_date = _parse_date(
        data.get("closingDate") or data.get("closing_date"), "closingDate"
    )
    lender_ref = (data.get("lenderRef") or data.get("lender_ref") or "")[:128]
    title_ref = (data.get("titleRef") or data.get("title_ref") or "")[:128]
    referral_ref = (data.get("referralRef") or data.get("referral_ref") or "")[:128]

    if require_preparing_fields:
        if primary is None:
            raise ValidationError({"primaryAgentId": ["A primary agent is required."]})
        line1 = property_snapshot.get("line1") or property_snapshot.get("address_line1")
        if not line1:
            raise ValidationError(
                {"propertyLine1": ["A property street address is required."]}
            )

    values = {
        "transaction_type": transaction_type,
        "representation_type": representation_type,
        "office": office,
        "primary_agent": primary,
        "co_agent": co_agent,
        "coordinator": coordinator,
        "property_snapshot": property_snapshot,
        "mls_number": mls_number,
        "client_snapshots": client_snapshots,
        "list_price": list_price,
        "contract_price": contract_price,
        "acceptance_date": acceptance_date,
        "closing_date": closing_date,
        "lender_ref": lender_ref,
        "title_ref": title_ref,
        "referral_ref": referral_ref,
        "existing": tx,
        "actor": actor,
    }
    return (
        office,
        transaction_type,
        representation_type,
        primary,
        co_agent,
        coordinator,
        values,
    )


def _write_draft_row(
    *,
    actor: ActorContext,
    values: dict[str, Any],
    submission_key: str | None = None,
) -> Transaction:
    existing: Transaction | None = values["existing"]
    if existing is None:
        # create_draft requires manage; own-create path uses the same writer
        # with an elevated actor permission set for the call.
        write_actor = ActorContext(
            user=actor.user,
            permissions=frozenset(set(actor.permissions) | {MANAGE_TRANSACTIONS}),
        )
        tx = create_draft(
            actor=write_actor,
            office=values["office"],
            transaction_type=values["transaction_type"],
            representation_type=values["representation_type"],
            primary_agent=values["primary_agent"],
            coordinator=values["coordinator"],
            property_snapshot=values["property_snapshot"],
            mls_number=values["mls_number"],
            client_snapshots=values["client_snapshots"],
            list_price=values["list_price"],
            contract_price=values["contract_price"],
            acceptance_date=values["acceptance_date"],
            closing_date=values["closing_date"],
            lender_ref=values["lender_ref"],
            title_ref=values["title_ref"],
            referral_ref=values["referral_ref"],
        )
        if submission_key:
            tx.submission_key = submission_key
            tx.save(update_fields=["submission_key", "updated_at"])
    else:
        if existing.status != TransactionStatus.DRAFT:
            raise ValidationError(
                {"form": ["Only draft transactions can be edited here."]}
            )
        locked = (
            Transaction.objects.select_for_update(of=("self",))
            .filter(pk=existing.pk)
            .first()
        )
        if locked is None:
            raise ValidationError({"form": ["This transaction no longer exists."]})
        locked.transaction_type = values["transaction_type"]
        locked.representation_type = values["representation_type"]
        locked.office = values["office"]
        locked.property_snapshot = values["property_snapshot"]
        locked.mls_number = values["mls_number"]
        locked.client_snapshots = values["client_snapshots"]
        locked.list_price = values["list_price"]
        locked.contract_price = values["contract_price"]
        locked.acceptance_date = values["acceptance_date"]
        locked.closing_date = values["closing_date"]
        locked.lender_ref = values["lender_ref"]
        locked.title_ref = values["title_ref"]
        locked.referral_ref = values["referral_ref"]
        if submission_key and not locked.submission_key:
            locked.submission_key = submission_key
        locked.save()
        write_actor = ActorContext(
            user=actor.user,
            permissions=frozenset(set(actor.permissions) | {MANAGE_TRANSACTIONS}),
        )
        if values["primary_agent"] is not None:
            upsert_assignment(
                actor=write_actor,
                tx=locked,
                user=values["primary_agent"],
                role=AssignmentRole.PRIMARY_AGENT,
                _skip_manage_check=True,
            )
        if values["coordinator"] is not None:
            upsert_assignment(
                actor=write_actor,
                tx=locked,
                user=values["coordinator"],
                role=AssignmentRole.COORDINATOR,
                _skip_manage_check=True,
            )
        tx = locked

    write_actor = ActorContext(
        user=actor.user,
        permissions=frozenset(set(actor.permissions) | {MANAGE_TRANSACTIONS}),
    )
    if values["co_agent"] is not None:
        upsert_assignment(
            actor=write_actor,
            tx=tx,
            user=values["co_agent"],
            role=AssignmentRole.CO_AGENT,
            _skip_manage_check=True,
        )
    return Transaction.objects.select_related(
        "office", "primary_agent", "coordinator"
    ).get(pk=tx.pk)


@transaction.atomic
def save_draft(*, user: User, data: dict[str, Any]) -> Transaction:
    """Persist a draft, allowing incomplete prepare-stage fields."""
    mode = require_creator(user)
    actor = actor_context(user)
    public_id = (data.get("publicId") or data.get("public_id") or "").strip()
    existing = None
    if public_id:
        existing = _load_editable_draft(user, public_id)
    _, _, _, _, _, _, values = _apply_fields(
        user=user,
        mode=mode,
        actor=actor,
        tx=existing,
        data=data,
        require_preparing_fields=False,
    )
    return _write_draft_row(actor=actor, values=values)


def _load_editable_draft(user: User, public_id: str) -> Transaction:
    try:
        uid = UUID(str(public_id))
    except (TypeError, ValueError) as exc:
        raise ValidationError({"publicId": ["Unknown transaction."]}) from exc
    tx = scoped_transaction_queryset(user).filter(public_id=uid).first()
    if tx is None:
        raise ValidationError({"publicId": ["Unknown transaction."]})
    if tx.status != TransactionStatus.DRAFT:
        raise ValidationError({"form": ["Only draft transactions can be edited here."]})
    mode = resolve_creator_mode(user)
    owns_draft = tx.primary_agent_pk == user.pk or tx.created_by_id == user.pk
    if not mode.manage and not owns_draft:
        raise PermissionDenied("You do not have permission to edit this draft.")
    return tx


@transaction.atomic
def prepare_transaction(
    *,
    user: User,
    data: dict[str, Any],
    confirmed_duplicate: bool = False,
) -> Transaction:
    """Create/update draft then transition to Preparing under an idempotency key."""
    mode = require_creator(user)
    actor = actor_context(user)
    key = (data.get("submissionKey") or data.get("submission_key") or "").strip()[:64]
    if not key:
        raise ValidationError({"submissionKey": ["A submission key is required."]})

    existing_by_key = (
        Transaction.objects.select_for_update(of=("self",))
        .filter(submission_key=key)
        .first()
    )
    if existing_by_key is not None:
        # Idempotent return — do not re-emit create or transition side effects.
        return existing_by_key

    public_id = (data.get("publicId") or data.get("public_id") or "").strip()
    existing = _load_editable_draft(user, public_id) if public_id else None

    office, _, _, _, _, _, values = _apply_fields(
        user=user,
        mode=mode,
        actor=actor,
        tx=existing,
        data=data,
        require_preparing_fields=True,
    )
    _ = office

    matches = find_duplicate_matches(
        user,
        mls_number=values["mls_number"],
        property_snapshot=values["property_snapshot"],
        client_snapshots=values["client_snapshots"],
        exclude_pk=existing.pk if existing is not None else None,
    )
    if matches and not confirmed_duplicate:
        raise DuplicateWarning(matches)

    try:
        tx = _write_draft_row(actor=actor, values=values, submission_key=key)
    except IntegrityError:
        winner = Transaction.objects.filter(submission_key=key).first()
        if winner is not None:
            return winner
        raise

    # Re-check under lock in case of race on the unique key.
    locked = (
        Transaction.objects.select_for_update(of=("self",)).filter(pk=tx.pk).first()
    )
    assert locked is not None
    if locked.status == TransactionStatus.PREPARING:
        return locked

    return transition(
        user=user,
        permissions=frozenset(set(actor.permissions) | {MANAGE_TRANSACTIONS}),
        tx=locked,
        to_status=TransactionStatus.PREPARING,
        expected_status=TransactionStatus.DRAFT,
        note="Prepared via create workflow",
    )


def build_new_transaction_page(
    user: User, *, draft: dict[str, Any] | None = None, errors=None, duplicates=None
) -> dict[str, Any]:
    mode = require_creator(user)
    data = dict(draft or {})
    txn_type = data.get("transactionType") or data.get("transaction_type") or ""
    rep = data.get("representationType") or data.get("representation_type") or ""
    offices = scoped_offices_for_creator(user)
    home = getattr(user, "office", None)
    jurisdiction = ""
    if mode.lock_office and home is not None:
        jurisdiction = getattr(home, "state", "") or ""
        data.setdefault("officeKey", home.stable_key)
        data.setdefault("primaryAgentId", str(user.pk))
    elif data.get("officeKey"):
        office = next((o for o in offices if o.stable_key == data["officeKey"]), None)
        if office is not None:
            jurisdiction = getattr(office, "state", "") or ""

    schema = build_create_schema(
        transaction_type=txn_type,
        representation_type=rep,
        jurisdiction=jurisdiction,
        stage="draft",
        lock_office=mode.lock_office,
        lock_primary_agent=mode.lock_primary_agent,
    )
    return {
        "schema": schema,
        "draft": data,
        "errors": errors or {"fields": {}, "form": []},
        "duplicates": duplicates or [],
        "offices": [
            {
                "stableKey": office.stable_key,
                "name": office.name,
                "state": getattr(office, "state", "") or "",
            }
            for office in offices
        ],
        "capabilities": {
            "manage": mode.manage,
            "createOwn": mode.create_own,
            "lockOffice": mode.lock_office,
            "lockPrimaryAgent": mode.lock_primary_agent,
        },
        "selfPerson": {
            "id": user.pk,
            "name": user.preferred_display_name()
            if hasattr(user, "preferred_display_name")
            else str(user),
            "email": user.email or "",
            "officeId": home.pk if home is not None else None,
            "officeName": home.name if home is not None else "",
            "officeState": getattr(home, "state", "") if home is not None else "",
            "officeKey": home.stable_key if home is not None else "",
            "licenseState": getattr(user, "license_state", "") or "",
            "agentIdentifier": getattr(user, "agent_identifier", "") or "",
        },
    }


def workspace_payload(user: User, tx: Transaction) -> dict[str, Any]:
    from apps.transactions.workspace import workspace_payload as build

    return build(user, tx)


def load_workspace_transaction(user: User, public_id: UUID) -> Transaction:
    from apps.transactions.concurrency import load_workspace_transaction as load

    return load(user, public_id)


__all__ = [
    "CreatorMode",
    "DuplicateWarning",
    "actor_context",
    "build_new_transaction_page",
    "find_duplicate_matches",
    "load_workspace_transaction",
    "prepare_transaction",
    "require_creator",
    "resolve_creator_mode",
    "save_draft",
    "scoped_offices_for_creator",
    "scoped_people_queryset",
    "search_transaction_people",
    "workspace_payload",
]
