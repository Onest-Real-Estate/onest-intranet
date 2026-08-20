"""Account access: disabling and reactivating a user, and what that costs them.

Kept out of :mod:`apps.user.services.agent_administration` on purpose. Every
field that module writes annotates a record; this one *ends somebody's access*.
Bundling the two would mean one form contract, one permission, and one audit
action covering both "corrected their agent ID" and "locked them out at 4pm on
a Friday".

The rules the rest of the stack relies on:

* the act is **explicit** — a dedicated endpoint, a dedicated permission, and a
  confirmation carrying a business reason, never a checkbox on a ModelForm;
* the act is **idempotent** — disabling a disabled account changes nothing and
  writes no second lifecycle event;
* disabling **invalidates every live session** so the change is enforced on the
  target's next request rather than whenever their cookie happens to expire;
* both directions emit an audit event and a domain event, and the domain event
  dispatches only after the transaction commits.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.events import publish
from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.models import User
from apps.user.services.agent_administration import (
    StaleAdministrationVersion,
    administration_version,
    invalidate_permission_cache,
    is_user_in_scope,
    locked_user_queryset,
)
from apps.user.services.role_assignments import has_effective_permission

MANAGE_PERMISSION = "user.manage_account_state"

DISABLED_ACTION = "user.account.disabled"
REACTIVATED_ACTION = "user.account.reactivated"
DOMAIN_EVENT = "user.account.state_changed"

BUSINESS_REASON_MAX_LENGTH = 500


@dataclass(frozen=True)
class AccountStateResult:
    """What the write actually did, so the caller can word the response."""

    user: User
    changed: bool
    is_active: bool
    sessions_revoked: int

    @property
    def action(self) -> str:
        return REACTIVATED_ACTION if self.is_active else DISABLED_ACTION


# ---------------------------------------------------------------------------
# Authority
# ---------------------------------------------------------------------------


def _log_denial(actor, target: User | None, *, reason: str) -> None:
    log_event(
        "security.account_state.denied",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=User._meta.label_lower,
            target_id=str(getattr(target, "pk", "") or ""),
            target_label=getattr(target, "email", ""),
        ),
        outcome=AuditEvent.Outcome.DENIED,
        source="request",
        channel="account_state",
        reason=reason,
        office_id=(
            target.office.stable_key
            if target is not None and target.office is not None
            else ""
        ),
    )


def can_manage_account_state(actor: User, target: User) -> bool:
    """Never true for one's own record — locking yourself out is not a feature.

    It is also the door a compromised session would use to strand the people
    who could revoke it, so the guard is unconditional rather than a warning.
    """
    if not getattr(actor, "is_authenticated", False):
        return False
    if actor.pk is not None and actor.pk == target.pk:
        return False
    if getattr(actor, "is_superuser", False):
        return True
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        return False
    return is_user_in_scope(actor, target)


def ensure_account_state_authority(actor: User, target: User) -> None:
    if actor.pk is not None and actor.pk == target.pk:
        _log_denial(actor, target, reason="self_account_state")
        raise PermissionDenied("You cannot disable or reactivate your own account.")
    if not can_manage_account_state(actor, target):
        _log_denial(actor, target, reason="out_of_scope_or_unauthorized")
        raise PermissionDenied("You may not change this user's account access.")


# ---------------------------------------------------------------------------
# Session invalidation
# ---------------------------------------------------------------------------


def revoke_user_sessions(user: User) -> int:
    """End every unexpired session belonging to ``user``.

    Django keeps no user → session index, so the only correct answer is to
    decode the live rows and match ``_auth_user_id``. Expired rows are skipped
    because they already authenticate nobody, and a decode failure is treated
    as "not this user" rather than raising: one corrupt row must not stop the
    rest of somebody's sessions from being cut.

    Deletion goes through the **configured session engine**, not through
    ``Session.objects.delete()``. Under ``cached_db`` — what this project runs
    whenever Redis is configured — a read is served from the cache first, so
    dropping the database row on its own would leave a working session in
    Redis until it expired on its own. That is exactly the window this function
    exists to close.
    """
    from django.contrib.sessions.models import Session

    store = import_module(settings.SESSION_ENGINE).SessionStore
    target_id = str(user.pk)
    doomed = [
        session.session_key
        for session in Session.objects.filter(expire_date__gte=timezone.now()).only(
            "session_key", "session_data"
        )
        if _session_belongs_to(session, target_id)
    ]
    for session_key in doomed:
        store(session_key).delete()
    return len(doomed)


def _session_belongs_to(session, target_id: str) -> bool:
    try:
        return session.get_decoded().get("_auth_user_id") == target_id
    except Exception:  # noqa: BLE001 - a tampered row is simply not a match
        return False


# ---------------------------------------------------------------------------
# Mutation
# ---------------------------------------------------------------------------


def set_account_state(
    *,
    actor: User,
    target: User,
    enabled: bool,
    business_reason: str,
    expected_version: str,
) -> AccountStateResult:
    """Disable or reactivate one account, once.

    Authority is re-checked here rather than only in the view: a crafted POST
    reaches this function by the same path the form does. The check runs
    *outside* the transaction because it writes a denial event before raising,
    and a denial rolled back by its own exception explains nothing.
    """
    ensure_account_state_authority(actor, target)
    reason = " ".join((business_reason or "").split())
    if not reason:
        raise ValidationError(
            {"business_reason": "Say why this account is changing hands."}
        )
    if len(reason) > BUSINESS_REASON_MAX_LENGTH:
        raise ValidationError(
            {
                "business_reason": (
                    f"Keep the reason under {BUSINESS_REASON_MAX_LENGTH} characters."
                )
            }
        )
    return _write_account_state(
        actor=actor,
        target=target,
        enabled=enabled,
        reason=reason,
        expected_version=expected_version,
    )


@transaction.atomic
def _write_account_state(
    *,
    actor: User,
    target: User,
    enabled: bool,
    reason: str,
    expected_version: str,
) -> AccountStateResult:
    locked = locked_user_queryset().get(pk=target.pk)
    if administration_version(locked) != (expected_version or ""):
        raise StaleAdministrationVersion()

    if locked.is_active == enabled:
        # Idempotent: the requested state is already the stored state. No
        # lifecycle event, no session sweep, no provenance bump — a repeated
        # submit must not read as a second decision in the audit trail.
        return AccountStateResult(
            user=locked, changed=False, is_active=enabled, sessions_revoked=0
        )

    locked.is_active = enabled
    locked.administration_updated_at = timezone.now()
    locked.administration_updated_by = actor
    locked.save(
        update_fields=[
            "is_active",
            "administration_updated_at",
            "administration_updated_by",
        ]
    )

    # Sessions are cut inside the transaction so a rollback cannot leave
    # somebody signed out of an account that was never disabled.
    revoked = 0 if enabled else revoke_user_sessions(locked)

    log_event(
        REACTIVATED_ACTION if enabled else DISABLED_ACTION,
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=User._meta.label_lower,
            target_id=str(locked.pk),
            target_label=locked.email,
        ),
        before={"is_active": not enabled},
        after={"is_active": enabled},
        office_id=(locked.office.stable_key if locked.office else ""),
        region_id=(
            locked.office.region.stable_key
            if locked.office and locked.office.region
            else ""
        ),
        channel="account_state",
        reason=reason,
        metadata={"sessions_revoked": revoked},
    )
    publish(
        DOMAIN_EVENT,
        actor_id=str(actor.pk),
        subject=f"user:{locked.pk}",
        payload={
            "user_id": locked.pk,
            "is_active": enabled,
            "sessions_revoked": revoked,
        },
    )

    invalidate_permission_cache(locked)
    invalidate_permission_cache(target)
    return AccountStateResult(
        user=locked, changed=True, is_active=enabled, sessions_revoked=revoked
    )


# ---------------------------------------------------------------------------
# Payload
# ---------------------------------------------------------------------------


def account_state_payload(actor: User, target: User) -> dict:
    """The account-access panel, already narrowed to what the actor may do."""
    manageable = can_manage_account_state(actor, target)
    return {
        "isActive": target.is_active,
        "label": "Active" if target.is_active else "Disabled",
        "tone": "success" if target.is_active else "destructive",
        "lastLoginAt": (target.last_login.isoformat() if target.last_login else None),
        "joinedAt": target.date_joined.isoformat() if target.date_joined else None,
        "canManage": manageable,
        # Why the buttons are missing, in the words the page renders.
        "reason": (
            ""
            if manageable
            else (
                "Nobody changes their own account access."
                if actor.pk == target.pk
                else "You may read this record but not change its account access."
            )
        ),
        "sessionPolicy": (
            "Disabling ends every signed-in session immediately and blocks the "
            "next request. Reactivating restores access at the next sign-in."
        ),
    }
