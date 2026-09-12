"""Source resolvers shipped with the notification domain.

Each resolver answers one question for one domain: *may this reader still see
the record this notification points at, and what should it say today?* They
are registered at app startup (``apps.notifications.apps``) and called in
batches by :func:`apps.notifications.sources.resolve_sources`.

A domain that has no resolver here fails closed — its notifications list with
no detail and no action. That is the intended state for modules that have not
shipped yet (contracts, transactions, inventory, rooms, leads): the inbox
degrades, it does not leak.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from apps.notifications.sources import SourceResolution
from apps.user.services.agent_administration import administered_user_queryset
from apps.user.services.onboarding_state import VIEW_PERMISSION
from apps.user.services.role_assignments import has_effective_permission

#: Source module key used by onboarding-coordination notifications.
ONBOARDING_MODULE = "onboarding"
ONBOARDING_TOOL_MODULE = "onboarding_tool"


def _record_ids(notifications: Sequence) -> dict[UUID, int]:
    resolved: dict[UUID, int] = {}
    for notification in notifications:
        raw = str(notification.source_record_id or "")
        if raw.isdigit():
            resolved[notification.public_id] = int(raw)
    return resolved


def resolve_onboarding_cases(
    user, notifications: Sequence
) -> dict[UUID, SourceResolution]:
    """Detail for onboarding-case notifications, re-derived per read.

    Two live checks, both of which can stop being true after delivery:

    * the reader still holds ``web.view_new_agents``, and
    * the agent is still inside the reader's administrative scope.

    Either failing removes the name and the destination from a notification
    that was legitimate when it was sent. Nothing rewrites the old row.
    """
    ids = _record_ids(notifications)
    if not ids or not has_effective_permission(user, VIEW_PERMISSION):
        return {}
    subjects = {
        subject.pk: subject
        for subject in administered_user_queryset(user).filter(pk__in=set(ids.values()))
    }
    resolutions: dict[UUID, SourceResolution] = {}
    for public_id, record_id in ids.items():
        subject = subjects.get(record_id)
        if subject is None:
            continue
        resolutions[public_id] = SourceResolution(
            available=True,
            detail=(
                f"Onboarding for {subject.preferred_display_name()}"
                + (f" · {subject.office.name}" if subject.office else "")
            ),
            action_available=True,
        )
    return resolutions


def resolve_onboarding_tools(
    user, notifications: Sequence
) -> dict[UUID, SourceResolution]:
    """Resolve only this agent's catalog-tool invitation notices."""
    from apps.onboarding_tools.models import OnboardingTool

    slugs_by_id: dict[UUID, str] = {}
    for notification in notifications:
        raw = str(notification.source_record_id or "")
        agent_id, separator, slug = raw.partition(":")
        if separator and agent_id.isdigit() and int(agent_id) == user.pk and slug:
            slugs_by_id[notification.public_id] = slug
    if not slugs_by_id:
        return {}
    names = dict(
        OnboardingTool.objects.filter(slug__in=set(slugs_by_id.values())).values_list(
            "slug", "name"
        )
    )
    return {
        public_id: SourceResolution(
            available=True,
            detail=(
                f"Look for the {names.get(slug, slug)} activation email in "
                "Microsoft Outlook."
            ),
            action_available=True,
        )
        for public_id, slug in slugs_by_id.items()
    }


CONTRACT_MODULE = "contract"


def resolve_contracts(user, notifications: Sequence) -> dict[UUID, SourceResolution]:
    """Detail for contract lifecycle notifications."""
    from apps.contract.services import accessible_contract_queryset
    from apps.contract.statuses import ContractStatus

    by_notification: dict[UUID, str] = {}
    event_by_id: dict[UUID, str] = {}
    for notification in notifications:
        raw = str(notification.source_record_id or "").strip()
        if raw:
            by_notification[notification.public_id] = raw
            event_by_id[notification.public_id] = str(
                getattr(notification, "event_key", "") or ""
            )
    if not by_notification:
        return {}

    contracts = {
        str(row.public_id): row
        for row in accessible_contract_queryset(user).filter(
            public_id__in=list(by_notification.values())
        )
    }
    detail_by_status = {
        ContractStatus.SENT: "Issued to you",
        ContractStatus.VIEWED: "Awaiting your signature",
        ContractStatus.SIGNED: "Signed agreement is available",
        ContractStatus.ACTIVE: "Active governing agreement",
        ContractStatus.SUPERSEDED: "Superseded by a replacement",
        ContractStatus.TERMINATED: "Agreement was terminated",
        ContractStatus.EXPIRED: "Agreement has expired",
        ContractStatus.GENERATION_ERROR: "PDF preparation needs attention",
    }
    signable = {ContractStatus.SENT, ContractStatus.VIEWED}
    resolutions: dict[UUID, SourceResolution] = {}
    for note_id, contract_id in by_notification.items():
        contract = contracts.get(contract_id)
        if contract is None:
            continue
        status = contract.status
        event_key = event_by_id.get(note_id, "")
        # Stale signature reminders must not stay actionable after signing or
        # terminal lifecycle moves — the source check fails closed here and
        # the email ledger suppresses the push copy.
        if event_key == "contract.signature_reminder" and (
            status not in signable or not contract.generated_pdf_id
        ):
            continue
        if (
            event_key == "contract.expiration_warning"
            and status != ContractStatus.ACTIVE
        ):
            continue
        if (
            status
            in {
                ContractStatus.SENT,
                ContractStatus.VIEWED,
            }
            and contract.generated_pdf_id
        ):
            detail = "Review PDF is ready to sign"
        else:
            detail = detail_by_status.get(status)
            if detail is None:
                if contract.generated_pdf_id is None and status != (
                    ContractStatus.GENERATION_ERROR
                ):
                    continue
                detail = "Contract update"
        resolutions[note_id] = SourceResolution(
            available=True,
            detail=detail,
            action_available=True,
        )
    return resolutions


def register_default_resolvers() -> None:
    from apps.notifications.sources import register_resolver, registered_modules

    if ONBOARDING_MODULE not in registered_modules():
        register_resolver(ONBOARDING_MODULE, resolve_onboarding_cases)
    if ONBOARDING_TOOL_MODULE not in registered_modules():
        register_resolver(ONBOARDING_TOOL_MODULE, resolve_onboarding_tools)
    if CONTRACT_MODULE not in registered_modules():
        register_resolver(CONTRACT_MODULE, resolve_contracts)
