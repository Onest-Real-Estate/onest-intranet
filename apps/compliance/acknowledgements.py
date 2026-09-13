"""Policy acknowledgement requirements, acknowledgements, and waivers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.http import Http404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.translation import gettext_lazy as _

from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.compliance.audience import recipients_for, visible_to
from apps.compliance.models import (
    PolicyAcknowledgement,
    PolicyAcknowledgementCorrection,
    PolicyAcknowledgementWaiver,
    PolicyFile,
    PolicyRequirement,
    PolicyVersion,
    PolicyVersionAccess,
)
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.roles import ROLE_BY_KEY
from apps.user.services.hierarchy import descendant_queryset
from apps.user.services.role_assignments import has_effective_permission
from apps.web.authorization import scope_queryset_for_user_office

MANAGE_PERMISSION = "web.manage_policies"
VIEW_COMPLIANCE_PERMISSION = "web.view_compliance"
VIEW_ACK_PERMISSION = "web.view_policy_acknowledgements"
WAIVE_PERMISSION = "web.waive_policy_acknowledgements"
DEFAULT_ACK_DUE_DAYS = 14
REPORT_USER_CAP = 200
REPORT_POLICY_CAP = 50

_VIEW_PERMISSIONS = (
    MANAGE_PERMISSION,
    VIEW_COMPLIANCE_PERMISSION,
    VIEW_ACK_PERMISSION,
)


def _due_days() -> int:
    return int(getattr(settings, "COMPLIANCE_ACK_DUE_DAYS", DEFAULT_ACK_DUE_DAYS))


def _has_any_permission(actor: User, *codenames: str) -> bool:
    return any(has_effective_permission(actor, code) for code in codenames)


def prior_family_sibling(version: PolicyVersion) -> PolicyVersion | None:
    return (
        PolicyVersion.objects.filter(
            version_family=version.version_family,
            version_number__lt=version.version_number,
        )
        .order_by("-version_number")
        .first()
    )


def family_satisfaction_counts(user: User, version: PolicyVersion) -> bool:
    """Whether this user has already satisfied the version's requirement."""
    if PolicyAcknowledgement.objects.filter(user=user, policy_version=version).exists():
        return True
    if PolicyAcknowledgementWaiver.objects.filter(
        user=user, policy_version=version, is_active=True
    ).exists():
        return True
    prior = prior_family_sibling(version)
    if prior is None or prior.reacknowledge_on_supersede:
        return False
    prior_ids = PolicyVersion.objects.filter(
        version_family=version.version_family,
        version_number__lt=version.version_number,
    ).values("pk")
    if PolicyAcknowledgement.objects.filter(
        user=user, policy_version_id__in=prior_ids
    ).exists():
        return True
    return PolicyAcknowledgementWaiver.objects.filter(
        user=user, policy_version_id__in=prior_ids, is_active=True
    ).exists()


def family_satisfied_user_ids(version: PolicyVersion) -> set[int]:
    """Users whose prior-family evidence satisfies this version."""
    acked = set(
        PolicyAcknowledgement.objects.filter(policy_version=version).values_list(
            "user_id", flat=True
        )
    )
    waived = set(
        PolicyAcknowledgementWaiver.objects.filter(
            policy_version=version, is_active=True
        ).values_list("user_id", flat=True)
    )
    satisfied = acked | waived
    prior = prior_family_sibling(version)
    if prior is None or prior.reacknowledge_on_supersede:
        return satisfied
    prior_ids = PolicyVersion.objects.filter(
        version_family=version.version_family,
        version_number__lt=version.version_number,
    ).values("pk")
    satisfied.update(
        PolicyAcknowledgement.objects.filter(
            policy_version_id__in=prior_ids
        ).values_list("user_id", flat=True)
    )
    satisfied.update(
        PolicyAcknowledgementWaiver.objects.filter(
            policy_version_id__in=prior_ids, is_active=True
        ).values_list("user_id", flat=True)
    )
    return satisfied


def on_policy_published(
    version: PolicyVersion, actor: User, *, now=None, due_at=None
) -> PolicyRequirement | None:
    """Create a mandatory acknowledgement requirement when publishing."""
    if not version.is_mandatory:
        return None
    moment = now or timezone.now()
    deadline = due_at or (moment + timedelta(days=_due_days()))
    PolicyRequirement.objects.filter(policy_version=version, is_active=True).update(
        is_active=False
    )
    requirement = PolicyRequirement.objects.create(
        policy_version=version,
        due_at=deadline,
        is_active=True,
    )
    log_event(
        "compliance.requirement_created",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=PolicyVersion._meta.label_lower,
            target_id=str(version.pk),
            target_label=version.title,
        ),
        after={"due_days": _due_days(), "is_mandatory": True},
    )
    return requirement


def _active_requirement(version: PolicyVersion) -> PolicyRequirement | None:
    return (
        PolicyRequirement.objects.filter(policy_version=version, is_active=True)
        .order_by("-created_at")
        .first()
    )


def version_has_document_files(version: PolicyVersion) -> bool:
    return PolicyFile.objects.filter(
        policy_version=version,
        role=PolicyFile.Role.DOCUMENT,
        is_active=True,
        processing_state=PolicyFile.ProcessingState.READY,
    ).exists()


def record_access(
    user: User,
    version: PolicyVersion,
    *,
    kind: str,
    policy_file: PolicyFile | None = None,
) -> PolicyVersionAccess | None:
    """Record one version-bound access. Replays update the existing row."""
    checksum = (version.content_checksum or "").strip()
    if not checksum:
        return None
    if kind == PolicyVersionAccess.Kind.DETAIL:
        row, created = PolicyVersionAccess.objects.get_or_create(
            user=user,
            policy_version=version,
            kind=PolicyVersionAccess.Kind.DETAIL,
            defaults={"content_checksum": checksum, "policy_file": None},
        )
    else:
        if policy_file is None:
            return None
        row, created = PolicyVersionAccess.objects.get_or_create(
            user=user,
            policy_version=version,
            kind=PolicyVersionAccess.Kind.DOCUMENT,
            policy_file=policy_file,
            defaults={"content_checksum": checksum},
        )
    if not created and row.content_checksum != checksum:
        row.content_checksum = checksum
        row.save(update_fields=["content_checksum", "accessed_at"])
    return row


def access_gate(user: User, version: PolicyVersion) -> dict[str, bool]:
    checksum = (version.content_checksum or "").strip()
    must_open = version_has_document_files(version)
    if not checksum:
        return {"mustOpenDocument": must_open, "documentAccessed": False}
    detail_ok = PolicyVersionAccess.objects.filter(
        user=user,
        policy_version=version,
        kind=PolicyVersionAccess.Kind.DETAIL,
        content_checksum=checksum,
    ).exists()
    if not must_open:
        return {"mustOpenDocument": False, "documentAccessed": detail_ok}
    document_ok = PolicyVersionAccess.objects.filter(
        user=user,
        policy_version=version,
        kind=PolicyVersionAccess.Kind.DOCUMENT,
        content_checksum=checksum,
    ).exists()
    return {
        "mustOpenDocument": True,
        "documentAccessed": detail_ok and document_ok,
    }


def user_ack_status(user: User | None, version: PolicyVersion) -> dict[str, Any]:
    gate = {"mustOpenDocument": False, "documentAccessed": False}
    if user is None or not getattr(user, "is_authenticated", False):
        return {
            "acknowledged": False,
            "required": False,
            "dueAt": None,
            "canAcknowledge": False,
            "waived": False,
            "acknowledgedAt": None,
            **gate,
        }
    ack = (
        PolicyAcknowledgement.objects.filter(user=user, policy_version=version)
        .order_by("-acknowledged_at")
        .first()
    )
    waiver = PolicyAcknowledgementWaiver.objects.filter(
        user=user, policy_version=version, is_active=True
    ).first()
    requirement = _active_requirement(version) if version.is_mandatory else None
    satisfied = family_satisfaction_counts(user, version)
    required = bool(requirement and version.is_mandatory and not satisfied)
    can_ack = (
        version.status == PolicyVersion.Status.PUBLISHED
        and bool(version.content_checksum)
        and ack is None
        and waiver is None
    )
    gate = access_gate(user, version)
    return {
        "acknowledged": ack is not None,
        "required": required,
        "dueAt": requirement.due_at.isoformat()
        if requirement and requirement.due_at
        else None,
        "canAcknowledge": can_ack,
        "waived": waiver is not None,
        "acknowledgedAt": ack.acknowledged_at.isoformat() if ack else None,
        **gate,
    }


def _request_meta(request) -> dict[str, Any]:
    if request is None:
        return {}
    meta = getattr(request, "META", {}) or {}
    request_id = (
        meta.get("HTTP_X_REQUEST_ID")
        or getattr(request, "headers", {}).get("X-Request-ID")
        or ""
    )
    return {
        "ip": (meta.get("REMOTE_ADDR") or "")[:64],
        "userAgent": (meta.get("HTTP_USER_AGENT") or "")[:255],
        "requestId": str(request_id)[:64],
    }


def _assert_access_gate(user: User, version: PolicyVersion) -> None:
    gate = access_gate(user, version)
    if gate["documentAccessed"]:
        return
    if gate["mustOpenDocument"]:
        raise ValidationError(
            {
                "form": [
                    _(
                        "Open the current policy document before acknowledging "
                        "this version."
                    )
                ]
            }
        )
    raise ValidationError(
        {
            "form": [
                _("Open this policy version before acknowledging it."),
            ]
        }
    )


@transaction.atomic
def acknowledge(
    user: User,
    version_id: int,
    *,
    expected_checksum: str,
    disclosure_version: int,
    request=None,
) -> PolicyAcknowledgement:
    version = (
        PolicyVersion.objects.select_for_update(of=("self",))
        .filter(pk=version_id)
        .first()
    )
    if version is None:
        raise Http404("No policy matches that id.")
    if not visible_to(user, version):
        raise Http404("No policy matches that id.")
    if version.status != PolicyVersion.Status.PUBLISHED:
        raise ValidationError(
            {"form": [_("Only published policies can be acknowledged.")]}
        )
    if (
        not version.content_checksum
        or version.content_checksum != (expected_checksum or "").strip()
    ):
        raise ValidationError(
            {
                "form": [
                    _(
                        "This policy changed since you opened it. "
                        "Reload and acknowledge the current version."
                    )
                ]
            }
        )
    if disclosure_version != version.disclosure_version:
        raise ValidationError(
            {
                "form": [
                    _("The acknowledgement disclosure changed. Reload and try again.")
                ]
            }
        )

    existing = PolicyAcknowledgement.objects.filter(
        user=user, policy_version=version
    ).first()
    if existing is not None:
        return existing

    if PolicyAcknowledgementWaiver.objects.filter(
        user=user, policy_version=version, is_active=True
    ).exists():
        raise ValidationError({"form": [_("This acknowledgement was waived.")]})

    _assert_access_gate(user, version)

    row = PolicyAcknowledgement(
        user=user,
        policy_version=version,
        content_checksum=version.content_checksum,
        disclosure_version=version.disclosure_version,
        disclosure_text=version.acknowledgement_disclosure,
        request_meta=_request_meta(request),
    )
    try:
        row.full_clean()
        row.save()
    except (IntegrityError, ValidationError):
        raced = PolicyAcknowledgement.objects.filter(
            user=user, policy_version=version
        ).first()
        if raced is None:
            raise
        return raced
    log_event(
        "compliance.acknowledged",
        actor=actor_from_user(user),
        target=AuditTarget(
            target_type=PolicyVersion._meta.label_lower,
            target_id=str(version.pk),
            target_label=version.title,
        ),
        after={"content_checksum": row.content_checksum},
    )
    expire_ack_reminders(user, version)
    return row


def expire_ack_reminders(user: User, version: PolicyVersion, *, now=None) -> int:
    """Expire unread acknowledgement reminders after completion."""
    from apps.notifications.models import Notification

    moment = now or timezone.now()
    return (
        Notification.objects.filter(
            recipient=user,
            source_module="compliance",
            source_record_type="policy_version",
            source_record_id=str(version.pk),
            event_key="policy.ack_reminder",
            archived_at__isnull=True,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=moment))
        .update(expires_at=moment)
    )


@transaction.atomic
def waive(
    actor: User,
    *,
    user_id: int,
    version_id: int,
    reason: str,
) -> PolicyAcknowledgementWaiver:
    if not has_effective_permission(actor, WAIVE_PERMISSION):
        raise PermissionDenied("You cannot waive policy acknowledgements.")

    version = PolicyVersion.objects.filter(pk=version_id).first()
    if version is None:
        raise Http404("No policy matches that id.")

    from apps.compliance.administration import publication_queryset

    if not publication_queryset(actor).filter(pk=version.pk).exists():
        raise Http404("No policy matches that id.")

    target_user = scoped_users(actor).filter(pk=user_id, is_active=True).first()
    if target_user is None:
        raise Http404("No user matches that id.")

    cleaned_reason = (reason or "").strip()
    if len(cleaned_reason) < 8:
        raise ValidationError(
            {"reason": [_("Explain the waiver in at least 8 characters.")]}
        )

    existing = PolicyAcknowledgementWaiver.objects.filter(
        user=target_user, policy_version=version
    ).first()
    if existing is not None and existing.is_active:
        return existing

    if PolicyAcknowledgement.objects.filter(
        user=target_user, policy_version=version
    ).exists():
        raise ValidationError({"form": [_("That person has already acknowledged.")]})

    if existing is not None:
        existing.reason = cleaned_reason
        existing.waived_by = actor
        existing.is_active = True
        existing.full_clean()
        existing.save(update_fields=["reason", "waived_by", "is_active", "waived_at"])
        row = existing
    else:
        row = PolicyAcknowledgementWaiver(
            user=target_user,
            policy_version=version,
            reason=cleaned_reason,
            waived_by=actor,
            is_active=True,
        )
        row.full_clean()
        row.save()
    log_event(
        "compliance.waived",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=PolicyVersion._meta.label_lower,
            target_id=str(version.pk),
            target_label=version.title,
        ),
        after={"user_id": target_user.pk, "reason": cleaned_reason[:200]},
    )
    expire_ack_reminders(target_user, version)
    return row


@transaction.atomic
def correct_acknowledgement(
    actor: User,
    *,
    user_id: int,
    version_id: int,
    kind: str,
    reason: str,
) -> PolicyAcknowledgementCorrection:
    if not has_effective_permission(actor, WAIVE_PERMISSION):
        raise PermissionDenied("You cannot correct policy acknowledgements.")

    version = PolicyVersion.objects.filter(pk=version_id).first()
    if version is None:
        raise Http404("No policy matches that id.")

    from apps.compliance.administration import publication_queryset

    if not publication_queryset(actor).filter(pk=version.pk).exists():
        raise Http404("No policy matches that id.")

    target_user = scoped_users(actor).filter(pk=user_id, is_active=True).first()
    if target_user is None:
        raise Http404("No user matches that id.")

    cleaned_reason = (reason or "").strip()
    if len(cleaned_reason) < 8:
        raise ValidationError(
            {"reason": [_("Explain the correction in at least 8 characters.")]}
        )
    if kind not in PolicyAcknowledgementCorrection.Kind.values:
        raise ValidationError({"kind": [_("Choose a valid correction kind.")]})

    if kind == PolicyAcknowledgementCorrection.Kind.REVOKE_WAIVER:
        waiver = PolicyAcknowledgementWaiver.objects.filter(
            user=target_user, policy_version=version, is_active=True
        ).first()
        if waiver is None:
            raise ValidationError({"form": [_("There is no active waiver to revoke.")]})
        waiver.is_active = False
        waiver.save(update_fields=["is_active"])

    row = PolicyAcknowledgementCorrection(
        user=target_user,
        policy_version=version,
        kind=kind,
        reason=cleaned_reason,
        corrected_by=actor,
    )
    row.full_clean()
    row.save()
    log_event(
        "compliance.corrected",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=PolicyVersion._meta.label_lower,
            target_id=str(version.pk),
            target_label=version.title,
        ),
        after={
            "user_id": target_user.pk,
            "kind": kind,
            "reason": cleaned_reason[:200],
        },
    )
    return row


def scoped_users(actor: User) -> QuerySet[User]:
    base = User.objects.filter(is_active=True).select_related(
        "office", "office__region"
    )
    return scope_queryset_for_user_office(actor, base, field_name="office")


def users_in_effective_audience(
    version: PolicyVersion, users: QuerySet[User], *, at=None
) -> QuerySet[User]:
    audience_ids = recipients_for(version, at=at).values("pk")
    filtered = users.filter(pk__in=audience_ids)
    codes = [code.upper() for code in (version.jurisdiction_state_codes or [])]
    if not codes:
        return filtered
    return filtered.filter(Q(license_state__in=codes) | Q(office__state__in=codes))


def open_requirements_for(
    user: User, *, now=None, overdue_only: bool = False
) -> list[PolicyRequirement]:
    from apps.compliance.audience import visible_policies
    from apps.compliance.services import apply_jurisdiction_visibility

    moment = now or timezone.now()
    visible = apply_jurisdiction_visibility(visible_policies(user, at=moment), user)
    visible_ids = visible.values("pk")
    queryset = (
        PolicyRequirement.objects.filter(
            is_active=True,
            policy_version_id__in=visible_ids,
            policy_version__is_mandatory=True,
            policy_version__status=PolicyVersion.Status.PUBLISHED,
        )
        .select_related("policy_version", "policy_version__category")
        .order_by("due_at", "pk")
    )
    if overdue_only:
        queryset = queryset.filter(Q(due_at__isnull=False), due_at__lt=moment)
    return [
        requirement
        for requirement in queryset
        if not family_satisfaction_counts(user, requirement.policy_version)
    ]


def overdue_requirements_for(user: User, *, now=None) -> list[PolicyRequirement]:
    return open_requirements_for(user, now=now, overdue_only=True)


def _parse_filter_datetime(raw: str, *, end_of_day: bool = False):
    value = (raw or "").strip()
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is not None:
        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
    day = parse_date(value)
    if day is None:
        return None
    clock = datetime.max.time() if end_of_day else datetime.min.time()
    moment = datetime.combine(day, clock)
    return timezone.make_aware(moment, timezone.get_current_timezone())


def _apply_report_user_filters(users: QuerySet[User], filters) -> QuerySet[User]:
    q = (filters.get("q") or "").strip()[:120]
    if q:
        users = users.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
        )
    office_key = (filters.get("office") or "").strip()
    if office_key:
        users = users.filter(office__stable_key=office_key)
    region_key = (filters.get("region") or "").strip()
    if region_key:
        region = Office.objects.filter(stable_key=region_key).first()
        if region is None:
            return users.none()
        office_ids = descendant_queryset(region).values("pk")
        users = users.filter(office_id__in=office_ids)
    role = (filters.get("role") or "").strip()
    if role:
        moment = timezone.now()
        holders = (
            UserRoleAssignment.objects.filter(role=role)
            .exclude(status=UserRoleAssignment.Status.REVOKED)
            .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=moment))
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=moment))
            .filter(Q(revoked_at__isnull=True) | Q(revoked_at__gt=moment))
            .values("user_id")
        )
        users = users.filter(pk__in=holders)
    return users


def report_filter_options(actor: User) -> dict[str, Any]:
    from apps.compliance.administration import publication_queryset

    offices = (
        Office.objects.filter(pk__in=scoped_users(actor).values("office_id"))
        .order_by("sort_order", "name")
        .distinct()
    )
    regions = offices.filter(
        kind__in=[Office.Kind.HEAD_OFFICE, Office.Kind.REGION]
    ) | Office.objects.filter(
        pk__in=offices.exclude(region_id=None).values("region_id")
    )
    policies = publication_queryset(actor).filter(
        status=PolicyVersion.Status.PUBLISHED, is_mandatory=True
    )
    return {
        "policies": [
            {"value": str(row.pk), "label": row.title}
            for row in policies.order_by("title", "pk")[:REPORT_POLICY_CAP]
        ],
        "offices": [{"value": row.stable_key, "label": row.name} for row in offices],
        "regions": [
            {"value": row.stable_key, "label": row.name}
            for row in regions.order_by("sort_order", "name").distinct()
        ],
        "roles": [
            {
                "value": code,
                "label": ROLE_BY_KEY[code].label if code in ROLE_BY_KEY else code,
            }
            for code in sorted(ROLE_BY_KEY)
        ],
        "statuses": [
            {"value": "pending", "label": "Pending"},
            {"value": "acknowledged", "label": "Acknowledged"},
            {"value": "waived", "label": "Waived"},
            {"value": "overdue", "label": "Overdue"},
        ],
    }


def scoped_report(actor: User, filters) -> dict[str, Any]:
    """Acknowledgement report rows for audience members in the actor's scope."""
    from apps.compliance.administration import publication_queryset

    if not _has_any_permission(actor, *_VIEW_PERMISSIONS):
        raise PermissionDenied("You cannot view acknowledgement reports.")

    version_id = str(filters.get("policy") or filters.get("policyId") or "").strip()
    versions = publication_queryset(actor).filter(
        status=PolicyVersion.Status.PUBLISHED, is_mandatory=True
    )
    if version_id.isdigit():
        versions = versions.filter(pk=int(version_id))

    users = _apply_report_user_filters(scoped_users(actor), filters)
    due_from = _parse_filter_datetime(str(filters.get("dueFrom") or ""))
    due_to = _parse_filter_datetime(str(filters.get("dueTo") or ""), end_of_day=True)
    status_filter = str(filters.get("status") or "").strip()

    rows: list[dict[str, Any]] = []
    now = timezone.now()
    for version in versions.order_by("title", "pk")[:REPORT_POLICY_CAP]:
        requirement = _active_requirement(version)
        due_at = requirement.due_at if requirement is not None else None
        if due_from and (due_at is None or due_at < due_from):
            continue
        if due_to and (due_at is None or due_at > due_to):
            continue
        audience = list(
            users_in_effective_audience(version, users).order_by(
                "last_name", "first_name", "pk"
            )[:REPORT_USER_CAP]
        )
        acks = {
            row.user_id: row  # ty: ignore[unresolved-attribute]
            for row in PolicyAcknowledgement.objects.filter(
                policy_version=version, user_id__in=[person.pk for person in audience]
            )
        }
        waivers = {
            row.user_id: row  # ty: ignore[unresolved-attribute]
            for row in PolicyAcknowledgementWaiver.objects.filter(
                policy_version=version,
                is_active=True,
                user_id__in=[person.pk for person in audience],
            )
        }
        carried = family_satisfied_user_ids(version)
        for person in audience:
            ack = acks.get(person.pk)
            waiver = waivers.get(person.pk)
            status = "pending"
            acknowledged_at = ack.acknowledged_at if ack else None
            if ack is not None:
                status = "acknowledged"
            elif waiver is not None:
                status = "waived"
            elif person.pk in carried:
                status = "acknowledged"
            elif requirement and requirement.due_at and requirement.due_at < now:
                status = "overdue"
            if status_filter and status != status_filter:
                continue
            rows.append(
                {
                    "userId": person.pk,
                    "userName": person.get_full_name() or person.email,
                    "email": person.email,
                    "officeName": person.office.name if person.office else "",
                    "officeKey": person.office.stable_key if person.office else "",
                    "policyId": version.pk,
                    "policyTitle": version.title,
                    "status": status,
                    "dueAt": (
                        requirement.due_at.isoformat()
                        if requirement and requirement.due_at
                        else None
                    ),
                    "acknowledgedAt": (
                        acknowledged_at.isoformat() if acknowledged_at else None
                    ),
                }
            )
    return {"items": rows, "totalItems": len(rows)}


def open_item_rows(actor: User, *, filters=None, row_limit: int | None = 500):
    """Audience-scoped pending/overdue acknowledgement rows for reports."""
    report = scoped_report(actor, filters or {})
    open_rows = [
        row for row in report["items"] if row["status"] in {"pending", "overdue"}
    ]
    truncated = False
    if row_limit is not None and len(open_rows) > row_limit:
        truncated = True
        open_rows = open_rows[:row_limit]
    return open_rows, truncated
