"""The single audience predicate for policy versions.

Every surface that shows policies — library, detail, acknowledgements,
downloads, search — asks this module, and only this module, whether a reader
may see it. Selectors are **OR**: matching any selector yields visibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.compliance.models import PolicyAudience, PolicyVersion
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.roles import ROLE_BY_KEY, normalize_role_code
from apps.user.services.hierarchy import ancestors, descendant_queryset
from apps.user.services.role_assignments import get_effective_access

Kind = PolicyAudience.Kind

MANAGE_PERMISSION = "web.manage_policies"
#: Below this length a recipient search returns nothing at all.
MIN_RECIPIENT_QUERY = 2
RECIPIENT_SEARCH_LIMIT = 20


def selectors_for(policy_version: PolicyVersion) -> QuerySet[PolicyAudience]:
    """The stored selectors for one policy version, targets already joined."""
    return PolicyAudience.objects.filter(policy_version=policy_version).select_related(
        "office", "user"
    )


@dataclass(frozen=True)
class AudienceContext:
    """Everything about one reader that the predicate needs."""

    user_id: int | None
    office_id: int | None
    office_chain_ids: frozenset[int]
    role_codes: frozenset[str]
    is_authenticated: bool


def live_role_codes(user, *, at=None) -> frozenset[str]:
    if not getattr(user, "is_authenticated", False):
        return frozenset()
    moment = at or timezone.now()
    rows = (
        UserRoleAssignment.objects.filter(user=user)
        .exclude(status=UserRoleAssignment.Status.REVOKED)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=moment))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=moment))
        .filter(Q(revoked_at__isnull=True) | Q(revoked_at__gt=moment))
        .values_list("role", flat=True)
    )
    return frozenset(normalize_role_code(row) or row for row in rows)


def audience_context(user, *, at=None) -> AudienceContext:
    if not getattr(user, "is_authenticated", False):
        return AudienceContext(
            user_id=None,
            office_id=None,
            office_chain_ids=frozenset(),
            role_codes=frozenset(),
            is_authenticated=False,
        )
    office = getattr(user, "office", None)
    return AudienceContext(
        user_id=user.pk,
        office_id=office.pk if office else None,
        office_chain_ids=frozenset(node.pk for node in ancestors(office)),
        role_codes=live_role_codes(user, at=at),
        is_authenticated=True,
    )


def selector_q(context: AudienceContext) -> Q:
    if not context.is_authenticated:
        return Q(pk__in=[])

    clauses = Q(kind=Kind.COMPANY)
    if context.role_codes:
        clauses |= Q(kind=Kind.ROLE, role__in=sorted(context.role_codes))
    if context.office_chain_ids:
        clauses |= Q(kind=Kind.REGION, office_id__in=sorted(context.office_chain_ids))
    if context.office_id is not None:
        clauses |= Q(kind=Kind.OFFICE, office_id=context.office_id)
    clauses |= Q(kind=Kind.USER, user_id=context.user_id)
    return clauses


def audience_q(context: AudienceContext) -> Q:
    if not context.is_authenticated:
        return Q(pk__in=[])
    return Q(
        pk__in=PolicyAudience.objects.filter(selector_q(context)).values(
            "policy_version_id"
        )
    )


def visible_policies(user, *, at=None, queryset=None) -> QuerySet[PolicyVersion]:
    """Published, in-window policy versions whose audience includes ``user``."""
    moment = at or timezone.now()
    base = PolicyVersion.objects.all() if queryset is None else queryset
    return (
        base.published()
        .within_window(now=moment)
        .filter(audience_q(audience_context(user, at=moment)))
        .select_related("category", "owner_office", "owner_user")
    )


def visible_to(user, policy_version: PolicyVersion, *, at=None) -> bool:
    if policy_version.pk is None:
        return False
    return visible_policies(user, at=at).filter(pk=policy_version.pk).exists()


def assert_visible(
    user, policy_version: PolicyVersion, *, at=None, reason: str
) -> None:
    if visible_to(user, policy_version, at=at):
        return
    log_event(
        "security.compliance.denied",
        actor=actor_from_user(user),
        target=AuditTarget(
            target_type=PolicyVersion._meta.label_lower,
            target_id=str(policy_version.pk or ""),
            target_label=policy_version.title,
        ),
        outcome=AuditEvent.Outcome.DENIED,
        reason=reason,
    )
    raise PermissionDenied("That policy is not addressed to you.")


def recipients_for(policy_version: PolicyVersion, *, at=None) -> QuerySet[User]:
    moment = at or timezone.now()
    selectors = list(selectors_for(policy_version))
    if not selectors:
        return User.objects.none()

    if any(selector.kind == Kind.COMPANY for selector in selectors):
        return User.objects.filter(is_active=True)

    clauses = Q()
    matched = False

    role_codes = sorted(
        {selector.role for selector in selectors if selector.kind == Kind.ROLE}
    )
    if role_codes:
        live_holders = (
            UserRoleAssignment.objects.filter(role__in=role_codes)
            .exclude(status=UserRoleAssignment.Status.REVOKED)
            .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=moment))
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=moment))
            .filter(Q(revoked_at__isnull=True) | Q(revoked_at__gt=moment))
            .values("user_id")
        )
        clauses |= Q(pk__in=live_holders)
        matched = True

    region_office_ids: set[int] = set()
    for selector in selectors:
        if selector.kind == Kind.REGION and selector.office is not None:
            region_office_ids.update(
                descendant_queryset(selector.office).values_list("pk", flat=True)
            )
    if region_office_ids:
        clauses |= Q(office_id__in=sorted(region_office_ids))
        matched = True

    exact_office_ids = sorted(
        {
            selector.office.pk
            for selector in selectors
            if selector.kind == Kind.OFFICE and selector.office is not None
        }
    )
    if exact_office_ids:
        clauses |= Q(office_id__in=exact_office_ids)
        matched = True

    named_user_ids = sorted(
        {
            selector.user.pk
            for selector in selectors
            if selector.kind == Kind.USER and selector.user is not None
        }
    )
    if named_user_ids:
        clauses |= Q(pk__in=named_user_ids)
        matched = True

    if not matched:
        return User.objects.none()
    return User.objects.filter(is_active=True).filter(clauses).distinct()


@dataclass(frozen=True)
class AudienceSelector:
    kind: str
    role: str = ""
    office: Office | None = None
    user: User | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "role": self.role,
            "officeId": self.office.pk if self.office else None,
            "userId": self.user.pk if self.user else None,
        }


def _deny(actor, *, reason: str, detail: dict | None = None) -> None:
    log_event(
        "security.compliance.audience_denied",
        actor=actor_from_user(actor),
        target=AuditTarget(target_type=PolicyVersion._meta.label_lower, target_id=""),
        outcome=AuditEvent.Outcome.DENIED,
        reason=reason,
        metadata=detail or {},
    )


def targetable_office_ids(actor) -> frozenset[int]:
    from apps.web.authorization import scope_queryset_for_offices

    if getattr(actor, "is_superuser", False):
        return frozenset(Office.objects.values_list("pk", flat=True))
    access = get_effective_access(actor)
    if access.company_wide:
        return frozenset(Office.objects.values_list("pk", flat=True))
    reachable: set[int] = set()
    for node in scope_queryset_for_offices(actor, Office.objects.all()):
        reachable.update(descendant_queryset(node).values_list("pk", flat=True))
    return frozenset(reachable)


def targetable_role_codes(actor) -> frozenset[str]:
    from apps.user.services.agent_administration import delegable_role_options

    if getattr(actor, "is_superuser", False):
        return frozenset(ROLE_BY_KEY)
    return frozenset(option["value"] for option in delegable_role_options(actor))


def targetable_user_queryset(actor) -> QuerySet[User]:
    from apps.user.services.agent_administration import administered_user_queryset

    return administered_user_queryset(actor)


def assert_can_target(actor, selectors) -> None:
    from apps.user.services.role_assignments import has_effective_permission

    selectors = list(selectors)
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        _deny(actor, reason="missing_permission")
        raise PermissionDenied("You cannot manage policies.")
    if not selectors:
        raise ValidationError(
            {"audience": _("Choose at least one audience before publishing.")}
        )

    access = get_effective_access(actor)
    offices = targetable_office_ids(actor)
    roles = targetable_role_codes(actor)

    for selector in selectors:
        if selector.kind == Kind.COMPANY:
            if not (getattr(actor, "is_superuser", False) or access.company_wide):
                _deny(actor, reason="company_audience_outside_grant")
                raise PermissionDenied(
                    "Only a brokerage-wide administrator can address everyone."
                )
        elif selector.kind == Kind.ROLE:
            if selector.role not in roles:
                _deny(
                    actor,
                    reason="role_not_delegable",
                    detail={"role": selector.role},
                )
                raise PermissionDenied(
                    "That role is outside the roles you may address."
                )
        elif selector.kind in {Kind.REGION, Kind.OFFICE}:
            if selector.office is None or selector.office.pk not in offices:
                _deny(
                    actor,
                    reason="office_outside_grant",
                    detail={"office_id": getattr(selector.office, "pk", None)},
                )
                raise PermissionDenied(
                    "That office is outside the scope you may address."
                )
        elif selector.kind == Kind.USER:
            if selector.user is None or not (
                targetable_user_queryset(actor).filter(pk=selector.user.pk).exists()
            ):
                _deny(
                    actor,
                    reason="user_outside_grant",
                    detail={"user_id": getattr(selector.user, "pk", None)},
                )
                raise PermissionDenied(
                    "That person is outside the people you may address."
                )
        else:
            raise ValidationError({"audience": _("Unknown audience type.")})


def replace_audience(actor, policy_version: PolicyVersion, selectors) -> None:
    selectors = list(selectors)
    assert_can_target(actor, selectors)
    before = describe_audience(policy_version)
    selectors_for(policy_version).delete()
    PolicyAudience.objects.bulk_create(
        [
            PolicyAudience(
                policy_version=policy_version,
                kind=selector.kind,
                role=selector.role if selector.kind == Kind.ROLE else "",
                office=selector.office
                if selector.kind in {Kind.REGION, Kind.OFFICE}
                else None,
                user=selector.user if selector.kind == Kind.USER else None,
            )
            for selector in selectors
        ],
        ignore_conflicts=True,
    )
    log_event(
        "compliance.audience_changed",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=PolicyVersion._meta.label_lower,
            target_id=str(policy_version.pk),
            target_label=policy_version.title,
        ),
        before={"audience": before},
        after={"audience": describe_audience(policy_version)},
    )


def describe_audience(policy_version: PolicyVersion) -> list[dict[str, Any]]:
    order = {
        Kind.COMPANY: 0,
        Kind.ROLE: 1,
        Kind.REGION: 2,
        Kind.OFFICE: 3,
        Kind.USER: 4,
    }
    rows = [
        {
            "kind": selector.kind,
            "label": _selector_label(selector),
            "code": selector.role or "",
            "officeId": selector.office.pk if selector.office else None,
            "userId": selector.user.pk if selector.user else None,
        }
        for selector in selectors_for(policy_version)
    ]
    return sorted(rows, key=lambda row: (order.get(row["kind"], 9), row["label"]))


def _selector_label(selector: PolicyAudience) -> str:
    if selector.kind == Kind.COMPANY:
        return "Everyone at oNEST"
    if selector.kind == Kind.ROLE:
        definition = ROLE_BY_KEY.get(selector.role)
        return definition.label if definition else selector.role
    if selector.kind == Kind.REGION and selector.office is not None:
        return f"{selector.office.name} and offices under it"
    if selector.office is not None:
        return selector.office.name
    if selector.user is not None:
        return selector.user.get_full_name() or selector.user.email
    return ""


def search_recipients(actor, query: str, *, limit: int = RECIPIENT_SEARCH_LIMIT):
    from apps.user.services.role_assignments import has_effective_permission

    if not has_effective_permission(actor, MANAGE_PERMISSION):
        _deny(actor, reason="missing_permission")
        raise PermissionDenied("You cannot address policies.")

    term = (query or "").strip()[:120]
    if len(term) < MIN_RECIPIENT_QUERY:
        return []
    rows = (
        targetable_user_queryset(actor)
        .filter(
            Q(first_name__icontains=term)
            | Q(last_name__icontains=term)
            | Q(email__icontains=term)
        )
        .filter(is_active=True)[: max(1, min(limit, RECIPIENT_SEARCH_LIMIT))]
    )
    return [
        {
            "id": row.pk,
            "name": row.get_full_name() or row.email,
            "email": row.email,
            "officeName": row.office.name if row.office else "",
        }
        for row in rows
    ]
