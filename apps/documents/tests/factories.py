"""Shared test helpers for the documents library."""

from __future__ import annotations

import hashlib

from django.core.files.base import ContentFile
from django.utils import timezone

from apps.documents.audience import AudienceSelector
from apps.documents.models import (
    DocumentAudience,
    DocumentCategory,
    DocumentFamily,
    DocumentFile,
    DocumentVersion,
)
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.tests.test_profile import completed_user

_TINY_PDF = b"%PDF-1.7\n" + b"x" * 40


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def category(code: str = "listing") -> DocumentCategory:
    return DocumentCategory.objects.get(code=code)


def assign(user, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def agent(slug="fairfax-va", email="docs-agent@example.com") -> User:
    return completed_user(email=email, office=office(slug))


def _apply_audience(
    version: DocumentVersion,
    audience: tuple[AudienceSelector, ...],
) -> None:
    DocumentAudience.objects.filter(document_version=version).delete()
    DocumentAudience.objects.bulk_create(
        [
            DocumentAudience(
                document_version=version,
                kind=selector.kind,
                role=selector.role
                if selector.kind == DocumentAudience.Kind.ROLE
                else "",
                office=selector.office
                if selector.kind
                in {DocumentAudience.Kind.REGION, DocumentAudience.Kind.OFFICE}
                else None,
                user=selector.user
                if selector.kind == DocumentAudience.Kind.USER
                else None,
            )
            for selector in audience
        ]
    )


def family(*, key: str, owner_office: Office) -> DocumentFamily:
    row, _created = DocumentFamily.objects.get_or_create(
        key=key, defaults={"owner_office": owner_office}
    )
    return row


def attach_ready_file(
    version: DocumentVersion,
    *,
    actor: User | None = None,
    name: str = "form.pdf",
) -> DocumentFile:
    checksum = hashlib.sha256(_TINY_PDF).hexdigest()
    row = DocumentFile(
        document_version=version,
        display_name=name,
        media_type="application/pdf",
        byte_size=len(_TINY_PDF),
        checksum=checksum,
        processing_state=DocumentFile.ProcessingState.READY,
        uploaded_by=actor,
    )
    row.file.save(name, ContentFile(_TINY_PDF), save=False)
    row.save()
    return row


def publish_document(
    *,
    key: str,
    name: str,
    owner_office: Office,
    audience: tuple[AudienceSelector, ...] | None = None,
    category_code: str = "listing",
    version_number: int = 1,
    description: str = "Description",
    jurisdiction_state_codes: list[str] | None = None,
    effective_at=None,
    expires_at=None,
    with_file: bool = True,
    status: str = DocumentVersion.Status.PUBLISHED,
) -> DocumentVersion:
    row_family = family(key=key, owner_office=owner_office)
    version = DocumentVersion.objects.create(
        family=row_family,
        name=name,
        description=description,
        category=category(category_code),
        jurisdiction_state_codes=jurisdiction_state_codes or [],
        status=status,
        version_number=version_number,
        published_at=(
            timezone.now() if status == DocumentVersion.Status.PUBLISHED else None
        ),
        effective_at=effective_at,
        expires_at=expires_at,
    )
    selectors = audience or (AudienceSelector(kind=DocumentAudience.Kind.COMPANY),)
    _apply_audience(version, selectors)
    if with_file:
        attach_ready_file(version)
    return version
