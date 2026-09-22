"""Transaction document upload, versioning, lock, delivery, and reviews."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.transactions.concurrency import transaction_version
from apps.transactions.deal_documents import (
    assert_version_mutable,
    classify_document,
    lock_version,
    refresh_current_version,
    retire_document,
    serialize_documents_for_reader,
    upload_document,
    upload_revision,
)
from apps.transactions.models import (
    TransactionDocument,
    TransactionDocumentVersion,
)
from apps.transactions.permissions import (
    CREATE_OWN_TRANSACTIONS,
    MANAGE_TRANSACTIONS,
    TRANSITION_TRANSACTIONS,
    VIEW_TRANSACTIONS,
)
from apps.transactions.tasks import process_transaction_document_version
from apps.transactions.taxonomy import (
    DocumentCategory,
    DocumentComplianceStatus,
    DocumentRequirement,
    DocumentSignatureStatus,
    NoteVisibility,
    WorkspaceSection,
)
from apps.transactions.tests.conftest import make_draft, office
from apps.transactions.workspace import workspace_payload
from apps.user.models import User, UserRoleAssignment
from apps.user.roles import REALTOR, TRANSACTION_COORDINATOR, ScopeType
from apps.user.tests.test_profile import completed_user

pytestmark = pytest.mark.django_db

_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _pdf(name: str = "offer.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, _PDF, content_type="application/pdf")


def _grant(user: User, *codenames: str) -> User:
    for codename in codenames:
        app_label, _, name = codename.partition(".")
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=name)
        )
    return User.objects.get(pk=user.pk)


def _assign(user: User, role: str, scope_type: str, scope_office=None) -> None:
    row = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    row.refresh_status()
    row.full_clean()
    row.save()


def _manager(seeded) -> User:
    user = completed_user(email="docs.mgr@example.com", office=office("fairfax-va"))
    _assign(user, TRANSACTION_COORDINATOR, ScopeType.OFFICE, office("fairfax-va"))
    return _grant(
        user,
        MANAGE_TRANSACTIONS,
        VIEW_TRANSACTIONS,
        TRANSITION_TRANSACTIONS,
    )


def _viewer(seeded) -> User:
    """Office-scoped viewer without manage/create_own — cannot triage quarantine."""
    user = completed_user(email="docs.viewer@example.com", office=office("fairfax-va"))
    return _grant(user, VIEW_TRANSACTIONS)


def _outsider(seeded) -> User:
    user = completed_user(email="docs.out@example.com", office=office("philadelphia"))
    _assign(user, REALTOR, ScopeType.OFFICE, office("philadelphia"))
    return _grant(user, CREATE_OWN_TRANSACTIONS, VIEW_TRANSACTIONS)


def _fresh_draft(seeded, mgr: User, agent: User | None = None):
    tx = make_draft(seeded=seeded, manager=mgr, agent=agent)
    tx.refresh_from_db()
    return tx


def _upload_ready(mgr: User, tx, *, name: str = "offer.pdf", **payload):
    package = upload_document(
        actor=mgr,
        public_id=tx.public_id,
        expected_version=transaction_version(tx),
        uploaded=_pdf(name),
        payload=payload or {"title": "Document"},
    )
    version = TransactionDocumentVersion.objects.filter(document=package).get()
    process_transaction_document_version.run(version.pk)
    version.refresh_from_db()
    package.refresh_from_db()
    return package, version


@pytest.fixture(autouse=True)
def _eager_celery(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True


def test_documents_section_is_live(seeded):
    mgr = _manager(seeded)
    tx = _fresh_draft(seeded, mgr)
    payload = workspace_payload(mgr, tx, section=WorkspaceSection.DOCUMENTS)
    section = next(s for s in payload["sections"] if s["id"] == "documents")
    assert section["live"] is True
    assert section["stub"] is False
    assert payload["documentSchema"] is not None
    assert payload["documents"] == []


def test_upload_inspect_and_process_to_ready(seeded):
    mgr = _manager(seeded)
    tx = _fresh_draft(seeded, mgr)
    package, version = _upload_ready(
        mgr,
        tx,
        title="Purchase agreement",
        category=DocumentCategory.PURCHASE_AGREEMENT,
        requirement=DocumentRequirement.REQUIRED,
    )
    assert version.processing_state == TransactionDocumentVersion.ProcessingState.READY
    assert package.current_version_pk == version.pk
    rows = serialize_documents_for_reader(mgr, tx)
    assert len(rows) == 1
    assert rows[0]["currentVersion"]["isReadable"] is True


def test_reject_disallowed_extension(seeded):
    from django.core.exceptions import ValidationError

    mgr = _manager(seeded)
    tx = _fresh_draft(seeded, mgr)
    with pytest.raises(ValidationError):
        upload_document(
            actor=mgr,
            public_id=tx.public_id,
            expected_version=transaction_version(tx),
            uploaded=SimpleUploadedFile(
                "malware.exe", b"MZ\x90\x00", content_type="application/octet-stream"
            ),
            payload={"title": "Bad"},
        )


def test_quarantined_not_visible_to_ordinary_reader(seeded):
    mgr = _manager(seeded)
    viewer = _viewer(seeded)
    tx = _fresh_draft(seeded, mgr)

    package, version = _upload_ready(mgr, tx, title="Disclosure", name="ok.pdf")
    version.processing_state = TransactionDocumentVersion.ProcessingState.QUARANTINED
    version.processing_note = "checksum mismatch"
    version.save(update_fields=["processing_state", "processing_note", "updated_at"])
    package.current_version = None
    package.save(update_fields=["current_version", "updated_at"])

    viewer_rows = serialize_documents_for_reader(viewer, tx)
    assert viewer_rows[0]["versions"] == []
    assert viewer_rows[0]["currentVersion"] is None

    mgr_rows = serialize_documents_for_reader(mgr, tx)
    assert len(mgr_rows[0]["versions"]) == 1
    assert mgr_rows[0]["versions"][0]["processingState"] == "quarantined"
    assert mgr_rows[0]["versions"][0]["isReadable"] is False


def test_current_version_is_highest_ready(seeded):
    mgr = _manager(seeded)
    tx = _fresh_draft(seeded, mgr)
    package, _v1 = _upload_ready(mgr, tx, title="Addendum", name="v1.pdf")
    tx.refresh_from_db()
    v2 = upload_revision(
        actor=mgr,
        public_id=tx.public_id,
        document_public_id=package.public_id,
        expected_version=transaction_version(tx),
        uploaded=_pdf("v2.pdf"),
    )
    process_transaction_document_version.run(v2.pk)
    package.refresh_from_db()
    assert package.current_version_pk == v2.pk
    assert v2.version_number == 2

    tx.refresh_from_db()
    v3 = upload_revision(
        actor=mgr,
        public_id=tx.public_id,
        document_public_id=package.public_id,
        expected_version=transaction_version(tx),
        uploaded=_pdf("v3.pdf"),
    )
    process_transaction_document_version.run(v3.pk)
    v3.processing_state = TransactionDocumentVersion.ProcessingState.FAILED
    v3.save(update_fields=["processing_state", "updated_at"])
    refresh_current_version(package)
    package.refresh_from_db()
    assert package.current_version_pk == v2.pk


def test_signed_version_cannot_be_retired(seeded):
    from django.core.exceptions import ValidationError

    mgr = _manager(seeded)
    tx = _fresh_draft(seeded, mgr)
    package, version = _upload_ready(mgr, tx, title="Closing")
    tx.refresh_from_db()
    lock_version(
        actor=mgr,
        public_id=tx.public_id,
        version_public_id=version.public_id,
        expected_version=transaction_version(tx),
        payload={"signatureStatus": DocumentSignatureStatus.SIGNED},
    )
    version.refresh_from_db()
    assert version.is_locked
    with pytest.raises(ValidationError):
        assert_version_mutable(version)

    tx.refresh_from_db()
    with pytest.raises(ValidationError):
        retire_document(
            actor=mgr,
            public_id=tx.public_id,
            document_public_id=package.public_id,
            expected_version=transaction_version(tx),
        )


def test_approved_lock_blocks_mutate(seeded):
    from django.core.exceptions import ValidationError

    mgr = _manager(seeded)
    tx = _fresh_draft(seeded, mgr)
    _package, version = _upload_ready(mgr, tx, title="Inspection")
    tx.refresh_from_db()
    lock_version(
        actor=mgr,
        public_id=tx.public_id,
        version_public_id=version.public_id,
        expected_version=transaction_version(tx),
        payload={"complianceStatus": DocumentComplianceStatus.APPROVED},
    )
    version.refresh_from_db()
    assert version.compliance_status == DocumentComplianceStatus.APPROVED
    assert version.locked_at is not None
    with pytest.raises(ValidationError):
        assert_version_mutable(version)


def test_review_visibility_filters(seeded):
    from apps.transactions.document_reviews import (
        save_review_comment,
        serialize_comments_for_reader,
    )

    mgr = _manager(seeded)
    viewer = _viewer(seeded)
    tx = _fresh_draft(seeded, mgr)
    _package, version = _upload_ready(mgr, tx, title="Notes doc")
    tx.refresh_from_db()
    save_review_comment(
        actor=mgr,
        public_id=tx.public_id,
        version_public_id=version.public_id,
        expected_version=transaction_version(tx),
        payload={"body": "Team note", "visibility": NoteVisibility.TEAM},
    )
    tx.refresh_from_db()
    save_review_comment(
        actor=mgr,
        public_id=tx.public_id,
        version_public_id=version.public_id,
        expected_version=transaction_version(tx),
        payload={
            "body": "Broker only",
            "visibility": NoteVisibility.BROKER_COMPLIANCE,
        },
    )

    viewer_comments = serialize_comments_for_reader(viewer, version)
    bodies = {c["body"] for c in viewer_comments}
    assert "Team note" in bodies
    assert "Broker only" not in bodies

    mgr_comments = serialize_comments_for_reader(mgr, version)
    assert {c["body"] for c in mgr_comments} == {"Team note", "Broker only"}


def test_download_requires_scope_and_ready(client, seeded):
    mgr = _manager(seeded)
    outsider = _outsider(seeded)
    tx = _fresh_draft(seeded, mgr)
    _package, version = _upload_ready(mgr, tx, title="Download me")
    url = reverse(
        "transaction_document_download", kwargs={"public_id": version.public_id}
    )

    client.force_login(outsider)
    assert client.get(url).status_code == 404

    client.force_login(mgr)
    response = client.get(url)
    assert response.status_code == 200
    assert response["Cache-Control"].startswith("private, no-store")

    version.processing_state = TransactionDocumentVersion.ProcessingState.PENDING
    version.save(update_fields=["processing_state"])
    assert client.get(url).status_code == 404


def test_guessed_version_id_404(client, seeded):
    mgr = _manager(seeded)
    client.force_login(mgr)
    url = reverse("transaction_document_download", kwargs={"public_id": uuid4()})
    assert client.get(url).status_code == 404


def test_multipart_upload_endpoint(client, seeded):
    mgr = _manager(seeded)
    tx = _fresh_draft(seeded, mgr)
    client.force_login(mgr)
    url = reverse("transaction_document_upload", kwargs={"public_id": tx.public_id})
    response = client.post(
        url,
        data={
            "expectedVersion": transaction_version(tx),
            "title": "Via multipart",
            "category": DocumentCategory.OTHER,
            "requirement": DocumentRequirement.OPTIONAL,
            "file": _pdf("multipart.pdf"),
        },
        HTTP_ACCEPT="application/json",
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["document"]["title"] == "Via multipart"
    assert TransactionDocument.objects.filter(transaction=tx).count() == 1
    version = TransactionDocumentVersion.objects.get()
    process_transaction_document_version.run(version.pk)
    version.refresh_from_db()
    assert version.processing_state == TransactionDocumentVersion.ProcessingState.READY


def test_json_classify_endpoint(client, seeded):
    import json

    mgr = _manager(seeded)
    tx = _fresh_draft(seeded, mgr)
    package, _version = _upload_ready(mgr, tx, title="Before")
    tx.refresh_from_db()
    client.force_login(mgr)
    url = reverse(
        "transaction_document_classify",
        kwargs={"public_id": tx.public_id, "document_id": package.public_id},
    )
    response = client.post(
        url,
        data=json.dumps(
            {
                "expectedVersion": transaction_version(tx),
                "title": "After",
                "category": DocumentCategory.DISCLOSURE,
                "requirement": DocumentRequirement.REQUIRED,
                "retentionPolicy": "indefinite",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 302
    package.refresh_from_db()
    assert package.title == "After"
    assert package.category == DocumentCategory.DISCLOSURE


def test_orphan_sweep_removes_stale_pending(seeded):
    from apps.transactions.tasks import sweep_orphan_documents

    mgr = _manager(seeded)
    tx = _fresh_draft(seeded, mgr)
    _package, version = _upload_ready(mgr, tx, title="Stale", name="stale.pdf")
    TransactionDocumentVersion.objects.filter(pk=version.pk).update(
        processing_state=TransactionDocumentVersion.ProcessingState.PENDING,
        created_at=timezone.now() - timedelta(days=30),
    )

    report = sweep_orphan_documents(now=timezone.now())
    assert version.pk in report.deleted_rows
    assert not TransactionDocumentVersion.objects.filter(pk=version.pk).exists()


def test_classify_helper(seeded):
    mgr = _manager(seeded)
    tx = _fresh_draft(seeded, mgr)
    package, _version = _upload_ready(mgr, tx, title="Raw")
    tx.refresh_from_db()
    classify_document(
        actor=mgr,
        public_id=tx.public_id,
        document_public_id=package.public_id,
        expected_version=transaction_version(tx),
        payload={
            "title": "Classified",
            "category": DocumentCategory.INSPECTION,
            "requirement": DocumentRequirement.REQUIRED,
        },
    )
    package.refresh_from_db()
    assert package.title == "Classified"
    assert package.category == DocumentCategory.INSPECTION
