"""Protected marketing file downloads and processing."""

from __future__ import annotations

import io

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.marketing.administration import (
    asset_version,
    create_asset,
    transition,
)
from apps.marketing.audience import AudienceSelector
from apps.marketing.media_service import (
    assert_readable_export,
    assert_readable_source,
    attach_file,
    media_publish_debt,
)
from apps.marketing.models import MarketingAudience, MarketingFile
from apps.marketing.services import validation_debt
from apps.marketing.tasks import process_marketing_file
from apps.marketing.tests.factories import (
    agent,
    attach_ready_export,
    attach_ready_source,
    category,
    office,
    publish_asset,
)
from apps.user.models import User
from apps.user.tests.test_profile import completed_user

Kind = MarketingAudience.Kind
State = MarketingFile.ProcessingState


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


@pytest.fixture(autouse=True)
def isolated_media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def grant(user: User, *codenames: str) -> User:
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="web", codename=codename)
        )
    return User.objects.get(pk=user.pk)


def _assign(user, role: str, scope_type: str, scope_office=None) -> None:
    from apps.marketing.tests.factories import assign

    assign(user, role, scope_type, scope_office)


def publisher(*, email="mkt-media-pub@example.com") -> User:
    user = completed_user(email=email, office=office("fairfax-va"))
    _assign(user, "system_admin", "company")
    return grant(
        user,
        "manage_marketing_resources",
        "publish_marketing_resources",
        "download_marketing_sources",
    )


def test_export_download_allowed_for_audience(seeded, client):
    reader = agent()
    asset = publish_asset(
        slug="public-export",
        title="Public export",
        owner_office=office("onest-head-office"),
        with_export=False,
    )
    row = attach_ready_export(asset, as_pdf=True)

    client.force_login(reader)
    response = client.get(reverse("marketing_resource_export", args=[row.pk]))
    assert response.status_code == 200
    assert b"".join(response.streaming_content).startswith(b"%PDF")
    assert "private" in response["Cache-Control"]


def test_export_download_denied_for_outsider(seeded, client):
    reader = agent()
    asset = publish_asset(
        slug="private-export",
        title="Private export",
        owner_office=office("onest-head-office"),
        audience=(AudienceSelector(kind=Kind.ROLE, role="system_admin"),),
        with_export=False,
    )
    row = attach_ready_export(asset, as_pdf=True)

    client.force_login(reader)
    assert (
        client.get(reverse("marketing_resource_export", args=[row.pk])).status_code
        == 403
    )


def test_source_download_denied_without_permission(seeded, client):
    reader = agent()
    asset = publish_asset(
        slug="has-source",
        title="Has source",
        owner_office=office("onest-head-office"),
        with_export=False,
    )
    attach_ready_export(asset)
    source = attach_ready_source(asset)

    client.force_login(reader)
    assert (
        client.get(reverse("marketing_resource_source", args=[source.pk])).status_code
        == 403
    )
    with pytest.raises(PermissionDenied):
        assert_readable_source(reader, source)


def test_source_download_allowed_with_permission_and_manage_scope(seeded, client):
    actor = publisher()
    asset = publish_asset(
        slug="admin-source",
        title="Admin source",
        owner_office=office("fairfax-va"),
        audience=(AudienceSelector(kind="office", office=office("fairfax-va")),),
        with_export=False,
    )
    attach_ready_export(asset)
    source = attach_ready_source(asset, actor=actor)

    client.force_login(actor)
    response = client.get(reverse("marketing_resource_source", args=[source.pk]))
    assert response.status_code == 200
    assert b"".join(response.streaming_content).startswith(b"%PDF")


def test_publish_refuses_when_export_pending(seeded):
    actor = publisher()
    draft = create_asset(
        actor=actor,
        office=office("fairfax-va"),
        cleaned={
            "title": "Pending export",
            "description": "",
            "usage_instructions": "",
            "category": category(),
            "asset_type": "logo",
            "publish_at": None,
            "expires_at": None,
            "jurisdiction_state_codes": [],
            "brand_codes": [],
            "display_order": 100,
        },
        selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
    )
    upload = SimpleUploadedFile("notes.pdf", b"%PDF-1.7\n" + b"x" * 40)
    media = attach_file(actor, draft, upload, role=MarketingFile.Role.EXPORT)
    assert media.processing_state == State.PENDING
    assert media_publish_debt(draft)
    assert any(field == "files" for field, _ in validation_debt(draft))
    with pytest.raises(ValidationError):
        transition(
            actor=actor,
            asset=draft,
            action="publish",
            expected_version=asset_version(draft),
        )


def test_process_marketing_file_checksum_mismatch_quarantines(seeded):
    actor = publisher()
    draft = create_asset(
        actor=actor,
        office=office("fairfax-va"),
        cleaned={
            "title": "Checksum check",
            "description": "",
            "usage_instructions": "",
            "category": category(),
            "asset_type": "logo",
            "publish_at": None,
            "expires_at": None,
            "jurisdiction_state_codes": [],
            "brand_codes": [],
            "display_order": 100,
        },
        selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
    )
    upload = SimpleUploadedFile("notes.pdf", b"%PDF-1.7\n" + b"x" * 40)
    media = attach_file(actor, draft, upload, role=MarketingFile.Role.EXPORT)
    storage = media.file.storage
    storage.delete(media.file.name)
    storage.save(media.file.name, io.BytesIO(b"%PDF-1.7\nsomething else entirely"))

    assert process_marketing_file.run(media.pk) == State.QUARANTINED
    media.refresh_from_db()
    assert media.is_readable is False
    assert "checksum" in media.processing_note.lower()


def test_assert_readable_export_for_audience(seeded):
    reader = agent()
    asset = publish_asset(
        slug="readable",
        title="Readable",
        owner_office=office("onest-head-office"),
        with_export=False,
    )
    row = attach_ready_export(asset, as_pdf=True)
    assert_readable_export(reader, row)
