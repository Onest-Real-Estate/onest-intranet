"""Status ownership for signature packages and their signers.

``SignaturePackage.save`` refuses a status write that does not come from here,
so this module is the only place a package changes state. Routing lives here
too: which signers are eligible right now, who gets invited next, and when the
package is finished enough to hand to the finalize task.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Min, QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.events import publish as publish_event
from apps.transactions.models import (
    SignaturePackage,
    SignaturePackageSigner,
)
from apps.transactions.signing.tokens import (
    invalidate_package_tokens,
    invalidate_signer_tokens,
    issue_access_token,
)
from apps.transactions.taxonomy import (
    ELIGIBLE_SIGNATURE_SIGNER_STATUSES,
    OPEN_SIGNATURE_PACKAGE_STATUSES,
    SIGNATURE_PACKAGE_STATUS_CODES,
    SignatureDeliveryMethod,
    SignaturePackageStatus,
    SignatureRoutingMode,
    SignatureSignerStatus,
)

logger = logging.getLogger("apps.transactions")

# Domain event names published by the signing services.
EVENT_PACKAGE_SENT = "transaction.signature_package_sent"
EVENT_PACKAGE_COMPLETED = "transaction.signature_package_completed"
EVENT_PACKAGE_DECLINED = "transaction.signature_package_declined"
EVENT_PACKAGE_CANCELLED = "transaction.signature_package_cancelled"
EVENT_PACKAGE_EXPIRED = "transaction.signature_package_expired"
EVENT_SIGNER_SIGNED = "transaction.signature_signed"
EVENT_SIGNATURE_REMINDER = "transaction.signature_reminder"

#: Signer states that still owe the package an outcome.
UNFINISHED_SIGNER_STATUSES = frozenset(
    {
        SignatureSignerStatus.PENDING,
        SignatureSignerStatus.INVITED,
        SignatureSignerStatus.VIEWED,
    }
)


class PackageNotOpen(ValidationError):
    """The package is not accepting signatures right now."""

    def __init__(self, message: str | None = None):
        super().__init__(
            {
                "form": [
                    str(
                        message
                        or _(
                            "This signature package is no longer open for "
                            "signing. Refresh for the current status."
                        )
                    )
                ]
            }
        )


class SignerNotEligible(ValidationError):
    """A real signer on an open package whose turn has not arrived."""

    def __init__(self, message: str | None = None):
        super().__init__(
            {
                "form": [
                    str(
                        message
                        or _(
                            "It is not your turn to sign yet. You will be "
                            "notified when the package reaches you."
                        )
                    )
                ]
            }
        )


def lock_package(package_id: int) -> SignaturePackage:
    """Row lock without joining nullable FKs (PostgreSQL FOR UPDATE rule)."""
    return SignaturePackage.objects.select_for_update(of=("self",)).get(pk=package_id)


def set_package_status(
    package: SignaturePackage,
    status: str,
    **timestamp_fields: Any,
) -> SignaturePackage:
    """The single writer of ``SignaturePackage.status``."""
    if status not in SIGNATURE_PACKAGE_STATUS_CODES:
        raise ValidationError({"status": [f"Unknown package status {status!r}."]})
    if package.status == status and not timestamp_fields:
        return package

    package.status = status
    update_fields = ["status", "updated_at"]
    for name, value in timestamp_fields.items():
        setattr(package, name, value)
        update_fields.append(name)

    package._allow_status_write = True
    try:
        package.save(update_fields=update_fields)
    finally:
        package._allow_status_write = False
    return package


def is_expired(package: SignaturePackage, *, now=None) -> bool:
    if package.expires_at is None:
        return False
    return package.expires_at <= (now or timezone.now())


def assert_package_open(package: SignaturePackage, *, now=None) -> None:
    """Refuse ceremony work on a package that is not sent/in progress."""
    if package.status not in OPEN_SIGNATURE_PACKAGE_STATUSES:
        raise PackageNotOpen()
    if is_expired(package, now=now):
        raise PackageNotOpen(
            _("This signature package expired. Ask the brokerage to resend it.")
        )


def signers_queryset(package: SignaturePackage) -> QuerySet[SignaturePackageSigner]:
    return SignaturePackageSigner.objects.filter(package_id=package.pk).order_by(
        "routing_order", "pk"
    )


def eligible_signers_queryset(
    package: SignaturePackage,
) -> QuerySet[SignaturePackageSigner]:
    """Signers who may open the ceremony right now.

    Parallel packages expose every invited or viewed signer at once. Ordered
    packages expose only the lowest outstanding routing order, so a later
    party cannot jump the queue.
    """
    qs = SignaturePackageSigner.objects.filter(
        package_id=package.pk,
        status__in=ELIGIBLE_SIGNATURE_SIGNER_STATUSES,
    )
    if package.routing_mode == SignatureRoutingMode.ORDERED:
        current = qs.aggregate(low=Min("routing_order")).get("low")
        if current is None:
            return qs.none()
        qs = qs.filter(routing_order=current)
    return qs.order_by("routing_order", "pk")


def is_signer_eligible(
    package: SignaturePackage, signer: SignaturePackageSigner
) -> bool:
    return eligible_signers_queryset(package).filter(pk=signer.pk).exists()


def next_routing_order(package: SignaturePackage) -> int | None:
    """Lowest routing order that still owes an outcome, or ``None`` when done."""
    return (
        SignaturePackageSigner.objects.filter(
            package_id=package.pk, status__in=UNFINISHED_SIGNER_STATUSES
        )
        .aggregate(low=Min("routing_order"))
        .get("low")
    )


def all_signers_signed(package: SignaturePackage) -> bool:
    return (
        not SignaturePackageSigner.objects.filter(package_id=package.pk)
        .exclude(status=SignatureSignerStatus.SIGNED)
        .exists()
    )


def queue_finalize(package_id: int) -> None:
    """Hand a fully signed package to the async finalize task after commit."""

    def _dispatch() -> None:
        from apps.transactions.tasks import finalize_signature_package

        try:
            finalize_signature_package.delay(package_id)
        except Exception:  # noqa: BLE001
            # The package row is already COMPLETED-eligible; ops can replay.
            logger.exception(
                "transactions: finalize dispatch failed package_id=%s", package_id
            )

    transaction.on_commit(_dispatch)


def _queue_invite_email(signer_id: int, raw_token: str) -> None:
    def _send() -> None:
        from apps.transactions.signing.emails import send_signer_invite_email

        signer = (
            SignaturePackageSigner.objects.select_related("package", "user")
            .filter(pk=signer_id)
            .first()
        )
        if signer is None:
            return
        send_signer_invite_email(signer, raw_token=raw_token)

    transaction.on_commit(_send)


def mark_signer_invited(
    signer: SignaturePackageSigner, *, now=None, notify: bool = True
) -> SignaturePackageSigner:
    """Move a pending signer to invited, minting a link for email delivery."""
    if signer.status != SignatureSignerStatus.PENDING:
        return signer
    moment = now or timezone.now()
    signer.status = SignatureSignerStatus.INVITED
    signer.invited_at = moment
    signer.save(update_fields=["status", "invited_at", "updated_at"])

    raw_token = ""
    if signer.delivery_method == SignatureDeliveryMethod.EMAIL:
        _token, raw_token = issue_access_token(signer)
    if notify:
        _queue_invite_email(signer.pk, raw_token)
    return signer


def invite_signers(
    signers: list[SignaturePackageSigner] | QuerySet[SignaturePackageSigner],
    *,
    now=None,
    notify: bool = True,
) -> int:
    count = 0
    for signer in signers:
        before = signer.status
        mark_signer_invited(signer, now=now, notify=notify)
        if signer.status != before:
            count += 1
    return count


def signers_for_initial_invite(
    package: SignaturePackage,
) -> QuerySet[SignaturePackageSigner]:
    """Who hears about the package the moment it is sent."""
    qs = SignaturePackageSigner.objects.filter(
        package_id=package.pk, status=SignatureSignerStatus.PENDING
    )
    if package.routing_mode == SignatureRoutingMode.ORDERED:
        current = qs.aggregate(low=Min("routing_order")).get("low")
        if current is None:
            return qs.none()
        qs = qs.filter(routing_order=current)
    return qs.order_by("routing_order", "pk")


def mark_viewed(signer: SignaturePackageSigner, *, now=None) -> SignaturePackageSigner:
    """Record the first ceremony open; later opens do not move the clock."""
    moment = now or timezone.now()
    update_fields: list[str] = []
    if signer.status == SignatureSignerStatus.INVITED:
        signer.status = SignatureSignerStatus.VIEWED
        update_fields.append("status")
    if signer.viewed_at is None:
        signer.viewed_at = moment
        update_fields.append("viewed_at")
    if update_fields:
        signer.save(update_fields=[*update_fields, "updated_at"])
    return signer


def advance_routing(package: SignaturePackage, *, now=None, notify: bool = True) -> int:
    """Invite the next ordered group once the current one is done."""
    if package.routing_mode != SignatureRoutingMode.ORDERED:
        return 0
    order = next_routing_order(package)
    if order is None:
        return 0
    pending = SignaturePackageSigner.objects.filter(
        package_id=package.pk,
        status=SignatureSignerStatus.PENDING,
        routing_order=order,
    ).order_by("pk")
    return invite_signers(pending, now=now, notify=notify)


def _event_payload(package: SignaturePackage, **extra: Any) -> dict[str, Any]:
    tx = package.transaction
    payload: dict[str, Any] = {
        "package_id": str(package.public_id),
        "transaction_id": str(tx.public_id),
        "office_id": str(tx.office_pk or ""),
        "occurred_at": timezone.now().isoformat(),
    }
    payload.update(extra)
    return payload


def publish_package_event(
    name: str, package: SignaturePackage, *, actor_id: str = "system", **extra: Any
) -> None:
    publish_event(
        name,
        actor_id=actor_id,
        subject=str(package.public_id),
        payload=_event_payload(package, **extra),
    )


def mark_signed(
    signer: SignaturePackageSigner,
    *,
    package: SignaturePackage | None = None,
    now=None,
    notify: bool = True,
) -> SignaturePackage:
    """Record one signer's completion and move the package forward.

    Caller must already hold the package row lock. When the last signer lands,
    finalization is queued after commit; the package only becomes ``completed``
    once :func:`apps.transactions.signing.finalize.finalize_package` has stored
    the sealed artifacts.
    """
    moment = now or timezone.now()
    locked = package if package is not None else lock_package(signer.package_id)

    if signer.status != SignatureSignerStatus.SIGNED:
        signer.status = SignatureSignerStatus.SIGNED
        signer.signed_at = moment
        signer.save(update_fields=["status", "signed_at", "updated_at"])
    invalidate_signer_tokens(signer, now=moment)

    publish_package_event(
        EVENT_SIGNER_SIGNED,
        locked,
        actor_id=str(signer.user_id or "external"),
        signer_id=str(signer.public_id),
        routing_order=str(signer.routing_order),
    )

    if all_signers_signed(locked):
        queue_finalize(locked.pk)
        return locked

    if locked.status != SignaturePackageStatus.IN_PROGRESS:
        set_package_status(locked, SignaturePackageStatus.IN_PROGRESS)
    advance_routing(locked, now=moment, notify=notify)
    return locked


def mark_declined(
    signer: SignaturePackageSigner,
    *,
    package: SignaturePackage | None = None,
    reason: str = "",
    now=None,
) -> SignaturePackage:
    """One refusal ends the package for everyone."""
    moment = now or timezone.now()
    locked = package if package is not None else lock_package(signer.package_id)

    if signer.status != SignatureSignerStatus.DECLINED:
        signer.status = SignatureSignerStatus.DECLINED
        signer.declined_at = moment
        signer.decline_reason = (reason or "")[:255]
        signer.save(
            update_fields=[
                "status",
                "declined_at",
                "decline_reason",
                "updated_at",
            ]
        )

    invalidate_package_tokens(locked.pk, now=moment)
    if locked.status not in {
        SignaturePackageStatus.DECLINED,
        SignaturePackageStatus.COMPLETED,
    }:
        set_package_status(locked, SignaturePackageStatus.DECLINED)
    publish_package_event(
        EVENT_PACKAGE_DECLINED,
        locked,
        actor_id=str(signer.user_id or "external"),
        signer_id=str(signer.public_id),
    )
    return locked


def expire_due_packages(*, now=None, limit: int = 200) -> int:
    """Beat-safe expiry for open packages past ``expires_at``."""
    moment = now or timezone.now()
    due = (
        SignaturePackage.objects.select_related("transaction")
        .filter(
            status__in=OPEN_SIGNATURE_PACKAGE_STATUSES,
            expires_at__isnull=False,
            expires_at__lte=moment,
        )
        .order_by("pk")[:limit]
    )
    expired = 0
    for package in due:
        with transaction.atomic():
            locked = lock_package(package.pk)
            if locked.status not in OPEN_SIGNATURE_PACKAGE_STATUSES:
                continue
            if locked.expires_at is None or locked.expires_at > moment:
                continue
            set_package_status(locked, SignaturePackageStatus.EXPIRED)
            SignaturePackageSigner.objects.filter(
                package_id=locked.pk, status__in=UNFINISHED_SIGNER_STATUSES
            ).update(status=SignatureSignerStatus.EXPIRED, updated_at=moment)
            invalidate_package_tokens(locked.pk, now=moment)
            locked.transaction = package.transaction
            publish_package_event(EVENT_PACKAGE_EXPIRED, locked)
            expired += 1
    if expired:
        logger.info("transactions: signature packages expired=%s", expired)
    return expired


__all__ = [
    "EVENT_PACKAGE_CANCELLED",
    "EVENT_PACKAGE_COMPLETED",
    "EVENT_PACKAGE_DECLINED",
    "EVENT_PACKAGE_EXPIRED",
    "EVENT_PACKAGE_SENT",
    "EVENT_SIGNATURE_REMINDER",
    "EVENT_SIGNER_SIGNED",
    "PackageNotOpen",
    "SignerNotEligible",
    "advance_routing",
    "all_signers_signed",
    "assert_package_open",
    "eligible_signers_queryset",
    "expire_due_packages",
    "invite_signers",
    "is_expired",
    "is_signer_eligible",
    "lock_package",
    "mark_declined",
    "mark_signed",
    "mark_signer_invited",
    "mark_viewed",
    "next_routing_order",
    "publish_package_event",
    "queue_finalize",
    "set_package_status",
    "signers_for_initial_invite",
    "signers_queryset",
]
