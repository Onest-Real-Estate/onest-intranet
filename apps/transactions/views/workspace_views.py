"""Minimal transaction workspace shell (expanded in #101)."""

from __future__ import annotations

import uuid
from typing import cast

from django.http import Http404, HttpRequest
from django.views.decorators.http import require_GET
from inertia import inertia

from apps.transactions.creation import load_workspace_transaction, workspace_payload
from apps.transactions.models import Transaction
from apps.user.models import User
from apps.web.authorization import enforce_policy

WORKSPACE_PAGE = "TransactionWorkspace"


def _actor(request: HttpRequest) -> User:
    return cast(User, request.user)


@enforce_policy("transaction_workspace")
@require_GET
@inertia(WORKSPACE_PAGE)
def transaction_workspace(request: HttpRequest, public_id: uuid.UUID):
    try:
        tx = load_workspace_transaction(_actor(request), public_id)
    except Transaction.DoesNotExist as exc:
        raise Http404("Transaction not found.") from exc
    return workspace_payload(_actor(request), tx)
