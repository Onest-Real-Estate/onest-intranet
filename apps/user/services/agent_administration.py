"""Broker-controlled profile administration: policy, scope, and persistence.

The self-service half of a profile lives in :mod:`apps.user.services.profile`.
This module owns the other half — the values an agent must not be able to set
about themselves — and answers three questions in one place so no caller has
to re-derive them:

* **who** may see or change another user's administrative record,
* **what** they may change about that user, given their own scope, and
* **what happens** afterwards: audit, cached-permission invalidation, and the
  default role assignment that follows an office move.

Every guard here is server-side. The React page mirrors it for the sake of the
person using it; nothing in it is load-bearing.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.administration_fields import (
    AGENT_STATUS_LABELS,
    AGENT_STATUS_TONES,
    ENGAGED_AGENT_STATUSES,
    LICENSE_VERIFICATION_LABELS,
    LICENSE_VERIFICATION_TONES,
    UNVERIFIED,
    VERIFIED,
    agent_status_options,
    license_verification_options,
)
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.roles import (
    ROLE_BY_KEY,
    ROLE_DEFINITIONS,
    ROLE_LABELS,
    ScopeType,
)
from apps.user.services.role_assignments import (
    get_effective_access,
    has_effective_permission,
)

VIEW_PERMISSION = "user.view_user_administration"
CHANGE_PERMISSION = "user.change_user_administration"

# Django field names the administration form owns. Nothing outside this set is
# writable through it, and nothing inside it is writable through /profile.
ADMINISTERED_FIELDS: tuple[str, ...] = (
    "agent_status",
    "start_date",
    "agent_identifier",
    "internal_notes",
    "license_verification_state",
    "license_verification_note",
    "office",
)

# The subset whose *values* are safe to keep in the audit trail. Operational
# notes are deliberately absent: the trail records that they changed, who
# changed them, and when — never their prose.
AUDIT_VALUE_FIELDS: tuple[str, ...] = (
    "agent_status",
    "start_date",
    "agent_identifier",
    "license_verification_state",
    "office",
)

# Changes that move somebody's access, rather than annotating their record.
# The page must confirm these before submitting and explain their effect.
HIGH_IMPACT_FIELDS: frozenset[str] = frozenset({"office", "agent_status"})


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdministrationScope:
    """What one actor may reach. ``company_wide`` short-circuits the rest."""

    company_wide: bool
    region_keys: frozenset[str]
    office_keys: frozenset[str]

    @property
    def is_empty(self) -> bool:
        return not (self.company_wide or self.region_keys or self.office_keys)


def administration_scope(actor: User) -> AdministrationScope:
    if getattr(actor, "is_superuser", False):
        return AdministrationScope(True, frozenset(), frozenset())
    access = get_effective_access(actor)
    return AdministrationScope(
        company_wide=access.company_wide,
        region_keys=access.region_keys,
        office_keys=access.office_keys,
    )


def _office_in_scope(office: Office | None, scope: AdministrationScope) -> bool:
    """An office is in scope when the actor holds it, or holds its region."""
    if scope.company_wide:
        return True
    if office is None:
        # Nobody but a company-wide administrator may touch a user who has no
        # office: there is no scope that can be said to contain them.
        return False
    if office.stable_key in scope.office_keys:
        return True
    if office.stable_key in scope.region_keys:
        return True
    region = office.region
    return region is not None and region.stable_key in scope.region_keys


def administered_user_queryset(actor: User) -> QuerySet[User]:
    """Users this actor may administer, filtered on the database, not in Python.

    Never takes a client-supplied office: the filter is built from the actor's
    own effective access and nothing else.
    """
    queryset = User.objects.select_related("office", "office__region").order_by(
        "first_name", "last_name", "email"
    )
    scope = administration_scope(actor)
    if scope.company_wide:
        return queryset
    if scope.is_empty:
        return queryset.none()
    filters = Q()
    if scope.office_keys:
        filters |= Q(office__stable_key__in=sorted(scope.office_keys))
    if scope.region_keys:
        keys = sorted(scope.region_keys)
        filters |= Q(office__region__stable_key__in=keys) | Q(
            office__stable_key__in=keys
        )
    return queryset.filter(filters)


def assignable_office_queryset(actor: User) -> QuerySet[Office]:
    """Offices this actor may move somebody *into*.

    Inactive and non-assignable offices are excluded here rather than in the
    form so a stale office cannot be resurrected by a crafted POST.
    """
    queryset = Office.assignable_queryset()
    scope = administration_scope(actor)
    if scope.company_wide:
        return queryset
    if scope.is_empty:
        return queryset.none()
    filters = Q()
    if scope.office_keys:
        filters |= Q(stable_key__in=sorted(scope.office_keys))
    if scope.region_keys:
        filters |= Q(region__stable_key__in=sorted(scope.region_keys))
    return queryset.filter(filters)


# ---------------------------------------------------------------------------
# Authority
# ---------------------------------------------------------------------------


def _log_denial(actor, target: User | None, *, reason: str, detail: dict | None = None):
    log_event(
        "security.user_administration.denied",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=User._meta.label_lower,
            target_id=str(getattr(target, "pk", "") or ""),
            target_label=getattr(target, "email", ""),
            target_snapshot=detail or {},
        ),
        outcome=AuditEvent.Outcome.DENIED,
        source="request",
        channel="user_administration",
        reason=reason,
        office_id=(
            target.office.stable_key
            if target is not None and target.office is not None
            else ""
        ),
    )


def can_view_administration(actor: User, target: User) -> bool:
    if not getattr(actor, "is_authenticated", False):
        return False
    if getattr(actor, "is_superuser", False):
        return True
    if not has_effective_permission(actor, VIEW_PERMISSION):
        return False
    return _office_in_scope(target.office, administration_scope(actor))


def can_change_administration(actor: User, target: User) -> bool:
    """Never true for one's own record — that is the self-promotion door."""
    if actor.pk is not None and actor.pk == target.pk:
        return False
    if getattr(actor, "is_superuser", False):
        return True
    if not has_effective_permission(actor, CHANGE_PERMISSION):
        return False
    return _office_in_scope(target.office, administration_scope(actor))


def ensure_view_authority(actor: User, target: User) -> None:
    if not can_view_administration(actor, target):
        _log_denial(actor, target, reason="out_of_scope_or_unauthorized_view")
        raise PermissionDenied("You may not view this user's administrative record.")


def ensure_change_authority(actor: User, target: User) -> None:
    if actor.pk is not None and actor.pk == target.pk:
        _log_denial(actor, target, reason="self_administration")
        raise PermissionDenied("You cannot administer your own record.")
    if not can_change_administration(actor, target):
        _log_denial(actor, target, reason="out_of_scope_or_unauthorized_change")
        raise PermissionDenied("You may not change this user's administrative record.")


def ensure_office_delegable(actor: User, office: Office | None) -> None:
    """The destination office must sit inside the actor's own grant.

    Checked against the queryset rather than the submitted value so a crafted
    office id outside the actor's region fails on the server even when the
    select never offered it.
    """
    if office is None:
        return
    if not assignable_office_queryset(actor).filter(pk=office.pk).exists():
        _log_denial(
            actor,
            None,
            reason="office_outside_delegation",
            detail={"office_id": office.pk},
        )
        raise PermissionDenied("That office is outside the scope you may delegate.")


def _scope_probe(actor: User, scope_type: str) -> Office | None:
    """A representative office the actor could name at this scope level.

    ``actor_can_manage_assignments`` answers per office; the form only needs to
    know whether *any* office in reach would be accepted, so one probe stands
    in for the whole set.
    """
    if scope_type == ScopeType.REGION:
        scope = administration_scope(actor)
        regions = Office.objects.filter(kind=Office.Kind.REGION, is_active=True)
        if not scope.company_wide:
            if not scope.region_keys:
                return None
            regions = regions.filter(stable_key__in=sorted(scope.region_keys))
        return regions.first()
    return assignable_office_queryset(actor).first()


def delegable_role_options(actor: User) -> list[dict[str, Any]]:
    """Roles this actor may grant, with the scopes they may grant them at.

    Mirrors ``role_assignments.actor_can_manage_assignments``; that service is
    still the enforcement point, this only keeps the form from offering a role
    the server would refuse. Protected roles (Admin) never appear: nobody
    grants themselves a peer.
    """
    from apps.user.services.role_assignments import actor_can_manage_assignments

    scope_labels = dict(ScopeType.CHOICES)
    options: list[dict[str, Any]] = []
    for definition in ROLE_DEFINITIONS:
        scopes: list[dict[str, str]] = []
        for scope_type in definition.valid_scope_types:
            probe = (
                None
                if scope_type == ScopeType.COMPANY
                else _scope_probe(actor, scope_type)
            )
            if scope_type != ScopeType.COMPANY and probe is None:
                continue
            if actor_can_manage_assignments(
                actor,
                role=definition.key,
                target_scope_type=scope_type,
                scope_office=probe,
            ):
                scopes.append({"value": scope_type, "label": scope_labels[scope_type]})
        if scopes:
            options.append(
                {
                    "value": definition.key,
                    "label": definition.label,
                    "scopes": scopes,
                }
            )
    return options


# ---------------------------------------------------------------------------
# Derived, read-only data owned elsewhere
# ---------------------------------------------------------------------------


def contract_status(user: User) -> dict[str, Any]:
    """Agent contract standing, read from the contract domain.

    Deliberately has no column of its own: a status an administrator can type
    into a profile is a status that drifts from the contract it claims to
    describe. Until the contract app lands, this reports "not connected"
    rather than inventing a value.
    """
    try:  # pragma: no cover - exercised once the contract app exists
        module = import_module("apps.contract.services")
    except ModuleNotFoundError:
        return {
            "status": None,
            "label": "Not connected",
            "tone": "neutral",
            "source": "contract",
            "available": False,
            "reason": "Agent contracts are not connected to the hub yet.",
        }
    return module.agent_contract_status(user)  # pragma: no cover


# ---------------------------------------------------------------------------
# Cached-permission invalidation
# ---------------------------------------------------------------------------

_PERMISSION_CACHE_ATTRS = (
    "_perm_cache",
    "_user_perm_cache",
    "_group_perm_cache",
    "_inertia_access_context",
)


def invalidate_permission_cache(user: User) -> None:
    """Drop every per-instance permission cache Django or the shell keeps.

    Effective access is otherwise recomputed per request, so the target user
    picks the change up on their next one — but the in-process instance that
    just moved office would keep answering from a cache filled before the move.
    """
    for attr in _PERMISSION_CACHE_ATTRS:
        try:
            delattr(user, attr)
        except AttributeError:
            continue


# ---------------------------------------------------------------------------
# Role assignment guards layered on top of the assignment service
# ---------------------------------------------------------------------------


def would_strip_last_live_assignment(
    user: User, *, assignment: UserRoleAssignment
) -> bool:
    remaining = (
        UserRoleAssignment.objects.filter(
            user=user,
            status__in=[
                UserRoleAssignment.Status.SCHEDULED,
                UserRoleAssignment.Status.ACTIVE,
            ],
        )
        .exclude(pk=assignment.pk)
        .exists()
    )
    return not remaining


def ensure_revocation_leaves_valid_access(
    user: User, *, assignment: UserRoleAssignment
) -> None:
    """Refuse to leave a working agent with no role at all.

    Somebody who has left or been suspended may be stripped bare; somebody
    still working here must keep at least one assignment, or their next request
    silently falls back to whatever their legacy groups happen to say.
    """
    if user.agent_status not in ENGAGED_AGENT_STATUSES:
        return
    if would_strip_last_live_assignment(user, assignment=assignment):
        raise ValidationError(
            {
                "__all__": (
                    "This is the only live role assignment for an agent who is "
                    "still working here. Assign a replacement role first, or "
                    "set their status to suspended or departed."
                )
            }
        )


# ---------------------------------------------------------------------------
# Field catalog
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdminFieldSpec:
    key: str
    prop: str
    label: str
    description: str
    # Who owns the value. Rendered beside it so nobody has to guess where a
    # correction has to come from.
    source: str
    high_impact: bool = False
    # Withheld from the person the record is about, however it is rendered.
    private: bool = False


ADMIN_FIELD_SPECS: tuple[AdminFieldSpec, ...] = (
    AdminFieldSpec(
        key="office",
        prop="officeId",
        label="Office",
        description=(
            "Determines what this person can see across the hub and which "
            "default Agent assignment they carry."
        ),
        source="Broker administration",
        high_impact=True,
    ),
    AdminFieldSpec(
        key="agent_status",
        prop="agentStatus",
        label="Agent status",
        description="Where this person stands with the brokerage.",
        source="Broker administration",
        high_impact=True,
    ),
    AdminFieldSpec(
        key="start_date",
        prop="startDate",
        label="Start date",
        description="The date this person joined the brokerage.",
        source="Broker administration",
    ),
    AdminFieldSpec(
        key="agent_identifier",
        prop="agentIdentifier",
        label="Agent ID",
        description="Internal identifier used by back-office systems.",
        source="Broker administration",
    ),
    AdminFieldSpec(
        key="license_verification_state",
        prop="licenseVerificationState",
        label="License verification",
        description=(
            "Set after checking the state license record. Resets to not "
            "verified whenever the agent edits their own license details."
        ),
        source="Broker compliance",
    ),
    AdminFieldSpec(
        key="license_verification_note",
        prop="licenseVerificationNote",
        label="Verification note",
        description="What was checked, and against which record.",
        source="Broker compliance",
    ),
    AdminFieldSpec(
        key="internal_notes",
        prop="internalNotes",
        label="Operational notes",
        description=(
            "Administrative notes about this person. Never shown to them, "
            "never written into the audit trail as text."
        ),
        source="Broker administration",
        private=True,
    ),
)

ADMIN_FIELD_BY_KEY = {spec.key: spec for spec in ADMIN_FIELD_SPECS}


class StaleAdministrationVersion(Exception):
    """Raised when the record changed since the form was rendered."""

    message = (
        "Somebody else changed this record while you were editing it. "
        "Reload the page to see their changes, then reapply yours."
    )


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------


def administration_version(user: User) -> str:
    """Opaque token identifying the administrative state of the record."""
    stamp = user.administration_updated_at
    return stamp.isoformat() if stamp else ""


def _office_summary(office: Office | None) -> dict | None:
    if office is None:
        return None
    return {
        "id": office.pk,
        "name": office.name,
        "pathLabel": office.path_label(),
        "regionName": office.region_name(),
        "isActive": office.is_active,
        "isAssignable": office.is_assignable,
    }


def _status_payload(value: str) -> dict:
    return {
        "value": value,
        "label": AGENT_STATUS_LABELS.get(value, value),
        "tone": AGENT_STATUS_TONES.get(value, "neutral"),
    }


def _verification_payload(user: User) -> dict:
    state = user.license_verification_state
    return {
        "state": state,
        "label": LICENSE_VERIFICATION_LABELS.get(state, state),
        "tone": LICENSE_VERIFICATION_TONES.get(state, "neutral"),
        "verifiedAt": (
            user.license_verified_at.isoformat() if user.license_verified_at else None
        ),
        "verifiedBy": (
            str(user.license_verified_by) if user.license_verified_by else None
        ),
        "note": user.license_verification_note,
    }


def administration_summary(user: User) -> dict:
    """The administrative facts a user is allowed to read about themselves.

    Everything here is rendered read-only on ``/profile``. Operational notes
    are absent by construction, not by a template forgetting to print them.
    """
    return {
        "agentStatus": _status_payload(user.agent_status),
        "startDate": user.start_date.isoformat() if user.start_date else None,
        "agentIdentifier": user.agent_identifier,
        "licenseVerification": _verification_payload(user),
        "contractStatus": contract_status(user),
        "lastReviewedAt": (
            user.administration_updated_at.isoformat()
            if user.administration_updated_at
            else None
        ),
    }


def administration_history(user: User, *, limit: int = 5) -> list[dict]:
    """Recent administrative events for this record, newest first.

    Scoped by the target rather than by the reader's audit permission: an
    administrator authorized to change this record is authorized to see what
    was changed on it.
    """
    events = AuditEvent.objects.filter(
        target_type=User._meta.label_lower,
        target_id=str(user.pk),
        action__in=[
            "user.administration.updated",
            "user.license_verification.reset",
        ],
    ).order_by("-occurred_at")[:limit]
    return [
        {
            "id": str(event.id),
            "action": event.action,
            "occurredAt": event.occurred_at.isoformat(),
            "actor": event.actor_label,
            "outcome": event.outcome,
            "fields": sorted(event.changes.keys()),
            "reason": event.reason,
        }
        for event in events
    ]


def _assignment_payload(assignment: UserRoleAssignment, *, can_revoke: bool) -> dict:
    return {
        "id": assignment.pk,
        "role": assignment.role,
        "roleLabel": ROLE_LABELS.get(assignment.role, assignment.role),
        "scopeType": assignment.scope_type,
        "scopeLabel": assignment.scope_label(),
        "status": assignment.status,
        "startsAt": assignment.starts_at.isoformat() if assignment.starts_at else None,
        "endsAt": assignment.ends_at.isoformat() if assignment.ends_at else None,
        "assignedBy": (str(assignment.assigned_by) if assignment.assigned_by else None),
        "businessReason": assignment.business_reason,
        "canRevoke": can_revoke,
    }


def role_assignment_payloads(actor: User, target: User) -> list[dict]:
    from apps.user.services.role_assignments import actor_can_manage_assignments

    assignments = (
        UserRoleAssignment.objects.filter(user=target)
        .exclude(status=UserRoleAssignment.Status.REVOKED)
        .select_related("scope_office", "scope_office__region", "assigned_by")
        .order_by("role", "-created_at")
    )
    # Resolved once for the whole table: the per-row check would otherwise
    # re-run the actor's effective access, writes included, for every row.
    access = get_effective_access(actor)
    return [
        _assignment_payload(
            assignment,
            can_revoke=(
                assignment.role in ROLE_BY_KEY
                and actor_can_manage_assignments(
                    actor,
                    role=assignment.role,
                    target_scope_type=assignment.scope_type,
                    scope_office=assignment.scope_office,
                    access=access,
                )
            ),
        )
        for assignment in assignments
    ]


def effective_access_payload(user: User) -> dict:
    """What this user's access actually resolves to right now."""
    access = get_effective_access(user)
    if access.company_wide:
        scope_label = "Brokerage-wide"
    elif access.region_keys:
        scope_label = ", ".join(
            Office.objects.filter(stable_key__in=sorted(access.region_keys))
            .order_by("sort_order", "name")
            .values_list("name", flat=True)
        )
    elif access.office_keys:
        scope_label = ", ".join(
            Office.objects.filter(stable_key__in=sorted(access.office_keys))
            .order_by("sort_order", "name")
            .values_list("name", flat=True)
        )
    else:
        scope_label = "No administrative scope"
    return {
        "roles": [ROLE_LABELS.get(key, key) for key in access.role_keys],
        "scopeLabel": scope_label,
        "isSuperuser": user.is_superuser,
        "liveAssignments": len(access.assignments),
    }


def administration_page_payload(actor: User, target: User) -> dict:
    """Everything the administration page renders, already scoped to the actor."""
    can_change = can_change_administration(actor, target)
    offices = assignable_office_queryset(actor)
    delegable_roles = delegable_role_options(actor)
    payload = {
        "subject": {
            "id": target.pk,
            "email": target.email,
            "displayName": str(target),
            "legalName": target.get_full_name().strip(),
            "preferredDisplayName": target.preferred_display_name(),
            "headshotUrl": target.headshot.url if target.headshot else None,
            "isActive": target.is_active,
            "isSelf": actor.pk == target.pk,
            "office": _office_summary(target.office),
            "profileCompleted": target.profile_completed,
        },
        "values": {
            "officeId": str(target.office.pk) if target.office else "",
            "agentStatus": target.agent_status,
            "startDate": target.start_date.isoformat() if target.start_date else "",
            "agentIdentifier": target.agent_identifier,
            "licenseVerificationState": target.license_verification_state,
            "licenseVerificationNote": target.license_verification_note,
            "internalNotes": target.internal_notes,
        },
        "version": administration_version(target),
        "fields": [
            {
                "key": spec.key,
                "prop": spec.prop,
                "label": spec.label,
                "description": spec.description,
                "source": spec.source,
                "highImpact": spec.high_impact,
                "private": spec.private,
            }
            for spec in ADMIN_FIELD_SPECS
        ],
        "license": {
            "number": target.license_number,
            "state": target.license_state,
            "expiresOn": (
                target.license_expires_on.isoformat()
                if target.license_expires_on
                else None
            ),
            "verification": _verification_payload(target),
        },
        "contractStatus": contract_status(target),
        "provenance": {
            "lastChangedAt": (
                target.administration_updated_at.isoformat()
                if target.administration_updated_at
                else None
            ),
            "lastChangedBy": (
                str(target.administration_updated_by)
                if target.administration_updated_by
                else None
            ),
        },
        "history": administration_history(target),
        "assignments": role_assignment_payloads(actor, target),
        "effectiveAccess": effective_access_payload(target),
        "options": {
            "agentStatuses": agent_status_options(),
            "licenseVerificationStates": license_verification_options(),
            "offices": [
                {
                    "id": office.pk,
                    "name": office.name,
                    "pathLabel": office.path_label(),
                    "regionName": office.region_name(),
                }
                for office in offices
            ],
            "roles": delegable_roles,
        },
        "editable": {
            "administration": can_change,
            "roleAssignments": bool(delegable_roles) and can_change,
        },
        "highImpactFields": sorted(HIGH_IMPACT_FIELDS),
    }
    if has_effective_permission(actor, "web.view_new_agents"):
        from django.urls import reverse

        from apps.user.services.onboarding_state import (
            build_onboarding_states,
            new_agent_queryset,
            state_payload,
        )

        if new_agent_queryset(actor).filter(pk=target.pk).exists():
            payload["onboardingState"] = {
                **state_payload(
                    actor,
                    build_onboarding_states([target])[0],
                    detail=False,
                ),
                "href": reverse("new_agent_onboarding", args=[target.pk]),
            }
    return payload


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


def _audit_snapshot(user: User) -> dict[str, Any]:
    """Before/after values for the trail — operational notes by shape only."""
    snapshot: dict[str, Any] = {}
    for field in AUDIT_VALUE_FIELDS:
        value = getattr(user, field)
        if field == "office":
            snapshot[field] = user.office.stable_key if user.office else None
        elif field == "start_date":
            snapshot[field] = value.isoformat() if value else None
        else:
            snapshot[field] = value
    # The note itself never leaves the database; only the fact it is set does.
    snapshot["internal_notes_present"] = bool(user.internal_notes)
    snapshot["license_verification_note_present"] = bool(user.license_verification_note)
    return snapshot


def _apply_license_verification(target: User, actor: User, previous_state: str) -> None:
    state = target.license_verification_state
    if state == previous_state:
        return
    if state == VERIFIED:
        target.license_verified_at = timezone.now()
        target.license_verified_by = actor
    else:
        target.license_verified_at = None
        target.license_verified_by = None


def update_administration(
    *,
    actor: User,
    target: User,
    cleaned: dict[str, Any],
    expected_version: str,
) -> User:
    """Persist the administrative half of a profile.

    Authority, delegation, and freshness are all re-checked here rather than in
    the view: a crafted POST reaches this function the same way the form does.

    The authority checks deliberately run *outside* the transaction below. They
    write a denial event before raising, and a denial recorded inside the
    atomic block would be rolled back by the very exception it exists to
    explain.
    """
    ensure_change_authority(actor, target)
    # Only a *move* has to be delegable. Re-checking an unchanged office would
    # trap anyone whose office has since been closed: the record could never be
    # corrected without first moving them somewhere they do not work.
    if "office" in cleaned and cleaned["office"] != target.office:
        ensure_office_delegable(actor, cleaned["office"])

    return _write_administration(
        actor=actor,
        target=target,
        cleaned=cleaned,
        expected_version=expected_version,
    )


def locked_user_queryset():
    """The target user row, locked for update, with its office loaded.

    ``of=("self",)`` is load-bearing: ``office`` is nullable, so
    ``select_related`` reaches it through a LEFT OUTER JOIN, and PostgreSQL
    refuses a bare ``FOR UPDATE`` that spans the nullable side of an outer
    join. SQLite drops row locking altogether, so nothing on a developer
    machine reproduces it — ``test_agent_administration`` compiles this
    queryset against the PostgreSQL backend to keep the guarantee testable.
    """
    return User.objects.select_for_update(of=("self",)).select_related(
        "office", "office__region"
    )


@transaction.atomic
def _write_administration(
    *,
    actor: User,
    target: User,
    cleaned: dict[str, Any],
    expected_version: str,
) -> User:
    locked = locked_user_queryset().get(pk=target.pk)
    if administration_version(locked) != (expected_version or ""):
        raise StaleAdministrationVersion()

    before = _audit_snapshot(locked)
    previous_office = locked.office
    previous_verification = locked.license_verification_state

    for field in ADMINISTERED_FIELDS:
        if field in cleaned:
            setattr(locked, field, cleaned[field])

    _apply_license_verification(locked, actor, previous_verification)
    locked.administration_updated_at = timezone.now()
    locked.administration_updated_by = actor

    office_changed = locked.office != previous_office
    locked.full_clean()
    locked.save()

    if office_changed:
        from apps.user.services.role_assignments import sync_default_agent_assignment

        sync_default_agent_assignment(
            locked,
            actor=actor,
            business_reason="Office changed by an administrator.",
        )

    after = _audit_snapshot(locked)
    log_event(
        "user.administration.updated",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=User._meta.label_lower,
            target_id=str(locked.pk),
            target_label=locked.email,
        ),
        before=before,
        after=after,
        office_id=(locked.office.stable_key if locked.office else ""),
        region_id=(
            locked.office.region.stable_key
            if locked.office and locked.office.region
            else ""
        ),
        channel="user_administration",
        metadata={"office_changed": office_changed},
    )

    # The office move above rewrites this user's scope; anything still holding
    # a permission cache filled before it would answer from the old office.
    invalidate_permission_cache(locked)
    invalidate_permission_cache(target)
    return locked


def reset_license_verification(user: User, *, reason: str) -> bool:
    """Drop a verification the agent's own edit just invalidated.

    Called from the self-service profile save: an agent who may edit their
    license number must not be able to carry a "verified" badge onto a number
    nobody checked.
    """
    if user.license_verification_state == UNVERIFIED and not user.license_verified_at:
        return False
    before = {
        "license_verification_state": user.license_verification_state,
        "license_verified_at": (
            user.license_verified_at.isoformat() if user.license_verified_at else None
        ),
    }
    user.license_verification_state = UNVERIFIED
    user.license_verified_at = None
    user.license_verified_by = None
    user.license_verification_note = ""
    user.save(
        update_fields=[
            "license_verification_state",
            "license_verified_at",
            "license_verified_by",
            "license_verification_note",
        ]
    )
    log_event(
        "user.license_verification.reset",
        actor=actor_from_user(user),
        target=AuditTarget(
            target_type=User._meta.label_lower,
            target_id=str(user.pk),
            target_label=user.email,
        ),
        before=before,
        after={"license_verification_state": UNVERIFIED, "license_verified_at": None},
        office_id=(user.office.stable_key if user.office else ""),
        channel="profile",
        reason=reason,
    )
    return True


def grant_role_assignment(
    *,
    actor: User,
    target: User,
    role: str,
    scope_type: str,
    scope_office: Office | None,
    starts_at=None,
    ends_at=None,
    business_reason: str = "",
) -> UserRoleAssignment:
    """Grant a role through the established service, after the scope check.

    The assignment service owns delegation; this adds the one thing it cannot
    know about — that the *target user* has to be inside the actor's
    administrative scope, not just the office being granted.
    """
    from apps.user.services.role_assignments import create_role_assignment

    ensure_change_authority(actor, target)
    if scope_office is not None:
        ensure_office_delegable(actor, scope_office)
    assignment = create_role_assignment(
        actor=actor,
        target_user=target,
        role=role,
        scope_type=scope_type,
        scope_office=scope_office,
        starts_at=starts_at,
        ends_at=ends_at,
        business_reason=business_reason,
    )
    invalidate_permission_cache(target)
    return assignment


def revoke_role_assignment_for_user(
    *,
    actor: User,
    target: User,
    assignment: UserRoleAssignment,
    business_reason: str = "",
) -> UserRoleAssignment:
    from apps.user.services.role_assignments import revoke_role_assignment

    ensure_change_authority(actor, target)
    if assignment.user.pk != target.pk:
        _log_denial(actor, target, reason="assignment_target_mismatch")
        raise PermissionDenied("That assignment does not belong to this user.")
    ensure_revocation_leaves_valid_access(target, assignment=assignment)
    revoked = revoke_role_assignment(
        actor=actor,
        assignment=assignment,
        business_reason=business_reason,
    )
    invalidate_permission_cache(target)
    return revoked


def scope_target_queryset(actor: User) -> QuerySet[Office]:
    """Offices *and* regions an actor may name as a role assignment's scope.

    Wider than :func:`assignable_office_queryset`, which answers a different
    question — where somebody may be seated. A region is never a workplace but
    is a perfectly ordinary scope for a Region Manager.
    """
    scope = administration_scope(actor)
    queryset = Office.visible_queryset().filter(is_active=True)
    if scope.company_wide:
        return queryset.filter(Q(is_assignable=True) | Q(kind=Office.Kind.REGION))
    if scope.is_empty:
        return queryset.none()
    filters = Q()
    if scope.office_keys:
        filters |= Q(stable_key__in=sorted(scope.office_keys))
    if scope.region_keys:
        keys = sorted(scope.region_keys)
        filters |= Q(stable_key__in=keys) | Q(region__stable_key__in=keys)
    return queryset.filter(filters)
