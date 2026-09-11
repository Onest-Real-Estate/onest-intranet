"""Hub-owned agent contract emails for lifecycle changes.

Transactional messages for the recipient agent. They carry only in-app paths
(re-authenticated on arrival), never durable file URLs or commercial terms.
Failures are logged and never raise into the lifecycle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import send_mail
from django.urls import NoReverseMatch, reverse

from apps.contract.models import AgentContract

logger = logging.getLogger(__name__)

#: Lifecycle actions that email the recipient after a successful transition.
#: ``issue`` no longer emails the agent — company signs first; ``mark_company_signed``
#: releases the agreement and uses the issued-notice copy.
AGENT_EMAIL_ACTIONS: frozenset[str] = frozenset(
    {
        "mark_company_signed",
        "mark_signed",
        "activate",
        "supersede",
        "terminate",
        "expire",
    }
)


@dataclass(frozen=True)
class _LifecycleEmailCopy:
    kind: str
    subject: str
    body: str
    route_name: str
    include_public_id_query: bool = False


_LIFECYCLE_COPY: dict[str, _LifecycleEmailCopy] = {
    "mark_company_signed": _LifecycleEmailCopy(
        kind="issued notice",
        subject="Your oNEST agent contract was issued",
        body=(
            "Your agent contract has been issued and is ready for your "
            "signature. Sign in to oNEST Hub to review and sign."
        ),
        route_name="my_contract",
    ),
    "issue": _LifecycleEmailCopy(
        kind="issued notice",
        subject="Your oNEST agent contract was issued",
        body=(
            "Your agent contract has been issued. oNEST Hub is preparing the "
            "review PDF; you will receive a separate message when it is ready "
            "to sign."
        ),
        route_name="my_contract",
    ),
    "mark_signed": _LifecycleEmailCopy(
        kind="signed confirmation",
        subject="Your oNEST agent contract is signed",
        body=(
            "Your electronic signature on your agent contract has been "
            "recorded. A certificate of completion is stored with the "
            "contract record."
        ),
        route_name="my_contract",
    ),
    "activate": _LifecycleEmailCopy(
        kind="activated notice",
        subject="Your oNEST agent contract is now active",
        body=(
            "Your agent contract is now the active governing agreement. "
            "Sign in to oNEST Hub to review it."
        ),
        route_name="my_contract",
    ),
    "supersede": _LifecycleEmailCopy(
        kind="superseded notice",
        subject="Your oNEST agent contract was superseded",
        body=(
            "Your agent contract was superseded by a replacement agreement. "
            "Sign in to oNEST Hub to review the current status."
        ),
        route_name="my_contract",
    ),
    "terminate": _LifecycleEmailCopy(
        kind="terminated notice",
        subject="Your oNEST agent contract was terminated",
        body=(
            "Your agent contract was terminated. Sign in to oNEST Hub to "
            "review the current status."
        ),
        route_name="my_contract",
    ),
    "expire": _LifecycleEmailCopy(
        kind="expired notice",
        subject="Your oNEST agent contract has expired",
        body=(
            "Your agent contract has expired by its policy end date. Sign in "
            "to oNEST Hub to review the current status."
        ),
        route_name="my_contract",
    ),
}


def _site_base() -> str:
    return (getattr(settings, "SITE_BASE_URL", "") or "http://localhost:8000").rstrip(
        "/"
    )


def _absolute(path: str) -> str:
    if not path.startswith("/") or path.startswith("//"):
        return ""
    return f"{_site_base()}{path}"


def _recipient_email(contract: AgentContract) -> str:
    recipient = contract.recipient
    return (getattr(recipient, "email", "") or "").strip()


def _party_greeting(contract: AgentContract) -> str:
    party = contract.party_snapshot or {}
    return str(party.get("displayName") or party.get("legalFirstName") or "Agent")


def _reverse_path(route_name: str, *, fallback: str) -> str:
    try:
        return reverse(route_name)
    except NoReverseMatch:  # pragma: no cover - route removal is a deploy bug
        return fallback


def _send(
    *, subject: str, body: str, to: str, contract: AgentContract, kind: str
) -> None:
    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", None) or None,
            [to],
            fail_silently=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "%s email failed contract_id=%s",
            kind,
            contract.pk,
        )


def send_lifecycle_status_email(contract: AgentContract, *, action: str) -> None:
    """Email the recipient after a durable lifecycle status change."""
    copy = _LIFECYCLE_COPY.get(action)
    if copy is None:
        return
    email = _recipient_email(contract)
    if not email:
        logger.warning(
            "%s skipped missing email contract_id=%s", copy.kind, contract.pk
        )
        return
    path = _reverse_path(copy.route_name, fallback="/my-contract")
    if copy.include_public_id_query:
        path = f"{path}?v={contract.public_id}"
    view_url = _absolute(path)
    name = _party_greeting(contract)
    body = f"Hello {name},\n\n{copy.body}\n\n{view_url}\n"
    _send(
        subject=copy.subject,
        body=body,
        to=email,
        contract=contract,
        kind=copy.kind,
    )


def send_signing_invite_email(contract: AgentContract) -> None:
    """Hub-owned signing invite after the review PDF is ready."""
    email = _recipient_email(contract)
    if not email:
        logger.warning(
            "signing invite skipped missing email contract_id=%s", contract.pk
        )
        return
    path = _reverse_path("my_contract_sign", fallback="/my-contract/sign")
    sign_url = _absolute(f"{path}?v={contract.public_id}")
    name = _party_greeting(contract)
    subject = "Your oNEST agent contract is ready to sign"
    body = (
        f"Hello {name},\n\n"
        "Your agent contract has been prepared and issued. Sign in to oNEST Hub "
        "and complete the electronic signature ceremony:\n\n"
        f"{sign_url}\n\n"
        "Only you, the named recipient, may sign this agreement.\n"
    )
    _send(
        subject=subject,
        body=body,
        to=email,
        contract=contract,
        kind="signing invite",
    )


def send_signed_confirmation_email(contract: AgentContract) -> None:
    """Backward-compatible alias for the signed lifecycle email."""
    send_lifecycle_status_email(contract, action="mark_signed")


def send_company_signatory_invite_email(contract: AgentContract) -> None:
    """Invite the named company officer to complete the Company ceremony."""
    signatory = contract.company_signatory
    email = (getattr(signatory, "email", "") or "").strip() if signatory else ""
    if not email:
        logger.warning(
            "company signatory invite skipped missing email contract_id=%s",
            contract.pk,
        )
        return
    try:
        path = reverse(
            "agent_contract_company_sign",
            kwargs={"public_id": contract.public_id},
        )
    except NoReverseMatch:  # pragma: no cover
        path = f"/operations/agent-contracts/{contract.public_id}/company-sign"
    sign_url = _absolute(path)
    name = signatory.preferred_display_name() if signatory is not None else "Officer"
    party = _party_greeting(contract)
    subject = "oNEST agent contract needs your company signature"
    body = (
        f"Hello {name},\n\n"
        f"An agent contract for {party} is awaiting your company signature. "
        "Sign in to oNEST Hub and complete the Company ceremony before the "
        "agent can sign:\n\n"
        f"{sign_url}\n"
    )
    _send(
        subject=subject,
        body=body,
        to=email,
        contract=contract,
        kind="company signatory invite",
    )
