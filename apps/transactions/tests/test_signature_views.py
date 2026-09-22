"""HTTP surface for signature packages: scope, both ceremony doors, delivery."""

from __future__ import annotations

import base64
import io
import json
from uuid import UUID, uuid4

import pytest
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from apps.transactions.concurrency import transaction_version
from apps.transactions.deal_documents import upload_document
from apps.transactions.models import (
    SignaturePackage,
    SignatureRecord,
    SignatureSigningIntent,
    TransactionDocumentVersion,
)
from apps.transactions.permissions import (
    MANAGE_TRANSACTIONS,
    TRANSITION_TRANSACTIONS,
    VIEW_TRANSACTIONS,
)
from apps.transactions.signing.authoring import (
    create_draft_package,
    replace_package_contents,
    validate_and_send,
)
from apps.transactions.signing.disclosure import DISCLOSURE_VERSION
from apps.transactions.signing.tokens import issue_access_token
from apps.transactions.taxonomy import (
    SignatureDeliveryMethod,
    SignaturePackageStatus,
    SignatureSignerStatus,
)
from apps.transactions.tests.conftest import make_draft, office
from apps.user.models import User, UserRoleAssignment
from apps.user.roles import REALTOR, TRANSACTION_COORDINATOR, ScopeType
from apps.user.tests.test_profile import completed_user
from apps.web.tests.test_permissions import inertia_page_script

pytestmark = pytest.mark.django_db


def _inertia_props(response) -> dict:
    """Assert on the Inertia page object, never on rendered HTML."""
    return inertia_page_script(response)["props"]


def _real_pdf(pages: int = 2) -> bytes:
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=letter)
    for index in range(pages):
        pdf.drawString(72, 700, f"Deal page {index + 1}")
        pdf.showPage()
    pdf.save()
    return buf.getvalue()


def _png_data_url() -> str:
    raw = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42m"
        "NkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )
    return "data:image/png;base64," + base64.b64encode(raw).decode()


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


@pytest.fixture(autouse=True)
def _signing_enabled(settings):
    """Dev-mode sealing; the cert gate would otherwise refuse every send."""
    settings.DEBUG = True
    settings.CONTRACT_SIGNING_CERT_PATH = ""
    settings.CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV = True


@pytest.fixture
def deal(seeded):
    manager = completed_user(
        email="sigview.manager@example.com", office=office("fairfax-va")
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
    tx.refresh_from_db()
    return manager, tx, version


def _outsider(seeded) -> User:
    user = completed_user(
        email="sigview.outsider@example.com", office=office("philadelphia")
    )
    _assign(user, REALTOR, ScopeType.OFFICE, office("philadelphia"))
    return _grant(user, MANAGE_TRANSACTIONS, VIEW_TRANSACTIONS)


def _signer_payload(key: str, role: str, order: int, **extra) -> dict:
    return {
        "key": key,
        "roleLabel": role,
        "displayName": f"{role} Person",
        "email": f"{key}@example.com",
        "routingOrder": order,
        **extra,
    }


def _field_payload(name: str, signer_key: str, document_key: str, page: int) -> dict:
    return {
        "name": name,
        "type": "signature",
        "signerKey": signer_key,
        "documentKey": document_key,
        "page": page,
        "x": 72,
        "y": 600,
        "w": 160,
        "h": 40,
    }


def _build_package(manager, tx, version, *, hub_user: User | None = None):
    """One email signer, plus an optional Hub signer second in the order."""
    package = create_draft_package(manager, tx, title="Offer package")
    key = str(version.public_id)
    signers = [_signer_payload("buyer", "Buyer", 1)]
    fields = [_field_payload("BuyerSignature", "buyer", key, 1)]
    if hub_user is not None:
        signers.append(
            _signer_payload(
                "seller",
                "Seller",
                2,
                deliveryMethod=SignatureDeliveryMethod.HUB,
                userId=hub_user.pk,
                email=hub_user.email,
            )
        )
        fields.append(_field_payload("SellerSignature", "seller", key, 2))
    tx.refresh_from_db()
    return replace_package_contents(
        manager, package, documents=[key], signers=signers, fields=fields
    )


# --------------------------------------------------------------------------- #
# Authoring
# --------------------------------------------------------------------------- #


def test_create_draft_over_json(client, deal):
    manager, tx, _version = deal
    client.force_login(manager)
    response = client.post(
        reverse(
            "transaction_signature_package_create", kwargs={"public_id": tx.public_id}
        ),
        data=json.dumps(
            {
                "expectedVersion": transaction_version(tx),
                "title": "Closing signatures",
                "routingMode": "parallel",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 302
    package = SignaturePackage.objects.get(transaction=tx)
    assert package.title == "Closing signatures"
    assert package.routing_mode == "parallel"
    assert package.status == SignaturePackageStatus.DRAFT


def test_save_rewrites_settings_and_contents(client, deal):
    manager, tx, version = deal
    package = create_draft_package(manager, tx, title="Before")
    tx.refresh_from_db()
    client.force_login(manager)
    key = str(version.public_id)
    response = client.post(
        reverse(
            "transaction_signature_package_save",
            kwargs={"public_id": tx.public_id, "package_id": package.public_id},
        ),
        data=json.dumps(
            {
                "expectedVersion": transaction_version(tx),
                "title": "After",
                "routingMode": "ordered",
                "expiresAt": None,
                "documents": [{"versionPublicId": key, "sortOrder": 0}],
                "signers": [_signer_payload("buyer", "Buyer", 1)],
                "fields": [_field_payload("BuyerSignature", "buyer", key, 1)],
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 302
    package.refresh_from_db()
    assert package.title == "After"
    assert package.documents.count() == 1
    assert package.signers.count() == 1


def test_authoring_denied_outside_office_scope(client, deal, seeded):
    manager, tx, version = deal
    package = _build_package(manager, tx, version)
    tx.refresh_from_db()
    client.force_login(_outsider(seeded))
    response = client.post(
        reverse(
            "transaction_signature_package_send",
            kwargs={"public_id": tx.public_id, "package_id": package.public_id},
        ),
        data=json.dumps({"expectedVersion": transaction_version(tx)}),
        content_type="application/json",
    )
    assert response.status_code == 404
    package.refresh_from_db()
    assert package.status == SignaturePackageStatus.DRAFT


def test_send_then_remind_over_json(client, deal):
    manager, tx, version = deal
    package = _build_package(manager, tx, version)
    tx.refresh_from_db()
    client.force_login(manager)

    sent = client.post(
        reverse(
            "transaction_signature_package_send",
            kwargs={"public_id": tx.public_id, "package_id": package.public_id},
        ),
        data=json.dumps({"expectedVersion": transaction_version(tx)}),
        content_type="application/json",
        HTTP_ACCEPT="application/json",
    )
    assert sent.status_code == 200
    assert sent.json() == {"ok": True, "status": SignaturePackageStatus.SENT}

    buyer = package.signers.get(role_label="Buyer")
    assert buyer.status == SignatureSignerStatus.INVITED

    reminded = client.post(
        reverse(
            "transaction_signature_signer_remind",
            kwargs={
                "public_id": tx.public_id,
                "package_id": package.public_id,
                "signer_id": buyer.public_id,
            },
        ),
        data=json.dumps({}),
        content_type="application/json",
        HTTP_ACCEPT="application/json",
    )
    assert reminded.status_code == 200
    assert reminded.json()["reminded"] is True


def test_cancel_over_json(client, deal):
    manager, tx, version = deal
    package = validate_and_send(manager, _build_package(manager, tx, version))
    tx.refresh_from_db()
    client.force_login(manager)
    response = client.post(
        reverse(
            "transaction_signature_package_cancel",
            kwargs={"public_id": tx.public_id, "package_id": package.public_id},
        ),
        data=json.dumps({"expectedVersion": transaction_version(tx)}),
        content_type="application/json",
        HTTP_ACCEPT="application/json",
    )
    assert response.status_code == 200
    assert response.json()["status"] == SignaturePackageStatus.CANCELLED


# --------------------------------------------------------------------------- #
# Hub ceremony
# --------------------------------------------------------------------------- #


def _hub_signer_user(seeded) -> User:
    return completed_user(
        email="sigview.hubsigner@example.com", office=office("fairfax-va")
    )


def test_hub_ceremony_renders_for_the_matched_signer(client, deal, seeded):
    manager, tx, version = deal
    hub_user = _hub_signer_user(seeded)
    package = validate_and_send(
        manager, _build_package(manager, tx, version, hub_user=hub_user)
    )
    client.force_login(hub_user)
    response = client.get(
        reverse(
            "transaction_signature_ceremony", kwargs={"public_id": package.public_id}
        )
    )
    assert response.status_code == 200
    props = _inertia_props(response)
    assert props["signer"]["roleLabel"] == "Seller"
    assert props["endpoints"]["mode"] == "hub"
    # Ordered routing: the buyer signs first, so the seller is not yet eligible.
    assert props["canSign"] is False
    assert props["recovery"]["code"] == "not_your_turn"


def test_hub_ceremony_denies_a_non_signer(client, deal, seeded):
    manager, tx, version = deal
    package = validate_and_send(
        manager, _build_package(manager, tx, version, hub_user=_hub_signer_user(seeded))
    )
    # The manager can manage the deal but is not a signer on this package.
    client.force_login(manager)
    response = client.get(
        reverse(
            "transaction_signature_ceremony", kwargs={"public_id": package.public_id}
        )
    )
    assert response.status_code == 403


def test_hub_ceremony_requires_login(client, deal, seeded):
    manager, tx, version = deal
    package = validate_and_send(
        manager, _build_package(manager, tx, version, hub_user=_hub_signer_user(seeded))
    )
    response = client.get(
        reverse(
            "transaction_signature_ceremony", kwargs={"public_id": package.public_id}
        )
    )
    assert response.status_code == 302


def test_unknown_package_is_not_found(client, deal):
    manager, _tx, _version = deal
    client.force_login(manager)
    response = client.get(
        reverse("transaction_signature_ceremony", kwargs={"public_id": uuid4()})
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Magic-link ceremony
# --------------------------------------------------------------------------- #


def test_magic_link_ceremony_needs_no_login(client, deal):
    manager, tx, version = deal
    package = validate_and_send(manager, _build_package(manager, tx, version))
    buyer = package.signers.get(role_label="Buyer")
    _token, raw = issue_access_token(buyer)

    response = client.get(
        reverse("transaction_signature_magic_link", kwargs={"token": raw})
    )
    assert response.status_code == 200
    props = _inertia_props(response)
    assert props["endpoints"]["mode"] == "magicLink"
    assert props["signer"]["roleLabel"] == "Buyer"
    assert props["canSign"] is True
    # A session exists now, so CSRF has something to bind the POSTs to.
    assert client.session.session_key


def test_magic_link_is_exempt_from_the_onboarding_gate():
    """An external signer must not be bounced to ``/onboarding``.

    ``ProfileCompletionMiddleware`` exempts a route by reading exactly this
    flag off the route's policy, so asserting the policy is asserting the gate.
    """
    from apps.web.authorization import ROUTE_POLICIES

    policy = ROUTE_POLICIES["transaction_signature_magic_link"]
    assert policy.access == "public"
    assert policy.allow_incomplete_profile is True
    assert "transaction_signature_magic_link_complete" in policy.route_names


def test_magic_link_rejects_a_tampered_token(client, deal):
    manager, tx, version = deal
    package = validate_and_send(manager, _build_package(manager, tx, version))
    buyer = package.signers.get(role_label="Buyer")
    _token, raw = issue_access_token(buyer)

    response = client.get(
        reverse("transaction_signature_magic_link", kwargs={"token": raw + "x"})
    )
    assert response.status_code == 403


def test_magic_link_signs_end_to_end(client, deal):
    manager, tx, version = deal
    package = validate_and_send(manager, _build_package(manager, tx, version))
    buyer = package.signers.get(role_label="Buyer")
    _token, raw = issue_access_token(buyer)

    start = client.post(
        reverse("transaction_signature_magic_link", kwargs={"token": raw}),
        data=json.dumps(
            {"consentAccepted": True, "disclosureVersion": DISCLOSURE_VERSION}
        ),
        content_type="application/json",
    )
    assert start.status_code == 200
    intent_id = _inertia_props(start)["ceremony"]["intentPublicId"]
    assert UUID(intent_id)

    done = client.post(
        reverse("transaction_signature_magic_link_complete", kwargs={"token": raw}),
        data=json.dumps(
            {
                "intentPublicId": intent_id,
                "signatureDataUrl": _png_data_url(),
                "signedDate": "2026-09-22",
            }
        ),
        content_type="application/json",
    )
    assert done.status_code == 200
    assert done.json()["signed"] is True
    assert SignatureRecord.objects.filter(package=package, signer=buyer).count() == 1

    buyer.refresh_from_db()
    assert buyer.status == SignatureSignerStatus.SIGNED
    # The link is one-time: redeeming it burns it.
    replay = client.get(
        reverse("transaction_signature_magic_link", kwargs={"token": raw})
    )
    assert replay.status_code == 403


def test_magic_link_decline_ends_the_package(client, deal):
    manager, tx, version = deal
    package = validate_and_send(manager, _build_package(manager, tx, version))
    buyer = package.signers.get(role_label="Buyer")
    _token, raw = issue_access_token(buyer)

    response = client.post(
        reverse("transaction_signature_magic_link_decline", kwargs={"token": raw}),
        data=json.dumps({"reason": "Terms changed"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["packageStatus"] == SignaturePackageStatus.DECLINED


def test_complete_refuses_an_unknown_intent(client, deal):
    manager, tx, version = deal
    package = validate_and_send(manager, _build_package(manager, tx, version))
    buyer = package.signers.get(role_label="Buyer")
    _token, raw = issue_access_token(buyer)

    response = client.post(
        reverse("transaction_signature_magic_link_complete", kwargs={"token": raw}),
        data=json.dumps(
            {
                "intentPublicId": str(uuid4()),
                "signatureDataUrl": _png_data_url(),
                "signedDate": "2026-09-22",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 403
    body = response.json()
    assert body["ok"] is False
    assert body["validation"]["form"]


# --------------------------------------------------------------------------- #
# File delivery
# --------------------------------------------------------------------------- #


def test_preview_accepts_a_link_and_refuses_a_stranger(client, deal, seeded):
    manager, tx, version = deal
    package = validate_and_send(manager, _build_package(manager, tx, version))
    document = package.documents.get()
    buyer = package.signers.get(role_label="Buyer")
    _token, raw = issue_access_token(buyer)
    url = reverse(
        "transaction_signature_document_preview",
        kwargs={"public_id": package.public_id, "document_id": document.public_id},
    )

    assert client.get(url).status_code == 404, "anonymous with no token"
    assert client.get(f"{url}?t={raw}").status_code == 200
    assert client.get(f"{url}?t={raw}x").status_code == 404

    client.force_login(_outsider(seeded))
    assert client.get(url).status_code == 404

    client.force_login(manager)
    scoped = client.get(url)
    assert scoped.status_code == 200
    assert scoped["Cache-Control"].startswith("private, no-store")


def test_artifact_download_requires_scope(client, deal, seeded):
    from apps.transactions.signing.finalize import finalize_package

    manager, tx, version = deal
    package = validate_and_send(manager, _build_package(manager, tx, version))
    buyer = package.signers.get(role_label="Buyer")
    _token, raw = issue_access_token(buyer)

    client.post(
        reverse("transaction_signature_magic_link", kwargs={"token": raw}),
        data=json.dumps(
            {"consentAccepted": True, "disclosureVersion": DISCLOSURE_VERSION}
        ),
        content_type="application/json",
    )
    intent = SignatureSigningIntent.objects.get(signer_id=buyer.pk)
    client.post(
        reverse("transaction_signature_magic_link_complete", kwargs={"token": raw}),
        data=json.dumps(
            {
                "intentPublicId": str(intent.public_id),
                "signatureDataUrl": _png_data_url(),
                "signedDate": "2026-09-22",
            }
        ),
        content_type="application/json",
    )
    assert finalize_package(package.pk) == "completed"

    artifact = package.artifacts.filter(package_document__isnull=False).get()
    url = reverse(
        "transaction_signature_artifact_download",
        kwargs={"public_id": artifact.public_id},
    )

    client.force_login(_outsider(seeded))
    assert client.get(url).status_code == 404

    client.force_login(manager)
    response = client.get(url)
    assert response.status_code == 200
    assert response["Cache-Control"].startswith("private, no-store")
