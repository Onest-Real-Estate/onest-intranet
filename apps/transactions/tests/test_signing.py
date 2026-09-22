"""Signature package authoring, ordered routing, ceremony, and finalization."""

from __future__ import annotations

import base64
import io
from uuid import UUID

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from apps.transactions.concurrency import transaction_version
from apps.transactions.deal_documents import upload_document
from apps.transactions.models import (
    SignatureAccessToken,
    SignatureArtifact,
    SignaturePackageSigner,
    SignatureRecord,
    TransactionDocumentVersion,
)
from apps.transactions.permissions import (
    MANAGE_TRANSACTIONS,
    TRANSITION_TRANSACTIONS,
    VIEW_TRANSACTIONS,
)
from apps.transactions.signing.authoring import (
    cancel_package,
    create_draft_package,
    replace_package_contents,
    validate_and_send,
)
from apps.transactions.signing.ceremony import (
    RequestMeta,
    ceremony_payload,
    complete_signing,
    decline_signing,
    resolve_signer_from_token,
    start_intent,
)
from apps.transactions.signing.disclosure import DISCLOSURE_VERSION
from apps.transactions.signing.finalize import finalize_package
from apps.transactions.signing.lifecycle import eligible_signers_queryset
from apps.transactions.signing.provider import get_signing_provider
from apps.transactions.signing.serialize import serialize_packages_for_reader
from apps.transactions.signing.tokens import hash_token, issue_access_token
from apps.transactions.taxonomy import (
    DocumentSignatureStatus,
    SignatureArtifactKind,
    SignatureDeliveryMethod,
    SignaturePackageStatus,
    SignatureRoutingMode,
    SignatureSignerStatus,
    WorkspaceSection,
)
from apps.transactions.tests.conftest import make_draft, office
from apps.transactions.workspace import workspace_payload
from apps.user.models import User, UserRoleAssignment
from apps.user.roles import REALTOR, TRANSACTION_COORDINATOR, ScopeType
from apps.user.tests.test_profile import completed_user

pytestmark = pytest.mark.django_db


def _real_pdf(pages: int = 2) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for index in range(pages):
        c.drawString(72, 700, f"Deal page {index + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def _png_data_url() -> str:
    # 1x1 transparent PNG — enough bytes to pass the appearance floor.
    raw = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42m"
        "NkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )
    return "data:image/png;base64," + base64.b64encode(raw).decode()


def _enable_signing(settings) -> None:
    settings.DEBUG = True
    settings.CONTRACT_SIGNING_CERT_PATH = ""
    settings.CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV = True


def _meta(session_key: str = "sess-1") -> RequestMeta:
    return RequestMeta(
        session_key=session_key, ip_address="127.0.0.1", user_agent="test"
    )


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


@pytest.fixture
def deal(seeded):
    manager = completed_user(
        email="sig.manager@example.com", office=office("fairfax-va")
    )
    _assign(manager, TRANSACTION_COORDINATOR, ScopeType.OFFICE, office("fairfax-va"))
    manager = _grant(
        manager, MANAGE_TRANSACTIONS, VIEW_TRANSACTIONS, TRANSITION_TRANSACTIONS
    )
    tx = make_draft(seeded=seeded, manager=manager)
    tx.refresh_from_db()
    document = upload_document(
        actor=manager,
        public_id=tx.public_id,
        expected_version=transaction_version(tx),
        uploaded=SimpleUploadedFile(
            "offer.pdf", _real_pdf(), content_type="application/pdf"
        ),
        payload={"title": "Purchase agreement"},
    )
    version = TransactionDocumentVersion.objects.filter(document=document).get()
    version.processing_state = TransactionDocumentVersion.ProcessingState.READY
    version.save(update_fields=["processing_state"])
    return manager, tx, version


def _build_package(
    manager,
    tx,
    version,
    *,
    routing_mode: str = SignatureRoutingMode.ORDERED,
):
    package = create_draft_package(
        manager,
        tx,
        title="Offer package",
        routing_mode=routing_mode,
    )
    return replace_package_contents(
        manager,
        package,
        documents=[str(version.public_id)],
        signers=[
            {
                "key": "buyer",
                "roleLabel": "Buyer",
                "displayName": "Pat Buyer",
                "email": "pat.buyer@example.com",
                "routingOrder": 1,
            },
            {
                "key": "seller",
                "roleLabel": "Seller",
                "displayName": "Sam Seller",
                "email": "sam.seller@example.com",
                "routingOrder": 2,
            },
        ],
        fields=[
            {
                "name": "BuyerSignature",
                "type": "signature",
                "signerKey": "buyer",
                "documentKey": str(version.public_id),
                "page": 1,
                "x": 72,
                "y": 600,
                "w": 160,
                "h": 40,
            },
            {
                "name": "BuyerDate",
                "type": "date",
                "signerKey": "buyer",
                "documentKey": str(version.public_id),
                "page": 1,
                "x": 260,
                "y": 600,
                "w": 120,
                "h": 24,
            },
            {
                "name": "SellerSignature",
                "type": "signature",
                "signerKey": "seller",
                "documentKey": str(version.public_id),
                "page": 2,
                "x": 72,
                "y": 600,
                "w": 160,
                "h": 40,
            },
        ],
    )


def _sign(signer, *, settings, session="sess-1", text_values=None):
    _enable_signing(settings)
    package = signer.package
    payload = start_intent(
        package=package,
        signer=signer,
        consent_accepted=True,
        disclosure_version=DISCLOSURE_VERSION,
        request_meta=_meta(session),
    )
    return complete_signing(
        intent_public_id=UUID(payload["ceremony"]["intentPublicId"]),
        signer=SignaturePackageSigner.objects.get(pk=signer.pk),
        signature_data_url=_png_data_url(),
        signed_date="2026-09-22",
        text_values=text_values,
        request_meta=_meta(session),
    )


def test_replace_contents_requires_a_required_field_per_signer(deal):
    manager, tx, version = deal
    package = create_draft_package(manager, tx, title="Missing fields")
    with pytest.raises(ValidationError) as exc:
        replace_package_contents(
            manager,
            package,
            documents=[str(version.public_id)],
            signers=[
                {
                    "key": "buyer",
                    "roleLabel": "Buyer",
                    "displayName": "Pat Buyer",
                    "email": "pat@example.com",
                },
                {
                    "key": "seller",
                    "roleLabel": "Seller",
                    "displayName": "Sam Seller",
                    "email": "sam@example.com",
                },
            ],
            fields=[
                {
                    "name": "BuyerSignature",
                    "type": "signature",
                    "signerKey": "buyer",
                    "documentKey": str(version.public_id),
                    "page": 1,
                    "x": 10,
                    "y": 10,
                    "w": 100,
                    "h": 20,
                }
            ],
        )
    assert "Seller" in str(exc.value)


def test_field_beyond_last_page_is_refused(deal):
    manager, tx, version = deal
    package = create_draft_package(manager, tx, title="Bad geometry")
    with pytest.raises(ValidationError) as exc:
        replace_package_contents(
            manager,
            package,
            documents=[str(version.public_id)],
            signers=[
                {
                    "key": "buyer",
                    "roleLabel": "Buyer",
                    "displayName": "Pat Buyer",
                    "email": "pat@example.com",
                }
            ],
            fields=[
                {
                    "name": "BuyerSignature",
                    "type": "signature",
                    "signerKey": "buyer",
                    "documentKey": str(version.public_id),
                    "page": 9,
                    "x": 10,
                    "y": 10,
                    "w": 100,
                    "h": 20,
                }
            ],
        )
    assert "page 9" in str(exc.value)


def test_hub_delivery_requires_a_hub_user(deal):
    manager, tx, version = deal
    package = create_draft_package(manager, tx, title="Hub signer")
    with pytest.raises(ValidationError) as exc:
        replace_package_contents(
            manager,
            package,
            documents=[str(version.public_id)],
            signers=[
                {
                    "key": "buyer",
                    "roleLabel": "Buyer",
                    "displayName": "Pat Buyer",
                    "email": "pat@example.com",
                    "deliveryMethod": SignatureDeliveryMethod.HUB,
                }
            ],
            fields=[],
        )
    assert "Hub delivery needs a Hub user" in str(exc.value)


def test_send_marks_documents_pending_and_invites_first_order(deal, settings):
    _enable_signing(settings)
    manager, tx, version = deal
    package = _build_package(manager, tx, version)

    sent = validate_and_send(manager, package)
    assert sent.status == SignaturePackageStatus.SENT
    assert sent.disclosure_version == DISCLOSURE_VERSION

    version.refresh_from_db()
    assert version.signature_status == DocumentSignatureStatus.PENDING

    buyer = sent.signers.get(role_label="Buyer")
    seller = sent.signers.get(role_label="Seller")
    assert buyer.status == SignatureSignerStatus.INVITED
    assert seller.status == SignatureSignerStatus.PENDING
    assert list(eligible_signers_queryset(sent)) == [buyer]


def test_magic_link_token_is_stored_hashed_only(deal, settings):
    _enable_signing(settings)
    manager, tx, version = deal
    sent = validate_and_send(manager, _build_package(manager, tx, version))
    buyer = sent.signers.get(role_label="Buyer")

    _row, raw = issue_access_token(buyer)
    stored = SignatureAccessToken.objects.filter(
        signer=buyer, consumed_at__isnull=True
    ).get()
    assert stored.token_hash == hash_token(raw)
    assert raw not in stored.token_hash

    package, signer, token = resolve_signer_from_token(raw)
    assert signer.pk == buyer.pk
    assert package.pk == sent.pk
    assert token.pk == stored.pk

    with pytest.raises(PermissionDenied):
        resolve_signer_from_token(raw + "x")


def test_ordered_routing_blocks_the_later_signer(deal, settings):
    _enable_signing(settings)
    manager, tx, version = deal
    sent = validate_and_send(manager, _build_package(manager, tx, version))
    seller = sent.signers.get(role_label="Seller")

    payload = ceremony_payload(sent, seller)
    assert payload["canSign"] is False
    assert payload["recovery"]["code"] == "not_your_turn"

    with pytest.raises(ValidationError):
        start_intent(
            package=sent,
            signer=seller,
            consent_accepted=True,
            disclosure_version=DISCLOSURE_VERSION,
            request_meta=_meta(),
        )


def test_signer_cannot_submit_another_signers_field(deal, settings):
    _enable_signing(settings)
    manager, tx, version = deal
    sent = validate_and_send(manager, _build_package(manager, tx, version))
    buyer = sent.signers.get(role_label="Buyer")

    with pytest.raises(PermissionDenied):
        _sign(buyer, settings=settings, text_values={"SellerSignature": "x"})


def test_full_ordered_flow_finalizes_with_sealed_artifacts(deal, settings):
    _enable_signing(settings)
    manager, tx, version = deal
    sent = validate_and_send(manager, _build_package(manager, tx, version))

    buyer = sent.signers.get(role_label="Buyer")
    result = _sign(buyer, settings=settings)
    assert result["signed"] is True

    seller = SignaturePackageSigner.objects.get(
        pk=sent.signers.get(role_label="Seller").pk
    )
    assert seller.status == SignatureSignerStatus.INVITED, "routing advanced"

    _sign(seller, settings=settings, session="sess-2")
    assert SignatureRecord.objects.filter(package=sent).count() == 2

    assert finalize_package(sent.pk) == "completed"
    sent.refresh_from_db()
    assert sent.status == SignaturePackageStatus.COMPLETED
    assert sent.completed_at is not None

    signed = SignatureArtifact.objects.filter(
        package=sent, kind=SignatureArtifactKind.SIGNED_PDF
    )
    certificate = SignatureArtifact.objects.filter(
        package=sent,
        kind=SignatureArtifactKind.CERTIFICATE_OF_COMPLETION,
        package_document__isnull=True,
    )
    assert signed.count() == 1
    assert certificate.count() == 1
    assert signed.get().byte_size > 0

    version.refresh_from_db()
    assert version.signature_status == DocumentSignatureStatus.SIGNED
    assert version.is_locked is True

    # Re-running must not mint a second set of artifacts.
    assert finalize_package(sent.pk) == "already"
    assert SignatureArtifact.objects.filter(package=sent).count() == 2


def test_completing_twice_is_idempotent(deal, settings):
    _enable_signing(settings)
    manager, tx, version = deal
    sent = validate_and_send(manager, _build_package(manager, tx, version))
    buyer = sent.signers.get(role_label="Buyer")

    payload = start_intent(
        package=sent,
        signer=buyer,
        consent_accepted=True,
        disclosure_version=DISCLOSURE_VERSION,
        request_meta=_meta(),
    )
    intent_id = UUID(payload["ceremony"]["intentPublicId"])

    def _submit():
        return complete_signing(
            intent_public_id=intent_id,
            signer=SignaturePackageSigner.objects.get(pk=buyer.pk),
            signature_data_url=_png_data_url(),
            signed_date="2026-09-22",
            request_meta=_meta(),
        )

    first = _submit()
    replay = _submit()

    assert replay["idempotent"] is True
    assert replay["signaturePublicId"] == first["signaturePublicId"]
    assert SignatureRecord.objects.filter(package=sent, signer=buyer).count() == 1


def test_decline_ends_the_package(deal, settings):
    _enable_signing(settings)
    manager, tx, version = deal
    sent = validate_and_send(manager, _build_package(manager, tx, version))
    buyer = sent.signers.get(role_label="Buyer")

    out = decline_signing(
        package=sent, signer=buyer, reason="Terms changed", request_meta=_meta()
    )
    assert out["packageStatus"] == SignaturePackageStatus.DECLINED

    buyer.refresh_from_db()
    assert buyer.status == SignatureSignerStatus.DECLINED
    assert not SignatureAccessToken.objects.filter(
        signer__package=sent, consumed_at__isnull=True
    ).exists()


def test_cancel_releases_pending_documents(deal, settings):
    _enable_signing(settings)
    manager, tx, version = deal
    sent = validate_and_send(manager, _build_package(manager, tx, version))

    cancelled = cancel_package(manager, sent)
    assert cancelled.status == SignaturePackageStatus.CANCELLED
    version.refresh_from_db()
    assert version.signature_status == DocumentSignatureStatus.NONE


def test_sent_package_contents_are_immutable(deal, settings):
    _enable_signing(settings)
    manager, tx, version = deal
    sent = validate_and_send(manager, _build_package(manager, tx, version))
    with pytest.raises(ValidationError):
        replace_package_contents(
            manager, sent, documents=[str(version.public_id)], signers=[], fields=[]
        )


def test_workspace_projection_hides_email_from_non_managers(deal, settings):
    _enable_signing(settings)
    manager, tx, version = deal
    validate_and_send(manager, _build_package(manager, tx, version))

    rows = serialize_packages_for_reader(manager, tx)
    assert len(rows) == 1
    assert rows[0]["progress"] == {"signed": 0, "total": 2}
    assert rows[0]["signers"][0]["email"] == "pat.buyer@example.com"

    outsider = completed_user(
        email="sig.outsider@example.com", office=office("philadelphia")
    )
    _assign(outsider, REALTOR, ScopeType.OFFICE, office("philadelphia"))
    hidden = serialize_packages_for_reader(_grant(outsider, VIEW_TRANSACTIONS), tx)
    assert hidden[0]["signers"][0]["email"] == ""
    assert hidden[0]["documents"][0]["sourceChecksum"] == ""


def test_draft_layout_round_trips_but_a_sent_one_does_not(deal, settings):
    """The authoring UI replaces contents wholesale, so a draft must carry its
    own geometry back or a save would silently drop every field."""
    _enable_signing(settings)
    manager, tx, version = deal
    draft = _build_package(manager, tx, version)

    rows = serialize_packages_for_reader(manager, tx)
    names = {field["name"] for field in rows[0]["fields"]}
    assert names == {"BuyerSignature", "BuyerDate", "SellerSignature"}
    assert rows[0]["fields"][0]["signerKey"] in {
        str(signer["publicId"]) for signer in rows[0]["signers"]
    }

    validate_and_send(manager, draft)
    assert "fields" not in serialize_packages_for_reader(manager, tx)[0]


def test_signatures_section_carries_the_deal_documents(deal):
    """The document picker builds a package from versions already on the deal."""
    manager, tx, version = deal
    payload = workspace_payload(manager, tx, section=WorkspaceSection.SIGNATURES)

    assert payload["signatureSchema"] is not None
    assert [row["publicId"] for row in payload["documents"]] == [
        str(version.document.public_id)
    ]


def test_provider_resolves_hub_native(settings):
    settings.TRANSACTION_SIGNING_PROVIDER = "hub_native"
    assert get_signing_provider().name == "hub_native"
