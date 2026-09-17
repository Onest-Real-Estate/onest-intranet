"""Protected document downloads and upload inspection."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.documents.audience import AudienceSelector
from apps.documents.media import inspect_document_upload
from apps.documents.media_service import upload_document
from apps.documents.models import DocumentFile, DocumentVersion
from apps.documents.tests.factories import (
    agent,
    attach_ready_file,
    office,
    publish_document,
)
from apps.user.models import User
from apps.user.tests.test_profile import completed_user


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


def manager(*, email="docs-manager@example.com") -> User:
    from apps.documents.tests.factories import assign

    user = completed_user(email=email, office=office("fairfax-va"))
    assign(user, "system_admin", "company")
    return grant(user, "manage_documents")


def _pdf_upload(name="form.pdf", data=None):
    payload = data if data is not None else b"%PDF-1.7\n" + b"x" * 40
    return SimpleUploadedFile(name, payload, content_type="application/pdf")


def test_inspect_rejects_disguised_and_empty_uploads(seeded):
    with pytest.raises(ValidationError):
        inspect_document_upload(
            SimpleUploadedFile("form.pdf", b"", content_type="application/pdf")
        )
    with pytest.raises(ValidationError):
        inspect_document_upload(
            SimpleUploadedFile("form.pdf", b"not-a-pdf", content_type="application/pdf")
        )
    with pytest.raises(ValidationError):
        inspect_document_upload(
            SimpleUploadedFile(
                "malware.exe", b"MZ", content_type="application/octet-stream"
            )
        )


def test_inspect_rejects_oversized_upload(seeded, settings):
    huge = b"%PDF-1.7\n" + (b"x" * (21 * 1024 * 1024))
    with pytest.raises(ValidationError):
        inspect_document_upload(_pdf_upload(data=huge))


def test_upload_document_stores_ready_file(seeded):
    actor = manager()
    version = publish_document(
        key="upload-me",
        name="Upload me",
        owner_office=office("onest-head-office"),
        status=DocumentVersion.Status.DRAFT,
        with_file=False,
    )
    row = upload_document(actor, version, _pdf_upload())
    assert row.processing_state == DocumentFile.ProcessingState.READY
    assert row.checksum
    assert row.file


def test_current_file_downloads_and_historical_file_404s(seeded, client):
    v1 = publish_document(
        key="download-family",
        name="Old file",
        owner_office=office("onest-head-office"),
        version_number=1,
    )
    old_file = DocumentFile.objects.get(document_version=v1)
    v2 = publish_document(
        key="download-family",
        name="New file",
        owner_office=office("onest-head-office"),
        version_number=2,
    )
    v1.status = DocumentVersion.Status.SUPERSEDED
    v1.save(update_fields=["status"])
    current_file = DocumentFile.objects.get(document_version=v2)

    reader = agent()
    client.force_login(reader)
    ok = client.get(reverse("document_file", args=[current_file.pk]))
    assert ok.status_code == 200
    assert ok["Cache-Control"].startswith("private, no-store")
    assert ok.get("Content-Disposition")

    denied = client.get(reverse("document_file", args=[old_file.pk]))
    assert denied.status_code == 404


def test_guessed_file_id_is_404(seeded, client):
    reader = agent()
    client.force_login(reader)
    response = client.get(reverse("document_file", args=[999_999]))
    assert response.status_code == 404


def test_pending_file_is_not_downloadable(seeded, client):
    version = publish_document(
        key="pending-file",
        name="Pending",
        owner_office=office("onest-head-office"),
        with_file=False,
    )
    row = attach_ready_file(version)
    row.processing_state = DocumentFile.ProcessingState.PENDING
    row.save(update_fields=["processing_state"])

    reader = agent()
    client.force_login(reader)
    response = client.get(reverse("document_file", args=[row.pk]))
    assert response.status_code == 404


def test_out_of_scope_download_is_404(seeded, client):
    version = publish_document(
        key="scoped-file",
        name="Scoped",
        owner_office=office("fairfax-va"),
        audience=(AudienceSelector(kind="office", office=office("fairfax-va")),),
    )
    row = DocumentFile.objects.get(document_version=version)
    stranger = completed_user(
        email="file-stranger@example.com", office=office("harrisburg")
    )
    client.force_login(stranger)
    response = client.get(reverse("document_file", args=[row.pk]))
    assert response.status_code == 404
