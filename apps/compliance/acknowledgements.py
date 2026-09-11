"""Policy acknowledgement requirements, acknowledgements, and waivers."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.http import Http404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.compliance.audience import visible_to
from apps.compliance.models import (
    PolicyAcknowledgement,
    PolicyAcknowledgementWaiver,
    PolicyRequirement,
    PolicyVersion,
)
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission
from apps.web.authorization import scope_queryset_for_user_office

MANAGE_PERMISSION = "web.manage_policies"
DEFAULT_ACK_DUE_DAYS = 14


def _due_days() -> int:
    return int(getattr(settings, "COMPLIANCE_ACK_DUE_DAYS", DEFAULT_ACK_DUE_DAYS))


def on_policy_published(version: PolicyVersion, actor: User, *, now=None) -> None:
    """Create a mandatory acknowledgement requirement when publishing."""
    if not version.is_mandatory:
        return
    moment = now or timezone.now()
    PolicyRequirement.objects.filter(policy_version=version, is_active=True).update(
        is_active=False
    )
    PolicyRequirement.objects.create(
        policy_version=version,
        due_at=moment + timedelta(days=_due_days()),
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


def _active_requirement(version: PolicyVersion) -> PolicyRequirement | None:
    return (
        PolicyRequirement.objects.filter(policy_version=version, is_active=True)
        .order_by("-created_at")
        .first()
    )


def user_ack_status(user: User | None, version: PolicyVersion) -> dict[str, Any]:
    if user is None or not getattr(user, "is_authenticated", False):
        return {
            "acknowledged": False,
            "required": False,
            "dueAt": None,
            "canAcknowledge": False,
            "waived": False,
            "acknowledgedAt": None,
        }
    ack = (
        PolicyAcknowledgement.objects.filter(user=user, policy_version=version)
        .order_by("-acknowledged_at")
        .first()
    )
    waiver = PolicyAcknowledgementWaiver.objects.filter(
        user=user, policy_version=version
    ).first()
    requirement = _active_requirement(version) if version.is_mandatory else None
    required = bool(requirement and version.is_mandatory and not ack and not waiver)
    can_ack = (
        version.status == PolicyVersion.Status.PUBLISHED
        and bool(version.content_checksum)
        and ack is None
        and waiver is None
    )
    return {
        "acknowledged": ack is not None,
        "required": required,
        "dueAt": requirement.due_at.isoformat()
        if requirement and requirement.due_at
        else None,
        "canAcknowledge": can_ack,
        "waived": waiver is not None,
        "acknowledgedAt": ack.acknowledged_at.isoformat() if ack else None,
    }


def _request_meta(request) -> dict[str, Any]:
    if request is None:
        return {}
    meta = getattr(request, "META", {}) or {}
    return {
        "ip": meta.get("REMOTE_ADDR", "")[:64],
        "userAgent": (meta.get("HTTP_USER_AGENT") or "")[:255],
    }


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
        user=user, policy_version=version
    ).exists():
        raise ValidationError({"form": [_("This acknowledgement was waived.")]})

    row = PolicyAcknowledgement(
        user=user,
        policy_version=version,
        content_checksum=version.content_checksum,
        disclosure_version=version.disclosure_version,
        request_meta=_request_meta(request),
    )
    row.full_clean()
    row.save()
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
    return row


@transaction.atomic
def waive(
    actor: User,
    *,
    user_id: int,
    version_id: int,
    reason: str,
) -> PolicyAcknowledgementWaiver:
    if not has_effective_permission(actor, MANAGE_PERMISSION):
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
    if existing is not None:
        return existing

    if PolicyAcknowledgement.objects.filter(
        user=target_user, policy_version=version
    ).exists():
        raise ValidationError({"form": [_("That person has already acknowledged.")]})

    row = PolicyAcknowledgementWaiver(
        user=target_user,
        policy_version=version,
        reason=cleaned_reason,
        waived_by=actor,
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
    return row


def scoped_users(actor: User) -> QuerySet[User]:
    base = User.objects.filter(is_active=True).select_related("office")
    return scope_queryset_for_user_office(actor, base, field_name="office")


def overdue_requirements_for(user: User, *, now=None) -> list[PolicyRequirement]:
    from apps.compliance.audience import visible_policies
    from apps.compliance.services import apply_jurisdiction_visibility

    moment = now or timezone.now()
    visible = apply_jurisdiction_visibility(visible_policies(user, at=moment), user)
    visible_ids = visible.values("pk")
    acked = PolicyAcknowledgement.objects.filter(user=user).values("policy_version_id")
    waived = PolicyAcknowledgementWaiver.objects.filter(user=user).values(
        "policy_version_id"
    )
    return list(
        PolicyRequirement.objects.filter(
            is_active=True,
            policy_version_id__in=visible_ids,
            policy_version__is_mandatory=True,
            policy_version__status=PolicyVersion.Status.PUBLISHED,
        )
        .filter(Q(due_at__isnull=False), due_at__lt=moment)
        .exclude(policy_version_id__in=acked)
        .exclude(policy_version_id__in=waived)
        .select_related("policy_version", "policy_version__category")
        .order_by("due_at", "pk")
    )


def scoped_report(actor: User, filters) -> dict[str, Any]:
    """Acknowledgement report rows for users in the actor's office scope."""
    from apps.compliance.administration import publication_queryset

    if not has_effective_permission(actor, MANAGE_PERMISSION) and not (
        has_effective_permission(actor, "web.view_compliance")
    ):
        raise PermissionDenied("You cannot view acknowledgement reports.")

    version_id = str(filters.get("policy") or filters.get("policyId") or "").strip()
    versions = publication_queryset(actor).filter(
        status=PolicyVersion.Status.PUBLISHED, is_mandatory=True
    )
    if version_id.isdigit():
        versions = versions.filter(pk=int(version_id))

    users = scoped_users(actor)
    q = (filters.get("q") or "").strip()[:120]
    if q:
        users = users.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
        )

    rows: list[dict[str, Any]] = []
    for version in versions.order_by("title", "pk")[:50]:
        requirement = _active_requirement(version)
        acks = {
            row.user.pk: row
            for row in PolicyAcknowledgement.objects.filter(
                policy_version=version
            ).select_related("user")
        }
        waivers = {
            row.user.pk: row
            for row in PolicyAcknowledgementWaiver.objects.filter(
                policy_version=version
            ).select_related("user")
        }
        for person in users.order_by("last_name", "first_name", "pk")[:200]:
            ack = acks.get(person.pk)
            waiver = waivers.get(person.pk)
            status = "pending"
            if ack is not None:
                status = "acknowledged"
            elif waiver is not None:
                status = "waived"
            elif (
                requirement
                and requirement.due_at
                and requirement.due_at < timezone.now()
            ):
                status = "overdue"
            rows.append(
                {
                    "userId": person.pk,
                    "userName": person.get_full_name() or person.email,
                    "email": person.email,
                    "officeName": person.office.name if person.office else "",
                    "policyId": version.pk,
                    "policyTitle": version.title,
                    "status": status,
                    "dueAt": (
                        requirement.due_at.isoformat()
                        if requirement and requirement.due_at
                        else None
                    ),
                    "acknowledgedAt": (
                        ack.acknowledged_at.isoformat() if ack else None
                    ),
                }
            )
    return {"items": rows, "totalItems": len(rows)}
