"""Shared test helpers for compliance policies."""

from __future__ import annotations

import uuid

from django.contrib.auth.models import Permission
from django.core.files.base import ContentFile

from apps.compliance.audience import AudienceSelector
from apps.compliance.models import (
    PolicyCategory,
    PolicyFile,
    PolicyVersion,
)
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.tests.test_profile import completed_user

_TINY_PDF = b"%PDF-1.7\n" + b"x" * 40


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def category(code: str = "manuals") -> PolicyCategory:
    return PolicyCategory.objects.get(code=code)


def assign(user, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def agent(**kwargs) -> User:
    email = (
        kwargs.pop("email", None) or f"compliance-agent-{uuid.uuid4().hex}@example.com"
    )
    return completed_user(
        email=email,
        office=kwargs.pop("office", office("fairfax-va")),
        **kwargs,
    )


def publisher(*, email: str | None = None) -> User:
    user = completed_user(
        email=email or f"compliance-publisher-{uuid.uuid4().hex}@example.com",
        office=office("fairfax-va"),
    )
    assign(user, "system_admin", "company")
    for codename in (
        "manage_policies",
        "approve_policies",
        "publish_policies",
        "view_compliance",
    ):
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="web", codename=codename)
        )
    return User.objects.get(pk=user.pk)


def attach_ready_document(
    version: PolicyVersion, *, name: str = "policy.pdf"
) -> PolicyFile:
    row = PolicyFile(
        policy_version=version,
        role=PolicyFile.Role.DOCUMENT,
        display_name=name,
        media_type="application/pdf",
        byte_size=len(_TINY_PDF),
        checksum="a" * 64,
        processing_state=PolicyFile.ProcessingState.READY,
        uploaded_by=version.created_by,
    )
    row.file.save(name, ContentFile(_TINY_PDF), save=False)
    row.full_clean(exclude={"uploaded_by"})
    row.save()
    return row


def publish_policy(
    *,
    title: str = "Handbook",
    owner_office: Office | None = None,
    audience: tuple[AudienceSelector, ...] | None = None,
    is_mandatory: bool = False,
    jurisdiction_state_codes: list[str] | None = None,
    actor: User | None = None,
) -> PolicyVersion:
    from apps.compliance.administration import (
        create_draft,
        policy_version_token,
        transition,
    )

    actor = actor or publisher()
    owning = owner_office or office("onest-head-office")
    selectors = list(audience or (AudienceSelector(kind="company"),))
    draft = create_draft(
        actor=actor,
        office=owning,
        cleaned={
            "title": title,
            "summary": "Summary",
            "body": "Body text",
            "category": category(),
            "jurisdiction_state_codes": jurisdiction_state_codes or [],
            "is_mandatory": is_mandatory,
            "reacknowledge_on_supersede": True,
            "acknowledgement_disclosure": "I acknowledge this policy.",
            "disclosure_version": 1,
            "display_order": 100,
        },
        selectors=selectors,
    )
    for action in ("submit", "approve", "publish"):
        transition(
            actor=actor,
            version=draft,
            action=action,
            expected_version=policy_version_token(draft),
        )
        draft.refresh_from_db()
    return draft
