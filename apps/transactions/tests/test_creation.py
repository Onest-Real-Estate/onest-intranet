"""Scoped transaction create / prepare / duplicate / idempotency tests."""

from __future__ import annotations

import json
import uuid

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.transactions.creation import (
    DuplicateWarning,
    find_duplicate_matches,
    prepare_transaction,
    save_draft,
)
from apps.transactions.models import Transaction
from apps.transactions.permissions import (
    CREATE_OWN_TRANSACTIONS,
    MANAGE_TRANSACTIONS,
)
from apps.transactions.taxonomy import (
    RepresentationType,
    TransactionStatus,
    TransactionType,
)
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.roles import (
    BRANCH_MANAGER,
    REALTOR,
    TRANSACTION_COORDINATOR,
    ScopeType,
)
from apps.user.tests.test_profile import completed_user


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def assign(user: User, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def grant(user: User, *codenames: str) -> User:
    for codename in codenames:
        app_label, _, name = codename.partition(".")
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=name)
        )
    return User.objects.get(pk=user.pk)


def agent_user(email="agent.create@example.com") -> User:
    user = completed_user(email=email, office=office("fairfax-va"))
    assign(user, REALTOR, ScopeType.OFFICE, office("fairfax-va"))
    return grant(user, CREATE_OWN_TRANSACTIONS)


def branch_manager_user(email="branch.create@example.com") -> User:
    user = completed_user(email=email, office=office("fairfax-va"))
    assign(user, BRANCH_MANAGER, ScopeType.OFFICE, office("fairfax-va"))
    return grant(user, MANAGE_TRANSACTIONS)


def tc_user(email="tc.create@example.com") -> User:
    user = completed_user(email=email, office=office("fairfax-va"))
    assign(user, TRANSACTION_COORDINATOR, ScopeType.OFFICE, office("fairfax-va"))
    return grant(user, MANAGE_TRANSACTIONS)


def base_payload(**overrides) -> dict:
    data = {
        "transactionType": TransactionType.BUY,
        "representationType": RepresentationType.BUYER,
        "officeKey": office("fairfax-va").stable_key,
        "propertyLine1": "100 Create St",
        "propertyCity": "Fairfax",
        "propertyState": "VA",
        "mlsNumber": "MLS-CREATE-1",
        "clientName": "Casey Client",
        "clientEmail": "casey@example.com",
        "submissionKey": str(uuid.uuid4()),
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_agent_prepare_forces_self_and_home_office(seeded):
    agent = agent_user()
    tx = prepare_transaction(
        user=agent,
        data=base_payload(
            # No primaryAgentId — lock fills self.
            officeKey=agent.office.stable_key if agent.office else "",
        ),
    )
    assert tx.status == TransactionStatus.PREPARING
    assert tx.primary_agent_pk == agent.pk
    assert agent.office is not None
    assert tx.office_pk == agent.office.pk


@pytest.mark.django_db
def test_agent_rejects_crafted_foreign_office_and_primary(seeded):
    from django.core.exceptions import ValidationError

    agent = agent_user()
    other = completed_user(email="other2@example.com", office=office("fairfax-va"))
    assign(other, REALTOR, ScopeType.OFFICE, office("fairfax-va"))

    with pytest.raises(ValidationError) as office_exc:
        prepare_transaction(
            user=agent,
            data=base_payload(officeKey=office("charlottesville-va").stable_key),
        )
    assert "officeKey" in office_exc.value.message_dict

    with pytest.raises(ValidationError) as primary_exc:
        prepare_transaction(
            user=agent,
            data=base_payload(primaryAgentId=str(other.pk)),
        )
    assert "primaryAgentId" in primary_exc.value.message_dict


@pytest.mark.django_db
def test_branch_manager_cannot_assign_out_of_scope_office(seeded):
    from django.core.exceptions import ValidationError

    manager = branch_manager_user()
    with pytest.raises(ValidationError):
        prepare_transaction(
            user=manager,
            data=base_payload(
                officeKey=office("charlottesville-va").stable_key,
                primaryAgentId=str(manager.pk),
            ),
        )


@pytest.mark.django_db
def test_denied_user_cannot_open_create(client, seeded):
    user = completed_user(email="nobody@example.com", office=office("fairfax-va"))
    client.force_login(user)
    response = client.get(reverse("transaction_new"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_prepare_idempotent_on_submission_key(seeded):
    manager = tc_user()
    agent = agent_user("primary.for.tc@example.com")
    key = str(uuid.uuid4())
    payload = base_payload(
        submissionKey=key,
        primaryAgentId=str(agent.pk),
    )
    first = prepare_transaction(user=manager, data=payload)
    second = prepare_transaction(user=manager, data=payload)
    assert first.pk == second.pk
    assert Transaction.objects.filter(submission_key=key).count() == 1


@pytest.mark.django_db
def test_duplicate_warns_then_override(seeded):
    manager = tc_user()
    agent = agent_user("dup.agent@example.com")
    first = prepare_transaction(
        user=manager,
        data=base_payload(
            submissionKey=str(uuid.uuid4()),
            primaryAgentId=str(agent.pk),
            mlsNumber="MLS-DUP-9",
        ),
    )
    assert first.status == TransactionStatus.PREPARING

    with pytest.raises(DuplicateWarning) as exc:
        prepare_transaction(
            user=manager,
            data=base_payload(
                submissionKey=str(uuid.uuid4()),
                primaryAgentId=str(agent.pk),
                mlsNumber="MLS-DUP-9",
                propertyLine1="Different St",
            ),
        )
    assert any(m["reference"] == first.reference for m in exc.value.matches)

    second = prepare_transaction(
        user=manager,
        data=base_payload(
            submissionKey=str(uuid.uuid4()),
            primaryAgentId=str(agent.pk),
            mlsNumber="MLS-DUP-9",
            propertyLine1="Different St",
        ),
        confirmed_duplicate=True,
    )
    assert second.pk != first.pk


@pytest.mark.django_db
def test_duplicate_finder_is_silent_outside_scope(seeded):
    fairfax_mgr = tc_user("fairfax.tc@example.com")
    agent = agent_user("fairfax.agent@example.com")
    prepare_transaction(
        user=fairfax_mgr,
        data=base_payload(
            submissionKey=str(uuid.uuid4()),
            primaryAgentId=str(agent.pk),
            mlsNumber="MLS-HIDDEN",
        ),
    )

    outsider = completed_user(
        email="outsider@example.com", office=office("charlottesville-va")
    )
    assign(outsider, BRANCH_MANAGER, ScopeType.OFFICE, office("charlottesville-va"))
    outsider = grant(outsider, MANAGE_TRANSACTIONS)

    matches = find_duplicate_matches(
        outsider,
        mls_number="MLS-HIDDEN",
        property_snapshot={},
        client_snapshots=[],
    )
    assert matches == []


@pytest.mark.django_db
def test_save_draft_allows_incomplete_then_prepare(seeded):
    manager = tc_user("draft.tc@example.com")
    agent = agent_user("draft.agent@example.com")
    draft = save_draft(
        user=manager,
        data={
            "transactionType": TransactionType.SELL,
            "representationType": RepresentationType.SELLER,
            "officeKey": office("fairfax-va").stable_key,
        },
    )
    assert draft.status == TransactionStatus.DRAFT
    assert draft.primary_agent_pk is None

    prepared = prepare_transaction(
        user=manager,
        data=base_payload(
            publicId=str(draft.public_id),
            transactionType=TransactionType.SELL,
            representationType=RepresentationType.SELLER,
            primaryAgentId=str(agent.pk),
            submissionKey=str(uuid.uuid4()),
            mlsNumber="MLS-DRAFT-1",
        ),
    )
    assert prepared.pk == draft.pk
    assert prepared.status == TransactionStatus.PREPARING


@pytest.mark.django_db
def test_inertia_json_prepare_redirects_to_workspace(client, seeded):
    manager = tc_user("json.tc@example.com")
    agent = agent_user("json.agent@example.com")
    client.force_login(manager)
    payload = base_payload(
        primaryAgentId=str(agent.pk),
        submissionKey=str(uuid.uuid4()),
    )
    response = client.post(
        reverse("transaction_prepare"),
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert response.status_code == 302
    tx = Transaction.objects.get(submission_key=payload["submissionKey"])
    assert str(tx.public_id) in response["Location"]


@pytest.mark.django_db
def test_type_representation_pair_validated(seeded):
    from django.core.exceptions import ValidationError

    manager = tc_user("pair.tc@example.com")
    agent = agent_user("pair.agent@example.com")
    with pytest.raises(ValidationError):
        prepare_transaction(
            user=manager,
            data=base_payload(
                transactionType=TransactionType.BUY,
                representationType=RepresentationType.LANDLORD,
                primaryAgentId=str(agent.pk),
            ),
        )
