"""Shared test helpers for marketing resources."""

from __future__ import annotations

import hashlib
import uuid

from django.core.files.base import ContentFile
from django.utils import timezone

from apps.marketing.audience import AudienceSelector
from apps.marketing.models import (
    MarketingAsset,
    MarketingAudience,
    MarketingCategory,
    MarketingFile,
)
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.tests.test_profile import completed_user

# Minimal valid 1×1 PNG.
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

_TINY_PDF = b"%PDF-1.7\n" + b"x" * 40


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def category(code: str = "logos") -> MarketingCategory:
    return MarketingCategory.objects.get(code=code)


def assign(user, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def agent(slug="fairfax-va", email="agent@example.com") -> User:
    return completed_user(email=email, office=office(slug))


def _apply_audience(
    asset: MarketingAsset,
    audience: tuple[AudienceSelector, ...],
) -> None:
    MarketingAudience.objects.filter(asset=asset).delete()
    MarketingAudience.objects.bulk_create(
        [
            MarketingAudience(
                asset=asset,
                kind=selector.kind,
                role=selector.role
                if selector.kind == MarketingAudience.Kind.ROLE
                else "",
                office=selector.office
                if selector.kind
                in {MarketingAudience.Kind.REGION, MarketingAudience.Kind.OFFICE}
                else None,
                user=selector.user
                if selector.kind == MarketingAudience.Kind.USER
                else None,
            )
            for selector in audience
        ]
    )


def publish_asset(
    *,
    slug: str,
    title: str,
    owner_office: Office,
    asset_type: str = "logo",
    description: str = "Description",
    audience: tuple[AudienceSelector, ...] | None = None,
    category_code: str = "logos",
    version_family=None,
    version_number: int = 1,
    with_export: bool = True,
) -> MarketingAsset:
    asset = MarketingAsset.objects.create(
        owner_office=owner_office,
        slug=slug,
        title=title,
        description=description,
        asset_type=asset_type,
        category=category(category_code),
        status=MarketingAsset.Status.PUBLISHED,
        published_at=timezone.now(),
        version_family=version_family or uuid.uuid4(),
        version_number=version_number,
    )
    selectors = audience or (AudienceSelector(kind=MarketingAudience.Kind.COMPANY),)
    _apply_audience(asset, selectors)
    if with_export:
        attach_ready_export(asset)
    return asset


def attach_ready_export(
    asset: MarketingAsset,
    *,
    actor: User | None = None,
    name: str = "export.png",
    as_pdf: bool = False,
) -> MarketingFile:
    """Create a READY EXPORT file with tiny PNG or PDF bytes in private storage."""
    data = _TINY_PDF if as_pdf else _TINY_PNG
    display = "export.pdf" if as_pdf else name
    media_type = "application/pdf" if as_pdf else "image/png"
    checksum = hashlib.sha256(data).hexdigest()
    row = MarketingFile(
        asset=asset,
        role=MarketingFile.Role.EXPORT,
        display_name=display,
        media_type=media_type,
        byte_size=len(data),
        checksum=checksum,
        processing_state=MarketingFile.ProcessingState.READY,
        uploaded_by=actor,
    )
    row.file.save(display, ContentFile(data), save=False)
    row.save()
    return row


def attach_ready_source(
    asset: MarketingAsset,
    *,
    actor: User | None = None,
    name: str = "source.pdf",
) -> MarketingFile:
    data = _TINY_PDF
    checksum = hashlib.sha256(data).hexdigest()
    row = MarketingFile(
        asset=asset,
        role=MarketingFile.Role.SOURCE,
        display_name=name,
        media_type="application/pdf",
        byte_size=len(data),
        checksum=checksum,
        processing_state=MarketingFile.ProcessingState.READY,
        uploaded_by=actor,
    )
    row.file.save(name, ContentFile(data), save=False)
    row.save()
    return row


def mark_exports_ready(asset: MarketingAsset) -> None:
    """Flip pending EXPORT clones (e.g. after duplicate_version) to READY."""
    MarketingFile.objects.filter(
        asset=asset,
        role=MarketingFile.Role.EXPORT,
        is_active=True,
    ).update(processing_state=MarketingFile.ProcessingState.READY)
