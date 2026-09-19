"""Training certificate issuance and learner download."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.training.certificate_service import (
    CertificateError,
    issue_certificate,
    stream_certificate,
)
from apps.training.models import TrainingCertificate, TrainingProgress
from apps.training.progress_service import mark_completed
from apps.training.tests.factories import agent, assign, office, publish_content
from apps.user.models import User
from apps.user.tests.test_profile import completed_user


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def grant(user: User, *codenames: str) -> User:
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="web", codename=codename)
        )
    return User.objects.get(pk=user.pk)


def publisher(*, slug="fairfax-va", email="publisher@example.com") -> User:
    user = completed_user(email=email, office=office(slug))
    assign(user, "system_admin", "company")
    return grant(user, "manage_training")


def regional_publisher(*, email="regional@example.com") -> User:
    user = completed_user(email=email, office=office("region-mid-atlantic"))
    assign(user, "regional_admin", "region", office("region-mid-atlantic"))
    return grant(user, "manage_training")


def _json_post(client: Client, url: str, data: dict, user: User):
    client.force_login(user)
    return client.post(
        url,
        data=json.dumps(data),
        content_type="application/json",
    )


@pytest.mark.django_db
def test_issue_certificate_happy_path(seeded, django_capture_on_commit_callbacks):
    actor = publisher()
    learner = agent(email="cert-learner@example.com")
    content = publish_content(
        slug="ethics-cert",
        title="Ethics certificate course",
        owner_office=office("fairfax-va"),
    )
    mark_completed(learner, content)

    with django_capture_on_commit_callbacks(execute=True):
        cert = issue_certificate(actor=actor, content=content, learner=learner)

    assert cert.status == TrainingCertificate.Status.APPROVED
    assert cert.file
    assert cert.approved_by == actor
    assert cert.approved_at is not None
    assert (
        AuditEvent.objects.filter(action="training.certificate_approved").count() == 1
    )

    response = stream_certificate(learner, content)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    # Landscape branded certificate — far larger than the old ~800B stub.
    assert cert.file.size > 8_000
    with cert.file.open("rb") as handle:
        pdf_bytes = handle.read()
    assert pdf_bytes.startswith(b"%PDF")
    from io import BytesIO

    from pypdf import PdfReader

    text = "".join(
        (page.extract_text() or "") for page in PdfReader(BytesIO(pdf_bytes)).pages
    )
    assert "CERTIFICATE" in text
    assert "Ethics" in text


@pytest.mark.django_db
def test_issue_refuses_incomplete_learner(seeded):
    actor = publisher()
    learner = agent(email="incomplete@example.com")
    content = publish_content(
        slug="incomplete-cert",
        title="Incomplete",
        owner_office=office("fairfax-va"),
    )
    with pytest.raises(CertificateError):
        issue_certificate(actor=actor, content=content, learner=learner)


@pytest.mark.django_db
def test_issue_refuses_out_of_scope_content(seeded):
    actor = regional_publisher()
    learner = agent(email="ct-agent@example.com", slug="connecticut")
    content = publish_content(
        slug="ct-only",
        title="Connecticut only",
        owner_office=office("connecticut"),
    )
    mark_completed(learner, content)
    with pytest.raises(PermissionDenied):
        issue_certificate(actor=actor, content=content, learner=learner)


@pytest.mark.django_db
def test_issue_refuses_out_of_scope_learner(seeded):
    actor = regional_publisher()
    learner = agent(email="ct-learner@example.com", slug="connecticut")
    content = publish_content(
        slug="mid-atlantic-item",
        title="Mid-Atlantic item",
        owner_office=office("fairfax-va"),
    )
    mark_completed(learner, content)
    with pytest.raises(PermissionDenied):
        issue_certificate(actor=actor, content=content, learner=learner)


@pytest.mark.django_db
def test_issue_is_idempotent(seeded, django_capture_on_commit_callbacks):
    actor = publisher()
    learner = agent(email="idempotent@example.com")
    content = publish_content(
        slug="idempotent-cert",
        title="Idempotent",
        owner_office=office("fairfax-va"),
    )
    mark_completed(learner, content)

    with django_capture_on_commit_callbacks(execute=True):
        first = issue_certificate(actor=actor, content=content, learner=learner)
    first_name = first.file.name
    first_approved_at = first.approved_at

    with django_capture_on_commit_callbacks(execute=True):
        second = issue_certificate(actor=actor, content=content, learner=learner)

    assert second.pk == first.pk
    assert second.file.name == first_name
    assert second.approved_at == first_approved_at
    assert (
        AuditEvent.objects.filter(action="training.certificate_approved").count() == 1
    )


@pytest.mark.django_db
def test_issue_json_post_and_workspace_payload(seeded):
    actor = publisher()
    learner = agent(email="workspace-cert@example.com")
    content = publish_content(
        slug="workspace-cert",
        title="Workspace cert",
        owner_office=office("fairfax-va"),
    )
    mark_completed(learner, content)

    client = Client()
    client.force_login(actor)
    edit = client.get(
        reverse("training_edit", args=[content.pk]), HTTP_X_INERTIA="true"
    )
    assert edit.status_code == 200
    props = json.loads(edit.content)["props"]["content"]
    assert props["certificates"]["eligibleCount"] == 1
    assert props["certificates"]["issuedCount"] == 0
    assert props["certificates"]["learners"][0]["id"] == learner.pk
    assert props["certificates"]["learners"][0]["certificate"] is None

    response = _json_post(
        client,
        reverse("training_certificate_issue", args=[content.pk]),
        {"learnerId": learner.pk},
        actor,
    )
    assert response.status_code in {302, 303}

    cert = TrainingCertificate.objects.get(user=learner, content=content)
    assert cert.status == TrainingCertificate.Status.APPROVED
    assert cert.file

    edit_after = client.get(
        reverse("training_edit", args=[content.pk]), HTTP_X_INERTIA="true"
    )
    props_after = json.loads(edit_after.content)["props"]["content"]
    assert props_after["certificates"]["issuedCount"] == 1
    row_cert = props_after["certificates"]["learners"][0]["certificate"]
    assert row_cert["status"] == TrainingCertificate.Status.APPROVED
    assert row_cert["available"] is True

    client.force_login(learner)
    download = client.get(reverse("training_certificate", args=[content.pk]))
    assert download.status_code == 200
    assert download["Content-Type"] == "application/pdf"


@pytest.mark.django_db
def test_learner_download_404_when_not_issued(seeded):
    learner = agent(email="no-cert@example.com")
    content = publish_content(
        slug="no-cert-yet",
        title="No cert",
        owner_office=office("fairfax-va"),
    )
    mark_completed(learner, content)
    client = Client()
    client.force_login(learner)
    response = client.get(reverse("training_certificate", args=[content.pk]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_progress_completed_at_present_for_issue_list(seeded):
    """Workspace list prefers completed_at ordering."""
    actor = publisher()
    older = agent(email="older@example.com")
    newer = agent(email="newer@example.com")
    content = publish_content(
        slug="ordered-certs",
        title="Ordered",
        owner_office=office("fairfax-va"),
    )
    older_row = mark_completed(older, content)
    newer_row = mark_completed(newer, content)
    TrainingProgress.objects.filter(pk=older_row.pk).update(
        completed_at=timezone.now() - timedelta(days=2)
    )
    TrainingProgress.objects.filter(pk=newer_row.pk).update(
        completed_at=timezone.now() - timedelta(hours=1)
    )

    client = Client()
    client.force_login(actor)
    edit = client.get(
        reverse("training_edit", args=[content.pk]), HTTP_X_INERTIA="true"
    )
    learners = json.loads(edit.content)["props"]["content"]["certificates"]["learners"]
    assert [row["id"] for row in learners] == [newer.pk, older.pk]


@pytest.mark.django_db
def test_certificate_pdf_is_landscape_branded_page():
    from datetime import date
    from io import BytesIO
    from uuid import uuid4

    from pypdf import PdfReader

    from apps.training.certificate_pdf import build_training_certificate_pdf

    public_id = str(uuid4())
    pdf = build_training_certificate_pdf(
        title="Leadership Skill Course",
        learner_name="Donna Stroupe",
        completed_at=date(2026, 11, 10),
        public_id=public_id,
        verify_url=f"http://localhost:8000/verify/training-certificates/{public_id}",
        signature="a" * 64,
        signature_algorithm="hmac-sha256-v1",
    )
    assert len(pdf) > 8_000
    assert pdf.startswith(b"%PDF")
    page = PdfReader(BytesIO(pdf)).pages[0]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    assert width > height  # landscape
    text = page.extract_text() or ""
    assert "CERTIFICATE" in text
    assert "Donna Stroupe" in text
    assert "Leadership Skill Course" in text
    assert "Cryptographic signature" in text
    assert public_id in text


@pytest.mark.django_db
def test_public_verify_json_and_signature(seeded, django_capture_on_commit_callbacks):
    actor = publisher()
    learner = agent(email="verify-me@example.com")
    content = publish_content(
        slug="verify-course",
        title="Verify Course",
        owner_office=office("fairfax-va"),
    )
    mark_completed(learner, content)
    with django_capture_on_commit_callbacks(execute=True):
        cert = issue_certificate(actor=actor, content=content, learner=learner)

    client = Client()
    url = reverse("training_certificate_verify", args=[cert.public_id])
    response = client.get(url, HTTP_ACCEPT="application/json")
    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["signatureValid"] is True
    assert payload["publicId"] == str(cert.public_id)
    assert payload["trainingTitle"] == "Verify Course"
    assert payload["learnerName"]

    missing = client.get(
        reverse(
            "training_certificate_verify", args=["00000000-0000-0000-0000-000000000099"]
        ),
        HTTP_ACCEPT="application/json",
    )
    assert missing.status_code == 404
    assert missing.json()["valid"] is False
