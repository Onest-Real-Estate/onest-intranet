"""Field projection omits sensitive keys without explicit grants."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from apps.transactions.models import Transaction
from apps.transactions.permissions import (
    VIEW_TRANSACTION_CLIENTS,
    VIEW_TRANSACTION_FINANCIALS,
    VIEW_TRANSACTIONS,
)
from apps.transactions.services import serialize_transaction
from apps.transactions.tests.conftest import assign, make_draft, office
from apps.user.tests.test_profile import completed_user


def _grant(user, *codenames: str) -> None:
    for full in codenames:
        app_label, codename = full.split(".", 1)
        if app_label == "web":
            ct = ContentType.objects.get_for_model(
                __import__(
                    "apps.web.models", fromlist=["OperationsPermission"]
                ).OperationsPermission
            )
        else:
            ct = ContentType.objects.get_for_model(Transaction)
        perm = Permission.objects.get(content_type=ct, codename=codename)
        user.user_permissions.add(perm)


@pytest.mark.django_db
def test_financials_and_clients_omitted_without_grants(seeded):
    tx = make_draft(seeded=seeded)
    viewer = completed_user(email="txn.view@example.com", office=office("fairfax-va"))
    assign(viewer, "transaction_coordinator", "office", office("fairfax-va"))
    # Role seed may already include field grants for TC — strip to view-only
    # by using a plain user with only web.view_transactions.
    plain = completed_user(email="txn.plain@example.com", office=office("fairfax-va"))
    _grant(plain, VIEW_TRANSACTIONS)
    # Office scope needs a role assignment with office keys; grant company view
    # via superuser-like assignment is heavy — instead use primary agent read path.
    agent = tx.primary_agent
    payload = serialize_transaction(agent, tx)
    assert "listPrice" not in payload
    assert "contractPrice" not in payload
    assert "clients" not in payload
    assert payload["publicId"] == str(tx.public_id)
    assert payload["property"]["line1"] == "123 Main St"


@pytest.mark.django_db
def test_financials_included_with_grant(seeded):
    tx = make_draft(seeded=seeded)
    accountant = completed_user(
        email="txn.acct@example.com", office=office("onest-head-office")
    )
    assign(accountant, "accountant", "company")
    _grant(accountant, VIEW_TRANSACTION_FINANCIALS)
    payload = serialize_transaction(accountant, tx)
    assert payload["listPrice"] == "475000.00"
    assert payload["contractPrice"] == "450000.00"
    assert "clients" not in payload


@pytest.mark.django_db
def test_clients_included_with_grant(seeded):
    tx = make_draft(seeded=seeded)
    tc = completed_user(email="txn.tc.proj@example.com", office=office("fairfax-va"))
    assign(tc, "transaction_coordinator", "office", office("fairfax-va"))
    _grant(tc, VIEW_TRANSACTION_CLIENTS, VIEW_TRANSACTION_FINANCIALS)
    payload = serialize_transaction(tc, tx)
    assert payload["clients"][0]["name"] == "Pat Client"
    assert "listPrice" in payload
