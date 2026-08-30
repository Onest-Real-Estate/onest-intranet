"""Central Agent Contract state machine.

Every status change for an issued or in-flight agreement goes through
:func:`transition`. Product forms, serializers, and Django admin must not
assign ``status`` (or lifecycle timestamps) directly — the model refuses
unguarded writes.

Concurrency uses ``select_for_update(of=("self",))`` plus an opaque
``expected_version`` token derived from ``updated_at``. Idempotent retries of
the same action against an already-at-target row are no-ops (no second audit
or domain event).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.events import publish as publish_event
from apps.audit.models import AuditEvent
from apps.audit.service import (
    AuditTarget,
    actor_from_user,
    log_event,
    system_actor,
)
from apps.contract.calculations.rules import CURRENT_RULE_VERSION
from apps.contract.emails import AGENT_EMAIL_ACTIONS
from apps.contract.models import AgentContract
from apps.contract.permissions import MANAGE_AGENT_CONTRACTS
from apps.contract.snapshots import (
    office_snapshot,
    party_snapshot,
    terms_snapshot_from_contract,
)
from apps.contract.statuses import (
    PIPELINE_STATUSES,
    TERMINAL_STATUSES,
    ContractStatus,
)
from apps.user.administration_fields import ACTIVE as ACTIVE_AGENT_STATUS
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission

logger = logging.getLogger(__name__)

_STATUS_WRITE_ALLOWED: ContextVar[bool] = ContextVar(
    "contract_status_write_allowed", default=False
)

TRANSITIONS: tuple[str, ...] = (
    "submit_for_review",
    "reopen",
    "issue",
    "mark_viewed",
    "mark_signed",
    "activate",
    "supersede",
    "terminate",
    "expire",
    "mark_generation_error",
    "retry_generation",
)

#: High-impact moves require ``confirmed=True`` from the caller.
CONFIRM_REQUIRED: frozenset[str] = frozenset(
    {"issue", "activate", "supersede", "terminate"}
)

#: Actions the Celery expire job (or other system callers) may run without a
#: human ``manage_agent_contracts`` grant.
SYSTEM_ACTIONS: frozenset[str] = frozenset({"expire", "mark_generation_error"})

_TARGET_STATUS: dict[str, str] = {
    "submit_for_review": ContractStatus.READY_FOR_REVIEW,
    "reopen": ContractStatus.DRAFT,
    "issue": ContractStatus.SENT,
    "mark_viewed": ContractStatus.VIEWED,
    "mark_signed": ContractStatus.SIGNED,
    "activate": ContractStatus.ACTIVE,
    "supersede": ContractStatus.SUPERSEDED,
    "terminate": ContractStatus.TERMINATED,
    "expire": ContractStatus.EXPIRED,
    "mark_generation_error": ContractStatus.GENERATION_ERROR,
    "retry_generation": ContractStatus.SENT,
}

_AUDIT_ACTION: dict[str, str] = {
    "submit_for_review": "contract.submitted_for_review",
    "reopen": "contract.reopened",
    "issue": "contract.issued",
    "mark_viewed": "contract.viewed",
    "mark_signed": "contract.signed",
    "activate": "contract.activated",
    "supersede": "contract.superseded",
    "terminate": "contract.terminated",
    "expire": "contract.expired",
    "mark_generation_error": "contract.generation_error",
    "retry_generation": "contract.generation_retried",
}

_DOMAIN_EVENT: dict[str, str] = {
    "issue": "contract.issued",
    "mark_viewed": "contract.viewed",
    "mark_signed": "contract.signed",
    "activate": "contract.activated",
    "supersede": "contract.superseded",
    "terminate": "contract.terminated",
    "expire": "contract.expired",
    "mark_generation_error": "contract.generation_error",
}


class StaleContractVersion(ValidationError):
    """The row moved between the form being rendered and being submitted."""

    message: str

    def __init__(self):
        self.message = str(
            _(
                "Somebody else saved this contract while you were working. "
                "Review the latest version before applying your changes."
            )
        )
        super().__init__(self.message)


class TransitionRefused(ValidationError):
    """A lifecycle action that does not apply to the row's current state."""

    message: str

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ConfirmationRequired(ValidationError):
    """High-impact transition posted without an explicit confirmation flag."""

    message: str

    def __init__(self, action: str):
        self.message = str(
            _("Confirm this %(action)s action before continuing.")
            % {"action": action.replace("_", " ")}
        )
        super().__init__(self.message)


@contextmanager
def allow_status_write():
    """Permit ``AgentContract.status`` mutation inside the lifecycle only."""
    token = _STATUS_WRITE_ALLOWED.set(True)
    try:
        yield
    finally:
        _STATUS_WRITE_ALLOWED.reset(token)


def status_write_allowed() -> bool:
    return bool(_STATUS_WRITE_ALLOWED.get())


def contract_version(contract: AgentContract) -> str:
    """Opaque concurrency token for workspace forms."""
    return contract.updated_at.isoformat(timespec="microseconds")


def _lock(pk: int) -> AgentContract:
    """Row lock without joining nullable FKs (PostgreSQL FOR UPDATE rule)."""
    return AgentContract.objects.select_for_update(of=("self",)).get(pk=pk)


def _assert_fresh(contract: AgentContract, expected_version: str) -> None:
    if contract_version(contract) != (expected_version or ""):
        raise StaleContractVersion()


def _office_in_scope(office, scope) -> bool:
    if scope.company_wide:
        return True
    if office is None:
        return False
    if office.stable_key in scope.office_keys:
        return True
    if office.stable_key in scope.region_keys:
        return True
    region = office.region
    return region is not None and region.stable_key in scope.region_keys


def _ensure_manage(actor: User | None) -> None:
    if actor is None:
        return
    if getattr(actor, "is_superuser", False):
        return
    if not has_effective_permission(actor, MANAGE_AGENT_CONTRACTS):
        raise PermissionDenied(_("You cannot manage agent contracts."))


def _authorize(actor: User | None, contract: AgentContract, action: str) -> None:
    if action in SYSTEM_ACTIONS and actor is None:
        return
    if action in {"mark_viewed", "mark_signed"}:
        if actor is None:
            raise PermissionDenied(_("Authentication required."))
        if getattr(actor, "is_superuser", False):
            return
        if actor.pk == contract.recipient_id:
            return
        _ensure_manage(actor)
        return
    if action in SYSTEM_ACTIONS and actor is not None:
        _ensure_manage(actor)
        return
    _ensure_manage(actor)


def _snapshot_row(contract: AgentContract) -> dict:
    return {
        "status": contract.status,
        "sent_at": contract.sent_at.isoformat() if contract.sent_at else None,
        "viewed_at": contract.viewed_at.isoformat() if contract.viewed_at else None,
        "signed_at": contract.signed_at.isoformat() if contract.signed_at else None,
        "activated_at": (
            contract.activated_at.isoformat() if contract.activated_at else None
        ),
        "superseded_at": (
            contract.superseded_at.isoformat() if contract.superseded_at else None
        ),
        "expired_at": (
            contract.expired_at.isoformat() if contract.expired_at else None
        ),
        "terminated_at": (
            contract.terminated_at.isoformat() if contract.terminated_at else None
        ),
        "calculation_rule_version": contract.calculation_rule_version,
    }


def _validate_issuance_sources(contract: AgentContract) -> None:
    """Re-check agent, office, and template before leaving the draft pipeline."""
    recipient = contract.recipient
    if not recipient.is_active:
        raise TransitionRefused(str(_("Recipient account is inactive.")))
    if recipient.agent_status != ACTIVE_AGENT_STATUS:
        raise TransitionRefused(str(_("Issuance requires an active agent status.")))
    office = contract.office
    if not office.is_active:
        raise TransitionRefused(str(_("Owning office is inactive.")))
    if not office.is_assignable:
        raise TransitionRefused(str(_("Owning office cannot be assigned contracts.")))
    template_version = contract.template_version
    if template_version is None:
        raise TransitionRefused(
            str(_("Choose a published template version before issuing."))
        )
    if template_version.status != template_version.Status.PUBLISHED:
        raise TransitionRefused(
            str(_("Only a published template version can be issued."))
        )
    if not contract.party_snapshot or not contract.office_snapshot:
        raise TransitionRefused(
            str(_("Issuance requires frozen party and office snapshots."))
        )


def _refresh_issuance_snapshots(contract: AgentContract) -> None:
    contract.party_snapshot = party_snapshot(contract.recipient)
    contract.office_snapshot = office_snapshot(contract.office)
    contract.terms_snapshot = terms_snapshot_from_contract(contract)
    contract.calculation_rule_version = (
        contract.calculation_rule_version or CURRENT_RULE_VERSION
    )


def _queue_pdf_generation(contract_id: int) -> None:
    def _enqueue() -> None:
        from apps.contract.tasks import generate_contract_pdf

        generate_contract_pdf.delay(contract_id)

    transaction.on_commit(_enqueue)


def _apply_transition(
    locked: AgentContract,
    *,
    action: str,
    now,
) -> None:
    target = _TARGET_STATUS[action]

    if action == "submit_for_review":
        if locked.status != ContractStatus.DRAFT:
            raise TransitionRefused(str(_("Only a draft can be submitted for review.")))
        locked.full_clean()
        locked.terms_snapshot = terms_snapshot_from_contract(locked)
    elif action == "reopen":
        if locked.status != ContractStatus.READY_FOR_REVIEW:
            raise TransitionRefused(
                str(_("Only a ready-for-review contract can be reopened."))
            )
    elif action == "issue":
        if locked.status != ContractStatus.READY_FOR_REVIEW:
            raise TransitionRefused(
                str(_("Only a ready-for-review contract can be issued."))
            )
        _validate_issuance_sources(locked)
        locked.full_clean()
        _refresh_issuance_snapshots(locked)
        locked.sent_at = now
    elif action == "mark_viewed":
        if locked.status != ContractStatus.SENT:
            raise TransitionRefused(str(_("Only a sent contract can be viewed.")))
        locked.viewed_at = now
    elif action == "mark_signed":
        if locked.status not in {ContractStatus.SENT, ContractStatus.VIEWED}:
            raise TransitionRefused(
                str(_("Only a sent or viewed contract can be marked signed."))
            )
        locked.signed_at = now
    elif action == "activate":
        if locked.status != ContractStatus.SIGNED:
            raise TransitionRefused(str(_("Only a signed contract can be activated.")))
        locked.activated_at = now
        _supersede_other_active(locked, now=now)
    elif action == "supersede":
        if locked.status in TERMINAL_STATUSES:
            raise TransitionRefused(str(_("A terminal contract cannot be superseded.")))
        if locked.status == ContractStatus.DRAFT:
            raise TransitionRefused(str(_("A draft cannot be superseded.")))
        locked.superseded_at = now
    elif action == "terminate":
        if locked.status in TERMINAL_STATUSES:
            raise TransitionRefused(
                str(_("A terminal contract cannot be terminated again."))
            )
        locked.terminated_at = now
    elif action == "expire":
        if locked.status != ContractStatus.ACTIVE:
            raise TransitionRefused(str(_("Only an active contract can expire.")))
        locked.expired_at = now
    elif action == "mark_generation_error":
        if locked.status != ContractStatus.SENT:
            raise TransitionRefused(
                str(_("Only a sent contract can enter generation error."))
            )
    elif action == "retry_generation":
        if locked.status != ContractStatus.GENERATION_ERROR:
            raise TransitionRefused(
                str(_("Only a generation-error contract can retry generation."))
            )
    else:
        raise TransitionRefused(str(_("That is not a contract action.")))

    locked.status = target


def _supersede_other_active(contract: AgentContract, *, now) -> None:
    siblings = (
        AgentContract.objects.select_for_update(of=("self",))
        .filter(recipient_id=contract.recipient_id, status=ContractStatus.ACTIVE)
        .exclude(pk=contract.pk)
    )
    for sibling in siblings:
        before = _snapshot_row(sibling)
        sibling.status = ContractStatus.SUPERSEDED
        sibling.superseded_at = now
        with allow_status_write():
            sibling.save(update_fields=["status", "superseded_at", "updated_at"])
        _log(
            "contract.superseded",
            actor=None,
            contract=sibling,
            before=before,
            after=_snapshot_row(sibling),
            system_label="lifecycle",
        )


def _log(
    action: str,
    *,
    actor: User | None,
    contract: AgentContract,
    before: dict,
    after: dict,
    system_label: str = "system",
    metadata: dict | None = None,
) -> None:
    audit_actor = (
        actor_from_user(actor) if actor is not None else system_actor(system_label)
    )
    log_event(
        action,
        actor=audit_actor,
        target=AuditTarget(
            target_type=AgentContract._meta.label_lower,
            target_id=str(contract.public_id),
            target_label=f"contract:{contract.public_id}",
            target_snapshot={
                "status": after.get("status"),
                "recipient_id": contract.recipient_id,
                "office_id": contract.office_id,
            },
        ),
        before=before,
        after=after,
        outcome=AuditEvent.Outcome.SUCCESS,
        source="service",
        channel="contract",
        office_id=getattr(contract.office, "stable_key", "") or "",
        metadata=metadata or {},
    )


def _emit_domain(
    name: str,
    *,
    actor: User | None,
    contract: AgentContract,
    now,
) -> None:
    payload: dict = {
        "contract_id": str(contract.public_id),
        "office_id": str(contract.office_id),
        "agent_id": str(contract.recipient_id),
        "status": contract.status,
        "occurred_at": now.isoformat(),
    }
    if name == "contract.signed":
        payload = {
            "contract_id": str(contract.public_id),
            "signer_id": str(contract.recipient_id),
            "signed_at": (contract.signed_at or now).isoformat(),
        }
    publish_event(
        name,
        actor_id=str(actor.pk) if actor is not None else "system",
        subject=str(contract.public_id),
        payload=payload,
    )


def transition(
    *,
    actor: User | None,
    contract: AgentContract,
    action: str,
    expected_version: str,
    confirmed: bool = False,
    idempotency_key: str = "",
    now=None,
) -> AgentContract:
    """One explicit lifecycle move. Authorize, then lock and apply."""
    if action not in TRANSITIONS:
        raise TransitionRefused(str(_("That is not a contract action.")))
    if action in CONFIRM_REQUIRED and not confirmed:
        raise ConfirmationRequired(action)
    _authorize(actor, contract, action)
    return _transition(
        actor=actor,
        contract=contract,
        action=action,
        expected_version=expected_version,
        confirmed=confirmed,
        idempotency_key=idempotency_key,
        now=now,
    )


@transaction.atomic
def _transition(
    *,
    actor: User | None,
    contract: AgentContract,
    action: str,
    expected_version: str,
    confirmed: bool,
    idempotency_key: str,
    now=None,
) -> AgentContract:
    moment = now or timezone.now()
    locked = _lock(contract.pk)
    _authorize(actor, locked, action)
    _assert_fresh(locked, expected_version)

    target = _TARGET_STATUS[action]
    if locked.status == target:
        # Idempotent retry: already there; no second audit/event/queue.
        return locked

    before = _snapshot_row(locked)
    _apply_transition(locked, action=action, now=moment)

    with allow_status_write():
        locked.full_clean()
        locked.save()

    after = _snapshot_row(locked)
    audit_name = _AUDIT_ACTION[action]
    _log(
        audit_name,
        actor=actor,
        contract=locked,
        before=before,
        after=after,
        metadata={"idempotency_key": idempotency_key} if idempotency_key else {},
    )
    domain_name = _DOMAIN_EVENT.get(action)
    if domain_name:
        _emit_domain(domain_name, actor=actor, contract=locked, now=moment)

    if action in {"issue", "retry_generation"}:
        _queue_pdf_generation(locked.pk)

    if action in AGENT_EMAIL_ACTIONS:
        _queue_agent_status_email(locked.pk, action=action)

    if action in {
        "mark_signed",
        "activate",
        "supersede",
        "terminate",
        "expire",
    }:
        _queue_suppress_stale_reminders(locked.pk)

    return locked


def _queue_suppress_stale_reminders(contract_pk: int) -> None:
    def _run() -> None:
        from apps.contract.notification_schedule import suppress_stale_reminders

        refreshed = AgentContract.objects.filter(pk=contract_pk).first()
        if refreshed is None:
            return
        try:
            suppress_stale_reminders(refreshed)
        except Exception:  # noqa: BLE001
            logger.exception(
                "suppress stale contract reminders failed id=%s", contract_pk
            )

    transaction.on_commit(_run)


def _queue_agent_status_email(contract_pk: int, *, action: str) -> None:
    from apps.contract.emails import send_lifecycle_status_email

    def _send() -> None:
        refreshed = (
            AgentContract.objects.select_related("recipient")
            .filter(pk=contract_pk)
            .first()
        )
        if refreshed is None:
            return
        try:
            send_lifecycle_status_email(refreshed, action=action)
        except Exception:  # noqa: BLE001
            logger.exception(
                "lifecycle email after %s failed id=%s",
                action,
                contract_pk,
            )

    transaction.on_commit(_send)


@dataclass(frozen=True)
class LifecycleCapabilities:
    can_manage: bool
    is_recipient: bool


def resolve_capabilities(actor: User, contract: AgentContract) -> LifecycleCapabilities:
    manage = bool(
        getattr(actor, "is_superuser", False)
        or has_effective_permission(actor, MANAGE_AGENT_CONTRACTS)
    )
    return LifecycleCapabilities(
        can_manage=manage,
        is_recipient=actor.pk == contract.recipient_id,
    )


def allowed_actions(actor: User | None, contract: AgentContract) -> list[str]:
    """Presentation adapter: which lifecycle buttons this actor may see."""
    status = contract.status
    actions: list[str] = []

    def add(name: str, predicate: Callable[[], bool]) -> None:
        if predicate():
            actions.append(name)

    if actor is None:
        return []

    caps = resolve_capabilities(actor, contract)
    add(
        "submit_for_review",
        lambda: caps.can_manage and status == ContractStatus.DRAFT,
    )
    add(
        "reopen",
        lambda: caps.can_manage and status == ContractStatus.READY_FOR_REVIEW,
    )
    add(
        "issue",
        lambda: caps.can_manage and status == ContractStatus.READY_FOR_REVIEW,
    )
    add(
        "mark_viewed",
        lambda: (
            (caps.can_manage or caps.is_recipient) and status == ContractStatus.SENT
        ),
    )
    add(
        "mark_signed",
        lambda: (
            caps.can_manage and status in {ContractStatus.SENT, ContractStatus.VIEWED}
        ),
    )
    add("activate", lambda: caps.can_manage and status == ContractStatus.SIGNED)
    add(
        "supersede",
        lambda: (
            caps.can_manage
            and status not in TERMINAL_STATUSES
            and status != ContractStatus.DRAFT
            and status in (PIPELINE_STATUSES | {ContractStatus.ACTIVE})
        ),
    )
    add(
        "terminate",
        lambda: caps.can_manage and status not in TERMINAL_STATUSES,
    )
    add("expire", lambda: caps.can_manage and status == ContractStatus.ACTIVE)
    add(
        "retry_generation",
        lambda: caps.can_manage and status == ContractStatus.GENERATION_ERROR,
    )
    return actions


def expire_due_contracts(*, as_of: date | None = None) -> int:
    """Expire active contracts whose ``expires_on`` is strictly before ``as_of``.

    Safe to re-run: already-expired rows are skipped by the queryset and by
    idempotent ``expire`` transitions.
    """
    today = as_of or timezone.localdate()
    due = list(
        AgentContract.objects.filter(
            status=ContractStatus.ACTIVE,
            expires_on__isnull=False,
            expires_on__lt=today,
        ).order_by("pk")
    )
    count = 0
    for contract in due:
        try:
            transition(
                actor=None,
                contract=contract,
                action="expire",
                expected_version=contract_version(contract),
                confirmed=False,
            )
            count += 1
        except (StaleContractVersion, TransitionRefused) as exc:
            logger.info(
                "expire skipped contract=%s reason=%s",
                contract.public_id,
                exc,
            )
    return count
