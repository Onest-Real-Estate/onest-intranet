"""Transaction workspace sections, notes visibility, and concurrency."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.transactions.concurrency import StaleTransactionVersion, transaction_version
from apps.transactions.key_dates import save_key_date
from apps.transactions.models import TransactionParty
from apps.transactions.notes import save_note, serialize_notes_for_reader
from apps.transactions.parties import save_party, serialize_parties
from apps.transactions.permissions import (
    CREATE_OWN_TRANSACTIONS,
    MANAGE_TRANSACTIONS,
    TRANSITION_TRANSACTIONS,
    VIEW_TRANSACTION_CLIENTS,
    VIEW_TRANSACTIONS,
)
from apps.transactions.property_data import save_property
from apps.transactions.services import create_draft
from apps.transactions.taxonomy import (
    NoteVisibility,
    PartyRole,
    RepresentationType,
    TransactionType,
)
from apps.transactions.tests.conftest import actor, office
from apps.user.models import User, UserRoleAssignment
from apps.user.roles import REALTOR, TRANSACTION_COORDINATOR, ScopeType
from apps.user.tests.test_profile import completed_user
from apps.web.tests.test_permissions import inertia_page_script


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def grant(user: User, *codenames: str) -> User:
    for codename in codenames:
        app_label, _, name = codename.partition(".")
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=name)
        )
    return User.objects.get(pk=user.pk)


def assign(user: User, role: str, scope_type: str, scope_office=None) -> None:
    row = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    row.refresh_status()
    row.full_clean()
    row.save()


def manager(seeded) -> User:
    user = completed_user(email="ws.mgr@example.com", office=office("fairfax-va"))
    assign(user, TRANSACTION_COORDINATOR, ScopeType.OFFICE, office("fairfax-va"))
    return grant(
        user,
        MANAGE_TRANSACTIONS,
        VIEW_TRANSACTIONS,
        TRANSITION_TRANSACTIONS,
        VIEW_TRANSACTION_CLIENTS,
    )


def agent(seeded) -> User:
    user = completed_user(email="ws.agent@example.com", office=office("fairfax-va"))
    assign(user, REALTOR, ScopeType.OFFICE, office("fairfax-va"))
    return grant(user, CREATE_OWN_TRANSACTIONS)


def draft_for(mgr: User, primary: User | None = None):
    tx = create_draft(
        actor=actor(mgr),
        office=office("fairfax-va"),
        transaction_type=TransactionType.BUY,
        representation_type=RepresentationType.BUYER,
        primary_agent=primary or mgr,
        property_snapshot={"line1": "100 Main St", "city": "Fairfax", "state": "VA"},
    )
    tx.refresh_from_db()
    return tx


@pytest.mark.django_db
def test_my_transactions_lists_assigned_only(client, seeded):
    mgr = manager(seeded)
    primary = agent(seeded)
    mine = draft_for(mgr, primary)
    other = draft_for(mgr, mgr)

    client.force_login(primary)
    response = client.get(reverse("my_transactions"))
    assert response.status_code == 200
    props = inertia_page_script(response)["props"]
    refs = {row["reference"] for row in props["items"]["items"]}
    assert mine.reference in refs
    assert other.reference not in refs


@pytest.mark.django_db
def test_workspace_section_and_party_primary_uniqueness(client, seeded):
    mgr = manager(seeded)
    tx = draft_for(mgr)
    version = transaction_version(tx)

    save_party(
        actor=mgr,
        public_id=tx.public_id,
        expected_version=version,
        payload={
            "role": PartyRole.BUYER,
            "displayName": "Ada Buyer",
            "email": "ada@example.com",
            "isPrimary": True,
            "kind": "person",
        },
    )
    tx.refresh_from_db()
    save_party(
        actor=mgr,
        public_id=tx.public_id,
        expected_version=transaction_version(tx),
        payload={
            "role": PartyRole.BUYER,
            "displayName": "Bea Buyer",
            "isPrimary": True,
            "kind": "person",
        },
    )
    primaries = TransactionParty.objects.filter(
        transaction=tx, role=PartyRole.BUYER, is_primary=True, ended_at__isnull=True
    )
    assert primaries.count() == 1
    assert primaries.get().display_name == "Bea Buyer"

    client.force_login(mgr)
    response = client.get(
        reverse("transaction_workspace", kwargs={"public_id": tx.public_id}),
        {"section": "parties"},
    )
    assert response.status_code == 200
    props = inertia_page_script(response)["props"]
    assert props["section"] == "parties"
    assert len(props["parties"]) == 2
    assert any(p.get("email") for p in props["parties"])


@pytest.mark.django_db
def test_party_contact_omitted_without_clients_grant(seeded):
    mgr = manager(seeded)
    tx = draft_for(mgr)
    save_party(
        actor=mgr,
        public_id=tx.public_id,
        expected_version=transaction_version(tx),
        payload={
            "role": PartyRole.SELLER,
            "displayName": "Sam Seller",
            "email": "sam@example.com",
            "isPrimary": True,
        },
    )
    stranger = completed_user(
        email="no.clients@example.com", office=office("fairfax-va")
    )
    # Direct grants only — no role bundle that includes clients projection.
    grant(stranger, MANAGE_TRANSACTIONS, VIEW_TRANSACTIONS)
    rows = serialize_parties(stranger, tx)
    assert rows
    assert "email" not in rows[0]


@pytest.mark.django_db
def test_note_visibility_omission(seeded):
    mgr = manager(seeded)
    primary = agent(seeded)
    tx = draft_for(mgr, primary)
    save_note(
        actor=mgr,
        public_id=tx.public_id,
        expected_version=transaction_version(tx),
        payload={"body": "Team note", "visibility": NoteVisibility.TEAM},
    )
    tx.refresh_from_db()
    save_note(
        actor=mgr,
        public_id=tx.public_id,
        expected_version=transaction_version(tx),
        payload={
            "body": "Broker only",
            "visibility": NoteVisibility.BROKER_COMPLIANCE,
        },
    )
    tx.refresh_from_db()
    save_note(
        actor=mgr,
        public_id=tx.public_id,
        expected_version=transaction_version(tx),
        payload={
            "body": "Private mgr",
            "visibility": NoteVisibility.PRIVATE_AUTHOR,
        },
    )

    agent_notes = serialize_notes_for_reader(primary, tx)
    bodies = {n["body"] for n in agent_notes}
    assert "Team note" in bodies
    assert "Broker only" not in bodies
    assert "Private mgr" not in bodies

    mgr_notes = serialize_notes_for_reader(mgr, tx)
    assert {n["body"] for n in mgr_notes} >= {
        "Team note",
        "Broker only",
        "Private mgr",
    }


@pytest.mark.django_db
def test_key_date_timezone_and_stale_version(seeded):
    mgr = manager(seeded)
    tx = draft_for(mgr)
    version = transaction_version(tx)
    save_key_date(
        actor=mgr,
        public_id=tx.public_id,
        expected_version=version,
        payload={
            "dateType": "closing",
            "occursAt": "2026-10-01T15:30",
            "timezone": "America/New_York",
        },
    )
    tx.refresh_from_db()
    assert tx.closing_date is not None

    with pytest.raises(StaleTransactionVersion):
        save_property(
            actor=mgr,
            public_id=tx.public_id,
            expected_version=version,
            payload={"line1": "200 Other St", "city": "Fairfax", "state": "VA"},
        )


@pytest.mark.django_db
def test_workspace_mutation_json_post_and_out_of_scope_404(client, seeded):
    mgr = manager(seeded)
    tx = draft_for(mgr)
    outsider = completed_user(email="out@example.com", office=office("philadelphia"))
    assign(outsider, REALTOR, ScopeType.OFFICE, office("philadelphia"))
    grant(outsider, CREATE_OWN_TRANSACTIONS)

    client.force_login(outsider)
    response = client.get(
        reverse("transaction_workspace", kwargs={"public_id": tx.public_id})
    )
    assert response.status_code == 404

    client.force_login(mgr)
    response = client.post(
        reverse("transaction_party_save", kwargs={"public_id": tx.public_id}),
        data=json.dumps(
            {
                "expectedVersion": transaction_version(tx),
                "role": "lender",
                "displayName": "First National",
                "kind": "organization",
                "isPrimary": True,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code in {302, 303}
    assert TransactionParty.objects.filter(
        transaction=tx, role="lender", ended_at__isnull=True
    ).exists()


@pytest.mark.django_db
def test_admin_transactions_live_list(client, seeded):
    mgr = manager(seeded)
    draft_for(mgr)
    client.force_login(mgr)
    response = client.get(reverse("admin_transactions"))
    assert response.status_code == 200
    props = inertia_page_script(response)["props"]
    assert "items" in props
    assert props["items"]["pagination"]["totalItems"] >= 1
