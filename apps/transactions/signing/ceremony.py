"""The signer-facing ceremony: resolve, disclose, intend, sign, or decline.

Two doors lead here. A Hub user is matched to a signer row by their own user
FK; an external party arrives with a magic link that resolves to exactly one
signer. Either way the signer identity comes from the server, never from the
request body, and a signer may only submit values for fields addressed to
them.

Shape follows :mod:`apps.contract.services.signing_service`: a short-lived
intent captures consent and binds the exact source bytes, and completion is
idempotent so a double submit cannot mint a second signature.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event, system_actor
from apps.transactions.media import checksum_of
from apps.transactions.models import (
    SignatureAccessToken,
    SignaturePackage,
    SignaturePackageDocument,
    SignaturePackageField,
    SignaturePackageSigner,
    SignatureRecord,
    SignatureSigningIntent,
)
from apps.transactions.signing.disclosure import (
    DISCLOSURE_VERSION,
    disclosure_payload,
)
from apps.transactions.signing.lifecycle import (
    PackageNotOpen,
    SignerNotEligible,
    assert_package_open,
    is_signer_eligible,
    lock_package,
    mark_declined,
    mark_signed,
    mark_viewed,
)
from apps.transactions.signing.pdf_stamp import (
    appearance_checksum,
    decode_data_url_image,
    require_signing_cert_or_raise,
    signing_is_ready,
)
from apps.transactions.signing.serialize import (
    serialize_ceremony_document,
    serialize_ceremony_signer,
)
from apps.transactions.signing.tokens import consume_token, lookup_active_token
from apps.transactions.taxonomy import (
    SignatureDeliveryMethod,
    SignatureFieldType,
    SignatureIntentStatus,
    SignaturePackageStatus,
    SignatureSignerStatus,
)
from apps.user.models import User

logger = logging.getLogger("apps.transactions")

SIGNING_METHOD = "hub_embedded"
UA_TRUNCATE = 256
MIN_APPEARANCE_BYTES = 32
MAX_TEXT_VALUE = 200


class CeremonyError(ValidationError):
    """User-facing recovery error raised inside the ceremony."""


@dataclass(frozen=True)
class RequestMeta:
    session_key: str
    ip_address: str
    user_agent: str


def hash_session_key(session_key: str) -> str:
    return hashlib.sha256((session_key or "").encode("utf-8")).hexdigest()


def hash_ip(ip_address: str) -> str:
    value = (ip_address or "").strip()
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_user_agent(user_agent: str) -> str:
    value = (user_agent or "")[:UA_TRUNCATE]
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def package_version(package: SignaturePackage) -> str:
    """Opaque concurrency token derived from ``updated_at`` (ISO µs)."""
    return package.updated_at.isoformat(timespec="microseconds")


# --------------------------------------------------------------------------- #
# Signer resolution
# --------------------------------------------------------------------------- #


def resolve_signer_from_hub_user(
    user: User, package: SignaturePackage
) -> SignaturePackageSigner:
    """Match an authenticated Hub user to their own signer row."""
    signer = SignaturePackageSigner.objects.filter(
        package_id=package.pk,
        user_id=getattr(user, "pk", None),
        delivery_method=SignatureDeliveryMethod.HUB,
    ).first()
    if signer is None:
        raise PermissionDenied(_("You are not a signer on this package."))
    return signer


def resolve_signer_from_token(
    raw_token: str,
) -> tuple[SignaturePackage, SignaturePackageSigner, SignatureAccessToken]:
    """Resolve a magic link to its one signer, package, and token row."""
    token = lookup_active_token(raw_token)
    if token is None:
        raise PermissionDenied(
            _("This signing link is invalid or has expired. Ask for a new one.")
        )
    signer = token.signer
    return signer.package, signer, token


def _signer_fields(
    package: SignaturePackage, signer: SignaturePackageSigner
) -> list[SignaturePackageField]:
    return list(
        SignaturePackageField.objects.filter(package_id=package.pk, signer_id=signer.pk)
        .select_related("document", "document__package", "signer")
        .order_by("document__sort_order", "page", "pk")
    )


def _source_checksums(package: SignaturePackage) -> dict[str, str]:
    return {
        str(public_id): checksum
        for public_id, checksum in SignaturePackageDocument.objects.filter(
            package_id=package.pk
        ).values_list("public_id", "source_checksum")
    }


def _read_version_bytes(document: SignaturePackageDocument) -> bytes:
    field = document.version.file
    field.open("rb")
    try:
        return field.read()
    finally:
        field.close()


def _assert_sources_unchanged(package: SignaturePackage) -> None:
    documents = SignaturePackageDocument.objects.filter(
        package_id=package.pk
    ).select_related("version")
    for document in documents:
        if checksum_of(_read_version_bytes(document)) != document.source_checksum:
            raise CeremonyError(
                {
                    "form": [
                        str(
                            _(
                                "A document in this package changed since it was "
                                "sent. Contact the brokerage before signing."
                            )
                        )
                    ]
                }
            )


# --------------------------------------------------------------------------- #
# Ceremony page
# --------------------------------------------------------------------------- #


def ceremony_payload(
    package: SignaturePackage,
    signer: SignaturePackageSigner,
    *,
    intent: SignatureSigningIntent | None = None,
) -> dict[str, Any]:
    """Inertia props for one signer's view of one package."""
    ready = signing_is_ready()
    open_now = package.status in {
        SignaturePackageStatus.SENT,
        SignaturePackageStatus.IN_PROGRESS,
    }
    eligible = open_now and is_signer_eligible(package, signer)
    already_signed = signer.status == SignatureSignerStatus.SIGNED

    recovery: dict[str, str] | None = None
    if already_signed:
        recovery = {
            "code": "already_signed",
            "message": str(_("You have already signed this package.")),
        }
    elif not open_now:
        recovery = {
            "code": "not_open",
            "message": str(
                _("This package is not open for signing. Contact the brokerage.")
            ),
        }
    elif not ready:
        recovery = {
            "code": "signing_unavailable",
            "message": str(
                _("Electronic signing is temporarily unavailable. Try again later.")
            ),
        }
    elif not eligible:
        recovery = {
            "code": "not_your_turn",
            "message": str(
                _(
                    "Another party signs before you. We will notify you when "
                    "it is your turn."
                )
            ),
        }

    fields = _signer_fields(package, signer)
    by_document: dict[int, list[SignaturePackageField]] = {}
    for field in fields:
        by_document.setdefault(field.document_id, []).append(field)

    documents = (
        SignaturePackageDocument.objects.filter(package_id=package.pk)
        .select_related("version", "package")
        .order_by("sort_order", "pk")
    )

    return {
        "canSign": bool(eligible and ready and not already_signed),
        "signingReady": ready,
        "recovery": recovery,
        "disclosure": disclosure_payload(),
        "package": {
            "publicId": str(package.public_id),
            "title": package.title,
            "status": package.status,
            "routingMode": package.routing_mode,
            "disclosureVersion": package.disclosure_version or DISCLOSURE_VERSION,
            "expiresAt": package.expires_at.isoformat() if package.expires_at else None,
            "expectedVersion": package_version(package),
        },
        "signer": serialize_ceremony_signer(signer),
        "documents": [
            serialize_ceremony_document(
                document, fields=by_document.get(document.pk, [])
            )
            for document in documents
        ],
        "ceremony": None
        if intent is None
        else {
            "intentPublicId": str(intent.public_id),
            "expiresAt": intent.expires_at.isoformat(),
        },
        "errors": {"fields": {}, "form": []},
    }


# --------------------------------------------------------------------------- #
# Intent
# --------------------------------------------------------------------------- #


def _intent_ttl() -> int:
    raw = getattr(settings, "TRANSACTION_SIGNING_INTENT_TTL_SECONDS", 900)
    try:
        return max(60, int(raw))
    except (TypeError, ValueError):
        return 900


def _expire_stale_intents(package: SignaturePackage, *, now) -> None:
    SignatureSigningIntent.objects.filter(
        package_id=package.pk,
        status=SignatureIntentStatus.PENDING,
        expires_at__lte=now,
    ).update(status=SignatureIntentStatus.EXPIRED)


def _cancel_pending_intents(
    package: SignaturePackage, signer: SignaturePackageSigner
) -> None:
    SignatureSigningIntent.objects.filter(
        package_id=package.pk,
        signer_id=signer.pk,
        status=SignatureIntentStatus.PENDING,
    ).update(status=SignatureIntentStatus.CANCELLED)


@db_transaction.atomic
def start_intent(
    *,
    package: SignaturePackage,
    signer: SignaturePackageSigner,
    consent_accepted: bool,
    disclosure_version: str,
    request_meta: RequestMeta,
    actor: User | None = None,
    access_token: SignatureAccessToken | None = None,
) -> dict[str, Any]:
    """Capture consent and bind the exact bytes this signer is about to sign."""
    require_signing_cert_or_raise()

    if not consent_accepted:
        raise CeremonyError(
            {
                "consentAccepted": str(
                    _("You must acknowledge the disclosure to continue.")
                )
            }
        )
    if disclosure_version != DISCLOSURE_VERSION:
        raise CeremonyError(
            {
                "form": [
                    str(
                        _(
                            "The disclosure text changed. Refresh this page and "
                            "acknowledge the current disclosure."
                        )
                    )
                ]
            }
        )
    if not (request_meta.session_key or "").strip():
        raise CeremonyError(
            {"form": [str(_("Your session is missing. Reload the page and retry."))]}
        )

    locked = lock_package(package.pk)
    assert_package_open(locked)
    signer.refresh_from_db()
    if signer.status == SignatureSignerStatus.SIGNED:
        raise CeremonyError({"form": [str(_("You have already signed this package."))]})
    if not is_signer_eligible(locked, signer):
        raise SignerNotEligible()

    fields = _signer_fields(locked, signer)
    if not any(f.field_type == SignatureFieldType.SIGNATURE for f in fields):
        raise CeremonyError(
            {
                "form": [
                    str(
                        _(
                            "This package has no signature field for you. "
                            "Contact the brokerage."
                        )
                    )
                ]
            }
        )

    _assert_sources_unchanged(locked)

    now = timezone.now()
    _expire_stale_intents(locked, now=now)
    _cancel_pending_intents(locked, signer)
    mark_viewed(signer, now=now)

    intent = SignatureSigningIntent(
        package=locked,
        signer=signer,
        actor=actor if getattr(actor, "pk", None) else None,
        package_version=package_version(locked),
        source_checksums=_source_checksums(locked),
        session_key_hash=hash_session_key(request_meta.session_key),
        access_token_hash=access_token.token_hash if access_token else "",
        request_ip_hash=hash_ip(request_meta.ip_address),
        request_ua_hash=hash_user_agent(request_meta.user_agent),
        disclosure_version=DISCLOSURE_VERSION,
        consent_accepted_at=now,
        status=SignatureIntentStatus.PENDING,
        expires_at=now + timedelta(seconds=_intent_ttl()),
    )
    intent.full_clean(exclude={"actor"})
    intent.save()

    log_event(
        "transaction.signing_intent.created",
        actor=actor_from_user(actor) if actor is not None else system_actor("signing"),
        target=AuditTarget(
            target_type="transaction.signature_package",
            target_id=str(locked.public_id),
            target_label=signer.role_label,
            target_snapshot={
                "intent_id": str(intent.public_id),
                "signer_id": str(signer.public_id),
                "disclosure_version": DISCLOSURE_VERSION,
            },
        ),
        outcome=AuditEvent.Outcome.SUCCESS,
        source="service",
        channel="transactions",
        metadata={
            "ip_hash": intent.request_ip_hash,
            "ua_hash": intent.request_ua_hash,
        },
    )

    locked.refresh_from_db()
    signer.refresh_from_db()
    return ceremony_payload(locked, signer, intent=intent)


# --------------------------------------------------------------------------- #
# Completion
# --------------------------------------------------------------------------- #


def _clean_text_values(
    raw: dict[str, str] | None, *, fields: list[SignaturePackageField]
) -> dict[str, str]:
    """Keep only values addressed to fields this signer actually owns."""
    if not raw:
        return {}
    if not isinstance(raw, dict):
        raise CeremonyError({"form": [str(_("Field values must be an object."))]})
    allowed = {
        field.name
        for field in fields
        if field.field_type in {SignatureFieldType.TEXT, SignatureFieldType.DATE}
    }
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise PermissionDenied(
            _("You cannot submit values for fields assigned to another signer.")
        )
    return {str(name): str(value or "")[:MAX_TEXT_VALUE] for name, value in raw.items()}


def _assert_required_values(
    fields: list[SignaturePackageField], values: dict[str, str]
) -> None:
    missing = [
        field.name
        for field in fields
        if field.required
        and field.field_type == SignatureFieldType.TEXT
        and not (values.get(field.name) or "").strip()
    ]
    if missing:
        raise CeremonyError(
            {"fields": {name: str(_("This field is required.")) for name in missing}}
        )


@db_transaction.atomic
def complete_signing(
    *,
    intent_public_id: UUID,
    signer: SignaturePackageSigner,
    signature_data_url: str,
    signed_date: str,
    initials_data_url: str = "",
    text_values: dict[str, str] | None = None,
    request_meta: RequestMeta,
    access_token: SignatureAccessToken | None = None,
) -> dict[str, Any]:
    """Record one durable signature, then advance or finalize the package."""
    require_signing_cert_or_raise()

    intent = (
        SignatureSigningIntent.objects.select_related("package", "signer")
        .filter(public_id=intent_public_id, signer_id=signer.pk)
        .first()
    )
    if intent is None:
        raise PermissionDenied(_("Signing intent is not available."))

    locked = lock_package(intent.package_id)

    existing = SignatureRecord.objects.filter(
        package_id=locked.pk, signer_id=signer.pk
    ).first()
    if existing is not None:
        return {
            "ok": True,
            "idempotent": True,
            "signed": True,
            "signaturePublicId": str(existing.public_id),
            "packageStatus": locked.status,
        }

    now = timezone.now()
    if intent.status != SignatureIntentStatus.PENDING:
        raise CeremonyError(
            {"form": [str(_("Signing intent is no longer pending. Start again."))]}
        )
    if intent.expires_at <= now:
        intent.status = SignatureIntentStatus.EXPIRED
        intent.save(update_fields=["status"])
        raise CeremonyError({"form": [str(_("Signing intent expired. Start again."))]})
    if intent.session_key_hash != hash_session_key(request_meta.session_key):
        raise PermissionDenied(
            _("Signing session does not match this browser session.")
        )
    if intent.access_token_hash and (
        access_token is None or access_token.token_hash != intent.access_token_hash
    ):
        raise PermissionDenied(_("Signing link does not match this ceremony."))

    assert_package_open(locked, now=now)
    signer.refresh_from_db()
    if not is_signer_eligible(locked, signer):
        raise SignerNotEligible()

    if intent.source_checksums != _source_checksums(locked):
        raise CeremonyError(
            {"form": [str(_("This package changed since you started. Start again."))]}
        )
    _assert_sources_unchanged(locked)

    date_value = (signed_date or "").strip()
    if not date_value:
        raise CeremonyError({"signedDate": str(_("Enter the signature date."))})

    signature_png = decode_data_url_image(signature_data_url)
    if len(signature_png) < MIN_APPEARANCE_BYTES:
        raise CeremonyError(
            {"signature": str(_("Draw or type your signature before submitting."))}
        )
    initials_png = (
        decode_data_url_image(initials_data_url) if initials_data_url else b""
    )

    fields = _signer_fields(locked, signer)
    values = _clean_text_values(text_values, fields=fields)
    _assert_required_values(fields, values)

    record = SignatureRecord(
        package=locked,
        signer=signer,
        intent=intent,
        method=SIGNING_METHOD,
        disclosure_version=intent.disclosure_version,
        source_checksums=dict(intent.source_checksums or {}),
        field_values=values,
        signed_date_value=date_value,
        appearance_checksum=appearance_checksum(signature_png),
        request_ip_hash=intent.request_ip_hash,
        request_ua_hash=intent.request_ua_hash,
    )
    record.appearance_file.save(
        f"appearance-{record.public_id}.png", ContentFile(signature_png), save=False
    )
    if initials_png:
        record.initials_file.save(
            f"initials-{record.public_id}.png", ContentFile(initials_png), save=False
        )
    try:
        with db_transaction.atomic():
            record.full_clean(exclude={"signed_at"})
            record.save()
    except IntegrityError:
        # Two submissions raced past the read above; the first one is durable.
        duplicate = SignatureRecord.objects.filter(
            package_id=locked.pk, signer_id=signer.pk
        ).first()
        if duplicate is None:
            raise
        return {
            "ok": True,
            "idempotent": True,
            "signed": True,
            "signaturePublicId": str(duplicate.public_id),
            "packageStatus": locked.status,
        }

    intent.status = SignatureIntentStatus.CONSUMED
    intent.consumed_at = now
    intent.save(update_fields=["status", "consumed_at"])
    if access_token is not None:
        consume_token(access_token)

    mark_signed(signer, package=locked, now=now)

    log_event(
        "transaction.signature.created",
        actor=actor_from_user(signer.user)
        if signer.user_id
        else system_actor("signing"),
        target=AuditTarget(
            target_type="transaction.signature_package",
            target_id=str(locked.public_id),
            target_label=signer.role_label,
            target_snapshot={
                "signature_id": str(record.public_id),
                "intent_id": str(intent.public_id),
                "signer_id": str(signer.public_id),
                "disclosure_version": record.disclosure_version,
                "method": record.method,
            },
        ),
        outcome=AuditEvent.Outcome.SUCCESS,
        source="service",
        channel="transactions",
    )

    locked.refresh_from_db()
    return {
        "ok": True,
        "signed": True,
        "signaturePublicId": str(record.public_id),
        "packageStatus": locked.status,
    }


@db_transaction.atomic
def decline_signing(
    *,
    package: SignaturePackage,
    signer: SignaturePackageSigner,
    reason: str = "",
    request_meta: RequestMeta | None = None,
    access_token: SignatureAccessToken | None = None,
) -> dict[str, Any]:
    """One party's refusal ends the package for everyone."""
    locked = lock_package(package.pk)
    signer.refresh_from_db()

    if signer.status == SignatureSignerStatus.SIGNED:
        raise CeremonyError(
            {"form": [str(_("You have already signed; a decline is not possible."))]}
        )
    if locked.status not in {
        SignaturePackageStatus.SENT,
        SignaturePackageStatus.IN_PROGRESS,
    }:
        raise PackageNotOpen()

    _cancel_pending_intents(locked, signer)
    mark_declined(signer, package=locked, reason=reason)
    if access_token is not None:
        consume_token(access_token)

    log_event(
        "transaction.signature.declined",
        actor=actor_from_user(signer.user)
        if signer.user_id
        else system_actor("signing"),
        target=AuditTarget(
            target_type="transaction.signature_package",
            target_id=str(locked.public_id),
            target_label=signer.role_label,
            target_snapshot={
                "signer_id": str(signer.public_id),
                "has_reason": bool((reason or "").strip()),
            },
        ),
        outcome=AuditEvent.Outcome.SUCCESS,
        source="service",
        channel="transactions",
        metadata={
            "ip_hash": hash_ip(request_meta.ip_address) if request_meta else "",
            "ua_hash": hash_user_agent(request_meta.user_agent) if request_meta else "",
        },
    )

    locked.refresh_from_db()
    return {"ok": True, "declined": True, "packageStatus": locked.status}


__all__ = [
    "CeremonyError",
    "RequestMeta",
    "ceremony_payload",
    "complete_signing",
    "decline_signing",
    "hash_ip",
    "hash_session_key",
    "hash_user_agent",
    "package_version",
    "resolve_signer_from_hub_user",
    "resolve_signer_from_token",
    "start_intent",
]
