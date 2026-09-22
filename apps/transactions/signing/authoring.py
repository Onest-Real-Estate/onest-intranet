"""Broker-side authoring of signature packages: build, validate, send, cancel.

Scope and permission mirror :mod:`apps.transactions.deal_documents` — the deal
must be visible in the caller's ``for_reader`` scope and the caller must be
able to manage it. Every write bumps the transaction's concurrency token so a
workspace ``expectedVersion`` held by another tab goes stale, and content is
only mutable while the package is a draft.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction as db_transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.service import AuditTarget, actor_from_user, log_on_commit
from apps.transactions.concurrency import (
    can_manage_workspace,
    load_workspace_transaction,
    lock_transaction,
    require_writable_transaction,
    touch_transaction,
)
from apps.transactions.media import checksum_of
from apps.transactions.models import (
    SignaturePackage,
    SignaturePackageDocument,
    SignaturePackageField,
    SignaturePackageSigner,
    Transaction,
    TransactionDocumentVersion,
    TransactionParty,
)
from apps.transactions.services import scoped_transaction_queryset
from apps.transactions.signing.disclosure import DISCLOSURE_VERSION
from apps.transactions.signing.field_layout import (
    normalize_package_fields,
    signer_keys_with_required_fields,
)
from apps.transactions.signing.lifecycle import (
    EVENT_PACKAGE_CANCELLED,
    EVENT_PACKAGE_SENT,
    invite_signers,
    lock_package,
    publish_package_event,
    set_package_status,
    signers_for_initial_invite,
)
from apps.transactions.signing.pdf_stamp import (
    page_count_of,
    require_signing_cert_or_raise,
)
from apps.transactions.signing.tokens import invalidate_package_tokens
from apps.transactions.taxonomy import (
    SIGNATURE_DELIVERY_METHOD_CODES,
    SIGNATURE_ROUTING_MODE_CODES,
    DocumentSignatureStatus,
    SignatureDeliveryMethod,
    SignaturePackageStatus,
    SignatureRoutingMode,
)
from apps.user.models import User

logger = logging.getLogger("apps.transactions")

MEDIA_TYPE_PDF = "application/pdf"
MAX_PACKAGE_DOCUMENTS = 20
MAX_PACKAGE_SIGNERS = 15

#: "Caller said nothing", as distinct from "caller cleared the value" — the
#: draft editor sends ``expiresAt: null`` to remove an expiry.
_UNSET = object()


class PackageNotDraft(ValidationError):
    """Content edits are only legal before the package is sent."""

    def __init__(self) -> None:
        super().__init__(
            {
                "form": [
                    str(
                        _(
                            "Only a draft package can be edited. Cancel this "
                            "package and build a new one."
                        )
                    )
                ]
            }
        )


# --------------------------------------------------------------------------- #
# Loading and authorization
# --------------------------------------------------------------------------- #


def _public_id(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    if hasattr(value, "public_id"):
        return value.public_id
    return UUID(str(value))


def _writable_transaction(
    actor: User, source: Any, expected_version: str
) -> Transaction:
    """Authorize manage, lock the deal row, and assert concurrency when given."""
    public_id = _public_id(source)
    if expected_version:
        return require_writable_transaction(
            actor, public_id, expected_version=expected_version
        )
    visible = load_workspace_transaction(actor, public_id)
    if not can_manage_workspace(actor, visible):
        raise PermissionDenied("You cannot edit this transaction.")
    return lock_transaction(visible.pk)


def load_package_for_reader(user: User, package: Any) -> SignaturePackage:
    """Resolve a package inside ``for_reader`` scope or raise ``DoesNotExist``."""
    scope = scoped_transaction_queryset(user)
    found = (
        SignaturePackage.objects.select_related("transaction", "transaction__office")
        .filter(public_id=_public_id(package), transaction__in=scope)
        .first()
    )
    if found is None:
        raise SignaturePackage.DoesNotExist
    return found


def _audit_target(package: SignaturePackage) -> AuditTarget:
    tx = package.transaction
    return AuditTarget(
        target_type="transaction.signature_package",
        target_id=str(package.public_id),
        target_label=package.title,
        target_snapshot={
            "transaction_id": str(tx.public_id),
            "reference": tx.reference,
            "status": package.status,
            "office_id": tx.office.stable_key if tx.office_pk else "",
        },
    )


# --------------------------------------------------------------------------- #
# Input parsing
# --------------------------------------------------------------------------- #


def _parse_title(raw: Any) -> str:
    title = str(raw or "").strip()
    if not title:
        raise ValidationError({"title": ["A package title is required."]})
    if len(title) > 180:
        raise ValidationError({"title": ["Titles are limited to 180 characters."]})
    return title


def _parse_routing_mode(raw: Any) -> str:
    mode = str(raw or SignatureRoutingMode.ORDERED).strip()
    if mode not in SIGNATURE_ROUTING_MODE_CODES:
        raise ValidationError({"routingMode": ["Unknown routing mode."]})
    return mode


def _parse_expires_at(raw: Any) -> datetime | None:
    if raw in (None, ""):
        return None
    if isinstance(raw, datetime):
        moment = raw
    else:
        try:
            moment = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationError(
                {"expiresAt": ["Use an ISO 8601 timestamp."]}
            ) from exc
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment, timezone.get_default_timezone())
    if moment <= timezone.now():
        raise ValidationError({"expiresAt": ["The expiry must be in the future."]})
    return moment


def _read_version_bytes(version: TransactionDocumentVersion) -> bytes:
    version.file.open("rb")
    try:
        return version.file.read()
    finally:
        version.file.close()


def _resolve_documents(tx: Transaction, raw: Any) -> list[dict[str, Any]]:
    """Freeze the chosen document versions with checksum and page count."""
    if not isinstance(raw, list) or not raw:
        raise ValidationError({"documents": ["Choose at least one document."]})
    if len(raw) > MAX_PACKAGE_DOCUMENTS:
        raise ValidationError(
            {
                "documents": [
                    f"A package can carry at most {MAX_PACKAGE_DOCUMENTS} documents."
                ]
            }
        )

    resolved: list[dict[str, Any]] = []
    seen: set[UUID] = set()
    for index, item in enumerate(raw):
        payload = item if isinstance(item, dict) else {"versionPublicId": item}
        try:
            version_id = _public_id(
                payload.get("versionPublicId")
                or payload.get("version_public_id")
                or payload.get("publicId")
            )
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                {"documents": [f"Document at index {index} has an invalid id."]}
            ) from exc
        if version_id in seen:
            raise ValidationError(
                {"documents": ["The same document version was listed twice."]}
            )
        seen.add(version_id)

        version = (
            TransactionDocumentVersion.objects.select_related("document")
            .filter(
                public_id=version_id,
                document__transaction_id=tx.pk,
                document__ended_at__isnull=True,
                is_active=True,
            )
            .first()
        )
        if version is None:
            raise ValidationError(
                {"documents": ["A chosen document is not on this transaction."]}
            )
        if not version.is_readable:
            raise ValidationError(
                {"documents": [f"“{version.display_name}” is not ready to sign yet."]}
            )
        if version.media_type != MEDIA_TYPE_PDF:
            raise ValidationError(
                {"documents": [f"“{version.display_name}” is not a PDF."]}
            )

        data = _read_version_bytes(version)
        live = checksum_of(data)
        if live != (version.checksum or "").lower():
            raise ValidationError(
                {
                    "documents": [
                        f"“{version.display_name}” changed on disk since it was "
                        "uploaded. Re-upload it before signing."
                    ]
                }
            )
        try:
            pages = page_count_of(data)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError(
                {"documents": [f"“{version.display_name}” could not be read as a PDF."]}
            ) from exc

        resolved.append(
            {
                "version": version,
                "key": str(version.public_id),
                "checksum": live,
                "page_count": max(1, pages),
                "sort_order": int(payload.get("sortOrder") or index),
            }
        )
    return resolved


def _resolve_signers(tx: Transaction, raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise ValidationError({"signers": ["Add at least one signer."]})
    if len(raw) > MAX_PACKAGE_SIGNERS:
        raise ValidationError(
            {"signers": [f"A package can carry at most {MAX_PACKAGE_SIGNERS} signers."]}
        )

    resolved: list[dict[str, Any]] = []
    emails: set[str] = set()
    keys: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValidationError(
                {"signers": [f"Signer at index {index} must be an object."]}
            )

        email = str(item.get("email") or "").strip().lower()
        if not email:
            raise ValidationError(
                {"signers": [f"Signer at index {index} needs an email address."]}
            )
        if email in emails:
            raise ValidationError(
                {"signers": ["Each signer needs a distinct email address."]}
            )
        emails.add(email)

        delivery = str(
            item.get("deliveryMethod")
            or item.get("delivery_method")
            or SignatureDeliveryMethod.EMAIL
        ).strip()
        if delivery not in SIGNATURE_DELIVERY_METHOD_CODES:
            raise ValidationError({"signers": ["Unknown delivery method."]})

        user = None
        raw_user = item.get("userId") or item.get("user_id")
        if raw_user not in (None, ""):
            user = User.objects.filter(pk=raw_user, is_active=True).first()
            if user is None:
                raise ValidationError(
                    {"signers": ["A named Hub signer could not be found."]}
                )
        if delivery == SignatureDeliveryMethod.HUB and user is None:
            raise ValidationError(
                {
                    "signers": [
                        "Hub delivery needs a Hub user. Choose the person or "
                        "switch that signer to an email link."
                    ]
                }
            )

        party = None
        raw_party = item.get("partyId") or item.get("party_id")
        if raw_party not in (None, ""):
            party = TransactionParty.objects.filter(
                public_id=_public_id(raw_party), transaction_id=tx.pk
            ).first()
            if party is None:
                raise ValidationError(
                    {"signers": ["A linked party is not on this transaction."]}
                )

        display_name = str(item.get("displayName") or item.get("display_name") or "")
        display_name = display_name.strip()
        if not display_name and user is not None:
            display_name = user.preferred_display_name()
        if not display_name:
            raise ValidationError(
                {"signers": [f"Signer at index {index} needs a display name."]}
            )

        role_label = str(item.get("roleLabel") or item.get("role_label") or "").strip()
        if not role_label:
            raise ValidationError(
                {"signers": [f"Signer at index {index} needs a role label."]}
            )

        try:
            routing_order = int(
                item.get("routingOrder") or item.get("routing_order") or 1
            )
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                {"signers": [f"Signer at index {index} has an invalid routing order."]}
            ) from exc
        if routing_order < 1:
            raise ValidationError({"signers": ["Routing order starts at 1."]})

        key = str(item.get("key") or item.get("publicId") or f"signer-{index}").strip()
        if key in keys:
            raise ValidationError({"signers": ["Each signer needs a distinct key."]})
        keys.add(key)

        resolved.append(
            {
                "key": key,
                "role_label": role_label[:64],
                "display_name": display_name[:255],
                "email": email,
                "delivery_method": delivery,
                "user": user,
                "party": party,
                "routing_order": routing_order,
            }
        )
    return resolved


# --------------------------------------------------------------------------- #
# Services
# --------------------------------------------------------------------------- #


@db_transaction.atomic
def create_draft_package(
    actor: User,
    transaction: Any,
    *,
    title: str,
    routing_mode: str = SignatureRoutingMode.ORDERED,
    expires_at: Any = None,
    expected_version: str = "",
) -> SignaturePackage:
    """Open an empty draft package on a deal the caller can manage."""
    tx = _writable_transaction(actor, transaction, expected_version)
    package = SignaturePackage(
        transaction=tx,
        title=_parse_title(title),
        routing_mode=_parse_routing_mode(routing_mode),
        expires_at=_parse_expires_at(expires_at),
        status=SignaturePackageStatus.DRAFT,
        created_by=actor,
    )
    package.full_clean(exclude={"created_by"})
    package.save()
    touch_transaction(tx)

    log_on_commit(
        "transaction.signature_package_created",
        actor=actor_from_user(actor),
        target=_audit_target(package),
        after={
            "package_id": str(package.public_id),
            "routing_mode": package.routing_mode,
            "expires_at": package.expires_at.isoformat()
            if package.expires_at
            else None,
        },
    )
    return package


@db_transaction.atomic
def replace_package_contents(
    actor: User,
    package: Any,
    *,
    documents: list[Any],
    signers: list[dict[str, Any]],
    fields: list[dict[str, Any]],
    title: Any = _UNSET,
    routing_mode: Any = _UNSET,
    expires_at: Any = _UNSET,
    expected_version: str = "",
) -> SignaturePackage:
    """Rewrite a draft package's settings, documents, signers, and field layout.

    Contents are replaced wholesale rather than patched: partial edits across
    three related tables produce layouts that reference deleted signers, and a
    draft has no signatures to preserve. Title, routing mode, and expiry are
    optional so the same call can save the whole draft the editor holds.
    """
    visible = load_package_for_reader(actor, package)
    tx = _writable_transaction(actor, visible.transaction, expected_version)
    locked = lock_package(visible.pk)
    if locked.status != SignaturePackageStatus.DRAFT:
        raise PackageNotDraft()

    settings_fields: list[str] = []
    if title is not _UNSET and title is not None:
        locked.title = _parse_title(title)
        settings_fields.append("title")
    if routing_mode is not _UNSET and routing_mode not in (None, ""):
        locked.routing_mode = _parse_routing_mode(routing_mode)
        settings_fields.append("routing_mode")
    if expires_at is not _UNSET:
        locked.expires_at = _parse_expires_at(expires_at)
        settings_fields.append("expires_at")
    if settings_fields:
        locked.save(update_fields=[*settings_fields, "updated_at"])

    resolved_documents = _resolve_documents(tx, documents)
    resolved_signers = _resolve_signers(tx, signers)

    page_counts = {row["key"]: row["page_count"] for row in resolved_documents}
    layout = normalize_package_fields(
        fields,
        signer_keys={row["key"] for row in resolved_signers},
        document_keys=set(page_counts),
        page_counts=page_counts,
    )

    required_keys = signer_keys_with_required_fields(layout)
    missing = [
        row["role_label"] for row in resolved_signers if row["key"] not in required_keys
    ]
    if missing:
        raise ValidationError(
            {
                "fields": [
                    "Every signer needs at least one required field. Missing: "
                    + ", ".join(sorted(missing))
                    + "."
                ]
            }
        )

    SignaturePackageField.objects.filter(package_id=locked.pk).delete()
    SignaturePackageSigner.objects.filter(package_id=locked.pk).delete()
    SignaturePackageDocument.objects.filter(package_id=locked.pk).delete()

    document_rows: dict[str, SignaturePackageDocument] = {}
    for row in resolved_documents:
        created = SignaturePackageDocument.objects.create(
            package=locked,
            version=row["version"],
            source_checksum=row["checksum"],
            page_count=row["page_count"],
            sort_order=row["sort_order"],
        )
        document_rows[row["key"]] = created

    signer_rows: dict[str, SignaturePackageSigner] = {}
    for row in resolved_signers:
        created_signer = SignaturePackageSigner.objects.create(
            package=locked,
            role_label=row["role_label"],
            display_name=row["display_name"],
            email=row["email"],
            delivery_method=row["delivery_method"],
            user=row["user"],
            party=row["party"],
            routing_order=row["routing_order"],
        )
        signer_rows[row["key"]] = created_signer

    SignaturePackageField.objects.bulk_create(
        [
            SignaturePackageField(
                package=locked,
                document=document_rows[item["documentKey"]],
                signer=signer_rows[item["signerKey"]],
                name=item["name"],
                field_type=item["type"],
                page=item["page"],
                x=item["x"],
                y=item["y"],
                w=item["w"],
                h=item["h"],
                required=item["required"],
            )
            for item in layout
        ]
    )

    touch_transaction(tx)
    locked.transaction = tx
    log_on_commit(
        "transaction.signature_package_contents_replaced",
        actor=actor_from_user(actor),
        target=_audit_target(locked),
        after={
            "package_id": str(locked.public_id),
            "document_count": len(document_rows),
            "signer_count": len(signer_rows),
            "field_count": len(layout),
        },
    )
    return locked


def _mark_documents_pending(package: SignaturePackage) -> int:
    """Flag every source version as awaiting signature (deal-document contract)."""
    version_ids = list(
        SignaturePackageDocument.objects.filter(package_id=package.pk).values_list(
            "version_id", flat=True
        )
    )
    if not version_ids:
        return 0
    return (
        TransactionDocumentVersion.objects.filter(pk__in=version_ids)
        .exclude(signature_status=DocumentSignatureStatus.SIGNED)
        .update(
            signature_status=DocumentSignatureStatus.PENDING,
            updated_at=timezone.now(),
        )
    )


def _release_pending_documents(package: SignaturePackage) -> int:
    """Undo the pending flag when a package ends without signatures."""
    version_ids = list(
        SignaturePackageDocument.objects.filter(package_id=package.pk).values_list(
            "version_id", flat=True
        )
    )
    if not version_ids:
        return 0
    return TransactionDocumentVersion.objects.filter(
        pk__in=version_ids, signature_status=DocumentSignatureStatus.PENDING
    ).update(
        signature_status=DocumentSignatureStatus.NONE,
        updated_at=timezone.now(),
    )


@db_transaction.atomic
def validate_and_send(
    actor: User,
    package: Any,
    *,
    expected_version: str = "",
) -> SignaturePackage:
    """Validate a draft, freeze the disclosure, and invite the first signers."""
    require_signing_cert_or_raise()

    visible = load_package_for_reader(actor, package)
    tx = _writable_transaction(actor, visible.transaction, expected_version)
    locked = lock_package(visible.pk)
    if locked.status != SignaturePackageStatus.DRAFT:
        raise PackageNotDraft()

    documents = list(
        SignaturePackageDocument.objects.filter(package_id=locked.pk).select_related(
            "version"
        )
    )
    if not documents:
        raise ValidationError({"documents": ["Add a document before sending."]})

    signers = list(SignaturePackageSigner.objects.filter(package_id=locked.pk))
    if not signers:
        raise ValidationError({"signers": ["Add a signer before sending."]})

    field_rows = list(
        SignaturePackageField.objects.filter(package_id=locked.pk).values(
            "signer_id", "required"
        )
    )
    with_required = {row["signer_id"] for row in field_rows if row["required"]}
    missing = [s.role_label for s in signers if s.pk not in with_required]
    if missing:
        raise ValidationError(
            {
                "fields": [
                    "Every signer needs at least one required field. Missing: "
                    + ", ".join(sorted(missing))
                    + "."
                ]
            }
        )

    for document in documents:
        version = document.version
        if not version.is_readable:
            raise ValidationError(
                {"documents": [f"“{version.display_name}” is no longer readable."]}
            )
        if checksum_of(_read_version_bytes(version)) != document.source_checksum:
            raise ValidationError(
                {
                    "documents": [
                        f"“{version.display_name}” changed since it was added. "
                        "Rebuild the package."
                    ]
                }
            )

    if locked.expires_at is not None and locked.expires_at <= timezone.now():
        raise ValidationError({"expiresAt": ["The expiry must be in the future."]})

    now = timezone.now()
    locked.disclosure_version = DISCLOSURE_VERSION
    locked.save(update_fields=["disclosure_version", "updated_at"])
    set_package_status(locked, SignaturePackageStatus.SENT, sent_at=now)
    _mark_documents_pending(locked)

    invite_signers(signers_for_initial_invite(locked), now=now)

    touch_transaction(tx)
    locked.transaction = tx
    publish_package_event(
        EVENT_PACKAGE_SENT,
        locked,
        actor_id=str(actor.pk),
        signer_count=str(len(signers)),
        document_count=str(len(documents)),
        routing_mode=locked.routing_mode,
    )
    log_on_commit(
        "transaction.signature_package_sent",
        actor=actor_from_user(actor),
        target=_audit_target(locked),
        after={
            "package_id": str(locked.public_id),
            "disclosure_version": locked.disclosure_version,
            "signer_count": len(signers),
            "document_count": len(documents),
        },
    )
    return locked


@db_transaction.atomic
def cancel_package(
    actor: User,
    package: Any,
    *,
    expected_version: str = "",
) -> SignaturePackage:
    """Withdraw a package that has not completed; links stop working at once."""
    visible = load_package_for_reader(actor, package)
    tx = _writable_transaction(actor, visible.transaction, expected_version)
    locked = lock_package(visible.pk)

    if locked.status == SignaturePackageStatus.COMPLETED:
        raise ValidationError(
            {"form": [str(_("A completed package cannot be cancelled."))]}
        )
    if locked.status == SignaturePackageStatus.CANCELLED:
        return locked

    now = timezone.now()
    set_package_status(locked, SignaturePackageStatus.CANCELLED, cancelled_at=now)
    invalidate_package_tokens(locked.pk, now=now)
    _release_pending_documents(locked)

    touch_transaction(tx)
    locked.transaction = tx
    publish_package_event(EVENT_PACKAGE_CANCELLED, locked, actor_id=str(actor.pk))
    log_on_commit(
        "transaction.signature_package_cancelled",
        actor=actor_from_user(actor),
        target=_audit_target(locked),
        after={"package_id": str(locked.public_id)},
    )
    return locked


__all__ = [
    "MAX_PACKAGE_DOCUMENTS",
    "MAX_PACKAGE_SIGNERS",
    "PackageNotDraft",
    "cancel_package",
    "create_draft_package",
    "load_package_for_reader",
    "replace_package_contents",
    "validate_and_send",
]
