"""Invite and reminder mail for transaction signature packages.

Hub signers get a path they must authenticate to open. External signers get a
one-time magic link; the raw token is passed in from the mint call and is
never read back out of the database, logged, or echoed into audit payloads.
Delivery failures are logged and never raise into the signing lifecycle.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.urls import NoReverseMatch, reverse

from apps.transactions.models import SignaturePackageSigner
from apps.transactions.taxonomy import SignatureDeliveryMethod

logger = logging.getLogger("apps.transactions")

#: Placeholder paths until the ceremony routes land in ``urls.py``.
HUB_CEREMONY_PATH = "/transactions/sign/{package_id}/"
MAGIC_LINK_PATH = "/sign/p/{token}/"

HUB_CEREMONY_ROUTE = "transaction_signature_ceremony"
MAGIC_LINK_ROUTE = "transaction_signature_magic_link"


def _site_base() -> str:
    return (getattr(settings, "SITE_BASE_URL", "") or "http://localhost:8000").rstrip(
        "/"
    )


def _absolute(path: str) -> str:
    if not path.startswith("/") or path.startswith("//"):
        return ""
    return f"{_site_base()}{path}"


def hub_ceremony_path(signer: SignaturePackageSigner) -> str:
    package_id = signer.package.public_id
    try:
        return reverse(HUB_CEREMONY_ROUTE, kwargs={"public_id": package_id})
    except NoReverseMatch:
        return HUB_CEREMONY_PATH.format(package_id=package_id)


def magic_link_path(raw_token: str) -> str:
    try:
        return reverse(MAGIC_LINK_ROUTE, kwargs={"token": raw_token})
    except NoReverseMatch:
        return MAGIC_LINK_PATH.format(token=raw_token)


def signing_url(signer: SignaturePackageSigner, *, raw_token: str = "") -> str:
    """Where this signer starts their ceremony, by delivery method."""
    if signer.delivery_method == SignatureDeliveryMethod.HUB:
        return _absolute(hub_ceremony_path(signer))
    if not raw_token:
        return ""
    return _absolute(magic_link_path(raw_token))


def _send(*, subject: str, body: str, to: str, signer_id: int, kind: str) -> None:
    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", None) or None,
            [to],
            fail_silently=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception("%s email failed signer_id=%s", kind, signer_id)


def _greeting(signer: SignaturePackageSigner) -> str:
    return (signer.display_name or "").strip() or "there"


def _recipient(signer: SignaturePackageSigner) -> str:
    return (signer.email or "").strip()


def send_signer_invite_email(
    signer: SignaturePackageSigner, *, raw_token: str = ""
) -> None:
    """First notice that a package is waiting on this signer."""
    email = _recipient(signer)
    if not email:
        logger.warning("signing invite skipped missing email signer_id=%s", signer.pk)
        return
    url = signing_url(signer, raw_token=raw_token)
    if not url:
        logger.warning("signing invite skipped missing link signer_id=%s", signer.pk)
        return

    package = signer.package
    subject = f"Signature requested: {package.title}"
    hub_note = (
        "Sign in to oNEST Hub and open the package to review and sign."
        if signer.delivery_method == SignatureDeliveryMethod.HUB
        else (
            "This link is personal to you, expires, and can only complete your "
            "own signature. Do not forward it."
        )
    )
    body = (
        f"Hello {_greeting(signer)},\n\n"
        f"You have been asked to sign “{package.title}” as "
        f"{signer.role_label}.\n\n"
        f"{url}\n\n"
        f"{hub_note}\n"
    )
    _send(
        subject=subject,
        body=body,
        to=email,
        signer_id=signer.pk,
        kind="signing invite",
    )


def send_signer_reminder_email(
    signer: SignaturePackageSigner, *, raw_token: str = "", reminder_day: int = 0
) -> None:
    """Cadence nudge for a signer who has not finished."""
    email = _recipient(signer)
    if not email:
        logger.warning("signing reminder skipped missing email signer_id=%s", signer.pk)
        return
    url = signing_url(signer, raw_token=raw_token)
    if not url:
        logger.warning("signing reminder skipped missing link signer_id=%s", signer.pk)
        return

    package = signer.package
    subject = f"Reminder: {package.title} is waiting for your signature"
    day_note = (
        f"It has been {reminder_day} days since the request was sent.\n\n"
        if reminder_day
        else ""
    )
    body = (
        f"Hello {_greeting(signer)},\n\n"
        f"“{package.title}” is still waiting for your signature as "
        f"{signer.role_label}.\n\n"
        f"{day_note}"
        f"{url}\n"
    )
    _send(
        subject=subject,
        body=body,
        to=email,
        signer_id=signer.pk,
        kind="signing reminder",
    )


def send_package_completed_email(signer: SignaturePackageSigner) -> None:
    """Close the loop once every party has signed and artifacts are sealed."""
    email = _recipient(signer)
    if not email:
        return
    package = signer.package
    body = (
        f"Hello {_greeting(signer)},\n\n"
        f"All parties have signed “{package.title}”. The signed documents and "
        "a certificate of completion are stored with the transaction record.\n\n"
        "Contact the brokerage if you need a copy.\n"
    )
    _send(
        subject=f"Completed: {package.title}",
        body=body,
        to=email,
        signer_id=signer.pk,
        kind="signing completion",
    )


__all__ = [
    "HUB_CEREMONY_PATH",
    "MAGIC_LINK_PATH",
    "hub_ceremony_path",
    "magic_link_path",
    "send_package_completed_email",
    "send_signer_invite_email",
    "send_signer_reminder_email",
    "signing_url",
]
